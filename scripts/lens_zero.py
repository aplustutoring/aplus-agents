"""Lens 0 — redundancy gatekeeper (decisions #12, #13).

For each candidate topic, compute embedding similarity vs the corpus of
PUBLISHED blogs on wetutorathome.com. Reject anything with cosine similarity
>= REDUNDANCY_THRESHOLD against any prior published post.

- Embeddings: OpenAI text-embedding-3-small (1536-dim, unit-normalized)
- Threshold: 0.85 cosine similarity (decision #12)
- Corpus: HubSpot blog posts with state=PUBLISHED only (decision #13)
- Cache: state/blog-embeddings.json keyed by post id; only newly-published posts
  get re-embedded each run, so this stays cheap.

Refresh mode (decision #14) is the caller's responsibility — set bypass=True
to skip the check entirely.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
EMBEDDINGS_CACHE = STATE_DIR / "blog-embeddings.json"

HUBSPOT_BASE = "https://api.hubapi.com"
BLOG_ID = "12422338726"
EMBEDDING_MODEL = "text-embedding-3-small"
REDUNDANCY_THRESHOLD = 0.85
EMBED_BATCH_SIZE = 100
HUBSPOT_PAGE_LIMIT = 100

logger = logging.getLogger(__name__)


# ---------- data shapes ----------

@dataclass
class PublishedPost:
    id: str
    title: str
    slug: str
    publish_date: Optional[str]
    embedding: Optional[list[float]] = None

    @property
    def embed_text(self) -> str:
        return self.title.strip()


@dataclass
class RedundancyVerdict:
    candidate_text: str
    is_redundant: bool
    max_similarity: float
    matched_post: Optional[PublishedPost] = None
    threshold: float = REDUNDANCY_THRESHOLD
    bypassed: bool = False


# ---------- HubSpot fetch ----------

def _hubspot_token() -> str:
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        raise RuntimeError("HUBSPOT_PRIVATE_APP_TOKEN not set")
    return token


def fetch_published_posts() -> list[PublishedPost]:
    """Paginate through every PUBLISHED post on the wetutorathome.com blog."""
    posts: list[PublishedPost] = []
    headers = {"Authorization": f"Bearer {_hubspot_token()}"}
    after: Optional[str] = None

    while True:
        params: dict = {
            "limit": HUBSPOT_PAGE_LIMIT,
            "contentGroupId": BLOG_ID,
            "state": "PUBLISHED",
            "properties": "id,name,slug,publishDate,htmlTitle",
        }
        if after:
            params["after"] = after
        r = requests.get(
            f"{HUBSPOT_BASE}/cms/v3/blogs/posts",
            headers=headers,
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        payload = r.json()
        for result in payload.get("results", []):
            posts.append(
                PublishedPost(
                    id=str(result.get("id")),
                    title=(result.get("htmlTitle") or result.get("name") or "").strip(),
                    slug=(result.get("slug") or "").strip(),
                    publish_date=result.get("publishDate"),
                )
            )
        paging = (payload.get("paging") or {}).get("next") or {}
        after = paging.get("after")
        if not after:
            break

    logger.info("hubspot_published_count count=%d", len(posts))
    return posts


# ---------- embedding cache ----------

def _load_cache() -> dict[str, dict]:
    if not EMBEDDINGS_CACHE.is_file():
        return {}
    try:
        return json.loads(EMBEDDINGS_CACHE.read_text())
    except (json.JSONDecodeError, ValueError):
        logger.warning("embedding cache unreadable, starting fresh")
        return {}


def _save_cache(cache: dict[str, dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    EMBEDDINGS_CACHE.write_text(json.dumps(cache, indent=2))


def _openai_client() -> OpenAI:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI()


def _embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in resp.data]


def embed_posts(posts: list[PublishedPost], *, client: Optional[OpenAI] = None) -> list[PublishedPost]:
    """Fill in .embedding on each post; reuse cache where possible."""
    cache = _load_cache()
    client = client or _openai_client()

    need_embed: list[PublishedPost] = []
    for post in posts:
        cached = cache.get(post.id)
        if cached and cached.get("title") == post.title:
            post.embedding = cached["embedding"]
        else:
            need_embed.append(post)

    if need_embed:
        logger.info("embedding_uncached count=%d (cache hits=%d)", len(need_embed), len(posts) - len(need_embed))
        for i in range(0, len(need_embed), EMBED_BATCH_SIZE):
            batch = need_embed[i : i + EMBED_BATCH_SIZE]
            vectors = _embed_batch(client, [p.embed_text for p in batch])
            for post, vec in zip(batch, vectors):
                post.embedding = vec
                cache[post.id] = {"title": post.title, "embedding": vec}
        _save_cache(cache)
    else:
        logger.info("embedding_all_cached count=%d", len(posts))

    return posts


# ---------- similarity ----------

def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity. OpenAI embeddings are already unit-normalized, but
    we divide by norms anyway in case the input came from a different source."""
    if not a or not b:
        return 0.0
    na, nb = _norm(a), _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return _dot(a, b) / (na * nb)


def check_redundancy(
    candidate_text: str,
    *,
    posts: Optional[list[PublishedPost]] = None,
    bypass: bool = False,
    threshold: float = REDUNDANCY_THRESHOLD,
    client: Optional[OpenAI] = None,
) -> RedundancyVerdict:
    """Check whether candidate_text is too similar to any published post.

    bypass=True returns is_redundant=False without making any API calls
    (refresh-mode override per decision #14).
    """
    if bypass:
        return RedundancyVerdict(
            candidate_text=candidate_text,
            is_redundant=False,
            max_similarity=0.0,
            bypassed=True,
            threshold=threshold,
        )

    client = client or _openai_client()
    if posts is None:
        posts = fetch_published_posts()
    posts = embed_posts(posts, client=client)

    candidate_vec = _embed_batch(client, [candidate_text])[0]

    best_post: Optional[PublishedPost] = None
    best_sim = 0.0
    for post in posts:
        if not post.embedding:
            continue
        sim = cosine_similarity(candidate_vec, post.embedding)
        if sim > best_sim:
            best_sim = sim
            best_post = post

    return RedundancyVerdict(
        candidate_text=candidate_text,
        is_redundant=best_sim >= threshold,
        max_similarity=best_sim,
        matched_post=best_post,
        threshold=threshold,
    )


def check_many(
    candidates: Iterable[str],
    *,
    bypass: bool = False,
    threshold: float = REDUNDANCY_THRESHOLD,
) -> list[RedundancyVerdict]:
    """Batched variant — fetches posts and candidate embeddings once."""
    candidates = list(candidates)
    if not candidates:
        return []
    if bypass:
        return [
            RedundancyVerdict(c, False, 0.0, bypassed=True, threshold=threshold)
            for c in candidates
        ]

    client = _openai_client()
    posts = embed_posts(fetch_published_posts(), client=client)
    candidate_vecs = _embed_batch(client, candidates)

    verdicts = []
    for text, vec in zip(candidates, candidate_vecs):
        best_post = None
        best_sim = 0.0
        for post in posts:
            if not post.embedding:
                continue
            sim = cosine_similarity(vec, post.embedding)
            if sim > best_sim:
                best_sim = sim
                best_post = post
        verdicts.append(
            RedundancyVerdict(
                candidate_text=text,
                is_redundant=best_sim >= threshold,
                max_similarity=best_sim,
                matched_post=best_post,
                threshold=threshold,
            )
        )
    return verdicts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("=== cosine sanity ===")
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    c = [0.7071, 0.7071, 0.0]
    assert abs(cosine_similarity(a, a) - 1.0) < 1e-6
    assert abs(cosine_similarity(a, b)) < 1e-6
    assert abs(cosine_similarity(a, c) - 0.7071) < 1e-3
    print("OK")

    print("\n=== bypass mode (no API calls) ===")
    v = check_redundancy("Charter school tutoring ROI guide", bypass=True)
    assert v.bypassed is True
    assert v.is_redundant is False
    print(f"bypass verdict: redundant={v.is_redundant} bypassed={v.bypassed}")

    print("\n=== live HubSpot fetch + OpenAI embed (costs ~1 cent) ===")
    candidate = "Charter school tutoring ROI guide for directors weighing intervention spend in 2026"
    verdict = check_redundancy(candidate)
    print(f"candidate: {verdict.candidate_text!r}")
    print(f"redundant: {verdict.is_redundant} (threshold {verdict.threshold})")
    print(f"max_similarity: {verdict.max_similarity:.4f}")
    if verdict.matched_post:
        print(f"closest post: {verdict.matched_post.title!r}")
        print(f"closest slug: {verdict.matched_post.slug}")
    print("ALL ASSERTIONS PASSED")

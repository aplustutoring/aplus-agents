#!/usr/bin/env python3
"""Weekly blog performance scorecard.

Reads the posts the content engine has published (HubSpot post ids from
state/history.json's content_build records), pulls each post's live URL + state
from the HubSpot CMS, fetches page analytics (views/visits) over a rolling window,
and posts a ranked scorecard to Slack.

Notes:
- A post still in DRAFT has no traffic yet — it's shown as 'draft (not published)'.
- Page analytics need the HubSpot private-app token to have a CMS/traffic
  analytics read scope: `cms-analytics-api-access` or `traffic-analytics-api-access`.
  (NOT "business-intelligence" — that grouping does not grant this endpoint.)
  If it's missing, the scorecard still posts (listing the posts) with an
  'add analytics scope' note instead of crashing.

Usage:
    python3 scripts/b2b/blog-metrics.py                 # post scorecard to Slack
    python3 scripts/b2b/blog-metrics.py --days 30 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys as _sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "shared"))
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "b2b"))

import requests
from dotenv import load_dotenv

from state import read_history

load_dotenv(override=True)
logger = logging.getLogger(__name__)

HUBSPOT_BASE = "https://api.hubapi.com"
PORTAL_ID = "6312752"
CHANNEL = os.environ.get("METRICS_CHANNEL", "#weekly-content-ready")
PT = timezone(timedelta(hours=-7), name="PT")


def _hs_headers() -> dict:
    tok = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not tok:
        raise RuntimeError("HUBSPOT_PRIVATE_APP_TOKEN not set")
    return {"Authorization": f"Bearer {tok}"}


def recent_posts(limit: int = 12) -> list[dict]:
    """Distinct content-engine posts (most recent first) from history."""
    hist = read_history()
    runs = hist.get("runs", []) if isinstance(hist, dict) else (hist or [])
    seen: set[str] = set()
    posts: list[dict] = []
    for r in reversed(runs):
        if not isinstance(r, dict) or r.get("kind") != "content_build":
            continue
        pid = r.get("hubspot_post_id")
        if not pid or str(pid) in seen:
            continue
        seen.add(str(pid))
        posts.append({"post_id": str(pid), "post_date": r.get("post_date"), "headline": r.get("headline", "")})
        if len(posts) >= limit:
            break
    return posts


def get_post(post_id: str) -> "dict | None":
    """CMS post detail: name, url, slug, state, publishDate."""
    try:
        r = requests.get(f"{HUBSPOT_BASE}/cms/v3/blogs/posts/{post_id}", headers=_hs_headers(), timeout=30)
        if r.status_code != 200:
            logger.warning("get_post %s -> %s", post_id, r.status_code)
            return None
        d = r.json()
        return {"name": d.get("name"), "url": d.get("url") or d.get("absoluteUrl"),
                "slug": d.get("slug"), "state": d.get("state"), "publish_date": d.get("publishDate")}
    except Exception as e:
        logger.warning("get_post %s failed: %s", post_id, e)
        return None


def fetch_page_analytics(days: int) -> "dict | None":
    """Per-page totals keyed by URL/path. Returns None if the analytics scope is
    missing or the call fails (caller degrades gracefully)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    try:
        r = requests.get(
            f"{HUBSPOT_BASE}/analytics/v2/reports/pages/total",
            headers=_hs_headers(),
            params={"start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d")},
            timeout=60,
        )
        if r.status_code == 403:
            logger.warning("analytics 403 — token missing scope: add cms-analytics-api-access "
                           "or traffic-analytics-api-access to the private app")
            return None
        if r.status_code != 200:
            logger.warning("analytics %s: %s", r.status_code, r.text[:200])
            return None
        return r.json()
    except Exception as e:
        logger.warning("analytics fetch failed: %s", e)
        return None


def _metrics_for(url: str, slug: str, analytics: dict) -> dict:
    """Match a post's url/slug against the analytics payload (keyed by page URL or
    a breakdowns list) and return {views, visits}."""
    key = (slug or url or "").rstrip("/").lower()
    if not key or not analytics:
        return {"views": 0, "visits": 0}

    def _row(d: dict) -> dict:
        return {"views": d.get("rawViews") or d.get("pageViews") or 0, "visits": d.get("visits") or 0}

    # Shape A: { "<page url>": {rawViews, visits, ...}, ... }
    for page, vals in analytics.items() if isinstance(analytics, dict) else []:
        if isinstance(vals, dict) and key.split("/")[-1] in str(page).lower():
            return _row(vals)
    # Shape B: { "breakdowns": [ {breakdown: "<url>", rawViews, visits}, ... ] }
    for row in (analytics.get("breakdowns", []) if isinstance(analytics, dict) else []):
        if isinstance(row, dict) and key.split("/")[-1] in str(row.get("breakdown", "")).lower():
            return _row(row)
    return {"views": 0, "visits": 0}


def build_scorecard(days: int) -> str:
    posts = recent_posts()
    if not posts:
        return ":bar_chart: *Blog performance* — no published posts tracked yet."

    analytics = fetch_page_analytics(days)
    rows = []
    for p in posts:
        detail = get_post(p["post_id"]) or {}
        state = (detail.get("state") or "").upper()
        edit_url = f"https://app.hubspot.com/blog/{PORTAL_ID}/editor/{p['post_id']}/content"
        m = _metrics_for(detail.get("url", ""), detail.get("slug", ""), analytics or {})
        rows.append({
            "headline": (p["headline"] or detail.get("name") or "")[:60],
            "post_date": p.get("post_date"),
            "edit_url": edit_url,
            "published": state in ("PUBLISHED", "SCHEDULED"),
            "views": m["views"], "visits": m["visits"],
        })

    rows.sort(key=lambda r: r["views"], reverse=True)
    lines = [f":bar_chart: *Blog performance — last {days} days*"]
    if analytics is None:
        lines.append(":warning: HubSpot analytics scope not enabled — add `cms-analytics-api-access` (or `traffic-analytics-api-access`) to the private app to populate views. Listing posts for now.")
    for i, r in enumerate(rows, 1):
        medal = {1: ":first_place_medal:", 2: ":second_place_medal:", 3: ":third_place_medal:"}.get(i, f"{i}.")
        status = "" if r["published"] else "  _(draft — not published yet)_"
        metric = f"{r['views']} views · {r['visits']} visits" if analytics is not None else "metrics pending scope"
        lines.append(f"{medal} <{r['edit_url']}|{r['headline']}> — {metric} _(post {r['post_date']})_{status}")
    return "\n".join(lines)


def post_to_slack(text: str) -> bool:
    tok = os.environ.get("SLACK_BOT_TOKEN")
    if not tok:
        logger.warning("SLACK_BOT_TOKEN not set; printing scorecard instead")
        print(text)
        return False
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {tok}"},
        json={"channel": CHANNEL, "text": text, "mrkdwn": True, "unfurl_links": False},
        timeout=30,
    )
    ok = r.json().get("ok")
    if not ok:
        logger.warning("slack post failed: %s", r.json().get("error"))
    return bool(ok)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Weekly blog performance scorecard -> Slack")
    ap.add_argument("--days", type=int, default=30, help="rolling window in days (default 30)")
    ap.add_argument("--dry-run", action="store_true", help="print the scorecard, do not post to Slack")
    args = ap.parse_args()
    scorecard = build_scorecard(args.days)
    if args.dry_run:
        print(scorecard)
        return 0
    post_to_slack(scorecard)
    print(scorecard)
    return 0


if __name__ == "__main__":
    sys.exit(main())

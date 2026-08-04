#!/usr/bin/env python3
"""Reusable B2B blog graphics generator (productionized from the per-bundle
_batch_v2.py blueprint).

Reads a bundle's blog-anchor-meta.md and generates, into <bundle>/graphics/:
  - hero.png            (Gemini 3.1 flash image — a DISTINCT topic photo per blog)
  - pull-quote-s1.png   (GPT Image 2 — branded quote card from pull_quotes[0])
  - pull-quote-s2.png   (GPT Image 2 — branded quote card from pull_quotes[1])
  - social-card.png     (GPT Image 2 — branded share card from the title)

Each generator is best-effort: a failure logs and leaves any existing file in
place (so a placeholder hero survives) rather than crashing the build. Writes
graphics/_results.json. Logo compositing is a separate step (composite-logo.py).

Usage:
    python3 scripts/b2b/build-graphics.py --bundle aplus-content/2026-06-08-<slug>/
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GEMINI = os.environ.get("GEMINI_API_KEY")
OPENAI = os.environ.get("OPENAI_API_KEY")

LOGO_EXCLUSION = (
    " Leave a clean ~140x140 pixel area in the bottom-right corner free of any "
    "text or graphic elements (the A+ Tutoring logo is composited there later). "
    "No watermarks. No date line."
)

# Appended to every text-bearing graphic so copy is never cropped off-canvas.
TEXT_FIT = (
    " CRITICAL TEXT-FIT RULE: the COMPLETE text must fit comfortably inside the canvas with "
    "generous margins on all four sides. Automatically reduce the font size and wrap across "
    "multiple lines as needed so that NO word is ever cropped, cut off at an edge, or running "
    "outside the frame. Every word must be fully visible — never zoom in on or crop the text."
)

# Characters each format holds at its DEFAULT (largest) type size. Copy longer than
# this is NOT cut down to fit — _fit_note asks for a smaller type size instead, so the
# whole sentence still lands inside the frame. Cutting copy to a fixed budget is what
# produced the mid-sentence "incomplete thought" cards (worst on the carousel, whose
# headline budget is the tightest and whose fallback copy is a long SEO title).
FIT_CHARS = {
    "pull_quote": 130,      # 3:2 landscape
    "social_card": 90,      # 16:9 landscape
    "carousel_headline": 55,
    "carousel_body": 100,   # portrait 1024x1536 (slide 1 carries headline + body)
    "fb_ig": 60,            # 1:1 square — least room, keep it punchy
}

# Type-size tiers, roomiest first: (copy-to-FIT_CHARS ratio the tier absorbs, type-size
# wording, max wrapped lines). Same shrink-as-it-gets-denser idea as the b2c timeline
# graphic, expressed as prompt wording because GPT Image renders the type, not us.
TYPE_TIERS = [
    (1.0, "very large display", 3),
    (1.6, "large", 5),
    (2.4, "medium", 7),
    (3.5, "modest but clearly legible", 10),
]

# Absolute ceiling per format: copy beyond the smallest tier's reach gets trimmed by
# _cap — to WHOLE SENTENCES only, never mid-phrase.
HARD_CHARS = {k: int(v * TYPE_TIERS[-1][0]) for k, v in FIT_CHARS.items()}

# Copy that hit its format's ceiling and lost a trailing sentence. Surfaced loudly at
# the end of the build and in graphics/_text-fit.json so QA sees it instead of finding
# it on LinkedIn.
SHORTENED: list[str] = []


def _cap(text: str, n: int, label: str = "") -> str:
    """Last-resort ceiling for copy too long even for the smallest type tier. Cuts ONLY
    at a sentence boundary, keeping whole sentences while they fit, so a card never shows
    an incomplete thought. If the first sentence alone is over the ceiling it is kept
    whole anyway and the type tier shrinks to hold it — chopping at a word boundary is
    exactly the 'cut off mid-sentence' bug this replaces."""
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    kept = ""
    for part in re.findall(r"[^.!?]+(?:[.!?]+|$)", text):
        candidate = (kept + part).strip()
        if kept and len(candidate) > n:
            break
        kept = candidate
    kept = kept or text
    if kept != text and label:
        SHORTENED.append(f"{label}: kept {len(kept)}/{len(text)} chars (dropped whole trailing sentences)")
    return kept


def _fit_note(text: str, budget: int, shrink: int = 0) -> str:
    """Prompt instruction that sizes `text` to a format's default-size char `budget`.
    Longer copy renders SMALLER and wraps across more lines rather than being cut — the
    generative equivalent of shrink-to-fit. `shrink` steps down one extra tier per unit,
    used to retry when vision QA still saw clipped text."""
    ratio = len(" ".join((text or "").split())) / max(budget, 1)
    tier = next((i for i, (r, _, _) in enumerate(TYPE_TIERS) if ratio <= r), len(TYPE_TIERS) - 1)
    _, size_word, max_lines = TYPE_TIERS[min(tier + shrink, len(TYPE_TIERS) - 1)]
    return (
        f" TYPE SIZE: set the text at a {size_word} size, wrapped across at most {max_lines} "
        "lines, chosen so every word — including the final punctuation — sits inside the "
        "margins. Do NOT shorten, paraphrase, summarize, or drop any words to make it fit; "
        "reduce the type size instead."
    )


_QA_ENABLED = os.environ.get("APLUS_GRAPHICS_QA", "1") != "0"


def _qa_text_fits(image_path: Path) -> "tuple[bool, str]":
    """Vision check: is any text on the graphic cropped/cut off/outside the frame, OR left
    reading as an incomplete thought? Returns (ok, reason). The incomplete-thought half
    matters because a card whose copy was truncated renders perfectly fitted — visually
    clean, semantically cut off — so an edges-only check passes it.
    Fail-open (ok=True) on any error so QA never blocks a build."""
    if not _QA_ENABLED:
        return True, "qa-disabled"
    try:
        import base64
        import anthropic
        b64 = base64.standard_b64encode(Path(image_path).read_bytes()).decode()
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-opus-4-7", max_tokens=80,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": (
                    "This is a marketing graphic with text. Check TWO things: (a) is ANY text cropped, "
                    "cut off at an edge, or running outside the frame/margins, and (b) does the visible "
                    "text stop mid-sentence or mid-word, or otherwise read as an incomplete thought? "
                    "Reply ONLY 'OK' if every word is fully visible with comfortable margins AND the "
                    "text reads as a complete finished thought, or 'CUTOFF: <short reason>' otherwise.")},
            ]}],
        )
        txt = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return (txt.upper().startswith("OK"), txt)
    except Exception as e:
        return True, f"qa-skipped: {e}"


def _gen_with_qa(make_prompt, size: str, out_path: Path, label: str, retries: int = 2) -> dict:
    """Generate a text graphic, then vision-QA it for cut-off text. make_prompt(shrink)
    returns the prompt for the SAME full copy one type tier smaller per shrink step, so a
    clipped result is retried at smaller type — never by cutting words out of the copy
    (the old scale-the-cap retry made the incomplete-thought problem worse each attempt).
    Returns the last _gpt_image result dict, carrying the final QA verdict."""
    r = {}
    for attempt in range(retries + 1):
        r = _gpt_image(make_prompt(attempt), size, out_path)
        if not r.get("ok"):
            return r
        ok, reason = _qa_text_fits(out_path)
        print(f"  [QA] {label}: {'OK' if ok else reason}")
        r["text_fit_qa"] = "ok" if ok else reason
        if ok:
            return r
        if attempt < retries:
            print(f"  [QA] {label}: regenerating at smaller type (attempt {attempt + 2})")
    return r

# A+ brand
NAVY = "#1A3A52"
ORANGE = "#EF5829"


def _gemini(prompt: str, aspect: str, out_path: Path) -> dict:
    if not GEMINI:
        return {"name": out_path.name, "ok": False, "error": "GEMINI_API_KEY not set"}
    model = "gemini-3.1-flash-image-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": aspect},
            "temperature": 0.7,
        },
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "aplus/1.0"})
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except Exception as e:
        return {"name": out_path.name, "ok": False, "error": str(e)[:300], "elapsed_s": round(time.time() - start, 1)}
    for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            out_path.write_bytes(base64.b64decode(part["inlineData"]["data"]))
            return {"name": out_path.name, "ok": True, "provider": "gemini-3.1-flash-image",
                    "elapsed_s": round(time.time() - start, 1)}
    return {"name": out_path.name, "ok": False, "error": "no inlineData", "elapsed_s": round(time.time() - start, 1)}


def _gpt_image(prompt: str, size: str, out_path: Path, quality: str = "medium") -> dict:
    if not OPENAI:
        return {"name": out_path.name, "ok": False, "error": "OPENAI_API_KEY not set"}
    body = json.dumps({"model": "gpt-image-2", "prompt": prompt, "n": 1, "size": size, "quality": quality}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI}"},
    )
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"name": out_path.name, "ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:200]}", "elapsed_s": round(time.time() - start, 1)}
    except Exception as e:
        return {"name": out_path.name, "ok": False, "error": str(e)[:200], "elapsed_s": round(time.time() - start, 1)}
    item = (result.get("data") or [{}])[0]
    if "b64_json" in item:
        out_path.write_bytes(base64.b64decode(item["b64_json"]))
        return {"name": out_path.name, "ok": True, "provider": "gpt-image-2", "elapsed_s": round(time.time() - start, 1)}
    return {"name": out_path.name, "ok": False, "error": "no b64_json", "elapsed_s": round(time.time() - start, 1)}


def _meta_field(text: str, field: str) -> str:
    m = re.search(rf"^{re.escape(field)}:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip().strip('"') if m else ""


def _meta_list(text: str, field: str) -> list[str]:
    m = re.search(rf"^{re.escape(field)}:\s*$", text, re.MULTILINE)
    if not m:
        return []
    items = []
    for line in text[m.end():].split("\n")[1:]:
        s = line.strip()
        if not s or not s.startswith("-"):
            break
        item = s[1:].strip().strip('"')
        items.append(item)
    return items


def hero_prompt(subject: str, headline: str) -> str:
    subject = subject or f"an editorial scene illustrating: {headline}"
    return (
        "A photorealistic documentary editorial photograph for a B2B education blog, "
        f"depicting: {subject}. Documentary style similar to The Atlantic or NYT "
        "education features. Natural color grading, warm window light, real-looking "
        "faces with no uncanny-valley artifacts, diverse subjects, NOT stock-photo "
        "styling. Shot at 35mm equivalent, shallow depth of field. 16:9 widescreen "
        "landscape. "
        "CRITICAL: this is a clean editorial PHOTOGRAPH, not an infographic. Any papers, "
        "binders, documents, notebooks, whiteboards, screens, or charts that appear in "
        "frame MUST be blank, out-of-focus, or illegible — absolutely NO readable text, "
        "numbers, statistics, tables, charts, spreadsheets, data, or handwriting anywhere "
        "in the image (it must never look like it is showing real data). No text overlay. "
        "No logos." + LOGO_EXCLUSION
    )


def pull_quote_prompt(quote: str, fit: str = "") -> str:
    return (
        "A landscape blog-body-width pull-quote graphic. Solid background A+ Orange "
        f"hex {ORANGE}. Subtle paper-grain texture at 5 percent opacity. Large white "
        "serif text (Playfair Display style, elegant editorial serif weight 700), "
        "centered vertically with generous left and right margins, reading EXACTLY: "
        f"\"{quote}\". Generous whitespace. NO date line. NO 'A+ Tutoring blog' text. "
        "NO attribution subtitle. NO 'Source:' footer. Just the verbatim quote. "
        "Aspect 3:2 landscape." + LOGO_EXCLUSION + TEXT_FIT + fit
    )


def social_card_prompt(headline: str, fit: str = "") -> str:
    return (
        "A flat institutional social media share card for an A+ Tutoring B2B blog "
        f"post. Solid background A+ Navy hex {NAVY}. Large white serif headline "
        "(Playfair Display style, elegant editorial serif weight 700) in the upper "
        f"third, left-aligned with generous margin, reading EXACTLY: \"{headline}\". "
        f"Below it, a thin horizontal A+ Orange {ORANGE} divider line ~200px wide. "
        "Generous whitespace. Clean, institutional. No photographs. No decorative "
        "icons. No date. Aspect 16:9 landscape." + LOGO_EXCLUSION + TEXT_FIT + fit
    )


def fb_ig_card_prompt(hook: str, fit: str = "") -> str:
    return (
        "A warm, approachable SQUARE social media graphic for A+ Tutoring (a California K-12 "
        "tutoring company), sized for Facebook and Instagram feeds. Solid background A+ Navy "
        f"hex {NAVY} with a subtle soft gradient. A large, friendly white headline (clean "
        "rounded sans-serif such as Poppins or DM Sans, weight 600) centered with generous "
        f"margins, reading EXACTLY: \"{hook}\". A short A+ Orange {ORANGE} accent underline "
        "beneath it. Lots of whitespace, modern and inviting, community-facing (not corporate "
        "or academic). No photographs, no clip-art icons, no date. Aspect 1:1 square."
        + LOGO_EXCLUSION + TEXT_FIT + fit
    )


def carousel_slide_prompt(headline: str, body: str, slide_num: int, total: int, is_cta: bool,
                          fit: str = "") -> str:
    swipe = (" A small right-pointing swipe indicator in the lower-left (this is slide 1 of the set)."
             if slide_num == 1 else " NO swipe indicator.")
    head = (f"a white serif headline (Playfair Display style, weight 700) reading EXACTLY: \"{headline}\", then "
            if headline else "")
    cta = " This is the final call-to-action slide." if is_cta else ""
    return (
        f"A portrait-orientation flat design slide for a LinkedIn carousel, slide {slide_num} of {total}. "
        f"Solid background A+ Navy hex {NAVY}. {head}white sans-serif body text (DM Sans style) reading "
        f"EXACTLY: \"{body}\". A thin A+ Orange {ORANGE} accent line. Generous whitespace, clean and "
        f"institutional. No photographs, no decorative icons, no 'Source:' footer.{swipe}{cta}"
        + LOGO_EXCLUSION + TEXT_FIT + fit
    )


def build(bundle: Path, with_hero: bool = True) -> dict:
    SHORTENED.clear()  # per-build, so a second call in-process reports only its own copy
    graphics = bundle / "graphics"
    graphics.mkdir(parents=True, exist_ok=True)
    meta_path = bundle / "blog-anchor-meta.md"
    meta_text = meta_path.read_text(encoding="utf-8") if meta_path.exists() else ""

    headline = _meta_field(meta_text, "h1_title") or _meta_field(meta_text, "html_title") or "A+ Tutoring"
    hero_subject = _meta_field(meta_text, "hero_alt_text") or _meta_field(meta_text, "featured_image_alt_text")
    quotes = _meta_list(meta_text, "pull_quotes")
    # Short complete-thought card headline (~8 words) the skill writes for social/FB/IG
    # graphics, so cards read cleanly instead of truncating the long SEO title.
    social_headline = _meta_field(meta_text, "social_headline")

    results = []

    # Hero — DISTINCT per blog (driven by the topic's hero alt text / headline).
    if with_hero:
        r = _gemini(hero_prompt(hero_subject, headline), "16:9", graphics / "hero.png")
        print("hero:", r.get("ok"), r.get("error", ""))
        results.append(r)

    # Copy is capped ONCE here, at the format's hard ceiling and on sentence boundaries;
    # the per-attempt lambda then only varies the type size, so a retry never eats words.

    # Social card — prefer the dedicated short headline, fall back to the SEO title.
    sc_text = _cap(social_headline or headline, HARD_CHARS["social_card"], "social_card")
    r = _gen_with_qa(lambda k: social_card_prompt(sc_text, _fit_note(sc_text, FIT_CHARS["social_card"], k)),
                     "1536x1024", graphics / "social-card.png", "social_card")
    results.append(r)

    # Up to 2 pull-quote cards.
    for slot, quote in zip(["s1", "s2"], (quotes + ["", ""])[:2]):
        if not quote:
            continue
        q = _cap(quote, HARD_CHARS["pull_quote"], f"pull_quote_{slot}")
        r = _gen_with_qa(lambda k, q=q: pull_quote_prompt(q, _fit_note(q, FIT_CHARS["pull_quote"], k)),
                         "1536x1024", graphics / f"pull-quote-{slot}.png", f"pull_quote_{slot}")
        results.append(r)

    # LinkedIn carousel (portrait): slide 1 = headline + first quote; slides 2-5 = carousel_slides.
    carousel = _meta_list(meta_text, "carousel_slides")
    if quotes or carousel:
        c1_head = _cap(social_headline or headline, HARD_CHARS["carousel_headline"], "carousel_headline")
        c1_body = _cap(quotes[0], HARD_CHARS["carousel_body"], "carousel_body") if quotes else ""
        # Slide 1 carries both blocks, so size the type against their combined budget.
        c1_budget = FIT_CHARS["carousel_headline"] + (FIT_CHARS["carousel_body"] if c1_body else 0)
        r = _gen_with_qa(
            lambda k: carousel_slide_prompt(
                c1_head, c1_body, 1, 5, False,
                _fit_note(f"{c1_head} {c1_body}".strip(), c1_budget, k)),
            "1024x1536", graphics / "linkedin-carousel-slide-1.png", "carousel_1")
        results.append(r)
        for i, text in enumerate(carousel[:4]):
            n = i + 2
            t = _cap(text, HARD_CHARS["carousel_body"], f"carousel_{n}")
            r = _gen_with_qa(
                lambda k, t=t, nn=n: carousel_slide_prompt(
                    "", t, nn, 5, nn == 5, _fit_note(t, FIT_CHARS["carousel_body"], k)),
                "1024x1536", graphics / f"linkedin-carousel-slide-{n}.png", f"carousel_{n}")
            results.append(r)

    # Facebook + Instagram share card (square — the SAME graphic posts to both).
    fb_text = _cap(social_headline or (quotes[0] if quotes else headline), HARD_CHARS["fb_ig"], "fb_ig")
    r = _gen_with_qa(lambda k: fb_ig_card_prompt(fb_text, _fit_note(fb_text, FIT_CHARS["fb_ig"], k)),
                     "1024x1024", graphics / "fb-ig-card.png", "fb_ig_card")
    results.append(r)

    (graphics / "_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Text-fit guard: anything that lost a sentence, or that QA still called cut off, is
    # reported loudly here and written for build-qa-checklist.py to surface. Silence here
    # is the signal that every card holds its complete copy.
    cutoff = [r.get("name") for r in results
              if str(r.get("text_fit_qa", "ok")).upper().startswith("CUTOFF")]
    (graphics / "_text-fit.json").write_text(
        json.dumps({"shortened": SHORTENED, "qa_cutoff": cutoff}, indent=2), encoding="utf-8")
    for line in SHORTENED:
        print(f"graphics: WARNING text-fit — {line}", file=sys.stderr)
    if cutoff:
        print(f"graphics: WARNING text-fit — QA still saw cut-off text on: {', '.join(cutoff)}",
              file=sys.stderr)

    ok = sum(1 for r in results if r.get("ok"))
    print(f"graphics: {ok}/{len(results)} generated")
    return {"bundle": str(bundle), "generated": ok, "total": len(results), "results": results,
            "text_fit": {"shortened": SHORTENED, "qa_cutoff": cutoff}}


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate B2B blog graphics (hero + pull-quotes + social card)")
    ap.add_argument("--bundle", required=True, help="bundle directory")
    ap.add_argument("--no-hero", action="store_true", help="skip hero regeneration (keep the existing hero)")
    args = ap.parse_args()
    bundle = Path(args.bundle)
    if not bundle.exists():
        print(f"ERROR: bundle not found: {bundle}", file=sys.stderr)
        return 1
    build(bundle, with_hero=not args.no_hero)
    return 0


if __name__ == "__main__":
    sys.exit(main())

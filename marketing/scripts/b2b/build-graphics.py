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

# Hard maximum characters that go onto each graphic format. These are tuned so the
# text fits the canvas at a readable size (GPT Image does not reliably shrink-to-fit,
# so the cap — not the prompt — is the real guarantee against overflow).
MAX_CHARS = {
    "pull_quote": 130,      # 3:2 landscape
    "social_card": 90,      # 16:9 landscape
    "carousel_headline": 55,
    "carousel_body": 100,   # portrait 1024x1536 (slide 1 carries headline + body)
    "fb_ig": 60,            # 1:1 square — least room, keep it punchy
}


def _cap(text: str, n: int) -> str:
    """Cap text to at most n chars, ending as cleanly as possible: prefer a sentence
    boundary, then a clause (comma) boundary, then a word boundary. Avoids the
    mid-phrase '...with a' truncations that read as cut off."""
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    window = text[:n]
    for sep in (". ", "! ", "? "):
        idx = window.rfind(sep)
        if idx >= n * 0.5:
            return window[: idx + 1].strip()
    idx = window.rfind(", ")
    if idx >= n * 0.55:
        return window[:idx].strip()
    return window.rsplit(" ", 1)[0].rstrip(" ,;:-")


_QA_ENABLED = os.environ.get("APLUS_GRAPHICS_QA", "1") != "0"


def _qa_text_fits(image_path: Path) -> "tuple[bool, str]":
    """Vision check: is any text on the graphic cropped/cut off/outside the frame?
    Returns (ok, reason). Fail-open (ok=True) on any error so QA never blocks a build."""
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
                    "This is a marketing graphic with text. Is ANY text cropped, cut off at an edge, "
                    "or running outside the frame/margins? Reply ONLY 'OK' if every word is fully "
                    "visible with comfortable margins, or 'CUTOFF: <short reason>' if any text is "
                    "clipped, touching an edge, or past the frame.")},
            ]}],
        )
        txt = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return (txt.upper().startswith("OK"), txt)
    except Exception as e:
        return True, f"qa-skipped: {e}"


def _gen_with_qa(make_prompt, size: str, out_path: Path, label: str, retries: int = 2) -> dict:
    """Generate a text graphic, then vision-QA it for cut-off text. make_prompt(scale)
    returns the prompt with its text capped to scale*max, so a cut-off result is retried
    at a tighter scale (0.8x). Returns the last _gpt_image result dict."""
    r = {}
    for attempt in range(retries + 1):
        scale = 0.8 ** attempt
        r = _gpt_image(make_prompt(scale), size, out_path)
        if not r.get("ok"):
            return r
        ok, reason = _qa_text_fits(out_path)
        print(f"  [QA] {label}: {'OK' if ok else reason}")
        if ok:
            return r
        if attempt < retries:
            print(f"  [QA] {label}: regenerating tighter (attempt {attempt + 2})")
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


def pull_quote_prompt(quote: str) -> str:
    return (
        "A landscape blog-body-width pull-quote graphic. Solid background A+ Orange "
        f"hex {ORANGE}. Subtle paper-grain texture at 5 percent opacity. Large white "
        "serif text (Playfair Display style, elegant editorial serif weight 700), "
        "centered vertically with generous left and right margins, reading EXACTLY: "
        f"\"{quote}\". Generous whitespace. NO date line. NO 'A+ Tutoring blog' text. "
        "NO attribution subtitle. NO 'Source:' footer. Just the verbatim quote. "
        "Aspect 3:2 landscape." + LOGO_EXCLUSION + TEXT_FIT
    )


def social_card_prompt(headline: str) -> str:
    return (
        "A flat institutional social media share card for an A+ Tutoring B2B blog "
        f"post. Solid background A+ Navy hex {NAVY}. Large white serif headline "
        "(Playfair Display style, elegant editorial serif weight 700) in the upper "
        f"third, left-aligned with generous margin, reading EXACTLY: \"{headline}\". "
        f"Below it, a thin horizontal A+ Orange {ORANGE} divider line ~200px wide. "
        "Generous whitespace. Clean, institutional. No photographs. No decorative "
        "icons. No date. Aspect 16:9 landscape." + LOGO_EXCLUSION + TEXT_FIT
    )


def fb_ig_card_prompt(hook: str) -> str:
    return (
        "A warm, approachable SQUARE social media graphic for A+ Tutoring (a California K-12 "
        "tutoring company), sized for Facebook and Instagram feeds. Solid background A+ Navy "
        f"hex {NAVY} with a subtle soft gradient. A large, friendly white headline (clean "
        "rounded sans-serif such as Poppins or DM Sans, weight 600) centered with generous "
        f"margins, reading EXACTLY: \"{hook}\". A short A+ Orange {ORANGE} accent underline "
        "beneath it. Lots of whitespace, modern and inviting, community-facing (not corporate "
        "or academic). No photographs, no clip-art icons, no date. Aspect 1:1 square."
        + LOGO_EXCLUSION + TEXT_FIT
    )


def carousel_slide_prompt(headline: str, body: str, slide_num: int, total: int, is_cta: bool) -> str:
    swipe = (" A small right-pointing swipe indicator in the lower-left (this is slide 1 of the set)."
             if slide_num == 1 else " NO swipe indicator.")
    head = (f"a white serif headline (Playfair Display style, weight 700) reading EXACTLY: \"{headline}\", then "
            if headline else "")
    cta = " This is the final call-to-action slide." if is_cta else ""
    return (
        f"A portrait-orientation flat design slide for a LinkedIn carousel, slide {slide_num} of {total}. "
        f"Solid background A+ Navy hex {NAVY}. {head}white sans-serif body text (DM Sans style) reading "
        f"EXACTLY: \"{body}\". A thin A+ Orange {ORANGE} accent line. Generous whitespace, clean and "
        f"institutional. No photographs, no decorative icons, no 'Source:' footer.{swipe}{cta}" + LOGO_EXCLUSION + TEXT_FIT
    )


def build(bundle: Path, with_hero: bool = True) -> dict:
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

    # Social card — prefer the dedicated short headline, fall back to the SEO title.
    sc_text = social_headline or headline
    r = _gen_with_qa(lambda s: social_card_prompt(_cap(sc_text, int(MAX_CHARS["social_card"] * s))),
                     "1536x1024", graphics / "social-card.png", "social_card")
    results.append(r)

    # Up to 2 pull-quote cards.
    for slot, quote in zip(["s1", "s2"], (quotes + ["", ""])[:2]):
        if not quote:
            continue
        r = _gen_with_qa(lambda s, q=quote: pull_quote_prompt(_cap(q, int(MAX_CHARS["pull_quote"] * s))),
                         "1536x1024", graphics / f"pull-quote-{slot}.png", f"pull_quote_{slot}")
        results.append(r)

    # LinkedIn carousel (portrait): slide 1 = headline + first quote; slides 2-5 = carousel_slides.
    carousel = _meta_list(meta_text, "carousel_slides")
    if quotes or carousel:
        c1_head = social_headline or headline
        c1_body = quotes[0] if quotes else ""
        r = _gen_with_qa(
            lambda s: carousel_slide_prompt(
                _cap(c1_head, int(MAX_CHARS["carousel_headline"] * s)),
                _cap(c1_body, int(MAX_CHARS["carousel_body"] * s)) if c1_body else "", 1, 5, False),
            "1024x1536", graphics / "linkedin-carousel-slide-1.png", "carousel_1")
        results.append(r)
        for i, text in enumerate(carousel[:4]):
            n = i + 2
            r = _gen_with_qa(
                lambda s, t=text, nn=n: carousel_slide_prompt("", _cap(t, int(MAX_CHARS["carousel_body"] * s)), nn, 5, nn == 5),
                "1024x1536", graphics / f"linkedin-carousel-slide-{n}.png", f"carousel_{n}")
            results.append(r)

    # Facebook + Instagram share card (square — the SAME graphic posts to both).
    fb_text = social_headline or (quotes[0] if quotes else headline)
    r = _gen_with_qa(lambda s: fb_ig_card_prompt(_cap(fb_text, int(MAX_CHARS["fb_ig"] * s))),
                     "1024x1024", graphics / "fb-ig-card.png", "fb_ig_card")
    results.append(r)

    (graphics / "_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    ok = sum(1 for r in results if r.get("ok"))
    print(f"graphics: {ok}/{len(results)} generated")
    return {"bundle": str(bundle), "generated": ok, "total": len(results), "results": results}


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

#!/usr/bin/env python3
"""
Generalized pull-quote graphics builder for any A+ case study.

Takes --bundle, reads pull_quotes (and optional pull_quote_attribution) from
metadata.md. Generates 2 quote graphics via GPT Image 2 with curly opening
quote mark + gold divider + attribution (B2C case-study style, per v2.1).

metadata.md:
    pull_quotes:
      - "First quote (complete grammatical sentence)."
      - "Second quote (complete grammatical sentence)."
    pull_quote_attribution: "Camila, Gabriela's mother"   # optional; one line applied to both

Usage:
    python3 scripts/build-case-study-pull-quotes.py --bundle aplus-content/{bundle}/
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=REPO / ".env")
OPENAI = os.environ.get("OPENAI_API_KEY")

LOGO_EXCLUSION = (
    " CRITICAL CONSTRAINT: Do NOT include any logo, wordmark, brand mark, "
    "watermark, signature, monogram, or company identifier anywhere in this "
    "image. Do NOT add an 'A+' mark or 'A+ Tutoring' wordmark, any chevron, "
    "graduation cap, pencil, apple, or book icon, or any tutoring-company "
    "logo approximation. The bottom-right 200x200 pixel zone MUST be solid "
    "background color with NO text or graphics. If you generate any logo or "
    "brand mark, the image is a failure. The real A+ logo is composited "
    "separately. This is the single most important constraint."
)


def parse_meta_field(text, field):
    block = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
    if block:
        for line in block.group(1).split("\n"):
            if ":" in line:
                k, _, v = line.partition(":")
                if k.strip() == field:
                    return v.strip()
    m = re.search(rf"^{re.escape(field)}:\s*(.+)$", text, re.MULTILINE)
    if m:
        v = m.group(1).strip()
        return v[1:-1] if v.startswith('"') and v.endswith('"') else v
    return ""


def parse_meta_list(text, field):
    m = re.search(rf"^{re.escape(field)}:\s*$", text, re.MULTILINE)
    if not m:
        return []
    items = []
    for line in text[m.end():].split("\n")[1:]:
        s = line.strip()
        if not s or not s.startswith("-"):
            break
        item = s[1:].strip()
        if item.startswith('"') and item.endswith('"'):
            item = item[1:-1]
        items.append(item)
    return items


def gpt_image_2(prompt, out_path):
    url = "https://api.openai.com/v1/images/generations"
    body = json.dumps({"model": "gpt-image-2", "prompt": prompt, "n": 1,
                       "size": "1536x1024", "quality": "medium"}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {OPENAI}"})
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return False, str(e)[:300]
    item = result.get("data", [{}])[0]
    if "b64_json" in item:
        out_path.write_bytes(base64.b64decode(item["b64_json"]))
        return True, out_path.stat().st_size
    return False, "no b64_json"


def quote_prompt(quote_text, attribution):
    return (
        "A landscape blog-body-width pull-quote graphic for a parent-facing "
        "case study. Solid background A+ Orange hex #EF5829. Subtle paper-grain "
        "texture at 5 percent opacity. LARGE elegant proper CURLY OPENING "
        "QUOTATION MARK (unicode left double quotation mark) at the upper-left "
        "in Playfair Display style weight 700, ~140pt, white at 90 percent "
        "opacity. Below it, large white serif text (Playfair Display weight "
        "700, ~44pt), generous margins, reading exactly: " + quote_text + " "
        "Below the quote, a small horizontal A+ Gold #F4A261 divider ~80px wide. "
        "Below the divider, attribution in white DM Sans weight 500 ~18pt "
        "reading exactly: " + attribution + " Bottom-right corner: clean "
        "~140x140 pixel area for the logo composite. NO date, NO 'A+ Tutoring "
        "blog' text, NO closing quote mark, NO straight quote marks around the "
        "text. Aspect 3:2 landscape."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    args = ap.parse_args()

    bundle = Path(args.bundle).resolve()
    meta_path = bundle / "metadata.md"
    if not meta_path.exists():
        print(f"ERROR: metadata.md not found in {bundle}", file=sys.stderr)
        return 1
    text = meta_path.read_text()
    out = bundle / "graphics"
    out.mkdir(parents=True, exist_ok=True)

    quotes = parse_meta_list(text, "pull_quotes")
    if len(quotes) < 2:
        print(f"ERROR: need 2 pull_quotes in metadata.md, found {len(quotes)}", file=sys.stderr)
        return 1

    # Attribution: single field applied to both, or derive from pseudonym
    attribution = parse_meta_field(text, "pull_quote_attribution")
    if not attribution:
        slug = parse_meta_field(text, "url_slug")
        pseudonym = slug.split("-")[0].capitalize() if slug else "the student"
        attribution = f"{pseudonym}\u2019s parent"

    print(f"=== Pull quotes: {bundle.name} ===")
    for slot, quote in zip(["s1", "s2"], quotes[:2]):
        print(f"Generating pull_quote_{slot}...")
        ok, info = gpt_image_2(quote_prompt(quote, attribution) + LOGO_EXCLUSION,
                               out / f"pull-quote-{slot}.png")
        print(f"  {ok} {info if not ok else str(info) + ' bytes'}")

    print(f"\nNext: composite-logo.py --bundle {args.bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

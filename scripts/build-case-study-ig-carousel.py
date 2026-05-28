#!/usr/bin/env python3
"""
Generalized Instagram carousel builder for any A+ case study.

Takes --bundle, reads carousel_slides (5) from metadata.md. Generates 5
square 1024x1024 slides via GPT Image 2, alternating Navy/Orange, swipe
indicator on slides 1-4, slide indicator top-right.

metadata.md:
    carousel_slides:
      - "Slide 1 hook"
      - "Slide 2 problem"
      - "Slide 3 turn"
      - "Slide 4 work"
      - "Slide 5 CTA"

Usage:
    python3 scripts/build-case-study-ig-carousel.py --bundle aplus-content/{bundle}/
"""
import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
import urllib.request
import urllib.error

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=REPO / ".env")
OPENAI = os.environ.get("OPENAI_API_KEY")

LOGO_EXCLUSION = (
    " CRITICAL CONSTRAINT: Do NOT include any logo, wordmark, brand mark, "
    "watermark, signature, monogram, or company identifier anywhere. No 'A+' "
    "mark, no 'A+ Tutoring' wordmark, no chevron/cap/pencil/apple/book icon, "
    "no tutoring-company logo approximation. The bottom-right 200x200 pixel "
    "zone MUST be solid background color with NO text or graphics. If you "
    "generate any logo, the image is a failure. Real logo composited "
    "separately. This is the single most important constraint."
)


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
                       "size": "1024x1024", "quality": "medium"}).encode()
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


def slide_prompt(slide_num, copy, total=5):
    is_navy = (slide_num % 2 == 1)
    bg_name = "A+ Navy" if is_navy else "A+ Orange"
    bg_hex = "#1A3A52" if is_navy else "#EF5829"
    show_swipe = slide_num < total
    swipe = (
        " Include a small subtle white right-pointing chevron near the "
        "lower-right (about 200px from right and bottom edges) suggesting "
        "'swipe to continue', not overlapping the logo zone."
        if show_swipe else
        " This is the FINAL slide. Do NOT include any swipe indicator or arrow."
    )
    return (
        f"A square 1080x1080 Instagram carousel slide for A+ Tutoring (a "
        f"California virtual K-12 tutoring company). Slide {slide_num} of "
        f"{total} in a parent-facing case-study carousel. Solid background "
        f"{bg_name} hex {bg_hex}, subtle paper-grain at 5 percent opacity. "
        f"Center: bold Playfair Display serif headline weight 700 ~56pt in "
        f"white, generous margins, centered, reading exactly: \"{copy}\" "
        f"Below it, a small horizontal A+ Gold #F4A261 divider ~100px wide. "
        f"Upper-right: small white DM Sans label '{slide_num} / {total}' "
        f"~14pt at 60 percent opacity, ~60px from each edge.{swipe} "
        f"Bottom-right: clean ~140x140 pixel zone for the logo composite. "
        f"Editorial NYT-Magazine aesthetic. NO photos of people, NO icons, "
        f"NO date, NO 'A+ Tutoring' text, NO 'Case Study' label."
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

    slides = parse_meta_list(text, "carousel_slides")
    if len(slides) < 5:
        print(f"ERROR: need 5 carousel_slides, found {len(slides)}", file=sys.stderr)
        return 1

    print(f"=== IG carousel: {bundle.name} ===")
    for i, copy in enumerate(slides[:5], 1):
        print(f"Generating slide {i}...")
        ok, info = gpt_image_2(slide_prompt(i, copy) + LOGO_EXCLUSION,
                               out / f"instagram-carousel-slide-{i}.png")
        print(f"  {ok} {info if not ok else str(info) + ' bytes'}")

    print(f"\nNext: composite-logo.py --bundle {args.bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

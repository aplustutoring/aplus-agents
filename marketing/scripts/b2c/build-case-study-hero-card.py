#!/usr/bin/env python3
"""
Generalized hero + OG social card builder for any A+ case study.

Takes --bundle, reads subject/grade/gender/ethnicity + title/subhead from
metadata.md, builds the hero prompt via scripts/b2c/hero_scene.py (subject- and
demographic-aware), generates hero (Gemini) + social card (GPT Image 2).

Usage:
    python3 scripts/b2c/build-case-study-hero-card.py --bundle aplus-content/{bundle}/
"""
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=REPO / ".env")
# Ensure B2C and shared helpers are importable after restructuring
sys.path.insert(0, str(REPO / "scripts" / "shared"))
sys.path.insert(0, str(REPO / "scripts" / "b2c"))
from hero_scene import build_hero_prompt, FACE_PARTIAL_CONSTRAINT

GEMINI = os.environ.get("GEMINI_API_KEY")
OPENAI = os.environ.get("OPENAI_API_KEY")

LOGO_EXCLUSION = (
    " CRITICAL CONSTRAINT: Do NOT include any logo, wordmark, brand mark, "
    "watermark, signature, monogram, or company identifier anywhere in this "
    "image. Do NOT add an 'A+' mark, an 'A+ Tutoring' wordmark, the word "
    "'Tutoring', the word 'aplustutoring', a chevron, a graduation cap icon, "
    "a pencil icon, an apple icon, a book icon, or any approximation of a "
    "tutoring-company logo. Do NOT add any badge, seal, certification mark, "
    "or signature graphic. The bottom-right 200x200 pixel zone MUST be solid "
    "background color with NO text, NO icons, NO graphics, NO design "
    "elements. The bottom-left 200x200 pixel zone must also be clean. If "
    "you generate any logo, wordmark, brand mark, or A+ approximation, the "
    "image is a generation failure and will be discarded. The real A+ logo "
    "is added in a separate post-processing step by a Python compositor; "
    "your job is to produce a clean canvas with NO branded marks of any "
    "kind. This is the single most important constraint."
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


def gemini(prompt, aspect, out_path):
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
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": "aplus/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except Exception as e:
        return False, str(e)[:300]
    for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            out_path.write_bytes(base64.b64decode(part["inlineData"]["data"]))
            return True, out_path.stat().st_size
    return False, "no inlineData"


def gpt_image_2(prompt, size, out_path):
    url = "https://api.openai.com/v1/images/generations"
    body = json.dumps({"model": "gpt-image-2", "prompt": prompt, "n": 1,
                       "size": size, "quality": "medium"}).encode()
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

    subject = parse_meta_field(text, "subject") or "math"
    grade = parse_meta_field(text, "grade") or "9"
    gender = parse_meta_field(text, "student_gender") or "girl"
    ethnicity = parse_meta_field(text, "student_ethnicity") or ""
    title = parse_meta_field(text, "h1_title") or "A+ Tutoring Case Study"
    fb_sub = parse_meta_field(text, "facebook_subhead") or \
        parse_meta_field(text, "meta_description") or ""

    print(f"=== Hero + social card: {bundle.name} ===")
    print(f"  subject={subject} grade={grade} gender={gender}")
    print(f"  ethnicity={ethnicity[:50]}")

    # Hero
    hero_prompt = build_hero_prompt(subject=subject, grade=grade,
                                    seed_text=title, gender=gender, ethnicity=ethnicity)
    ok, info = gemini(hero_prompt + FACE_PARTIAL_CONSTRAINT + LOGO_EXCLUSION,
                      "16:9", out / "hero.png")
    print(f"hero: {ok} {info if not ok else str(info) + ' bytes'}")

    # Social card
    social_prompt = (
        "A flat institutional social media share card for an A+ Tutoring case "
        "study blog post. Solid background A+ Navy hex #1A3A52. Large white "
        "serif headline (Playfair Display style, weight 700) upper-left, "
        f"generous margin, reading exactly: \"{title}\" Below it, a thin "
        "horizontal A+ Orange #EF5829 divider about 200px wide, then a smaller "
        f"white DM Sans subhead reading exactly: \"{fb_sub}\" Bottom-right "
        "corner: leave a clean ~140x140 pixel area for the A+ logo composite. "
        "Editorial NYT-Magazine aesthetic. No photographs. No icons. No date. "
        "Aspect 16:9 landscape."
    )
    ok, info = gpt_image_2(social_prompt + LOGO_EXCLUSION, "1536x1024", out / "social-card.png")
    print(f"social_card: {ok} {info if not ok else str(info) + ' bytes'}")

    print(f"\nNext: composite-logo.py --bundle {args.bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Generalized Facebook share builder for any A+ case study.

Takes --bundle, reads facebook_headline + facebook_subhead from metadata.md.
Generates a 1200x630 landscape FB share graphic via GPT Image 2.

Usage:
    python3 scripts/build-case-study-facebook.py --bundle aplus-content/{bundle}/
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
    "watermark, monogram, or company identifier. No 'A+' mark, no chevron/"
    "cap/pencil/apple/book icon. Bottom-right 200x200 pixel zone MUST be "
    "solid background color with NO text or graphics. If you generate any "
    "logo, the image is a failure. Real logo composited separately. This is "
    "the single most important constraint."
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

    headline = parse_meta_field(text, "facebook_headline") or parse_meta_field(text, "h1_title")
    subhead = parse_meta_field(text, "facebook_subhead") or parse_meta_field(text, "meta_description")

    print(f"=== Facebook share: {bundle.name} ===")
    prompt = (
        "A 1200x630 landscape Facebook share graphic for an A+ Tutoring case "
        "study. Solid background A+ Navy hex #1A3A52, subtle paper-grain at 5 "
        "percent. Upper-left: small A+ Gold #F4A261 DM Sans uppercase label "
        "'A+ TUTORING CASE STUDY' ~14pt weight 700 letter-spaced. Below it, a "
        f"large white Playfair Display serif headline weight 700 ~48pt, left-"
        f"aligned, reading exactly: \"{headline}\" Below it, a thin horizontal "
        "A+ Orange #EF5829 divider ~180px wide, then a smaller white DM Sans "
        f"subhead ~18pt reading exactly: \"{subhead}\" Bottom-right: clean "
        "~140x140 pixel area for the logo composite. Editorial NYT-Magazine "
        "aesthetic. NO photos of people, NO icons, NO date, NO button. "
        "Aspect 1.91:1 landscape."
    )
    ok, info = gpt_image_2(prompt + LOGO_EXCLUSION, out / "facebook.png")
    print(f"facebook: {ok} {info if not ok else str(info) + ' bytes'}")
    print(f"\nNext: composite-logo.py --bundle {args.bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

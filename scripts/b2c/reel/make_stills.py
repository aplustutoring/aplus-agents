#!/usr/bin/env python3
"""
make_stills.py — generate the reel's scene stills via the DIRECT Gemini image
API (GEMINI_API_KEY from .env), same pattern as build-case-study-comic.py:
generate an anchor hero, then reference it for every beat so the hero is
consistent ACROSS THIS REEL. Stills are full-bleed and banner-free (the reel
adds captions dynamically and animates the art, so no baked text).

Resumable: existing stills are reused. Output: {bundle}/reel/stills/<key>.png

Usage:  python3 scripts/b2c/reel/make_stills.py --bundle aplus-content/{bundle}/ [--force]
"""
import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reel_common as rc

MODEL = "gemini-3-pro-image"
IMAGE_SIZE = "2K"
URL = (f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
       f":generateContent?key={rc.GEMINI_KEY}")

STYLE = ("A vibrant cel-shaded comic-book illustration, bold ink outlines and "
         "halftone shading, bright saturated colors, dramatic radial speed lines.")
LOCK = ("Use the EXACT SAME character shown in the reference image: identical "
        "face, hair, age, body, costume design, colors and chest emblem. Same "
        "cel-shaded comic art style. Only change the pose and the scene. ")


def gemini(prompt, out_path, ref=None, aspect="9:16"):
    parts = []
    if ref is not None:
        parts.append({"inlineData": {"mimeType": "image/png",
                      "data": base64.b64encode(Path(ref).read_bytes()).decode()}})
    parts.append({"text": prompt})
    body = json.dumps({"contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
        "imageConfig": {"aspectRatio": aspect, "imageSize": IMAGE_SIZE},
        "temperature": 0.6}}).encode()
    req = urllib.request.Request(URL, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "aplus/1.0"})
    r = json.loads(urllib.request.urlopen(req, timeout=240).read())
    for p in r.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in p:
            Path(out_path).write_bytes(base64.b64decode(p["inlineData"]["data"]))
            return True, Path(out_path).stat().st_size
    return False, "no inlineData"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not rc.GEMINI_KEY:
        sys.exit("GEMINI_API_KEY not set")

    script = rc.load_script(args.bundle)
    sdir = rc.stills_dir(args.bundle)
    sdir.mkdir(parents=True, exist_ok=True)

    # anchor (no banner, clean establishing portrait) — reference for all beats
    anchor = sdir / "anchor.png"
    if anchor.exists() and not args.force:
        print(f"  anchor: reuse {anchor.name}")
    else:
        prompt = (f"{STYLE} {script['hero']} Standing in a confident heroic "
                  f"portrait pose, plain soft studio background. Full-bleed 9:16, "
                  f"NO text, NO caption box, NO banner, NO border.")
        ok, info = gemini(prompt, anchor)
        print(f"  anchor: {ok} {info}")
        if not ok:
            sys.exit(f"anchor failed: {info}")

    for beat in script["beats"]:
        key = beat["key"]
        out = sdir / f"{key}.png"
        if out.exists() and not args.force:
            print(f"  {key}: reuse {out.name}")
            continue
        prompt = f"{STYLE} {LOCK}New scene: {beat['scene']}"
        ok, info = gemini(prompt, out, ref=anchor)
        print(f"  {key}: {ok} {info}")
        if not ok:
            sys.exit(f"{key} still failed: {info}")
    print("stills done")
    return 0


if __name__ == "__main__":
    sys.exit(main())

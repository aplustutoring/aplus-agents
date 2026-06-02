#!/usr/bin/env python3
"""Composite the real A+ Tutoring logo onto a bundle's flat graphics.

v2.4 (2026-05-20) reusable centralized compositor. Replaces per-bundle
`_composite_logo_v2.py` scripts going forward.

Design rules enforced:

1. IDEMPOTENCY
   - Inputs are files matching <name>.png that do NOT already end in
     `-with-logo.png`.
   - Outputs are written as `<name>-with-logo.png`.
   - Files already named `-with-logo.png` are never re-processed.

2. PRE-EXISTING-LOGO DETECTION
   - Before compositing, sample the bottom-right ~200x80 zone of the
     source. If RGB standard deviation across that zone exceeds the
     threshold (default 20), the source likely contains AI-generated
     content (most often an AI-rendered fake logo). Log a warning and
     continue, so the QA walkthrough can flag it.
   - For files with logos detected pre-composite, the operator should
     regenerate the source with stronger anti-logo prompts (see
     LOGO_EXCLUSION in `_batch_v2.py` per aplus-graphic-prompts v2.4).

3. SMART LOGO COLOR SELECTION
   - Sample a 50x50 region at the logo placement target.
   - Detect A+ Orange (R>200, G<140, B<80) -> use white-variant logo.
   - Detect A+ Navy (R<60, G<80, B>50, low luminance) -> use white-variant.
   - Otherwise: luminance < 40% -> white. luminance > 60% -> two-color.
     40-60% (ambiguous) -> white as the safer default.

4. ALPHA HANDLING (anti-halo, from v2.3)
   - Chroma-key whites in source logo (RGB >= 240) to alpha 0.
   - Hard threshold: any pixel with alpha < 100 becomes alpha 0; any
     pixel with alpha >= 100 becomes alpha 255. No semi-transparent edges.
   - Apply threshold again after LANCZOS resize (which re-introduces
     soft edges).
   - Composite via PIL.Image.alpha_composite for clean blending.

5. LOGO SOURCE FILES
   - Prefers the repo-tracked source at <repo>/assets/logo.png (works in
     CI without extra steps). Falls back to ~/Desktop/logo.png for
     existing local dev habits. The two-color source is read; the white
     variant is produced in-process via color replacement. Fails clearly
     if neither source is present.

Usage:
    python3 scripts/shared/composite-logo.py --bundle aplus-content/2026-05-20-weekly/
    python3 scripts/shared/composite-logo.py --bundle aplus-content/2026-05-20-weekly/ --dry-run
    python3 scripts/shared/composite-logo.py --bundle aplus-content/2026-05-20-weekly/ --force

This script does NOT process the photographic files (hero, facebook,
instagram-post, instagram-story-single) which intentionally ship with
no logo. The 3-frame IG story sequence is built+composited separately by
scripts/b2c/build-instagram-stories.py.
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageStat


# ----- Constants -----
# Logo source. Prefer the repo-tracked asset (works in CI without any
# extra workflow steps and removes the need for a per-machine ~/Desktop
# convention). Fall back to ~/Desktop/logo.png so existing local dev
# habits keep working.
_REPO_LOGO = Path(__file__).resolve().parents[2] / "assets" / "logo.png"
_DESKTOP_LOGO = Path.home() / "Desktop" / "logo.png"
LOGO_PATH = _REPO_LOGO if _REPO_LOGO.exists() else _DESKTOP_LOGO
ALPHA_THRESHOLD = 100  # v2.4: pixels with alpha < 100 -> 0, >=100 -> 255.

# Variance threshold for pre-existing logo detection in the bottom-right
# logo zone. AI-generated content (text, icons, wordmarks) has high RGB
# variance; a clean solid color background has low variance.
LOGO_ZONE_STD_THRESHOLD = 20.0
LOGO_ZONE_W = 200
LOGO_ZONE_H = 80

# Brand color detection thresholds
def is_aplus_orange(r, g, b):
    return r > 200 and g < 140 and b < 80

def is_aplus_navy(r, g, b):
    # Navy is dominant blue with low overall luminance
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return r < 80 and g < 90 and b > 50 and lum < 0.30

# Per-canvas defaults (logo width in pixels, anchor as top-left tuple).
# Keys are matched against the canvas filename prefix.
PER_CANVAS_CONFIG = {
    # social-card / pull-quote / topic-graphic: 1536x1024 landscape
    "social-card": dict(logo_width=150, anchor=(1360, 850)),
    "pull-quote-s1": dict(logo_width=150, anchor=(1360, 850)),
    "pull-quote-s2": dict(logo_width=150, anchor=(1360, 850)),
    "pull-quote-s3": dict(logo_width=150, anchor=(1360, 850)),
    "topic-graphic": dict(logo_width=150, anchor=(1360, 850)),
    # LinkedIn carousel slide: 1024x1536 portrait
    "linkedin-carousel-slide-1": dict(logo_width=140, anchor=(850, 1360)),
    "linkedin-carousel-slide-2": dict(logo_width=140, anchor=(830, 1360)),
    "linkedin-carousel-slide-3": dict(logo_width=140, anchor=(850, 1360)),
    "linkedin-carousel-slide-4": dict(logo_width=140, anchor=(830, 1360)),
    "linkedin-carousel-slide-5": dict(logo_width=140, anchor=(850, 1360)),
    # Instagram carousel slide: 1024x1024 square (case studies, B2C)
    "instagram-carousel-slide-1": dict(logo_width=120, anchor=(870, 870)),
    "instagram-carousel-slide-2": dict(logo_width=120, anchor=(870, 870)),
    "instagram-carousel-slide-3": dict(logo_width=120, anchor=(870, 870)),
    "instagram-carousel-slide-4": dict(logo_width=120, anchor=(870, 870)),
    "instagram-carousel-slide-5": dict(logo_width=120, anchor=(870, 870)),
    # Facebook share: 1200x630 landscape (case-study, flat text-on-color)
    "facebook": dict(logo_width=140, anchor=(1370, 460)),
    # Facebook share: 1200x630 landscape (case-study, flat text-on-color)
    "facebook": dict(logo_width=140, anchor=(1370, 460)),
}

# Files we explicitly do NOT process (photographic, or composed elsewhere)
SKIP_PREFIXES = {
    "hero",
    # "facebook" removed v2.4: case-study FB share is flat text-on-color, needs logo composited.
    # B2B FB share was photographic and didn't need composite. If B2B uses photographic FB again,
    # add per-bundle exclusion logic instead of re-adding here.
    "instagram-post",
    "instagram-story",  # both single and 3-frame: composited by build-instagram-stories.py
    "preset-stat-graphic",  # composited at brand-kit build time
}


# ----- Alpha handling -----
def hardclamp_alpha(rgba_img):
    """Binary alpha: <THRESHOLD -> 0, >=THRESHOLD -> 255."""
    px = rgba_img.load()
    for y in range(rgba_img.height):
        for x in range(rgba_img.width):
            r, g, b, a = px[x, y]
            if a < ALPHA_THRESHOLD:
                px[x, y] = (r, g, b, 0)
            else:
                px[x, y] = (r, g, b, 255)
    return rgba_img


# ----- Logo prep -----
def chroma_keyed_logo():
    raw = Image.open(LOGO_PATH).convert("RGBA")
    px = raw.load()
    for y in range(raw.height):
        for x in range(raw.width):
            r, g, b, a = px[x, y]
            if r >= 240 and g >= 240 and b >= 240:
                px[x, y] = (r, g, b, 0)
    hardclamp_alpha(raw)
    return raw


def white_variant(rgba_logo):
    out = rgba_logo.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (255, 255, 255, a)
    hardclamp_alpha(out)
    return out


# ----- Background sampling -----
def sample_mean_rgb(img, box):
    """Mean RGB across a (left, top, right, bottom) box."""
    crop = img.crop(box).convert("RGB")
    stat = ImageStat.Stat(crop)
    return tuple(int(v) for v in stat.mean)


def sample_std_rgb(img, box):
    """Per-channel std deviation across a (left, top, right, bottom) box.
    Higher std = more AI-generated content; lower std = solid background."""
    crop = img.crop(box).convert("RGB")
    stat = ImageStat.Stat(crop)
    return tuple(float(v) for v in stat.stddev)


def pick_logo_variant(mean_rgb, two_color, white):
    """Return (variant_name, logo_rgba) based on the background mean RGB."""
    r, g, b = mean_rgb
    if is_aplus_orange(r, g, b):
        return ("white", white)
    if is_aplus_navy(r, g, b):
        return ("white", white)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    if lum < 0.40:
        return ("white", white)
    if lum > 0.60:
        return ("two-color", two_color)
    # 40-60% ambiguous -> white as safer default
    return ("white", white)


def detect_pre_existing_logo(img, anchor, logo_width):
    """Return True if the bottom-right logo zone likely contains content
    already (high RGB std deviation suggests text or graphic elements,
    not a clean solid background)."""
    left = max(0, anchor[0])
    top = max(0, anchor[1])
    right = min(img.width, left + LOGO_ZONE_W)
    bottom = min(img.height, top + LOGO_ZONE_H)
    if right - left < 10 or bottom - top < 10:
        return False
    stds = sample_std_rgb(img, (left, top, right, bottom))
    return any(s > LOGO_ZONE_STD_THRESHOLD for s in stds)


# ----- Composite -----
def composite_one(src_path, two_color, white, dry_run=False):
    name = src_path.stem  # filename without .png
    # Idempotency: never re-process a -with-logo file
    if name.endswith("-with-logo"):
        print(f"  [skip] {src_path.name} already a composited output")
        return None

    config = None
    for prefix, cfg in PER_CANVAS_CONFIG.items():
        if name == prefix:
            config = cfg
            break
    if config is None:
        # No mapping for this filename — skip silently
        return None

    out_path = src_path.with_name(name + "-with-logo.png")

    base = Image.open(src_path).convert("RGBA")
    anchor = config["anchor"]
    logo_width = config["logo_width"]

    # Pre-existing logo / content detection in the placement zone
    has_content = detect_pre_existing_logo(base, anchor, logo_width)
    if has_content:
        print(
            f"  [warn] {src_path.name}: bottom-right zone has content "
            f"(std > {LOGO_ZONE_STD_THRESHOLD}). Source may already contain an "
            f"AI-rendered logo. Composite will still run but QA should verify."
        )

    # Smart logo color selection based on background sample at the anchor
    sample_box = (
        anchor[0] - 50,
        anchor[1] - 50,
        anchor[0],
        anchor[1],
    )
    mean_rgb = sample_mean_rgb(base, sample_box)
    variant_name, logo_rgba = pick_logo_variant(mean_rgb, two_color, white)

    if dry_run:
        print(
            f"  [dry-run] {src_path.name}: bg-sample rgb={mean_rgb} -> "
            f"{variant_name} variant, write {out_path.name}"
        )
        return out_path

    aspect = logo_rgba.height / logo_rgba.width
    target_h = int(logo_width * aspect)
    logo_resized = logo_rgba.resize((logo_width, target_h), Image.LANCZOS)
    hardclamp_alpha(logo_resized)

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(logo_resized, anchor, logo_resized)
    result = Image.alpha_composite(base, layer)
    result.save(out_path, "PNG")
    print(
        f"  [ok]   {src_path.name} -> {out_path.name}  "
        f"(variant={variant_name}, bg={mean_rgb}, {logo_width}x{target_h})"
    )
    return out_path


# ----- Main -----
def main():
    parser = argparse.ArgumentParser(
        description="Composite A+ logo onto a bundle's flat graphics (idempotent, smart color, halo-free)."
    )
    parser.add_argument("--bundle", required=True, help="Path to bundle directory")
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no writes")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process even if -with-logo file exists (overwrites it).",
    )
    args = parser.parse_args()

    if not LOGO_PATH.exists():
        print(f"ERROR: logo source not found at {LOGO_PATH}", file=sys.stderr)
        return 1

    bundle = Path(args.bundle).resolve()
    gfx = bundle / "graphics"
    if not gfx.is_dir():
        print(f"ERROR: graphics dir not found: {gfx}", file=sys.stderr)
        return 1

    two_color = chroma_keyed_logo()
    white = white_variant(two_color)

    pngs = sorted(p for p in gfx.glob("*.png"))
    if not pngs:
        print(f"WARNING: no .png files in {gfx}", file=sys.stderr)
        return 0

    print(f"Compositing logos in {gfx}")
    print(f"  Logo source: {LOGO_PATH}")
    print(f"  Two-color variant + white variant prepared (hard-alpha)")
    print(f"  Files: {len(pngs)}")
    print()

    processed = 0
    for src in pngs:
        # Skip non-flat photographic files and pre-composited files
        if any(src.name.startswith(p) for p in SKIP_PREFIXES):
            print(f"  [skip] {src.name} (photographic / composited elsewhere)")
            continue
        if src.stem.endswith("-with-logo") and not args.force:
            continue
        if composite_one(src, two_color, white, dry_run=args.dry_run):
            processed += 1

    print(f"\nDone. {processed} file(s) composited.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

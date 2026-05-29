#!/usr/bin/env python3
"""Diagnose whether an AI-generated graphic has pre-existing content in
the LOGO PLACEMENT ZONE — the exact rectangle where the real A+ logo
will land during composite.

The detection logic per filename (from PER_CANVAS_CONFIG in
scripts/composite-logo.py):

  - 1024x1536 carousel slides: logo anchor (~830-850, 1360), width 140
    -> sampled box ~(830, 1360, 1000, 1510)
  - 1536x1024 social-card / pull-quote / topic-graphic: logo anchor
    (1360, 850), width 150 -> sampled box ~(1360, 850, 1510, 1000)

Usage:
    python3 scripts/shared/diagnose-logo-zone.py PATH1.png [PATH2.png ...]

Reports per file:
  - logo zone RGB mean (background color)
  - logo zone RGB std deviation (variance)
  - verdict: "clean" if max(std) < 20, "CONTENT DETECTED" if higher
"""
import sys
from pathlib import Path
from PIL import Image, ImageStat


# Match the same zones the composite script uses
ZONES_BY_CANVAS = {
    # 1024x1536 portrait carousel
    (1024, 1536): (830, 1360, 1000, 1510),
    # 1536x1024 landscape social card / pull-quote / topic
    (1536, 1024): (1360, 850, 1510, 1000),
}


def diagnose(p):
    img = Image.open(p).convert("RGB")
    W, H = img.size
    box = ZONES_BY_CANVAS.get((W, H))
    if box is None:
        # Fallback: assume bottom-right 200x150 area
        box = (W - 200, H - 200, W - 30, H - 30)
    crop = img.crop(box)
    mean = ImageStat.Stat(crop).mean
    std = ImageStat.Stat(crop).stddev
    max_std = max(std)
    verdict = "clean" if max_std < 20 else "CONTENT DETECTED (AI may have added a logo)"
    print(
        f"{p.name:50}  size={W}x{H:<5}  zone={box}  "
        f"bg=rgb({int(mean[0])},{int(mean[1])},{int(mean[2])})  "
        f"max_std={max_std:5.1f}  -> {verdict}"
    )
    return max_std


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    bad = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"missing: {p}", file=sys.stderr)
            continue
        std = diagnose(p)
        if std >= 20:
            bad += 1
    if bad:
        print(f"\n{bad} file(s) flagged with logo-zone content.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

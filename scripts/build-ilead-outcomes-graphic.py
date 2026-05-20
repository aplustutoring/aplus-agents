#!/usr/bin/env python3
"""
Build the iLEAD 2024-25 Tier 3 outcomes data-viz graphic as a permanent
A+ Tutoring brand asset.

This is the canonical iLEAD outcomes graphic used across A+ marketing.
Run this whenever the iLEAD data changes (typically once per school year)
to refresh the brand asset in both brand kits.

Output:
  aplus-b2b-brand-kit/ilead-outcomes-graphic.png
  aplus-b2c-brand-kit/ilead-outcomes-graphic.png

Numbers are hardcoded in this script (not parameterized) on purpose so the
canonical brand asset cannot accidentally drift. Update the constants
below when the underlying case studies are updated.

Source of truth: aplus-fact-check SKILL v1.2 verified table.
Constants verified 2026-05-19.
"""
import sys
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import Wedge

# Register A+ brand fonts (Playfair Display + DM Sans) per aplus-graphic-prompts v2.0
BRAND_FONTS_DIR = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-b2b-brand-kit/fonts")
for _ttf in BRAND_FONTS_DIR.glob("*.ttf"):
    try:
        fm.fontManager.addfont(str(_ttf))
    except Exception:
        pass

def _find_font(*candidates):
    for c in candidates:
        for f in fm.fontManager.ttflist:
            if c.lower() in f.name.lower():
                return f.name
    return None

HEADING_FONT = _find_font("Playfair Display", "Playfair", "Georgia") or "serif"
BODY_FONT = _find_font("DM Sans", "Helvetica", "Arial") or "sans-serif"

# A+ brand palette
NAVY = "#1A3A52"
ORANGE = "#EF5829"
WHITE = "#FFFFFF"
RING_BG = "#34526F"
SUBLABEL_GRAY = "#B0BEC5"

# Canonical iLEAD Tier 3 data (2024-25 school year)
# Source: aplus-fact-check SKILL v1.2 verified table.
# If this changes, update HERE and re-run.
DATA = [
    {"pct": 75.0,  "primary": "Math Tier 3",
     "sub": "12 students, 9 improved"},
    {"pct": 87.5, "primary": "ELA Tier 3",
     "sub": "8 students, 7 improved"},
    {"pct": 80.0, "primary": "Combined",
     "sub": "20 students, 16 improved"},
]

HEADLINE = "iLEAD 2024-25 Tier 3 Outcomes"
FOOTER = "Source: A+ Tutoring published case studies"

OUTPUTS = [
    Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-b2b-brand-kit/ilead-outcomes-graphic.png"),
    Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-b2c-brand-kit/ilead-outcomes-graphic.png"),
]


def format_pct(p):
    return f"{int(p)}%" if p == int(p) else f"{p}%"


def build_ring(ax, percentage, label_primary, label_sub):
    cx, cy, r, w = 0.5, 0.62, 0.32, 0.05
    bg = Wedge((cx, cy), r, 0, 360, width=w, color=RING_BG)
    ax.add_patch(bg)
    sweep = (percentage / 100.0) * 360.0
    theta1 = 90.0 - sweep
    theta2 = 90.0
    orange = Wedge((cx, cy), r, theta1, theta2, width=w, color=ORANGE)
    ax.add_patch(orange)
    ax.text(cx, cy, format_pct(percentage),
            ha="center", va="center", fontfamily=HEADING_FONT,
            fontsize=44, fontweight="bold", color=WHITE)
    ax.text(cx, 0.20, label_primary,
            ha="center", va="center", fontfamily=BODY_FONT,
            fontsize=15, fontweight="bold", color=WHITE)
    ax.text(cx, 0.11, label_sub,
            ha="center", va="center", fontfamily=BODY_FONT,
            fontsize=11, color=SUBLABEL_GRAY)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(NAVY)


def build_graphic(out_path):
    fig = plt.figure(figsize=(10.8, 10.8), dpi=100, facecolor=NAVY)
    fig.text(0.5, 0.92, HEADLINE,
             ha="center", va="center", fontfamily=HEADING_FONT,
             fontsize=30, fontweight="bold", color=WHITE)
    n = len(DATA)
    for i, row in enumerate(DATA):
        ax = fig.add_subplot(1, n, i + 1)
        build_ring(ax, row["pct"], row["primary"], row["sub"])
    plt.subplots_adjust(left=0.04, right=0.96, top=0.85, bottom=0.10)
    fig.text(0.04, 0.04, FOOTER,
             ha="left", va="bottom", fontfamily=BODY_FONT,
             fontsize=11, color=SUBLABEL_GRAY)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=100, facecolor=NAVY, edgecolor="none")
    plt.close(fig)
    print(f"Saved: {out_path}")


def composite_logo(out_path):
    """Apply the white-variant A+ logo to bottom-right of the rendered graphic.

    Mirrors the chroma-key + alpha_composite pattern from
    aplus-content/*/graphics/_composite_logo_v2.py.
    """
    from PIL import Image, ImageDraw
    logo_path = Path("/Users/romanslavinsky/Desktop/logo.png")
    if not logo_path.exists():
        print(f"  WARN: logo not found at {logo_path}; skipping composite")
        return

    raw = Image.open(logo_path).convert("RGBA")
    # chroma-key whites to alpha 0
    corners = [raw.getpixel((0, 0)), raw.getpixel((raw.width - 1, 0)),
               raw.getpixel((0, raw.height - 1)), raw.getpixel((raw.width - 1, raw.height - 1))]
    if max(p[3] for p in corners) > 0:
        px = raw.load()
        for y in range(raw.height):
            for x in range(raw.width):
                r, g, b, a = px[x, y]
                if r >= 240 and g >= 240 and b >= 240:
                    px[x, y] = (r, g, b, 0)
    # white variant
    px = raw.load()
    for y in range(raw.height):
        for x in range(raw.width):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (255, 255, 255, a)

    base = Image.open(out_path).convert("RGBA")
    bg = base.getpixel((50, 50))
    # Erase a small bottom-right area, paste white logo
    ImageDraw.Draw(base).rectangle((820, 820, 1020, 1020), fill=bg)
    logo_resized = raw.resize((100, 100), Image.LANCZOS)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(logo_resized, (890, 890), logo_resized)
    result = Image.alpha_composite(base, layer)
    result.save(out_path, "PNG")
    print(f"  Logo composited: {out_path.name}")


def main():
    # Build once, then copy + composite into each target location
    tmp = Path("/tmp/ilead-outcomes-graphic.png")
    build_graphic(tmp)

    for out_path in OUTPUTS:
        shutil.copy(tmp, out_path)
        composite_logo(out_path)

    tmp.unlink(missing_ok=True)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

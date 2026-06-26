#!/usr/bin/env python3
"""
Deterministic creative-graphic builder for A+ Tutoring weekly bundles.

Renders a 1080x1080 square data-visualization graphic with 3 percentage circles
showing proportional fills (matplotlib Wedge patches, not AI). Used when an
AI-generated infographic would risk visual inaccuracy on the ring fills.

Usage examples:
    # iLEAD outcomes (the default A+ use case):
    python3 scripts/b2b/build-creative-graphic.py \\
        --output graphics/creative-graphic.png \\
        --circles "75:Math Tier 3:12 students" \\
                  "87.5:ELA Tier 3:8 students" \\
                  "80:Combined:20 students"

    # Custom headline / footer:
    python3 scripts/b2b/build-creative-graphic.py \\
        --output out.png \\
        --headline "Spring 2026 outcomes" \\
        --footer  "Source: internal A+ dashboard" \\
        --circles "62:Reading:32 students" \\
                  "71:Math:32 students"

Each circle spec is "percentage:primary_label:sub_label". The percentage
determines the orange-ring fill proportionally; the labels render below
the ring. Center of each ring shows the percentage value.
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge

# A+ brand palette (verified hex codes)
NAVY = "#1A3A52"
ORANGE = "#EF5829"
WHITE = "#FFFFFF"
RING_BG = "#34526F"        # navy with slight lift — visible under orange
SUBLABEL_GRAY = "#B0BEC5"  # muted gray for sublabels and footer


def parse_circle_spec(spec):
    """Parse 'percentage:label:sublabel' into a tuple."""
    parts = spec.split(":")
    if len(parts) != 3:
        raise ValueError(f"Circle spec must be 'percentage:label:sublabel', got: {spec!r}")
    pct = float(parts[0])
    if not 0 <= pct <= 100:
        raise ValueError(f"Percentage must be 0-100, got: {pct}")
    return (pct, parts[1].strip(), parts[2].strip())


def format_pct(pct):
    """Render an integer percentage as '75%', a float as '87.5%'."""
    if pct == int(pct):
        return f"{int(pct)}%"
    return f"{pct}%"


def build_ring(ax, percentage, label_primary, label_sub):
    """Render one donut ring with proportional orange fill + labels.

    Layout inside the axes (axes coordinates 0-1):
      Ring center: (0.5, 0.62)
      Ring outer radius: 0.32, ring width: 0.05
      Center percentage text at (0.5, 0.62)
      Primary label below ring at (0.5, 0.20)
      Sub-label below primary at (0.5, 0.11)
    """
    cx, cy, r, w = 0.5, 0.62, 0.32, 0.05

    # Full background ring
    bg = Wedge((cx, cy), r, 0, 360, width=w, color=RING_BG, edgecolor="none")
    ax.add_patch(bg)

    # Orange arc — clockwise from top (90 deg) for `percentage` percent of 360
    # matplotlib Wedge fills counter-clockwise from theta1 to theta2,
    # so we set theta1 = 90 - sweep, theta2 = 90 so the visible arc is the
    # FIRST percentage% sweeping clockwise from the 12 o'clock position.
    sweep = (percentage / 100.0) * 360.0
    theta1 = 90.0 - sweep
    theta2 = 90.0
    orange = Wedge((cx, cy), r, theta1, theta2, width=w, color=ORANGE, edgecolor="none")
    ax.add_patch(orange)

    # Center percentage text — large + bold
    ax.text(cx, cy, format_pct(percentage),
            ha="center", va="center",
            fontsize=44, fontweight="bold", color=WHITE)

    # Primary label below ring
    ax.text(cx, 0.20, label_primary,
            ha="center", va="center",
            fontsize=15, fontweight="bold", color=WHITE)

    # Sub-label (e.g., student count)
    ax.text(cx, 0.11, label_sub,
            ha="center", va="center",
            fontsize=12, color=SUBLABEL_GRAY)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(NAVY)


def main():
    parser = argparse.ArgumentParser(
        description="Build a deterministic A+ data-viz creative-graphic with proportional ring fills."
    )
    parser.add_argument("--output", required=True, help="Output PNG path")
    parser.add_argument("--circles", nargs="+", required=True,
                        help="One or more circle specs: 'percentage:label:sublabel'")
    parser.add_argument("--headline", default="iLEAD 2024-25 Tier 3 Outcomes",
                        help="Top headline text")
    parser.add_argument("--footer", default="Source: A+ Tutoring published case studies",
                        help="Bottom footer text")
    parser.add_argument("--size", type=int, default=1080,
                        help="Square output edge length in pixels")
    args = parser.parse_args()

    try:
        circles = [parse_circle_spec(spec) for spec in args.circles]
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not circles or len(circles) > 5:
        print("ERROR: provide 1-5 circles", file=sys.stderr)
        return 1

    # Figure: square at 100 dpi
    inches = args.size / 100.0
    fig = plt.figure(figsize=(inches, inches), dpi=100, facecolor=NAVY)

    # Headline
    fig.text(0.5, 0.92, args.headline,
             ha="center", va="center",
             fontsize=30, fontweight="bold", color=WHITE)

    # Subplots — one per circle in a horizontal row
    n = len(circles)
    for i, (pct, label, sub) in enumerate(circles):
        ax = fig.add_subplot(1, n, i + 1)
        build_ring(ax, pct, label, sub)

    plt.subplots_adjust(left=0.04, right=0.96, top=0.85, bottom=0.10)

    # Footer at bottom-left (logo composite will land in bottom-right)
    fig.text(0.04, 0.04, args.footer,
             ha="left", va="bottom",
             fontsize=11, color=SUBLABEL_GRAY)

    # Save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=100, facecolor=NAVY, edgecolor="none")
    plt.close(fig)

    # Verify the saved file is the expected size
    actual = out_path.stat().st_size
    print(f"Saved: {out_path} ({actual:,} bytes)")

    # Verify pixel dimensions
    try:
        from PIL import Image
        with Image.open(out_path) as im:
            print(f"Dimensions: {im.size[0]}x{im.size[1]}")
            if im.size != (args.size, args.size):
                print(f"WARNING: expected {args.size}x{args.size}", file=sys.stderr)
    except ImportError:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())

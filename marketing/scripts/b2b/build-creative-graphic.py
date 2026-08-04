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
import textwrap
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


def fit_text(text, width, fontsize, min_fontsize=None):
    """Wrap `text` to `width` characters per line and shrink the font as it spills onto
    extra lines, so long labels stay inside the frame instead of running off the canvas.

    Returns (wrapped_text, fontsize). The type shrinks ~12 percent per extra line, floored
    at min_fontsize (default 55 percent of the requested size) so it stays legible. Labels
    are never cut: over-long copy gets smaller and taller, matching the b2c timeline
    graphic's density-aware sizing.
    """
    text = " ".join(str(text or "").split())
    if not text:
        return "", fontsize
    floor = min_fontsize if min_fontsize is not None else fontsize * 0.55
    # break_long_words=False so a long token never splits mid-word ("percenta / ge").
    lines = textwrap.wrap(text, width=max(int(width), 1),
                          break_long_words=False, break_on_hyphens=False) or [text]
    fontsize = max(floor, fontsize * (0.88 ** (len(lines) - 1)))
    # A single token wider than the wrap width still overflows its line, so scale the
    # type down by how far past the width the longest line actually runs.
    longest = max(len(ln) for ln in lines)
    if longest > width:
        fontsize = max(floor, fontsize * (width / longest))
    return "\n".join(lines), fontsize


def shrink_into_canvas(fig, artists, min_fontsize=7, margin=0.02):
    """Shrink figure-level text until its RENDERED box sits inside the canvas, keeping a
    `margin` (share of the canvas edge) of clear space so it never sits flush to an edge.

    Wrapping alone is not enough: a headline wrapped onto several lines grows vertically
    from its fixed centre and can still run off the top of a smaller --size canvas.
    Measured, so it is a no-op whenever the text already fits (including at the default
    1080px, where nothing changes).
    """
    fig.canvas.draw()
    width, height = fig.get_size_inches() * fig.dpi
    pad_x, pad_y = margin * width, margin * height
    for artist in artists:
        for _ in range(14):
            box = artist.get_window_extent()
            inside = (box.x0 >= pad_x and box.y0 >= pad_y
                      and box.x1 <= width - pad_x and box.y1 <= height - pad_y)
            if inside or artist.get_fontsize() <= min_fontsize:
                break
            # shrink by the worst overshoot on any side, as a share of the box
            over_x = max(box.x1 - (width - pad_x), pad_x - box.x0, 0) / (box.width or 1)
            over_y = max(box.y1 - (height - pad_y), pad_y - box.y0, 0) / (box.height or 1)
            factor = max(1.0 - max(over_x, over_y), 0.5) * 0.98
            artist.set_fontsize(max(min_fontsize, artist.get_fontsize() * factor))
            fig.canvas.draw()


# Share of its own column the centre percentage may occupy before it runs into the
# neighbouring ring. Deliberately the column width, not the ring's inner diameter: at
# 44pt a wide value like '87.5%' already straddles the ring stroke in the canonical
# 3-ring graphic, and restyling that approved asset is a separate decision from keeping
# text inside its frame.
PCT_MAX_COLUMN_FRACTION = 0.94


def settle_ring_text(fig, rings, pad_px=6, min_pct_fontsize=14):
    """Resolve ring text against the layout that actually got drawn.

    Two fixes, both measured rather than estimated (font metrics vary by font and
    platform, and the layout is not known when the artists are created):
      1. The centre percentage shrinks until it fits its own column — at 44pt it is wider
         than the column once 4-5 rings share the row, and spills into its neighbour.
      2. Each sub-label is pushed down until it clears its primary label. The nominal 0.09
         gap between the two slots is thinner than the type itself once the axes shrinks or
         a primary wraps to 2+ lines, and the two overprint.

    Both are no-ops for the canonical 3-ring iLEAD graphic, which renders unchanged.
    """
    fig.canvas.draw()
    for pct, primary, sub in rings:
        max_px = PCT_MAX_COLUMN_FRACTION * pct.axes.get_window_extent().width
        for _ in range(12):
            width = pct.get_window_extent().width
            if width <= max_px or pct.get_fontsize() <= min_pct_fontsize:
                break
            pct.set_fontsize(max(min_pct_fontsize, pct.get_fontsize() * (max_px / width) * 0.98))
            fig.canvas.draw()

        trans = sub.axes.transAxes
        for _ in range(8):
            pb, sb = primary.get_window_extent(), sub.get_window_extent()
            gap = pb.y0 - sb.y1                       # primary sits above the sub-label
            if gap >= pad_px or min(pb.x1, sb.x1) <= max(pb.x0, sb.x0):
                break                                 # clear vertically, or side by side
            x_px, y_px = trans.transform((0.5, sub.get_position()[1]))
            sub.set_y(trans.inverted().transform((x_px, y_px - (pad_px - gap)))[1])
            fig.canvas.draw()


def build_ring(ax, percentage, label_primary, label_sub, columns=1, scale=1.0):
    """Render one donut ring with proportional orange fill + labels.

    Layout inside the axes (axes coordinates 0-1):
      Ring center: (0.5, 0.62)
      Ring outer radius: 0.32, ring width: 0.05
      Center percentage text at (0.5, 0.62)
      Primary label below ring at (0.5, 0.20)
      Sub-label below primary at (0.5, 0.11)

    `columns` is the number of rings in the row: labels are wrapped and shrunk to the
    width of their own column so a long label never spills into its neighbour or off the
    canvas edge. `scale` is the output size relative to the default 1080px, since the font
    sizes here are absolute points and a smaller canvas therefore fits fewer characters.
    Returns the (percentage, primary, sub) text artists so settle_ring_text can resolve
    them against the drawn layout.
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
    pct = ax.text(cx, cy, format_pct(percentage),
                  ha="center", va="center",
                  fontsize=44, fontweight="bold", color=WHITE)

    # Primary label below ring — wrapped + shrunk to fit this ring's column
    primary_text, primary_fs = fit_text(label_primary, 86 * scale // max(columns, 1), 15)
    primary = ax.text(cx, 0.20, primary_text,
                      ha="center", va="center", multialignment="center",
                      fontsize=primary_fs, fontweight="bold", color=WHITE)

    # Sub-label (e.g., student count)
    sub_text, sub_fs = fit_text(label_sub, 108 * scale // max(columns, 1), 12)
    sub = ax.text(cx, 0.11, sub_text,
                  ha="center", va="center", multialignment="center",
                  fontsize=sub_fs, color=SUBLABEL_GRAY)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(NAVY)
    return pct, primary, sub


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

    # Font sizes below are absolute points, so a non-default --size fits proportionally
    # fewer (or more) characters per line.
    scale = args.size / 1080.0

    # Headline — wrapped + shrunk so a long headline never runs off the canvas
    headline_text, headline_fs = fit_text(args.headline, 43 * scale, 30)
    headline = fig.text(0.5, 0.92, headline_text,
                        ha="center", va="center", multialignment="center",
                        fontsize=headline_fs, fontweight="bold", color=WHITE)

    # Subplots — one per circle in a horizontal row
    n = len(circles)
    rings = []
    for i, (pct, label, sub) in enumerate(circles):
        ax = fig.add_subplot(1, n, i + 1)
        rings.append(build_ring(ax, pct, label, sub, columns=n, scale=scale))

    plt.subplots_adjust(left=0.04, right=0.96, top=0.85, bottom=0.10)

    # Ring text is sized/positioned before the layout is known, so settle it now.
    settle_ring_text(fig, rings)

    # Footer at bottom-left (logo composite will land in bottom-right, so the footer only
    # gets ~70 percent of the width before it would collide with the logo zone)
    footer_text, footer_fs = fit_text(args.footer, 82 * scale, 11)
    footer = fig.text(0.04, 0.04, footer_text,
                      ha="left", va="bottom", multialignment="left",
                      fontsize=footer_fs, color=SUBLABEL_GRAY)

    # Wrapped blocks grow from a fixed anchor, so make sure they still land on-canvas.
    shrink_into_canvas(fig, [headline, footer])

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

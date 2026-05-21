#!/usr/bin/env python3
"""Build the 3-frame A+ Tutoring Instagram Story sequence for a weekly bundle.

Replaces the prior single-photo IG story and the IG feed post (both
removed in aplus-graphic-prompts v2.2, 2026-05-20).

Per Danielle's design principles:
  - NO AI-generated people of any kind
  - Brand-forward typography (Playfair Display + DM Sans)
  - Heavy A+ navy + orange + gold
  - 1080x1920 vertical (9:16)
  - Logo positioned consistently bottom-center across all 3 frames
  - "Swipe →" indicator on frames 1 and 2 only
  - Frame 3 reserves top-center cleanspace for the user-added link sticker

Frame 1 — HOOK
  Background: A+ Navy.
  Big Playfair Display question/stat headline.
  Optional DM Sans subhead beneath.
  Logo bottom-center (white variant).
  "Swipe →" indicator bottom-right.

Frame 2 — KEY INSIGHT
  Background: A+ Orange.
  A large stat or short claim rendered Playfair Display 700.
  Supporting line in DM Sans below.
  Logo bottom-center (white variant).
  "Swipe →" indicator bottom-right.

Frame 3 — CTA
  Background: A+ Navy.
  Reserved 220px tall top-center cleanspace for the IG link sticker.
  Big Playfair Display CTA copy.
  DM Sans "Tap the link sticker above" instruction.
  Logo bottom-center (white variant).
  NO swipe indicator.

Inputs (from blog-anchor-meta.md):
  instagram_story_frames:
    - "Frame 1 hook text"      # appears as headline on frame 1
    - "Frame 2 insight text"   # appears as headline on frame 2
    - "Frame 3 CTA text"       # appears as headline on frame 3

Optional (each frame can have a subhead):
  instagram_story_subheads:
    - "frame 1 subhead"
    - "frame 2 subhead"
    - "frame 3 subhead"

Usage:
  python3 scripts/build-instagram-stories.py --bundle aplus-content/2026-05-19-weekly/
"""
import argparse
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
from PIL import Image, ImageDraw


# ----- Brand palette -----
NAVY = "#1A3A52"
ORANGE = "#EF5829"
GOLD = "#F4A261"
WHITE = "#FFFFFF"
OFF_WHITE = "#FAF7F2"


# ----- Font registration (Playfair Display + DM Sans) -----
BRAND_FONTS_DIR = Path(__file__).resolve().parent.parent / "aplus-b2b-brand-kit" / "fonts"
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

LOGO_PATH = Path("/Users/romanslavinsky/Desktop/logo.png")


# ----- Meta parsing -----
def extract_list(text, field):
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
        elif item.startswith("'") and item.endswith("'"):
            item = item[1:-1]
        items.append(item)
    return items


# ----- Frame renderers -----
def _frame_canvas(bg_color):
    """Return (fig, ax) with the 1080x1920 vertical canvas set up."""
    # 1080x1920 at dpi=100 -> figsize 10.8 x 19.2
    fig = plt.figure(figsize=(10.8, 19.2), dpi=100, facecolor=bg_color)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.set_facecolor(bg_color)
    return fig, ax


def _wrap(text, max_chars):
    """Naive word-wrap to a max line length. Returns list of lines."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        candidate = (cur + " " + w).strip()
        if len(candidate) <= max_chars:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _swipe_indicator(ax, color=WHITE):
    """Bottom-right swipe indicator on frames 1 and 2."""
    ax.text(95, 8, "Swipe →", ha="right", va="center",
            fontfamily=BODY_FONT, fontsize=20, fontweight="bold", color=color, alpha=0.95)


def render_frame_1(headline, subhead, out_path):
    fig, ax = _frame_canvas(NAVY)
    lines = _wrap(headline, max_chars=22)
    # Render headline centered, large
    y = 65
    line_step = 7
    if len(lines) > 4:
        line_step = 5.5
    for line in lines:
        ax.text(50, y, line, ha="center", va="center",
                fontfamily=HEADING_FONT, fontsize=64, fontweight="bold",
                color=WHITE)
        y -= line_step
    if subhead:
        sub_lines = _wrap(subhead, max_chars=42)
        ys = 30
        for line in sub_lines:
            ax.text(50, ys, line, ha="center", va="center",
                    fontfamily=BODY_FONT, fontsize=24, fontweight="normal",
                    color=GOLD, alpha=0.95)
            ys -= 4
    _swipe_indicator(ax)
    fig.savefig(out_path, dpi=100, facecolor=NAVY, edgecolor="none",
                bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def render_frame_2(headline, subhead, out_path):
    fig, ax = _frame_canvas(ORANGE)
    lines = _wrap(headline, max_chars=18)
    # The headline often contains a percentage or short data point — render large
    y = 62
    line_step = 8
    if len(lines) > 3:
        line_step = 6
    for line in lines:
        ax.text(50, y, line, ha="center", va="center",
                fontfamily=HEADING_FONT, fontsize=80, fontweight="bold",
                color=WHITE)
        y -= line_step
    if subhead:
        sub_lines = _wrap(subhead, max_chars=44)
        ys = 30
        for line in sub_lines:
            ax.text(50, ys, line, ha="center", va="center",
                    fontfamily=BODY_FONT, fontsize=24, fontweight="normal",
                    color=WHITE, alpha=0.95)
            ys -= 4
    _swipe_indicator(ax, color=WHITE)
    fig.savefig(out_path, dpi=100, facecolor=ORANGE, edgecolor="none",
                bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def render_frame_3(headline, subhead, out_path):
    fig, ax = _frame_canvas(NAVY)
    # v2.3 rule (2026-05-20): NO literal placeholder box or text at the top.
    # Top portion of frame is intentionally minimal. The bottom-of-frame
    # arrow + instruction "↑ Tap the link sticker above" directs Roman /
    # Danielle to drop the Instagram link sticker in the upper third
    # before posting. No artifact, no placeholder.

    # Big CTA headline, raised slightly now that the top region is clean
    lines = _wrap(headline, max_chars=20)
    y = 62
    line_step = 7
    if len(lines) > 3:
        line_step = 6
    for line in lines:
        ax.text(50, y, line, ha="center", va="center",
                fontfamily=HEADING_FONT, fontsize=68, fontweight="bold",
                color=WHITE)
        y -= line_step

    if subhead:
        sub_lines = _wrap(subhead, max_chars=42)
        ys = 36
        for line in sub_lines:
            ax.text(50, ys, line, ha="center", va="center",
                    fontfamily=BODY_FONT, fontsize=24, fontweight="normal",
                    color=GOLD, alpha=0.95)
            ys -= 4

    # Bottom instruction (placed safely above the logo zone)
    ax.text(50, 22, "↑  Tap the link sticker above", ha="center", va="center",
            fontfamily=BODY_FONT, fontsize=22, fontweight="bold",
            color=ORANGE, alpha=0.95)

    # NO swipe indicator on frame 3 (final frame)
    fig.savefig(out_path, dpi=100, facecolor=NAVY, edgecolor="none",
                bbox_inches="tight", pad_inches=0)
    plt.close(fig)


# ----- Logo composite -----
ALPHA_THRESHOLD = 128  # v2.3: anti-halo. Any pixel with alpha < this becomes
                       # fully transparent; any pixel with alpha >= this becomes
                       # fully opaque. Eliminates soft anti-aliased edges that
                       # showed up as faint rectangular halos on dark backgrounds.


def _hardclamp_alpha(rgba_img):
    """Hard-clamp the alpha channel to binary (0 or 255).

    This eliminates soft anti-aliased edges that bleed light into a dark
    background and render as a faint halo around the logo. After this
    pass, every pixel is either fully transparent or fully opaque — no
    in-between semi-transparency.
    """
    px = rgba_img.load()
    for y in range(rgba_img.height):
        for x in range(rgba_img.width):
            r, g, b, a = px[x, y]
            if a < ALPHA_THRESHOLD:
                px[x, y] = (r, g, b, 0)
            else:
                px[x, y] = (r, g, b, 255)
    return rgba_img


def _white_logo():
    """Return a white-variant of the A+ logo (RGBA, chroma-keyed, hard-alpha)."""
    raw = Image.open(LOGO_PATH).convert("RGBA")
    # 1. Chroma-key whites to alpha 0 (covers the case where the source PNG
    #    has opaque white corners instead of transparent corners).
    px = raw.load()
    for y in range(raw.height):
        for x in range(raw.width):
            r, g, b, a = px[x, y]
            if r >= 240 and g >= 240 and b >= 240:
                px[x, y] = (r, g, b, 0)
    # 2. White color variant (every still-visible pixel becomes pure white,
    #    keeping its alpha — we'll hard-clamp alpha next).
    px = raw.load()
    for y in range(raw.height):
        for x in range(raw.width):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (255, 255, 255, a)
    # 3. Hard alpha threshold (v2.3) — eliminates soft edges.
    _hardclamp_alpha(raw)
    return raw


def composite_logo_bottom_center(png_path, logo_rgba, logo_width=220, bottom_margin=120):
    """Composite the (already chroma-keyed, hard-alpha) logo at bottom-center.

    NO erase-rectangle step (removed v2.3). The Frame prompts reserve clean
    space, and the hard-alpha logo composites onto whatever pixels are
    underneath without leaving a halo.
    """
    base = Image.open(png_path).convert("RGBA")
    # Preserve aspect ratio
    aspect = logo_rgba.height / logo_rgba.width
    target_h = int(logo_width * aspect)
    logo_resized = logo_rgba.resize((logo_width, target_h), Image.LANCZOS)
    # LANCZOS re-introduces soft edges; clamp again after resize
    _hardclamp_alpha(logo_resized)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    x = (base.width - logo_width) // 2
    y = base.height - target_h - bottom_margin
    layer.paste(logo_resized, (x, y), logo_resized)
    result = Image.alpha_composite(base, layer)
    result.save(png_path, "PNG")


# ----- Main -----
def main():
    parser = argparse.ArgumentParser(
        description="Build the 3-frame Instagram Story sequence for a weekly bundle."
    )
    parser.add_argument("--bundle", required=True, help="Bundle directory")
    args = parser.parse_args()

    bundle = Path(args.bundle).resolve()
    meta_path = bundle / "blog-anchor-meta.md"
    out_dir = bundle / "graphics"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not meta_path.exists():
        print(f"ERROR: meta not found: {meta_path}", file=sys.stderr)
        return 1

    text = meta_path.read_text()
    frames = extract_list(text, "instagram_story_frames")
    subheads = extract_list(text, "instagram_story_subheads")

    if len(frames) < 3:
        print(
            f"ERROR: instagram_story_frames must have 3 entries; "
            f"meta has {len(frames)}.",
            file=sys.stderr,
        )
        return 1

    # Pad subheads to 3 (empty strings are fine)
    while len(subheads) < 3:
        subheads.append("")

    print(f"Building 3-frame IG story sequence into {out_dir}")
    print(f"  HEADING_FONT={HEADING_FONT}  BODY_FONT={BODY_FONT}")

    paths = [
        out_dir / "instagram-story-1.png",
        out_dir / "instagram-story-2.png",
        out_dir / "instagram-story-3.png",
    ]
    renderers = [render_frame_1, render_frame_2, render_frame_3]
    for i, (renderer, path) in enumerate(zip(renderers, paths), start=1):
        renderer(frames[i - 1], subheads[i - 1], path)
        size = path.stat().st_size
        print(f"  frame {i}: '{frames[i-1][:50]}{'...' if len(frames[i-1])>50 else ''}' -> {path.name} ({size:,} bytes)")

    # Composite logo bottom-center on all 3 frames
    logo = _white_logo()
    for path in paths:
        composite_logo_bottom_center(path, logo, logo_width=220, bottom_margin=160)
        print(f"  logo composited: {path.name}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

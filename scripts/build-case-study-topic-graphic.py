#!/usr/bin/env python3
"""
Generalized milestone-timeline data-viz for any A+ case study (qualitative-led).

Reads milestone data from the bundle's metadata.md instead of hardcoding it,
and takes a --bundle argument so it works for every case study.

metadata.md must contain a milestones block in this format:

    milestones:
      - "Feb | Quotient rule | Strong understanding"
      - "Early Mar | Radical notation | Strong progress"
      - "Mid Mar | Geometric perspective | Strong spatial reasoning"
      - "Late Mar | Exponential growth | Demonstrated perseverance"
      - "Apr | Parabolas | Pattern recognition"

Each entry is "month | topic | verbatim_phrase". 3-6 milestones recommended.
The script spaces them evenly across the timeline automatically.

Also reads (optional):
    milestone_title:    headline (default "{Pseudonym}'S RECOVERY")
    milestone_subtitle: sub-line under the title
    milestone_footer:   bold footer takeaway
    milestone_footer_sub: italic orange sub-footer

Usage:
    python3 scripts/build-case-study-topic-graphic.py --bundle aplus-content/{bundle}/
"""
import argparse
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

NAVY = "#1A3A52"
ORANGE = "#EF5829"
GOLD = "#F4A261"
WHITE = "#FFFFFF"

REPO = Path(__file__).resolve().parents[1]
BRAND_FONTS_DIR = REPO / "aplus-b2b-brand-kit" / "fonts"
for ttf in BRAND_FONTS_DIR.glob("*.ttf"):
    try:
        fm.fontManager.addfont(str(ttf))
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


def parse_meta_field(text, field):
    """Scalar field from metadata.md (fenced block OR standalone line)."""
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


def parse_meta_list(text, field):
    """YAML-style list of strings."""
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

    # Parse milestones
    raw = parse_meta_list(text, "milestones")
    if not raw:
        print("ERROR: no milestones: list in metadata.md", file=sys.stderr)
        print("Add a milestones block (month | topic | phrase per line).", file=sys.stderr)
        return 1
    milestones = []
    for entry in raw:
        parts = [p.strip() for p in entry.split("|")]
        if len(parts) != 3:
            print(f"WARNING: skipping malformed milestone: {entry}", file=sys.stderr)
            continue
        milestones.append(tuple(parts))  # (month, topic, phrase)
    if not milestones:
        print("ERROR: no valid milestones parsed.", file=sys.stderr)
        return 1

    # Derive pseudonym from slug for default title
    slug = parse_meta_field(text, "url_slug")
    pseudonym = slug.split("-")[0].capitalize() if slug else "Student"

    title = parse_meta_field(text, "milestone_title") or f"{pseudonym.upper()}'S RECOVERY"
    subtitle = parse_meta_field(text, "milestone_subtitle") or \
        "Milestones from the tutor's lesson notes"
    footer = parse_meta_field(text, "milestone_footer") or \
        "Steady forward motion, week by week."
    footer_sub = parse_meta_field(text, "milestone_footer_sub") or \
        "Not a finished story. A mid-recovery one."

    # ---- Build figure ----
    fig = plt.figure(figsize=(12.0, 8.0), dpi=100, facecolor=NAVY)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.set_facecolor(NAVY)

    ax.text(50, 92, title, ha="center", va="center",
            fontfamily=HEADING_FONT, fontsize=28, fontweight="bold", color=WHITE)
    ax.text(50, 85, subtitle, ha="center", va="center",
            fontfamily=BODY_FONT, fontsize=14, color=GOLD)

    # Evenly space milestones across x=15..85
    n = len(milestones)
    if n == 1:
        xs = [50]
    else:
        left, right = 15, 85
        xs = [left + (right - left) * i / (n - 1) for i in range(n)]

    ax.plot([xs[0], xs[-1]], [50, 50], color=WHITE, linewidth=2, alpha=0.4, zorder=1)

    for i, ((month, topic, phrase), x) in enumerate(zip(milestones, xs)):
        color = ORANGE if i % 2 == 0 else GOLD
        ax.scatter([x], [50], s=380, color=color, edgecolors=WHITE,
                   linewidths=2.5, zorder=3)
        ax.text(x, 42, month, ha="center", va="center",
                fontfamily=BODY_FONT, fontsize=11, fontweight="bold",
                color=WHITE, alpha=0.85)
        ax.text(x, 62, topic, ha="center", va="center",
                fontfamily=HEADING_FONT, fontsize=13, fontweight="bold", color=WHITE)
        ax.text(x, 70, f'"{phrase}"', ha="center", va="center",
                fontfamily=BODY_FONT, fontsize=10, color=GOLD, style="italic")

    ax.text(50, 28, subtitle if False else
            "Source: weekly lesson notes from the A+ Tutoring tutor",
            ha="center", va="center",
            fontfamily=BODY_FONT, fontsize=10, color=WHITE, alpha=0.7)
    ax.text(50, 18, footer, ha="center", va="center",
            fontfamily=HEADING_FONT, fontsize=16, fontweight="bold", color=WHITE)
    ax.text(50, 11, footer_sub, ha="center", va="center",
            fontfamily=BODY_FONT, fontsize=12, color=ORANGE, style="italic")

    out = bundle / "graphics" / "topic-graphic.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=100, facecolor=NAVY)
    print(f"Saved: {out}")
    print(f"Milestones: {len(milestones)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Topic-specific data viz for May 19 bundle:
21-Day Decision Window Timeline (Summer as Tier 3 Runway).

Deterministic matplotlib build. Output: topic-graphic.png at blog-body-width
landscape (1536x1024, 3:2 aspect, ~150dpi).

Applies aplus-graphic-prompts v2.0:
- Blog-body-width landscape NOT square
- Heavy A+ brand colors (Navy lead, Orange accents, Gold milestone callout)
- Playfair Display headings + DM Sans body
- No date watermark, no 'A+ Tutoring blog' subtitle
- Logo placement handled by separate composite script
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.font_manager as fm
from pathlib import Path

NAVY = "#1A3A52"
ORANGE = "#EF5829"
GOLD = "#F4A261"
WHITE = "#FFFFFF"
OFF_WHITE = "#FAF7F2"
LIGHT_GRAY = "#E8E8E8"
CHARCOAL = "#2E2E2E"

# Font handling: register A+ brand fonts (Playfair Display + DM Sans)
BRAND_FONTS_DIR = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-b2b-brand-kit/fonts")
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

HEADING_FONT = _find_font("Playfair Display", "Playfair", "Georgia", "Times New Roman", "DejaVu Serif") or "serif"
BODY_FONT = _find_font("DM Sans", "Helvetica", "Arial", "DejaVu Sans") or "sans-serif"

fig = plt.figure(figsize=(15.36, 10.24), dpi=100, facecolor=NAVY)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")
ax.set_facecolor(NAVY)

# Title
ax.text(50, 90, "THE 21-DAY DECISION WINDOW", ha="center", va="center",
        fontfamily=HEADING_FONT, fontsize=34, fontweight="bold", color=WHITE)
ax.text(50, 83, "Build Your Tier 3 Summer Runway Before Staffing Locks",
        ha="center", va="center", fontfamily=BODY_FONT, fontsize=18,
        fontweight="normal", color=GOLD)

# Timeline track
track_y = 55
track_left = 8
track_right = 92
ax.plot([track_left, track_right], [track_y, track_y], color=WHITE,
        linewidth=2, alpha=0.5, zorder=1)

# Milestones
milestones = [
    {"x": 8,  "date": "MAY 19",      "label": "Spring MAP\nreports land",  "color": ORANGE, "kind": "today"},
    {"x": 23, "date": "MAY 23",      "label": "Pull spring\nMAP data",     "color": WHITE,  "kind": "step"},
    {"x": 36, "date": "MAY 25",      "label": "Cross-reference\nIEP + EL", "color": WHITE,  "kind": "step"},
    {"x": 50, "date": "MAY 28",      "label": "Lock cohort\n(10-30)",      "color": WHITE,  "kind": "step"},
    {"x": 67, "date": "JUNE 5",      "label": "Confirm staffing\n+ dosage", "color": ORANGE, "kind": "step"},
    {"x": 84, "date": "JULY 8",      "label": "Tier 3 runway\nstarts",     "color": GOLD,   "kind": "launch"},
]

for m in milestones:
    # Dot
    if m["kind"] == "launch":
        ax.scatter([m["x"]], [track_y], s=560, color=GOLD, edgecolors=WHITE,
                   linewidths=3, zorder=3)
    elif m["kind"] == "today":
        ax.scatter([m["x"]], [track_y], s=520, color=ORANGE, edgecolors=WHITE,
                   linewidths=3, zorder=3)
    else:
        ax.scatter([m["x"]], [track_y], s=320, color=NAVY, edgecolors=WHITE,
                   linewidths=2.5, zorder=3)

    # Date above
    ax.text(m["x"], track_y + 7, m["date"], ha="center", va="center",
            fontfamily=BODY_FONT, fontsize=13, fontweight="bold", color=m["color"])
    # Label below
    ax.text(m["x"], track_y - 9, m["label"], ha="center", va="top",
            fontfamily=BODY_FONT, fontsize=12, fontweight="normal", color=WHITE,
            linespacing=1.3)

# "TODAY" marker on May 19
ax.text(8, track_y + 14, "TODAY", ha="center", va="center",
        fontfamily=BODY_FONT, fontsize=10, fontweight="bold", color=ORANGE,
        bbox=dict(boxstyle="round,pad=0.5", facecolor=NAVY, edgecolor=ORANGE,
                  linewidth=1.5))

# Lower band: key constraints
band_y = 18
ax.add_patch(mpatches.FancyBboxPatch(
    (8, 8), 84, 18, boxstyle="round,pad=0.5", linewidth=0,
    facecolor="#214A6B", alpha=0.6, zorder=1))

constraints = [
    {"x": 20, "label": "COHORT SIZE",     "value": "10-30",      "unit": "students"},
    {"x": 38, "label": "BLOCK LENGTH",    "value": "6-8",        "unit": "weeks"},
    {"x": 56, "label": "TOTAL DOSAGE",    "value": "18-24",      "unit": "hours / student"},
    {"x": 78, "label": "iLEAD TIER 3",    "value": "75 / 87.5 / 80", "unit": "% (Math / ELA / Combined)"},
]
for c in constraints:
    ax.text(c["x"], 21.5, c["label"], ha="center", va="center",
            fontfamily=BODY_FONT, fontsize=10, fontweight="bold", color=GOLD,
            alpha=0.95)
    ax.text(c["x"], 15.5, c["value"], ha="center", va="center",
            fontfamily=HEADING_FONT, fontsize=22, fontweight="bold", color=WHITE)
    ax.text(c["x"], 11, c["unit"], ha="center", va="center",
            fontfamily=BODY_FONT, fontsize=9, color=WHITE, alpha=0.75)

# Bottom-right corner: leave space for logo composite
ax.text(50, 3, "Source: Learning Policy Institute, Stanford NSSA, AIR, A+ Tutoring case studies",
        ha="center", va="center", fontfamily=BODY_FONT, fontsize=8,
        color=WHITE, alpha=0.5)

out_path = Path(__file__).parent / "topic-graphic.png"
fig.savefig(out_path, dpi=100, facecolor=NAVY, edgecolor="none",
            bbox_inches="tight", pad_inches=0)
plt.close(fig)
print(f"Saved {out_path} ({out_path.stat().st_size:,} bytes)")
print(f"  heading_font={HEADING_FONT}")
print(f"  body_font={BODY_FONT}")

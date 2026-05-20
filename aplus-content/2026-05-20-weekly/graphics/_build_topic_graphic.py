#!/usr/bin/env python3
"""Topic-specific data viz for May 20 bundle:
State dyslexia screening implementation timeline.

Deterministic matplotlib build. Output: topic-graphic.png at blog-body-width
landscape (1536x1024, 3:2 aspect).

Applies aplus-graphic-prompts v2.0:
- Blog-body-width landscape (not square)
- Heavy A+ brand colors throughout
- Playfair Display headings + DM Sans body (registered TTFs)
- No date watermark, no "A+ Tutoring blog" subtitle
- Logo placement handled by separate composite script
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
from pathlib import Path

NAVY = "#1A3A52"
ORANGE = "#EF5829"
GOLD = "#F4A261"
WHITE = "#FFFFFF"
OFF_WHITE = "#FAF7F2"
LIGHT_GRAY = "#E8E8E8"
CHARCOAL = "#2E2E2E"
BAND_BG = "#214A6B"

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

HEADING_FONT = _find_font("Playfair Display", "Playfair", "Georgia") or "serif"
BODY_FONT = _find_font("DM Sans", "Helvetica", "Arial") or "sans-serif"

fig = plt.figure(figsize=(15.36, 10.24), dpi=100, facecolor=NAVY)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")
ax.set_facecolor(NAVY)

# Title
ax.text(50, 92, "K-2 DYSLEXIA SCREENING DEADLINES", ha="center", va="center",
        fontfamily=HEADING_FONT, fontsize=32, fontweight="bold", color=WHITE)
ax.text(50, 85, "18+ States Now Require Universal Screening", ha="center", va="center",
        fontfamily=BODY_FONT, fontsize=17, fontweight="normal", color=GOLD)

# Left column: states already in implementation (2025-26)
ax.text(20, 75, "ALREADY IN IMPLEMENTATION", ha="center", va="center",
        fontfamily=BODY_FONT, fontsize=12, fontweight="bold", color=ORANGE)
ax.text(20, 71, "2025-26 school year", ha="center", va="center",
        fontfamily=BODY_FONT, fontsize=10, color=WHITE, alpha=0.7)
states_now = [
    ("California", "SB 114"),
    ("Texas", "HB 3928"),
    ("Florida", "SB 250"),
    ("Michigan", "Public Act"),
    ("Connecticut", "Reading Reform Act"),
    ("Colorado", "READ Act"),
    ("Massachusetts", "DESE rules"),
]
for i, (state, law) in enumerate(states_now):
    y = 64 - i * 5
    ax.scatter([10], [y], s=80, color=ORANGE, zorder=3)
    ax.text(13, y, state, ha="left", va="center",
            fontfamily=HEADING_FONT, fontsize=14, fontweight="bold", color=WHITE)
    ax.text(13, y - 2.2, law, ha="left", va="center",
            fontfamily=BODY_FONT, fontsize=9, color=WHITE, alpha=0.7)

# Center column: states in 2026-27 implementation
ax.text(50, 75, "IMPLEMENTATION DEADLINE", ha="center", va="center",
        fontfamily=BODY_FONT, fontsize=12, fontweight="bold", color=GOLD)
ax.text(50, 71, "Fall 2026 (THIS YEAR)", ha="center", va="center",
        fontfamily=BODY_FONT, fontsize=10, color=WHITE, alpha=0.7)
states_fall = [
    ("Ohio", "SB 21"),
    ("New Jersey", "S2843"),
    ("Pennsylvania", "Act 18"),
    ("Tennessee", "Reading 360"),
    ("Virginia", "VLA Act"),
    ("North Carolina", "Excellent Public Schools"),
    ("Georgia", "HB 538"),
]
for i, (state, law) in enumerate(states_fall):
    y = 64 - i * 5
    ax.scatter([42], [y], s=90, color=GOLD, edgecolors=WHITE, linewidths=1.5, zorder=3)
    ax.text(45, y, state, ha="left", va="center",
            fontfamily=HEADING_FONT, fontsize=14, fontweight="bold", color=WHITE)
    ax.text(45, y - 2.2, law, ha="left", va="center",
            fontfamily=BODY_FONT, fontsize=9, color=WHITE, alpha=0.7)

# Right column: states with later deadlines
ax.text(80, 75, "LATER DEADLINES", ha="center", va="center",
        fontfamily=BODY_FONT, fontsize=12, fontweight="bold", color=WHITE)
ax.text(80, 71, "2027 and beyond", ha="center", va="center",
        fontfamily=BODY_FONT, fontsize=10, color=WHITE, alpha=0.7)
states_later = [
    ("Illinois", "HB 3030"),
    ("Washington", "RCW 28A.300"),
    ("Oregon", "SB 1054"),
    ("Maryland", "Ready to Read"),
    ("New York", "Action Plan"),
    ("Indiana", "HEA 1558"),
    ("Wisconsin", "Act 20"),
]
for i, (state, law) in enumerate(states_later):
    y = 64 - i * 5
    ax.scatter([72], [y], s=70, color=WHITE, edgecolors=NAVY, linewidths=1.5, alpha=0.65, zorder=3)
    ax.text(75, y, state, ha="left", va="center",
            fontfamily=HEADING_FONT, fontsize=14, fontweight="bold", color=WHITE)
    ax.text(75, y - 2.2, law, ha="left", va="center",
            fontfamily=BODY_FONT, fontsize=9, color=WHITE, alpha=0.7)

# Bottom band: the operational question
ax.add_patch(mpatches.FancyBboxPatch(
    (8, 8), 84, 18, boxstyle="round,pad=0.5", linewidth=0,
    facecolor=BAND_BG, alpha=0.6, zorder=1))

ax.text(50, 21.5, "THE QUESTION CHARTER DIRECTORS SHOULD ASK", ha="center", va="center",
        fontfamily=BODY_FONT, fontsize=11, fontweight="bold", color=GOLD)
ax.text(50, 16, "If we screen 200 K-2 students this fall and 30 score below threshold,",
        ha="center", va="center", fontfamily=HEADING_FONT, fontsize=16,
        fontweight="normal", color=WHITE, fontstyle="italic")
ax.text(50, 12, "what is our written intervention plan for those 30 students by Halloween?",
        ha="center", va="center", fontfamily=HEADING_FONT, fontsize=16,
        fontweight="normal", color=WHITE, fontstyle="italic")

# Footer source
ax.text(50, 3, "Source: International Dyslexia Association state law tracker, state department of education pages",
        ha="center", va="center", fontfamily=BODY_FONT, fontsize=8,
        color=WHITE, alpha=0.5)

out_path = Path(__file__).parent / "topic-graphic.png"
fig.savefig(out_path, dpi=100, facecolor=NAVY, edgecolor="none",
            bbox_inches="tight", pad_inches=0)
plt.close(fig)
print(f"Saved {out_path} ({out_path.stat().st_size:,} bytes)")
print(f"  heading_font={HEADING_FONT}")
print(f"  body_font={BODY_FONT}")

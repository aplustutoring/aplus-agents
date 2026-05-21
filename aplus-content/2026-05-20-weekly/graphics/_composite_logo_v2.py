#!/usr/bin/env python3
"""Composite real A+ Tutoring logo onto the v2.3 graphic set for May 20 bundle.

v2.3 (2026-05-20) fixes the visible rectangular halo around carousel logos:
  1. NO erase-rectangle step. The Frame prompts reserve clean space; the
     hard-alpha logo composites onto whatever pixels are underneath
     without painting a sample-color rectangle that might mismatch the
     surrounding textured background.
  2. Hard alpha threshold (alpha < 128 -> 0, alpha >= 128 -> 255). This
     eliminates soft anti-aliased edges that bleed light into navy /
     orange backgrounds and rendered as faint halos.
  3. Preserve logo aspect ratio when resizing (was previously stretched
     square at e.g. 140x140 even though logo source is ~320x230).

Color rule:
  - White-variant logo on orange / navy / dark / saturated backgrounds
  - Two-color logo on white / cream / light backgrounds

Hero, instagram-post, instagram-story (single-photo), facebook are NOT
processed here:
  - hero / facebook are photographic; no logo composite by design
  - instagram-post.png and the single instagram-story.png were retired in v2.2
  - The 3-frame instagram-story-{1,2,3}.png are built and logo-composited
    by scripts/build-instagram-stories.py directly
  - preset-stat-graphic.png already has its logo composited at brand-kit
    build time
"""
from PIL import Image, ImageDraw
from pathlib import Path

LOGO = Path("/Users/romanslavinsky/Desktop/logo.png")
GFX = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-content/2026-05-20-weekly/graphics")

ALPHA_THRESHOLD = 128


def _hardclamp_alpha(rgba_img):
    """Binary alpha: <128 -> 0, >=128 -> 255. Eliminates halo."""
    px = rgba_img.load()
    for y in range(rgba_img.height):
        for x in range(rgba_img.width):
            r, g, b, a = px[x, y]
            if a < ALPHA_THRESHOLD:
                px[x, y] = (r, g, b, 0)
            else:
                px[x, y] = (r, g, b, 255)
    return rgba_img


def chroma_keyed_logo():
    """Return RGBA logo with white pixels chroma-keyed to transparent +
    hard-clamped alpha (no soft edges)."""
    raw = Image.open(LOGO).convert("RGBA")
    px = raw.load()
    for y in range(raw.height):
        for x in range(raw.width):
            r, g, b, a = px[x, y]
            if r >= 240 and g >= 240 and b >= 240:
                px[x, y] = (r, g, b, 0)
    _hardclamp_alpha(raw)
    return raw


def white_variant(rgba_logo):
    """Recolor non-transparent pixels to pure white + hard-clamp alpha."""
    out = rgba_logo.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (255, 255, 255, a)
    _hardclamp_alpha(out)
    return out


def composite(source_name, output_name, logo_anchor, logo_width, logo_rgba):
    """Composite a logo with preserved aspect ratio + hard alpha.

    NO erase-rectangle. The chroma-keyed + hard-alpha logo composites
    cleanly without halo.
    """
    src = GFX / source_name
    out = GFX / output_name
    if not src.exists():
        print(f"  SKIP (missing): {source_name}")
        return
    print(f"=== {source_name} -> {output_name} ===")
    base = Image.open(src).convert("RGBA")
    aspect = logo_rgba.height / logo_rgba.width
    target_h = int(logo_width * aspect)
    logo_resized = logo_rgba.resize((logo_width, target_h), Image.LANCZOS)
    _hardclamp_alpha(logo_resized)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(logo_resized, logo_anchor, logo_resized)
    result = Image.alpha_composite(base, layer)
    result.save(out, "PNG")
    print(f"  wrote {out.name} ({logo_width}x{target_h} logo, aspect-preserved)")


LOGO_2COLOR = chroma_keyed_logo()
LOGO_WHITE = white_variant(LOGO_2COLOR)


# All anchors are top-left corners of where the logo lands.
# Logo widths calibrated per canvas:
#   - 1536x1024 (social card, pull-quote, topic graphic): 150px wide
#   - 1024x1536 (carousel slide):                         140px wide

# Social card (navy bg) -> white variant, bottom-right
composite("social-card.png", "social-card-with-logo.png",
          logo_anchor=(1360, 850), logo_width=150, logo_rgba=LOGO_WHITE)

# Pull-quote s1, s2 (orange bg) -> white variant, bottom-right
for slot in ("s1", "s2"):
    composite(f"pull-quote-{slot}.png", f"pull-quote-{slot}-with-logo.png",
              logo_anchor=(1360, 850), logo_width=150, logo_rgba=LOGO_WHITE)

# Topic graphic (navy bg) -> white variant, bottom-right
composite("topic-graphic.png", "topic-graphic-with-logo.png",
          logo_anchor=(1360, 850), logo_width=150, logo_rgba=LOGO_WHITE)

# Carousel slide 1 (navy bg, hook + swipe) -> white variant, bottom-right
composite("linkedin-carousel-slide-1.png", "linkedin-carousel-slide-1-with-logo.png",
          logo_anchor=(850, 1360), logo_width=140, logo_rgba=LOGO_WHITE)

# Carousel slide 2 (white bg + orange stripe) -> two-color, bottom-right
composite("linkedin-carousel-slide-2.png", "linkedin-carousel-slide-2-with-logo.png",
          logo_anchor=(830, 1360), logo_width=140, logo_rgba=LOGO_2COLOR)

# Carousel slide 3 (orange bg) -> white variant, bottom-right
composite("linkedin-carousel-slide-3.png", "linkedin-carousel-slide-3-with-logo.png",
          logo_anchor=(850, 1360), logo_width=140, logo_rgba=LOGO_WHITE)

# Carousel slide 4 (white bg + orange stripe) -> two-color, bottom-right
composite("linkedin-carousel-slide-4.png", "linkedin-carousel-slide-4-with-logo.png",
          logo_anchor=(830, 1360), logo_width=140, logo_rgba=LOGO_2COLOR)

# Carousel slide 5 (navy bg, CTA, NO swipe indicator) -> white variant, bottom-right
composite("linkedin-carousel-slide-5.png", "linkedin-carousel-slide-5-with-logo.png",
          logo_anchor=(850, 1360), logo_width=140, logo_rgba=LOGO_WHITE)

print("\nDone.")

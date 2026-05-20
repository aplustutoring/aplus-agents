#!/usr/bin/env python3
"""Composite real A+ Tutoring logo onto the v2.0 graphic set for May 19 bundle.

Updates from May 18:
- Only 2 pull-quotes (s1, s2) instead of 3 (per aplus-graphic-prompts v2.0)
- Pull-quotes are now 1536x1024 landscape (not 1024x1024 square)
- Social card and pull-quotes use bottom-right cleanspace zone the AI was
  prompted to leave blank
- Carousel slide 5 has NO swipe indicator
- topic-graphic.png is a separate matplotlib build; logo composited here too

White-variant logo on orange/navy/dark backgrounds.
Two-color logo on white/cream backgrounds.
Hero, instagram-post, instagram-story, facebook are photographs — no logo composite.
preset-stat-graphic.png already has its logo composited at brand-kit build time.
"""
from PIL import Image, ImageDraw
from pathlib import Path

LOGO = Path("/Users/romanslavinsky/Desktop/logo.png")
GFX = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-content/2026-05-20-weekly/graphics")


def chroma_keyed_logo():
    raw = Image.open(LOGO).convert("RGBA")
    corners = [raw.getpixel((0, 0)), raw.getpixel((raw.width - 1, 0)),
               raw.getpixel((0, raw.height - 1)), raw.getpixel((raw.width - 1, raw.height - 1))]
    if max(p[3] for p in corners) == 0:
        return raw
    px = raw.load()
    for y in range(raw.height):
        for x in range(raw.width):
            r, g, b, a = px[x, y]
            if r >= 240 and g >= 240 and b >= 240:
                px[x, y] = (r, g, b, 0)
    return raw


def white_variant(rgba_logo):
    out = rgba_logo.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (255, 255, 255, a)
    return out


def composite(source_name, output_name, erase_box, logo_anchor, logo_width, sample_xy, logo_rgba):
    src = GFX / source_name
    out = GFX / output_name
    if not src.exists():
        print(f"  SKIP (missing): {source_name}")
        return
    print(f"=== {source_name} -> {output_name} ===")
    base = Image.open(src).convert("RGBA")
    bg = base.getpixel(sample_xy)
    ImageDraw.Draw(base).rectangle(erase_box, fill=bg)
    logo_resized = logo_rgba.resize((logo_width, logo_width), Image.LANCZOS)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(logo_resized, logo_anchor, logo_resized)
    result = Image.alpha_composite(base, layer)
    result.save(out, "PNG")
    print(f"  wrote {out.name}")


LOGO_2COLOR = chroma_keyed_logo()
LOGO_WHITE = white_variant(LOGO_2COLOR)


# Social card: 1536x1024 navy bg, bottom-right cleanspace → white variant logo
composite("social-card.png", "social-card-with-logo.png",
          erase_box=(1330, 820, 1520, 1010), logo_anchor=(1360, 850), logo_width=150,
          sample_xy=(50, 50), logo_rgba=LOGO_WHITE)

# Pull-quote s1, s2: 1536x1024 orange bg → white variant logo bottom-right
for slot in ("s1", "s2"):
    composite(f"pull-quote-{slot}.png", f"pull-quote-{slot}-with-logo.png",
              erase_box=(1330, 820, 1520, 1010), logo_anchor=(1360, 850), logo_width=150,
              sample_xy=(20, 20), logo_rgba=LOGO_WHITE)

# Topic graphic: 1536x1024 navy bg → white variant logo bottom-right (matplotlib left clearspace)
composite("topic-graphic.png", "topic-graphic-with-logo.png",
          erase_box=(1330, 820, 1520, 1010), logo_anchor=(1360, 850), logo_width=150,
          sample_xy=(50, 50), logo_rgba=LOGO_WHITE)

# Carousel slide 1: 1024x1536 navy bg, hook + swipe indicator → white variant logo bottom-right
composite("linkedin-carousel-slide-1.png", "linkedin-carousel-slide-1-with-logo.png",
          erase_box=(820, 1330, 1010, 1510), logo_anchor=(850, 1360), logo_width=140,
          sample_xy=(500, 1500), logo_rgba=LOGO_WHITE)

# Carousel slide 2: white bg, orange stripe → two-color logo bottom-right
composite("linkedin-carousel-slide-2.png", "linkedin-carousel-slide-2-with-logo.png",
          erase_box=(800, 1330, 1010, 1510), logo_anchor=(830, 1360), logo_width=140,
          sample_xy=(500, 500), logo_rgba=LOGO_2COLOR)

# Carousel slide 3: orange bg → white variant logo bottom-right
composite("linkedin-carousel-slide-3.png", "linkedin-carousel-slide-3-with-logo.png",
          erase_box=(820, 1330, 1010, 1510), logo_anchor=(850, 1360), logo_width=140,
          sample_xy=(500, 500), logo_rgba=LOGO_WHITE)

# Carousel slide 4: white bg, orange stripe → two-color logo bottom-right
composite("linkedin-carousel-slide-4.png", "linkedin-carousel-slide-4-with-logo.png",
          erase_box=(800, 1330, 1010, 1510), logo_anchor=(830, 1360), logo_width=140,
          sample_xy=(500, 500), logo_rgba=LOGO_2COLOR)

# Carousel slide 5: navy bg, CTA, NO swipe indicator → white variant logo bottom-right
composite("linkedin-carousel-slide-5.png", "linkedin-carousel-slide-5-with-logo.png",
          erase_box=(820, 1330, 1010, 1510), logo_anchor=(850, 1360), logo_width=140,
          sample_xy=(500, 200), logo_rgba=LOGO_WHITE)

print("\nDone.")

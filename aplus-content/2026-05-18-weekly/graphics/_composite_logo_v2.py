#!/usr/bin/env python3
"""Composite real A+ Tutoring logo onto the full v2 14-graphic set.

White-variant logo on orange/navy/dark backgrounds.
Two-color logo on white/cream backgrounds.
Hero, instagram-post, instagram-story, facebook are photographs — no logo composite.
"""
from PIL import Image, ImageDraw
from pathlib import Path
import shutil

LOGO = Path("/Users/romanslavinsky/Desktop/logo.png")
GFX = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-content/2026-05-18-weekly/graphics")


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
    print(f"  bg sample {sample_xy}: RGBA{bg}")
    ImageDraw.Draw(base).rectangle(erase_box, fill=bg)
    logo_resized = logo_rgba.resize((logo_width, logo_width), Image.LANCZOS)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(logo_resized, logo_anchor, logo_resized)
    result = Image.alpha_composite(base, layer)
    result.save(out, "PNG")
    print(f"  wrote {out.name}")


LOGO_2COLOR = chroma_keyed_logo()
LOGO_WHITE = white_variant(LOGO_2COLOR)


# Social card (navy bg) — white variant logo bottom-right
composite("social-card.png", "social-card-with-logo.png",
          erase_box=(1320, 800, 1520, 1010), logo_anchor=(1360, 830), logo_width=160,
          sample_xy=(50, 50), logo_rgba=LOGO_WHITE)

# Pull-quote s1, s2, s3 (orange bg) — white variant
for slot in ("s1", "s2", "s3"):
    composite(f"pull-quote-{slot}.png", f"pull-quote-{slot}-with-logo.png",
              erase_box=(820, 820, 1020, 1020), logo_anchor=(890, 890), logo_width=100,
              sample_xy=(20, 20), logo_rgba=LOGO_WHITE)

# Carousel slide 1 (navy bg) — white variant top-left
composite("linkedin-carousel-slide-1.png", "linkedin-carousel-slide-1-with-logo.png",
          erase_box=(0, 10, 320, 240), logo_anchor=(30, 40), logo_width=110,
          sample_xy=(500, 1500), logo_rgba=LOGO_WHITE)

# Carousel slides 2-4 (white bg with orange stripe) — two-color logo bottom-right
for slot in (2, 3, 4):
    composite(f"linkedin-carousel-slide-{slot}.png", f"linkedin-carousel-slide-{slot}-with-logo.png",
              erase_box=(800, 1330, 1010, 1510), logo_anchor=(840, 1370), logo_width=130,
              sample_xy=(500, 500), logo_rgba=LOGO_2COLOR)

# Carousel slide 5 (navy bg) — white variant bottom-left
composite("linkedin-carousel-slide-5.png", "linkedin-carousel-slide-5-with-logo.png",
          erase_box=(10, 1300, 270, 1510), logo_anchor=(40, 1340), logo_width=130,
          sample_xy=(500, 200), logo_rgba=LOGO_WHITE)

# Creative graphic (navy bg) — white variant bottom-right
composite("creative-graphic.png", "creative-graphic-with-logo.png",
          erase_box=(820, 820, 1020, 1020), logo_anchor=(890, 890), logo_width=100,
          sample_xy=(50, 50), logo_rgba=LOGO_WHITE)

print("\nDone.")

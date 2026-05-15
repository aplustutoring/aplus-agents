#!/usr/bin/env python3
"""Composite the real A+ Tutoring logo onto the 3 text graphics with proper alpha.

Uses Image.alpha_composite() so the logo's semi-transparent edges blend with the
actual underlying bg color (navy or orange), not a default white. Chroma-keys
the source logo (which is RGBA but has an opaque white background, not real
alpha=0) before compositing.

Two logo variants:
- Two-color (orange wordmark + navy book): used on the navy social card and
  navy carousel slide, where the orange wordmark pops nicely against navy.
- White-recolored (every non-bg pixel replaced with white, alpha preserved):
  used on the orange pull-quote, where the orange wordmark would otherwise
  blend into the background.
"""
from PIL import Image, ImageDraw
from pathlib import Path

LOGO = Path("/Users/romanslavinsky/Desktop/logo.png")
LOGO_WHITE_EXPORT = Path("/Users/romanslavinsky/Desktop/logo-white.png")
GFX = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-content/2026-05-15-weekly/graphics")


def chroma_keyed_logo():
    """Return an RGBA logo with white background converted to alpha=0."""
    raw = Image.open(LOGO).convert("RGBA")
    print(f"  Logo source: mode={raw.mode}, size={raw.size}")
    corners = [raw.getpixel((0, 0)), raw.getpixel((raw.width - 1, 0)),
               raw.getpixel((0, raw.height - 1)),
               raw.getpixel((raw.width - 1, raw.height - 1))]
    print(f"  Logo corner alphas: {[p[3] for p in corners]}")
    if max(p[3] for p in corners) == 0:
        print("  → Logo already has true RGBA transparency. Using as-is.")
        return raw
    print("  → Logo has opaque corners; chroma-keying near-whites to alpha=0.")
    px = raw.load()
    threshold = 240
    for y in range(raw.height):
        for x in range(raw.width):
            r, g, b, a = px[x, y]
            if r >= threshold and g >= threshold and b >= threshold:
                px[x, y] = (r, g, b, 0)
    return raw


def white_variant(rgba_logo):
    """Take a chroma-keyed RGBA logo and return a variant where every
    non-transparent pixel has RGB replaced with white. Alpha values are
    preserved so anti-aliased edges stay smooth."""
    out = rgba_logo.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (255, 255, 255, a)
    return out


def composite(source_name, output_name, erase_box, logo_anchor, logo_width,
              sample_xy, logo_rgba):
    src = GFX / source_name
    out = GFX / output_name
    print(f"\n=== {source_name} → {output_name} ===")

    base = Image.open(src).convert("RGBA")
    bg = base.getpixel(sample_xy)
    print(f"  Sampled bg at {sample_xy}: RGBA{bg}")
    ImageDraw.Draw(base).rectangle(erase_box, fill=bg)

    logo_resized = logo_rgba.resize((logo_width, logo_width), Image.LANCZOS)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(logo_resized, logo_anchor, logo_resized)
    result = Image.alpha_composite(base, layer)
    result.save(out, "PNG")

    edge = result.getpixel((logo_anchor[0] - 2, logo_anchor[1] + logo_width // 2))
    inside = result.getpixel((logo_anchor[0] + 2, logo_anchor[1] + 2))
    print(f"  Edge pixel: RGBA{edge}   Inside-logo-corner: RGBA{inside}")
    print(f"  Wrote {out}")


print("Loading logo (two-color)...")
LOGO_2COLOR = chroma_keyed_logo()

print("\nGenerating white variant...")
LOGO_WHITE = white_variant(LOGO_2COLOR)
LOGO_WHITE.save(LOGO_WHITE_EXPORT, "PNG")
print(f"  Exported reusable white logo: {LOGO_WHITE_EXPORT}")

# Social card — orange-on-navy wordmark pops on navy. Use the two-color logo.
composite(
    "social-card.png",
    "social-card-with-logo.png",
    erase_box=(1320, 800, 1520, 1010),
    logo_anchor=(1360, 830),
    logo_width=160,
    sample_xy=(50, 50),
    logo_rgba=LOGO_2COLOR,
)

# Pull-quote — orange-on-orange would blend. Use the white variant, slightly larger.
composite(
    "pull-quote.png",
    "pull-quote-with-logo.png",
    erase_box=(820, 820, 1020, 1020),
    logo_anchor=(869, 869),
    logo_width=130,
    sample_xy=(20, 20),
    logo_rgba=LOGO_WHITE,
)

# Carousel slide — navy background, two-color logo.
composite(
    "carousel-slide-1.png",
    "carousel-slide-1-with-logo.png",
    erase_box=(0, 10, 320, 240),
    logo_anchor=(30, 40),
    logo_width=110,
    sample_xy=(500, 1500),
    logo_rgba=LOGO_2COLOR,
)

print("\nDone.")

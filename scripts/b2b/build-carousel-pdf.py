#!/usr/bin/env python3
"""Combine the logo-composited LinkedIn carousel slides into a single PDF.

LinkedIn document/carousel posts take ONE multi-page PDF (not loose images), so
this stitches graphics/linkedin-carousel-slide-{1..5}-with-logo.png into
graphics/linkedin-carousel.pdf, pages in order. Run AFTER composite-logo.py.

Usage: python3 scripts/b2b/build-carousel-pdf.py --bundle <bundle-dir>
"""
import sys
import argparse
from pathlib import Path


def build_pdf(bundle: str) -> int:
    g = Path(bundle) / "graphics"
    slides = [g / f"linkedin-carousel-slide-{i}-with-logo.png" for i in range(1, 6)]
    present = [s for s in slides if s.exists()]
    if not present:
        print(f"build-carousel-pdf: no carousel slides found in {g}", file=sys.stderr)
        return 0  # best-effort: nothing to do, don't fail the build
    try:
        from PIL import Image
    except Exception as e:
        print(f"build-carousel-pdf: PIL unavailable: {e}", file=sys.stderr)
        return 0
    imgs = [Image.open(s).convert("RGB") for s in present]
    out = g / "linkedin-carousel.pdf"
    imgs[0].save(out, "PDF", save_all=True, append_images=imgs[1:], resolution=150.0)
    print(f"build-carousel-pdf: wrote {out.name} ({len(present)} pages)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Stitch LinkedIn carousel slides into one PDF")
    ap.add_argument("--bundle", required=True)
    args = ap.parse_args()
    return build_pdf(args.bundle)


if __name__ == "__main__":
    sys.exit(main())

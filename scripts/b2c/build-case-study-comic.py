#!/usr/bin/env python3
"""
5-panel comic-storyboard builder for an A+ case study.

Each spotlight gets its OWN comic, generated from that case study's metadata.
The student is a FICTIONAL superhero archetype (never the real child), A+ is the
sidekick, with a fixed 5-beat arc: struggle -> sidekick -> breakthrough -> win
(+ a CTA footer).

GUARDRAILS (non-negotiable):
  - The hero is a generic archetype typed only by subject (power) and grade
    (age band). NO real name, NO likeness, NO photo, NO real-kid pseudonym.
  - Public captions surface ONLY non-sensitive axes: subject, grade band, arc.
    NEVER IEP / disability / ELL/EL / low-income / foster in any caption.
  - All caption + stat text is overlaid with PIL. The image model NEVER
    renders text (models garble it).
  - Image gen = DIRECT Gemini API (same pattern as build-case-study-hero-card),
    never Higgsfield/Canva (connected apps, won't run headless in CI).

Character consistency: generate an anchor hero, then feed it back as a reference
image for every beat so it's the same hero throughout (confirmed working with
gemini-3.1-flash-image-preview).

Usage:
    python3 scripts/b2c/build-case-study-comic.py --bundle aplus-content/{bundle}/
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]  # repo root (scripts/b2c/<file>)
load_dotenv(dotenv_path=REPO / ".env")
GEMINI = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-3.1-flash-image-preview"
GEM_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI}"

# --- brand ---
NAVY = (26, 58, 82)      # #1A3A52
ORANGE = (239, 88, 41)   # #EF5829
IVORY = (248, 244, 237)  # #F8F4ED
FONTS = REPO / "skills" / "aplus-b2b-brand-kit" / "fonts"

NO_TEXT = (" Absolutely NO text, words, letters, numbers, captions, speech "
           "bubbles, logos, or watermarks anywhere in the image — text is added "
           "later by a separate compositor.")

# Subject -> hero power / emblem / struggle prop. Drives the art, not a label.
SUBJECT_POWER = {
    "math":    ("a glowing orange 'M' chest emblem",
                "glowing mathematical equations, numbers and geometry swirling around him",
                "an open math workbook full of problems"),
    "reading": ("a glowing orange open-book chest emblem",
                "glowing words, letters and luminous floating open books swirling around him",
                "an open book and a reading passage"),
    "english": ("a glowing orange open-book chest emblem",
                "glowing words, letters and luminous floating books swirling around him",
                "an open reading passage"),
    "writing": ("a glowing orange quill-pen chest emblem",
                "glowing sentences and a luminous pen trailing light around him",
                "a writing notebook"),
    "science": ("a glowing orange atom chest emblem",
                "glowing molecules, beakers and constellations swirling around him",
                "a science worksheet"),
}
DEFAULT_POWER = ("a glowing orange star chest emblem",
                 "glowing knowledge energy swirling around him",
                 "an open workbook")


def grade_age_band(grade):
    m = re.search(r"\d+", str(grade))
    g = int(m.group()) if m else 9
    if g <= 2:  return "about 7 years old"
    if g <= 5:  return "about 9 years old"
    if g <= 8:  return "about 12 years old"
    return "about 15 years old"


def parse_meta_field(text, field):
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


def font(sz, bold=True):
    p = FONTS / ("PlayfairDisplay-Bold.ttf" if bold else "DMSans-Regular.ttf")
    return ImageFont.truetype(str(p), sz)


def gemini(prompt, out_path, ref=None, aspect="3:4"):
    parts = []
    if ref is not None:
        parts.append({"inlineData": {"mimeType": "image/png",
                      "data": base64.b64encode(Path(ref).read_bytes()).decode()}})
    parts.append({"text": prompt})
    body = json.dumps({"contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
        "imageConfig": {"aspectRatio": aspect}, "temperature": 0.6}}).encode()
    req = urllib.request.Request(GEM_URL, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "aplus/1.0"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=240).read())
    except Exception as e:
        return False, str(e)[:300]
    for p in r.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in p:
            Path(out_path).write_bytes(base64.b64decode(p["inlineData"]["data"]))
            return True, Path(out_path).stat().st_size
    return False, "no inlineData"


# ---------------------------------------------------------------------------
# LAYER 1 — art
# ---------------------------------------------------------------------------
def hero_base(subject, grade, gender):
    emblem, _, _ = SUBJECT_POWER.get(subject.lower(), DEFAULT_POWER)
    age = grade_age_band(grade)
    kid = "girl" if gender.lower().startswith("g") else "boy"
    return (
        f"A vibrant cel-shaded comic-book illustration, bold ink outlines and "
        f"halftone shading, bright saturated colors. A FICTIONAL young superhero "
        f"archetype (not a real person), a {kid} {age}, wearing a navy-blue "
        f"(#1A3A52) and orange (#EF5829) superhero costume with {emblem} and an "
        f"orange cape. Friendly, heroic, all-ages tone."
    )


LOCK = ("Use the EXACT SAME character shown in the reference image: identical "
        "face, hair, age, body, costume design, colors and chest emblem. Same "
        "cel-shaded comic art style. Only change the pose and the scene. ")


def beat_prompts(subject, grade, gender):
    _, power, prop = SUBJECT_POWER.get(subject.lower(), DEFAULT_POWER)
    base = hero_base(subject, grade, gender)
    return {
        # anchor: clean establishing portrait, used only as the reference
        "anchor": base + " Standing in a confident heroic portrait pose, plain "
                  "soft studio background." + NO_TEXT,
        "struggle": LOCK + f"New scene: the hero sits slumped at a wooden school "
                    f"desk, looking defeated and frustrated, {prop} in front of "
                    f"him, dim muted classroom background." + NO_TEXT,
        "sidekick": LOCK + "New scene: a friendly glowing orange robot sidekick "
                    "(the A+ helper) arrives beside the hero, offering a "
                    "reassuring hand; the hero looks up with the first spark of "
                    "hope; warm encouraging background." + NO_TEXT,
        "breakthrough": LOCK + f"New scene: the hero stands triumphant, fists "
                    f"raised, {power}, bright dynamic radiant background, the "
                    f"moment it clicks." + NO_TEXT,
        "win": LOCK + "New scene: the hero stands heroically with cape flowing "
               "and a confident smile, hands on hips, a LARGE BLANK orange "
               "circular badge centered on the chest (leave it empty), bright "
               "triumphant city-skyline background." + NO_TEXT,
        "cta": LOCK + "New scene: the hero stands warm and welcoming, extending "
               "an open hand toward the viewer as a friendly invitation, gentle "
               "optimistic sunrise background." + NO_TEXT,
    }


def generate_panels(out_dir, subject, grade, gender):
    prompts = beat_prompts(subject, grade, gender)
    out_dir.mkdir(parents=True, exist_ok=True)
    # anchor first (no ref), then every beat references the anchor for a
    # consistent hero. Existing panels are reused (cheap re-runs / resumable).
    anchor_path = out_dir / "comic-anchor.png"
    if anchor_path.exists():
        print(f"  anchor: reuse {anchor_path.name}")
    else:
        ok, info = gemini(prompts["anchor"], anchor_path)
        print(f"  anchor: {ok} {info}")
        if not ok:
            raise RuntimeError(f"anchor generation failed: {info}")
    paths = {}
    for beat in BEATS:
        p = out_dir / f"comic-{beat}.png"
        if p.exists():
            print(f"  {beat}: reuse {p.name}")
        else:
            ok, info = gemini(prompts[beat], p, ref=anchor_path)
            print(f"  {beat}: {ok} {info}")
            if not ok:
                raise RuntimeError(f"{beat} generation failed: {info}")
        paths[beat] = p
    return paths


# ---------------------------------------------------------------------------
# LAYER 2 — text + composite (PIL)
# ---------------------------------------------------------------------------
# Five beats, each shipped as its OWN standalone graphic (not a storyboard).
BEATS = ["struggle", "sidekick", "breakthrough", "win", "cta"]
BANNER = {"struggle": NAVY, "sidekick": NAVY, "breakthrough": ORANGE,
          "win": ORANGE, "cta": ORANGE}


def captions(subject):
    subj = subject.capitalize() if subject else "Math"
    return {
        "struggle": f"{subj} used to feel impossible.",
        "sidekick": "Then came someone in their corner.",
        "breakthrough": "One day, it clicked.",
        "win": "Now they’re the hero of their own story.",
        "cta": "Every kid has a breakthrough in them. Book a consultation.",
    }


def _wrap(d, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def banner(im, text, color):
    """Overlay a caption band across the top of a panel."""
    im = im.copy()
    d = ImageDraw.Draw(im, "RGBA")
    bh = int(im.height * 0.18)
    d.rectangle([0, 0, im.width, bh], fill=color + (235,))
    fnt = font(max(20, int(im.width / 16)))
    lines = _wrap(d, text, fnt, im.width - int(im.width * 0.08))
    lh = d.textbbox((0, 0), "Ay", font=fnt)[3] + 8
    y = (bh - lh * len(lines)) // 2
    for ln in lines:
        tw = d.textlength(ln, font=fnt)
        d.text(((im.width - tw) // 2, y), ln, font=fnt, fill=IVORY)
        y += lh
    return im


def stat_badge(im, stat):
    """Draw a clean stat badge near the chest of the win panel (text, not gen).
    Approximate chest position; tune visually if needed."""
    if not stat:
        return im
    im = im.copy()
    d = ImageDraw.Draw(im, "RGBA")
    r = int(im.width * 0.12)
    cx, cy = int(im.width * 0.5), int(im.height * 0.46)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ORANGE + (255,),
              outline=IVORY, width=max(3, r // 12))
    fnt = font(max(18, int(r / max(2, len(stat) * 0.42))))
    tw = d.textlength(stat, font=fnt)
    th = d.textbbox((0, 0), stat, font=fnt)[3]
    d.text((cx - tw / 2, cy - th / 2), stat, font=fnt, fill=IVORY)
    return im


def paste_logo(canvas):
    logo = REPO / "scripts" / "shared" / "assets" / "logo.png"
    for cand in [logo, REPO / "assets" / "logo.png"]:
        if cand.exists():
            lg = Image.open(cand).convert("RGBA")
            lw = int(canvas.width * 0.11)
            lh = int(lw * lg.height / lg.width)
            lg = lg.resize((lw, lh), Image.LANCZOS)
            canvas.paste(lg, (canvas.width - lw - 30, canvas.height - lh - 24), lg)
            return canvas
    print("  (logo not found; skipping logo composite)", file=sys.stderr)
    return canvas


def build_individual_graphics(panel_paths, subject, stat, out_dir):
    """Each beat as its OWN standalone, shareable graphic (not a storyboard):
    captioned panel centered on an ivory IG-feed canvas with the A+ logo. The
    win beat also gets the result-stat badge. Returns the list of output paths."""
    caps = captions(subject)
    IW, IH = 1080, 1350  # Instagram feed portrait (4:5)
    PAD = 48
    outputs = []
    for i, beat in enumerate(BEATS, 1):
        im = Image.open(panel_paths[beat]).convert("RGB")
        if beat == "win":
            im = stat_badge(im, stat)
        im = banner(im, caps[beat], BANNER[beat])
        canvas = Image.new("RGB", (IW, IH), IVORY)
        scale = min((IW - PAD * 2) / im.width, (IH - PAD * 2) / im.height)
        p = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        canvas.paste(p, ((IW - p.width) // 2, (IH - p.height) // 2))
        paste_logo(canvas)
        outp = out_dir / f"comic-{i}-{beat}.png"
        canvas.save(outp)
        outputs.append(outp)
        print(f"  graphic {i}/{len(BEATS)} ({beat}): {outp.name} {canvas.size}")
    return outputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--panels-dir", default=None,
                    help="Reuse already-generated panels here (skip image gen)")
    args = ap.parse_args()

    bundle = Path(args.bundle).resolve()
    meta = bundle / "metadata.md"
    if not meta.exists():
        print(f"ERROR: metadata.md not found in {bundle}", file=sys.stderr)
        return 1
    text = meta.read_text()
    subject = parse_meta_field(text, "subject") or "math"
    grade = parse_meta_field(text, "grade") or "9"
    gender = parse_meta_field(text, "student_gender") or "boy"
    # Non-sensitive result stat only (e.g. "+75 pts", "34th %ile"). Never a
    # protected classification.
    stat = parse_meta_field(text, "comic_stat") or parse_meta_field(text, "result_stat")

    out = bundle / "graphics"
    print(f"=== Comic: {bundle.name} | subject={subject} grade={grade} gender={gender} stat={stat!r} ===")

    if args.panels_dir:
        pd = Path(args.panels_dir)
        panel_paths = {b: pd / f"comic-{b}.png" for b in BEATS}
    else:
        if not GEMINI:
            print("ERROR: GEMINI_API_KEY not set.", file=sys.stderr)
            return 1
        panel_paths = generate_panels(out, subject, grade, gender)

    build_individual_graphics(panel_paths, subject, stat, out)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

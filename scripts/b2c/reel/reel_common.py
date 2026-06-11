#!/usr/bin/env python3
"""
reel_common.py — shared helpers for the A+ Spotlight Reel skill.

Bundle-aware. A reel lives entirely under:  {bundle}/reel/
  script.json                 the authored storyboard script (see make_script.py)
  stills/<key>.png            generated scene stills (+ anchor.png)
  work/                       intermediates (vo, clips, segments, caption frames)
  spotlight-reel.mp4          final output

Direct-API only (Gemini + OpenAI keys from .env). Mirrors the repo convention
in build-case-study-comic.py. The Spotlight Reel is INDEPENDENT of the comic:
both read the same upstream metadata; neither reads the other.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[3]
load_dotenv(REPO / ".env")

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

# resolve via PATH (CI: /usr/bin; mac Homebrew) with a Homebrew fallback
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

# ── canvas / encode ──────────────────────────────────────────────────────────
W, H, FPS = 720, 1280, 30
CRF, PRESET = 18, "medium"

# ── brand ────────────────────────────────────────────────────────────────────
NAVY = "#1A3A52"
ORANGE = "#EF5829"
IVORY = "#F8F4ED"
FONTS = REPO / "skills" / "aplus-b2b-brand-kit" / "fonts"
DM_SANS = FONTS / "DMSans-Regular.ttf"
PLAYFAIR = FONTS / "PlayfairDisplay-Bold.ttf"

# beat order (the 4 animated beats; endcard handled separately)
BEATS = ["struggle", "sidekick", "breakthrough", "win"]


# ── bundle paths ─────────────────────────────────────────────────────────────
def reel_dir(bundle):    return Path(bundle) / "reel"
def script_path(bundle): return reel_dir(bundle) / "script.json"
def stills_dir(bundle):  return reel_dir(bundle) / "stills"
def work_dir(bundle):    return reel_dir(bundle) / "work"
def output_path(bundle): return reel_dir(bundle) / "spotlight-reel.mp4"


def load_script(bundle):
    p = script_path(bundle)
    if not p.exists():
        raise SystemExit(f"missing {p} — run make_script.py --bundle {bundle} first")
    return json.loads(p.read_text())


# ── metadata parsing (same shape as build-case-study-comic.py) ───────────────
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


def read_metadata(bundle):
    meta = Path(bundle) / "metadata.md"
    if not meta.exists():
        raise SystemExit(f"metadata.md not found in {bundle}")
    t = meta.read_text()
    return {
        "subject": parse_meta_field(t, "subject") or "math",
        "grade": parse_meta_field(t, "grade") or "9",
        "gender": parse_meta_field(t, "student_gender") or "boy",
        "stat": parse_meta_field(t, "comic_stat") or parse_meta_field(t, "result_stat"),
    }


# ── hero archetype (fictional; never the real child) ─────────────────────────
SUBJECT_POWER = {
    "math":    ("a large bold orange letter 'M' chest emblem",
                "glowing orange math symbols, geometric shapes and golden sparks swirling around him"),
    "reading": ("a glowing orange open-book chest emblem",
                "glowing open books and streams of warm golden light swirling around him"),
    "english": ("a glowing orange open-book chest emblem",
                "glowing open books and streams of warm golden light swirling around him"),
    "writing": ("a glowing orange quill-pen chest emblem",
                "a luminous pen trailing ribbons of golden light around him"),
    "science": ("a glowing orange atom chest emblem",
                "glowing molecules, beakers and constellations of light swirling around him"),
}
DEFAULT_POWER = ("a glowing orange star chest emblem",
                 "glowing golden energy and sparks of light swirling around him")


def grade_age_band(grade):
    m = re.search(r"\d+", str(grade))
    g = int(m.group()) if m else 9
    if g <= 2:  return "about 7 years old"
    if g <= 5:  return "about 9 years old"
    if g <= 8:  return "about 12 years old"
    return "about 15 years old"


def hero_power(subject):
    return SUBJECT_POWER.get(str(subject).lower(), DEFAULT_POWER)


def hero_description(subject, grade, gender):
    emblem, _ = hero_power(subject)
    age = grade_age_band(grade)
    kid = "girl" if str(gender).lower().startswith("g") else "boy"
    return (
        f"a FICTIONAL young superhero archetype (not a real person), a {kid} "
        f"{age}, athletic, with a navy-blue (#1A3A52) and orange (#EF5829) "
        f"superhero costume, {emblem}, orange gauntlets and orange boots. "
        f"Friendly, heroic, all-ages comic-book tone."
    )


# ── ffmpeg helpers ───────────────────────────────────────────────────────────
def run(cmd):
    subprocess.run(cmd, check=True)


def dur(path):
    out = subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)])
    return float(out.strip())


# ── logo (chroma-key white bg -> transparent; same method as the comic) ──────
def keyed_logo():
    for cand in [REPO / "skills" / "aplus-b2c-brand-kit" / "logo.png",
                 REPO / "assets" / "logo.png"]:
        if cand.exists():
            lg = Image.open(cand).convert("RGBA")
            px = lg.load()
            for y in range(lg.height):
                for x in range(lg.width):
                    r, g, b, a = px[x, y]
                    if (r >= 240 and g >= 240 and b >= 240) or a < 128:
                        px[x, y] = (r, g, b, 0)
                    else:
                        px[x, y] = (r, g, b, 255)
            bbox = lg.getchannel("A").getbbox()
            return lg.crop(bbox) if bbox else lg
    return None


# ── watermark badge (top-left A+ chip) ───────────────────────────────────────
def build_watermark(out, logo_w=150, pad=20, radius=26, alpha=205):
    logo = keyed_logo()
    if logo is None:
        raise SystemExit("logo.png not found for watermark")
    ratio = logo_w / logo.width
    logo = logo.resize((logo_w, round(logo.height * ratio)), Image.LANCZOS)
    cw, ch = logo.width + 2 * pad, logo.height + 2 * pad
    chip = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(chip).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=radius,
                                           fill=(255, 255, 255, alpha))
    chip.alpha_composite(logo, (pad, pad))
    chip.save(out)
    return out


# ── end card still ───────────────────────────────────────────────────────────
def build_endcard(out, headline1, headline2, cta, note=None, url=None):
    img = Image.new("RGB", (W, H), IVORY)
    d = ImageDraw.Draw(img)
    logo = keyed_logo()
    if logo:
        lw = 300
        logo = logo.resize((lw, round(logo.height * lw / logo.width)), Image.LANCZOS)
        img.paste(logo, ((W - logo.width) // 2, 280), logo)
    hf = ImageFont.truetype(str(PLAYFAIR), 58)
    for i, line in enumerate((headline1, headline2)):
        d.text((W / 2, 700 + i * (58 + 18)), line, font=hf, fill=NAVY, anchor="ma")
    cf = ImageFont.truetype(str(DM_SANS), 38)
    tb = d.textbbox((0, 0), cta, font=cf)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    bw, bh = tw + 112, th + 60
    bx, by = (W - bw) / 2, 1010
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh / 2, fill="#E07A3F")
    d.text((W / 2, by + bh / 2), cta, font=cf, fill="#FFFFFF", anchor="mm")
    # gentle secondary invitation under the primary CTA: more stories + link
    y = by + bh + 34
    if note:
        d.text((W / 2, y), note, font=ImageFont.truetype(str(DM_SANS), 28),
               fill=NAVY, anchor="ma")
        y += 42
    if url:
        d.text((W / 2, y), url, font=ImageFont.truetype(str(DM_SANS), 26),
               fill="#E07A3F", anchor="ma")   # orange reads as a link
    img.save(out)
    return out


# ── karaoke caption frames (white -> A+ orange on the active word) ───────────
CAP_SIZE = 52
CAP_W_FRAC = 0.86
CAP_BASELINE_FRAC = 0.82
CAP_LINE_GAP = 14
COL_IDLE = (255, 255, 255, 255)
COL_ACTIVE = (239, 88, 41, 255)     # A+ orange
COL_STROKE = (26, 58, 82, 255)      # A+ navy outline
STROKE_W = 7


def _layout(words, font, draw):
    maxw = int(W * CAP_W_FRAC)
    space = draw.textlength(" ", font=font)
    lines, cur, curw = [], [], 0.0
    for w in words:
        ww = draw.textlength(w["word"], font=font)
        if cur and curw + space + ww > maxw:
            lines.append((cur, curw)); cur, curw = [], 0.0
        if cur:
            curw += space
        cur.append((w, ww)); curw += ww
    if cur:
        lines.append((cur, curw))
    asc, desc = font.getmetrics()
    line_h = asc + desc
    total_h = len(lines) * line_h + (len(lines) - 1) * CAP_LINE_GAP
    y = int(H * CAP_BASELINE_FRAC) - total_h
    placed = []
    for ln, lw in lines:
        x = (W - lw) / 2
        for w, ww in ln:
            placed.append((x, y, w["word"]))
            x += ww + space
        y += line_h + CAP_LINE_GAP
    return placed


def render_caption_states(words, outdir, lead):
    """One full-frame transparent PNG per word-state. Returns [(png, start, end)]
    in clip-time (already offset by `lead`)."""
    outdir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(DM_SANS), CAP_SIZE)
    probe = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    placed = _layout(words, font, probe)
    states, n = [], len(words)
    for i in range(n):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for j in range(i + 1):
            x, y, text = placed[j]
            col = COL_ACTIVE if j == i else COL_IDLE
            d.text((x, y), text, font=font, fill=col,
                   stroke_width=STROKE_W, stroke_fill=COL_STROKE)
        p = outdir / f"state_{i:02d}.png"
        img.save(p)
        start = lead + words[i]["start"]
        end = lead + (words[i + 1]["start"] if i + 1 < n else words[i]["end"] + 1.5)
        states.append((str(p), round(start, 3), round(end, 3)))
    return states

#!/usr/bin/env python3
"""
textstory_common.py — shared helpers for the animated text-message spotlight.

Bundle-aware. A textstory lives entirely under:  {bundle}/textstory/
  scenes.json                 the generated scene script (see make_scenes.py)
  work/                       intermediates (rendered html, mix.wav, video_only)
  textstory.mp4               final 1080x1920 ~30s output

Pure programmatic rendering (headless Chromium + ffmpeg) — NO image/video
generation APIs anywhere in this format. Mirrors the repo conventions in
scripts/b2c/reel/reel_common.py. The textstory is INDEPENDENT of the comic
and the reel: all three read the same upstream metadata; none reads another.

GUARDRAILS (non-negotiable, enforced in make_scenes.py validation):
  - Dialogue is INVENTED and archetypal, written fresh from the arc beats.
    NEVER verbatim quotes from parent call transcripts (that would fabricate
    a record of a real conversation).
  - No real names, school names, or identifying details. Generic parent
    contacts only; the student is only ever "he"/"she".
  - End-card disclosure "Based on real A+ family outcomes" is baked into the
    template — not generated, so it can never be omitted.
  - Chat UI is generic messenger-styled, not an iMessage clone; SFX are our
    own files in assets/sfx/, never Apple's.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

SFX_DIR = REPO / "assets" / "sfx"
SFX_FILES = ("pop.wav", "swoosh.wav", "keyboard_clicks.wav", "shutter.wav", "music_bed.wav")

# ── brand ────────────────────────────────────────────────────────────────────
ORANGE = "#EF5829"
IVORY = "#F8F4ED"

# ── canvas / encode ──────────────────────────────────────────────────────────
W, H, FPS = 1080, 1920, 30

# ── bundle paths ─────────────────────────────────────────────────────────────
def textstory_dir(bundle): return Path(bundle) / "textstory"
def scenes_path(bundle):   return textstory_dir(bundle) / "scenes.json"
def work_dir(bundle):      return textstory_dir(bundle) / "work"
def output_path(bundle):   return textstory_dir(bundle) / "textstory.mp4"


# ── contact-name variants ────────────────────────────────────────────────────
# The thread is the mom's phone (audience = moms), texting her husband. Each
# episode picks its contact label deterministically from this pool (SHA-256 of
# the bundle name — same indexing pattern as the orchestrator's pseudonym
# pools) so episodes vary but re-runs are stable. Names are common-American
# generic; if one collides with a real name in the bundle's name-map.json,
# pick_contact skips to the next entry.
CONTACT_POOL = [
    "Hubby 💍",
    "Babe ❤️",
    "Love ❤️",
    "Hubs 💕",
    "Mike ❤️",
    "Dave ❤️",
    "Chris 💍",
    "My Love ❤️",
    "Honey 💛",
    "Matt ❤️",
]


def _name_part(label: str) -> str:
    """'Mike ❤️' -> 'mike' (for collision checks against name-map reals)."""
    return re.sub(r"[^A-Za-z]", "", label).lower()


def pick_contact(bundle, name_map: dict | None = None) -> dict:
    """Deterministic contact label for this bundle, skipping any label whose
    name collides with a real or pseudonym name from the bundle's name map."""
    taken = set()
    for e in (name_map or {}).get("entries", []):
        for k in ("real", "pseudonym"):
            v = (e.get(k) or "").strip().lower()
            if v:
                taken.add(v.split()[0])
    seed = int.from_bytes(
        hashlib.sha256(Path(bundle).resolve().name.encode()).digest()[:4], "big"
    )
    for step in range(len(CONTACT_POOL)):
        label = CONTACT_POOL[(seed + step) % len(CONTACT_POOL)]
        if _name_part(label) not in taken:
            return {"name": label, "letter": label[0].upper()}
    return {"name": "Hubby 💍", "letter": "H"}


def load_name_map(bundle) -> dict:
    p = Path(bundle) / "name-map.json"
    return json.loads(p.read_text()) if p.exists() else {}


def load_scenes(bundle) -> dict:
    p = scenes_path(bundle)
    if not p.exists():
        raise SystemExit(f"missing {p} — run make_scenes.py --bundle {bundle} first")
    return json.loads(p.read_text())


# ── metadata parsing (same shape as reel_common / comic) ─────────────────────
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
        "case_pattern": parse_meta_field(t, "case_pattern"),
        "school_named": parse_meta_field(t, "school_named"),
        "stat": parse_meta_field(t, "comic_stat") or parse_meta_field(t, "result_stat"),
    }


def find_doc1(bundle) -> Path:
    """The anonymized published case study (case-study-{pseudonym}.md)."""
    matches = sorted(Path(bundle).glob("case-study-*.md"))
    if not matches:
        raise SystemExit(f"no case-study-*.md found in {bundle}")
    return matches[0]

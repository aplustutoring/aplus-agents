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

# ── relationship dynamics ────────────────────────────────────────────────────
# DYNAMICS = every dynamic the generator/renderer supports.
# DEFAULT_DYNAMICS = the set a spotlight ships by default. family_group is
# supported but off by default (request it explicitly with --only family_group).
DYNAMICS = ["parents", "grandma", "mom_friend", "kid_parent", "family_group"]
DEFAULT_DYNAMICS = ["parents", "grandma", "mom_friend", "kid_parent"]


# ── bundle paths ─────────────────────────────────────────────────────────────
# A dynamic suffix keeps the five episodes side by side in the bundle:
#   textstory/scenes-grandma.json  ->  textstory/textstory-grandma.mp4
# (dynamic=None keeps the legacy single-file names for back-compat.)
def textstory_dir(bundle): return Path(bundle) / "textstory"
def work_dir(bundle):      return textstory_dir(bundle) / "work"

def scenes_path(bundle, dynamic=None):
    name = f"scenes-{dynamic}.json" if dynamic else "scenes.json"
    return textstory_dir(bundle) / name

def output_path(bundle, dynamic=None):
    name = f"textstory-{dynamic}.mp4" if dynamic else "textstory.mp4"
    return textstory_dir(bundle) / name


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


# Per-dynamic label pools for the "left" (contact) side of a 1:1 thread.
# right is always the mom ("you"). All labels are generic / role-based —
# never a real first name lifted from the case.
GRANDMA_POOL = ["Má ❤️", "Mom ❤️", "Grandma 💕", "Abuela ❤️", "Nana 💕",
                "Mamá ❤️", "Gigi 💕", "Grams ❤️"]
FRIEND_POOL = ["Jess 🌸", "Steph ☀️", "Nicole 💛", "Dani 🌷", "Court 💐",
               "Mel ✨", "Bri 🌼", "Kayla 💗"]
# family group: a group name + a set of role-based members (no real names)
GROUP_NAMES = ["Familia 👨‍👩‍👧‍👦", "The Group Chat 💬", "Family 💕", "La Familia ❤️"]
GROUP_MEMBERS = [("abuela", "Abuela"), ("tio", "Tío"), ("prima", "Prima"),
                 ("auntie", "Auntie"), ("nana", "Nana"), ("cousin", "Cuz"),
                 ("tia", "Tía"), ("uncle", "Uncle")]


def _seed(bundle, salt: str) -> int:
    return int.from_bytes(
        hashlib.sha256((Path(bundle).resolve().name + "|" + salt).encode()).digest()[:4],
        "big")


def _taken_names(name_map: dict | None) -> set:
    taken = set()
    for e in (name_map or {}).get("entries", []):
        for k in ("real", "pseudonym"):
            v = (e.get(k) or "").strip().lower()
            if v:
                taken.add(v.split()[0])
    return taken


def _pick_from(pool, bundle, salt, taken) -> str:
    seed = _seed(bundle, salt)
    for step in range(len(pool)):
        label = pool[(seed + step) % len(pool)]
        if _name_part(label) not in taken:
            return label
    return pool[seed % len(pool)]


def student_initial(name_map: dict | None) -> str:
    """First initial of the student pseudonym (already non-identifying), for
    the kid_parent header. Falls back to a neutral letter."""
    for e in (name_map or {}).get("entries", []):
        if e.get("role") == "student" and (e.get("pseudonym") or "").strip():
            return e["pseudonym"].strip()[0].upper()
    return "D"


def pick_contact(bundle, name_map: dict | None = None) -> dict:
    """Legacy: deterministic husband label (parents dynamic baseline)."""
    label = _pick_from(CONTACT_POOL, bundle, "parents", _taken_names(name_map))
    return {"name": label, "letter": label[0].upper()}


def build_contacts(dynamic: str, bundle, name_map: dict | None, meta: dict) -> dict:
    """Return the `contacts` block for a dynamic. right is always 'Mom' (you);
    deterministic per bundle so re-runs are stable but episodes vary.

    family_group returns {group, members:{key:name}}; the others return
    {left:<other party label>, right:'Mom'}."""
    taken = _taken_names(name_map)
    if dynamic == "parents":
        return {"left": _pick_from(CONTACT_POOL, bundle, "parents", taken), "right": "Mom"}
    if dynamic == "grandma":
        return {"left": _pick_from(GRANDMA_POOL, bundle, "grandma", taken), "right": "Mom"}
    if dynamic == "mom_friend":
        return {"left": _pick_from(FRIEND_POOL, bundle, "friend", taken), "right": "Mom"}
    if dynamic == "kid_parent":
        return {"left": student_initial(name_map), "right": "Mom"}
    if dynamic == "family_group":
        gname = GROUP_NAMES[_seed(bundle, "group") % len(GROUP_NAMES)]
        seed = _seed(bundle, "members")
        n = len(GROUP_MEMBERS)
        chosen, keys = {}, []
        for k in range(3):  # three relatives + the mom ("me")
            key, name = GROUP_MEMBERS[(seed + k) % n]
            chosen[key] = name
            keys.append(key)
        return {"group": gname, "members": chosen, "member_keys": keys}
    raise ValueError(f"unknown dynamic: {dynamic}")


def load_name_map(bundle) -> dict:
    p = Path(bundle) / "name-map.json"
    return json.loads(p.read_text()) if p.exists() else {}


def load_scenes(bundle, dynamic=None) -> dict:
    p = scenes_path(bundle, dynamic)
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

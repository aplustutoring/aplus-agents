#!/usr/bin/env python3
"""
Hero scene selector for A+ Tutoring B2C case study graphics.

Maps a case study's subject + grade level to a varied, home-setting hero
prompt that shows a representative child (face turned/partial, NOT fully
identifiable) at an age that matches the grade, with signs of siblings
(most A+ families have more than one kid).

This solves the "every hero looks identical" problem: the prompt varies by
subject (math desk vs reading nook vs writing journal vs science) and by
grade band (elementary props vs high-school props).

IMPORTANT — identification safety:
The child shown is AI-GENERATED and REPRESENTATIVE, never the real student.
The face is turned away, in profile, or partially out of frame so no
specific minor is identifiable. This is the B2C-case-study standard
(replaces the earlier fully-face-free rule, per Roman 2026-05-27).

Usage (from _batch_v2.py):
    from hero_scene import build_hero_prompt
    hero_prompt = build_hero_prompt(subject="math", grade=9)
"""


# ---------- Grade band → child age + props ----------


def _child_noun(gender):
    g = (gender or "").lower()
    if g in ("girl", "female", "f", "she", "her"):
        return "girl"
    if g in ("boy", "male", "m", "he", "him"):
        return "boy"
    return "child"

def _grade_band(grade, gender=None):
    """Return (age_phrase, props_phrase) for a grade level."""
    try:
        g = int(grade)
    except (ValueError, TypeError):
        g = 6  # default to middle-grade if unknown

    if g <= 2:
        return (
            "a young {noun} around 6 to 8 years old",
            "picture books, crayons, a coloring sheet, a stuffed animal on the chair",
        )
    elif g <= 5:
        return (
            "a {noun} around 9 to 11 years old",
            "a spiral notebook, colored pencils, a kid's water bottle, a backpack on the floor",
        )
    elif g <= 8:
        return (
            "a middle-school-aged {noun} around 12 to 14 years old",
            "a laptop, a spiral notebook, a textbook, earbuds on the table, a backpack",
        )
    else:
        return (
            "a teenage {noun} around 15 to 17 years old",
            "a laptop showing a tutoring session, a textbook, a spiral notebook, "
            "a phone face-down on the table, a backpack on a nearby chair",
        )


# ---------- Subject → scene ----------

def _subject_scene(subject):
    """Return a scene description for a subject area."""
    s = (subject or "").lower()
    if "math" in s or "algebra" in s or "geometry" in s or "calculus" in s:
        return (
            "working through math problems. Visible on the table: a notebook "
            "with handwritten equations, graph paper, a pencil, a calculator"
        )
    elif "read" in s or "english" in s or "ela" in s or "literacy" in s or "phonics" in s:
        return (
            "reading. Visible: an open book or workbook, a bookmark, a cozy "
            "reading lamp, a small stack of books nearby"
        )
    elif "writ" in s or "essay" in s or "composition" in s:
        return (
            "writing. Visible: an open journal or notebook with handwriting, "
            "a pen, a few crumpled draft pages, a laptop angled to the side"
        )
    elif "scien" in s or "biology" in s or "chemistry" in s or "physics" in s:
        return (
            "working on science. Visible: a notebook with diagrams, a science "
            "textbook, a few labeled sketches, a small desk lamp"
        )
    else:
        return (
            "doing schoolwork. Visible: an open notebook, a laptop, a pencil, "
            "a textbook on the table"
        )


# ---------- Home setting rotation ----------
# Vary the room so heroes don't all look like the same kitchen.

_SETTINGS = [
    "a warm kitchen table with late-afternoon sunlight through a window, "
    "kitchen cabinets softly out of focus behind",
    "a cozy living room, sitting at a coffee table or low table, a couch and "
    "family photos softly out of focus behind",
    "a bedroom desk with a window, soft natural light, a bookshelf behind",
    "a dining room table with warm overhead light, a hutch and family items "
    "softly out of focus behind",
]


def _setting_for(seed_text):
    """Pick a setting deterministically from a seed (so re-runs are stable)."""
    idx = sum(ord(c) for c in (seed_text or "default")) % len(_SETTINGS)
    return _SETTINGS[idx]


# ---------- Sibling signals ----------

_SIBLING_HINT = (
    "Include subtle signs that this is a family with more than one child: "
    "a second smaller backpack by the door, a younger sibling's drawing on "
    "the fridge or wall, a couple of differently-sized shoes near the "
    "entryway, or a younger child playing quietly in the soft-focus "
    "background. Keep these subtle, not staged."
)


# ---------- Identification-safety constraint ----------

FACE_PARTIAL_CONSTRAINT = (
    " CRITICAL CONSTRAINT: The child must NOT be fully facially identifiable. "
    "Show the child from behind, in profile, looking down at their work, or "
    "with the face partially out of frame or turned away from camera. The "
    "viewer should sense a real kid in a real moment WITHOUT being able to "
    "identify a specific child. This image is an AI-generated representative "
    "scene, NOT a real student. Do NOT render a clear front-facing portrait. "
    "Any sibling shown in the background must also be face-turned or "
    "soft-focus, never a clear identifiable portrait. No nudity, nothing "
    "other than a wholesome family learning moment."
)


def build_hero_prompt(subject=None, grade=None, seed_text=None, gender=None, ethnicity=None):
    """Build a complete hero image prompt for a case study.

    Args:
        subject: e.g. "math", "reading", "writing", "science"
        grade: int or str grade level (used for child age + props)
        seed_text: optional text (e.g. the title) to deterministically pick a setting

    Returns:
        The hero prompt string (WITHOUT the LOGO_EXCLUSION suffix — the
        caller appends that, as in the existing _batch_v2.py pattern).
    """
    age_phrase, props_phrase = _grade_band(grade)
    age_phrase = age_phrase.format(noun=_child_noun(gender))
    if ethnicity:
        ethnicity_clause = f"CRITICAL: The child is {ethnicity}. Render with skin tone, hair, and features authentic to that background."
    else:
        ethnicity_clause = "CRITICAL: The child is a child of color (Latino/Hispanic or African American), reflecting A+ Tutoring's real California charter families. Render with warm brown or medium-brown skin tone and dark hair."
    scene = _subject_scene(subject)
    setting = _setting_for(seed_text or subject or "default")

    prompt = (
        f"A photorealistic documentary-style photograph of {age_phrase} {scene}, "
        f"at {setting}. The child is captured candidly, face turned away or "
        f"looking down at their work (not facing the camera). On and around "
        f"the table: {props_phrase}. {_SIBLING_HINT} "
        f"Warm, natural late-afternoon light. The setting is unmistakably a "
        f"home, NEVER a classroom (no rows of desks, no chalkboard, no school "
        f"lockers). The child reads as ethnically ambiguous or diverse (reflecting A+ Tutoring's real families, many of whom are Latino or African American). Do NOT default to a white child. Documentary style similar to The Atlantic or NYT education "
        f"features. Natural color grading, warm shadows, shallow depth of "
        f"field at 35mm equivalent. 3:2 widescreen landscape. The aesthetic "
        f"should make a parent reading this case study feel: this could be my "
        f"kid, my home, this afternoon. No text overlay."
    )
    prompt = prompt.replace("{ethnicity_clause}", ethnicity_clause)
    return prompt


# ---------- Self-test ----------

if __name__ == "__main__":
    print("=== math, grade 9 ===")
    print(build_hero_prompt("math", 9, "The Day Camila Heard"))
    print("\n=== reading, grade 2 ===")
    print(build_hero_prompt("reading", 2, "Early Reading Story"))
    print("\n=== writing, grade 6 ===")
    print(build_hero_prompt("writing", 6, "Finding His Voice"))

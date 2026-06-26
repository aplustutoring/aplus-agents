#!/usr/bin/env python3
"""
make_script.py — emit a baseline storyboard SCRIPT (script.json) for a bundle's
spotlight reel, derived from {bundle}/metadata.md.

This is the deterministic baseline. The aplus-spotlight-reel SKILL then has the
agent REFINE the `vo` lines to be student-specific and in B2C voice, and run the
anonymization + brand-check gates before rendering. Scene/motion prompts and the
fictional hero archetype are derived here so the look stays on-brand.

The reel is INDEPENDENT of the comic: this reads the same upstream metadata the
comic reads; it never reads the comic's output.

Usage:  python3 scripts/b2c/reel/make_script.py --bundle aplus-content/{bundle}/
        [--voice Achird] [--force]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reel_common as rc


def beats_for(subject, gender):
    subj = str(subject).lower()
    emblem, power = rc.hero_power(subject)
    he = "she" if str(gender).lower().startswith("g") else "he"
    him = "her" if str(gender).lower().startswith("g") else "him"
    his = "her" if str(gender).lower().startswith("g") else "his"
    NB = ("Full-bleed 9:16 vertical comic-book art that fills the ENTIRE frame "
          "edge to edge. NO caption box, NO speech bubble, NO empty banner or "
          "strip, NO text, NO border, NO letterbox. Bold inked outlines, cel "
          "shading, vibrant colors, dramatic radial speed lines.")
    return [
        {
            "key": "struggle",
            "scene": (f"{NB} The hero sits slumped and defeated at a wooden study "
                      f"desk, head low and shoulders heavy, an open {subj} workbook "
                      f"in front of {him}. Dim gray tangled {subj} symbols drift "
                      f"around {his} head like cold fog. Muted cool blue-gray tones, "
                      f"somber and melancholy. No robot in this scene."),
            "motion": ("Subtle melancholy motion: shoulders rise and fall with a "
                       "heavy sigh, gray symbols swirl slowly like fog, a faint "
                       "flicker pulses through one symbol and dies, camera very "
                       "slowly pulls back. Muted cool tones. No style drift, no "
                       "morphing of the face."),
            "vo": f"For a while, {subj} felt impossible, and watching your child struggle is hard.",
            "delivery": "Gentle, empathetic and a little slow; you understand how hard it is to watch your child struggle.",
        },
        {
            "key": "sidekick",
            "scene": (f"{NB} The hero, seated at the desk, slowly lifts {his} head "
                      f"with the first spark of hope. Beside {him} hovers a friendly "
                      f"rounded pale-blue-and-white robot sidekick with a glowing "
                      f"screen face and a bright glowing 'A+' emblem on its chest, "
                      f"extending a glowing 'A+' tablet toward {him}. The dim gray "
                      f"{subj} symbols flicker back to warm orange light one by one. "
                      f"Palette warming from cool gray to golden."),
            "motion": ("Hopeful warming motion: the robot hovers and its emblem "
                       "pulses, the hero lifts head and shoulders, gray symbols "
                       "flicker to warm orange one by one, camera slowly drifts in. "
                       "No style drift, no morphing of the face."),
            "vo": "Then they had someone in their corner, meeting them right where they were.",
            "delivery": "Hopeful and reassuring, gradually warming and lifting.",
        },
        {
            "key": "breakthrough",
            "scene": (f"{NB} The hero stands powered-up, reaching out and grabbing a "
                      f"single glowing bright orange {subj} symbol that locks into "
                      f"place and bursts with light. Orange energy radiates outward "
                      f"in expanding waves, {power}. A friendly pale-blue-and-white "
                      f"robot sidekick with a glowing 'A+' chest emblem cheers beside "
                      f"{him}. Explosive warm orange radial background, triumphant, "
                      f"dynamic low angle."),
            "motion": ("Polished motion-graphics energy: the glowing element locks "
                       "into place with a burst of light, orange energy radiates in "
                       "slow waves, symbols orbit in controlled harmony, the robot "
                       "bobs cheering, camera slowly pushes in. No style drift, no "
                       "morphing of the face."),
            "vo": "Then one day, it just clicks, and it all starts to make sense.",
            "delivery": "A bright, genuine spark of delight — the moment it finally clicks. Smiling and uplifting, natural not shouty.",
        },
        {
            "key": "win",
            "scene": (f"{NB} The hero strikes a triumphant victory power pose with a "
                      f"billowing orange cape and a confident smile, {power} orbiting "
                      f"{him} like planets in harmony. Golden light rays radiate from "
                      f"behind {him}. A proud pale-blue-and-white robot sidekick with "
                      f"a glowing 'A+' chest emblem hovers in the background. "
                      f"Celebratory, heroic, warm golden tones."),
            "motion": ("Triumphant celebratory motion: the cape billows in slow "
                       "motion, symbols orbit in smooth harmony, golden rays pulse, "
                       "the robot hovers proudly, camera slowly rises in a gentle "
                       "heroic upward tilt. No style drift, no morphing of the face."),
            "vo": "Now they're confident, the hero of their own story.",
            "delivery": "Proud, warm and confident, with a happy smile.",
        },
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--voice", default="Achird", help="Gemini TTS voice")
    ap.add_argument("--force", action="store_true", help="overwrite existing script.json")
    args = ap.parse_args()

    meta = rc.read_metadata(args.bundle)
    out = rc.script_path(args.bundle)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not args.force:
        print(f"{out} exists (use --force to overwrite)")
        return 0

    script = {
        "subject": meta["subject"],
        "grade": meta["grade"],
        "gender": meta["gender"],
        "stat": meta["stat"],
        "voice": args.voice,
        "hero": rc.hero_description(meta["subject"], meta["grade"], meta["gender"]),
        "beats": beats_for(meta["subject"], meta["gender"]),
        "endcard": {
            "headline1": "Every kid has a",
            "headline2": "breakthrough in them.",
            "cta": "Book a consultation",          # primary goal
            "note": "Read the full stories:",       # gentle secondary invite
            "url": "wetutorathome.com/success/case-studies",
            "vo": "Every kid has a breakthrough in them. Book a consultation.",
            "delivery": "Warm and inviting; a gentle, encouraging call to action.",
        },
        "_note": ("Baseline draft. Refine `vo` lines to be student-specific and in "
                  "B2C voice, then run check-anonymization + aplus-brand-check + "
                  "aplus-fact-check before rendering. Captions are auto-derived from "
                  "the spoken `vo` (Whisper), so they always match the audio."),
    }
    out.write_text(json.dumps(script, indent=2, ensure_ascii=False))
    print(f"wrote {out}  (subject={meta['subject']} grade={meta['grade']} voice={args.voice})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

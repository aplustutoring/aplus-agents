#!/usr/bin/env python3
"""
make_scenes.py — generate {bundle}/textstory/scenes.json from bundle metadata.

One Claude call (ANTHROPIC_API_KEY, same direct-API pattern as the draft
stage) converts the case study's arc into an INVENTED Mom<->Dad text thread.
The system prompt encodes the format guardrails; this script then VALIDATES
the output before it can reach the renderer:

  - schema shape (scenes/msgs/froms/types)
  - no real names, pseudonyms, or school names (from name-map.json + metadata)
  - no protected classifications (IEP/ELL/disability/income/foster)
  - no verbatim transcript lifting: any 6-word run shared with the bundle's
    raw source_texts.json rejects the script (dialogue must be invented —
    quoting a real parent's words would fabricate a record of a real
    conversation)

On validation failure the call retries once with the violations fed back.

Usage:  python3 scripts/b2c/textstory/make_scenes.py --bundle aplus-content/{bundle}/
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textstory_common as tc  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv(tc.REPO / ".env")

CLAUDE_MODEL = "claude-opus-4-7"   # same tier as the orchestrator's draft stage
MAX_MSG_CHARS = 95
SENSITIVE_TERMS = [
    "iep", "504", "ell ", " el ", "english learner", "disability", "disabled",
    "special ed", "sped", "foster", "low-income", "low income", "free lunch",
    "reduced lunch", "medicaid", "autis", "adhd", "dyslex",
]

SYSTEM_PROMPT = """\
You write 30-second vertical social videos for A+ Tutoring formatted as a
text-message thread between two parents (a mom and a dad) about their child's
tutoring turnaround. You are given the published (anonymized) case study and
its metadata. Output ONLY a JSON object, no markdown fences, no commentary.

HARD RULES — violating any of these fails the job:
1. The dialogue is INVENTED. Write it fresh from the story's arc. NEVER copy,
   quote, or lightly paraphrase sentences from the case study or any parent
   quote in it. No phrase of 6+ consecutive words may match the source.
2. NO names of any kind: no student name or pseudonym, no parent names, no
   school name, no tutor name, no city. The child is only "he" or "she"
   (match student_gender). The parents are just the two speakers.
3. NEVER mention or imply protected classifications: IEP, 504, ELL/English
   learner, disability, diagnosis, income, foster status.
4. Keep it texty: contractions, lowercase-casual where natural, short bursts,
   occasional emoji (sparingly, like real parents). Each message under 90
   characters. It must read like real spouses, not ad copy.
5. Arc shape across 4 scenes (each scene = one evening, weeks apart, shown by
   its timestamp divider):
     scene 1 — the struggle (pain, worry; end on an emotional gut-punch)
     scene 2 — tutoring starts (small, wry, guarded hope)
     scene 3 — the turn (something unprompted happens; disbelief, joy)
     scene 4 — the proof (a concrete win; use type:"screenshot" for a grade
               or score reveal, then 2-3 stunned texts)
6. Exactly one message in scene 1 may use {"from":"dad","type":"typing_pause"}
   — dad starts typing, stops. Place it right after the most painful line.
   It is an emotional beat; use it.
7. Scene 4 must contain exactly one {"from":"mom","type":"screenshot",
   "alt":"<what the screenshot shows, generic>"} message.
8. 15-19 total messages across all 4 scenes. Timestamps: realistic
   "Mon D, H:MM PM" style, spanning roughly the case study's time span,
   in chronological order.

OUTPUT SHAPE (exactly this structure):
{
  "episode": "<short-kebab-slug-from-the-arc>",
  "scenes": [
    {"ts": "Sept 12, 8:47 PM", "msgs": [
      {"from": "mom", "text": "..."},
      {"from": "dad", "text": "..."},
      {"from": "dad", "type": "typing_pause"},
      {"from": "mom", "type": "screenshot", "alt": "..."}
    ]}
  ],
  "endcard_line": "<one short punchy line for the end card, max 42 chars,
                   second-person or universal, e.g. 'Every parent deserves
                   this text.'>"
}
"""


def claude_scenes(meta: dict, doc1: str, feedback: str | None = None) -> dict:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY is not set.")
    client = anthropic.Anthropic(api_key=api_key)

    user = (
        f"subject: {meta['subject']}\n"
        f"grade: {meta['grade']}\n"
        f"student_gender: {meta['gender']}\n"
        f"case_pattern: {meta['case_pattern']}\n"
        f"headline_stat: {meta['stat']}\n\n"
        f"PUBLISHED CASE STUDY (anonymized; do NOT quote from it):\n\n{doc1}"
    )
    if feedback:
        user += (
            "\n\nYOUR PREVIOUS ATTEMPT FAILED VALIDATION. Violations:\n"
            f"{feedback}\nRegenerate the full JSON fixing every violation."
        )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("Claude returned no JSON object")
    return json.loads(m.group(0))


# ── validation ───────────────────────────────────────────────────────────────
def _norm_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _ngrams(words: list[str], n: int):
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def validate(scenes: dict, banned_names: list[str], school: str,
             source_texts: dict[str, str]) -> list[str]:
    errors: list[str] = []
    sc = scenes.get("scenes")
    if not isinstance(sc, list) or not 3 <= len(sc) <= 5:
        return [f"need 3-5 scenes, got {sc if not isinstance(sc, list) else len(sc)}"]

    msgs = [m for s in sc for m in s.get("msgs", [])]
    n_text = sum(1 for m in msgs if m.get("text"))
    if not 12 <= n_text <= 22:
        errors.append(f"need 15-19 text messages, got {n_text}")
    if sum(1 for m in msgs if m.get("type") == "screenshot") != 1:
        errors.append("need exactly one screenshot message")
    if sum(1 for m in msgs if m.get("type") == "typing_pause") > 1:
        errors.append("at most one typing_pause")

    all_text = " ".join(m.get("text", "") + " " + m.get("alt", "") for m in msgs)
    all_text += " " + scenes.get("endcard_line", "")
    low = " " + all_text.lower() + " "

    for m in msgs:
        if m.get("from") not in ("mom", "dad"):
            errors.append(f"bad from: {m.get('from')!r}")
        t = m.get("text", "")
        if len(t) > MAX_MSG_CHARS:
            errors.append(f"message over {MAX_MSG_CHARS} chars: {t[:40]!r}...")

    for name in banned_names:
        if re.search(rf"\b{re.escape(name)}\b", all_text, re.IGNORECASE):
            errors.append(f"banned name appears in dialogue: {name!r}")
    if school:
        for token in re.findall(r"[A-Za-z]{4,}", school):
            if token.lower() in ("school", "academy", "charter", "elementary",
                                 "middle", "high", "academies"):
                continue
            if re.search(rf"\b{re.escape(token)}\b", all_text, re.IGNORECASE):
                errors.append(f"school name token in dialogue: {token!r}")
    for term in SENSITIVE_TERMS:
        if term in low:
            errors.append(f"protected-classification term in dialogue: {term.strip()!r}")

    # verbatim-lift check vs raw transcripts: any shared 6-word run fails
    gen_grams = _ngrams(_norm_words(all_text), 6)
    if gen_grams:
        for fname, src in (source_texts or {}).items():
            hit = gen_grams & _ngrams(_norm_words(src), 6)
            if hit:
                errors.append(
                    f"verbatim 6-word overlap with source {fname!r}: {sorted(hit)[0]!r}")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--force", action="store_true", help="regenerate even if scenes.json exists")
    args = ap.parse_args()

    out = tc.scenes_path(args.bundle)
    if out.exists() and not args.force:
        print(f"scenes.json already exists: {out} (use --force to regenerate)")
        return 0

    meta = tc.read_metadata(args.bundle)
    doc1 = tc.find_doc1(args.bundle).read_text()
    name_map = tc.load_name_map(args.bundle)
    banned = sorted({
        v.strip() for e in name_map.get("entries", [])
        for v in (e.get("real", ""), e.get("pseudonym", "")) if v.strip()
    })
    st_path = Path(args.bundle) / "source_texts.json"
    source_texts = json.loads(st_path.read_text()) if st_path.exists() else {}

    feedback = None
    for attempt in (1, 2):
        print(f"scene generation attempt {attempt} ...")
        scenes = claude_scenes(meta, doc1, feedback)
        errors = validate(scenes, banned, meta.get("school_named", ""), source_texts)
        if not errors:
            break
        print("  validation failures:\n   - " + "\n   - ".join(errors))
        feedback = "\n".join(f"- {e}" for e in errors)
    else:
        sys.exit("scene validation failed twice — not writing scenes.json")
    if errors:
        sys.exit("scene validation failed twice — not writing scenes.json")

    scenes["contact"] = tc.pick_contact(args.bundle, name_map)
    scenes["endcard"] = {
        "line": (scenes.pop("endcard_line", "") or "Every parent deserves this text.")[:60],
        "cta": "Book a free consultation",
        "cta_url": "https://meetings.hubspot.com/successful/consultation",
        # disclosure intentionally NOT configurable here: the renderer's
        # template bakes "Based on real A+ family outcomes" into the end card.
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scenes, indent=2, ensure_ascii=False))
    n = sum(len(s["msgs"]) for s in scenes["scenes"])
    print(f"wrote {out} ({len(scenes['scenes'])} scenes, {n} messages, "
          f"contact {scenes['contact']['name']!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

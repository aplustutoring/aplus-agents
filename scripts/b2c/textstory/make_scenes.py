#!/usr/bin/env python3
"""
make_scenes.py — generate {bundle}/textstory/scenes-<dynamic>.json from a
bundle's case study, for ONE relationship dynamic.

Each spotlight produces five text-story episodes (see textstory_common.DYNAMICS),
all from the SAME case arc, each in a different sender pairing / voice:
  parents · grandma · mom_friend · kid_parent · family_group

One Claude call per dynamic (ANTHROPIC_API_KEY, same direct-API pattern as the
draft stage). Per-dynamic calls — not one combined call — so each gets a focused
voice-rules prompt + few-shot and validates/retries independently; a malformed
response for one dynamic never poisons the others. Cost is ~5x one short call
(~$0.50/spotlight), still zero generation-API spend.

Guardrails (encoded in the prompt AND hard-validated here):
  - invented archetypal dialogue; no 6-word verbatim overlap with raw transcripts
  - no real names / pseudonyms / school-name tokens; kid by initial only
  - no protected classifications (IEP/504/ELL/disability/income/foster)
  - kid_parent: child lines stay sparse (<=7 words) and never salesy
  - contacts (sender labels) are injected in CODE, not generated, so the POV
    convention (right = the mom = "you") and name-safety can't drift
  - end-card disclosure is baked into the renderer template, never generated

Usage:
  python3 scripts/b2c/textstory/make_scenes.py --bundle <bundle> --dynamic grandma
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

CLAUDE_MODEL = "claude-opus-4-7"
MAX_MSG_CHARS = 95
KID_MAX_WORDS = 7
SENSITIVE_TERMS = [
    "iep", "504", "ell ", " el ", "english learner", "disability", "disabled",
    "special ed", "sped", "foster", "low-income", "low income", "free lunch",
    "reduced lunch", "medicaid", "autis", "adhd", "dyslex",
]
# phrases a real kid would never text — kills the kid_parent illusion
SALESY_TERMS = [
    "journey", "unlock", "confidence", "amazing", "incredible", "potential",
    "grades have", "improved so", "thanks to", "best decision", "highly recommend",
    "game changer", "game-changer", "passionate", "so grateful", "officially",
    "couldn't be prouder", "proud of myself for",
]

# ── shared schema spec ───────────────────────────────────────────────────────
SCHEMA_SPEC = """\
OUTPUT: a single JSON object, no markdown fences, no commentary. Shape:
{
  "episode": "<short-kebab-slug>",
  "scenes": [
    {"ts": "Tue, Sept 9, 7:12 PM", "msgs": [ <message>, ... ]}
  ],
  "endcard_line": "<one short punchy end-card line, <=42 chars>"
}

A <message> is one of:
  {"from": <sender>, "text": "..."}                       a text bubble
  {"from": <sender>, "text": "...", "caps": true}         emphatic ALL-CAPS bubble
  {"from": <sender>, "type": "typing_pause"}              dots appear, then stop (a beat)
  {"from": <sender>, "type": "voice_message", "duration": "0:47"}  a voice note
  {"from": <sender>, "type": "screenshot", "alt": "<what it shows>",
     "shot": {"portal": "Grade Portal", "course": "Algebra 1",
              "term": "Sem 1", "grade": "B+", "trend": [30,46,70,104]}}
  {"from": <sender>, "type": "reaction", "emoji": "😭", "target": "previous"}

RULES (all dynamics):
- 3-4 scenes, each a different evening/day weeks apart, shown by its timestamp.
- Arc across the scenes: struggle -> change begins -> proof -> joy.
- EXACTLY ONE screenshot message, in the proof/joy stretch. Put a realistic
  grade/score/level in its "shot" (a clean PUBLIC stat only — never a
  classification). The screenshot is the visual payoff.
- Invent every line fresh. Do NOT copy or paraphrase sentences from the case
  study; no run of 6+ consecutive words may match it.
- No names of anyone (no student/parent/tutor/teacher names, no school, no
  city). Refer to the child only as he/she or "the kid".
- Never mention IEP/504/ELL/disability/diagnosis/income/foster.
- Texty and real: contractions, lowercase-casual, short bursts, emoji used
  the way real people use them. Each text bubble under 90 characters.
"""

PARENTS_FEWSHOT = """\
EXAMPLE (parents — "who is this child", math arc):
{"episode":"who-is-this-child","scenes":[
 {"ts":"Sept 12, 8:47 PM","msgs":[
   {"from":"right","text":"He shut his door again. Math homework fight #3 this week 😞"},
   {"from":"left","text":"Same as last year. I don't know what else to do"},
   {"from":"right","text":"He said \\"I'm just stupid at math\\" tonight"},
   {"from":"left","type":"typing_pause"},
   {"from":"left","text":"That one hurts"}]},
 {"ts":"Nov 14, 6:22 PM","msgs":[
   {"from":"right","text":"You're not going to believe this"},
   {"from":"right","text":"He's doing homework. RIGHT NOW. Nobody asked him."},
   {"from":"left","text":"WHO IS THIS CHILD"}]},
 {"ts":"Jan 20, 3:05 PM","msgs":[
   {"from":"right","type":"screenshot","alt":"grade portal B+ in Algebra","shot":{"portal":"Grade Portal","course":"Algebra 1","term":"Sem 1","grade":"B+","trend":[30,48,72,104]}},
   {"from":"right","text":"That's ALGEBRA."},
   {"from":"left","text":"Call me right now"}]}],
 "endcard_line":"Every parent deserves this text."}
"""

GRANDMA_FEWSHOT = """\
EXAMPLE (grandma — reading arc; right=Mom, left=grandma):
{"episode":"abuela-finds-out","scenes":[
 {"ts":"Tue, Sept 9, 7:12 PM","msgs":[
   {"from":"right","text":"Ma he cried over his reading again tonight"},
   {"from":"left","text":"MI AMOR. He is SO smart. Who said this","caps":true},
   {"from":"right","text":"He did. He thinks he's the slow one"},
   {"from":"left","type":"voice_message","duration":"0:48"}]},
 {"ts":"Thu, Oct 16, 5:40 PM","msgs":[
   {"from":"right","text":"the tutor has him reading out loud to me now"},
   {"from":"left","text":"QUE?? put him on the phone put him on","caps":true}]},
 {"ts":"Fri, Dec 5, 6:30 PM","msgs":[
   {"from":"right","type":"screenshot","alt":"reading level jumped","shot":{"portal":"Reading Level","course":"Chapter Books","term":"Level M → R","grade":"R","trend":[28,44,68,100]}},
   {"from":"left","type":"voice_message","duration":"1:02"},
   {"from":"left","type":"reaction","emoji":"😭","target":"previous"}]}],
 "endcard_line":"Every grandma deserves this voice note."}
"""

SLACK_SCHEMA_SPEC = """\
OUTPUT: a single JSON object, no fences, no commentary. Shape:
{
  "episode": "<short-kebab-slug>",
  "scenes": [ {"msgs": [ <post>, ... ]} ],   // exactly ONE scene (one thread)
  "endcard_line": "<one short end-card line, <=52 chars>"
}
A <post> is: {"from": <role-key>, "ts": "4:47 PM", "text": "...",
              "reactions": [{"emoji": "🎉", "count": 12}]}   // reactions optional

RULES (team_slack):
- 6-9 posts, ONE thread, realistic times a minute or two apart.
- The TUTOR posts first and opens with a SPECIFIC IMAGE (the chapter she read,
  the unprompted homework) — NEVER a stat. Emotional and concrete.
- Put @channel (or @here) in the tutor's or a lead's post at the emotional peak.
- Team replies are short, warm, human. Sneak in ONE credibility data point
  naturally via the "data" person (e.g. a reclassification %), never forced.
- The FOUNDER posts LAST and closes on the mission ("this is why we do this").
- The child is referred to ONLY by a single initial. No student/tutor full
  names beyond the role display names, no school, no city.
- Invent every line; no 6+ consecutive words matching the case study.
- Reactions: use a few emoji+count pills on the big posts; keep counts realistic
  (single/low-double digits).
- Slack-native texture is welcome where it feels natural and doesn't bury the
  story: a /giphy line (e.g. "/giphy happy dance"), "pinned this to the channel",
  an @mention of a teammate by name. Use at most one or two such touches.
"""

TEAM_SLACK_FEWSHOT = """\
EXAMPLE (team_slack — reading arc; keys: tutor, peer, data, founder):
{"episode":"this-is-why-we-do-this","scenes":[{"msgs":[
 {"from":"tutor","ts":"4:47 PM","text":"@channel ok I have to share this. D just read a full chapter out loud. unprompted. then asked for ONE more page 😭","reactions":[{"emoji":"🎉","count":12},{"emoji":"❤️","count":8}]},
 {"from":"peer","ts":"4:48 PM","text":"the SAME kid who hid under the desk during her September assessment??"},
 {"from":"tutor","ts":"4:48 PM","text":"the exact same kid. she told me \\"books are kind of fun now\\""},
 {"from":"data","ts":"4:49 PM","text":"this is the reclassification story in real time. 63% of our intervention kids move up a level in a semester and it still gets me","reactions":[{"emoji":"📈","count":7}]},
 {"from":"peer","ts":"4:50 PM","text":"I'm not crying you're crying 🥹","reactions":[{"emoji":"😭","count":9}]},
 {"from":"founder","ts":"4:52 PM","text":"This. This is why we do this. Thank you ❤️","reactions":[{"emoji":"❤️","count":15}]}
]}],"endcard_line":"Behind every win is a team that loses it over your kid."}
"""

DYNAMIC_CONFIG = {
    "parents": {
        "senders": "Use from \"right\" (the mom, you) and \"left\" (her husband). Equal voices.",
        "voice": (
            "The parental war room. Clipped, tag-team worry that turns into shared "
            "relief. Both carry emotion equally. One typing_pause on the most "
            "painful line in scene 1. No voice messages, no reactions needed."),
        "fewshot": PARENTS_FEWSHOT,
    },
    "grandma": {
        "senders": "Use from \"right\" (the mom, you) and \"left\" (the grandma).",
        "voice": (
            "Generational and warm. The grandma's love comes first, always. Use "
            "ALL-CAPS as EMOTION (set \"caps\": true), not anger. Give her at least "
            "TWO voice_message notes (grandmas leave voice notes). Light tech "
            "bewilderment is endearing, never mocking. A Spanish term of endearment "
            "(mi amor, mija, que lindo) is welcome where it fits naturally. Payoff: "
            "the kid reads/works FOR the grandma. Add a reaction on the final beat."),
        "fewshot": GRANDMA_FEWSHOT,
    },
    "mom_friend": {
        "senders": "Use from \"right\" (the mom, you) and \"left\" (her mom-friend).",
        "voice": (
            "The referral engine. Casual, gossipy-warm, the way two mom-friends "
            "actually text. The friend watches the turnaround secondhand. END on "
            "the referral ask + link share: the friend says some version of "
            "\"ok WHO is this tutor\" and you reply \"I'll send you the link\" / "
            "\"sending it now\". That last beat models the exact behavior we want a "
            "viewer to do. No voice messages needed."),
        "fewshot": PARENTS_FEWSHOT,
    },
    "kid_parent": {
        "senders": "Use from \"right\" (the mom, you) and \"left\" (the KID).",
        "voice": (
            "Highest ceiling, highest risk. The MOM (right) carries all the emotion. "
            "The KID (left) texts like a real kid: 2-6 words, deadpan, lowercase, "
            "no punctuation flourishes, zero enthusiasm-performance. A real kid "
            "texts \"k\", \"idk\", \"it was fine\", \"can my tutor keep going over "
            "summer\". NEVER let the kid sound precocious, grateful-on-cue, or like "
            "an ad. The kid's peak beat is asking — flat and real — to keep the "
            "tutor over summer; that lands BECAUSE it's underplayed. If the kid "
            "sounds like a copywriter the episode is dead. No caps, no voice notes "
            "from the kid."),
        "fewshot": PARENTS_FEWSHOT,
    },
    "family_group": {
        "senders": None,  # filled per-bundle (member keys) in build_system_prompt
        "voice": (
            "The family group chat. Rapid, overlapping, joyful chaos. You (\"me\") "
            "drop ONE proof screenshot and the relatives pile on: the grandma in "
            "ALL-CAPS (caps:true), an excitable uncle, a hyped cousin doing \"W\" / "
            "\"WWWW\". Use several short reaction messages (emoji tapbacks) to make "
            "it feel like an avalanche. Keep most messages very short. It should "
            "feel screenshot-and-share-worthy."),
        "fewshot": GRANDMA_FEWSHOT,
    },
    "team_slack": {
        "senders": None,  # filled per-bundle (role keys) in build_system_prompt
        "voice": (
            "A+'s internal #student-wins Slack channel — the behind-the-scenes that "
            "sells the CULTURE: a team that loses it over a kid's win. A tutor "
            "shares the win, the team piles on. Warm, human, real workplace texture. "
            "This is INVENTED archetype, never a real Slack message anyone actually "
            "sent."),
        "fewshot": TEAM_SLACK_FEWSHOT,
        "schema": SLACK_SCHEMA_SPEC,
    },
}


def build_system_prompt(dynamic: str, contacts: dict) -> str:
    cfg = DYNAMIC_CONFIG[dynamic]
    if dynamic == "team_slack":
        members = contacts.get("members", {})
        roster = ", ".join(f'"{k}" ({members[k]})' for k in contacts.get("member_keys", []))
        senders = (
            f'This is a team Slack channel (#student-wins). Use these exact role '
            f'keys for "from": {roster}. The "tutor" posts first and opens; the '
            f'"founder" posts last and closes. Every post must come from one of '
            f'those keys.')
        return (
            "You write 30-second vertical social videos for A+ Tutoring as an "
            "internal Slack thread about a child's tutoring win.\n\n"
            f"DYNAMIC: team_slack\n{senders}\n\nVOICE: {cfg['voice']}\n\n"
            f"{cfg['schema']}\n{cfg['fewshot']}"
        )
    if dynamic == "family_group":
        keys = contacts.get("member_keys", [])
        members = contacts.get("members", {})
        roster = ", ".join(f'"{k}" ({members[k]})' for k in keys)
        senders = (
            f'This is a GROUP chat. Use from "me" for the mom (you, the proof-'
            f'dropper) and these relatives: {roster}. Every message '
            f'must come from "me" or one of those exact keys.')
    else:
        senders = cfg["senders"]
    return (
        "You write 30-second vertical social videos for A+ Tutoring as a "
        "text-message thread about a child's tutoring turnaround.\n\n"
        f"DYNAMIC: {dynamic}\n{senders}\n\nVOICE: {cfg['voice']}\n\n"
        f"{SCHEMA_SPEC}\n{cfg['fewshot']}"
    )


# ── Claude call ──────────────────────────────────────────────────────────────
def claude_scenes(dynamic: str, contacts: dict, meta: dict, doc1: str,
                  feedback: str | None = None) -> dict:
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
        user += ("\n\nYOUR PREVIOUS ATTEMPT FAILED VALIDATION. Violations:\n"
                 f"{feedback}\nRegenerate the full JSON fixing every violation.")
    message = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=4000,
        system=build_system_prompt(dynamic, contacts),
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
    return json.loads(_extract_json(text))


def _extract_json(text: str) -> str:
    """Return the first balanced {...} object, ignoring any prose/extra value
    the model may append after it (json.loads rejects trailing data)."""
    start = text.find("{")
    if start < 0:
        raise ValueError("Claude returned no JSON object")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("Claude returned an unbalanced JSON object")


# ── validation ───────────────────────────────────────────────────────────────
def _norm_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _ngrams(words, n):
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _valid_senders(dynamic: str, contacts: dict) -> set:
    if dynamic in ("family_group", "team_slack"):
        return set(contacts.get("member_keys", [])) | ({"me"} if dynamic == "family_group" else set())
    return {"left", "right"}


def _shared_text_checks(msgs, scenes, banned_names, school, source_texts,
                        max_chars) -> list[str]:
    """Guardrail checks common to every dynamic: no banned/pseudonym/school
    names, no protected classifications, no verbatim transcript overlap,
    per-message length cap."""
    errors: list[str] = []
    for m in msgs:
        t = m.get("text", "")
        if len(t) > max_chars:
            errors.append(f"message over {max_chars} chars: {t[:40]!r}...")
    all_text = " ".join(m.get("text", "") + " " + m.get("alt", "") for m in msgs)
    all_text += " " + scenes.get("endcard_line", "")
    low = " " + all_text.lower() + " "
    for name in banned_names:
        if re.search(rf"\b{re.escape(name)}\b", all_text, re.IGNORECASE):
            errors.append(f"banned name in dialogue: {name!r}")
    if school:
        for token in re.findall(r"[A-Za-z]{4,}", school):
            if token.lower() in ("school", "academy", "charter", "elementary",
                                  "middle", "high", "academies", "prep"):
                continue
            if re.search(rf"\b{re.escape(token)}\b", all_text, re.IGNORECASE):
                errors.append(f"school name token in dialogue: {token!r}")
    for term in SENSITIVE_TERMS:
        if term in low:
            errors.append(f"protected-classification term: {term.strip()!r}")
    gen_grams = _ngrams(_norm_words(all_text), 6)
    if gen_grams:
        for fname, src in (source_texts or {}).items():
            hit = gen_grams & _ngrams(_norm_words(src), 6)
            if hit:
                errors.append(f"verbatim 6-word overlap with {fname!r}: {sorted(hit)[0]!r}")
    return errors


def validate(dynamic, scenes, contacts, banned_names, school, source_texts) -> list[str]:
    if dynamic == "team_slack":
        return _validate_team_slack(scenes, contacts, banned_names, school, source_texts)

    errors: list[str] = []
    sc = scenes.get("scenes")
    if not isinstance(sc, list) or not 3 <= len(sc) <= 4:
        return [f"need 3-4 scenes, got {sc if not isinstance(sc, list) else len(sc)}"]

    msgs = [m for s in sc for m in s.get("msgs", [])]
    valid_from = _valid_senders(dynamic, contacts)
    n_text = sum(1 for m in msgs if m.get("text"))
    if not 8 <= n_text <= 24:
        errors.append(f"need ~10-22 text messages, got {n_text}")
    n_shot = sum(1 for m in msgs if m.get("type") == "screenshot")
    if n_shot != 1:
        errors.append(f"need exactly one screenshot, got {n_shot}")
    for m in msgs:
        if m.get("from") not in valid_from:
            errors.append(f"bad from {m.get('from')!r} (allowed: {sorted(valid_from)})")

    errors += _shared_text_checks(msgs, scenes, banned_names, school, source_texts, MAX_MSG_CHARS)
    errors += _validate_dynamic(dynamic, msgs, contacts)
    return errors


def _validate_team_slack(scenes, contacts, banned_names, school, source_texts) -> list[str]:
    errors: list[str] = []
    sc = scenes.get("scenes")
    if not isinstance(sc, list) or not 1 <= len(sc) <= 2:
        return [f"team_slack needs 1 thread (scene), got {sc if not isinstance(sc, list) else len(sc)}"]
    msgs = [m for s in sc for m in s.get("msgs", [])]
    if not 5 <= len(msgs) <= 12:
        errors.append(f"need 6-9 posts, got {len(msgs)}")
    valid_from = _valid_senders("team_slack", contacts)
    for m in msgs:
        if m.get("from") not in valid_from:
            errors.append(f"bad from {m.get('from')!r} (allowed: {sorted(valid_from)})")
    if msgs:
        if msgs[0].get("from") != "tutor":
            errors.append("the tutor must post first")
        if msgs[-1].get("from") != "founder":
            errors.append("the founder must close the thread")
    joined = " ".join(m.get("text", "") for m in msgs)
    if not re.search(r"@(channel|here|everyone)", joined):
        errors.append("needs an @channel/@here broadcast ping at the peak")
    if not re.search(r"\d", joined):
        errors.append("sneak in one credibility data point (a number/percent)")
    # the tutor's opener must lead with an image, not a bare stat: only flag if
    # it literally STARTS with a number (after any @mentions), e.g. "63% of...".
    if msgs:
        opener = re.sub(r"^\s*(@\w+\s*)+", "", msgs[0].get("text", "") or "").strip()
        if opener[:1].isdigit():
            errors.append("tutor opener should lead with an image, not a number/stat")
    # Slack posts run longer than texts; allow a roomier cap.
    errors += _shared_text_checks(msgs, scenes, banned_names, school, source_texts, 300)
    return errors


def _validate_dynamic(dynamic, msgs, contacts) -> list[str]:
    e: list[str] = []
    if dynamic == "grandma":
        if sum(1 for m in msgs if m.get("type") == "voice_message") < 1:
            e.append("grandma needs at least one voice_message")
        if not any(m.get("caps") for m in msgs):
            e.append("grandma needs at least one ALL-CAPS (caps:true) line")
    elif dynamic == "kid_parent":
        for m in msgs:
            if m.get("from") != "left" or not m.get("text"):
                continue
            words = m["text"].split()
            if len(words) > KID_MAX_WORDS:
                e.append(f"kid line too long ({len(words)} words): {m['text'][:40]!r}")
            low = m["text"].lower()
            for term in SALESY_TERMS:
                if term in low:
                    e.append(f"kid line sounds salesy ({term!r}): {m['text'][:40]!r}")
    elif dynamic == "mom_friend":
        tail = " ".join(m.get("text", "") for m in msgs[-4:]).lower()
        if not re.search(r"link|send (you|it)|sending|who is (the )?tutor|what tutor", tail):
            e.append("mom_friend must end on the referral ask + link share")
    elif dynamic == "family_group":
        senders = {m.get("from") for m in msgs}
        relatives = senders - {"me"}
        if len(relatives) < 2:
            e.append(f"family_group needs >=2 relatives reacting, got {sorted(relatives)}")
        if sum(1 for m in msgs if m.get("type") == "reaction") < 1:
            e.append("family_group needs at least one reaction")
    return e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--dynamic", required=True, choices=tc.DYNAMICS)
    ap.add_argument("--force", action="store_true", help="regenerate even if it exists")
    args = ap.parse_args()

    out = tc.scenes_path(args.bundle, args.dynamic)
    if out.exists() and not args.force:
        print(f"{out.name} exists (use --force to regenerate)")
        return 0

    meta = tc.read_metadata(args.bundle)
    doc1 = tc.find_doc1(args.bundle).read_text()
    name_map = tc.load_name_map(args.bundle)
    contacts = tc.build_contacts(args.dynamic, args.bundle, name_map, meta)
    banned = sorted({
        v.strip() for e in name_map.get("entries", [])
        for v in (e.get("real", ""), e.get("pseudonym", "")) if v.strip()
    })
    st_path = Path(args.bundle) / "source_texts.json"
    source_texts = json.loads(st_path.read_text()) if st_path.exists() else {}

    feedback, errors = None, ["init"]
    for attempt in (1, 2, 3):
        print(f"[{args.dynamic}] scene generation attempt {attempt} ...")
        try:
            scenes = claude_scenes(args.dynamic, contacts, meta, doc1, feedback)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"  could not parse Claude output: {exc}")
            feedback = f"- your output was not a single valid JSON object ({exc})"
            errors = [str(exc)]
            continue
        errors = validate(args.dynamic, scenes, contacts,
                          banned, meta.get("school_named", ""), source_texts)
        if not errors:
            break
        print("  validation failures:\n   - " + "\n   - ".join(errors))
        feedback = "\n".join(f"- {x}" for x in errors)
    if errors:
        sys.exit(f"[{args.dynamic}] scene generation failed after retries — not writing")

    # contacts/members injected here (NOT model-generated) -> POV, name-safety,
    # and the consent flag can't drift from what the model produces.
    default_line = ("Behind every win is a team that loses it over your kid."
                    if args.dynamic == "team_slack" else "Every parent deserves this text.")
    out_obj = {
        "episode": scenes.get("episode", args.dynamic),
        "dynamic": args.dynamic,
        "scenes": scenes["scenes"],
        "endcard": {
            "line": (scenes.get("endcard_line") or default_line)[:60],
            "cta": "Book a free consultation",
            "cta_url": "https://meetings.hubspot.com/successful/consultation",
            # disclosure intentionally absent — the renderer template bakes it in
            # ("real A+ family outcomes" / "real A+ team moments").
        },
    }
    if args.dynamic == "team_slack":
        out_obj["skin"] = "slack"
        out_obj["channel"] = contacts.get("channel", "student-wins")
        out_obj["members"] = contacts.get("members", {})
    else:
        out_obj["contacts"] = {k: v for k, v in contacts.items() if k != "member_keys"}
        if args.dynamic == "family_group":
            out_obj["contacts"]["member_keys"] = contacts.get("member_keys", [])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(out_obj, indent=2, ensure_ascii=False))
    n = sum(len(s["msgs"]) for s in scenes["scenes"])
    print(f"wrote {out.name} ({len(scenes['scenes'])} scenes, {n} msgs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

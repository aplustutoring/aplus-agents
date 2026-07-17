#!/usr/bin/env python3
"""
call_agent.py
-------------
Call Agent v1 for A+ Tutoring: JustCall -> Claude summary -> HubSpot -> Slack.

Polls the JustCall API for completed INBOUND calls on the monitored numbers
(config.yml), pulls each call's AI transcript, summarizes it with Claude,
logs a Call engagement (+ Note when there are action items) on the matching
HubSpot contact, and posts a daily digest to Slack.

Scheduled poller, not a webhook — run daily via GitHub Actions
(.github/workflows/call-agent.yml), same pattern as ops/scorecard.

V1 SCOPE (do not expand casually — see README):
  - Inbound calls only, one monitored number (the main A+ line).
  - JustCall native AI transcripts only; no third-party transcription.
    Recording-but-no-transcript calls are skipped and counted in the digest.
  - require_recording guardrail (CA two-party consent): calls with no
    recording are never transcribed/summarized by any means.
  - No auto-created HubSpot contacts; unmatched calls go to digest triage.

ENVIRONMENT VARIABLES (.env locally / repo secrets on Actions):
  JUSTCALL_API_KEY, JUSTCALL_API_SECRET   required
  HUBSPOT_API_KEY                          required (same token as ops/scorecard)
  ANTHROPIC_API_KEY                        required
  SLACK_BOT_TOKEN (+ slack.channel)        one of these two required
  SLACK_WEBHOOK_URL                        (bot token wins if both set)

FLAGS / MODES:
  --dry-run        real JustCall + Claude reads, print instead of writing to
                   HubSpot/Slack, state not persisted. Default for the first
                   deployment (workflow passes --dry-run until the repo
                   variable CALL_AGENT_LIVE=true).
  --no-digest      process calls but hold digest entries in state for a later
                   run to flush (for multiple runs per day).
  --since ISO      manual cursor override (UTC, e.g. 2026-07-09T00:00:00).
  CHECK_ONLY=true  CI smoke mode: confirm secrets/config wired, no reads/writes
                   (matches ops/scorecard convention).

JustCall API notes (verified against developer.justcall.io, 2026-07):
  - GET /v2.1/calls               list; call_direction=Incoming, from/to_datetime,
                                  justcall_number, page/per_page (max 100).
  - GET /v2.1/calls_ai/{id}       transcript lives HERE (fetch_transcription=true),
                                  NOT on the call object (moved Aug 2024).
  - Auth header is "key:secret" per official docs; some clients need Basic
    base64 — we fall back automatically on 401.
  - 429 backoff via X-Rate-Limit-* headers (no Retry-After documented).
"""

import os
import re
import sys
import json
import time
import base64
import logging
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

# Load repo-root .env first (fleet convention), then local override if present.
load_dotenv(REPO_ROOT / ".env")
load_dotenv(HERE / ".env", override=True)

JUSTCALL_API_KEY    = os.getenv("JUSTCALL_API_KEY", "")
JUSTCALL_API_SECRET = os.getenv("JUSTCALL_API_SECRET", "")
# Fleet has two names for the HubSpot private-app token: HUBSPOT_API_KEY
# (ops/scorecard, Actions secret) and HUBSPOT_PRIVATE_APP_TOKEN (marketing,
# local .env). Accept either.
HUBSPOT_API_KEY     = os.getenv("HUBSPOT_API_KEY", "") or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
SLACK_BOT_TOKEN     = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_WEBHOOK_URL   = os.getenv("SLACK_WEBHOOK_URL", "")
CHECK_ONLY          = os.getenv("CHECK_ONLY", "").lower() == "true"

JC_BASE = "https://api.justcall.io"
HS_BASE = "https://api.hubapi.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── Config ───────────────────────────────────────────────────────────────────

def load_config():
    with open(HERE / "config.yml") as f:
        cfg = yaml.safe_load(f)
    numbers = cfg["justcall"]["monitored_numbers"]
    if any("REPLACE_WITH" in str(n) for n in numbers):
        raise SystemExit(
            "config.yml: monitored_numbers still contains the placeholder — "
            "set the main A+ line in E.164 before running."
        )
    return cfg


# ─── State (idempotency cursor) ───────────────────────────────────────────────

def load_state(path):
    p = REPO_ROOT / path
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {"processed_call_ids": [], "last_run_utc": None, "pending_digest": []}


def save_state(state, path, max_ids):
    state["processed_call_ids"] = state["processed_call_ids"][-max_ids:]
    p = REPO_ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(p)  # atomic — a crash mid-write never corrupts the cursor
    log.info(f"State saved: {p.relative_to(REPO_ROOT)}")


# ─── JustCall API ─────────────────────────────────────────────────────────────

_jc_auth_mode = "plain"  # flips to "basic" if the documented plain form 401s


def _jc_headers():
    if _jc_auth_mode == "plain":
        auth = f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}"
    else:
        token = base64.b64encode(
            f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}".encode()
        ).decode()
        auth = f"Basic {token}"
    return {"Authorization": auth, "Accept": "application/json"}


def jc_get(path, params=None):
    """GET from JustCall with 401 auth-mode fallback + 429 backoff."""
    global _jc_auth_mode
    for attempt in range(4):
        r = requests.get(f"{JC_BASE}{path}", headers=_jc_headers(),
                         params=params or {}, timeout=30)
        if r.status_code == 401 and _jc_auth_mode == "plain":
            log.warning("JustCall 401 on plain key:secret auth — retrying as Basic base64")
            _jc_auth_mode = "basic"
            continue
        if r.status_code == 429:
            # No documented Retry-After; use burst-reset epoch if present.
            reset = r.headers.get("X-Rate-Limit-Burst-Reset") or r.headers.get("X-Rate-Limit-Reset")
            wait = max(float(reset) - time.time(), 5) if reset else 15 * (attempt + 1)
            wait = min(wait, 120)
            log.warning(f"JustCall rate limit (429), retrying in {wait:.0f}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def fetch_inbound_calls(cfg, since_utc):
    """
    Completed inbound calls on the monitored numbers since since_utc.
    Pages via page/per_page; dedup across pages/numbers by call id.
    """
    jc = cfg["justcall"]
    seen, calls = set(), []
    since_str = since_utc.strftime("%Y-%m-%d %H:%M:%S")
    for number in jc["monitored_numbers"]:
        log.info(f"Fetching inbound calls on {number} since {since_str} UTC...")
        page = 0  # pagination is 0-indexed (verified live 2026-07-10; docs don't say)
        while True:
            data = jc_get("/v2.1/calls", params={
                "call_direction": "Incoming",
                "justcall_number": re.sub(r"\D", "", str(number)),
                "from_datetime": since_str,
                "per_page": 100,
                "page": page,
                "sort": "datetime",
                "order": "asc",
            })
            batch = data.get("data", data if isinstance(data, list) else [])
            if not batch:
                break
            for c in batch:
                cid = c.get("id")
                if cid is not None and cid not in seen:
                    seen.add(cid)
                    calls.append(c)
            if len(batch) < 100:
                break
            page += 1
    log.info(f"  -> {len(calls)} inbound calls fetched")
    return calls


def fetch_transcript(call_id, pause_s):
    """
    Transcript via the AI endpoint (transcripts were removed from the Call API
    in Aug 2024). Returns plain-text transcript or None if unavailable.
    The per-turn key names aren't published in the docs, so parse defensively.
    """
    time.sleep(pause_s)  # stay under the 30/min burst limit
    try:
        data = jc_get(f"/v2.1/calls_ai/{call_id}", params={
            "platform": "justcall",
            "fetch_transcription": "true",
            "fetch_summary": "false",
            "fetch_ai_insights": "false",
            "fetch_action_items": "false",
            "fetch_smart_chapters": "false",
        })
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None  # no AI data for this call
        raise

    body = data.get("data", data)
    if isinstance(body, list):
        body = body[0] if body else {}
    raw = (body or {}).get("call_transcription")
    if not raw:
        return None

    if isinstance(raw, str):
        return raw.strip() or None

    # Documented as "an array of speaker IDs, sentences, and timestamps" —
    # exact keys unpublished, so try the plausible ones.
    lines = []
    for turn in raw:
        if isinstance(turn, str):
            lines.append(turn)
            continue
        if not isinstance(turn, dict):
            continue
        text = next((turn[k] for k in
                     ("sentence", "text", "content", "transcript", "message")
                     if turn.get(k)), None)
        if not text:
            continue
        speaker = next((turn[k] for k in
                        ("speaker", "speaker_name", "speaker_id", "speaker_label")
                        if turn.get(k) not in (None, "")), "?")
        lines.append(f"[{speaker}] {text}")
    return "\n".join(lines).strip() or None


def call_datetime_utc(call):
    """Best-effort UTC datetime of a JustCall call object."""
    d, t = call.get("call_date", ""), call.get("call_time", "")
    try:
        return datetime.strptime(f"{d} {t}"[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def call_type(call):
    """Lowercase call type ('answered'|'missed'|'voicemail'|'abandoned').
    Live API returns lowercase despite the docs' capitalized enum."""
    info = call.get("call_info") or {}
    return str(info.get("type") or call.get("type") or "").lower()


def has_recording(call):
    """Live API nests recording under call_info (docs imply top-level)."""
    info = call.get("call_info") or {}
    return bool(info.get("recording") or info.get("recording_child")
                or call.get("recording") or call.get("recording_child"))


# ─── Claude summarization ─────────────────────────────────────────────────────

CALLER_TYPES = ["parent", "school/charter contact", "tutor applicant", "vendor", "spam", "other"]
INTENTS = ["new inquiry", "scheduling", "billing", "complaint", "school partnership", "other"]
SENTIMENTS = ["positive", "neutral", "negative"]

# HubSpot enum option values (verified against the live portal 2026-07-10).
GRADE_OPTIONS = ["Pre-K", "TK", "Kindergarten", "1", "2", "3", "4", "5", "6",
                 "7", "8", "9", "10", "11", "12", "Graduated/College"]
MODALITY_OPTIONS = ["Online Tutoring", "In-Person Tutoring"]
SUBJECT_NEED_OPTIONS = ["English Language Arts", "Math", "Both", "Other"]
HEARD_OPTIONS = ["I'm a returning customer", "Yelp!", "Google Search",
                 "Facebook Group", "Instagram", "From my School", "From a Friend",
                 "From my Charter School", "Driving/Walking By",
                 "ChatGPT/Gemini/AI Search", "Next Door",
                 "I somehow found your card in my wallet", "LA Times", "KQED/NPR",
                 "On TV", "Through a youth organization (CFGC, FPY)",
                 "Royal Basketball School", "Other", "School Event"]

# Family-record fields: extraction key -> (HubSpot property, write policy).
#   log        prepend a dated entry, keep previous content (narrative fields)
#   overwrite  facts that legitimately change over time (grade, school, ...)
#   fill_only  write only when currently blank (names, attribution)
#   correction write only on an explicit correction stated in the call
# ⚠ Portal naming traps (verified): `student_last_name` HOLDS THE STUDENT'S
#   FIRST/FULL NAME (label "Student FIRST Name"); the actual last name lives in
#   `student_last_name_if_diff_from_parent`. `school` is a FB-Ads field — the
#   student's school is `student_school`.
RECORD_FIELD_MAP = {
    "whats_going_on":        ("parent_concerns_what_can_we_do_to_help_", "log"),
    "what_we_can_do_to_help": ("student_additional_information", "log"),
    "student_first_name":    ("student_last_name", "fill_only"),
    "student_last_name":     ("student_last_name_if_diff_from_parent", "fill_only"),
    "grade_level":           ("what_is_your_child_s_current_grade_level_", "overwrite"),
    "student_school":        ("student_school", "overwrite"),
    "subject_need":          ("subject_need", "overwrite"),
    "online_or_in_person":   ("online_or_in_person", "overwrite"),
    "how_did_you_hear":      ("how_did_you_hear_about_us_", "fill_only"),
    "referral_name":         ("referral_name", "fill_only"),
    "email_correction":      ("email", "correction"),
    "phone_correction":      ("phone", "correction"),
}

# Properties fetched with the contact so Claude can compare call vs record.
KEY_PROPERTIES = sorted({prop for prop, _ in RECORD_FIELD_MAP.values()}
                        | {"firstname", "lastname", "email", "phone", "mobilephone"})

SUMMARY_PROMPT = """You are processing an inbound phone call to A+ Tutoring, \
a K-12 tutoring company in California (families/parents, partner schools and \
charter schools, tutor applicants). Your output updates the family's CRM \
record, creates follow-up tasks, and feeds a daily ops digest.

1. Summarize the call: 3-5 sentences covering who called, why, and outcome.
2. Classify the caller and intent, note sentiment.
3. List action items — things A+ STAFF must do after this call (not things the
   family will do). Include an owner_hint only when a specific A+ person was
   named as responsible. Set follow_up_needed accordingly.
4. Propose family-record updates in record_updates, comparing the call against
   the CURRENT RECORD below (all-null record = caller not in CRM; leave
   record_updates fields null in that case):
   - whats_going_on / what_we_can_do_to_help: a concise NEW log entry (1-3
     sentences each) capturing what this call revealed — the situation, and
     what A+ can do. Null if the call adds nothing meaningful (e.g. a vendor
     call). Write the entry text only; the system adds the date.
   - Factual fields (student name, grade, school, subject, modality): fill or
     correct ONLY from information clearly stated in the call. If the record
     already names a DIFFERENT student than the one discussed, leave the
     factual fields null and put the details in the log entries instead —
     never overwrite one sibling's data with another's.
   - how_did_you_hear / referral_name: only if the caller said how they found
     A+ or who referred them. When a school counselor/teacher/staff member
     referred the family, use "From my School" — "From my Charter School" is
     ONLY when the family is explicitly a charter-school (instructional funds)
     family. When unsure between the two, use "From my School".
   - email_correction / phone_correction: ONLY if the call explicitly
     established that the contact info on file is wrong AND a replacement was
     CONFIRMED WORKING on the call. If a proposed replacement also failed
     (e.g. it bounced too), leave null and cover it in an action item instead.
     Never infer.
   Never invent values. Null means "no update".

CURRENT RECORD (HubSpot contact):
{record_json}

Transcript{truncated_note}:
---
{transcript}
---"""

_NULLABLE_STR = {"anyOf": [{"type": "string"}, {"type": "null"}]}


def _nullable_enum(options):
    return {"anyOf": [{"type": "string", "enum": options}, {"type": "null"}]}

# Strict schema enforced via output_config.format (structured outputs) —
# assistant prefill is not supported on the 4.6+ model family.
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "caller_type": {"type": "string", "enum": CALLER_TYPES},
        "intent": {"type": "string", "enum": INTENTS},
        "sentiment": {"type": "string", "enum": SENTIMENTS},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "owner_hint": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["item", "owner_hint"],
                "additionalProperties": False,
            },
        },
        "follow_up_needed": {"type": "boolean"},
        "student_or_school_names_mentioned": {
            "type": "array",
            "items": {"type": "string"},
        },
        "record_updates": {
            "type": "object",
            "properties": {
                "whats_going_on": _NULLABLE_STR,
                "what_we_can_do_to_help": _NULLABLE_STR,
                "student_first_name": _NULLABLE_STR,
                "student_last_name": _NULLABLE_STR,
                "grade_level": _nullable_enum(GRADE_OPTIONS),
                "student_school": _NULLABLE_STR,
                "subject_need": _nullable_enum(SUBJECT_NEED_OPTIONS),
                "online_or_in_person": _nullable_enum(MODALITY_OPTIONS),
                "how_did_you_hear": _nullable_enum(HEARD_OPTIONS),
                "referral_name": _NULLABLE_STR,
                "email_correction": _NULLABLE_STR,
                "phone_correction": _NULLABLE_STR,
            },
            "required": list(RECORD_FIELD_MAP.keys()),
            "additionalProperties": False,
        },
    },
    "required": ["summary", "caller_type", "intent", "sentiment", "action_items",
                 "follow_up_needed", "student_or_school_names_mentioned",
                 "record_updates"],
    "additionalProperties": False,
}


def summarize_call(transcript, cfg, contact=None):
    """Claude summary + record-update proposal as validated dict.
    contact: matched HubSpot contact (or None) — current values feed the prompt."""
    import anthropic

    ccfg = cfg["claude"]
    max_chars = ccfg["max_transcript_chars"]
    truncated = len(transcript) > max_chars
    if truncated:
        transcript = transcript[:max_chars]
        log.info(f"  transcript truncated to {max_chars} chars (cost guard)")

    # Current record, keyed by extraction field so Claude compares like-for-like.
    props = (contact or {}).get("properties", {})
    record = {"parent_name": f"{props.get('firstname') or ''} {props.get('lastname') or ''}".strip() or None,
              "email_on_file": props.get("email"),
              "phone_on_file": props.get("phone")}
    for field, (hs_prop, _) in RECORD_FIELD_MAP.items():
        record[field] = props.get(hs_prop) or None

    prompt = SUMMARY_PROMPT.format(
        record_json=json.dumps(record, indent=2),
        truncated_note=" (truncated)" if truncated else "",
        transcript=transcript,
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=3)
    resp = client.messages.create(
        model=ccfg["model"],
        max_tokens=ccfg["max_tokens"],
        output_config={"format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise ValueError("Claude refused to summarize this transcript")
    text = next(b.text for b in resp.content if b.type == "text")
    summary = _validate_summary(json.loads(text))  # belt-and-braces re-validation
    summary["_truncated"] = truncated
    return summary


def _validate_summary(d):
    """Enforce the strict schema; coerce out-of-enum values to their fallback."""
    if not isinstance(d, dict):
        raise ValueError("summary is not a JSON object")
    for key in ("summary", "caller_type", "intent", "sentiment",
                "action_items", "follow_up_needed", "student_or_school_names_mentioned"):
        if key not in d:
            raise ValueError(f"missing key: {key}")
    if not isinstance(d["summary"], str) or not d["summary"].strip():
        raise ValueError("summary must be a non-empty string")
    if d["caller_type"] not in CALLER_TYPES:
        d["caller_type"] = "other"
    if d["intent"] not in INTENTS:
        d["intent"] = "other"
    if d["sentiment"] not in SENTIMENTS:
        d["sentiment"] = "neutral"
    if not isinstance(d["action_items"], list):
        raise ValueError("action_items must be an array")
    items = []
    for it in d["action_items"]:
        if isinstance(it, str):
            items.append({"item": it, "owner_hint": None})
        elif isinstance(it, dict) and it.get("item"):
            items.append({"item": str(it["item"]), "owner_hint": it.get("owner_hint") or None})
    d["action_items"] = items
    d["follow_up_needed"] = bool(d["follow_up_needed"])
    if not isinstance(d["student_or_school_names_mentioned"], list):
        d["student_or_school_names_mentioned"] = []
    d["student_or_school_names_mentioned"] = [str(x) for x in d["student_or_school_names_mentioned"]]

    ru = d.get("record_updates") or {}
    clean = {}
    enum_bounds = {"grade_level": GRADE_OPTIONS, "subject_need": SUBJECT_NEED_OPTIONS,
                   "online_or_in_person": MODALITY_OPTIONS, "how_did_you_hear": HEARD_OPTIONS}
    for field in RECORD_FIELD_MAP:
        val = ru.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            clean[field] = None
            continue
        val = str(val).strip()
        if field in enum_bounds and val not in enum_bounds[field]:
            log.warning(f"  record_updates.{field}: '{val}' not a valid option — dropped")
            val = None
        clean[field] = val
    d["record_updates"] = clean
    return d


# ─── Coaching (rubric scoring) ────────────────────────────────────────────────

RUBRIC_DIMENSIONS = ["U1", "U2", "U3", "U4", "U5", "S1", "S2", "S3", "S4", "V1", "V2"]

COACHING_PROMPT = """You are a supportive call coach for A+ Tutoring, reviewing \
an inbound call answered by {agent_name}. Score the call against the rubric \
below. Apply the S-dimensions only when the call is a new inquiry or school \
partnership; the V-dimensions only for scheduling/billing/complaint calls; \
universal dimensions always. Use null for N/A. Anchor every observation to a \
short verbatim quote from the transcript. Tone: coach, not critic — assume \
good intent.

RUBRIC:
{rubric}

Call context: caller_type={caller_type}, intent={intent}, sentiment={sentiment}

Transcript:
---
{transcript}
---"""

_SCORE = {"anyOf": [{"type": "integer", "enum": [1, 2, 3, 4, 5]}, {"type": "null"}]}

COACHING_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "enum": RUBRIC_DIMENSIONS},
                    "score": _SCORE,
                    "note": {"type": "string"},
                },
                "required": ["dimension", "score", "note"],
                "additionalProperties": False,
            },
        },
        "went_well": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"quote": {"type": "string"}, "comment": {"type": "string"}},
                "required": ["quote", "comment"],
                "additionalProperties": False,
            },
        },
        "coaching_moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "why": {"type": "string"},
                    "try_instead": {"type": "string"},
                },
                "required": ["quote", "why", "try_instead"],
                "additionalProperties": False,
            },
        },
        "missed_opportunities": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["scores", "went_well", "coaching_moments", "missed_opportunities"],
    "additionalProperties": False,
}

_rubric_cache = None


def load_rubric(cfg):
    global _rubric_cache
    if _rubric_cache is None:
        with open(REPO_ROOT / cfg["coaching"]["rubric_path"]) as f:
            _rubric_cache = f.read()
    return _rubric_cache


def score_call(transcript, summary, agent_name, cfg):
    """Rubric score for coaching. Returns dict with scores + overall, or raises."""
    import anthropic

    ccfg = cfg["claude"]
    prompt = COACHING_PROMPT.format(
        agent_name=agent_name or "the team member",
        rubric=load_rubric(cfg),
        caller_type=summary["caller_type"],
        intent=summary["intent"],
        sentiment=summary["sentiment"],
        transcript=transcript[:ccfg["max_transcript_chars"]],
    )
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=3)
    resp = client.messages.create(
        model=ccfg["model"],
        max_tokens=ccfg["max_tokens"],
        output_config={"format": {"type": "json_schema", "schema": COACHING_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise ValueError("Claude refused to score this transcript")
    card = json.loads(next(b.text for b in resp.content if b.type == "text"))
    scored = [s["score"] for s in card["scores"] if s["score"] is not None]
    card["overall"] = round(sum(scored) / len(scored), 1) if scored else None
    return card


RUBRIC_DIM_LABELS = {
    "U1": "Opening & professionalism", "U2": "Listening & empathy",
    "U3": "Call control & structure", "U4": "Information capture & verification",
    "U5": "Next steps & ownership",
    "S1": "Discovery depth", "S2": "Program fit & value",
    "S3": "Pricing confidence", "S4": "Advance (the close)",
    "V1": "Ownership & recovery", "V2": "Confirmation of resolution",
}


def build_coaching_note(agent_name, time_pt, summary, card):
    """Rubric evaluation as an HTML Note body for the HubSpot contact."""
    import html
    esc = html.escape
    rows = []
    for s in card["scores"]:
        if s["score"] is None:
            continue
        label = RUBRIC_DIM_LABELS.get(s["dimension"], s["dimension"])
        rows.append(f"<li><b>{s['dimension']} {label}: {s['score']}/5</b>"
                    f" — {esc(s['note'])}</li>")
    parts = [
        f"<p><b>[Call Agent] Call quality evaluation — {esc(agent_name or 'unknown')}"
        f" · {esc(time_pt)} · overall {card['overall']}/5</b><br>"
        f"Rubric v1 (ops/call_agent/rubric.md) · intent: {esc(summary['intent'])}"
        f" · sentiment: {esc(summary['sentiment'])}</p>",
        "<p><b>Scores</b></p><ul>" + "".join(rows) + "</ul>",
    ]
    if card["went_well"]:
        parts.append("<p><b>What went well</b></p><ul>" + "".join(
            f"<li>“{esc(w['quote'])}” — {esc(w['comment'])}</li>"
            for w in card["went_well"]) + "</ul>")
    if card["coaching_moments"]:
        parts.append("<p><b>Coaching moments</b></p><ul>" + "".join(
            f"<li>“{esc(m['quote'])}” — {esc(m['why'])}<br>"
            f"<i>Try:</i> “{esc(m['try_instead'])}”</li>"
            for m in card["coaching_moments"]) + "</ul>")
    if card["missed_opportunities"]:
        parts.append("<p><b>Missed opportunities</b></p><ul>" + "".join(
            f"<li>{esc(m)}</li>" for m in card["missed_opportunities"]) + "</ul>")
    return "".join(parts)


def create_coaching_note(contact_id, note_html, when_utc):
    return hs_post("crm/v3/objects/notes", {
        "properties": {
            "hs_timestamp": str(int(when_utc.timestamp() * 1000)),
            "hs_note_body": note_html[:65000],
        },
        "associations": [{
            "to": {"id": contact_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}],
        }],
    }).get("id")


def build_coaching_card(agent_name, contact_label, number, time_pt, summary, card):
    who = contact_label or f"`{number}`"
    by_dim = {s["dimension"]: s for s in card["scores"]}
    score_bits = [f"{d} {by_dim[d]['score']}" for d in RUBRIC_DIMENSIONS
                  if d in by_dim and by_dim[d]["score"] is not None]
    lines = [
        f":studio_microphone: *Coaching — {agent_name or 'unknown'}* · {time_pt} · "
        f"{who} ({summary['intent']})",
        f"Overall *{card['overall']}/5*  ·  " + " · ".join(score_bits),
    ]
    for w in card["went_well"][:2]:
        lines.append(f":white_check_mark: \"{w['quote']}\" — {w['comment']}")
    for m in card["coaching_moments"][:2]:
        lines.append(f":bulb: \"{m['quote']}\" — {m['why']}\n    _Try:_ \"{m['try_instead']}\"")
    if card["missed_opportunities"]:
        lines.append(":mag: Missed: " + "; ".join(card["missed_opportunities"][:4]))
    return "\n".join(lines)


# ─── HubSpot ──────────────────────────────────────────────────────────────────

def _hs_request(method, endpoint, payload=None):
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(4):
        r = requests.request(method, f"{HS_BASE}/{endpoint}", headers=headers,
                             json=payload, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", 5 * (attempt + 1)))
            log.warning(f"HubSpot rate limit (429), retrying in {wait:.0f}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def hs_post(endpoint, payload):
    return _hs_request("POST", endpoint, payload)


def hs_patch(endpoint, payload):
    return _hs_request("PATCH", endpoint, payload)


def phone_variants(number):
    """
    E.164 + common US formatting variants for HubSpot phone matching.
    Returns (e164, [variants]).
    """
    digits = re.sub(r"\D", "", str(number or ""))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        e164 = f"+{re.sub(r'[^0-9]', '', str(number))}" if digits else ""
        return e164, [v for v in {str(number), e164} if v]
    a, b, c = digits[:3], digits[3:6], digits[6:]
    e164 = f"+1{digits}"
    variants = [e164, digits, f"1{digits}",
                f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}", f"+1 {a}-{b}-{c}"]
    return e164, variants


def find_contact_by_phone(caller_number):
    """
    HubSpot contact by phone. Tier 1: exact IN-match on phone/mobilephone
    variants. Tier 2: CONTAINS_TOKEN on the wildcarded 10-digit number.
    Returns contact dict or None.
    """
    e164, variants = phone_variants(caller_number)
    if not variants:
        return None
    props = KEY_PROPERTIES

    payload = {
        "filterGroups": [
            {"filters": [{"propertyName": "phone", "operator": "IN", "values": variants}]},
            {"filters": [{"propertyName": "mobilephone", "operator": "IN", "values": variants}]},
        ],
        "properties": props,
        "limit": 5,
    }
    res = hs_post("crm/v3/objects/contacts/search", payload)
    if res.get("total", 0) > 0:
        return res["results"][0]

    digits = re.sub(r"\D", "", e164)[-10:]
    if len(digits) == 10:
        payload = {
            "filterGroups": [
                {"filters": [{"propertyName": "phone", "operator": "CONTAINS_TOKEN", "value": f"*{digits}"}]},
                {"filters": [{"propertyName": "mobilephone", "operator": "CONTAINS_TOKEN", "value": f"*{digits}"}]},
            ],
            "properties": props,
            "limit": 5,
        }
        res = hs_post("crm/v3/objects/contacts/search", payload)
        if res.get("total", 0) > 0:
            return res["results"][0]
    return None


def log_call_to_hubspot(contact_id, call, summary, transcript_status):
    """Create a Call engagement on the contact; Note when there are action items."""
    when = call_datetime_utc(call) or datetime.now(timezone.utc)
    ts_ms = str(int(when.timestamp() * 1000))
    duration = (call.get("call_duration") or {}).get("total_duration") or 0

    body_lines = [
        f"[Call Agent] Inbound call summary ({summary['caller_type']} / {summary['intent']} / {summary['sentiment']})",
        "",
        summary["summary"],
    ]
    if summary["student_or_school_names_mentioned"]:
        body_lines += ["", "Mentioned: " + ", ".join(summary["student_or_school_names_mentioned"])]
    if summary.get("_truncated"):
        body_lines += ["", "(Transcript truncated before summarization — cost guard.)"]
    if summary["follow_up_needed"]:
        body_lines += ["", "⚠ Follow-up needed."]

    call_obj = hs_post("crm/v3/objects/calls", {
        "properties": {
            "hs_timestamp": ts_ms,
            "hs_call_title": f"Inbound call — {summary['intent']} ({summary['caller_type']})",
            "hs_call_body": "\n".join(body_lines),
            "hs_call_direction": "INBOUND",
            "hs_call_status": "COMPLETED",
            "hs_call_from_number": call.get("contact_number", ""),
            "hs_call_to_number": call.get("justcall_number", ""),
            "hs_call_duration": str(int(duration) * 1000),  # HubSpot wants ms
        },
        "associations": [{
            "to": {"id": contact_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 194}],
        }],
    })

    return call_obj.get("id")


def next_business_day(dt, n=1):
    """dt + n business days (skips Sat/Sun), at 5 PM PT expressed in UTC."""
    d = dt
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def apply_record_updates(contact, updates, call_date_pt):
    """
    Write proposed family-record updates per the per-field policy.
    Returns (applied, skipped): applied = [(label, old, new)],
    skipped = [(label, current, proposed, reason)] — surfaced in the digest.
    """
    props = contact.get("properties", {})
    patch, applied, skipped = {}, [], []

    for field, value in updates.items():
        if value is None:
            continue
        hs_prop, policy = RECORD_FIELD_MAP[field]
        current = (props.get(hs_prop) or "").strip()

        if policy == "log":
            # Dated entry prepended; previous entries preserved (Roman's rule:
            # "treat it like a log — log today's date and the update").
            entry = f"[{call_date_pt} call] {value}"
            patch[hs_prop] = f"{entry}\n\n{current}" if current else entry
            applied.append((field, "(appended to log)", value))
        elif policy == "overwrite":
            if current == value:
                continue
            patch[hs_prop] = value
            applied.append((field, current or "(blank)", value))
        elif policy == "fill_only":
            if current:
                if current.lower() != value.lower():
                    skipped.append((field, current, value, "existing value kept (fill-only)"))
                continue
            patch[hs_prop] = value
            applied.append((field, "(blank)", value))
        elif policy == "correction":
            if current.lower() == value.lower():
                continue
            patch[hs_prop] = value
            applied.append((field, current or "(blank)", value))

    if patch:
        hs_patch(f"crm/v3/objects/contacts/{contact['id']}", {"properties": patch})
    return applied, skipped


def _resolve_owner(owner_hint, cfg):
    """owner_hint ('Roman', 'have Paola call...') -> HubSpot owner id."""
    owners = cfg["hubspot"]["owners"]
    hint = (owner_hint or "").lower()
    for name, oid in owners.items():
        if name in hint:
            return oid
    return owners[cfg["hubspot"]["default_task_owner"]]


def create_task(contact_id, subject, body, owner_id, due_utc, priority="MEDIUM"):
    """HubSpot Task on the contact (shows in the owner's tasks queue)."""
    payload = {
        "properties": {
            "hs_timestamp": str(int(due_utc.timestamp() * 1000)),  # due date
            "hs_task_subject": subject,
            "hs_task_body": body,
            "hs_task_status": "NOT_STARTED",
            "hs_task_priority": priority,
            "hs_task_type": "TODO",
            "hubspot_owner_id": str(owner_id),
        },
    }
    if contact_id:
        payload["associations"] = [{
            "to": {"id": contact_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}],
        }]
    return hs_post("crm/v3/objects/tasks", payload).get("id")


def create_checkin_ticket(contact_id, contact_label, number, summary, cfg, now_utc):
    """
    Negative-sentiment/complaint flow: HIGH-priority ticket in the Support
    Pipeline + companion check-in task due in N business days (tickets have no
    native due date). Returns the ticket id.
    """
    tcfg = cfg["hubspot"]["ticket"]
    owner_id = cfg["hubspot"]["owners"][tcfg["owner"]]
    who = contact_label or number
    content = (f"[Call Agent] Negative-sentiment/complaint call from {who} ({number}).\n\n"
               f"{summary['summary']}\n\n"
               f"Intent: {summary['intent']} · Sentiment: {summary['sentiment']}\n"
               f"Check in with the family within {tcfg['check_in_business_days']} business days.")
    payload = {
        "properties": {
            "subject": f"Check in with {who} — call {now_utc.strftime('%Y-%m-%d')}",
            "content": content,
            "hs_pipeline": tcfg["pipeline"],
            "hs_pipeline_stage": tcfg["stage"],
            "hs_ticket_priority": tcfg["priority"],
            "source_type": "PHONE",
            "hubspot_owner_id": str(owner_id),
        },
    }
    if contact_id:
        payload["associations"] = [{
            "to": {"id": contact_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 16}],
        }]
    ticket_id = hs_post("crm/v3/objects/tickets", payload).get("id")
    create_task(
        contact_id,
        f"Check in with {who} (ticket follow-up)",
        f"Family check-in after a negative-sentiment call. Ticket {ticket_id}.\n\n{summary['summary']}",
        owner_id,
        next_business_day(now_utc, tcfg["check_in_business_days"]),
        priority="HIGH",
    )
    return ticket_id


# ─── Slack digest ─────────────────────────────────────────────────────────────

def fmt_time_pt(call):
    """Call time as short PT string (fleet reports in PT)."""
    dt = call_datetime_utc(call)
    if not dt:
        return "?"
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%-I:%M %p")
    except Exception:
        return dt.strftime("%H:%M UTC")


def build_digest(entries, skipped, failures, run_date_pt):
    """
    entries: [{call, summary, matched, contact_label, time_pt, number}]
    skipped: [{number, time_pt, reason}]   failures: [{call_id, number, error}]
    """
    matched = [e for e in entries if e["matched"]]
    unmatched = [e for e in entries if not e["matched"]]
    n_no_rec = sum(1 for s in skipped if s["reason"] == "no recording")
    n_no_tr = sum(1 for s in skipped if s["reason"] == "no transcript")
    n_hangup = sum(1 for s in skipped if s["reason"] == "hang-up")
    n_tasks = sum(len(e.get("tasks_created", [])) for e in entries)
    n_updates = sum(len(e.get("record_applied", [])) for e in entries)

    lines = [
        f":telephone_receiver: *Call Agent digest — {run_date_pt}*",
        f"Processed *{len(entries)}* call{'s' if len(entries) != 1 else ''} "
        f"(matched {len(matched)}, unmatched {len(unmatched)}) · "
        f"Hang-ups: {n_hangup} · Skipped: {n_no_rec} no recording, {n_no_tr} no transcript · "
        f"Tasks created: {n_tasks} · Record updates: {n_updates} · "
        f"Failures: {len(failures)}",
    ]

    def one_liner(e):
        s = e["summary"]
        flags = ""
        if s["sentiment"] == "negative":
            flags += " :red_circle:"
        if s["follow_up_needed"]:
            flags += " :bangbang: follow-up"
        if e.get("ticket_id"):
            flags += f" :ticket: {e['ticket_id']}"
        if e.get("tasks_created"):
            flags += f" ({len(e['tasks_created'])} task{'s' if len(e['tasks_created']) != 1 else ''})"
        first = s["summary"].split(". ")[0].rstrip(".") + "."
        who = e["contact_label"] or e["number"]
        return f"• {e['time_pt']} — {who} ({s['intent']}){flags} — {first}"

    attention = [e for e in entries
                 if e["summary"]["follow_up_needed"] or e["summary"]["sentiment"] == "negative"]
    if attention:
        lines += ["", "*Needs attention*"]
        lines += [one_liner(e) for e in attention]

    by_type = {}
    for e in entries:
        by_type.setdefault(e["summary"]["caller_type"], []).append(e)
    for ctype in CALLER_TYPES:
        group = by_type.get(ctype)
        if not group:
            continue
        lines += ["", f"*{ctype.capitalize()}* ({len(group)})"]
        lines += [one_liner(e) for e in group]

    updated = [e for e in entries if e.get("record_applied")]
    if updated:
        lines += ["", "*Family-record updates applied*"]
        for e in updated:
            who = e["contact_label"] or e["number"]
            for field, old, new in e["record_applied"]:
                shown = new if len(str(new)) <= 80 else str(new)[:77] + "..."
                lines.append(f"• {who}: {field} — {old} → {shown}")

    review = [e for e in entries if e.get("record_skipped")]
    if review:
        lines += ["", "*Proposed but NOT applied (existing value kept — review)*"]
        for e in review:
            who = e["contact_label"] or e["number"]
            for field, current, proposed, _ in e["record_skipped"]:
                lines.append(f"• {who}: {field} — record has '{current}', call says '{proposed}'")

    if unmatched:
        lines += ["", "*Unmatched calls — human triage (no HubSpot contact; not auto-created)*"]
        for e in unmatched:
            first = e["summary"]["summary"].split(". ")[0].rstrip(".") + "."
            lines.append(f"• `{e['number']}` @ {e['time_pt']} — {first}")

    listed_skips = [s for s in skipped if s["reason"] != "hang-up"]  # hang-ups are header-count only
    if listed_skips:
        lines += ["", "*Skipped*"]
        for s in listed_skips:
            lines.append(f"• `{s['number']}` @ {s['time_pt']} — {s['reason']}")

    if failures:
        lines += ["", "*Failures (see run logs)*"]
        for f in failures:
            lines.append(f"• call {f['call_id']} (`{f['number']}`) — {f['error']}")

    return "\n".join(lines)


def post_to_slack(text, channel):
    if SLACK_BOT_TOKEN:
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                     "Content-Type": "application/json; charset=utf-8"},
            json={"channel": channel, "text": text, "unfurl_links": False},
            timeout=15,
        )
        r.raise_for_status()
        if not r.json().get("ok"):
            raise RuntimeError(f"Slack API error: {r.json().get('error')}")
        log.info(f"Digest posted to {channel} (bot token)")
    elif SLACK_WEBHOOK_URL:
        r = requests.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=15)
        r.raise_for_status()
        log.info("Digest posted (webhook)")
    else:
        raise RuntimeError("Neither SLACK_BOT_TOKEN nor SLACK_WEBHOOK_URL is set")


# ─── Main ─────────────────────────────────────────────────────────────────────

def process_call(call, cfg, dry_run, now_utc):
    """One call end-to-end. Returns ('entry'|'skipped', payload)."""
    cid = call.get("id")
    number = call.get("contact_number", "?")
    time_pt = fmt_time_pt(call)
    jc = cfg["justcall"]

    # Consent guardrail — never transcribe/summarize an unrecorded call.
    if jc["require_recording"] and not has_recording(call):
        log.info(f"  call {cid}: no recording — skipped (consent guardrail)")
        return "skipped", {"number": number, "time_pt": time_pt, "reason": "no recording"}

    transcript = fetch_transcript(cid, jc["ai_fetch_pause_seconds"])
    if not transcript:
        log.info(f"  call {cid}: recording but no transcript — skipped")
        return "skipped", {"number": number, "time_pt": time_pt, "reason": "no transcript"}

    # Hang-up filter: IVR fragments get no Claude call and no HubSpot writes.
    if len(transcript) < jc["min_transcript_chars"]:
        log.info(f"  call {cid}: {len(transcript)}-char transcript — hang-up, skipped")
        return "skipped", {"number": number, "time_pt": time_pt, "reason": "hang-up"}

    # Match BEFORE summarizing so the current record feeds the prompt.
    contact = find_contact_by_phone(number)
    contact_label = None
    if contact:
        p = contact.get("properties", {})
        contact_label = f"{p.get('firstname', '')} {p.get('lastname', '')}".strip() or p.get("email")

    log.info(f"  call {cid}: summarizing ({len(transcript)} chars, "
             f"{'matched: ' + contact_label if contact else 'unmatched'})...")
    summary = summarize_call(transcript, cfg, contact)

    call_date_pt = now_utc.strftime("%Y-%m-%d")
    is_negative = (summary["sentiment"] == "negative" or summary["intent"] == "complaint")
    applied, skipped_updates, tasks_created, ticket_id = [], [], [], None

    if dry_run:
        if contact:
            log.info(f"  call {cid}: DRY RUN — would log call to contact {contact['id']} "
                     f"({contact_label}) and apply record updates")
        for it in summary["action_items"]:
            oid = _resolve_owner(it["owner_hint"], cfg)
            log.info(f"  call {cid}: DRY RUN — would create Task '{it['item']}' (owner {oid})")
        if is_negative:
            log.info(f"  call {cid}: DRY RUN — would create HIGH ticket + check-in task "
                     f"+ alert to {cfg['slack']['alert_channel'] or '(alert_channel unset)'}")
        log.info(f"  call {cid} summary:\n{json.dumps(summary, indent=2)}")
    else:
        if contact:
            log_call_to_hubspot(contact["id"], call, summary, transcript)
            applied, skipped_updates = apply_record_updates(
                contact, summary["record_updates"], call_date_pt)
            if applied:
                log.info(f"  call {cid}: record updated — "
                         + "; ".join(f"{f}: {n!r}" for f, _, n in applied))
        else:
            log.info(f"  call {cid}: no HubSpot contact for {number} — digest triage "
                     f"(auto-create disabled in v1)")

        # Action items -> HubSpot Tasks (owner from hint, default Paola).
        due = next_business_day(now_utc, cfg["hubspot"]["task_due_business_days"])
        for it in summary["action_items"]:
            oid = _resolve_owner(it["owner_hint"], cfg)
            task_id = create_task(
                contact["id"] if contact else None,
                it["item"][:250],
                f"[Call Agent] From inbound call {call_date_pt} ({contact_label or number}).\n\n"
                f"{summary['summary']}",
                oid, due,
                priority="HIGH" if is_negative else "MEDIUM",
            )
            tasks_created.append((it["item"], oid, task_id))
            log.info(f"  call {cid}: Task {task_id} created (owner {oid})")

        if is_negative:
            ticket_id = create_checkin_ticket(
                contact["id"] if contact else None,
                contact_label, number, summary, cfg, now_utc)
            log.info(f"  call {cid}: check-in ticket {ticket_id} created")

    # Coaching: rubric score, posted to the private coaching channel.
    # Never allowed to fail the call — it's an internal-quality side channel.
    coached = False
    if cfg["coaching"]["enabled"]:
        try:
            agent_name = call.get("agent_name") or (call.get("agent") or {}).get("name")
            card = score_call(transcript, summary, agent_name, cfg)
            coaching_text = build_coaching_card(
                agent_name, contact_label, number, time_pt, summary, card)
            coach_channel = cfg["coaching"]["channel"] or cfg["slack"]["alert_channel"]
            if dry_run or not coach_channel:
                log.info(f"  call {cid}: coaching card"
                         f"{' (DRY RUN)' if dry_run else ' (coaching channel unset)'}:\n"
                         f"{coaching_text}")
            else:
                post_to_slack(coaching_text, coach_channel)
            # Full evaluation as a Note on the contact (team-visible in HubSpot;
            # toggle via coaching.note_to_contact).
            if cfg["coaching"]["note_to_contact"] and contact:
                if dry_run:
                    log.info(f"  call {cid}: DRY RUN — would attach coaching Note "
                             f"to contact {contact['id']}")
                else:
                    note_id = create_coaching_note(
                        contact["id"],
                        build_coaching_note(agent_name, time_pt, summary, card),
                        now_utc)
                    log.info(f"  call {cid}: coaching Note {note_id} on contact {contact['id']}")
            coached = True
        except Exception as e:
            log.warning(f"  call {cid}: coaching scoring failed (call still processed): {e}")

    # Immediate private alert for negative calls (dry-run prints it instead).
    if is_negative:
        alert = build_alert(contact_label, number, time_pt, summary, ticket_id)
        alert_channel = cfg["slack"]["alert_channel"]
        if dry_run or not alert_channel:
            log.info(f"  call {cid}: negative-sentiment alert"
                     f"{' (DRY RUN)' if dry_run else ' (alert_channel unset)'}:\n{alert}")
        else:
            try:
                post_to_slack(alert, alert_channel)
            except Exception as e:
                log.warning(f"  call {cid}: alert post failed: {e}")

    return "entry", {
        "call_id": cid,
        "number": number,
        "time_pt": time_pt,
        "matched": contact is not None,
        "contact_label": contact_label,
        "summary": summary,
        "record_applied": [(f, o, n) for f, o, n in applied],
        "record_skipped": [(f, c, p, r) for f, c, p, r in skipped_updates],
        "tasks_created": [(item, oid) for item, oid, _ in tasks_created],
        "ticket_id": ticket_id,
        "coached": coached,
    }


def build_alert(contact_label, number, time_pt, summary, ticket_id):
    who = contact_label or f"`{number}`"
    lines = [
        f":rotating_light: *Negative call — {who}* ({time_pt})",
        summary["summary"],
        f"Intent: {summary['intent']} · Sentiment: {summary['sentiment']}",
    ]
    if summary["action_items"]:
        lines.append("Action items: " + "; ".join(i["item"] for i in summary["action_items"]))
    if ticket_id:
        lines.append(f"Check-in ticket created: {ticket_id} (due in 2 business days)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Call Agent v1 (JustCall -> HubSpot + Slack)")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + summarize, print instead of writing to HubSpot/Slack")
    ap.add_argument("--no-digest", action="store_true",
                    help="hold digest entries in state; a later run flushes them")
    ap.add_argument("--since", default=None,
                    help="manual cursor override, UTC ISO (e.g. 2026-07-09T00:00:00)")
    args = ap.parse_args()

    # CI smoke mode (scorecard convention): secrets wired? then exit.
    if CHECK_ONLY:
        missing = [k for k, v in {
            "JUSTCALL_API_KEY": JUSTCALL_API_KEY,
            "JUSTCALL_API_SECRET": JUSTCALL_API_SECRET,
            "HUBSPOT_API_KEY": HUBSPOT_API_KEY,
            "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        }.items() if not v]
        if not (SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL):
            missing.append("SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL")
        if missing:
            raise SystemExit(f"CHECK FAILED — missing: {', '.join(missing)}")
        load_config()
        print("CHECK OK: secrets present, config valid; skipping all reads/writes.")
        return

    for k, v in {"JUSTCALL_API_KEY": JUSTCALL_API_KEY,
                 "JUSTCALL_API_SECRET": JUSTCALL_API_SECRET,
                 "HUBSPOT_API_KEY": HUBSPOT_API_KEY,
                 "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY}.items():
        if not v:
            raise EnvironmentError(f"{k} not set")

    cfg = load_config()
    if args.dry_run:
        log.info("DRY RUN MODE — no HubSpot/Slack writes, state not persisted")

    state = load_state(cfg["state"]["path"])
    processed_ids = set(state["processed_call_ids"])
    now_utc = datetime.now(timezone.utc)
    jc = cfg["justcall"]

    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    elif state["last_run_utc"]:
        since = (datetime.fromisoformat(state["last_run_utc"])
                 - timedelta(minutes=jc["overlap_minutes"]))
    else:
        since = now_utc - timedelta(days=jc["initial_lookback_days"])
        log.info(f"No cursor — first run, looking back {jc['initial_lookback_days']} day(s)")

    calls = fetch_inbound_calls(cfg, since)

    entries, skipped, failures = [], [], []
    for call in calls:
        cid = call.get("id")
        if cid in processed_ids:
            continue  # idempotency: never process the same call twice
        ctype = call_type(call)
        if ctype not in [t.lower() for t in jc["process_call_types"]]:
            log.info(f"  call {cid}: type '{ctype}' not processed in v1 — ignored")
            processed_ids.add(cid)
            state["processed_call_ids"].append(cid)
            continue
        try:
            kind, payload = process_call(call, cfg, args.dry_run, now_utc)
            if kind == "skipped" and payload["reason"] == "no transcript":
                # JustCall's AI transcript lags the call by a few minutes. Leave
                # the call unprocessed and retry next run until the grace window
                # expires; only then count it as a real "no transcript" skip.
                call_dt = call_datetime_utc(call)
                grace = jc.get("transcript_grace_minutes", 45)
                if call_dt and (now_utc - call_dt) < timedelta(minutes=grace):
                    log.info(f"  call {cid}: transcript not ready yet — retrying next run")
                    continue  # not marked processed
            (entries if kind == "entry" else skipped).append(payload)
        except Exception as e:  # one bad call must never kill the run
            log.error(f"  call {cid} FAILED: {e}", exc_info=True)
            failures.append({"call_id": cid,
                             "number": call.get("contact_number", "?"),
                             "error": f"{type(e).__name__}: {e}"})
        processed_ids.add(cid)
        state["processed_call_ids"].append(cid)

    log.info(f"Run summary: {len(entries)} processed, {len(skipped)} skipped, "
             f"{len(failures)} failed")

    # Digest: pending entries/skips/failures from earlier --no-digest runs
    # flush with this one.
    all_entries = state.get("pending_digest", []) + entries
    all_skipped = state.get("pending_skipped", []) + skipped
    all_failures = state.get("pending_failures", []) + failures
    try:
        from zoneinfo import ZoneInfo
        run_date_pt = now_utc.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%b %-d, %Y")
    except Exception:
        run_date_pt = now_utc.strftime("%b %d, %Y")

    if args.no_digest:
        state["pending_digest"] = all_entries
        state["pending_skipped"] = all_skipped
        state["pending_failures"] = all_failures
        log.info(f"--no-digest: holding {len(all_entries)} entries, "
                 f"{len(all_skipped)} skips, {len(all_failures)} failures for a later run")
    else:
        if all_entries or all_skipped or all_failures:
            digest = build_digest(all_entries, all_skipped, all_failures, run_date_pt)
            if args.dry_run:
                log.info(f"DRY RUN — digest that would post to Slack:\n{digest}")
            else:
                post_to_slack(digest, cfg["slack"]["channel"])
        else:
            log.info("No new calls, nothing skipped/failed — no digest to post")
        state["pending_digest"] = []
        state["pending_skipped"] = []
        state["pending_failures"] = []

    if not args.dry_run:
        state["last_run_utc"] = now_utc.isoformat()
        save_state(state, cfg["state"]["path"], cfg["state"]["max_processed_ids"])

    log.info("Call agent run complete.")


if __name__ == "__main__":
    main()

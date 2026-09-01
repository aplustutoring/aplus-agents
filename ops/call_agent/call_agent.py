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

EXIT CODES:
  0  healthy run — including a quiet day (no calls) or a day where every call
     was legitimately skipped (hang-up / no recording / no transcript).
  1  every call the run attempted raised (0 successes, >=1 failure). The digest
     still posts and state is still saved; the nonzero exit is what wakes the
     Actions retry sweeper. A private Slack alert fires alongside it.

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
    ALL inbound calls account-wide (every line) since since_utc. One fetch
    serves both monitored-number processing and missed-call alerting — the
    main loop routes by line. Pages via page/per_page; dedup by call id.
    """
    jc = cfg["justcall"]
    seen, calls = set(), []
    # from_datetime is interpreted in the ACCOUNT timezone even though the
    # response's call_date/call_time are UTC (verified live 2026-07-17 — a UTC
    # cursor reads as hours in the future and silently returns nothing).
    from zoneinfo import ZoneInfo
    tz_name = jc.get("account_timezone", "America/Los_Angeles")
    since_str = since_utc.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S")
    log.info(f"Fetching inbound calls (all lines) since {since_str} {tz_name} "
             f"({since_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC)...")
    directions = ["Incoming"]
    if jc.get("monitor_outbound"):
        directions.append("Outgoing")  # all lines (Roman 2026-07-27)
    for direction in directions:
        page = 0  # pagination is 0-indexed (verified live 2026-07-10; docs don't say)
        while True:
            data = jc_get("/v2.1/calls", params={
                "call_direction": direction,
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
    log.info(f"  -> {len(calls)} calls fetched ({', '.join(d.lower() for d in directions)})")
    return calls


def fetch_daily_activity(cfg, now_utc):
    """
    ALL calls today (both directions, every line in the account) since
    midnight in the account timezone — feeds the digest's daily-activity
    brief. Independent of the processing cursor and monitored_numbers.
    """
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(cfg["justcall"].get("account_timezone", "America/Los_Angeles"))
    day_start = now_utc.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    since_str = day_start.strftime("%Y-%m-%d %H:%M:%S")
    calls, page = [], 0
    while True:
        data = jc_get("/v2.1/calls", params={
            "from_datetime": since_str,
            "per_page": 100,
            "page": page,
            "sort": "datetime",
            "order": "asc",
        })
        batch = data.get("data", data if isinstance(data, list) else [])
        if not batch:
            break
        calls.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return calls


def _line_name(number, cfg):
    """Friendly line name from config (justcall.line_names), else (818) 555-1234."""
    digits = re.sub(r"\D", "", str(number or ""))
    names = cfg["justcall"].get("line_names") or {}
    for key, name in names.items():
        if re.sub(r"\D", "", str(key)) == digits:
            return name
    if len(digits) == 11 and digits.startswith("1"):
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return str(number or "?")


def _fmt_outcomes(counter):
    """Counter of call types -> '8 answered, 2 missed, 1 voicemail'."""
    order = ["answered", "missed", "abandoned", "voicemail", "unanswered"]
    parts = [f"{counter[t]} {t}" for t in order if counter.get(t)]
    parts += [f"{v} {t}" for t, v in sorted(counter.items())
              if t not in order and v]
    return ", ".join(parts)


def build_activity_brief(calls, cfg, run_date_pt):
    """Slack block: today's account-wide call totals by person and by line."""
    from collections import Counter, defaultdict
    n_in, n_out = 0, 0
    in_types, out_types = Counter(), Counter()
    per_person = defaultdict(lambda: {"in": Counter(), "out": Counter()})
    per_line = defaultdict(lambda: {"in": Counter(), "out": Counter()})

    for c in calls:
        ci = c.get("call_info", {}) or {}
        direction = (ci.get("direction") or "").lower()
        ctype = (ci.get("type") or "unknown").lower()
        person = c.get("agent_name") or (c.get("agent") or {}).get("name") or "Unassigned"
        line = _line_name(c.get("justcall_number"), cfg)
        if direction == "incoming":
            n_in += 1
            in_types[ctype] += 1
            per_person[person]["in"][ctype] += 1
            per_line[line]["in"][ctype] += 1
        else:
            n_out += 1
            out_types[ctype] += 1
            per_person[person]["out"][ctype] += 1
            per_line[line]["out"][ctype] += 1

    total = n_in + n_out
    lines = [
        f":bar_chart: *Daily call activity — {run_date_pt}* (all lines)",
        f"Total *{total}*: {n_in} inbound · {n_out} outbound",
    ]
    if in_types:
        lines.append(f"Inbound: {_fmt_outcomes(in_types)}")
    if out_types:
        lines.append(f"Outbound: {_fmt_outcomes(out_types)}")

    def side(counts):
        n = sum(counts.values())
        return n, _fmt_outcomes(counts)

    if per_person:
        lines += ["", "*By person*"]
        for person in sorted(per_person, key=lambda p: -sum(
                sum(s.values()) for s in per_person[p].values())):
            i_n, i_s = side(per_person[person]["in"])
            o_n, o_s = side(per_person[person]["out"])
            bits = []
            if i_n:
                bits.append(f"{i_n} in ({i_s})")
            if o_n:
                bits.append(f"{o_n} out ({o_s})")
            lines.append(f"• {person} — " + " · ".join(bits))

    if per_line:
        lines += ["", "*By line*"]
        for line_nm in sorted(per_line, key=lambda l: -sum(
                sum(s.values()) for s in per_line[l].values())):
            i_n, i_s = side(per_line[line_nm]["in"])
            o_n, o_s = side(per_line[line_nm]["out"])
            bits = []
            if i_n:
                bits.append(f"{i_n} in ({i_s})")
            if o_n:
                bits.append(f"{o_n} out ({o_s})")
            lines.append(f"• {line_nm} — " + " · ".join(bits))

    return "\n".join(lines)


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


def call_direction(call):
    """'incoming' | 'outgoing' (normalized; live values are capitalized)."""
    info = call.get("call_info") or {}
    return str(info.get("direction") or call.get("direction") or "incoming").lower()


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

# Which team owns an action item (Paola 2026-09-01). Trial/session logistics
# belong to the scheduling team, not to this agent's follow-up queue — the
# taxonomy Claude applies is in SUMMARY_PROMPT step 3. "follow_up" is the
# fallback for anything unrouted: a sales follow-up landing on Paola is the
# behaviour that has always been correct.
ACTION_ROUTES = ["scheduling", "follow_up"]
# Prefix on the HubSpot task subject so a scheduling item is identifiable in
# the queue even when no scheduling owner is configured yet (see
# hubspot.scheduling_task_owner in config.yml).
SCHEDULING_TASK_PREFIX = "[Scheduling] "

# Lead-status assignment (hs_lead_status). These are the portal's internal
# option VALUES, not labels (verified live 2026-07-20 — e.g. value
# 'We Connected' is labeled 'QTL - NEW' in the UI). Claude picks one per call
# per the rules in SUMMARY_PROMPT; "no_change" leaves the field alone (used
# for existing/past customers, whose status the deal pipeline owns).
LEAD_STATUS_OPTIONS = [
    "We Connected",                  # QTL - NEW: prospective family we spoke with
    "QTL - Charter",                 # charter family paying with charter funds
    "QTL - Diagnostic Sent",         # test prep / must evaluate first
    "Teacher in a School",           # label "Decision Maker/Director": school leadership/staff
    "Charter School Teacher TOR/EF", # label "Teacher of Record/EF/ES": charter TOR/EF facilitating a family
    "Tutor-Active",                  # tutor applicant
    "UNQUALIFIED",                   # spam / vendor / dead opportunity
    "no_change",
]

# Human-facing display names for Slack/digest/logs. HubSpot gets the internal
# values above; the team sees the portal's UI labels (which differ — verified
# live 2026-07-20).
LEAD_STATUS_LABELS = {
    "NEW": "New (Inbox)",
    "ATTEMPTED_TO_CONTACT": "Attempting to Contact",
    "We Connected": "QTL - NEW",
    "CAP": "QTL - CAP",
    "OPEN_DEAL": "Open deal",
    "Using Someone Else": "Check Back Quarterly",
    "UNQUALIFIED": "Dead Opportunity/Unqualified",
    # 2026-08-17 (Roman): non-family lead-status labels = persona names.
    "Teacher in a School": "Decision Maker/Director",
    "Charter School Teacher TOR/EF": "Teacher of Record/EF/ES",
    "Tutor-Active": "Tutors",
}

FIELD_LABELS = {
    "whats_going_on": "What's going on?",
    "what_we_can_do_to_help": "What we can do to help",
    "student_first_name": "Student first name",
    "student_last_name": "Student last name",
    "grade_level": "Grade level",
    "student_school": "School",
    "subject_need": "Subject",
    "online_or_in_person": "Online/In-person",
    "how_did_you_hear": "How did you hear about us",
    "referral_name": "Referral name",
    "email_correction": "Email",
    "phone_correction": "Phone",
    "lead_status": "Lead status",
}


def status_label(value):
    """UI label for an hs_lead_status internal value (falls back to the value)."""
    return LEAD_STATUS_LABELS.get(value, value)

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
                        | {"firstname", "lastname", "email", "phone", "mobilephone",
                           "hs_lead_status"})

SUMMARY_PROMPT = """Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.

You are processing a phone call ({direction_desc}) for A+ Tutoring, \
a K-12 tutoring company in California (families/parents, partner schools and \
charter schools, tutor applicants). Your output updates the family's CRM \
record, creates follow-up tasks, and feeds a daily ops digest.

1. Summarize the call: 3-5 sentences covering who was on the call, why, and
   the outcome. For OUTBOUND calls, caller_type/intent describe the external
   party and the purpose of our outreach (e.g. lead follow-up = new inquiry).
2. Classify the caller and intent, note sentiment.
3. List action items — things A+ STAFF must do after this call (not things the
   family will do). Include an owner_hint only when a specific A+ person was
   named as responsible. Set follow_up_needed accordingly.
   Route every action item with `route` — which team actually does the work:
   - "scheduling": session/trial logistics the scheduling team owns. Booking,
     moving or confirming a trial or session; texting or calling a family to
     confirm a trial day/time; sending a tutor's profile or bio to a family;
     calling back about an already-scheduled trial or session (including a
     dropped or transferred call about one); matching or swapping a tutor;
     calendar and availability coordination.
   - "follow_up": the sales / relationship follow-up this agent's own tasks
     exist for. Calling a prospective family back about pricing, program fit
     or their decision; sending pricing, an agreement or an assessment link;
     billing and account questions; anything arising from a complaint;
     school / charter partnership follow-up; correcting the family's record.
   When an item could be read either way, ask who physically does it: if the
   answer is "whoever owns the calendar", it is "scheduling".
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
5. Assign lead_status — the contact's CRM lead status after this call (the
   current value is current_lead_status in the record below):
   - Prospective FAMILY inquiries we actually spoke with: "QTL - Charter" if
     the family pays with charter-school instructional funds; "QTL -
     Diagnostic Sent" if the need is test prep or A+ must evaluate/diagnose
     the student before proposing a plan; otherwise "We Connected".
   - School staff calling in a professional capacity: "Teacher in a School";
     if they are specifically a charter-school TOR/EF facilitating a family's
     enrollment: "Charter School Teacher TOR/EF".
   - Tutor applicants: "Tutor-Active". Spam, solicitors, vendors: "UNQUALIFIED".
   - "no_change" is ONLY for: an EXISTING or past CUSTOMER (family already
     receiving/received tutoring) calling about their service — their status
     is owned by the deal pipeline, never demote it; a caller who is not the
     person in the record shown; or a call too garbled to classify at all.
     A record that merely already CONTAINS notes about this same inquiry is
     NOT a reason for no_change — prospective families, school staff, tutor
     applicants, and spam must always get a status, especially when
     current_lead_status is null.
   Briefly justify in lead_status_reason.
6. Set next_step_scheduled — true ONLY if a CONCRETE next step was locked in
   during the call: an assessment/diagnostic or first session booked, or a
   callback/meeting at a specific agreed day+time. "We'll send pricing",
   "we'll follow up", "call us anytime" = false. This only applies to
   prospective-family and school-partnership calls; for every other caller
   type (existing customers, vendors, tutors, spam) set true so no flag is
   raised.
7. Write handoff_note — a short brief for a teammate who was NOT on this call
   and will handle the follow-up: who called and their tone, what was
   discussed and PROMISED (pricing quoted, program/model recommended,
   dates/timing agreed), student/parent/school names, what the caller now
   expects to happen, and a suggested opener for the follow-up contact.
   Write it as instructions to the teammate ("Karen expects...", "open
   with..."). Null when follow_up_needed is false.
8. Record every NAME CORRECTION the call established in name_corrections —
   the caller telling us we have a student's or parent's name wrong ("it's
   Autumn, not Autumn-Rose", "she goes by Katie"), including a name we read
   back incorrectly. Each entry is {{"wrong": <the name we had/used>,
   "correct": <what the caller said it is>}}. Empty array when no name was
   corrected. Once a name is corrected, use the CORRECTED name everywhere in
   this output — the summary, every action item, the handoff note and the
   record log entries. Never carry the old name into anything a teammate will
   read or say to the family.

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
                    "route": {"type": "string", "enum": ACTION_ROUTES},
                },
                "required": ["item", "owner_hint", "route"],
                "additionalProperties": False,
            },
        },
        "name_corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "wrong": {"type": "string"},
                    "correct": {"type": "string"},
                },
                "required": ["wrong", "correct"],
                "additionalProperties": False,
            },
        },
        "follow_up_needed": {"type": "boolean"},
        "next_step_scheduled": {"type": "boolean"},
        "handoff_note": _NULLABLE_STR,
        "lead_status": {"type": "string", "enum": LEAD_STATUS_OPTIONS},
        "lead_status_reason": {"type": "string"},
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
                 "name_corrections",
                 "follow_up_needed", "next_step_scheduled", "handoff_note",
                 "lead_status", "lead_status_reason",
                 "student_or_school_names_mentioned", "record_updates"],
    "additionalProperties": False,
}


def summarize_call(transcript, cfg, contact=None, call=None):
    """Claude summary + record-update proposal as validated dict.
    contact: matched HubSpot contact (or None) — current values feed the prompt.
    call: the JustCall call object (direction-aware prompt framing)."""
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
              "phone_on_file": props.get("phone"),
              "current_lead_status": props.get("hs_lead_status") or None}
    for field, (hs_prop, _) in RECORD_FIELD_MAP.items():
        record[field] = props.get(hs_prop) or None

    direction = call_direction(call or {})
    prompt = SUMMARY_PROMPT.format(
        direction_desc=("OUTBOUND — our team placed this call" if direction == "outgoing"
                        else "INBOUND — the contact called us"),
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
    if d.get("lead_status") not in LEAD_STATUS_OPTIONS:
        d["lead_status"] = "no_change"
    d["lead_status_reason"] = str(d.get("lead_status_reason") or "")
    if not isinstance(d["action_items"], list):
        raise ValueError("action_items must be an array")
    items = []
    for it in d["action_items"]:
        if isinstance(it, str):
            items.append({"item": it, "owner_hint": None, "route": "follow_up"})
        elif isinstance(it, dict) and it.get("item"):
            route = it.get("route")
            items.append({"item": str(it["item"]),
                          "owner_hint": it.get("owner_hint") or None,
                          "route": route if route in ACTION_ROUTES else "follow_up"})
    d["action_items"] = items
    d["follow_up_needed"] = bool(d["follow_up_needed"])
    d["next_step_scheduled"] = bool(d.get("next_step_scheduled", True))
    hn = d.get("handoff_note")
    d["handoff_note"] = str(hn).strip() or None if isinstance(hn, str) else None
    if not isinstance(d["student_or_school_names_mentioned"], list):
        d["student_or_school_names_mentioned"] = []
    d["student_or_school_names_mentioned"] = [str(x) for x in d["student_or_school_names_mentioned"]]
    d["name_corrections"] = _clean_name_corrections(d.get("name_corrections"))

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
    _apply_name_corrections(d)
    return d


# Free-text record_updates fields a corrected name can appear in. The enum
# fields (grade, subject, modality, attribution) never contain a name.
_NAME_BEARING_RECORD_FIELDS = ("whats_going_on", "what_we_can_do_to_help",
                               "student_first_name", "student_last_name",
                               "referral_name")


def _clean_name_corrections(raw):
    """Normalize name_corrections to [{'wrong','correct'}] with both non-empty
    and actually different. Anything malformed is dropped, not raised on — a
    bad correction entry must never cost us the whole call."""
    out = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        wrong = str(c.get("wrong") or "").strip()
        correct = str(c.get("correct") or "").strip()
        if not wrong or not correct or wrong.lower() == correct.lower():
            continue
        out.append({"wrong": wrong, "correct": correct})
    return out


def _swap_name(text, wrong, correct):
    """Whole-word, case-insensitive replacement of one name in one string."""
    if not text:
        return text
    return re.sub(rf"\b{re.escape(wrong)}\b", correct, text, flags=re.IGNORECASE)


def _apply_name_corrections(d):
    """
    Belt-and-braces enforcement of prompt step 8: when the call corrected a
    name, no stale name survives into anything a teammate reads or says to the
    family (Paola 2026-09-01 — the child's name was corrected to 'Autumn' on
    the call and the old name still went out in the next-step language).
    The prompt already asks for this; this pass catches the misses.
    """
    corrections = d.get("name_corrections") or []
    if not corrections:
        return d
    for c in corrections:
        wrong, correct = c["wrong"], c["correct"]
        # "Autumn" -> "Autumn Rose" would re-match its own output and stack up
        # ("Autumn Rose Rose"). The prompt still carries the corrected name;
        # only the mechanical sweep steps aside.
        if re.search(rf"\b{re.escape(wrong)}\b", correct, flags=re.IGNORECASE):
            log.warning(f"  name correction '{wrong}' -> '{correct}': corrected name "
                        f"contains the old one — swap skipped (model output kept)")
            continue
        d["summary"] = _swap_name(d["summary"], wrong, correct)
        d["handoff_note"] = _swap_name(d.get("handoff_note"), wrong, correct)
        for it in d["action_items"]:
            it["item"] = _swap_name(it["item"], wrong, correct)
        d["student_or_school_names_mentioned"] = [
            _swap_name(n, wrong, correct) for n in d["student_or_school_names_mentioned"]]
        for field in _NAME_BEARING_RECORD_FIELDS:
            d["record_updates"][field] = _swap_name(
                d["record_updates"].get(field), wrong, correct)
    return d


# ─── Coaching (rubric scoring) ────────────────────────────────────────────────

RUBRIC_DIMENSIONS = ["U1", "U2", "U3", "U4", "U5", "S1", "S2", "S3", "S4", "V1", "V2"]

COACHING_PROMPT = """Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.

You are a supportive call coach for A+ Tutoring, reviewing \
a call handled by {agent_name} ({direction_desc}). Score the call against the rubric \
below. Apply the S-dimensions only when the call is a new inquiry or school \
partnership; the V-dimensions only for scheduling/billing/complaint calls; \
universal dimensions always. Use null for N/A. For OUTBOUND calls adapt the
anchors: U1 = introduced self + A+ Tutoring clearly at the start (no IVR
exists); S4 advance matters MORE (we initiated — the call should end with a
concrete commitment); V-dimensions apply when the outbound call is service
recovery. Anchor every observation to a \
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


def score_call(transcript, summary, agent_name, cfg, call=None):
    """Rubric score for coaching. Returns dict with scores + overall, or raises."""
    import anthropic

    ccfg = cfg["claude"]
    direction = call_direction(call or {})
    prompt = COACHING_PROMPT.format(
        direction_desc=("OUTBOUND — our team placed this call" if direction == "outgoing"
                        else "INBOUND — the contact called us"),
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



def fmt_phone(number):
    """Pretty US phone for Slack display: (818) 555-1234; non-US left as-is."""
    d = re.sub(r"\D", "", str(number or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if len(d) == 10:
        return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    return str(number or "?")


def who_line(contact_label, number):
    """Slack display name — ALWAYS includes the phone number (fleet rule,
    Roman 2026-07-27: every call-agent Slack post carries the contact's number)."""
    phone = f"`{fmt_phone(number)}`"
    return f"{contact_label} {phone}" if contact_label else phone


SCORES_LEDGER = "ops/call_agent/state/scores.jsonl"


def append_score_record(call, agent_name, card, now_utc):
    """One JSONL line per scored call — the data behind the weekly scorecard.
    Committed back by the workflow with the rest of state/."""
    rec = {
        "call_id": call.get("id"),
        "date_pt": fmt_date_pt(call_datetime_utc(call) or now_utc),
        "agent": agent_name or "unknown",
        "direction": call_direction(call),
        "overall": card.get("overall"),
        "scores": {s["dimension"]: s["score"] for s in card.get("scores", [])
                   if s.get("score") is not None},
    }
    path = REPO_ROOT / SCORES_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def weekly_scorecard(cfg, now_utc):
    """Aggregate last week's (Mon-Sun, PT) per-call scores per person -> #calls."""
    from zoneinfo import ZoneInfo
    today_pt = now_utc.astimezone(ZoneInfo("America/Los_Angeles")).date()
    week_start = today_pt - timedelta(days=today_pt.weekday() + 7)  # prior Monday
    week_end = week_start + timedelta(days=6)
    prior_start, prior_end = week_start - timedelta(days=7), week_start - timedelta(days=1)

    path = REPO_ROOT / SCORES_LEDGER
    if not path.exists():
        log.info("weekly scorecard: no scores ledger yet — nothing to report")
        return
    recs = [json.loads(l) for l in open(path) if l.strip()]

    def window(a, b):
        out = {}
        for r in recs:
            if r.get("overall") is None:
                continue
            if a.isoformat() <= r["date_pt"] <= b.isoformat():
                out.setdefault(r["agent"], []).append(r)
        return out

    cur, prior = window(week_start, week_end), window(prior_start, prior_end)
    lines = [f":bar_chart: *Weekly call scores — {week_start.strftime('%b %-d')}–{week_end.strftime('%b %-d')}*"]
    if not cur:
        lines.append("_No scored calls last week._")
    known = {k.capitalize() for k in (cfg["coaching"].get("slack_user_ids") or {})}
    seen_first = set()
    for agent, rs in sorted(cur.items(), key=lambda kv: -len(kv[1])):
        seen_first.add(agent.split()[0].capitalize())
        overall = sum(r["overall"] for r in rs) / len(rs)
        trend = ""
        if agent in prior:
            delta = overall - sum(r["overall"] for r in prior[agent]) / len(prior[agent])
            arrow = "▲" if delta > 0.05 else ("▼" if delta < -0.05 else "→")
            trend = f"  {arrow} {delta:+.1f} vs prior wk"
        dims = {}
        for r in rs:
            for d, s in r["scores"].items():
                dims.setdefault(d, []).append(s)
        davg = {d: sum(v)/len(v) for d, v in dims.items()}
        hi = max(davg, key=davg.get); lo = min(davg, key=davg.get)
        n_out = sum(1 for r in rs if r["direction"] == "outgoing")
        lines.append(
            f"*{agent}* — *{overall:.1f}/5* ({len(rs)} scored: {len(rs)-n_out} in / {n_out} out){trend}\n"
            f"    strongest {hi} {davg[hi]:.1f} · weakest {lo} {davg[lo]:.1f}"
            + (f" — {RUBRIC_DIM_LABELS.get(lo, lo)}" if lo in RUBRIC_DIM_LABELS else ""))
    quiet = known - seen_first
    if quiet:
        lines.append(f"_No scored calls: {', '.join(sorted(quiet))}_")
    lines.append("_Per-dimension anchors: ops/call_agent/rubric.md_")
    post_to_slack("\n".join(lines), cfg["coaching"]["channel"] or cfg["slack"]["channel"])
    log.info(f"weekly scorecard posted ({len(cur)} people, week {week_start} – {week_end})")


def agent_slack_id(agent_name, cfg):
    """JustCall agent_name -> Slack user ID via coaching.slack_user_ids (first-name match)."""
    ids = (cfg.get("coaching") or {}).get("slack_user_ids") or {}
    name = (agent_name or "").lower()
    for key, uid in ids.items():
        if key in name:
            return uid
    return None


def build_coaching_card(agent_name, contact_label, number, time_pt, summary, card, mention=None):
    who = who_line(contact_label, number)
    by_dim = {s["dimension"]: s for s in card["scores"]}
    score_bits = [f"{d} {by_dim[d]['score']}" for d in RUBRIC_DIMENSIONS
                  if d in by_dim and by_dim[d]["score"] is not None]
    display = mention or (agent_name or "unknown")
    lines = [
        f":studio_microphone: *Coaching — {display}* · {time_pt} · "
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


# The CallRail→HubSpot integration auto-creates a contact for EVERY inbound
# call, using the telco caller-ID (CNAM) string as the name — "Inglewood Ca",
# "Wireless Caller", "Toll Free Call". Treating those shells as known contacts
# defeats the abandoned-IVR spam suppression (abandoned_known_only), so
# find_contact_by_phone filters them out of search results.
US_STATE_ABBRS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "PR", "VI", "GU",
}

GENERIC_CNAM_NAMES = ("wireless caller", "toll free", "unavailable",
                      "voip caller", "anonymous", "restricted")


def _is_cnam_name(name):
    """True when a contact name looks like a telco CNAM caller-ID string:
    a generic label, or a location string ending in a state abbreviation
    ("Inglewood Ca", "Lsan Da 12 Ca")."""
    name = " ".join((name or "").split())
    if not name:
        return False
    low = name.lower()
    if any(low == g or low.startswith(g + " ") for g in GENERIC_CNAM_NAMES):
        return True
    tokens = name.split()
    last = tokens[-1]
    return bool(len(tokens) >= 2 and re.fullmatch(r"[A-Z][a-z]", last)
                and last.upper() in US_STATE_ABBRS)


def _is_callrail_junk_contact(contact):
    """CallRail auto-created caller-ID shell: sourced from CallRail, no email,
    and named after the CNAM string. Real families keep matching — any email
    or a human-looking name clears the record."""
    p = contact.get("properties") or {}
    if (p.get("hs_object_source_detail_1") or "").strip().lower() != "callrail":
        return False
    if (p.get("email") or "").strip():
        return False
    return _is_cnam_name(f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip())


def _first_real_contact(results):
    for c in results:
        if _is_callrail_junk_contact(c):
            p = c.get("properties") or {}
            log.info(f"  ignoring CallRail caller-ID shell contact {c.get('id')} "
                     f"({p.get('firstname', '')} {p.get('lastname', '')})")
            continue
        return c
    return None


def find_contact_by_phone(caller_number):
    """
    HubSpot contact by phone. Tier 1: exact IN-match on phone/mobilephone
    variants. Tier 2: CONTAINS_TOKEN on the wildcarded 10-digit number.
    CallRail caller-ID shell contacts are skipped (see _is_callrail_junk_contact),
    so a number whose only match is a shell counts as unknown.
    Returns contact dict or None.
    """
    e164, variants = phone_variants(caller_number)
    if not variants:
        return None
    props = KEY_PROPERTIES + ["hs_object_source_detail_1"]

    payload = {
        "filterGroups": [
            {"filters": [{"propertyName": "phone", "operator": "IN", "values": variants}]},
            {"filters": [{"propertyName": "mobilephone", "operator": "IN", "values": variants}]},
        ],
        "properties": props,
        "limit": 5,
    }
    res = hs_post("crm/v3/objects/contacts/search", payload)
    contact = _first_real_contact(res.get("results") or [])
    if contact:
        return contact

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
        contact = _first_real_contact(res.get("results") or [])
        if contact:
            return contact
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
            "hs_call_title": f"{'Outbound' if call_direction(call) == 'outgoing' else 'Inbound'} call — {summary['intent']} ({summary['caller_type']})",
            "hs_call_body": "\n".join(body_lines),
            "hs_call_direction": "OUTBOUND" if call_direction(call) == "outgoing" else "INBOUND",
            "hs_call_status": "COMPLETED",
            "hs_call_from_number": call.get("justcall_number", "") if call_direction(call) == "outgoing" else call.get("contact_number", ""),
            "hs_call_to_number": call.get("contact_number", "") if call_direction(call) == "outgoing" else call.get("justcall_number", ""),
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


def _resolve_owner(owner_hint, cfg, answered_by=None, route="follow_up"):
    """Task owner for a follow-up.
    Scheduling-routed items (trial/session logistics — see ACTION_ROUTES) go to
    scheduling_task_owner when one is configured; that beats the Roman handoff
    rule below, because the handoff rule is about who does FOLLOW-UP, and this
    work is not follow-up. With no scheduling owner configured the item still
    lands on the default owner, carrying SCHEDULING_TASK_PREFIX in its subject.
    Calls ROMAN answered hand off to default_task_owner (Paola) no matter who
    the call named — sales calls ring Roman first, but Paola does 100% of
    follow-up (Roman 2026-08-13); the task body carries a handoff block.
    Other answerers: owner_hint ('have Janelle call...') -> owner id,
    else default_task_owner."""
    owners = cfg["hubspot"]["owners"]
    if route == "scheduling":
        sched = cfg["hubspot"].get("scheduling_task_owner")
        if sched and sched in owners:
            return owners[sched]
    if (answered_by or "").strip().lower().startswith("roman"):
        return owners[cfg["hubspot"]["default_task_owner"]]
    hint = (owner_hint or "").lower()
    for name, oid in owners.items():
        if name in hint:
            return oid
    return owners[cfg["hubspot"]["default_task_owner"]]


def task_subject(action_item):
    """HubSpot task subject for an action item, capped at HubSpot's 250 chars.
    Scheduling-routed items carry SCHEDULING_TASK_PREFIX so they read as the
    scheduling team's work at a glance in whichever queue they land in."""
    prefix = SCHEDULING_TASK_PREFIX if action_item["route"] == "scheduling" else ""
    return f"{prefix}{action_item['item']}"[:250]


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
    who = who_line(contact_label, number)
    content = (f"[Call Agent] Negative-sentiment/complaint call from {who} ({number}).\n\n"
               f"{summary['summary']}\n\n"
               f"Intent: {summary['intent']} · Sentiment: {summary['sentiment']}\n"
               f"Check in with the family within {tcfg['check_in_business_days']} business days.")
    payload = {
        "properties": {
            "subject": f"Check in with {who} — call {fmt_date_pt(now_utc)}",
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


def fmt_date_pt(dt_utc):
    """Aware UTC datetime -> PT date string (fleet reports in PT)."""
    try:
        from zoneinfo import ZoneInfo
        return dt_utc.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    except Exception:
        return dt_utc.strftime("%Y-%m-%d")


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
    # Entries carried over from a --no-digest run predate the route element;
    # a missing route just means "not scheduling".
    n_sched = sum(1 for e in entries for t in e.get("tasks_created", [])
                  if len(t) > 2 and t[2] == "scheduling")
    n_updates = sum(len(e.get("record_applied", [])) for e in entries)

    lines = [
        f":telephone_receiver: *Call Agent digest — {run_date_pt}*",
        f"Processed *{len(entries)}* call{'s' if len(entries) != 1 else ''} "
        f"(matched {len(matched)}, unmatched {len(unmatched)}) · "
        f"Hang-ups: {n_hangup} · Skipped: {n_no_rec} no recording, {n_no_tr} no transcript · "
        f"Tasks created: {n_tasks}"
        + (f" ({n_sched} to scheduling)" if n_sched else "")
        + f" · Record updates: {n_updates} · "
        f"Failures: {len(failures)}",
    ]

    def one_liner(e):
        s = e["summary"]
        flags = ""
        if s["sentiment"] == "negative":
            flags += " :red_circle:"
        if s["follow_up_needed"]:
            flags += " :bangbang: follow-up"
        if e.get("no_next_step"):
            flags += " :calendar: NO next step booked"
        if e.get("ticket_id"):
            flags += f" :ticket: {e['ticket_id']}"
        if e.get("tasks_created"):
            flags += f" ({len(e['tasks_created'])} task{'s' if len(e['tasks_created']) != 1 else ''})"
        first = s["summary"].split(". ")[0].rstrip(".") + "."
        who = who_line(e["contact_label"], e["number"])
        arrow = "↗ " if e.get("direction") == "outgoing" else ""
        return f"• {arrow}{e['time_pt']} — {who} ({s['intent']}){flags} — {first}"

    attention = [e for e in entries
                 if e["summary"]["follow_up_needed"]
                 or e["summary"]["sentiment"] == "negative"
                 or e.get("no_next_step")]
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
            who = who_line(e["contact_label"], e["number"])
            for field, old, new in e["record_applied"]:
                shown = new if len(str(new)) <= 80 else str(new)[:77] + "..."
                lines.append(f"• {who}: {FIELD_LABELS.get(field, field)} — {old} → {shown}")

    review = [e for e in entries if e.get("record_skipped")]
    if review:
        lines += ["", "*Proposed but NOT applied (existing value kept — review)*"]
        for e in review:
            who = who_line(e["contact_label"], e["number"])
            for field, current, proposed, _ in e["record_skipped"]:
                lines.append(f"• {who}: {FIELD_LABELS.get(field, field)} — "
                             f"record has '{current}', call says '{proposed}'")

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
    summary = summarize_call(transcript, cfg, contact, call)

    try:
        from zoneinfo import ZoneInfo
        _pt = ZoneInfo("America/Los_Angeles")
        call_date_pt = (call_datetime_utc(call) or now_utc).astimezone(_pt).strftime("%Y-%m-%d")
    except Exception:
        call_date_pt = now_utc.strftime("%Y-%m-%d")
    is_negative = (summary["sentiment"] == "negative" or summary["intent"] == "complaint")
    no_next_step = (summary["caller_type"] == "parent"
                    and summary["intent"] == "new inquiry"
                    and not summary["next_step_scheduled"])
    applied, skipped_updates, tasks_created, ticket_id = [], [], [], None

    # Handoff routing (Roman 2026-08-13): sales calls ring Roman first, but
    # Paola does 100% of follow-up. When Roman answered, every task goes to
    # Paola and its body opens with a handoff block: who spoke to the family
    # + the model's handoff brief (what was promised, names, timing, opener).
    answered_by = call.get("agent_name") or (call.get("agent") or {}).get("name") or ""
    roman_answered = answered_by.strip().lower().startswith("roman")
    handoff_block = ""
    if roman_answered:
        handoff_block = (f"HANDOFF — Roman spoke with this caller on {call_date_pt}; "
                         f"follow-up is assigned to Paola.\n")
        if summary.get("handoff_note"):
            handoff_block += f"{summary['handoff_note']}\n"
        handoff_block += "\n"

    if dry_run:
        if contact:
            log.info(f"  call {cid}: DRY RUN — would log call to contact {contact['id']} "
                     f"({contact_label}) and apply record updates")
            if summary["lead_status"] != "no_change":
                log.info(f"  call {cid}: DRY RUN — would set lead status to "
                         f"'{status_label(summary['lead_status'])}' "
                         f"({summary['lead_status_reason']})")
        for it in summary["action_items"]:
            oid = _resolve_owner(it["owner_hint"], cfg, answered_by, it["route"])
            log.info(f"  call {cid}: DRY RUN — would create Task "
                     f"'{task_subject(it)}' (owner {oid}"
                     f"{', Roman-answered handoff' if roman_answered else ''})")
        if is_negative:
            log.info(f"  call {cid}: DRY RUN — would create HIGH ticket + check-in task "
                     f"+ alert to {cfg['slack']['alert_channel'] or '(alert_channel unset)'}")
        if no_next_step:
            log.info(f"  call {cid}: DRY RUN — new inquiry with NO next step booked; "
                     f"would create same-day HIGH task")
        log.info(f"  call {cid} summary:\n{json.dumps(summary, indent=2)}")
    else:
        if contact:
            log_call_to_hubspot(contact["id"], call, summary, transcript)
            applied, skipped_updates = apply_record_updates(
                contact, summary["record_updates"], call_date_pt)
            new_status = summary["lead_status"]
            current_status = (contact.get("properties") or {}).get("hs_lead_status") or ""
            if new_status != "no_change" and new_status != current_status:
                hs_patch(f"crm/v3/objects/contacts/{contact['id']}",
                         {"properties": {"hs_lead_status": new_status}})
                old_lbl = status_label(current_status) or "(blank)"
                applied.append(("lead_status", old_lbl, status_label(new_status)))
                log.info(f"  call {cid}: lead status {old_lbl} → "
                         f"{status_label(new_status)} ({summary['lead_status_reason']})")
            if applied:
                log.info(f"  call {cid}: record updated — "
                         + "; ".join(f"{FIELD_LABELS.get(f, f)}: {n!r}" for f, _, n in applied))
        else:
            log.info(f"  call {cid}: no HubSpot contact for {number} — digest triage "
                     f"(auto-create disabled in v1)")

        # Action items -> HubSpot Tasks (Roman-answered calls hand off to
        # Paola with a handoff block; otherwise owner from hint, default Paola).
        # Scheduling-routed items are subject-prefixed and, once
        # scheduling_task_owner is set, land on the scheduling queue instead.
        due = next_business_day(now_utc, cfg["hubspot"]["task_due_business_days"])
        for it in summary["action_items"]:
            oid = _resolve_owner(it["owner_hint"], cfg, answered_by, it["route"])
            task_id = create_task(
                contact["id"] if contact else None,
                task_subject(it),
                f"[Call Agent] From inbound call {call_date_pt} ({contact_label or fmt_phone(number)} · {fmt_phone(number)}).\n\n"
                f"{handoff_block}{summary['summary']}",
                oid, due,
                priority="HIGH" if is_negative else "MEDIUM",
            )
            tasks_created.append((it["item"], oid, it["route"], task_id))
            log.info(f"  call {cid}: Task {task_id} created (owner {oid}, "
                     f"route {it['route']})")

        if is_negative:
            ticket_id = create_checkin_ticket(
                contact["id"] if contact else None,
                contact_label, number, summary, cfg, now_utc)
            log.info(f"  call {cid}: check-in ticket {ticket_id} created")

        # No-next-step guard: a new family inquiry that ended without a booked
        # next step gets a same-day HIGH task — "we'll follow up" is where
        # leads die.
        if no_next_step:
            create_task(
                contact["id"] if contact else None,
                f"Book next step with {contact_label or fmt_phone(number)} ({fmt_phone(number)}) — none set on call",
                f"[Call Agent] New-inquiry call ended without a concrete next "
                f"step (assessment / first session / scheduled callback). Call "
                f"back TODAY and lock one in.\n\n{handoff_block}{summary['summary']}",
                _resolve_owner(None, cfg, answered_by), now_utc, priority="HIGH")
            log.info(f"  call {cid}: no next step booked — same-day HIGH task created")

    # Coaching: rubric score, posted to the private coaching channel.
    # Never allowed to fail the call — it's an internal-quality side channel.
    coached = False
    if cfg["coaching"]["enabled"]:
        try:
            agent_name = call.get("agent_name") or (call.get("agent") or {}).get("name")
            card = score_call(transcript, summary, agent_name, cfg, call)
            slack_uid = agent_slack_id(agent_name, cfg)
            coaching_text = build_coaching_card(
                agent_name, contact_label, number, time_pt, summary, card,
                mention=f"<@{slack_uid}>" if slack_uid else None)
            coach_channel = cfg["coaching"]["channel"] or cfg["slack"]["alert_channel"]
            if dry_run or not coach_channel:
                log.info(f"  call {cid}: coaching card"
                         f"{' (DRY RUN)' if dry_run else ' (coaching channel unset)'}:\n"
                         f"{coaching_text}")
            else:
                post_to_slack(coaching_text, coach_channel)
                # DM the card to whoever handled the call — the channel tag
                # alone doesn't notify non-members of the private channel.
                if cfg["coaching"].get("dm_person") and slack_uid:
                    try:
                        post_to_slack(coaching_text, slack_uid)
                    except Exception as e:
                        log.warning(f"  coaching DM to {agent_name} failed: {e}")
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
            if not dry_run:
                try:
                    append_score_record(call, agent_name, card, now_utc)
                except Exception as e:
                    log.warning(f"  call {cid}: score ledger append failed: {e}")
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
        "no_next_step": no_next_step,
        "summary": summary,
        "record_applied": [(f, o, n) for f, o, n in applied],
        "record_skipped": [(f, c, p, r) for f, c, p, r in skipped_updates],
        "tasks_created": [(item, oid, route) for item, oid, route, _ in tasks_created],
        "ticket_id": ticket_id,
        "coached": coached,
        "direction": call_direction(call),
    }


def handle_missed_call(call, cfg, dry_run, now_utc):
    """
    Immediate Slack alert (+ same-day HIGH call-back task) for an inbound
    call that never became a conversation (missed/abandoned/voicemail).
    Metadata only — nothing is transcribed or summarized — so this safely
    covers ALL account lines regardless of recording disclosure.

    Spam filter: "abandoned" means the caller hung up in the IVR before any
    agent rang — the classic robocall signature (numbers look local-spoofed,
    duration metadata is all zeros so it can't help). With
    abandoned_known_only (default), abandoned calls alert ONLY when the
    number matches a HubSpot contact; unknown ones are counted silently
    (still visible in the daily brief's totals). Missed and voicemail calls
    navigated the IVR like a human and always alert.

    Returns "alerted" or "suppressed".
    """
    mc = cfg["missed_calls"]
    number = call.get("contact_number", "?")
    line = _line_name(call.get("justcall_number"), cfg)
    ctype = call_type(call)
    time_pt = fmt_time_pt(call)

    contact, label = None, None
    try:
        contact = find_contact_by_phone(number)
    except Exception as e:
        log.warning(f"  missed-call contact lookup failed for {number}: {e}")
    if contact:
        p = contact.get("properties", {})
        label = f"{p.get('firstname', '')} {p.get('lastname', '')}".strip() or p.get("email")

    if (ctype == "abandoned" and contact is None
            and mc.get("abandoned_known_only", True)):
        log.info(f"  call {call.get('id')}: abandoned in IVR from unknown "
                 f"{number} on {line} — likely spam, no alert")
        return "suppressed"

    who = who_line(label, number)
    status = (contact or {}).get("properties", {}).get("hs_lead_status")
    status_txt = f" · lead status: {status_label(status)}" if status else ""
    text = (f":telephone_receiver: :x: *{ctype.capitalize()} call — {line}* ({time_pt})\n"
            f"{who}{status_txt} — call back NOW. Contact rates drop ~10x after "
            f"the first few minutes.")

    channel = mc.get("channel") or cfg["slack"]["alert_channel"]
    if dry_run or not channel:
        log.info(f"  missed-call alert{' (DRY RUN)' if dry_run else ' (channel unset)'}:\n{text}")
    else:
        post_to_slack(text, channel)

    if mc.get("create_task", True):
        subject = f"Call back {label or number} — {ctype} call on {line}"
        if dry_run:
            log.info(f"  DRY RUN — would create same-day call-back task: {subject}")
        else:
            create_task(
                contact["id"] if contact else None,
                subject,
                f"[Call Agent] Inbound {ctype} call at {time_pt} on {line}. "
                f"No conversation happened — call back promptly.",
                _resolve_owner(None, cfg), now_utc,  # due immediately, not tomorrow
                priority="HIGH",
            )
    log.info(f"  call {call.get('id')}: {ctype} on {line} ({number}) — alerted")
    return "alerted"


def build_alert(contact_label, number, time_pt, summary, ticket_id):
    who = who_line(contact_label, number)
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
    ap.add_argument("--weekly-scorecard", action="store_true",
                    help="post last week's per-person score rollup and exit (no call processing)")
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
    if args.weekly_scorecard:
        weekly_scorecard(cfg, datetime.now(timezone.utc))
        return
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

    monitored_digits = {re.sub(r"\D", "", str(n)) for n in jc["monitored_numbers"]}
    mc_cfg = cfg.get("missed_calls") or {}
    mc_types = [t.lower() for t in mc_cfg.get("alert_types", [])]

    entries, skipped, failures = [], [], []
    n_missed, n_spam = 0, 0
    for call in calls:
        cid = call.get("id")
        if cid in processed_ids:
            continue  # idempotency: never process the same call twice
        ctype = call_type(call)
        direction = call_direction(call)
        on_monitored = (re.sub(r"\D", "", str(call.get("justcall_number") or ""))
                        in monitored_digits)
        if direction == "outgoing":
            on_monitored = True  # outbound monitored on ALL lines (Roman 2026-07-27)
        # Missed-call alerting: any line, metadata only. Speed-to-callback
        # is the conversion lever, so these alert on the poll that sees them.
        if mc_cfg.get("enabled") and ctype in mc_types and direction == "incoming":
            try:  # never fatal
                if handle_missed_call(call, cfg, args.dry_run, now_utc) == "alerted":
                    n_missed += 1
                else:
                    n_spam += 1
            except Exception as e:
                log.warning(f"  call {cid}: missed-call alert failed: {e}")
            processed_ids.add(cid)
            state["processed_call_ids"].append(cid)
            continue
        if not on_monitored:
            log.info(f"  call {cid}: line not monitored — ignored")
            processed_ids.add(cid)
            state["processed_call_ids"].append(cid)
            continue
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
             f"{len(failures)} failed, {n_missed} missed-call alert{'s' if n_missed != 1 else ''}, "
             f"{n_spam} likely-spam abandoned suppressed")

    # Health verdict for the exit code. process_call failures are caught per
    # call so one bad call can't kill the run — but that also meant a run where
    # EVERY call blew up still exited 0 and the Actions retry sweeper stayed
    # quiet (correction 2026-08-20). Skips (hang-up, no recording, no
    # transcript) are normal outcomes, not failures, so an all-skips day is
    # still a healthy run; only "we attempted work and nothing but exceptions
    # came back" is a broken one.
    attempted = len(entries) + len(skipped) + len(failures)
    succeeded = len(entries)
    zero_success = bool(failures) and succeeded == 0

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
        # Daily-activity brief (account-wide, all lines, both directions) —
        # posts every digest run even when the agent processed nothing. Never
        # allowed to sink the digest itself.
        brief = None
        try:
            activity = fetch_daily_activity(cfg, now_utc)
            brief = build_activity_brief(activity, cfg, run_date_pt)
        except Exception as e:
            log.warning(f"daily-activity brief failed (digest still posts): {e}")

        digest = None
        if all_entries or all_skipped or all_failures:
            digest = build_digest(all_entries, all_skipped, all_failures, run_date_pt)
        else:
            log.info("No new processed calls — posting activity brief only")
        combined = "\n\n".join(part for part in (brief, digest) if part)
        if combined:
            if args.dry_run:
                log.info(f"DRY RUN — digest that would post to Slack:\n{combined}")
            else:
                post_to_slack(combined, cfg["slack"]["channel"])
        state["pending_digest"] = []
        state["pending_skipped"] = []
        state["pending_failures"] = []

    if not args.dry_run:
        state["last_run_utc"] = now_utc.isoformat()
        save_state(state, cfg["state"]["path"], cfg["state"]["max_processed_ids"])

    # Digest and state are already handled above — fail loudly only at the end,
    # so a broken run still reports what it saw and stays idempotent.
    if zero_success:
        log.error(f"RUN FAILED — 0/{attempted} calls succeeded "
                  f"({len(failures)} failed, {len(skipped)} skipped)")
        alert = (f":rotating_light: *Call agent: 0/{attempted} calls succeeded* "
                 f"({len(failures)} failed, {len(skipped)} skipped) — {run_date_pt} run")
        alert_channel = cfg["slack"]["alert_channel"]
        if args.dry_run or not alert_channel:
            log.info(f"  zero-success alert"
                     f"{' (DRY RUN)' if args.dry_run else ' (alert_channel unset)'}:\n{alert}")
        else:
            try:  # the exit code is the real signal; Slack is best-effort
                post_to_slack(alert, alert_channel)
            except Exception as e:
                log.warning(f"  zero-success alert post failed: {e}")
        sys.exit(1)

    log.info("Call agent run complete.")


if __name__ == "__main__":
    main()

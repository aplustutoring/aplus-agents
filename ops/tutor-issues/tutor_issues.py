#!/usr/bin/env python3
"""
ops/tutor-issues — Tutor-issue ticketing engine.

Issues we notice get logged as HubSpot tickets on the TUTOR's contact record
(Support Pipeline, category "Tutor Issue", owner = Operations role). Silent
internal log in v1: nothing here is tutor-facing.

Three sources, one ticket shape:
  sweep    Teachworks proof only (Mondays, last complete Sun-Sat week):
             missed_lesson_or_late  — per-student no-show statuses
             notes_not_completed    — unmarked after the Sunday cutoff
                                      (same definition as the scorecard's
                                      unmarked-lessons <3% metric)
  inbound  family reports by email (triage audit log -> HubSpot Conversations
           body) or SMS (JustCall) — a reasoning pass extracts tutor/type/
           evidence; resolves -> ticket + scheduler notification; can't
           resolve -> NO ticket, the scheduler is told to file manually.
  intake   structured Slack messages in #tutor-issues for types 2/4/5:
             tutor-issue <type> | <tutor> | <one-line evidence>

Guards (non-negotiable): baseline-stamp first run creates nothing; one open
ticket per tutor per type per period (recurrence updates it); one digest per
run; hard caps abort loudly BEFORE any write; same-day reruns are no-ops.

Usage:
  python3 tutor_issues.py --mode all|sweep|inbound|intake [--dry-run]
                          [--force-sweep] [--probe-lateness]
                          [--report-json PATH] [--simulate-event PATH]
"""

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
STATE_DIR = HERE / "state"

HS_BASE = "https://api.hubapi.com"
TW_BASE = "https://api.teachworks.com/v1"
JC_BASE = "https://api.justcall.io"

HUBSPOT_API_KEY = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
JUSTCALL_API_KEY = os.getenv("JUSTCALL_API_KEY", "")
JUSTCALL_API_SECRET = os.getenv("JUSTCALL_API_SECRET", "")

TW_TOKENS = {}
if os.getenv("TEACHWORKS_TOKEN", "") or os.getenv("TEACHWORKS_TOKEN_ONLINE", ""):
    TW_TOKENS["online"] = os.getenv("TEACHWORKS_TOKEN", "") or os.getenv("TEACHWORKS_TOKEN_ONLINE", "")
if os.getenv("TEACHWORKS_TOKEN_INPERSON", ""):
    TW_TOKENS["in_person"] = os.getenv("TEACHWORKS_TOKEN_INPERSON", "")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("tutor-issues")

ISSUE_TYPES = ["missed_lesson_or_late", "tutor_change_requested",
               "notes_not_completed", "scheduling_flip_flop",
               "tech_issue_unreported"]
TYPE_LABELS = {
    "missed_lesson_or_late": "Missed lesson / late",
    "tutor_change_requested": "Tutor change requested",
    "notes_not_completed": "Lesson notes not completed",
    "scheduling_flip_flop": "Scheduling flip-flop",
    "tech_issue_unreported": "Tech issue not reported",
}


def load_cfg():
    with open(HERE / "config.yml") as f:
        return yaml.safe_load(f)


# ─── State (all writes atomic; dry runs never write) ─────────────────────────

def _state_path(name):
    return STATE_DIR / f"{name}.json"


def load_state(name, default):
    p = _state_path(name)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return default


def save_state(name, data, dry_run):
    if dry_run:
        log.info(f"[dry-run] would save state/{name}.json")
        return
    STATE_DIR.mkdir(exist_ok=True)
    p = _state_path(name)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    tmp.replace(p)


# ─── Teachworks (both accounts, same client shape as ops/scorecard) ──────────

def tw_get(endpoint, token, params=None):
    headers = {"Authorization": f"Token token={token}",
               "Content-Type": "application/json"}
    params = dict(params or {})
    params["per_page"] = 80
    params["page"] = 1
    results = []
    while True:
        for attempt in range(3):
            r = requests.get(f"{TW_BASE}/{endpoint}", headers=headers,
                             params=params, timeout=30)
            if r.status_code == 403:
                wait = 5 * (attempt + 1)
                log.warning(f"Teachworks rate limit, retrying in {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        else:
            r.raise_for_status()
        data = r.json()
        if not data:
            return results
        results.extend(data)
        if len(data) < params["per_page"]:
            return results
        params["page"] += 1


def last_complete_week(today=None):
    """(sunday, saturday) of the most recently COMPLETED Sun-Sat week."""
    today = today or datetime.now().date()
    days_since_sat = (today.weekday() - 5) % 7 or 7
    saturday = today - timedelta(days=days_since_sat)
    return saturday - timedelta(days=6), saturday


def iso_week_key(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def fetch_week_lessons(start, end):
    """All lessons in [start, end] across both Teachworks accounts, each
    tagged with its account key."""
    out = []
    for acct, tok in TW_TOKENS.items():
        lessons = tw_get("lessons", tok, {
            "from_date[gte]": start.isoformat(),
            "from_date[lte]": end.isoformat(),
        })
        for l in lessons:
            l["_acct"] = acct
        out.extend(lessons)
        log.info(f"[{acct}] {len(lessons)} lessons {start}..{end}")
    return out


def fetch_employees():
    """(acct, employee_id) -> record with name/email/status, plus a
    normalized-name index for exact-match resolution."""
    by_id, by_name, by_email = {}, defaultdict(list), defaultdict(list)

    def norm(s):
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    for acct, tok in TW_TOKENS.items():
        for e in tw_get("employees", tok):
            rec = {"acct": acct, "id": str(e.get("id")),
                   "first": (e.get("first_name") or "").strip(),
                   "last": (e.get("last_name") or "").strip(),
                   "email": (e.get("email") or "").strip().lower(),
                   "status": (e.get("status") or "").strip()}
            by_id[(acct, rec["id"])] = rec
            full = norm(f"{rec['first']} {rec['last']}")
            if full:
                by_name[full].append(rec)
            if rec["email"]:
                by_email[rec["email"]].append(rec)
    return by_id, by_name, by_email


# ─── HubSpot ─────────────────────────────────────────────────────────────────

def hs_req(method, path, payload=None, params=None):
    r = requests.request(method, f"{HS_BASE}/{path}",
                         headers={"Authorization": f"Bearer {HUBSPOT_API_KEY}",
                                  "Content-Type": "application/json"},
                         json=payload, params=params, timeout=30)
    r.raise_for_status()
    return r.json() if r.text else {}


def ticket_category_value(label):
    """Enumeration rule: match hs_ticket_category BY LABEL, use the portal's
    internal value. Refuses to run if the label is missing."""
    prop = hs_req("GET", "crm/v3/properties/tickets/hs_ticket_category")
    for opt in prop.get("options", []):
        if opt.get("label") == label:
            return opt["value"]
    raise RuntimeError(f"hs_ticket_category has no option labeled {label!r} — refusing")


def find_tutor_contact(email):
    """Exact-email contact search; returns (contact_id, personas, name) or None."""
    if not email:
        return None
    res = hs_req("POST", "crm/v3/objects/contacts/search", {
        "filterGroups": [{"filters": [
            {"propertyName": "email", "operator": "EQ", "value": email}]}],
        "properties": ["firstname", "lastname", "a_persona", "email"],
        "limit": 2,
    })
    hits = res.get("results", [])
    if len(hits) != 1:
        return None
    c = hits[0]
    p = c.get("properties", {})
    personas = [s.strip() for s in (p.get("a_persona") or "").split(";") if s.strip()]
    name = f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip() or email
    return c["id"], personas, name


def get_ticket(ticket_id):
    try:
        return hs_req("GET", f"crm/v3/objects/tickets/{ticket_id}",
                      params={"properties": "hs_pipeline_stage,tutor_issue_occurrences,"
                                            "tutor_issue_source_ids,subject"})
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None
        raise


def create_ticket(props, contact_id):
    payload = {
        "properties": props,
        "associations": [{
            "to": {"id": contact_id},
            # 16 = HubSpot-defined ticket->contact association
            "types": [{"associationCategory": "HUBSPOT_DEFINED",
                       "associationTypeId": 16}],
        }],
    }
    return hs_req("POST", "crm/v3/objects/tickets", payload).get("id")


def update_ticket(ticket_id, props):
    hs_req("PATCH", f"crm/v3/objects/tickets/{ticket_id}", {"properties": props})


def fetch_thread_text(thread_id, limit=8):
    """Plain text of the most recent messages in a HubSpot Conversations
    thread (the triage inbox is a Conversations inbox)."""
    res = hs_req("GET", f"conversations/v3/conversations/threads/{thread_id}/messages",
                 params={"limit": limit})
    parts = []
    for m in res.get("results", []):
        if m.get("type") != "MESSAGE":
            continue
        txt = m.get("text") or ""
        sender = (m.get("senders") or [{}])[0]
        addr = ((sender.get("deliveryIdentifier") or {}).get("value")) or ""
        if txt.strip():
            parts.append(f"From {addr}:\n{txt.strip()}")
    return "\n\n---\n\n".join(parts[-4:])


# ─── JustCall SMS ────────────────────────────────────────────────────────────

_jc_auth_mode = "plain"


def _jc_headers():
    global _jc_auth_mode
    if _jc_auth_mode == "plain":
        auth = f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}"
    else:
        auth = "Basic " + base64.b64encode(
            f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}".encode()).decode()
    return {"Authorization": auth, "Accept": "application/json"}


def jc_get(path, params=None):
    global _jc_auth_mode
    for attempt in range(4):
        r = requests.get(f"{JC_BASE}{path}", headers=_jc_headers(),
                         params=params or {}, timeout=30)
        if r.status_code == 401 and _jc_auth_mode == "plain":
            _jc_auth_mode = "basic"
            continue
        if r.status_code == 429:
            time.sleep(min(15 * (attempt + 1), 120))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def fetch_inbound_sms(lookback_minutes):
    since = datetime.now() - timedelta(minutes=lookback_minutes)
    data = jc_get("/v2.1/texts", params={
        "from_datetime": since.strftime("%Y-%m-%d %H:%M:%S"),
        "sort": "datetime", "order": "asc", "per_page": 100,
    })
    texts = data.get("data", []) if isinstance(data, dict) else []
    return [t for t in texts
            if str(t.get("direction", "")).lower().startswith("in")]


# ─── Slack ───────────────────────────────────────────────────────────────────

def slack_api(method, payload):
    r = requests.post(f"https://slack.com/api/{method}",
                      headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                               "Content-Type": "application/json; charset=utf-8"},
                      json=payload, timeout=20)
    r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Slack {method} failed: {body.get('error')}")
    return body


def fetch_channel_messages(channel, oldest_ts):
    res = slack_api("conversations.history",
                    {"channel": channel, "oldest": oldest_ts, "limit": 100})
    return res.get("messages", [])


# ─── Claude reasoning (inbound reports) ──────────────────────────────────────

EXTRACT_PROMPT = """\
You are the reasoning stage of A+ Tutoring's tutor-issue logger. A family \
sent the message below ({source}). Decide whether it REPORTS a concrete \
tutor-issue event, and extract the facts. Do not guess: if the message does \
not name or clearly identify the tutor, say so with low confidence.

Issue types (pick at most one):
- missed_lesson_or_late: the tutor did not show up, or arrived late
- tutor_change_requested: the family asks for a different tutor
- scheduling_flip_flop: repeated tutor-driven rescheduling churn
- tech_issue_unreported: a tech problem happened and was not reported
- notes_not_completed: lesson notes were not completed

Message:
<message>
{text}
</message>

Return ONLY a JSON object:
{{"is_tutor_issue": bool,
  "issue_type": "<one of the five>" or null,
  "tutor_name": "<full name as stated>" or null,
  "tutor_email": "<email if stated>" or null,
  "student_name": "<student/child full name if stated>" or null,
  "event_date": "YYYY-MM-DD" or null,
  "evidence_summary": "<one sentence, facts only>",
  "reasoning": "<2-3 sentences: why this classification and identification>",
  "confidence": 0.0-1.0}}
"""


def extract_report(text, source, cfg):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=3)
    resp = client.messages.create(
        model=cfg["claude"]["model"],
        max_tokens=cfg["claude"]["max_tokens"],
        messages=[{"role": "user",
                   "content": EXTRACT_PROMPT.format(source=source, text=text[:6000])}],
    )
    raw = resp.content[0].text.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ─── Tutor resolution (refusal is a signal, a guess is a landmine) ───────────

def resolve_tutor(ref, employees, cfg):
    """ref: {'tw_id': (acct,id)} or {'email': ...} or {'name': ...}.
    Returns {'contact_id','name','email','tw'} or {'refused': reason}."""
    by_id, by_name, by_email = employees
    emp = None
    if ref.get("tw_id"):
        emp = by_id.get(ref["tw_id"])
        if not emp:
            return {"refused": f"no Teachworks employee {ref['tw_id']}"}
    elif ref.get("email"):
        cands = by_email.get(ref["email"].strip().lower(), [])
        if len(cands) > 1:
            return {"refused": f"email {ref['email']} matches {len(cands)} TW employees"}
        emp = cands[0] if cands else None
    elif ref.get("name"):
        key = re.sub(r"\s+", " ", ref["name"].strip().lower())
        cands = by_name.get(key, [])
        if len(cands) != 1:
            return {"refused": f"name {ref['name']!r} matches {len(cands)} TW employees "
                               "(need exactly 1)"}
        emp = cands[0]
    else:
        return {"refused": "no tutor identifier in the report"}

    email = (emp["email"] if emp else ref.get("email", "")).strip().lower()
    if not email:
        return {"refused": f"TW employee {emp['acct']}:{emp['id']} has no email on file"}
    hit = find_tutor_contact(email)
    if not hit:
        return {"refused": f"no unique HubSpot contact with email {email}"}
    contact_id, personas, name = hit
    if "Tutors" not in personas:
        return {"refused": f"contact {contact_id} ({email}) a_persona lacks 'Tutors' "
                           f"(has: {personas or 'none'})"}
    return {"contact_id": contact_id, "name": name, "email": email,
            "tw": f"{emp['acct']}:{emp['id']}" if emp else ""}


def scheduler_for_student(student_name, cfg):
    initial = (student_name or "").strip().lower()[:1]
    if initial and initial in "abcdefghijkl":
        return cfg["schedulers"]["a_to_l"]
    if initial and initial in "mnopqrstuvwxyz":
        return cfg["schedulers"]["m_to_z"]
    return cfg["hubspot"]["roles"]["fallback_scheduler"]


# ─── Detectors (sweep: Teachworks proof only) ────────────────────────────────

def sweep_events(cfg, week_start, week_end):
    """Qualifying events for the completed week, grouped
    (tutor_tw_key, issue_type) -> {'events': [...], 'tutor': emp_stub}."""
    d = cfg["detectors"]
    no_show = set(d["missed_lesson_or_late"]["no_show_statuses"])
    marked = set(d["notes_not_completed"]["marked_statuses"])
    lessons = fetch_week_lessons(week_start, week_end)
    grouped = defaultdict(lambda: {"events": [], "students": []})

    for lesson in lessons:
        acct = lesson["_acct"]
        emp_id = lesson.get("employee_id")
        lesson_key = f"tw:{acct}:{lesson.get('id')}"
        date = (lesson.get("from_date") or "")[:10]
        participants = lesson.get("participants") or [{
            "status": lesson.get("status"), "student_name": lesson.get("name")}]
        for p in participants:
            status = (p.get("status") or "").strip().lower()
            student = (p.get("student_name") or "").strip()
            issue = None
            if status in no_show:
                issue = "missed_lesson_or_late"
            elif status not in marked:
                issue = "notes_not_completed"
            if not issue:
                continue
            key = (acct, str(emp_id) if emp_id else f"name:{lesson.get('employee_name')}")
            g = grouped[(key, issue)]
            g["events"].append({"key": f"{lesson_key}:{p.get('student_id') or student}:{issue}",
                                "source_id": lesson_key, "date": date,
                                "student": student, "status": status})
            g["students"].append(student)
            g["tutor_name"] = (lesson.get("employee_name") or "").strip()
    return grouped, lessons


def probe_lateness(lessons):
    """Diagnostic: does Teachworks expose an ACTUAL start distinct from the
    scheduled one? Reports observed time-ish fields so the threshold decision
    is made on evidence, never silently."""
    fields = defaultdict(int)
    samples = {}
    for l in lessons[:500]:
        for k, v in l.items():
            if v not in (None, "", []) and re.search(
                    r"time|start|arriv|clock|actual|check", k, re.I):
                fields[k] += 1
                samples.setdefault(k, str(v)[:40])
    return {"lessons_probed": min(len(lessons), 500),
            "time_like_fields": {k: {"count": c, "sample": samples[k]}
                                 for k, c in sorted(fields.items())}}


# ─── Planning (everything funnels into planned actions; caps run before
#     ANY write; one digest per run) ─────────────────────────────────────────

class Plan:
    def __init__(self):
        self.tickets = []        # {create|update, tutor, issue_type, ...}
        self.notifications = []  # {scheduler, text}
        self.refusals = []       # {source, reason, detail}
        self.digest_lines = []
        self.processed_keys = []


def period_key(issue_type, event_date, cfg):
    mode = cfg["dedupe_period"].get(issue_type, "weekly")
    d = datetime.strptime(event_date, "%Y-%m-%d").date() if event_date \
        else datetime.now().date()
    return iso_week_key(d) if mode == "weekly" else f"30d-from-{d.isoformat()}"


def within_period(issue_type, existing_period, event_date, cfg):
    mode = cfg["dedupe_period"].get(issue_type, "weekly")
    if mode == "weekly":
        return existing_period == period_key(issue_type, event_date, cfg)
    m = re.match(r"30d-from-(\d{4}-\d{2}-\d{2})", existing_period or "")
    if not m:
        return False
    anchor = datetime.strptime(m.group(1), "%Y-%m-%d").date()
    d = datetime.strptime(event_date, "%Y-%m-%d").date() if event_date \
        else datetime.now().date()
    return (d - anchor).days <= 30


def plan_ticket(plan, cfg, tickets_index, tutor, issue_type, events,
                source, evidence, student=None, reasoning=None):
    """One open ticket per tutor per type per period: update if the indexed
    ticket is still open and in-period, else create."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    event_date = (events[0].get("date") if events else None) or \
        datetime.now().date().isoformat()
    idx_key = f"{tutor['contact_id']}:{issue_type}"
    source_lines = sorted({e["source_id"] for e in events})

    # Same tutor+type twice in ONE run: merge into the already-planned
    # ticket instead of planning a second create/update.
    for t in plan.tickets:
        if t["idx_key"] == idx_key:
            t["props"]["tutor_issue_occurrences"] += len(events)
            t["props"]["tutor_issue_source_ids"] = "\n".join(
                dict.fromkeys(t["props"]["tutor_issue_source_ids"].split("\n")
                              + source_lines))
            return

    existing = tickets_index.get(idx_key)

    if existing and within_period(issue_type, existing.get("period"),
                                  event_date, cfg):
        live = get_ticket(existing["ticket_id"])
        closed = cfg["hubspot"]["ticket"]["closed_stage"]
        if live and str(live["properties"].get("hs_pipeline_stage")) != closed:
            occurrences = int(live["properties"].get("tutor_issue_occurrences") or 1)
            old_sources = live["properties"].get("tutor_issue_source_ids") or ""
            merged = "\n".join(dict.fromkeys(
                [s for s in old_sources.split("\n") if s] + source_lines))
            plan.tickets.append({
                "action": "update", "ticket_id": existing["ticket_id"],
                "tutor": tutor, "issue_type": issue_type,
                "props": {"tutor_issue_occurrences": occurrences + len(events),
                          "tutor_issue_last_event_at": now_iso,
                          "tutor_issue_source_ids": merged},
                "idx_key": idx_key, "period": existing["period"],
            })
            return

    pk = period_key(issue_type, event_date, cfg)
    subject_detail = f"{len(events)} event(s), {pk}" if len(events) > 1 else \
        (f"wk of {event_date}" if cfg["dedupe_period"][issue_type] == "weekly"
         else f"reported {event_date}")
    content = [f"Tutor: {tutor['name']} ({tutor['email']}; TW {tutor.get('tw') or 'n/a'})",
               f"Issue: {TYPE_LABELS[issue_type]}",
               f"Source: {source}", f"Evidence: {evidence}"]
    if student:
        content.append(f"Student: {student}")
    if reasoning:
        content.append(f"Reasoning: {reasoning}")
    content.append("Silent internal log (v1) — do not contact the tutor from this ticket.")
    plan.tickets.append({
        "action": "create", "tutor": tutor, "issue_type": issue_type,
        "props": {
            "subject": f"[Tutor Issue] {TYPE_LABELS[issue_type]}: {tutor['name']} ({subject_detail})",
            "content": "\n".join(content),
            "hs_pipeline": cfg["hubspot"]["ticket"]["pipeline"],
            "hs_pipeline_stage": cfg["hubspot"]["ticket"]["stage"],
            "hs_ticket_priority": cfg["priority_by_type"][issue_type],
            "hubspot_owner_id": cfg["staff"][cfg["hubspot"]["roles"]["operations"]]["hubspot_owner_id"],
            "ticket_source": "tutor_issues",
            "source_agent": cfg["registry_id"],
            "tutor_issue_type": issue_type,
            "tutor_issue_source_ids": "\n".join(source_lines),
            "tutor_issue_detected_at": now_iso,
            "tutor_issue_last_event_at": now_iso,
            "tutor_issue_occurrences": len(events),
            "tutor_issue_period": pk,
        },
        "idx_key": idx_key, "period": pk,
    })


# ─── Sources -> plan ─────────────────────────────────────────────────────────

def run_sweep(plan, cfg, state, employees, baseline_mode):
    week_start, week_end = last_complete_week()
    grouped, lessons = sweep_events(cfg, week_start, week_end)
    processed = set(state["processed"])
    d = cfg["detectors"]
    mins = {"missed_lesson_or_late": d["missed_lesson_or_late"]["min_events_per_week"],
            "notes_not_completed": d["notes_not_completed"]["min_events_per_week"]}

    for (tw_key, issue_type), g in sorted(grouped.items(), key=lambda kv: str(kv[0])):
        fresh = [e for e in g["events"] if e["key"] not in processed]
        if not fresh:
            continue
        if baseline_mode:
            plan.processed_keys.extend(e["key"] for e in fresh)
            continue
        if len(fresh) < mins[issue_type]:
            continue
        acct, emp_id = tw_key
        ref = {"tw_id": (acct, emp_id)} if not str(emp_id).startswith("name:") \
            else {"name": str(emp_id)[5:]}
        tutor = resolve_tutor(ref, employees, cfg)
        if tutor.get("refused"):
            plan.refusals.append({
                "source": f"sweep/{issue_type}",
                "tutor_hint": g.get("tutor_name") or str(tw_key),
                "events": len(fresh), "reason": tutor["refused"]})
            continue
        evidence = "; ".join(f"{e['date']} {e['student']} [{e['status'] or 'unmarked'}]"
                             for e in fresh[:8])
        plan_ticket(plan, cfg, state["tickets"], tutor, issue_type, fresh,
                    source=f"Teachworks sweep, week {week_start}..{week_end}",
                    evidence=evidence)
        plan.processed_keys.extend(e["key"] for e in fresh)
    return week_start, week_end, lessons


def _handle_report(plan, cfg, state, employees, *, event_key, source_label,
                   source_id, text, baseline_mode):
    """Shared email/SMS path: reason -> resolve -> ticket+notify, or flag."""
    if event_key in set(state["processed"]):
        return
    if baseline_mode:
        plan.processed_keys.append(event_key)
        return
    ex = extract_report(text, source_label, cfg)
    plan.processed_keys.append(event_key)
    if not ex or not ex.get("is_tutor_issue"):
        return
    issue_type = ex.get("issue_type")
    scheduler = scheduler_for_student(ex.get("student_name"), cfg)
    conf = float(ex.get("confidence") or 0)
    if issue_type not in ISSUE_TYPES or conf < cfg["inbound"]["min_confidence"]:
        plan.refusals.append({"source": source_label, "reason":
                              f"low confidence ({conf:.2f}) or no clear type",
                              "detail": ex.get("evidence_summary", "")})
        plan.notifications.append({
            "scheduler": scheduler,
            "text": (f"Couldn't auto-file a tutor issue from a {source_label} "
                     f"({source_id}) — please review and file manually if real. "
                     f"Summary: {ex.get('evidence_summary') or 'n/a'}")})
        return
    ref = {"email": ex["tutor_email"]} if ex.get("tutor_email") \
        else {"name": ex.get("tutor_name") or ""}
    tutor = resolve_tutor(ref, employees, cfg)
    if tutor.get("refused"):
        plan.refusals.append({"source": source_label,
                              "reason": tutor["refused"],
                              "detail": ex.get("evidence_summary", "")})
        plan.notifications.append({
            "scheduler": scheduler,
            "text": (f"Tutor issue reported via {source_label} ({source_id}) but the "
                     f"tutor couldn't be matched ({tutor['refused']}) — "
                     f"please file manually. Summary: {ex.get('evidence_summary')}")})
        return
    events = [{"key": event_key, "source_id": source_id,
               "date": ex.get("event_date") or datetime.now().date().isoformat(),
               "student": ex.get("student_name") or "", "status": "reported"}]
    plan_ticket(plan, cfg, state["tickets"], tutor, issue_type, events,
                source=source_label, evidence=ex.get("evidence_summary", ""),
                student=ex.get("student_name"), reasoning=ex.get("reasoning"))
    plan.notifications.append({
        "scheduler": scheduler, "ticket_ref": len(plan.tickets) - 1,
        "text": (f"Tutor-issue ticket {{ticket_id}} filed from a {source_label} "
                 f"({source_id}): {TYPE_LABELS[issue_type]} — {tutor['name']}. "
                 f"{ex.get('evidence_summary', '')}")})


def run_inbound_email(plan, cfg, state, employees, baseline_mode):
    path = REPO_ROOT / cfg["inbound"]["email"]["audit_log"]
    if not path.exists():
        log.warning(f"audit log missing: {path}")
        return
    cats = set(cfg["inbound"]["email"]["scan_categories"])
    cursor = state["cursors"].get("email_audit_ts", "")
    scanned = 0
    max_scan = cfg["inbound"]["max_scan_per_run"]
    newest = cursor
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("timestamp", "")
            if cursor and ts <= cursor:
                continue
            if rec.get("category") not in cats:
                newest = max(newest, ts)
                continue
            if scanned >= max_scan:
                # stop BEFORE advancing the cursor over this unscanned record
                log.warning("inbound email scan cap reached; rest next run")
                break
            newest = max(newest, ts)
            event_key = f"hsconv:{rec.get('message_id')}"
            if baseline_mode or event_key in set(state["processed"]):
                if event_key not in set(state["processed"]):
                    plan.processed_keys.append(event_key)
                continue
            scanned += 1
            text = ""
            if rec.get("thread_id"):
                try:
                    text = fetch_thread_text(rec["thread_id"])
                except requests.HTTPError as e:
                    log.warning(f"thread {rec['thread_id']} fetch failed: {e}")
            text = text or rec.get("reason", "")
            _handle_report(plan, cfg, state, employees,
                           event_key=event_key,
                           source_label="family email",
                           source_id=f"hsconv:{rec.get('thread_id')}"
                                     + (f" hsticket:{rec['ticket_id']}" if rec.get("ticket_id") else ""),
                           text=text, baseline_mode=baseline_mode)
    if newest:
        state["cursors"]["email_audit_ts"] = newest


def run_inbound_sms(plan, cfg, state, employees, baseline_mode):
    if not cfg["inbound"]["sms"]["enabled"]:
        return
    if not (JUSTCALL_API_KEY and JUSTCALL_API_SECRET):
        log.warning("JustCall creds missing — SMS leg skipped")
        return
    for t in fetch_inbound_sms(cfg["inbound"]["sms"]["lookback_minutes"]):
        sms_id = str(t.get("id"))
        body = (t.get("sms_info") or {}).get("body") or t.get("body") or ""
        sender = t.get("contact_number") or t.get("from") or "unknown"
        if not body.strip():
            continue
        _handle_report(plan, cfg, state, employees,
                       event_key=f"jcsms:{sms_id}",
                       source_label="family text (SMS)",
                       source_id=f"jcsms:{sms_id} from {sender}",
                       text=body, baseline_mode=baseline_mode)


INTAKE_RE = re.compile(r"^\s*tutor-issue\s+(\S+)\s*\|\s*([^|]+?)\s*\|\s*(.+)$",
                       re.IGNORECASE | re.DOTALL)


def run_intake(plan, cfg, state, employees, baseline_mode, dry_run):
    channel = cfg["slack"]["channel"]
    if not channel:
        log.info("intake: slack.channel unset — skipped (setup pending)")
        return
    oldest = state["cursors"].get("slack_ts", "0")
    newest = oldest
    for msg in sorted(fetch_channel_messages(channel, oldest),
                      key=lambda m: m.get("ts", "")):
        ts = msg.get("ts", "0")
        if float(ts) <= float(oldest):
            continue
        newest = max(newest, ts, key=float)
        if msg.get("bot_id") or msg.get("subtype"):
            continue
        event_key = f"slack:{ts}"
        if event_key in set(state["processed"]):
            continue
        m = INTAKE_RE.match(msg.get("text") or "")
        if not m:
            continue  # ordinary conversation in the channel is not intake
        plan.processed_keys.append(event_key)
        if baseline_mode:
            continue
        issue_type, tutor_raw, note = (m.group(1).strip().lower(),
                                       m.group(2).strip(), m.group(3).strip())

        def reject(reason):
            plan.refusals.append({"source": "slack intake", "reason": reason,
                                  "detail": (msg.get("text") or "")[:120]})
            plan.notifications.append({
                "thread_ts": ts,
                "text": f"Rejected — {reason}. Format: `tutor-issue "
                        f"<type> | <tutor email, tw:<acct>:<id>, or \"First Last\"> | <evidence>`"})

        if issue_type not in cfg["intake"]["allowed_types"]:
            reject(f"type {issue_type!r} is not manual-intake "
                   f"(allowed: {', '.join(cfg['intake']['allowed_types'])})")
            continue
        twm = re.match(r"tw:(\w+):(\d+)$", tutor_raw)
        if twm:
            ref = {"tw_id": (twm.group(1), twm.group(2))}
        elif "@" in tutor_raw:
            ref = {"email": tutor_raw}
        else:
            ref = {"name": tutor_raw.strip('"')}
        tutor = resolve_tutor(ref, employees, cfg)
        if tutor.get("refused"):
            reject(tutor["refused"])
            continue
        events = [{"key": event_key,
                   "source_id": f"slack:{channel}:{ts}",
                   "date": datetime.now().date().isoformat(),
                   "student": "", "status": "reported"}]
        plan_ticket(plan, cfg, state["tickets"], tutor, issue_type, events,
                    source="structured Slack intake (#tutor-issues)",
                    evidence=note)
        plan.notifications.append({
            "thread_ts": ts, "ticket_ref": len(plan.tickets) - 1,
            "text": f"Ticket {{ticket_id}} created: {TYPE_LABELS[issue_type]} — {tutor['name']}."})
    if float(newest) > float(oldest):
        state["cursors"]["slack_ts"] = newest


# ─── Execution (caps first, then writes, then ONE digest) ────────────────────

def enforce_caps(plan, cfg, dry_run):
    """LIVE: abort before any write — a bug must refuse to act, not flood.
    DRY-RUN: report the violation but keep planning visible, so the analysis
    run shows the full distribution AND the fact the cap would have fired."""
    g = cfg["guards"]
    creates = [t for t in plan.tickets if t["action"] == "create"]
    violations = []
    if len(creates) > g["max_tickets_per_run"]:
        violations.append(f"CAP EXCEEDED: {len(creates)} ticket creates > "
                          f"max_tickets_per_run={g['max_tickets_per_run']}")
    if len(plan.notifications) > g["max_notifications_per_run"]:
        violations.append(f"CAP EXCEEDED: {len(plan.notifications)} notifications > "
                          f"max_notifications_per_run={g['max_notifications_per_run']}")
    if violations and not dry_run:
        raise SystemExit("; ".join(violations) + " — refusing to act.")
    for v in violations:
        log.warning(f"[dry-run] {v} — a live run would refuse to act")
    return violations


def execute(plan, cfg, state, dry_run):
    channel = cfg["slack"]["channel"]
    created = []
    for t in plan.tickets:
        if t["action"] == "create":
            if dry_run:
                tid = f"DRY-{len(created)+1}"
            else:
                tid = create_ticket(t["props"], t["tutor"]["contact_id"])
            created.append(tid)
            t["ticket_id"] = tid
            state["tickets"][t["idx_key"]] = {"ticket_id": tid, "period": t["period"]}
            plan.digest_lines.append(
                f"CREATED {tid}: {t['props']['subject']}")
        else:
            if not dry_run:
                update_ticket(t["ticket_id"], t["props"])
            plan.digest_lines.append(
                f"UPDATED {t['ticket_id']}: {TYPE_LABELS[t['issue_type']]} — "
                f"{t['tutor']['name']} (+{t['props']['tutor_issue_occurrences']} total)")
    for r in plan.refusals:
        plan.digest_lines.append(f"REFUSED [{r['source']}]: {r['reason']}")

    for n in plan.notifications:
        tid = plan.tickets[n["ticket_ref"]].get("ticket_id", "?") \
            if "ticket_ref" in n else ""
        text = n["text"].replace("{ticket_id}", str(tid))
        sched = n.get("scheduler")
        if sched:
            sid = cfg["staff"].get(sched, {}).get("slack_id", "")
            text = (f"<@{sid}> " if sid else f"{sched}: ") + text
        if dry_run or not channel:
            log.info(f"[dry-run] notify: {text}")
        elif n.get("thread_ts"):
            slack_api("chat.postMessage", {"channel": channel,
                                           "thread_ts": n["thread_ts"], "text": text})
        else:
            slack_api("chat.postMessage", {"channel": channel, "text": text})

    if plan.digest_lines:
        ops = cfg["hubspot"]["roles"]["operations"]
        ops_sid = cfg["staff"].get(ops, {}).get("slack_id", "")
        mention = f"<@{ops_sid}> " if (cfg["slack"]["mention_ops"] and ops_sid) else ""
        digest = (f"{mention}Tutor-issue run "
                  f"{datetime.now().strftime('%Y-%m-%d %H:%M')} — "
                  f"{len(created)} created, "
                  f"{sum(1 for t in plan.tickets if t['action']=='update')} updated, "
                  f"{len(plan.refusals)} refused:\n"
                  + "\n".join(f"• {l}" for l in plan.digest_lines))
        if dry_run or not channel:
            log.info(f"[dry-run] digest:\n{digest}")
        else:
            slack_api("chat.postMessage", {"channel": channel, "text": digest})


def report(plan, extra=None):
    creates = [t for t in plan.tickets if t["action"] == "create"]
    by_type, by_tutor = defaultdict(int), defaultdict(int)
    for t in plan.tickets:
        by_type[t["issue_type"]] += 1
        by_tutor[t["tutor"]["name"]] += 1
    return {
        "would_create": len(creates),
        "would_update": len(plan.tickets) - len(creates),
        "by_issue_type": dict(by_type),
        "by_tutor": dict(sorted(by_tutor.items(), key=lambda kv: -kv[1])),
        "top_tutors": sorted(by_tutor.items(), key=lambda kv: -kv[1])[:10],
        "refusals": plan.refusals,
        "notifications": [n["text"] for n in plan.notifications],
        "digest_lines": plan.digest_lines,
        **(extra or {}),
    }


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="all",
                    choices=["all", "sweep", "inbound", "intake"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-sweep", action="store_true",
                    help="run the weekly sweep on a non-Monday")
    ap.add_argument("--probe-lateness", action="store_true",
                    help="dump observed Teachworks time fields (dry diagnostic)")
    ap.add_argument("--report-json", default="")
    ap.add_argument("--assume-baselined", action="store_true",
                    help="DRY-RUN DIAGNOSTIC ONLY: plan as if the baseline were "
                         "already stamped empty, to show the full would-create "
                         "distribution the real baseline run will suppress")
    ap.add_argument("--simulate-event", default="",
                    help="path to a JSON file with one synthetic inbound report "
                         "(dry-run verification: must yield exactly 1 ticket + 1 digest line)")
    args = ap.parse_args()
    cfg = load_cfg()

    if not HUBSPOT_API_KEY:
        raise SystemExit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    if not TW_TOKENS and args.mode in ("all", "sweep"):
        raise SystemExit("Teachworks tokens missing (sweep needs them)")

    state = {
        "processed": load_state("processed", []),
        "cursors": load_state("cursors", {}),
        "tickets": load_state("tickets", {}),
    }
    baseline = load_state("baseline", None)
    baseline_mode = baseline is None
    if args.assume_baselined:
        if not args.dry_run:
            raise SystemExit("--assume-baselined is a dry-run diagnostic only")
        baseline_mode = False
    if baseline_mode:
        log.warning("NO BASELINE — this run stamps existing qualifying events "
                    "and creates/sends NOTHING.")

    # Verify the category label exists before any planning (fail early).
    cat_value = ticket_category_value(cfg["hubspot"]["ticket"]["category_label"])
    log.info(f"hs_ticket_category label {cfg['hubspot']['ticket']['category_label']!r} "
             f"-> value {cat_value!r}")

    employees = fetch_employees() if TW_TOKENS else ({}, defaultdict(list), defaultdict(list))
    plan = Plan()
    extra = {}

    if args.simulate_event:
        with open(args.simulate_event) as f:
            sim = json.load(f)
        _handle_report(plan, cfg, state, employees,
                       event_key=f"sim:{sim.get('id', 'event')}",
                       source_label=sim.get("source_label", "family email"),
                       source_id=sim.get("source_id", "sim:1"),
                       text=sim["text"], baseline_mode=False)
    else:
        is_monday = datetime.now().weekday() == 0
        if args.mode in ("all", "sweep") and (is_monday or args.force_sweep
                                              or args.mode == "sweep"):
            ws, we, lessons = run_sweep(plan, cfg, state, employees, baseline_mode)
            extra["sweep_week"] = f"{ws}..{we}"
            if args.probe_lateness:
                extra["lateness_probe"] = probe_lateness(lessons)
        if args.mode in ("all", "inbound"):
            run_inbound_email(plan, cfg, state, employees, baseline_mode)
            run_inbound_sms(plan, cfg, state, employees, baseline_mode)
        if args.mode in ("all", "intake"):
            run_intake(plan, cfg, state, employees, baseline_mode, args.dry_run)

    # stamp category into every create (verified value, matched by label)
    for t in plan.tickets:
        if t["action"] == "create":
            t["props"]["hs_ticket_category"] = cat_value

    extra["cap_violations"] = enforce_caps(plan, cfg, args.dry_run)
    execute(plan, cfg, state, args.dry_run)

    if baseline_mode:
        save_state("baseline", {"stamped_at":
                                datetime.now(timezone.utc).isoformat(),
                                "stamped_events": len(plan.processed_keys)},
                   args.dry_run)
    state["processed"] = sorted(set(state["processed"]) | set(plan.processed_keys))
    if not args.simulate_event:
        save_state("processed", state["processed"], args.dry_run)
        save_state("cursors", state["cursors"], args.dry_run)
        save_state("tickets", state["tickets"], args.dry_run)

    rep = report(plan, extra)
    rep["baseline_mode"] = baseline_mode
    print(json.dumps(rep, indent=2, default=str))
    if args.report_json:
        with open(args.report_json, "w") as f:
            json.dump(rep, f, indent=2, default=str)


if __name__ == "__main__":
    main()

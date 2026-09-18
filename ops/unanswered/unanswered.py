#!/usr/bin/env python3
"""
ops/unanswered — somebody asked for a PERSON and nobody got back to them.

Over 2026-09-14 to 09-16 four people texted asking for a named human. The team
answered every one, by phone, one of them within 68 seconds. Nothing watched
that, so the only way to know was to go and look, and looking at the text log
alone produced three false alarms that accused the team of neglect while they
were on the call.

So this agent is built around two rules.

  1. Detection is literal. A message counts only if it asks to be called or
     names a member of staff. Inferring "this person sounds like they want a
     human" would put a neglect alert on a thread that is going fine.

  2. Resolution is cross-channel and self-healing. "Has anyone got back to
     them" is answered by HubSpot's notes_last_contacted, which aggregates
     calls, emails, texts and meetings. The moment that moves past the ask,
     the alert closes itself. A false positive costs nobody an interruption.

The shape is copied from the call agent's handle_missed_call, which already
does the right thing for a ringing phone: Slack alert plus a same-day HIGH
call-back task on the contact. A text asking for a person had no equivalent.

Usage:
  python3 unanswered.py [--dry-run] [--report-json PATH]
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

HS_BASE = "https://api.hubapi.com"
JC_BASE = "https://api.justcall.io"

HUBSPOT_API_KEY = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
JUSTCALL_API_KEY = os.getenv("JUSTCALL_API_KEY", "")
JUSTCALL_API_SECRET = os.getenv("JUSTCALL_API_SECRET", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("unanswered")


def load_cfg():
    with open(HERE / "config.yml") as f:
        return yaml.safe_load(f)


# ─── state ───────────────────────────────────────────────────────────────────

def _state_dir(cfg):
    return REPO_ROOT / cfg["state"]["path"]


def load_state(cfg, name, default):
    p = _state_dir(cfg) / f"{name}.json"
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def save_state(cfg, name, data, dry_run):
    if dry_run:
        log.info(f"  DRY RUN — would save state/{name}.json")
        return
    d = _state_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(data, indent=2, sort_keys=True))


# ─── JustCall ────────────────────────────────────────────────────────────────

def _jc_headers():
    return {"Authorization": f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}",
            "Accept": "application/json"}


def fetch_inbound_texts(cfg, max_pages=40):
    """Inbound texts in the window, across every line.

    Two JustCall traps, both of which return the WRONG rows silently rather
    than erroring (verified live 2026-09-14):
      - paging is ZERO-indexed, so page=1 skips the newest 100 texts and a
        short window comes back empty;
      - with order=asc the first page is the OLDEST 100 in the window.
    So: start at page 0 and walk next_page_link.
    """
    mins = int(cfg["justcall"]["lookback_minutes"])
    since = datetime.now() - timedelta(minutes=mins)
    out, page = [], 0
    while page < max_pages:
        r = requests.get(f"{JC_BASE}/v2.1/texts", headers=_jc_headers(), timeout=40,
                         params={"per_page": 100, "page": page,
                                 "from_datetime": since.strftime("%Y-%m-%d %H:%M:%S")})
        if r.status_code == 429:
            time.sleep(5)
            continue
        if r.status_code >= 300:
            raise RuntimeError(f"JustCall texts HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        rows = d.get("data") or []
        out += rows
        if not rows or not d.get("next_page_link"):   # NOT next_page_url
            break
        page += 1
    return [t for t in out if str(t.get("direction", "")).lower().startswith("in")]


def text_body(t):
    return ((t.get("sms_info") or {}).get("body") or t.get("body") or "").strip()


def text_when(t):
    """UTC 'YYYY-MM-DD HH:MM:SS' as JustCall reports it on the row."""
    info = t.get("sms_info") or {}
    return " ".join(x for x in [t.get("sms_date") or info.get("sms_date") or "",
                                t.get("sms_time") or info.get("sms_time") or ""]
                    if x).strip()


# ─── detection ───────────────────────────────────────────────────────────────

def named_staff(body, staff_names):
    """The staff first name this message mentions, or ''. Word-boundary match
    so 'romantic' does not read as Roman and 'kathy' does not read as Kath."""
    low = (body or "").lower()
    for name in staff_names:
        if re.search(rf"\b{re.escape(name.lower())}\b", low):
            return name.lower()
    return ""


def personal_ask(body, cfg):
    """Why this message is an ask for a person, or '' when it is not.

    Literal on purpose. Two triggers: it asks to be called, or it names a
    member of staff. A thank-you that names the person who just helped is the
    commonest false positive and is excluded by prefix.
    """
    d = cfg["detect"]
    text = (body or "").strip()
    if not text:
        return ""
    low = text.lower()
    for pre in d.get("ignore_if_starts_with") or []:
        if low.startswith(pre.lower()):
            return ""
    who = named_staff(text, d.get("staff_first_names") or [])
    asked_to_call = next((p for p in (d.get("call_phrases") or [])
                          if p.lower() in low), "")
    # Say both when both are true. "Janelle can you please call me" is a
    # request for one specific person, and an alert that only says "asked to
    # be called" loses the half that decides who picks it up.
    if who and asked_to_call:
        return f"asked {who.capitalize()} to call them"
    if asked_to_call:
        return f'asked to be called ("{asked_to_call}")'
    if who:
        return f"asked for {who.capitalize()} by name"
    return ""


# ─── HubSpot ─────────────────────────────────────────────────────────────────

def hs_req(method, path, payload=None, params=None):
    r = requests.request(method, f"{HS_BASE}/{path.lstrip('/')}",
                         headers={"Authorization": f"Bearer {HUBSPOT_API_KEY}",
                                  "Content-Type": "application/json"},
                         json=payload, params=params, timeout=30)
    if r.status_code == 429:
        time.sleep(3)
        return hs_req(method, path, payload, params)
    r.raise_for_status()
    return r.json() if r.text else {}


def phone_digits(number):
    d = re.sub(r"\D", "", str(number or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else ""


CONTACT_PROPS = ["firstname", "lastname", "email", "phone", "mobilephone",
                 "notes_last_contacted", "hubspot_owner_id", "a_persona"]


def find_contact_by_phone(number):
    """HubSpot contact for a number, or None.

    Tier 0 is HubSpot's own normalised phone index, which holds the bare
    digits however the number was typed. Guessing formatting variants is
    always one punctuation style behind reality: on 2026-09-16 it missed
    Maddy Zamany, stored "(310)456-4963" with no space after the paren.
    Tier 1 keeps the variants, because the index is HubSpot-maintained and a
    contact edited seconds ago may not be in it yet.
    """
    n = phone_digits(number)
    if not n:
        return None
    res = hs_req("POST", "crm/v3/objects/contacts/search", {
        "filterGroups": [
            {"filters": [{"propertyName": "hs_searchable_calculated_phone_number",
                          "operator": "EQ", "value": n}]},
            {"filters": [{"propertyName": "hs_searchable_calculated_mobile_number",
                          "operator": "EQ", "value": n}]}],
        "properties": CONTACT_PROPS, "limit": 5})
    hits = res.get("results") or []
    if not hits:
        a, b, c = n[:3], n[3:6], n[6:]
        variants = [f"+1{n}", n, f"1{n}", f"({a}) {b}-{c}", f"{a}-{b}-{c}",
                    f"({a}){b}-{c}", f"+1 {a}-{b}-{c}"]
        res = hs_req("POST", "crm/v3/objects/contacts/search", {
            "filterGroups": [
                {"filters": [{"propertyName": "phone", "operator": "IN", "values": variants}]},
                {"filters": [{"propertyName": "mobilephone", "operator": "IN",
                              "values": variants}]}],
            "properties": CONTACT_PROPS, "limit": 5})
        hits = res.get("results") or []
    if len(hits) != 1:
        return None if not hits else hits[0]
    return hits[0]


def last_touch(contact):
    """When anyone last contacted this person, on ANY channel."""
    return ((contact or {}).get("properties") or {}).get("notes_last_contacted") or ""


def answered_since(contact, when_utc, cfg):
    """True when somebody got back to them after the message.

    notes_last_contacted is ISO-Z; the JustCall stamp is 'YYYY-MM-DD HH:MM:SS'
    in UTC. Compare the first 19 characters of each with T normalised out.
    """
    last = last_touch(contact)
    if not last or not when_utc:
        return False
    return last[:19].replace("T", " ") >= when_utc[:19]


def create_task(cfg, contact_id, subject, body, owner_id, dry_run):
    props = {"hs_task_subject": subject, "hs_task_body": body,
             "hs_task_status": "NOT_STARTED", "hs_task_type": "TODO",
             "hs_task_priority": cfg["hubspot"].get("task_priority", "HIGH"),
             "hs_timestamp": str(int(datetime.now(timezone.utc).timestamp() * 1000))}
    if owner_id:
        props["hubspot_owner_id"] = str(owner_id)
    payload = {"properties": props}
    if contact_id:
        payload["associations"] = [{
            "to": {"id": str(contact_id)},
            "types": [{"associationCategory": "HUBSPOT_DEFINED",
                       "associationTypeId": 204}]}]
    if dry_run:
        log.info(f"  DRY RUN — would create task: {subject}")
        return "DRYRUN"
    return hs_req("POST", "crm/v3/objects/tasks", payload).get("id", "")


def complete_task(task_id, dry_run):
    """Close a task we opened, because the ask has since been answered."""
    if not task_id or task_id == "DRYRUN":
        return
    if dry_run:
        log.info(f"  DRY RUN — would complete task {task_id}")
        return
    try:
        hs_req("PATCH", f"crm/v3/objects/tasks/{task_id}",
               {"properties": {"hs_task_status": "COMPLETED"}})
    except requests.HTTPError as e:
        log.warning(f"  could not complete task {task_id}: {e}")


# ─── Slack ───────────────────────────────────────────────────────────────────

def post_slack(cfg, text, dry_run):
    channel = cfg["slack"].get("channel")
    if dry_run or not channel or not SLACK_BOT_TOKEN:
        log.info(f"  {'DRY RUN' if dry_run else 'slack unset'} — would post:\n{text}")
        return
    r = requests.post("https://slack.com/api/chat.postMessage",
                      headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                               "Content-Type": "application/json; charset=utf-8"},
                      json={"channel": channel, "text": text}, timeout=20)
    body = r.json()
    if not body.get("ok"):
        log.warning(f"  slack post failed: {body.get('error')}")


# ─── the run ─────────────────────────────────────────────────────────────────

def line_name(cfg, number):
    return (cfg["justcall"]["line_names"] or {}).get(str(number or ""), str(number or "a line"))


def owner_for(cfg, who):
    owners = cfg["hubspot"]["owners"] or {}
    if who and cfg["hubspot"].get("route_to_named_person") and who in owners:
        return owners[who], who
    default = cfg["hubspot"].get("default_owner")
    return owners.get(default), default


def resolve_open_asks(cfg, state, dry_run):
    """Self-healing pass. For every ask we alerted on, re-read the contact: if
    anyone has touched them since, close the task and forget it.

    This is the half that matters. The failure being fixed is not a missed
    message, it is an alert that keeps insisting a family was ignored after
    somebody already called them back.
    """
    closed = []
    for sms_id, rec in list((state.get("open") or {}).items()):
        cid = rec.get("contact_id")
        if not cid:
            continue
        try:
            contact = hs_req("GET", f"crm/v3/objects/contacts/{cid}",
                             params={"properties": ",".join(CONTACT_PROPS)})
        except requests.HTTPError:
            continue
        if answered_since(contact, rec.get("at"), cfg):
            complete_task(rec.get("task_id"), dry_run)
            closed.append({"sms_id": sms_id, "who": rec.get("label"),
                           "answered_at": last_touch(contact)})
            state["open"].pop(sms_id, None)
    return closed


def run(cfg, dry_run):
    state = {"open": load_state(cfg, "open", {}),
             "seen": load_state(cfg, "seen", [])}
    baseline = load_state(cfg, "baseline", None)
    baseline_mode = baseline is None
    if baseline_mode:
        log.warning("NO BASELINE — this run stamps what already qualifies and "
                    "creates NOTHING.")

    closed = resolve_open_asks(cfg, state, dry_run)
    for c in closed:
        log.info(f"  closed: {c['who']} was answered at {c['answered_at']}")

    texts = fetch_inbound_texts(cfg)
    seen = set(state["seen"])
    grace = timedelta(minutes=int(cfg["resolve"]["grace_minutes"]))
    now = datetime.now(timezone.utc)
    alerts, held, unknown = [], [], []

    for t in texts:
        sms_id = str(t.get("id"))
        if sms_id in seen:
            continue
        body = text_body(t)
        why = personal_ask(body, cfg)
        if not why:
            continue
        when = text_when(t)
        try:
            sent = datetime.strptime(when[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if now - sent < grace:
            held.append({"who": t.get("contact_name") or t.get("contact_number"),
                         "why": why, "age_min": round((now - sent).total_seconds() / 60)})
            continue                       # still inside the grace window

        state["seen"].append(sms_id)
        number = t.get("contact_number") or ""
        contact = find_contact_by_phone(number)

        if contact and answered_since(contact, when, cfg):
            continue                       # somebody already got back to them

        p = (contact or {}).get("properties") or {}
        label = f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip() \
            or (t.get("contact_name") or "") or str(number)

        if not contact and not cfg["resolve"].get("alert_unknown_numbers", True):
            continue
        if not contact:
            unknown.append(label)

        cid = (contact or {}).get("id")
        if cfg["guards"].get("one_open_ask_per_contact", True) and cid:
            if any(r.get("contact_id") == cid for r in (state["open"] or {}).values()):
                continue                   # already alerted, do not double up

        if baseline_mode:
            continue

        who = named_staff(body, cfg["detect"].get("staff_first_names") or [])
        owner_id, owner_key = owner_for(cfg, who)
        line = line_name(cfg, t.get("justcall_number"))
        age_min = round((now - sent).total_seconds() / 60)

        subject = f"Call back {label} — {why}"
        task_body = (f"[Unanswered] {label} texted {line} at {when} UTC and {why}.\n\n"
                     f'Their words: "{body[:400]}"\n\n'
                     f"Nobody has contacted them on any channel since "
                     f"({age_min} minutes). This task closes itself once "
                     f"anyone calls, emails or texts them.")
        task_id = create_task(cfg, cid, subject, task_body, owner_id, dry_run)

        mention = (cfg["slack"]["slack_user_ids"] or {}).get(owner_key or "", "")
        tag = f"<@{mention}> " if mention else ""
        note = "" if contact else " (number not in HubSpot — a stranger asking us to call)"
        post_slack(cfg, (f":telephone_receiver: *Nobody has got back to {label}*{note}\n"
                         f"{tag}They texted {line} {age_min} min ago and {why}.\n"
                         f'> {body[:300]}\n'
                         f"Closes itself as soon as anyone contacts them."), dry_run)

        state["open"][sms_id] = {"contact_id": cid, "task_id": task_id,
                                 "at": when, "label": label, "why": why}
        alerts.append({"who": label, "why": why, "age_min": age_min,
                       "owner": owner_key, "known": bool(contact)})

        if len(alerts) >= int(cfg["guards"]["max_alerts_per_run"]):
            log.warning("  alert cap reached — stopping this run")
            break

    if baseline_mode:
        save_state(cfg, "baseline", {"stamped_at": now.isoformat(),
                                     "stamped": len(state["seen"])}, dry_run)
    state["seen"] = sorted(set(state["seen"]))[-4000:]
    save_state(cfg, "seen", state["seen"], dry_run)
    save_state(cfg, "open", state["open"], dry_run)
    return {"alerts": alerts, "closed": closed, "held_in_grace": held,
            "unknown_numbers": unknown, "baseline_mode": baseline_mode,
            "scanned": len(texts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report-json", default="")
    args = ap.parse_args()
    cfg = load_cfg()
    if not HUBSPOT_API_KEY:
        raise SystemExit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    if not (JUSTCALL_API_KEY and JUSTCALL_API_SECRET):
        raise SystemExit("JustCall credentials missing")

    report = run(cfg, args.dry_run)
    log.info(f"scanned {report['scanned']} inbound texts · "
             f"{len(report['alerts'])} alerted · {len(report['closed'])} self-closed · "
             f"{len(report['held_in_grace'])} still inside grace")
    for a in report["alerts"]:
        log.info(f"  ALERT {a['who']} — {a['why']} ({a['age_min']} min, "
                 f"owner {a['owner']}{'' if a['known'] else ', unknown number'})")
    if args.report_json:
        Path(args.report_json).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    sys.exit(main())

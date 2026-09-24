#!/usr/bin/env python3
"""
ops/checkin — the quality check-in, owned by us instead of by a Zap.

Measured before rebuilding: over 7 days the existing campaign sent 9 texts and
got 8 replies, 5 of them substantive. It surfaced a family leaving over price,
two service gaps nobody had reported, and a testimonial. It is one of the best
performing things we do.

It also, once in nine, spoke over a human. Albee Li got "hope you are doing
well, wanted to check in" fifteen minutes after a scheduler had apologised to
her about the very lesson she was complaining about.

So this is not a replacement, it is the same idea with three fixes:

  GATE      no send if anyone has messaged that family in 48h, if a ticket is
            open, outside business hours, or twice in a day.
  COPY      name the tutor, name the student, count the sessions, and ask what
            they want focused on NEXT. "How is it going" gets "fine".
  TRIAGE    a reply that reports a problem or hints at leaving becomes a HIGH
            ticket for that student's scheduler, with the family's own words
            on it. Judy Goldzweig told us she was leaving over cost and was
            answered with "let me know if there's any other way I can assist".

Usage:
  python3 checkin.py [--dry-run] [--triage-only] [--report-json PATH]
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
from zoneinfo import ZoneInfo

import requests
import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
PT = ZoneInfo("America/Los_Angeles")

HS = "https://api.hubapi.com"
JC = "https://api.justcall.io"

HUBSPOT_API_KEY = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
JUSTCALL_API_KEY = os.getenv("JUSTCALL_API_KEY", "")
JUSTCALL_API_SECRET = os.getenv("JUSTCALL_API_SECRET", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("checkin")


def load_cfg():
    with open(HERE / "config.yml") as f:
        return yaml.safe_load(f)


# ─── state ───────────────────────────────────────────────────────────────────

def _dir(cfg):
    return REPO_ROOT / cfg["state"]["path"]


def load_state(cfg, name, default):
    p = _dir(cfg) / f"{name}.json"
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except (json.JSONDecodeError, OSError):
        return default


def save_state(cfg, name, data, dry_run):
    if dry_run:
        log.info(f"  DRY RUN — would save state/{name}.json")
        return
    d = _dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(data, indent=2, sort_keys=True))


# ─── clients ─────────────────────────────────────────────────────────────────

def hs(method, path, payload=None, params=None):
    r = requests.request(method, f"{HS}/{path.lstrip('/')}",
                         headers={"Authorization": f"Bearer {HUBSPOT_API_KEY}",
                                  "Content-Type": "application/json"},
                         json=payload, params=params, timeout=30)
    if r.status_code == 429:
        time.sleep(3)
        return hs(method, path, payload, params)
    r.raise_for_status()
    return r.json() if r.text else {}


def _jc_headers():
    return {"Authorization": f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}",
            "Accept": "application/json", "Content-Type": "application/json"}


def jc_texts(hours, max_pages=40):
    """Every text in the window, both directions.

    Paging is ZERO-indexed and order=asc puts the OLDEST page first, so a
    single unpaginated call returns stale rows and misses everything recent
    (both verified live 2026-09-14). Start at 0 and walk next_page_link.

    from_datetime is read in the ACCOUNT clock (PT) while the rows come back
    stamped UTC. This script is run by hand from a Mac that is already on PT,
    so a naive now() happened to work here, but the same line on a UTC runner
    blinded ops/unanswered for a week (2026-09-17 to 09-23). Derive the clock
    rather than inherit it.
    """
    tz = ZoneInfo("America/Los_Angeles")
    since = datetime.now(timezone.utc).astimezone(tz) - timedelta(hours=hours)
    out, page = [], 0
    while page < max_pages:
        r = requests.get(f"{JC}/v2.1/texts", headers=_jc_headers(), timeout=40,
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
        if not rows or not d.get("next_page_link"):
            break
        page += 1
    return out


def jc_send(from_line, to_number, body, dry_run):
    if dry_run:
        log.info(f"  DRY RUN — would text {to_number}:\n      {body}")
        return True, "dry-run"
    r = requests.post(f"{JC}/v2.1/texts/new", headers=_jc_headers(), timeout=30,
                      json={"justcall_number": from_line, "contact_number": to_number,
                            "body": body})
    return r.status_code < 400, f"{r.status_code} {r.text[:160]}"


def slack(cfg, text, dry_run):
    ch = cfg["slack"].get("channel")
    if dry_run or not ch or not SLACK_BOT_TOKEN:
        log.info(f"  {'DRY RUN' if dry_run else 'slack unset'} — would post:\n{text}")
        return
    requests.post("https://slack.com/api/chat.postMessage",
                  headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                           "Content-Type": "application/json; charset=utf-8"},
                  json={"channel": ch, "text": text}, timeout=20)


# ─── helpers ─────────────────────────────────────────────────────────────────

def digits(v):
    d = re.sub(r"\D", "", str(v or ""))[-10:]
    return d if len(d) == 10 else ""


def first_name(full):
    """First name for customer-facing copy. Teachworks returns "Last, First",
    and the raw value put "Mondays with Karl, Sonya" in front of a family on
    2026-09-16 who replied "I don't know who Karl is?"."""
    full = (full or "").strip()
    if not full:
        return ""
    if "," in full:
        after = full.split(",", 1)[1].strip()
        return after.split()[0] if after else full.split(",")[0].strip()
    return full.split()[0].strip(" ,")


def in_send_window(cfg, now_pt=None):
    g = cfg["gate"]
    now = now_pt or datetime.now(PT)
    if g.get("send_weekdays_only", True) and now.weekday() > 4:
        return False
    return g["send_hour_start_pt"] <= now.hour < g["send_hour_end_pt"]


def scheduler_for(cfg, surname):
    key = cfg["schedulers"]["a_to_l"] if (surname or "z")[:1].upper() <= "L" \
        else cfg["schedulers"]["m_to_z"]
    return key, cfg["staff"][key]


def classify(body, cfg):
    """What kind of reply is this? Returns ('churn'|'gap'|'', matched phrase)."""
    low = (body or "").lower()
    t = cfg["triage"]
    for p in t.get("churn_phrases") or []:
        if p.lower() in low:
            return "churn", p
    for p in t.get("gap_phrases") or []:
        if p.lower() in low:
            return "gap", p
    return "", ""


def render(cfg, parent, student, tutor):
    c = cfg["copy"]
    if tutor:
        body = c["with_tutor"].format(parent=first_name(parent), student=first_name(student),
                                      tutor=first_name(tutor))
    else:
        body = c["without_tutor"].format(parent=first_name(parent),
                                         student=first_name(student))
    assert "—" not in body and "--" not in body, "em dash in outbound copy"
    return body


# Captures the whole name after "with", including a "Last, First" pair.
TUTOR_RE = re.compile(r"\bwith ([A-Z][a-zA-Z'\-]+(?:,\s*[A-Z][a-zA-Z'\-]+)?)")


def tutor_from_schedule(sched, known_first_names=None):
    """The tutor's FIRST name out of a schedule string.

    Two shapes live in this field at once, because deals written before
    2026-09-16 kept the raw Teachworks value:

        "Tuesdays 6:00 PM with Seifeldin, Youssef"   -> Youssef
        "Mondays 10:00 AM with Sonya"                -> Sonya

    Taking the token straight after "with" yields the SURNAME on the first
    shape, which is the same mistake that told Nikita Brixey her son's tutor
    was "Karl" (Sonya's surname) and made her reply "I don't know who Karl
    is?". So capture the whole pair and run it through first_name().

    Returns '' when the schedule names more than one distinct tutor, and ''
    when the result is not a known tutor first name. Naming the wrong person
    to a parent is worse than naming nobody.
    """
    names = {first_name(m.group(1)) for m in TUTOR_RE.finditer(sched or "")}
    names.discard("")
    if len(names) != 1:
        return ""
    name = names.pop()
    if known_first_names is not None and name.lower() not in known_first_names:
        return ""
    return name


def tutor_first_names():
    """Lowercased first names of every tutor contact, for the surname guard."""
    out, after = set(), None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "a_persona", "operator": "CONTAINS_TOKEN",
             "value": "Tutors"}]}],
            "properties": ["firstname"], "limit": 100}
        if after:
            body["after"] = after
        j = hs("POST", "crm/v3/objects/contacts/search", body)
        for c in j.get("results", []):
            fn = (c["properties"].get("firstname") or "").strip().lower()
            if fn:
                out.add(fn)
        after = ((j.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    return out


def parent_student(dealname):
    """'Parent - Student - School N - YY/YY'."""
    parts = [p.strip() for p in (dealname or "").split(" - ")]
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")


DEAL_PROPS = ["dealname", "createdate", "dealstage", "schedule_preferences",
              "checkin_last_sent_at"]


def audience(cfg):
    a = cfg["audience"]
    out, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "EQ", "value": a["pipeline"]},
            {"propertyName": "dealstage", "operator": "IN", "values": a["stages"]}]}],
            "properties": DEAL_PROPS, "limit": 100,
            "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}]}
        if after:
            body["after"] = after
        j = hs("POST", "crm/v3/objects/deals/search", body)
        out += j.get("results", [])
        after = ((j.get("paging") or {}).get("next") or {}).get("after")
        if not after or len(out) >= 500:
            break
    return out


def deal_contact(deal_id):
    a = hs("GET", f"crm/v4/objects/deals/{deal_id}/associations/contacts")
    ids = [str(x["toObjectId"]) for x in a.get("results", [])][:5]
    if not ids:
        return None
    b = hs("POST", "crm/v3/objects/contacts/batch/read",
           {"inputs": [{"id": i} for i in ids],
            "properties": ["firstname", "lastname", "phone", "mobilephone", "a_persona",
                           "student_last_name_if_diff_from_parent"]})
    for c in b.get("results", []):
        if "Family" in (c["properties"].get("a_persona") or ""):
            return c
    return (b.get("results") or [None])[0]


def has_open_ticket(contact_id):
    a = hs("GET", f"crm/v4/objects/contacts/{contact_id}/associations/tickets")
    ids = [str(x["toObjectId"]) for x in a.get("results", [])][-20:]
    if not ids:
        return False
    b = hs("POST", "crm/v3/objects/tickets/batch/read",
           {"inputs": [{"id": i} for i in ids],
            "properties": ["hs_pipeline_stage", "subject"]})
    return any(str(t["properties"].get("hs_pipeline_stage")) not in ("4",)
               for t in b.get("results", []))


def run(cfg, dry_run, triage_only=False):
    state = {"sent": load_state(cfg, "sent", {}),
             "triaged": load_state(cfg, "triaged", [])}
    baseline = load_state(cfg, "baseline", None)
    baseline_mode = baseline is None
    if baseline_mode:
        log.warning("NO BASELINE — this run stamps and sends NOTHING.")

    now = datetime.now(timezone.utc)
    g, a = cfg["gate"], cfg["audience"]

    # recent traffic, used both to gate sends and to find replies to triage
    texts = jc_texts(max(int(g["skip_if_message_within_hours"]), 72))
    last_msg, our_checkins = {}, []
    for t in texts:
        n = digits(t.get("contact_number"))
        if not n:
            continue
        info = t.get("sms_info") or {}
        w = f"{t.get('sms_date') or info.get('sms_date')} {t.get('sms_time') or info.get('sms_time')}"
        if n not in last_msg or w > last_msg[n]:
            last_msg[n] = w
        b = (info.get("body") or "").strip()
        out = not str(t.get("direction", "")).lower().startswith("in")
        if out and "would like" in b and "focus on next" in b:
            our_checkins.append((n, w))

    # ── triage replies to our own check-ins ──────────────────────────────
    tickets = []
    if cfg["triage"].get("enabled"):
        seen = set(state["triaged"])
        for n, sent_at in our_checkins:
            for t in texts:
                if digits(t.get("contact_number")) != n:
                    continue
                if not str(t.get("direction", "")).lower().startswith("in"):
                    continue
                info = t.get("sms_info") or {}
                w = f"{t.get('sms_date') or info.get('sms_date')} {t.get('sms_time') or info.get('sms_time')}"
                if w <= sent_at:
                    continue
                key = f"{n}:{w}"
                if key in seen:
                    continue
                body = (info.get("body") or "").strip()
                kind, phrase = classify(body, cfg)
                if not kind:
                    continue
                state["triaged"].append(key)
                if baseline_mode:
                    continue
                label = t.get("contact_name") or n
                sk, staff = scheduler_for(cfg, str(label).split()[-1] if label else "z")
                subject = (f"[Check-in] {'Retention risk' if kind == 'churn' else 'Service gap'}"
                           f": {label}")
                note = (f"They replied to our check-in with:\n\n\"{body[:500]}\"\n\n"
                        f"Matched on \"{phrase}\". This is the reply the check-in "
                        f"exists to surface, so it needs an answer, not an "
                        f"acknowledgement.")
                if not dry_run:
                    hs("POST", "crm/v3/objects/tickets", {"properties": {
                        "subject": subject, "content": note,
                        "hs_pipeline": cfg["triage"]["ticket_pipeline"],
                        "hs_pipeline_stage": cfg["triage"]["ticket_stage"],
                        "hs_ticket_priority": "HIGH",
                        "hubspot_owner_id": staff["hubspot_owner_id"]}})
                slack(cfg, f":warning: *{subject}* (owner {sk})\n> {body[:280]}", dry_run)
                tickets.append({"who": label, "kind": kind, "phrase": phrase,
                                "owner": sk, "said": body[:160]})
                break

    sends = []
    if not triage_only:
        if not cfg.get("armed"):
            log.warning("armed:false — planning only, nothing will be sent")
        if not in_send_window(cfg):
            log.info("outside the send window — no check-ins this run")
        else:
            known = tutor_first_names()
            # ONE text per family, not one per deal. A charter family has a
            # deal per PO slice, so the first dry run planned six identical
            # texts to Christian Gomez and four to Deanna Bernard.
            done_families = set()
            for d in audience(cfg):
                if len(sends) >= int(cfg["guards"]["max_sends_per_run"]):
                    log.warning("send cap reached")
                    break
                p = d["properties"]
                did = d["id"]
                started = (p.get("createdate") or "")[:10]
                if not started:
                    continue
                age = (now.date() - datetime.fromisoformat(started).date()).days
                if age < int(a["first_checkin_after_days"]):
                    continue
                prev = state["sent"].get(did, {}).get("at", "")
                if prev:
                    since_prev = (now.date() - datetime.fromisoformat(prev[:10]).date()).days
                    if since_prev < int(a["repeat_after_days"]):
                        continue
                c = deal_contact(did)
                if not c:
                    continue
                cp = c["properties"]
                num = digits(cp.get("mobilephone") or cp.get("phone"))
                if not num:
                    continue
                if num in done_families:
                    continue                  # already texted this family this run
                recent = last_msg.get(num, "")
                if recent:
                    rd = datetime.strptime(recent[:19], "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=timezone.utc)
                    if (now - rd).total_seconds() < int(g["skip_if_message_within_hours"]) * 3600:
                        continue          # a conversation is already happening
                if g.get("skip_if_open_ticket") and has_open_ticket(c["id"]):
                    continue
                parent, student = parent_student(p.get("dealname"))
                tutor = tutor_from_schedule(p.get("schedule_preferences"), known)
                body = render(cfg, parent, student, tutor)
                done_families.add(num)
                state["sent"][did] = {"at": now.isoformat(), "to": num}
                if baseline_mode or not cfg.get("armed"):
                    sends.append({"who": parent, "student": student, "tutor": tutor,
                                  "body": body, "sent": False})
                    continue
                ok, detail = jc_send(cfg["sms"]["from_line"], f"+1{num}", body, dry_run)
                sends.append({"who": parent, "student": student, "tutor": tutor,
                              "body": body, "sent": ok, "detail": detail})

    if baseline_mode:
        save_state(cfg, "baseline", {"stamped_at": now.isoformat()}, dry_run)
    save_state(cfg, "sent", state["sent"], dry_run)
    save_state(cfg, "triaged", sorted(set(state["triaged"]))[-3000:], dry_run)
    return {"sends": sends, "tickets": tickets, "baseline_mode": baseline_mode,
            "armed": bool(cfg.get("armed")), "in_window": in_send_window(cfg)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--triage-only", action="store_true",
                    help="only triage replies, send nothing")
    ap.add_argument("--report-json", default="")
    args = ap.parse_args()
    cfg = load_cfg()
    if not HUBSPOT_API_KEY:
        raise SystemExit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    if not (JUSTCALL_API_KEY and JUSTCALL_API_SECRET):
        raise SystemExit("JustCall credentials missing")

    rep = run(cfg, args.dry_run, args.triage_only)
    log.info(f"armed={rep['armed']} in_window={rep['in_window']} "
             f"planned {len(rep['sends'])} check-in(s), {len(rep['tickets'])} ticket(s)")
    for s in rep["sends"]:
        log.info(f"  -> {s['who']} / {s['student']} (tutor {s['tutor'] or 'unknown'})")
        log.info(f"     {s['body']}")
    for t in rep["tickets"]:
        log.info(f"  ticket {t['kind']}: {t['who']} -> {t['owner']} :: {t['said']}")
    if args.report_json:
        Path(args.report_json).write_text(json.dumps(rep, indent=2))


if __name__ == "__main__":
    sys.exit(main())

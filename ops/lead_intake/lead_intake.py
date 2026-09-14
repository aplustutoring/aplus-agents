#!/usr/bin/env python3
"""
ops/lead_intake — stage 01 (first touch): a person submits a form, a human is
told within the SLA, with everything they need to make the call.

Replaces HubSpot flow 50818589 "Lead Pipe Line - Online", whose seven defects
are traced in docs/investigations/2026-09-14-online-lead-intake.md. Each one is
answered structurally here, not patched:

  F1  the flow emailed "we could not leave a voicemail" on a DEFAULT branch and
      stamped ATTEMPTED_TO_CONTACT on a timer -> this engine NEVER writes a
      lead status. Only a real call may move it off New (Inbox).
  F2  the alert task was held behind a delay-until-15:30 (up to 23h) -> the
      task is created on the same poll as the conversion, due in SLA hours.
  F3  the "connected" branch counted the flow's OWN outbound email and then
      dead-ended -> there is no branch; the poll is idempotent and re-runs.
  F4  the SMS body rendered a numeric owner id as the rep's name -> copy lives
      in templates/ under review, and nothing sends (see the ceiling below).
  F5  enrollment was 29 pinned form GUIDs -> config.intake_events matches the
      conversion event by name, so a new landing page is covered on day one.
  F7  the exit goal locked out anyone who had ever started tutoring, so
      returning customers got NOTHING -> selection is a cursor over
      recent_conversion_date. A cursor has no memory. A returning family is
      simply a row newer than the cursor, and the alert leads with their
      history.

The ceiling is knowledge/journey/01-first-touch.md, which for this stage says
the agent may classify, create the ticket/task with the routing owner and SLA,
and stamp an [Agent] note ALONE, but must DRAFT the reply for the owning seat.
So this engine does not text or email a family. `send: false` in config.yml is
that rule in code, and stages 00 and 01 are still DRAFT / agent_readable:false,
so it may not be flipped yet.

Every proposed touch still runs email/src/presend.check() and the verdict is
written into the alert. That is the point of the spine: the seat is told "this
family has an active thread on the support line, owned by Janelle" BEFORE they
pick up the phone, not after the family asks how many people they are talking
to at A+.

Guards (non-negotiable, fleet convention): the first run baseline-stamps the
cursor and creates nothing; one alert per contact per conversion; a run over
max_leads_per_run aborts before any write; dry run is the default.

Usage:
  python3 lead_intake.py [--dry-run] [--live] [--report-json PATH]
                         [--since ISO] [--contact ID]

Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.
Before contacting a family, teacher, or tutor, read knowledge/journey/README.md
and pass knowledge/journey/00-pre-send-checklist.md. Act only on stages marked
REVIEWED.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
STATE = HERE / "state"
sys.path.insert(0, str(ROOT / "email"))

CURSOR_FILE = STATE / "cursor.json"
PROCESSED_FILE = STATE / "processed.json"


# ── config / state ─────────────────────────────────────────────────
def cfg() -> dict:
    return yaml.safe_load((HERE / "config.yml").read_text()) or {}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")


# ── pure core (unit-tested; no network) ────────────────────────────
def is_intake_event(event_name: str, c: dict) -> bool:
    """Does this conversion mean 'a person asked us for tutoring'?

    not_a_lead wins over intake_events: 'Teacher Scholarship Program Form' must
    never be read as a tutoring lead just because a page title contains one of
    the intake phrases.
    """
    name = (event_name or "").lower()
    if not name:
        return False
    if any(bad in name for bad in (c.get("not_a_lead") or [])):
        return False
    return any(good in name for good in (c.get("intake_events") or []))


def classify(props: dict) -> str:
    """audience for routing. Persona first (it is the model of record), then
    lead status, which carries identity for the ~90% of contacts with no
    persona set (2026-08-17: 10,064 of 11,115)."""
    persona = props.get("a_persona") or ""
    if "Tutors" in persona:
        return "tutor"
    if "Teacher of Record" in persona:
        return "tor"
    if "Decision Maker" in persona:
        return "decision_maker"
    if "Family" in persona:
        return "family"
    status = props.get("hs_lead_status") or ""
    if status == "Charter School Teacher TOR/EF":
        return "tor"
    if status == "Teacher in a School":
        return "decision_maker"
    if status == "Tutor-Active":
        return "tutor"
    return "family"


def norm_phone(raw: str) -> str:
    """Digits only, US +1 stripped. '+118184048544' and '+18184048544' both
    give '8184048544' — the intake form writes both shapes."""
    d = re.sub(r"\D", "", raw or "")
    while len(d) > 10 and d.startswith("1"):
        d = d[1:]
    return d


def is_spam(props: dict, phone_counts: Counter, c: dict) -> str:
    """Return a reason string, or "" when the lead looks real."""
    s = c.get("spam") or {}
    raw = props.get("phone") or ""
    p10 = norm_phone(raw)
    if s.get("non_us_phone") and p10 and len(p10) != 10:
        return f"phone {raw} is not a US number"

    cap = int(s.get("shared_phone_max") or 0)
    if p10 and cap and phone_counts.get(p10, 0) > cap:
        return f"phone {raw} shared by {phone_counts[p10]} contacts in this window"
    domain = (props.get("email") or "").split("@")[-1].lower()
    if domain and domain in (s.get("email_domains") or []):
        return f"email domain {domain} is blocklisted"
    return ""


def route(audience: str, c: dict) -> dict:
    r = (c.get("routing") or {}).get(audience)
    if not r:
        r = (c.get("routing") or {}).get("family") or {}
    return dict(r)


def returning_summary(deals: list[dict]) -> str:
    """The line that would have saved David Reich. Deals are the proof a family
    has been with us before; flow 50818589 used that same fact to lock them OUT."""
    if not deals:
        return ""
    started = [d for d in deals
               if (d.get("properties") or d).get("start_of_tutoring_for_this_deal")]
    names = [((d.get("properties") or d).get("dealname") or "") for d in deals]
    names = [n for n in names if n][:3]
    head = (f"RETURNING FAMILY — {len(deals)} prior deal(s)"
            + (f", tutoring started on {len(started)} of them" if started else ""))
    return head + (": " + "; ".join(names) if names else "")


def select(rows: list[dict], cursor_iso: str, processed: set, c: dict) -> list[dict]:
    """Rows newer than the cursor whose conversion is an intake event and that
    we have not already alerted on. Sorted oldest first so the cursor advances
    monotonically and a mid-run failure resumes cleanly."""
    out = []
    for r in rows:
        p = r.get("properties") or {}
        at = p.get("recent_conversion_date") or ""
        if not at or at <= cursor_iso:
            continue
        if not is_intake_event(p.get("recent_conversion_event_name"), c):
            continue
        if f"{r.get('id')}:{at}" in processed:
            continue
        out.append(r)
    return sorted(out, key=lambda r: (r.get("properties") or {}).get("recent_conversion_date") or "")


def alert_task(contact: dict, audience: str, seat_name: str, gate, returning: str,
               draft: str) -> tuple[str, str]:
    """(subject, body) for the seat's task. Everything needed to make the call
    is in the body; the seat should not have to open three tabs."""
    p = contact.get("properties") or {}
    name = " ".join(x for x in (p.get("firstname"), p.get("lastname")) if x) or p.get("email") or contact.get("id")
    subject = f"New lead: {name} ({audience})"
    lines = [
        f"Submitted {p.get('recent_conversion_date', '?')} via {p.get('recent_conversion_event_name', '?')}",
        f"Phone {p.get('phone') or 'none on file'} · Email {p.get('email') or 'none on file'}",
        f"Owner seat: {seat_name}",
    ]
    if returning:
        lines += ["", returning, "Open with what we already know. Do not introduce A+ from scratch."]
    lines += ["", "PRE-SEND (email/src/presend.py, knowledge/journey/00-pre-send-checklist.md):",
              f"  verdict: {gate.verdict.upper()}"]
    for reason in (gate.reasons or ["all checks clear"]):
        lines.append(f"  - {reason}")
    if gate.owner:
        who = gate.owner.get("name") or gate.owner.get("seat")
        lines.append(f"  ACTIVE THREAD IS OWNED BY {who}. Talk to them before you reach out.")
    lines += ["", "DRAFT first touch (review, then send from the seat's own line):", draft,
              "", "Ask on the first reply: \"Has anyone at A+ already been in touch with you?\"",
              "(knowledge/journey/01-first-touch.md)"]
    return subject, "\n".join(lines)


def render(template: str, props: dict) -> str:
    """{{token}} merge over contact properties, then the outbound style rule:
    no em dashes or double hyphens in anything customer-facing (CLAUDE.md,
    Roman 2026-08-24, locked)."""
    out = template
    for k, v in (props or {}).items():
        out = out.replace("{{" + k + "}}", str(v or ""))
    out = re.sub(r"\{\{\w+\}\}", "", out)
    return out.replace("—", ", ").replace("--", ", ")


# ── runner ─────────────────────────────────────────────────────────
def run(live: bool, since: str = "", only_contact: str = "", report_path: str = "") -> dict:
    from src import presend                       # noqa: E402  the one gate
    from src import hubspot_client as hs          # noqa: E402  the one client
    from src.config import staff                  # noqa: E402

    c = cfg()
    report: dict = {"at": datetime.now(timezone.utc).isoformat(), "live": live,
                    "baselined": False, "considered": 0, "alerts": [], "spam": [], "skipped": []}

    cursor = since or _load(CURSOR_FILE, {}).get("recent_conversion_date", "")
    processed = set(_load(PROCESSED_FILE, []))

    look_h = int(c.get("baseline_lookback_hours") or 24)
    floor = (datetime.now(timezone.utc) - timedelta(hours=look_h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = fetch_conversions(hs, cursor or floor, only_contact)
    report["considered"] = len(rows)

    # Fleet guard: the first ever run stamps the cursor and creates nothing.
    if not cursor and not since:
        newest = max([(r.get("properties") or {}).get("recent_conversion_date") or "" for r in rows],
                     default=floor)
        _save(CURSOR_FILE, {"recent_conversion_date": newest, "baselined_at": report["at"]})
        report["baselined"] = True
        print(f"baseline stamped at {newest}; {len(rows)} conversions suppressed, nothing created")
        return _finish(report, report_path)

    picked = select(rows, cursor, processed, c)
    if len(picked) > int(c.get("max_leads_per_run") or 25):
        raise SystemExit(f"ABORT before any write: {len(picked)} leads in one run exceeds "
                         f"max_leads_per_run={c.get('max_leads_per_run')}. Investigate, then raise the cap.")

    phone_counts = Counter(norm_phone((r.get("properties") or {}).get("phone") or "") for r in rows)
    phone_counts.pop("", None)
    tpl = (HERE / "templates" / "first-touch-family.txt").read_text()

    for r in picked:
        cid, p = str(r.get("id")), (r.get("properties") or {})
        key = f"{cid}:{p.get('recent_conversion_date')}"
        spam = is_spam(p, phone_counts, c)
        if spam:
            report["spam"].append({"contact": cid, "reason": spam})
            processed.add(key)
            continue

        audience = classify(p)
        r_cfg = route(audience, c)
        seat_key = r_cfg.get("seat") or "charter_sales"
        seat = staff(seat_key) or {}
        try:
            deals = hs.get_contact_deals(cid)
        except Exception as e:                    # noqa: BLE001
            deals = []
            print(f"  ⚠️  could not read deals for {cid}: {e}")
        returning = returning_summary(deals)

        draft = render(tpl, {**p, "seat_first": (seat.get("name") or seat_key).split()[0]})
        gate = presend.check(cid, "sms", r_cfg.get("line") or "charter_sales",
                             r_cfg.get("purpose") or "lead_first_touch",
                             phone=p.get("phone") or "", contact=r, body=draft)

        subject, body = alert_task(r, audience, seat.get("name") or seat_key, gate, returning, draft)
        due = datetime.now(timezone.utc) + timedelta(hours=float(r_cfg.get("sla_hours") or 1.5))
        row = {"contact": cid, "audience": audience, "seat": seat_key,
               "verdict": gate.verdict, "reasons": gate.reasons, "returning": bool(returning),
               "due": due.isoformat(), "subject": subject}

        if live:
            hs.create_task(subject, body, seat.get("hubspot_owner_id"),
                           int(due.timestamp() * 1000), contact_id=cid)
            hs.add_contact_note(cid, "[Agent] first touch (ops/lead_intake) — stage 01\n" + body)
            # No lead-status write. Only a real call may move a contact off
            # New (Inbox); see F1 in the module docstring.
            processed.add(key)
        report["alerts"].append(row)
        print(f"{gate.verdict.upper():5} | {subject} | seat {seat_key} | "
              f"{'RETURNING' if returning else 'new'} | due {due:%Y-%m-%d %H:%M}Z")

    if live and picked:
        newest = (picked[-1].get("properties") or {}).get("recent_conversion_date") or cursor
        _save(CURSOR_FILE, {"recent_conversion_date": newest, "updated_at": report["at"]})
        _save(PROCESSED_FILE, sorted(processed)[-5000:])
    return _finish(report, report_path)


def fetch_conversions(hs, since_iso: str, only_contact: str = "") -> list[dict]:
    """Contacts whose recent_conversion_date is newer than `since_iso`.

    This IS the fix for F5 and F7: no form GUID list, no exit goal, no memory of
    what the contact did in 2023."""
    props = ["firstname", "lastname", "email", "phone", "mobilephone", "a_persona",
             "hs_lead_status", "hubspot_owner_id", "lifecyclestage",
             "recent_conversion_event_name", "recent_conversion_date",
             "sms_opt_out", "hs_email_optout", "agent_last_outbound_at",
             "agent_last_outbound_seat", "agent_last_inbound_at"]
    if only_contact:
        return [hs._get(f"/crm/v3/objects/contacts/{only_contact}", {"properties": ",".join(props)})]
    return hs._search_all("/crm/v3/objects/contacts/search",
                          [{"propertyName": "recent_conversion_date",
                            "operator": "GT", "value": since_iso}], props)


def _finish(report: dict, path: str) -> dict:
    if path:
        Path(path).write_text(json.dumps(report, indent=1) + "\n")
    n = len(report["alerts"])
    print(f"\n{n} alert(s), {len(report['spam'])} spam, "
          f"{sum(1 for a in report['alerts'] if a['returning'])} returning "
          f"{'(DRY RUN, nothing written)' if not report['live'] else ''}")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="write tasks and notes (default: dry run)")
    ap.add_argument("--dry-run", action="store_true", help="explicit dry run (the default)")
    ap.add_argument("--since", default="", help="ISO cursor override, e.g. 2026-09-01T00:00:00Z")
    ap.add_argument("--contact", default="", help="one contact id, for verification")
    ap.add_argument("--report-json", default="")
    a = ap.parse_args()
    if cfg().get("send"):
        raise SystemExit("config.send is true, but stages 00 and 01 are not REVIEWED. "
                         "See knowledge/journey/README.md. Refusing to run.")
    run(live=a.live and not a.dry_run, since=a.since, only_contact=a.contact,
        report_path=a.report_json)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Network half of ops/lead_agent: build the dossier, run the decision, execute.

Kept separate from lead_agent.py so the guardrails can be unit-tested with no
network and no API key.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lead_agent import (CURSOR, HERE, PT, cfg, decide, enforce, evidence_ok,  # noqa: F401
                        in_window, task_from)

PROPS = ["firstname", "lastname", "email", "phone", "mobilephone", "a_persona",
         "hs_lead_status", "hubspot_owner_id", "lifecyclestage", "student_school",
         "recent_conversion_event_name", "recent_conversion_date", "num_associated_deals",
         "sms_opt_out", "hs_email_optout", "hs_email_last_email_name", "hs_email_last_send_date",
         "agent_last_outbound_at", "agent_last_outbound_seat", "agent_last_inbound_at",
         "notes_last_contacted", "num_contacted_notes"]


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")


def audience(props: dict) -> str:
    persona = props.get("a_persona") or ""
    if "Tutors" in persona:
        return "tutor"
    if "Teacher of Record" in persona:
        return "tor"
    if "Decision Maker" in persona:
        return "decision_maker"
    status = props.get("hs_lead_status") or ""
    if status == "Charter School Teacher TOR/EF":
        return "tor"
    if status == "Teacher in a School":
        return "decision_maker"
    return "family"


def build_dossier(hs, presend, cid: str, row: dict, c: dict) -> dict:
    """Everything we know about this person, as facts. The agent reasons over
    this and nothing else, so anything missing here is invisible to it."""
    p = row.get("properties") or {}
    now = datetime.now(timezone.utc)
    conv = p.get("recent_conversion_date") or ""

    def _after(items, key="createdate"):
        return [i for i in items if ((i.get("properties") or i).get(key) or "") >= conv]

    try:
        deals = hs.get_contact_deals(cid)
    except Exception as e:                                        # noqa: BLE001
        deals, _ = [], print(f"  deals unreadable for {cid}: {e}")
    calls = hs.recent_calls_for_contact(cid, int((now - timedelta(days=60)).timestamp() * 1000), limit=10)
    calls_out = [k for k in calls if ((k.get("properties") or {}).get("hs_call_direction") or "") == "OUTBOUND"]
    connected = [k for k in calls
                 if float((k.get("properties") or {}).get("hs_call_duration") or 0) >= 60000]
    meetings_after = _after(hs._search_all("/crm/v3/objects/meetings/search",
                                           [{"propertyName": "hs_createdate", "operator": "GT", "value": conv}],
                                           ["hs_meeting_title", "hs_createdate"]) if conv else [], "hs_createdate")

    replied = presend.has_replied_since(cid, p.get("phone") or "", conv or
                                        (now - timedelta(days=30)).isoformat())
    last_out = p.get("agent_last_outbound_at")
    hours_since = None
    if last_out:
        try:
            hours_since = (now - datetime.fromtimestamp(int(last_out) / 1000, tz=timezone.utc)).total_seconds() / 3600
        except (TypeError, ValueError):
            hours_since = None

    prior = [d for d in deals if (d.get("properties") or d).get("start_of_tutoring_for_this_deal")]
    returning = ""
    if prior:
        names = [((d.get('properties') or d).get('dealname') or '') for d in prior][:3]
        returning = (f"RETURNING FAMILY: {len(prior)} prior deal(s) where tutoring started "
                     f"({'; '.join(n for n in names if n)}). They know us. Do not introduce A+ from scratch.")

    return {
        "now": now.isoformat(),
        "contact": {k: p.get(k) for k in PROPS if p.get(k)},
        "audience": audience(p),
        "submitted_at": conv,
        "hours_since_submit": round((now - datetime.fromisoformat(conv.replace("Z", "+00:00"))).total_seconds() / 3600, 1)
        if conv else None,
        "returning": returning,
        "history": {
            "deals": [{"name": (d.get("properties") or d).get("dealname"),
                       "created": (d.get("properties") or d).get("createdate"),
                       "tutoring_started": (d.get("properties") or d).get("start_of_tutoring_for_this_deal")}
                      for d in deals],
            "calls": [{"title": (k.get("properties") or {}).get("hs_call_title"),
                       "at": (k.get("properties") or {}).get("hs_timestamp"),
                       "seconds": round(float((k.get("properties") or {}).get("hs_call_duration") or 0) / 1000)}
                      for k in calls],
            "meetings_since_submit": [(m.get("properties") or {}).get("hs_meeting_title") for m in meetings_after],
            "last_marketing_email": p.get("hs_email_last_email_name"),
        },
        "evidence": {                    # what enforce() checks a status against
            "calls_outbound": len(calls_out),
            "calls_connected": len(connected),
            "meetings": len(meetings_after),
            "deals": len(deals),
            "replied": 1 if (replied.get("latest") or "") else 0,
        },
        "replies": {"latest": replied.get("latest"), "email": len(replied.get("email") or []),
                    "sms": len(replied.get("sms") or []), "errors": replied.get("errors")},
        "touches": {"outbound_today": 0, "hours_since_last_outbound": hours_since,
                    "last_seat": p.get("agent_last_outbound_seat")},
        "in_thread": bool(replied.get("latest")),
    }


def run(live: bool, only_contact: str = "", since: str = "", report_path: str = "") -> dict:
    from src import hubspot_client as hs, presend      # noqa: E402
    from src.config import staff                       # noqa: E402

    c = cfg()
    now = datetime.now(timezone.utc)
    report = {"at": now.isoformat(), "live": live, "send_enabled": bool(c.get("send")), "decisions": []}

    floor = (now - timedelta(hours=int(c.get("lookback_hours") or 72))).strftime("%Y-%m-%dT%H:%M:%SZ")
    cursor = since or _load(CURSOR, {}).get("recent_conversion_date") or floor
    if only_contact:
        rows = [hs._get(f"/crm/v3/objects/contacts/{only_contact}", {"properties": ",".join(PROPS)})]
    else:
        rows = hs._search_all("/crm/v3/objects/contacts/search",
                              [{"propertyName": "recent_conversion_date", "operator": "GT", "value": cursor}],
                              PROPS)
    if len(rows) > int(c.get("max_leads_per_run") or 25):
        raise SystemExit(f"ABORT before any write: {len(rows)} leads exceeds max_leads_per_run")

    for row in rows:
        cid = str(row.get("id"))
        dossier = build_dossier(hs, presend, cid, row, c)
        r = (c.get("routing") or {}).get(dossier["audience"]) or {}
        seat = staff(r.get("seat") or "charter_sales") or {}
        dossier["seat"] = {"key": r.get("seat"), "name": seat.get("name"), "line": r.get("line")}
        dossier["booking_link"] = c.get("booking_link") or "(none configured — do not offer a link)"

        gate = presend.check(cid, "sms", r.get("line") or "charter_sales",
                             r.get("purpose") or "lead_first_touch",
                             phone=(row.get("properties") or {}).get("phone") or "", contact=row)
        dossier["gate"] = {"verdict": gate.verdict, "reasons": gate.reasons,
                           "owner": (gate.owner or {}).get("name")}

        decision = decide(dossier, c)
        if gate.verdict != "allow" and decision.get("action") in ("send_sms", "send_email"):
            decision["action"] = "create_task"
            held = [f"pre-send {gate.verdict}: {r_}" for r_ in gate.reasons]
        else:
            held = []
        decision, notes = enforce(decision, dossier, c, now=now)
        notes = held + notes

        rowout = {"contact": cid, "name": dossier["contact"].get("firstname", ""),
                  "audience": dossier["audience"], "action": decision["action"],
                  "why": decision.get("why"), "confidence": decision.get("confidence"),
                  "held_back": notes, "gate": gate.verdict}
        report["decisions"].append(rowout)
        print(f"{decision['action']:12} | {dossier['contact'].get('firstname','?'):12} | "
              f"{decision.get('confidence','?'):6} | {decision.get('why','')[:70]}")

        if not live:
            continue
        if decision["action"] == "set_status":
            hs.patch_contact_props(cid, {"hs_lead_status": decision["new_status"]})
        elif decision["action"] in ("create_task", "handoff"):
            subj, body = task_from(decision, dossier, notes)
            due = now + timedelta(hours=float(r.get("sla_hours") or 1.5))
            hs.create_task(subj, body, seat.get("hubspot_owner_id"),
                           int(due.timestamp() * 1000), contact_id=cid)
        hs.add_contact_note(cid, "[Agent] lead_agent decision\n" + json.dumps(decision, indent=1))

    if live and rows and not only_contact:
        newest = max((r.get("properties") or {}).get("recent_conversion_date") or "" for r in rows)
        _save(CURSOR, {"recent_conversion_date": newest or cursor, "updated_at": now.isoformat()})
    if report_path:
        Path(report_path).write_text(json.dumps(report, indent=1) + "\n")
    print(f"\n{len(report['decisions'])} decision(s){'' if live else ' (PLAN ONLY, nothing written)'}")
    return report

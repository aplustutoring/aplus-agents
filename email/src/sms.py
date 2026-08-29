"""Agent-owned transactional SMS — replaces the HubSpot workflow chain
(#AP pending, Roman 2026-08-28: "all our texts are tied to workflows, can we
use agents instead" → LFG).

Why: the workflow path (agent stamps deal → stage-copy workflow stamps the
contact → contact-based flow enrolls, branches, texts, clears the stamp) died
silently on 2026-08-13 and nobody knew for two weeks. This sweep is the same
logic in versioned, tested, loudly-failing code — and because it watches
DEALS (not agent actions), manually created deals get texted too, which the
workflow chain never handled for the Free Trial pipeline.

Runs from deal_sync.run() every ~15 min. For each Pre-Lesson deal in a
configured pipeline created after sms.start_date:

  tutored == "Yes"  → text the family now
  tutored == "No"   → alert the deal's owner first; text on a LATER cycle
                      (>= one sweep apart — the workflow's delay semantics)
  tutored unset     → skip once, audited (po_inbox already gap-DMs these)

Guardrails: one text per deal ever (audit key), one text per FAMILY per 24h
(multi-PO emails create 4 deals — the family gets ONE text), quiet hours
(PT), start-date fence (never texts pre-cutover backlog), opt-out property
respected, em-dash scrub, DRY_RUN, 3-strike send retry then a Slack flag.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from . import audit, hubspot_client as hs, slack_client
from .business_hours import now_la
from .config import DRY_RUN, JUSTCALL_API_KEY, JUSTCALL_API_SECRET, cfg, staff
from .gmail_client import _scrub_outbound

JC_BASE = "https://api.justcall.io"


def _jc_send(to_number: str, body: str) -> dict:
    """One SMS via JustCall (the line schedulers already answer — replies land
    in the same JustCall threads they handle today)."""
    sc = cfg().get("sms", {})
    payload = {"justcall_number": sc.get("justcall_number"),
               "contact_number": to_number, "body": body}
    if DRY_RUN:
        print(f"[DRY_RUN] justcall SMS -> {to_number}: {body[:80]}")
        return {"dry_run": True}
    r = requests.post(f"{JC_BASE}/v2.1/texts/new",
                      headers={"Authorization": f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}",
                               "Accept": "application/json"},
                      json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def _in_send_window(now=None) -> bool:
    sc = cfg().get("sms", {})
    local = (now or now_la())
    return int(sc.get("send_hour_start_pt", 8)) <= local.hour < int(sc.get("send_hour_end_pt", 20))


def _sms_records() -> dict:
    """Audit-derived state: {kind:{deal_id: last_ts}} + per-contact last send."""
    state = {"sent": {}, "alerted": {}, "skipped": {}, "errors": {}, "contact_sent": {}}
    for r in audit._iter_records():
        act, did = r.get("action_taken", ""), str(r.get("deal_id") or "")
        ts = str(r.get("timestamp") or "")
        if act == "sms_sent":
            state["sent"][did] = ts
            cid = str(r.get("contact_id") or "")
            if cid:
                state["contact_sent"][cid] = max(state["contact_sent"].get(cid, ""), ts)
        elif act == "sms_staff_alerted":
            state["alerted"][did] = ts
        elif act == "sms_skipped_unverified":
            state["skipped"][did] = ts
        elif act == "sms_error":
            state["errors"][did] = state["errors"].get(did, 0) + 1
    return state


def _family_phone(contact: dict) -> str:
    p = (contact or {}).get("properties") or {}
    return (p.get("mobilephone") or p.get("phone") or "").strip()


def _pre_lesson_deals(pipeline_id: str, start_ms: int) -> list[dict]:
    out, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
                    {"propertyName": "pipeline", "operator": "EQ", "value": pipeline_id},
                    {"propertyName": "createdate", "operator": "GTE", "value": str(start_ms)}]}],
                "properties": ["dealname", "pipeline", "dealstage", "createdate",
                               "schedule_preferences", "hubspot_owner_id",
                               "is_the_family_currently_being_tutored_by_us_"],
                "limit": 100}
        if after:
            body["after"] = after
        res = hs._write("POST", "/crm/v3/objects/deals/search", body)
        for d in res.get("results", []):
            label = hs.stage_label(pipeline_id, (d["properties"] or {}).get("dealstage")).lower()
            if "pre-lesson" in label:
                out.append(d)
        after = ((res.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    return out


def run_sweep() -> None:
    sc = cfg().get("sms", {})
    if not sc.get("enabled") or not sc.get("pipelines"):
        return
    if not _in_send_window():
        return                          # retried next cycle — nothing is lost
    try:
        start = datetime.fromisoformat(sc["start_date"]).replace(
            tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        print("sms: start_date missing/unparseable — sweep disabled (the fence "
              "against texting the backlog is mandatory)")
        return
    start_ms = int(start.timestamp() * 1000)
    state = _sms_records()
    now_iso = datetime.now(timezone.utc).isoformat()
    sent = 0
    for pipeline_id, pconf in (sc.get("pipelines") or {}).items():
        template = (sc.get("templates") or {}).get((pconf or {}).get("template") or "")
        if not template:
            print(f"sms: pipeline {pipeline_id} has no template — skipped")
            continue
        for d in _pre_lesson_deals(pipeline_id, start_ms):
            did = str(d["id"])
            p = d.get("properties") or {}
            if did in state["sent"] or did in state["skipped"] \
                    or state["errors"].get(did, 0) >= 3:
                continue
            tutored = (p.get("is_the_family_currently_being_tutored_by_us_") or "").strip()
            if tutored not in ("Yes", "No"):
                audit.append({"message_id": f"sms-skip:{did}", "source": "sms",
                              "action_taken": "sms_skipped_unverified", "deal_id": did,
                              "deal_name": p.get("dealname")})
                continue
            from .deal_sync import _deal_contact
            contact = _deal_contact(did, p.get("dealname") or "")
            cid = str((contact or {}).get("id") or "")
            full = {}
            if cid:
                try:
                    full = hs._get(f"/crm/v3/objects/contacts/{cid}",
                                   {"properties": "firstname,phone,mobilephone,"
                                                  + (sc.get("opt_out_property") or "phone")})
                except Exception:  # noqa: BLE001
                    full = {}
            phone = _family_phone(full)
            if not cid or not phone:
                audit.append({"message_id": f"sms-skip:{did}", "source": "sms",
                              "action_taken": "sms_skipped_unverified", "deal_id": did,
                              "deal_name": p.get("dealname"), "reason": "no family phone"})
                continue
            opt_prop = sc.get("opt_out_property")
            if opt_prop and str(((full.get("properties") or {}).get(opt_prop) or "")).lower() \
                    in ("true", "yes", "1"):
                audit.append({"message_id": f"sms-skip:{did}", "source": "sms",
                              "action_taken": "sms_skipped_unverified", "deal_id": did,
                              "reason": "opted out"})
                continue
            # "No" = unbooked month: staff alert first, text on a LATER sweep
            if tutored == "No" and did not in state["alerted"]:
                owner = _owner_staff(p.get("hubspot_owner_id"))
                target = owner or staff(sc.get("fallback_alert", "charter_admin"))
                if target.get("slack_user_id"):
                    try:
                        slack_client.dm(target["slack_user_id"],
                                        f"📅 New PO, month not booked — {p.get('dealname')}. "
                                        f"The family gets the schedule-confirmation text on "
                                        f"the next sweep (~15 min); get ahead of it if you "
                                        f"want to call first.")
                    except Exception as e:  # noqa: BLE001
                        print(f"  ⚠️  sms staff alert failed (non-fatal): {e}")
                audit.append({"message_id": f"sms-alert:{did}", "source": "sms",
                              "action_taken": "sms_staff_alerted", "deal_id": did,
                              "deal_name": p.get("dealname")})
                continue
            # one text per FAMILY per 24h — a 4-PO email makes 4 deals, not 4 texts
            last = state["contact_sent"].get(cid, "")
            if last and last > (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat():
                audit.append({"message_id": f"sms-sent:{did}", "source": "sms",
                              "action_taken": "sms_sent", "deal_id": did, "contact_id": cid,
                              "deduped_with_recent_family_text": True})
                continue
            first = ((full.get("properties") or {}).get("firstname") or "there").strip()
            sched = (p.get("schedule_preferences") or "").strip() \
                or cfg()["po_inbox"].get("schedule_ask_fallback", "")
            body = _scrub_outbound(template.format(first_name=first,
                                                   schedule_preferences=sched))
            try:
                _jc_send(phone, body)
            except Exception as e:  # noqa: BLE001
                audit.append({"message_id": f"sms-error:{did}:{state['errors'].get(did, 0)}",
                              "source": "sms", "action_taken": "sms_error",
                              "deal_id": did, "error": str(e)[:200]})
                if state["errors"].get(did, 0) + 1 >= 3:
                    s = staff(sc.get("fallback_alert", "charter_admin"))
                    if s.get("slack_user_id"):
                        slack_client.dm(s["slack_user_id"],
                                        f"⚠️ SMS failed 3x for '{p.get('dealname')}' "
                                        f"({phone}) — text the family manually.")
                continue
            audit.append({"message_id": f"sms-sent:{did}", "source": "sms",
                          "action_taken": "sms_sent", "deal_id": did, "contact_id": cid,
                          "deal_name": p.get("dealname"), "to": phone,
                          "timestamp": now_iso})
            state["contact_sent"][cid] = now_iso
            sent += 1
    print(f"sms: sweep done, {sent} text(s) sent")


def _owner_staff(owner_id) -> dict:
    for rec in (cfg().get("staff") or {}).values():
        if str(rec.get("hubspot_owner_id") or "") == str(owner_id or ""):
            return rec
    return {}

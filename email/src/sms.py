"""Agent-owned transactional SMS — replaces the HubSpot workflow chain
(Roman 2026-08-28: "all our texts are tied to workflows, can we use agents
instead" → LFG; copy + rules locked 2026-09-01).

Why: the workflow path (agent stamps deal → stage-copy workflow stamps the
contact → contact-based flow enrolls, branches, texts, clears the stamp) died
silently on 2026-08-13 and nobody knew for two weeks. This sweep is the same
job in versioned, tested, loudly-failing code — and because it watches DEALS
(not agent actions), manually created deals get texted too.

Runs from deal_sync.run() every ~15 min. Qualifying deals (Pre-Lesson, in a
configured pipeline, created after sms.start_date) are GROUPED BY FAMILY —
one text per family naming every kid with a fresh PO (Roman 2026-09-01:
"name the kid"; a 2-PO day for two siblings is ONE message, not two).

Message choice is driven by what we KNOW (Roman-approved copy, brand voice):
  schedule on file      → CONFIRM variant ("does this still work: ...")
  no schedule           → ASK variant ("what days and times work best")
The old flow jammed the ask-fallback string into the confirm sentence and
shipped incoherent texts for months — the variants exist so that can't recur.

The tutored property routes the STAFF side only: any deal marked "No" (month
unbooked) DMs the deal's owner first and the family texts on the NEXT sweep;
"unset" no longer suppresses the text (the intake gap DM already fired) — the
ask variant needs no verification. Pending-approval OAs text normally
(Roman: "if it says pending approval for us it means approved").

Guardrails: one text per deal ever, one per FAMILY per 24h, quiet hours
8am-8pm PT, hard start_date fence over the backlog, opt-out hook, em-dash
scrub, 3-strike send retry then a manual-text flag.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from . import audit, hubspot_client as hs, slack_client
from .business_hours import now_la
from .config import (DRY_RUN, JUSTCALL_API_KEY, JUSTCALL_API_SECRET,
                     RESEND_API_KEY, ROOT, cfg, staff)
from .gmail_client import _scrub_outbound

JC_BASE = "https://api.justcall.io"


def _jc_send(to_number: str, body: str) -> dict:
    """One SMS via JustCall (the line schedulers already answer — replies land
    in the same JustCall threads they handle today)."""
    sc = cfg().get("sms", {})
    payload = {"justcall_number": sc.get("justcall_number"),
               "contact_number": to_number, "body": body}
    if DRY_RUN:
        print(f"[DRY_RUN] justcall SMS -> {to_number}: {body[:100]}")
        return {"dry_run": True}
    r = requests.post(f"{JC_BASE}/v2.1/texts/new",
                      headers={"Authorization": f"{JUSTCALL_API_KEY}:{JUSTCALL_API_SECRET}",
                               "Accept": "application/json"},
                      json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def _send_welcome(to_email: str, first_name: str) -> None:
    """The "What to Expect (Charter)" onboarding email, sent via RESEND the
    moment the family texts (Roman 2026-09-03, Option A — amending the
    only-outbound-email rule: tutor-doc receipt PLUS this). Lifetime stats
    earned the rebuild: 58% opens, real replies, zero spam over 432 sends;
    it went dark with the flow on Aug 13. Why Resend and not HubSpot's
    single-send: the portal lacks the transactional-email scope (probed live,
    MISSING_SCOPES), and Resend already sends for this verified domain (the
    booth agent). Replies go to admin@ — the triage agent's own inbox — and
    the HubSpot BCC log address puts every send on the contact's timeline.
    Consent suppression is gone too: the old flow silently withheld this from
    ~70 families for missing MARKETING consent; a received-your-PO email is
    transactional and now always sends."""
    sc = cfg().get("sms", {})
    wc = sc.get("welcome") or {}
    tpl_path = ROOT / (wc.get("template") or "templates/welcome_charter.html")
    html = tpl_path.read_text().replace("__FIRST_NAME__", first_name or "Parent")
    payload = {"from": wc.get("from", "A+ Tutoring Success Team <admin@wetutorathome.com>"),
               "to": [to_email],
               "reply_to": wc.get("reply_to", "admin@wetutorathome.com"),
               "subject": wc.get("subject",
                                 "We received your PO! Ready to Launch: Next Steps"),
               "html": html}
    bcc = (cfg().get("hubspot") or {}).get("bcc_log_address")
    if bcc:
        payload["bcc"] = [bcc]
    if DRY_RUN:
        print(f"[DRY_RUN] resend welcome -> {to_email}")
        return
    r = requests.post("https://api.resend.com/emails",
                      headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                      json=payload, timeout=30)
    r.raise_for_status()


def _in_send_window(now=None) -> bool:
    sc = cfg().get("sms", {})
    local = (now or now_la())
    return int(sc.get("send_hour_start_pt", 8)) <= local.hour < int(sc.get("send_hour_end_pt", 20))


def _sms_records() -> dict:
    """Audit-derived state: per-deal markers + per-contact last send."""
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
                               "student_first_name",
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


def _student_first(props: dict) -> str:
    """The kid's first name — the stamped property, else the deal-name segment."""
    sf = (props.get("student_first_name") or "").strip()
    if sf:
        return sf.split()[0]
    parts = [p.strip() for p in (props.get("dealname") or "").split(" - ")]
    return parts[1].split()[0] if len(parts) > 1 and parts[1] else ""


def _fmt_students(names: list[str]) -> str:
    """'Ana' / 'Ana and Bo' / 'Ana, Bo and Cy'."""
    if not names:
        return "your student"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _family_schedule(deals: list[dict]) -> str:
    """The first REAL schedule among the family's deals — the ask-fallback
    string is a request for a schedule, never a schedule."""
    fallback = (cfg()["po_inbox"].get("schedule_ask_fallback") or "").strip().lower()
    for d in deals:
        s = ((d.get("properties") or {}).get("schedule_preferences") or "").strip()
        if s and s.lower() != fallback:
            return s
    return ""


def _pick_template(sc: dict, base: str, multi: bool, know_sched: bool) -> str:
    key = f"{base}_{'multi_' if multi else ''}{'confirm' if know_sched else 'ask'}"
    return (sc.get("templates") or {}).get(key, "")


def _owner_staff(owner_id) -> dict:
    for rec in (cfg().get("staff") or {}).values():
        if str(rec.get("hubspot_owner_id") or "") == str(owner_id or ""):
            return rec
    return {}


def run_sweep() -> None:
    sc = cfg().get("sms", {})
    if not sc.get("enabled") or not sc.get("pipelines"):
        return
    if not _in_send_window():
        return                          # retried next cycle — nothing is lost
    try:
        start = datetime.fromisoformat(sc["start_date"]).replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        print("sms: start_date missing/unparseable — sweep disabled (the fence "
              "against texting the backlog is mandatory)")
        return
    start_ms = int(start.timestamp() * 1000)
    state = _sms_records()
    now_iso = datetime.now(timezone.utc).isoformat()
    sent = 0

    # ── collect qualifying deals per family ──────────────────────
    from .deal_sync import _deal_contact
    families: dict = {}   # cid -> {"contact":…, "deals":[…], "template":base}
    for pipeline_id, pconf in (sc.get("pipelines") or {}).items():
        base = (pconf or {}).get("template") or ""
        if not base:
            print(f"sms: pipeline {pipeline_id} has no template — skipped")
            continue
        for d in _pre_lesson_deals(pipeline_id, start_ms):
            did = str(d["id"])
            if did in state["sent"] or state["errors"].get(did, 0) >= 3:
                continue
            contact = _deal_contact(did, (d.get("properties") or {}).get("dealname") or "")
            cid = str((contact or {}).get("id") or "")
            if not cid:
                if did not in state["skipped"]:
                    audit.append({"message_id": f"sms-skip:{did}", "source": "sms",
                                  "action_taken": "sms_skipped_unverified", "deal_id": did,
                                  "reason": "no family contact on deal"})
                continue
            fam = families.setdefault(cid, {"deals": [], "template": base})
            fam["deals"].append(d)

    # ── one decision + at most one text per family ───────────────
    for cid, fam in families.items():
        deals = fam["deals"]
        dids = [str(d["id"]) for d in deals]
        props = [d.get("properties") or {} for d in deals]
        try:
            full = hs._get(f"/crm/v3/objects/contacts/{cid}",
                           {"properties": "firstname,email,phone,mobilephone,"
                                          + (sc.get("opt_out_property") or "phone")})
        except Exception:  # noqa: BLE001
            full = {}
        phone = _family_phone(full)
        if not phone:
            for did in dids:
                if did not in state["skipped"]:
                    audit.append({"message_id": f"sms-skip:{did}", "source": "sms",
                                  "action_taken": "sms_skipped_unverified", "deal_id": did,
                                  "reason": "no family phone"})
            continue
        opt_prop = sc.get("opt_out_property")
        if opt_prop and str(((full.get("properties") or {}).get(opt_prop) or "")).lower() \
                in ("true", "yes", "1"):
            for did in dids:
                if did not in state["skipped"]:
                    audit.append({"message_id": f"sms-skip:{did}", "source": "sms",
                                  "action_taken": "sms_skipped_unverified", "deal_id": did,
                                  "reason": "opted out"})
            continue
        # tutored routes the STAFF side only: a "No" month gets the owner a
        # heads-up first; the family texts on the NEXT sweep.
        unbooked = [d for d, p in zip(deals, props)
                    if (p.get("is_the_family_currently_being_tutored_by_us_") or "") == "No"]
        unalerted = [d for d in unbooked if str(d["id"]) not in state["alerted"]]
        if unalerted:
            owner = _owner_staff((unalerted[0].get("properties") or {}).get("hubspot_owner_id"))
            target = owner or staff(sc.get("fallback_alert", "charter_admin"))
            names = _fmt_students(sorted({_student_first(p) for p in props} - {""}))
            if target.get("slack_user_id"):
                try:
                    parent = (props[0].get('dealname') or '').split(' - ')[0]
                    slack_client.dm(target["slack_user_id"],
                                    f"📅 New PO for {names} (parent: {parent}). No lessons "
                                    f"are on the calendar for them yet. In about 15 minutes "
                                    f"the family will automatically get a text asking what "
                                    f"days and times work. If you'd rather call them first, "
                                    f"now is your window.")
                except Exception as e:  # noqa: BLE001
                    print(f"  ⚠️  sms staff alert failed (non-fatal): {e}")
            for d in unalerted:
                audit.append({"message_id": f"sms-alert:{d['id']}", "source": "sms",
                              "action_taken": "sms_staff_alerted", "deal_id": str(d["id"]),
                              "deal_name": (d.get("properties") or {}).get("dealname")})
            continue
        # one text per FAMILY per 24h — siblings and multi-PO days collapse
        last = state["contact_sent"].get(cid, "")
        if last and last > (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat():
            for did in dids:
                audit.append({"message_id": f"sms-sent:{did}", "source": "sms",
                              "action_taken": "sms_sent", "deal_id": did, "contact_id": cid,
                              "deduped_with_recent_family_text": True})
            continue
        students = sorted({_student_first(p) for p in props} - {""})
        sched = _family_schedule(deals)
        template = _pick_template(sc, fam["template"], len(students) > 1, bool(sched))
        if not template:
            print(f"sms: no template for family {cid} "
                  f"(multi={len(students) > 1}, sched={bool(sched)}) — skipped")
            continue
        first = ((full.get("properties") or {}).get("firstname") or "there").strip()
        body = _scrub_outbound(template.format(
            first_name=first, student=_fmt_students(students[:1]),
            students=_fmt_students(students), schedule=sched))
        try:
            _jc_send(phone, body)
        except Exception as e:  # noqa: BLE001
            for did in dids:
                audit.append({"message_id": f"sms-error:{did}:{state['errors'].get(did, 0)}",
                              "source": "sms", "action_taken": "sms_error",
                              "deal_id": did, "error": str(e)[:200]})
            if state["errors"].get(dids[0], 0) + 1 >= 3:
                s = staff(sc.get("fallback_alert", "charter_admin"))
                if s.get("slack_user_id"):
                    slack_client.dm(s["slack_user_id"],
                                    f"⚠️ SMS failed 3x for {_fmt_students(students)} "
                                    f"({phone}) — text the family manually.")
            continue
        # the welcome email rides the SAME event: one family, one text, one
        # "What to Expect" email. A failed email never voids the text (audited
        # + flagged instead), and the family markers below dedupe both.
        pconf2 = (sc.get("pipelines") or {}).get(
            deals[0]["properties"].get("pipeline") or "")
        wants_welcome = isinstance(pconf2, dict) and pconf2.get("welcome")
        to_email = ((full.get("properties") or {}).get("email") or "").strip()
        welcome = ""
        if wants_welcome and to_email:
            try:
                _send_welcome(to_email, first)
                welcome = to_email
            except Exception as e:  # noqa: BLE001 — email must never void the text
                audit.append({"message_id": f"welcome-error:{dids[0]}", "source": "sms",
                              "action_taken": "welcome_email_error", "deal_id": dids[0],
                              "contact_id": cid, "error": str(e)[:200]})
                st = staff(sc.get("fallback_alert", "charter_admin"))
                if st.get("slack_user_id"):
                    try:
                        slack_client.dm(st["slack_user_id"],
                                        f"⚠️ What-to-Expect email failed for "
                                        f"{_fmt_students(students)} ({to_email}) — the "
                                        f"schedule text DID send; forward the welcome "
                                        f"email manually. Error: {str(e)[:120]}")
                    except Exception:  # noqa: BLE001
                        pass
        for did in dids:
            audit.append({"message_id": f"sms-sent:{did}", "source": "sms",
                          "action_taken": "sms_sent", "deal_id": did, "contact_id": cid,
                          "to": phone, "body": body[:300],
                          "welcome_email_to": welcome, "timestamp": now_iso})
        state["contact_sent"][cid] = now_iso
        sent += 1
    print(f"sms: sweep done, {sent} text(s) sent")

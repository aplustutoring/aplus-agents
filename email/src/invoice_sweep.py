"""PO invoice-timing sweep — the "smart prompt" for Kath.

Once a day (time-gated inside the deal-sync schedule): for every ACTIVE charter
deal carrying a PO, compare the student's Teachworks hours USED since the deal
was created against the PO's hours (number_of_hours_in_this_po):

  hours exhausted           → prompt Kath to submit the invoice NOW
  else invoice due date hit → prompt on the date (end of the PO's service month,
                              from the deal's due property or the deal-name tag
                              like '(Aug) 26/27')

Read-only against Teachworks/HubSpot + one Slack DM; one prompt per deal ever
(audit key invoice-prompt:{deal_id}).
"""
from __future__ import annotations

import re
from datetime import datetime

from . import audit, hubspot_client as hs, slack_client, teachworks_client as tw
from .business_hours import now_la
from .config import cfg
from .po_inbox import _po_month_end

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_NAME_TAG = re.compile(r"\((jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\)"
                       r"\s*(\d{2})/(\d{2})", re.I)


def _dealname_month_end(dealname: str):
    """Invoice due date from the charter deal-name tag '(Aug) 26/27' — Aug-Dec belong
    to the first school year, Jan-Jul to the second. None if no tag."""
    m = _NAME_TAG.search(dealname or "")
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    year = 2000 + int(m.group(2) if month >= 8 else m.group(3))
    return _po_month_end(f"{year}-{month:02d}")


def _due_date(props: dict, dealname: str):
    prop = (cfg()["deal_sync"].get("invoice_sweep", {}).get("invoice_due_property")
            or cfg()["po_inbox"].get("invoice_task", {}).get("invoice_due_property") or "").strip()
    raw = (props.get(prop) or "").strip() if prop else ""
    if raw:
        try:
            d = datetime.fromisoformat(raw[:10])
            return now_la().replace(year=d.year, month=d.month, day=d.day,
                                    hour=17, minute=0, second=0, microsecond=0)
        except ValueError:
            pass
    return _dealname_month_end(dealname)


def _hours_used(email: str, student_first: str, since_iso: str, token: str) -> float | None:
    """Attended/completed Teachworks lesson hours for the family's named student
    since the deal was created. None when the family/student isn't in TW yet."""
    cust = tw.find_customer_by_email(email, token)
    if not cust:
        return None
    studs = tw.tw_get("students", {"customer_id": cust.get("id")}, token=token)
    sf = (student_first or "").strip().lower()
    stud = next((s for s in studs if (s.get("first_name") or "").strip().lower() == sf), None)
    if not stud:
        return None
    total = 0.0
    for l in tw.tw_get("lessons", {"student_id": stud["id"], "from_date[gte]": since_iso},
                       token=token):
        status = str(l.get("status", "")).lower()
        if not ("attend" in status or "complete" in status):
            continue
        dur = l.get("duration")
        if dur:
            try:
                total += float(dur) / 60.0
            except (TypeError, ValueError):
                continue
    return total


def _find_po_deals(charter_pipelines: list[str], due_prop: str) -> list[dict]:
    props = ["dealname", "pipeline", "dealstage", "createdate", "po_number",
             "amount", "number_of_hours_in_this_po"]
    if due_prop:
        props.append(due_prop)
    groups = [{"filters": [
        {"propertyName": "pipeline", "operator": "EQ", "value": pid},
        {"propertyName": "po_number", "operator": "HAS_PROPERTY"},
    ]} for pid in charter_pipelines]
    res = hs._write("POST", "/crm/v3/objects/deals/search",
                    {"filterGroups": groups, "properties": props, "limit": 100,
                     "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}]})
    return res.get("results", []) if isinstance(res, dict) else []


def run_sweep(force: bool = False) -> None:
    """Called from deal_sync.run() every cycle; self-gates to once a day."""
    ds = cfg().get("deal_sync", {})
    sw = ds.get("invoice_sweep", {})
    if not sw.get("enabled"):
        return
    now = now_la()
    if not force and not (now.hour == int(sw.get("hour_pt", 9)) and now.minute < 15):
        return
    due_prop = (sw.get("invoice_due_property")
                or cfg()["po_inbox"].get("invoice_task", {}).get("invoice_due_property") or "")
    owner = cfg()["staff"].get(sw.get("owner", "kath"), {})
    active_patterns = cfg().get("deal_automation", {}).get(
        "active_stage_patterns", ["pre-lesson", "post-lesson", "in program"])
    token = tw.accounts().get("online")
    deals = _find_po_deals(list(ds.get("charter_pipelines", [])), due_prop)
    print(f"invoice_sweep: {len(deals)} charter PO deal(s)")
    prompted = 0
    for d in deals:
        key = f"invoice-prompt:{d['id']}"
        if audit.already_processed(key):
            continue
        p = d.get("properties") or {}
        label = hs.stage_label(p.get("pipeline"), p.get("dealstage")).lower()
        if label and not any(pat in label for pat in active_patterns):
            continue  # stopped/closed deals don't get invoiced
        dealname = p.get("dealname") or ""
        # family + student via the deal's contact (same resolution as the TW sync)
        from .deal_sync import _deal_contact, _student_firsts_from_dealname
        contact = _deal_contact(d["id"], dealname)
        email = ((contact or {}).get("properties") or {}).get("email", "")
        students = _student_firsts_from_dealname(dealname)
        try:
            po_hours = float(p.get("number_of_hours_in_this_po") or 0)
        except (TypeError, ValueError):
            po_hours = 0.0
        used = None
        if email and students and po_hours and token:
            since = (p.get("createdate") or "")[:10] or None
            try:
                used = _hours_used(email, students[0], since, token)
            except Exception as e:  # noqa: BLE001 — TW hiccup must not kill the sweep
                print(f"  ⚠️  hours lookup failed for deal {d['id']}: {e}")
        due = _due_date(p, dealname)
        reason = None
        if used is not None and po_hours and used >= po_hours:
            reason = f"PO hours used up ({used:g} of {po_hours:g})"
        elif due and now >= due:
            reason = f"invoice due date reached ({due.strftime('%b %-d')})"
        if not reason:
            continue
        hours_bit = (f" Hours used: {used:g}/{po_hours:g}." if used is not None and po_hours
                     else "")
        slack_client.dm(owner.get("slack_user_id"),
                        f"🧾 Time to SUBMIT the invoice to the school's ops system — "
                        f"{dealname}: {reason}."
                        f" PO {p.get('po_number') or 'n/a'}, ${p.get('amount') or '?'}."
                        f"{hours_bit} The TW invoice was created at PO receipt — submit it now.")
        cc = cfg().get("notify", {}).get("cc_owner_dms_to")
        if cc and cc != sw.get("owner", "kath"):
            ccs = cfg()["staff"].get(cc, {})
            if ccs.get("slack_user_id"):
                slack_client.dm(ccs["slack_user_id"],
                                f"📋 [copy → {owner.get('name', 'Kath')}] 🧾 invoice prompt: {dealname} — {reason}")
        audit.append({"message_id": key, "source": "invoice_sweep", "deal_id": d["id"],
                      "deal_name": dealname, "action_taken": "invoice_prompted",
                      "reason": reason, "owner": sw.get("owner", "kath")})
        prompted += 1
        print(f"  🧾 {dealname}: {reason}")
    print(f"invoice_sweep: {prompted} prompt(s)")

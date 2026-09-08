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
from .config import cfg, staff
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
             "amount", "number_of_hours_in_this_po", "invoice_submitted_date"]
    if due_prop:
        props.append(due_prop)
    props += ["invoice__", "lessons_fulfilled_date"]
    # Only deals whose invoice is NOT yet submitted, created since the 26/27
    # era began. The old single page of 100 (newest first) meant the sweep never
    # looked past the newest hundred POs: by 2026-09-01 an August deal was
    # already off the page, and Charlotte Czaja's $300 invoice sat 25 days past
    # due with nobody prompted.
    since = (cfg().get("deal_sync", {}).get("invoice_sweep", {}).get("since") or "2026-07-01")
    since_ms = str(int(datetime.fromisoformat(since).timestamp() * 1000))
    groups = [{"filters": [
        {"propertyName": "pipeline", "operator": "EQ", "value": pid},
        {"propertyName": "po_number", "operator": "HAS_PROPERTY"},
        {"propertyName": "invoice_submitted_date", "operator": "NOT_HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
    ]} for pid in charter_pipelines]
    out, after = [], None
    while True:
        body = {"filterGroups": groups, "properties": props, "limit": 200,
                "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}]}
        if after:
            body["after"] = after
        res = hs._write("POST", "/crm/v3/objects/deals/search", body)
        if not isinstance(res, dict):
            break
        out += res.get("results", [])
        after = ((res.get("paging") or {}).get("next") or {}).get("after")
        if not after or len(out) >= 5000:
            break
    return out


def _overdue_items(deals: list[dict], now, active_patterns: list[str], grace_days: int) -> list[dict]:
    """Deals with a Teachworks invoice (Invoice # stamped) that is past its due
    date and still not submitted to the school. Due date = the deal's due
    property (lessons_fulfilled_date, synced nightly from the TW invoice), else
    the deal-name month tag."""
    items = []
    for d in deals:
        p = d.get("properties") or {}
        inv = (p.get("invoice__") or "").strip()
        if not inv or p.get("invoice_submitted_date"):
            continue
        label = hs.stage_label(p.get("pipeline"), p.get("dealstage")).lower()
        if label and not any(pat in label for pat in active_patterns):
            continue
        dealname = p.get("dealname") or ""
        due = _due_date(p, dealname)
        if not due:
            continue
        late = (now.date() - due.date()).days
        if late < grace_days:
            continue
        try:
            amt = float(p.get("amount") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        items.append({"deal_id": d["id"], "dealname": dealname, "po": p.get("po_number") or "n/a",
                      "invoice": inv, "amount": amt, "due": due.strftime("%b %-d"), "late": late})
    items.sort(key=lambda i: -i["late"])
    return items


def run_overdue_nag(deals: list[dict], now, sw: dict, active_patterns: list[str]) -> int:
    """EVERY business day, one digest to the submissions owner listing every
    invoice past due and not yet submitted, with days late; the visionary role
    is pulled in once anything is `escalate_after_days` late. Repeats daily
    until the list is empty (Roman 2026-09-08: "we are not falling behind on
    submissions this year"). The one-shot prompt above stays as the first
    nudge; this is the follow-through it never had."""
    if now.weekday() >= 5:
        return 0
    key = f"submission-nag:{now.strftime('%Y-%m-%d')}"
    if audit.already_processed(key):
        return 0
    items = _overdue_items(deals, now, active_patterns, int(sw.get("overdue_grace_days", 1)))
    if not items:
        return 0
    total = sum(i["amount"] for i in items)
    escalate_after = int(sw.get("escalate_after_days", 3))
    worst = items[0]["late"]
    lines = [f"• {i['dealname']} | PO {i['po']} | inv {i['invoice']} | ${i['amount']:,.2f} | "
             f"due {i['due']} | {i['late']} day{'s' if i['late'] != 1 else ''} late" for i in items]
    body = (f"🧾 OVERDUE INVOICE SUBMISSIONS: {len(items)} invoice{'s' if len(items) != 1 else ''}, "
            f"${total:,.2f} (as of {now.strftime('%b %-d')})\n" + "\n".join(lines) +
            "\nSubmit each in the school's ops system, then set Invoice Submitted Date and move "
            "the deal to Invoice Submitted. This list repeats every business day until it is empty.")
    owner_key = sw.get("owner", "kath")
    owner = staff(owner_key)
    if owner.get("slack_user_id"):
        slack_client.dm(owner["slack_user_id"], body)
    escalated = False
    if worst >= escalate_after:
        esc_key = sw.get("escalate_to", "visionary")
        esc = staff(esc_key)
        if esc.get("slack_user_id") and esc.get("slack_user_id") != owner.get("slack_user_id"):
            slack_client.dm(esc["slack_user_id"],
                            f"🚩 ESCALATION: invoice submissions {worst} days overdue "
                            f"({owner.get('name', owner_key)} is being nagged daily).\n{body}")
            escalated = True
    if not escalated:
        cc = cfg().get("notify", {}).get("cc_owner_dms_to")
        if cc and cc != owner_key:
            ccs = staff(cc)
            if ccs.get("slack_user_id") and ccs.get("slack_user_id") != owner.get("slack_user_id"):
                slack_client.dm(ccs["slack_user_id"],
                                f"📋 [copy → {owner.get('name', owner_key)}] {body}")
    audit.append({"message_id": key, "source": "invoice_sweep", "action_taken": "submission_nag",
                  "count": len(items), "total": round(total, 2), "max_days_late": worst,
                  "escalated": escalated, "owner": owner_key,
                  "deal_ids": [i["deal_id"] for i in items]})
    print(f"invoice_sweep: overdue-submission nag sent ({len(items)} invoice(s), ${total:,.2f}, "
          f"worst {worst}d{', escalated' if escalated else ''})")
    return len(items)


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
    owner = staff(sw.get("owner", "kath"))
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
        if p.get("invoice_submitted_date"):
            continue  # invoice already submitted to the school — never prompt
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
                        f"{hours_bit} The TW invoice was created at PO receipt — submit it, "
                        f"then set invoice_submitted_date and move the deal to Invoice Submitted.")
        cc = cfg().get("notify", {}).get("cc_owner_dms_to")
        if cc and cc != sw.get("owner", "kath"):
            ccs = staff(cc)
            if ccs.get("slack_user_id"):
                slack_client.dm(ccs["slack_user_id"],
                                f"📋 [copy → {owner.get('name', 'Kath')}] 🧾 invoice prompt: {dealname} — {reason}")
        audit.append({"message_id": key, "source": "invoice_sweep", "deal_id": d["id"],
                      "deal_name": dealname, "action_taken": "invoice_prompted",
                      "reason": reason, "owner": sw.get("owner", "kath")})
        prompted += 1
        print(f"  🧾 {dealname}: {reason}")
    print(f"invoice_sweep: {prompted} prompt(s)")
    try:
        run_overdue_nag(deals, now, sw, active_patterns)
    except Exception as e:  # noqa: BLE001 — the nag must never kill the sweep
        print(f"  ⚠️  overdue-submission nag failed (non-fatal): {e}")

"""Charter-PO inbox flow (separate Gmail).

Per new email: extract PO details with Claude — READING PDF/image attachments
(the actual PO document) natively — → HubSpot ticket to Kath (same accountability
spine as the admin inbox) → advance the matching "Waiting for PO" deal or create
one. Parent contact info found in the PO → the HubSpot contact is found-or-created
and associated to the deal (that's what lets the Teachworks sync create the
family); parent info missing → the ticket tells Kath to get it from the TOR.
POs NEVER get a reply draft; non-PO mail gets one when warranted (drafts are
REAL Gmail drafts a human sends). Label → ticket → Slack DM Kath (+ CC) →
audit. The agent never sends from this address.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone

from . import audit, gmail_client as gm, hubspot_client as hs, slack_client
from .business_hours import add_business_hours, now_la
from .classifier import parse_classification  # reuse the tolerant JSON parser
from .config import ANTHROPIC_API_KEY, DRY_RUN, cfg

PO_SYSTEM = (
    "You process A+ Tutoring's charter-school PURCHASE ORDER inbox. The email may "
    "include PDF/image attachments (the actual PO document) — read them; PO details "
    "usually live there, not in the body. "
    "Respond with a SINGLE JSON object, no prose: {is_po (bool), school, student_first, "
    "student_last, po_number, amount, hours, parent_first, parent_last, parent_email, "
    "parent_phone, tor_first, tor_last, tor_email, po_month, level_up (bool), summary, "
    "draft_reply, confidence (0-1)}. "
    "is_po=true ONLY for a NEW purchase order / funding authorization that starts or adds "
    "service. Invoice requests, invoicing follow-ups, payment reminders, statements, or "
    "questions about EXISTING service are NOT new POs → is_po=false (still extract "
    "school/student/po_number/amount and summarize; these get a review ticket, no deal). "
    "parent_* = the PARENT/GUARDIAN's contact info from the email or PO document — never "
    "the school staff, TOR, or education specialist; empty string for anything not stated. "
    "tor_* = the Teacher of Record / education specialist handling this PO (often the "
    "email sender) — never the parent. school_bill_to = the school's exact billing "
    "name/address from the PO (schools reject invoices with a wrong Bill To); empty if "
    "not stated. "
    "draft_reply rules: if is_po → ALWAYS empty string (we never reply to purchase "
    "orders). For non-PO emails that warrant a human reply → a short warm draft (first "
    "person plural, no em dashes, signed 'A+ Tutoring Team'); empty for automated "
    "notifications and spam. If the email is NOT PO-related (spam, misc), set "
    "is_po=false and summarize what it is."
)


def _content_blocks(body: str, subject: str, sender: str, attachments: list[dict]) -> list:
    """User-message content: the email text plus each readable attachment as a native
    document/image block, so the extractor reads the PO PDF itself."""
    blocks: list = [{"type": "text", "text":
                     f"FROM: {sender}\nSUBJECT: {subject}\n\n{body[:6000]}"}]
    for a in attachments or []:
        kind = "document" if a["mime"] == "application/pdf" else "image"
        blocks.append({"type": kind, "source": {
            "type": "base64", "media_type": a["mime"], "data": a["data_b64"]}})
    blocks.append({"type": "text", "text": "Return the JSON now."})
    return blocks


def po_extract(body: str, subject: str, sender: str,
               attachments: list[dict] | None = None) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    c = cfg()["classifier"]
    msg = client.messages.create(
        model=c["model"], max_tokens=c["max_tokens"], system=PO_SYSTEM,
        messages=[{"role": "user",
                   "content": _content_blocks(body, subject, sender, attachments or [])}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    return json.loads(cleaned[start:end + 1])


def _attach_po_to_deal(deal_id, attachments: list[dict], po: dict,
                       note_parts: list[str]) -> None:
    """Upload the PO document(s) to HubSpot Files and pin them to the deal as a
    note — the deal record must carry the actual PO PDF. Best-effort: a failed
    upload never blocks the deal, it just asks for a manual attach."""
    if not attachments or not deal_id or deal_id == "DRYRUN":
        return
    import base64 as _b64
    try:
        file_ids = []
        for a in attachments:
            fid = hs.upload_file(a["filename"], _b64.b64decode(a["data_b64"]), a["mime"])
            if fid:
                file_ids.append(fid)
        if file_ids:
            hs.add_deal_note(deal_id,
                             f"📎 PO document from charter@ email (PO {po.get('po_number') or 'n/a'}, "
                             f"{po.get('school') or 'school n/a'}).", file_ids)
            note_parts.append(f"📎 PO document attached to the deal "
                              f"({', '.join(a['filename'] for a in attachments)}).")
        else:
            note_parts.append("📎 PO upload to HubSpot failed — attach the PDF to the deal manually.")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  PO attach failed (non-fatal): {e}")
        note_parts.append("📎 PO upload to HubSpot failed — attach the PDF to the deal manually.")


def _associate_tor(deal_id, po: dict, note_parts: list[str]) -> None:
    """Associate the Teacher of Record's contact to the deal (find-or-create by
    email). The parent stays the deal's family contact — the Teachworks sync picks
    the contact matching the deal-name parent, so adding the TOR is safe."""
    t_email = (po.get("tor_email") or "").strip().lower()
    p_email = (po.get("parent_email") or "").strip().lower()
    if not t_email or t_email == p_email or not deal_id or deal_id == "DRYRUN":
        return
    try:
        tor = hs.find_contact_by_email(t_email)
        if not tor:
            tor = hs.create_contact(t_email, po.get("tor_first") or None,
                                    po.get("tor_last") or None)
        if tor and tor.get("id") not in (None, "DRYRUN"):
            hs.associate_contact_to_deal(deal_id, tor["id"])
            note_parts.append(f"🧑‍🏫 TOR {po.get('tor_first', '')} {po.get('tor_last', '')} "
                              f"<{t_email}> associated to the deal.")
    except Exception as e:  # noqa: BLE001 — TOR association is best-effort
        print(f"  ⚠️  TOR association failed (non-fatal): {e}")


def _po_month_end(po_month: str):
    """Last day of the PO's service month (5 PM PT) — the invoice due date. None if
    the month is missing/unparseable."""
    import calendar
    m = re.match(r"^(\d{4})-(\d{2})$", (po_month or "").strip())
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    last = calendar.monthrange(year, month)[1]
    return now_la().replace(year=year, month=month, day=last,
                            hour=17, minute=0, second=0, microsecond=0)


def _invoice_task(deal_id, po: dict, note_parts: list[str]) -> None:
    """STEP 1 of the PO money flow: on receipt, the PO is converted to a Teachworks
    invoice — a same-day HubSpot Task for Kath (the TW API can't create invoices).
    STEP 2 (submitting that invoice to the school's ops system once service is
    delivered) is prompted separately by the invoice sweep. The submission due date
    (end of the PO's service month) is stamped on the deal when
    po_inbox.invoice_task.invoice_due_property names a HubSpot date property."""
    ic = cfg()["po_inbox"].get("invoice_task", {})
    if not ic.get("enabled") or not po.get("amount"):
        return
    month_end = _po_month_end(po.get("po_month") or "")
    try:
        prop = (ic.get("invoice_due_property") or "").strip()
        if prop and month_end and deal_id and deal_id != "DRYRUN":
            try:
                hs._write("PATCH", f"/crm/v3/objects/deals/{deal_id}",
                          {"properties": {prop: month_end.strftime("%Y-%m-%d")}})
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  invoice-due deal property failed (non-fatal): {e}")
        owner = cfg()["staff"].get(ic.get("owner", "kath"), {})
        due = add_business_hours(now_la(), int(ic.get("due_business_hours", 8)))
        submit_line = (f"Submit to the school's ops system by: "
                       f"{month_end.strftime('%b %-d, %Y')} (end of PO month "
                       f"{po.get('po_month')}) — you'll be prompted when it's time." if month_end
                       else "Submission due date: PO month not stated — confirm the service month.")
        student = f"{po.get('student_first', '')} {po.get('student_last', '')}".strip() or "student n/a"
        body = (f"STEP 1: convert this PO to a Teachworks invoice NOW (API can't — manual).\n"
                f"Student: {student}\nSchool: {po.get('school') or 'n/a'}\n"
                f"PO #: {po.get('po_number') or 'n/a'}\nAmount: ${po.get('amount')}\n"
                f"Hours: {po.get('hours') or 'n/a'}\n{submit_line}\n"
                f"HubSpot deal id: {deal_id}. The PO PDF is attached to the deal; the family/"
                f"student are created in Teachworks by the deal sync.")
        hs.create_task(f"Convert PO to TW invoice — {student} ({po.get('school') or '?'}, "
                       f"PO {po.get('po_number') or 'n/a'}, ${po.get('amount')})",
                       body, owner.get("hubspot_owner_id"),
                       int(due.timestamp() * 1000), priority="HIGH")
        note_parts.append(f"🧾 Convert-to-TW-invoice task created for {owner.get('name', 'Kath')} "
                          f"(${po.get('amount')}, due {due.strftime('%b %-d')}).")
    except Exception as e:  # noqa: BLE001 — the deal must survive a task failure
        print(f"  ⚠️  invoice task failed (non-fatal): {e}")
        note_parts.append("🧾 Could not create the Teachworks-invoice task — invoice manually.")


def _handle_deal(po: dict, note_parts: list[str], attachments: list[dict] | None = None) -> None:
    """Advance the matching Waiting-for-PO deal, or create one."""
    pc = cfg()["po_inbox"]
    student = (po.get("student_last") or po.get("student_first") or "").strip()
    school = (po.get("school") or "").strip()
    token = student or school
    if not token:
        note_parts.append("💼 No student/school extracted — no deal action; review manually.")
        return
    # PO-number dedupe via the canonical po_number PROPERTY (then name as backstop).
    po_num = (po.get("po_number") or "").strip()
    if po_num:
        dup = hs.find_deals_by_po_number(po_num) or hs.search_deals_by_name(po_num)
        if dup:
            dn = (dup[0].get("properties") or {}).get("dealname", "?")
            note_parts.append(f"💼 DUPLICATE PO {po_num} ('{dn}') — no new deal; Kath alerted.")
            owner = cfg()["staff"].get(pc.get("owner", "kath"), {})
            slack_client.dm(owner.get("slack_user_id"),
                            f"🚨 URGENT — duplicate PO received: PO {po_num} already has deal "
                            f"'{dn}'. Check whether the school re-sent it or this is a second "
                            f"authorization before doing anything.")
            return
    waiting = (hs.search_deals_by_name(token, pc["deal_pipeline_id"], pc["waiting_for_po_stage"])
               if pc.get("waiting_for_po_stage") else [])   # stage retired → always create
    if len(waiting) == 1:
        d = waiting[0]
        hs.move_deal_stage(d["id"], pc["advance_to_stage"])
        note_parts.append(f"💼 Deal '{d['properties'].get('dealname')}' advanced: "
                          f"Waiting for PO → Pre-Lesson (PO {po.get('po_number') or 'n/a'}).")
        _associate_tor(d["id"], po, note_parts)
        _attach_po_to_deal(d["id"], attachments or [], po, note_parts)
        _invoice_task(d["id"], po, note_parts)
    elif len(waiting) > 1:
        names = "; ".join(d["properties"].get("dealname", "?") for d in waiting)
        note_parts.append(f"💼 {len(waiting)} deals waiting for PO match '{token}' — advance manually: {names}")
    else:
        name = " - ".join(x for x in [school, f"{po.get('student_first','')} {po.get('student_last','')}".strip(),
                                      f"PO {po.get('po_number')}" if po.get("po_number") else ""] if x)
        # deal type: existing business if this student already has deals anywhere, else new
        prior = hs.search_deals_by_name(token)
        dtype = "existingbusiness" if prior else "newbusiness"
        # deal OWNER = the assigned scheduler (A-L/M-Z by family last name), not Kath
        from .business_hours import now_la
        from .router import scheduler_for_last_name
        sched_key, _ = scheduler_for_last_name(po.get("student_last") or "")
        sched = cfg()["staff"].get(sched_key, {})
        close_ms = int((now_la() + timedelta(days=30)).timestamp() * 1000)
        extra = {"po_number": po_num}
        if po.get("hours"):
            extra["number_of_hours_in_this_po"] = po["hours"]
        # Associate the PARENT contact — the Teachworks sync keys the family on the
        # deal's contact email, so a deal without a parent contact never reaches
        # Teachworks. Best source: parent info extracted from the PO itself (find the
        # HubSpot contact by email, CREATE it if new); fallback: unique student-name
        # match against existing family contacts.
        contact_id = None
        contact_bit = ""
        p_email = (po.get("parent_email") or "").strip().lower()
        if p_email:
            try:
                existing = hs.find_contact_by_email(p_email)
                if existing:
                    contact_id = existing["id"]
                    contact_bit = f"linked to existing contact {p_email}, "
                else:
                    created_c = hs.create_contact(p_email, po.get("parent_first") or None,
                                                  po.get("parent_last") or None,
                                                  phone=po.get("parent_phone") or None)
                    contact_id = created_c.get("id")
                    contact_bit = (f"CREATED HubSpot contact {po.get('parent_first', '')} "
                                   f"{po.get('parent_last', '')} <{p_email}> from the PO, ")
            except Exception as e:  # noqa: BLE001 — contact handling is best-effort
                print(f"  ⚠️  parent-contact create/lookup failed (non-fatal): {e}")
        if not contact_id:
            try:
                parents = hs.find_family_contact(po.get("student_first") or "",
                                                 po.get("student_last") or "")
            except Exception:  # noqa: BLE001
                parents = []
            if len(parents) == 1:
                contact_id = parents[0]["id"]
                contact_bit = (f"linked to family contact "
                               f"{parents[0]['properties'].get('firstname', '')} "
                               f"{parents[0]['properties'].get('lastname', '')}".strip() + ", ")
        if not contact_id:
            contact_bit = ("NO parent contact info in the PO and no unique family match — "
                           "get it from the TOR (no reply is sent to POs), then associate "
                           "the parent on the deal so the Teachworks sync picks it up, ")
        pipeline_id, stage_id = pc["deal_pipeline_id"], pc["advance_to_stage"]
        if po.get("level_up"):
            if pc.get("levelup_pipeline_id"):
                pipeline_id = pc["levelup_pipeline_id"]
                stage_id = pc.get("levelup_stage_id") or stage_id
                note_parts.append("⤴️ LEVEL UP PO → Level Up A pipeline.")
            else:
                note_parts.append("⚠️ LEVEL UP detected but po_inbox.levelup_pipeline_id is "
                                  "not configured — deal created in the default Charter "
                                  "pipeline; MOVE IT and set the config.")
        d = hs.create_deal(name or f"PO {po.get('po_number') or '(new)'}",
                           pipeline_id, stage_id, po.get("amount") or None,
                           contact_id=contact_id,
                           dealtype=dtype, owner_id=sched.get("hubspot_owner_id"),
                           closedate_ms=close_ms, extra_props=extra)
        note_parts.append(f"💼 Created deal '{name}' in Charter pipeline (Pre-Lesson, "
                          f"{'Existing' if prior else 'New'} Business, owner {sched.get('name', sched_key)}, "
                          f"{contact_bit}id {d.get('id')}).")
        _associate_tor(d.get("id"), po, note_parts)
        _attach_po_to_deal(d.get("id"), attachments or [], po, note_parts)
        _invoice_task(d.get("id"), po, note_parts)
        # No waiting on the next cron: run the Teachworks sync for THIS deal now.
        if d.get("id") and d.get("id") != "DRYRUN":
            try:
                from . import deal_sync
                rec = deal_sync.sync_deal(
                    {"id": d["id"], "properties": {
                        "pipeline": pipeline_id, "dealname": name, "po_number": po_num}}) or {}
                note_parts.append(f"🔄 Teachworks sync ran immediately: "
                                  f"{rec.get('action_taken', 'skipped')}.")
            except Exception as e:  # noqa: BLE001 — the 15-min sync will retry
                print(f"  ⚠️  immediate TW sync failed (cron will retry): {e}")


def _thread_already_handled(thread_id: str) -> bool:
    """One conversation = one ticket: later messages on a handled thread are part of an
    ongoing exchange humans are already on — skip them."""
    for r in audit._iter_records():
        if r.get("source") == "po_inbox" and r.get("thread_id") == thread_id:
            return True
    return False


def process_po_message(stub_id: str) -> dict | None:
    pc = cfg()["po_inbox"]
    m = gm.get_message(stub_id)
    if audit.already_processed(f"gmail:{m['id']}") or _thread_already_handled(m["threadId"]):
        return None
    attachments: list[dict] = []
    try:
        attachments = gm.get_attachments(m["id"])
    except Exception as e:  # noqa: BLE001 — extraction proceeds on the body alone
        print(f"  ⚠️  attachment fetch failed (non-fatal): {e}")
    po = po_extract(m["body"], m["subject"], m["sender"], attachments)
    owner = cfg()["staff"][pc.get("owner", "kath")]
    record = {"message_id": f"gmail:{m['id']}", "thread_id": m["threadId"], "source": "po_inbox",
              "category": "new_po" if po.get("is_po") else "po_inbox_other",
              "confidence": po.get("confidence"), "owner": pc.get("owner", "kath"),
              "po_number": po.get("po_number") or "", "school": po.get("school") or "",
              "attachments_read": [a["filename"] for a in attachments],
              "parent_email": po.get("parent_email") or "",
              "reason": (po.get("summary") or "")[:300]}
    note_parts: list[str] = []
    sla_due = add_business_hours(now_la(), 8)

    if po.get("is_po"):
        _handle_deal(po, note_parts, attachments)
        labels = [pc["label_processed"]] + ([f"School/{po['school'][:40]}"] if po.get("school") else [])
    else:
        labels = [pc["label_review"]]
        note_parts.append(f"Not a PO: {po.get('summary','')[:200]}")

    # Ticket (same spine as admin inbox)
    subject = (f"new_po — {po.get('school') or m['sender'][:40]}"
               + (f" (PO {po['po_number']})" if po.get("po_number") else "")) if po.get("is_po") \
              else f"po_inbox review — {m['subject'][:50]}"
    desc = (f"From PO inbox ({pc['address']}).\nFrom: {m['sender']}\nSubject: {m['subject']}\n"
            f"School: {po.get('school')} | Student: {po.get('student_first')} {po.get('student_last')} | "
            f"PO#: {po.get('po_number')} | Amount: {po.get('amount')} | Hours: {po.get('hours')}\n"
            f"Parent: {po.get('parent_first', '')} {po.get('parent_last', '')} "
            f"<{po.get('parent_email') or 'no email'}> {po.get('parent_phone') or ''}\n"
            f"Attachments read: {', '.join(a['filename'] for a in attachments) or 'none'}\n"
            f"Summary: {po.get('summary')}\n" + "\n".join(note_parts)
            + f"\nSLA due: {sla_due.isoformat()}")
    ticket = hs.create_ticket(subject, owner["hubspot_owner_id"],
                              cfg()["hubspot"]["ticket_stages"]["needs_approval"], desc, None,
                              priority="MEDIUM", category="new_deal_po", source="EMAIL")
    record["ticket_id"] = ticket.get("id")
    record["sla_due"] = sla_due.isoformat()

    # The email lives in Gmail (not a HubSpot conversation), so embed the body as a NOTE
    # — otherwise the ticket has no readable email at all.
    if record["ticket_id"] and record["ticket_id"] != "DRYRUN":
        try:
            hs.add_ticket_note(
                record["ticket_id"],
                f"📧 Original email (charter@ Gmail) — from {m['sender']}\n"
                f"Subject: {m['subject']}\n\n{(m['body'] or '(no text)')[:6000]}")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  email-body note failed (non-fatal): {e}")

    # Gmail: labels + a real draft reply (never sent by the agent)
    try:
        gm.apply_labels(m["id"], labels)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  label failed (non-fatal): {e}")
    draft = "" if po.get("is_po") else (po.get("draft_reply") or "").strip()
    if draft:
        try:
            sender_addr = re.search(r"<([^>]+)>", m["sender"])
            to_addr = sender_addr.group(1) if sender_addr else m["sender"]
            gm.create_draft_reply(m["threadId"], to_addr, m["subject"], draft,
                                  m.get("message_id_header", ""))
            record["draft_posted"] = True
        except Exception as e:  # noqa: BLE001
            record["draft_posted"] = False
            print(f"  ⚠️  gmail draft failed (non-fatal): {e}")

    deal_bit = next((p for p in note_parts if p.startswith("💼")), "")
    slack_client.dm(owner["slack_user_id"],
                    f"📦 PO inbox: {subject}. {deal_bit} Draft in Gmail Drafts. "
                    f"{hs.ticket_url(record['ticket_id']) if record.get('ticket_id') else ''}")
    cc = cfg().get("notify", {}).get("cc_owner_dms_to")
    if cc and cc != pc.get("owner"):
        ccs = cfg()["staff"].get(cc, {})
        if ccs.get("slack_user_id"):
            slack_client.dm(ccs["slack_user_id"], f"📋 [copy → {owner['name']}] 📦 {subject}")

    record["action_taken"] = "po_processed"
    audit.append(record)
    print(f"  📦 {subject} → {pc.get('owner')} (ticket {record.get('ticket_id')})")
    return record


def run() -> None:
    pc = cfg().get("po_inbox", {})
    if not pc.get("address"):
        print("po_inbox.address not configured — skipping (see SETUP §7)")
        return
    import json as _json
    from pathlib import Path
    cur_path = Path(__file__).resolve().parent.parent / "state" / "po_cursor.json"
    state = _json.loads(cur_path.read_text()) if cur_path.exists() else {}
    since = state.get("last_epoch")
    if not since:
        since = int(datetime.now(timezone.utc).timestamp())
        if not DRY_RUN:
            cur_path.write_text(_json.dumps({"last_epoch": since}))
        print(f"po_inbox: baseline set ({since}); new mail picked up next run")
        return
    try:
        stubs = gm.list_messages(f"in:inbox after:{since}")
    except Exception as e:  # noqa: BLE001 — most likely DWD not granted yet
        if "unauthorized_client" in str(e):
            print("po_inbox: Gmail delegation not granted yet (SETUP §7a) — skipping cleanly")
            return
        raise
    print(f"po_inbox: {len(stubs)} new message(s)")
    newest = since
    for s in stubs:
        try:
            rec = process_po_message(s["id"])
            if rec:
                newest = max(newest, int(datetime.now(timezone.utc).timestamp()))
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  error on gmail {s['id']}: {e}", file=sys.stderr)
            traceback.print_exc()
            audit.append({"message_id": f"gmail:{s['id']}", "source": "po_inbox",
                          "action_taken": "error", "error": str(e)[:200]})
    if not DRY_RUN:
        cur_path.write_text(_json.dumps({"last_epoch": newest}))


if __name__ == "__main__":
    run()

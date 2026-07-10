"""Charter-PO inbox flow (separate Gmail).

Per new email: extract PO details with Claude → HubSpot ticket to Kath (same
accountability spine as the admin inbox) → advance the matching "Waiting for PO"
deal or create one → label the email in Gmail → leave a REAL Gmail draft reply →
Slack DM Kath (+ CC) → audit. The agent never sends from this address.
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
    "You process A+ Tutoring's charter-school PURCHASE ORDER inbox. "
    "Respond with a SINGLE JSON object, no prose: {is_po (bool), school, student_first, "
    "student_last, po_number, amount, hours, summary, draft_reply, confidence (0-1)}. "
    "is_po=true ONLY for a NEW purchase order / funding authorization that starts or adds "
    "service. Invoice requests, invoicing follow-ups, payment reminders, statements, or "
    "questions about EXISTING service are NOT new POs → is_po=false (still extract "
    "school/student/po_number/amount and summarize; these get a review ticket, no deal). "
    "Extract from the email body; empty string for anything not stated. draft_reply = a "
    "short warm acknowledgment (first person plural, no em dashes, signed 'A+ Tutoring "
    "Team') confirming receipt and next steps; empty if no reply is warranted (e.g. "
    "automated notification or spam). If the email is NOT PO-related (spam, misc), set "
    "is_po=false and summarize what it is."
)


def po_extract(body: str, subject: str, sender: str) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    c = cfg()["classifier"]
    msg = client.messages.create(
        model=c["model"], max_tokens=c["max_tokens"], system=PO_SYSTEM,
        messages=[{"role": "user", "content":
                   f"FROM: {sender}\nSUBJECT: {subject}\n\n{body[:6000]}\n\nReturn the JSON now."}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    return json.loads(cleaned[start:end + 1])


def _handle_deal(po: dict, note_parts: list[str]) -> None:
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
            note_parts.append(f"💼 Deal already exists for PO {po_num} ('{dn}') — no new deal.")
            return
    waiting = (hs.search_deals_by_name(token, pc["deal_pipeline_id"], pc["waiting_for_po_stage"])
               if pc.get("waiting_for_po_stage") else [])   # stage retired → always create
    if len(waiting) == 1:
        d = waiting[0]
        hs.move_deal_stage(d["id"], pc["advance_to_stage"])
        note_parts.append(f"💼 Deal '{d['properties'].get('dealname')}' advanced: "
                          f"Waiting for PO → Pre-Lesson (PO {po.get('po_number') or 'n/a'}).")
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
        d = hs.create_deal(name or f"PO {po.get('po_number') or '(new)'}",
                           pc["deal_pipeline_id"], pc["advance_to_stage"], po.get("amount") or None,
                           dealtype=dtype, owner_id=sched.get("hubspot_owner_id"),
                           closedate_ms=close_ms, extra_props=extra)
        note_parts.append(f"💼 Created deal '{name}' in Charter pipeline (Pre-Lesson, "
                          f"{'Existing' if prior else 'New'} Business, owner {sched.get('name', sched_key)}), "
                          f"id {d.get('id')}.")


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
    po = po_extract(m["body"], m["subject"], m["sender"])
    owner = cfg()["staff"][pc.get("owner", "kath")]
    record = {"message_id": f"gmail:{m['id']}", "thread_id": m["threadId"], "source": "po_inbox",
              "category": "new_po" if po.get("is_po") else "po_inbox_other",
              "confidence": po.get("confidence"), "owner": pc.get("owner", "kath"),
              "po_number": po.get("po_number") or "", "school": po.get("school") or "",
              "reason": (po.get("summary") or "")[:300]}
    note_parts: list[str] = []
    sla_due = add_business_hours(now_la(), 8)

    if po.get("is_po"):
        _handle_deal(po, note_parts)
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
    draft = (po.get("draft_reply") or "").strip()
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

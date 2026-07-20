"""Triage entrypoint.

Per run: poll HubSpot Conversations for new inbound messages since the cursor,
enrich + classify + route each, open a ticket, draft a reply (as a COMMENT) unless
suppressed, DM the owner, and audit every decision.

Autonomy exceptions (the ONLY auto-actions): junk → archive; tutor_document →
send a fixed receipt then ticket. Everything else is draft-only.

FERPA: only the email body + the structured enrichment summary go to Claude.
"""
from __future__ import annotations

import sys
import traceback
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from . import audit, hubspot_client as hs, slack_client, teachworks_client as tw
from .business_hours import LA, add_business_hours, now_la
from .classifier import classify
from .config import DRY_RUN, ROOT, cfg, require
from .router import resolve

DOC_RECEIPT = "tutor_document"  # the only category permitted to send an outbound MESSAGE

# Human-readable category labels for ticket subjects (Option A naming).
_CATEGORY_LABELS = {
    "school_partner": "School Partner",
    "charter_newsletter": "Charter Newsletter",
    "complaint": "Complaint",
    "payment_dispute": "Payment Dispute",
    "tor_inquiry": "TOR Inquiry",
    "new_po": "New PO",
    "reschedule": "Reschedule",
    "scheduling": "Scheduling",
    "cancellation": "Cancellation",
    "business_dev": "Business Dev",
    "tutor_issue": "Tutor Issue",
    "tutor_document": "Tutor Document",
    "recruitment": "Recruitment",
    "junk": "Junk",
    "unknown": "Unknown",
}


def _category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, (category or "Unknown").replace("_", " ").title())


def _ticket_subject(category: str, contact: dict | None, result: dict,
                    last_name: str | None, contact_name: str) -> str:
    """Option A ticket naming — `Lastname, Firstname — Category`.
    Lastname = family/parent surname (email content via the classifier → HubSpot contact).
    Firstname = the student when the email is about one, else the contact's own first
    name. Falls back to the email local-part when we have no real name (brand-new sender,
    no CRM/Teachworks match)."""
    props = (contact or {}).get("properties") or {}
    ln = (last_name or props.get("lastname") or "").strip()
    fn = (result.get("student_first_name") or props.get("firstname") or "").strip()
    if ln and fn:
        who = f"{ln}, {fn}"
    elif ln or fn:
        who = ln or fn
    else:
        who = contact_name
    return f"{who} — {_category_label(category)}"


def build_enrichment_summary(contact: dict | None, hs_enrich: dict, tw_enrich: dict) -> str:
    """Compact, FERPA-safe text block for the classifier (counts/dates/names only)."""
    lines = []
    props = (hs_enrich or {}).get("properties", {})
    if contact:
        lines.append(f"contact_id: {contact.get('id')}")
    if props:
        lines.append(f"lifecycle_stage: {props.get('lifecyclestage')}")
        lines.append(f"hubspot_owner_id: {props.get('hubspot_owner_id')}")
        lines.append(f"lead_status: {props.get('hs_lead_status')}")
    lines.append(f"associated_deals: {(hs_enrich or {}).get('associated_deals', 0)}")
    if tw_enrich.get("teachworks_match"):
        lines += [
            f"teachworks_account: {tw_enrich.get('teachworks_account')}",   # online | in_person
            f"parent: {tw_enrich.get('parent_name')} (last_name={tw_enrich.get('parent_last_name')})",
            f"student: {tw_enrich.get('student_name')}",
            f"assigned_tutor: {tw_enrich.get('assigned_tutor')}",
            f"upcoming_lessons: {tw_enrich.get('upcoming_lessons')}",
            f"recent_lessons: {tw_enrich.get('recent_lessons')}",
            f"attended/no_show/cancelled: "
            f"{tw_enrich.get('attended_count')}/{tw_enrich.get('no_show_count')}/{tw_enrich.get('cancelled_count')}",
            f"last_lesson_date: {tw_enrich.get('last_lesson_date')}",
        ]
    else:
        lines.append("teachworks_match: false")
    return "\n".join(str(l) for l in lines)


def _parent_last_name(contact: dict | None, tw_enrich: dict, result: dict | None = None) -> str | None:
    """Last name for the A-L / M-Z scheduler split = the PARENT/family last name.
    Priority: (1) name read from the email CONTENT by the classifier — needed when the
    sender isn't the parent (e.g. Teachworks notifications name the family in the body);
    (2) the HubSpot contact (the parent who emailed); (3) the Teachworks family record.
    NEVER the student's name."""
    if result and result.get("parent_last_name"):
        return str(result["parent_last_name"]).strip()
    if contact:
        ln = (contact.get("properties") or {}).get("lastname")
        if ln:
            return ln
    return tw_enrich.get("parent_last_name")


def _cancellation_deal_action(family_cid, result: dict) -> tuple[str, dict | None]:
    """Deal handling on a cancellation. Auto-moves the student's deal to its pipeline's
    Stopped stage ONLY when: type=stop, confidence ≥ min, and exactly ONE active deal
    matches the student. Otherwise surfaces the candidate deal(s) for a human. Returns
    (line for the ticket/DM, record of the move or None)."""
    da = cfg().get("deal_automation", {})
    if not (da.get("enabled") and family_cid):
        return "", None
    if (result.get("cancellation_type") or "").lower() == "one_time":
        return "", None   # one-time skip — the family stays; don't touch deals
    sf = (result.get("student_first_name") or "").strip().lower()
    active_pats = [p.lower() for p in da.get("active_stage_patterns", [])]
    stop_pats = [p.lower() for p in da.get("stop_stage_patterns", [])]
    cands = []
    for dl in hs.get_contact_deals(family_cid):
        label = hs.stage_label(dl["pipeline"], dl["stage"]).lower()
        is_active = any(pat in label for pat in active_pats)
        matches_student = (not sf) or (sf in (dl["name"] or "").lower())
        if is_active and matches_student:
            cands.append(dl)
    ctype = (result.get("cancellation_type") or "").lower()
    # Pause AND stop both close the student's active deals (a returning family gets a new
    # renewal deal; the win-back task drives that). Move ALL matching active deals (stale
    # data may leave several open) — but ONLY when a student name scopes it, so we never
    # touch a sibling's / the family's other deals.
    auto_types = set(da.get("auto_move_types", ["stop"]))
    can_auto = (ctype in auto_types
                and result.get("confidence", 0) >= da.get("min_confidence", 0.9)
                and bool(sf) and len(cands) >= 1)
    if can_auto:
        moves = []
        for dl in cands:
            stop_sid, stop_label = hs.find_stop_stage(dl["pipeline"], stop_pats)
            if not stop_sid:
                continue
            old = hs.stage_label(dl["pipeline"], dl["stage"])
            hs.move_deal_stage(dl["id"], stop_sid)
            moves.append({"deal_id": dl["id"], "deal_name": dl["name"], "from": old, "to": stop_label})
        if moves:
            listing = "; ".join(f"'{m['deal_name']}' {m['from']}→{m['to']}" for m in moves)
            return f"\n💸 Auto-moved {len(moves)} deal(s): {listing} (undo if wrong).", {"moves": moves}
    if cands:
        listing = "; ".join(f"{d['name']} [{hs.stage_label(d['pipeline'], d['stage'])}]" for d in cands)
        return f"\n💸 Review deal stage ({ctype or 'cancellation'}): {listing}", None
    return "", None


def _doc_receipt_text() -> str:
    return (ROOT / "templates" / "doc_receipt.md").read_text().strip()


def _followup_due_date(today: date) -> date:
    """+days from today, but never starting a win-back in a summer blackout month — those
    bump to the fall term start (Sep 1). Keeps reach-outs at term-starts / 90 days, not
    mid-summer when families are intentionally out."""
    cf = cfg().get("cancellation_followup", {})
    target = today + timedelta(days=int(cf.get("days", 90)))

    # Summer blackout (whole months) → fall start.
    if target.month in set(cf.get("blackout_months", [5, 6, 7])):
        mo, dy = (int(x) for x in str(cf.get("blackout_to", "09-01")).split("-"))
        bumped = date(target.year, mo, dy)
        target = bumped if bumped > today else date(target.year + 1, mo, dy)

    # Holiday blackout (date range that wraps year-end) → resume date.
    hb = cf.get("holiday_blackout") or {}
    if hb:
        s, e, r = (tuple(int(x) for x in str(hb[k]).split("-")) for k in ("start", "end", "resume"))
        md = (target.month, target.day)
        in_window = (md >= s or md <= e) if s > e else (s <= md <= e)
        if in_window:
            ry = target.year + 1 if target.month == 12 else target.year
            target = date(ry, r[0], r[1])
    return target


def _cancellation_followup(family_cid, family_email, owner_id, hs_priority, student_first,
                           family_label, result) -> str:
    """Schedule a re-engagement task with a sample email (due min(+days, by_date)), and —
    if a workflow id is configured — also enroll the family contact into a HubSpot
    re-engagement drip."""
    cf = cfg().get("cancellation_followup", {})
    if not cf.get("enabled"):
        return ""
    due = _followup_due_date(now_la().date())
    due_dt = datetime.combine(due, time(9, 0), tzinfo=LA)
    assign = cf.get("assign_to", "owner")
    task_owner = owner_id if assign == "owner" else (cfg()["staff"].get(assign, {}) or {}).get("hubspot_owner_id")
    student = student_first or "your student"
    sample = (ROOT / "templates" / "reengagement.md").read_text().strip().replace("{student}", student)
    ctype = result.get("cancellation_type") or "cancellation"
    body = (
        f"Win-back follow-up ({ctype}; reason: {result.get('cancellation_reason') or 'n/a'}).\n"
        f"Re-engage the {family_label or 'family'} for the new term. Start with the email below; "
        f"if no reply, follow up with a phone call around {due.isoformat()}. "
        f"If they resume, create a NEW deal marked dealtype=Existing Business (not a Renewal).\n\n"
        f"── Sample email to send first ──\n{sample}"
    )
    hs.create_task(f"Re-engage: {family_label or student} ({ctype})", body, task_owner,
                   int(due_dt.timestamp() * 1000), hs_priority, family_cid)
    line = f"\n📆 Re-engagement follow-up task set for {due.isoformat()} (sample email included)."
    wf = cf.get("reengage_workflow_id")
    if wf and family_email:
        try:
            hs.enroll_contact_in_workflow(wf, family_email)
            line += f"\n🔁 Enrolled {family_email} in re-engagement workflow {wf}."
        except Exception as e:  # noqa: BLE001 — enrollment is best-effort
            print(f"  ⚠️  workflow enrollment failed (non-fatal): {e}")
    return line


def _notify_owner(decision, text: str) -> None:
    """DM the routed owner, and CC a configured staffer (by NAME) if set."""
    if decision.owner and decision.owner.get("slack_user_id"):
        slack_client.dm(decision.owner["slack_user_id"], text)
    cc_key = cfg().get("notify", {}).get("cc_owner_dms_to")
    if cc_key and cc_key != decision.owner_key:
        cc = cfg()["staff"].get(cc_key, {})
        if cc.get("slack_user_id"):
            owner_name = (decision.owner or {}).get("name") or decision.owner_key or "unassigned"
            slack_client.dm(cc["slack_user_id"], f"📋 [copy → {owner_name}] {text}")


def _open_ticket_record_for_thread(thread_id: str) -> dict | None:
    """Most recent OPEN ticket on this conversation thread (one thread = one ticket).
    Returns the audit record that opened/last-touched it (carries ticket_id + owner +
    category), or None when there's no prior ticket OR the last one is closed — in which
    case a reply starts a fresh ticket. This is what stops a new ticket being created for
    every customer reply on an ongoing thread."""
    rec = None
    for r in audit._iter_records():
        if (r.get("thread_id") == thread_id
                and r.get("ticket_id") and r.get("ticket_id") != "DRYRUN"
                and r.get("action_taken") in ("ticket_created", "ticket_followup", "ticket_reopened")):
            rec = r  # _iter_records is chronological → last touch wins
    if not rec:
        return None
    closed = cfg()["hubspot"]["ticket_stages"].get("closed")
    try:
        t = hs.get_ticket(rec["ticket_id"])
    except Exception:  # noqa: BLE001 — if we can't read it, fall back to creating one
        return None
    if not t or (t.get("properties") or {}).get("hs_pipeline_stage") == closed:
        return None
    return rec


def _handle_followup(thread_id: str, message: dict, prior: dict, result: dict,
                     decision, base_record: dict, email: str, body: str) -> dict:
    """A customer reply on a thread that already has an open ticket: keep it ON that
    ticket. Append the new message as a note, re-draft the reply, re-open the ticket (with
    a fresh SLA window) if it was waiting on the family, and DM the ticket's owner. Never
    opens a second ticket."""
    ticket_id = prior["ticket_id"]
    hs_cfg = cfg()["hubspot"]
    stages = hs_cfg["ticket_stages"]
    record = dict(base_record)
    record["ticket_id"] = ticket_id
    # Continuity: a follow-up belongs to the ORIGINAL ticket's owner/category, not the
    # reply's fresh routing (a one-word "ok thanks" reply must not re-route the ticket).
    owner_key = prior.get("owner")
    record["owner"] = owner_key
    record["category"] = prior.get("category", decision.category)

    # Re-open if the ticket had moved to a waiting/handled stage — the family just
    # replied, so the ball is back with the owner.
    reopened = False
    try:
        t = hs.get_ticket(ticket_id)
        stage = (t.get("properties") or {}).get("hs_pipeline_stage")
        handled = {stages.get("handled"), hs_cfg.get("handled_stage_tutor")}
        if stage in handled and stages.get("needs_approval"):
            hs.update_ticket_stage(ticket_id, stages["needs_approval"])
            reopened = True
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  follow-up reopen check failed (non-fatal): {e}")
    record["reopened"] = reopened

    # Append the new inbound message as a note.
    subj = message.get("subject") or "(no subject)"
    try:
        hs.add_ticket_note(
            ticket_id,
            f"📧 Follow-up email — from {email or 'unknown'}\nSubject: {subj}\n\n"
            f"{(body or '(no text)')[:6000]}")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  follow-up note failed (non-fatal): {e}")

    # Re-draft the reply as an internal comment (same rules as a fresh ticket).
    draft_text = result.get("draft_reply") or ""
    is_teachworks = (email or "").lower().endswith("@teachworks.com")
    if decision.should_draft and draft_text.strip() and not is_teachworks:
        hs.post_comment(thread_id, f"[A+ draft reply — review & send]\n\n{draft_text}")
        record["draft_posted"] = True
    else:
        record["draft_posted"] = False

    # DM the ticket's owner that the customer replied.
    owner = cfg()["staff"].get(owner_key) if owner_key else None
    contact_name = email.split("@")[0] if email else "unknown"
    reopen_bit = " (re-opened)" if reopened else ""
    _notify_owner(SimpleNamespace(owner=owner, owner_key=owner_key),
                  f"↩️ Customer replied on existing ticket{reopen_bit} — {contact_name}. "
                  f"{hs.ticket_url(ticket_id)}")

    if reopened:
        # Fresh SLA window so the hourly sweep treats it as newly due, not an instant
        # breach against the old (already-elapsed) clock. A reply to a still-open ticket
        # keeps the original clock (action_taken=ticket_followup, no sla change).
        sla_hours = cfg()["routing"].get(record["category"], {}).get("sla_hours") or decision.sla_hours
        sla_due = add_business_hours(now_la(), sla_hours) if sla_hours else None
        record["sla_due"] = sla_due.isoformat() if sla_due else None
        record["action_taken"] = "ticket_reopened"
    else:
        record["action_taken"] = "ticket_followup"
    audit.append(record)
    print(f"  follow-up → ticket {ticket_id} (reopened={reopened})")
    return record


def process_message(thread_id: str, message: dict) -> dict | None:
    """Handle one inbound message end to end. Returns the audit record."""
    message_id = message.get("id")
    if not message_id or audit.already_processed(message_id):
        return None

    email = hs.sender_email(message) or ""
    body = message.get("text") or message.get("richText") or ""

    # ── Identify contact ──
    contact = hs.find_contact_by_email(email) if email else None
    new_contact = False
    if not contact and email:
        contact = hs.create_contact(email)
        new_contact = True
    contact_id = contact.get("id") if contact else None

    # ── Enrich (HubSpot CRM + Teachworks) ──
    hs_enrich = hs.contact_enrichment(contact_id) if contact_id else {}
    tw_enrich = tw.enrichment_for_email(email) if email else {"teachworks_match": False}
    summary = build_enrichment_summary(contact, hs_enrich, tw_enrich)

    # ── Classify ──
    result = classify(body, summary)
    # Parent last name (for A-L/M-Z split): email CONTENT first (the family the email is
    # about — e.g. Teachworks notices name the family), then the HubSpot contact, then TW.
    last_name = _parent_last_name(contact, tw_enrich, result)
    decision = resolve(result["category"], result["confidence"], last_name)
    contact_name = email.split("@")[0] if email else "unknown"

    # Pre-deal leads own their thread with sales support until a deal exists.
    # The A-L/M-Z split assumes an active family; a lead with no deal and no
    # Teachworks account isn't one, and scheduler-routing them drops the sale
    # (per Roman 2026-07-20, after the Deanna Smith miss).
    split = cfg()["scheduler_split"]
    predeal_intake = False
    if (decision.owner_key in (split["a_to_l"], split["m_to_z"])
            and (hs_enrich.get("properties") or {}).get("lifecyclestage") == "lead"
            and not hs_enrich.get("associated_deals")
            and not tw_enrich.get("teachworks_match")):
        decision.owner_key = "paola"
        decision.owner = cfg()["staff"].get("paola")
        decision.notes.append("pre-deal lead (no deal, no Teachworks account) — Paola owns until deal creation")
        predeal_intake = True

    # #4 Internal staff email → route to the teammate it's addressed to ("Hi Kath" → Kath)
    icfg = cfg().get("internal", {})
    idomain = (icfg.get("domain") or "").lower()
    internal_routed = False
    if email and idomain and email.lower().endswith("@" + idomain):
        rcpt = (result.get("internal_recipient") or "").strip().lower()
        staff = cfg()["staff"]
        key = next((k for k, s in staff.items()
                    if rcpt and (s.get("name", "").lower() == rcpt or k == rcpt)), None)
        key = key or icfg.get("fallback", "roman")
        decision.owner_key, decision.owner, decision.review = key, staff.get(key), False
        internal_routed = True

    # #3 Teachworks notice → link the ticket to the FAMILY contact (so the owner can
    # email the family straight from the ticket), not the no-reply Teachworks address.
    ticket_contact_id = contact_id
    family_email = email   # who to enroll / email; the sender, unless we resolve the family
    if email.lower().endswith("@teachworks.com") and last_name:
        fam = hs.find_family_contact(result.get("student_first_name") or "", last_name)
        if len(fam) == 1:
            ticket_contact_id = fam[0]["id"]
            family_email = (fam[0].get("properties") or {}).get("email") or email

    record = {
        "message_id": message_id,
        "thread_id": thread_id,
        "contact_id": contact_id,
        "new_contact": new_contact,
        "category": decision.category,
        "risk": result.get("risk"),
        "confidence": result["confidence"],
        "owner": decision.owner_key,
        "reason": result.get("reason"),
        "cancellation_reason": result.get("cancellation_reason") or "",
    }

    # ── Already-open ticket on this thread → keep the reply on it (one thread = one
    #    ticket) instead of spawning a new ticket per customer reply. Checked BEFORE junk
    #    archive so an active conversation is never archived as junk. ──
    prior = _open_ticket_record_for_thread(thread_id)
    if prior:
        return _handle_followup(thread_id, message, prior, result, decision, record, email, body)

    # ── Autonomy exception 1: junk → archive ──
    if decision.auto_archive:
        hs.archive_thread(thread_id)
        record["action_taken"] = "junk_archived"
        audit.append(record)
        print(f"  junk → archived thread {thread_id}")
        return record

    # ── SLA + ticket ──
    sla_due = add_business_hours(now_la(), decision.sla_hours) if decision.sla_hours else None
    owner_id = decision.owner.get("hubspot_owner_id") if decision.owner else None
    subject = _ticket_subject(decision.category, contact, result, last_name, contact_name)
    cancel_reason = record["cancellation_reason"]
    desc = (
        f"Auto-triaged by aplus_email_agent.\n"
        f"Category: {decision.category} | risk: {result.get('risk')} | "
        f"confidence: {result['confidence']:.2f}\n"
        f"Reason: {result.get('reason')}\n"
        + (f"Cancellation reason: {cancel_reason}\n" if cancel_reason else "")
        + f"SLA due: {sla_due.isoformat() if sla_due else 'n/a'}\n"
        f"Notes: {'; '.join(decision.notes) or 'none'}"
    )
    hs_cfg = cfg()["hubspot"]
    stuck = hs_cfg.get("stuck_stage")
    # Internal emails have a real owner → normal queue. Otherwise unknown/review → Stuck.
    if internal_routed:
        entry_stage = hs_cfg["ticket_stages"]["needs_approval"]
    elif stuck and (decision.category == "unknown" or decision.review):
        entry_stage = stuck
    else:
        entry_stage = hs_cfg["ticket_stages"]["needs_approval"]
    tf = cfg().get("ticket_fields", {})
    hs_priority = tf.get("priority_map", {}).get(decision.priority, "MEDIUM")
    if tf.get("priority_urgent_on_high_risk") and result.get("risk") == "high":
        hs_priority = "URGENT"
    if decision.category == "cancellation":   # category depends on the cancellation type (KPI)
        ccm = tf.get("cancellation_category_map", {})
        hs_category = ccm.get((result.get("cancellation_type") or "").lower(),
                              ccm.get("default", tf.get("category_default")))
    else:
        hs_category = tf.get("category_map", {}).get(decision.category, tf.get("category_default"))
    ticket = hs.create_ticket(subject, owner_id, entry_stage, desc, ticket_contact_id,
                              priority=hs_priority, category=hs_category, source=tf.get("source"))
    ticket_id = ticket.get("id")
    record["ticket_id"] = ticket_id
    record["sla_due"] = sla_due.isoformat() if sla_due else None

    # Attach the email two ways: (1) associate the conversation thread, and (2) post the
    # email body as a NOTE — the note reliably renders on the ticket in the UI even when
    # HubSpot's unlabeled conversation association doesn't surface the email.
    if ticket_id and ticket_id != "DRYRUN":
        try:
            hs.link_thread_to_ticket(thread_id, ticket_id)
        except Exception as e:  # noqa: BLE001 — best-effort, never block triage
            print(f"  ⚠️  thread→ticket link failed (non-fatal): {e}")
        try:
            subj = message.get("subject") or "(no subject)"
            hs.add_ticket_note(
                ticket_id,
                f"📧 Original email — from {email or 'unknown'}\nSubject: {subj}\n\n"
                f"{(body or '(no text)')[:6000]}")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  email-body note failed (non-fatal): {e}")

    # ── Autonomy exception 2: tutor_document → send receipt, then ticket to Kath ──
    if decision.category == DOC_RECEIPT:
        try:
            sent = _send_doc_receipt(thread_id, message)
            record["receipt_sent"] = True
            record["receipt_message_id"] = (sent or {}).get("id")
        except Exception as e:  # noqa: BLE001 — receipt is best-effort, never block the ticket
            record["receipt_sent"] = False
            record["receipt_error"] = str(e)[:150]
            print(f"  ⚠️  doc receipt send failed (non-fatal): {e}")

    # ── Draft reply as internal COMMENT (suppressed for no-draft + Teachworks no-reply;
    #     for Teachworks the draft still lives in the ticket note so the owner emails the
    #     family from the ticket) ──
    draft_text = result.get("draft_reply") or ""
    is_teachworks = email.lower().endswith("@teachworks.com")
    if decision.should_draft and draft_text.strip() and not is_teachworks:
        hs.post_comment(thread_id, f"[A+ draft reply — review & send]\n\n{draft_text}")
        record["draft_posted"] = True
    else:
        record["draft_posted"] = False

    # ── Returning family booking new service → create a deal (Existing Business) ──
    b2c_line = ""
    bd = cfg().get("b2c_deal", {})
    if (bd.get("enabled") and decision.category == "scheduling"
            and result.get("confidence", 0) >= bd.get("min_confidence", 0.9)):
        is_existing = (hs_enrich.get("associated_deals", 0) > 0
                       or tw_enrich.get("recent_lessons", 0) > 0)
        if is_existing:
            try:
                props = (contact or {}).get("properties") or {}
                parent = " ".join(filter(None, [props.get("firstname"), props.get("lastname")])) or contact_name
                student = (result.get("student_first_name") or "").strip()
                dname = f"{parent} - {student}" if student else parent
                # Pipeline = the family's most recent B2C deal's pipeline; fallback Gold.
                psm = bd.get("pipeline_stage_map", {})
                pipeline = bd.get("fallback_pipeline", "default")
                if contact_id:
                    prior = [dl for dl in hs.get_contact_deals(contact_id) if dl["pipeline"] in psm]
                    if prior:
                        pipeline = max(prior, key=lambda dl: int(dl["id"]))["pipeline"]
                close_ms = int((now_la() + timedelta(days=30)).timestamp() * 1000)
                d = hs.create_deal(dname, pipeline, psm.get(pipeline, "appointmentscheduled"),
                                   contact_id=contact_id, dealtype=bd.get("dealtype"),
                                   owner_id=owner_id, closedate_ms=close_ms,
                                   extra_props={"schedule_preferences": result.get("schedule_preference"),
                                                "student_grade": result.get("student_grade")})
                record["deal_created"] = d.get("id")
                b2c_line = f"\n💼 Created deal '{dname}' (Existing Business, Pre-Lesson), id {d.get('id')}."
            except Exception as e:  # noqa: BLE001 — best-effort
                print(f"  ⚠️  b2c deal create failed (non-fatal): {e}")

    # ── Pre-deal lead → suggest the deal, human creates it ──
    # New Business can't infer a pipeline from prior deals (there are none), so the
    # agent hands Paola a ready-to-create suggestion instead of guessing one into
    # the CRM and polluting funnel metrics.
    predeal_line = ""
    if predeal_intake:
        props = (contact or {}).get("properties") or {}
        parent = " ".join(filter(None, [props.get("firstname"), props.get("lastname")])) or contact_name
        student = (result.get("student_first_name") or "").strip()
        sug_name = f"{parent} - {student}" if student else parent
        pref = (result.get("schedule_preference") or "").strip()
        pref_bit = f" Schedule preference: {pref}." if pref else " Schedule preference: not stated."
        predeal_line = (
            f"\n🧲 PRE-DEAL LEAD — no deal on file; you own this until the deal exists. "
            f"Suggested deal: '{sug_name}' → Gold Tutoring / Pre-Lesson (switch pipeline if "
            f"Free Trial or In-Person fits better).{pref_bit} "
            f"Create it from the contact: {hs.contact_url(contact_id) if contact_id else '(no contact id)'}"
        )
        record["predeal_intake"] = True

    # ── Cancellation extras: deal automation + win-back + Teachworks verify ──
    deal_line, deal_rec, followup_line, tw_line = "", None, "", ""
    if decision.category == "cancellation":
        # Verify both Teachworks accounts for leftover future lessons (pause/stop only —
        # a one-time skip keeps the schedule).
        if (result.get("cancellation_type") or "").lower() in ("pause", "stop"):
            try:
                left = tw.upcoming_lessons_for_family(family_email, result.get("student_first_name"))
                if left:
                    listing = "; ".join(
                        f"{l['date']} {l['time']} {l['student']} w/ {l['tutor']} [{l['account']}]"
                        for l in left[:6])
                    more = f" (+{len(left)-6} more)" if len(left) > 6 else ""
                    tw_line = (f"\n⚠️ Teachworks: {len(left)} future lesson(s) still scheduled — "
                               f"remove them: {listing}{more}")
                else:
                    tw_line = "\n✅ Teachworks checked (both accounts): no future lessons remain."
                record["tw_lessons_left"] = len(left)
            except Exception as e:  # noqa: BLE001 — verify is best-effort
                print(f"  ⚠️  Teachworks verify failed (non-fatal): {e}")
        try:
            deal_line, deal_rec = _cancellation_deal_action(ticket_contact_id, result)
            if deal_rec:
                record["deal_moved"] = deal_rec
        except Exception as e:  # noqa: BLE001 — best-effort, never block triage
            print(f"  ⚠️  deal action failed (non-fatal): {e}")
        # Win-back only for pause/stop — a one-time skip isn't churn.
        if (result.get("cancellation_type") or "").lower() in ("pause", "stop"):
            try:
                followup_line = _cancellation_followup(
                    ticket_contact_id, family_email, owner_id, hs_priority,
                    result.get("student_first_name"), last_name, result)
                record["followup_scheduled"] = bool(followup_line)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  follow-up task failed (non-fatal): {e}")

    # ── HubSpot Task for the owner (due-dated to-do with reminders) ──
    owner_name = (decision.owner or {}).get("name") or decision.owner_key or "unassigned"
    task_line = ""
    if cfg().get("owner_task", {}).get("enabled") and owner_id and sla_due:
        tbody = (
            f"{result.get('reason')}\n"
            + (f"Cancellation reason: {cancel_reason}\n" if cancel_reason else "")
            + f"\nTicket: {hs.ticket_url(ticket_id) if ticket_id else ''}\n"
            f"Proposed reply:\n{draft_text or '(none — handle manually)'}"
        )
        try:
            hs.create_task(f"Reply: {decision.category} — {contact_name}", tbody,
                           owner_id, int(sla_due.timestamp() * 1000), hs_priority, ticket_contact_id)
            record["task_created"] = True
            task_line = f"\n✅ A HubSpot Task was created for {owner_name}, due {record['sla_due']} — check your Tasks queue."
        except Exception as e:  # noqa: BLE001 — task is best-effort, never block triage
            print(f"  ⚠️  task create failed (non-fatal): {e}")
            record["task_created"] = False

    # ── Ticket note (mirror audit; tells the owner a Task was created) ──
    note = (
        f"{subject}\nOwner: {decision.owner_key} | SLA due: {record['sla_due']}\n"
        f"Confidence: {result['confidence']:.2f}\nReason: {result.get('reason')}\n"
        + (f"Cancellation reason: {cancel_reason}\n" if cancel_reason else "")
        + task_line + deal_line + followup_line + tw_line + b2c_line + predeal_line
        + f"\n\nProposed reply:\n{draft_text or '(none — flagged for human handling)'}"
    )
    if ticket_id:
        hs.add_ticket_note(ticket_id, note)

    # ── owner Slack DM (+ CC) ──
    flag = " ⚠️ REVIEW (no draft)" if not record["draft_posted"] else ""
    reason_bit = f" Cancellation reason: {cancel_reason}." if cancel_reason else ""
    task_bit = " 📋 Task created." if record.get("task_created") else ""
    deal_bit = (f" 💸 {len(deal_rec['moves'])} deal(s) auto-moved (undo if wrong)." if deal_rec
                else (" 💸 check deal stage." if deal_line else ""))
    followup_bit = " 📆 re-engagement follow-up scheduled." if followup_line else ""
    n_left = record.get("tw_lessons_left")
    tw_bit = (f" ⚠️ {n_left} TW lesson(s) to remove." if n_left
              else (" ✅ TW schedule clear." if n_left == 0 else ""))
    b2c_bit = " 💼 deal created (Existing Business)." if record.get("deal_created") else ""
    predeal_bit = f" {predeal_line.strip()}" if predeal_line else ""
    notify_text = (
        f"New *{decision.category}* from {contact_name}{flag}.{reason_bit}{task_bit}{deal_bit}{followup_bit}{tw_bit}{b2c_bit}{predeal_bit} "
        f"Due {record['sla_due']}. {hs.ticket_url(ticket_id) if ticket_id else ''}"
    )
    _notify_owner(decision, notify_text)

    record["action_taken"] = "ticket_created"
    audit.append(record)
    print(f"  {decision.category} → {decision.owner_key} (ticket {ticket_id}, due {record['sla_due']})")
    return record


def _send_doc_receipt(thread_id: str, message: dict) -> dict:
    """The ONLY outbound MESSAGE the agent ever sends. Replies to the original sender
    from the configured agent actor. Raises if config/message fields are missing."""
    actor = cfg().get("doc_receipt", {}).get("sender_actor_id")
    senders = message.get("senders") or []
    di = senders[0].get("deliveryIdentifier") if senders else None
    ch, cha = message.get("channelId"), message.get("channelAccountId")
    if not (actor and di and ch and cha):
        raise RuntimeError(f"doc receipt missing fields (actor={bool(actor)}, di={bool(di)}, ch={ch})")
    return hs.send_message(
        thread_id, _doc_receipt_text(), channel_id=ch, channel_account_id=cha,
        sender_actor_id=actor, recipients=[{"recipientField": "TO", "deliveryIdentifier": di}],
    )


def run() -> None:
    require("HUBSPOT_PRIVATE_APP_TOKEN", "ANTHROPIC_API_KEY")
    print(f"=== triage run (DRY_RUN={DRY_RUN}) ===")
    from .config import HUBSPOT_PRIVATE_APP_TOKEN
    if not HUBSPOT_PRIVATE_APP_TOKEN:
        print("  HUBSPOT_PRIVATE_APP_TOKEN unset — cannot poll inbox. "
              "Set it (and run SETUP.md) before a real run. Nothing to do.")
        return
    inbox_id = str(cfg()["hubspot"].get("inbox_id") or "")
    since = audit.read_cursor().get("last_processed_ts")
    if not since:
        # First run: baseline at 'now' so we don't replay years of closed history.
        # (To backfill, set state/cursor.json last_processed_ts to a past timestamp.)
        since = datetime.now(timezone.utc).isoformat()
        audit.write_cursor({"last_processed_ts": since})
        print(f"  no cursor — baseline set to {since}. New mail is picked up next run.")
        return

    newest, after, processed, pages = since, None, 0, 0
    while pages < 50:  # hard cap — HubSpot can return a non-terminating paging cursor
        pages += 1
        data = hs.list_threads(latest_after=since, after=after)
        results = data.get("results", [])
        if not results:
            break  # empty page → done (HubSpot may still hand back a stale next cursor)
        for thread in results:
            if inbox_id and str(thread.get("inboxId")) != inbox_id:
                continue
            ts = thread.get("latestMessageTimestamp") or ""
            thread_id = thread.get("id")
            try:
                msg = hs.latest_inbound(thread_id)
                if msg and process_message(thread_id, msg):
                    processed += 1
            except Exception as e:  # noqa: BLE001 — never let one bad email kill the run
                print(f"  ⚠️  error on thread {thread_id}: {e}", file=sys.stderr)
                traceback.print_exc()
                audit.append({"thread_id": thread_id, "action_taken": "error", "error": str(e)})
            if ts > newest:
                newest = ts
        next_after = (data.get("paging") or {}).get("next", {}).get("after")
        if not next_after or next_after == after:
            break  # no/again-same cursor → done
        after = next_after

    audit.write_cursor({"last_processed_ts": newest})
    print(f"=== processed {processed} new message(s) ===")


if __name__ == "__main__":
    run()

"""Charter-PO inbox flow (separate Gmail).

Per new email: extract PO details with Claude — READING PDF/image attachments
(the actual PO document) natively — → HubSpot ticket to Kath (same accountability
spine as the admin inbox) → advance the matching "Waiting for PO" deal or create
one. Deals are named "Parent - Student - School N - YY/YY" (Roman, 2026-08-10).
Parent contact info found in the PO → the HubSpot contact is found-or-created
and associated to the deal (that's what lets the Teachworks sync create the
family); parent info missing → the deal is named "NEEDS PARENT - ..." and the
PARENT CHASE flow drafts an info request to the TOR (name+email+phone), catches
the reply, auto-creates the contact, renames the deal, and unblocks Teachworks;
no reply in the window → escalation DM.
POs NEVER get an extractor reply draft (the chase draft is the one exception, and
a human still sends it); non-PO mail gets one when warranted (drafts are REAL
Gmail drafts a human sends). Label → ticket → Slack DM Kath (+ CC) → audit.
The agent never sends from this address.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone

from . import audit, gmail_client as gm, hubspot_client as hs, slack_client, teachworks_client as tw
from .business_hours import add_business_hours, now_la
from .classifier import parse_classification  # reuse the tolerant JSON parser
from .config import ANTHROPIC_API_KEY, DRY_RUN, cfg

PO_SYSTEM = (
    "You process A+ Tutoring's charter-school PURCHASE ORDER inbox. The email may "
    "include PDF/image attachments (the actual PO document) — read them; PO details "
    "usually live there, not in the body. "
    "Respond with a SINGLE JSON object, no prose: {is_po (bool), school, student_first, "
    "student_last, grade, po_number, amount, hours, parent_first, parent_last, parent_email, "
    "parent_phone, tor_first, tor_last, tor_email, po_month, level_up (bool), summary, "
    "draft_reply, confidence (0-1)}. "
    "is_po=true ONLY for a NEW purchase order / funding authorization that starts or adds "
    "service. Invoice requests, invoicing follow-ups, payment reminders, statements, or "
    "questions about EXISTING service are NOT new POs → is_po=false (still extract "
    "school/student/po_number/amount and summarize; these get a review ticket, no deal). "
    "parent_* = the PARENT/GUARDIAN's contact info from the email or PO document — never "
    "the school staff, TOR, or education specialist; empty string for anything not stated. "
    "If the email is a REPLY providing a family's contact details (we ask TORs for parent "
    "info), extract them into parent_* even though is_po=false. "
    "tor_* = the Teacher of Record / education specialist handling this PO (often the "
    "email sender) — never the parent. "
    "If the email/attachments contain MULTIPLE distinct purchase orders (different PO "
    "numbers — schools often issue one per service month), ALSO return pos: an array "
    "[{po_number, amount, hours, po_month}, ...] with one entry per PO, each carrying "
    "ITS OWN amount/hours/month from the document; the top-level student/school/"
    "parent/TOR fields are shared. Omit pos for single-PO emails. school_bill_to = the school's exact billing "
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


def _stamp_deal_properties(deal_id, po: dict, note_parts: list[str]) -> None:
    """ALWAYS fill the core student properties on the deal — student first + last
    name, grade, school — via the internal names in po_inbox.deal_property_map.
    A separate non-fatal PATCH so a bad property name can never kill the deal."""
    pmap = cfg()["po_inbox"].get("deal_property_map") or {}
    values = {"student_first": po.get("student_first"), "student_last": po.get("student_last"),
              "grade": po.get("grade"), "school": po.get("school"),
              "parent_email": po.get("parent_email"), "parent_phone": po.get("parent_phone")}
    props = {pmap[k]: v for k, v in values.items() if pmap.get(k) and v}
    if not props or not deal_id or deal_id == "DRYRUN":
        missing = [k for k, v in values.items() if not v]
        if missing:
            note_parts.append(f"⚠️ Not in the PO: {', '.join(missing)} — fill on the deal manually.")
        return
    try:
        hs._write("PATCH", f"/crm/v3/objects/deals/{deal_id}", {"properties": props})
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  deal property stamp failed (non-fatal): {e}")
    missing = [k for k, v in values.items() if not v]
    if missing:
        note_parts.append(f"⚠️ Not in the PO: {', '.join(missing)} — fill on the deal manually.")


def _no_lessons_alert(po: dict, deal_name: str, note_parts: list[str]) -> None:
    """New PO for a student with NOTHING on the Teachworks calendar → post to the
    Slack channel (scheduling needs to move). Student already has upcoming lessons →
    stay quiet."""
    p_email = (po.get("parent_email") or "").strip().lower()
    upcoming = []
    try:
        if p_email:
            upcoming = tw.upcoming_lessons_for_family(p_email, po.get("student_first") or "")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  calendar check failed (treating as no lessons): {e}")
    if upcoming:
        note_parts.append(f"🗓️ {len(upcoming)} upcoming lesson(s) already on the calendar — "
                          "no scheduling alert.")
        return
    channel = (cfg()["po_inbox"].get("no_lessons_channel")
               or cfg()["slack"]["digest_channel"])
    student = f"{po.get('student_first', '')} {po.get('student_last', '')}".strip() or "student"
    slack_client.post_message(channel,
                              f"🗓️ New PO, nothing on the calendar: *{student}* "
                              f"({po.get('school') or 'school n/a'}) — deal '{deal_name}'. "
                              f"PO {po.get('po_number') or 'n/a'}, {po.get('hours') or '?'} hrs. "
                              f"Get them scheduled.")
    note_parts.append("🗓️ No upcoming lessons — scheduling alert posted to Slack.")


# Personas are stamped ONLY on contacts this agent CREATES (a_persona is a
# multi-select checkbox; a single value is a plain string, multiple are
# semicolon-separated). Existing contacts are never overwritten — the checkbox
# may already carry other personas.
TOR_CREATE_PROPS = {"hs_lead_status": "Charter School Teacher TOR/EF",
                    "a_persona": "Teacher of Record/EF/ES"}
FAMILY_CREATE_PROPS = {"a_persona": "Family"}


def _sync_family_tor(family_id, tor_id, tor_label: str, note_parts: list[str]) -> None:
    """#AP031: the PO is the source-of-truth event for teacher assignment —
    every incoming PO syncs the family's contact→contact "Teacher of Record"
    association (typeId 15, USER_DEFINED) so the links never go stale.

    ADD-only: a family already linked to a DIFFERENT TOR gets the new link
    ADDED and the change flagged on the ticket; existing links are NEVER
    auto-removed — multi-kid families legitimately have multiple TORs
    (different kids, different teachers). Removal is out of scope for v1.
    Best-effort like every other post-deal step."""
    if not family_id or not tor_id or "DRYRUN" in (str(family_id), str(tor_id)) \
            or str(family_id) == str(tor_id):
        return
    try:
        existing = hs.get_contact_to_contact_associations(family_id)
        linked_tor_ids = {str(r.get("toObjectId")) for r in existing
                          if any(t.get("typeId") == hs.TOR_ASSOC_TYPE_ID
                                 and t.get("category") == "USER_DEFINED"
                                 for t in r.get("associationTypes", []))}
        if str(tor_id) in linked_tor_ids:
            return  # already linked — no-op
        hs.associate_contacts(family_id, tor_id)
        if linked_tor_ids:
            note_parts.append(
                f"🔗 TOR CHANGE: family contact {family_id} was already linked to "
                f"different TOR(s) (contact id {', '.join(sorted(linked_tor_ids))}) — "
                f"ADDED {tor_label}; existing links kept (multi-kid families have "
                f"multiple TORs). Review whether the old link is stale.")
        else:
            note_parts.append(f"🔗 Family → TOR association created ({tor_label}, #AP031).")
    except Exception as e:  # noqa: BLE001 — association sync is best-effort
        print(f"  ⚠️  family→TOR association sync failed (non-fatal): {e}")
        note_parts.append("🔗 Family→TOR association sync failed — link manually (#AP031).")


def _associate_tor(deal_id, po: dict, note_parts: list[str],
                   family_contact_id=None) -> None:
    """Associate the Teacher of Record's contact to the deal (find-or-create by
    email), then sync the family→TOR contact association (#AP031). The parent
    stays the deal's family contact — the Teachworks sync picks the contact
    matching the deal-name parent, so adding the TOR is safe.

    TOR lookup order: primary email, then secondary email (some TORs' school
    address is a HubSpot secondary email; creating on a primary-only miss
    would duplicate them). Contacts created here are stamped with the TOR
    persona + lead status."""
    t_email = (po.get("tor_email") or "").strip().lower()
    p_email = (po.get("parent_email") or "").strip().lower()
    if not t_email or t_email == p_email or not deal_id or deal_id == "DRYRUN":
        return
    try:
        tor = hs.find_contact_by_email(t_email)
        if not tor:
            tor = hs.find_contact_by_secondary_email(t_email)
            if tor:
                note_parts.append(f"🧑‍🏫 TOR matched via SECONDARY email {t_email} "
                                  f"(primary is different) — no duplicate created.")
        if not tor:
            tor = hs.create_contact(t_email, po.get("tor_first") or None,
                                    po.get("tor_last") or None,
                                    extra_props=TOR_CREATE_PROPS)
            note_parts.append(f"🧑‍🏫 CREATED TOR contact <{t_email}> (persona + lead "
                              f"status stamped) — if this teacher already exists under "
                              f"a personal email, merge manually.")
        if tor and tor.get("id") not in (None, "DRYRUN"):
            hs.associate_contact_to_deal(deal_id, tor["id"])
            note_parts.append(f"🧑‍🏫 TOR {po.get('tor_first', '')} {po.get('tor_last', '')} "
                              f"<{t_email}> associated to the deal.")
            # #AP031 family→TOR sync: family id from the create path when known,
            # else resolved by the PO's parent email (lookup only, never create).
            fam_id = family_contact_id
            if not fam_id and p_email:
                fam = hs.find_contact_by_email(p_email)
                fam_id = fam.get("id") if fam else None
            tor_label = (f"{po.get('tor_first', '')} {po.get('tor_last', '')}".strip()
                         or t_email)
            _sync_family_tor(fam_id, tor.get("id"), tor_label, note_parts)
    except Exception as e:  # noqa: BLE001 — TOR association is best-effort
        print(f"  ⚠️  TOR association failed (non-fatal): {e}")


_MONTH_NAMES = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _po_month_end(po_month: str):
    """Last day of the PO's service month (5 PM PT) — the invoice due date. Accepts
    '2026-08', 'August 2026', 'Aug 2026', or '8/2026' (extractors drift on format —
    the Milo test returned the prose form). None if missing/unparseable."""
    import calendar
    raw = (po_month or "").strip()
    year = month = None
    m = re.match(r"^(\d{4})-(\d{1,2})$", raw)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
    if year is None:
        m = re.match(r"^([A-Za-z]{3,9})\.?,?\s+(\d{4})$", raw)
        if m and m.group(1)[:3].lower() in _MONTH_NAMES:
            year, month = int(m.group(2)), _MONTH_NAMES[m.group(1)[:3].lower()]
    if year is None:
        m = re.match(r"^(\d{1,2})[/-](\d{4})$", raw)
        if m:
            year, month = int(m.group(2)), int(m.group(1))
    if year is None:
        return None
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


def _norm_po_number(raw) -> str:
    """'PO7514044381' / 'P.O. #7514044381' / 'PO 7514044381' → '7514044381'
    (Roman, 2026-08-10: the number only, never a PO prefix). Letters that are
    PART of the number (e.g. Blue Ridge's 'PF593736') are kept."""
    s = str(raw or "").strip()
    return re.sub(r"^\s*P\.?\s*O\.?\s*[#:\-]?\s*", "", s, flags=re.I).strip()


def _split_pos(po: dict) -> list[dict]:
    """One deal per PO number (Roman, 2026-08-06: each PO number is its own
    deal, even when several arrive in one email — schools issue one per
    service month). Multi-PO emails come back from the extractor as pos=[...]
    sharing the top-level student/school/parent/TOR; as a fallback, a
    comma-jammed po_number field is split with per-PO amounts flagged for
    manual fill (better three deals missing an amount than one mashed deal)."""
    subs = po.get("pos") if isinstance(po.get("pos"), list) else []
    subs = [x for x in subs if isinstance(x, dict) and (x.get("po_number") or "").strip()]
    if len(subs) >= 2:
        return [{**po, "pos": None, "po_number": _norm_po_number(x["po_number"]),
                 "amount": x.get("amount"), "hours": x.get("hours"),
                 "po_month": x.get("po_month") or po.get("po_month")} for x in subs]
    nums = [_norm_po_number(n) for n in re.split(r"[,;]|\band\b", str(po.get("po_number") or ""))
            if _norm_po_number(n)]
    if len(nums) >= 2:
        return [{**po, "pos": None, "po_number": n, "amount": None, "hours": None,
                 "_split_amount_unknown": True} for n in nums]
    return [po]


def _handle_deal(po: dict, note_parts: list[str], attachments: list[dict] | None = None,
                 msg: dict | None = None) -> None:
    """One deal per PO in the email (usually one; see _split_pos)."""
    subs = _split_pos(po)
    if len(subs) > 1:
        note_parts.append(f"📑 Multi-PO email: {len(subs)} POs → one deal each "
                          f"({', '.join(x['po_number'] for x in subs)}).")
    for i, sub in enumerate(subs):
        if sub.get("_split_amount_unknown"):
            note_parts.append(f"⚠️ PO {sub['po_number']}: per-PO amount/hours not "
                              f"extracted — fill on the deal manually.")
        # scheduling alert once per email, not once per PO month; seq_offset
        # staggers 'School N' across sibling deals created in the same email
        _handle_one_po(sub, note_parts, attachments, no_lessons_check=(i == 0),
                       msg=msg, seq_offset=i)


def _school_short(school: str) -> tuple[str, bool]:
    """Shorthand school name from po_inbox.school_short_names (keys matched
    case-insensitively as substrings of the extracted name). Unmapped → the
    extracted name as-is, flagged so the mapping gets added."""
    s = (school or "").strip()
    for k, v in (cfg()["po_inbox"].get("school_short_names") or {}).items():
        if k.lower() in s.lower():
            return v, True
    return s, False


def _school_year_tag(po: dict) -> str:
    """'26/27' from the PO's service month — Aug-Dec belong to the first year,
    Jan-Jul to the second. No parseable month → today's date decides."""
    dt = _po_month_end(po.get("po_month") or "") or now_la()
    y = dt.year if dt.month >= 8 else dt.year - 1
    return f"{y % 100:02d}/{(y + 1) % 100:02d}"


def _next_school_seq(po: dict, short: str, year_tag: str) -> int:
    """N in 'School N': this student's existing deal count at this school this
    school year + 1. Counted from deal names (search by student first name,
    filter by school + year tag) — best-effort, defaults to 1."""
    sf = (po.get("student_first") or "").strip()
    if not sf or not short:
        return 1
    try:
        cands = hs.search_deals_by_name(sf)
    except Exception:  # noqa: BLE001 — naming must never block the deal
        return 1
    n = 0
    for d in cands:
        dn = ((d.get("properties") or {}).get("dealname") or "").lower()
        if short.lower() in dn and year_tag in dn and sf.lower() in dn:
            n += 1
    return n + 1


def _deal_name(po: dict, parent_name: str, note_parts: list[str],
               seq_offset: int = 0) -> str:
    """Roman's convention (2026-08-10): 'Parent - Student - School N - YY/YY'.
    Parent unresolved → 'NEEDS PARENT - ...' until the chase flow fills it in.
    seq_offset staggers N across the deals of one multi-PO email (the HubSpot
    search index won't see sibling deals created milliseconds earlier)."""
    short, mapped = _school_short(po.get("school") or "")
    year = _school_year_tag(po)
    student = f"{po.get('student_first', '')} {po.get('student_last', '')}".strip()
    seq = _next_school_seq(po, short, year) + seq_offset
    if short and not mapped:
        note_parts.append(f"🏫 School '{short}' has no shorthand — add it to "
                          f"po_inbox.school_short_names in config.yaml.")
    school_bit = f"{short} {seq}".strip() if short else ""
    return " - ".join(x for x in [parent_name or "NEEDS PARENT", student,
                                  school_bit, year] if x)


def _open_chases() -> dict:
    """thread_id → latest parent chase still awaiting the TOR's reply."""
    opened, resolved = {}, set()
    for r in audit._iter_records():
        if r.get("action_taken") == "parent_chase_opened" and r.get("thread_id"):
            opened[r["thread_id"]] = r
        elif r.get("action_taken") == "parent_chase_resolved":
            resolved.add(r.get("thread_id"))
    return {t: r for t, r in opened.items() if t not in resolved}


def _open_parent_chase(deal_id, deal_name: str, pipeline_id: str, po: dict,
                       msg: dict | None, note_parts: list[str]) -> None:
    """Parent info missing → the deal (and everything downstream: Teachworks
    family/student, scheduling, invoice hours) is blocked. Chase it: DRAFT a
    parent-info request (name + email + phone) to the TOR — else the sender —
    on the same thread. A human sends the draft (this agent never sends from
    charter@); the reply is caught by _resolve_parent_chase."""
    ch = cfg()["po_inbox"].get("parent_chase", {})
    if not ch.get("enabled") or not msg or not deal_id or deal_id == "DRYRUN":
        return
    to_addr = (po.get("tor_email") or "").strip()
    if not to_addr:
        m = re.search(r"<([^>]+)>", msg.get("sender") or "")
        to_addr = m.group(1) if m else (msg.get("sender") or "")
    if not to_addr:
        note_parts.append("📨 No TOR/sender address to ask for parent info — chase manually.")
        return
    student = f"{po.get('student_first', '')} {po.get('student_last', '')}".strip() or "the student"
    greeting = f"Hi {po.get('tor_first')}".strip() if po.get("tor_first") else "Hi"
    body = (f"{greeting},\n\n"
            f"Thank you for the purchase order for {student}. To get scheduling set up "
            f"we still need the parent/guardian's contact information:\n\n"
            f"  - Parent/guardian full name\n"
            f"  - Email address\n"
            f"  - Phone number\n\n"
            f"Could you reply with those when you have a moment? We'll take it from there.\n\n"
            f"A+ Tutoring Team")
    try:
        gm.create_draft_reply(msg["threadId"], to_addr, msg.get("subject") or "",
                              body, msg.get("message_id_header", ""))
    except Exception as e:  # noqa: BLE001 — chase failure must not block the deal
        print(f"  ⚠️  parent-chase draft failed (non-fatal): {e}")
        note_parts.append(f"📨 Could not draft the parent-info request to {to_addr} — ask manually.")
        return
    due = add_business_hours(now_la(), int(ch.get("escalate_business_hours", 16)))
    audit.append({"message_id": f"parent-chase:{deal_id}", "source": "po_inbox",
                  "action_taken": "parent_chase_opened", "deal_id": deal_id,
                  "deal_name": deal_name, "pipeline": pipeline_id,
                  "po_number": (po.get("po_number") or "").strip(),
                  "thread_id": msg["threadId"], "student": student,
                  "school": po.get("school") or "",
                  "tor_email": (po.get("tor_email") or "").strip().lower(),
                  "chase_to": to_addr, "sla_due": due.isoformat()})
    note_parts.append(f"📨 Parent-info request DRAFTED to {to_addr} — SEND it from Gmail "
                      f"Drafts; the reply auto-creates the contact and unblocks Teachworks.")


def _resolve_parent_chase(chase: dict, po: dict, note_parts: list[str]) -> None:
    """The TOR replied with the parent's info → create/find the Family contact
    (email + phone + persona), associate it to the waiting deal, swap 'NEEDS
    PARENT' for the real name, link family→TOR (#AP031), and run the Teachworks
    sync NOW — the whole downstream chain unblocks with zero manual data entry."""
    deal_id = chase.get("deal_id")
    p_email = (po.get("parent_email") or "").strip().lower()
    if not deal_id or not p_email:
        return
    try:
        c = hs.find_contact_by_email(p_email)
        created = False
        if not c:
            c = hs.create_contact(p_email, po.get("parent_first") or None,
                                  po.get("parent_last") or None,
                                  phone=po.get("parent_phone") or None,
                                  extra_props=FAMILY_CREATE_PROPS)
            created = True
        cid = c.get("id")
        if not cid or cid == "DRYRUN":
            return
        hs.associate_contact_to_deal(deal_id, cid)
        props = c.get("properties") or {}
        parent_name = (f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
                       or f"{po.get('parent_first', '')} {po.get('parent_last', '')}".strip()
                       or p_email.split("@")[0])
        old_name = chase.get("deal_name") or ""
        new_name = old_name
        if "NEEDS PARENT" in old_name:
            new_name = old_name.replace("NEEDS PARENT", parent_name)
            try:
                hs._write("PATCH", f"/crm/v3/objects/deals/{deal_id}",
                          {"properties": {"dealname": new_name}})
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  deal rename failed (non-fatal): {e}")
                new_name = old_name
        # parent email/phone deal properties (same map as at PO time)
        pmap = cfg()["po_inbox"].get("deal_property_map") or {}
        stamps = {pmap[k]: v for k, v in {"parent_email": p_email,
                                          "parent_phone": po.get("parent_phone")}.items()
                  if pmap.get(k) and v}
        if stamps:
            try:
                hs._write("PATCH", f"/crm/v3/objects/deals/{deal_id}", {"properties": stamps})
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  parent property stamp failed (non-fatal): {e}")
        t_email = (chase.get("tor_email") or "").strip().lower()
        if t_email and t_email != p_email:
            tor = (hs.find_contact_by_email(t_email)
                   or hs.find_contact_by_secondary_email(t_email))
            if tor and tor.get("id"):
                _sync_family_tor(cid, tor["id"], t_email, note_parts)
        note_parts.append(f"💼 PARENT RESOLVED: {parent_name} <{p_email}> "
                          f"({'contact created' if created else 'existing contact'}) "
                          f"associated to deal '{new_name}' (id {deal_id}).")
        audit.append({"message_id": f"parent-chase-resolved:{deal_id}", "source": "po_inbox",
                      "action_taken": "parent_chase_resolved", "deal_id": deal_id,
                      "thread_id": chase.get("thread_id"), "parent_email": p_email})
        try:
            from . import deal_sync
            rec = deal_sync.sync_deal({"id": deal_id, "properties": {
                "pipeline": chase.get("pipeline") or cfg()["po_inbox"]["deal_pipeline_id"],
                "dealname": new_name,
                "po_number": chase.get("po_number") or ""}}) or {}
            note_parts.append(f"🔄 Teachworks sync ran immediately: "
                              f"{rec.get('action_taken', 'skipped')}.")
        except Exception as e:  # noqa: BLE001 — the 15-min sync will retry
            print(f"  ⚠️  immediate TW sync failed (cron will retry): {e}")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  parent-chase resolution failed (non-fatal): {e}")
        note_parts.append("💼 Parent info received but auto-resolution FAILED — "
                          "create/associate the contact manually.")


def _sweep_parent_chases() -> None:
    """Chase past its window with no reply → one escalation DM to the owner
    (chase by phone). Never re-pings a deal."""
    pc = cfg()["po_inbox"]
    if not pc.get("parent_chase", {}).get("enabled"):
        return
    escalated = {r.get("deal_id") for r in audit._iter_records()
                 if r.get("action_taken") == "parent_chase_escalated"}
    now = now_la()
    owner = cfg()["staff"].get(pc.get("owner", "kath"), {})
    for r in _open_chases().values():
        if r.get("deal_id") in escalated:
            continue
        try:
            due = datetime.fromisoformat(r["sla_due"])
        except (KeyError, TypeError, ValueError):
            continue
        if now <= due:
            continue
        slack_client.dm(owner.get("slack_user_id"),
                        f"⏰ Still NO parent info for deal '{r.get('deal_name')}' — "
                        f"asked {r.get('chase_to')} on {(r.get('timestamp') or '')[:10]} "
                        f"with no reply. The Teachworks family can't be created until we "
                        f"have the parent's name, email, and phone — chase by phone.")
        audit.append({"message_id": f"parent-chase-escalation:{r.get('deal_id')}",
                      "source": "po_inbox", "action_taken": "parent_chase_escalated",
                      "deal_id": r.get("deal_id"), "thread_id": r.get("thread_id")})


def _find_parent_via_deals(po: dict):
    """POs typically DON'T include parent info — Kath's manual fix was to
    look the student up in HubSpot and read the parent off their prior deal
    (deals are named 'Parent - Student - School (Month)' and carry the family
    contact). Mechanized: search deals by the student's first name, narrow to
    names also containing the student's last name when possible, collect the
    deals' non-TOR contacts — a UNIQUE parent across matches resolves it;
    anything ambiguous falls through to the last-name search, then manual.
    Returns (contact, deal_name) or None."""
    sf = (po.get("student_first") or "").strip()
    sl = (po.get("student_last") or "").strip().lower()
    t_email = (po.get("tor_email") or "").strip().lower()
    if not sf:
        return None
    try:
        cands = hs.search_deals_by_name(sf)
        if not cands:
            return None
        narrowed = [d for d in cands
                    if sl and sl in ((d.get("properties") or {}).get("dealname") or "").lower()] or cands
        parents = {}
        for d in narrowed[:6]:
            for c in hs.get_deal_contacts(d["id"]):
                props = c.get("properties") or {}
                em = (props.get("email") or "").lower()
                if t_email and em == t_email:
                    continue                      # the TOR is on deals too — never the parent
                if "Teacher of Record" in (props.get("a_persona") or ""):
                    continue
                parents[str(c.get("id"))] = (c, (d.get("properties") or {}).get("dealname", "?"))
        if len(parents) == 1:
            return next(iter(parents.values()))
    except Exception as e:  # noqa: BLE001 — parent resolution is best-effort
        print(f"  ⚠️  prior-deal parent lookup failed (non-fatal): {e}")
    return None


def _handle_one_po(po: dict, note_parts: list[str], attachments: list[dict] | None = None,
                   no_lessons_check: bool = True, msg: dict | None = None,
                   seq_offset: int = 0) -> None:
    """Advance the matching Waiting-for-PO deal, or create one."""
    pc = cfg()["po_inbox"]
    student = (po.get("student_last") or po.get("student_first") or "").strip()
    school = (po.get("school") or "").strip()
    token = student or school
    if not token:
        note_parts.append("💼 No student/school extracted — no deal action; review manually.")
        return
    # PO-number dedupe via the canonical po_number PROPERTY (then name as backstop).
    po_num = _norm_po_number(po.get("po_number"))
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
        # Resolve the PARENT contact FIRST — the deal name leads with the parent
        # (Roman, 2026-08-10), and the Teachworks sync keys the family on the
        # deal's contact email, so a deal without a parent contact never reaches
        # Teachworks. Best source: parent info extracted from the PO itself (find
        # the HubSpot contact by email, CREATE it if new); fallback: the student's
        # prior deal, then a unique student-name match against family contacts.
        contact_id = None
        contact_bit = ""
        parent_name = ""
        p_email = (po.get("parent_email") or "").strip().lower()
        if p_email:
            try:
                existing = hs.find_contact_by_email(p_email)
                if existing:
                    contact_id = existing["id"]
                    xp = existing.get("properties") or {}
                    parent_name = (f"{xp.get('firstname', '')} {xp.get('lastname', '')}".strip()
                                   or f"{po.get('parent_first', '')} {po.get('parent_last', '')}".strip())
                    contact_bit = f"linked to existing contact {p_email}, "
                else:
                    created_c = hs.create_contact(p_email, po.get("parent_first") or None,
                                                  po.get("parent_last") or None,
                                                  phone=po.get("parent_phone") or None,
                                                  extra_props=FAMILY_CREATE_PROPS)
                    contact_id = created_c.get("id")
                    parent_name = f"{po.get('parent_first', '')} {po.get('parent_last', '')}".strip()
                    contact_bit = (f"CREATED HubSpot contact {po.get('parent_first', '')} "
                                   f"{po.get('parent_last', '')} <{p_email}> from the PO, ")
            except Exception as e:  # noqa: BLE001 — contact handling is best-effort
                print(f"  ⚠️  parent-contact create/lookup failed (non-fatal): {e}")
        if not contact_id:
            found = _find_parent_via_deals(po)
            if found:
                c, dn = found
                contact_id = c.get("id")
                parent_name = (f"{(c.get('properties') or {}).get('firstname', '')} "
                               f"{(c.get('properties') or {}).get('lastname', '')}").strip()
                contact_bit = (f"parent {parent_name or 'parent'} resolved from the "
                               f"student's prior deal '{dn}', ")
        if not contact_id:
            try:
                parents = hs.find_family_contact(po.get("student_first") or "",
                                                 po.get("student_last") or "")
            except Exception:  # noqa: BLE001
                parents = []
            if len(parents) == 1:
                contact_id = parents[0]["id"]
                parent_name = (f"{parents[0]['properties'].get('firstname', '')} "
                               f"{parents[0]['properties'].get('lastname', '')}").strip()
                contact_bit = f"linked to family contact {parent_name}, "
        if not contact_id:
            contact_bit = ("NO parent contact info in the PO and no unique family match — "
                           "parent-info request drafted to the TOR/sender (see 📨); once it "
                           "lands the contact is auto-created and associated, ")
        if contact_id and not parent_name and p_email:
            parent_name = p_email.split("@")[0]
        name = _deal_name(po, parent_name, note_parts, seq_offset)
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
        _associate_tor(d.get("id"), po, note_parts, family_contact_id=contact_id)
        _stamp_deal_properties(d.get("id"), po, note_parts)
        _attach_po_to_deal(d.get("id"), attachments or [], po, note_parts)
        _invoice_task(d.get("id"), po, note_parts)
        if not contact_id:
            _open_parent_chase(d.get("id"), name, pipeline_id, po, msg, note_parts)
        if no_lessons_check:
            _no_lessons_alert(po, name, note_parts)
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
    """One PO conversation = one ticket — but only a thread where a REAL PO was
    already processed is closed. A thread whose only record is a review ticket
    (e.g. an order agreement marked 'THIS IS NOT A PO') stays OPEN: the actual
    POs often arrive as replies on that same thread, and skipping them would
    silently drop deals (the iLEAD/Jaramillo case, 2026-08-06)."""
    for r in audit._iter_records():
        if r.get("source") == "po_inbox" and r.get("thread_id") == thread_id \
                and r.get("category") == "new_po":
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
    po["po_number"] = _norm_po_number(po.get("po_number"))
    if isinstance(po.get("pos"), list):
        for x in po["pos"]:
            if isinstance(x, dict) and x.get("po_number"):
                x["po_number"] = _norm_po_number(x["po_number"])
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
        _handle_deal(po, note_parts, attachments, msg=m)
        labels = [pc["label_processed"]] + ([f"School/{po['school'][:40]}"] if po.get("school") else [])
    else:
        labels = [pc["label_review"]]
        # A reply on a thread with an open parent chase that carries the parent's
        # info → auto-create the contact and unblock the waiting deal.
        chase = _open_chases().get(m["threadId"])
        if chase and (po.get("parent_email") or "").strip():
            _resolve_parent_chase(chase, po, note_parts)
            record["category"] = "parent_info_reply"
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
    try:
        _sweep_parent_chases()
    except Exception as e:  # noqa: BLE001 — the sweep must never kill the run
        print(f"  ⚠️  parent-chase sweep failed (non-fatal): {e}")
    if not DRY_RUN:
        cur_path.write_text(_json.dumps({"last_epoch": newest}))


if __name__ == "__main__":
    run()

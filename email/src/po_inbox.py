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

from . import audit, draft_feedback, gmail_client as gm, hubspot_client as hs, slack_client, teachworks_client as tw
from .business_hours import add_business_hours, now_la
from .classifier import parse_classification  # reuse the tolerant JSON parser
from .config import ANTHROPIC_API_KEY, DRY_RUN, cfg, staff

PO_SYSTEM = (
    "You process A+ Tutoring's charter-school PURCHASE ORDER inbox. The email may "
    "include PDF/image attachments (the actual PO document) — read them; PO details "
    "usually live there, not in the body. "
    "Respond with a SINGLE JSON object, no prose: {is_po (bool), pending_approval (bool), "
    "school, student_first, "
    "student_last, grade, po_number, amount, rate, hours, parent_first, parent_last, "
    "parent_email, "
    "parent_phone, tor_first, tor_last, tor_email, tutor_name, po_month, level_up (bool), "
    "summary, draft_reply, confidence (0-1)}. "
    "tutor_name = the A+ tutor named on the PO/order agreement, if any (e.g. 'Jacquelyn Lemerond'). "
    "rate = the HOURLY RATE stated in the PO (number only, e.g. 75). hours = the hours "
    "stated in the PO; if the PO states only an amount and a rate, leave hours empty — "
    "we compute it. "
    "amount = the PO/authorization VALUE — what we invoice the school. OPS/iLEAD forms "
    "often show BOTH the PO value AND a smaller vendor payout net of the platform fee "
    "(e.g. Value 150.00 but payout 140.00): ALWAYS use the PO value / 'Total Cost' "
    "figures, NEVER the net payout — for the top-level amount and every pos[] entry. "
    "is_po=true ONLY for a NEW purchase order / funding authorization that starts or adds "
    "service. Order Agreements / Vendor Agreement Forms that list purchase orders for a "
    "student (the OPS/iLEAD pattern) ARE POs even when the document is stamped 'THIS IS "
    "NOT A PO' — set is_po=true AND pending_approval=true (the school still has to approve "
    "them in its ordering portal); pending_approval=false for a normally issued PO. "
    "Invoice requests, invoicing follow-ups, payment reminders, statements, or "
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
    "parent/TOR fields are shared. Omit pos for single-PO emails. "
    "If ONE certificate/PO covers MULTIPLE STUDENTS (Heartland/Procurify-style service "
    "certificates), return pos with one entry PER STUDENT (per month when months "
    "differ) — each entry ALSO carries its own student_first, student_last, grade, and "
    "parent_* when stated per family; synthesize unique po_number values as "
    "'<PO>-<StudentFirstLast>' when the certificate has one number for all students. school_bill_to = the school's exact billing "
    "name/address from the PO (schools reject invoices with a wrong Bill To); empty if "
    "not stated. "
    "draft_reply rules: if is_po → ALWAYS empty string (we never reply to purchase "
    "orders). Draft ONLY when a NAMED HUMAN directly asked A+ a question or requested "
    "an action needing a written reply. ALWAYS empty for: mass/bulk notices, "
    "welcome/onboarding confirmations, compliance broadcasts, DocuSign/portal/system "
    "notifications, auto-acknowledgments, payment confirmations, newsletters, spam, and "
    "anything from a noreply/notifications address. When drafting: short and warm, first "
    "person plural, no em dashes, signed 'A+ Tutoring Team'. If the email is NOT PO-related (spam, misc), set "
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
        model=c["model"], max_tokens=c["max_tokens"],
        system=PO_SYSTEM + draft_feedback.style_rules_prompt(),
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
              "parent_email": po.get("parent_email"), "parent_phone": po.get("parent_phone"),
              "tor_name": f"{po.get('tor_first', '')} {po.get('tor_last', '')}".strip(),
              "tor_email": po.get("tor_email")}
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


def _fmt_time(hhmm: str) -> str:
    """'15:30' → '3:30 PM'; anything unparseable comes back as-is."""
    try:
        h, m = (hhmm or "").split(":")
        h = int(h)
        return f"{(h - 1) % 12 + 1}:{m} {'PM' if h >= 12 else 'AM'}"
    except (ValueError, AttributeError):
        return hhmm or ""


def _schedule_text(lessons: list[dict]) -> str:
    """Human schedule line for the SMS from lesson slots — grouped into
    recurring (weekday, time, tutor) patterns, most frequent first:
    'Wednesdays 3:30 PM with Sarah, Fridays 4:00 PM with Sarah'."""
    from collections import Counter
    from datetime import date as _date
    slots: Counter = Counter()
    for l in lessons or []:
        try:
            wd = _date.fromisoformat(str(l.get("date"))[:10]).strftime("%A")
        except ValueError:
            continue
        slots[(wd, (l.get("time") or "").strip(), (l.get("tutor") or "").strip())] += 1
    parts = []
    for (wd, t, tut), _n in slots.most_common(4):
        bit = wd + "s" + (f" {_fmt_time(t)}" if t else "")
        if tut:
            bit += f" with {tut}"
        parts.append(bit)
    return ", ".join(parts)


def _student_activity(email: str, student_first: str, cache: dict | None = None,
                      parent_name: str = ""):
    """The PO student's Teachworks lesson signal {found, recent, upcoming},
    memoized per run (multi-PO emails share one lookup). None = could NOT check
    (no email / TW error) — the caller must treat None as UNKNOWN, never as a
    verified answer. The parent's name rides along so the TW lookup survives
    duplicate/inactive customer records that own the email (Aly Daly case)."""
    key = ((email or "").strip().lower(), (student_first or "").strip().lower())
    if not key[0] or not key[1]:
        return None
    cache = cache if cache is not None else {}
    if key not in cache:
        p_parts = (parent_name or "").strip().split()
        try:
            days = int(cfg()["po_inbox"].get("currently_tutored_lookback_days", 30))
            cache[key] = tw.student_lesson_activity(
                key[0], student_first, lookback_days=days,
                parent_first=p_parts[0] if p_parts else "",
                parent_last=" ".join(p_parts[1:]) if len(p_parts) > 1 else "")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  calendar check failed: {e}")
            cache[key] = None
    return cache[key]


def _no_lessons_alert(po: dict, deal_name: str, note_parts: list[str],
                      upcoming=None) -> None:
    """New PO for a student with NOTHING on the Teachworks calendar → post to the
    Slack channel (scheduling needs to move). Student already has upcoming lessons →
    stay quiet. `upcoming` is the precomputed upcoming-lesson COUNT (None =
    unverifiable → alert anyway, better loud than silent)."""
    if upcoming:
        note_parts.append(f"🗓️ {upcoming} upcoming lesson(s) already on the calendar — "
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


def _fold_name(s: str) -> str:
    """Accent-insensitive comparison key ('Véronique' == 'Veronique')."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c)).strip().lower()


def _tor_by_name(first: str, last: str) -> list[dict]:
    """Existing TOR contacts matching a bare name from the PO. Last name via
    HubSpot search (TOR-flagged only), first name compared accent-insensitively
    here — the portal stores 'Véronique', the PDF says 'Veronique'."""
    if not (last or "").strip():
        return []
    try:
        cands = hs.find_tor_contacts_by_lastname(last.strip())
    except Exception:  # noqa: BLE001 — fallback lookup is best-effort
        return []
    ff = _fold_name(first)
    if not ff:
        return cands
    exact = [c for c in cands
             if _fold_name((c.get("properties") or {}).get("firstname") or "") == ff]
    if exact:
        return exact
    # First-name VARIANT (PO said 'Christina', portal has 'Christine'): a
    # UNIQUE last-name match within the TOR-flagged pool is trusted anyway;
    # multiple candidates still fall through to the manual flag.
    return cands if len(cands) == 1 else []


def _heal_tor_contact(tor: dict, note_parts: list[str]) -> None:
    """Deal automations flip TOR lead status to customer values when a teacher
    lands on a deal (OPEN_DEAL — the Mary Nieves SMS incident, 2026-08-13).
    Whenever the agent touches a TOR contact it re-asserts the TOR persona
    (append-only) and lead status, so the teacher marker never decays. Skips
    dual-role contacts (persona also Family) — their status is legitimately
    customer-driven."""
    props = tor.get("properties") or {}
    if not props or tor.get("id") in (None, "DRYRUN"):
        return
    vals = [v for v in (props.get("a_persona") or "").split(";") if v]
    fixes = {}
    if TOR_CREATE_PROPS["a_persona"] not in vals:
        fixes["a_persona"] = ";".join(vals + [TOR_CREATE_PROPS["a_persona"]])
    if "hs_lead_status" in props and "Family" not in vals \
            and props.get("hs_lead_status") != hs.TOR_LEAD_STATUS:
        fixes["hs_lead_status"] = hs.TOR_LEAD_STATUS
    if not fixes:
        return
    try:
        hs._write("PATCH", f"/crm/v3/objects/contacts/{tor['id']}", {"properties": fixes})
        note_parts.append(f"🧑‍🏫 TOR contact healed ({', '.join(fixes)} re-asserted — "
                          f"deal automations flip these).")
    except Exception as e:  # noqa: BLE001 — healing is best-effort
        print(f"  ⚠️  TOR heal failed (non-fatal): {e}")


def _associate_tor(deal_id, po: dict, note_parts: list[str],
                   family_contact_id=None) -> None:
    """Associate the Teacher of Record's contact to the deal (find-or-create by
    email), then sync the family→TOR contact association (#AP031). The parent
    stays the deal's family contact — the Teachworks sync picks the contact
    matching the deal-name parent, so adding the TOR is safe.

    TOR lookup order: primary email, then secondary email (some TORs' school
    address is a HubSpot secondary email; creating on a primary-only miss
    would duplicate them). Contacts created here are stamped with the TOR
    persona + lead status.

    NAME-only fallback (Roman, 2026-08-10): OPS/iLEAD PDFs name the TOR without
    an email — a UNIQUE match among existing TOR-flagged contacts is associated
    (lookup only, never created from a bare name); anything else is flagged on
    the ticket instead of skipping silently."""
    t_email = (po.get("tor_email") or "").strip().lower()
    p_email = (po.get("parent_email") or "").strip().lower()
    t_name = f"{po.get('tor_first', '')} {po.get('tor_last', '')}".strip()
    if not deal_id or deal_id == "DRYRUN" or (t_email and t_email == p_email) \
            or not (t_email or t_name):
        return
    try:
        tor = None
        if t_email:
            tor = hs.find_contact_by_email(
                t_email, properties=["email", "firstname", "lastname",
                                     "a_persona", "hs_lead_status"])
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
        else:
            matches = _tor_by_name(po.get("tor_first") or "", po.get("tor_last") or "")
            if len(matches) == 1:
                tor = matches[0]
                resolved = ((tor.get("properties") or {}).get("email") or "").strip().lower()
                if resolved:
                    # feeds the teacher_of_record_email deal stamp downstream
                    po["tor_email"] = resolved
                note_parts.append(f"🧑‍🏫 TOR {t_name} matched by NAME (PO had no email) → "
                                  f"existing TOR contact <{resolved or '?'}>.")
            else:
                note_parts.append(f"🧑‍🏫 TOR '{t_name}' named in the PO without an email; "
                                  f"{'multiple' if matches else 'no'} matching TOR "
                                  f"contacts in HubSpot — associate manually.")
                return
        if tor and tor.get("id") not in (None, "DRYRUN"):
            _heal_tor_contact(tor, note_parts)
            hs.associate_contact_to_deal(deal_id, tor["id"])
            display = t_email or (tor.get("properties") or {}).get("email") or "no email"
            note_parts.append(f"🧑‍🏫 TOR {po.get('tor_first', '')} {po.get('tor_last', '')} "
                              f"<{display}> associated to the deal.")
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
        owner = staff(ic.get("owner", "kath"))
        due = add_business_hours(now_la(), int(ic.get("due_business_hours", 8)))
        submit_line = (f"Submit to the school's ops system by: "
                       f"{month_end.strftime('%b %-d, %Y')} (end of PO month "
                       f"{po.get('po_month')}) — you'll be prompted when it's time." if month_end
                       else "Submission due date: PO month not stated — confirm the service month.")
        student = f"{po.get('student_first', '')} {po.get('student_last', '')}".strip() or "student n/a"
        pending_line = ("\n⏳ PO is PENDING school approval (order agreement) — confirm it is "
                        "approved before submitting the invoice." if po.get("pending_approval") else "")
        rate_bit = f" @ ${po.get('rate')}/hr" if po.get("rate") else ""
        body = (f"STEP 1: convert this PO to a Teachworks invoice NOW (API can't — manual)."
                f"{pending_line}\n"
                f"Student: {student}\nSchool: {po.get('school') or 'n/a'}\n"
                f"PO #: {po.get('po_number') or 'n/a'}\nAmount: ${po.get('amount')}\n"
                f"Hours: {po.get('hours') or 'n/a'}{rate_bit}\n"
                f"{submit_line}\n"
                f"THEN fill on the HubSpot deal: 'Invoice #' (the TW invoice number) and "
                f"confirm 'Expected Lessons Fulfilled Date' (prefilled to the end of the "
                f"PO month — that's the invoice due date).\n"
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
        out = []
        for x in subs:
            sub = {**po, "pos": None, "po_number": _norm_po_number(x["po_number"]),
                   "amount": x.get("amount"), "hours": x.get("hours"),
                   "po_month": x.get("po_month") or po.get("po_month")}
            # multi-STUDENT certificates: per-entry student/parent fields win
            for k in ("student_first", "student_last", "grade", "parent_first",
                      "parent_last", "parent_email", "parent_phone", "rate"):
                if str(x.get(k) or "").strip():
                    sub[k] = x[k]
            out.append(sub)
        return out
    nums = [_norm_po_number(n) for n in re.split(r"[,;]|\band\b", str(po.get("po_number") or ""))
            if _norm_po_number(n)]
    if len(nums) >= 2:
        return [{**po, "pos": None, "po_number": n, "amount": None, "hours": None,
                 "_split_amount_unknown": True} for n in nums]
    return [po]


def _dm_scheduler(po: dict, created: list[dict], note_parts: list[str]) -> None:
    """Direct DM to the assigned scheduler (the deal owner): a new PO deal means
    lessons need scheduling — the 72-hr Pre→Post-Lesson clock starts now.
    One DM per email, listing every deal it created (Roman, 2026-08-10)."""
    from .router import scheduler_for_last_name
    sched_key, _ = scheduler_for_last_name(po.get("student_last") or "")
    sched = staff(sched_key)
    if not sched.get("slack_user_id"):
        return
    student = f"{po.get('student_first', '')} {po.get('student_last', '')}".strip() or "student n/a"
    names = "; ".join(c["name"] for c in created)
    pending = (" ⏳ PENDING school approval — confirm in the school portal before "
               "lessons start." if any(c.get("pending") for c in created) else "")
    try:
        slack_client.dm(sched["slack_user_id"],
                        f"🆕 {len(created)} new PO deal(s) assigned to you — {student} "
                        f"({po.get('school') or 'school n/a'}): {names}. In Pre-Lesson now — "
                        f"get lessons scheduled to hit the 72-hr Post-Lesson target.{pending}")
        note_parts.append(f"👤 Scheduler {sched.get('name', sched_key)} DM'd directly "
                          f"about the new deal(s).")
    except Exception as e:  # noqa: BLE001 — a DM failure must never block the deal
        print(f"  ⚠️  scheduler DM failed (non-fatal): {e}")


def _handle_deal(po: dict, note_parts: list[str], attachments: list[dict] | None = None,
                 msg: dict | None = None) -> None:
    """One deal per PO in the email (usually one; see _split_pos)."""
    subs = _split_pos(po)
    if len(subs) > 1:
        note_parts.append(f"📑 Multi-PO email: {len(subs)} POs → one deal each "
                          f"({', '.join(x['po_number'] for x in subs)}).")
    if po.get("pending_approval"):
        # Roman, 2026-08-10: "THIS IS NOT A PO" order agreements ARE POs —
        # full flow now, flagged so Kath confirms approval in the school portal.
        note_parts.append("⏳ PO(s) PENDING school approval (order agreement) — confirm "
                          "approved in the school's ordering portal before service starts.")
    created: list[dict] = []
    tw_cache: dict = {}   # one Teachworks calendar lookup per family per email
    seq_cache: dict = {}  # 'School N' base counted ONCE per email (no double-count)
    chase_queue: list = []  # (deal_id, deal_name, pipeline_id, po) needing a parent
    stu_seen: dict = {}   # multi-STUDENT certificates: offsets count per student
    for sub in subs:
        if sub.get("_split_amount_unknown"):
            note_parts.append(f"⚠️ PO {sub['po_number']}: per-PO amount/hours not "
                              f"extracted — fill on the deal manually.")
        skey = ((sub.get("student_first") or "").strip().lower(),
                (sub.get("student_last") or "").strip().lower())
        off = stu_seen.get(skey, 0)
        stu_seen[skey] = off + 1
        # scheduling alert once per STUDENT, not once per PO month; seq_offset
        # staggers 'School N' across the same student's deals in this email
        rec = _handle_one_po(sub, note_parts, attachments, no_lessons_check=(off == 0),
                             msg=msg, seq_offset=off, tw_cache=tw_cache,
                             seq_cache=seq_cache, chase_queue=chase_queue)
        if rec:
            created.append(rec)
    _open_parent_chases(chase_queue, msg, note_parts)
    if created:
        _dm_scheduler(po, created, note_parts)


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
               seq_offset: int = 0, seq_cache: dict | None = None) -> str:
    """Roman's convention (2026-08-10): 'Parent - Student - School N - YY/YY'.
    Parent unresolved → 'NEEDS PARENT - ...' until the chase flow fills it in.
    seq_offset staggers N across the deals of one multi-PO email; the BASE
    count is searched ONCE per email (seq_cache) — re-searching per sibling
    double-counts as the index catches up (the Zackarias 1,2,4,7,9 bug)."""
    short, mapped = _school_short(po.get("school") or "")
    year = _school_year_tag(po)
    student = f"{po.get('student_first', '')} {po.get('student_last', '')}".strip()
    # keyed per STUDENT too — a multi-student certificate numbers each kid's
    # deals from their own count, not a shared one
    key = (short.lower(), year, (po.get("student_first") or "").strip().lower())
    if seq_cache is not None and key in seq_cache:
        base = seq_cache[key]
    else:
        base = _next_school_seq(po, short, year)
        if seq_cache is not None:
            seq_cache[key] = base
    seq = base + seq_offset
    if short and not mapped:
        note_parts.append(f"🏫 School '{short}' has no shorthand — add it to "
                          f"po_inbox.school_short_names in config.yaml.")
    school_bit = f"{short} {seq}".strip() if short else ""
    return " - ".join(x for x in [parent_name or "NEEDS PARENT", student,
                                  school_bit, year] if x)


_NOREPLY_RE = re.compile(r"no-?reply|do-?not-?reply|notifications?@|@mailer\.", re.I)


def _human_addr(addr: str) -> bool:
    """Robot mailboxes are never draft recipients — a reply to noreply@ is a
    dead letter that silently kills the chase."""
    return bool((addr or "").strip()) and not _NOREPLY_RE.search(addr)


def _recent_call_context(tor_email: str) -> dict | None:
    """The call agent logs Claude summaries of every call as HubSpot Call
    engagements. Before chasing a TOR by email, look at their recent calls —
    the answer may already be in a phone conversation (the Karen Mercer case:
    the parent's name was on her contact an hour before the chase drafted)."""
    if not tor_email:
        return None
    try:
        tor = hs.find_contact_by_email(tor_email)
        if not tor or tor.get("id") in (None, "DRYRUN"):
            return None
        since = int((now_la() - timedelta(days=21)).timestamp() * 1000)
        for c in hs.recent_calls_for_contact(tor["id"], since):
            p = c.get("properties") or {}
            body = p.get("hs_call_body") or ""
            if "[Call Agent]" in body:
                return {"title": p.get("hs_call_title") or "call",
                        "date": str(p.get("hs_timestamp") or "")[:10],
                        "snippet": body[:400]}
    except Exception as e:  # noqa: BLE001 — context lookup is best-effort
        print(f"  ⚠️  call-context lookup failed (non-fatal): {e}")
    return None


def _open_chases() -> dict:
    """thread_id → LIST of parent chases still awaiting a reply (a multi-family
    certificate opens several chases on one thread — the Heartland case)."""
    opened, resolved = {}, set()
    for r in audit._iter_records():
        if r.get("action_taken") == "parent_chase_opened" and r.get("thread_id"):
            opened[str(r.get("deal_id"))] = r
        elif r.get("action_taken") == "parent_chase_resolved":
            resolved.add(str(r.get("deal_id")))
    out: dict = {}
    for did, r in opened.items():
        if did not in resolved:
            out.setdefault(r["thread_id"], []).append(r)
    return out


def _open_parent_chases(queue: list, msg: dict | None, note_parts: list[str]) -> None:
    """Parent info missing → the deal (and everything downstream: Teachworks
    family/student, scheduling, invoice hours) is blocked. Chase it: DRAFT a
    parent-info request (name + email + phone) to the TOR — else the sender —
    on the same thread. ONE draft per recipient per email, listing every
    student (the Heartland certificate produced 5 identical drafts to the same
    TOR — never again). A human sends the draft; replies are caught by
    _resolve_parent_chases."""
    ch = cfg()["po_inbox"].get("parent_chase", {})
    if not ch.get("enabled") or not msg or not queue:
        return
    sender_m = re.search(r"<([^>]+)>", msg.get("sender") or "")
    sender_addr = (sender_m.group(1) if sender_m else (msg.get("sender") or "")).strip().lower()
    by_to: dict = {}
    for deal_id, deal_name, pipeline_id, po in queue:
        if not deal_id or deal_id == "DRYRUN":
            continue
        # recipient ladder: PO's TOR email → human sender. Robot addresses are
        # NEVER recipients — no human to ask means no draft, loud flag instead.
        to_addr = (po.get("tor_email") or "").strip()
        if not _human_addr(to_addr):
            to_addr = sender_addr if _human_addr(sender_addr) else ""
        if not to_addr:
            note_parts.append("📨 No HUMAN recipient for the parent-info request "
                              "(sender is a noreply robot, no TOR email) — find the "
                              "school contact and chase manually.")
            continue
        by_to.setdefault(to_addr, []).append((deal_id, deal_name, pipeline_id, po))
    for to_addr, items in by_to.items():
        students = []
        for _d, _n, _p, po in items:
            s = f"{po.get('student_first', '')} {po.get('student_last', '')}".strip()
            if s and s not in students:
                students.append(s)
        student_line = ", ".join(students) or "the student"
        first = items[0][3]
        greeting = f"Hi {first.get('tor_first')}".strip() if first.get("tor_first") else "Hi"
        plural = len(students) > 1
        # what did a recent phone call already tell us? (Karen Mercer case)
        ctx = _recent_call_context(to_addr)
        ctx_line = ("\n\nP.S. Some of this may already have come up on a recent call "
                    "with our team - if so, apologies for the double-ask." if ctx else "")
        body = (f"{greeting},\n\n"
                f"Thank you for the purchase order for {student_line}. To get scheduling "
                f"set up we still need the parent/guardian contact information for "
                f"{'each family' if plural else 'the family'}:\n\n"
                f"  - Parent/guardian full name\n"
                f"  - Email address\n"
                f"  - Phone number\n\n"
                f"Could you reply with those when you have a moment? We'll take it "
                f"from there.{ctx_line}\n\n"
                f"A+ Tutoring Team")
        bcc = (cfg().get("hubspot", {}) or {}).get("bcc_log_address") or ""
        short, _m = _school_short(first.get("school") or "")
        try:
            if to_addr.lower() != sender_addr:
                # fresh thread — a clean email to the TOR, not a reply quoting
                # a portal robot; replies land on the NEW thread
                draft = gm.create_draft(
                    to_addr, f"Parent contact info needed — {student_line}"
                             f" ({short or 'charter'})", body, bcc=bcc)
            else:
                draft = gm.create_draft_reply(msg["threadId"], to_addr,
                                              msg.get("subject") or "", body,
                                              msg.get("message_id_header", ""), bcc=bcc)
        except Exception as e:  # noqa: BLE001 — chase failure must not block the deal
            print(f"  ⚠️  parent-chase draft failed (non-fatal): {e}")
            note_parts.append(f"📨 Could not draft the parent-info request to {to_addr} "
                              f"— ask manually.")
            continue
        d_msg = (draft or {}).get("message") or {}
        chase_thread = d_msg.get("threadId") or msg["threadId"]
        draft_feedback.register(draft, "parent_chase", body, to_addr, "po_inbox",
                                thread_id=chase_thread, meta={"students": student_line})
        try:
            if d_msg.get("id"):
                gm.apply_labels(d_msg["id"], ["A+ Agent/Draft Pending"])
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  draft label failed (non-fatal): {e}")
        due = add_business_hours(now_la(), int(ch.get("escalate_business_hours", 16)))
        for deal_id, deal_name, pipeline_id, po in items:
            student = (f"{po.get('student_first', '')} "
                       f"{po.get('student_last', '')}").strip() or "the student"
            audit.append({"message_id": f"parent-chase:{deal_id}", "source": "po_inbox",
                          "action_taken": "parent_chase_opened", "deal_id": deal_id,
                          "deal_name": deal_name, "pipeline": pipeline_id,
                          "po_number": (po.get("po_number") or "").strip(),
                          "thread_id": chase_thread, "student": student,
                          "school": po.get("school") or "",
                          "tor_email": (po.get("tor_email") or "").strip().lower(),
                          "chase_to": to_addr, "draft_id": (draft or {}).get("id"),
                          "sla_due": due.isoformat()})
        note_parts.append(f"📨 Parent-info request DRAFTED to {to_addr} for "
                          f"{student_line} — SEND it from Gmail Drafts; the reply "
                          f"auto-creates the contact and unblocks Teachworks.")
        if ctx:
            note_parts.append(f"📞 A recent call may ALREADY have this info: "
                              f"\"{ctx['title']}\" ({ctx['date']}) on the TOR's record — "
                              f"check it before sending the draft.")


def _resolve_parent_chases(chases: list, po: dict, note_parts: list[str]) -> None:
    """A reply with parent info against a thread's OPEN chases. Multi-family
    threads (Heartland): resolve only the chases whose student the reply names;
    no student named → resolve them all (single-family threads, e.g. one kid's
    multi-month POs, are the common case and want exactly that)."""
    sf = (po.get("student_first") or "").strip().lower()
    targets = [c for c in chases
               if sf and sf in (c.get("student") or "").lower()] or chases
    for chase in targets:
        _resolve_parent_chase(chase, po, note_parts)


def _resolve_parent_chase(chase: dict, po: dict, note_parts: list[str]) -> None:
    """The TOR replied with the parent's info → create/find the Family contact
    (email + phone + persona), associate it to the waiting deal, swap 'NEEDS
    PARENT' for the real name, link family→TOR (#AP031), and run the Teachworks
    sync NOW — the whole downstream chain unblocks with zero manual data entry."""
    deal_id = chase.get("deal_id")
    p_email = (po.get("parent_email") or "").strip().lower()
    if not deal_id or not p_email or _internal_email(p_email):
        return
    try:
        # rename from the LIVE deal name, never the audit's stale copy — a
        # human may have fixed it since (Pilibos incident, 2026-08-14)
        try:
            live = hs._get(f"/crm/v3/objects/deals/{deal_id}", {"properties": "dealname"})
            live_name = (live.get("properties") or {}).get("dealname") or ""
        except Exception:  # noqa: BLE001
            live_name = ""
        if live_name:
            chase = {**chase, "deal_name": live_name}
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
        # Arm the scheduling SMS for the just-attached parent: the deal-side
        # stamper fired at creation when NO parent existed, so this contact never
        # got contact_level_deal_stage and the family never got their text
        # (Roman batch, 2026-08-14). Charter Trad only — that's the SMS flow's
        # trigger value.
        if (chase.get("pipeline") or "") == cfg()["po_inbox"].get("deal_pipeline_id"):
            try:
                hs._write("PATCH", f"/crm/v3/objects/contacts/{cid}",
                          {"properties": {"contact_level_deal_stage":
                                          "Pre-Lesson (Charter Traditional)"}})
                note_parts.append("💬 Scheduling-text workflow armed for the parent.")
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  SMS arm failed (non-fatal): {e}")
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
    ch = pc.get("parent_chase", {})
    if not ch.get("enabled"):
        return
    sent, escalated, sales_pinged = {}, set(), set()
    for r in audit._iter_records():
        a = r.get("action_taken")
        if a == "parent_chase_sent":
            sent[str(r.get("deal_id"))] = r
        elif a == "parent_chase_escalated":
            escalated.add(str(r.get("deal_id")))
        elif a in ("parent_chase_sales_notified", "parent_chase_paola_notified"):
            sales_pinged.add(str(r.get("deal_id")))
    now = now_la()
    for r in (c for lst in _open_chases().values() for c in lst):
        did = str(r.get("deal_id"))
        # a chase whose draft was never SENT must not blame the TOR for not
        # replying — the unsent-draft nag (_sweep_chase_drafts) covers that.
        # Legacy chases without a draft_id fall back to the opened clock.
        s = sent.get(did)
        if not s and r.get("draft_id"):
            continue
        # Roman, 2026-08-14: family contact info still missing 24 HOURS after
        # the email went out → CHARTER SALES (role, mapped in config — never a
        # person's name in code) is notified too, ahead of the escalation.
        if did not in sales_pinged:
            try:
                anchor = datetime.fromisoformat((s or r).get("timestamp") or "")
            except (TypeError, ValueError):
                anchor = None
            hrs = float(ch.get("notify_charter_sales_after_hours",
                               ch.get("notify_paola_after_hours", 24)))
            if anchor and now > anchor + timedelta(hours=hrs):
                sales = staff(pc.get("charter_sales") or "charter_sales")
                if sales.get("slack_user_id"):
                    slack_client.dm(sales["slack_user_id"],
                                    f"👨‍👩‍👧 Family contact info STILL MISSING {int(hrs)}h "
                                    f"after our email — deal '{r.get('deal_name')}' "
                                    f"(student {r.get('student')}, asked {r.get('chase_to')}). "
                                    f"Please follow up with the TOR/school directly.")
                audit.append({"message_id": f"parent-chase-sales:{did}",
                              "source": "po_inbox",
                              "action_taken": "parent_chase_sales_notified",
                              "deal_id": did, "thread_id": r.get("thread_id")})
        if did in escalated:
            continue
        try:
            due = datetime.fromisoformat((s or r)["sla_due"])
        except (KeyError, TypeError, ValueError):
            continue
        if now <= due:
            continue
        # missing info still missing → both Kath AND Roman hear about it
        for key in pc.get("missing_info_dms", [pc.get("owner", "kath")]):
            st = staff(key)
            if st.get("slack_user_id"):
                slack_client.dm(st["slack_user_id"],
                                f"⏰ Still NO parent info for deal '{r.get('deal_name')}' — "
                                f"asked {r.get('chase_to')} on {(r.get('timestamp') or '')[:10]} "
                                f"with no reply. The Teachworks family can't be created until we "
                                f"have the parent's name, email, and phone — chase by phone.")
        audit.append({"message_id": f"parent-chase-escalation:{r.get('deal_id')}",
                      "source": "po_inbox", "action_taken": "parent_chase_escalated",
                      "deal_id": r.get("deal_id"), "thread_id": r.get("thread_id")})


def _sweep_chase_drafts() -> None:
    """Draft accountability: a chase draft that VANISHED from Drafts was sent —
    log parent_chase_sent (starting the TOR's reply clock) and flip the Gmail
    label. One still SITTING in Drafts past the nag window → 🚩 to Kath+Roman."""
    pc = cfg()["po_inbox"]
    ch = pc.get("parent_chase", {})
    if not ch.get("enabled"):
        return
    sent_ids, nagged = set(), set()
    for r in audit._iter_records():
        if r.get("action_taken") == "parent_chase_sent":
            sent_ids.add(str(r.get("deal_id")))
        elif r.get("action_taken") == "parent_chase_draft_nag":
            nagged.add(r.get("draft_id"))
    now = now_la()
    seen_drafts: dict = {}
    for r in (c for lst in _open_chases().values() for c in lst):
        did, draft_id = str(r.get("deal_id")), r.get("draft_id")
        if not draft_id or did in sent_ids:
            continue
        if draft_id not in seen_drafts:
            seen_drafts[draft_id] = gm.get_draft(draft_id)
        if seen_drafts[draft_id] is None:      # gone from Drafts → it was sent
            due = add_business_hours(now, int(ch.get("escalate_business_hours", 16)))
            audit.append({"message_id": f"parent-chase-sent:{did}", "source": "po_inbox",
                          "action_taken": "parent_chase_sent", "deal_id": did,
                          "thread_id": r.get("thread_id"), "draft_id": draft_id,
                          "sla_due": due.isoformat()})
            continue
        if draft_id in nagged:
            continue
        try:
            opened = datetime.fromisoformat(r.get("timestamp") or "")
        except (TypeError, ValueError):
            continue
        if now > add_business_hours(opened,
                                    int(ch.get("draft_unsent_nag_business_hours", 4))):
            for key in pc.get("missing_info_dms", [pc.get("owner", "kath")]):
                st = staff(key)
                if st.get("slack_user_id"):
                    slack_client.dm(st["slack_user_id"],
                                    f"📨 The parent-info draft to {r.get('chase_to')} "
                                    f"('{r.get('deal_name')}') is STILL SITTING in Gmail "
                                    f"Drafts — send it or the chase goes nowhere.")
            audit.append({"message_id": f"parent-chase-draft-nag:{draft_id}",
                          "source": "po_inbox", "action_taken": "parent_chase_draft_nag",
                          "draft_id": draft_id, "deal_id": did})


_PLACEHOLDER_STUDENTS = {"the student", "student", "n/a", "unknown", ""}


def _internal_email(email: str) -> bool:
    dom = (cfg().get("internal", {}) or {}).get("domain", "wetutorathome.com")
    return (email or "").strip().lower().endswith(f"@{dom}")


def _deal_still_needs_parent(deal_id) -> bool:
    """LIVE check: only a deal still named 'NEEDS PARENT - …' is a candidate
    for auto-resolution. Kath fixes deals by hand; the audit's stale
    deal_name must never outrank the portal (the 2026-08-14 'Pilibos
    Student' incident — five hand-fixed Heartland deals were renamed to a
    test contact by this sweep)."""
    try:
        d = hs._get(f"/crm/v3/objects/deals/{deal_id}", {"properties": "dealname"})
    except Exception:  # noqa: BLE001
        return False
    return "NEEDS PARENT" in ((d.get("properties") or {}).get("dealname") or "")


def _sweep_chase_self_resolve() -> None:
    """Open chases re-check HubSpot each run: the family may have appeared on
    its own (called in, intake form) — the August Vouniozos case, where the
    contact existed hours before anyone read the TOR's reply.

    Guards (post-incident): (1) a REAL student name — placeholders like
    'the student' are never searched; (2) the deal must STILL say NEEDS
    PARENT in the portal; (3) internal/test contacts (@wetutorathome.com)
    are never auto-attached."""
    for r in (c for lst in _open_chases().values() for c in lst):
        student = (r.get("student") or "").strip()
        if student.lower() in _PLACEHOLDER_STUDENTS:
            continue
        parts = student.split()
        if len(parts) < 2:
            continue
        if not _deal_still_needs_parent(r.get("deal_id")):
            # already fixed by a human (or resolved elsewhere) → close the
            # chase so it stops being swept, but touch NOTHING on the deal
            audit.append({"message_id": f"parent-chase-resolved:{r.get('deal_id')}",
                          "source": "po_inbox", "action_taken": "parent_chase_resolved",
                          "deal_id": r.get("deal_id"), "thread_id": r.get("thread_id"),
                          "resolved_via": "deal no longer NEEDS PARENT (human fixed)"})
            continue
        try:
            parents = hs.find_family_contact(parts[0], " ".join(parts[1:]))
        except Exception:  # noqa: BLE001
            continue
        if len(parents) != 1:
            continue
        props = parents[0].get("properties") or {}
        em = (props.get("email") or "").strip()
        if not em or _internal_email(em):
            continue
        notes: list[str] = []
        _resolve_parent_chase(r, {"parent_email": em,
                                  "parent_first": props.get("firstname"),
                                  "parent_last": props.get("lastname"),
                                  "parent_phone": props.get("phone")}, notes)
        for n in notes:
            print(f"  🔁 self-resolve: {n}")


def _sweep_pending_pos() -> None:
    """Pending order-agreement POs with no approval signal past the window →
    one nag to Kath + Roman (the duplicate alert on the re-issued/approved PO
    confirms them; portal-only approvals need the human check this prompts)."""
    opened, confirmed, reminded = {}, set(), set()
    for r in audit._iter_records():
        act = r.get("action_taken")
        if act == "pending_po_opened" and r.get("deal_id"):
            opened[str(r["deal_id"])] = r
        elif act == "pending_po_confirmed":
            confirmed.add((r.get("po_number") or "").strip())
        elif act == "pending_po_reminded":
            reminded.add(str(r.get("deal_id")))
    now = now_la()
    pc = cfg()["po_inbox"]
    for did, r in opened.items():
        if did in reminded or (r.get("po_number") or "").strip() in confirmed:
            continue
        try:
            due = datetime.fromisoformat(r["sla_due"])
        except (KeyError, TypeError, ValueError):
            continue
        if now <= due:
            continue
        for key in pc.get("missing_info_dms", [pc.get("owner", "kath")]):
            s = staff(key)
            if s.get("slack_user_id"):
                slack_client.dm(s["slack_user_id"],
                                f"⏳ PO {r.get('po_number')} ('{r.get('deal_name')}') is "
                                f"still PENDING school approval with no approval signal "
                                f"since {(r.get('timestamp') or '')[:10]} — check the "
                                f"school's ordering portal; no service or invoice until "
                                f"it's approved.")
        audit.append({"message_id": f"pending-po-reminder:{did}", "source": "po_inbox",
                      "action_taken": "pending_po_reminded", "deal_id": did,
                      "po_number": (r.get("po_number") or "").strip()})


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
                   seq_offset: int = 0, tw_cache: dict | None = None,
                   seq_cache: dict | None = None,
                   chase_queue: list | None = None) -> dict | None:
    """Advance the matching Waiting-for-PO deal, or create one. Returns
    {name, pending} for a CREATED deal (drives the scheduler DM), else None."""
    pc = cfg()["po_inbox"]
    student = (po.get("student_last") or po.get("student_first") or "").strip()
    school = (po.get("school") or "").strip()
    token = student or school
    if not token:
        note_parts.append("💼 No student/school extracted — no deal action; review manually.")
        return
    # PO hours: schools often state only amount + hourly rate — compute them
    # (Roman, 2026-08-11: "you might have to calculate; our rate will be in the PO").
    if not po.get("hours"):
        try:
            amt = float(str(po.get("amount") or "").replace(",", "") or 0)
            rate = float(str(po.get("rate") or "").replace(",", "") or 0)
            if amt > 0 and rate > 0:
                po["hours"] = f"{amt / rate:g}"
                note_parts.append(f"🧮 Hours computed from the PO: ${amt:g} ÷ "
                                  f"${rate:g}/hr = {po['hours']} hrs.")
        except (TypeError, ValueError):
            pass
    # PO-number dedupe via the canonical po_number PROPERTY (then name as backstop).
    po_num = _norm_po_number(po.get("po_number"))
    if po_num:
        dup = hs.find_deals_by_po_number(po_num) or hs.search_deals_by_name(po_num)
        if dup:
            dn = (dup[0].get("properties") or {}).get("dealname", "?")
            note_parts.append(f"💼 DUPLICATE PO {po_num} ('{dn}') — no new deal; Kath alerted.")
            owner = staff(pc.get("owner", "kath"))
            slack_client.dm(owner.get("slack_user_id"),
                            f"🚨 URGENT — duplicate PO received: PO {po_num} already has deal "
                            f"'{dn}'. Check whether the school re-sent it or this is a second "
                            f"authorization before doing anything.")
            # the approved PO re-arriving IS the approval signal — close the
            # pending-approval sweep for this PO number
            audit.append({"message_id": f"pending-po-confirmed:{po_num}",
                          "source": "po_inbox", "action_taken": "pending_po_confirmed",
                          "po_number": po_num, "deal_name": dn})
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
        sched = staff(sched_key)
        close_ms = int((now_la() + timedelta(days=30)).timestamp() * 1000)
        # Slack routing flag: the HubSpot workflow behind this checkbox posts the
        # deal to the right channel by pipeline (Roman, 2026-08-10).
        extra = {"po_number": po_num,
                 "should_this_deal_be_posted_to_a_slack_channel_": "true"}
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
        parent_email_res = ""   # the RESOLVED family email (PO or contact record)
        p_email = (po.get("parent_email") or "").strip().lower()
        if p_email:
            parent_email_res = p_email
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
            # STEP 2 (Roman, 2026-08-18): the student may already be IN
            # Teachworks — a family with real lesson history (and ideally the
            # PO's tutor as their last tutor) is the surest parent there is.
            fam = None
            try:
                fam = tw.find_family_by_student(po.get("student_first") or "",
                                                po.get("student_last") or "",
                                                tutor_hint=po.get("tutor_name") or "")
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  TW student lookup failed (non-fatal): {e}")
            if fam and fam.get("email") and not _internal_email(fam["email"]):
                try:
                    existing = hs.find_contact_by_email(fam["email"])
                    if existing:
                        contact_id = existing["id"]
                        xp = existing.get("properties") or {}
                        parent_name = (f"{xp.get('firstname', '')} {xp.get('lastname', '')}".strip()
                                       or f"{fam['parent_first']} {fam['parent_last']}".strip())
                    else:
                        created_c = hs.create_contact(fam["email"], fam.get("parent_first") or None,
                                                      fam.get("parent_last") or None,
                                                      phone=fam.get("phone") or None,
                                                      extra_props=FAMILY_CREATE_PROPS)
                        contact_id = created_c.get("id")
                        parent_name = f"{fam['parent_first']} {fam['parent_last']}".strip()
                    parent_email_res = fam["email"]
                    po.setdefault("parent_email", fam["email"])
                    if not po.get("parent_phone") and fam.get("phone"):
                        po["parent_phone"] = fam["phone"]
                    why = (f"tutor {fam['tutor']} matches the PO" if fam.get("tutor_match")
                           else f"{fam['lessons']} lessons, last tutor {fam['tutor'] or '?'}")
                    contact_bit = (f"parent {parent_name} found IN TEACHWORKS by student "
                                   f"name ({why}, last lesson {fam.get('last_lesson') or '?'}), ")
                    if not fam.get("tutor_match") and (po.get("tutor_name") or "").strip():
                        note_parts.append(f"⚠️ TW family matched by student name but the PO's "
                                          f"tutor ({po['tutor_name']}) ≠ their last tutor "
                                          f"({fam['tutor'] or '?'}) — verify it's the same "
                                          f"student before scheduling.")
                except Exception as e:  # noqa: BLE001
                    print(f"  ⚠️  TW-family contact link failed (non-fatal): {e}")
        if not contact_id:
            found = _find_parent_via_deals(po)
            if found:
                c, dn = found
                contact_id = c.get("id")
                parent_name = (f"{(c.get('properties') or {}).get('firstname', '')} "
                               f"{(c.get('properties') or {}).get('lastname', '')}").strip()
                parent_email_res = ((c.get("properties") or {}).get("email") or "").lower()
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
                parent_email_res = (parents[0]["properties"].get("email") or "").lower()
                contact_bit = f"linked to family contact {parent_name}, "
        if not contact_id:
            contact_bit = ("NO parent contact info in the PO and no unique family match — "
                           "parent-info request drafted to the TOR/sender (see 📨); once it "
                           "lands the contact is auto-created and associated, ")
        if contact_id and not parent_name and p_email:
            parent_name = p_email.split("@")[0]
        # "Is the family currently being tutored by us?" ROUTES the SMS workflow
        # (verified against flow 1603217415, 2026-08-11): BOTH values text the
        # family a schedule-confirmation; "No" additionally alerts staff by
        # internal email first. Text frequency is safe at the workflow level —
        # it's contact-based, one enrollment at a time, re-armed per PO event.
        # THE RULE (Roman, student-level, MONTH-SCOPED, true value on EVERY
        # deal): Yes = THIS student has a lesson booked in the PO's service
        # month (month unknown → any upcoming); No = that month is unbooked.
        # Unverifiable → left unset and flagged (gap DM to Kath + Roman).
        act = (_student_activity(parent_email_res, po.get("student_first") or "",
                                 tw_cache, parent_name=parent_name)
               if parent_email_res else None)
        tw_note = None
        if parent_email_res and act is None:
            tw_note = ("⚠️ Could not verify the Teachworks calendar — set 'Is the family "
                       "currently being tutored by us?' on the deal manually (it routes "
                       "scheduling texts).")
        elif act is not None:
            month_end = _po_month_end(po.get("po_month") or "")
            if month_end is not None:
                pref = month_end.strftime("%Y-%m")
                tutored = any(str(d).startswith(pref)
                              for d in act.get("upcoming_dates") or [])
            else:
                tutored = bool(act.get("upcoming"))
            extra["is_the_family_currently_being_tutored_by_us_"] = \
                "Yes" if tutored else "No"
            # The SMS reads {{schedule_preferences}} off the DEAL — PO deals never
            # had it, so charter texts ended "...still works for you: " BLANK.
            # Stamp the student's live TW schedule (upcoming slots, else the
            # recent pattern); nothing derivable → gap DM, text needs a human.
            sched_pref = (_schedule_text(act.get("upcoming_lessons") or [])
                          or _schedule_text(act.get("recent_lessons") or []))
            if sched_pref:
                extra["schedule_preferences"] = sched_pref
            else:
                tw_note = ("⚠️ No TW schedule to put in the SMS "
                           "(schedule_preferences blank) — the confirmation text "
                           "will be incomplete; set the schedule manually.")
        upcoming = act.get("upcoming") if act else None
        name = _deal_name(po, parent_name, note_parts, seq_offset, seq_cache)
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
        if tw_note:
            note_parts.append(tw_note)
        _associate_tor(d.get("id"), po, note_parts, family_contact_id=contact_id)
        _stamp_deal_properties(d.get("id"), po, note_parts)
        _attach_po_to_deal(d.get("id"), attachments or [], po, note_parts)
        _invoice_task(d.get("id"), po, note_parts)
        if not contact_id:
            if chase_queue is not None:
                chase_queue.append((d.get("id"), name, pipeline_id, po))
            else:
                _open_parent_chases([(d.get("id"), name, pipeline_id, po)],
                                    msg, note_parts)
        if po.get("pending_approval") and d.get("id") and d.get("id") != "DRYRUN":
            # pending-approval follow-up sweep: track the open pending PO; the
            # duplicate alert (approved PO re-arriving) confirms it, the sweep
            # nags after the window (Roman batch, 2026-08-14)
            audit.append({"message_id": f"pending-po:{d.get('id')}", "source": "po_inbox",
                          "action_taken": "pending_po_opened", "deal_id": d.get("id"),
                          "deal_name": name, "po_number": po_num,
                          "sla_due": add_business_hours(
                              now_la(), int(pc.get("pending_sweep_business_hours", 16))
                          ).isoformat()})
        if no_lessons_check:
            _no_lessons_alert(po, name, note_parts, upcoming)
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
        return {"name": name, "pending": bool(po.get("pending_approval"))}
    return None


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


def _gap_notes(note_parts: list[str]) -> list[str]:
    """The notes that mean SOMETHING IS MISSING: fields the PO didn't state,
    unmatched TOR/parent, failed uploads, any 'do it manually' follow-up."""
    return [p for p in note_parts if p.startswith(("⚠️", "📨"))
            or "manually" in p or "NEEDS PARENT" in p or "no shorthand" in p]


def _notify_gaps(subject: str, note_parts: list[str], ticket_id=None) -> None:
    """Roman, 2026-08-11: anything missing on PO intake is DM'd DIRECTLY to
    Kath AND Roman (po_inbox.missing_info_dms) — never just a ticket line."""
    gaps = _gap_notes(note_parts)
    if not gaps:
        return
    msg = "🚩 MISSING INFO — " + subject + "\n" + "\n".join(f"• {g}" for g in gaps)
    if ticket_id and ticket_id != "DRYRUN":
        msg += f"\n{hs.ticket_url(ticket_id)}"
    for key in cfg()["po_inbox"].get("missing_info_dms", ["kath", "roman"]):
        s = staff(key)
        if s.get("slack_user_id"):
            try:
                slack_client.dm(s["slack_user_id"], msg)
            except Exception as e:  # noqa: BLE001 — alerting must not kill the run
                print(f"  ⚠️  gap DM to {key} failed (non-fatal): {e}")


def _closed_thread(thread_id: str) -> bool:
    """A thread whose REAL PO was already processed (and no parent chase is
    waiting on it). Replies on closed threads are NOT skipped — schools send
    corrections there (the Zie Rojas amount correction, 2026-08-12, was
    silently dropped by the old skip) — they're processed and labeled."""
    return _thread_already_handled(thread_id) and thread_id not in _open_chases()


def process_po_message(stub_id: str, force: bool = False) -> dict | None:
    """force=True (replay) bypasses the processed guard — used to re-run a
    message under new rules (e.g. order agreements now counting as POs)."""
    pc = cfg()["po_inbox"]
    m = gm.get_message(stub_id)
    if not force and audit.already_processed(f"gmail:{m['id']}"):
        return None
    closed_thread = _closed_thread(m["threadId"])
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
    owner = staff(pc.get("owner", "kath"))
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
        # A reply on a thread with open parent chases that carries the parent's
        # info → auto-create the contact and unblock the waiting deal(s).
        chases = _open_chases().get(m["threadId"]) or []
        if chases and (po.get("parent_email") or "").strip():
            _resolve_parent_chases(chases, po, note_parts)
            record["category"] = "parent_info_reply"
        note_parts.append(f"Not a PO: {po.get('summary','')[:200]}")

    # Ticket (same spine as admin inbox)
    subject = (f"new_po — {po.get('school') or m['sender'][:40]}"
               + (f" (PO {po['po_number']})" if po.get("po_number") else "")) if po.get("is_po") \
              else f"po_inbox review — {m['subject'][:50]}"
    if closed_thread and not po.get("is_po"):
        subject = f"PO-thread reply — {m['subject'][:50]}"
        note_parts.insert(0, "↩️ Reply on an ALREADY-PROCESSED PO thread — check it for "
                             "corrections or updates to the existing deal(s).")
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
            if not _human_addr(to_addr):
                raise ValueError(f"robot recipient {to_addr} — no draft")
            bcc = (cfg().get("hubspot", {}) or {}).get("bcc_log_address") or ""
            d = gm.create_draft_reply(m["threadId"], to_addr, m["subject"], draft,
                                      m.get("message_id_header", ""), bcc=bcc)
            draft_feedback.register(d, "reply", draft, to_addr, "po_inbox",
                                    thread_id=m["threadId"])
            dm_id = ((d or {}).get("message") or {}).get("id")
            if dm_id:
                try:
                    gm.apply_labels(dm_id, ["A+ Agent/Draft Pending"])
                except Exception as le:  # noqa: BLE001
                    print(f"  ⚠️  draft label failed (non-fatal): {le}")
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
        ccs = staff(cc)
        if ccs.get("slack_user_id"):
            slack_client.dm(ccs["slack_user_id"], f"📋 [copy → {owner['name']}] 📦 {subject}")
    _notify_gaps(subject, note_parts, record.get("ticket_id"))

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
    import os
    from pathlib import Path
    # Replay: PO_REPLAY_MSG_IDS="<gmail_id>,<gmail_id>" reprocesses specific
    # messages ignoring the processed/thread guards (same pattern as the
    # deal-sync FORCE_DEAL_ID tool) — for rule changes like OAs-are-POs.
    for rid in [x.strip() for x in (os.environ.get("PO_REPLAY_MSG_IDS") or "").split(",")
                if x.strip()]:
        try:
            print(f"po_inbox: REPLAY {rid}")
            process_po_message(rid, force=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  replay error on {rid}: {e}", file=sys.stderr)
            traceback.print_exc()
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
    try:
        _sweep_pending_pos()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  pending-PO sweep failed (non-fatal): {e}")
    try:
        _sweep_chase_drafts()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  chase-draft sweep failed (non-fatal): {e}")
    try:
        _sweep_chase_self_resolve()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  chase self-resolve sweep failed (non-fatal): {e}")
    try:
        draft_feedback.sweep()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  draft-feedback sweep failed (non-fatal): {e}")
    if not DRY_RUN:
        cur_path.write_text(_json.dumps({"last_epoch": newest}))


if __name__ == "__main__":
    run()

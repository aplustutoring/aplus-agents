"""Low-balance renewal agent — a Teachworks package-balance alert becomes a
tracked renewal case, and the family (and their teacher of record) hear from
the charter_sales seat the same day.

Roman 2026-09-08: "when a family hits a low balance alert on hours in
Teachworks, families get contacted." The trigger already exists: the
Teachworks Package Balance Alerts add-on emails admin@ (via info@) every time
a student's unused package hours reach the alert level, 1 to 5 times a
weekday. Until now the triage classifier read those as `unknown` or
`scheduling` and filed tickets to the schedulers (55 of 81 since June went
to the Stuck queue); the renewal chase itself lived on a Monday board Paola
fed by hand ("A+ Charter Low Balance Alerts", 8802830977) that drove the
retired HubSpot flow "Low Balance Alerts - Charter" (552811839, off since
2025-10-01). This module replaces both: the alert is recognised
DETERMINISTICALLY (no LLM in the loop), the case is a HubSpot ticket owned
by the charter_sales seat, the outreach goes out from that seat, and the
case closes itself when the school's new PO lands (po_inbox creates the
deal; this sweep sees it).

Rules honoured (all locked):
  - Alerts route to Paola ONLY (Danielle, 2026-08-12: "do not include me").
  - Families and specific-student teacher contact = charter_sales seat:
    from-name, reply-to, sign-off, task owner (Roman 2026-08-25).
  - Teachers are emailed, never called (Roman 2026-09-03).
  - The PO is issued by the SCHOOL; copy asks the family to request it from
    their TOR and offers vendor details, never "we handle the PO"
    (Roman 2026-09-02). Every charter student has funds; hours are simply
    running low (Roman 2026-09-02).
  - Level Up Terri (pipeline 72281989) teachers are never emailed about a
    low balance: they cannot issue additional POs (Roman 2025-10-29).
  - No em dashes in anything customer-facing (Roman 2026-08-24).

Safety: `armed: false` in config means the agent files the ticket, writes
the exact copy it WOULD send into the ticket note, and DMs the seat; nothing
reaches a family or a teacher until Roman flips the flag in a PR. One case
per student + package per school year; repeated alerts (Teachworks re-fires
on every balance change) add a note, never a second text.

State: the audit log (low_balance_opened / _resolved / _escalated / _sms_sent
/ _repeat records), same as every other sweep. Runs: handle_alert() from the
triage pass the moment the email lands; run_sweep() from deal_sync.run()
every cycle (self-gated to once an hour) to send deferred texts, close cases
whose PO arrived, and escalate the ones that stalled.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

from . import audit, draft_feedback, gmail_client as gm, hubspot_client as hs, slack_client
from .business_hours import add_business_hours, now_la
from .config import DRY_RUN, RESEND_API_KEY, ROOT, cfg, staff
from .gmail_client import _scrub_outbound

TEACHWORKS_DOMAIN = "teachworks.com"

# "This message is to inform you that the Charter - iLEAD  package balance
#  for Taylor Rodriguez has reached the level of 4 hours
#  and is currently at 4.0 unused hours."
_ALERT_RE = re.compile(
    r"that the\s+(?P<package>.+?)\s+package balance\s+for\s+(?P<student>.+?)\s+"
    r"has reached the level of\s+(?P<level>\d+(?:\.\d+)?)\s+(?:hours?|lessons?)\s+"
    r"and is currently at\s+(?P<hours>\d+(?:\.\d+)?)\s+unused\s+(?P<unit>hours?|lessons?)",
    re.I | re.S)
_DETAIL_RE = re.compile(r"^[ \t]*(Name|Email|Home Phone|Mobile Phone|Student)[ \t]*:[ \t]*(.*?)[ \t]*$",
                        re.I | re.M)


# ── alert recognition ───────────────────────────────────────────────────────

def is_teachworks_sender(addrs: list[str]) -> bool:
    return any(a.strip().lower().endswith("@" + TEACHWORKS_DOMAIN) for a in addrs or [])


def parse_alert(body: str) -> dict | None:
    """The alert's facts, or None when this is not a package-balance alert
    (Teachworks also emails cancellations, form completions, reminders)."""
    text = re.sub(r"<[^>]+>", " ", body or "")
    text = re.sub(r"[ \t]+", " ", text)
    m = _ALERT_RE.search(text)
    if not m:
        return None
    details = {k.lower().replace(" ", "_"): v.strip()
               for k, v in _DETAIL_RE.findall(text)}
    student = re.sub(r"\s+", " ", m.group("student")).strip()
    parent = details.get("name", "")
    parts = parent.split()
    sparts = student.split()
    return {
        "package": re.sub(r"\s+", " ", m.group("package")).strip(),
        "student": student,
        "student_first": sparts[0] if sparts else "",
        "student_last": " ".join(sparts[1:]) if len(sparts) > 1 else "",
        "level": float(m.group("level")),
        "hours": float(m.group("hours")),
        "unit": "hours" if m.group("unit").lower().startswith("hour") else "lessons",
        "parent_name": parent,
        "parent_first": parts[0] if parts else "",
        "parent_last": " ".join(parts[1:]) if len(parts) > 1 else "",
        "parent_email": (details.get("email") or "").lower(),
        "parent_phone": details.get("mobile_phone") or details.get("home_phone") or "",
    }


def is_charter_package(package: str, pipeline_id: str = "") -> bool:
    """Charter = the package name says so, or the student's current deal sits in
    a charter pipeline (deal_sync's list, or any pipeline named Charter)."""
    if "charter" in (package or "").lower():
        return True
    ds = cfg().get("deal_sync", {}) or {}
    if pipeline_id and str(pipeline_id) in [str(p) for p in ds.get("charter_pipelines", [])]:
        return True
    try:
        return bool(pipeline_id) and "charter" in hs.pipeline_label(str(pipeline_id)).lower()
    except Exception:  # noqa: BLE001
        return False


# ── identity + state ────────────────────────────────────────────────────────

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def season(d=None) -> str:
    """School year label: Aug-Dec belong to the year that starts, Jan-Jul to
    the one that ends. 2026-09-08 -> '26/27'."""
    d = d or now_la()
    y = d.year if d.month >= 8 else d.year - 1
    return f"{str(y)[-2:]}/{str(y + 1)[-2:]}"


def case_key(alert: dict, d=None) -> str:
    return f"low-balance:{season(d)}:{_slug(alert['student'])}:{_slug(alert['package'])}"


def open_cases() -> dict:
    """{case_key: opened record (with any later sms/escalation flags folded in)}
    for every case without a resolved record."""
    opened: dict = {}
    for r in audit._iter_records():
        act = r.get("action_taken") or ""
        key = str(r.get("message_id") or "")
        if act == "low_balance_opened":
            opened[key] = dict(r)
        elif act == "low_balance_resolved":
            opened.pop(key.rsplit(":resolved", 1)[0], None)
        elif act == "low_balance_sms_sent":
            base = key.rsplit(":sms", 1)[0]
            if base in opened:
                opened[base]["sms_sent"] = True
        elif act == "low_balance_escalated":
            base = key.rsplit(":escalated", 1)[0]
            if base in opened:
                opened[base]["escalated"] = True
        elif act == "low_balance_draft_nag":
            base = key.rsplit(":draft-nag", 1)[0]
            if base in opened:
                opened[base]["draft_nagged"] = True
    return opened


# ── HubSpot lookups ─────────────────────────────────────────────────────────

_DEAL_PROPS = ["dealname", "pipeline", "dealstage", "createdate", "po_number",
               "number_of_hours_in_this_po", "teacher_of_record_name",
               "teacher_of_record_email", "student_school", "hubspot_owner_id",
               "invoice__", "student_first_name", "student_last_name_if_diff_from_parent"]


def _student_deals(first: str, last: str, created_after_ms: int | None = None) -> list[dict]:
    """The student's deals, newest first. Exact first-name property match plus
    a last-name check (the property when stamped, else the deal name) so a
    common first name never pulls another family's deal (the Mateo lesson,
    2026-08-28)."""
    if not first:
        return []
    filters = [{"propertyName": "student_first_name", "operator": "EQ", "value": first}]
    if created_after_ms:
        filters.append({"propertyName": "createdate", "operator": "GT",
                        "value": str(created_after_ms)})
    body = {"filterGroups": [{"filters": filters}], "properties": _DEAL_PROPS,
            "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
            "limit": 100}
    res = hs._write("POST", "/crm/v3/objects/deals/search", body)   # searches pass through DRY_RUN
    deals = res.get("results", []) if isinstance(res, dict) else []
    ln = (last or "").strip().lower()
    if not ln:
        return deals
    out = []
    for d in deals:
        p = d.get("properties") or {}
        stamped = (p.get("student_last_name_if_diff_from_parent") or "").strip().lower()
        name = (p.get("dealname") or "").lower()
        if stamped == ln or (not stamped and ln in name) or f"{first.lower()} {ln}" in name:
            out.append(d)
    return out


def _current_po_deal(deals: list[dict]) -> dict | None:
    """The newest deal that carries a PO — the package the alert is about."""
    for d in deals:
        if ((d.get("properties") or {}).get("po_number") or "").strip():
            return d
    return deals[0] if deals else None


def _family_contact(alert: dict) -> dict | None:
    props = ["email", "firstname", "lastname", "phone", "mobilephone", "hubspot_owner_id"]
    if alert.get("parent_email"):
        c = hs.find_contact_by_email(alert["parent_email"], properties=props)
        if c:
            return c
    if alert.get("parent_last"):
        found = hs.find_family_contact(alert.get("student_first", ""), alert["parent_last"])
        if len(found) == 1:
            return found[0]
    return None


def _tor_email_fallback(dp: dict, contact: dict | None) -> str:
    """The teacher's email when the deal names the TOR but carries no address
    (Taylor Rodriguez, 2026-09-09 replay: 'Kylee Cooper-Robles', no email).
    1) the PO agent's own name match among TOR-flagged contacts (unique hit
    only); 2) the family contact's 'Teacher of Record' association (#AP031,
    typeId 15), unique hit only. Never a guess."""
    name = (dp.get("teacher_of_record_name") or "").strip()
    if name:
        parts = name.split()
        first, last = (parts[0], " ".join(parts[1:])) if len(parts) > 1 else ("", parts[0])
        try:
            from .po_inbox import _tor_by_name
            hits = [c for c in _tor_by_name(first, last)
                    if ((c.get("properties") or {}).get("email") or "").strip()]
            if len(hits) == 1:
                return hits[0]["properties"]["email"].strip().lower()
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  TOR name match failed (non-fatal): {e}")
    cid = (contact or {}).get("id")
    if cid and cid != "DRYRUN":
        try:
            assoc = hs._get(f"/crm/v4/objects/contacts/{cid}/associations/contacts")
            tor_ids = [str(r.get("toObjectId")) for r in assoc.get("results", [])
                       if any(t.get("typeId") == 15 for t in r.get("associationTypes", []))]
            if len(tor_ids) == 1:
                c = hs._get(f"/crm/v3/objects/contacts/{tor_ids[0]}", {"properties": "email"})
                return ((c.get("properties") or {}).get("email") or "").strip().lower()
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  TOR association lookup failed (non-fatal): {e}")
    return ""


def _school_short(dealname: str, school: str) -> str:
    parts = [p.strip() for p in (dealname or "").split(" - ")]
    if len(parts) >= 3 and parts[2]:
        return re.sub(r"\s+\d+$", "", parts[2])          # 'iLead 1' -> 'iLead'
    return (school or "").strip()


# ── Teachworks: who they work with, how it is going ─────────────────────────

_NOTE_FIELDS = ("notes", "lesson_notes", "shared_notes", "public_notes", "note", "description")
_ATTENDED = ("attend", "complete")


def _first_name(full: str) -> str:
    """Teachworks names people 'Last, First' (employee_name, student_name);
    the 2026-09-09 replay texted a family about 'Torres,'. A comma means
    last-first; otherwise the first token."""
    full = (full or "").strip()
    if not full:
        return ""
    if "," in full:
        after = full.split(",", 1)[1].strip()
        return after.split()[0].strip() if after else full.split(",")[0].strip()
    return full.split()[0].strip(" ,")


def _tw_recent(alert: dict, deal: dict | None) -> dict:
    """The student's recent attended lessons, both Teachworks accounts:
    {tutor_first, sessions, since, subjects, notes, notes_fields_seen}.
    Window = since the current PO deal was created (else lookback_days).
    Tutor = the most recent attended lesson's tutor, FIRST name only
    (customer-facing rule, Roman 2026-08-14). Lesson notes are read
    liberally from whatever field Teachworks exposes (unverified as of
    2026-09-09; `notes_fields_seen` in the audit record tells us which, if
    any, came through on the first live alert). Never raises."""
    from . import teachworks_client as tw
    lb = cfg().get("low_balance", {}) or {}
    out = {"tutor_first": "", "sessions": 0, "since": "", "subjects": [], "notes": [],
           "notes_fields_seen": []}
    email = (alert.get("parent_email") or "").strip().lower()
    sf = (alert.get("student_first") or "").strip().lower()
    if not email or not sf:
        return out
    dp = (deal or {}).get("properties") or {}
    since = (dp.get("createdate") or "")[:10]
    if not since:
        since = (date.today() - timedelta(days=int(lb.get("lookback_days", 60)))).isoformat()
    out["since"] = since
    today = date.today().isoformat()
    lessons: list[dict] = []
    try:
        for _acct, token in tw.accounts().items():
            for cust in tw.customers_for_family(email, alert.get("parent_last", ""),
                                                alert.get("parent_first", ""), token=token):
                for s in tw.tw_get("students", {"customer_id": cust.get("id")}, token=token):
                    if (s.get("first_name") or "").strip().lower() != sf:
                        continue
                    for l in tw.tw_get("lessons", {"student_id": s["id"], "from_date[gte]": since},
                                       token=token):
                        d = str(l.get("from_date") or "")[:10]
                        if not d or d > today:
                            continue
                        st = str(l.get("status") or "").lower()
                        parts = l.get("participants") or []
                        pst = [str(p.get("status") or "").lower() for p in parts
                               if sf in str(p.get("student_name") or "").lower()] or [st]
                        if not any(any(a in x for a in _ATTENDED) for x in pst + [st]):
                            continue
                        lessons.append(l)
    except Exception as e:  # noqa: BLE001 — enrichment must never block the case
        print(f"  ⚠️  low-balance Teachworks lookup failed (non-fatal): {e}")
        return out
    lessons.sort(key=lambda l: str(l.get("from_date") or ""), reverse=True)
    out["sessions"] = len(lessons)
    if lessons:
        out["tutor_first"] = _first_name(lessons[0].get("employee_name") or "")
    seen: set = set()
    for l in lessons[:4]:
        nm = (l.get("name") or l.get("service_name") or "").strip()
        if nm and nm.lower() not in seen and sf not in nm.lower():
            seen.add(nm.lower())
            out["subjects"].append(nm)
        sources = [l] + [p for p in (l.get("participants") or [])
                         if sf in str(p.get("student_name") or "").lower()]
        for src in sources:
            for f in _NOTE_FIELDS:
                v = src.get(f)
                if isinstance(v, str) and len(v.strip()) > 15:
                    out["notes"].append(re.sub(r"<[^>]+>", " ", v).strip()[:800])
                    if f not in out["notes_fields_seen"]:
                        out["notes_fields_seen"].append(f)
    return out


_POSITIVITY_SYSTEM = (
    "Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md. "
    "You write ONE warm, specific sentence for a parent about what their child has been "
    "working on in recent tutoring sessions, from the tutor's lesson notes. Rules: begin "
    "with 'Lately' and use the child's first name once; at most 25 words; name the subject "
    "or skill, not scores or grades; do not name the tutor; no problems, struggles, "
    "behaviour, or absences; no exclamation marks; no em dashes; plain, human, true to the "
    "notes. If the notes hold nothing positive and concrete, output exactly: NONE."
)


def _positivity(student_first: str, tutor_first: str, notes: list[str], client=None) -> str:
    """One sentence of genuine progress from the last few lesson notes, or ''.
    Behind low_balance.positivity.enabled; the output is validated (length,
    no digits, no em dash) so a bad generation is dropped, never sent."""
    lb = cfg().get("low_balance", {}) or {}
    pc = lb.get("positivity") or {}
    if not pc.get("enabled") or not notes:
        return ""
    try:
        if client is None:
            from anthropic import Anthropic  # lazy: tests need no SDK
            from .config import ANTHROPIC_API_KEY
            client = Anthropic(api_key=ANTHROPIC_API_KEY)
        user = (f"Student first name: {student_first}\nTutor first name: {tutor_first or 'the tutor'}\n"
                f"Lesson notes, newest first:\n" + "\n---\n".join(notes[:4]))
        msg = client.messages.create(model=pc.get("model", "claude-sonnet-4-6"),
                                     max_tokens=int(pc.get("max_tokens", 120)),
                                     system=_POSITIVITY_SYSTEM,
                                     messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  positivity generation failed (non-fatal): {e}")
        return ""
    text = text.strip().strip('"')
    if (not text or text.upper().startswith("NONE") or len(text.split()) > 30
            or re.search(r"\d", text) or "—" in text or "!" in text or "\n" in text):
        return ""
    return _scrub_outbound(text if text.endswith(".") else text + ".")


def _personal(alert: dict, recent: dict, positivity: str) -> tuple[str, str]:
    """(personal_sms, personal_line): the sentence that makes the note ours.
    Tutor FIRST name only, no session counts, no dates (Roman 2026-09-09:
    "lets just use tutors name, first name. no duration"). The positivity
    sentence rides the email only. Each starts with a space so an empty
    value leaves the template clean."""
    student = alert.get("student_first") or "your student"
    tutor = recent.get("tutor_first") or ""
    sms = line = f" {student} has been working with {tutor}." if tutor else ""
    if positivity:
        line = (line + " " + positivity) if line else " " + positivity
    return sms, line


# ── copy ────────────────────────────────────────────────────────────────────

def _fmt_hours(h: float, unit: str = "hours") -> str:
    n = f"{h:g}"
    if unit == "lessons":
        return f"{n} lesson{'' if h == 1 else 's'}"
    return f"{n} hour{'' if h == 1 else 's'}"


def _render(template: str, ctx: dict) -> str:
    out = template
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return _scrub_outbound(out)


def _context(alert: dict, deal: dict | None, contact: dict | None, sender: dict,
             recent: dict | None = None, positivity: str = "") -> dict:
    p = (deal or {}).get("properties") or {}
    cp = (contact or {}).get("properties") or {}
    recent = recent or {}
    personal_sms, personal_line = _personal(alert, recent, positivity)
    tor_name = (p.get("teacher_of_record_name") or "").strip()
    tor_first = tor_name.split()[0] if tor_name else ""
    first = (cp.get("firstname") or alert.get("parent_first") or "there").strip()
    # Customer-facing copy says "4 hours or less" (Roman 2026-09-09), never
    # the exact balance: the number moves between the alert and the read, and
    # the line is what the family needs to act on. Staff notes keep the exact.
    max_hours = (cfg().get("low_balance", {}) or {}).get("max_hours")
    line = (_fmt_hours(float(max_hours), alert.get("unit", "hours")) + " or less"
            if max_hours is not None else _fmt_hours(alert.get("hours", 0), alert.get("unit", "hours")))
    return {
        "first_name": first,
        "parent_name": alert.get("parent_name") or first,
        "student": alert.get("student_first") or alert.get("student") or "your student",
        "student_full": alert.get("student") or "",
        "hours": line,
        "hours_exact": _fmt_hours(alert.get("hours", 0), alert.get("unit", "hours")),
        "tor_name": tor_name or "your teacher of record",
        "tor_first": tor_first or "there",
        "tor_or_ef": tor_name or "your teacher of record or educational facilitator",
        # school / PO number are STAFF context now (never in family copy);
        # blank when unknown so the teacher draft's "(PO 123)" simply vanishes
        "school": _school_short(p.get("dealname") or "", p.get("student_school") or ""),
        "po_number": (p.get("po_number") or "").strip(),
        "po_ref": (f" (PO {(p.get('po_number') or '').strip()})" if (p.get("po_number") or "").strip() else ""),
        "sender_first": sender.get("name", "A+ Tutoring").split()[0],
        "sender_name": sender.get("name", "A+ Tutoring"),
        "sender_email": sender.get("email", "admin@wetutorathome.com"),
        "phone_line": cfg().get("sms", {}).get("justcall_number", ""),
        "tutor_first": recent.get("tutor_first") or "",
        "sessions_on_po": str(recent.get("sessions") or 0),
        "po_since": recent.get("since") or "",
        "personal_sms": personal_sms,
        "personal_line": personal_line,
        "positivity": positivity,
    }


def _seat_mailbox(value: str, seat: dict) -> str:
    """'seat' in config = the charter_sales seat's own Gmail address (from the
    staff block, the only home for names and addresses); anything else is
    taken literally."""
    if (value or "").strip().lower() == "seat":
        return (seat.get("email") or "").strip()
    return (value or "").strip()


# ── outbound rails ──────────────────────────────────────────────────────────

def _send_family_email(to_email: str, ctx: dict, lb: dict) -> None:
    fe = lb.get("family_email") or {}
    tpl = ROOT / (fe.get("template") or "templates/low_balance_charter.html")
    html = _render(tpl.read_text(), ctx)
    payload = {"from": _render(fe.get("from", "A+ Tutoring <admin@wetutorathome.com>"), ctx),
               "to": [to_email],
               "reply_to": _render(fe.get("reply_to", "{sender_email}"), ctx),
               "subject": _render(fe.get("subject", "{student}'s tutoring hours are running low"), ctx),
               "html": html}
    bcc = (cfg().get("hubspot") or {}).get("bcc_log_address")
    if bcc:
        payload["bcc"] = [bcc]
    if DRY_RUN:
        print(f"[DRY_RUN] resend low-balance email -> {to_email}")
        return
    import requests
    r = requests.post("https://api.resend.com/emails",
                      headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                      json=payload, timeout=30)
    r.raise_for_status()


def _send_sms(phone: str, body: str) -> dict:
    from .sms import _jc_send
    return _jc_send(phone, body)


def _in_sms_window() -> bool:
    from .sms import _in_send_window
    return _in_send_window()


def _tor_draft(to_addr: str, subject: str, body: str, lb: dict, seat: dict) -> dict:
    """A real Gmail draft in the charter_sales seat's own mailbox: the seat
    reads it, sends it in one click, and draft_feedback records what changed."""
    te = lb.get("tor_email") or {}
    mailbox = _seat_mailbox(te.get("mailbox") or "", seat)
    bcc = (cfg().get("hubspot") or {}).get("bcc_log_address") or ""
    draft = gm.create_draft(to_addr, subject, body, bcc=bcc, mailbox=mailbox or None)
    d_msg = (draft or {}).get("message") or {}
    try:
        if d_msg.get("id"):
            gm.apply_labels(d_msg["id"], ["A+ Agent/Draft Pending"], mailbox=mailbox or None)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  draft label failed (non-fatal): {e}")
    draft_feedback.register(draft, "low_balance_tor", body, to_addr, "low_balance",
                            thread_id=d_msg.get("threadId") or "",
                            meta={"mailbox": mailbox})
    return draft or {}


def _phone_for(alert: dict, contact: dict | None) -> str:
    cp = (contact or {}).get("properties") or {}
    return (alert.get("parent_phone") or cp.get("mobilephone") or cp.get("phone") or "").strip()


def _opted_out(contact: dict | None) -> bool:
    prop = (cfg().get("sms", {}) or {}).get("opt_out_property")
    if not prop or not contact:
        return False
    v = str(((contact.get("properties") or {}).get(prop) or "")).lower()
    return v in ("true", "yes", "1")


# ── the case ────────────────────────────────────────────────────────────────

def handle_alert(thread_id: str, message: dict, alert: dict) -> dict:
    """One Teachworks package-balance alert -> one renewal case (or a note on
    the open one). Returns the audit record for the triage loop."""
    lb = cfg().get("low_balance", {}) or {}
    message_id = message.get("id")
    key = case_key(alert)
    seat_key = lb.get("owner", "charter_sales")
    seat = staff(seat_key) or {}
    record = {"message_id": message_id, "thread_id": thread_id, "contact_id": None,
              "new_contact": False, "category": "low_balance", "risk": "low",
              "confidence": 1.0, "owner": seat_key, "cancellation_reason": "",
              "reason": (f"Teachworks package-balance alert: {alert['student']} "
                         f"({alert['package']}) at {_fmt_hours(alert['hours'], alert['unit'])}"),
              "case_key": key, "student": alert["student"], "package": alert["package"],
              "hours": alert["hours"], "parent_email": alert.get("parent_email", "")}
    if not lb.get("enabled", True):
        record["action_taken"] = "low_balance_disabled"
        audit.append(record)
        return record
    # Roman 2026-09-09: "4 hours or less". Teachworks' alert level is set per
    # package in Teachworks; this is OUR gate, so a package alerting at 6 or
    # 8 hours never opens a case until the balance actually reaches the line.
    max_hours = lb.get("max_hours")
    if max_hours is not None and float(alert.get("hours", 0)) > float(max_hours):
        record["action_taken"] = "low_balance_above_threshold"
        record["max_hours"] = float(max_hours)
        audit.append(record)
        print(f"  ⏭ low balance alert for {alert['student']} at {_fmt_hours(alert['hours'], alert['unit'])} "
              f"is above the {max_hours}-hour line; no case")
        return record

    # Teachworks re-fires on every balance change: the open case gets a note,
    # never a second text (Paola's 2026-01-29 report: one family texted 3x).
    cases = open_cases()
    if key in cases:
        prior = cases[key]
        tid = prior.get("ticket_id")
        if tid and tid != "DRYRUN":
            try:
                hs.add_ticket_note(tid, f"🔁 Teachworks alerted again: {alert['student']} is now at "
                                        f"{_fmt_hours(alert['hours'], alert['unit'])} on "
                                        f"{alert['package']}. Case already open; no new outreach.")
                hs.link_thread_to_ticket(thread_id, tid)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  repeat-alert note failed (non-fatal): {e}")
        record.update(action_taken="low_balance_repeat", ticket_id=tid)
        audit.append(record)
        print(f"  🔁 low balance repeat for {alert['student']} (case open, ticket {tid})")
        return record

    # ── resolve who this is ──
    contact = _family_contact(alert)
    contact_id = (contact or {}).get("id")
    deals = []
    try:
        deals = _student_deals(alert.get("student_first", ""), alert.get("student_last", ""))
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  deal lookup failed (non-fatal): {e}")
    deal = _current_po_deal(deals)
    dp = (deal or {}).get("properties") or {}
    pipeline = str(dp.get("pipeline") or "")
    charter = is_charter_package(alert["package"], pipeline)
    tor_email = (dp.get("teacher_of_record_email") or "").strip().lower()
    if not tor_email and charter and deal:
        tor_email = _tor_email_fallback(dp, contact)
    no_tor = [str(x) for x in lb.get("no_teacher_email_pipelines", [])]
    tor_blocked = pipeline in no_tor
    # LOW_BALANCE_FORCE_ARMED=1 lets a DRY_RUN replay walk every outreach
    # path (each rail is dry-run guarded) without touching config.
    armed = (bool(lb.get("armed")) or os.environ.get("LOW_BALANCE_FORCE_ARMED") == "1") and charter
    # what makes the note ours: the tutor, the sessions on this PO, and (when
    # enabled) one true sentence from the last few lesson notes
    recent = _tw_recent(alert, deal) if charter else {}
    positivity = _positivity(alert.get("student_first", ""), recent.get("tutor_first", ""),
                             recent.get("notes") or []) if charter else ""
    ctx = _context(alert, deal, contact, seat, recent, positivity)
    hrs = ctx["hours_exact"]               # staff-facing: ticket, task, DM
    record.update(tutor_first=recent.get("tutor_first") or "", sessions_on_po=recent.get("sessions") or 0,
                  notes_fields_seen=recent.get("notes_fields_seen") or [],
                  positivity=positivity)

    # ── ticket first (everything else hangs off it) ──
    hs_cfg = cfg()["hubspot"]
    tf = cfg().get("ticket_fields", {}) or {}
    sla_due = add_business_hours(now_la(), float(lb.get("sla_hours", 8)))
    school_tag = ctx["school"] or "school unknown"
    subject = f"Low balance: {alert['student']} ({school_tag}), {hrs} left"
    flags = []
    if not contact:
        flags.append("family contact NOT found in HubSpot (matched by alert email / student + surname)")
    if not deal:
        flags.append("no deal found for this student (name lookup)")
    elif not dp.get("po_number"):
        flags.append("student's newest deal has no PO number")
    if charter and not tor_email:
        flags.append("no teacher-of-record email on the deal; teacher not contacted")
    if not charter:
        flags.append("NOT a charter package (Gold / private pay): no automated outreach; "
                     "phase 2 per Roman, handle by hand")
    if tor_blocked:
        flags.append("pipeline is on the no-teacher-email list (Level Up Terri cannot issue "
                     "additional POs, Roman 2025-10-29); family only")
    desc = (f"Auto-filed by the low-balance agent.\n"
            f"Student: {alert['student']} | Package: {alert['package']} | "
            f"Unused: {hrs} (alert level {_fmt_hours(alert['level'], alert['unit'])})\n"
            f"Parent: {alert.get('parent_name') or '?'} <{alert.get('parent_email') or '?'}> "
            f"{alert.get('parent_phone') or ''}\n"
            + (f"Deal: {dp.get('dealname')} (id {deal['id']}) | PO {dp.get('po_number') or '?'} | "
               f"{dp.get('number_of_hours_in_this_po') or '?'} hrs | pipeline {hs.pipeline_label(pipeline) or pipeline}\n"
               if deal else "Deal: none found\n")
            + (f"TOR: {dp.get('teacher_of_record_name') or '?'} <{tor_email or '?'}>\n" if deal else "")
            + f"SLA due: {sla_due.isoformat()}\n"
            + ("Flags: " + "; ".join(flags) if flags else "Flags: none")
            + "\nThis case closes itself when a new PO for the student creates a deal.")
    ticket = hs.create_ticket(subject, seat.get("hubspot_owner_id"),
                              hs_cfg["ticket_stages"]["needs_approval"], desc, contact_id,
                              priority=tf.get("priority_map", {}).get(lb.get("priority", "normal"), "MEDIUM"),
                              category=tf.get("category_map", {}).get("low_balance", tf.get("category_default")),
                              source=tf.get("source"))
    tid = ticket.get("id")
    record.update(ticket_id=tid, contact_id=contact_id, deal_id=(deal or {}).get("id"),
                  pipeline=pipeline, school=ctx["school"], tor_email=tor_email,
                  charter=charter, armed=armed, sla_due=sla_due.isoformat(),
                  opened_at=datetime.now(timezone.utc).isoformat(), flags=flags)
    if tid and tid != "DRYRUN":
        try:
            hs.link_thread_to_ticket(thread_id, tid)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  thread→ticket link failed (non-fatal): {e}")

    # ── the copy (rendered once; sent, drafted, or merely shown) ──
    sms_tpl = (lb.get("sms_template_with_tutor") if ctx["tutor_first"] else "") or lb.get("sms_template", "")
    sms_body = _render(sms_tpl, ctx) if sms_tpl else ""
    te = lb.get("tor_email") or {}
    tor_subject = _render(te.get("subject", "New PO needed for {student_full}"), ctx)
    tor_body = _render(te.get("body", ""), ctx) if te.get("body") else ""
    phone = _phone_for(alert, contact)
    to_email = (alert.get("parent_email") or ((contact or {}).get("properties") or {}).get("email") or "").strip()
    note_parts = [f"📧 Original alert\n{(message.get('text') or '')[:1500]}"]
    lines = []
    if DRY_RUN:
        # a replay's whole point is to read the copy as the family would
        fe = lb.get("family_email") or {}
        try:
            html = _render((ROOT / (fe.get("template") or "templates/low_balance_charter.html")).read_text(), ctx)
            email_text = re.sub(r"\n{3,}", "\n\n", re.sub(r"<[^>]+>", "", html.replace("</p>", "\n")
                                                          .replace("<br>", "\n")).replace("&nbsp;", " ")).strip()
        except Exception as e:  # noqa: BLE001
            email_text = f"(template render failed: {e})"
        print("\n══════ LOW BALANCE PREVIEW ══════"
              f"\nStudent: {alert['student']} | tutor: {ctx['tutor_first'] or '(none found)'} | "
              f"sessions on PO: {ctx['sessions_on_po']} | notes fields seen: {recent.get('notes_fields_seen')}"
              f"\nPositivity: {positivity or '(none)'}"
              f"\n\n--- SMS to {phone or '(no phone)'} ---\n{sms_body}"
              f"\n\n--- EMAIL to {to_email or '(no email)'} | subject: {_render(fe.get('subject', ''), ctx)} ---\n{email_text}"
              f"\n\n--- TEACHER DRAFT to {tor_email or '(no TOR email)'}"
              f"{' (BLOCKED: no-teacher-email pipeline)' if tor_blocked else ''} | subject: {tor_subject} ---\n{tor_body}"
              "\n══════════════════════════════════\n")

    if armed:
        # family SMS: quiet hours defer it to the hourly sweep (never dropped)
        if phone and sms_body and not _opted_out(contact):
            if _in_sms_window():
                try:
                    _send_sms(phone, sms_body)
                    audit.append({"message_id": f"{key}:sms", "source": "low_balance",
                                  "action_taken": "low_balance_sms_sent", "phone": phone,
                                  "ticket_id": tid, "body": sms_body})
                    record["sms_sent"] = True
                    lines.append(f"📱 Texted {phone}: \"{sms_body}\"")
                except Exception as e:  # noqa: BLE001
                    record["sms_error"] = str(e)[:200]
                    lines.append(f"⚠️ Text to {phone} FAILED ({str(e)[:80]}); send it by hand")
            else:
                record.update(sms_pending=True, sms_body=sms_body, phone=phone)
                lines.append(f"📱 Text queued for the 8am-8pm PT window: \"{sms_body}\"")
        elif not phone:
            lines.append("📱 No phone on file; no text sent")
        elif _opted_out(contact):
            lines.append("📱 Family opted out of texts; no text sent")
        # family email
        fe = lb.get("family_email") or {}
        if to_email and fe.get("mode", "send") == "send":
            try:
                _send_family_email(to_email, ctx, lb)
                record["email_sent"] = to_email
                lines.append(f"✉️ Emailed the family at {to_email} ({_render(fe.get('subject', ''), ctx)})")
            except Exception as e:  # noqa: BLE001
                record["email_error"] = str(e)[:200]
                lines.append(f"⚠️ Family email FAILED ({str(e)[:80]}); send it by hand")
        # teacher of record: email only, drafted in the seat's mailbox
        if tor_email and not tor_blocked and tor_body:
            if te.get("mode", "draft") == "draft":
                try:
                    draft = _tor_draft(tor_email, tor_subject, tor_body, lb, seat)
                    mailbox = _seat_mailbox(te.get("mailbox") or "", seat)
                    record["tor_draft_id"] = (draft or {}).get("id")
                    record["tor_mailbox"] = mailbox
                    lines.append(f"🍎 Teacher email DRAFTED to {tor_email} in "
                                 f"{mailbox or 'the charter@ mailbox'}: open Drafts, read, send")
                except Exception as e:  # noqa: BLE001
                    record["tor_error"] = str(e)[:200]
                    lines.append(f"⚠️ Teacher draft FAILED ({str(e)[:80]}); email {tor_email} by hand")
            else:
                lines.append(f"🍎 Teacher email mode '{te.get('mode')}' not supported; email {tor_email} by hand")
    else:
        why = ("agent not armed" if charter else "not a charter package")
        lines.append(f"⏸ No outreach ({why}). What the agent WOULD send:")
        if sms_body:
            lines.append(f"  📱 SMS to {phone or 'no phone'}: \"{sms_body}\"")
        if to_email:
            lines.append(f"  ✉️ Email to {to_email}: {_render((lb.get('family_email') or {}).get('subject', ''), ctx)}")
        if tor_email and not tor_blocked and tor_body:
            lines.append(f"  🍎 Teacher email to {tor_email}: {tor_subject}\n{tor_body}")

    # follow-up task for the seat (the human side of the chase)
    task_line = ""
    fu_days = float(lb.get("follow_up_business_days", 3))
    if seat.get("hubspot_owner_id"):
        due = add_business_hours(now_la(), fu_days * 8)
        tbody = (f"{alert['student']} ({school_tag}) has {hrs} left on {alert['package']}.\n"
                 + "\n".join(lines) + "\n\n"
                 f"Next: confirm the school is issuing a new PO (ask {ctx['tor_name']} if the "
                 f"family has not). The case closes itself when the PO lands.\n"
                 f"Ticket: {hs.ticket_url(tid) if tid else ''}")
        try:
            t = hs.create_task(f"Low balance follow-up: {alert['student']} ({school_tag})", tbody,
                               seat["hubspot_owner_id"], int(due.timestamp() * 1000),
                               priority="MEDIUM", contact_id=contact_id)
            record["task_id"] = t.get("id")
            task_line = f"\n📋 Follow-up task due {due.strftime('%a %b %-d')}"
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  task create failed (non-fatal): {e}")

    if tid and tid != "DRYRUN":
        try:
            hs.add_ticket_note(tid, "\n".join(note_parts + ["", "What the agent did:"] + lines))
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  ticket note failed (non-fatal): {e}")

    # one DM, to the seat only (Danielle 2026-08-12: Paola, nobody else)
    dm = (f"📉 LOW BALANCE: *{alert['student']}* ({school_tag}) has {hrs} left on "
          f"{alert['package']}. Parent {alert.get('parent_name') or '?'} "
          f"{alert.get('parent_email') or ''} {phone}\n" + "\n".join(lines) + task_line
          + (f"\n🚩 {'; '.join(flags)}" if flags else "")
          + (f"\nTicket: {hs.ticket_url(tid)}" if tid and tid != 'DRYRUN' else ""))
    for role in lb.get("notify", [seat_key]) or []:
        s = staff(role) or {}
        if s.get("slack_user_id"):
            try:
                slack_client.dm(s["slack_user_id"], dm)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  low-balance DM failed (non-fatal): {e}")

    record["action_taken"] = "low_balance_opened"
    record["message_id"] = key                     # the case is the audit identity
    record["alert_message_id"] = message_id
    audit.append(record)
    # the triage loop dedupes on the ALERT's message id; keep that trail too
    audit.append({"message_id": message_id, "thread_id": thread_id, "source": "low_balance",
                  "action_taken": "low_balance_alert_processed", "case_key": key,
                  "ticket_id": tid})
    print(f"  📉 low balance case opened: {alert['student']} {hrs} → ticket {tid}"
          f"{' (armed)' if armed else ' (held)'}")
    return record


# ── the sweep: deferred texts, self-closing cases, escalation ───────────────

def _resolve(key: str, case: dict, reason: str, close_ticket: bool = True) -> None:
    tid = case.get("ticket_id")
    if tid and tid != "DRYRUN":
        try:
            hs.add_ticket_note(tid, f"✅ Low-balance case resolved: {reason}")
            if close_ticket:
                hs.update_ticket_stage(tid, cfg()["hubspot"]["ticket_stages"]["closed"])
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  resolve note/close failed (non-fatal): {e}")
    audit.append({"message_id": f"{key}:resolved", "source": "low_balance",
                  "action_taken": "low_balance_resolved", "reason": reason,
                  "ticket_id": tid, "student": case.get("student")})
    print(f"  ✅ low balance resolved: {case.get('student')} — {reason}")


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def run_sweep(force: bool = False) -> None:
    """Called from deal_sync.run() every cycle; self-gates to once an hour."""
    lb = cfg().get("low_balance", {}) or {}
    if not lb.get("enabled", True):
        return
    now = now_la()
    if not force and now.minute >= 15:
        return
    cases = open_cases()
    if not cases:
        return
    stop_patterns = [p.lower() for p in cfg().get("deal_automation", {}).get(
        "stop_stage_patterns", ["stopped", "closed lost", "cancelled"])]
    escalate_days = int(lb.get("escalate_days", 10))
    seat = staff(lb.get("owner", "charter_sales")) or {}
    esc = staff(lb.get("escalate_to", "visionary")) or {}
    now_utc = datetime.now(timezone.utc)
    stalled = []
    for key, case in cases.items():
        opened = case.get("opened_at") or case.get("timestamp") or ""
        first = (case.get("student") or "").split()[0] if case.get("student") else ""
        last = " ".join((case.get("student") or "").split()[1:])
        # 1. the school's new PO arrived (po_inbox made the deal) -> done
        try:
            newer = _student_deals(first, last, _ms(opened) if opened else None)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  low-balance sweep deal lookup failed for {key}: {e}")
            newer = []
        po_deal = next((d for d in newer if ((d.get("properties") or {}).get("po_number") or "").strip()), None)
        if po_deal:
            p = po_deal["properties"]
            _resolve(key, case, f"new PO {p.get('po_number')} received: {p.get('dealname')} "
                                f"(deal {po_deal['id']})")
            continue
        # 2. the family stopped -> not a renewal chase any more
        did = case.get("deal_id")
        if did and did != "DRYRUN":
            try:
                d = hs._get(f"/crm/v3/objects/deals/{did}", {"properties": "pipeline,dealstage"})
                dp = d.get("properties") or {}
                label = hs.stage_label(dp.get("pipeline"), dp.get("dealstage")).lower()
                if label and any(pat in label for pat in stop_patterns):
                    _resolve(key, case, f"deal moved to '{label}' (family not continuing)")
                    continue
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  low-balance sweep deal read failed for {key}: {e}")
        # 3. a text that was queued for the send window (body + phone were
        #    rendered and stored at alert time, so nothing is re-derived here)
        if case.get("sms_pending") and not case.get("sms_sent") and lb.get("armed") and _in_sms_window():
            body = case.get("sms_body") or ""
            phone = case.get("phone") or ""
            if phone and body:
                try:
                    _send_sms(phone, body)
                    audit.append({"message_id": f"{key}:sms", "source": "low_balance",
                                  "action_taken": "low_balance_sms_sent", "phone": phone,
                                  "ticket_id": case.get("ticket_id"), "body": body})
                except Exception as e:  # noqa: BLE001
                    print(f"  ⚠️  deferred low-balance text failed for {key}: {e}")
        # 4. teacher draft still sitting unsent -> one nag to the seat
        if (case.get("tor_draft_id") and not case.get("draft_nagged")
                and opened and now_utc - datetime.fromisoformat(opened) > timedelta(hours=float(lb.get("draft_unsent_nag_hours", 24)))):
            try:
                still = gm.get_draft(case["tor_draft_id"], mailbox=case.get("tor_mailbox") or None)
            except Exception:  # noqa: BLE001
                still = None
            if still is not None and seat.get("slack_user_id"):
                slack_client.dm(seat["slack_user_id"],
                                f"🍎 The teacher email for *{case.get('student')}* (low balance) is still "
                                f"in your Gmail Drafts. Send it or discard it so the case moves.")
                audit.append({"message_id": f"{key}:draft-nag", "source": "low_balance",
                              "action_taken": "low_balance_draft_nag", "ticket_id": case.get("ticket_id")})
        # 5. stalled: no PO after escalate_days
        if opened and not case.get("escalated"):
            age = (now_utc - datetime.fromisoformat(opened)).days
            if age >= escalate_days:
                stalled.append((key, case, age))
    if stalled:
        lines = [f"• {c.get('student')} ({c.get('school') or '?'}) opened {a}d ago"
                 + (f" · {hs.ticket_url(c['ticket_id'])}" if c.get("ticket_id") and c["ticket_id"] != "DRYRUN" else "")
                 for _k, c, a in stalled]
        text = (f"🚩 LOW BALANCE, NO PO after {escalate_days}+ days ({len(stalled)}):\n" + "\n".join(lines)
                + "\nEach one still has no new PO deal. Confirm with the teacher of record, or mark "
                  "the deal Stopped if the family is done.")
        for who in (seat, esc):
            if who.get("slack_user_id"):
                try:
                    slack_client.dm(who["slack_user_id"], text)
                except Exception as e:  # noqa: BLE001
                    print(f"  ⚠️  escalation DM failed (non-fatal): {e}")
        for key, c, a in stalled:
            audit.append({"message_id": f"{key}:escalated", "source": "low_balance",
                          "action_taken": "low_balance_escalated", "age_days": a,
                          "ticket_id": c.get("ticket_id")})


# ── replay: run one real alert through the agent (DRY_RUN for a preview) ───

def replay_thread(thread_id: str) -> dict | None:
    """Re-run the Teachworks alert on a HubSpot conversation thread as if it
    had just arrived. With DRY_RUN=true every write is printed instead of
    made and the rendered SMS / email / teacher draft are shown in full;
    with LOW_BALANCE_FORCE_ARMED=1 the outreach paths run too (all dry-run
    guarded). Used for the 2026-09-09 Taylor Rodriguez test case."""
    hs.SEARCH_PASSTHROUGH = True          # reads must work or the replay proves nothing
    msgs = [m for m in hs.get_messages(thread_id)
            if m.get("type") == "MESSAGE" and is_teachworks_sender(_addrs(m))]
    if not msgs:
        print(f"replay: no Teachworks message on thread {thread_id}")
        return None
    m = msgs[-1]
    body = m.get("text") or m.get("richText") or ""
    alert = parse_alert(body)
    if not alert:
        print(f"replay: message {m.get('id')} is not a package-balance alert:\n{body[:400]}")
        return None
    print(f"replay: thread {thread_id} message {m.get('id')} → {alert['student']} "
          f"{_fmt_hours(alert['hours'], alert['unit'])} on {alert['package']}")
    return handle_alert(thread_id, m, alert)


def _addrs(message: dict) -> list[str]:
    out = []
    for s in message.get("senders") or []:
        dv = s.get("deliveryIdentifier")
        if isinstance(dv, dict) and "@" in str(dv.get("value", "")):
            out.append(str(dv["value"]).lower())
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Low-balance agent: replay or sweep")
    ap.add_argument("--thread", help="HubSpot conversation thread id carrying a Teachworks alert")
    ap.add_argument("--sweep", action="store_true", help="run the resolver sweep now (ignores the hourly gate)")
    args = ap.parse_args()
    if args.thread:
        replay_thread(args.thread)
    elif args.sweep:
        run_sweep(force=True)
    else:
        ap.print_help()

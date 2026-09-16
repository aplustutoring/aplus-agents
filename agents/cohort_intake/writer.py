"""HubSpot writer: family contacts, ES (TOR) contacts, one deal per student,
associations (spec §5.3, §5.4). Fill-only on existing records, agent props
always written, idempotent on school + student id + subject + term (§6).

Enumeration props are written by LABEL looked up in the portal at run time
(the fleet rule: agents read labels, never internal values). A label the
portal does not carry is skipped and reported; it never fails the row.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from functools import lru_cache
from zoneinfo import ZoneInfo

from . import cohort as C, messages as M
from .rows import Group, Row
from ._bootstrap import agent_cfg, audit, email_cfg, hs, staff

PT = ZoneInfo("America/Los_Angeles")

FAMILY_PROPS = ["email", "firstname", "lastname", "phone", "a_persona", "lifecyclestage",
                "hubspot_owner_id", "charter_school_family_", "parent_first_name",
                "parent_last_name", "parent_email", "parent_phone_number", "student_last_name",
                "student_last_name_if_diff_from_parent", "student_email_address",
                "what_is_your_child_s_current_grade_level_", "student_school", "subject_need",
                "teacher_of_record_name", "teacher_of_record_email_address"]
TOR_PROPS = ["email", "firstname", "lastname", "a_persona", "hubspot_owner_id",
             "educational_facillitator_teacher_of_record", "charter_school_teacher",
             "school_canonical"]
DEAL_PROPS = ["dealname", "pipeline", "dealstage", "amount", "hubspot_owner_id", "iem_student_id",
              "hsa_cohort", "hsa_group", "hsa_sessions", "hsa_start", "hsa_slot", "description"]


@dataclass
class Outcome:
    student_id: str
    deal_id: str = ""
    deal_created: bool = False
    contact_id: str = ""
    tor_id: str = ""
    amount: Decimal = Decimal(0)
    sessions: int = 0
    start: date | None = None
    skipped_props: list[str] = field(default_factory=list)


# ── enumeration labels → values ──────────────────────────────────────────────

@lru_cache(maxsize=64)
def _options(obj: str, prop: str) -> tuple[tuple[str, str], ...]:
    try:
        got = hs._get(f"/crm/v3/properties/{obj}/{prop}")
    except Exception:  # noqa: BLE001 — unknown property = no options
        return ()
    return tuple((o.get("label", ""), o.get("value", "")) for o in (got or {}).get("options", []))


def enum_value(obj: str, prop: str, wanted: str) -> str | None:
    """Value whose LABEL equals `wanted` (case-insensitive), else whose label
    contains it as a whole token; None when the portal has no such option."""
    w = (wanted or "").strip().lower()
    if not w:
        return None
    opts = _options(obj, prop)
    for label, value in opts:
        if label.strip().lower() == w:
            return value
    for label, value in opts:
        if w in label.lower().split() or w in label.lower():
            return value
    return None


_WINDOW = __import__("re").compile(r"(\d{1,2})\s*(am|pm)\s*-\s*(\d{1,2})\s*(am|pm)", __import__("re").I)


def _hour24(h: int, ampm: str) -> int:
    h = h % 12
    return h + (12 if ampm.lower() == "pm" else 0)


def _window_value(prop: str, slot: C.Slot) -> str | None:
    """The portal's per-day schedule preference is a WINDOW ('9AM-12PM',
    '12PM-3PM', read live 2026-09-16), not a time. Pick the option whose
    window contains the slot hour (end inclusive: 3:00 PM → 12PM-3PM)."""
    m = __import__("re").match(r"(\d{1,2}):(\d{2}) (AM|PM)", slot.time_label)
    if not m:
        return None
    hour = _hour24(int(m.group(1)), m.group(3))
    for label, value in _options("deals", prop):
        w = _WINDOW.search(label)
        if not w:
            continue
        lo, hi = _hour24(int(w.group(1)), w.group(2)), _hour24(int(w.group(3)), w.group(4))
        if lo <= hour <= hi:
            return value
    return None


def _grade_value(grade: str) -> str | None:
    """'9' → the option labelled '9th', '9th Grade', 'Grade 9' or '9'."""
    g = (grade or "").strip()
    if not g:
        return None
    for label, value in _options("contacts", "what_is_your_child_s_current_grade_level_"):
        tokens = label.lower().replace("grade", " ").replace("th", " ").replace("st", " ") \
            .replace("nd", " ").replace("rd", " ").split()
        if g.lower() in tokens or label.strip().lower() == g.lower():
            return value
    return None


# ── owners ───────────────────────────────────────────────────────────────────

def group_owner(group_number: int) -> dict:
    """Odd group → scheduler_a_l, even → scheduler_m_z (LOCKED Roman 9/15)."""
    gp = agent_cfg()["hubspot"]["group_parity"]
    return staff(gp["odd"] if group_number % 2 else gp["even"]) or {}


def tor_owner() -> dict:
    return staff(agent_cfg()["hubspot"]["tor_owner"]) or {}


# ── contacts ─────────────────────────────────────────────────────────────────

def _fill_only(existing: dict, wanted: dict) -> dict:
    """Props to PATCH on an existing record: only those blank today."""
    cur = existing.get("properties") or {}
    return {k: v for k, v in wanted.items() if v not in (None, "") and not str(cur.get(k) or "").strip()}


def _persona(existing: dict | None, add: str) -> str:
    cur = ((existing or {}).get("properties") or {}).get("a_persona") or ""
    parts = [p for p in cur.split(";") if p]
    if add not in parts:
        parts.append(add)
    return ";".join(parts)


def family_props(row: Row, owner_id: str, existing: dict | None, skipped: list[str]) -> dict:
    grade = _grade_value(row.grade)
    if row.grade and not grade:
        skipped.append(f"grade '{row.grade}' has no option on what_is_your_child_s_current_grade_level_")
    subj = enum_value("contacts", "subject_need", row.subject.split()[0] if row.subject else "")
    if row.subject and not subj:
        skipped.append(f"subject '{row.subject}' has no option on subject_need")
    props = {
        "firstname": row.parent_first, "lastname": row.parent_last,
        "phone": row.parent_phone, "a_persona": _persona(existing, "Family"),
        "lifecyclestage": "customer", "hubspot_owner_id": owner_id,
        "charter_school_family_": "true",
        "parent_first_name": row.parent_first, "parent_last_name": row.parent_last,
        "parent_email": row.parent_email, "parent_phone_number": row.parent_phone,
        "student_last_name": row.student_first,                  # label "Student FIRST Name"
        "student_last_name_if_diff_from_parent": row.student_last,
        "student_email_address": row.student_email or "",
        "what_is_your_child_s_current_grade_level_": grade or "",
        "student_school": row.school, "subject_need": subj or "",
        "teacher_of_record_name": row.es_name, "teacher_of_record_email_address": row.es_email,
    }
    return {k: v for k, v in props.items() if v not in (None, "")}


def tor_props(row: Row, existing: dict | None, skipped: list[str]) -> dict:
    label = agent_cfg()["hubspot"]["charter_school_teacher_label"]
    school_opt = enum_value("contacts", "charter_school_teacher", label)
    if not school_opt:
        skipped.append(f"charter_school_teacher has no option labelled '{label}'")
    props = {
        "firstname": row.es_first, "lastname": row.es_last,
        "a_persona": _persona(existing, "Teacher of Record/EF/ES"),
        "hubspot_owner_id": str(tor_owner().get("hubspot_owner_id") or ""),
        "educational_facillitator_teacher_of_record": "true",
        "charter_school_teacher": school_opt or "", "school_canonical": row.school,
    }
    return {k: v for k, v in props.items() if v not in (None, "")}


def upsert_contact(email: str, wanted: dict, read_props: list[str], persona: str,
                   dry_run: bool) -> tuple[str, str]:
    """(contact id, 'created'|'updated'|'unchanged'). Existing = fill-only,
    except a_persona which gains the persona (multi-select, never loses one)."""
    existing = hs.find_contact_by_email(email, properties=read_props)
    if existing:
        patch = _fill_only(existing, wanted)
        cur_persona = (existing.get("properties") or {}).get("a_persona") or ""
        if persona not in cur_persona.split(";"):
            patch["a_persona"] = wanted["a_persona"]
        if not patch:
            return str(existing["id"]), "unchanged"
        if not dry_run:
            hs.patch_contact_props(existing["id"], patch)
        return str(existing["id"]), "updated"
    if dry_run:
        return "DRYRUN", "created"
    extra = {k: v for k, v in wanted.items() if k not in ("firstname", "lastname", "phone")}
    made = hs.create_contact(email, wanted.get("firstname"), wanted.get("lastname"),
                            wanted.get("phone"), extra_props=extra)
    return str(made.get("id")), "created"


# ── deals ────────────────────────────────────────────────────────────────────

def find_deal(row: Row) -> dict | None:
    """The existing deal for school + student id + subject + term, if any."""
    hc = agent_cfg()["hubspot"]
    hits = hs._search_all("/crm/v3/objects/deals/search", [
        {"propertyName": "pipeline", "operator": "EQ", "value": hc["pipeline"]},
        {"propertyName": "iem_student_id", "operator": "EQ", "value": row.student_id},
    ], DEAL_PROPS)
    tag = f"IEM HSA {row.subject}".lower()
    for d in hits:
        name = ((d.get("properties") or {}).get("dealname") or "").lower()
        if tag in name and row.school.lower() in name:
            return d
    return None


def stage_ok() -> str:
    """The Pre-Lesson stage id, checked against the portal label because the
    SMS sweep qualifies deals on the label containing 'pre-lesson'."""
    hc = agent_cfg()["hubspot"]
    label = hs.stage_label(hc["pipeline"], hc["pre_lesson_stage"]).lower()
    if "pre-lesson" not in label:
        raise RuntimeError(f"stage {hc['pre_lesson_stage']} in pipeline {hc['pipeline']} is labelled "
                           f"{label!r}, not Pre-Lesson; the SMS sweep would never see these deals")
    return hc["pre_lesson_stage"]


def deal_props(row: Row, group: Group, dates: list[date], amount: Decimal, sessions: int,
               owner_id: str, skipped: list[str]) -> dict:
    hc = agent_cfg()["hubspot"]
    charter = enum_value("deals", "online__inperson__charter", "Charter")
    if not charter:
        skipped.append("online__inperson__charter has no 'Charter' option")
    slot_prop = "monday_schedule_preference" if group.slot.weekday == 0 else "wednesday_schedule_preference"
    slot_val = _window_value(slot_prop, group.slot)
    if not slot_val:
        skipped.append(f"{slot_prop} has no window option covering {group.slot.time_label}")
    start, end = dates[0], dates[-1]
    props = {
        "dealname": M.deal_name(row),
        "hubspot_owner_id": owner_id,
        "online__inperson__charter": charter or "",
        "iem_student_id": row.student_id,
        "student_first_name": row.student_first,
        "student_last_name_if_diff_from_parent": row.student_last,
        "student_grade": row.grade, "student_school": row.school,
        "parent_email": row.parent_email, "parent_phone": row.parent_phone,
        "teacher_of_record_name": row.es_name, "teacher_of_record_email": row.es_email,
        "tor_first_name": row.es_first, "tor_last_name": row.es_last,
        "number_of_hours_in_this_po": str(sessions),
        "start_of_tutoring_for_this_deal": start.isoformat(),
        "date_of_last_lesson_in_this_deal": end.isoformat(),
        "lessons_fulfilled_date": end.isoformat(),
        "schedule_preferences": M.schedule_preference(group, start),
        slot_prop: slot_val or "",
        "hsa_cohort": str(group.cohort.number),
        "hsa_group": f"C{group.cohort.number}-G{group.number}",
        "hsa_sessions": str(sessions),
        "hsa_start": start.isoformat(),
        "hsa_slot": group.slot.label,
        "description": M.deal_description(row, group, dates, amount, sessions),
    }
    return {k: v for k, v in props.items() if v not in (None, "")}


def _closedate_ms(d: date) -> int:
    return int(datetime.combine(d, time(9, 0), tzinfo=PT).timestamp() * 1000)


# ── plan + execute ───────────────────────────────────────────────────────────

def plan_group(group: Group, today: date) -> dict:
    """What execute_group would do, without writing: per-student amounts and
    sessions (late adds get the remaining sessions), which contacts/deals
    exist, who owns the group."""
    owner = group_owner(group.number)
    dates = group.dates
    amounts = group.amounts
    existing_deals = {r.student_id: find_deal(r) for r in group.rows}
    family_actions, tor_actions, deal_actions, sessions = {}, {}, [], []
    for r in group.rows:
        fam = hs.find_contact_by_email(r.parent_email, properties=["email"])
        family_actions[r.student_id] = "update" if fam else "create"
        if r.es_email not in tor_actions:
            tor = hs.find_contact_by_email(r.es_email, properties=["email"])
            tor_actions[r.es_email] = "update" if tor else "create"
        d = existing_deals[r.student_id]
        late = d is None and today > dates[0]
        n = len(C.remaining_sessions(dates, today)) if late else len(dates)
        sessions.append(n)
        if d:
            cur = (d.get("properties") or {}).get("amount") or ""
            changed = Decimal(str(cur or 0)) != amounts[group.rows.index(r)]
            deal_actions.append(f"update {d['id']}" + (" (amount re-split)" if changed else ""))
        else:
            deal_actions.append("create" + (f" (late add: {n} of {len(dates)} sessions)" if late else ""))
    return {"owner_name": owner.get("name", "?"), "owner_id": str(owner.get("hubspot_owner_id") or ""),
            "amounts": amounts, "sessions": sessions, "dates": dates,
            "family_actions": family_actions, "tor_actions": tor_actions,
            "deal_actions": deal_actions, "existing_deals": existing_deals}


def execute_group(group: Group, plan: dict, today: date, dry_run: bool) -> list[Outcome]:
    stage = stage_ok()
    hc = agent_cfg()["hubspot"]
    dates: list[date] = plan["dates"]
    owner_id = plan["owner_id"]
    outcomes: list[Outcome] = []
    tor_ids: dict[str, str] = {}
    for i, r in enumerate(group.rows):
        out = Outcome(student_id=r.student_id, amount=plan["amounts"][i], sessions=plan["sessions"][i])
        skipped = out.skipped_props
        # ES contact (one per ES)
        if r.es_email not in tor_ids:
            tor_existing = hs.find_contact_by_email(r.es_email, properties=TOR_PROPS)
            tor_ids[r.es_email], _ = upsert_contact(
                r.es_email, tor_props(r, tor_existing, skipped), TOR_PROPS,
                "Teacher of Record/EF/ES", dry_run)
        out.tor_id = tor_ids[r.es_email]
        # family contact
        fam_existing = hs.find_contact_by_email(r.parent_email, properties=FAMILY_PROPS)
        out.contact_id, _ = upsert_contact(
            r.parent_email, family_props(r, owner_id, fam_existing, skipped), FAMILY_PROPS,
            "Family", dry_run)
        if not dry_run and out.contact_id != "DRYRUN" and out.tor_id != "DRYRUN":
            hs.associate_contacts(out.contact_id, out.tor_id)          # Family → TOR (typeId 15)
        # deal
        my_dates = dates
        if plan["existing_deals"][r.student_id] is None and today > dates[0]:
            my_dates = C.remaining_sessions(dates, today) or dates
        out.start = my_dates[0]
        props = deal_props(r, group, my_dates, out.amount, out.sessions, owner_id, skipped)
        existing = plan["existing_deals"][r.student_id]
        if existing:
            out.deal_id = str(existing["id"])
            cur_amt = Decimal(str((existing.get("properties") or {}).get("amount") or 0))
            patch = {k: v for k, v in props.items() if k != "dealname"}
            patch["amount"] = str(out.amount)
            if not dry_run:
                hs._write("PATCH", f"/crm/v3/objects/deals/{out.deal_id}", {"properties": patch})
                if cur_amt != out.amount:
                    hs.add_deal_note(out.deal_id,
                                     f"[Agent] cohort_intake re-split: amount {cur_amt} → {out.amount} "
                                     f"({len(group.rows)} students in {props['hsa_group']} on "
                                     f"{today:%Y-%m-%d}).")
        else:
            out.deal_created = True
            if dry_run:
                out.deal_id = "DRYRUN"
            else:
                made = hs.create_deal(props.pop("dealname"), hc["pipeline"], stage, str(out.amount),
                                      contact_id=out.contact_id, owner_id=owner_id,
                                      closedate_ms=_closedate_ms(group.cohort.start), extra_props=props)
                out.deal_id = str(made.get("id"))
                if out.tor_id != "DRYRUN":
                    hs.associate_contact_to_deal(out.deal_id, out.tor_id)
        audit.append({"message_id": f"cohort:{r.idempotency_key}", "source": "cohort_intake",
                      "action_taken": "cohort_deal_created" if out.deal_created else "cohort_deal_updated",
                      "deal_id": out.deal_id, "contact_id": out.contact_id, "tor_id": out.tor_id,
                      "group": props.get("hsa_group"), "amount": str(out.amount),
                      "sessions": out.sessions, "skipped_props": skipped})
        outcomes.append(out)
    return outcomes


def deal_url(deal_id: str) -> str:
    portal = (email_cfg().get("hubspot") or {}).get("portal_id", "6312752")
    return f"https://app.hubspot.com/contacts/{portal}/record/0-3/{deal_id}"

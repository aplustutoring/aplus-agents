"""Fill-only student/parent stamp on new deals — replaces HubSpot workflow
34950163 "Contact to Deal Properties" (2020) and the student copy in 366207297.

That workflow enrolled any contact with a Pre-Lesson deal and copied the
contact's ONE student name + grade (and parent first/last, contact id) onto
EVERY associated deal, overwriting whatever was there. One parent, three
kids → three deals all named after one kid, 80 s after po_inbox had stamped
each deal correctly (Melara, PO 1443416, 2026-09-04; Elenes 2026-09-08).
Roman, 2026-09-10: "yes, and turn off the workflows."

Rules (Roman 2026-09-10):
  • FILL ONLY. A property that already has a value is never touched — the
    per-deal stamps from po_inbox and the teacher-scholarship workflows win.
  • The student's first name comes from the DEAL NAME first ("Lesly Elenes -
    Nathan" → Nathan; "Mayra Aguilar - Ezekiel Melara - Sky Mountain 1 - 26/27"
    → Ezekiel), the contact's student field second. Two students in one deal
    name ("Kash and Kingston") → ambiguous → student fields left blank, flagged.
  • Grade copies from the contact ONLY when the student IS the contact's
    student (same first name, or the deal name named none) — a sibling's grade
    is not this kid's grade.
  • Parent first/last + contact record id copy from the deal's Family contact.
Runs from deal_sync for every NEW deal in `student_stamp.pipelines`; one
decision per deal (audit student_stamp:{id}); all writes are plain PATCHes,
so a replay is harmless.
"""
from __future__ import annotations

import re

from . import audit, hubspot_client as hs
from .config import DRY_RUN, cfg

DEAL_PROPS = ["dealname", "pipeline", "student_first_name", "student_grade",
              "first_name", "last_name", "contact_record_id"]
# contact property → what it feeds. student_last_name is the LEGACY contact
# field that holds the student's FIRST name (label "Student FIRST Name").
CONTACT_PROPS = ["email", "firstname", "lastname", "a_persona", "student_first_name",
                 "student_last_name", "what_is_your_child_s_current_grade_level_"]

_DASH_SPLIT = re.compile(r"\s+-\s*|\s*-\s+")


def student_firsts_from_dealname(dealname: str) -> list[str]:
    """'Parent - Student ...' / 'Renewal - Parent - Student' → student first
    names in the second segment (siblings split on and/&/,). 'PO 123' or a
    missing segment → []."""
    parts = [p.strip() for p in _DASH_SPLIT.split(dealname or "") if p.strip()]
    if parts and parts[0].lower() in ("renewal", "renewals"):
        parts = parts[1:]
    if len(parts) < 2 or parts[1].lower().startswith("po"):
        return []
    out: list[str] = []
    for chunk in re.split(r"\s+and\s+|\s*&\s*|\s*,\s*", parts[1]):
        first = chunk.strip().split()[0] if chunk.strip() else ""
        if first and first.lower() not in (o.lower() for o in out):
            out.append(first)
    return out


def plan(deal_props: dict, contact: dict | None) -> tuple[dict, list[str]]:
    """(properties to PATCH, notes). Pure: no network. Only BLANK deal
    properties appear in the result."""
    cp = (contact or {}).get("properties") or {}
    cid = str((contact or {}).get("id") or "")
    notes: list[str] = []
    if cp and not hs.is_family_contact(cp):
        # The deal's only contact is the school's TOR/ES — never the parent.
        notes.append(f"contact {cp.get('email', '?')} is school staff, not the family; "
                     f"parent fields left blank")
        cp, cid = {}, ""
    blank = {k for k in ("student_first_name", "student_grade", "first_name",
                         "last_name", "contact_record_id")
             if not str(deal_props.get(k) or "").strip()}
    out: dict = {}
    names = student_firsts_from_dealname(deal_props.get("dealname") or "")
    c_student = (cp.get("student_first_name") or cp.get("student_last_name") or "").strip()
    c_student = c_student.split()[0] if c_student else ""
    if len(names) > 1:
        student = ""
        notes.append(f"deal name lists several students ({', '.join(names)}); "
                     f"student fields left for a human")
    elif names:
        student = names[0]
        if c_student and c_student.lower() != student.lower():
            notes.append(f"deal name says {student}, contact's student is {c_student}; "
                         f"deal name wins, grade not copied")
    else:
        student = c_student
    if student and "student_first_name" in blank:
        out["student_first_name"] = student
    grade = (cp.get("what_is_your_child_s_current_grade_level_") or "").strip()
    same_kid = bool(student) and (not c_student or student.lower() == c_student.lower())
    if grade and same_kid and "student_grade" in blank:
        out["student_grade"] = grade
    if cp.get("firstname") and "first_name" in blank:
        out["first_name"] = cp["firstname"].strip()
    if cp.get("lastname") and "last_name" in blank:
        out["last_name"] = cp["lastname"].strip()
    if cid and "contact_record_id" in blank:
        out["contact_record_id"] = cid
    return out, notes


def maybe_stamp(deal: dict, contact: dict | None) -> dict | None:
    """Fill the blank student/parent properties on one NEW deal. Returns the
    audit record, or None when off / pipeline not covered / already decided."""
    ss = cfg().get("student_stamp") or {}
    if not ss.get("enabled"):
        return None
    pid = (deal.get("properties") or {}).get("pipeline")
    if pid not in set(ss.get("pipelines") or []):
        return None
    key = f"student_stamp:{deal['id']}"
    if audit.already_processed(key):
        return None
    try:
        return _stamp(deal, contact, key)
    except Exception as e:  # noqa: BLE001 — a stamp failure must never hold the sync cursor
        print(f"  ⚠️  student_stamp failed on deal {deal.get('id')} (non-fatal): {e}")
        return None


def _stamp(deal: dict, contact: dict | None, key: str) -> dict:
    live = hs._get(f"/crm/v3/objects/deals/{deal['id']}",
                   {"properties": ",".join(DEAL_PROPS)})
    props = live.get("properties") or {}
    writes, notes = plan(props, contact)
    rec = {"message_id": key, "source": "deal_sync", "deal_id": deal["id"],
           "deal_name": props.get("dealname"), "stamped": writes, "notes": notes,
           "contact_id": (contact or {}).get("id")}
    if not contact:
        # No Family contact yet → nothing to copy; not marked done, so a FORCE
        # replay (or the backfill) picks it up once the contact is associated.
        rec.update({"message_id": f"student_stamp-skip:{deal['id']}",
                    "action_taken": "student_stamp_skipped", "reason": "no contact on deal"})
        audit.append(rec)
        return rec
    if writes and not DRY_RUN:
        hs._write("PATCH", f"/crm/v3/objects/deals/{deal['id']}", {"properties": writes})
    rec["action_taken"] = "student_stamped" if writes else "student_stamp_noop"
    audit.append(rec)
    return rec


def backfill(since_iso: str, live: bool = False) -> dict:
    """Fill blanks on every deal created since `since_iso` in the covered
    pipelines. Dry run by default; prints one line per deal that would change."""
    from .deal_sync import _deal_contact
    ss = cfg().get("student_stamp") or {}
    body = {"filterGroups": [{"filters": [
                {"propertyName": "createdate", "operator": "GTE", "value": since_iso},
                {"propertyName": "pipeline", "operator": "IN",
                 "values": list(ss.get("pipelines") or [])}]}],
            "properties": DEAL_PROPS, "limit": 100}
    deals: list = []
    while True:
        res = hs._get_search("/crm/v3/objects/deals/search", body)
        deals.extend(res.get("results", []))
        after = ((res.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
        body["after"] = after
    summary = {"scanned": len(deals), "changed": 0, "noop": 0, "no_contact": 0, "flagged": []}
    for d in deals:
        p = d.get("properties") or {}
        if all(str(p.get(k) or "").strip() for k in
               ("student_first_name", "student_grade", "first_name", "last_name")):
            summary["noop"] += 1
            continue
        contact = _deal_contact(d["id"], p.get("dealname", ""))
        if not contact:
            summary["no_contact"] += 1
            print(f"  · {d['id']} {p.get('dealname')}: no contact")
            continue
        writes, notes = plan(p, contact)
        for n in notes:
            summary["flagged"].append((d["id"], p.get("dealname"), n))
        if not writes:
            summary["noop"] += 1
            continue
        summary["changed"] += 1
        print(f"  {'✍️' if live else '·'} {d['id']} {p.get('dealname')}: {writes}"
              + (f"  ⚠️ {'; '.join(notes)}" if notes else ""))
        if live:
            hs._write("PATCH", f"/crm/v3/objects/deals/{d['id']}", {"properties": writes})
    return summary


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser(description="fill-only student/parent stamp backfill")
    ap.add_argument("--since", default="2026-08-01T00:00:00Z")
    ap.add_argument("--live", action="store_true", help="write (default: dry run)")
    a = ap.parse_args()
    s = backfill(a.since, live=a.live)
    print(json.dumps({k: v for k, v in s.items() if k != "flagged"}))
    for f in s["flagged"]:
        print("  ⚠️", *f)

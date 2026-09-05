#!/usr/bin/env python3
"""Roster for a teacher who replied "send it" (teacher outreach 26/27).

Roman 2026-09-04: Sequence 1 promises "want a quick list of who tutored with
us? say send it." The Accountable rule says the mechanism exists before the
promise ships; this is the mechanism. Deal-based, read-only.

  python3 scripts/teacher_roster.py christine.gurney@ileadexploration.org

Prints a paste-ready roster: every distinct student named on a charter deal
where this teacher is teacher_of_record_email since SINCE, with the parent
(deal name leads with the parent), school, most recent service month, and the
assigned tutor FIRST name (customer-facing rule: no tutor last names).
"""

import argparse
import collections
import os
import re
import sys
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent.parent
    load_dotenv(_here / ".env", override=False)
    if "/.claude/worktrees/" in str(_here):
        load_dotenv(Path(str(_here).split("/.claude/worktrees/")[0]) / ".env", override=False)
except ImportError:
    pass

HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}
CHARTER_PIPELINES = ["907748", "72281989", "88841552", "5119061", "1066195"]
SINCE = "2025-08-01"
NOT_STUDENT = {"a", "summer", "level", "ilead", "charter"}


def hs(method, path, **kw):
    for _ in range(6):
        r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)) or 10)
            continue
        r.raise_for_status()
        return r.json() if r.text else {}
    r.raise_for_status()


def deals_for_teacher(email, since):
    since_ms = int(time.mktime(time.strptime(since, "%Y-%m-%d")) * 1000)
    out, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "IN", "values": CHARTER_PIPELINES},
            {"propertyName": "createdate", "operator": "GTE", "value": str(since_ms)},
            {"propertyName": "teacher_of_record_email", "operator": "EQ", "value": email},
        ]}], "properties": ["dealname", "student_first_name", "student_last_name_if_diff_from_parent",
                            "student_grade", "student_school", "assigned_tutor", "createdate", "amount",
                            "hs_is_closed_won", "parent_email"],
            "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}], "limit": 100}
        if after:
            body["after"] = after
        j = hs("POST", "/crm/v3/objects/deals/search", json=body)
        out += [x.get("properties", {}) for x in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return out


def parent_and_student(p):
    """'Parent - Student - School N - YY/YY' → (parent, student)."""
    parts = [s.strip() for s in (p.get("dealname") or "").split(" - ")]
    parent = parts[0] if parts else ""
    student = (p.get("student_first_name") or "").strip() or (parts[1].split(" ")[0] if len(parts) > 1 else "")
    if student.lower() in NOT_STUDENT or not re.match(r"^[A-Za-zÀ-ÿ'\-]+$", student):
        student = ""
    return parent, student


def tutor_first(raw):
    raw = (raw or "").strip()
    return raw.split(" ")[0] if raw else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("teacher_email")
    ap.add_argument("--since", default=SINCE)
    args = ap.parse_args()
    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    email = args.teacher_email.strip().lower()
    deals = deals_for_teacher(email, args.since)
    if not deals:
        print(f"No charter deals since {args.since} name {email} as teacher of record.")
        return
    rows = {}
    # Older deal names carry a prefix instead of the parent ("A - Ember - iLEAD ...",
    # "Summer 2025 - ..."). Those rows merge into the student's real-parent row when
    # one exists, so a family is never listed twice.
    placeholder = {"a", "summer", "summer 2025", "summer 2026", "charter", "level up", ""}
    for p in deals:                      # newest first (sorted DESC)
        parent, student = parent_and_student(p)
        if parent.lower() in placeholder:
            parent = ""
        key = (parent.lower(), student.lower())
        if not parent:
            real = next((k for k in rows if k[1] == student.lower() and k[0]), None)
            if real:
                key = real
        r = rows.setdefault(key, {"parent": parent, "student": student, "school": p.get("student_school") or "",
                                  "tutor": tutor_first(p.get("assigned_tutor")), "last": (p.get("createdate") or "")[:7],
                                  "pos": 0, "dollars": 0.0})
        r["pos"] += 1
        r["dollars"] += float(p.get("amount") or 0)
        if not r["tutor"]:
            r["tutor"] = tutor_first(p.get("assigned_tutor"))
    # second pass: a prefix-only row whose student later appeared with a real parent
    for key in [k for k in rows if not k[0]]:
        real = next((k for k in rows if k[1] == key[1] and k[0]), None)
        if real:
            rows[real]["pos"] += rows[key]["pos"]
            rows[real]["dollars"] += rows[key]["dollars"]
            del rows[key]
    fams = sorted(rows.values(), key=lambda r: (r["parent"].lower(), r["student"].lower()))
    print(f"Roster for {email} (charter deals since {args.since}: {len(deals)}, families/students: {len(fams)})\n")
    print("Paste-ready:\n")
    for r in fams:
        who = f"{r['student']} ({r['parent']})" if r["student"] else r["parent"]
        tutor = f", tutor {r['tutor']}" if r["tutor"] else ""
        print(f"  • {who}{tutor}, last PO {r['last']}")
    print(f"\n(internal) total ${sum(r['dollars'] for r in fams):,.0f} across {sum(r['pos'] for r in fams)} POs")


if __name__ == "__main__":
    main()

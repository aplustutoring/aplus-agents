#!/usr/bin/env python3
"""
A+ Tutoring — Repeat Missed Lessons (2-Week Report)
Finds students with 2+ no-shows in a rolling 2-week Sun–Sat window
and populates a Monday.com board with scheduler assignments.

Usage:
  python3 aplus_missed_lessons_sync.py

Requirements:
  - .env file in the same directory with:
      TEACHWORKS_API_KEY=<key>
      MONDAY_API_KEY=<key>
  - pip install requests python-dotenv

Pulls from:
  - Teachworks API (lessons, students, families)

Writes to:
  - Repeat Missed Lessons — 2-Week Report (18406630845)

Notes:
  - Window is 2 complete Sun–Sat weeks (14 days).
  - No-show statuses: no_show, missed, no show.
  - Threshold: 2+ no-shows in the window.
  - Scheduler assignment: Janelle (A–L), Yolanda (M–Z).
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# LOAD SECRETS FROM .env FILE
# ─────────────────────────────────────────────
load_dotenv()

TEACHWORKS_API_KEY = os.getenv("TEACHWORKS_API_KEY")
MONDAY_API_KEY     = os.getenv("MONDAY_API_KEY")

# ─────────────────────────────────────────────
# MONDAY.COM BOARD & COLUMN IDs
# ─────────────────────────────────────────────
BOARD_ID = 18406630845

COLS = {
    "people":        "multiple_person_mm1zc1r9",
    "no_show_count": "numeric_mm1zqjan",
    "no_show_dates": "text_mm1z1gg0",
    "phone":         "phone_mm1zdbm1",
    "email":         "email_mm1zbtct",
    "contacted":     "color_mm1z399f",
    "notes":         "text_mm1zaat5",
}

# Monday.com user IDs (for the People column)
MONDAY_USER_IDS = {
    "kath":    "48072738",
    "janelle": "76279527",
    "yolanda": "97968060",
    "mandy":   "76279529",
}

# ─────────────────────────────────────────────
# SCHEDULER ASSIGNMENT
# ─────────────────────────────────────────────
JANELLE_RANGE = tuple("abcdefghijkl")   # A–L
YOLANDA_RANGE = tuple("mnopqrstuvwxyz")  # M–Z

NO_SHOW_STATUSES = {"no_show", "missed", "no show"}

# ─────────────────────────────────────────────
# DATE HELPERS
# ─────────────────────────────────────────────
def get_two_week_range():
    """Returns (sunday_start, saturday_end) of the most recently completed
    2-week window (two full Sun–Sat weeks)."""
    today = datetime.now().date()
    # Find the most recent Saturday (end of last complete week)
    days_since_saturday = (today.weekday() + 2) % 7  # Sat=0 offset
    if days_since_saturday == 0:
        days_since_saturday = 7  # If today is Saturday, use *last* Saturday
    last_saturday = today - timedelta(days=days_since_saturday)
    # Go back one more full week for the 2-week window
    two_week_sunday = last_saturday - timedelta(days=13)  # 14 days inclusive
    return two_week_sunday, last_saturday

# ─────────────────────────────────────────────
# TEACHWORKS API
# ─────────────────────────────────────────────
TW_BASE = "https://api.teachworks.com/v1"

def tw_get(endpoint, params=None):
    headers = {
        "Authorization": f"Token token={TEACHWORKS_API_KEY}",
        "Content-Type": "application/json",
    }
    params = params or {}
    results = []
    params["per_page"] = 80
    params["page"] = 1
    while True:
        for attempt in range(3):
            r = requests.get(f"{TW_BASE}/{endpoint}", headers=headers, params=params, timeout=30)
            if r.status_code == 403:
                wait = 5 * (attempt + 1)
                print(f"      \u23f3 Teachworks rate limit, retrying in {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        else:
            r.raise_for_status()
        data = r.json()
        if not data:
            break
        results.extend(data)
        if len(data) < 80:
            break
        params["page"] += 1
    return results

# ─────────────────────────────────────────────
# FETCH REPEAT NO-SHOWS (2-WEEK WINDOW)
# ─────────────────────────────────────────────
def fetch_repeat_missed(start_date, end_date, min_no_shows=2):
    """Find students with 2+ no-shows in the 2-week window.
    Returns list of dicts: {student_id, name, count, dates, scheduler}
    sorted by count descending."""
    print(f"    Pulling lessons ({start_date} \u2013 {end_date})...")
    lessons = tw_get("lessons", {
        "from_date[gte]": start_date.isoformat(),
        "from_date[lte]": end_date.isoformat(),
    })
    print(f"    Lessons in 2-week window: {len(lessons)}")

    no_show_data = {}  # student_id -> {name, count, dates, scheduler}

    def record_no_show(sid, name, lesson_date):
        last_name = name.split(",")[0].strip().lower()
        initial = last_name[0] if last_name else ""
        if initial in JANELLE_RANGE:
            scheduler = "janelle"
        elif initial in YOLANDA_RANGE:
            scheduler = "yolanda"
        else:
            scheduler = "unassigned"

        if sid not in no_show_data:
            no_show_data[sid] = {"name": name, "count": 0, "dates": [], "scheduler": scheduler}
        no_show_data[sid]["count"] += 1
        if lesson_date:
            no_show_data[sid]["dates"].append(lesson_date)

    for lesson in lessons:
        lesson_date = (lesson.get("from_date") or "")[:10]
        participants = lesson.get("participants") or []

        if participants:
            for p in participants:
                if (p.get("status") or "").lower() in NO_SHOW_STATUSES:
                    sid = p.get("student_id")
                    if sid:
                        record_no_show(sid, (p.get("student_name") or "Unknown").strip(), lesson_date)
        else:
            if (lesson.get("status") or "").lower() in NO_SHOW_STATUSES:
                lesson_id = str(lesson.get("id") or lesson.get("name", "unknown"))
                record_no_show(lesson_id, lesson.get("name", "Unknown"), lesson_date)

    flagged = [
        {"student_id": sid, **data}
        for sid, data in no_show_data.items()
        if data["count"] >= min_no_shows
    ]
    flagged.sort(key=lambda x: (-x["count"], x["name"]))

    print(f"    Students with {min_no_shows}+ no-shows: {len(flagged)}")
    return flagged

# ─────────────────────────────────────────────
# FETCH STUDENT CONTACT INFO
# ─────────────────────────────────────────────
def fetch_student_contact_info(student_ids):
    """Pull contact info (email, phone) for flagged students.
    Maps student -> family to get family-level contact details."""
    if not student_ids:
        return {}

    print(f"    Pulling active students for contact info...")
    students = tw_get("students", {"status": "Active"})
    student_map = {}
    customer_ids = set()
    for s in students:
        sid = s["id"]
        if sid in student_ids:
            student_map[sid] = {
                "email": s.get("email") or "",
                "phone": s.get("mobile_phone") or s.get("home_phone") or "",
                "customer_id": s.get("customer_id"),
            }
            if s.get("customer_id"):
                customer_ids.add(s["customer_id"])

    # Pull family-level contact info as fallback
    if customer_ids:
        print(f"    Pulling families for fallback contact info...")
        families = tw_get("customers", {"status": "Active", "customer_type": "family"})
        family_map = {f["id"]: f for f in families}

        for sid, info in student_map.items():
            cid = info.get("customer_id")
            if cid and cid in family_map:
                fam = family_map[cid]
                if not info["email"]:
                    info["email"] = fam.get("email") or ""
                if not info["phone"]:
                    info["phone"] = fam.get("mobile_phone") or fam.get("home_phone") or ""

    print(f"    Contact info resolved for {len(student_map)} students")
    return student_map

# ─────────────────────────────────────────────
# MONDAY.COM API
# ─────────────────────────────────────────────
MONDAY_URL = "https://api.monday.com/v2"

def monday_query(query, variables=None):
    headers = {
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables or {}}
    for attempt in range(3):
        try:
            r = requests.post(MONDAY_URL, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            if attempt < 2:
                wait = 5 * (attempt + 1)
                print(f"      \u23f3 Monday.com timeout, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise

def create_group(board_id, group_name):
    q = """
    mutation ($boardId: ID!, $groupName: String!) {
      create_group(board_id: $boardId, group_name: $groupName) { id }
    }"""
    data = monday_query(q, {"boardId": str(board_id), "groupName": group_name})
    return data["data"]["create_group"]["id"]

def create_item(board_id, group_id, item_name, column_values):
    q = """
    mutation ($boardId: ID!, $groupId: String!, $name: String!, $colVals: JSON!) {
      create_item(board_id: $boardId, group_id: $groupId, item_name: $name,
                  column_values: $colVals) { id }
    }"""
    data = monday_query(q, {
        "boardId": str(board_id),
        "groupId": group_id,
        "name": item_name,
        "colVals": json.dumps(column_values),
    })
    if data.get("errors"):
        print(f"    Monday.com error: {data['errors']}")
        return None
    return data["data"]["create_item"]["id"]

# ─────────────────────────────────────────────
# WRITE: REPEAT MISSED LESSONS BOARD
# ─────────────────────────────────────────────
def write_missed_lessons_report(flagged_students, contact_info, start_date, end_date):
    board_id = BOARD_ID
    week_label = f"{start_date.strftime('%-m/%-d')} \u2013 {end_date.strftime('%-m/%-d')}"
    print(f"  Creating group: {week_label}")
    group_id = create_group(board_id, week_label)

    for student in flagged_students:
        # Build column values
        col_vals = {
            COLS["no_show_count"]: student["count"],
            COLS["no_show_dates"]: ", ".join(sorted(set(student["dates"]))),
        }

        # Assign scheduler
        scheduler_id = MONDAY_USER_IDS.get(student["scheduler"])
        if scheduler_id:
            col_vals[COLS["people"]] = {
                "personsAndTeams": [{"id": int(scheduler_id), "kind": "person"}]
            }

        # Contact info
        sid = student["student_id"]
        info = contact_info.get(sid, {})
        if info.get("email"):
            col_vals[COLS["email"]] = {"email": info["email"], "text": info["email"]}
        if info.get("phone"):
            digits = re.sub(r"\D", "", info["phone"])
            if digits and not digits.startswith("1"):
                digits = "1" + digits
            if digits:
                col_vals[COLS["phone"]] = {"phone": "+" + digits, "countryShortName": "US"}

        # Display name: "Last, First" -> "First Last"
        raw_name = student["name"]
        if "," in raw_name:
            parts = raw_name.split(",", 1)
            display_name = f"{parts[1].strip()} {parts[0].strip()}"
        else:
            display_name = raw_name

        print(f"    Adding: {display_name} ({student['count']} no-shows \u2014 {student['scheduler']})")
        create_item(board_id, group_id, display_name, col_vals)

    print(f"  \u2705 Repeat Missed Lessons updated ({len(flagged_students)} students).")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    # CHECK_ONLY: CI smoke test \u2014 confirm required secrets are wired, then exit
    # before any Teachworks read or Monday write. (No DRY_RUN mode here, so this
    # is how the migrated GitHub Actions job self-tests.)
    if os.getenv("CHECK_ONLY", "").lower() == "true":
        missing = [k for k in ("TEACHWORKS_API_KEY", "MONDAY_API_KEY") if not os.getenv(k)]
        if missing:
            print(f"CHECK FAILED: missing env: {', '.join(missing)}")
            raise SystemExit(1)
        print("CHECK OK: TEACHWORKS_API_KEY / MONDAY_API_KEY present; skipping all reads/writes.")
        raise SystemExit(0)

    print(f"\n{'='*60}")
    print(f"  A+ Tutoring \u2014 Repeat Missed Lessons (2-Week Report)")
    print(f"  {datetime.now().strftime('%A %B %d, %Y %I:%M %p')}")
    print(f"{'='*60}\n")

    # 1. Calculate 2-week range
    start_date, end_date = get_two_week_range()
    print(f"\U0001f4c5 2-Week Window: {start_date} \u2192 {end_date}\n")

    # 2. Pull no-show data
    print("\U0001f4e5 Pulling Teachworks lesson data...")
    flagged = fetch_repeat_missed(start_date, end_date)

    if not flagged:
        print("\n  \u2705 No students with 2+ no-shows in the 2-week window.")
        print(f"\n{'='*60}")
        print(f"  \u2705 Complete \u2014 nothing to report.")
        print(f"{'='*60}\n")
        return

    # Print summary
    print(f"\n   \u26a0\ufe0f  {len(flagged)} student(s) with 2+ no-shows:\n")
    janelle_list = [s for s in flagged if s["scheduler"] == "janelle"]
    yolanda_list = [s for s in flagged if s["scheduler"] == "yolanda"]
    other_list   = [s for s in flagged if s["scheduler"] == "unassigned"]

    for label, group in [("Janelle (A\u2013L)", janelle_list),
                         ("Yolanda (M\u2013Z)", yolanda_list),
                         ("Unassigned", other_list)]:
        if group:
            print(f"   {label}:")
            for s in group:
                dates_str = ", ".join(sorted(set(s["dates"])))
                print(f"     {s['name']:35} {s['count']} no-shows  [{dates_str}]")
            print()

    # 3. Fetch contact info for flagged students
    print("\U0001f4e5 Pulling student contact info...")
    student_ids = {s["student_id"] for s in flagged if isinstance(s["student_id"], int)}
    contact_info = fetch_student_contact_info(student_ids)

    # 4. Write to Monday.com
    print("\n\U0001f4e4 Writing to Monday.com...")
    write_missed_lessons_report(flagged, contact_info, start_date, end_date)

    print(f"\n{'='*60}")
    print(f"  \u2705 Sync complete!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()

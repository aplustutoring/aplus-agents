#!/usr/bin/env python3
"""
A+ Tutoring — Weekly Data Sync Script
Runs every Monday at 9:00 AM via cron job on Roman's Mac.

Usage:
  python3 aplus_weekly_sync.py

Requirements:
  - .env file in the same directory with:
      TEACHWORKS_API_KEY=<key>
      HUBSPOT_API_KEY=<key>
      MONDAY_API_KEY=<key>
  - pip install requests python-dotenv

Pulls from:
  - Teachworks API (lessons, packages, new students)
  - HubSpot API (72-hr turnaround, charter pipeline deals)

Writes to:
  - Weekly Lesson Report - Detail (18401289623)
  - L10 Scorecard (18402267902)
  - First Lesson Report - Weekly & Monthly (18402249443)

Notes:
  - Week range is Sun–Sat to match Teachworks reporting.
  - Hours are counted as "student lesson hours" — each participant in a
    group lesson is counted individually using their per-student status
    (e.g. one student Attended, another Missed in the same lesson).
    This matches the Teachworks "Student Lesson Hours by Status" report.
  - Source of truth for validation: Teachworks > Reports >
    Student Lesson Hours by Status (same Sun–Sat date range).
"""

import os
import re
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# LOAD SECRETS FROM .env FILE
# ─────────────────────────────────────────────
load_dotenv()

TEACHWORKS_API_KEY   = os.getenv("TEACHWORKS_API_KEY")
HUBSPOT_API_KEY      = os.getenv("HUBSPOT_API_KEY")
MONDAY_API_KEY       = os.getenv("MONDAY_API_KEY")

# ─────────────────────────────────────────────
# MONDAY.COM BOARD & ITEM IDs
# ─────────────────────────────────────────────
BOARDS = {
    "weekly_lesson_report":    18401289623,
    "l10_scorecard":           18402267902,
    "first_lesson_report":     18402249443,
    "inactive_student_outreach": 18404113639,
}

# Inactive Student Outreach column IDs
ISO_COLS = {
    "last_lesson_date": "date_mm1gyg42",
    "days_inactive":    "numeric_mm1gby89",
    "people":           "multiple_person_mm1g7983",
    "phone":            "phone_mm1gzxgk",
    "email":            "email_mm1gre3q",
}

# L10 Scorecard item IDs
SCORECARD_ITEMS = {
    "hours_attended":        11483245331,   # Emily — Company Student Lesson Hours Attended
    "package_units_sold":    11483189029,   # Emily — Company Package Units Sold
    "cancellation_rate":     11408675886,   # Mandy — Company Cancellation Rate %
    "new_students":          11487301255,   # Emily — New Students First Lesson Completed
    "package_hours_sold":    11487307948,   # Roman — Annual Package Hours Sold (running total)
    "post_lesson_72hr":      11521873481,   # Mandy — 72-Hr Post-Lesson Turnaround %
    "charter_deals":         11521760217,   # Danielle — Active Proposals snapshot (Proposal Out)
    "csm_new_deals":         11487307910,   # Danielle — New Deals Created This Week
    "csm_outreach_initiated":12005709448,   # Danielle — Outreach Initiated This Week
    "csm_meetings_scheduled":11760102894,   # Danielle — Meetings Scheduled This Week
    "csm_meetings_held":     11760067895,   # Danielle — Meetings Held This Week
    "nps_client":            12017535419,   # Paola — NPS Client Satisfaction (avg of Family NPS responses)
    "nps_tutor":             12017557543,   # Mandy — Tutor NPS (avg of Tutor Satisfaction responses)
    "nps_support_bot":       12017578482,   # Roman — Support BOT NPS (avg of Support Bot responses)
}

# Auto-status rules for L10 scorecard rows.
# weekly_threshold: status = "On Track" if value >= goal, else "Off Track".
#                   The goal is read live from the board's `target` column
#                   (SCORECARD_COLS["target"]); "threshold" below is only a
#                   fallback used when that cell is empty or unparseable.
# vs_prior_week:    status = "On Track" if value >= prior week's value, else "Off Track"
# Rows not listed here keep manual status (no auto-update).
SCORECARD_STATUS_RULES = {
    "csm_new_deals":          {"type": "weekly_threshold", "threshold": 5},
    "csm_outreach_initiated": {"type": "weekly_threshold", "threshold": 5},
    "csm_meetings_scheduled": {"type": "weekly_threshold", "threshold": 2},
    "csm_meetings_held":      {"type": "weekly_threshold", "threshold": 1},
    "charter_deals":          {"type": "weekly_threshold", "threshold": 1},
    "nps_client":             {"type": "weekly_threshold", "threshold": 9.0, "no_data_label": "No Data"},
    "nps_tutor":              {"type": "weekly_threshold", "threshold": 9.0, "no_data_label": "No Data"},
    "nps_support_bot":        {"type": "weekly_threshold", "threshold": 9.0, "no_data_label": "No Data"},
}

STATUS_COLUMN_ID = "color_mm1ctjhx"

# L10 Scorecard column IDs
SCORECARD_COLS = {
    "target":    "text_mm13s9jw",
}

# Weekly Lesson Report column IDs
WLR_COLS = {
    "total_hrs":      "numeric_mm0vj2eh",
    "attended_hrs":   "numeric_mm0vmnzh",
    "cancelled_hrs":  "numeric_mm0vstqb",
    "no_show_hrs":    "numeric_mm0v2nzt",
    "unmarked_hrs":   "numeric_mm0vnkfa",
    "cancel_rate":    "numeric_mm0vef0g",
    "unmarked_rate":  "numeric_mm0vrgzn",
    "post_lesson_pct":"numeric_mm13kccf",
    "people":         "multiple_person_mm19mjac",
    "long_text":      "long_text_mm1gw0x4",
}

# First Lesson Report column IDs
FLR_COLS = {
    "week_ending":    "date_mm12831z",
    "student_count":  "numeric_mm12rc70",
}

# Monday.com user IDs (for the People column in Weekly Lesson Report)
MONDAY_USER_IDS = {
    "kath":    "48072738",
    "janelle": "76279527",
    "yolanda": "97968060",
    "mandy":   "76279529",
}

# HubSpot pipeline ID for Charter Schools Marketing
# Pipeline IDs
PIPELINES_72HR = {
    "default":   {"name": "Gold Tutoring",    "pre": ["appointmentscheduled", "closedlost"],
                  "post_and_beyond": ["presentationscheduled", "15961683", "980957"]},
    "19120821":  {"name": "Free Trial",       "pre": ["47072313", "47314737"],
                  "post_and_beyond": ["47314738", "47314739"]},
    "3067397":   {"name": "In-Person",        "pre": ["3067398", "3067399"],
                  "post_and_beyond": ["3067400", "16859552", "3067402"]},
    "907748":    {"name": "Charter Trad",     "pre": ["996346455", "907749"],
                  "post_and_beyond": ["907774", "907775", "13267787"]},
    "72281989":  {"name": "Charter Terri",    "pre": ["140397124"],
                  "post_and_beyond": ["140397125", "140397126", "140444790", "968309572"]},
    "88841552":  {"name": "Charter Amy",      "pre": ["164922249"],
                  "post_and_beyond": ["164922250", "164922255", "193388062", "203002711"]},
    "5119061":   {"name": "IEM Inc",          "pre": ["5119062"],
                  "post_and_beyond": ["5119063", "5119064", "5119065", "5119066"]},
}


# ─────────────────────────────────────────────
# DATE HELPERS
# ─────────────────────────────────────────────
def get_last_week_range():
    """Returns (sunday, saturday) of the most recently completed week.
    Teachworks reports use Sun–Sat weeks."""
    today = datetime.now().date()
    # today.weekday(): Mon=0 … Sun=6
    # Find the most recent Saturday (end of last complete week)
    days_since_saturday = (today.weekday() + 2) % 7  # Sat=0 offset
    if days_since_saturday == 0:
        days_since_saturday = 7  # If today is Saturday, use *last* Saturday
    last_saturday = today - timedelta(days=days_since_saturday)
    last_sunday = last_saturday - timedelta(days=6)
    return last_sunday, last_saturday

def get_current_fy_start():
    """FY runs July 1 – June 30. Returns start of current FY."""
    today = datetime.now().date()
    if today.month >= 7:
        return datetime(today.year, 7, 1).date()
    else:
        return datetime(today.year - 1, 7, 1).date()

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
    params["per_page"] = 80  # Teachworks API max is 80 per page
    params["page"] = 1
    while True:
        for attempt in range(3):
            r = requests.get(f"{TW_BASE}/{endpoint}", headers=headers, params=params, timeout=30)
            if r.status_code == 403:
                wait = 5 * (attempt + 1)
                print(f"      ⏳ Teachworks rate limit, retrying in {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        else:
            r.raise_for_status()  # raise on final failure
        data = r.json()
        if not data:
            break
        results.extend(data)
        if len(data) < 80:
            break
        params["page"] += 1
    return results

def fetch_lessons_for_week(start_date, end_date):
    """Pull all lessons for the week."""
    return tw_get("lessons", {
        "from_date[gte]": start_date.isoformat(),
        "from_date[lte]": end_date.isoformat(),
    })

def fetch_package_hours_fy(end_date):
    """Pull total package units sold for the fiscal year (July 1 through end_date).
    FY runs July 1 – June 30. Sums the 'quantity' field from packages on each invoice."""
    fy_start = get_current_fy_start()
    invoices = tw_get("invoices", {
        "date[gte]": fy_start.isoformat(),
        "date[lte]": end_date.isoformat(),
    })
    total = 0
    for inv in invoices:
        if inv.get("status") == "Void":
            continue
        for pkg in inv.get("packages", []):
            total += float(pkg.get("quantity") or 0)
    print(f"    Package hours FY ({fy_start.strftime('%-m/%-d/%y')} – {end_date.strftime('%-m/%-d/%y')}): {total} from {len(invoices)} invoices")
    return total

def fetch_package_hours_week(start_date, end_date):
    """Pull package units sold during the reporting week.
    Sums the 'quantity' field from the 'packages' array on each invoice."""
    invoices = tw_get("invoices", {
        "date[gte]": start_date.isoformat(),
        "date[lte]": end_date.isoformat(),
    })
    total = 0
    for inv in invoices:
        if inv.get("status") == "Void":
            continue
        for pkg in inv.get("packages", []):
            total += float(pkg.get("quantity") or 0)
    print(f"    Package units this week: {total} from {len(invoices)} invoices")
    return total

def fetch_new_students_week(start_date, end_date, week_lessons=None):
    """Count students whose first-ever lesson was this week.
    Uses a two-pass approach:
      1. Fast 180-day lookback eliminates most returning students.
      2. For remaining candidates, checks full history via per-student
         API calls to match Teachworks' First Lesson Report exactly."""
    if week_lessons is None:
        week_lessons = fetch_lessons_for_week(start_date, end_date)

    # All student IDs seen this week (any status — first lesson report isn't status-filtered)
    week_student_ids = {}
    for l in week_lessons:
        for p in (l.get("participants") or []):
            sid = p.get("student_id")
            if sid:
                week_student_ids[sid] = p.get("student_name", "")

    # Pass 1: Pull prior 180 days of lessons to quickly eliminate most returning students
    lookback_start = start_date - timedelta(days=180)
    prior_lessons = tw_get("lessons", {
        "from_date[gte]": lookback_start.isoformat(),
        "to_date[lte]": (start_date - timedelta(days=1)).isoformat(),
    })
    prior_students = set()
    for l in prior_lessons:
        for p in (l.get("participants") or []):
            sid = p.get("student_id")
            if sid:
                prior_students.add(sid)

    candidates = {sid: name for sid, name in week_student_ids.items()
                  if sid not in prior_students}

    # Pass 2: For each candidate, verify they have no lessons before the 180-day window
    new_students = {}
    if candidates:
        pre_lookback = (lookback_start - timedelta(days=1)).isoformat()
        for sid, name in candidates.items():
            older_lessons = tw_get("lessons", {
                "to_date[lte]": pre_lookback,
                "student_id": sid,
                "per_page": 1,
            })
            if not older_lessons:
                new_students[sid] = name
            else:
                print(f"      ↳ {name} is a returning student (has lessons before {lookback_start})")

    print(f"    First lesson students: {len(new_students)} (checked {len(week_student_ids)} this week, {len(candidates)} candidates verified against full history)")
    for sid, name in sorted(new_students.items(), key=lambda x: x[1]):
        print(f"      {name}")
    return len(new_students)

# ─────────────────────────────────────────────
# LESSON DATA PROCESSING
# ─────────────────────────────────────────────
JANELLE_RANGE = tuple("abcdefghijkl")  # A–L
YOLANDA_RANGE = tuple("mnopqrstuvwxyz")  # M–Z

def get_last_name_initial(lesson):
    """Extract first letter of student last name from participants array.
    Teachworks returns student_name as 'Last, First' format."""
    participants = lesson.get("participants") or []
    if participants:
        student_name = participants[0].get("student_name") or ""
        # Format is "Last, First" — take everything before the comma
        last = student_name.split(",")[0].strip().lower()
        return last[0] if last else ""
    # Fallback: try name field directly
    name = lesson.get("name") or ""
    parts = name.split()
    return parts[-1][0].lower() if parts else ""

def classify_lesson(lesson):
    """Returns 'janelle', 'yolanda', or None based on student last name."""
    initial = get_last_name_initial(lesson)
    if initial in JANELLE_RANGE:
        return "janelle"
    elif initial in YOLANDA_RANGE:
        return "yolanda"
    return None

def scheduler_for_initial(initial):
    """Map a last-name initial to the owning scheduler (A–L Janelle, M–Z Yolanda)."""
    if initial in JANELLE_RANGE:
        return "janelle"
    if initial in YOLANDA_RANGE:
        return "yolanda"
    return "unassigned"

def scheduler_from_deal_name(dealname):
    """Scheduler for a HubSpot deal, keyed off the PARENT's last name.

    Deal names follow 'Parent First Last - Student ...', so the parent's last
    name is the last token before the ' - ' student separator (falling back to
    the last token of the whole name when there's no separator)."""
    parent = (dealname or "").split(" - ")[0].strip()
    tokens = parent.split()
    initial = tokens[-1][0].lower() if tokens and tokens[-1] else ""
    return scheduler_for_initial(initial)

def get_lesson_hours(lesson):
    """Return duration in hours from duration_minutes."""
    minutes = float(lesson.get("duration_minutes") or 0)
    return round(minutes / 60, 4)

def get_lesson_status(lesson):
    """Normalize lesson status to lowercase."""
    return (lesson.get("status") or "").lower()

def process_lessons(lessons):
    """
    Returns a dict with metrics split by:
      kath (all scheduled), janelle (A-L), yolanda (M-Z), company (total)
    """
    result = {
        "kath":    {"scheduled": 0},
        "janelle": {"attended": 0, "cancelled": 0, "no_show": 0, "unmarked": 0, "total": 0},
        "yolanda": {"attended": 0, "cancelled": 0, "no_show": 0, "unmarked": 0, "total": 0},
        "company": {"attended": 0, "cancelled": 0, "no_show": 0, "unmarked": 0, "total": 0},
    }

    # Track unmarked lessons by tutor: {tutor_name: {"hours": X, "lessons": [student_name, ...]}}
    unmarked_by_tutor = {}

    def add_status_hours(bucket, status, hrs):
        """Add hours to the appropriate status bucket."""
        bucket["total"] += hrs
        if status in ("attended", "completed"):
            bucket["attended"] += hrs
        elif status in ("cancelled", "canceled"):
            bucket["cancelled"] += hrs
        elif status in ("no_show", "missed", "no show"):
            bucket["no_show"] += hrs
        else:
            bucket["unmarked"] += hrs

    def is_unmarked(status):
        return status not in ("attended", "completed", "cancelled", "canceled",
                              "no_show", "missed", "no show")

    for lesson in lessons:
        minutes = float(lesson.get("duration_minutes") or 0)
        per_student_hrs = round(minutes / 60, 4)
        participants = lesson.get("participants") or []
        tutor_name = (lesson.get("employee_name") or "Unknown Tutor").strip()

        if participants:
            # Count each participant individually with their own status
            for p in participants:
                p_status = (p.get("status") or "").lower()
                result["kath"]["scheduled"] += per_student_hrs
                add_status_hours(result["company"], p_status, per_student_hrs)

                # Track unmarked by tutor
                if is_unmarked(p_status):
                    if tutor_name not in unmarked_by_tutor:
                        unmarked_by_tutor[tutor_name] = {"hours": 0, "students": []}
                    unmarked_by_tutor[tutor_name]["hours"] += per_student_hrs
                    student_name = (p.get("student_name") or "Unknown").strip()
                    unmarked_by_tutor[tutor_name]["students"].append(student_name)

                # Per-owner split by student last name
                name = (p.get("student_name") or "").split(",")[0].strip().lower()
                initial = name[0] if name else ""
                if initial in JANELLE_RANGE:
                    add_status_hours(result["janelle"], p_status, per_student_hrs)
                elif initial in YOLANDA_RANGE:
                    add_status_hours(result["yolanda"], p_status, per_student_hrs)
        else:
            # No participants array — use lesson-level data
            hrs = per_student_hrs
            status = get_lesson_status(lesson)
            result["kath"]["scheduled"] += hrs
            add_status_hours(result["company"], status, hrs)

            if is_unmarked(status):
                if tutor_name not in unmarked_by_tutor:
                    unmarked_by_tutor[tutor_name] = {"hours": 0, "students": []}
                unmarked_by_tutor[tutor_name]["hours"] += hrs
                unmarked_by_tutor[tutor_name]["students"].append(lesson.get("name", "Unknown"))

            owner = classify_lesson(lesson)
            if owner in ("janelle", "yolanda"):
                add_status_hours(result[owner], status, hrs)

    # Calculate rates
    for group in ("janelle", "yolanda", "company"):
        total = result[group]["total"]
        attended = result[group]["attended"]
        cancelled = result[group]["cancelled"]
        unmarked = result[group]["unmarked"]
        result[group]["cancel_rate"] = round((cancelled / total * 100), 1) if total else 0
        result[group]["unmarked_rate"] = round((unmarked / total * 100), 1) if total else 0

    # Build unmarked tutor analysis for Kath
    result["unmarked_by_tutor"] = unmarked_by_tutor

    return result

# ─────────────────────────────────────────────
# INACTIVE FAMILY DETECTION
# ─────────────────────────────────────────────
def fetch_inactive_families(end_date):
    """Find active families whose last lesson (any status) was 30-45 days ago.
    Uses the reporting week's Saturday (end_date) as the reference point so
    results are consistent regardless of when the script is run.
    Matches Teachworks 'Active Family Last Lesson' report."""
    cutoff_45 = (end_date - timedelta(days=45)).isoformat()

    # 1. Active families and students
    print("    Pulling active families...")
    families = tw_get("customers", {"status": "Active", "customer_type": "family"})
    print(f"    Active families: {len(families)}")

    print("    Pulling active students...")
    students = tw_get("students", {"status": "Active"})
    student_to_customer = {s["id"]: s["customer_id"] for s in students}
    print(f"    Active students: {len(students)}")

    # 2. All lessons in last 45 days
    print("    Pulling lessons (last 45 days)...")
    lessons = tw_get("lessons", {"from_date[gte]": cutoff_45})
    print(f"    Lessons: {len(lessons)}")

    # 3. Build customer_id -> last lesson date
    customer_last_lesson = {}
    for l in lessons:
        lesson_date = (l.get("from_date") or "")[:10]
        for p in (l.get("participants") or []):
            sid = p.get("student_id")
            cid = student_to_customer.get(sid)
            if cid and lesson_date:
                if cid not in customer_last_lesson or lesson_date > customer_last_lesson[cid]:
                    customer_last_lesson[cid] = lesson_date

    # 4. Filter to 30-45 days inactive
    inactive = []
    for f in families:
        cid = f["id"]
        last = customer_last_lesson.get(cid)
        if not last:
            continue
        last_date = datetime.strptime(last, "%Y-%m-%d").date()
        days = (end_date - last_date).days
        if 30 <= days <= 45:
            last_name = f.get("last_name") or ""
            initial = last_name[0].lower() if last_name else ""
            if initial in JANELLE_RANGE:
                scheduler = "janelle"
            elif initial in YOLANDA_RANGE:
                scheduler = "yolanda"
            else:
                scheduler = "unassigned"
            inactive.append({
                "name": f"{f.get('first_name', '')} {last_name}".strip(),
                "last_name": last_name,
                "email": f.get("email") or "",
                "phone": f.get("mobile_phone") or f.get("home_phone") or "",
                "last_lesson": last,
                "days_inactive": days,
                "scheduler": scheduler,
            })

    inactive.sort(key=lambda x: x["days_inactive"], reverse=True)
    print(f"    Families 30-45 days inactive: {len(inactive)}")
    return inactive

# ─────────────────────────────────────────────
# NO-SHOW REPORT (TRAILING 14-DAY WINDOW)
# ─────────────────────────────────────────────
NO_SHOW_STATUSES = {"no_show", "missed", "no show"}

def fetch_no_show_report(end_date, min_no_shows=3):
    """Find students with more than 2 no-shows in the trailing 14-day window.
    Window runs from (end_date - 13 days) through end_date, inclusive.
    Returns (flagged_list, window_start_date) where flagged_list contains dicts:
      {student_id, name, count, dates, scheduler}
    sorted by count descending."""
    window_start = end_date - timedelta(days=13)  # 14 days inclusive

    print(f"    Pulling lessons ({window_start} – {end_date}) for no-show analysis...")
    lessons = tw_get("lessons", {
        "from_date[gte]": window_start.isoformat(),
        "from_date[lte]": end_date.isoformat(),
    })
    print(f"    Lessons in 14-day window: {len(lessons)}")

    no_show_data = {}  # student_id -> {name, count, dates, scheduler}

    def record_no_show(sid, name, lesson_date):
        """Classify student by last name and record a no-show."""
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
            # No participants array — use lesson-level status and name
            if get_lesson_status(lesson) in NO_SHOW_STATUSES:
                lesson_id = str(lesson.get("id") or lesson.get("name", "unknown"))
                record_no_show(lesson_id, lesson.get("name", "Unknown"), lesson_date)

    flagged = [
        {"student_id": sid, **data}
        for sid, data in no_show_data.items()
        if data["count"] >= min_no_shows
    ]
    flagged.sort(key=lambda x: (-x["count"], x["name"]))

    print(f"    Students with {min_no_shows}+ no-shows: {len(flagged)}")
    return flagged, window_start


# ─────────────────────────────────────────────
# HUBSPOT API
# ─────────────────────────────────────────────
HS_BASE = "https://api.hubapi.com"

def hs_get(endpoint, params=None):
    headers = {"Authorization": f"Bearer {HUBSPOT_API_KEY}"}
    for attempt in range(4):
        r = requests.get(f"{HS_BASE}/{endpoint}", headers=headers, params=params or {}, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", 5 * (attempt + 1)))
            print(f"      ⏳ HubSpot rate limit (429), retrying in {wait:.0f}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()  # raise on final failure
    return r.json()

def hs_post(endpoint, payload):
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(4):
        r = requests.post(f"{HS_BASE}/{endpoint}", headers=headers, json=payload, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", 5 * (attempt + 1)))
            print(f"      ⏳ HubSpot rate limit (429), retrying in {wait:.0f}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()  # raise on final failure
    return r.json()

def fetch_72hr_turnaround(start_date, end_date):
    """
    Of deals created during the reporting week (Gold, Free Trial, In-Person),
    what % did NOT move into a Post-Lesson stage within 72 hours?
    Uses hs_v2_cumulative_time_in_{stageId} properties.
    Returns (pct_missed, missed_deals_list).
    """
    MS_72HR = 72 * 3600 * 1000  # 72 hours in milliseconds
    start_ms = str(int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000))
    end_ms   = str(int(datetime.combine(end_date, datetime.max.time()).timestamp() * 1000))

    base_props = ["dealname", "dealstage", "pipeline", "createdate", "hubspot_owner_id"]

    all_deals = []
    for pid, cfg in PIPELINES_72HR.items():
        # Only request timing properties relevant to this pipeline
        timing_props = [f"hs_v2_cumulative_time_in_{sid}" for sid in cfg["pre"]]
        after = None
        while True:
            payload = {
                "filterGroups": [{
                    "filters": [
                        {"propertyName": "createdate", "operator": "GTE", "value": start_ms},
                        {"propertyName": "createdate", "operator": "LTE", "value": end_ms},
                        {"propertyName": "pipeline", "operator": "EQ", "value": pid},
                    ]
                }],
                "properties": base_props + timing_props,
                "limit": 100,
            }
            if after:
                payload["after"] = after
            data = hs_post("crm/v3/objects/deals/search", payload)
            all_deals.extend(data.get("results", []))
            paging = data.get("paging", {}).get("next", {})
            after = paging.get("after")
            if not after:
                break

    if not all_deals:
        return 0, []

    missed = []
    on_time = 0
    for d in all_deals:
        p = d["properties"]
        pid = p.get("pipeline", "")
        cfg = PIPELINES_72HR.get(pid)
        if not cfg:
            continue

        # Check if deal reached post-lesson (or beyond) by current stage
        current_stage = p.get("dealstage", "")
        reached_post = current_stage in cfg["post_and_beyond"]

        # Sum cumulative time in all pre-lesson stages (milliseconds)
        pre_time = sum(
            float(p.get(f"hs_v2_cumulative_time_in_{sid}") or 0)
            for sid in cfg["pre"]
        )

        if reached_post and pre_time <= MS_72HR:
            on_time += 1
        else:
            # Missed: either never reached post-lesson, or took > 72 hrs
            pre_hrs = pre_time / 3600000 if pre_time > 0 else None
            # If still in pre-lesson, calculate elapsed time from creation
            if not reached_post and pre_hrs is None:
                created = datetime.fromisoformat(p["createdate"].replace("Z", "+00:00"))
                elapsed = (datetime.now(created.tzinfo) - created).total_seconds() / 3600
                pre_hrs = elapsed
            # Classify deal by scheduler using the parent's last name
            dealname = p.get("dealname", "Unknown")
            scheduler = scheduler_from_deal_name(dealname)
            missed.append({
                "name": dealname,
                "pipeline": cfg["name"],
                "stage": current_stage,
                "pre_hours": round(pre_hrs or 0, 1),
                "reached_post": reached_post,
                "scheduler": scheduler,
            })

    total = len(all_deals)
    pct_missed = round(len(missed) / total * 100, 1) if total > 0 else 0

    # Also add scheduler to on-time deals for per-scheduler % calculation
    all_deal_schedulers = [
        scheduler_from_deal_name(d["properties"].get("dealname", ""))
        for d in all_deals
    ]

    return pct_missed, missed, all_deal_schedulers

# ─────────────────────────────────────────────
# CHARTER SCHOOL MARKETING (B2B) — Danielle's L10 metrics
# Distinct from the B2C charter pipeline (907748) used in 72-hr turnaround.
# Stage IDs verified 2026-05-29 after Danielle restructured the pipeline:
#   - "Outreach Initiated" was deleted; we now track entries into "Meeting Requested"
#     (kept the variable name OUTREACH_INITIATED to match the L10 Monday item).
#   - "Meeting Scheduled" / "Meeting Held" IDs shifted by one (Danielle reused 1321538607
#     for "Meeting Held"; "Meeting Scheduled" moved to 1321538606).
#   - "Follow-Up Active" (Negotiating) was deleted — Active Proposals is now Proposal Out only.
#   - New stage "Referred Contact" (1365065371) is a pre-outreach intake bucket — excluded
#     from all aggregations.
# ─────────────────────────────────────────────
CSM_PIPELINE                 = "145539386"
CSM_STAGE_OUTREACH_INITIATED = "1360392500"   # HubSpot label: "Meeting Requested"
CSM_STAGE_MEETING_SCHEDULED  = "1321538606"
CSM_STAGE_MEETING_HELD       = "1321538607"
CSM_STAGE_PROPOSAL_SENT      = "1310539811"   # HubSpot label: "Proposal Out"
CSM_STAGE_CLOSED_WON         = "1321538610"   # HubSpot label: "Program Contracted (Won)"
CSM_STAGE_CLOSED_LOST        = "1321538611"   # HubSpot label: "Not Moving Forward (Lost)"
CSM_STAGE_REFERRED_CONTACT   = "1365065371"   # pre-outreach intake — ignored per Roman 2026-05-29
CSM_EXCLUDED_STAGES          = ["1360466730", CSM_STAGE_REFERRED_CONTACT]  # phantom + referred intake
CSM_ACTIVE_PROPOSAL_STAGES   = [CSM_STAGE_PROPOSAL_SENT]  # Follow-Up Active stage was removed


# ─────────────────────────────────────────────
# NPS SOURCE BOARDS — aggregated weekly into L10 Scorecard
# ─────────────────────────────────────────────
NPS_BOARDS = {
    "family":      {"board_id": "18407864618", "score_col": "numeric_mm28sp55", "date_col": "date_mm28a78k"},
    "tutor":       {"board_id": "18407864611", "score_col": "numeric_mm28xrec", "date_col": "date_mm28f1ns"},
    "support_bot": {"board_id": "18407864631", "score_col": "numeric_mm28ffz1", "date_col": "date_mm28d7m0"},
}


def fetch_nps_weekly_avg(nps_key, start_date, end_date):
    """Average NPS score for responses dated within [start_date, end_date].

    Returns None if there are zero responses in the window — caller should
    treat this as 'No Data' and leave the L10 cell empty.

    Implementation note: Monday's items_page date-range filter syntax has
    been brittle across API versions. Simplest reliable approach: fetch all
    items from the source board (each has <100 items) and filter in Python.
    """
    cfg = NPS_BOARDS[nps_key]
    query = """
    query ($board: ID!) {
      boards(ids: [$board]) {
        items_page(limit: 500) {
          items {
            column_values(ids: ["%s", "%s"]) { id text }
          }
        }
      }
    }
    """ % (cfg["score_col"], cfg["date_col"])
    result = monday_query(query, {"board": cfg["board_id"]})
    items = result["data"]["boards"][0]["items_page"]["items"]
    start_str = start_date.strftime("%Y-%m-%d")
    end_str   = end_date.strftime("%Y-%m-%d")
    scores = []
    for item in items:
        score_text = None
        date_text  = None
        for cv in item["column_values"]:
            if cv["id"] == cfg["score_col"]:
                score_text = cv["text"]
            elif cv["id"] == cfg["date_col"]:
                date_text = cv["text"]
        if not (score_text and date_text):
            continue
        if start_str <= date_text <= end_str:
            try:
                scores.append(float(score_text))
            except ValueError:
                continue
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def _fetch_csm_stage_entry_count(start_date, end_date, stage_id):
    """Count CSM deals that entered `stage_id` during [start_date, end_date]."""
    start_ms = str(int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000))
    end_ms   = str(int(datetime.combine(end_date, datetime.max.time()).timestamp() * 1000))
    prop = f"hs_v2_date_entered_{stage_id}"
    payload = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "EQ",  "value": CSM_PIPELINE},
            {"propertyName": prop,       "operator": "GTE", "value": start_ms},
            {"propertyName": prop,       "operator": "LTE", "value": end_ms},
        ]}],
        "properties": ["dealname"],
        "limit": 1,
    }
    return hs_post("crm/v3/objects/deals/search", payload).get("total", 0)


def fetch_csm_new_deals_created(start_date, end_date):
    """Count deals created in CSM pipeline this week.

    Excludes phantom stage (1360466730) and Closed Lost (1321538611).
    Rationale: a deal created and immediately closed-lost is data cleanup, not
    real prospecting activity. Counting it inflates the metric and obscures
    Danielle's actual top-of-funnel work.
    """
    start_ms = str(int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000))
    end_ms   = str(int(datetime.combine(end_date, datetime.max.time()).timestamp() * 1000))
    excluded_from_new_deals = CSM_EXCLUDED_STAGES + [CSM_STAGE_CLOSED_LOST]
    filters = [
        {"propertyName": "pipeline",   "operator": "EQ",  "value": CSM_PIPELINE},
        {"propertyName": "createdate", "operator": "GTE", "value": start_ms},
        {"propertyName": "createdate", "operator": "LTE", "value": end_ms},
    ]
    for excluded in excluded_from_new_deals:
        filters.append({"propertyName": "dealstage", "operator": "NEQ", "value": excluded})
    payload = {"filterGroups": [{"filters": filters}], "properties": ["dealname"], "limit": 1}
    return hs_post("crm/v3/objects/deals/search", payload).get("total", 0)


def fetch_csm_outreach_initiated(start_date, end_date):
    return _fetch_csm_stage_entry_count(start_date, end_date, CSM_STAGE_OUTREACH_INITIATED)


def fetch_csm_meetings_scheduled(start_date, end_date):
    return _fetch_csm_stage_entry_count(start_date, end_date, CSM_STAGE_MEETING_SCHEDULED)


def fetch_csm_meetings_held(start_date, end_date):
    return _fetch_csm_stage_entry_count(start_date, end_date, CSM_STAGE_MEETING_HELD)


def fetch_charter_active_deals():
    """Snapshot: deals currently in Proposal Sent + Follow-Up Active (post-proposal)."""
    payload = {
        "filterGroups": [
            {"filters": [
                {"propertyName": "pipeline",  "operator": "EQ", "value": CSM_PIPELINE},
                {"propertyName": "dealstage", "operator": "EQ", "value": stage},
            ]}
            for stage in CSM_ACTIVE_PROPOSAL_STAGES
        ],
        "properties": ["dealname"],
        "limit": 1,
    }
    return hs_post("crm/v3/objects/deals/search", payload).get("total", 0)


def fetch_charter_pilots_signed(start_date, end_date):
    """Count deals that entered Closed Won during the week (Sun–Sat)."""
    return _fetch_csm_stage_entry_count(start_date, end_date, CSM_STAGE_CLOSED_WON)

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
                print(f"      ⏳ Monday.com timeout, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise

def create_group(board_id, group_name):
    """Create a new group in a Monday.com board."""
    q = """
    mutation ($boardId: ID!, $groupName: String!) {
      create_group(board_id: $boardId, group_name: $groupName) { id }
    }"""
    data = monday_query(q, {"boardId": str(board_id), "groupName": group_name})
    return data["data"]["create_group"]["id"]

def create_item(board_id, group_id, item_name, column_values):
    """Create a new item in a Monday.com board."""
    import json
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

def update_item(board_id, item_id, column_values):
    """Update column values on an existing Monday.com item."""
    import json
    # Monday.com numbers columns require string values (even "0")
    sanitized = {}
    for k, v in column_values.items():
        if isinstance(v, (int, float)):
            sanitized[k] = str(v)
        else:
            sanitized[k] = v
    q = """
    mutation ($boardId: ID!, $itemId: ID!, $colVals: JSON!) {
      change_multiple_column_values(board_id: $boardId, item_id: $itemId,
                                    column_values: $colVals) { id }
    }"""
    monday_query(q, {
        "boardId": str(board_id),
        "itemId": str(item_id),
        "colVals": json.dumps(sanitized),
    })

def get_or_create_scorecard_week_col(board_id, start_date, end_date):
    """Find or create the weekly numbers column on the L10 Scorecard.
    Column title format: '3/8/26-3/14/26' (no words, just dates with 2-digit year)."""
    col_title = f"{start_date.strftime('%-m/%-d/%y')}-{end_date.strftime('%-m/%-d/%y')}"

    # Check existing columns
    q = '{ boards(ids: [%s]) { columns { id title type } } }' % board_id
    data = monday_query(q)
    for c in data["data"]["boards"][0]["columns"]:
        if c["title"] == col_title:
            print(f"    Found existing scorecard column: {col_title} → {c['id']}")
            return c["id"]

    # Create new numbers column
    q = """
    mutation ($boardId: ID!, $title: String!) {
      create_column(board_id: $boardId, title: $title, column_type: numbers) { id }
    }"""
    data = monday_query(q, {"boardId": str(board_id), "title": col_title})
    col_id = data["data"]["create_column"]["id"]
    print(f"    Created new scorecard column: {col_title} → {col_id}")
    return col_id

def get_prior_week_col(board_id, start_date):
    """Return column ID for the week prior to start_date, or None if not found.
    Mirrors the title format used by get_or_create_scorecard_week_col."""
    prior_start = start_date - timedelta(days=7)
    prior_end   = start_date - timedelta(days=1)
    col_title = f"{prior_start.strftime('%-m/%-d/%y')}-{prior_end.strftime('%-m/%-d/%y')}"
    q = '{ boards(ids: [%s]) { columns { id title type } } }' % board_id
    data = monday_query(q)
    for c in data["data"]["boards"][0]["columns"]:
        if c["title"] == col_title:
            return c["id"]
    return None

# ─────────────────────────────────────────────
# WRITE: WEEKLY LESSON REPORT
# ─────────────────────────────────────────────
def build_unmarked_tutor_analysis(unmarked_by_tutor):
    """Build a text breakdown of unmarked lessons by tutor."""
    if not unmarked_by_tutor:
        return "No unmarked lessons this week. ✅"

    # Sort by hours descending
    sorted_tutors = sorted(unmarked_by_tutor.items(), key=lambda x: x[1]["hours"], reverse=True)
    total_hrs = sum(t[1]["hours"] for t in sorted_tutors)

    lines = [f"{round(total_hrs, 2)} total unmarked hours across {len(sorted_tutors)} tutor(s):\n"]
    for tutor, data in sorted_tutors:
        hrs = round(data["hours"], 2)
        count = len(data["students"])
        lines.append(f"• {tutor} — {hrs}hrs ({count} student-lesson(s))")
        for s in data["students"]:
            lines.append(f"  - {s}")
        lines.append("")

    return "\n".join(lines)


def build_missed_deals_analysis(missed_deals):
    """Build a text analysis of deals that missed the 72-hr post-lesson window."""
    if not missed_deals:
        return "All deals moved to Post-Lesson within 72 hours. ✅"

    lines = [f"{len(missed_deals)} deal(s) did NOT reach Post-Lesson within 72 hours:\n"]
    for d in missed_deals:
        if d["reached_post"]:
            status = f"Reached Post-Lesson but took {d['pre_hours']}hrs (exceeded 72hr target)"
        else:
            status = f"Still in Pre-Lesson — {d['pre_hours']}hrs and counting"
        lines.append(f"• {d['name']} ({d['pipeline']})")
        lines.append(f"  → {status}\n")

    # Summary
    still_stuck = [d for d in missed_deals if not d["reached_post"]]
    late_movers = [d for d in missed_deals if d["reached_post"]]
    if still_stuck:
        lines.append(f"⚠️ {len(still_stuck)} deal(s) still have not moved to Post-Lesson and need immediate follow-up.")
    if late_movers:
        lines.append(f"ℹ️ {len(late_movers)} deal(s) eventually moved to Post-Lesson but exceeded the 72-hr window.")

    return "\n".join(lines)


def write_weekly_lesson_report(metrics, post_lesson_pct, missed_deals,
                               janelle_72hr_pct, yolanda_72hr_pct,
                               janelle_missed, yolanda_missed,
                               start_date, end_date):
    board_id = BOARDS["weekly_lesson_report"]
    week_label = f"Week of {start_date.strftime('%-m/%-d')} - {end_date.strftime('%-m/%-d')}"
    print(f"  Creating group: {week_label}")
    group_id = create_group(board_id, week_label)

    # Build per-scheduler long-text analysis
    janelle_analysis = build_missed_deals_analysis(janelle_missed)
    yolanda_analysis = build_missed_deals_analysis(yolanda_missed)
    kath_analysis = build_unmarked_tutor_analysis(metrics.get("unmarked_by_tutor", {}))

    rows = [
        ("Company Total", {
            WLR_COLS["total_hrs"]:       metrics["company"]["total"],
            WLR_COLS["attended_hrs"]:    metrics["company"]["attended"],
            WLR_COLS["cancelled_hrs"]:   metrics["company"]["cancelled"],
            WLR_COLS["no_show_hrs"]:     metrics["company"]["no_show"],
            WLR_COLS["unmarked_hrs"]:    metrics["company"]["unmarked"],
            WLR_COLS["cancel_rate"]:     metrics["company"]["cancel_rate"],
            WLR_COLS["unmarked_rate"]:   metrics["company"]["unmarked_rate"],
            WLR_COLS["post_lesson_pct"]: post_lesson_pct,
            WLR_COLS["long_text"]:       build_missed_deals_analysis(missed_deals),
            WLR_COLS["people"]:          {"personsAndTeams": [{"id": int(MONDAY_USER_IDS["mandy"]), "kind": "person"}]},
        }),
        ("Janelle — A–L", {
            WLR_COLS["total_hrs"]:       metrics["janelle"]["total"],
            WLR_COLS["attended_hrs"]:    metrics["janelle"]["attended"],
            WLR_COLS["cancelled_hrs"]:   metrics["janelle"]["cancelled"],
            WLR_COLS["no_show_hrs"]:     metrics["janelle"]["no_show"],
            WLR_COLS["unmarked_hrs"]:    metrics["janelle"]["unmarked"],
            WLR_COLS["cancel_rate"]:     metrics["janelle"]["cancel_rate"],
            WLR_COLS["unmarked_rate"]:   metrics["janelle"]["unmarked_rate"],
            WLR_COLS["post_lesson_pct"]: janelle_72hr_pct,
            WLR_COLS["long_text"]:       janelle_analysis,
            WLR_COLS["people"]:          {"personsAndTeams": [{"id": int(MONDAY_USER_IDS["janelle"]), "kind": "person"}]},
        }),
        ("Yolanda — M–Z", {
            WLR_COLS["total_hrs"]:       metrics["yolanda"]["total"],
            WLR_COLS["attended_hrs"]:    metrics["yolanda"]["attended"],
            WLR_COLS["cancelled_hrs"]:   metrics["yolanda"]["cancelled"],
            WLR_COLS["no_show_hrs"]:     metrics["yolanda"]["no_show"],
            WLR_COLS["unmarked_hrs"]:    metrics["yolanda"]["unmarked"],
            WLR_COLS["cancel_rate"]:     metrics["yolanda"]["cancel_rate"],
            WLR_COLS["unmarked_rate"]:   metrics["yolanda"]["unmarked_rate"],
            WLR_COLS["post_lesson_pct"]: yolanda_72hr_pct,
            WLR_COLS["long_text"]:       yolanda_analysis,
            WLR_COLS["people"]:          {"personsAndTeams": [{"id": int(MONDAY_USER_IDS["yolanda"]), "kind": "person"}]},
        }),
        ("Kath — Scheduled Hours", {
            WLR_COLS["total_hrs"]:      metrics["kath"]["scheduled"],
            WLR_COLS["unmarked_hrs"]:   metrics["company"]["unmarked"],
            WLR_COLS["unmarked_rate"]:  metrics["company"]["unmarked_rate"],
            WLR_COLS["long_text"]:      kath_analysis,
            WLR_COLS["people"]:         {"personsAndTeams": [{"id": int(MONDAY_USER_IDS["kath"]), "kind": "person"}]},
        }),
    ]

    for name, col_vals in rows:
        print(f"    Adding row: {name}")
        create_item(board_id, group_id, name, col_vals)

    print("  ✅ Weekly Lesson Report updated.")

# ─────────────────────────────────────────────
# WRITE: L10 SCORECARD
# ─────────────────────────────────────────────
def compute_status(rule, current_value, prior_value=None, threshold_override=None):
    """Compute On Track / Off Track / No Data based on rule type.

    threshold_override: the goal read from the board's `target` column. When
    provided it wins over the rule's hardcoded fallback `threshold`.
    """
    if current_value is None:
        return rule.get("no_data_label")  # returns "No Data" or None
    if rule["type"] == "weekly_threshold":
        threshold = threshold_override if threshold_override is not None else rule["threshold"]
        return "On Track" if current_value >= threshold else "Off Track"
    if rule["type"] == "vs_prior_week":
        if prior_value is None:
            return "On Track"  # first week of data, can't compare
        return "On Track" if current_value >= prior_value else "Off Track"
    return None


def fetch_prior_week_value(board_id, item_id, prior_col):
    """Read prior week's numeric value for a scorecard item.

    Returns None if column doesn't exist or value is empty.
    """
    try:
        query = """
        query ($board: ID!, $item: [ID!]) {
          boards(ids: [$board]) {
            items_page(query_params: {ids: $item}) {
              items { column_values(ids: ["%s"]) { text } }
            }
          }
        }
        """ % prior_col
        result = monday_query(query, {"board": str(board_id), "item": [str(item_id)]})
        text = result["data"]["boards"][0]["items_page"]["items"][0]["column_values"][0]["text"]
        return float(text) if text else None
    except Exception as e:
        print(f"   ⚠️  Couldn't fetch prior week value for item {item_id}: {e}")
        return None


def fetch_target_value(board_id, item_id):
    """Read a scorecard row's goal from the board's `target` column and parse a number.

    Returns None if the column/cell is empty or unparseable, so the caller falls
    back to the rule's hardcoded threshold. Grabs the first numeric token, so
    goal text like "5", ">= 5", "5+", or "9.0" all resolve.
    """
    try:
        query = """
        query ($board: ID!, $item: [ID!]) {
          boards(ids: [$board]) {
            items_page(query_params: {ids: $item}) {
              items { column_values(ids: ["%s"]) { text } }
            }
          }
        }
        """ % SCORECARD_COLS["target"]
        result = monday_query(query, {"board": str(board_id), "item": [str(item_id)]})
        text = result["data"]["boards"][0]["items_page"]["items"][0]["column_values"][0]["text"]
        if not text:
            return None
        m = re.search(r"[-+]?\d*\.?\d+", text.replace(",", ""))
        return float(m.group()) if m else None
    except Exception as e:
        print(f"   ⚠️  Couldn't fetch target for item {item_id}: {e}")
        return None


def apply_status_updates(metric_values, board_id, prior_col):
    """Set On Track / Off Track status on each scorecard row per SCORECARD_STATUS_RULES."""
    import json
    print("\n🎯 Updating scorecard statuses...")
    for metric_key, rule in SCORECARD_STATUS_RULES.items():
        if metric_key not in SCORECARD_ITEMS:
            continue
        item_id = SCORECARD_ITEMS[metric_key]
        current = metric_values.get(metric_key, 0)
        prior = None
        target = None
        if rule["type"] == "vs_prior_week" and prior_col:
            prior = fetch_prior_week_value(board_id, item_id, prior_col)
        elif rule["type"] == "weekly_threshold":
            target = fetch_target_value(board_id, item_id)
        status = compute_status(rule, current, prior, threshold_override=target)
        if status is None:
            continue
        status_value = json.dumps({STATUS_COLUMN_ID: {"label": status}})
        mutation = """
        mutation ($board: ID!, $item: ID!, $vals: JSON!) {
          change_multiple_column_values(board_id: $board, item_id: $item, column_values: $vals) { id }
        }
        """
        monday_query(mutation, {"board": str(board_id), "item": str(item_id), "vals": status_value})
        goal_src = f"goal {target:g}" if target is not None else f"default {rule.get('threshold')}"
        print(f"   {metric_key}: {current} → {status}  (vs {goal_src})")


def write_l10_scorecard(metrics, post_lesson_pct, charter_deals,
                        package_hours_fy, new_students, pkg_units_wk=0,
                        csm_new_deals=0, csm_outreach=0,
                        csm_meetings_sch=0, csm_meetings_held=0,
                        nps_client=None, nps_tutor=None, nps_support_bot=None,
                        start_date=None, end_date=None):
    board_id = BOARDS["l10_scorecard"]
    col = get_or_create_scorecard_week_col(board_id, start_date, end_date)

    updates = [
        (SCORECARD_ITEMS["hours_attended"],         {col: metrics["company"]["attended"]}),
        (SCORECARD_ITEMS["package_units_sold"],     {col: pkg_units_wk}),
        (SCORECARD_ITEMS["cancellation_rate"],      {col: metrics["company"]["cancel_rate"]}),
        (SCORECARD_ITEMS["new_students"],           {col: new_students}),
        (SCORECARD_ITEMS["package_hours_sold"],     {col: package_hours_fy}),
        (SCORECARD_ITEMS["charter_deals"],          {col: charter_deals}),
        (SCORECARD_ITEMS["post_lesson_72hr"],       {col: post_lesson_pct}),
        (SCORECARD_ITEMS["csm_new_deals"],          {col: csm_new_deals}),
        (SCORECARD_ITEMS["csm_outreach_initiated"], {col: csm_outreach}),
        (SCORECARD_ITEMS["csm_meetings_scheduled"], {col: csm_meetings_sch}),
        (SCORECARD_ITEMS["csm_meetings_held"],      {col: csm_meetings_held}),
        (SCORECARD_ITEMS["nps_client"],             {col: nps_client}),
        (SCORECARD_ITEMS["nps_tutor"],              {col: nps_tutor}),
        (SCORECARD_ITEMS["nps_support_bot"],        {col: nps_support_bot}),
    ]

    for item_id, col_vals in updates:
        if any(v is None for v in col_vals.values()):
            print(f"    Skipping numeric write for item {item_id} (no data)")
            continue
        print(f"    Updating scorecard item {item_id}")
        update_item(board_id, item_id, col_vals)

    print("  ✅ L10 Scorecard updated.")

    metric_values = {
        "csm_new_deals":          csm_new_deals,
        "csm_outreach_initiated": csm_outreach,
        "csm_meetings_scheduled": csm_meetings_sch,
        "csm_meetings_held":      csm_meetings_held,
        "charter_deals":          charter_deals,
        "nps_client":             nps_client,
        "nps_tutor":              nps_tutor,
        "nps_support_bot":        nps_support_bot,
    }
    prior_col = get_prior_week_col(board_id, start_date)
    apply_status_updates(metric_values, board_id, prior_col)

# ─────────────────────────────────────────────
# WRITE: FIRST LESSON REPORT
# ─────────────────────────────────────────────
def write_first_lesson_report(new_students, start_date, end_date):
    board_id = BOARDS["first_lesson_report"]
    week_label = f"Week ending {end_date.strftime('%-m/%-d/%Y')}"
    group_id = "group_mm125d1v"  # Weekly Detail group

    col_vals = {
        FLR_COLS["week_ending"]:   {"date": end_date.isoformat()},
        FLR_COLS["student_count"]: new_students,
    }

    print(f"    Adding first lesson row: {week_label} — {new_students} students")
    create_item(board_id, group_id, week_label, col_vals)
    print("  ✅ First Lesson Report updated.")

# ─────────────────────────────────────────────
# WRITE: INACTIVE STUDENT OUTREACH
# ─────────────────────────────────────────────
def write_inactive_family_report(inactive_families, start_date, end_date):
    board_id = BOARDS["inactive_student_outreach"]
    week_label = f"Week of {start_date.strftime('%-m/%-d')} - {end_date.strftime('%-m/%-d')}"
    print(f"  Creating group: {week_label}")
    group_id = create_group(board_id, week_label)

    for fam in inactive_families:
        col_vals = {
            ISO_COLS["last_lesson_date"]: {"date": fam["last_lesson"]},
            ISO_COLS["days_inactive"]:    fam["days_inactive"],
        }
        # Assign scheduler to People column
        scheduler_id = MONDAY_USER_IDS.get(fam["scheduler"])
        if scheduler_id:
            col_vals[ISO_COLS["people"]] = {"personsAndTeams": [{"id": int(scheduler_id), "kind": "person"}]}
        if fam["email"]:
            col_vals[ISO_COLS["email"]] = {"email": fam["email"], "text": fam["email"]}
        if fam["phone"]:
            # Strip to digits only for Monday.com phone column
            digits = re.sub(r"\D", "", fam["phone"])
            if digits and not digits.startswith("1"):
                digits = "1" + digits
            col_vals[ISO_COLS["phone"]] = {"phone": "+" + digits, "countryShortName": "US"}
        print(f"    Adding: {fam['name']} ({fam['days_inactive']}d — {fam['scheduler']})")
        create_item(board_id, group_id, fam["name"], col_vals)

    print(f"  ✅ Inactive Student Outreach updated ({len(inactive_families)} families).")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    # CHECK_ONLY: CI smoke test — confirm required secrets are wired, then exit
    # before any Teachworks read or HubSpot/Monday write. (No DRY_RUN mode here,
    # so this is how the migrated GitHub Actions job self-tests.)
    if os.getenv("CHECK_ONLY", "").lower() == "true":
        missing = [k for k in ("TEACHWORKS_API_KEY", "HUBSPOT_API_KEY", "MONDAY_API_KEY") if not os.getenv(k)]
        if missing:
            print(f"CHECK FAILED: missing env: {', '.join(missing)}")
            raise SystemExit(1)
        print("CHECK OK: TEACHWORKS_API_KEY / HUBSPOT_API_KEY / MONDAY_API_KEY present; skipping all reads/writes.")
        raise SystemExit(0)

    print(f"\n{'='*55}")
    print(f"  A+ Tutoring Weekly Sync — {datetime.now().strftime('%A %B %d, %Y %I:%M %p')}")
    print(f"{'='*55}\n")

    # 1. Calculate week range
    if os.getenv("WEEK_START") and os.getenv("WEEK_END"):
        start_date = datetime.strptime(os.environ["WEEK_START"], "%Y-%m-%d").date()
        end_date   = datetime.strptime(os.environ["WEEK_END"],   "%Y-%m-%d").date()
        print(f"⚠️  Manual override: running for {start_date} → {end_date}")
    else:
        start_date, end_date = get_last_week_range()
    print(f"📅 Week: {start_date} → {end_date}\n")

    # 2. Pull Teachworks data
    print("📥 Pulling Teachworks data...")
    lessons       = fetch_lessons_for_week(start_date, end_date)
    metrics       = process_lessons(lessons)
    package_hrs   = fetch_package_hours_fy(end_date)
    pkg_units_wk  = fetch_package_hours_week(start_date, end_date)
    new_students  = fetch_new_students_week(start_date, end_date, week_lessons=lessons)
    print(f"   Lessons pulled: {len(lessons)}")
    print(f"\n   {'':20} {'Attended':>10} {'Cancelled':>10} {'No Show':>10} {'Unmarked':>10} {'Total':>10} {'Cancel%':>8} {'Unmrk%':>8}")
    print(f"   {'─'*88}")
    for label, key in [("Kath (Scheduled)", None), ("Janelle (A–L)", "janelle"), ("Yolanda (M–Z)", "yolanda"), ("Company Total", "company")]:
        if key is None:
            print(f"   {label:20} {'':>10} {'':>10} {'':>10} {'':>10} {metrics['kath']['scheduled']:>10.2f}")
        else:
            m = metrics[key]
            print(f"   {label:20} {m['attended']:>10.2f} {m['cancelled']:>10.2f} {m['no_show']:>10.2f} {m['unmarked']:>10.2f} {m['total']:>10.2f} {m['cancel_rate']:>7.1f}% {m['unmarked_rate']:>7.1f}%")
    print(f"\n   Package hours YTD: {package_hrs}")
    print(f"   New students: {new_students}")

    # 3. Inactive family report
    print("\n📥 Checking for inactive families (30-45 days)...")
    inactive_families = fetch_inactive_families(end_date)
    janelle_inactive = [f for f in inactive_families if f["scheduler"] == "janelle"]
    yolanda_inactive = [f for f in inactive_families if f["scheduler"] == "yolanda"]

    print(f"\n   Janelle (A–L): {len(janelle_inactive)} families")
    for f in janelle_inactive:
        print(f"     {f['name']:30} Last lesson: {f['last_lesson']}  ({f['days_inactive']}d)")
    print(f"\n   Yolanda (M–Z): {len(yolanda_inactive)} families")
    for f in yolanda_inactive:
        print(f"     {f['name']:30} Last lesson: {f['last_lesson']}  ({f['days_inactive']}d)")
    print(f"\n   Total inactive: {len(inactive_families)}")

    # 4. No-show report — trailing 14-day window
    print("\n📥 Checking for repeat no-shows (trailing 14 days)...")
    no_show_flagged, ns_window_start = fetch_no_show_report(end_date)

    print(f"\n   No-show report ({ns_window_start} – {end_date}):")
    if no_show_flagged:
        print(f"   ⚠️  {len(no_show_flagged)} student(s) with 3+ no-shows in the last 14 days:\n")
        janelle_ns = [s for s in no_show_flagged if s["scheduler"] == "janelle"]
        yolanda_ns = [s for s in no_show_flagged if s["scheduler"] == "yolanda"]
        other_ns   = [s for s in no_show_flagged if s["scheduler"] == "unassigned"]
        for label, group in [("Janelle (A–L)", janelle_ns), ("Yolanda (M–Z)", yolanda_ns), ("Unassigned", other_ns)]:
            if group:
                print(f"   {label}:")
                for s in group:
                    dates_str = ", ".join(sorted(set(s["dates"])))
                    print(f"     {s['name']:35} {s['count']} no-shows  [{dates_str}]")
                print()
    else:
        print("   ✅ No students with 3+ no-shows in the last 14 days.")

    # 5. Pull HubSpot data
    print("\n📥 Pulling HubSpot data...")
    post_lesson_pct, missed_deals, all_deal_schedulers = fetch_72hr_turnaround(start_date, end_date)

    # Per-scheduler 72-hr missed %
    janelle_total = all_deal_schedulers.count("janelle")
    yolanda_total = all_deal_schedulers.count("yolanda")
    janelle_missed = [d for d in missed_deals if d.get("scheduler") == "janelle"]
    yolanda_missed = [d for d in missed_deals if d.get("scheduler") == "yolanda"]
    janelle_72hr_pct = round(len(janelle_missed) / janelle_total * 100, 1) if janelle_total else 0
    yolanda_72hr_pct = round(len(yolanda_missed) / yolanda_total * 100, 1) if yolanda_total else 0
    charter_deals     = fetch_charter_active_deals()
    csm_new_deals     = fetch_csm_new_deals_created(start_date, end_date)
    csm_outreach      = fetch_csm_outreach_initiated(start_date, end_date)
    csm_meetings_sch  = fetch_csm_meetings_scheduled(start_date, end_date)
    csm_meetings_held = fetch_csm_meetings_held(start_date, end_date)
    print(f"   72-hr turnaround: {post_lesson_pct}% missed (did NOT reach Post-Lesson within 72 hrs)")
    if missed_deals:
        print(f"\n   Deals that missed 72-hr window ({len(missed_deals)}):")
        for d in missed_deals:
            status = f"still in pre-lesson ({d['pre_hours']}hrs)" if not d["reached_post"] else f"took {d['pre_hours']}hrs to reach Post-Lesson"
            print(f"     {d['name']:40} {d['pipeline']:15} {status}")
    else:
        print("   All deals moved to Post-Lesson within 72 hours.")
    print(f"\n   Active Proposals (Proposal Out): {charter_deals}")
    print(f"   New Deals Created this week: {csm_new_deals}")
    print(f"   Outreach Initiated this week: {csm_outreach}")
    print(f"   Meetings Scheduled this week: {csm_meetings_sch}")
    print(f"   Meetings Held this week: {csm_meetings_held}")

    # 6. Pull NPS data from Monday.com source boards
    print("\n📥 Pulling NPS data from Monday.com...")
    nps_client      = fetch_nps_weekly_avg("family", start_date, end_date)
    nps_tutor       = fetch_nps_weekly_avg("tutor", start_date, end_date)
    nps_support_bot = fetch_nps_weekly_avg("support_bot", start_date, end_date)
    print(f"   NPS Client Satisfaction: {nps_client if nps_client is not None else 'No Data'}")
    print(f"   Tutor NPS: {nps_tutor if nps_tutor is not None else 'No Data'}")
    print(f"   Support Bot NPS: {nps_support_bot if nps_support_bot is not None else 'No Data'}")

    # 7. Write to Monday.com
    print("\n📤 Writing to Monday.com...")
    write_weekly_lesson_report(metrics, post_lesson_pct, missed_deals,
                               janelle_72hr_pct, yolanda_72hr_pct,
                               janelle_missed, yolanda_missed,
                               start_date, end_date)
    write_l10_scorecard(metrics, post_lesson_pct, charter_deals,
                        package_hrs, new_students, pkg_units_wk,
                        csm_new_deals=csm_new_deals, csm_outreach=csm_outreach,
                        csm_meetings_sch=csm_meetings_sch, csm_meetings_held=csm_meetings_held,
                        nps_client=nps_client, nps_tutor=nps_tutor, nps_support_bot=nps_support_bot,
                        start_date=start_date, end_date=end_date)
    write_first_lesson_report(new_students, start_date, end_date)
    write_inactive_family_report(inactive_families, start_date, end_date)

    print(f"\n{'='*55}")
    print(f"  ✅ Sync complete!")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    main()

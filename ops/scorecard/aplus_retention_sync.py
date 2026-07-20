#!/usr/bin/env python3
"""
aplus_retention_sync.py
-----------------------
Weekly retention tracker for A+ Tutoring.
Pulls all attended lessons from Teachworks (2020-present),
computes cohort retention curves and at-risk queue,
writes to Google Sheets, and posts to Slack.

Run every Monday AM alongside aplus_weekly_sync.py:
  0 9 * * 1 cd /Users/romanslavinsky/Documents/aplus-sync && /usr/bin/python3 aplus_retention_sync.py

FIRST RUN INSTRUCTIONS:
  1. Leave GOOGLE_SHEET_ID = "" below
  2. Run the script once: python3 aplus_retention_sync.py
  3. It will create a new sheet and print the ID in the logs
  4. Paste that ID into GOOGLE_SHEET_ID below and save
  5. All future runs update that sheet in place

ENVIRONMENT VARIABLES (in .env):
  TEACHWORKS_API_KEY              required
  SLACK_WEBHOOK_URL               required
  GOOGLE_SERVICE_ACCOUNT_JSON     path to service account .json file (default: service_account.json)

OPTIONAL FLAGS:
  DRY_RUN=true    prints output, skips all writes
  BACKFILL=true   forces full re-pull from 2020 (automatic on first run)
"""

import os
import json
import logging
import requests
from datetime import date, datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv

import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

# ─── PASTE SHEET ID HERE AFTER FIRST RUN ─────────────────────────────────────
GOOGLE_SHEET_ID = "1xdbxXZcPaLcdJlRBKGvnAmuEs7IuHPa5GF1ly0ASYq4"
# ─────────────────────────────────────────────────────────────────────────────

TEACHWORKS_API_KEY          = os.getenv("TEACHWORKS_API_KEY")
SLACK_WEBHOOK_URL           = os.getenv("SLACK_WEBHOOK_URL", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
DRY_RUN                     = os.getenv("DRY_RUN", "false").lower() == "true"

TEACHWORKS_BASE = "https://api.teachworks.com/v1"
BACKFILL_START  = date(2020, 1, 1)

ACTIVE_DAYS  = 29       # lesson within 29 days = Active; 30+ = At-Risk
MILESTONES   = [30, 60, 90, 180, 365]

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

TAB_COHORT   = "Cohort Data"
TAB_AT_RISK  = "At-Risk Queue"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── Teachworks helpers ───────────────────────────────────────────────────────

def tw_get(endpoint, params=None):
    """Paginated GET from Teachworks. Returns full list across all pages."""
    headers  = {
        "Authorization": f"Token token={TEACHWORKS_API_KEY}",
        "Content-Type": "application/json",
    }
    params   = params or {}
    results  = []
    per_page = 80  # Teachworks API max is 80 per page
    params["per_page"] = per_page
    params["page"] = 1
    while True:
        for attempt in range(3):
            resp = requests.get(
                f"{TEACHWORKS_BASE}/{endpoint}",
                headers=headers, params=params, timeout=30
            )
            if resp.status_code == 403:
                wait = 5 * (attempt + 1)
                log.warning(f"Teachworks rate limit, retrying in {wait}s...")
                import time; time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        results.extend(data)
        if len(data) < per_page:
            break
        params["page"] += 1
    return results


def fetch_lessons(from_date):
    """Fetch all lessons (any status) from from_date to today."""
    log.info(f"Fetching all lessons from {from_date} to {date.today()}...")
    raw = tw_get("lessons", params={
        "from_date[gte]": from_date.isoformat(),
        "from_date[lte]": date.today().isoformat(),
    })
    # Deduplicate by lesson ID (API may return duplicates across pages)
    seen = set()
    all_lessons = []
    for l in raw:
        lid = l.get("id")
        if lid not in seen:
            seen.add(lid)
            all_lessons.append(l)
    log.info(f"  -> {len(all_lessons)} unique lessons fetched ({len(raw)} raw)")
    return all_lessons


def fetch_upcoming():
    """Lessons scheduled in the next 21 days (used to reduce risk score)."""
    log.info("Fetching upcoming lessons (next 21 days)...")
    today = date.today()
    lessons = tw_get("lessons", params={
        "status":         "scheduled",
        "from_date[gte]": today.isoformat(),
        "from_date[lte]": (today + timedelta(days=21)).isoformat(),
    })
    log.info(f"  -> {len(lessons)} upcoming lessons fetched")
    return lessons


def get_lesson_date(lesson):
    raw = lesson.get("from_date", "")
    if raw:
        try:
            return datetime.fromisoformat(str(raw)[:10]).date()
        except ValueError:
            pass
    return None


# ─── Student aggregation ──────────────────────────────────────────────────────

def build_students(lessons):
    """
    Aggregate lessons into per-student records.
    Students are nested inside each lesson's 'participants' array.
    Uses per-participant status (not lesson-level) for accuracy in group lessons.
    - all_dates:  every lesson regardless of status (for first_lesson cohort assignment)
    - dates:      only attended/completed lessons (for retention measurement)
    """
    raw = defaultdict(lambda: {"name": "Unknown", "dates": [], "all_dates": []})
    for lesson in lessons:
        d = get_lesson_date(lesson)
        if not d:
            continue
        for p in (lesson.get("participants") or []):
            sid = p.get("student_id")
            if not sid:
                continue
            sid = str(sid)
            raw[sid]["name"] = (p.get("student_name") or "Unknown").strip()
            raw[sid]["all_dates"].append(d)
            p_status = (p.get("status") or "").lower()
            if p_status in ("attended", "completed"):
                raw[sid]["dates"].append(d)

    students = {}
    for sid, s in raw.items():
        if not s["all_dates"]:
            continue
        s["all_dates"].sort()
        s["dates"].sort()
        s["first_lesson"] = s["all_dates"][0]   # first calendar appearance
        s["last_lesson"]  = s["dates"][-1] if s["dates"] else s["all_dates"][-1]
        students[sid] = s
    return students


def build_upcoming_set(upcoming_lessons):
    sids = set()
    for l in upcoming_lessons:
        for p in (l.get("participants") or []):
            sid = p.get("student_id")
            if sid:
                sids.add(str(sid))
    return sids


# ─── Retention calculations ───────────────────────────────────────────────────

def week_sunday(d):
    """Return the Sunday that starts the Sun-Sat week containing d."""
    # d.weekday(): Mon=0 … Sun=6  →  offset to get preceding Sunday
    days_since_sunday = (d.weekday() + 1) % 7
    return d - timedelta(days=days_since_sunday)


def sun_sat_week(d):
    """Label for the Sun-Sat week containing d, e.g. '2025-W03'."""
    sun = week_sunday(d)
    # Week number = how many Sundays since Jan 1 of that year
    jan1 = date(sun.year, 1, 1)
    week_num = ((sun - jan1).days // 7) + 1
    return f"{sun.year}-W{week_num:02d}"


def cohort_retention_pct(cohort_students, milestone_days):
    """
    Of students in this cohort, what % had a lesson at least
    milestone_days after their first lesson?
    Returns None if the milestone date hasn't passed yet for this cohort.
    """
    today = date.today()
    result_rows = []
    for s in cohort_students:
        milestone_date = s["first_lesson"] + timedelta(days=milestone_days)
        if milestone_date > today:
            continue  # student too recent to measure, skip
        retained = any(d >= milestone_date for d in s["dates"])
        result_rows.append(retained)

    if not result_rows:
        return None  # no students measurable yet
    return round(sum(result_rows) / len(result_rows) * 100, 1)


def calc_risk_score(student, has_upcoming):
    """
    Churn risk score 1-10. Higher = more likely to churn soon.
    Only run on students who are already inactive (30+ days).
    """
    today         = date.today()
    days_inactive = (today - student["last_lesson"]).days
    score         = 1

    # Days since last lesson
    if days_inactive >= 60:
        score += 4
    elif days_inactive >= 30:
        score += 3

    # No upcoming lesson booked
    if not has_upcoming:
        score += 2

    # Frequency declining: 30 days before last lesson vs 30 days before that
    last = student["last_lesson"]
    recent = [d for d in student["dates"] if last - timedelta(days=30) <= d <= last]
    prior  = [d for d in student["dates"]
              if last - timedelta(days=60) <= d < last - timedelta(days=30)]
    if prior and len(recent) < len(prior):
        score += 2

    return min(score, 10)


# ─── Cohort rows ─────────────────────────────────────────────────────────────

def build_cohort_rows(students):
    """
    Group students by the Sun-Sat week of their first lesson.
    Returns list of row dicts sorted oldest to newest.
    """
    cohorts = defaultdict(list)
    for s in students.values():
        cohorts[sun_sat_week(s["first_lesson"])].append(s)

    rows = []
    for wk in sorted(cohorts.keys()):
        group = cohorts[wk]
        row = {
            "cohort_week":  wk,
            "week_end":     (week_sunday(group[0]["first_lesson"]) + timedelta(days=6)).isoformat(),
            "students":     len(group),
        }
        for m in MILESTONES:
            row[f"ret_{m}"] = cohort_retention_pct(group, m)
        rows.append(row)
    return rows


# ─── At-risk queue ────────────────────────────────────────────────────────────

def build_at_risk(students, upcoming_set):
    """
    Students with last lesson 30-89 days ago.
    90+ days = effectively churned, separate issue.
    Sorted by risk score descending.
    """
    today   = date.today()
    at_risk = []
    for sid, s in students.items():
        days_inactive = (today - s["last_lesson"]).days
        if days_inactive < 30 or days_inactive >= 90:
            continue
        has_upcoming = sid in upcoming_set
        score = calc_risk_score(s, has_upcoming)
        at_risk.append({
            "name":          s["name"],
            "last_lesson":   s["last_lesson"].isoformat(),
            "days_inactive": days_inactive,
            "upcoming":      "Yes" if has_upcoming else "No",
            "risk_score":    score,
        })
    return sorted(at_risk, key=lambda x: -x["risk_score"])


# ─── Google Sheets ────────────────────────────────────────────────────────────

def gspread_client():
    creds = Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_JSON, scopes=GOOGLE_SCOPES
    )
    # BackOffHTTPClient retries transient Sheets API errors (429/5xx) with
    # exponential backoff instead of killing the whole run on one 502.
    return gspread.authorize(creds, http_client=gspread.BackOffHTTPClient)


def get_or_create_sheet(gc):
    global GOOGLE_SHEET_ID
    if GOOGLE_SHEET_ID:
        log.info(f"Opening sheet: {GOOGLE_SHEET_ID}")
        return gc.open_by_key(GOOGLE_SHEET_ID)

    log.info("Creating new Google Sheet...")
    sh = gc.create("A+ Tutoring — Retention Tracker")
    sh.share(None, perm_type="anyone", role="reader")
    GOOGLE_SHEET_ID = sh.id

    log.info("=" * 60)
    log.info("NEW SHEET CREATED. Add this to your script:")
    log.info(f'  GOOGLE_SHEET_ID = "{GOOGLE_SHEET_ID}"')
    log.info(f"  URL: https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}")
    log.info("=" * 60)
    return sh


def get_tab(sh, name):
    try:
        return sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=name, rows=2000, cols=20)


def write_cohort_tab(sh, rows):
    ws = get_tab(sh, TAB_COHORT)
    headers = [
        "Cohort week", "Week ending (Sat)", "Students",
        "30-day %", "60-day %", "90-day %", "180-day %", "365-day %",
    ]
    data = [headers]
    for r in rows:
        data.append([
            r["cohort_week"],
            r["week_end"],
            r["students"],
            r["ret_30"]  if r["ret_30"]  is not None else "—",
            r["ret_60"]  if r["ret_60"]  is not None else "—",
            r["ret_90"]  if r["ret_90"]  is not None else "—",
            r["ret_180"] if r["ret_180"] is not None else "—",
            r["ret_365"] if r["ret_365"] is not None else "—",
        ])
    ws.clear()
    ws.update(data, "A1")
    ws.format("A1:H1", {"textFormat": {"bold": True}})
    ws.freeze(rows=1)
    log.info(f"  Cohort tab: {len(rows)} cohort weeks written")


def write_at_risk_tab(sh, at_risk):
    ws = get_tab(sh, TAB_AT_RISK)
    headers = [
        "Student name", "Last lesson", "Days inactive",
        "Upcoming?", "Risk score (1-10)",
    ]
    data = [headers]
    for r in at_risk:
        data.append([
            r["name"],
            r["last_lesson"],
            r["days_inactive"],
            r["upcoming"],
            r["risk_score"],
        ])
    ws.clear()
    ws.update(data, "A1")
    ws.format("A1:E1", {"textFormat": {"bold": True}})
    ws.freeze(rows=1)

    # Color-code the risk score column (batched to avoid rate limits)
    formats = []
    for i, r in enumerate(at_risk, start=2):
        score = r["risk_score"]
        if score >= 7:
            bg = {"red": 0.96, "green": 0.80, "blue": 0.80}   # red
        elif score >= 5:
            bg = {"red": 0.99, "green": 0.94, "blue": 0.75}   # amber
        else:
            bg = {"red": 0.85, "green": 0.94, "blue": 0.84}   # green
        formats.append({"range": f"E{i}", "format": {"backgroundColor": bg}})
    if formats:
        ws.batch_format(formats)

    log.info(f"  At-risk tab: {len(at_risk)} students written")


TAB_TRENDS = "Trends"


def _build_monthly_rows(cohort_rows):
    """Aggregate weekly cohort rows into monthly rows."""
    months = defaultdict(lambda: {"students": 0, "retained": {m: [] for m in MILESTONES}})
    for r in cohort_rows:
        month_key = r["week_end"][:7]  # "2024-01"
        months[month_key]["students"] += r["students"]
        for m in MILESTONES:
            val = r[f"ret_{m}"]
            if val is not None:
                # Weight by cohort size for accurate monthly average
                months[month_key]["retained"][m].append((val, r["students"]))

    rows = []
    for mk in sorted(months.keys()):
        md = months[mk]
        row = {"month": mk, "students": md["students"]}
        for m in MILESTONES:
            pairs = md["retained"][m]
            if pairs:
                total_students = sum(n for _, n in pairs)
                row[f"ret_{m}"] = round(sum(v * n for v, n in pairs) / total_students, 1)
            else:
                row[f"ret_{m}"] = None
        rows.append(row)
    return rows


def _build_rolling_rows(cohort_rows, window=4):
    """Compute rolling N-week average of each retention milestone."""
    rows = []
    for i in range(len(cohort_rows)):
        start = max(0, i - window + 1)
        window_rows = cohort_rows[start:i + 1]
        row = {"cohort_week": cohort_rows[i]["cohort_week"]}
        for m in MILESTONES:
            vals = [r[f"ret_{m}"] for r in window_rows if r[f"ret_{m}"] is not None]
            row[f"ret_{m}"] = round(sum(vals) / len(vals), 1) if vals else None
        rows.append(row)
    return rows


def _build_retention_curve(students):
    """Average retention curve: what % of all students are still active at day N."""
    today = date.today()
    day_points = [7, 14, 30, 45, 60, 90, 120, 150, 180, 270, 365]
    curve = []
    for days in day_points:
        eligible = [s for s in students.values()
                    if (today - s["first_lesson"]).days >= days]
        if not eligible:
            curve.append({"days": days, "pct": None})
            continue
        retained = sum(1 for s in eligible
                       if any(d >= s["first_lesson"] + timedelta(days=days) for d in s["dates"]))
        curve.append({"days": days, "pct": round(retained / len(eligible) * 100, 1)})
    return curve


def _build_monthly_retention_curves(students):
    """
    Build retention curves per cohort month.
    Returns dict: {"2024-01": [{"days": 7, "pct": 85.0}, ...], ...}
    """
    today = date.today()
    day_points = [7, 14, 30, 45, 60, 90, 120, 150, 180, 270, 365]

    # Group students by first-lesson month
    by_month = defaultdict(list)
    for s in students.values():
        by_month[s["first_lesson"].strftime("%Y-%m")].append(s)

    curves = {}
    for month_key in sorted(by_month.keys()):
        group = by_month[month_key]
        curve = []
        for days in day_points:
            eligible = [s for s in group
                        if (today - s["first_lesson"]).days >= days]
            if not eligible:
                curve.append(None)
                continue
            retained = sum(1 for s in eligible
                           if any(d >= s["first_lesson"] + timedelta(days=days)
                                  for d in s["dates"]))
            curve.append(round(retained / len(eligible) * 100, 1))
        curves[month_key] = curve
    return curves, day_points


def _make_chart(sheet_id, title, chart_type, domain_col, series_cols,
                total_rows, anchor_sheet_id, anchor_row, x_title, y_title):
    """Helper to build a Google Sheets addChart request."""
    return {
        "addChart": {
            "chart": {
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": anchor_sheet_id,
                            "rowIndex": anchor_row,
                            "columnIndex": 0,
                        },
                        "widthPixels": 1400,
                        "heightPixels": 500,
                    }
                },
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": chart_type,
                        "legendPosition": "BOTTOM_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": x_title},
                            {"position": "LEFT_AXIS", "title": y_title,
                             "viewWindowOptions": {"viewWindowMin": 0, "viewWindowMax": 100}},
                        ],
                        "domains": [{
                            "domain": {
                                "sourceRange": {
                                    "sources": [{
                                        "sheetId": sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": total_rows,
                                        "startColumnIndex": domain_col,
                                        "endColumnIndex": domain_col + 1,
                                    }]
                                }
                            }
                        }],
                        "series": [
                            {
                                "series": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": sheet_id,
                                            "startRowIndex": 0,
                                            "endRowIndex": total_rows,
                                            "startColumnIndex": c,
                                            "endColumnIndex": c + 1,
                                        }]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                            }
                            for c in series_cols
                        ],
                    },
                },
            }
        }
    }


def write_trends_tab(sh, cohort_rows, students):
    """Create Trends tab with three charts: monthly, retention curve, rolling avg."""
    # Delete existing tabs to start fresh
    for tab_name in [TAB_TRENDS, "Monthly Cohorts", "Retention Curve", "Rolling Average"]:
        try:
            sh.del_worksheet(sh.worksheet(tab_name))
        except gspread.exceptions.WorksheetNotFound:
            pass

    trends_ws = sh.add_worksheet(title=TAB_TRENDS, rows=100, cols=1)

    # ── 1. Monthly Cohorts data tab ──
    monthly_rows = _build_monthly_rows(cohort_rows)
    monthly_ws = sh.add_worksheet(title="Monthly Cohorts", rows=len(monthly_rows) + 1, cols=8)
    headers = ["Month", "Students", "30-day %", "60-day %", "90-day %", "180-day %", "365-day %"]
    data = [headers]
    for r in monthly_rows:
        data.append([
            r["month"], r["students"],
            r["ret_30"]  if r["ret_30"]  is not None else "",
            r["ret_60"]  if r["ret_60"]  is not None else "",
            r["ret_90"]  if r["ret_90"]  is not None else "",
            r["ret_180"] if r["ret_180"] is not None else "",
            r["ret_365"] if r["ret_365"] is not None else "",
        ])
    monthly_ws.update(data, "A1")
    monthly_ws.format("A1:G1", {"textFormat": {"bold": True}})
    monthly_ws.freeze(rows=1)

    # ── 2. Retention Curve data tab (per-month curves for YoY comparison) ──
    monthly_curves, day_points = _build_monthly_retention_curves(students)
    month_keys = sorted(monthly_curves.keys())
    num_cols = len(month_keys) + 1  # days column + one column per month
    curve_ws = sh.add_worksheet(title="Retention Curve",
                                rows=len(day_points) + 1, cols=num_cols)
    curve_headers = ["Days"] + month_keys
    curve_data = [curve_headers]
    for i, days in enumerate(day_points):
        row = [days]
        for mk in month_keys:
            val = monthly_curves[mk][i]
            row.append(val if val is not None else "")
        curve_data.append(row)
    curve_ws.update(curve_data, "A1")
    curve_ws.format(f"A1:{chr(65 + min(num_cols - 1, 25))}1", {"textFormat": {"bold": True}})
    curve_ws.freeze(rows=1)

    # ── 3. Rolling Average data tab ──
    rolling_rows = _build_rolling_rows(cohort_rows)
    rolling_ws = sh.add_worksheet(title="Rolling Average", rows=len(rolling_rows) + 1, cols=7)
    roll_headers = ["Cohort Week", "30-day %", "60-day %", "90-day %", "180-day %", "365-day %"]
    roll_data = [roll_headers]
    for r in rolling_rows:
        roll_data.append([
            r["cohort_week"],
            r["ret_30"]  if r["ret_30"]  is not None else "",
            r["ret_60"]  if r["ret_60"]  is not None else "",
            r["ret_90"]  if r["ret_90"]  is not None else "",
            r["ret_180"] if r["ret_180"] is not None else "",
            r["ret_365"] if r["ret_365"] is not None else "",
        ])
    rolling_ws.update(roll_data, "A1")
    rolling_ws.format("A1:F1", {"textFormat": {"bold": True}})
    rolling_ws.freeze(rows=1)

    # ── Build all three charts on the Trends tab ──
    charts = [
        _make_chart(
            sheet_id=monthly_ws.id,
            title="Monthly Cohort Retention Trends",
            chart_type="LINE",
            domain_col=0, series_cols=[2, 3, 4, 5, 6],
            total_rows=len(monthly_rows) + 1,
            anchor_sheet_id=trends_ws.id, anchor_row=0,
            x_title="Cohort Month", y_title="Retention %",
        ),
        _make_chart(
            sheet_id=curve_ws.id,
            title="Retention Curve by Cohort Month",
            chart_type="LINE",
            domain_col=0,
            series_cols=list(range(1, len(month_keys) + 1)),
            total_rows=len(day_points) + 1,
            anchor_sheet_id=trends_ws.id, anchor_row=28,
            x_title="Days Since First Lesson", y_title="Retention %",
        ),
        _make_chart(
            sheet_id=rolling_ws.id,
            title="4-Week Rolling Average Retention",
            chart_type="LINE",
            domain_col=0, series_cols=[1, 2, 3, 4, 5],
            total_rows=len(rolling_rows) + 1,
            anchor_sheet_id=trends_ws.id, anchor_row=56,
            x_title="Cohort Week", y_title="Retention %",
        ),
    ]

    sh.batch_update({"requests": charts})
    log.info("  Trends tab: 3 charts created (monthly, curve, rolling avg)")


# ─── Slack ────────────────────────────────────────────────────────────────────

def _yoy_comparison(cohort_rows):
    """Compare the latest measurable week to the same ISO week one year ago."""
    today = date.today()
    current_week = sun_sat_week(today)
    last_year_week = sun_sat_week(today - timedelta(weeks=52))

    by_week = {r["cohort_week"]: r for r in cohort_rows}

    comparisons = []
    for m in MILESTONES:
        # Find the latest week that has data for this milestone
        measurable = [r for r in cohort_rows if r[f"ret_{m}"] is not None]
        if not measurable:
            continue
        latest = measurable[-1]

        # Find the same ISO week last year
        latest_iso = latest["cohort_week"]
        year, wk_num = latest_iso.split("-W")
        prev_year_iso = f"{int(year) - 1}-W{wk_num}"
        prev = by_week.get(prev_year_iso)

        comp = {
            "milestone": f"{m}-day",
            "current_week": latest_iso,
            "current_pct": latest[f"ret_{m}"],
            "prev_week": prev_year_iso if prev else None,
            "prev_pct": prev[f"ret_{m}"] if prev and prev[f"ret_{m}"] is not None else None,
        }
        if comp["prev_pct"] is not None:
            diff = comp["current_pct"] - comp["prev_pct"]
            comp["delta"] = diff
            comp["arrow"] = "↑" if diff > 0 else ("↓" if diff < 0 else "→")
        else:
            comp["delta"] = None
            comp["arrow"] = "—"
        comparisons.append(comp)
    return comparisons


def _build_exec_summary(cohort_rows, at_risk, students):
    """Build executive summary lines for Slack and the sheet."""
    today = date.today()
    comparisons = _yoy_comparison(cohort_rows)

    active = sum(1 for s in students.values()
                 if (today - s["last_lesson"]).days <= 29)
    total = len(students)
    critical = sum(1 for r in at_risk if r["risk_score"] >= 7)

    summary = {
        "date": today.strftime("%b %d, %Y"),
        "total_students": total,
        "active_students": active,
        "at_risk_count": len(at_risk),
        "critical_count": critical,
        "comparisons": comparisons,
    }
    return summary


def write_exec_summary_tab(sh, cohort_rows, at_risk, students):
    """Write an Executive Summary tab with YoY comparisons."""
    tab_name = "Executive Summary"
    try:
        sh.del_worksheet(sh.worksheet(tab_name))
    except gspread.exceptions.WorksheetNotFound:
        pass

    summary = _build_exec_summary(cohort_rows, at_risk, students)
    ws = sh.add_worksheet(title=tab_name, rows=30, cols=7)

    data = [
        [f"A+ Retention — Executive Summary", "", "", "", "", ""],
        [f"Report date: {summary['date']}", "", "", "", "", ""],
        [""],
        ["OVERVIEW", "", "", "", "", ""],
        ["Total students (since Jan 2024)", summary["total_students"], "", "", "", ""],
        ["Currently active (last 29 days)", summary["active_students"], "", "", "", ""],
        ["At-risk (30-89 days inactive)", summary["at_risk_count"], "", "", "", ""],
        ["Critical (score 7+)", summary["critical_count"], "", "", "", ""],
        [""],
        ["YEAR-OVER-YEAR COMPARISON", "", "", "", "", ""],
        ["Milestone", "Current Week", "Current %", "Same Week Last Year", "Last Year %", "Change"],
    ]

    for c in summary["comparisons"]:
        arrow_val = ""
        if c["delta"] is not None:
            sign = "+" if c["delta"] > 0 else ""
            arrow_val = f"{c['arrow']} {sign}{c['delta']:.1f}pp"
        data.append([
            c["milestone"],
            c["current_week"],
            c["current_pct"],
            c["prev_week"] or "N/A",
            c["prev_pct"] if c["prev_pct"] is not None else "N/A",
            arrow_val,
        ])

    ws.update(data, "A1")

    # Formatting
    ws.format("A1", {"textFormat": {"bold": True, "fontSize": 14}})
    ws.format("A4", {"textFormat": {"bold": True, "fontSize": 12}})
    ws.format("A10", {"textFormat": {"bold": True, "fontSize": 12}})
    ws.format("A11:F11", {"textFormat": {"bold": True}})

    # Color the change column — green for positive, red for negative
    for i, c in enumerate(summary["comparisons"]):
        row = 12 + i  # 1-indexed
        if c["delta"] is not None:
            color = {"red": 0.2, "green": 0.7, "blue": 0.2} if c["delta"] > 0 else \
                    {"red": 0.8, "green": 0.2, "blue": 0.2} if c["delta"] < 0 else \
                    {"red": 0.5, "green": 0.5, "blue": 0.5}
            ws.format(f"F{row}", {"textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": color}}})

    ws.freeze(rows=0, cols=0)
    log.info("  Executive Summary tab: YoY comparison written")
    return summary


def post_to_slack(at_risk, cohort_rows, sheet_url, students):
    if not SLACK_WEBHOOK_URL:
        log.info("SLACK_WEBHOOK_URL not set — skipping Slack post")
        return

    summary = _build_exec_summary(cohort_rows, at_risk, students)

    lines = [
        f":bar_chart: *A+ Retention Report — {summary['date']}*",
        "",
        f"*Overview*",
        f"Active students: *{summary['active_students']}* of {summary['total_students']} total",
        f"At-risk: *{summary['at_risk_count']}*   Critical: *{summary['critical_count']}*",
        "",
    ]

    # Year-over-year comparison
    if summary["comparisons"]:
        lines.append("*Year-over-Year Comparison*")
        for c in summary["comparisons"]:
            if c["delta"] is not None:
                emoji = ":chart_with_upwards_trend:" if c["delta"] > 0 else \
                        ":chart_with_downwards_trend:" if c["delta"] < 0 else ":left_right_arrow:"
                sign = "+" if c["delta"] > 0 else ""
                lines.append(
                    f"{emoji} {c['milestone']}: *{c['current_pct']}%* "
                    f"({sign}{c['delta']:.1f}pp vs {c['prev_week']})"
                )
            else:
                lines.append(f":new: {c['milestone']}: *{c['current_pct']}%* (no YoY data)")
        lines.append("")

    # Top at-risk students
    if at_risk:
        lines.append("*Paola — top priority this week:*")
        for r in at_risk[:5]:
            flag = ":red_circle:" if r["risk_score"] >= 7 else ":yellow_circle:"
            upcoming_note = " (has upcoming lesson)" if r["upcoming"] == "Yes" else ""
            lines.append(
                f"{flag} {r['name']} — "
                f"{r['days_inactive']} days inactive, "
                f"score {r['risk_score']}/10{upcoming_note}"
            )
        if len(at_risk) > 5:
            lines.append(f"_...and {len(at_risk) - 5} more in the sheet_")
        lines.append("")

    lines.append(f"<{sheet_url}|Open retention sheet>")

    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json={"text": "\n".join(lines)}, timeout=10)
        resp.raise_for_status()
        log.info("Slack message posted")
    except Exception as e:
        log.warning(f"Slack post failed: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if DRY_RUN:
        log.info("DRY RUN MODE — no writes will occur")

    # Always fetch full history — retention milestones need complete lesson data
    lessons      = fetch_lessons(BACKFILL_START)
    upcoming     = fetch_upcoming()
    students     = build_students(lessons)
    upcoming_set = build_upcoming_set(upcoming)

    log.info(f"Unique students: {len(students)}")

    cohort_rows = build_cohort_rows(students)
    at_risk     = build_at_risk(students, upcoming_set)

    today        = date.today()
    active_count = sum(
        1 for s in students.values()
        if (today - s["last_lesson"]).days <= ACTIVE_DAYS
    )

    log.info(f"Active   (last lesson within {ACTIVE_DAYS} days): {active_count}")
    log.info(f"At-risk  (30-89 days inactive):                   {len(at_risk)}")
    log.info(f"Cohort weeks in sheet:                            {len(cohort_rows)}")

    if DRY_RUN:
        log.info("--- Sample cohort rows (last 3) ---")
        for r in cohort_rows[-3:]:
            log.info(f"  {r}")
        log.info("--- Top 5 at-risk ---")
        for r in at_risk[:5]:
            log.info(f"  {r}")
        return

    gc = gspread_client()
    sh = get_or_create_sheet(gc)

    write_cohort_tab(sh, cohort_rows)
    write_at_risk_tab(sh, at_risk)
    write_trends_tab(sh, cohort_rows, students)
    write_exec_summary_tab(sh, cohort_rows, at_risk, students)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sh.id}"
    log.info(f"Sheet updated: {sheet_url}")

    post_to_slack(at_risk, cohort_rows, sheet_url, students)

    log.info("Retention sync complete.")


if __name__ == "__main__":
    if not TEACHWORKS_API_KEY:
        raise EnvironmentError("TEACHWORKS_API_KEY not set")
    main()

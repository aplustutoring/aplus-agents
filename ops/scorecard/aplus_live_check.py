#!/usr/bin/env python3
"""
A+ Tutoring — Live Data Check
Pulls current week-to-date data from Teachworks and HubSpot.
Does NOT write to Monday.com — display only.

Usage:
  python3 aplus_live_check.py              # Current week (Sunday through today)
  python3 aplus_live_check.py --from 2026-03-01 --to 2026-03-07   # Custom range
"""

import argparse
from datetime import datetime, timedelta

from aplus_weekly_sync import (
    fetch_lessons_for_week,
    process_lessons,
    fetch_package_hours_fy,
    fetch_package_hours_week,
    fetch_new_students_week,
    fetch_inactive_families,
    fetch_72hr_turnaround,
    fetch_charter_active_deals,
    fetch_charter_pilots_signed,
    build_unmarked_tutor_analysis,
    build_missed_deals_analysis,
    JANELLE_RANGE,
    YOLANDA_RANGE,
)


def get_current_week_range():
    """Returns (sunday, today) for the in-progress week."""
    today = datetime.now().date()
    days_since_sunday = (today.weekday() + 1) % 7
    sunday = today - timedelta(days=days_since_sunday)
    return sunday, today


def main():
    parser = argparse.ArgumentParser(description="A+ Tutoring — Live Data Check")
    parser.add_argument("--from", dest="from_date", type=str,
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", type=str,
                        help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.from_date and args.to_date:
        start_date = datetime.strptime(args.from_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.to_date, "%Y-%m-%d").date()
        mode = "Custom range"
    else:
        start_date, end_date = get_current_week_range()
        mode = "Live (current week)"

    print(f"\n{'='*55}")
    print(f"  A+ Tutoring Live Check — {datetime.now().strftime('%A %B %d, %Y %I:%M %p')}")
    print(f"{'='*55}\n")
    print(f"📅 {mode}: {start_date} → {end_date}\n")

    # Teachworks data
    print("📥 Pulling Teachworks data...")
    lessons = fetch_lessons_for_week(start_date, end_date)
    metrics = process_lessons(lessons)
    package_hrs = fetch_package_hours_fy(end_date)
    pkg_units_wk = fetch_package_hours_week(start_date, end_date)
    new_students = fetch_new_students_week(start_date, end_date, week_lessons=lessons)
    print(f"   Lessons pulled: {len(lessons)}")

    print(f"\n   {'':20} {'Attended':>10} {'Cancelled':>10} {'No Show':>10} {'Unmarked':>10} {'Total':>10} {'Cancel%':>8} {'Unmrk%':>8}")
    print(f"   {'─'*88}")
    for label, key in [("Kath (Scheduled)", None), ("Janelle (A–L)", "janelle"),
                       ("Yolanda (M–Z)", "yolanda"), ("Company Total", "company")]:
        if key is None:
            print(f"   {label:20} {'':>10} {'':>10} {'':>10} {'':>10} {metrics['kath']['scheduled']:>10.2f}")
        else:
            m = metrics[key]
            print(f"   {label:20} {m['attended']:>10.2f} {m['cancelled']:>10.2f} {m['no_show']:>10.2f} {m['unmarked']:>10.2f} {m['total']:>10.2f} {m['cancel_rate']:>7.1f}% {m['unmarked_rate']:>7.1f}%")

    print(f"\n   Package hours YTD: {round(package_hrs, 2)}")
    print(f"   Package units this period: {round(pkg_units_wk, 2)}")
    print(f"   New students: {new_students}")

    # Unmarked tutor breakdown
    unmarked_by_tutor = metrics.get("unmarked_by_tutor", {})
    if unmarked_by_tutor:
        print(f"\n   📋 Unmarked lesson breakdown:")
        for line in build_unmarked_tutor_analysis(unmarked_by_tutor).split("\n"):
            print(f"   {line}")

    # Inactive families
    print(f"\n📥 Checking for inactive families (30-45 days from {end_date})...")
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

    # HubSpot data
    print(f"\n📥 Pulling HubSpot data...")
    post_lesson_pct, missed_deals, all_deal_schedulers = fetch_72hr_turnaround(start_date, end_date)

    janelle_total = all_deal_schedulers.count("janelle")
    yolanda_total = all_deal_schedulers.count("yolanda")
    janelle_missed = [d for d in missed_deals if d.get("scheduler") == "janelle"]
    yolanda_missed = [d for d in missed_deals if d.get("scheduler") == "yolanda"]
    janelle_72hr_pct = round(len(janelle_missed) / janelle_total * 100, 1) if janelle_total else 0
    yolanda_72hr_pct = round(len(yolanda_missed) / yolanda_total * 100, 1) if yolanda_total else 0

    print(f"   72-hr turnaround: {post_lesson_pct}% missed (company)")
    print(f"   Janelle: {janelle_72hr_pct}% missed ({len(janelle_missed)}/{janelle_total} deals)")
    print(f"   Yolanda: {yolanda_72hr_pct}% missed ({len(yolanda_missed)}/{yolanda_total} deals)")

    if missed_deals:
        print(f"\n   Deals that missed 72-hr window ({len(missed_deals)}):")
        for d in missed_deals:
            status = (f"still in pre-lesson ({d['pre_hours']}hrs)"
                      if not d["reached_post"]
                      else f"took {d['pre_hours']}hrs to reach Post-Lesson")
            print(f"     {d['name']:40} {d['pipeline']:15} {status}")

    charter_deals = fetch_charter_active_deals()
    pilots_signed = fetch_charter_pilots_signed()
    print(f"\n   Charter deals (Proposal/Negotiating): {charter_deals}")
    print(f"   Pilots signed (Closed Won): {pilots_signed}")

    print(f"\n{'='*55}")
    print(f"  ✅ Live check complete — no data written to Monday.com")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()

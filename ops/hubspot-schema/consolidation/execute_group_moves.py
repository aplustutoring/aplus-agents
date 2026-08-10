#!/usr/bin/env python3
"""One-off migration: move approved keeper contact properties into their persona
groups (consolidation proposal, approved by Roman 2026-08-10).

Moves ONLY — PATCH groupName on existing properties; internal names, types,
options, and data untouched. Idempotent: properties already in the target
group are skipped. Never touches HubSpot-defined properties.

Usage:
  python3 execute_group_moves.py --dry-run
  python3 execute_group_moves.py
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

TOKEN = os.getenv("HUBSPOT_API_KEY", "") or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "")
HS = "https://api.hubapi.com"

# name -> target persona group (from contacts-proposal.md, approved 2026-08-10)
MOVES = {
    # family
    "charter_school_family_": "family",
    "teacher_of_record_name": "family",
    "teacher_of_record_email_address": "family",
    "how_did_you_hear_about_us_": "family",
    "referral_name": "family",
    "parent_concerns_what_can_we_do_to_help_": "family",
    "what_is_your_child_s_current_grade_level_": "family",
    "parent_email": "family",
    "parent_first_name": "family",
    "parent_last_name": "family",
    "parent_phone_number": "family",
    "subject_need": "family",
    "online_or_in_person": "family",
    "student_school": "family",
    "student_additional_information": "family",
    "student_full_name_clone_": "family",
    "student_3_full_name": "family",
    "student_4_full_name": "family",
    "monday_schedule_preference": "family",
    "tuesday_schedule_preference": "family",
    "wednesday_schedule_preference": "family",
    "thursday_schedule_preference": "family",
    "friday_schedule_preference": "family",
    "saturday_schedule_preference": "family",
    "sunday_schedule_preference": "family",
    # tor
    "educational_facillitator_teacher_of_record": "tor",
    "charter_school_teacher": "tor",
    "last_tor_workflow_enrollment_date": "tor",
    "teacher_email_address": "tor",
    # tutor
    "a__pay_per_hour": "tutor",
    "resume": "tutor",
    "tutor_profile": "tutor",
    "online_in_person_": "tutor",
    "select_days_for_availability": "tutor",
    "what_subjects_do_you_feel_the_most_qualified_to_tutor_": "tutor",
    "completed_tutor_training": "tutor",
    "university_attended": "tutor",
    "degree_received": "tutor",
    # student
    "student_email_address": "student",
    "student_last_name": "student",
    "student_last_name_if_diff_from_parent": "student",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not TOKEN:
        sys.exit("HUBSPOT_API_KEY / HUBSPOT_PRIVATE_APP_TOKEN not set")
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

    groups = {g["name"] for g in requests.get(
        f"{HS}/crm/v3/properties/contacts/groups", headers=h, timeout=20).json()["results"]}
    missing = {g for g in MOVES.values()} - groups
    if missing:
        sys.exit(f"target groups missing in portal: {missing} — run create_properties.py first")

    moved = skipped = 0
    for name, target in MOVES.items():
        r = requests.get(f"{HS}/crm/v3/properties/contacts/{name}", headers=h, timeout=20)
        if r.status_code != 200:
            print(f"  {name}: GET {r.status_code} — SKIPPING ({r.text[:120]})")
            continue
        p = r.json()
        if p.get("hubspotDefined"):
            print(f"  {name}: hubspotDefined — never touch, SKIPPING")
            continue
        cur = p["groupName"]
        if cur == target:
            print(f"  {name}: already in {target}")
            skipped += 1
            continue
        print(f"  {name}: {cur} -> {target}" + (" (dry-run)" if args.dry_run else ""))
        if not args.dry_run:
            pr = requests.patch(f"{HS}/crm/v3/properties/contacts/{name}",
                                headers=h, json={"groupName": target}, timeout=20)
            if pr.status_code >= 400:
                print(f"    FAILED {pr.status_code}: {pr.text[:200]}")
                continue
        moved += 1
        time.sleep(0.2)
    print(f"\n{moved} {'would move' if args.dry_run else 'moved'}, {skipped} already in place.")


if __name__ == "__main__":
    main()

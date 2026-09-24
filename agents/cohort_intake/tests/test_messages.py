"""Copy the agent produces (spec §5.4, §5.7, §8): locked structure, dated
list from the one calendar, skip dates spelled out, no em dashes anywhere."""
from decimal import Decimal

from agents.cohort_intake import messages as M, rows as R
from agents.cohort_intake.tests import fixtures as F


def _g():
    return R.assemble_groups(F.parsed_group1())[0]


def test_es_email_has_calendar_skip_dates_and_no_em_dash():
    g = _g()
    subject, body = M.es_email(g, "kortiz@ieminc.org", g.dates)
    assert subject == "Your HSA English 9 group starts Sep 21: A+ Tutoring"
    assert "—" not in subject and "—" not in body and "--" not in body
    assert body.startswith("Hi Karen,")
    assert "starts Monday, September 21, 2026, Monday 10:00 AM PT, weekly through May 14, 2027" in body
    assert "Diego Reyna (grade 9, Ocean Grove Charter School)" in body
    assert "any request to change comes to you, not us" in body
    assert "Session calendar (all 25 dates): Sep 21 (2026)" in body
    assert "May 10" in body and "Nov 23 to 27" in body
    assert "reply here or text/call 818-869-1627" in body
    assert body.rstrip().endswith("A+ Tutoring Success Team")


def test_scheduler_handoff_names_skip_dates_count_and_deal_links():
    g = _g()
    text = M.scheduler_handoff(g, g.dates, {"IEM-1001": "https://hs/1"}, "Janelle")
    assert "Book *25 sessions* from Mon Sep 21, 2026" in text
    assert "through Mon May 10, 2027" in text
    assert "Skip dates (no session may be booked on these, LOCKED)" in text
    assert "Exact skipped Mondays: Nov 23, Nov 30, Dec 21, Dec 28, Jan 4, Jan 11, Mar 8, Mar 29, Apr 26" in text
    assert "Diego Reyna, grade 9" in text and "https://hs/1" in text and "(deal pending)" in text
    assert "—" not in text


def test_deal_description_follows_the_locked_structure():
    g = _g()
    desc = M.deal_description(g.rows[1], g, g.dates, Decimal("1250"), 25)
    lines = desc.splitlines()
    assert lines[0] == "IEM High School Academy English 9 Intervention, Cohort 1 (Group 1)"
    assert lines[1] == "Student: Maya Chen, grade 9, Ocean Grove Charter School (IEM ID IEM-1002)"
    assert lines[2] == "Parent: Lin Chen, lin.chen@gmail.com, +18185550102"
    assert lines[3] == "ES: Karen Ortiz, kortiz@ieminc.org"
    assert lines[4].startswith("Schedule: Monday 10:00 AM PT, weekly, Sep 21, 2026 through May 10, 2027. 25 one-hour")
    assert lines[5] == "Group: Diego Reyna, Owen Park"
    assert lines[6].startswith("Session calendar: ") and lines[7].startswith("No class: ")
    assert lines[8] == "Notes from school: (none)"
    assert lines[-1] == "Schedule is fixed by IEM; change requests go to the ES, not A+."


def test_plan_summary_lists_amounts_actions_and_refusals():
    g = _g()
    plans = {g.label: {"owner_name": "Janelle", "amounts": g.amounts,
                       "deal_actions": ["create", "update D2", "create"],
                       "family_actions": {r.student_id: "create" for r in g.rows},
                       "tor_actions": {"kortiz@ieminc.org": "create"}}}
    text = M.plan_summary([g], plans, ["row 7 (IEM-9): parent email is blank"], "dry-run")
    assert "3 student(s)" in text and "$1,250.00 → deal create" in text
    assert "⚠️ parent last name = student's" in text                 # Reyna flagged
    assert "Refused (fix the sheet, re-run)" in text and "IEM-9" in text
    assert "1 text + 1 welcome email per family" in text

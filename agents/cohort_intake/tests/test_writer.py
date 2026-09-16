"""HubSpot writer (spec §5.3, §5.4, §6): contacts fill-only, one deal per
student with the locked description, parity ownership, idempotent re-runs,
late-add re-split, enum labels looked up at run time."""
from datetime import date
from decimal import Decimal

import pytest

from agents.cohort_intake import rows as R, writer as W
from agents.cohort_intake.tests import fixtures as F, hsmock as H

TODAY = date(2026, 9, 15)


def _group(extra=()):
    return R.assemble_groups(F.parsed_group1(extra))[0]


def test_plan_group_1_english_9(monkeypatch):
    fake = H.FakeHS()
    H.wire(monkeypatch, fake)
    g = _group()
    plan = W.plan_group(g, TODAY)
    assert plan["owner_name"] == "Janelle" and plan["owner_id"] == "80047202"   # group 1 = odd
    assert plan["amounts"] == [Decimal("1250")] * 3 and plan["sessions"] == [25, 25, 25]
    assert plan["deal_actions"] == ["create", "create", "create"]
    assert plan["family_actions"] == {"IEM-1001": "create", "IEM-1002": "create", "IEM-1003": "create"}
    assert plan["tor_actions"] == {"kortiz@ieminc.org": "create"}


def test_execute_writes_contacts_deals_and_associations(monkeypatch):
    fake = H.FakeHS()
    recorded = H.wire(monkeypatch, fake)
    g = _group()
    outs = W.execute_group(g, W.plan_group(g, TODAY), TODAY, dry_run=False)
    # one ES contact, three family contacts
    emails = [c["properties"]["email"] for c in fake.created_contacts]
    assert emails.count("kortiz@ieminc.org") == 1 and len(emails) == 4
    tor = fake.contacts["kortiz@ieminc.org"]["properties"]
    assert tor["a_persona"] == "Teacher of Record/EF/ES" and tor["hubspot_owner_id"] == "227538487"
    assert tor["charter_school_teacher"] == "IEM Inc SS/OG/SM"
    assert tor["school_canonical"] == "Ocean Grove Charter School"
    fam = fake.contacts["reyna.family@gmail.com"]["properties"]
    assert (fam["firstname"], fam["lastname"]) == ("Reyna", "Reyna")           # flagged single name
    assert fam["a_persona"] == "Family" and fam["lifecyclestage"] == "customer"
    assert fam["charter_school_family_"] == "true" and fam["hubspot_owner_id"] == "80047202"
    assert fam["student_last_name"] == "Diego"                                  # label "Student FIRST Name"
    assert fam["student_last_name_if_diff_from_parent"] == "Reyna"
    assert fam["what_is_your_child_s_current_grade_level_"] == "9"
    assert fam["subject_need"] == "English Language Arts" and fam["student_email_address"] == "diego@ieminc.org"
    assert fam["teacher_of_record_email_address"] == "kortiz@ieminc.org"
    # three deals, correct props
    assert len(fake.created_deals) == 3 and all(o.deal_created for o in outs)
    d = fake.created_deals[0]["properties"]
    assert d["dealname"] == "Reyna - Diego Reyna - Ocean Grove Charter School - IEM HSA English 9"
    assert d["pipeline"] == "5119061" and d["dealstage"] == "5119062" and d["amount"] == "1250.00"
    assert d["hubspot_owner_id"] == "80047202" and d["online__inperson__charter"] == "ONLINE CHARTER"
    assert d["iem_student_id"] == "IEM-1001" and d["hsa_group"] == "C1-G1" and d["hsa_cohort"] == "1"
    assert d["hsa_sessions"] == "25" and d["hsa_start"] == "2026-09-21" and d["hsa_slot"] == "Monday 10:00 AM"
    assert d["number_of_hours_in_this_po"] == "25"
    assert d["start_of_tutoring_for_this_deal"] == "2026-09-21"
    assert d["date_of_last_lesson_in_this_deal"] == "2027-05-10" == d["lessons_fulfilled_date"]
    assert d["schedule_preferences"] == "Monday 10:00 AM PT weekly from Sep 21, 2026"
    assert d["monday_schedule_preference"] == "9AM-12PM"           # portal windows, not times
    assert d["tor_first_name"] == "Karen" and d["tor_last_name"] == "Ortiz"
    desc = d["description"]
    assert desc.startswith("IEM High School Academy English 9 Intervention, Cohort 1 (Group 1)")
    assert "Student: Diego Reyna, grade 9, Ocean Grove Charter School (IEM ID IEM-1001)" in desc
    assert "Group: Maya Chen, Owen Park" in desc
    assert "Session calendar: Sep 21 (2026), Sep 28" in desc and "No class: Nov 23 to 27" in desc
    assert "This deal = $1,250.00 (25 x $150 / 3 students)" in desc
    assert "Notes from school: 4th grade on i-Ready" in desc
    assert "—" not in desc
    # associations: family → TOR per student, TOR → deal per deal, family on the deal at create
    assert len(fake.assoc_cc) == 3 and len(fake.assoc_cd) == 3
    assert fake.created_deals[0]["contact_id"] == fake.contacts["reyna.family@gmail.com"]["id"]
    assert [r["action_taken"] for r in recorded] == ["cohort_deal_created"] * 3
    assert recorded[0]["message_id"] == "cohort:Ocean Grove Charter School|IEM-1001|english 9|26/27"


def test_existing_contacts_are_fill_only_but_gain_the_persona(monkeypatch):
    fake = H.FakeHS(contacts={"reyna.family@gmail.com": {
        "id": "C9", "properties": {"email": "reyna.family@gmail.com", "firstname": "Reyna",
                                   "lastname": "Garcia", "a_persona": "Student",
                                   "student_school": "Elsewhere"}}})
    H.wire(monkeypatch, fake)
    g = _group()
    W.execute_group(g, W.plan_group(g, TODAY), TODAY, dry_run=False)
    patch = [p for cid, p in fake.patched_contacts if cid == "C9"][0]
    assert "lastname" not in patch and "student_school" not in patch     # human values kept
    assert patch["a_persona"] == "Student;Family"                          # persona added
    assert patch["phone"] == "+18185550101" and patch["parent_email"] == "reyna.family@gmail.com"


def test_rerun_updates_the_same_deals_and_never_duplicates(monkeypatch):
    fake = H.FakeHS(deals=[
        H.existing_deal("IEM-1001", "Reyna - Diego Reyna - Ocean Grove Charter School - IEM HSA English 9"),
        H.existing_deal("IEM-1002", "Lin Chen - Maya Chen - Ocean Grove Charter School - IEM HSA English 9"),
        H.existing_deal("IEM-1003", "Susan Park - Owen Park - Ocean Grove Charter School - IEM HSA English 9")])
    recorded = H.wire(monkeypatch, fake)
    g = _group()
    plan = W.plan_group(g, TODAY)
    assert plan["deal_actions"] == ["update D1", "update D2", "update D3"]
    outs = W.execute_group(g, plan, TODAY, dry_run=False)
    assert fake.created_deals == [] and len(fake.patched_deals) == 3
    assert all(not o.deal_created for o in outs)
    assert fake.notes == []                                              # amount unchanged: no note
    assert {r["action_taken"] for r in recorded} == {"cohort_deal_updated"}


def test_late_add_resplits_and_gives_the_new_student_the_remaining_sessions(monkeypatch):
    fake = H.FakeHS(deals=[
        H.existing_deal("IEM-1001", "Reyna - Diego Reyna - Ocean Grove Charter School - IEM HSA English 9"),
        H.existing_deal("IEM-1002", "Lin Chen - Maya Chen - Ocean Grove Charter School - IEM HSA English 9"),
        H.existing_deal("IEM-1003", "Susan Park - Owen Park - Ocean Grove Charter School - IEM HSA English 9")])
    H.wire(monkeypatch, fake)
    late_day = date(2026, 10, 6)
    g = _group(extra=[F.LATE_ADD])
    plan = W.plan_group(g, late_day)
    assert plan["amounts"] == [Decimal("937.50")] * 4
    assert plan["sessions"] == [25, 25, 25, 22]
    assert plan["deal_actions"][:3] == [f"update D{i} (amount re-split)" for i in (1, 2, 3)]
    assert plan["deal_actions"][3] == "create (late add: 22 of 25 sessions)"
    outs = W.execute_group(g, plan, late_day, dry_run=False)
    assert [p["amount"] for _d, p in fake.patched_deals] == ["937.50"] * 3
    assert len(fake.notes) == 3 and "re-split: amount 1250 → 937.50" in fake.notes[0][1]
    new = fake.created_deals[0]["properties"]
    assert new["iem_student_id"] == "IEM-1004" and new["amount"] == "937.50"
    assert new["hsa_sessions"] == "22" and new["hsa_start"] == "2026-10-12"
    assert outs[3].start == date(2026, 10, 12)


def test_even_group_goes_to_the_m_z_seat(monkeypatch):
    fake = H.FakeHS()
    H.wire(monkeypatch, fake)
    idx = R.header_map(F.HEADERS)
    row = R.parse_row(9, F.TEST_001, idx, F.resolve_school)          # group 4
    g = R.assemble_groups([row])[0]
    plan = W.plan_group(g, TODAY)
    assert plan["owner_name"] == "Yolanda"
    W.execute_group(g, plan, TODAY, dry_run=False)
    assert fake.created_deals[0]["properties"]["hubspot_owner_id"] == "86868539"
    assert fake.created_deals[0]["properties"]["hsa_group"] == "C1-G4"


def test_missing_enum_option_is_skipped_and_reported_not_fatal(monkeypatch):
    fake = H.FakeHS(options={})
    H.wire(monkeypatch, fake)
    g = _group()
    outs = W.execute_group(g, W.plan_group(g, TODAY), TODAY, dry_run=False)
    assert len(fake.created_deals) == 3
    d = fake.created_deals[0]["properties"]
    assert "online__inperson__charter" not in d and "monday_schedule_preference" not in d
    assert any("no 'Charter' option" in s for s in outs[0].skipped_props)
    assert any("grade '9'" in s for s in outs[0].skipped_props)
    assert any("no window option covering 10:00 AM" in s for s in outs[0].skipped_props)


def test_slot_maps_to_the_portal_window_options(monkeypatch):
    H.wire(monkeypatch, H.FakeHS())
    from agents.cohort_intake import cohort as C
    assert W._window_value("monday_schedule_preference", C.parse_slot("Mon 10:00")) == "9AM-12PM"
    assert W._window_value("wednesday_schedule_preference", C.parse_slot("Wed 11:00")) == "9AM-12PM"
    assert W._window_value("wednesday_schedule_preference", C.parse_slot("Wed 3:00")) == "12PM-3PM"


def test_wrong_stage_label_refuses_to_write(monkeypatch):
    fake = H.FakeHS(stage="Closed Won")
    H.wire(monkeypatch, fake)
    g = _group()
    with pytest.raises(RuntimeError, match="not Pre-Lesson"):
        W.execute_group(g, W.plan_group(g, TODAY), TODAY, dry_run=False)
    assert fake.created_deals == [] and fake.created_contacts == []


def test_dry_run_execute_writes_nothing(monkeypatch):
    fake = H.FakeHS()
    H.wire(monkeypatch, fake)
    g = _group()
    outs = W.execute_group(g, W.plan_group(g, TODAY), TODAY, dry_run=True)
    assert fake.created_contacts == [] and fake.created_deals == []
    assert all(o.deal_id == "DRYRUN" for o in outs)

"""Pure-logic tests for the tutor-issue engine — no network, no state writes.

Run: python3 -m pytest ops/tutor-issues/tests/ -q  (from repo root)
"""
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("tutor_issues", HERE / "tutor_issues.py")
ti = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ti)


@pytest.fixture
def cfg():
    with open(HERE / "config.yml") as f:
        return yaml.safe_load(f)


# ── week + period math ───────────────────────────────────────────────────────

def test_last_complete_week_is_sun_sat():
    # Wed 2026-08-26 -> Sun 2026-08-16 .. Sat 2026-08-22
    start, end = ti.last_complete_week(date(2026, 8, 26))
    assert (start.isoformat(), end.isoformat()) == ("2026-08-16", "2026-08-22")
    assert start.weekday() == 6 and end.weekday() == 5


def test_last_complete_week_on_monday_uses_just_finished_week():
    start, end = ti.last_complete_week(date(2026, 8, 24))  # Monday
    assert end.isoformat() == "2026-08-22"


def test_period_weekly_vs_rolling(cfg):
    assert ti.period_key("missed_lesson_or_late", "2026-08-18", cfg).startswith("2026-W")
    assert ti.period_key("tutor_change_requested", "2026-08-18", cfg) == "30d-from-2026-08-18"
    assert ti.within_period("tutor_change_requested", "30d-from-2026-08-01",
                            "2026-08-26", cfg)
    assert not ti.within_period("tutor_change_requested", "30d-from-2026-07-01",
                                "2026-08-26", cfg)
    # weekly: same week updates, next week is a new ticket
    wk = ti.period_key("notes_not_completed", "2026-08-18", cfg)
    assert ti.within_period("notes_not_completed", wk, "2026-08-19", cfg)
    assert not ti.within_period("notes_not_completed", wk, "2026-08-25", cfg)


# ── scheduler split (same rule as the missed-lessons sync) ───────────────────

def test_scheduler_split(cfg):
    assert ti.scheduler_for_student("Alvarez, Ben", cfg) == "janelle"
    assert ti.scheduler_for_student("Martinez, Ana", cfg) == "yolanda"
    assert ti.scheduler_for_student("", cfg) == cfg["hubspot"]["roles"]["fallback_scheduler"]


# ── intake parsing ───────────────────────────────────────────────────────────

def test_intake_regex_strict():
    ok = ti.INTAKE_RE.match(
        'tutor-issue scheduling_flip_flop | jane@x.com | rescheduled 4x this month')
    assert ok and ok.group(1) == "scheduling_flip_flop"
    assert ti.INTAKE_RE.match("our tutor keeps cancelling, someone help") is None
    assert ti.INTAKE_RE.match("tutor-issue scheduling_flip_flop jane@x.com") is None


# ── one open ticket per tutor per type per period ────────────────────────────

TUTOR = {"contact_id": "101", "name": "Jane Doe", "email": "jane@x.com", "tw": "online:5"}


def _events(n, d="2026-08-18"):
    return [{"key": f"k{i}", "source_id": f"tw:online:{i}", "date": d,
             "student": "Alvarez, Ben", "status": "no_show"} for i in range(n)]


def test_same_run_merge_never_double_creates(cfg):
    plan = ti.Plan()
    ti.plan_ticket(plan, cfg, {}, TUTOR, "missed_lesson_or_late", _events(2),
                   source="test", evidence="e1")
    ti.plan_ticket(plan, cfg, {}, TUTOR, "missed_lesson_or_late", _events(1),
                   source="test", evidence="e2")
    assert len(plan.tickets) == 1
    assert plan.tickets[0]["props"]["tutor_issue_occurrences"] == 3


def test_recurrence_updates_open_ticket(cfg, monkeypatch):
    monkeypatch.setattr(ti, "get_ticket", lambda tid: {
        "properties": {"hs_pipeline_stage": "131537027",
                       "tutor_issue_occurrences": "2",
                       "tutor_issue_source_ids": "tw:online:0"}})
    idx = {"101:missed_lesson_or_late":
           {"ticket_id": "T1", "period": ti.period_key(
               "missed_lesson_or_late", "2026-08-18", cfg)}}
    plan = ti.Plan()
    ti.plan_ticket(plan, cfg, idx, TUTOR, "missed_lesson_or_late",
                   _events(1, "2026-08-19"), source="test", evidence="e")
    assert plan.tickets[0]["action"] == "update"
    assert plan.tickets[0]["props"]["tutor_issue_occurrences"] == 3


def test_closed_ticket_gets_fresh_one(cfg, monkeypatch):
    monkeypatch.setattr(ti, "get_ticket", lambda tid: {
        "properties": {"hs_pipeline_stage": cfg["hubspot"]["ticket"]["closed_stage"],
                       "tutor_issue_occurrences": "2",
                       "tutor_issue_source_ids": ""}})
    idx = {"101:missed_lesson_or_late":
           {"ticket_id": "T1", "period": ti.period_key(
               "missed_lesson_or_late", "2026-08-18", cfg)}}
    plan = ti.Plan()
    ti.plan_ticket(plan, cfg, idx, TUTOR, "missed_lesson_or_late",
                   _events(1, "2026-08-19"), source="test", evidence="e")
    assert plan.tickets[0]["action"] == "create"


def test_ticket_shape(cfg):
    plan = ti.Plan()
    ti.plan_ticket(plan, cfg, {}, TUTOR, "notes_not_completed", _events(2),
                   source="test", evidence="e")
    p = plan.tickets[0]["props"]
    assert p["hs_pipeline"] == "0" and p["hs_pipeline_stage"] == "131537027"
    assert p["hubspot_owner_id"] == cfg["staff"]["mandy"]["hubspot_owner_id"]
    assert p["ticket_source"] == "tutor_issues"
    assert p["hs_ticket_priority"] == "LOW"
    assert p["subject"].startswith("[Tutor Issue] Lesson notes not completed: Jane Doe")
    # outbound-style rule check on anything a human might paste: no em dashes
    assert "—" not in p["subject"] and "--" not in p["subject"]


# ── guards ───────────────────────────────────────────────────────────────────

def test_caps_abort_loudly_on_live_report_on_dry(cfg):
    plan = ti.Plan()
    for i in range(cfg["guards"]["max_tickets_per_run"] + 1):
        t = dict(TUTOR)
        t["contact_id"] = str(i)
        ti.plan_ticket(plan, cfg, {}, t, "missed_lesson_or_late", _events(1),
                       source="test", evidence="e")
    with pytest.raises(SystemExit, match="CAP EXCEEDED"):
        ti.enforce_caps(plan, cfg, dry_run=False)
    violations = ti.enforce_caps(plan, cfg, dry_run=True)
    assert violations and "CAP EXCEEDED" in violations[0]


def test_priority_mapping_covers_all_types(cfg):
    assert set(cfg["priority_by_type"]) == set(ti.ISSUE_TYPES)
    assert set(cfg["dedupe_period"]) == set(ti.ISSUE_TYPES)


# ── family resolution from the texting number (Roman 2026-09-10) ─────────────

def _contact(cid, persona="Family", first="Dana", last="Alvarez",
             surname="", email="dana@example.com", source=""):
    return {"id": cid, "properties": {
        "firstname": first, "lastname": last, "a_persona": persona,
        "email": email, "student_last_name": "",
        "student_last_name_if_diff_from_parent": surname,
        "hs_object_source_detail_1": source}}


def _families(monkeypatch, hits):
    monkeypatch.setattr(ti, "search_contacts_by_phone", lambda number: hits)


def test_phone_digits_normalizes_to_last_ten():
    assert ti.phone_digits("+1 (818) 573-6644") == "8185736644"
    assert ti.phone_digits("18185736644") == "8185736644"
    assert ti.phone_digits("573-6644") == ""


def test_find_family_none_when_nothing_matches(monkeypatch):
    _families(monkeypatch, [])
    assert ti.find_family_by_phone("+18185550100") is None


def test_find_family_returns_the_single_family(monkeypatch):
    _families(monkeypatch, [_contact("555")])
    fam = ti.find_family_by_phone("+18185550100")
    assert fam["id"] == "555" and fam["lastname"] == "Alvarez"
    assert "Family" in fam["a_persona"]


def test_find_family_refuses_when_several_match(monkeypatch):
    _families(monkeypatch, [_contact("555"), _contact("556", last="Nguyen")])
    plan = ti.Plan()
    assert ti.find_family_by_phone("+18185550100", plan=plan) is None
    assert plan.refusals and "555" in plan.refusals[0]["reason"]


def test_find_family_refuses_a_tutor_texting_about_themselves(monkeypatch):
    _families(monkeypatch, [_contact("777", persona="Tutors", first="Christa",
                                     last="Bretz")])
    assert ti.find_family_by_phone("+18183395667") is None


def test_find_family_refuses_a_teacher_of_record(monkeypatch):
    _families(monkeypatch, [_contact("888", persona="Teacher of Record/EF/ES")])
    assert ti.find_family_by_phone("+18185550100") is None


def test_find_family_skips_callrail_shells(monkeypatch):
    _families(monkeypatch, [
        _contact("900", persona="", first="Inglewood", last="Ca", email="",
                 source="CallRail"),
        _contact("901")])
    assert ti.find_family_by_phone("+18185550100")["id"] == "901"


# ── both contacts land on the ticket ─────────────────────────────────────────

def _capture_create(monkeypatch):
    seen = {}

    def fake(method, path, payload=None, params=None):
        seen["method"], seen["path"], seen["payload"] = method, path, payload
        return {"id": "T9"}
    monkeypatch.setattr(ti, "hs_req", fake)
    return seen


def test_create_ticket_carries_tutor_then_family(monkeypatch):
    seen = _capture_create(monkeypatch)
    ti.create_ticket({"subject": "s"}, ["101", "555"])
    assocs = seen["payload"]["associations"]
    assert [a["to"]["id"] for a in assocs] == ["101", "555"]
    assert all(a["types"][0]["associationTypeId"] == 16 for a in assocs)
    assert all(a["types"][0]["associationCategory"] == "HUBSPOT_DEFINED"
               for a in assocs)


def test_create_ticket_one_association_without_a_family(monkeypatch):
    seen = _capture_create(monkeypatch)
    ti.create_ticket({"subject": "s"}, ["101", None, "101"])
    assert [a["to"]["id"] for a in seen["payload"]["associations"]] == ["101"]


FAMILY = {"id": "555", "firstname": "Dana", "lastname": "Alvarez",
          "a_persona": "Family", "student_last_name": "Zoe",
          "student_surname": ""}


def _late(cfg, family=None, issue="missed_lesson_or_late", quote=None):
    plan = ti.Plan()
    ti.plan_ticket(plan, cfg, {}, TUTOR, issue, _events(1),
                   source="family text (SMS)", evidence="tutor never showed",
                   family=family, quote=quote)
    return plan.tickets[0]


def test_late_report_associates_both_contacts(cfg):
    assert _late(cfg, FAMILY)["contact_ids"] == ["101", "555"]


def test_report_without_a_family_stays_tutor_only(cfg):
    assert _late(cfg)["contact_ids"] == ["101"]


# ── routing: the scheduler owns a tutor-late text, not Operations ────────────

def test_late_report_routes_a_to_l_to_janelle(cfg):
    t = _late(cfg, FAMILY)
    assert t["owner_role"] == "janelle"
    assert t["props"]["hubspot_owner_id"] == cfg["staff"]["janelle"]["hubspot_owner_id"]


def test_late_report_routes_m_to_z_to_yolanda(cfg):
    fam = dict(FAMILY, lastname="Martinez")
    t = _late(cfg, fam)
    assert t["owner_role"] == "yolanda"
    assert t["props"]["hubspot_owner_id"] == cfg["staff"]["yolanda"]["hubspot_owner_id"]


def test_routing_uses_the_student_surname_not_student_last_name(cfg):
    # student_last_name is labelled "Student FIRST Name" in the registry, so a
    # student called Zoe Martinez under parent Alvarez must route M-Z.
    fam = dict(FAMILY, student_surname="Martinez")
    assert _late(cfg, fam)["owner_role"] == "yolanda"
    # and the parent's lastname is the fallback when no student surname is set
    assert ti.family_routing_surname(FAMILY) == "Alvarez"


def test_late_report_without_a_family_stays_with_operations(cfg):
    t = _late(cfg)
    ops = cfg["hubspot"]["roles"]["operations"]
    assert t["props"]["hubspot_owner_id"] == cfg["staff"][ops]["hubspot_owner_id"]


def test_other_categories_keep_operations_even_with_a_family(cfg):
    t = _late(cfg, FAMILY, issue="tutor_change_requested")
    ops = cfg["hubspot"]["roles"]["operations"]
    assert t["props"]["hubspot_owner_id"] == cfg["staff"][ops]["hubspot_owner_id"]
    assert t["owner_role"] == ops


# ── the family's own words on the ticket ─────────────────────────────────────

QUOTE = {"text": "Hi, Marcus still isn't here and it's 4:09. Should we wait?",
         "sender": "+18185550100", "line": "+18186869627",
         "received": "2026-09-10 16:09:00"}


def test_description_quotes_the_text_verbatim(cfg):
    body = _late(cfg, FAMILY, quote=QUOTE)["props"]["content"]
    assert QUOTE["text"] in body
    assert "+18185550100" in body and "+18186869627" in body
    assert "2026-09-10 16:09:00" in body
    assert "Family: Dana Alvarez (contact 555)" in body


def test_quote_is_trimmed_to_500_chars(cfg):
    long_quote = dict(QUOTE, text="late " * 300)
    body = _late(cfg, FAMILY, quote=long_quote)["props"]["content"]
    quoted = body.split('"')[1]
    assert len(quoted) <= 500


# ── the config block is the switch: flags off reproduces today's behavior ────

@pytest.fixture
def cfg_flags_off(cfg):
    c = json.loads(json.dumps(cfg))
    c["late_reports"] = {"enabled": True, "route_to_scheduler": False,
                         "associate_family": False}
    return c


def test_flags_off_reproduces_todays_behavior(cfg_flags_off):
    t = _late(cfg_flags_off, FAMILY, quote=QUOTE)
    ops = cfg_flags_off["hubspot"]["roles"]["operations"]
    assert t["contact_ids"] == ["101"]
    assert t["props"]["hubspot_owner_id"] == cfg_flags_off["staff"][ops]["hubspot_owner_id"]


def test_missing_late_reports_block_reproduces_todays_behavior(cfg):
    c = json.loads(json.dumps(cfg))
    c.pop("late_reports", None)
    t = _late(c, FAMILY, quote=QUOTE)
    ops = c["hubspot"]["roles"]["operations"]
    assert t["contact_ids"] == ["101"]
    assert t["props"]["hubspot_owner_id"] == c["staff"][ops]["hubspot_owner_id"]


def test_config_ships_the_flags_on(cfg):
    lr = cfg["late_reports"]
    assert lr["enabled"] and lr["route_to_scheduler"] and lr["associate_family"]

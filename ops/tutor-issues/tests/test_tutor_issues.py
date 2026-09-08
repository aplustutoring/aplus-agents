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

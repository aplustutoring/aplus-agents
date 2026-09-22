"""Guardrail tests for ops/lead_agent. No network, no API key.

These test the half that Claude cannot argue with. Every case is a real failure
from docs/investigations/2026-09-14-online-lead-intake.md or the 2026-09-09
Gonzalez incident.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import lead_agent as la  # noqa: E402

C = la.cfg()
PT = ZoneInfo("America/Los_Angeles")
NOON = datetime(2026, 9, 22, 12, 0, tzinfo=PT).astimezone(timezone.utc)


def dossier(**kw):
    base = {"contact": {"firstname": "Olga", "lastname": "Vus"}, "in_thread": False,
            "returning": "", "gate": {"verdict": "allow", "reasons": []},
            "evidence": {"calls_outbound": 0, "calls_connected": 0, "meetings": 0,
                         "deals": 0, "replied": 0},
            "touches": {"outbound_today": 0, "hours_since_last_outbound": None}}
    base.update(kw)
    return base


def send(**kw):
    d = {"action": "send_sms", "sms_body": "Hi Olga, quick question about Nika.",
         "confidence": "high", "why": "no signal in 12h", "read": "", "signal": ""}
    d.update(kw)
    return d


# ── the defect that started this: a status with no evidence ────────
def test_attempting_to_contact_needs_a_real_call():
    """F1. The old flow stamped this on a timer and emailed families 'we could
    not leave a voicemail' with nobody having dialed."""
    ok, why = la.evidence_ok("ATTEMPTED_TO_CONTACT", dossier(), C)
    assert not ok and "calls_outbound" in why


def test_attempting_to_contact_is_allowed_once_a_call_exists():
    d = dossier(evidence={"calls_outbound": 1, "calls_connected": 0, "meetings": 0, "deals": 0, "replied": 0})
    assert la.evidence_ok("ATTEMPTED_TO_CONTACT", d, C)[0]


def test_meeting_booked_needs_a_meeting():
    assert not la.evidence_ok("Meeting Booked", dossier(), C)[0]
    assert la.evidence_ok("Meeting Booked", dossier(
        evidence={"meetings": 1, "calls_outbound": 0, "calls_connected": 0, "deals": 0, "replied": 0}), C)[0]


def test_unqualified_is_never_the_agents_call():
    ok, why = la.evidence_ok("UNQUALIFIED", dossier(), C)
    assert not ok and "never an agent decision" in why


def test_an_unproven_status_becomes_a_task_not_a_write():
    d, notes = la.enforce({"action": "set_status", "new_status": "ATTEMPTED_TO_CONTACT",
                           "confidence": "high", "why": "x"}, dossier(), C, now=NOON)
    assert d["action"] == "create_task"
    assert any("calls_outbound" in n for n in notes)


# ── copy rules applied in code, not requested in a prompt ──────────
def test_em_dashes_and_double_hyphens_never_reach_a_customer():
    assert "—" not in la.scrub("Hi — there")
    assert "--" not in la.scrub("Hi -- there")
    d, _ = la.enforce(send(sms_body="Hi Olga — we can help -- really."), dossier(), C, now=NOON)
    assert "—" not in d["sms_body"] and "--" not in d["sms_body"]


def test_a_cold_text_gets_a_stop_line_added():
    d, notes = la.enforce(send(), dossier(), C, now=NOON)
    assert "STOP" in d["sms_body"] and any("STOP" in n for n in notes)


def test_a_reply_in_thread_needs_no_stop_line():
    d, _ = la.enforce(send(), dossier(in_thread=True), C, now=NOON)
    assert d["sms_body"].count("STOP") == 0


def test_an_empty_body_never_sends():
    d, notes = la.enforce(send(sms_body="   "), dossier(), C, now=NOON)
    assert d["action"] == "create_task" and any("empty" in n for n in notes)


# ── frequency and hours, counted from the record ───────────────────
def test_a_second_touch_the_same_day_is_held():
    """The Gonzalez failure: three texts, two numbers, one afternoon."""
    d, notes = la.enforce(send(), dossier(
        touches={"outbound_today": 1, "hours_since_last_outbound": 30}), C, now=NOON)
    assert d["action"] == "create_task" and any("already contacted today" in n for n in notes)


def test_a_touch_inside_the_gap_is_held():
    d, notes = la.enforce(send(), dossier(
        touches={"outbound_today": 0, "hours_since_last_outbound": 3}), C, now=NOON)
    assert d["action"] == "create_task" and any("inside the" in n for n in notes)


def test_nothing_goes_out_at_two_in_the_morning():
    two_am = datetime(2026, 9, 22, 2, 0, tzinfo=PT).astimezone(timezone.utc)
    d, notes = la.enforce(send(), dossier(), C, now=two_am)
    assert d["action"] == "create_task" and any("working window" in n for n in notes)


def test_the_window_is_pacific_not_utc():
    """12:00 PT is 19:00 UTC. A window compared in UTC would reject it."""
    assert la.in_window(NOON, C)


# ── confidence, and the draft ceiling ──────────────────────────────
def test_medium_confidence_is_a_humans_call():
    d, notes = la.enforce(send(confidence="medium"), dossier(), C, now=NOON)
    assert d["action"] == "create_task" and any("below the send bar" in n for n in notes)


def test_send_off_turns_every_outbound_into_a_draft():
    """knowledge/journey 00 + 01 are not REVIEWED, so nothing reaches a person."""
    assert C["send"] is False
    d, notes = la.enforce(send(), dossier(), C, now=NOON)
    assert d["action"] == "create_task"
    assert d["drafted_channel"] == "send_sms"
    assert any("not REVIEWED" in n for n in notes)


def test_a_blocked_send_becomes_a_task_never_silence():
    """Silence is how the old flow lost people. Every held send still surfaces."""
    for kw in ({"confidence": "low"}, {"sms_body": ""}):
        d, _ = la.enforce(send(**kw), dossier(), C, now=NOON)
        assert d["action"] == "create_task"


def test_wait_and_nothing_survive_untouched():
    for act in ("wait", "nothing"):
        d, notes = la.enforce({"action": act, "confidence": "high", "why": "they booked"},
                              dossier(), C, now=NOON)
        assert d["action"] == act and notes == []


def test_an_unknown_action_is_never_executed():
    d, notes = la.enforce({"action": "delete_everything", "confidence": "high"}, dossier(), C, now=NOON)
    assert d["action"] == "create_task" and any("unknown action" in n for n in notes)


# ── the task a human opens ─────────────────────────────────────────
def test_the_task_carries_the_reasoning_the_draft_and_why_it_was_held():
    d, notes = la.enforce(send(why="two days quiet after opening both emails"), dossier(
        returning="RETURNING FAMILY: 2 prior deal(s) where tutoring started."), C, now=NOON)
    subj, body = la.task_from(d, dossier(returning="RETURNING FAMILY: 2 prior deal(s)."), notes)
    assert "Olga" in subj
    assert "two days quiet" in body
    assert "DRAFT SMS" in body and "HELD BACK BY" in body
    assert "RETURNING FAMILY" in body


def test_the_decision_schema_covers_every_action():
    assert set(la.DECISION_SCHEMA["properties"]["action"]["enum"]) == set(la.ACTIONS)
    assert la.DECISION_SCHEMA["additionalProperties"] is False

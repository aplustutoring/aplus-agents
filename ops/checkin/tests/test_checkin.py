"""The check-in: copy quality, the gate, and the triage that was missing.

Every reply quoted below is verbatim from the week of 2026-09-10, when the
ungated campaign produced them and nothing acted on them.
"""
import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

HERE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("checkin", HERE / "checkin.py")
ck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ck)
PT = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def cfg():
    with open(HERE / "config.yml") as f:
        return yaml.safe_load(f)


# ── copy ─────────────────────────────────────────────────────────────────────

def test_copy_names_the_tutor_and_the_student(cfg):
    body = ck.render(cfg, "Albee Li", "Emma Li", "Jessica Moreno")
    assert "Albee" in body and "Emma" in body and "Jessica" in body


def test_copy_uses_first_names_only(cfg):
    """LOCKED 2026-09-09: students, parents and tutors by first name in
    anything a family reads."""
    body = ck.render(cfg, "Albee Li", "Emma Li", "Jessica Moreno")
    for surname in ("Li", "Moreno"):
        assert f" {surname}" not in body


def test_copy_has_no_em_dashes(cfg):
    for body in (ck.render(cfg, "Albee", "Emma", "Jessica"),
                 ck.render(cfg, "Albee", "Emma", "")):
        assert "—" not in body and "--" not in body


def test_copy_asks_what_to_focus_on_next(cfg):
    """"How is it going" gets "fine". Asking what to focus on NEXT is what got
    Miran's missing homework and Albee's missing lesson plan."""
    assert "focus on next" in ck.render(cfg, "A", "B", "C")


def test_copy_falls_back_cleanly_with_no_tutor(cfg):
    body = ck.render(cfg, "Albee", "Emma", "")
    assert "Emma" in body and "{" not in body


# ── tutor name extraction ────────────────────────────────────────────────────

def test_tutor_pulled_from_the_schedule():
    assert ck.tutor_from_schedule("Mondays 10:00 AM with Sonya") == "Sonya"


def test_tutor_from_the_last_comma_first_shape():
    """Deals written before 2026-09-16 kept the raw Teachworks value. Taking
    the token after "with" gives the SURNAME, which is what told Nikita Brixey
    her son's tutor was "Karl"."""
    assert ck.tutor_from_schedule(
        "Tuesdays 6:00 PM with Seifeldin, Youssef") == "Youssef"
    assert ck.tutor_from_schedule(
        "Mondays 10:00 AM with Karl, Sonya, Mondays 10:30 AM with Karl, Sonya") == "Sonya"


def test_two_tutors_means_name_neither():
    """Telling a parent the wrong tutor's name is worse than naming none."""
    s = "Mondays 10:00 AM with Sonya, Fridays 2:00 PM with Kelly"
    assert ck.tutor_from_schedule(s) == ""


def test_unknown_first_name_is_refused():
    """The 2026-09-17 dry run produced "sessions with Siddiqui", a surname.
    A name that is nobody's first name does not go in front of a parent."""
    known = {"sonya", "youssef", "kelly"}
    assert ck.tutor_from_schedule("Mondays with Siddiqui", known) == ""
    assert ck.tutor_from_schedule("Mondays with Sonya", known) == "Sonya"


def test_no_schedule_means_no_tutor():
    assert ck.tutor_from_schedule("") == ""
    assert ck.tutor_from_schedule(None) == ""
    assert ck.tutor_from_schedule("we don't have your schedule on file yet") == ""


# ── the first-name helper, and the bug it exists for ─────────────────────────

def test_first_name_handles_teachworks_last_comma_first():
    assert ck.first_name("Karl, Sonya") == "Sonya"
    assert ck.first_name("Sonya Karl") == "Sonya"
    assert ck.first_name("Torres,") == "Torres"
    assert ck.first_name("") == ""


# ── the gate ─────────────────────────────────────────────────────────────────

def test_send_window_is_business_hours(cfg):
    assert ck.in_send_window(cfg, datetime(2026, 9, 17, 10, 0, tzinfo=PT))
    assert not ck.in_send_window(cfg, datetime(2026, 9, 17, 7, 0, tzinfo=PT))
    assert not ck.in_send_window(cfg, datetime(2026, 9, 17, 20, 0, tzinfo=PT))


def test_no_sends_at_the_weekend(cfg):
    assert not ck.in_send_window(cfg, datetime(2026, 9, 19, 10, 0, tzinfo=PT))  # Saturday
    assert not ck.in_send_window(cfg, datetime(2026, 9, 20, 10, 0, tzinfo=PT))  # Sunday


def test_gate_settings_that_stop_the_albee_case(cfg):
    """Albee Li got the robot 15 minutes after a scheduler had apologised to
    her about the very lesson she was complaining about."""
    assert cfg["gate"]["skip_if_message_within_hours"] >= 24
    assert cfg["gate"]["skip_if_open_ticket"] is True
    assert cfg["gate"]["max_per_family_per_day"] == 1


def test_ships_disarmed(cfg):
    assert cfg["armed"] is False


# ── triage: the replies nothing used to catch ────────────────────────────────

def test_catches_a_family_leaving_over_price(cfg):
    """Judy Goldzweig, 2026-09-15. She was answered with "let me know if
    there's any other way I can assist" and left."""
    kind, _ = ck.classify(
        "Hi, we are exploring other services before we make a final decision. "
        "So no lessons until further notice", cfg)
    assert kind == "churn"


def test_catches_a_service_gap(cfg):
    """Miran Mavlan and Albee Li, both 2026-09-15, both real problems nobody
    had reported through any other channel."""
    assert ck.classify("My only concern would be she has no homework or book "
                       "to follow", cfg)[0] == "gap"
    assert ck.classify("we just do not know the plan, so she not able to "
                       "preview for the class", cfg)[0] == "gap"


def test_catches_a_student_who_never_started(cfg):
    assert ck.classify("Zahavi is supposed to start tutoring but hasn't", cfg)[0] == "gap"


def test_a_happy_reply_makes_no_ticket(cfg):
    for good in ("Hi, all the lessons went amazing. You were totally right.",
                 "They're going well. He's enjoying working with Youssef",
                 "Thank you!", ""):
        assert ck.classify(good, cfg)[0] == ""


def test_tickets_route_to_the_students_scheduler(cfg):
    key, staff = ck.scheduler_for(cfg, "Brixey")
    assert key == cfg["schedulers"]["a_to_l"]
    key, staff = ck.scheduler_for(cfg, "Soroudi")
    assert key == cfg["schedulers"]["m_to_z"]
    assert staff["hubspot_owner_id"]


# ── deal parsing ─────────────────────────────────────────────────────────────

def test_parent_and_student_from_the_deal_name():
    par, stu = ck.parent_student("Mary Gonzalez - Andrew Gonzalez - iLead 1 - 26/27")
    assert par == "Mary Gonzalez" and stu == "Andrew Gonzalez"
    assert ck.parent_student("") == ("", "")


def test_texts_fetch_starts_at_page_zero(cfg, monkeypatch):
    """page=1 skips the newest 100 texts, which is what made a monitor report
    "quiet" for ten hours on 2026-09-12."""
    seen = []

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"data": []}

    monkeypatch.setattr(ck.requests, "get",
                        lambda url, headers=None, timeout=None, params=None:
                        (seen.append(params.get("page")), R())[1])
    ck.jc_texts(24)
    assert seen[0] == 0

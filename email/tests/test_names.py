"""One definition of the customer-facing first name, and the two real texts
that went out wrong before it existed."""
from src.names import first_name
from src.po_inbox import _schedule_text


def test_teachworks_last_comma_first():
    # 2026-09-16, sent to Nikita Brixey: "Mondays 10:00 AM with Karl, Sonya".
    # Karl is Sonya's surname. She replied "I don't know who Karl is?"
    assert first_name("Karl, Sonya") == "Sonya"


def test_plain_first_last():
    assert first_name("Sonya Karl") == "Sonya"


def test_single_name():
    assert first_name("Sonya") == "Sonya"


def test_trailing_comma_falls_back_to_the_surname():
    # 2026-09-09, the low-balance replay texted a family about "Torres,".
    # A surname reads better in a sentence than a blank.
    assert first_name("Torres,") == "Torres"


def test_blank_and_none():
    assert first_name("") == ""
    assert first_name(None) == ""
    assert first_name("   ") == ""


def test_schedule_text_uses_the_first_name_only():
    lessons = [{"date": "2026-09-21", "time": "10:00", "tutor": "Karl, Sonya"},
               {"date": "2026-09-28", "time": "10:00", "tutor": "Karl, Sonya"}]
    out = _schedule_text(lessons)
    assert "with Sonya" in out
    assert "Karl" not in out


def test_schedule_text_groups_one_tutor_into_one_slot():
    """The comma used to split one tutor across what looked like two people."""
    lessons = [{"date": "2026-09-21", "time": "10:00", "tutor": "Karl, Sonya"},
               {"date": "2026-09-28", "time": "10:00", "tutor": "Sonya Karl"}]
    out = _schedule_text(lessons)
    assert out.count("Sonya") == 1


def test_schedule_text_survives_a_missing_tutor():
    lessons = [{"date": "2026-09-21", "time": "10:00", "tutor": ""}]
    out = _schedule_text(lessons)
    assert out.startswith("Mondays")
    assert "with" not in out


def test_low_balance_shares_the_definition():
    from src import low_balance
    assert low_balance._first_name("Karl, Sonya") == "Sonya"

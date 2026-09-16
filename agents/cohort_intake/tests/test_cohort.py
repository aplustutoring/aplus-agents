"""Cohort table, session calendar and amount split (spec §2, §5.4, §9 1c)."""
from datetime import date
from decimal import Decimal

import pytest

from agents.cohort_intake import cohort as c


# ─── cohort resolution ────────────────────────────────────────────────────────

def test_cohort_comes_from_the_start_date():
    co = c.resolve_cohort("1, 9/21/26")
    assert (co.number, co.sessions, co.group_total) == (1, 25, Decimal("3750"))


@pytest.mark.parametrize("cell,n,sessions", [
    ("2, 10/19/26", 2, 21), ("3, 11/9/26", 3, 18), ("4, 1/25/27", 4, 13),
    ("5, 2/8/27", 5, 11), ("6, 3/15/27", 6, 7), ("9/21/2026", 1, 25),
])
def test_every_cohort_start_resolves(cell, n, sessions):
    co = c.resolve_cohort(cell)
    assert (co.number, co.sessions) == (n, sessions)


def test_leading_number_never_overrides_the_date():
    with pytest.raises(c.CohortError, match="says 2 but start 9/21/26 is cohort 1"):
        c.resolve_cohort("2, 9/21/26")


def test_unknown_start_is_refused():
    with pytest.raises(c.CohortError, match="not a cohort start"):
        c.resolve_cohort("1, 9/22/26")


# ─── slots ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,label", [
    ("Mon 10:00 AM", "Monday 10:00 AM"), ("Monday 10am", "Monday 10:00 AM"),
    ("Wed 11:00 AM", "Wednesday 11:00 AM"), ("Wed 3 PM", "Wednesday 3:00 PM"),
    ("Wednesday, 3:00pm", "Wednesday 3:00 PM"),
])
def test_program_slots_parse(raw, label):
    assert c.parse_slot(raw).label == label


def test_off_program_slot_is_refused():
    with pytest.raises(c.CohortError, match="not one of the program slots"):
        c.parse_slot("Tue 4:00 PM")


# ─── calendar (LOCKED: no session on a no-class date) ────────────────────────

C1 = c.resolve_cohort("1, 9/21/26")
MON = c.parse_slot("Mon 10:00 AM")
WED11 = c.parse_slot("Wed 11:00 AM")


def test_c1_monday_series_is_exactly_25_lessons_none_on_no_class_dates():
    dates = c.session_dates(C1, MON)
    assert len(dates) == 25
    assert dates[0] == date(2026, 9, 21)
    assert dates[-1] == date(2027, 5, 10)
    assert all(d.weekday() == 0 for d in dates)
    for d in dates:
        assert not (date(2026, 11, 23) <= d <= date(2026, 12, 4)), d
        assert not (date(2026, 12, 19) <= d <= date(2027, 1, 17)), d
        assert d not in (date(2027, 3, 8), date(2027, 3, 29), date(2027, 4, 26)), d
    # spring starts Jan 18: MLK Day IS a session day (Danielle 9/15)
    assert date(2027, 1, 18) in dates
    assert date(2027, 2, 15) in dates                     # Presidents' Day too


def test_c1_wednesday_series_skips_the_wednesdays_of_the_no_class_weeks():
    dates = c.session_dates(C1, WED11)
    assert len(dates) == 25
    assert dates[0] == date(2026, 9, 23)
    for skipped in (date(2026, 11, 25), date(2026, 12, 2), date(2027, 3, 10),
                    date(2027, 3, 31), date(2027, 4, 28)):
        assert skipped not in dates


@pytest.mark.parametrize("cell", ["2, 10/19/26", "3, 11/9/26", "4, 1/25/27",
                                  "5, 2/8/27", "6, 3/15/27"])
@pytest.mark.parametrize("slot", [MON, WED11, c.parse_slot("Wed 3:00 PM")])
def test_every_cohort_fits_its_session_count_before_may_14(cell, slot):
    co = c.resolve_cohort(cell)
    dates = c.session_dates(co, slot)
    assert len(dates) == co.sessions
    assert dates[-1] <= date(2027, 5, 14)
    assert not any(c.is_no_class(d) for d in dates)


def test_remaining_sessions_for_a_late_add():
    dates = c.session_dates(C1, MON)
    left = c.remaining_sessions(dates, date(2026, 10, 6))
    assert left[0] == date(2026, 10, 12) and len(left) == 22


# ─── money ────────────────────────────────────────────────────────────────────

def test_group_1_english_9_splits_3750_three_ways():
    # Danielle's blueprint example: 3 students, C1, $1,250 each.
    assert c.split_amount(C1.group_total, 3) == [Decimal("1250")] * 3


def test_late_add_resplits_to_four():
    assert c.split_amount(C1.group_total, 4) == [Decimal("937.50")] * 4


def test_remainder_cents_land_on_the_first_deal():
    assert c.split_amount(100, 3) == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum(c.split_amount(Decimal("3150"), 4)) == Decimal("3150")


def test_no_class_text_has_no_em_dashes():
    assert "—" not in c.no_class_text() and "--" not in c.no_class_text()
    assert "—" not in c.fmt_dates(c.session_dates(C1, MON))

from datetime import datetime
from zoneinfo import ZoneInfo

from src.business_hours import LA, add_business_hours

# Reference week: 2026-06-09 is Tuesday, so 06-12 = Fri, 06-13 = Sat, 06-15 = Mon.


def la(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=LA)


def test_friday_evening_four_hours_due_monday_1pm():
    """LOCKED case: Fri 7 PM + 4h SLA → Mon 1 PM."""
    start = la(2026, 6, 12, 19)          # Friday 7:00 PM PT
    assert add_business_hours(start, 4) == la(2026, 6, 15, 13)  # Monday 1:00 PM PT


def test_weekend_arrival_starts_monday_open():
    start = la(2026, 6, 13, 10)          # Saturday 10 AM
    assert add_business_hours(start, 1) == la(2026, 6, 15, 10)  # Monday 10 AM


def test_midday_same_day():
    start = la(2026, 6, 10, 10)          # Wednesday 10 AM
    assert add_business_hours(start, 3) == la(2026, 6, 10, 13)  # Wednesday 1 PM


def test_before_open_starts_at_nine():
    start = la(2026, 6, 10, 7)           # Wednesday 7 AM (before open)
    assert add_business_hours(start, 2) == la(2026, 6, 10, 11)


def test_spills_into_next_business_day():
    start = la(2026, 6, 8, 17)           # Monday 5 PM, 1h left in window
    assert add_business_hours(start, 2) == la(2026, 6, 9, 10)  # Tuesday 10 AM


def test_multi_day_48h_six_business_days():
    # 48 business hours = 5 full 9h days (45h) + 3h. Start Mon 9 AM.
    start = la(2026, 6, 8, 9)            # Monday 9 AM
    # Mon..Fri = 45h consumed by Fri 6 PM; +3h → Mon (06-15) 12 PM.
    assert add_business_hours(start, 48) == la(2026, 6, 15, 12)


def test_input_utc_is_converted():
    # Friday 7 PM PT == Saturday 02:00 UTC (PDT = UTC-7).
    start = datetime(2026, 6, 13, 2, 0, tzinfo=ZoneInfo("UTC"))
    assert add_business_hours(start, 4) == la(2026, 6, 15, 13)


def test_prev_business_day_skips_weekend():
    import datetime as dt
    from src.business_hours import prev_business_day
    assert prev_business_day(dt.date(2026, 6, 15)) == dt.date(2026, 6, 12)  # Mon → Fri
    assert prev_business_day(dt.date(2026, 6, 12)) == dt.date(2026, 6, 11)  # Fri → Thu
    assert prev_business_day(dt.date(2026, 6, 14)) == dt.date(2026, 6, 12)  # Sun → Fri

"""SLA business-hours clock (LOCKED).

The clock runs 9:00 AM - 6:00 PM America/Los_Angeles, Monday-Friday only.
An email arriving outside the window starts its clock at the next window open.

Example (unit-tested): a Friday 7 PM arrival with a 4h SLA is due Monday 1 PM.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")
UTC = ZoneInfo("UTC")

OPEN_H = 9
CLOSE_H = 18  # 6 PM
DAY_HOURS = CLOSE_H - OPEN_H  # 9 business hours/day


def _to_la(dt: datetime) -> datetime:
    """Normalize to America/Los_Angeles. Naive datetimes are assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(LA)


def _is_business_day(d) -> bool:
    return d.weekday() < 5  # Mon=0 .. Fri=4


def _open_at(d) -> datetime:
    return datetime.combine(d, time(OPEN_H), tzinfo=LA)


def _close_at(d) -> datetime:
    return datetime.combine(d, time(CLOSE_H), tzinfo=LA)


def advance_to_open(dt: datetime) -> datetime:
    """Move dt forward to the next instant inside a business window."""
    dt = _to_la(dt)
    while True:
        if not _is_business_day(dt.date()):
            dt = _open_at(dt.date() + timedelta(days=1))
            continue
        open_dt, close_dt = _open_at(dt.date()), _close_at(dt.date())
        if dt < open_dt:
            return open_dt
        if dt >= close_dt:
            dt = _open_at(dt.date() + timedelta(days=1))
            continue
        return dt  # already inside the window


def add_business_hours(start_dt: datetime, hours: float) -> datetime:
    """Return the due datetime (LA tz) after consuming `hours` business hours."""
    dt = advance_to_open(start_dt)
    remaining = timedelta(hours=hours)
    while remaining > timedelta(0):
        avail = _close_at(dt.date()) - dt
        if remaining <= avail:
            return dt + remaining
        remaining -= avail
        dt = advance_to_open(_close_at(dt.date()))
    return dt


def prev_business_day(d):
    """The most recent Mon-Fri strictly before date `d` (Fri when d is Mon/Sun)."""
    d = d - timedelta(days=1)
    while not _is_business_day(d):
        d = d - timedelta(days=1)
    return d


def now_la() -> datetime:
    return datetime.now(tz=LA)


def is_past_due(due_dt: datetime, now: datetime | None = None) -> bool:
    now = _to_la(now) if now else now_la()
    return now > _to_la(due_dt)

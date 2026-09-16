"""Cohort facts, session calendar and amount split for IEM HSA groups.

Everything here is pure: spec docs/specs/cohort-intake-spec.md §2 (cohort
table, slots, no-class weeks, pricing) and §9 1c (calendar rules resolved by
Danielle 9/15). The dated session list generated here is the ONE source for
the Teachworks booking list, the family email, the ES email and the
scheduler handoff (spec §9, LOCKED).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

SESSION_RATE = Decimal("150")          # flat per group session, any size
PROGRAM_END = date(2027, 5, 14)          # every cohort ends here
MAX_GROUP = 4                            # NSSA HIT cap; target 3
SLOT_HOUR = {"mon 10:00 am": ("Monday", "10:00 AM"),
             "wed 11:00 am": ("Wednesday", "11:00 AM"),
             "wed 3:00 pm": ("Wednesday", "3:00 PM")}

# (cohort, registration deadline, start, sessions)
COHORTS: tuple[tuple[int, date, date, int], ...] = (
    (1, date(2026, 9, 14), date(2026, 9, 21), 25),
    (2, date(2026, 10, 12), date(2026, 10, 19), 21),
    (3, date(2026, 11, 2), date(2026, 11, 9), 18),
    (4, date(2027, 1, 11), date(2027, 1, 25), 13),
    (5, date(2027, 2, 1), date(2027, 2, 8), 11),
    (6, date(2027, 3, 8), date(2027, 3, 15), 7),
)

# No-class windows, inclusive. "Week of Mar 8" means the whole week, so a
# Wednesday group skips Mar 10 (Danielle 9/15).
NO_CLASS: tuple[tuple[date, date, str], ...] = (
    (date(2026, 11, 23), date(2026, 11, 27), "Nov 23 to 27 (Thanksgiving week)"),
    (date(2026, 11, 30), date(2026, 12, 4), "Nov 30 to Dec 4"),
    (date(2026, 12, 19), date(2027, 1, 17), "Dec 19 to Jan 17 (winter break)"),
    (date(2027, 3, 8), date(2027, 3, 12), "week of Mar 8"),
    (date(2027, 3, 29), date(2027, 4, 2), "week of Mar 29"),
    (date(2027, 4, 26), date(2027, 4, 30), "week of Apr 26"),
)

WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3, "friday": 4, "fri": 4}


class CohortError(ValueError):
    """A row that cannot be resolved against the locked program facts."""


@dataclass(frozen=True)
class Cohort:
    number: int
    start: date
    sessions: int

    @property
    def group_total(self) -> Decimal:
        return SESSION_RATE * self.sessions


@dataclass(frozen=True)
class Slot:
    weekday: int          # 0 = Monday
    day_name: str         # "Monday"
    time_label: str       # "10:00 AM"

    @property
    def label(self) -> str:
        return f"{self.day_name} {self.time_label}"

    @property
    def short(self) -> str:
        return f"{self.day_name[:3]} {self.time_label}"


def no_class_dates() -> frozenset[date]:
    out: set[date] = set()
    for a, b, _ in NO_CLASS:
        d = a
        while d <= b:
            out.add(d)
            d += timedelta(days=1)
    return frozenset(out)


def no_class_text() -> str:
    return "; ".join(label for _a, _b, label in NO_CLASS)


def is_no_class(d: date) -> bool:
    return d in no_class_dates()


_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")


def parse_sheet_date(raw: str) -> date | None:
    """'9/21/26', '09/21/2026', '2026-09-21' → date; None when unparseable."""
    s = (raw or "").strip()
    if not s:
        return None
    m = _DATE_RE.search(s)
    if m:
        mo, d, y = (int(x) for x in m.groups())
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(*(int(x) for x in m.groups()))
        except ValueError:
            return None
    return None


def resolve_cohort(cohort_start_cell: str) -> Cohort:
    """'1, 9/21/26' → Cohort 1. The cohort is decided by the START DATE
    matched to the table, never by the leading number (spec §2). A leading
    number that disagrees with the date is reported, not trusted."""
    start = parse_sheet_date(cohort_start_cell)
    if not start:
        raise CohortError(f"no start date in {cohort_start_cell!r}")
    for n, _deadline, s, sessions in COHORTS:
        if s == start:
            m = re.match(r"\s*(\d+)\s*,", cohort_start_cell or "")
            if m and int(m.group(1)) != n:
                raise CohortError(
                    f"cohort label says {m.group(1)} but start {start:%-m/%-d/%y} is cohort {n}")
            return Cohort(n, s, sessions)
    known = ", ".join(f"{s:%-m/%-d/%y}" for _n, _d, s, _x in COHORTS)
    raise CohortError(f"start {start:%-m/%-d/%y} is not a cohort start (known: {known})")


def parse_slot(raw: str) -> Slot:
    """'Mon 10:00 AM' / 'Monday 10am' / 'Wed 3 PM' / 'Wed 3:00' → Slot. Only
    the three locked slots are accepted. Danielle's sheet writes them without
    AM/PM ('Mon 10:00', 'Wed 3:00', verified on the first live dry run
    2026-09-16); the program slots make that unambiguous, so a missing
    meridian is resolved against them rather than refused."""
    s = re.sub(r"\s+", " ", (raw or "").strip().lower())
    m = re.match(r"([a-z]+)\.?,?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if not m or m.group(1) not in WEEKDAYS:
        raise CohortError(f"unparseable slot {raw!r}")
    hour, minute, ampm = int(m.group(2)), int(m.group(3) or 0), m.group(4)
    day3 = m.group(1)[:3]
    candidates = [ampm] if ampm else ["am", "pm"]
    keys = [k for k in (f"{day3} {hour}:{minute:02d} {x}" for x in candidates) if k in SLOT_HOUR]
    if len(keys) != 1:
        raise CohortError(f"slot {raw!r} is not one of the program slots "
                          f"(Mon 10:00 AM, Wed 11:00 AM, Wed 3:00 PM)")
    day_name, time_label = SLOT_HOUR[keys[0]]
    return Slot(WEEKDAYS[m.group(1)], day_name, time_label)


def session_dates(cohort: Cohort, slot: Slot) -> list[date]:
    """Weekly dates on the slot's weekday, from the first occurrence on or
    after the cohort start, skipping every no-class date, exactly
    cohort.sessions long, all on or before PROGRAM_END. Raises if the
    program window cannot hold the session count (it can for all six
    cohorts and all three slots; this guards the table against edits)."""
    skip = no_class_dates()
    d = cohort.start
    while d.weekday() != slot.weekday:
        d += timedelta(days=1)
    out: list[date] = []
    while len(out) < cohort.sessions:
        if d > PROGRAM_END:
            raise CohortError(
                f"cohort {cohort.number} {slot.label}: only {len(out)} of "
                f"{cohort.sessions} sessions fit before {PROGRAM_END:%-m/%-d/%y}")
        if d not in skip:
            out.append(d)
        d += timedelta(days=7)
    return out


def remaining_sessions(dates: list[date], as_of: date) -> list[date]:
    """Sessions on or after `as_of` (late-add allocation, spec §6)."""
    return [d for d in dates if d >= as_of]


def split_amount(total: Decimal | int, n: int) -> list[Decimal]:
    """Even split to the cent; the remainder cents land on the FIRST deal
    (spec §5.4). 3,750 / 3 → 1,250 each; 3,750 / 4 → 937.50 each;
    3,150 / 4 → 787.50 each; 100 / 3 → 33.34, 33.33, 33.33."""
    if n <= 0:
        raise CohortError("cannot split among zero students")
    total = Decimal(total)
    base = (total / n).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    parts = [base] * n
    parts[0] = base + (total - base * n)
    return parts


def fmt_date(d: date) -> str:
    return f"{d:%a %b %-d, %Y}"


def fmt_dates(dates: list[date]) -> str:
    """'Mon Sep 21, Sep 28, Oct 5 ... 2026; Jan 18 ... 2027' style list that
    reads in an email: grouped by year, month abbreviations, no em dashes."""
    if not dates:
        return "(none)"
    parts: list[str] = []
    year = None
    for d in dates:
        if d.year != year:
            year = d.year
            parts.append(f"{d:%b %-d} ({d.year})")
        else:
            parts.append(f"{d:%b %-d}")
    return ", ".join(parts)

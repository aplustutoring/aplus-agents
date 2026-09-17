"""Intake rows: header mapping, hard-stop validation, group assembly.

Spec §3 (headers, verified 9/15), §4 (hard-stops, cap 4). Pure: the sheet
client hands in lists of cell strings; school resolution is injected so the
aliases file is the only place a school spelling is decided (never guessed
here).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable

from . import cohort as C

READY = "ready"

# Input columns (Danielle's), matched case/space-insensitively by these keys.
INPUT_HEADERS = {
    "student_id": ("student id",),
    "student_first": ("student first name",),
    "student_last": ("student last name",),
    "grade": ("grade",),
    "school": ("school",),
    "student_email": ("student email (not iem email)", "student email"),
    "parent_name": ("parent name",),
    "parent_email": ("parent email",),
    "parent_phone": ("contact phone number", "parent phone", "phone"),
    "es_name": ("es name",),
    "es_email": ("es email",),
    "subject": ("tutoring subject", "subject"),
    "notes": ("notes",),
    "slot": ("day/time", "slot"),
    "cohort_start": ("cohort #/start date", "cohort/start date", "cohort #", "start date"),
    "group": ("group #", "group", "cohort number"),
    "status": ("a+ status", "status"),
}
# Agent-written columns (spec §3). Created at the right of the sheet if absent.
OUTPUT_HEADERS = ["HubSpot Deal ID", "Teachworks ID", "Cohort", "Sessions", "Text Sent",
                  "Welcome Sent", "ES Email Sent", "Tutor", "Last Updated"]

REQUIRED = ("parent_email", "parent_phone", "es_email", "subject", "grade",
            "cohort_start", "school", "group")


class RowError(ValueError):
    """Hard-stop: the row cannot be processed as it stands (spec §4)."""


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower())


def header_map(headers: list[str]) -> dict[str, int]:
    """Column index per logical key. Missing optional columns are absent;
    a missing REQUIRED column is a RowError for every row, raised here."""
    norm = [_norm_header(h) for h in headers]
    out: dict[str, int] = {}
    for key, names in INPUT_HEADERS.items():
        for name in names:
            if name in norm:
                out[key] = norm.index(name)
                break
    for key in OUTPUT_HEADERS:
        if _norm_header(key) in norm:
            out[f"out:{key}"] = norm.index(_norm_header(key))
    missing = [k for k in REQUIRED + ("student_id", "student_first", "student_last", "status", "slot")
               if k not in out]
    if missing:
        raise RowError(f"Intake tab is missing columns for: {', '.join(missing)}")
    return out


def normalize_phone(raw: str) -> str | None:
    """US number → E.164 (+1XXXXXXXXXX); None when it is not 10/11 digits."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return "+1" + digits


def normalize_grade(raw: str) -> str | None:
    """'9', '9th', 'Grade 9', '09' → '9'; 'K' → 'K'."""
    s = (raw or "").strip().lower()
    if not s:
        return None
    if s in ("k", "kindergarten", "tk"):
        return s.upper()
    m = re.search(r"(\d{1,2})", s)
    if not m:
        return None
    n = int(m.group(1))
    return str(n) if 1 <= n <= 12 else None


def split_parent_name(parent_name: str, student_last: str) -> tuple[str, str, bool]:
    """(first, last, flagged). A single token ('Reyna') means no parent last
    name on the sheet: last = the student's and the row is flagged (spec §5.3)."""
    parts = [p for p in re.split(r"\s+", (parent_name or "").strip()) if p]
    if not parts:
        return "", student_last, True
    if len(parts) == 1:
        return parts[0], student_last, True
    return " ".join(parts[:-1]), parts[-1], False


@dataclass
class Row:
    sheet_row: int                    # 1-based row number on the Intake tab
    student_id: str
    student_first: str
    student_last: str
    grade: str
    school_raw: str
    school: str                       # canonical (Ocean Grove / Sky Mountain / South Sutter)
    student_email: str | None
    parent_first: str
    parent_last: str
    parent_name_raw: str              # exactly as Danielle wrote it (deal name, description)
    parent_name_flagged: bool
    parent_email: str
    parent_phone: str                 # E.164
    es_name: str
    es_email: str
    subject: str
    notes: str
    slot: C.Slot
    cohort: C.Cohort
    group: int
    status: str
    outputs: dict[str, str] = field(default_factory=dict)   # existing agent columns

    @property
    def student_name(self) -> str:
        return f"{self.student_first} {self.student_last}".strip()

    @property
    def student_short(self) -> str:
        """'Diego R.' for logs that any repo collaborator can read."""
        return f"{self.student_first} {self.student_last[:1]}.".strip() if self.student_last else self.student_first

    @property
    def parent_name(self) -> str:
        """The parent as the sheet names them ('Reyna' stays 'Reyna' in the
        deal name and description; the contact record gets the student's
        last name per spec §5.3)."""
        return self.parent_name_raw or f"{self.parent_first} {self.parent_last}".strip()

    @property
    def es_first(self) -> str:
        return (self.es_name or "").strip().split(" ")[0]

    @property
    def es_last(self) -> str:
        parts = (self.es_name or "").strip().split(" ")
        return " ".join(parts[1:]) if len(parts) > 1 else ""

    @property
    def group_key(self) -> tuple[int, int, str, str]:
        """One group = one cohort + group number + slot + subject."""
        return (self.cohort.number, self.group, self.slot.label, self.subject.strip().lower())

    @property
    def idempotency_key(self) -> str:
        """school + student_id + subject + term (spec §6)."""
        return f"{self.school}|{self.student_id}|{self.subject.strip().lower()}|26/27"


def _cell(cells: list[str], idx: dict[str, int], key: str) -> str:
    i = idx.get(key)
    if i is None or i >= len(cells):
        return ""
    return str(cells[i] or "").strip()


def parse_row(sheet_row: int, cells: list[str], idx: dict[str, int],
              resolve_school: Callable[[str], str | None]) -> Row:
    """Cells → Row, or RowError listing EVERY hard-stop on the row at once so
    Danielle fixes the sheet in one pass."""
    problems: list[str] = []
    get = lambda k: _cell(cells, idx, k)  # noqa: E731

    for key in REQUIRED:
        if not get(key):
            problems.append(f"{key.replace('_', ' ')} is blank")

    # Problems never echo a parent's phone or email: this text lands in the
    # Actions log and the Slack summary (FERPA pass, Roman 2026-09-16).
    phone = normalize_phone(get("parent_phone"))
    if get("parent_phone") and not phone:
        problems.append("parent phone is not a 10-digit US number")
    grade = normalize_grade(get("grade"))
    if get("grade") and not grade:
        problems.append(f"grade {get('grade')!r} is unparseable")
    parent_email = get("parent_email").lower()
    if parent_email and "@" not in parent_email:
        problems.append("parent email is not an address")
    es_email = get("es_email").lower()
    if es_email and "@" not in es_email:
        problems.append("ES email is not an address")

    cohort = slot = None
    if get("cohort_start"):
        try:
            cohort = C.resolve_cohort(get("cohort_start"))
        except C.CohortError as e:
            problems.append(str(e))
    if get("slot"):
        try:
            slot = C.parse_slot(get("slot"))
        except C.CohortError as e:
            problems.append(str(e))
    else:
        problems.append("day/time is blank")

    school = resolve_school(get("school")) if get("school") else None
    if get("school") and not school:
        problems.append(f"school {get('school')!r} is not in school-aliases.yml "
                        f"(add it there; never guessed)")

    group_raw = get("group")
    group = int(group_raw) if re.fullmatch(r"\d+", group_raw or "") else None
    if group_raw and group is None:
        problems.append(f"group # {group_raw!r} is not a number")

    if problems:
        raise RowError(f"row {sheet_row} ({get('student_id') or 'no id'}): " + "; ".join(problems))

    student_email = get("student_email").lower() or None
    if student_email == parent_email:
        student_email = None          # Danielle 9/15: no non-IEM address, no flag
    pf, pl, flagged = split_parent_name(get("parent_name"), get("student_last"))
    outputs = {k[4:]: _cell(cells, idx, k) for k in idx if k.startswith("out:")}
    return Row(
        sheet_row=sheet_row, student_id=get("student_id"),
        student_first=get("student_first"), student_last=get("student_last"),
        grade=grade or "", school_raw=get("school"), school=school or "",
        student_email=student_email, parent_first=pf, parent_last=pl,
        parent_name_raw=re.sub(r"\s+", " ", get("parent_name")).strip(),
        parent_name_flagged=flagged, parent_email=parent_email, parent_phone=phone or "",
        es_name=get("es_name"), es_email=es_email, subject=get("subject"),
        notes=get("notes"), slot=slot, cohort=cohort, group=group, status=get("status"),
        outputs=outputs,
    )


def is_ready(cells: list[str], idx: dict[str, int]) -> bool:
    return _cell(cells, idx, "status").strip().lower() == READY


@dataclass
class Group:
    rows: list[Row]

    @property
    def cohort(self) -> C.Cohort:
        return self.rows[0].cohort

    @property
    def slot(self) -> C.Slot:
        return self.rows[0].slot

    @property
    def number(self) -> int:
        return self.rows[0].group

    @property
    def subject(self) -> str:
        return self.rows[0].subject

    @property
    def label(self) -> str:
        return f"Cohort {self.cohort.number} Group {self.number} {self.subject} ({self.slot.label})"

    @property
    def dates(self) -> list[date]:
        return C.session_dates(self.cohort, self.slot)

    @property
    def amounts(self) -> list[Decimal]:
        return C.split_amount(self.cohort.group_total, len(self.rows))

    @property
    def es_emails(self) -> list[str]:
        seen: list[str] = []
        for r in self.rows:
            if r.es_email not in seen:
                seen.append(r.es_email)
        return seen


def assemble_groups(rows: list[Row]) -> list[Group]:
    """Group Ready rows by (cohort, group #, slot, subject), rows in sheet
    order. Refuses a group of more than MAX_GROUP (spec §4: ask Danielle to
    split) and a group whose rows disagree on the ES-visible facts."""
    by: dict[tuple, list[Row]] = {}
    for r in rows:
        by.setdefault(r.group_key, []).append(r)
    out: list[Group] = []
    for key, rs in sorted(by.items()):
        if len(rs) > C.MAX_GROUP:
            ids = ", ".join(r.student_id for r in rs)
            raise RowError(f"group {key[1]} (cohort {key[0]}, {key[3]}) has {len(rs)} students "
                           f"({ids}); the cap is {C.MAX_GROUP}. Ask Danielle to split it.")
        out.append(Group(rows=rs))
    return out

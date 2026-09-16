"""Every piece of text the agent produces: deal description (spec §5.4,
LOCKED structure), the ES group email (spec §8), the scheduler handoff
(spec §5.7), the run summary and the Log line. No em dashes anywhere: the
scrub runs on every customer-facing string and the tests check it.

Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import cohort as C
from .rows import Group, Row
from ._bootstrap import agent_cfg, scrub

PROGRAM_END_TEXT = "May 14, 2027"


def _money(x: Decimal | float) -> str:
    return f"${Decimal(x):,.2f}"


def deal_name(row: Row) -> str:
    return f"{row.parent_name} - {row.student_name} - {row.school} - IEM HSA {row.subject}"


def schedule_preference(group: Group, start: date) -> str:
    return f"{group.slot.label} PT weekly from {start:%b %-d, %Y}"


def deal_description(row: Row, group: Group, dates: list[date], amount: Decimal,
                     sessions: int) -> str:
    others = [r.student_name for r in group.rows if r.student_id != row.student_id]
    n = len(group.rows)
    lines = [
        f"IEM High School Academy {row.subject} Intervention, Cohort {group.cohort.number} (Group {group.number})",
        f"Student: {row.student_name}, grade {row.grade}, {row.school} (IEM ID {row.student_id})",
        f"Parent: {row.parent_name}, {row.parent_email}, {row.parent_phone}",
        f"ES: {row.es_name}, {row.es_email}",
        f"Schedule: {group.slot.label} PT, weekly, {dates[0]:%b %-d, %Y} through {dates[-1]:%b %-d, %Y}. "
        f"{sessions} one-hour group sessions.",
        f"Group: {', '.join(others) if others else '(only student so far)'}",
        f"Session calendar: {C.fmt_dates(dates)}",
        f"No class: {C.no_class_text()}",
        f"Notes from school: {row.notes or '(none)'}",
        f"Billing: flat $150 per group session, invoiced upfront to IEM (Angie Covil). "
        f"This deal = {_money(amount)} ({group.cohort.sessions} x $150 / {n} students). "
        f"Hours tracked per student in Teachworks at $0/hr.",
        "Reports: session notes to parent + ES after every lesson; Friday attendance report to "
        "Jamie Hetrick, Monica Presby, Angie Covil.",
        "Schedule is fixed by IEM; change requests go to the ES, not A+.",
    ]
    return scrub("\n".join(lines))


def es_email(group: Group, es_email_addr: str, dates: list[date]) -> tuple[str, str]:
    """(subject, body) for one ES about one group. Danielle's wording rule:
    reply here or text/call the 818 for anything."""
    rows = [r for r in group.rows if r.es_email == es_email_addr] or group.rows
    es_first = rows[0].es_first or "there"
    students = "; ".join(f"{r.student_name} (grade {r.grade}, {r.school})" for r in group.rows)
    line = agent_cfg()["program"]["support_line"]
    subject = f"Your HSA {group.subject} group starts {dates[0]:%b %-d}: A+ Tutoring"
    body = (
        f"Hi {es_first},\n\n"
        f"Your {group.subject} group (Cohort {group.cohort.number}) starts {dates[0]:%A, %B %-d, %Y}, "
        f"{group.slot.label} PT, weekly through {PROGRAM_END_TEXT}. Students: {students}.\n\n"
        f"The day and time are fixed for the group; families have been told they cannot be changed, "
        f"and any request to change comes to you, not us.\n\n"
        f"Lesson links: each student has one join link for the whole year, sent to the parent. "
        f"Students on school devices or school email cannot receive our emails (domain restriction), "
        f"so parents will forward the link to you once to pass along inside the school system. "
        f"Reply if you'd like the links sent to you directly as well.\n\n"
        f"You'll get session notes after every lesson for each student. Tutor introduction follows "
        f"once confirmed. Weekly attendance reports go to the IEM admin team.\n\n"
        f"Session calendar (all {len(dates)} dates): {C.fmt_dates(dates)}. "
        f"No class: {C.no_class_text()}.\n\n"
        f"Roster changes go through Jamie/Monica on the sheet; anything else, reply here or "
        f"text/call {line}.\n\n"
        f"A+ Tutoring Success Team"
    )
    return scrub(subject), scrub(body)


def scheduler_handoff(group: Group, dates: list[date], deal_urls: dict[str, str],
                      owner_name: str) -> str:
    """Slack DM to the owning scheduler (spec §5.7, LOCKED definition)."""
    head = (f"📚 *IEM HSA cohort handoff* for {owner_name}: {group.label}\n"
            f"Book *{len(dates)} sessions* from {dates[0]:%a %b %-d, %Y}, weekly, "
            f"{group.slot.label} PT, through {dates[-1]:%a %b %-d, %Y}. "
            f"Confirm a tutor for {group.slot.label}.")
    roster = ["", "*Roster*"]
    for r in group.rows:
        roster.append(f"• {r.student_name}, grade {r.grade}, {r.school} | parent {r.parent_name} "
                      f"{r.parent_phone} | ES {r.es_name} <{r.es_email}> | "
                      f"{deal_urls.get(r.student_id, '(deal pending)')}")
    skips = ["", f"*Skip dates (no session may be booked on these, LOCKED):* {C.no_class_text()}",
             f"Exact skipped {group.slot.day_name}s: " +
             ", ".join(f"{d:%b %-d}" for d in _skipped_weekdays(group)),
             "", f"*Session dates:* {C.fmt_dates(dates)}",
             "", "The schedule is IEM's and fixed: no time changes for these families. "
                 "The tutor intro and the one steady lesson link come from your Teachworks "
                 "lesson-creation email. Hours are $0/hr per student; the group invoice is "
                 "Kath's task."]
    return "\n".join([head] + roster + skips)


def _skipped_weekdays(group: Group) -> list[date]:
    """The slot's weekdays that fall inside a no-class window between the
    first and last session: what the scheduler must leave empty."""
    dates = group.dates
    out = []
    d = dates[0]
    while d <= dates[-1]:
        if C.is_no_class(d):
            out.append(d)
        d = d.fromordinal(d.toordinal() + 7)
    return out


def plan_summary(groups: list[Group], plans: dict, refused: list[str], mode: str) -> str:
    """The dry-run table DM'd to Roman + Danielle (spec §5.2)."""
    lines = [f"🗂 *cohort_intake {mode}*: {len(groups)} group(s), "
             f"{sum(len(g.rows) for g in groups)} student(s)"]
    for g in groups:
        p = plans[g.label]
        lines.append(f"\n*{g.label}* — {g.cohort.sessions} sessions, group total "
                     f"{_money(g.cohort.group_total)}, first {g.dates[0]:%b %-d} last {g.dates[-1]:%b %-d}; "
                     f"owner {p['owner_name']}")
        for r, amt, action in zip(g.rows, p["amounts"], p["deal_actions"]):
            lines.append(f"  • {r.student_name} ({r.student_id}) {_money(amt)} → deal {action}; "
                         f"family {p['family_actions'][r.student_id]}; "
                         f"ES {r.es_name} {p['tor_actions'][r.es_email]}"
                         + (" ⚠️ parent last name = student's" if r.parent_name_flagged else ""))
        lines.append(f"  Sends: 1 text + 1 welcome email per family via the SMS sweep (≤15 min after "
                     f"the deals land); ES email to {', '.join(g.es_emails)} this run.")
    if refused:
        lines.append("\n*Refused (fix the sheet, re-run):*")
        lines += [f"  ✗ {x}" for x in refused]
    return "\n".join(lines)

---
name: journey-02-attempting-to-contact
description: >-
  We have a lead and no conversation yet. The chase to a booked meeting or a
  live call: who chases, from where, how often, and when to stop.
status: DRAFT
owner_seat: charter_sales
reviewers: []
agent_readable: false
version: 0.1
---

# 02. Attempting to contact

## Entry marker

Lead status Attempting to Contact, set by the lead workflows after the first
text and email go unanswered, or by the seat after a missed call back.

## Exit marker

Meeting Booked (a consult on the charter_sales seat's meetings link), a QTL
status after a live call, or Dead Opportunity after the cadence runs out.

## Owner seat

`charter_sales`. The workflow's "New Lead Alert" call task is assigned to this
seat. For teachers, `sales`, through the outreach sequences.

## Channel and identity

Families: the charter_sales line for calls and texts, paola@ or the workflow
email for email, signed Paola. The "inbox is full" voicemail email is part of
the cadence (`docs/CHANGELOG.md`, 2026-08-17 lead status entry). Teachers:
email only, from danielle@, on the sequence cadence in
`ops/messenger/teacher-sequences.yml` (50 a day, weekdays, armed by config).

## What the agent may do alone, must draft, must ask

**Alone:** enroll teachers in the sequence under the armed config; log
attempts; nudge the seat when a task is overdue (`task-completion-sweep`).

**Draft:** follow-up texts and emails for the seat to send. Under 25
recipients there is no send rail today.

**Ask:** any change to cadence; any touch beyond the cadence; any text to a
family who wrote back on another line.

## Questions we ask the family here

- The same intake questions as `01`, if they were not answered.
- "What days and times work for a quick call?" The consult is the goal.
- Nothing new. Repeating the ask is not a new question.

## Questions the agent asks itself here

- How many touches has this family had, on which channels, in the last week
  (checklist item 5)? The family cadence is not written down; count before
  adding one.
- Did they reply somewhere we are not looking (checklist item 1)?
- Is the meeting already booked? The Meeting Booked workflow stamps the
  status; the Ads nurture does not yet exit on it (open item).
- Has the lead gone cold on purpose? A STOP or an "I'll reach out" is an exit,
  not a pause.

## Where charter and private pay diverge

Charter: the chase can name the school funds and the teacher route. Private
pay: the chase offers the consult and, if the caller asked, the diagnostic.
Teachers: never chased by phone.

## Handoff out

- Meeting booked: `03-discovery.md`, same seat.
- Dead: status set, note why, no further touch until a win-back round
  (`09`).
- Pattern: HubSpot task on the seat, Slack DM when the task sweep finds it
  overdue.

## Known gaps

- No written family cadence: how many touches, how far apart, when to stop.
- No small-send rail; follow-ups are hand-sent or session-scripted.
- The Ads lead nurture keeps chasing after a meeting is booked (a 30-second
  portal edit, noted 2026-08-17, still open).
- Meeting Booked creates no task and no reminder for a no-show.

## Related

- `01-first-touch.md`, `03-discovery.md`.
- `ops/messenger/teacher-sequences.yml`.
- `email/src/task_sweep.py`.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

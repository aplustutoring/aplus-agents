---
name: journey-06-first-lesson
description: >-
  The first session is on the calendar and then happens. Scheduling owns it,
  the support line speaks, and the one question that matters afterward is how
  it went. Nothing in the repo observes this step yet.
status: DRAFT
owner_seat: scheduling_lead
reviewers: []
agent_readable: false
version: 0.1
---

# 06. First lesson

## Entry marker

A first session exists on the Teachworks calendar for the student. Booked by a
scheduler by hand; no code books lessons.

## Exit marker

The session is attended (Teachworks status), and the deal moves to
Post-Lesson. The weekly scorecard measures Pre-Lesson to Post-Lesson within 72
hours (`ops/scorecard/aplus_weekly_sync.py`).

## Owner seat

The assigned scheduler for the booking; `scheduling_lead` for the quality of
the first session.

## Channel and identity

Support line 818-869-1627 and admin@, signed by the scheduler. Teachworks sends
its own lesson reminders with the join link. The tutor's channel
(`11-tutor.md`) for anything the tutor needs before the session.

## What the agent may do alone, must draft, must ask

**Alone:** post the "no upcoming lessons" alert when a deal sits in Pre-Lesson
with an empty calendar; read the Teachworks attendance status after the
session.

**Draft:** a first-session check-in to the family (no template exists).

**Ask:** any change to the booked slot; any message to the tutor that is not
in their channel.

## Questions we ask the family here

- Before: "You are set for {day} at {time} with {tutor}. The join link comes
  from Teachworks. Anything we should tell {tutor} before the first session?"
- After (NEW, no template): "How did the first session go, and is there
  anything to adjust?" One question, asked once, within a day.

## Questions the agent asks itself here

- Is the student actually on the calendar, or only promised? Teachworks is the
  truth for lessons, HubSpot for the family.
- Did the session happen? Attendance status, not the calendar.
- Is the tutor the one the family asked for? If the scheduler substituted,
  the family should hear it from the scheduler before the session, not
  discover it.
- Did the welcome text already go out, and did the family confirm the
  schedule? The `_confirm` versus `_ask` texts in `email/config.yaml` depend
  on whether a real schedule is on the deal.

## Where charter and private pay diverge

Charter: Kath's PO-to-invoice task should be done before the first session so
attended hours count against the PO. Private pay: the trial welcome asks for a
card on file before the free session; the Gold welcome mentions the cc
authorization form.

## Handoff out

- To `07-active-service.md`: the deal at Post-Lesson.
- To scheduling_lead: a first session that was missed or went badly, through
  `ops/tutor-issues/` if it is a tutor signal, through the routing table if it
  is a family complaint.
- Pattern: Teachworks status, HubSpot deal stage, Slack alert.

## Known gaps

- No owner is named for "first lesson observed" and nothing writes it to
  HubSpot. The retention definitions (`retention-definitions` worktree,
  `docs/RETENTION.md`) define first lesson but no code uses it as a journey
  step.
- No first-session check-in template.
- The 72-hour target has no escalation when missed.

## Related

- `05-deal-open-pre-lesson.md`, `07-active-service.md`, `11-tutor.md`.
- `ops/scorecard/aplus_weekly_sync.py`.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

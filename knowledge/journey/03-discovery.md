---
name: journey-03-discovery
description: >-
  The consult or the live call: what we learn about the student, what we
  promise, and how a call Roman answered hands to Paola. Produces a QTL
  status.
status: DRAFT
owner_seat: charter_sales
reviewers: []
agent_readable: false
version: 0.1
---

# 03. Discovery

## Entry marker

Lead status Meeting Booked (a consult booked on the charter_sales seat's
meetings link, stamped by the Meeting Booked workflow) or a live inbound call
on the main or support line (`ops/call_agent/`).

## Exit marker

One of QTL-NEW (we connected, private pay), QTL-Charter (charter funds),
QTL-Diagnostic Sent (test prep or evaluate first). Set by the seat after the
consult, or by the call agent from the transcript within its write policy.

## Owner seat

`charter_sales`. Sales calls ring Roman first and overflow to Paola; Paola does
all follow-up. A call Roman answered produces a task for Paola with a HANDOFF
block saying what Roman covered (`ops/call_agent/config.yml`,
`default_task_owner`; `ops/call_agent/call_agent.py`).

## Channel and identity

Phone. The consult is on Paola's calendar. The call agent transcribes only
calls with a recording and never creates contacts on its own
(`ops/call_agent/README.md`). The post-call recap to the family, if any, is a
text or email from the charter_sales line, signed Paola.

## What the agent may do alone, must draft, must ask

**Alone:** summarize the call, update the record within the write policy
(`ops/call_agent/README.md`, field write policy), set the lead status the
ladder allows, create the follow-up task, post the coaching card.

**Draft:** the post-call recap to the family (no template exists).

**Ask:** any promise about a start date, a specific tutor, or a price the seat
did not state on the call.

## Questions we ask the family here

The discovery rubric, `ops/call_agent/rubric.md`, S1 through S4:

- Grade, school, subjects, and the "why now": confidence, grades slipping, a
  test coming.
- Prior tutoring, and what success looks like to the parent.
- Program fit, pricing without hedging, and the close: an assessment booked,
  diagnostics sent with a return plan, or a specific follow-up date.
- Who does what by when, stated so the caller could repeat it back.
- Charter: which school, who is the teacher of record, is the family on
  instructional funds. Every charter student has funds; the question is the
  route, not whether.
- Schedule preference: days and times (`email/src/classifier.py` asks for it
  when missing; ask on the call too).

## Questions the agent asks itself here

- Did Roman already cover part of this on the call? Read the HANDOFF block
  before drafting anything.
- Is the caller an existing or past customer? Then the status is owned by the
  deal pipeline and the call agent must not demote it.
- Is this a school staff call rather than a family? Different seat, different
  status.
- Was the call recorded? If not, there is no transcript and no summary; say
  so.

## Where charter and private pay diverge

Charter leaves with the teacher's name and school captured, and heads to the
teacher-of-record check in `04`. Private pay leaves with a package or
diagnostic path and a quoted price from the seat.

## Handoff out

- To charter_sales: the follow-up task with the summary and the HANDOFF block.
- To scheduling: nothing yet; there is no deal.
- Pattern: HubSpot task, call summary note on the contact, coaching card in
  `#calls`.

## Known gaps

- No post-call recap template for the family.
- `scheduling_task_owner` in the call agent config is empty, so scheduling
  action items from calls still land on Paola with a prefix.
- Meeting Booked stamps a status and nothing else; no reminder, no no-show
  path.

## Related

- `ops/call_agent/rubric.md`, `ops/call_agent/README.md`.
- `02-attempting-to-contact.md`, `04-qualified-to-deal.md`.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

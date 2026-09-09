---
name: journey-07-active-service
description: >-
  Lessons are happening. Reschedules, cancellations, tutor issues, complaints,
  billing. The routing table in email/config.yaml decides who owns each, and
  the inbox team's scenario guide (email/TEAM_PLAYBOOK.md) says what to do.
status: DRAFT
owner_seat: operations
reviewers: []
agent_readable: false
version: 0.1
---

# 07. Active service

## Entry marker

Deal at Post-Lesson. The student is on the calendar with attended sessions.

## Exit marker

Charter: the PO's hours are used or the PO month ends, Kath submits the invoice
to the school, the deal moves to Invoice Submitted and then closed won when the
school pays (`docs/PO-PROCESS.md`, Stages 6 and 7). Private pay: the package is
exhausted, which is `08-renewal.md`. Or a pause or stop, which is `09`.

## Owner seat

By category, from the routing table in `email/config.yaml` (`routing:`), which
is the source of truth for owners and SLAs. In short: scheduling, reschedules,
and cancellations to the scheduler by student last name; tutor issues,
complaints, and payment disputes to `scheduling_lead`; school partner and
business development to `sales`; new POs and family inquiries to
`charter_sales` and `charter_admin`; tutor documents to `charter_admin`;
reviews to `quality`.

SLA hours are stated in three files and disagree. This playbook treats
`email/config.yaml` as the truth. Reconciling `email/rules.md` and
`email/TEAM_PLAYBOOK.md` is an open item.

## Channel and identity

Support line and admin@ for everything family-facing, signed by the scheduler
or "A+ Tutoring Team". Billing to and from the school on charter@ (Kath). The
email agent drafts; a human sends from HubSpot. The only two automatic
outbound messages are the tutor-document receipt and the PO welcome
(`email/TEAM_PLAYBOOK.md`, auto-actions).

## What the agent may do alone, must draft, must ask

**Alone:** classify and route every inbox email to a ticket with owner and SLA;
move a deal to Stopped on a confident stop or pause; close a ticket only with
a second system's evidence; auto-close a PO-to-invoice task whose invoice
number is already filled; nag overdue invoices daily.

**Draft:** replies for every category marked `draft: true` in the routing
table.

**Ask (never drafted):** complaints and payment disputes (`no_draft_categories`
in `email/config.yaml`); reviews, which are answered on the platform, not by
email.

## Questions we ask the family here

- Reschedule or cancellation: which sessions, one time or ongoing, and the
  new days and times. The classifier asks for a schedule preference when it is
  missing.
- Tutor issue or complaint: what happened, when, with whom. Then nothing else
  from an agent; a person replies.
- Billing: which invoice, which month.
- Pause or stop: whether this is a pause with a return date or a stop, and
  why, so the win-back task lands in the right season.

## Questions the agent asks itself here

- Who owns this category, and is that seat already in the thread (checklist
  item 1)?
- Is this a family message or a school message? Same student, different seat.
- Is confidence high enough to route, and high enough to move a deal? The
  thresholds are in `email/config.yaml`; below them, a human decides.
- Is the tutor resolvable to exactly one contact? If not, no tutor-issue
  ticket; the scheduler is told to file it by hand
  (`ops/tutor-issues/config.yml`).

## Where charter and private pay diverge

Charter: hours are tracked against the PO; the invoice sweep prompts Kath when
attended hours reach the PO or the PO month ends; a school paying is the close.
Private pay: package balance in Teachworks; renewal is the family's decision;
no school in the loop.

## Handoff out

- Ticket with owner and SLA (the routing table), Slack DM to the owner, SLA
  breach ladder to supervisor and then operations (`email/src/sla_sweep.py`).
- Tutor signals to `#tutor-issues` and a ticket on the tutor's contact, owned by
  the operations role as that config names it.
- Invoices to Kath by daily DM until submitted; escalation to the visionary
  seat after three days.

## Known gaps

- The `operations` role key names different people in `email/config.yaml` and
  `ops/tutor-issues/config.yml`.
- Payment and closed won has no owner and no agent watching it.
- Reviews have a seat but no stated account or from-name for the platform
  reply.
- The pause-and-stop path and the win-back copy are separate voices.

## Related

- `email/TEAM_PLAYBOOK.md`: the scenario table for this stage.
- `email/rules.md`: the classifier categories.
- `docs/PO-PROCESS.md`, Stages 5 to 7.
- `ops/tutor-issues/README.md`.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

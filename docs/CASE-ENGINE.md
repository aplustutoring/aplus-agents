# The case engine: Tasks, Tickets and Pipelines, fleet-wide

Source of truth for how A+ agents and people track work in HubSpot. Locked
by Roman on 2026-09-16 (overnight build spec). If the code changes, change
this file in the same PR. Code: `email/src/case_engine.py`; config:
`email/config.yaml` under `case_engine:`.

## The rule (locked). Test in order, first yes wins.

1. **Task**: one person, one thing, one date. Done when done. Machines
   create a task only when they cannot do the thing themselves. Never a
   task to record that something happened.
2. **Ticket**: a case open until an outcome we count, can sit in a waiting
   state, may change hands, needs an age clock. One ticket per case.
3. **Pipeline**: only when the owner set and the closed outcomes differ from
   every existing pipeline. A stage difference alone does not earn one.

Ceiling: 10 human tasks per seat per day, enforced once in
`hubspot_client.create_task` for every machine path (config
`tasks.daily_ceiling_per_owner`). Past it the task is not created, the seat
lead (`tasks.ceiling_notify`) is DM'd with what would have been created, and
the audit log carries `task_ceiling_hit`.

## The three ticket pipelines (portal 6312752, created 2026-09-16)

| Pipeline | id | Stages (closed in bold) | Owner rule | Clients |
|---|---|---|---|---|
| **Renewals** | 935649887 | Waiting on family, Needs scheduler, Needs invoice, **Renewed**, **Not renewing**, **No response** | trial = charter_sales (the only override); IEM HSA deal = group parity (odd scheduler_a_l, even scheduler_m_z, from the deal's `hsa_group`); else family surname A-L scheduler_a_l, M-Z scheduler_m_z | low_balance |
| **Support** | 0 (rebuilt in place) | New, Waiting on us, Waiting on tutor, Waiting on family, **Resolved**, **Won't fix** (legacy Stuck / Stalled Deals / Charter School Documentation stay until empty) | by `support_category`: po_watch, po_exception, billing = charter_admin; scheduling = surname split; everything else = operations | po_inbox (po_watch, po_exception), email triage, humans |
| **Tutor Accountability** | 935648438 | New, Debrief, Probation, Evaluated, **Resolved** | operations | tutor_issues (spec'd, counting only; automation not armed) |

Ticket properties the engine writes (group Case engine, all `[Agent]`):
`case_key` (one ticket per case), `case_client`, `funding_type`
(charter / private_pay / trial), `retention_risk`, `support_category`,
`linked_tutor_ticket_id`, `sla_due_at`; plus `tutor_issue_type` and
`tutor_probation_until` in the Tutor group.

Retention risk is **priority High + `retention_risk` = true**, no stage.
The board sorts on the flag.

## The surname split (cancellation, reschedule, scheduling)

Cancellation, reschedule and scheduling work is owned by the FAMILY's
surname, never the student's and never the tutor's: **A-L -> `scheduler_a_l`,
M-Z -> `scheduler_m_z`** (config `scheduler_split`, held today by Janelle and
Yolanda; `router.scheduler_for_last_name` is the one implementation). The
ticket and every task hung off it — the SLA reply task and the win-back
`Re-engage:` task — carry that owner.

The surname comes from the email CONTENT first, because the sender often
isn't the family: a Teachworks notice names them in the body
(`main._parent_last_name`). Then the HubSpot contact, then the Teachworks
family record.

One override, and only one: a **pre-deal lead** — a family with no deal and
no Teachworks account — goes to `charter_sales` until the deal exists, so a
new sale isn't handed to a scheduler (Roman 2026-07-20, after the Deanna
Smith miss).

Worked example. `Sterling, Sam — Cancellation`, a Teachworks notice for a
one-time skip on 9/21. Surname Sterling, S is M-Z, so the ticket and its
reply task are **Yolanda's**. The pre-deal override does not apply: the
notice's no-reply sender is not the family, and a family Teachworks writes
about is active by definition. (Before 2026-09-21 it did apply — the override
tested the no-reply sender, found no deal and no Teachworks account, and gave
71 notices to charter sales. Paola caught it on this one.
`email/src/backfill_notice_owners.py` reassigned the open ones.)

## The engine's shape

trigger -> `open_case` (idempotent by `case_key`, associates contact and
deal, stamps the SLA clock) -> the client's rails -> reply watcher ->
closer sweep -> escalation (`mark_risk`, `dm_role`) -> digests
(`ops/queues/queue_digest.py`).

Every client declares its owner rule in config as a named role or a split.
The engine sends nothing to a family, ever; the rails and the presend gate
stay where they are.

## Client 1: low balance (Renewals)

Every Teachworks package-balance alert opens a Renewals case at detection
(email triage no longer opens `low_balance` tickets; `charter_only` is
retired):

- charter and private pay -> owner by the split; trial (a trial package,
  0.0 hours) -> `funding_type` trial, owner charter_sales.
- Day 0 email from shared admin@ ("A+ Tutoring"), reply-to the case owner
  (the scheduler; charter_sales for a trial). Day 1 text from 818-869-1627
  signed "this is A+ Tutoring". Teacher email from charter_sales, charter
  only. Private pay and trial: the payment-link rail
  (`low_balance.private_pay`, armed last; needs `payment_links`), no
  teacher step.
- Replies: family reply -> ticket to Needs scheduler, DM the case owner;
  teacher reply -> DM charter_sales.
- Retention risk = the later of day 7 and balance at 1 hour or less; DM the
  case owner only. Roman is on no case DM.
- New PO -> Needs invoice; the ticket closes as Renewed when Invoice # lands
  on the deal (`needs_invoice_sweep`, hourly). Deal Stopped -> Not renewing.
  Day 28 of silence after risk -> No response, re-engagement list.
- An open Tutor Accountability ticket on the same family is linked on the
  Renewals ticket (`linked_tutor_ticket_id`); the scheduler escalates to
  operations, ownership does not change.
- No companion task (the +3 business day task was never built; nothing to
  retire).

Fleet-health defect: a charter or private-pay Renewals ticket owned by
charter_sales. The Monday digest prints it.

## Client 2: PO watch (Support)

A clean PO -> deal stamp + timeline note + Support ticket `po_watch`, owner
charter_admin (`po_inbox.invoice_task.mode: ticket`). It closes itself when
Invoice # is on the deal (`po_watch_sweep`, hourly). Exceptions (no parent
match, ambiguous rate, amount mismatch, void invoice, review needed) carry
`support_category` po_exception. No more one-task-per-PO.

## Client 3: tutor accountability (spec, not armed)

Issue types: tutor_switch_requested, late_or_no_notice, incomplete_notes,
unresponsive_mia, scheduling_flip_flop, other, positive_review. Ticket
associated to the tutor contact and the family contact. Count per tutor in
`tutor_accountability.window_days`: 1st = Debrief, 2nd = Probation for
`probation_days` (no new students), 3rd = flag to the L10 agenda + operations
DM. Page 2 of the Escalation Procedure is unread; the automation stays
`armed: false` until Roman reads it. Seeded 2026-09-16 from the open tutor
tickets (three tutors already at two tickets: Bax, Basinger, Torres).

## Service levels (working draft, config `case_engine.service_levels`)

Renewals: human column touched within 1 business day, never 3 without a
logged touch, Needs invoice 1. Support: first response 1, tutor issues
resolved in 5, complaints same day. Tasks: care calls within the assigned
week, scheduling and callbacks next business day, teacher replies 1.

## Digests (`.github/workflows/queue-digests.yml`)

- Monday 9:05 AM PT: per pipeline and per seat, open by stage and age, the
  oldest open, entered and closed last week by outcome, SLA breaches, overdue
  tasks per seat, machine-created tasks vs the ceiling, Renewals trailing
  4-week renewal rate per family.
- Daily 9:00 AM PT: fleet recap (merged PRs, config changes, failed runs).
  Nothing outside the fleet.

## Migration 2026-09-16

`ops/queues/migration_table_2026_09_16.md` is the classification of the 109
open tickets; `ops/queues/migrate_tickets_2026_09_16.py --live` executes it
one ticket at a time with a note on each (REVIEW rows untouched). Order:
pipelines built -> table posted -> owners switched -> triage low_balance
path off -> engine armed for private pay and trial.

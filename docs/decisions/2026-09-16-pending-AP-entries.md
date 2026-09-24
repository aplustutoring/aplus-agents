# #AP entries to log (2026-09-16 overnight build)

Roman logs these to the A+ Decision Log with the next free numbers. Text is
ready to paste.

## #AP0xx — Charter renewals belong to the schedulers
Charter and private-pay renewal cases (Teachworks low-balance alerts) are
owned by the scheduling seats: family surname A-L = scheduler_a_l, M-Z =
scheduler_m_z; IEM HSA deals by group-number parity (odd A-L, even M-Z).
charter_sales keeps the teacher-of-record email and the day-7 conversation
is the owner's. No exceptions. Config: `case_engine.owner_rules.renewals`.

## #AP0xx — Day 0 renewal sender = shared admin@
The day-0 low-balance email leaves from "A+ Tutoring <admin@wetutorathome.com>"
with reply-to the case owner (the scheduler; charter_sales for a trial). The
day-1 text leaves from the support line 818-869-1627 signed "this is A+
Tutoring". Sender identity is the office, not a person (Paola, 9/11).

## #AP0xx — Triage routes Teachworks alerts by package family
Email triage no longer opens `low_balance` tickets. Every Teachworks
package-balance alert routes at detection into the case engine: charter and
private pay -> Renewals ticket, owner by split; trial at 0.0 hours -> Renewals
ticket, funding_type = trial, owner charter_sales. Renewed = converted. A
charter or private-pay renewal ticket owned by charter_sales is a fleet-health
defect.

## #AP0xx — PO watch replaces the per-PO task
A clean PO creates a Support ticket (category po_watch, owner charter_admin)
that auto-closes when the Teachworks invoice number is stamped on the deal.
Exceptions are po_exception. No more one task per PO.

## #AP0xx — Trials are Renewals tickets with the charter_sales override
A trial package alert opens a Renewals ticket with funding_type = trial and
owner charter_sales, the only owner override in the Renewals pipeline.

## #AP0xx — Tutor Accountability pipeline
Tutor issues live in their own ticket pipeline (New, Debrief, Probation,
Evaluated, Resolved), owner operations, ticket associated to the tutor and
the family. Count per tutor in 30 days: 1st = Debrief, 2nd = Probation (30
days, no new students), 3rd = L10 agenda + operations DM. Automation spec'd
from the Escalation Procedure page 1; not armed until page 2 is read.

## Also locked in the same spec
- THE RULE: Task = one person, one thing, one date; Ticket = a case open
  until an outcome we count; Pipeline = only when owner set and closed
  outcomes differ. Ceiling 10 human tasks per seat per day.
- roles.operations = Mandy (Emily keeps `escalation`).

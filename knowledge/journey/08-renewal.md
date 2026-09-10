---
name: journey-08-renewal
description: >-
  The package is running low, the PO month is ending, or the season turns.
  Who asks for the next PO or package, from which line, and what we ask the
  family and the teacher. The low-balance agent exists but is unmerged and
  unarmed.
status: DRAFT
owner_seat: charter_sales
reviewers: []
agent_readable: false
version: 0.1
---

# 08. Renewal

## Entry marker

Charter: a Teachworks low-balance alert (four hours or less on the package), or
the last PO month approaching, or a new season with last season's deal and no
new one (the gap list, `scripts/charter_gap_analysis.py`). Private pay: the
package near zero in Teachworks.

## Exit marker

A new deal. Returning families get a new deal marked existing business, never
a renewal deal (`email/config.yaml`, `dealtype`). Or the family lapses, which is
`09-pause-stop-winback.md`.

## Owner seat

`charter_sales`. Retention is the charter_sales seat's quarterly rock
(`knowledge/eos/README.md`). The low-balance agent files its ticket to this
seat and DMs only this seat (`corrections/call-agent/2026-08-12-low-balance-alerts-route-paola-only.md`).

## Channel and identity

Open decision. A family with a live deal is scheduling's, so scheduling talk
goes from the support line. The renewal ask is a sales conversation. Which
line and identity makes the renewal ask is Roman's call (README open item 6).
Until decided: scheduling logistics from the support line, the renewal ask
itself from the charter_sales seat by email or from Paola's line, and never
both on the same day (checklist item 5).

The teacher: email only, from the charter_sales seat, asking for the next PO
(the low-balance agent's teacher draft goes out of paola@).

## What the agent may do alone, must draft, must ask

**Alone (when the low-balance agent is merged and armed):** file the ticket,
DM the seat, write the copy it would have sent into the ticket note; once
armed, send the family text and email and draft the teacher email.

**Draft:** the teacher's next-PO email; the family's renewal email.

**Ask:** the send of anything renewal-shaped until the agent is armed; any
renewal ask to a Level Up (Terri) family's teacher, since those teachers
cannot issue additional POs.

## Questions we ask the family here

- "Do you want to keep going with {tutor}, same days and times?"
- Charter: "Your school's next PO covers it; would you like us to send
  {teacher} the hours?" The school issues the PO. The family may prefer to
  take it to the teacher themselves (Gonzalez did); that is a yes.
- Private pay: package size for the next block, and whether the schedule
  changes.
- Encouraged cadence, `knowledge/program-model.md`: at least 8 to 12
  45-minute sessions a month, offered alongside whatever the family chose,
  never instead of it, and never as a monthly dollar total.

## Questions we ask the teacher here

- "{Student} has about {hours} left. Can the school issue the next PO? Tell me
  what you need from us." Hours to the family are stated as "four hours or
  less", never the exact balance; the exact number is staff-only
  (low-balance agent config).

## Questions the agent asks itself here

- Is a new PO already on file? The low-balance agent self-closes on a newer
  deal with a PO number; check before asking anyone.
- Is this family currently in a scheduling thread on the support line? Then
  the renewal ask waits for a quiet day or goes through the scheduler.
- Is the tutor still active? Never name one who left.
- Is this a Level Up (Terri) family? Then the teacher route is closed.
- Which unit am I tracking, the student or the family? Retention is per
  student (`docs/RETENTION.md`, `retention-definitions` worktree).

## Where charter and private pay diverge

Charter: teacher, PO, hours; the school pays. Private pay: the family pays; a
Gold renewal deal exists as a pipeline but returning families get an
existing-business deal in the main pipeline. Private-pay low balance is
explicitly phase two, handled by hand, no owner named.

## Handoff out

- To the teacher: the next-PO email, drafted, human sends.
- To scheduling: nothing changes until the new PO or package lands.
- To the visionary seat: the low-balance agent escalates after ten days with
  no PO.
- Pattern: ticket to charter_sales, task with a follow-up date, Gmail draft
  labeled "A+ Agent/Draft Pending".

## Known gaps

- The low-balance agent is in the `low-balance-agent` worktree, unmerged,
  `armed: false`.
- The care ladder (day 14, 45, 75 checks; 30, 60, 90 day win-back) is
  specified and has no code (`ops/care/` does not exist).
- Charter renewal is not a live scorecard measurable; the gap script is a
  manual one-shot with the season hardcoded.
- The renewal-ask identity is undecided.

## Related

- `07-active-service.md`, `09-pause-stop-winback.md`, `10-teacher-of-record.md`.
- `email/src/invoice_sweep.py`, `scripts/charter_gap_analysis.py`.
- `knowledge/eos/README.md`.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

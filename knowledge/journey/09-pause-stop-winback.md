---
name: journey-09-pause-stop-winback
description: >-
  A family has paused, stopped, or lapsed. They are a lead again: charter_sales
  owns them, the charter_sales line speaks, and the win-back message names the
  student and the tutor or gets no reply at all.
status: DRAFT
owner_seat: charter_sales
reviewers: []
agent_readable: false
version: 0.1
---

# 09. Pause, stop, win-back

## Entry marker

Any of: a cancellation email classified pause or stop, which moves the deal to
its pipeline's Stopped stage and opens a re-engagement task
(`email/config.yaml`, `deal_automation` and `reengagement`); a lead status of
Past Customer, Check Back Quarterly, or Dead Opportunity; or a family on a
season gap list, meaning a deal last season and none this season
(`scripts/charter_gap_analysis.py`).

## Exit marker

A yes. The family goes back to `04-qualified-to-deal.md` with a
teacher-of-record check (charter) or a quote (private pay). Or a no, a STOP, or
silence after the round, and the contact stays here with the reason noted.

## Owner seat

`charter_sales`. The Day-7 call task in a win-back round goes to this seat
(`ops/messenger/CAMPAIGN-2026-08-17.md`).

## Channel and identity

A family with no active deal is a lead again: charter_sales line 818-573-6644,
signed "Paola with A+ Tutoring", or a marketing email from the A+ Tutoring
Team with reply-to routed to the charter_sales seat. Bulk rounds go through
`ops/messenger/` (25 or more recipients, dry-run default, STOP line required).
Under 25 there is no rail yet; follow `00-pre-send-checklist.md` by hand.

The moment a yes turns into a deal, the family leaves this stage and the line
switches (`05-deal-open-pre-lesson.md`).

## What the agent may do alone, must draft, must ask

**Alone:** build the audience list with the send-time checks below; read and
tally replies; stamp `sms_opt_out` on a STOP; note every send and reply on the
contact.

**Draft:** the win-back copy (Roman approves copy before a round); the
per-family follow-ups.

**Ask:** the send itself (a round is armed by Roman); any relay of a tutor's
availability (checklist item 4); any text to a family who already replied.

## Questions we ask the family here

- Do you want to pick back up with {tutor} this year? Named student, named
  tutor. Evidence: the 2026-08 charter round got 3.9 percent replies on the
  named-tutor email and zero on every nameless variant (`docs/CHANGELOG.md`,
  2026-09-08 analysis entry).
- If yes: is {teacher} still your teacher of record, same as last year?
  (charter, leads into 04).
- What days and times, and how many sessions a week.
- If no: nothing more. "If now is not the time, that is a good answer" is in
  the copy or implied by the STOP line. An honest no is caring.

## Questions the agent asks itself here

- Does this contact already have a deal this season? Check at send time, not
  at list-build time; families convert between the two.
- Has this contact written to us since the round started, on any line or the
  inbox? Thread scan, not `hs_email_last_reply_date`. A replier leaves the
  list.
- Is the tutor I am about to name still active? `last_tutor_active` in
  `ops/hubspot-schema/properties.yml`. Never name a tutor who left.
- Is this family in an open scheduling thread on the support line? Then they
  are not a lead, whatever the list says (the Gonzalez rule).
- Is it inside the send window, and does the template carry a STOP line (new
  touch) or not (reply in thread)?

## Where charter and private pay diverge

Charter: the message can say the school funds cover it and the PO route
follows a yes; every charter student has funds. Private pay: no funds
language; the ask is the tutor and the schedule, and pricing comes from the
seat, not the template. Private-pay lapsed families were not messaged in the
2026-09 round; that is the next round.

## Handoff out

- A yes: to `04-qualified-to-deal.md`, same seat.
- A question only a person can answer (price, funds, "does the school pay?"):
  Slack DM to charter_sales with the thread link, and a holding reply only if
  it is inside the same thread.
- A tutor named by the family: to the scheduler, `11-tutor.md`, not to the
  tutor directly.
- STOP: stamp `sms_opt_out`, note the contact, no reply.

## Known gaps

- No rail under 25 recipients; the 2026-09-08 follow-ups ran from session
  scripts (PR B adds `one_to_few.py`).
- STOP-reply ingestion is not built; opt-outs are stamped by hand.
- The pause-and-stop path (`email/templates/reengagement.md`) and the
  campaign win-back copy are two voices with no cross-reference.
- Private-pay lapsed families have no re-engagement mechanism at all; the old
  Past Customer nurture workflow was disabled in the 2026-07 purge.

## Related

- `ops/messenger/README.md` and `ops/messenger/CAMPAIGN-2026-08-17.md`.
- `scripts/charter_gap_analysis.py`, `scripts/campaign_revenue_report.py`.
- `04-qualified-to-deal.md`, `00-pre-send-checklist.md`.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

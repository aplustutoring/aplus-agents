---
name: journey-05-deal-open-pre-lesson
description: >-
  A PO or deal exists and the student is not yet on the calendar. Scheduling
  owns the family from here; the line switches to the support line; tutor
  selection and any statement of tutor availability belong to a scheduler.
status: DRAFT
owner_seat: scheduling_lead
reviewers: []
agent_readable: false
version: 0.1
---

# 05. Deal open, pre-lesson

This is the hand-over point. The family stops being a lead the moment a deal
exists, and every message to them changes line and identity. The Gonzalez
incident happened because an agent kept treating a family in this stage as a
lead.

## Entry marker

A deal at the Pre-Lesson stage in a charter pipeline (created by the PO agent,
`email/src/po_inbox.py`, when the PO lands) or in a private-pay pipeline
(created by hand or by the web purchase flow). Deal naming, stage ids, and
what fires automatically off the new deal: `docs/PO-PROCESS.md`, Stages 3 and 4.

## Exit marker

The deal moves to Post-Lesson after the first attended session
(`06-first-lesson.md`). The 72-hour target from Pre-Lesson to Post-Lesson is
stated only in the scheduler DM the PO agent sends (`_dm_scheduler` in
`email/src/po_inbox.py`); no sweep measures it.

## Owner seat

The assigned scheduler: `scheduler_a_l` for student last names A to L,
`scheduler_m_z` for M to Z (`email/config.yaml`, `scheduler_split`).
`scheduling_lead` watches the 72-hour window. The deal owner property carries
the same split.

## Channel and identity

Support line 818-869-1627 for texts, admin@ (the HubSpot conversations inbox)
for email, signed by the scheduler's first name or "A+ Tutoring Team". The
welcome text and What-to-Expect email go out automatically from here
(`email/src/sms.py`, `email/config.yaml` `sms:` block).

Never the charter_sales line, never signed Paola, once the deal exists. If the
family last wrote to us on the charter_sales line (a win-back reply, for
example), the scheduler's first message on the support line should say who
they are and that they are picking up from Paola. One handoff sentence
prevents "how many people am I talking to."

## What the agent may do alone, must draft, must ask

**Alone:** the transactional welcome text and email (standing, PR-locked copy in
`email/config.yaml`); the "no upcoming lessons" Slack alert; notes and tasks on
the deal.

**Draft:** replies to scheduling questions, for the scheduler to send from
admin@.

**Ask:** which tutor. A tutor's availability is stated to a family only by a
scheduler, after the tutor confirmed. An agent may carry a tutor's words to
the scheduler (`11-tutor.md`); it does not carry them to the family.

## Questions we ask the family here

- Preferred days and times, and how many sessions a week. Existing:
  `schedule_preferences` on the deal and the `_ask` texts in
  `email/config.yaml` (`charter_po_ask`, `gold_ask`, `trial_ask`).
- Online or in person (`online_or_in_person` in
  `ops/hubspot-schema/properties.yml`).
- Siblings on the same day or split (`student_names`, the multi-student
  texts).
- Who else should get lesson notes (the welcome email asks this).
- NEW, only when the family came through a win-back text: "You were texting
  with Paola. I'm {first name} on the scheduling side, and I'll take it from
  here." Not a question, a handoff line.

## Questions the agent asks itself here

- Is this family already in a thread on the support line or admin@? If yes,
  the scheduler owns every next message (checklist item 1).
- Did a welcome text already go out today? The SMS engine enforces one per
  family per 24 hours; nothing else does (checklist item 5).
- Has a tutor been named by a scheduler? If not, there is nothing to tell the
  family about tutors yet (checklist item 4).
- Is the PO's hour count on the deal, or blank because the amount fit two
  offerings? A blank means Kath has a task open; do not quote hours to the
  family.

## Where charter and private pay diverge

Charter: the PO fixes the hours; scheduling books against them; Kath converts
the PO to a Teachworks invoice the same day (`docs/PO-PROCESS.md`, Stage 5).
Private pay (Gold, In-Person, Free Trial): no PO; the welcome copy is
deliberately PO-free; the trial welcome asks for a card on file; billing method
in Teachworks is Service List Cost, not Package (`email/src/deal_sync.py`).

## Handoff out

- To the tutor: `11-tutor.md`, posted by or on behalf of the scheduler.
- To Kath: the "Convert PO to TW invoice" task the PO agent opens.
- To Paola: only if the family asks a funds or program question the scheduler
  cannot answer; DM with the thread link.
- Pattern: HubSpot task with a due date, Slack DM to the seat, note on the deal.

## Known gaps

- No code selects a tutor. No code books a lesson (the Teachworks client can
  create families and students, not lessons).
- The 72-hour target has no sweep and no escalation.
- The "no upcoming lessons" alert posts to `#email-agent` because
  `no_lessons_channel` is empty in `email/config.yaml`; no owner is named.
- A family whose last message was on the charter_sales line gets no automatic
  handoff sentence; today it depends on the scheduler noticing.

## Related

- `04-qualified-to-deal.md`: what happens before the deal exists.
- `06-first-lesson.md`: what happens after.
- `11-tutor.md`: how the tutor ask is made.
- `docs/PO-PROCESS.md`: the PO agent, Stages 3 to 5.
- `00-pre-send-checklist.md`.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

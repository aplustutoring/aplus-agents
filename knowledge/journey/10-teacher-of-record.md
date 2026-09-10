---
name: journey-10-teacher-of-record
description: >-
  The teacher-of-record track that runs beside the family track: who emails a
  teacher, about what, from which seat, and what we ask. Teachers are email
  only. The school issues the PO.
status: DRAFT
owner_seat: sales
reviewers: []
agent_readable: false
version: 0.1
---

# 10. Teacher of record (parallel track)

A teacher of record (TOR, also educational facilitator or education
specialist) issues the PO that funds a charter student. They are contacted
about students, never about themselves as customers.

## Entry marker

A contact with persona Teacher of Record/EF/ES. Created by the PO agent from
a PO (`email/src/po_inbox.py`, `TOR_CREATE_PROPS`), by an event booth, by the
teacher outreach lists, or by the new-teacher flow when a family names a
teacher we do not have (Roman 2026-09-08: ask the family for the email, then
create the contact with the same properties the PO agent uses, school from the
email domain, family linked).

## Exit marker

None. The track is ongoing; a teacher stays a teacher across families and
seasons. Per-student exits: the PO lands (`04` to `05`), or the teacher says
no student comes to mind.

## Owner seat

`sales` owns every teacher contact (Roman 2026-09-02, decision #AP046) and
speaks to teachers about many students. `charter_sales` speaks to a teacher
about one specific student (`CLAUDE.md`, sender routing). Sender identity
means from-name, reply-to, sign-off, and the follow-up task owner.

## Channel and identity

Email only. No call tasks, no meeting links, no "book a call"
(`ops/messenger/CAMPAIGN-2026-09-08-teachers.md`). Outreach sequences go from
danielle@ (HubSpot sequences, `ops/messenger/teacher-sequences.yml`); campaign
emails carry Danielle's from-name with reply-to routed to the sales seat. A
one-student email goes from the charter_sales seat's mailbox. Never SMS.

## What the agent may do alone, must draft, must ask

**Alone:** enroll teachers in the outreach sequences under the armed config
(`teacher_sequence_enroll`); create a teacher contact from a parent-supplied
email and link the family (intended standing go once `04` is REVIEWED); stamp
`[Agent] School` from the email domain.

**Draft:** the parent-info chase when a PO arrives without a parent (the PO
agent already drafts it, a human sends); the hours email for a returning
student (hours and the PO ask only; a returning teacher already has us as a
vendor and is never offered vendor details, Roman 2026-09-09); any reply to a
teacher.

**Ask:** anything that creates a teacher from a name alone (never; email
only), any teacher contact outside the sequence cadence, any mention of the
NSSA Badge outside the approved framings.

## Questions we ask the teacher here

- Outreach: "Is there a student who comes to mind?" and "If nobody does, that
  is a good answer" (CARE, an honest no).
- Returning family: "Reply with the name and I will send the vendor details
  and hours for the PO; once the school issues it we take everything from
  there" (`seq1_worked_with_us.md`).
- PO without a parent: parent or guardian name, email, phone, exactly those
  three (`email/src/po_inbox.py`, the chase draft), after checking whether the
  teacher recently spoke to us on a call.
- Never: "can you handle the PO for us?" The school issues it.

## Questions the agent asks itself here

- Many students or one? That decides the seat.
- Is this teacher already in a sequence? A sequence exits on reply; do not
  send a second thread beside it.
- Did this teacher email us in the last 14 days on charter@ or admin@? Then
  reply in that thread, same seat.
- Is the school known? `ops/hubspot-schema/school-aliases.yml` maps domains to
  the canonical school name; an unknown domain means flag, not guess.
- Is this a generic inbox (info@school)? `[Agent] Generic Inbox` marks those;
  they get no personal ask.

## Where charter and private pay diverge

Private pay has no teacher of record. This track is charter only. Level Up
(Terri) teachers cannot issue additional POs
(`no_teacher_email_pipelines` in the low-balance agent's config, unmerged), so
renewal asks for those families do not go to the teacher.

## Handoff out

- A teacher's reply naming a student: to charter_sales, `04`.
- A teacher's reply with parent info: the PO agent resolves the chase and
  syncs the deal.
- A teacher who wants a roster of last year's families: `scripts/teacher_roster.py`,
  pasted by the sales seat.
- Pattern: HubSpot sequence, Gmail draft labeled "A+ Agent/Draft Pending",
  note on the teacher and the family.

## Known gaps

- No template or code for the hours email; the sequence promises "vendor
  details and hours" to every teacher, but a returning teacher gets hours
  only (2026-09-09 rule above). The sequence copy still says vendor details.
- No vendor-details artifact in the repo.
- New-teacher intake automation (ask for email, create, link) is not built; it
  ran by hand on 2026-09-08 and the shape is recorded in `docs/CHANGELOG.md`.
- The Teacher Scholarship program's stage-1 emails still say "book a call",
  against the email-only rule; flagged as Danielle's call in the campaign doc.
- Most teacher contacts have no `a_persona` set; lead status is doing identity
  duty (`docs/CHANGELOG.md`, 2026-08-17 lead status entry).

## Related

- `04-qualified-to-deal.md`: where the teacher's PO matters.
- `ops/messenger/CAMPAIGN-2026-09-08-teachers.md` and
  `ops/messenger/templates/teacher-outreach-2026-09/`.
- `ops/hubspot-schema/school-aliases.yml`, `scripts/teacher_school_stamp.py`.
- `knowledge/credentials.yml` for the Badge claim.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

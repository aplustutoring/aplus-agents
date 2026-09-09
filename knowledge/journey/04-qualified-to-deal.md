---
name: journey-04-qualified-to-deal
description: >-
  The family wants tutoring and nothing is booked yet. Charter: confirm the
  teacher of record, send the teacher the hours, wait for the school's PO.
  Private pay: quote, payment, package. The biggest fork in the journey.
status: DRAFT
owner_seat: charter_sales
reviewers: []
agent_readable: false
version: 0.1
---

# 04. Qualified to deal

## Entry marker

Lead status QTL-Charter (charter funds), QTL-NEW, or QTL-Diagnostic Sent
(`ops/call_agent/call_agent.py`, the lead status ladder), or a yes to a
win-back message (`09-pause-stop-winback.md`).

## Exit marker

Charter: a deal exists at Pre-Lesson, created by the PO agent when the school's
PO lands in charter@ (`docs/PO-PROCESS.md`). Private pay: payment received and
a deal at Pre-Lesson in the Gold, In-Person, or Free Trial pipeline.

## Owner seat

`charter_sales` for the family. For the teacher: a teacher about one student is
`charter_sales`; a teacher for many students is `sales` (`CLAUDE.md`, sender
routing). The hours-and-vendor-details reply to a teacher is a human step
today.

## Channel and identity

The family is still a lead: charter_sales line 818-573-6644, "Paola with A+
Tutoring", or paola@. The teacher: email only, no calls, no meeting links
(`ops/messenger/CAMPAIGN-2026-09-08-teachers.md`), from the seat above.

## What the agent may do alone, must draft, must ask

**Alone (intended standing go once this stage is REVIEWED, Roman 2026-09-09):**
the teacher-of-record confirmation text after a family says yes; asking the
family for a new teacher's email when the name changed, then creating the
teacher contact the way the PO agent does (persona Teacher of Record, teacher
lead status, owner sales seat, school from the email domain via
`ops/hubspot-schema/school-aliases.yml`, family linked, note on both). Until
REVIEWED, both are per-go.

**Draft:** the hours email to the teacher (no template exists; see gaps); the
private-pay quote.

**Ask:** any relay of tutor availability (that is stage 05 and 11 territory);
any promise about start dates.

## Questions we ask the family here

- Charter: "Is {student}'s teacher of record still {teacher}, same as last
  year? Reply YES or send the new name." Nine of nine accepted on 2026-09-08.
- If changed: "Do you have an email address for {new teacher}?" One family
  replied with the address inside the hour.
- Days, times, sessions per week, subject focus. The family often volunteers
  this; take it down verbatim on the contact note.
- Private pay: online or in person, package size, who pays.
- NEW: "Has anyone else at A+ already been in touch about this?" Asked once,
  warmly, it prevents the double-thread problem before it starts.

## Questions we ask the teacher here

- Parent or guardian name, email, and phone, exactly those three, when the PO
  arrives without them (`email/src/po_inbox.py`, the parent chase). Check the
  teacher's recent call context first; the chase draft already does.
- For a returning family: "We spoke with {parent}; {student} is ready to pick
  back up with {tutor} at {schedule}. Here are the hours and our vendor
  details for the PO." No template exists for this; see gaps.

## Questions the agent asks itself here

- Has the school already issued a PO? Search deals for this family and
  charter@ for the student's name before asking the family anything about the
  PO.
- Is the teacher on file the right one? Family-to-teacher link (association
  type 15) first, the legacy `teacher_of_record_name` field second.
- Do I have a go to contact the teacher at all? Teacher contact is email-only
  and, for one student, the charter_sales seat's.
- Is this family already talking to scheduling? Then they are past this stage.

## Where charter and private pay diverge

Charter: family yes, teacher confirmed, hours to the teacher, school issues
the PO, PO lands, deal created, welcome text from the support line. The school
issues the PO; we never say we handle it. Every charter student has funds.
Private pay: quote from the seat (pricing is not in any template; the two
charter offerings are declared in `email/config.yaml`, `service_offerings`),
payment, Teachworks package, deal by hand. Private-pay stage markers are not
verified in the repo (open item).

## Handoff out

- To the teacher: the hours email, by the seat, by hand today.
- To Kath: nothing until the PO lands; then the PO agent takes over.
- To scheduling: the deal itself is the handoff. The family's stated days and
  times must be on the deal (`schedule_preferences`) so the welcome text asks
  to confirm rather than asking from scratch.
- Pattern: HubSpot note on the contact for every exchange, Gmail draft for
  the teacher email, Slack DM to the seat when a family asks a funds or price
  question.

## Known gaps

- No template and no code for the hours-and-vendor-details email to a
  teacher. The teacher outreach sequence promises it
  (`ops/messenger/templates/teacher-outreach-2026-09/seq1_worked_with_us.md`),
  and Danielle writes it by hand.
- No vendor-details artifact (rates, hours, how to issue the PO) in the repo.
- The high-dosage recommendation (Roman: three sessions a week, 45 minutes) is
  not written anywhere in the repo.
- Private-pay pricing lives only with the seats.
- Portal approval of a pending PO can take 14 or more days; the PO agent nags
  after `pending_portal_approval_days`.

## Related

- `03-discovery.md` before, `05-deal-open-pre-lesson.md` after.
- `10-teacher-of-record.md`: the teacher track.
- `docs/PO-PROCESS.md`: what happens when the PO lands.
- `00-pre-send-checklist.md`.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

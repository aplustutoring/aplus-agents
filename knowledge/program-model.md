---
name: program-model
description: >-
  A+ Tutoring's encouraged tutoring cadence (at least 8 to 12 45-minute
  sessions a month, two to three a week), what it rests on, how to offer it
  beside what a family asked for, and how it is priced without sticker shock.
  Read before quoting a schedule or hours to a family or a teacher of record.
status: DRAFT
owner_seat: visionary
reviewers: []
version: 0.2
---

# Program model: the cadence we encourage

## The recommendation

**At least 8 to 12 45-minute sessions a month, two to three a week, with the
same tutor.** Roman, 2026-09-09: "the recommended schedule is three times a
week, 45 minutes" and, the same day, "we encourage students to do at least 8
to 12 45-minute sessions monthly."

Priced from `knowledge/rate-card.yml`: 45-minute sessions are $60 each; hour
sessions are $75 per hour. The two are separate offerings, never pro-rated
from each other.

## What it rests on

The high-dosage (also called high-impact) tutoring model studied by the
National Student Support Accelerator at Stanford University: frequent
sessions (three or more a week), 30 minutes or longer, a consistent tutor,
one-on-one or very small groups, aligned to what the student is doing in
class. That is the design A+ built its program around.

Keep two things separate in any copy: the research on the model, and the
Badge A+ holds. The Badge (`knowledge/credentials.yml`, claim string verbatim,
never paraphrased) denotes the quality of our program design as reviewed by
NSSA; it does not denote outcomes and never sits inside a results claim.
"Our program follows the high-dosage model" is a design statement. "Stanford
validated our results" is false and is not to be written.

## How to offer it, and the sticker-shock rule

The family's stated cadence is the starting point, never the wrong answer.
Offer the range beside it and let them choose. **Quote the per-session or
per-hour rate. Never write a monthly dollar total** to a family or a teacher
(Roman 2026-09-09: "we can't sticker shock them"). The teacher computes the PO
amount from the sessions; the family hears a rate, not a bill.

> {Parent} asked for {their cadence}. We encourage at least 8 to 12
> 45-minute sessions a month, two to three a week, which is where we see
> students settle in fastest; 45-minute sessions are $60 each and hour
> sessions are $75 per hour. Either works, and we are glad to start where the
> family is comfortable and add sessions as {student} gets going.

Rules that apply (pointers, not restated): every charter student has funds,
never "students with funds"; the school issues the PO, we send the teacher
the hours (`ops/messenger/CAMPAIGN-2026-09-08-teachers.md`); no em dashes
(`CLAUDE.md`); never name an inactive tutor
(`ops/hubspot-schema/properties.yml`, `last_tutor_active`).

## Cadences we see, for staff only

For the seat's own math when a teacher asks "how many hours should the PO
say." Not for copy.

| Cadence | Unit | Per PO month |
|---|---|---|
| 1 x 60 min | hour, $75 | 4 hours |
| 2 x 60 min | hour, $75 | 8 hours |
| 3 x 60 min | hour, $75 | 12 hours |
| 2 x 45 min | session, $60 | 8 sessions |
| 3 x 45 min (top of the encouraged range) | session, $60 | 12 sessions |

In-person and private-pay rates are in `knowledge/rate-card.yml`; where that
file says null, the seat quotes by hand and the number does not go in agent
copy.

## Where this is referenced

Stage files `knowledge/journey/04-qualified-to-deal.md` and
`08-renewal.md`; the teacher hours-request drafts. Agents that quote a
cadence read this file; they do not restate the numbers in their prompts.

## Version

- v0.2 (2026-09-09): range framing (8 to 12 sessions a month) and the no
  monthly total rule, per Roman the same day.
- v0.1 (2026-09-09): first write-down.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

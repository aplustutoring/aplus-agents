---
name: program-model
description: >-
  A+ Tutoring's recommended tutoring cadence (three 45-minute sessions a
  week), what it rests on, how to offer it beside what a family asked for,
  and how it is priced. Read before quoting a schedule or hours to a family
  or a teacher of record.
status: DRAFT
owner_seat: visionary
reviewers: []
version: 0.1
---

# Program model: the cadence we recommend

## The recommendation

**Three sessions a week, 45 minutes each, with the same tutor.** Roman,
2026-09-09: "the recommended schedule is three times a week, 45 minutes."

Per week: 2 hours 15 minutes. Per PO month (four weeks): about 9 hours.
Priced from `knowledge/rate-card.yml`: 9 hours at the online charter rate of
$75 per hour is $675 a month.

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

## How to offer it

The family's stated cadence is the starting point, never the wrong answer.
Offer the recommendation beside it, priced, and let them choose:

> {Parent} asked for {their cadence}. Our recommended cadence is three
> 45-minute sessions a week, about 9 hours a month, which is where we see
> students settle in fastest. Either works; we are glad to start where the
> family is comfortable and add sessions as {student} gets going.

Rules that apply (pointers, not restated): every charter student has funds,
never "students with funds"; the school issues the PO, we send the teacher
the hours (`ops/messenger/CAMPAIGN-2026-09-08-teachers.md`); no em dashes
(`CLAUDE.md`); never name an inactive tutor
(`ops/hubspot-schema/properties.yml`, `last_tutor_active`).

## Common cadences, priced (online charter, $75 per hour)

| Cadence | Hours per week | Hours per PO month | Monthly amount |
|---|---|---|---|
| 1 x 60 min | 1 | 4 | $300 |
| 2 x 60 min | 2 | 8 | $600 |
| 2 x 30 min | 1 | 4 | $300 |
| 3 x 45 min (recommended) | 2.25 | 9 | $675 |
| 3 x 60 min | 3 | 12 | $900 |

Per-session pricing and in-person rates are in `knowledge/rate-card.yml`;
where that file says null, the seat quotes by hand and the number does not go
in agent copy.

## Where this is referenced

Stage files `knowledge/journey/04-qualified-to-deal.md` and
`08-renewal.md`; the teacher hours-request drafts. Agents that quote a
cadence read this file; they do not restate the numbers in their prompts.

## Version

- v0.1 (2026-09-09): first write-down. Numbers from Roman; pricing from the
  rate card. DRAFT until Roman reviews.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

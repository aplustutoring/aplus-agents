---
name: aplus-outbound-copy
description: The locked rules for anything a family, teacher, or tutor reads. Load before writing or reviewing any email, SMS, draft, template, campaign copy, or agent-generated message, and before building an agent that can send one. Covers who we text from which line, quiet hours, the PO language, the scholarship language, first names, em dashes, and the pre-send gate. Triggers: "write an email", "draft a text", "campaign copy", "message the family", "reach out to", "send a reminder", "what should we say".
---

# Outbound copy: the locked rules

Ground all reasoning and output in A+ CARE core values: `ops/values/care-values.md`.

Before contacting a family, teacher, or tutor, read `knowledge/journey/README.md`
and pass `knowledge/journey/00-pre-send-checklist.md`. Act only on stages marked
REVIEWED.

Every rule here was locked by Roman after a specific message went wrong. None of
them are style preferences.

## The gate, before the words

You do not get to the copy rules until the six pre-send checks pass:
`knowledge/journey/00-pre-send-checklist.md`. In short: who already has this
thread, which line and identity, is there a go for exactly this audience and
message, who confirmed any tutor time you are about to name, what did this
person already hear from us today, and is this a reply or a new touch. A fail
means hand off, not send.

**"Watch" authorizes reading and reporting only.** Relaying, posting and
texting are coordinating, and each needs its own go.

## Who sends, and from where

| Situation | Seat | Channel |
|---|---|---|
| No deal yet (a lead) | charter_sales | Text from **818-573-6644** |
| Deal exists (scheduling) | scheduler | Text from **818-869-1627** |
| Teacher about ONE specific student | charter_sales | Email only |
| Teacher, to acquire MULTIPLE students | sales | Email only |
| Any family message | charter_sales | Per the deal test above |
| Tutor | scheduler | Their private Slack channel, or SMS from the support line if they have none |

Sender identity means all four: from-name, reply-to, sign-off, and the owner of
the follow-up task. Never change identity mid-thread.

**Teachers are email only.** No call tasks, no meeting links, no "book a call"
CTA. The personal touch is a hand-written email from the sales seat.

## Timing

- Transactional SMS: **8 AM to 8 PM PT**, business days.
- Bulk messenger: **9 AM to 8 PM PT** (`ops/messenger/config.yml`, TCPA-safe).
- Use the stricter window when unsure. No agent texts a family or asks a school
  for a PO on a Saturday.
- Every inbound text is acknowledged within **1 hour**.
- A STOP line is required on any SMS that is a **new touch**. Not required on a
  reply inside a live thread.

## Language, locked

**No em dashes. No double hyphens.** Not in emails, SMS, drafts, marketing copy,
or anything a customer reads. Use periods, commas, or parentheses. Internal docs
and code comments are fine. (Roman 2026-08-24.)

**First names only.** Students, parents, tutors and teachers are all first name
in anything a family or teacher reads. Full names are staff-side only.
(Roman 2026-09-09.)

**Every charter student has funds.** Never write "students with funds", and
never make funds conditional. The scholarship value is "this does not touch
their allocation", not "no funds needed". (Roman 2026-09-02.)

**The school issues the PO, we do not.** Never promise "we handle the PO". The
copy is: reply with the student's name, we send vendor details and hours for the
PO, and we take over once the school issues it. (Roman 2026-09-02.)

**Parents can submit the PO themselves, and we prefer that.** The teacher is the
backup, named in email only, never in an SMS. (Roman 2026-09-09.)

**Returning teachers get no vendor information.** A teacher who has issued us a
PO before never receives "if you need our vendor details". The ask is the PO and
the hours. Vendor details are for schools new to A+ only. (Roman 2026-09-09.)

**Get the PO first, then scheduling.** A tutor's offered time stays internal and
is never relayed to a family before the deal exists. (Roman 2026-09-10.)

**Credentials are quoted, never paraphrased.** Claim strings live in
`knowledge/credentials.yml` and carry their term window. A claim without its
date range is a defect. `public_ready: false` is a hard gate. The NSSA badge
claim never appears in an SMS.

## Rates

$75 per hour, or $60 per 45-minute session. Never pro-rated. Three 45-minute
sessions a week is 12 sessions a month, which is $720. (Roman 2026-09-09.)
These are not yet in a config file, so if a quote needs a variant, ask before
writing it.

## Escalation

All escalation goes to Emily. Never name a scheduling lead in customer copy, and
never name anyone who cannot receive the work.

## What good looks like

From the re-engagement analysis (2026-09): win-back copy worked **only** when it
named the specific tutor and the specific student. Nameless copy got zero
replies. Specificity is not a nicety here, it is the entire difference between
a reply and silence.

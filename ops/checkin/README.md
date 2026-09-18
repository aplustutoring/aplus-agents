# ops/checkin — the quality check-in, owned by us instead of by a Zap

## Measure first

Before changing anything, 7 days of live traffic through the existing HubSpot
workflow "Quality - 2.0" (1680794394 → Zapier hook):

| | |
|---|---|
| sends | 9 |
| replies | 8 (89%) |
| replied within 1h | 7 |
| substantive replies | 5 (56% of sends) |
| **collisions** | **1 (11% landed within an hour of a human message)** |

An 89% reply rate is exceptional, and the substance is the whole point. In one
week it surfaced a family leaving over price, two service gaps nobody had
reported through any other channel, and an unprompted testimonial:

- *"we are exploring other services before we make a final decision"* — Judy Goldzweig
- *"she has no homework or book to follow"* — Miran Mavlan
- *"we just do not know the plan, so she not able to preview for the class"* — Albee Li
- *"all the lessons went amazing. You were totally right. It worked. I was doubting a virtual tutoring session"* — Lesly Elenes

**So the campaign is not the problem.** Three narrow things are.

## The three fixes

**1. The gate.** One send in nine interrupted a live conversation. Albee Li got
"hope you are doing well, wanted to check in" fifteen minutes after a scheduler
had apologised to her about the very lesson she was complaining about. This
agent skips anyone messaged in the last 48 hours, anyone with an open ticket,
anything outside business hours on a weekday, and sends at most once per family
per day. It also sends once per FAMILY, not once per deal: the first dry run
planned six identical texts to one parent because charter families have a deal
per purchase order slice.

**2. The copy.** The old text named nobody and could have been about any child
at any company. This one names the student and the tutor, and closes by asking
what they would like focused on **next**. "How is it going" gets "fine". Asking
what to focus on next is what produced Miran's missing homework and Albee's
missing lesson plan.

**3. Triage.** Nothing caught what the campaign found. Judy told us she was
leaving over cost and was answered with "let me know if there's any other way I
can assist". Now a reply matching a churn or service-gap phrase opens a HIGH
ticket for that student's scheduler with the family's own words on it.

## Naming a tutor safely

`schedule_preferences` holds two shapes at once, because deals written before
2026-09-16 kept the raw Teachworks value:

    "Tuesdays 6:00 PM with Seifeldin, Youssef"   -> Youssef
    "Mondays 10:00 AM with Sonya"                -> Sonya

Taking the token after "with" yields the SURNAME on the first shape. That is
the same mistake that told Nikita Brixey her son's tutor was "Karl", which is
Sonya's surname, and made her reply *"I don't know who Karl is?"*.

So the extractor captures the whole pair, runs it through `first_name()`, and
then checks the result against the first names of real tutor contacts. A name
that is nobody's first name is dropped. The first dry run produced "sessions
with Siddiqui" before that check existed.

Two distinct tutors in one schedule means naming neither.

## Known data gap

In the first live dry run, **11 of 12 families in Post-Lesson had no tutor on
the deal** — most still read "we don't have your schedule on file yet". The
personalisation works; the data to power it is mostly missing. Worth fixing
upstream, because the tutor's name is the single thing that makes this text
feel like it came from someone who knows the child.

## Running

    python3 ops/checkin/checkin.py [--dry-run] [--triage-only] [--report-json PATH]

Ships with `armed: false`. It plans and prints and writes nothing customer
facing until Roman flips it. First run stamps a baseline and sends nothing;
that is not configurable off.

## Cutover

This does not replace the Zap by itself. Until "Quality - 2.0" is paused in
HubSpot, both would send. Order: read a dry run, flip `armed`, then pause the
workflow, then delete the Zap.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

Before contacting a family, teacher, or tutor, read knowledge/journey/README.md
and pass knowledge/journey/00-pre-send-checklist.md. Act only on stages marked
REVIEWED.

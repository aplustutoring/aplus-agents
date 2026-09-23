# Handoff: build tutor agents A, B and C

Paste this whole file into a fresh Claude Code session. It is written to be
self-contained.

---

## What you are building

Three agents about tutor quality, in this order. **A spec goes to Roman before
any code on each one. He is the sole merge gate.**

| | Agent | One sentence |
|---|---|---|
| **A** | Tutor evaluation | Score every active tutor against the 6-category rubric, on a cadence, from evidence the systems already hold |
| **B** | Tutor accountability | Turn a scored problem into a ticket someone owns, and close the loop when it is fixed |
| **C** | Onboarding completeness | Tell us which newly onboarded tutors are missing something required, before they teach |

**Agent D (the Moneyball tutor score) is explicitly NOT to be built.** If asked,
produce a data-availability report only: what exists, what does not, what would
have to be collected. Nothing else.

Anything beyond A, B, C is a suggestion for Roman, not a PR.

---

## Why these three, and what already exists

**A** is the machine half of an EOS rock: "Every Tutor Scored", a 6-category
NSSA-aligned rubric, 100% of tutors scored with a recurring cadence. The rubric
is the seat holder's; you are not inventing it. `ops/call_agent/rubric.md` is the
precedent for how a rubric is expressed in this repo and scored by a model, and
`#flagged-lesson-notes` already posts per-lesson note-quality judgements, which
is one input, not the whole score.

**B** partly exists. `ops/tutor-issues/` files tickets for five issue types and
is live. Read it before designing anything: you are extending a working engine,
not replacing it. Its guards (baseline-stamp on first run, one open ticket per
tutor per type per period, one digest per run, hard caps) are the house style.

**C** is currently a human chain: Kath posts "another tutor has been onboarded"
in `#support-team`, and a scheduler chases certificates in the tutor's private
Slack channel. The required items include an approved Child Abuse Mandated
Reporter training certificate. The agent's job is to notice what is missing, not
to chase it itself.

---

## Rules that are not negotiable

These are Roman's, locked, and most were written after something broke.

**Roles, never names.** Config keys, properties and audit actions name a role
(`tutor_quality_owner`, `operations`, `scheduler_split`). The `staff:` block is
the only home for a person. On 2026-09-17 a seat was vacated and 173 items piled
up on a dead owner because agents pointed at a person.

**Check the seat is occupied.** Before handing work to a human, confirm they are
on the roster. `#tutor-issues` @-mentioned a departed employee on every run for
days, and five family no-show reports were handed to nobody.

**Refuse rather than guess.** An unresolvable tutor means no ticket. A
low-confidence read means no action. But a refusal must reach a live person and
be re-asked if it is not picked up. Log *what you saw*, not just that you
declined: `low confidence (0.40)` with no text is a dead end nobody can improve.

**Never assert silence you cannot prove.** Tutors live in Slack, not SMS. A
checker that reads only one channel called an actively-supported tutor neglected
for 68 hours. If you claim someone was not contacted, read text, call, email
*and* Slack.

**Do not re-derive who a person is.** `deal_sync._deal_contact`,
`router.scheduler_for_last_name` and `email/src/names.py` already answer family,
scheduler and first name. A script that read surnames out of subject lines would
have dropped 150 tasks on one scheduler in a single run. Read the associated
contact; never parse a name out of free text.

**Guards, every time.** Ship OFF behind a config flag. `DRY_RUN` writes nothing.
First run stamps a baseline and acts on nothing. One digest per run, never a DM
per item (a dry run once fired 80 DMs). A hard cap per run. State, not the time
window, prevents repeats. An unreadable data source aborts the run rather than
being read as "nothing happened".

**Copy rules if anything is tutor-facing.** No em dashes. First names only.
Nothing goes to a family, teacher or tutor without passing
`knowledge/journey/00-pre-send-checklist.md`, and only stages marked REVIEWED are
readable.

**Tests carry the history.** Every test in this repo is a bug that shipped, and
the docstring says which one. Pin the clock: a time-dependent test passed the day
it was written and failed five days later.

**Process.** Work in a git worktree, never the shared checkout. Append to
`docs/CHANGELOG.md` with what changed and *why*. Show the diff before opening the
PR. Never say a stage ID number to Roman; stage names only.

---

## Agent A: tutor evaluation

**Question it answers:** how is each active tutor doing, on the same six
categories, every cycle, without anyone filling in a form.

**Before designing:** get the rubric from the seat that owns it. Do not invent
categories. Ask what a score is *for*: a conversation, a pay band, a match
decision. The answer changes the design.

**Evidence the systems already hold**, all of which is cheaper than asking a
human: lesson notes quality (already judged per lesson), attendance and
punctuality from Teachworks, notes-completion rate, family sentiment from call
summaries and inbound messages, tutor responsiveness in their Slack channel,
open accountability tickets, retention of the students they teach.

**The trap:** a score built only from what is easy to count will measure
compliance, not teaching. Say so in the spec and name what the score cannot see.

**Output:** a score per tutor per cycle, written to HubSpot as `[Agent]`
properties, plus one digest. It does not tell the tutor anything. A score that
reaches a tutor without a human deciding to send it is a firing offence for an
agent.

## Agent B: tutor accountability

**Question it answers:** when a tutor has a problem worth acting on, who owns it
and how do we know it got fixed.

**Read `ops/tutor-issues/` first.** It already opens tickets for missed lessons,
unmarked notes, tutor-change requests, scheduling flip-flops, tech issues and
unresponsiveness in Slack. Extend it. Do not start a second engine.

**What is missing today, in order of value:**

1. A refusal that reaches a live person and is re-asked. Five family reports of a
   tutor no-show were refused at low confidence and handed to a departed seat.
2. Closure. A ticket opens; nothing watches whether the behaviour changed.
3. Pattern over instance. Three chases in a month should be one ticket showing
   three, which the config already intends (`rolling_30d`) but nothing verifies.

**The trap:** this agent accuses people. A tutor was nearly ticketed for being
mid-lesson nine minutes after a Slack message. Every rule needs the question
"what innocent explanation does this fail to consider", answered in the spec.

## Agent C: onboarding completeness

**Question it answers:** which tutors have started, or are about to, without
everything we require.

**Inputs:** the onboarding announcements in `#support-team`, the tutor's HubSpot
record, `tutor_roster_status`, Teachworks profile existence, and the certificate
list the scheduler currently chases by hand.

**Output:** one digest naming each incomplete tutor and exactly what is missing,
to the seat that owns onboarding. Not to the tutor.

**The trap:** "missing" is usually "we were never told", not "they did not do
it". The digest should read as a checklist, never as an accusation, and a tutor
with a missing item who has not yet taught is a different urgency from one who
has.

---

## Sequence

C, then B, then A. C is the smallest and its output is unambiguous. B builds on
a live engine. A needs the rubric and a decision about what the score is for,
which is the slowest thing to get.

Spec to Roman on each before code. Ship every one OFF.

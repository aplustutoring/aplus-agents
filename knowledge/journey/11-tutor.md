---
name: journey-11-tutor
description: >-
  How we contact a tutor about a student: where each tutor lives (Slack
  channel, team group DM, or SMS on the support line), what an ask contains,
  who decides the match, and what a tutor's reply is and is not.
status: DRAFT
owner_seat: scheduling_lead
reviewers: []
agent_readable: false
version: 0.1
---

# 11. Tutor (parallel track)

Tutors are part of the team, not customers, and the channel rules are
different from the family track. This file covers the ask "can you take this
student?" and what to do with the answer.

## Entry marker

A scheduler or charter_sales has named a tutor for a specific student, either
because the family asked for them by name (a win-back reply, a returning
family) or because the scheduler matched them.

## Exit marker

The tutor confirms days and times, or declines, in their own channel or by
text. A confirmation is an offer to the scheduler, who books it and tells the
family.

## Owner seat

The assigned scheduler (`scheduler_a_l` or `scheduler_m_z`) owns the match and
the booking. `scheduling_lead` owns tutor quality and the tutor roster.

## Channel and identity

Where each tutor lives, verified 2026-09-08:

- Most active tutors have a private Slack channel named `#first-last` (for
  example `#cathy-westcot`, `#stephanie-torres`, `#jonathan-szatkowski`,
  `#kelly-james`). Post there, tag the scheduler and Paola.
- Tutors without a channel have a group DM with the whole team. Find it with
  Slack search `from:<@tutor>` filtered to group DMs.
- SMS-only tutors (Christa is one, Roman 2026-09-08) are texted from the
  support line 818-869-1627, never the charter_sales line. A tutor
  conversation is scheduling, not sales.

Identity: the person posting, by name. The aplus bot cannot post in private
tutor channels it is not a member of and cannot open group DMs (no
`mpim:write`), so today a human or a human's Slack token posts.

Wrong-channel guard: first names are not unique across all tutor records (ten
Stephanies in HubSpot) but are unique among tutors with an active roster
status. Before mapping a first name to a channel, confirm exactly one tutor
with that first name has an active roster status
(`tutor_roster_status` in `ops/hubspot-schema/properties.yml`) and that the
Slack user matches.

## What the agent may do alone, must draft, must ask

**Alone:** look up the tutor's channel and roster status; read replies and
report them to the scheduler.

**Draft:** the ask text, for the scheduler to post, until the tutor-ask
standing go exists (Roman 2026-09-09: intended, once this stage is REVIEWED).

**Ask:** which tutor, always. An agent posts a tutor ask only for a tutor a
scheduler or charter_sales named. It never picks.

## What an ask contains

- Student first name, school, charter or private pay.
- What the family asked for: days, times, sessions per week, subject focus,
  anything the parent said that helps (a reading level, "not a morning
  person").
- Teacher-of-record status: confirmed, or being confirmed.
- PO status: hours going to the teacher, or PO already on file.
- The question: "Can you take {student} on {days} at {times}?" and "Reply here
  with what works, and {scheduler} will lock it in once the PO lands."
- Never the family's phone number or email.

## Questions we ask the tutor here

- Can you take this student, at these days and times?
- If not those, what do you have open?
- Anything that changes soon (a class, a job) that the scheduler should know?
- For a returning pair: anything from last year the family should hear from us
  (subject shift, what worked)?

## Questions the agent asks itself here

- Did a scheduler or charter_sales name this tutor? If not, stop (checklist
  item 4).
- Is this tutor active on the roster and unique by first name?
- Has this tutor already been asked about this student in the last 14 days?
  Read the channel before posting.
- Is the tutor's reply an offer to the family? No. It goes to the scheduler,
  who books and tells the family from the support line.

## Where charter and private pay diverge

Charter: the tutor's availability has to fit the PO's hours; the ask says
whether hours are on file. Private pay: the ask says the package or trial
length instead. The channel rules are the same.

## Handoff out

- To the scheduler: the tutor's answer, verbatim, in the family's HubSpot note
  and a Slack DM if the scheduler is not in the channel.
- To scheduling_lead: a tutor who declines twice, or who reports a schedule
  change that affects other students (`ops/tutor-issues/` is the quality
  channel, `#tutor-issues`).

## The repeat ask (Roman 2026-09-09)

No reply in six hours: one repeat in the same channel, more direct, with a
deadline and the consequence ("if we do not hear back we will set {student}
up with another tutor so the family is not left waiting"). Tag charter_sales.
After the deadline the scheduler reassigns. Before calling a tutor silent,
read the replies under every ask we posted (Slack threads), the channel's
top-level messages alone are not the record. A tutor who already answered
and gets the repeat anyway reads it as not being listened to.

## Known gaps

- Reading Slack thread replies is a manual step; the Monitor tick and the
  session scripts read channels, not threads, until a script does it.
- Tutor-ask automation is not built. The bot lacks the Slack scopes for group
  DMs and is not in the private channels.
- No file maps tutor to channel; it was discovered by search on 2026-09-08 and
  recorded in the session memory, not the repo. A `tutor_slack_channel`
  property or a config map is an open item.
- Two Christa HubSpot records, one with the phone and one with the email.

## Related

- `05-deal-open-pre-lesson.md`: the stage that raises the ask.
- `ops/tutor-issues/config.yml`: tutor quality signals and their owner.
- `00-pre-send-checklist.md`, item 4.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

---
name: journey-00-pre-send-checklist
description: >-
  Six yes-or-no checks every agent and human passes before any outbound
  message to a family, a teacher of record, or a tutor, on any channel. Each
  check names the lookup, the answer you must write down, and what counts as a
  fail. A fail means hand off, not send.
status: DRAFT
owner_seat: visionary
reviewers: []
agent_readable: false
version: 0.1
---

# 00. Pre-send checklist

Run this before any outbound message to a family, a teacher of record, or a
tutor, on any channel, at any stage. Write the six answers into the HubSpot
note on the contact (or the run log) before sending. If any item fails, do not
send. Use the table at the bottom to hand off.

Why six items: each one is a question the agent did not ask on 2026-09-09.
Together they would have stopped the Gonzalez texts.

## 1. Who already has this thread

**Look up** the contact in every place a conversation can live:

- JustCall, support line 818-869-1627
- JustCall, charter_sales line 818-573-6644
- HubSpot conversations inbox (admin@), by contact
- charter@ threads (the PO agent's mailbox)
- danielle@ and paola@ sequences
- open HubSpot tickets and tasks on the contact
- for a tutor: the replies under every ask we posted in their Slack channel
  or group DM, not just the channel's top-level messages

Do not use `hs_email_last_reply_date`. Inbox replies never stamp it. Scan the
threads. In Slack, a tutor's answer lives in the thread under our ask;
reading the channel alone shows nothing and makes a tutor who answered look
silent (2026-09-09: Tarisa and Aesha had both replied in-thread and got a
deadline nudge anyway. Tarisa: "I have been replying! in the thread!").

**Write:** one line per source, either "none" or "thread {id}, last message
{date}, from {them or us}, owner {seat}".

**PASS:** every source is "none", or every open thread is owned by the seat you
are acting for.

**FAIL:** any thread with a message in the last 14 days owned by a seat you are
not acting for. Scheduling has the family on the support line means you do not
text from the charter_sales line, whatever the deal state says.

## 2. Which line and identity

**Look up** the contact's deals. Any deal at Pre-Lesson or later in the current
season?

**Write:** "deal {id}, stage {name}: support line, scheduler identity" or "no
deal: charter_sales line, Paola identity". For a teacher: "teacher about one
student: charter_sales by email" or "teacher for many students: sales by
email". For a tutor: "tutor: Slack channel {name}" or "tutor: support line
SMS".

**PASS:** the line and identity you are about to use match what you wrote.

**FAIL:** you cannot state the deal result, or the line contradicts it. Rule
source: `ops/messenger/config.yml` (Roman 2026-09-08, locked) and the identity
map in `README.md`.

## 3. Standing go or per-action go

**Look up** the instruction that authorizes this send. Quote it: person, date,
words. A go covers exactly one audience, one template or message, one line,
one time window. A standing go is one written in `email/config.yaml`
(`presend.standing_go`) for a stage that is REVIEWED.

**Write:** the quote, and which of the four it covers.

**PASS:** the quote covers this audience, this message, this line, now.

**FAIL:** any of the four differs, or the instruction was about watching,
tallying, summarizing, or reporting. "Watch for responses" authorizes reading
and reporting only. Relaying, posting, and texting are coordinating, and each
needs its own go until a standing go exists.

## 4. Who decides tutor offers and tutor matches

**Look up** the source of any tutor availability or tutor name in your message.

**Write:** "no tutor availability in this message", or "availability stated by
{scheduler seat} on {date} after {tutor} confirmed in {channel}", or "tutor
named by {scheduler seat or charter_sales} on {date}".

**PASS:** one of those three, with the seat and date filled in.

**FAIL:** the message tells a family a tutor "has openings" or "can take" a
slot without a scheduler's confirmation in the note, or you are posting a tutor
ask for a tutor nobody at A+ named. A tutor's own words in their channel are
an offer to the scheduler, not to the family.

## 5. What this person already heard from us today

**Look up** outbound touches to this contact in the last 24 hours across every
source in item 1: JustCall outbound on both lines, Gmail sent, HubSpot
conversation replies, `[Agent]` notes. The transactional SMS engine enforces
one text per family per 24 hours on its own; nothing else does, so count by
hand.

**Write:** the count and the sources.

**PASS:** the count is 0, or this message is a reply inside the same thread
(item 6).

**FAIL:** the count is 1 or more and this is a new touch. Three texts in an
hour from two numbers is what "too many people" looks like from the family's
side.

## 6. Reply inside a live thread, or a new touch

**Look up** the most recent message in the thread you are about to use. Is it
from the contact?

**Write:** "reply: same line, same identity, same thread as their last message"
or "new touch".

**PASS:** a reply, or a new touch where items 1 to 5 pass and item 3 quotes a
per-action go.

**FAIL:** a new touch on a different line from the one the contact last used,
or a "reply" that changes identity mid-thread.

## Then the copy gate

Pointers only, each rule lives in one place:

- No em dashes or double hyphens: `CLAUDE.md`, outbound style.
- The school issues the PO; we send the teacher the hours:
  `ops/messenger/CAMPAIGN-2026-09-08-teachers.md`.
- Every charter student has funds: same file.
- Tutor first names only, never an inactive tutor:
  `ops/hubspot-schema/properties.yml`.
- NSSA Badge only via the claim string in `knowledge/credentials.yml`, never
  in an SMS.
- Quiet hours: 8 AM to 8 PM PT for transactional SMS (`email/config.yaml`),
  9 AM to 8 PM PT for the bulk messenger (`ops/messenger/config.yml`). Use the
  stricter one when unsure.
- STOP line: required on any SMS that is a new touch. Not required on a reply
  inside a live thread (Roman 2026-09-08).

## If an item fails

| Failed | Do this instead of sending |
|---|---|
| 1 or 6 | Slack DM the owning seat with the thread link and what the contact said. |
| 2 | Stop. Ask charter_sales and the scheduler which line owns this family. |
| 3 | Post the proposed message, audience, line, and window where Roman can see it, and wait for a go. |
| 4 | Post the tutor's words to the scheduler (`11-tutor.md`), not to the family. |
| 5 | Hold until the 24-hour window clears, or the owning seat says otherwise. |

## Related

- `README.md`: the journey table and identity map.
- `email/config.yaml`: `presend:` block (PR B), the standing-go list and the
  code that runs these checks for SMS.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

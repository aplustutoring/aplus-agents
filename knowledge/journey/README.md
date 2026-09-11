---
name: journey-playbook
description: >-
  The A+ customer journey, first touch to renewal, for charter and private pay,
  with the pre-send checklist every agent and human passes before contacting a
  family, a teacher of record, or a tutor. Read before any outbound contact.
status: DRAFT
owner_seat: visionary
reviewers: []
agent_readable: false
version: 0.1
---

# Customer journey communication playbook

## Why this exists

On 2026-09-09, during the charter SMS win-back round, an agent told to "watch
for responses" relayed tutor availability to families and posted tutor asks on
its own. The Gonzalez family was texted from Paola's lead line while scheduling
had already booked them on the support line. Mom wrote back: "I don't know how
many people I'm talking to at A+." Roman: "I love the initiative, this is the
future, but we have to learn more and ask questions... what questions to ask,
and tie everything together." The incident record is in `docs/CHANGELOG.md`
(2026-09-08 and 2026-09-09 entries).

This playbook is the answer. It walks the journey top of funnel to renewal, and
for every stage says who owns it, which identity speaks, what an agent may do
alone, and which questions to ask, of the family and of itself, before acting.

## Purpose, when to apply, when not to

**Apply** before any outbound message to a family, a teacher of record (TOR),
or a tutor, on any channel: SMS, email, Slack, a HubSpot sequence, a marketing
email, a call task. Humans and agents alike.

**Do not apply** to internal Slack (team channels, digests, DMs to seats),
marketing content that is not addressed to a known person (blogs, spotlights,
the brand kits in `marketing/skills/` govern those), or reading and reporting.
Reading is always allowed. Reporting is always allowed. "Watch" means read and
report; it never means send.

## The journey in one table

| # | Stage | Enters when | Leaves when | Owner seat | Line or inbox | File | Status |
|---|---|---|---|---|---|---|---|
| 01 | First touch | contact created, lead status New (Inbox) | first two-way exchange | charter_sales (families), sales (teachers) | the channel the contact used | `01-first-touch.md` | DRAFT |
| 02 | Attempting to contact | lead status Attempting to Contact | meeting booked, QTL status, or dead | charter_sales | charter_sales line, paola@; danielle@ for teachers | `02-attempting-to-contact.md` | DRAFT |
| 03 | Discovery | Meeting Booked, or a live call | a QTL status | charter_sales | phone, main line | `03-discovery.md` | DRAFT |
| 04 | Qualified to deal | QTL-Charter / QTL-NEW / QTL-Diagnostic Sent | a deal exists at Pre-Lesson, or payment received | charter_sales; TOR hours request is a human step | charter_sales line for the family, email for the teacher | `04-qualified-to-deal.md` | DRAFT |
| 05 | Deal open, pre-lesson | deal at Pre-Lesson | deal at Post-Lesson | scheduler (A to L Janelle, M to Z Yolanda), scheduling_lead | support line, admin@ | `05-deal-open-pre-lesson.md` | DRAFT |
| 06 | First lesson | first session on the calendar | first session attended | scheduler, scheduling_lead | support line, admin@ | `06-first-lesson.md` | DRAFT |
| 07 | Active service | Post-Lesson | invoice submitted and paid, or package exhausted | by category, routing table in `email/config.yaml` | support line, admin@, charter@ for billing | `07-active-service.md` | DRAFT |
| 08 | Renewal | low balance, last PO month, package near zero | new deal (existing business) or 09 | charter_sales | open decision, see file | `08-renewal.md` | DRAFT |
| 09 | Pause, stop, win-back | Stopped stage, Past Customer, Check Back Quarterly, Dead | reply yes (back to 04) or dead | charter_sales | charter_sales line (no deal = lead again) | `09-pause-stop-winback.md` | DRAFT |
| 10 | Teacher of record (parallel track) | a TOR contact exists | ongoing | sales (many students), charter_sales (one student) | email only | `10-teacher-of-record.md` | DRAFT |
| 11 | Tutor (parallel track) | a tutor is named for a student | tutor confirms or declines | scheduler, scheduling_lead | tutor's Slack channel, team group DM, or support line SMS | `11-tutor.md` | DRAFT |

The pre-send checklist, `00-pre-send-checklist.md`, applies at every stage and
must be REVIEWED before any stage file is readable by an agent.

## Identity map

Who speaks, from where, and when. Seats are role keys from `email/config.yaml`
(`roles:`); people are named only in that file's `staff:` block. Line numbers
for the JustCall lines are in `ops/messenger/config.yml` and
`email/config.yaml` (`sms:`).

| Seat | From-name | Line or inbox | Speaks when |
|---|---|---|---|
| charter_sales | "Paola with A+ Tutoring" | charter_sales line 818-573-6644, paola@ | a family with NO deal yet (a lead); a teacher about ONE student |
| scheduler_a_l, scheduler_m_z, scheduling_lead | scheduler's first name | support line 818-869-1627, admin@ (HubSpot conversations inbox) | a family WITH a deal; tutors who are SMS-only |
| sales | "Danielle Brodetsky" | danielle@ (HubSpot sequences), campaign reply-to info@ | teachers for MANY students; school partners |
| charter_admin | Kath | charter@ (PO agent), tickets | purchase orders, invoices, billing |
| main line | A+ Tutoring | 818-850-6284 | inbound calls (`ops/call_agent/`) |

The rule that ties the lines together (Roman, 2026-09-08, locked): a family with
no deal yet is a lead and is texted from the charter_sales line. Once a PO or
deal exists the family belongs to scheduling and is texted from the support
line. Never the other way round. A family in an active scheduling thread is
never lead-texted, whatever the deal state says.

## Stage field template

Every stage file has this frontmatter and these headings, in this order.
Reviewers can check compliance by eye.

```yaml
---
name: journey-NN-slug
description: one line
status: DRAFT            # DRAFT | REVIEWED
owner_seat: role_key     # from email/config.yaml roles:
reviewers: []            # [{seat, person, date}] appended, never overwritten
agent_readable: false    # visionary flips to true; requires status REVIEWED
version: 0.1
---
```

Headings: Entry marker. Exit marker. Owner seat. Channel and identity. What the
agent may do alone, must draft, must ask. Questions we ask the family or
teacher here. Questions the agent asks itself here. Where charter and private
pay diverge. Handoff out. Known gaps. Related.

Rules of the template: cite existing questions and rules by file path, do not
restate them. Write gaps as "no owner", "no code", "no template" when that is
the truth (CARE, accountable). Name people only through their seat.

## Rules that apply at every stage

Pointers only. Each rule lives in one place and is not copied here.

- Sender routing (teachers for many students to sales; families to
  charter_sales; a teacher about one student to charter_sales): `CLAUDE.md`,
  "Key context", outbound sender routing.
- No em dashes or double hyphens in anything customer-facing: `CLAUDE.md`,
  outbound style. Enforced in code only for Gmail drafts and transactional SMS
  (`email/src/gmail_client.py`, `_scrub_outbound`); everywhere else it is on
  the author.
- The school issues the PO. We send the teacher the hours. Never "we handle the
  PO": `ops/messenger/CAMPAIGN-2026-09-08-teachers.md`.
- Every charter student has funds. Never "students with funds": same file.
- Teachers are contacted by email only. No call tasks, no meeting links: same
  file.
- Tutors are named by first name only, and never an inactive tutor:
  `ops/hubspot-schema/properties.yml`, `last_tutor_name` and
  `last_tutor_active`.
- The NSSA Badge claim is read verbatim from `knowledge/credentials.yml`, is
  about program design not outcomes, and never goes in an SMS.
- Which line by stage: `ops/messenger/config.yml` (`sms.numbers`, PR #195) and
  the identity map above.
- Values: `ops/values/care-values.md`. Read it, do not restate it.

## How agents should use this

1. Find the stage. Look up the contact's lead status, persona, and deals. The
   journey table says which file.
2. Check the file's frontmatter. If `status` is not REVIEWED or `agent_readable`
   is false, do not act on it. Ask the owner seat instead, and say which stage
   you are in and what you wanted to do.
3. Pass `00-pre-send-checklist.md`. Write the six answers into the HubSpot note
   or the run log before sending. A failed item means hand off, not send.
4. Use the stage's "may do alone / must draft / must ask" as the ceiling. A
   standing go in `email/config.yaml` (`presend.standing_go`, PR B) never
   exceeds what the stage file allows.
5. When the stage file and reality disagree, reality wins and the file gets a
   correction through `#agent-feedback` (`corrections/README.md`).

## Review status and sign-off

Roman reviews in the PR and collects each seat's sign-off himself. On his word
the session appends `{seat, person, date}` to a file's `reviewers`, flips
`status: REVIEWED`, and Roman's own approval flips `agent_readable`.

Suggested owner seat per file, so Roman knows who to ask: charter_sales for
01, 02, 03, the family side of 04, 08, 09. sales for 10 and the teacher
paragraphs of 01 and 04. scheduling_lead for 05, 06, 11, and the tutor_issue and
complaint rows of 07. charter_admin for the PO, invoice, and closed-won
paragraphs of 04 and 07. operations for this README's journey table, every
"Handoff out" section, the SLA source-of-truth line in 07, and every "Known
gaps" section. visionary for 00 and this README.

An agent reads a stage only if REVIEWED and agent_readable. An unreviewed stage
means "ask the owner seat". 00 must be REVIEWED before any stage is readable.

## Open items

Decisions or code that this playbook does not settle. Deciding seat in
parentheses.

1. The `operations` role key maps to two people: `email/config.yaml` (emily)
   and `ops/tutor-issues/config.yml` (mandy). Rename one or move ownership
   (visionary).
2. SLA hours differ across `email/rules.md`, `email/config.yaml`, and
   `email/TEAM_PLAYBOOK.md`. This playbook treats `email/config.yaml` as the
   truth; reconcile the other two (operations).
3. The em-dash scrub does not cover HubSpot marketing emails or the bulk
   messenger (code).
4. STOP-reply ingestion, new-teacher intake automation, and tutor-ask
   automation are not built. Tutor group DMs need the bot to have `mpim:write`
   and `mpim:read` (visionary, code).
5. Private-pay stage markers (quote sent, payment received, package created)
   are not verified in the repo (sales, visionary).
6. Which identity makes the renewal ask to a family that already has a deal:
   support line or charter_sales line (visionary).
7. Two Christa HubSpot records, one with the phone and one with the email,
   unmerged (scheduling_lead).
8. A lint that every stage file has the template headings and a valid status
   (code).
9. The payment and closed-won stage has no owner and no agent watching it
   (`docs/PO-PROCESS.md`, Stage 7) (charter_admin, visionary).
10. Small sends under 25 recipients have no rail today; PR B adds one. Until
    then, follow `00-pre-send-checklist.md` by hand.

## Related

- `email/TEAM_PLAYBOOK.md`: the inbox team's scenario guide for stage 07.
- `docs/PO-PROCESS.md`: the PO agent, stages 04 and 05.
- `ops/messenger/README.md`: bulk email and SMS, stage 09.
- `ops/call_agent/rubric.md`: the discovery rubric, stage 03.
- `knowledge/eos/README.md`: quarterly rocks and who owns retention.

## Version

- v0.1 (2026-09-09): first draft after the charter SMS round 2 incident. All
  stages DRAFT.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

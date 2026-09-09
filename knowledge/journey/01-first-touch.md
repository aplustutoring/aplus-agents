---
name: journey-01-first-touch
description: >-
  A new contact reaches us, or we reach them for the first time: web form,
  call, campaign reply, referral, teacher nomination, booth. Reply on the
  channel they used, from the seat that owns them, and find out who at A+ they
  have already spoken with.
status: DRAFT
owner_seat: charter_sales
reviewers: []
agent_readable: false
version: 0.1
---

# 01. First touch

## Entry marker

A contact is created, or an existing contact writes in after a long gap, with
lead status New (Inbox). Sources: web form (the HubSpot "Lead Pipe Line"
workflows set the status and the owner), inbound call (`ops/call_agent/`),
campaign reply (`campaign_family` or `campaign_school` in the routing table,
`email/config.yaml`), referral, teacher nomination (Teacher Scholarship), event
booth (`booth/`), or a reply to a bulk text on the charter_sales line.

Persona (`a_persona`) says who they are: Family, Teacher of Record, Decision
Maker, Tutor, Student. Most contacts have none set yet, so lead status carries
identity for them.

## Exit marker

The first two-way exchange is logged, and the status moves to Attempting to
Contact (no reply yet), Meeting Booked, or a QTL status (a call happened).

## Owner seat

`charter_sales` for families. `sales` for teachers and school staff. The
Online lead workflow assigns the family to the charter_sales seat; the Ads
workflow assigns to the visionary seat (open item: two front doors, two
owners).

## Channel and identity

Reply on the channel the contact used. A form lead gets the workflow's text
and email; a caller gets a call back from the charter_sales line; a campaign
reply gets a reply in the same thread from the seat that sent the campaign; a
bulk-text reply stays on the charter_sales line, signed Paola. A family with
no deal is a lead, so the charter_sales line is the only line that texts them.

## What the agent may do alone, must draft, must ask

**Alone:** classify the message, create the ticket with the routing table's
owner and SLA, stamp a `[Agent]` note, log the call, stamp the lead status the
call ladder allows.

**Draft:** the reply, for the owning seat to send from HubSpot.

**Ask:** nothing outbound on a channel the contact did not use; nothing to a
contact who is marked opted out or not a marketing contact.

## Questions we ask the family here

- The intake set, already on the form: what is going on, grade, subject need,
  online or in person, how did you hear about us and who referred you, student
  and sibling names, school (`ops/hubspot-schema/properties.yml`, family
  group).
- On a call: the discovery rubric (`03-discovery.md`).
- NEW: "Has anyone at A+ already been in touch with you?" Ask it once, warmly,
  on the first reply. It tells us which thread to join and it is the question
  the Gonzalez family needed us to ask.

## Questions the agent asks itself here

- Is this a reply or a new touch? A reply stays in its thread (checklist item
  6).
- Is there already an open thread on the other line or in the inbox
  (checklist item 1)? A campaign reply from a family who is also mid-scheduling
  belongs to scheduling.
- Is the persona set? If not, what does the lead status say, and does the
  content agree?
- Is this a charter family? The form's school field and the charter intake
  fingerprint decide the fork in `04`.

## Where charter and private pay diverge

Charter: capture the school and, if known, the teacher of record at first
touch; the funds question is never conditional (every charter student has
funds). Private pay: capture online or in person and package interest; pricing
comes from the seat on the call, not from a template.

## Handoff out

- Family to charter_sales: ticket with the 90-minute SLA for customer-facing
  categories, Slack DM to the seat, HubSpot task with a due date.
- Teacher or school staff to sales: same pattern, 8-hour SLA for
  business-development categories.
- A caller Roman answered: the HANDOFF block routes the follow-up task to
  charter_sales with what Roman already covered
  (`ops/call_agent/call_agent.py`).

## Known gaps

- Inbox replies never stamp `hs_email_last_reply_date`; "have they replied?"
  needs a thread scan.
- The Online lead workflow's first text renders an owner id where a name
  should be (`docs/CHANGELOG.md` explorations, 2026-09-09); a portal fix.
- Persona is empty for most contacts; the backfill from lead status was
  proposed and not run.
- Two front doors (Online, Ads) assign different owners.

## Related

- `02-attempting-to-contact.md`, `03-discovery.md`.
- `email/rules.md` (classifier categories), `email/config.yaml` (routing).
- `ops/call_agent/README.md`.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

---
name: aplus-hubspot
description: How A+ reads and writes HubSpot without breaking the CRM. Load before any script, agent, or query that touches HubSpot contacts, deals, tickets, properties, lists, or workflows. Covers the property registry, the enumeration rule, the [Agent] labeling convention, the persona model, the field-name traps that have cost real time, and the rule about bulk writes. Triggers: "HubSpot", "contact property", "deal stage", "create a property", "update the CRM", "pull a list", "ticket".
---

# HubSpot rules

Ground all reasoning and output in A+ CARE core values: `ops/values/care-values.md`.

HubSpot (portal 6312752) owns **families**: every contact, every deal, and every
communication. Teachworks owns **lessons**: scheduling and attendance. Engines
sync from Teachworks into HubSpot. No local cache, sheet, or state file is ever
authoritative over those two.

## Properties are declared, never created ad hoc

`ops/hubspot-schema/properties.yml` is the source of truth. It syncs to the
portal via `create_properties.py`, which is **additive only**. Declare a new
property there and let the sync create it. A property created by hand in the
portal is invisible to the fleet.

Any property an agent **writes** gets:

- the label prefix `[Agent] `
- a description starting `AGENT PROPERTY — written by <script>`

A human looking at a contact record must be able to tell agent-maintained fields
from intake capture at a glance. (Roman 2026-08-14.)

## The enumeration rule

**Agents always read option LABELS, never internal values.** These diverge, and
the divergence is not cosmetic: the lead status whose label is `We Connected`
has the internal value `QTL - NEW`. Code that matches on the internal value is
code that silently matches the wrong thing.

## The contact model

Five personas on `a_persona`, a multi-select checkbox in the `master` group:
Decision Maker/Director, Teacher of Record/EF/ES, Family, Tutors, Student.

Family to Teacher-of-Record links are **contact-to-contact associations** with
the paired label "Teacher of Record" (associationTypeId 15, USER_DEFINED;
the reverse, "Family", is 14). The stamped text fields
(`teacher_of_record_name` / `teacher_of_record_email` on family contacts) are
legacy intake capture, not the source of truth. Read the association.

## Field-name traps

Each of these has cost real debugging time.

| Trap | Reality |
|---|---|
| `school` | Does not exist on contacts. The field is `student_school`. |
| `student_last_name` | Holds the student's **first** name. |
| `notes_last_contacted` | Updates on **inbound** too. It does not answer "did we get back to them". For that, take the newest outbound text, call, or email (`scripts/waiting.py`). |
| `hs_email_last_reply_date` | Inbox replies never stamp it. Scan the threads. |
| Workflow IDs | v3 and v4 return different ids for the same workflow. Merge by name. Enrollment totals only come from the v3 LIST endpoint. |

## Tasks, tickets and pipelines

Roman's locked rule governs which object to use; the case engine
(`email/src/case_engine.py`) implements it. Pipelines: Renewals 935649887,
Support 0, Tutor Accountability 935648438. There is a ceiling of 10 tasks per
seat per day, because a seat that receives 546 machine-made tasks in nine days
stops reading any of them.

Lists are HubSpot properties, views and tickets. **Never propose a Monday
board.** Monday was retired 2026-09-10.

Event segmentation: every event gets a HubSpot ACTIVE list named
`Event: <label>` per the `aplus_event_tag` option, built by `event_lists.py`
after the schema sync. Never hand-make an event list.

## Bulk writes are a human action

The classifier blocks bulk HubSpot writes on purpose. A migration or backfill
script is written, reviewed, dry-run, and then **run by Roman**, not executed
inside an agent run. `hubspot-archive.yml` is the fleet's delete tool: dry run
first, always, and read the output before the live pass.

A HubSpot workflow that writes the same field an agent writes will clobber it.
On 2026-09-10 a contact-to-deal workflow overwrote what a human had typed 90
seconds earlier. Before adding an agent writer, check whether a portal workflow
already writes that field, and turn one of them off.

## Before you query

Read-only exploration is cheap and encouraged: search contacts, read a deal,
list properties. Write paths are where the rules above apply. When in doubt
about whether something counts as a bulk write, it does. Ask Roman.

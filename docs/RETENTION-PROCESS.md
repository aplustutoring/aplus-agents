# The A+ retention journey — the process, who owns what, what the agents do

Source of truth for retention, the way `PO-PROCESS.md` is for purchase orders.
Agreed with Roman on 2026-09-10 (question by question). If the code changes,
change this file in the same PR. Lives in HubSpot only: Monday is retired
(quarterly goal), Zapier flows are replaced step by step.

Retention starts at the **first lesson**, not at the renewal. Every family
walks the same skeleton; charter and private pay branch only where the money
comes from (a school PO versus a package), and spotlights are charter only.

## The journey

| Day | Trigger | Agent | Human | Build step |
|---|---|---|---|---|
| 0 | Tutor posts lesson-one notes in Teachworks | **Brief** as a note on the family's contact record (tutor, what was covered, next session). **Quality-check text** from the charter_sales seat's line the next morning, inside the 8am to 8pm PT window. Never at night. | Paola reads the brief. | 2 |
| 0 + 48h | Lesson-one notes still missing | Quality text goes **anyway**. **Ticket to charter_admin (Kath)**, associated to the **tutor's** contact, so the naughty list builds itself. | Kath chases the tutor. | 2 |
| 1 | After the first text | **What-to-expect email** (lesson notes are coming, attendance matters). Today a HubSpot workflow; moves into the agent. | | 3 |
| 14 | Check-in call | **Ticket for Paola with the brief inside**: lesson-notes summary, attendance so far, tutor-issue flags. Her outbound call logged in HubSpot as **No answer**, **Left voicemail** or **Busy** fires the follow-up **text from her line**; **Connected** or **Texted instead** does not. | Paola calls. | 3 |
| 21 | NPS survey (earliest) | Sent only after **reasoning**: no open ticket, no unresolved conversation, no no-show streak, no tutor-issue flag. Otherwise **held with the reason** and Paola told. Score stamped on the contact. Survey copy to be refreshed. | | 4 |
| 30 | Referral email | From Paola's name. **Free half hour for both sides** (the live referral page). Only if the day-14 call was Connected or the family replied to a text. | | 4 |
| 45 | Care call | Same as day 14. Private pay: the brief carries the **package upgrade math** so Paola can pitch it live. | Paola calls. | 3 |
| 75 | Spotlight, **charter only** | Once Paola submits **her HubSpot form** (existing; activates workflows): teacher message, parent ask for scores and photos, replies tracked, "folder ready" ping. The Drive watcher and the spotlight pipeline take it from there. | Paola submits the form, drops the folder in Drive. | 5 |
| any | **Low balance**, 4 hours or fewer | See below. | | 1 (built) |
| any | Deal moved to Stopped, or 21 days of silence after Retention Risk | Case closed as **Lost** with a reason (agent writes `no_response` or `stopped`; Paola picks moved on / cost / schedule / tutor fit / school funding when she knows). **Family enrolled in re-engagement** (the charter SMS round 2 and private-pay win-back campaigns). The journey does not stop. | Paola sets the reason when she knows it. | 5 |

## Low balance (step 1, built 2026-09-08 to 10, `email/src/low_balance.py`)

Trigger: Teachworks' Package Balance Alerts email ("...package balance for
<student> has reached the level of N hours and is currently at N unused
hours") at **4 hours or fewer**. Recognised deterministically before the
classifier. One case per student + package per school year; repeat alerts add
a note, never a second message.

| Day | Charter | Private pay (auto-renews at 2 hours) |
|---|---|---|
| 0 | **Email** to the parent from Paola's name, reply-to paola@: hours are running low, tutor's first name, one true sentence from the last 30 days of lesson notes, "we would love to keep that progress going", please submit a new PO or ask your teacher of record to. Ticket opens for Paola. Deal → **Low Hours**. | **One upgrade email**: current tier and rate, the next tier and rate, "or keep going as you are and it renews on its own". No text, no teacher. Deal → Low Hours. |
| 1, next business morning | If **no PO deal, no reply from the parent in paola@'s inbox, and the ticket is still open**: **text** from Paola's line (same progress line) and the **teacher draft** in Paola's Gmail (progress line, PO number, "could you issue a new PO"). Never for Level Up Terri teachers. Deal → Family Contacted / Teacher Contacted. | nothing |
| 7 | No PO: the ticket **is the retention issue**. Subject "RETENTION RISK: …", priority HIGH, deal → **Retention Risk**, one DM to Paola and Roman. No task. | |
| 28 | Still nothing: closed as **Lost** (`no_response`), re-engagement list. | same |
| any | New PO deal → ticket closed, deal → **Renewed**. Deal Stopped → **Not Renewing**. | Any new deal → Renewed. |

**Scope (Roman 2026-09-10, later):** charter service codes only, out of
pocket excluded (`low_balance.charter_only: true`). A private-pay or
out-of-pocket alert is not this agent's: no case, no email; it takes the
ordinary inbox triage path. The private-pay column below describes dormant
code for when that switch is flipped.

**Grouping (Roman 2026-09-10):** siblings alert minutes apart (the three
Melaras, one hour between them), so the day-0 email is sent by the sweep
after `email_delay_minutes` (60) as **one email per family naming every
student**; day 1 is **one text per family** and **one draft per teacher**
naming every student that teacher has running low. **Backfill:** the
email-triage workflow input `backfill_days=N` opens a case for every alert
of the last N days that has none (skipping students whose newer PO deal
already exists) and sends the day-0 emails at once; the rest follows the
normal clock. **Private pay on pre-2026 service codes** (the Teachworks
package name carries the pricing year) gets a ticket but no upgrade email:
that renewal is a rate conversation for the seat.

Copy rules, all locked by Roman on 2026-09-09: "4 hours or less", never the
exact balance; **first names for everyone** (student, parent, tutor, teacher);
**no school name and no teacher name** in family copy; **parent submits the
PO first**, the teacher of record is the unnamed backup; the progress sentence
is **derived from lesson notes of the last month or does not exist**, never
imagined; no em dashes.

## Where it lives (HubSpot)

- **Ticket per case**, owner charter_sales. Where Paola works it.
- **Deal properties** (`ops/hubspot-schema/properties.yml`, group Retention
  journey): `retention_stage`, `retention_lost_reason`,
  `retention_low_balance_alert_date`, `retention_last_notice_sent`,
  `retention_last_touch`. The later journey steps write the same fields.
- **Saved deal view "Renewal Chase"**: `retention_stage` not in Renewed / Not
  Renewing / Lost, sorted by alert date. This is the list.
- **Audit log** (`email/state/audit_log.jsonl`): every case event. Feeds the
  scorecard: renewal rate within 14 days, retention rate month over month,
  cases open past 7 days.
- **Email performance**: every agent-sent template tracked for opens, clicks
  and replies (build step 4).

## What it replaces (each switched off only after its replacement ran clean)

Zapier first-lesson text · HubSpot "What to Expect" workflow · Monday
"Retention" board · Monday "A+ Charter Low Balance Alerts" board · HubSpot
"Low Balance Alerts - Charter" flow (already off).

## Pricing the agents may quote (2026 sheets)

Charter: $60 per 45-minute session (recommended), $75 per 60-minute session,
covered in full by charter funds. Private pay online: Improvement 8h $88,
Prep 20h $83, Success 50h $73, Soar 100h $68, single sessions $95 per hour.
In person: 8h $115, 20h $108, 50h $103, 100h $93, single $130. Larger
packages, lower rates.

## Build order

1. Low balance, staged, plus the deal properties and the view. **Built.**
2. Lesson-one brief, quality text, missing-notes ticket to Kath. Kills the Zapier flow.
3. Day-14 and day-45 briefs, call-outcome text, What-to-expect email moved in.
4. NPS with reasoning, day-30 referral, email performance tracking.
5. Spotlight handoff from Paola's form, Lost stage, re-engagement enrollment.

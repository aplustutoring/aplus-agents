# Email Agent — Team Playbook

How the inbox assistant works, and **what each person does** when something lands.

## The flow (every email)
A new email to admin@wetutorathome.com → the agent reads it → figures out what it is →
makes a **HubSpot ticket**, assigns the right person, writes a **draft reply** (when
appropriate), creates a **Task** (due-dated to-do with reminders), and sends that person
a **Slack DM**. **The agent never sends a reply to a customer on its own** — a human
reviews and sends. (Two exceptions: spam is auto-archived, and tutors who submit a
document get an automatic "we received it" receipt.)

## How you find your work (3 ways)
1. **Slack DM** from **@aplus** — has a direct link to the ticket. Fastest.
2. **HubSpot → Tickets → "My tickets"** (or the Support Pipeline board, your name).
3. **HubSpot → Tasks → "My tasks"** — due-dated, with reminders.

## What the ticket stages mean
| Stage | Meaning | Who moves it |
|---|---|---|
| **Needs Approval** | New — agent dropped it, draft ready, **review & send** (your worklist) | agent (drops here) |
| **Working on it** | You've picked it up / actively handling | you |
| **Waiting on Family / Tutor** | You replied; ball is with them | **auto** when you send a reply |
| **Stuck** | Uncertain, or escalated past SLA — needs attention | agent / you |
| **Done** | Resolved | **you, manually** (Done is a deliberate human close) |

---

## Scenario table — what the agent does + what YOU do

**Response SLA = 90 minutes** (9 AM–6 PM PT, Mon–Fri) for everything customer-facing.

| Email type | Agent → owner | SLA | What you do |
|---|---|---|---|
| **Reschedule** (move an existing session) | draft → **Janelle** (A–L) / **Yolanda** (M–Z) | 90 min | Offer open times fast — this is a **save**, keeps it off the cancellation rate. |
| **Scheduling** (new booking / availability) | draft → scheduler | 90 min | Review draft → send. |
| **Cancellation** — **one-time / pause / stop** | draft → scheduler; reason + type captured. **Pause AND stop** → auto-close the student's active deals + re-engagement follow-up task (sample email, due ~Sep 1 / Jan 2). **One-time** → no deal/win-back (family stays) | 90 min | Try to **reschedule** instead of cancel. Review draft → send. Eyeball the auto-deal-move (undo if wrong); when the family resumes, create a **NEW deal marked Existing Business** (Renewal deals are only for immediate continuations). |
| **Returning family booking new service** (`scheduling`, existing customer) | draft → scheduler + **agent creates the deal** (Gold/Pre-Lesson, **Existing Business**) | 90 min | Review draft → send; deal is already on the board. |
| **Tutor issue** (unhappy / wants a switch) | ticket → **Mandy**, NO draft | 90 min | Handle fast — a switch usually **saves** the account. |
| **Complaint** | ticket → **Mandy**, NO draft | 90 min | Handle personally. |
| **Payment dispute** | ticket → **Mandy**, NO draft | 90 min | Handle personally. |
| **School partner** (contract, PO, program) | draft → **Danielle** | 90 min | Review draft → send. Revenue-critical. |
| **Business dev** (partnerships, collabs, press, staff-referred pitches) | draft → **Danielle** | 8h | Review and decide if it's worth pursuing. |
| **TOR inquiry / new PO** | draft → **Paola** | 90 min | Review draft → send. |
| **Tutor document** | **auto-receipt to tutor** + ticket → **Kath** | 90 min | Process the document. No reply needed. |
| **Recruitment** (applying to tutor) | draft → **Mandy** | 90 min | Review draft → send. |
| **Charter newsletter** (mass announcement) | FYI ticket → **Danielle**, no draft | 48h | Read. Usually no action. |
| **Junk / spam / vendor / payment notices** | **auto-archived** (recoverable) | — | Nothing. |
| **Unknown / unclear** | ticket → **Stuck**, owned by **Mandy** | 4h | Mandy glances daily, dismisses noise, reassigns the rare real one. |
| **Internal staff email** (@wetutorathome.com) | routed to the **teammate it's addressed to** ("Hi Kath" → Kath); ticket. Falls back to Roman if unclear | — | That teammate handles it. |
| **Teachworks notification** | cancellation/etc. → scheduler by family name; **ticket linked to the family contact**, draft in the ticket (no reply sent to Teachworks) | 24h | Open ticket → email the **family** straight from the ticket. |

---

## Escalation — when something sits too long
- **1× past due** → the **owner** gets a Slack reminder.
- **2× past due** → **Mandy** is pinged (she watches the schedulers, nudges them).
- **3× past due** ("really off") → **Emily** is pinged + the ticket moves to **Stuck**.

## Reports you'll get
- **Hourly check-in** (Roman, 9–5 PT, launch only — stops 2026-06-24). 9 AM one covers overnight.
- **Daily summary** (Roman, 6 PM PT) — volume by category/owner, drafts, junk, escalations.
- **Weekly digest** (#email-agent, Mon 8 AM) — full week + the L10 scorecard rows.

## Auto-actions to know about (the only two)
1. **Junk → archived** (never deleted — recoverable in HubSpot's archived view).
2. **Tutor document → auto-receipt** ("we've received your document") sent to the tutor.
Everything else is **draft-only**; a human always sends.

---

## Decisions (locked 2026-06-10)
1. **Stuck queue → Mandy.** She checks it daily; unknowns are now assigned to her.
2. **Payment notices → archived for now.** Future: trigger a "record payment in
   Teachworks" flow (not built yet).
3. **Teachworks notifications →** capture the reason + route by family name, draft goes
   **in the ticket** (no reply sent to the no-reply address), and the ticket is linked to
   the **family contact** so the scheduler emails them from the ticket.
4. **Internal emails → routed to the addressed teammate** (Roman if unclear), with a ticket.

## Still a team convention to agree on
- **Marking "Done":** tickets auto-move to *Waiting on Family* when you reply. Decide as a
  team who marks them **Done** and when (on customer confirmation, or end-of-day cleanup).

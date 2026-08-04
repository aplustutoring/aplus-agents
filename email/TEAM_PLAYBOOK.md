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

## Charter PO inbox (charter@wetutorathome.com)

A separate Gmail the agent polls every 15 minutes on the same schedule as the admin
inbox. **Every** email there gets a HubSpot ticket to **Kath** (same accountability
spine) and a Gmail label. **Purchase orders never get a reply.** Non-PO mail gets a
**real Gmail draft** when a reply makes sense (the agent never sends from this
address).

**The PO money flow is two steps:** (1) on receipt, the PO is converted to a
Teachworks invoice; (2) once the service is delivered, that invoice is submitted
to the school's ops system. The agent drives both.

**When the email is a NEW purchase order** (a funding authorization that starts or
adds service — not an invoice follow-up, statement, or renewal paperwork):

1. The agent extracts school, student, PO #, amount, hours, the PO's **service
   month**, and the parent's + TOR's contact info — **reading PDF/image attachments
   (the actual PO document) directly**, not just the email body.
2. **Dedupe:** if a deal already carries that PO # → **no new deal + an URGENT
   Slack DM to Kath** (is it a re-send or a second authorization?).
3. Otherwise it **creates the deal** at Pre-Lesson — in the **Level Up A pipeline
   when the PO mentions LEVEL UP** (`po_inbox.levelup_pipeline_id`), else the
   Charter pipeline:
   - name `School - Student First Last - PO 123`, close date +30 days
   - `po_number` + hours properties filled; **submission due date (end of the PO's
     service month) stamped on the deal** alongside the amount
   - **student first + last name, grade, and school always stamped on the deal**
     (property map in `po_inbox.deal_property_map`; anything the PO didn't state is
     flagged on the ticket for manual fill)
   - **New Business** if the student has no prior deals, else **Existing Business**
   - owner = the **assigned scheduler** (A–L → Janelle, M–Z → Yolanda)
4. **Parent contact fork:** parent info in the PO → HubSpot contact found-or-
   **created** and associated to the deal (this is what feeds Teachworks); missing →
   the **ticket tells Kath to get the parent's name/email/phone from the TOR** (no
   reply is sent to POs). The **TOR's contact is also associated** to the deal
   either way.
5. **The PO PDF is uploaded to HubSpot and pinned to the deal.**
6. **No cron lag:** the Teachworks sync runs for the new deal **immediately in the
   same run** — family + student exist in Teachworks the moment the deal exists
   (the 15-min sync remains as backstop).
7. **STEP 1 task — convert the PO to a Teachworks invoice:** a same-day HIGH task
   for Kath with student, school, PO #, amount, hours, and the submission due date.
8. **STEP 2 prompt — submit to the school's ops system:** every morning (9 AM PT)
   the agent checks each active PO deal. Student's attended Teachworks hours have
   **used up the PO's hours** → Kath is DM'd to **submit now**; otherwise she's
   DM'd when the **end of the PO month** arrives. One prompt per deal.
9. **Scheduling nudge:** if the student has **no upcoming lessons on the
   Teachworks calendar**, the agent posts to the Slack channel ("get them
   scheduled"); students already on the calendar stay quiet.
10. Ticket → Kath with everything extracted + the original email embedded as a
    note; Slack DM to Kath (copy to Roman); labels `A+ Agent/Processed` +
    `School/<name>`.

Anything that is NOT a new PO (invoicing follow-ups, vendor renewals, COI requests,
event invites, out-of-office) gets the `A+ Agent/Needs Review` label and a review
ticket to Kath — no deal is touched.

## Deal → Teachworks sync (replaces the Zapier zap)

Every **new HubSpot deal** (any pipeline except New Tutor / School Partnership /
Upsells, any creator — human or agent) is synced to Teachworks within ~15 minutes:

- **Family:** matched by the deal contact's **email**. Existing family → contact info
  updated (HubSpot wins); no family → one is created. In-person pipelines go to the
  in-person Teachworks account; everything else to online.
- **Student(s):** first name(s) from the deal name (`Parent - Student`, sibling names
  like "Kash and Kingston" both created), skipped if already under the family.
  **All charter families get Package billing by default** — a deal is charter when
  its pipeline is in the config list *or its pipeline name contains "Charter"*, so
  new charter pipelines can never fall back to private-pay billing. Private pay
  gets **Service List Cost**.
- **Per-pipeline settings:** each pipeline can carry its own Teachworks settings
  (account, billing method, extra family/student fields) via
  `deal_sync.pipeline_settings` in `config.yaml` — that's where the differences
  between the online pipelines (Charter Trad/Terri/Amy, IEM, Subscription, Gold)
  live. Filling that table in is part of the go-live checklist below.
- **Safety guards — the sync will NOT write, and instead posts to #email-agent,**
  when a charter deal's contact doesn't look like the parent named in the deal (it's
  usually the school's education specialist). Fix: associate the real parent contact,
  or create the family in Teachworks by hand. Internal @wetutorathome.com contacts
  are skipped silently.

**Status: pilot mode** (`deal_sync.dry_run_first: true` in `config.yaml`). Every run
logs exactly what it *would* write — nothing touches Teachworks yet. Go-live
checklist for flipping `dry_run_first: false`:

1. Review the latest `[PILOT]` lines in the deal-sync Action run: are the
   CREATE/UPDATE targets and student names right?
2. Confirm the NEEDS-REVIEW flags are catching the school-staff contacts (and not
   flagging real parents).
3. Fill in `deal_sync.pipeline_settings` — the per-pipeline Teachworks settings
   (billing method, extra fields) for each online pipeline.
4. Flip the flag in `email/config.yaml` and merge. The cursor was frozen during the
   pilot, so **every deal since the pilot started replays for real** on the next run
   — expect a large first batch and spot-check it in Teachworks.

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

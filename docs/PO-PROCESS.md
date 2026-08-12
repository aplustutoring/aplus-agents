# How a Purchase Order becomes a deal — the complete process

The reference for what happens when a PO lands in charter@wetutorathome.com,
every property the agent sets, how each value is decided, and what the humans
own. Kept in sync with `email/src/po_inbox.py` — if the code changes, change
this file in the same PR. (Last verified: 2026-08-11, suite 202.)

## Stage 0 — Arrival

- Schools email **charter@wetutorathome.com**. The agent polls every 15 minutes
  on weekday business hours (GitHub Actions, `email-po-inbox.yml`).
- Already-processed messages are skipped (audit log). A thread that already
  produced a real PO is closed — **unless** it has an open parent chase, in
  which case replies still get read (the TOR's parent info must get through).
- Replay: `replay_msg_ids` workflow input reprocesses specific Gmail messages
  past the guards (for rule changes / backfills).

## Stage 1 — Extraction (the agent reads the actual PO PDF)

Claude reads the email body **and every PDF/image attachment** and extracts:
school, student first/last, grade, PO number(s), amount, **hourly rate**,
hours, parent name/email/phone, TOR name/email, service month, Bill To,
level-up flag, and a summary.

| Decision | Rule |
|---|---|
| Is it a PO? | A new PO or funding authorization = yes. **Order agreements stamped "THIS IS NOT A PO" (OPS/iLEAD) = yes**, flagged `pending_approval` — confirm approved in the school's portal before service. Invoices, payment reminders, vendor admin = no → review ticket only, no deal. |
| PO number | Stored **bare** — any "PO"/"P.O.#" prefix is stripped. Letters that are part of the number (PF593736) are kept. |
| Multiple POs in one email | One deal **per PO number** (schools issue one per service month). |
| Hours | As stated in the PO. **Not stated → computed: amount ÷ hourly rate** (e.g. $150 ÷ $75/hr = 2), noted on the ticket. |

**Duplicate check** (before anything else): the `po_number` property is
searched; a match = no new deal + urgent DM to Kath. On a pending order
agreement, this alert doubles as "the school approved and issued the real PO."

## Stage 2 — Parent resolution (before naming — the deal name leads with the parent)

Tried in order; the first hit wins:

1. **Parent email in the PO** → find the contact, or create it
   (`a_persona=Family`, phone included).
2. **The student's prior deal** → its non-TOR contact, if unique.
3. **Unique family-contact match** by student name.
4. **Nothing** → the deal is born `NEEDS PARENT - …` and the **parent chase**
   starts: a request for the parent's name/email/phone is drafted to the TOR
   (else the sender) on the same thread — a human sends it (the agent never
   sends from charter@). The reply auto-creates the contact, renames the deal,
   and fires the Teachworks sync. Silent for 2 business days → escalation DM.

Why it matters: the Teachworks sync keys the family on the deal's parent
contact email — no parent contact means no TW family, no scheduling, no
invoice hour-tracking.

## Stage 3 — The deal and every property on it

| Property | Example / value | How it's decided |
|---|---|---|
| `dealname` | Jessica Jaramillo - Isaac Jaramillo - iLead 1 - 26/27 | `Parent - Student - School N - YY/YY`. Shorthand from `po_inbox.school_short_names` (unmapped → extracted name + ticket flag). N = the student's deal count at that school this school year + 1 (staggered across multi-PO emails). School year from the PO's service month (Aug–Dec = first year). Parent unresolved → `NEEDS PARENT - …`. |
| `pipeline` / `dealstage` | Charter Trad → Pre-Lesson | Level-up POs route to the Level Up A pipeline instead. |
| `amount` | 150.0 | The PO's dollar amount (per-PO in multi-PO emails). |
| `dealtype` | existingbusiness | Student has **any** prior deal → Existing Business; else New Business. |
| `hubspot_owner_id` | Janelle / Yolanda | Scheduler split by student last name: A–L → Janelle, M–Z → Yolanda. |
| `closedate` | +30 days | Fixed rule. |
| `po_number` | 7514044381 | Bare number — the canonical dedupe key. |
| `number_of_hours_in_this_po` | 2 | From the PO, or computed amount ÷ rate. |
| `should_this_deal_be_posted_to_a_slack_channel_` | true | **Always** — the HubSpot workflow behind the checkbox posts the deal to the per-pipeline Slack channel. |
| `is_the_family_currently_being_tutored_by_us_` | Yes / No / unset | **Yes** = the student has a TW lesson booked **in the PO's service month** (month unparseable → any upcoming lesson). **No** = that month is unbooked — including student not in TW at all. **Unset** = couldn't verify (no parent email / TW error) → 🚩 gap DM, never guessed. Routes the SMS flow: **both values text**; "No" adds an internal staff alert + delay first. |
| `schedule_preferences` | Wednesdays 3:30 PM with Sarah Lee | The student's live TW schedule — upcoming slots first, else the recent 30-day pattern. Feeds the SMS's `{{schedule_preference}}` token. Underivable → unset + 🚩 gap DM (the text would end in a blank). |
| `student_first_name` | Isaac | From the PO (separate non-fatal stamp). |
| `student_last_name_if_diff_from_parent` | Jaramillo | From the PO. |
| `student_grade` | 3 | From the PO. |
| `student_school` | iCC1 for iLEAD Hybrid Exploration | From the PO (full extracted name). |
| `parent_email` / `parent_phone` | — | From the PO when stated; also stamped when a parent-chase reply resolves them. Missing → ticket flag + 🚩 DM. |
| `teacher_of_record_name` | Mary Nieves | The TOR named in the PO/email. Missing → ticket flag + 🚩 DM. |
| `teacher_of_record_email` | mary.nieves@… | From the PO; PO has only the name → the email is **resolved from the matched TOR contact** and stamped anyway. |
| `lessons_fulfilled_date` | Aug 31 | **Last day of the PO's service month** — the invoice due date. Prefilled by the agent; Kath confirms (see Stage 5). |
| `invoice__` (Invoice #) | *Kath fills* | The Teachworks invoice number, after she creates the invoice (Stage 5). |
| `invoice_submitted_date` | *Kath fills* | When she submits the invoice to the school (Stage 6). Clears the deal from the unbilled sweep. |

Also attached to the deal:

- **The PO PDF** — uploaded to HubSpot Files and pinned as a note.
- **The parent contact** (Stage 2).
- **The TOR contact** — by email (primary → secondary → create with
  `a_persona=Teacher of Record/EF/ES` + lead status); PDF names the TOR without
  an email → **name match** among existing TOR-flagged contacts
  (accent-insensitive; unique match or a visible flag; never created from a
  bare name). Family→TOR "Teacher of Record" association synced (#AP031,
  add-only — old links are never removed).

## Stage 4 — What fires automatically off the new deal

1. **Teachworks sync, immediately** — family/student created or updated (the
   15-minute cron retries if it hiccups).
2. **Ticket to Kath** (Needs Approval) with every flag, plus the original email
   embedded as a note. Gmail labeled `A+ Agent/Processed` + `School/<name>`.
3. **Slack**: DM to Kath (+ CC Roman) · **one DM to the assigned scheduler**
   per PO email (deal list, 72-hr Post-Lesson target, pending warning) ·
   channel post via the checkbox workflow · no-lessons alert when the calendar
   is empty · **🚩 missing-info DM to Kath AND Roman** listing every gap
   (missing fields, unmatched TOR/parent, NEEDS PARENT, blank schedule, failed
   uploads).
4. **SMS** (HubSpot flow 1603217415, contact-based): the parent enrolls,
   branches on the tutored property — "Yes" texts right away; "No" emails staff
   internally, waits, then texts. The text: *"We received your Purchase Order.
   Wanted to confirm that this schedule still works for you:
   {{schedule_preference}}"*. The flow clears its trigger at the end, so the
   next PO re-arms it — **one text per kid per PO event, structurally never
   daily.**

## Stage 5 — Kath: convert the PO to a Teachworks invoice (same day)

Her HubSpot task (HIGH, due 8 business hours) says exactly:

1. Create the TW invoice — student, PO#, amount, hours (with rate when
   computed), **Bill To exactly as the PO states it**. Pending order agreement
   → confirm approval in the school's portal first.
2. **Fill on the deal: `Invoice #`** (the TW invoice number) and **confirm
   `Expected Lessons Fulfilled Date`** — prefilled to the end of the PO month;
   that is the invoice due date.

## Stage 6 — Month end: submit and stamp

The invoice sweep prompts Kath when the PO's hours are used up **or** the
service month ends: submit the TW invoice to the school's ops system, then
**stamp `invoice_submitted_date` and move the deal to Invoice Submitted**.
Deals missing that stamp are what the sweep counts as unbilled.

## Stage 7 — Payment

School pays → deal moves to closed/won manually. (No agent watches this stage
yet — open roadmap item.)

## Who owns what

| Owner | Duties |
|---|---|
| **Agent** | Everything in Stages 0–4; all property stamping above except the two Kath fields. |
| **Kath** | Convert PO → TW invoice; fill `Invoice #`; confirm the due date; submit at month end + stamp `invoice_submitted_date`; confirm pending OAs in school portals; send parent-chase drafts from Gmail Drafts. |
| **Schedulers (Janelle / Yolanda)** | Get lessons booked within the 72-hr Post-Lesson window; deals arrive in their queue + DM. |
| **Roman** | Gets every 🚩 missing-info DM and the CC of Kath's pings; owns rule changes (this doc + Decision Log). |

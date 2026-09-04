# How a Purchase Order becomes a deal — the complete process

The reference for what happens when a PO lands in charter@wetutorathome.com,
every property the agent sets, how each value is decided, and what the humans
own. Kept in sync with `email/src/po_inbox.py` — if the code changes, change
this file in the same PR. (Last verified: 2026-08-11, suite 202.)

## Stage 0 — Arrival

- Schools email **charter@wetutorathome.com**. The agent polls every 15 minutes
  on weekday business hours (GitHub Actions, `email-po-inbox.yml`).
- **POs that land elsewhere** (2026-09-03): schools' ordering systems email the
  vendor contact on file, and Heartwood's OPS account points at admin@. Each
  run first copies PO-shaped mail (`src/po_sources.is_po_shaped`: ordering-system
  sender, "Purchase Order #" / "new POs" subject, or a PO/OA-numbered PDF) from
  every `po_inbox.sources` mailbox into charter@ (Gmail insert, label
  `A+ Agent/Mirrored from other inbox`), then processes the copy like any other
  arrival. The admin triage never junks such mail: it opens a HIGH handoff
  ticket to charter_admin that this agent closes once the copy is processed. A
  handoff ticket still open after 2 business hours means the mirror is broken
  (charter_admin + visionary are DM'd when a source fails).
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
| Is it a PO? | A new PO or funding authorization = yes. **Order agreements stamped "THIS IS NOT A PO" (OPS/iLEAD) = yes**, flagged `pending_approval` — confirm approved in the school's portal before service. **Portal approval takes ≥14 days** (Roman 2026-08-26), so the pending sweep nags only after `pending_portal_approval_days` (14 calendar days), not hours. Invoices, payment reminders, vendor admin = no → review ticket only, no deal. |
| Non-PO disposition | Every non-PO gets a `category_hint` that sets the ticket: **`vendor_compliance`** (unsigned agreements, invoicing-rule changes — these block or reshape POs) → **HIGH, owned by `po_inbox.compliance_owner` (sales seat)**; **`scam`** (advance-fee shape) → LOW, sender **never** captured as a parent contact; **`marketing_junk`** → LOW; `family_inquiry` / `other` → MEDIUM to Kath as before. (Roman 2026-08-26, after the Epic California C&CP signature request sat as a generic MEDIUM ticket.) |
| PO number | Stored **bare** — any "PO"/"P.O.#" prefix is stripped. Letters that are part of the number (PF593736) are kept. |
| Multiple POs in one email | One deal **per PO number** (schools issue one per service month). |
| Hours | As stated in the PO — **always stored as HOURS**. Two offerings (Roman 2026-08-26): **$75/hour** (the 99% case) and **$60 per 45-minute session** (a 4-session PO stamps **3** hours). Rate + unit stated → computed (per-session rates convert ×0.75). **No rate stated → computed only when exactly ONE offering divides the amount cleanly** ($150 → 2 hrs; $60 → 1 session = 0.75 hrs). $300 fits both (4 hrs OR 5 sessions = 3.75) → hours stay **blank + 🚩 flagged**, never guessed. Offerings live in `po_inbox.service_offerings`. |
| Cancellation | A school PO-cancellation notice (0 billable, or unstated) → the deal is moved to its pipeline's **Stopped** stage, **amount and hours zeroed**, a note pinned; DMs to Kath (+Roman via `missing_info_dms`) and the deal's owner; **HIGH task to Kath: void the TW invoice** (API can't). **Partial** cancellation (billable > 0 stated) → **nothing auto-changes**; Kath adjusts by hand off the alert. A cancelled PO number re-arriving is announced as a **re-issue**, not a duplicate. |

**Duplicate check** (before anything else): the `po_number` property is
searched; a match = no new deal + urgent DM to Kath. On a pending order
agreement, this alert doubles as "the school approved and issued the real PO."

## Stage 2 — Parent resolution (before naming — the deal name leads with the parent)

Tried in order; the first hit wins:

1. **Parent email in the PO** → find the contact, or create it
   (`a_persona=Family`, phone included).
2. **The student in Teachworks** → search both TW accounts by the student's
   exact name, then — schools and TW disagree on compound surnames — by each
   part of a hyphenated/spaced last name ('Murray-Fiore' also tries 'Murray'
   and 'Fiore'; first name stays exact). A student with real lesson history
   gives us their family (parent name/email/phone) directly — and if the PO's
   tutor is that student's last tutor, it's decisive. 0-lesson shell records
   never count; a tutor mismatch is flagged for verification. (Matthew Rose,
   2026-08-18: 104 lessons with Jacquelyn Lemerond → Megan Miller, no chase.)
3. **The student's prior deal** → its non-TOR contact, if unique. Matched by
   EXACT student-name properties (first + last, compound-surname parts
   retried) — **never by first name alone**: a first-name deal-name search
   resolved the wrong Mateo's parent on 2026-08-28 (Luis Ramirez instead of
   Sarah Fiore), mis-keying the deal, TW family, and SMS. No last-name
   agreement → this step returns nothing and the chase runs instead.
4. **Family-contact match** by student name — a lone surname hit only counts
   when that contact's student fields or deal names carry the student's first
   name (the "Dina Rose" collision).
5. **Nothing** → the deal is born `NEEDS PARENT - …` and the **parent chase**
   starts. Before drafting, the agent checks the TOR's recent **call-agent
   summaries** — a phone call may already hold the answer (flagged on the
   ticket). The request (parent name/email/phone) is drafted to the TOR — as a
   **fresh email** when the PO came from a portal robot (never addressed to
   noreply); one draft per recipient even for multi-student certificates. A
   human sends it (the agent never sends from charter@). Drafts carry the
   Gmail label `A+ Agent/Draft Pending` + the HubSpot BCC; the agent detects
   the send (unsent after 4 business hours → 🚩 nag), the reply auto-creates
   the contact, renames the deal, fires the Teachworks sync, and arms the
   family's SMS. Open chases also **self-resolve** if the family contact
   appears on its own. No reply 2 business days after the SEND → escalation DM.

Why it matters: the Teachworks sync keys the family on the deal's parent
contact email — no parent contact means no TW family, no scheduling, no
invoice hour-tracking.

## Stage 3 — The deal and every property on it

| Property | Example / value | How it's decided |
|---|---|---|
| `dealname` | Jessica Jaramillo - Isaac Jaramillo - iLead 1 - 26/27 | `Parent - Student - School N - YY/YY`. Shorthand from `po_inbox.school_short_names` (unmapped → extracted name + ticket flag). N = the student's deal count at that school this school year + 1, counted from an **exact search on the student name properties** (never name tokens — a limit-10 unsorted token search made every 10+-deal student restart at N=1: the McGraw/Saenz duplicate names, fixed 2026-08-26) and kept contiguous across all emails of a run by a run-scoped counter (the search index lags same-run creations). School year from the PO's service month (Aug–Dec = first year). Parent unresolved → `NEEDS PARENT - …`. |
| `pipeline` / `dealstage` | Charter Trad → Pre-Lesson | Level-up POs route to the Level Up A pipeline instead. |
| `amount` | 150.0 | The PO's dollar amount (per-PO in multi-PO emails). |
| `dealtype` | existingbusiness | Student has **any** prior deal → Existing Business; else New Business. |
| `hubspot_owner_id` | Janelle / Yolanda | Scheduler split by student last name: A–L → Janelle, M–Z → Yolanda. |
| `closedate` | +30 days | Fixed rule. |
| `po_number` | 7514044381 | Bare number — the canonical dedupe key. |
| `number_of_hours_in_this_po` | 2 | From the PO, or computed per the two-offering Hours rule above (always hours, never sessions). Ambiguous/unmatched amounts stay blank + 🚩. |
| `should_this_deal_be_posted_to_a_slack_channel_` | true | **Always** — the HubSpot workflow behind the checkbox posts the deal to the per-pipeline Slack channel. |
| `is_the_family_currently_being_tutored_by_us_` | Yes / No / unset | **Yes** = the student has a TW lesson booked **in the PO's service month** (month unparseable → any upcoming lesson). **No** = that month is unbooked — including student not in TW at all. **Unset** = couldn't verify (no parent email / TW error) → 🚩 gap DM, never guessed. Routes the SMS flow: **both values text**; "No" adds an internal staff alert + delay first. |
| `schedule_preferences` | Wednesdays 3:30 PM with Sarah Lee | The student's live TW schedule — upcoming slots first, else the recent 30-day pattern. Feeds the SMS's `{{schedule_preference}}` token. Underivable → unset + 🚩 gap DM (the text would end in a blank). |
| `student_first_name` | Isaac | From the PO (separate non-fatal stamp). |
| `student_last_name_if_diff_from_parent` | Jaramillo | From the PO. |
| `student_grade` | 3 | From the PO. |
| `student_school` | iCC1 for iLEAD Hybrid Exploration | From the PO (full extracted name). |
| `parent_email` / `parent_phone` | — | From the PO when stated, **or the RESOLVED family email** (Teachworks / prior deal / family contact — iLEAD OAs state a phone but no email; the resolved value is stamped with a 📇 note, 2026-08-26). Also stamped when a parent-chase reply resolves them. Genuinely unresolvable → ticket flag + 🚩 DM. |
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
4. **SMS** — AGENT-OWNED as of 2026-08-29 (Roman, after HubSpot flow
   1603217415 died silently on an Aug 13 edit and no charter family was
   texted for two weeks). `email/src/sms.py` sweeps Pre-Lesson deals in the
   configured pipelines every deal-sync cycle (~15 min) and texts the family
   via JustCall (`sms:` in config.yaml). Deals are GROUPED BY FAMILY — a
   multi-kid PO day is ONE text naming every student (Roman 2026-09-01:
   "name the kid"). The MESSAGE is chosen by what we know: schedule on file →
   the CONFIRM variant; none → the ASK variant ("what days and times work
   best for their sessions" — always "their", never a gendered guess; brand
   voice, no personal sign-off). The tutored property routes STAFF only:
   any "No" deal DMs the owner first and the family texts on the NEXT sweep;
   **unset no longer suppresses the text** (asking for a schedule needs no
   verification). Pending-approval OAs text normally ("if it says pending
   approval for us it means approved"). Copy lives in `sms.templates`.
   The **"What to Expect (Charter)" email** (58% lifetime opens, real replies)
   rides the same event: one family, one text, one onboarding email, sent
   via RESEND from "A+ Tutoring Success Team <admin@wetutorathome.com>" (the
   same address replies go to — HubSpot's Conversations inbox, so the triage
   agent reads responses; HubSpot BCC stamps the contact timeline). Copy
   lives in email/templates/welcome_charter.html. The ~1-in-4 families the
   old flow suppressed for missing marketing consent get it too (Roman
   2026-09-03, Option A; `welcome: true` per pipeline). A failed email never
   voids the text: audited + Kath flagged to forward manually.
   Guardrails: one text per deal ever, **one text per family per 24h** (a
   4-PO email never sends 4 texts), quiet hours 8am-8pm PT, a hard
   `start_date` fence so pre-cutover backlogs can never be texted, em-dash
   scrub, 3-strike send retry then a manual-text flag to Kath. The old
   HubSpot flow stays OFF; a pipeline's flow must be off BEFORE it is listed
   in `sms.pipelines` (that ordering is what makes double-texting
   impossible). Sweep watches DEALS, so manually created deals text too.

5. **Sibling-gap tripwire** (daily): a family that renewed SOME kids but
   has a last-season-active sibling with no new PO → 🚩 DM to the
   charter_sales seat after a 5-day settle window, once per family+kid per
   season. Whole-family non-renewals are the chase list, never a flag.
   (Roman 2026-09-04, after Eliana Fiore / Zahavi Villa / Abigail Miller.)

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

# aplus-agents changelog

Session-level record of changes to agent behavior, schema, skills, or process —
the shared memory between Claude-in-chat and Claude Code sessions. Every session
that changes how the fleet behaves appends an entry here (see the Session
Documentation Protocol in `CLAUDE.md`): date, what changed, WHY, files touched.
Newest entries first.

---

## 2026-09-03 — SMS live + zombie flow killed + welcome email agent-owned

**Go-live:** agent SMS (PR #144) merged with Roman's locked copy (name the
kid, "their", brand voice, pending=approved), fence moved to 2026-09-03, the
JustCall probe verified live by Roman. First production sweep: clean zero.

**Zombie:** at 4:28 PM, 8 min BEFORE the merge, the "dead" HubSpot flow
1603217415 woke up and sent Marissa Escandon the old garbled template (its
stuck enrollment recovered for the first fresh contact). Contained to one
family (JustCall carrier receipts: 2 texts, both delivered). Response: flow
DISABLED by state (revision 43, was only dead by luck), Escandon deal marked
sms_sent on main so the new sweep never double-texts, Paola (who owned the
live thread since 8/27) smooths it over. Lesson for the record: a stuck
workflow is a landmine, not a corpse — "dead" was verified, "off" was not.

**Welcome email (this commit, Roman: "option A, build that shit"):** the
flow's one email action was NOT internal staff mail as PO-PROCESS claimed —
it was "What to Expect (Charter)" TO THE FAMILY (58.3% opens, 10 replies,
0 spam over 432 sends), dark since Aug 13 with the texts. Now agent-owned:
`sms._send_welcome` fires HubSpot's transactional single-send alongside each
family text (same fence/dedupe/audit); marketing-consent suppression (70
families!) no longer applies; a failed email never voids the text (audited,
welcome_email_error + Kath DM). Locked-rule AMENDMENT (Roman): the agent's
outbound emails = tutor-doc receipt + this single-send.
**Files:** email/src/sms.py, email/config.yaml, email/tests/test_sms.py
(3 new; suite 370 green), docs/PO-PROCESS.md.
**Verify before relying on it:** the single-send endpoint needs HubSpot's
transactional add-on — probe command in the session notes; failure mode is
loud (DM to Kath) either way.

## 2026-09-02 — Campaign routing logged as #AP046

**What:** Appended the campaign-routing decision (PRs #134 + #159) to the A+
Decision Log as **#AP046**, and marked the staging entry in
`ops/fleet-health/audit/reports/decision-log-draft.txt` as appended so it cannot
be posted twice.

**Why:** CLAUDE.md requires a Decision Log entry when a decision is locked; the
routing table was amended twice in three days. The number was read from the live
document rather than guessed: the Doc was at #AP045, while the in-repo staging
file was stale at #AP017 and code references reached #AP044.

**Note for a future session:** the staging file's format (pipe-separated header,
wrapped field bodies) does NOT match the live Doc, which uses
`Month DD, YYYY · #APxxx` with single-line fields. Match the Doc when appending.
Also worth revisiting: #AP044's STATUS still says NSSA badge assets and usage
guidelines are unconfirmed. Both are now in hand as of this campaign.

**Files:** `ops/fleet-health/audit/reports/decision-log-draft.txt`,
`docs/CHANGELOG.md`.

---

## 2026-09-02 — Teachworks invoice due dates sync to the deal, so "ready to submit" is a HubSpot view

**What changed**
- `scripts/tw_invoice_due_sync.py` — new. Reads Teachworks invoice due dates,
  matches them to 26/27 charter deals on `Invoice #`, writes `invoice_due_date`.
- `.github/workflows/tw-invoice-due-sync.yml` — new. Manual (dry-run default)
  plus 6am PT weekdays.

**Why**
Roman locked the rule on 2026-09-02: **an invoice is ready to submit once it is
at least one day past its due date.** Simpler than anything proposed before it —
no Teachworks hours lookup, no service-month inference.

The catch was that the due date lives on the Teachworks invoice, submission
happens in the OPS portal (which we cannot read), and HubSpot knew neither.
`invoice_due_date` already exists on the deal, correctly labelled, populated on
75 of 157 26/27 deals and never written by an agent.

Copying the authoritative date across turns "what should Kath submit today?"
into a plain saved view she can keep open:

    Invoice #              is known
    Invoice Submitted Date is empty
    Invoice Due Date       is before today

No new property, no new tool for her to learn, and the date comes from the
system that owns it. Deliberately chose `invoice_due_date` over
`lessons_fulfilled_date` — the latter is an *expected* date the PO doc has Kath
confirm, not the invoice's actual due date.

**What the rule showed on real data**
Applying it by hand first (joining the 2026-09-01 Teachworks xref to HubSpot):
of 138 invoiced-but-unsubmitted 26/27 deals, **1 is genuinely past due** —
invoice 54421, Angela Czaja / Charlotte Czaja, Heartland, due 2026-08-14, $300.
The other 91 matched deals are simply not due yet. The $31,974 previously
described as "delivered but not billed" was mostly not billable.

46 deals had no due date on file because the xref only covered families with PO
deals since 2026-08-07. That blind spot is exactly what this sync removes.

**Files touched**
- `scripts/tw_invoice_due_sync.py`
- `.github/workflows/tw-invoice-due-sync.yml`
- `docs/CHANGELOG.md`

**Verification** — script and workflow parse; dry run is the default and the
Teachworks side is read-only. Needs a dry run in Actions (tokens are Actions
secrets) before the first `--apply`.

**Decision log** — candidate: "an invoice is ready to submit once it is at least
one day past its due date; the due date is the Teachworks invoice's, synced to
`invoice_due_date`."

---

## 2026-09-02 (evening) — CORRECTION: deal `school_name` is a live Teacher Scholarship field, not dead; two test contacts deleted

**What:** Reverses this morning's RETIRE call on deal property `school_name` in
`deals-proposal.md` (KEEPER again, with the writer and readers named). Roman asked to
archive it; the pre-archive look showed all 6 deals carrying it are in pipeline
918901819 "Teacher Scholarship Program Tracking - Families", one created today. A scan
of all 128 forms and 235 workflows found the writer: workflow 1861452046 "Teacher
Scholarship – Create Student Deal per Form Submission" maps contact `student_school` →
deal `school_name` on deal create, and WF-01 (1858089740) and WF-03 (1859135906) read
`{{ enrolled_object.school_name }}` in their notification emails. Archiving would have
silently blanked the school on every future Teacher Scholarship family deal and email.
Not archived. Instead relabeled in-portal to "Teacher Scholarship Student School" (Roman, same session) so it reads as what it is; internal name `school_name` unchanged, so the three workflows are unaffected; `properties.yml` label updated to match. Also on Roman's instruction: soft-deleted two Teacher-persona test
contacts created 2026-08-12 by the Teacher Scholarship alpha run, `daniellebrodetsky@
gmail.com` (241417873326) and `hugh.jazz@gmail.com` (241380683818); no deals or
associations; restorable 90 days. PR #160 merged (squash, c40c845).

**Why the morning call was wrong:** the "nothing writes it" claim came from
`grep`-ing the repo and counting charter-pipeline deals since Aug 2025. The writer is a
HubSpot workflow, not repo code, and the deals are in a non-charter pipeline. Lesson,
per the investigation rule: a "dead property" verdict needs a portal-wide writer scan
(forms + workflows), not a repo grep + one pipeline. `find_school_name_writer.py`
(session scratchpad) is the pattern; worth promoting into `ops/fleet-health/audit/`
before the next retire pass.

**Options if `school_name` should still go (Roman's call, not done):** remap workflow
1861452046 to write `student_school`, update the two email bodies, then archive. Or
leave it: it does a real job today.

**Files:** `ops/hubspot-schema/consolidation/deals-proposal.md`, `docs/CHANGELOG.md`.

---

## 2026-09-02 (later) — School stamp widened to every teacher; generic inboxes flagged

**What:** `scripts/teacher_school_stamp.py` v2 now resolves a teacher's school from
three HubSpot sources in order of specificity, never guessing: (1) charter deals the
teacher is named on, unanimous wins outright; (2) the contact intake enumeration
`charter_school_teacher` (read as LABEL), which is filled on 1,075/1,086 teachers and
agreed with deals 217/218 times — it now beats a SPLIT deal vote; (3) a verified email
domain. Deal ↔ intake disagreements are reported. Network-level labels (IEM, Pacific
Charter Institute, iLEAD) are not disagreements with their own schools. New
`[Agent] Generic Inbox` (`generic_inbox`, boolean, `tor` group) is set to Yes from the
email local-part (purchasing@, invoices@, studentservices@, info@, noreply@, vendors@,
ap@ …) so teacher outreach lists can exclude shared mailboxes; they still get a school.
Internal test contacts (@wetutorathome.com) and no-email contacts are skipped.
`school-aliases.yml` grew to 32 canonical schools / 82 spellings / 32 domains: every
intake label added as an alias; IEM and Pacific Charter Institute added as buckets for
central-office staff; 9 new schools (Excel Academy Charter School, Julian Charter
School, Springs Charter Schools, The Cottonwood School, BEST Academy, Epic California
Academy, Brighton Hall School, + Rio Valley/Heritage Peak spellings). Run with
`--all-tor --execute`: **922 contacts written (921 school, 30 generic flag)**, 157
already correct from the morning run, **6 unresolved**, 2 skipped. Re-run: 0 pending.

**Why:** Roman 2026-09-02: "Widen the script … you have to be smart, the excel academy
emails are for excel academy maybe their email domain is different from web, assume
nothing. Figure out a way to keep generic inboxes separate." The morning `--all-tor`
dry run left 113 unresolved on domains not in the alias file. Rather than assume a
domain = a school, each new domain was verified two ways: the contacts' own intake
label agreed with the domain 100% (excelacademy.education = Excel 26/26, jcs-inc.org =
Julian 15/15, springscs.org = Springs 14/14, …) and the domain's website title named
the school (curl, `<title>`). Vendors are deliberately not schools: dennis@mrdmath.com
stays unresolved.

**Unresolved (6), left alone on purpose:** 5 personal Gmail/Yahoo addresses with the
teacher persona and no intake label (one is Danielle's own personal Gmail, one is
"Hugh Jazz" — persona hygiene), and the Mr. D Math vendor. **Skipped (2):** Joyce
Showers (no email), paola+testheartlandef@ (test). **One disagreement:**
jedge@ieminc.org — deals split iLEAD 4 / South Sutter 3, intake says IEM → IEM.

**Files:** `scripts/teacher_school_stamp.py`, `ops/hubspot-schema/school-aliases.yml`,
`ops/hubspot-schema/properties.yml` (generic_inbox declared + school_canonical
description), `ops/fleet-health/audit/backups/2026-09-02-teacher-school-stamp/`
(pre-write backup for the 922), `docs/CHANGELOG.md`.

---

## 2026-09-02 — Teachers get a canonical school; iLEAD is one bucket; `school_name` retired (#AP-pending)

**What:** Teacher (TOR/EF/ES) contacts now carry `[Agent] School` (`school_canonical`,
`tor` group, declared in `properties.yml`, created in-portal by `create_properties.py`).
It is derived from the charter DEALS the teacher is named on
(`teacher_of_record_email` → `student_school`), not from the Family↔TOR association,
and normalised through a new shared lookup `ops/hubspot-schema/school-aliases.yml`
(23 canonical schools, 46 raw spellings, 17 email-domain fallbacks). New script
`scripts/teacher_school_stamp.py` (read-only by default, `--execute` writes with a
pre-write backup, `--all-tor` widens from list 3110 to every TOR persona). First run
stamped all **159** contacts on list 3110 (157 via deals, 2 via domain, 0 unresolved,
0 unknown spellings). In `deals-proposal.md`, deal property `school_name` flips from
KEEPER to RETIRE (6 deals all-time, 0 since Aug 2025, nothing writes it; archive
in-portal is Roman's action).

**Why:** Roman 2026-09-02, after the Pile 1 breakdown: teacher contacts had no usable
school (`student_school` filled on 15/159, `company` 26/159), so every teacher cut was
an email-domain guess. Deal analysis showed `student_school` is 96% filled on 2,377
charter deals since Aug 2025 but under 50 spellings, 14 of them iLEAD (63% of deals).
Locked decisions: **iLEAD is ONE bucket** (Exploration / Hybrid / Antelope Valley /
Lancaster / "California Charters" all → "iLEAD"); everything else stays school-level
with `network` recorded informationally (IEM, Pacific Charter Institute). The alias
file, not an enum, is the fix because `po_inbox` writes `student_school` free-text from
the PO (locked rules 11-12) and an enum would break those writes. Unknown spellings
are reported and skipped, never guessed, so the file stays complete.

**Also this session (data, not code):** all 1,085 TOR-persona contacts reassigned to
owner Danielle (227538487) on 2026-09-01 — 795 had been owned by deactivated staff
(Janina 621, Melanie 167, Rafa 7). Pre-change owners backed up in the session
scratchpad (`owners_backup_TOR_2026-09-01.json`).

**Open:** `--all-tor` dry run reaches 973/1,086 (222 deal, 751 domain); 113 unresolved
on unknown domains (excelacademy.education, brightonhallschool.org, …) — not executed,
Roman approved Pile 1 only. Two Pile 1 rows are not teachers (`poinquiries@ieminc.org`
shared inbox) — persona hygiene. `jedge@ieminc.org` resolves to iLEAD (4 deals) over
South Sutter (3) — most-common rule, worth a human look.

**Files:** `ops/hubspot-schema/school-aliases.yml` (new), `scripts/teacher_school_stamp.py`
(new), `ops/hubspot-schema/properties.yml`, `ops/hubspot-schema/consolidation/deals-proposal.md`,
`docs/CHANGELOG.md`.
## 2026-09-02 — Campaign replies need evidence, not just timing

**What:** `email/rules.md` gains a shared "Campaign replies: the evidence rule"
section gating both `campaign_family` and `campaign_school`. A reply is campaign
traffic only with positive evidence in the email itself: quoted campaign text, the
campaign subject line, or an explicit mention of its subject matter (the Badge,
NSSA, Stanford, the award). Timing and list membership are explicitly declared NOT
evidence, with the common failure named outright (short pleasant notes: "Thank you
so much!", "You're most welcome"). With no signal, the email is classified on its
content and the campaign is ignored. Both category blocks point at the gate,
`campaign_school` carries a worked negative example, and the NSSA block in Active
campaigns records the real send dates plus a retire-when-replies-stop note.

**Why:** Roman 2026-09-02. Of the first four replies the agent tagged as NSSA
campaign traffic, Danielle confirmed Erica Porter's was ordinary tutoring
correspondence, and Jaclyn Bershadsky's arrived before the leads send even went
out. The original rules listed the positive signals but never said timing and list
membership were insufficient, so the classifier filled the gap itself. Misrouting a
real request into a courtesy lane costs more than missing a congratulations note.

**Verified:** the live classifier was re-run against all three real emails.
Erica Porter and Jaclyn Bershadsky now return `unknown` (human review) instead of a
campaign category; Alyson Cruz's genuine Badge reply stays `campaign_school` with
confidence rising 0.82 to 0.92. Suite green (355 passed).

**Files:** `email/rules.md`, `docs/CHANGELOG.md`.
## 2026-09-02 — NSSA campaign routing staged for the Decision Log

**What:** Appended a draft entry to
`ops/fleet-health/audit/reports/decision-log-draft.txt` covering both amendments
to the LOCKED routing table: the `campaign_family` / `campaign_school` categories
(PR #134) and the evidence rule that gates them (PR #159), recorded as one
decision with its correction. Number left as #AP-NEXT: the Google Doc is the
authority on the current sequence, and the staging file is stale at #AP017 while
in-repo references already reach #AP044.

**Why:** CLAUDE.md requires a Decision Log entry when a decision is locked, and
the routing table has now been amended twice in three days. Roman assigns the
number and appends via the existing Zapier Google Docs pipe.

**Files:** `ops/fleet-health/audit/reports/decision-log-draft.txt`,
`docs/CHANGELOG.md`.

---

## 2026-09-01 — Call agent: scheduling-vs-follow-up task routing + name-correction propagation

**What changed**
- `ops/call_agent/call_agent.py`
  - `SUMMARY_PROMPT` step 3 gains a routing taxonomy: every action item is
    tagged `scheduling` (trial/session logistics) or `follow_up` (sales,
    billing, complaints, partnerships), with the tie-breaker "who physically
    does it — if it's whoever owns the calendar, it's scheduling".
  - New `SUMMARY_PROMPT` step 8 + `name_corrections` schema field: the model
    records any name the call corrected and must use the corrected name
    everywhere. `_apply_name_corrections()` sweeps summary, action items,
    handoff note, names-mentioned and the free-text record fields afterwards.
  - `task_subject()` prefixes scheduling items with `[Scheduling] `;
    `_resolve_owner()` takes a route and sends them to
    `hubspot.scheduling_task_owner` when configured (that beats the
    Roman-answered handoff rule — the handoff rule is about follow-up).
  - Digest header counts scheduling-routed tasks separately.
- `ops/call_agent/config.yml` — new `hubspot.scheduling_task_owner`, empty.
- `ops/call_agent/tests/test_action_routing.py` — 19 new tests.
- `ops/call_agent/README.md` — routing + name-correction behavior documented.

**Why**
Paola's 2026-09-01 correction (thread `1788290216.784979`): the agent was
proposing tasks for scheduling-team work — send a tutor profile, text a family
to confirm a trial, call back about a dropped transfer about a booked session —
so they sat in her follow-up queue instead of the scheduling team's. Separately,
a child's name corrected to "Autumn" on the call still went out under the old
name in the next-step language: the prompt never said a correction has to
propagate, and nothing enforced it after generation.

**Open item for Roman**
`scheduling_task_owner` ships EMPTY because nobody has confirmed the scheduling
team's HubSpot owner id (Divyesh? a shared `scheduling@` seat?). Until it is
set, scheduling items still land on Paola — but prefixed `[Scheduling] ` and
counted separately in the digest, so they are sortable out of her queue today.
Setting it is a one-line config edit once Roman confirms.

---

## 2026-08-31 — Blue Ridge BTSC 2026 "Spin Back to School" booth (schema PR)

**What changed**
- `ops/hubspot-schema/properties.yml` — 3 enum option additions + 1 new property:
  `aplus_event_tag` gains `blue_ridge_btsc_2026`; `aplus_event_role` gains
  `parent` and `student`; new `aplus_booth_prize` (single-line text, EVENT-TEMP).
- `booth/blue-ridge/worker.js` — new Worker, HubSpot upsert only.
- `booth/blue-ridge/test-worker.mjs` — 24 tests.
- `booth/blue-ridge/{wrangler.toml,DEPLOY.md}`.

**Why**
Lead magnet for the Blue Ridge back-to-school event, modeled on the Sage Oak
booth (`booth/`). Spin first, capture second: the prize is gated behind the
redeem form. v1 is HubSpot capture only — no email, MMS or print, because the
prize is physical and handed over at the table.

`aplus_booth_prize` is new because nothing existing fits. `aplus_booth_goal` was
NOT reused: it holds photo-banner text and overloading it would corrupt the Sage
Oak capture. Kept out of KEEPERS.md deliberately — single-event capture, not
agent vocabulary, and a review-for-archive candidate once the event is
reconciled.

`aplus_event_role` needed parent and student because Sage Oak was school staff
only and this event is open to families. The original three options are
untouched; the UI's "Teacher / School Staff" maps to `teacher`.

**Two Sage Oak bugs fixed here**

1. *Enum labels written instead of values.* The Sage Oak build wrote labels and
   HubSpot silently rejected them. Writes now take internal values
   (`teacher`, `blue_ridge_btsc_2026`, `"true"`), and the test asserts that no
   human-facing label appears in any write payload, for every role.
2. *Event tag overwritten instead of appended (#AP032).* `aplus_event_tag` is
   `fieldType: checkbox`, so a flat PATCH replaces the whole set. Sage Oak's
   Worker searches with `properties: ["email"]` and writes the tag flat —
   correct as the only event, wrong the moment a second exists. This Worker
   reads the current value and unions, so a returning Sage Oak attendee ends up
   carrying both tags.

**Schema gate.** `create_properties.py` does NOT run until Roman merges this PR.
The Worker is safe to deploy first regardless: an unsynced property returns
`PROPERTY_DOESNT_EXIST`, and the Worker drops that key and retries so the lead
is still captured.

**Files touched**
- `ops/hubspot-schema/properties.yml`
- `booth/blue-ridge/worker.js`, `test-worker.mjs`, `wrangler.toml`, `DEPLOY.md`
- `docs/CHANGELOG.md`

**Verification** — `node booth/blue-ridge/test-worker.mjs`: 24 passed. The tests
read `properties.yml` directly, so a manifest and Worker that disagree fail.

**Decision log** — #AP032 (append-only event tag) is now enforced in code and
covered by a test. Candidate entry: "event-temp properties are declared in
properties.yml but deliberately excluded from KEEPERS.md."

---

## 2026-08-31 — Task sweep: auto-close finished invoice tasks + watch Kath

**What:** `task_sweep._autoclose_done_tasks` — an open "Convert PO to TW
invoice" task whose deal already carries an `Invoice #` is DONE; the sweep
closes it (audited `task_autoclosed`) BEFORE bucketing, so nobody is nagged
about finished work. `charter_admin` (Kath) joins `task_sweep.monitor`.
**Why:** on 2026-08-31 ten of her invoice tasks sat NOT_STARTED while every
one of their invoices — 54528 through 54537, consecutive — was already
created. She does the work; the task list keeps the phantom. Kath was also
the ONE seat nobody monitored, and she holds the entire PO→invoice money
path. Adding her without the auto-close would have shipped pure noise, so
the order matters: close the phantoms first, then watch the seat.
**Notes:** the PO parser anchors on the subject's trailing comma — a
digit-leading rule silently skipped Blue Ridge's `PF593736`, and a bare
`\bPO\s+` grabbed the literal "PO to" from "Convert PO to TW invoice"
(caught by the first test run). Lookup failures never kill the sweep;
`autoclose_invoice_tasks: false` reverts to report-only.
**Files:** email/src/task_sweep.py, email/config.yaml,
email/tests/test_task_sweep.py (6 new; suite 355 green).

## 2026-08-28 — Task-completion sweep + 1,025-task backlog closure (#AP-pending)

**What changed**
- New agent `task-completion-sweep` — the first agent that READS HubSpot Tasks
  back (two agents create them; nothing ever checked completion). Weekday
  8 AM PT: digest to #agent-feedback per owner (overdue + due today, silent
  when clean), ONE bundled DM per owner once a task is 3+ days overdue
  (3-day audit-held cadence, never one DM per task), Monday on-time/late
  completion scoreboard. Monitors seats visionary/sales/charter_sales/
  scheduler_a_l (roles, not names). Deterministic — no CARE pointer.
- 30-day horizon: tasks overdue longer are "stale backlog" — weekly count
  line only, never itemized or DM'd. Day-one reality check: 717 open tasks
  for the four seats, 246 overdue inside the horizon; per-task DMs would
  have repeated the reasoner's 102-DM mistake.
- Backlog remediation (Roman, in-session): `close_stale_tasks.py` bulk-closed
  all 1,025 open tasks created before 2026-08-01 (any owner, incl. ex-staff
  and 59 unassigned). Every id is in the audit log as `task_bulk_closed`;
  the weekly scoreboard excludes those ids so they never read as
  "completed late". Portal open-task count: 1,745 → 712.
- `hubspot_client.py`: `search_open_tasks()`, `search_completed_tasks()`,
  `search_open_tasks_created_before()`, `batch_complete_tasks()`,
  `task_url()`, shared `_search_all()`. Tasks read scope verified live (200).
- `config.py`: `monitor` added to `_ROLE_LIST_KEYS`.

**Why:** Tasks were a write-only medium — an overdue task made no noise
anywhere, and the backlog had grown to 1,745 with 2019-era entries drowning
any live signal.

**Files:** `email/src/task_sweep.py`, `email/src/close_stale_tasks.py`,
`email/src/hubspot_client.py`, `email/src/audit.py`, `email/src/config.py`,
`email/config.yaml`, `email/tests/test_task_sweep.py` (16 tests; suite 331
green), `.github/workflows/task-sweep.yml`, `registry.yml`,
`email/state/audit_log.jsonl` (11 bulk-close records).
## 2026-08-31 — Gmail cursor overlap window (the Lia Beck miss)

**What:** the PO inbox poll now queries `cursor_overlap_seconds` (default
3600) BEHIND its cursor (`_inbox_query`); re-listed mail is free via the
already_processed guard. **Why:** on 8/28 two OPS emails (sisters Jil and
Lia Beck, same parent, same TOR) landed 2 minutes apart; the poll that
processed Jil's advanced the cursor past Lia's arrival — her email sat
invisible to `after:` for 3 days while everyone (Kath, Roman, and Friday's
session) hunted for it. Any message landing behind the cursor (processing
races, Gmail search-index lag) was permanently lost; now anything within an
hour is self-healing. **Recovery (in session):** cursor rewound on a side
branch (lia-recover) + dispatch → Lia's 4 deals created correctly (POs
3114181748-51, $240 = 4 sessions = 3 hrs each, Sept-Dec, Evelin Jimenez
resolved). That run's state push died on the cursor conflict, so its audit
records were reconstructed by hand in this commit (po_processed marker + 4
pending_po_opened rows, sla 2026-09-14) — without them the pending-approval
sweep would never remind about Lia's OAs. Delete branch lia-recover after
merge. **Files:** email/src/po_inbox.py, email/config.yaml,
email/state/audit_log.jsonl (reconstruction), email/tests/test_po_inbox.py
(suite 334 green).

## 2026-08-31 — The weekly FB/IG caption gets a per-platform link line (content-build)

**What changed**
- `marketing/scripts/b2b/deliver-to-slack.py` — "Reply 5 — Facebook + Instagram
  post" is now two replies: Instagram (ends `Link in story.`) and Facebook (ends
  `Link in comments.`). New `append_link_cta()` inserts that line above the
  caption's trailing hashtags line; new `piece_body()` centralizes body assembly
  so the dry-run preview and the real delivery cannot drift apart. Blog assets
  renumbered to Reply 7 and the stale module docstring now matches `PIECES`.
- `marketing/scripts/b2b/content-build.py` — the `fb-ig-post.md` caption prompt
  is told not to write its own link-location phrasing, so the model cannot emit a
  "link in bio" that contradicts the appended line.
- `marketing/scripts/b2b/build-qa-checklist.py` — one checklist line for it.

**Why**
Danielle reported (Slack `1788190269.210389`, correction
`corrections/content-build/2026-08-31-weekly-caption-link-phrasing.md`) that the
Instagram caption should say "link in story" and Facebook "link in comments".

The reported diagnosis assumed a per-platform CTA branch had the two platforms
swapped. There was no branch. `content-build.py` generated ONE caption and
`deliver-to-slack.py` shipped it as a single "post the SAME caption + image to
both" reply, so no correct phrasing was reachable for either platform: whatever
the model happened to write was pasted verbatim into both. Splitting the reply is
what makes Danielle's request expressible at all, and it matches how every other
piece in the bundle already works (one reply per destination, copy-paste ready).

The line is appended deterministically rather than prompted for, because a caption
that names the wrong place to find the link is worse than one that omits it.
## 2026-08-27 — Email agent: campaign-reply categories for the NSSA badge sends

**What:** Two new classifier categories, `campaign_family` (families replying to a
marketing/announcement email: sign-ups, added sessions, referrals — owner
`charter_sales`, 90 min, high priority, draft on) and `campaign_school`
(TORs/EFs/ESs/directors replying: congrats, badge questions, shareable-material
asks — owner `sales`, 8 business hrs, draft on). Added an "Active campaigns"
section to `rules.md` describing the three NSSA badge announcement sends
(subjects, audiences, "just reply" CTA) so the classifier recognizes campaign
traffic; the block is meant to be updated as campaigns launch and retire.
Congrats-only replies get a warm thank-you draft at low risk. School replies
that are real program/PO business still classify `school_partner`.

**Why:** Roman 2026-08-27 — the NSSA badge announcement (3 segmented sends,
~7,250 recipients, lists 3196/3197/3198) uses reply-as-CTA, and replies land in
the agent-triaged admin inbox (info@ is an alias of admin@). Without campaign
awareness, family sign-up replies would route to the schedulers instead of
Paola, and teacher replies would land inconsistently. Routing-table addition
approved by Roman in-session (routing table otherwise LOCKED June 9).

**Files:** `email/rules.md`, `email/src/classifier.py`, `email/config.yaml`
(routing + category_map). Tests: classifier/router/orchestration suites green
(43 passed).

---

## 2026-08-27 — Charter mail is routed by what it IS, not stamped new_deal_po (#AP-pending)

**What changed**
- `ops/hubspot-schema/properties.yml` — declares `po_work_type` (11 options).
- `email/config.yaml` — new `po_inbox.work_types`: owner, priority and
  hs_ticket_category per work type.
- `email/src/po_inbox.py` — the extractor prompt gains `ar_followup`,
  `invoice_correction` and `vendor_onboarding`; owner/priority/category now come
  from config instead of being hardcoded; the ticket carries `po_work_type`,
  `ticket_source` and `source_thread_id`.
- `email/src/hubspot_client.py` — `create_ticket(extra_props=...)`, and a 400 on
  an unsynced property retries without it rather than losing the ticket.
- `email/tests/test_po_work_types.py` — 12 tests.

**Why**
`po_inbox` filed every charter@ ticket with `category="new_deal_po"` hardcoded at
the call site. On 2026-08-27 that was 93 open tickets — and **42 of them carried
"Not a PO:" in their own description**. The agent works out what each one is,
writes it in prose, and the next line threw it away.

The cost is measurable. Across 845 tickets created since 2026-06-01:

| bucket | n | closed | median time to close |
|---|---|---|---|
| a real hs_ticket_category | 157 | 92% | **0.25 days** |
| the catch-all | 688 | 80% | 2.15 days |

8.6x slower and 12 points less likely to close, on 81% of the queue. The
mechanism: a constant category means no routing rule matches, so no owner is
derived, so it lands on whoever owns the inbox (Kath) with no SLA and no
done-state. That one line is why Kath held 95 tickets covering work that was
never hers, why the Granite Mountain COI sat 14 days with no compliance owner,
and why AR chasing was split across four people.

The three new types come from the corpus, not from imagination — they are what
the agent's own "Not a PO:" summaries already said: vendor_onboarding 11 open,
ar_followup 7 (median 14d), invoice_correction 2 (Suncoast held $1,330 for ten
days over a Bill To name).

Also finally writes `ticket_source` and `source_thread_id`, declared for #AP007
and written on zero tickets until now — which is why dedup could only key on the
PO number and the reasoner had to find Gmail threads by searching the subject.

**Needs the schema sync.** `po_work_type` must exist in portal 6312752 before
the stamp lands: run `.github/workflows/hubspot-schema.yml` (dry-run first). Until
it does, `create_ticket` drops the stamp and logs a warning rather than failing —
tickets keep flowing either way.

**Files touched**
- `ops/hubspot-schema/properties.yml`, `email/config.yaml`
- `email/src/po_inbox.py`, `email/src/hubspot_client.py`
- `email/tests/test_po_work_types.py`, `docs/CHANGELOG.md`

**Verification** — 328 passed (was 316; 12 new). Config is asserted against the
real closed `hs_ticket_category` enumeration so an invented value fails the suite.

**Decision log** — candidate: "charter inbox mail is categorised by work type;
the agent's own classification is stamped, not discarded."

---

## 2026-08-27 — The reasoner can read the charter@ Gmail thread (#AP-pending)

**What changed**
- `email/src/gmail_client.py` — new `get_thread()` and `find_thread()`; the
  message parser factored out as `_parse_message()`.
- `email/src/ticket_reasoner.py` — new `enrich_gmail_thread()`, run on every
  PO ticket before reasoning.
- `email/src/hubspot_client.py` — `search_open_tickets()` now fetches `content`.
- `.github/workflows/ticket-reasoner.yml` — new, dispatchable, dry-run default.
- `email/tests/test_ticket_reasoner.py` — 6 more tests.

**Why**
Roman, 2026-08-27, on the Koby Wells ticket: Kath sent invoice 51832 to Suncoast
on Aug 17 and the reasoner still reported "no response from us is recorded".

PO tickets carry **zero** HubSpot email engagements by design — po_inbox embeds
the inbound mail as a NOTE ("The email lives in Gmail, not a HubSpot
conversation") and every reply Kath sends leaves from the charter@ mailbox,
which HubSpot never sees. So the sweep was judging 44 of Kath's 97 tickets on
evidence that structurally cannot contain her outbound work. Its BALL_IN_COURT
verdicts on that queue were unreliable, and right only by luck where they were
right at all.

Three defects found while wiring it:

1. `search_open_tickets()` never requested `content`, so `description` was
   empty on EVERY ticket the sweep has ever looked at — including the sender
   address that points back to the Gmail thread.
2. `gather()` flattens note text to a single line, so `Subject:(.+)` swallowed
   231 characters of message body into the Gmail query. The subject now comes
   from the TICKET subject, which is the email subject behind a known prefix.
3. The sender is written two ways ("From: Name <addr>" in the description,
   "— from Name" in the note), so extraction takes the first real address that
   is not our own mailbox instead of matching either shape.

`gmail_thread: UNAVAILABLE` is deliberately distinct from an empty thread and
the model is told to cap confidence at 0.6 on it — an unlocatable thread is not
evidence that nobody replied.

**Not yet verified against live data.** The Google service-account credential
exists only as an Actions secret, so the Gmail path cannot run locally. The new
workflow is how it gets exercised, and `workflow_dispatch` only becomes
available once this is on the default branch.

**Files touched**
- `email/src/gmail_client.py`, `email/src/ticket_reasoner.py`
- `email/src/hubspot_client.py`, `.github/workflows/ticket-reasoner.yml`
- `email/tests/test_ticket_reasoner.py`, `docs/CHANGELOG.md`

**Verification** — 304 passed (was 298; 6 new).

**Decision log** — candidate: "a ticket's evidence includes the mailbox it
actually lives in; absent evidence is never read as absence of action."


---

## 2026-08-28 — Transactional SMS moves from HubSpot workflows to the agent

**What:** `email/src/sms.py` — a deal-driven SMS sweep run from deal_sync
every ~15 min, sending via JustCall (line +18188691627, the one schedulers
answer). Phase 1 covers Charter Trad (pipeline 907748). Branch semantics
mirror the old flow in tested code: tutored Yes → text now; No → DM the
deal's owner, text next sweep; unset → skip, audited. Guardrails: one text
per deal (audit key), one per FAMILY per 24h (4-PO emails send 1 text),
quiet hours 8-20 PT, `sms.start_date` hard fence (2026-08-29 — the backlog
can never be texted), opt-out property hook, em-dash scrub, 3-strike retry
then manual-text flag. Config under `sms:` in config.yaml.
**Why:** the HubSpot flow chain (stamp deal → stage-copy workflow → contact
flow → self-clearing trigger property) died silently on an Aug 13 edit — no
charter family texted for two weeks, zero alerts. Workflows are unversioned,
untested, and fail silent; the agent is none of those. Sweeping DEALS also
covers manually created deals — the Free Trial pipeline was NEVER wired to
any SMS flow (Yolanda's Perez/Motiwalla/Villarroel report).
**Cutover:** flow 1603217415 is already dead (left disabled-in-effect); a
pipeline's flow must be OFF before it's added to `sms.pipelines`. Phase 2/3:
gold/in-person + trial pipelines, then retire the stage-copy workflow and
`contact_level_deal_stage`. 54 stale enrollment flags remain to clear
(scripts ready; classifier blocked in-session, Roman runs them).
**Files:** email/src/{sms,config,deal_sync}.py, email/config.yaml,
email/tests/test_sms.py (10 new; suite 342 green), docs/PO-PROCESS.md.
**Decision to log:** transactional SMS is agent-owned; workflows are for
nothing customer-facing that the fleet can do in code.

## 2026-08-28 — Parent resolution: never guess across families (Mateo Murray-Fiore)

**What:** PO 3114179131 (Mateo Murray-Fiore, iLEAD) resolved the WRONG parent —
Luis Ramirez, whose private-pay son is a different Mateo. Deal, TW family
(customer 2159873), and the SMS parent_email all keyed on him. Two compounding
causes, both fixed:
1. `teachworks_client.find_family_by_student` queried TW with the PO's exact
   surname ('Murray-Fiore'); TW has 'Fiore' → zero candidates, so the surest
   source (Sarah Fiore's family, real lesson history, TOR Emma Luckey) was
   skipped. NOW: exact surname first, then each hyphen/space part; first name
   stays exact and lesson-history scoring still gates every candidate.
2. `po_inbox._find_parent_via_deals` used the limit-10 unsorted deal-NAME
   token search (same disease as the numbering bug, second call site) plus an
   `or cands` fallback that matched on FIRST NAME ALONE when the last name hit
   nothing — that fallback picked Luis. NOW: exact student-property search
   (search_deals_by_student, compound parts retried), the first-name-only
   fallback is DELETED, and a missing last name returns None → parent chase.
**Why:** a wrong family is worse than no family — chase beats guess, always.
**Remediation (in session, Roman-approved):** deal 64464582696 repointed to
Sarah Fiore (association + parent_email + rename) with an explanatory note;
Kath had detached Luis; Roman deleted the mistaken TW student. Kath DM'd to
check SMS flow 1603217415 for a Luis enrollment and watch for a duplicate
'Mateo Murray-Fiore' TW student on the next deal-sync pass.
**Files:** email/src/{teachworks_client,po_inbox}.py,
email/tests/test_po_inbox.py (320 green), docs/PO-PROCESS.md (Stage 2 synced).

## 2026-08-27 — Cron-starvation watchdog + local PO-inbox heartbeat (Roman: "both")

**What:** GitHub's schedule trigger starved the whole fleet today — the PO
inbox's 9 AM PT window opened and no scheduled run fired for 8.5 hours
(email-triage 10 hrs stale, call-agent 8, deal-sync 6, all mid-business-day);
a Lake View PO (105712-C030-LVC) sat unread until a manual dispatch at 10:34.
Two layers added:
1. `ops/fleet-health/watchdog/cron_watchdog.py` — runs after every retry
   sweep (fleet-retry.yml): any watched scheduled workflow silent past its
   threshold during PT business hours (po-inbox 60 min, triage 90, deal-sync
   60, call-agent 60) gets a catch-up `workflow_dispatch` (dispatches fire
   even when cron starves) + ONE Slack alert per episode to the approvers.
   Reuses sweep.py's gh/alert helpers. Limit: rides the scheduler it watches.
2. `scripts/po-inbox-heartbeat.sh` + `scripts/launchd/com.aplus.po-inbox-heartbeat.plist`
   — launchd on Roman's Mac, every 15 min, weekday 07:45-19:15 PT: dispatches
   email-po-inbox.yml unless a run happened <12 min ago; a failed dispatch
   DMs the visionary role (token from .env, role from email/config.yaml).
   Installed to ~/Library/Application Support/aplus/ (repo copy is the
   template). Covers TOTAL cron starvation, where layer 1 also sleeps.
**Why:** a PO sitting unread is booked-lesson/invoice latency; retry sweeping
only sees runs that STARTED — never-started runs were invisible before this.
**Files:** ops/fleet-health/watchdog/cron_watchdog.py, .github/workflows/
fleet-retry.yml, scripts/po-inbox-heartbeat.sh, scripts/launchd/….plist.
**Also:** dispatched catch-up runs for triage/deal-sync/call-agent in session;
the earlier manual PO-inbox dispatch created the Keesee deal ("Lake View
Charter School 2" — the #128 numbering fix live) and routed Epic's re-sent
C&CP as COMPLIANCE/HIGH to Danielle (dispositions live).

---


## 2026-08-26 — Ticket routing: call check-ins to Paola, internal fallback names the seat

**What changed**
- `ops/call_agent/config.yml` — negative-sentiment call check-in ticket
  `hubspot.ticket.owner`: `roman` → `paola`.
- `email/config.yaml` — `internal.fallback`: `roman` → `visionary`.

**Why**
An L10 audit of Roman's 18 open tickets traced where they come from. Two were
config, not human hand-off:

1. The call agent's follow-up TASK went to `default_task_owner` (Paola, per the
   2026-08-13 routing decision: "Paola does 100% of follow-up") while the
   companion check-in TICKET for the same call was hard-wired to Roman four
   lines below it. One call, two owners. Three such tickets were open on Roman
   at audit time, 6 to 14 days old. The ticket now follows the task.
2. `internal.fallback` named a person, which the accountability-chart rule
   (Roman, 2026-08-14) reserves for the `staff:` block. `fallback` is already in
   `_ROLE_KEYS`, so `visionary` resolves through `roles:` to the same person
   today — this is shape, not behavior. Team change now means editing `roles:`
   only.

Not changed: the email agent's category routing was found CORRECT. business_dev
and school_partner route to `sales` (Danielle) and complaint/unknown to
`scheduling_lead` (Mandy), exactly as configured; the audit log confirms every
ticket was created with the right owner. The 8 that reached Roman were
reassigned by hand in the CRM afterward. That is a people conversation, not a
config fix. Likewise SLA escalation never reassigns — `escalation.level3` is
`operations` (Emily) and the sweep only DMs.

**Files touched**
- `ops/call_agent/config.yml`
- `email/config.yaml`
- `docs/CHANGELOG.md`

**Verification** — `email` suite 247 passed; both configs re-resolved
(`ticket.owner` == `default_task_owner` == Paola; `internal.fallback` →
visionary → Roman).

**Decision log** — candidate entry for the A+ Decision Log: "call check-in
ticket follows the follow-up owner, not the Director." Not yet numbered.


---

## 2026-08-26 — Reasoning sweep + the 24-hour pester policy (#AP-pending)

**What changed**
- `email/src/ticket_reasoner.py` — new. Gathers evidence per open ticket across
  HubSpot (email direction, notes, contacts) and JustCall (texts, calls), adds
  the invoice proof, classifies, then closes or pesters.
- `email/src/justcall_client.py` — new, read-only SMS/call index by number.
- `email/src/hubspot_client.py` — `get_ticket_emails/notes/contacts`,
  `invoiced_po_numbers()`.
- `email/src/audit.py` — `last_reasoner_pester()`.
- `email/config.yaml` — new `reasoner:` block.
- `email/tests/test_ticket_reasoner.py` — 21 tests.

**Why**
Roman asked for a 24-hour pester policy. There was none: the SLA chain fires on
per-category hours, pings each level once, then goes silent forever, and only
ever saw agent-filed tickets. But a PURE 24-hour rule is wrong too — measured on
the live queue it fires 102 DMs, 77 of them to Kath, and most of hers are PO
tickets whose invoice already exists. Pestering someone about finished work is
how a bot gets muted. So the trigger is the ticket's real STATE, not its age.

Ladder (Roman 2026-08-26): 24h owner, 48h + supervisor, 96h + last resort, daily
after. Pesters regardless of who owes the reply.

Closing is double-gated: `allow_close` is OFF, and a close also needs confidence
>= 0.85. Hard evidence short-circuits the model entirely — an invoiced PO and a
same-PO duplicate never need a judgment call.

`invoiced_po_numbers()` reads HubSpot's own Invoice # field rather than matching
Teachworks invoice amounts. Cross-checked on the open queue: identical 33-of-36
answer, one system instead of two, no ambiguous amount matching.

**What the dry run caught (this is why it was run)**
`mark_duplicates` originally keyed on subject text as well as PO number, and
moved to close ticket 45243331980 — one of two tickets both titled "Eddie
Sumlin" from the same referral partner but for DIFFERENT students (CNA support
on Saturdays vs a new intake for Kaliyah P). Closing it would have destroyed a
live referral that has already sat 111 days. Dedup is now PO-number only;
`source_thread_id` would be the right second key but is populated on zero open
tickets, same unwritten #AP007 convention as `ticket_source`.

**Dry-run result, 156 open tickets, nothing written**
BALL_IN_COURT 48, RESOLVED 29, WAITING 24, NO_ACTION 20, UNCLEAR 18, DUPLICATE
17 → would close 61, pester 86, leave 9. Queue 156 → 95. Checked against the 14
tickets identified by hand as genuinely unresolved: after the dedup fix it closes
none of them.

**Files touched**
- `email/src/ticket_reasoner.py`, `email/src/justcall_client.py`
- `email/src/hubspot_client.py`, `email/src/audit.py`, `email/config.yaml`
- `email/tests/test_ticket_reasoner.py`, `docs/CHANGELOG.md`

**Verification** — 292 passed (was 271; 21 new).

**Decision log** — candidates: "tickets are pestered on a 24/48/96h ladder then
daily, regardless of who owes the reply"; "a ticket is triaged on its evidence,
not its age"; "only a shared PO number proves two tickets are duplicates."


---

## 2026-08-26 — Parent resolution from deal student-name properties (#AP-pending)

**What changed**
- `email/src/hubspot_client.py` — new `search_deals_by_student()` (matches the
  deal properties `student_first_name` + `student_last_name_if_diff_from_parent`,
  first AND last, never first alone) and `is_family_contact()`.
- `email/src/po_inbox.py` — new `_parent_from_student_deals()`, tried first
  inside `_find_parent_via_deals()`; the deal-NAME search stays as fallback.
- `email/conftest.py` — autouse fixture blocking live HTTP in unit tests.
- `email/tests/test_parent_from_deals.py` — 13 tests.

**Why**
Roman's idea, 2026-08-26: if a PO names a student, look that name up in the
DEAL student-name properties. Measured against the 19 deals flagged NEEDS PARENT
since 2026-08-01, it reaches the correct parent for all nine families and
resolves 18 of 19 uniquely. It beats both existing lookups because:

- searching contacts by `lastname` assumes the family shares the student's
  surname. Giada Di Nardo's parent is Leeanne Gonzales (0 matches) and Matthew
  Rose's is Megan Miller (3 matches, and it picked the wrong one — Dina Rose, a
  2022 contact — then named five deals after her);
- searching deal NAMES is text matching over a convention that carries typos:
  four consecutive Doyal deals read "Copper" while the property reads "Cooper";
- the old guard rejected a lone surname match unless the parent record already
  named THAT student, which a new sibling never does. All three Czaja children
  were flagged despite Angela Czaja being in HubSpot since January.

Two guards, both load-bearing: only a STRICT frequency winner is accepted (a tie
falls through to NEEDS PARENT), and a first-name-only match is never accepted
("Cooper" alone spans three unrelated families).

Also fixed: `is_family_contact()` no longer drops a parent tagged Teacher of
Record. In homeschool charters the parent frequently IS the EF/ES — Kristy
Doyal's `a_persona` reads "Teacher of Record/EF/ES;Family" — and the old filter
excluded every TOR-tagged contact, discarding real parents.

**Test-harness fix (found doing the above)**
`DRY_RUN` only short-circuits WRITES, and `config.py` calls `load_dotenv()` at
import, so a local test run carried a real HubSpot token and the suite was
quietly making live API calls; CI was making calls that could only fail. The new
autouse fixture blocks `requests.*` outright. Suite runtime went 17.02s → 0.27s
with no test failing, which shows none of that traffic was ever needed.

**Known data bug (not fixed here)**
Deal `57397570424` is Payton Curtis's but carries
`student_last_name_if_diff_from_parent = "Doyal"`. That mis-stamp is what drags
Anita Curtis into Cooper Doyal's candidate set, and similar contamination on the
Heartland deals is what makes Rayven Holloway tie 7-7. Worth a cleanup pass —
several things read that field.

**Files touched**
- `email/src/hubspot_client.py`, `email/src/po_inbox.py`
- `email/conftest.py`, `email/tests/test_parent_from_deals.py`, `docs/CHANGELOG.md`

**Verification** — 271 passed (was 258; 13 new).

**Decision log** — candidate: "resolve a PO's parent from the deal student-name
properties, and never guess on a tie." Not yet numbered.


---

## 2026-08-26 — Aging sweep: every open ticket gets nagged, not just agent-filed ones

**What changed**
- `email/src/hubspot_client.py` — new `search_open_tickets()`: every open ticket
  in the portal, read straight from HubSpot.
- `email/src/sla_sweep.py` — new `aging_sweep()`, called at the end of `run()`.
- `email/src/audit.py` — new `last_aging_nag()`; added `from __future__ import
  annotations` (the new signature uses `str | None` and CI/local run 3.11/3.9).
- `email/config.yaml` — new `aging_sweep:` block; `internal.fallback`
  `visionary` → `operations`.
- `email/tests/test_aging_sweep.py` — 11 tests.

**Why**
Roman, 2026-08-26, after the L10 audit found four of his tickets aged 96 to 135
days having never triggered a single ping. Two separate holes:

1. **Coverage.** The escalation chain walks `state/audit_log.jsonl`, so it only
   sees tickets the email/PO agents created. Tickets made by hand in the CRM and
   tickets from the call agent were never swept at all. `aging_sweep()` reads
   HubSpot directly instead.
2. **It went silent.** `escalation_levels_pinged()` means each level fires once
   and then never again, so a ticket that survives level 3 is quiet forever no
   matter how old. The aging sweep re-nags every `repeat_every_days`.

Thresholds (7d owner / 14d + supervisor / 30d + last resort / re-nag weekly) are
the knob to tune; they are config, not code.

Also locked this session: **Roman does not own support tickets.** Anything that
would have escalated to him goes to the `operations` seat (Emily), which is why
`internal.fallback` moved off `visionary`. His 18 open tickets were reassigned
in HubSpot the same day — agent-routed ones back to the routing-table owner,
hand-escalated ones to Emily. His open count went 18 → 0.

**Files touched**
- `email/src/hubspot_client.py`, `email/src/sla_sweep.py`, `email/src/audit.py`
- `email/config.yaml`, `email/tests/test_aging_sweep.py`, `docs/CHANGELOG.md`

**Verification** — `email` suite 258 passed (was 247; 11 new). A test caught a
real bug pre-merge: a never-nagged ticket read as "nagged just now" because
`_days_since(None)` returns 0, which would have silenced the sweep on exactly
the tickets it exists to catch.

**Decision log** — candidate: "the Director does not own support tickets;
escalations land on Operations." Not yet numbered.

---


## 2026-08-26 — Tutor-issue ticketing LIVE

**What:** Flip after the verified live baseline (run 33030729514: 0 created,
0 refusals, nothing sent, state committed). #tutor-issues channel
C0BSU4KGA0K wired into config; Actions schedule enabled (Monday 17:00 UTC
sweep + 2h inbound/intake polls); temporary branch-push verification
trigger removed; registry status active.

**Why:** All launch gates from the build entry below passed. Still open for
Roman: dedupe-period confirmation (config-tunable defaults live: weekly
sweep types / rolling-30d report types) and the decision-log entry.

**Files:** `ops/tutor-issues/config.yml`, `.github/workflows/tutor-issues.yml`,
`registry.yml`, `docs/CHANGELOG.md`.


---

## 2026-08-26 — Tutor-issue ticketing engine (ops/tutor-issues, PR pending)

**What:** New engine logging tutor issues as HubSpot tickets on the TUTOR's
contact record (Support Pipeline, category "Tutor Issue", owner = Operations
role = Mandy, opens in "Working on it"). Five types via `tutor_issue_type`;
6 new ticket properties + `tutor` ticket group + `ticket_source` option
declared in `ops/hubspot-schema/properties.yml` (sync post-merge). Three
sources: Monday Teachworks sweep (no-shows -> missed_lesson_or_late;
unmarked-after-Sunday -> notes_not_completed, same definition as the
scorecard metric), reasoned inbound family reports (triage audit log +
HubSpot Conversations bodies, JustCall SMS; Claude extraction with the
reasoning written into the ticket; unresolvable = NO ticket, scheduler told
to file manually), and structured Slack intake in #tutor-issues for types
2/4/5. Scheduler notices route Janelle/Yolanda by the A-L/M-Z student split
(same rule as the missed-lessons sync). Guards: baseline-stamp first run,
one open ticket per tutor/type/period (weekly sweep types, rolling-30d
report types — Roman still to confirm), ONE digest per run, hard caps that
refuse to act, idempotent event keys. Lateness detection is OFF pending the
`--probe-lateness` evidence that Teachworks records an actual start.

**Why:** Roman-approved policy 2026-08-26: issues we notice must become an
auditable, silent (v1) log on the tutor record, with escalations landing on
Operations; automated only where Teachworks proves the event, because a
false ticket about a contractor's conduct is worse than a missed one. The
notification guards answer the 2026-08-25 aging-sweep near-miss (80 DMs).

**Files:** `ops/tutor-issues/` (engine, config, tests, README),
`ops/hubspot-schema/properties.yml`, `registry.yml`,
`.github/workflows/tutor-issues.yml`, `docs/CHANGELOG.md`.


---

## 2026-08-26 — PO agent refined off a 6-day audit (Roman session)

Ten changes from auditing Aug 20-26 (49 PO deals, $9,178; 24 false pending
reminders; 6 duplicate-named deals; a PO cancelled 2 hrs after intake that the
agent acknowledged politely and did nothing about):

1. **`staff` shadowing crash fixed** (`main.py`) — `staff = cfg()["staff"]`
   in the internal-routing branch shadowed the import, so the pre-deal-lead
   branch raised UnboundLocalError; 3 threads retried every 15 min Aug 22-25,
   never processed. Local renamed `staff_map`.
2. **'School N' numbering fixed** — `_next_school_seq` searched deal-name
   tokens, limit 10, no sort: any student with 10+ historical deals ALWAYS
   restarted at N=1 (Violet McGraw iLead 1,2,3 twice; each Saenz kid 1,2,3,4
   twice — 24 distinct POs, zero true dupes). Now: exact-match search on
   `student_first_name` (+last, first-only fallback), newest-first, limit 100
   (new `hs.search_deals_by_student`), PLUS a run-scoped `_RUN_SEQ` counter so
   same-run emails continue 4,5,6 past the search-index lag.
3. **Two service offerings in hours computation** (Roman decision, locked):
   $75/hour AND $60 per 45-min session (`po_inbox.service_offerings`).
   `hours` is ALWAYS hours (4-session PO stamps 3; no new properties). Rate +
   `rate_unit` extracted from the PO; no rate → compute only when exactly ONE
   offering divides the amount cleanly; $300 fits both → blank + 🚩 flag.
4. **`po_month` finally defined in the extractor prompt** (YYYY-MM, service
   month not issue date) — it was an undefined key, so `lessons_fulfilled_date`
   (invoice due = end of PO month) was blank on 13/15 deals; missing month now
   ⚠️-flags into the gap DM.
5. **Resolved parent email stamped** — the agent resolved families via TW/prior
   deals but stamped only the raw PO field (blank on iLEAD OAs): 14/15 deals
   missing `parent_email` the CRM already knew, gap DMs crying wolf. The
   resolved value now backfills `po['parent_email']` pre-stamp.
6. **Gap DM reworded** ("not in the PO and not resolvable from records") and
   now includes the two fields Kath actually needs: hours + invoice due date.
7. **Pending-approval sweep: 14 CALENDAR days** (`pending_portal_approval_days`,
   was 16 business hours) — iLEAD/OPS portal approval takes ≥14 days (Roman),
   so the old window produced only false nags.
8. **PO cancellation handling** (`_handle_cancellation`, decisions locked:
   zero + Kath voids): school cancellation notice → deal to its Stopped stage,
   amount+hours zeroed, note pinned, DMs (Kath+Roman+deal owner), HIGH
   void-TW-invoice task. Partial (billable>0) → NOTHING auto-changes, manual
   flag. Cancelled-PO re-issue announced as re-issue, not duplicate. Ticket
   subject "PO CANCELLED — …", HIGH.
9. **Non-PO dispositions** via `category_hint`: vendor_compliance → HIGH ticket
   to `compliance_owner` (sales seat — Epic California C&CP sat as generic
   MEDIUM while blocking that school's POs); scam → LOW + sender never captured
   as parent contact (Marcus Parker advance-fee pattern was recorded as
   parent_email); marketing_junk → LOW.
10. **Em-dash scrub at the Gmail-draft choke point** (`gmail_client._scrub_outbound`)
    — the locked no-em-dash outbound rule was prompt-only and a Heartland draft
    shipped one on 2026-08-19; now enforced in code on every draft body.

**Why:** the audit showed the agent's data capture was ~50% of spec on live
deals, its alerts fired about the wrong things, and cancellations had zero
handling (live money risk).
**Files:** email/src/{main,po_inbox,hubspot_client,gmail_client,config}.py,
email/config.yaml, email/tests/test_po_inbox.py (suite 258 green),
docs/PO-PROCESS.md (kept in sync per its header).
**Also this session (manual, outside this PR):** Emma Savoie deal 64379560281
stopped/zeroed + team alerted; Epic ticket 47830084212 → Danielle HIGH (via
scratchpad script Roman ran). **Pipeline config gap flagged to Roman:** Charter
Trad "Stopped" (13267787) is isClosed=false/10% — cancelled deals pollute the
forecast; Level Up's is closed/0%. HubSpot-side fix, Roman's call.

---


## 2026-08-26 — Duplicate-PO red-flag detector in the PO day report (Roman)

**What:** `email/src/po_daily_report.py` — every 6 PM PT report now runs a
PORTAL-WIDE duplicate-PO sweep (all deals with po_number, paginated; numbers
normalized against stray "PO "/"#" prefixes). Any PO number on 2+ deals gets
a 🚩 section in Roman's DM (top 10 listed with deal names/dates); the check
also runs on no-PO days and never kills the report on API failure. Origin:
Rosa Miramontes' 24-deal renewal LOOKED duplicated (same deal names twice) —
PO cross-reference proved all 24 POs unique (two batches per kid), but Roman:
"EXPLICITLY WE CAN NOT HAVE DUPLICATE PO'S red flag alert." Pure helper
find_duplicate_pos() split from fetching for tests.
**Why:** One PO must never be billed twice; name-level similarity is not
enough to spot it, number-level is.
**Files:** email/src/po_daily_report.py, email/tests/test_daily_summary.py
(suite 249 green).

---

## 2026-08-25 — Spotlight reel: delivery no longer gated on `--skip-hubspot`

**What:** `stage_reel` and `stage_textstory` decided whether to upload to Slack
by reading `skip_hubspot`. That flag means "Skip HubSpot contact lookup and
proceed with local input only" (Phase 0 auto-discovery); the documented delivery
gate is `--dry-run` ("Run stages without HubSpot publish or Slack delivery").
Both stages now read a single helper, `_is_delivering(run)`, which keys off
`dry_run`. Three consequences, all verified: a `--skip-hubspot` run now actually
uploads the reel; a `--reel-only --dry-run` run no longer posts to Slack (it
did); and a blocked reel now posts its heads-up under `--skip-hubspot` instead
of swallowing it. `reel_status`/`textstory_status` of `"ok"` is now reserved for
an asset that reached Slack — a rendered-but-unposted one reports
`"generated, not delivered (--dry-run)"` — and `--reel-only` treats delivery
(not rendering) as the success criterion except under `--dry-run`.

**Why:** Paola's fifth report of missing Animated Spotlight Reels (thread
1787612254.091039, correction `2026-08-24-spotlight-reels-not-delivered`). With
`--skip-hubspot` set, the reel generated in full (Gemini stills, TTS, Veo clips,
ffmpeg encode), `deliver_reel.py` was never invoked, the "reel is missing" alert
was suppressed by that same flag, and the run printed `Reel: ok`. `stage_slack`
never read the flag, so the case study, graphics and thread arrived normally and
only the video was absent — exactly what Paola kept reporting. This also explains
why PRs #95, #100, #104, #107 and #113 did not help: they hardened the alerting
that this flag switches off. #95's changelog lists a `--skip-hubspot` scenario as
verified, which locked the wrong behavior in as expected.

**Files:** `marketing/scripts/b2c/spotlight_orchestrator.py`.

**Verified:** the real `stage_reel` driven with `subprocess.run` and the Slack
helpers stubbed, across four scenarios (pipeline + `--skip-hubspot`, pipeline
with no flags, `--reel-only --dry-run`, and blocked-on-missing-key +
`--skip-hubspot`), run against both `main` and the fix. No APIs, Slack or ffmpeg
touched. `marketing/` has no committed test harness, so this was a scratch
script rather than a checked-in regression test.

**Not done:** no reel was produced or delivered for the three students. That
needs Gemini/OpenAI/Slack credentials, the Drive folder IDs (FERPA-withheld to
the Slack thread) and a workflow dispatch, none of which are available from the
repo. Still open and unchanged by this PR: there is no GitHub Actions workflow
that runs `--reel-only`, so the recovery path built by #100/#104/#107/#113 can
only be run from a laptop with full credentials — Paola cannot self-serve it.

---

## 2026-08-25 — Charter campaign fully live + Cold Revival wave built (Roman)

**What:** (1) ALL 5 campaign workflows ON (Roman's toggles): 359 of 429 gap
families emailed (Win-back-1 259, Multi 67, Never-Started 24, No-Lesson 9);
3 converters correctly send-blocked by exit goals (Garcia, Lujan, Miller);
Reply-to-Paola Slack ping live. Conversions to date: 6 families, 20 POs,
~$5.4k. (2) Never-Started AUDIT before its launch: 4 false "never started"
pulled (Sicam, Loya, Gonzalez, Allen — sequential monthly POs prove service;
TW match missed them, likely different email/name; pending student-name TW
lookup). (3) NEW WAVE built on Roman's "Build it": ever-held QTL-Charter
status-history scan (full portal, 315 ever-held; only 4 hold it now) ∪
charter intake fingerprint (charter_school_family_/student_school) →
**189 cold-revival prospects** (charter-interested, NEVER any charter deal,
reachable, minus live-funnel/OPEN_DEAL/prior-repliers/tests). List 3188,
emails 220327810721 + 220321043819 (em-dash-free per new rule), workflow
1872725354 (OFF, pending Roman publish+toggle; goal = ANY charter deal OR
reply). Reply-ping workflow extended to list 3188. (4) Email copy clarity
pass (Roman): plain English, no "26/27" jargon, "at no cost to you" removed
on Roman's veto, firstname fallback "there" everywhere; sent win-back pair
left untouched.
**Files:** portal-side; scratchpad tooling (uncovered_final.py,
status_history_scan.py, build_prospects.py) — promote to scripts/ if the
cold-revival becomes a recurring motion.
## 2026-08-25 — Badge files committed, with an alteration guard (#AP044)

**What:** the NSSA-supplied `.png` (1200x1200) and `.svg` now live at
`marketing/assets/nssa/nssa-tutoring-program-design-badge-2026-2029.{png,svg}`,
alongside the existing `marketing/assets/` logo convention. `asset_path` and
`asset_path_svg` point at them, so `logo_ready: true` is now backed by files
rather than a promise.

Copied byte-for-byte from the originals on Roman's Desktop — verified identical
by sha256 before committing, and the PNG was opened and read to confirm it is
the real Badge (A+ Tutoring, 2026-2029) rather than a screenshot or a
placeholder.

**The guard:** NSSA permits **no alteration of the Badge image, including text
or design**. That is a rule no code can enforce by reading a policy, so the
sha256 of each file is recorded in `credentials.yml` and asserted by
`test_badge_files_exist_and_are_unaltered`. A recolour to fit a palette, a crop,
or an innocent re-export through an image tool all change the hash and fail the
test. Verified by appending one byte to the PNG: the test failed with
"PNG has been ALTERED", and passed again on restore.

This matters because the graphics pipeline exists to composite and transform
images. Without the guard, an automated resize is exactly how an altered
trademark would ship without anyone deciding to alter it.

**Also:** `test_null_field_never_renders_none` was pointed at
`usage_guidelines_url`, which is the field that is null now that `asset_path` is
populated. The behaviour under test is unchanged; only the example moved.

**Verified:** 18 credential tests, full suite 284.

**Files:** `marketing/assets/nssa/` (2 new), `knowledge/credentials.yml`,
`scripts/tests/test_credentials.py`.

---
## 2026-08-27 — [fix] po_inbox tests: stop calling the live HubSpot API

**What:** the two tests #128 added for the re-issued-PO refinement
(`test_po_number_dedupe_blocks_second_deal`,
`test_no_scheduler_dm_when_nothing_created`) stubbed deal search and creation
but not `hs.stage_label`, whose first call fetches `/crm/v3/pipelines/deals`
LIVE. In CI that 401s and both tests die before their assertions; on any
machine with a token in env they would query the production portal on every
test run. Two-line fix: stub `stage_label` in both. 131 po_inbox tests green,
full suite 289.

**How it got to main:** #128 merged from another session with the 2 tests red,
and this session's own merge pipeline masked the failure locally by piping
pytest through `tail` (the exit-code rule, violated in a shell one-liner).
Found while bisecting after clearing the PR queue.

**Flagged, not fixed (the other session's code):** `stage_label` itself has no
error guard, unlike `pipeline_label` beside it — a pipelines-fetch blip in
production raises mid-PO-processing on the dupe path.

**Files:** `email/tests/test_po_inbox.py`.
## 2026-08-26 — CARE core values wired into the fleet's reasoning layer

**What:** New `ops/values/care-values.md` holds A+ Tutoring's vision, mission
and the four CARE values verbatim from wetutorathome.com/about-us, in a block
marked LOCKED. One canonical copy; the values text appears in exactly one file
in the repo, verified by grep.

Every agent whose output is **reasoned** now carries one pointer line:
`Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.`

**The brief said "every active agent". Only 6 of 26 qualify, and that is the
right answer.** The other 20 are deterministic: syncs, sweeps, metrics, relays,
list builders. They never call a model, so there is no reasoning for values to
shape, and a pointer inside them is dead text a later reader mistakes for
something load-bearing. Same for all 10 manual agents, every one of which was
checked individually rather than assumed.

**The biggest reasoning surface was not in the registry entrypoints at all.**
`topic-gen`, `content-build` and `spotlight-orchestrator` reason through the 15
`SKILL.md` files loaded by `SkillsRunner`, not through their .py files. That is
where blog posts, case studies, brand checks and Danielle's voice are actually
produced. Roman confirmed: "care reaches customer facing". All 15 carry the
pointer.

**Where two prompts existed, the split was made on what the prompt produces**,
not on which was primary (Roman was undecided, so the rule is recorded):
pointer where the model emits language a human reads or a judgment a human acts
on; skip pure extraction or classification into JSON.
- `call_agent.SUMMARY_PROMPT` — writes CRM summaries and handoff notes. Pointer.
- `call_agent.COACHING_PROMPT` — coaches a named colleague on their own call.
  The most values-sensitive prompt in the fleet. Pointer.
- `feedback_agent.ANALYZE_PROMPT` — proposes fixes for a human to approve.
  Pointer.
- `feedback_agent.CLASSIFY_PROMPT` — **skipped.** Pure routing taxonomy (which
  agent, what type). Emits no prose; values change nothing about it.
- `po_inbox.PO_SYSTEM` — initially looked like pure JSON extraction, but the
  same call drafts the real Gmail chase emails a human sends to teachers.
  Customer-facing. Pointer.

**The "how this applies to agent output" section is behavioural, not slogans.**
Every rule in it is falsifiable against a piece of output: never state a metric
without its source; absence of a record is not evidence of absence; say what was
NOT done; name strengths before gaps; propose an agent before a manual
workaround; when the data does not fit the model, the model is probably wrong.
Several are lessons this fleet learned the hard way and had nowhere to record.

**Discrepancies with the brief, for the record:** it said 5 manual agents (there
are 10) and implied all active agents have prompts (6 do).

**Convention documented in CLAUDE.md** so new agents inherit the pointer, with
the deterministic-agent exception stated so nobody "fixes" the gap later.

**Files:** `ops/values/care-values.md` (new), `email/src/classifier.py`,
`email/src/po_inbox.py`, `ops/call_agent/call_agent.py`,
`ops/feedback-agent/feedback_agent.py`,
`marketing/scripts/b2c/spotlight_orchestrator.py`,
`.github/workflows/feedback-fix.yml`, `marketing/skills/*/SKILL.md` (15),
`CLAUDE.md`. Suite 269 green.
## 2026-08-27 — NEW AGENT: pr-merge-nudge — green fixes stop rotting in the queue

**Why:** the feedback loop produces [fix]/[correction] PRs faster than they get
merged. On 2026-08-26: ten open PRs, six of them fixes with green CI, the oldest
six days — while the bugs they fix kept firing. The 2026-08-20 grant lets
Danielle, Paola and Emily approve+merge exactly these, but nobody is prompted,
so nobody merges. The bottleneck was attention, not permission.

**What:** `ops/fleet-health/pr_merge_nudge.py` + Mon/Wed/Fri 9:05 AM PT
workflow. Finds open PRs that are (a) non-draft, (b) older than 3 days,
(c) titled [fix]/[correction], (d) mergeable with a GREEN check suite, and posts
ONE digest to #agent-feedback pinging the approver roster with one-click links.
Fix PRs with failing/pending checks are listed without a ping — they need work,
not approval. Silence means clean.

**Never remediates:** it does not merge, approve, close or comment. The click
stays human. Approvers come from `ops/feedback-agent/config.yml` (roles, not
names) — the same roster that holds the merge grant, so a roster change
propagates automatically.

**Scope kept sharp on purpose:** non-fix PRs are branch-hygiene's beat and are
excluded; Mon/Wed/Fri not daily, because pinging four people daily trains
everyone to ignore the ping (same reasoning as alerts_to staying narrow).

**Validated against the live queue before shipping:** dry-run found exactly the
right four (#93 6d, #102 5d, #101 5d, #106 4d, all green) and correctly excluded
the two 2-day-old corrections still inside the bound.

**Files:** `ops/fleet-health/pr_merge_nudge.py` (new),
`.github/workflows/pr-merge-nudge.yml` (new), `registry.yml`, `docs/FLEET.md`.

---
## 2026-08-25 — NSSA guidelines received: design is not effectiveness (#AP044)

**Roman supplied NSSA's "Promotion Guidelines & Messaging" doc and the Badge
image.** The terms are now encoded in `knowledge/credentials.yml` under
`usage_rules` rather than paraphrased, and pushed into the skills that write
copy — a rule that lives only in a yaml file never reaches the agent drafting a
blog post.

**The term that constrains us most, and was not something we would have
guessed:**

> "This Badge denotes **quality of design, not quality of implementation or
> effectiveness**."

Our content leads with outcome data — 75%, 87.5%, +19.4 RIT. Putting the Badge
beside those figures implies Stanford validated our *results*. It did not; it
reviewed how the program is designed. This is a live risk in exactly the assets
we produce: the spotlight case-study credibility block sits directly above the
results table. `aplus-fact-check` now flags the fusions specifically —
"Stanford-validated results", "NSSA-verified outcomes", a sentence where the
Badge is the subject and an outcome figure the object, or the Badge placed
inside a results table rather than beside it.

**Other terms now enforced:**
- **The image may not be altered in any way**, including text or design. That
  lands on `aplus-graphic-prompts` and the compositing pipeline: no recolouring
  to fit a palette, no cropping, no retyping as vector, no compositing into a
  generated image. Supplied file as-is or leave it out.
- **"Badge" is always capitalised** (NSSA's rule, now a fact-check flag).
- **Stanford attribution is granted** — "the National Student Support
  Accelerator at Stanford University" is NSSA's own approved framing, and it is
  far stronger for a teacher audience than the bare acronym. The three approved
  messages are recorded verbatim so agents lean on the issuer's words.
- Social attribution handles and hashtags recorded for the social skills.

**`logo_ready` flipped to true, but `asset_path` is still null.** The files live
in an NSSA-supplied Google Drive folder and are not in the repo. A consumer must
check `asset_path`, not just `logo_ready`, or it will try to render `None` — the
test says so explicitly and will need updating when the files land.

**Superseded:** the earlier entry treating the live scholarship funnel's "more
than one session" as an overclaim. Danielle (Slack 2026-08-24) explained it:
teachers may nominate **multiple students, one session each**. The funnel was
right and my reading was wrong.

**Verified:** 18 credential tests (3 new, including one asserting the
effectiveness rule actually reached the fact-check skill), full suite 284.

**Files:** `knowledge/credentials.yml`, `marketing/skills/aplus-fact-check/
SKILL.md`, `marketing/skills/aplus-graphic-prompts/SKILL.md`, 5 × content
`SKILL.md`, `scripts/tests/test_credentials.py`.

---
## 2026-08-25 — NSSA badge cleared for marketing use; image stays gated (#AP044)

**Roman:** "i just want it to be known by our agents that we received the NSSA
badge. its a big thing to include in our marketing emails and marketing content."

The first pass shipped `public_ready: false`, which meant agents were *forbidden*
from using it. That was the opposite of the intent. **`public_ready: true`.**
Stating a credential we hold is a statement of fact and Roman is the claim
authority.

**The badge IMAGE is a separate decision and stays shut** — new `logo_ready:
false`. Usage guidelines govern display of NSSA's *mark*: size, clear space,
placement, whether it may sit beside our logo. Those are unread, and a trademark
is not ours to render however we like. A factual sentence carries no such risk.
Splitting the two means the marketing value is available now while the one thing
that actually needs permission stays blocked.

**The gap that would have broken this quietly:** content passes through
`aplus-fact-check` before publishing, and that skill's verified-claims table
knew nothing about the badge. The blog agent would have written a true claim and
our own fact-checker would have flagged it as unverified, or burned searches
trying to confirm it. The table now carries the credential, points at
`knowledge/credentials.yml` as the source, and lists what to flag instead:
a missing term window, wording that does not match `claim_string`, embellishment
("NSSA-certified", "NSSA-accredited", "NSSA-endorsed", "NSSA-approved provider",
"NSSA-rated" — none of which is what we hold), and any use of the image while
`logo_ready` is false.

**Five content skills** (b2b/b2c brand kits, blog-longform, spotlight case
study, danielle-voice) now say the badge is a differentiator worth using, with
guidance rather than just permission: lead with what it means before the
acronym, because most readers have never heard of NSSA; give it one clean
mention in a credibility block rather than three scattered ones; never
embellish; text only.

**A tension worth recording.** Writing that guidance put the claim string into
six files, and `test_no_hardcoded_claim_strings_in_repo` caught it immediately.
But the test was also too strict: it forbade even *naming* the credential, and a
skill cannot teach a badge it may not name. Resolved by separating the two
things — skills name the credential and point at
`knowledge/credentials.yml` for the wording; the test now guards the **claim
string with its term window**, which is the part that goes stale on renewal.
It lives in exactly one place, plus tests and this changelog.

**Verified:** 16 credential tests, full suite 282 passed.

**Files:** `knowledge/credentials.yml`, `marketing/skills/aplus-fact-check/
SKILL.md`, 5 × content `SKILL.md`, `scripts/credentials.py`,
`scripts/tests/test_credentials.py`.

---
## 2026-08-25 — NSSA badge: one credentials file, gated in code (#AP044)

**What:** A+ earned the **NSSA Tutoring Program Design Badge, 2026-2029**. Rather
than putting that string into agent prompts, templates and copy files, it is
declared once in **`knowledge/credentials.yml`** and every consumer reads from
there through `scripts/credentials.py`.

**Why one file:** a claim copied into N places goes stale in N places, and this
one has a hard expiry. Same doctrine as the HubSpot property registry: declare
once, read everywhere, never duplicate. `grep -ri "program design badge"` is a
test (`test_no_hardcoded_claim_strings_in_repo`), not a convention.

**Where it lives, and why not `shared/`:** the #AP044 handoff proposed
`shared/credentials.yml`. There is no `shared/` data directory at the repo root
(`marketing/scripts/shared/` is script code), while `knowledge/` is already
defined by its own README as "material that agents read but do not generate".
Creating `shared/` would have been the parallel home the handoff warns against.

**The gate is code, not convention.** `scripts/credentials.py` fails CLOSED and
raises rather than emitting a partial claim, because a credential that renders
as an empty string inside a vendor packet is worse than a loud build failure:
- `public_ready: false` → `CredentialNotPublic`. **Currently false** and stays
  false until Roman reads NSSA's usage terms.
- surface not in `approved_surfaces`, or in `prohibited_surfaces` →
  `CredentialSurfaceNotApproved`.
- past `expires_on` → `CredentialExpired`.
- a null field (`asset_path` today) never renders the string "None".

**Two additions to the proposed schema:** `prohibited_surfaces` (call-agent
scripts and SMS — SMS has no room for the term window, and a claim without it is
a defect by Roman's own rule), and `expires_on_confirmed`, so the expiry guard
can say out loud when its own input is a guess.

**Expiry guard:** `scripts/credential_expiry_check.py` +
`.github/workflows/credential-expiry.yml`, monthly, warns at 180 days, escalates
after expiry. **Never remediates** — it does not edit copy, retire a claim, or
flip `public_ready`. Verified against all three states by overriding today.

**Wired:** messenger (`{{credentials.<id>.<field>}}` as an available merge field,
never auto-inserted), and the skills that produce partner-facing language —
b2b/b2c brand kits, blog-longform, spotlight case study, danielle-voice — each
told to read the claim verbatim and to check `public_ready` first.

**Found while wiring, not in the brief:**
1. **The blog agent already writes about NSSA badging as a market trend.** A
   published post argues "NSSA-style quality screens favor embedded providers
   like A+", written when we did not hold the badge. It now argues for a screen
   we passed without disclosing that. Content opportunity and a disclosure
   question.
2. **`aplus-research/SKILL.md` lists NSSA as a neutral primary research source.**
   We now hold their credential. A disclosure note was added: citing NSSA for
   field research is fine, leaning on NSSA to validate A+ is not, without saying
   why the relationship exists.

**Roman 2026-08-25:** expiry is **August 2029** (`2029-08-31`; day-of-month not
stated, and the 180-day warning lands the same either way). Badge image files
and usage guidelines are **not yet in hand** — both stay null, and finding a URL
online will not be enough to flip the gate. The terms have to be read.

**Correction to the #AP044 handoff (Roman 2026-08-25):** the handoff named a
second repo, `~/code/skills`, holding "proposal or packet generators". **Neither
exists.** `aplus-agents` is the entire surface, and a search here found no
proposal or packet generator either — the only "proposal" files are internal
HubSpot consolidation docs. The first version of this entry recorded those
generators as "not reachable", which implied they were somewhere else. They are
nowhere.

Consequence recorded in `credentials.yml`: `approved_surfaces` is now annotated
by who produces each surface. Two are agent-produced (case studies, blog author
bio) and resolve through the gate; two are produced by Danielle **by hand**
(charter vendor packets, intervention proposals) with this file as their
reference; two live outside the repo entirely (website, email signature) where
nothing here can enforce the gate, so they become a human checklist item when
`public_ready` flips. The list is permission, not automation.

**Verified:** 15 new credential tests; full suite 281 passed. `registry_check`
clean apart from the pre-existing unregistered `automation-audit.yml`.

**Files:** `knowledge/credentials.yml` (new), `scripts/credentials.py` (new),
`scripts/credential_expiry_check.py` (new), `scripts/tests/test_credentials.py`
(new), `.github/workflows/credential-expiry.yml` (new),
`ops/messenger/messenger.py`, 6 × `marketing/skills/*/SKILL.md`, `registry.yml`,
`docs/FLEET.md`.

---
## 2026-08-24 — Spotlight Orchestrator: `--reel-only` takes a batch; the real blocker escalated

**Reported:** Paola, a fifth time on the same asset — three existing case
studies (Amelia, Ethan, Isabella) are missing their Animated Spotlight Reels.
Backfill request, not a bug: build the reels with the existing pipeline, match
the Wyatt spec, do not touch the other assets in those packs.

**Diagnosis (correcting the filed one):** the approved plan was, for the fourth
session running, "locate the bundles under `marketing/aplus-content/`, run
`build_reel.py`, deliver with `deliver_reel.py`". Re-verified here rather than
taken on trust, and still unrunnable: `marketing/aplus-content/` does not exist
and is gitignored (bundles are 30-day Actions artifacts built in the runner),
and there are no Gemini/OpenAI/Slack credentials and no ffmpeg in this checkout.
The plan's one code item — "consider adding a `--reels-only` flag so future
single-asset backfills don't require a bespoke run" — **already shipped** on
2026-08-20 as `--reel-only BUNDLE`. So the approved plan contained nothing this
session could execute and nothing left to build.

**Why the reels still have not arrived, plainly:** `--reel-only` cannot be run
by the people who need it. There is no `rerender-reel` Actions workflow to match
`rerender-textstory.yml`, and no workflow anywhere invokes `--reel-only`
(verified: zero matches for `reel-only` under `.github/workflows/`). It is a
command that only runs on a laptop that happens to have Veo/Gemini/OpenAI/Slack
keys, ffmpeg, and a hand-unpacked artifact. The three sessions below each named
this as the blocker and each was scoped out of `.github/workflows/`; this
session was too. Four consecutive sessions have now improved a command nobody
can invoke while the asset count delivered to Paola stayed at zero. **This is an
escalation, not another footnote:** the next action on this agent should be the
`rerender-reel` workflow, and it should be scoped in.

**Fix (the honest minimal one, in scope):** `--reel-only` now takes one or more
bundles, because this report is the first to ask for a batch and three bespoke
invocations are three chances to mistype an artifact path with no single verdict
at the end. Every bundle is preflighted before any of them generates anything,
so a bundle unpacked one level off is named up front instead of surfacing after
its predecessors have spent Veo credit; if any bundle fails preflight, nothing
is generated and nothing is delivered (the approved plan's "stop and report
exactly which student and which input is missing"). Each bundle then gets its
own run record and its own `REEL_RECOVERY_TIMEOUT_S` budget — per student, not
split across the batch — and a per-bundle summary plus a batch exit code at the
end. `--reel-thread-ts` is rejected with more than one bundle: it names one case
study's review thread, so a batch sharing it would drop every student's reel
into one family's thread. Repeated paths collapse so a bundle named twice is not
delivered twice. `_bundle_blockers` splits the bundle-shaped preconditions out
of `_reel_blockers` so the batch preflight reports a verdict per student without
repeating the run-wide env/binary blockers once per student; `_reel_blockers`
delegates to it and its output is unchanged.

**Verified:** 47 stubbed assertions across 11 scenarios with `stage_reel`, the
run-state writers and the Slack alert faked — no Veo, Gemini, OpenAI, ffmpeg or
Slack touched. Single-bundle behavior byte-identical (no preflight noise, no
batch summary, the verified "Reel recovery FAILED — nothing was delivered."
string intact); three bundles run in order with distinct run ids; a bundle
missing `metadata.md` and a nonexistent directory each block the whole batch
before the first generation call; a mid-batch failure still runs the bundles
behind it, exits 1, names the failed one, and does **not** claim the batch
delivered nothing; duplicate paths collapse to one run; `--reel-thread-ts`
accepted for one bundle and rejected with exit 2 for two; `--dry-run` renders
without delivering; a normal `--source` run and the standalone
`--reel-thread-ts` guard are unaffected by the `nargs` change. Plus one real
unstubbed run confirming the preflight rejects a bad batch with exit 1 and
writes no run state.

**The three reels are still not generated.** That is what Paola asked for and
this session could not produce it, for the same reason as the last three: no
bundles, no credentials, no ffmpeg here. What changed is that when the batch is
finally runnable it is one command with one verdict.

**Files:** `marketing/scripts/b2c/spotlight_orchestrator.py`, `docs/CHANGELOG.md`.

---
## 2026-08-21 — Spotlight Orchestrator: the reel now names its blocker, in Paola's thread

**Reported:** Paola, a fourth time on the same bundle (Amelia) — "generate and
deliver the superhero video reel for an existing Spotlight case study, **or
surface the specific blocker preventing it**." The second clause is the new
part, and it is the one nothing in the three entries below has answered.

**Diagnosis (correcting the filed one):** the approved plan was again "locate
the bundle under `marketing/aplus-content/`, run `build_reel.py`, deliver with
`deliver_reel.py`". Confirmed unrunnable here for the third session running, and
re-verified rather than taken on trust: `marketing/aplus-content/` does not
exist and is gitignored (the bundle is a 30-day Actions artifact built in the
runner); `GEMINI_API_KEY`, `OPENAI_API_KEY` and `SLACK_BOT_TOKEN` are all unset
in this checkout; `ffmpeg`/`ffprobe` are not installed. `stage_reel` is wired
into `STAGE_ORDER` between `slack` and `textstory` and does run, so "the
orchestrator didn't run it" remains wrong. What was still true, and is what this
session fixes, is that when it runs and fails **nobody learns why**:

1. **The alert only ever said "exit 1".** `run_step` wrote the failing step's
   stdout/stderr to the runner log and then threw away the text, raising
   `reel {name} failed (exit {returncode})`. That string is what reached
   `reel_status`, the completion summary and the Slack heads-up. Whether Veo
   refused one beat on safety grounds, a key was unset, or ffmpeg was missing,
   the operator-visible output was identical — which is how four reports could
   be filed about this reel without the cause ever being written down.
2. **The heads-up goes to a channel that is unset by default.** `_post_stage_alert`
   no-ops without `SLACK_FAILURE_CHANNEL`, and the workflow passes
   `vars.SLACK_FAILURE_CHANNEL || ''`. Even when it is set it is an ops channel,
   not the review thread Paola is waiting in. "Surfaced" to a channel nobody
   reads is indistinguishable from silence — and silence is exactly what she has
   had four times.
3. **A run doomed by config still spent the generation budget first.** The steps
   happen to be ordered cheapest-first only by accident: `stills`/`voice`/`clips`
   need `GEMINI_API_KEY`, but `assemble` is the one that needs `OPENAI_API_KEY`
   (Whisper word timings) and ffmpeg. A recovery missing only the Whisper key
   renders 5 Gemini 2K stills, 5 TTS lines and 4 Veo clips — real money, ~10
   minutes — and only then dies, twice, once per attempt.

**Fix:** all in `stage_reel` and its alert path.
`_reel_blockers()` pre-flights what the steps actually read — `metadata.md`,
`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ffmpeg`, `ffprobe`, and `SLACK_BOT_TOKEN`
when the run will deliver — and names every missing one before the first step
runs, so a run that cannot finish says so instead of buying its way to the same
conclusion. `_have_bin` mirrors `reel_common`'s resolution order so an explicit
`$FFMPEG`/`$FFPROBE` override is not reported as missing. `_last_lines()` keeps
the last three non-empty lines the failing step printed — stderr first (where
the `make_*` scripts `sys.exit()`), falling back to stdout (where `make_clips.py`
reports `NO VIDEO (safety/RAI)` and names the refused beat) — and carries them
into the raised error, so `reel_status` and both alerts now read
`reel clips failed (exit 1): … struggle: NO VIDEO (safety/RAI) … WITH FAILURES
['struggle']` instead of `exit 1`. `_post_thread_note()` posts a one-line plain
note into the case study's own review thread whenever the reel fails and a
thread exists, so the blocker lands where the reel was promised; the ops-channel
heads-up is unchanged in content and still fires alongside it. Recovery wording
now says the thread got that note rather than claiming nothing was posted to it.

**Verified:** stubbed scenarios with `subprocess.run`, the state writers and both
Slack posters faked — no Veo, Gemini, OpenAI, ffmpeg or Slack touched. Blocker
enumeration with nothing available, with `GEMINI_API_KEY` only, and with
everything satisfied (including the `$FFMPEG` override path and the delivering
vs. render-only distinction for `SLACK_BOT_TOKEN`); a blocked stage returning
without executing a single step (asserted by making `subprocess.run` raise);
`_last_lines` preferring stderr, falling back to stdout, handling empty output
and truncating at 400 chars; a Veo RAI refusal on the `clips` step surfacing the
beat name in both the thread note and the ops alert after the retry; the happy
path still running all six steps in order and posting nothing; and `--dry-run`
still stopping after `build_reel` without requiring a Slack token.

**The reel itself is still not generated** — fourth session, same three reasons:
no bundle, no credentials, no ffmpeg in this checkout. This session answers the
second half of what Paola asked for ("or surface the specific blocker"), not the
first.

**Left undone deliberately:** still no `rerender-reel` Actions workflow to match
`rerender-textstory`, which is the thing that would put this recovery on a
button in CI where the keys and ffmpeg live. Three consecutive sessions have now
been scoped out of `.github/workflows/` and `registry.yml` (where the reel
scripts are still absent from `spotlight-orchestrator`'s `depends_on`), and
three consecutive reports have ended without the asset. This is the fix; it
needs a decision from Roman rather than a fourth note here.

**Files:** `marketing/scripts/b2c/spotlight_orchestrator.py`.

---
## 2026-08-21 — Spotlight Orchestrator: the reel recovery run can now finish

**Reported:** Paola, a third time on the same bundle (Amelia) — asking for just
the missing superhero reel to be generated against the existing Spotlight
bundle, without regenerating any of the other assets.

**Diagnosis (correcting the filed one):** the approved plan was to locate
Amelia's bundle, run `make_script` → … → `build_reel` against it, and deliver
with `deliver_reel.py`. None of that is runnable from this repo, for the reasons
the two entries below already record: `marketing/aplus-content/` is gitignored
and built inside the CI runner (there is no bundle here), and there is no
`.env`, no `GEMINI_API_KEY`/`OPENAI_API_KEY`/Slack token and no `ffmpeg` in this
checkout. The invocation the plan describes already exists too — `--reel-only`
shipped 2026-08-20 and does exactly "reel and nothing else". So the honest
question was not *how do we invoke it* but *does that invocation actually
finish*, and two things say no:

1. **Recovery inherited the pipeline's 900s budget.** `REEL_TIMEOUT_S` exists to
   stop a stuck Veo poll from taking the textstory + logsheet stages and the
   completion summary down with it. `--reel-only` has no later stages to
   protect — the reel *is* the job — but got the same 900s ceiling, shared
   across both attempts. A cold recovery renders 5 Gemini 2K stills, 5 TTS
   lines and 4 Veo clips (whose submit alone backs off up to 90s × 6 on a 429)
   before ffmpeg starts. When the first pass eats the budget the retry dies on
   `budget exhausted before script` without running a single step, and recovery
   mode exits 1 — Veo spend burned, nothing delivered.
2. **A failed recovery told the operator to run the recovery.** `_post_reel_alert`
   has one message: "download the bundle artifact from this Actions run, unpack
   it under `marketing/aplus-content/`, then run `--reel-only …`". Correct for a
   pipeline miss; circular for a `--reel-only` run, which is already local,
   already has the bundle, and has no Actions artifact to fetch. It also frames
   the failure as "*Spotlight reel is missing* — blog, graphics and text-stories
   unaffected", i.e. as a fresh pipeline miss rather than "your recovery just
   failed". Pointing at a recovery nobody can act on is precisely how the first
   two reports ended with the reel still undelivered.

**Fix:** `REEL_RECOVERY_TIMEOUT_S` (default 3600s, `SPOTLIGHT_REEL_RECOVERY_TIMEOUT_S`)
applies in `--reel-only` mode; the pipeline keeps 900s unchanged, and the
"budget exhausted" message now names whichever budget actually ran out.
`_post_reel_alert` gets recovery wording: the recovery failed, nothing else in
the pack was touched, nothing was posted to the student's thread, the steps
resume so one more pass is worth it for a transient 429, and if the same step
fails twice fix that step instead of looping. Pipeline wording is byte-identical.
`run_reel_only` also states its premise before doing anything — "no reel in this
bundle yet — confirmed missing", or a warning that an existing
`spotlight-reel.mp4` will be rebuilt and delivered a second time into the
review thread. Not blocked (a deliberate rebuild is legitimate), just never a
surprise.

**Verified:** 22 stubbed assertions across nine scenarios with `subprocess.run`,
the state writers and the Slack alert faked — no Veo, Gemini, OpenAI, ffmpeg or
Slack touched. Happy path (six steps in order, thread-ts passthrough, exit 0);
recovery budget applied to generation with delivery still budgeted separately;
pipeline mode still 900s; a slow first attempt now leaves the retry room to
re-run every step, and the failure names the real step rather than the budget;
a failed recovery exits 1, delivers nothing, and posts an alert with no artifact
instructions and no prefilled restart command; pipeline alert text unchanged;
both pre-flight messages; both bundle guards; `--reel-thread-ts` without
`--reel-only` still exits 2.

**The reel itself is still not generated.** That is the deliverable Paola asked
for and this session could not produce it — no bundle, no credentials, no
ffmpeg here. What changed is that the recovery run, when someone with the
artifact and the keys does start it, is no longer capped at 15 minutes and no
longer answers its own failure with instructions to start over.

**Left undone deliberately:** still no `rerender-reel` Actions workflow to match
`rerender-textstory` — the thing that would make this a button in CI where the
keys and ffmpeg live, and the reason all three reports have ended without the
asset. This session was scoped out of `.github/workflows/` and `registry.yml`
(where the reel scripts are still missing from `depends_on`), same as the last
one. Escalating it rather than re-noting it is the follow-up.

**Files:** `marketing/scripts/b2c/spotlight_orchestrator.py`.

---
## 2026-08-20 — Spotlight Orchestrator: a missing reel can now actually be recovered

**Reported:** Paola, a second time on the same bundle (Amelia) — the superhero
reel still has not arrived. The earlier entry below made the miss *visible*; it
did not make it *fixable*, so the deliverable never showed up.

**Diagnosis (correcting the filed one):** the approved plan assumed the reel
step had been skipped for this bundle and that the reel could be re-run against
it from the repo. Neither holds. `stage_reel` is wired into `STAGE_ORDER` and
`STAGE_DISPATCH` between `slack` and `textstory` and it ran — it is not skipped.
And `marketing/aplus-content/` is gitignored and built inside the CI runner, so
there is no bundle in this checkout to point `build_reel.py` at, and no
Gemini/OpenAI/Slack credentials here to run it with. The real defect is the one
underneath both: **the reel had no recovery path at all.** The textstory stage
has had one since it shipped — the "Re-render textstories for a bundle"
workflow pulls the bundle artifact and re-runs just that builder. The reel got
none. The orchestrator has `--stop-after` but no way to *start* mid-pipeline, so
the only "recovery" was a full re-run.

**Why it matters:** the heads-up added below told the operator to "re-dispatch
the Drive folder with SPOTLIGHT_REEL=1; the reel steps resume from whatever
already rendered." Every clause of that is wrong in CI. A re-dispatch starts at
`init` in a fresh runner, so nothing resumes — every Veo clip and VO regenerates
from zero, at cost and with the same 429 exposure. It rewrites the HubSpot draft
under `--force-update` and re-posts Paola's entire review thread a second time.
And `SPOTLIGHT_REEL` is not a workflow input, so it cannot be set from the
Actions UI at all. Faced with that, nobody ran it — which is why a visible miss
stayed an undelivered one.

**Fix:** `--reel-only BUNDLE` on the orchestrator — generate + deliver the reel
against an already-built bundle and nothing else. `--source` is no longer
unconditionally required (validated in `main()` instead); `--reel-thread-ts`
lands the recovered reel in the case study's existing review thread rather than
starting a new top-level post. Unlike the pipeline, where the reel is a
non-fatal bonus, recovery mode exits 1 if the reel does not ship — delivering it
is the whole point. `--dry-run` renders without posting. `_post_reel_alert` now
names this command, prefilled with the bundle name and thread ts, instead of the
re-dispatch advice.

**Verified:** eight stubbed scenarios with `subprocess.run` and the Slack alert
faked — no Veo, OpenAI, ffmpeg or Slack touched (happy path with thread-ts
passthrough; flaky step rescued by the resumable retry; hard failure → exit 1,
no delivery, alert naming the new command; delivery failure → exactly one
delivery attempt, no double-post; `--dry-run` builds but does not post; missing
bundle dir and bundle-without-metadata.md rejected before anything runs;
`SPOTLIGHT_REEL=0` no longer reads as success in recovery mode) plus CLI wiring
(arg validation, `--help`, and a normal `--source` run still reaching its
stages).

**Still not verified against Amelia's own bundle** — same reason as below: it
lives in a 30-day Actions artifact, not in this checkout, and rendering it needs
credentials this session does not have. What changed is that the recovery is now
a command Roman can actually run against that artifact.

**Left undone deliberately:** there is no `rerender-reel` Actions workflow to
match `rerender-textstory` (which would download the artifact and invoke
`--reel-only` in CI, where the keys and ffmpeg live), and the reel scripts are
still absent from the registry's `depends_on` for `spotlight-orchestrator`. This
session was scoped out of both `.github/workflows/` and `registry.yml`. Together
they are the obvious follow-up: with the workflow in place the recovery is a
button, not a local run.

**Files:** `marketing/scripts/b2c/spotlight_orchestrator.py`.
## 2026-08-21 — Spotlight Orchestrator: the reel retry can now actually clear a refused beat

**Reported:** Paola, a THIRD time on the same bundle (Amelia) — she approved a
one-shot reel delivery on 2026-08-20 and the reel still has not landed in Slack.

**Diagnosis (correcting the filed one, twice over):**

1. *There is no approval handler.* The approved plan asked us to "trace the
   approval handler in `spotlight_orchestrator.py` to confirm it dispatches to
   `build_reel.py` + `deliver_reel.py` for a one-shot approval." No such path
   exists. `spotlight-orchestrator` is triggered only by `repository_dispatch` /
   `workflow_dispatch` from the Drive watcher; nothing in the engine consumes a
   Slack approval. (The `await-slack-approval.py` / `approval-poll.yml`
   machinery belongs to the B2B content-build engine and is not in this agent's
   dependency graph.) So Paola's approval could not start anything — it was
   approval for a human to run a recovery, and no human ran one.
2. *The reel could not be re-delivered from the repo.* Plan step 3 pointed at
   `marketing/aplus-content/<amelia-bundle>/`. That directory does not exist in
   the checkout and is gitignored — bundles are built inside the CI runner and
   survive only as a 30-day Actions artifact. Same wall the 2026-08-20 session
   hit.

**What we found underneath, and fixed:** the resumable retry added on
2026-08-20 cannot clear the failure class its own comment names. It cites "a
single RAI-rejected beat" — but a second pass re-submits the *byte-identical*
still and motion prompt to Veo, precisely because the steps are resumable
(`make_stills` reuses the still on disk). A beat Veo refuses on safety/RAI
grounds is therefore refused again, forever, and no number of retries or Drive
re-dispatches will ever produce that reel. Two sessions of recovery tooling sit
on top of a retry that is a no-op for half the failures it was written for.

**Fix:** break the determinism. `make_clips.py` now records the beat keys it
could not render to `{bundle}/reel/work/clip_failures.json` (rewritten every
pass, empty list included, so a stale file can't be misread). `make_stills.py`
gains `--only key ...`, mirroring `make_clips.py`, and deliberately keeps the
existing anchor even under `--force` when `--only` is given — a fresh anchor
would relock the hero to a different face and the regenerated beat would no
longer match the beats already rendered. `stage_reel` reads the failures file
after a failed attempt and re-renders exactly those stills before retrying, so
attempt 2 hands Veo a different image. The regen is best-effort: if it fails,
the plain retry still happens. Failure text (run state, stderr, the Slack
heads-up, the completion summary) now names the refused beats, so "reel clips
failed (exit 1)" no longer means a trip to the Actions log to learn which of
the four it was.

**Verified:** 18 assertions across three stubbed suites — no Veo, Gemini,
OpenAI, ffmpeg or Slack touched. `make_stills --only` (regen one beat, several
beats, anchor preserved, bare `--force` unchanged, no-flags resume unchanged,
missing anchor still generated, unknown key rejected); `make_clips` failures
file (RAI-refused beat recorded + exit 1, clean pass records `[]`, stale file
cleared on the all-present early return); `stage_reel` (happy path byte-for-byte
unchanged, refused beat → regen → retry delivers, permanent refusal → no
delivery + alert naming the beat, non-clip failure → plain retry with no
invented regen, failed regen doesn't consume the retry, delivery still gets
exactly one attempt, `--skip-hubspot` and `SPOTLIGHT_REEL=0` unchanged, and
`_failed_clip_keys` tolerating junk/missing input).

**NOT verified against Amelia's bundle, and Amelia's reel is still not
delivered.** Same wall as the two entries below: the bundle is a CI artifact,
not a checkout, and rendering needs Gemini/OpenAI/Slack credentials this session
does not have. This change makes the *next* run able to recover itself; it does
not retroactively produce the reel Paola has now asked for three times.

**Left undone deliberately — and this is now the blocking item.** Producing
Amelia's reel needs a runnable surface, and there still isn't one: PR #100
(`--reel-only`) is open and unmerged, and there is no `rerender-reel` Actions
workflow to match `rerender-textstory` (which is how the textstory stage has
always been recoverable — download the artifact, re-run one builder, in CI where
the keys and ffmpeg live). This session was scoped out of `.github/workflows/`
and `registry.yml`, as the last two were. Three corrections have now been closed
with code while the deliverable stayed undelivered; the next one should merge
#100 and add the workflow rather than add more orchestrator logic. The reel
scripts are also still missing from the registry's `depends_on` for
`spotlight-orchestrator`.

**Files:** `marketing/scripts/b2c/spotlight_orchestrator.py`,
`marketing/scripts/b2c/reel/make_stills.py`,
`marketing/scripts/b2c/reel/make_clips.py`.

---
## 2026-08-20 — Spotlight Orchestrator: a missing reel is no longer a silent miss

**Reported:** Paola — the case study for Amelia arrived in
#student-spotlight-ready with the blog, graphics and text-stories, but no
superhero reel, and nothing said one had been attempted.

**Diagnosis (correcting the filed one):** the reel IS wired into the
orchestrator — `stage_reel` sits in `STAGE_ORDER`/`STAGE_DISPATCH` between
`slack` and `textstory`, and the workflow installs ffmpeg for it. The reel
scripts missing from the registry's `depends_on` is a documentation gap, not
the cause. The real defect is that the stage has no failure signal at all:
`stage_reel` caught every exception, wrote `reel_status` into
`marketing/state/spotlight-runs.json` (gitignored — it does not survive the CI
job), printed to stderr, and exited 0 under a "SPOTLIGHT ORCHESTRATION
COMPLETE" banner that never mentioned the reel. The neighbouring textstory
stage already solved exactly this with a SLACK_FAILURE_CHANNEL heads-up; the
reel stage was never given one. On top of that a single flaky Veo beat killed
the whole reel with no retry, and `make_clips.py` polls Veo with no ceiling of
its own, so a stuck generation could burn the job's 30-minute timeout and take
the later stages down with it.

**Why it matters:** the reel is the only asset in the pack whose absence is
invisible. Every other piece either lands in the thread or fails the run. A
bonus asset being non-fatal is right; being unobservable is not — the miss
surfaces only when a human notices the gap days later, which is exactly how
this was found.

**Fix:** in `stage_reel` — one retry of the generation steps (all of them are
resumable, so the retry only regenerates what failed); a shared wall-clock
budget, `SPOTLIGHT_REEL_TIMEOUT_S` (default 900s), so the stage cannot eat the
job; delivery kept to a single attempt and budgeted separately so a retry can
never double-post into Paola's review thread; and a Slack heads-up on failure
via the same channel the textstory stage uses. `stage_complete` now prints the
reel status. The textstory alert was refactored onto the shared
`_post_stage_alert` helper with its message unchanged.

**Verified:** seven stubbed scenarios against `stage_reel` (happy path, flaky
step rescued by the resumable retry, hard failure, hang past the budget,
delivery failure, `--skip-hubspot`, no failure channel configured) — no APIs,
Slack or ffmpeg touched. Textstory alert text confirmed byte-identical.

**NOT verified against Amelia's bundle.** Bundles are gitignored and built in
CI (30-day Actions artifact), and re-running the reel needs Gemini/OpenAI/Slack
credentials, so the approved plan's steps 1–3 and 5 (locate the bundle, re-run
the pipeline standalone, diff against the last good reel, deliver to Paola)
cannot be done from the repo. They need a re-dispatch of Amelia's Drive folder.

**Left undone deliberately:** the reel scripts are still absent from the
registry's `depends_on` for `spotlight-orchestrator` — the session was scoped
out of `registry.yml`. Worth a one-line follow-up.

**Files:** `marketing/scripts/b2c/spotlight_orchestrator.py`.

---
## 2026-08-20 — Photo booth registered (39 agents, new Events engine)

**What:** `sage-oak-booth` is in `registry.yml` — the Cloudflare Worker + Pages
booth from PR #66, under a new `Events` engine. Written by reading `worker.js`
rather than the README, so the entry lists what it actually does: upserts the
HubSpot contact by email with the five events-group properties, applies a
CREATE-ONLY persona stamp by self-identified role (teacher → TOR persona + lead
status, administrator → Decision Maker, support_staff → none, existing contacts
never overwritten — po_inbox doctrine), logs an email engagement and a photo
note on the contact, sends the framed photo via Resend, and sends MMS from the
main A+ line via JustCall.

**Why now:** PR #66 merged mid-session and `registry_check.py` flagged
`booth/wrangler.toml` within a minute — the discovery heuristic added earlier
today doing exactly its job on a real merge rather than a simulated one.

**Two things recorded in the entry that are not in its README:**
- It is hand-deployed in TWO pieces (`wrangler deploy` + `wrangler pages
  deploy`); editing this repo makes neither live.
- **REVIEW ITEM for Roman:** `GET /photo/<key>` is public and unauthenticated —
  unguessable-key privacy only — and the archive copy is written with NO TTL, so
  attendee photos stay publicly retrievable indefinitely. Reasonable for MMS
  delivery, worth a deliberate decision for a school event.

**Also flagged:** status is `active`, but this is scoped to one event. When Sage
Oak BTSC 2026 is done it should go `unverified` or be retired rather than sit
`active` forever.

**Files:** `registry.yml`, `ops/fleet-health/fleet_brief.py` (Events in the
engine order), `docs/FLEET.md`, `docs/CHANGELOG.md`.

---

## 2026-08-25 — Booth Photo URL property (Summit follow-up sequence prep)

**What:** NEW contact property `aplus_booth_photo_url` ("[Agent] Booth Photo
URL", events group) — public URL of the contact's framed booth photo, the
personalization token for event follow-up emails (Danielle's Summit sequence).
Backfill for the 35 salvaged Summit photos + touch-email copy follow.

**Why:** Roman/Danielle 2026-08-23..25: teacher follow-up sequence runs
HubSpot-native; photo embed needs a per-contact public URL token.

**Files:** `ops/hubspot-schema/properties.yml`,
`ops/hubspot-schema/consolidation/KEEPERS.md` (81→82).

---

## 2026-08-23 — PO texts ask for the schedule when the PO doesn't state one

**What:** When a PO has no schedule and Teachworks has none either,
`schedule_preferences` is now stamped with a general ask (new config
`po_inbox.schedule_ask_fallback`, worded to follow the SMS template's
"...still works for you:" colon in workflow 1603217415) so the confirmation
text asks the family for their schedule instead of trailing off blank. The
old ⚠️ "set the schedule manually" note becomes an ℹ️ ticket note that does
NOT trip the 🚩 gap DM — nothing manual remains. Suite 247 green.

**Why:** Roman 2026-08-22: "If the schedule is not included in the purchase
order, we need to include just a general phrase of please provide us your
schedule. and that will get auto texted."

**Files:** `email/src/po_inbox.py`, `email/config.yaml`,
`email/tests/test_po_inbox.py` (blank-schedule test reworked + default test).

---

## 2026-08-20 — Feedback agent: the pinned channel post is not a report

**What:** Intake now drops "channel furniture" before classification. A
top-level message matching ≥2 distinct phrases from the pinned how-to-use post
(`intake.ignore.meta_markers` in `ops/feedback-agent/config.yml`) is logged and
skipped — nothing filed, no thread reply, marked processed so Slack retries
don't re-run it. A companion `intake.ignore.sender_app_ids` knob ignores posts
by a given Slack app/workflow; it ships EMPTY on purpose (below). Also withdrew
the mis-filed report from `state/state.json` so Friday's digest doesn't count
it against the feedback agent.

**Why:** Roman posted the channel's own pinned explainer into the channel on
2026-08-20 and the classifier filed it as an IDEA against the feedback agent
(thread 1787258667.896529). The post is written by a human into the channel, so
it carries no `bot_id` and the relay forwards it like any report; the classifier
then did its job on text that describes every agent in the fleet.

**Correction to the approved plan:** the plan proposed ignoring sender
`U0AKFN28V1U` ("the Slack workflow bot at the bottom is the giveaway"). It
isn't one — that ID is the "*Sent using* <@…>" attribution Roman's client
appends to everything he types, including real reports (content-build carousel
overflow 2026-08-04, call-agent exit code 2026-08-20) and his `status` queries.
Ignoring it would have silently swallowed every report Roman files. The knob
exists, documented, empty.

**Files:** `ops/feedback-agent/feedback_agent.py`,
`ops/feedback-agent/config.yml`, `ops/feedback-agent/README.md`,
`ops/feedback-agent/state/state.json`,
`ops/feedback-agent/tests/test_meta_posts.py` (new, 7 tests green).

---
## 2026-08-20 — Screenshot relay: fix shipped, problem NOT closed

**What:** Stopped debugging and wrote the state down. The relay's subtype filter
fix is deployed (Apps Script Version 3, 2:14 PM PT) but screenshots STILL do not
reach the agent: a screenshot posted at 2:15:57 PM produced no dispatch, while a
plain-text reply 35 seconds earlier did. Necessary but not sufficient. Logged as
an open weak point plus a TODO in `ARCHITECTURE.md` carrying the next diagnostic
step (Apps Script -> Executions at 2:15:57; present = script bug, absent = Slack
app config, most likely a missing `files:read` bot scope requiring a reinstall).

**Also:** posted a correction into the pinned #agent-feedback thread. The pin
told the team screenshots were fixed. They are not, and leaving that standing
would have kept people posting reports into a void believing they had landed.
The correction names Danielle's three lost reports explicitly — she has been
reporting the same bug since Aug 13 and getting silence — and gives the
workaround: report in text, attach the screenshot as a thread reply afterwards.

**Roman should edit the pinned message itself** (it was posted under his
account, and the API cannot edit it) to strike the "Screenshots are welcome /
Fixed now" paragraph.

**Rule going in:** do not announce this fixed again without a passing test. It
was announced once already on a fix that was real but incomplete.

**Files:** `ARCHITECTURE.md`, `docs/CHANGELOG.md`.

---

## 2026-08-20 — Approve + merge opened to Danielle, Paola and Emily

**What:** Split `slack.approvers` out of `slack.alerts_to`. `alerts_to` still
controls who gets @-pinged (Roman only — pinging four people on every proposal
trains everyone to ignore pings); `approvers` controls who may fire the coding
agent and squash-merge its PR from a thread reply. Set to Roman, Danielle, Paola,
Emily. Falls back to `alerts_to` when unset, so older configs are unaffected.
The proposal message now names who can act, reporter first.

**Why:** Roman 2026-08-20 — "i want it that danielle or paola or emily could do
the approve and merges." The case it unlocks: whoever reports a problem can ship
its fix. Paola reports the missing reel, Paola approves, Paola merges — no round
trip through Roman for work she is closest to. An unnamed permission is one
nobody uses, hence naming the approvers in the message itself.

**Not delegated:** DEMOTE registry flips stay with Roman until a Fleet Manager
exists to verify state changes (#AP011).

**Also:** posted a pinned explainer to #agent-feedback covering how to report,
the approve/merge/no vocabulary, that screenshots now work, the FERPA rule, and
what to do when the agent stays silent.

**Files:** `ops/feedback-agent/config.yml`, `ops/feedback-agent/feedback_agent.py`,
`docs/CHANGELOG.md`.

---

## 2026-08-20 — Feedback agent: schema debris no longer reaches HubSpot ticket subjects

**What:** The classifier's free-text fields are now scrubbed of leaked schema
fragments, the classification retries once when debris appears, and the ticket
subject truncates on a word boundary instead of mid-token.

**Why:** Caught live on Paola's spotlight report. Structured output is
schema-constrained and `json.loads` parsed it fine — but the model lost the thread
mid-field and wrote schema INTO a value:

    summary = "...the other assets rendered successfully.','clarifying_question':"

That summary flowed unvalidated into `subject: f"[AGENT] {label}: {summary[:120]}"`,
so the drafted HubSpot ticket read `...successfully.','clari` — a corrupted subject
line on a ticket the whole team sees.

**How:** `scrub_debris()` cuts any trailing `'...','field':` fragment out of
summary / ack_message / clarifying_question and reports which fields were dirty;
one retry (degraded output rarely repeats), then ship the scrubbed value rather
than fail — a slightly clipped summary still reaches a human, a crash does not.
`truncate_words()` replaces the raw `[:120]` slice. Verified against the real
failure plus false-positive guards: legitimate apostrophes ("Danielle's op-ed")
and colons ("Ratio is 3:1") are untouched.

**Files:** `ops/feedback-agent/feedback_agent.py`, `docs/CHANGELOG.md`.

---

## 2026-08-20 — INCIDENT: every #agent-feedback report with a screenshot was silently dropped

**What:** The Slack relay dropped any message carrying a file. Slack tags an
attachment-bearing message `subtype: "file_share"`, and the relay's filter was a
bare `if (ev.subtype) return textOut_('ok')` — written to drop edits, deletes and
joins. The relay answers Slack `ok`, so there was no error, no retry, and no
Actions run. The report simply evaporated, and from the reporter's side the agent
had ignored them.

**Evidence (100% correlation across the visible channel history):** reports WITH
a screenshot — Danielle Aug 13, Aug 17, Aug 18; Paola Aug 20 — got no agent reply
at all. Reports WITHOUT one — Paola Aug 14, Roman Aug 20 09:21, the Aug 20 13:11
test — were all answered within a minute.

**Why it matters more than the count suggests:** people attach a screenshot
exactly when a problem is visual and hard to put in words, so this ate the most
careful reports. Danielle reported the LinkedIn op-ed being cut off THREE times
(Aug 13/17/18), each with a screenshot, each into a void — while the one report
of hers that did land (Aug 11) had its fix run die on the claude-code-action bot
guard. She has never once seen this loop work.

**Fix:** allow `file_share` and `thread_broadcast` through; keep dropping edits,
deletes, joins and bot messages. A file-only post (screenshot, no words) now
falls back to the file title instead of being dropped for having no text. The
dispatch payload carries `has_files` so the agent can ask what the screenshot
shows rather than guess — it classifies from text and does not read images.
Filter verified against seven event shapes; the script parses.

**NOT LIVE YET.** This is an Apps Script: it deploys by hand from the Apps Script
UI, and editing the file in this repo changes nothing until someone pastes it in.
That deploy is Roman's. (Exactly the hazard the `runtime:` field added earlier
today exists to make visible.)

**Files:** `ops/feedback-agent/relay/apps-script.gs`, `docs/CHANGELOG.md`.

---
## 2026-08-20 — Call agent: a 100%-failure run now exits 1

**What:** `ops/call_agent/call_agent.py` counts outcomes around the per-call loop
(attempted / succeeded / skipped / failed) and, when at least one call raised and
none succeeded, logs `RUN FAILED — 0/N calls succeeded`, posts a one-line alert to
`slack.alert_channel` (the private #calls channel), and `sys.exit(1)`. The digest
still posts and state is still saved first, so the failing run reports what it saw
and stays idempotent. New `ops/call_agent/tests/test_exit_code.py` covers it.

**Why:** Reported as a correction — process_call exceptions are caught per call so
one bad call can't kill the run, but nothing tracked whether ANY call succeeded, so
a run that failed every call exited 0 and the Actions retry sweeper stayed silent.
Total failure was indistinguishable from a quiet day.

**Scope note (differs slightly from the approved plan):** the approved condition was
`attempted > 0 and succeeded == 0`. That would fire on a day where every call was
legitimately skipped — hang-up, no recording, no transcript are normal outcomes, and
an all-hang-ups afternoon is common. The condition shipped is `failed > 0 and
succeeded == 0`, which is the reported failure mode without the false alarm.

**Known gap (not fixed here):** failed calls are still marked processed, so a
sweeper retry of the same window is a no-op. The nonzero exit is a signal to a human,
not yet a self-healing retry. Worth a follow-up decision on whether failures should
stay off the processed list.

**Files:** `ops/call_agent/call_agent.py`, `ops/call_agent/tests/test_exit_code.py`,
`docs/CHANGELOG.md`.

---
## 2026-08-20 — `runtime:` — the fleet is not all GitHub Actions

**What:** Added a required `runtime:` field (`github-actions` | `cloudflare-worker`
| `apps-script` | `zapier`) plus `source:` for non-Actions agents, registered the
two Google Apps Scripts that were previously named only as the `source:` of other
entries (`spotlight-drive-watcher`, `feedback-slack-relay`), and taught
`registry_check.py` to DISCOVER non-Actions agents rather than only validate
declared ones — `wrangler.toml` means a Worker, `*.gs` means an Apps Script, and
anything unreferenced by the registry is flagged. FLEET.md now prints the runtime
when it is not the default and warns that those agents deploy by hand.

**Why:** Roman asked why the photo booth agents were not in the handoff. Three
reasons, worst last: it is on the unmerged `booth-backend` branch (PR #66 open,
22 commits); it is a Cloudflare Worker + Pages app, which the registry's
workflow-shaped schema could not express; and **registry_check.py structurally
could not have caught it** — it compared registry.yml against
`.github/workflows/` only, so Workers, Apps Scripts, and Zapier zaps were an
invisible class. The booth writes four contact properties to production HubSpot,
emails via Resend, and sends MMS from the main A+ line.

**Bug found while testing:** sibling-directory coverage was too loose — the
spotlight watcher's `.gs` was masked by `download-drive-folder.py` in the same
directory, so deleting its registry entry did NOT trip the check. Sibling
coverage is now per-pattern: on for `wrangler.toml` (config beside a named
worker script), off for `*.gs` (the script IS the agent). Both discovery paths
verified by removing entries and confirming the flag fires.

**Still unregistered:** the Sage Oak photo booth itself. Its code is not on main,
and another session is actively working that branch — the entry should land with
PR #66. Once merged, the new discovery heuristic will flag it if it does not.

**Files:** `registry.yml` (runtime on 38 entries + 2 new Apps Script agents),
`ops/fleet-health/registry_check.py`, `ops/fleet-health/fleet_brief.py`,
`docs/FLEET.md`, `docs/CHANGELOG.md`.

---

## 2026-08-20 — Prevention: generated FLEET.md, an enforced registry, an exit-code rule

**What:** Three mechanisms, in the order Roman picked (3, 1, 2).

1. **`docs/FLEET.md` is now generated** from `registry.yml` by
   `ops/fleet-health/fleet_brief.py`, regenerated on every merge to main.
   Grouped by engine, with an autonomy section and per-agent reads/writes.
   Handing the fleet to Claude-in-chat is now "copy one file" instead of a
   hand-written summary that is stale on arrival. Required a new `engine:`
   field on all 36 registry entries (inferring it from entrypoint paths breaks
   on cases like tw-invoice-xref, which lives in email/ but is a charter tool).
2. **`ops/fleet-health/registry_check.py`** enforces the registry's own first
   rule: workflows <-> registry both directions, required fields, unique ids,
   entrypoints exist, FLEET.md current. Wired up as the `fleet-docs` workflow —
   which had to register itself to pass its own check. ROLLOUT: PRs run with
   `--warn` (annotate, don't block); drop the flag in a couple of weeks.
3. **Exit-code rule** added to ARCHITECTURE.md governance: an agent that
   accomplished NONE of its work must exit non-zero. Deliberately narrow — a
   sweeping "any failure exits non-zero" would break call-agent's per-call
   isolation, which is correct design. 0 of 50 is a failed run; 49 of 50 is a
   warning. Three agents still need the change: campaign-launch (enroll.py),
   bulk-messenger (messenger.py), call-agent (all-calls-failed case only).

**Why:** Roman — "we do it in code, but then claude chat doesnt know about it and
neither does github, and i always feel like we are back asswards." The diagnosis:
these mechanisms already existed as CONVENTIONS (register everything, update the
changelog) and conventions decay silently. Nine workflows broke the registration
rule for weeks; ARCHITECTURE.md was wrong for seven. Nothing was watching, and
nothing published what the repo already knew.

**Files:** `ops/fleet-health/fleet_brief.py` (new),
`ops/fleet-health/registry_check.py` (new), `.github/workflows/fleet-docs.yml`
(new), `docs/FLEET.md` (new, generated), `registry.yml` (engine field on 36
entries + the fleet-docs entry), `ARCHITECTURE.md`, `docs/CHANGELOG.md`.

**Decision-log candidates for Roman:** (a) generated fleet breakdown as the
canonical handoff artifact; (b) registry check blocking merges after rollout;
(c) the exit-code rule as a fleet-wide convention.

---

## 2026-08-20 — ARCHITECTURE.md rewritten to match the fleet as it actually is

**What:** The human-readable fleet map described four engines with email in a
separate repo — the world as of ~2026-06. Rewritten for the real eight: added
the call agent, feedback agent, messenger, and fleet-health; folded email in;
replaced the finished migration history with an **Autonomy** section (what
writes without asking vs. what only drafts) and a **Known weak points** section.
Added the rule that `registry.yml` wins on conflict.

**Why:** Roman — it was the last fleet doc still wrong after the registry pass,
and it is the file a human reads first.

**Note:** this entry was written when the rewrite was committed (231ab2d) but
silently failed to land — the insert matched on surrounding prose, which a
concurrent session had just changed, so the no-op reported success. Restored
here, and the insert is now anchored on structure. A small live instance of the
exact failure mode the entry above is about.

---


## 2026-08-20 — Charter campaign: wave 2 sent, all segments built, Paola hot list

**What:** (1) WAVE 2 SENT: 213 more Win-back-1-student families through live
workflow 1868435042 (Roman "lets move on to the next list") — campaign total
259 emailed; 11 prior-repliers held back (reply-date exit goal would silently
skip them), 27 excluded, 2 enrollment-blocked (Aquaddoomi, DaVault → Paola
calls). Weekday-only action windows (Mon–Fri 9:00–18:00 PT) set on the live
workflow — wave-2's Day-3 nudge moved off Sunday. (2) PILOT LEARNINGS baked
in: lead-status=OPEN_DEAL exit goal removed (34 families carried stale
Open-deal status from 25/26 and were silently skipped — root cause of the
13/47 partial send); reply exit = hs_email_last_reply_date IS_KNOWN (UI-valid
shape; the API accepted an IS_AFTER timePoint the UI rendered "always
False"). Both live-verified: Surova + Potter replies exited them. (3) ALL
REMAINING SEGMENTS BUILT (OFF, pending Roman publish+enable — marketing-email
publish scope unavailable at account tier): queues 3162 Never-Started (28),
3163 No-Lesson (10), 3164 Multi (71); emails 219949380453 / 219949261351 /
219949261355 / 219949261359 / 219949380457; workflows 1869922921 / 1869934421 /
1869933870 (same goal trio, weekday windows, Paola Day-7 task). Multi
student_names scrubbed: Munoz "Alanna/Alannah" deduped; White (Yari/Yuri)
+ Lopez (Mathew/Matthew) HELD for Roman (twins vs typo — not queued). (4)
PAOLA HOT LIST 3161 (55) Slack-DM'd to Paola: T1 replied (Surova asked for
Fred/Vlado; Potter), T2 opened (30, revenue-ranked), T3 Hot-12 never emailed
(personal calls), T4 email-unreachable (7). Behavior at 48h: 46 sent /
18 opened (39%) / 2 replied / both repliers auto-exited before the nudge.
**Files:** portal-side builds; durable scripts already in scripts/. Session
worktree was reset mid-flight — recreated per concurrency rule before this
commit.

## 2026-08-20 — registry.yml: the 9 unregistered workflows are now registered

**What:** Added registry entries for every live workflow that was running
without one — `email-po-daily-report`, `email-draft-feedback`, `feedback-fix`,
`campaign-launch` (monday-launch.yml), and the five manual charter/Teachworks
analysis tools (`charter-gap-analysis`, `tw-tutor-active-check`,
`tw-invoice-status`, `tw-invoice-xref`, `tw-invoice-backfill`). The charter
section's "NOT BUILT" note is kept — the prospecting ENGINE still doesn't
exist — with a new paragraph distinguishing it from the manual read-only
analysis tools that do. Registry is now 35 agents (22 active, 10 manual,
3 deprecated) and `.github/workflows/` ⇄ `registry.yml` cross-check is clean
in both directions.

**Why:** Roman, reviewing a fleet breakdown: the registry's own first rule is
"if it's not here, it doesn't exist," and the feedback agent classifies every
`#agent-feedback` report against this file's vocabulary. Nine live workflows —
including two that write to HubSpot and one that opens PRs — were invisible to
that vocabulary, so nobody could report a problem against them and the DEMOTE
path had no target to flip.

**Follow-up:** `source_agent` and `ticket_source` derive their enum options
from this file (`options_from: registry`), so the HubSpot schema sync
(`.github/workflows/hubspot-schema.yml`) needs a run to pick up the 9 new
options. Not run in this session — portal writes are Roman's call.

**Files:** `registry.yml`, `docs/CHANGELOG.md`.

---

## 2026-08-18 — Parent resolution step 2: the student in Teachworks (Roman: "build")

**What:** New tw.find_family_by_student(): searches both TW accounts for the
PO's student by exact name, scores candidates by real lesson history (+100 when
the PO's tutor is their last tutor; 0-lesson shells never count), returns the
family (parent name/email/phone, last tutor, lesson count). Wired into
po_inbox parent resolution as STEP 2 — after "parent email in the PO", BEFORE
prior deals and the surname search — with the extractor now pulling
`tutor_name` off the PO. Internal-domain families skipped; tutor mismatch adds
a "verify same student" flag. Matthew Rose (iLEAD, 3 POs) resolved this way
by hand today: TW showed Megan Miller's Matthew with 104 lessons, all with
Jacquelyn Lemerond — the tutor on the new PO — while the "Dina Rose / Matthew"
record had 0 lessons (a 2022 Gold-pipeline shell). Deals renamed "Megan Miller
- Matthew Rose - iLead 1/2/3 - 26/27", Megan attached + stamped, family→TOR
(Sara Ramirez), SMS armed, chases closed. Also: tw_student_lookup.py + xref
workflow input for ad-hoc "have we ever tutored X?" checks (shows last tutor).

**Why:** Roman: "matthew rose can be found in teachworks, to eliminate if we
ever tutored him before… cross reference who the last teacher [tutor] was for
both of the matthews and you will know" → "build".

**Files:** `email/src/teachworks_client.py`, `email/src/po_inbox.py`,
`email/tw_student_lookup.py` (new), `.github/workflows/tw-invoice-xref.yml`,
`email/tests/test_po_inbox.py` (suite 246 green), `docs/PO-PROCESS.md`.

## 2026-08-18 — Week audit + wrong-family fix (Matthew Rose) + South Sutter errant PO

**What:** Week-of-Aug-10 PO audit (16 emails → 43 deals, $9.8k, 72% same-day
TW-invoiced). Roman caught: (1) Matthew Rose (iLEAD, 3 POs) attached to
"Dina Rose" — a 2022 contact with the same surname and no student data. Root
cause: find_family_contact() returned a LONE surname match without ever
checking the student name (the same-surname tiebreak only ran on 2+ matches).
Fixed: a single surname match is accepted only when the contact's student-name
props or an associated deal name carry the student's first name; else [] →
the parent chase runs. Deals detached from Dina, renamed NEEDS PARENT, parent
stamps cleared; PO replayed so the agent re-chases via TOR Sara Ramirez.
(2) South Sutter/IEM PO 1309153 ($3,010, 3 students, "submitted 4/3/2025") is
a stale 2025 errant — 3 deals ARCHIVED (Roman). Also fixed during audit: Seeley
×5 amounts → reissued $75/hr ($637.50; Kath caught the old-rate PO, Christine
Gurney reissued Aug 18); Heartland ×5 stale parent_email from the Pilibos
incident corrected; Kruz Invoice # tab char cleaned. Open for Kath: confirm
Seeley TW invoices 54435–439 at new amounts; Cooper Doyal Invoice # 54422 not
found under Kristy's TW record.

**Files:** `email/src/hubspot_client.py`, `email/tests/{test_family_contact,
test_po_inbox}.py` (suite 242 green).

## 2026-08-17 — Draft feedback loop (Tiers 1+2) — the team's edits train the drafter

**What:** New `email/src/draft_feedback.py`. Tier 1: every agent-created draft
(chase + reply, charter@ inbox) is registered with its exact text
(state/draft_registry.jsonl); each 15-min run settles drafts that left Gmail
Drafts by comparing to what was actually SENT on the thread — sent_as_is (≥97%
similar) / edited (≥50%) / rewritten / discarded — flips the sent message to
`A+ Agent/Sent`, and stores the unified diff. Tier 2: edits/rewrites/discards
become one file each in `corrections/email-drafts/` (fleet corrections format)
plus a distilled line in `STYLE-RULES.md`, which BOTH drafting prompts (PO
extractor + admin classifier) load at runtime (last 25 rules) — tomorrow's
drafts carry yesterday's edits. Weekly Friday 4 PM PT one-liner to the
visionary seat (new email-draft-feedback-weekly.yml). Tier 3 unchanged: a reply
to the aplus bot in #agent-feedback files a rule via the feedback agent.
Admin-inbox drafts (HubSpot conversation comments) consume the rules but
aren't outcome-tracked yet — different plumbing, follow-up.

**Why:** Roman: "is there a way for the agent to get input from kath and from
all others when drafts are made whether the draft was good or needs
improvement" → "LETS DO IT".

**Files:** `email/src/draft_feedback.py` (new), `email/src/po_inbox.py`,
`email/src/classifier.py`, `email/tests/test_draft_feedback.py` (new; suite
239 green), `.github/workflows/{email-po-inbox,email-draft-feedback-weekly}.yml`,
`corrections/email-drafts/README.md` (new).

## 2026-08-17 — INCIDENT: chase self-resolve renamed 5 Heartland deals to "Pilibos Student"

**What:** Roman: "how come heartland deals were named pilibos?" Property
history: integration 39943154 (our app) at 2026-08-14 19:35Z — the po_inbox
`_sweep_chase_self_resolve` shipped that day. Root cause: the Heartland chases
were opened BEFORE the multi-student fix, so their audit records carried the
placeholder student "the student"; the sweep searched family contacts for it,
found exactly one match — Roman's TEST contact "Pilibos Student"
(roman+001@wetutorathome.com) — and "resolved" all five chases against deals
Kath had already fixed by hand: renamed them from the audit's STALE
"NEEDS PARENT - Heartland N" to "Pilibos Student - Heartland N" and attached
the test contact. Repaired in-portal: five names restored (Kristy Doyal /
Angela Czaja ×3 / Jamie Holloway), test contact detached from all five (real
parents untouched). Code guards: (1) placeholder student strings never
searched; (2) the deal must STILL say NEEDS PARENT in the LIVE portal (human-
fixed deals just close their chase, touching nothing); (3) internal-domain
(@wetutorathome.com) contacts never auto-attached; (4) resolution renames
from the LIVE deal name, never the audit copy. 4 regression tests.

**Why:** Wrote automation that trusted its own stale bookkeeping over the
portal and treated a placeholder as data. Both fixed at the root.

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py`
(suite 231 green).

---

## 2026-08-17 — Charter Monday launch: 6-way family segmentation + student names (Roman)

**What:** Roman: "split list as segmented as you can make them" (after
catching that 1-student copy undersold multi-student families — 81 of 389).
New `scripts/charter_gap_segments.py`: derives EVERY student per family from
charter deal titles since 2025-08-01, stamps NEW contact props `student_names`
("Brooke, Haven & Lillie") + `student_count` ([Agent]-labeled, registry +2,
UPDATE-only import — 419 stamped), and builds 6 static lists = recency ×
student-count × personalization: 3138 Hot-1 (9), 3140 Hot-Multi (3),
3136 Win-back-1 (299), 3135 Win-back-Multi (78), 3137 Never Started (30),
3139 No Lesson Data (10) — sums to the 429 gap families. campaign.yml
re-wired to the six (2-way lists 3112/3113 superseded, kept). New copy
drafts: families_winback_multi / families_hot_multi / families_no_lesson_data
(multi variants use {{student_names}} and "their tutors" — no single-tutor
token, since siblings often had different tutors). Still DISARMED.
**Files:** scripts/charter_gap_segments.py (new), ops/hubspot-schema/
properties.yml, ops/messenger/campaign.yml, ops/messenger/templates/
campaign-2026-08-17/ (+3).

---

## 2026-08-17 — Lead status: unhidden, funnel-ordered, persona-labeled + Meeting Booked hard-wired

**What:** (1) `hs_lead_status` had 14 of 17 options HIDDEN (unknown when/who —
property updatedAt stale at 2024-09). Roman: "I don't want anything hidden" →
all 17 unhidden (backup `ops/fleet-health/audit/backups/2026-08-11-hs_lead_
status-before-unhide.json`). (2) Options reordered to the funnel Roman
described: New (Inbox) → Attempting to Contact → Meeting Booked → QTL-NEW /
QTL-Charter / QTL-Diagnostic Sent → Open deal → Past Customer / Check Back
Quarterly / Dead Opportunity; then the persona labels; then leftovers.
(3) LOCKED rule (Roman): for non-family personas the lead-status LABEL = the
persona name. Two label renames (internal values unchanged, so no workflow or
agent breaks): `Charter School Teacher TOR/EF` → label "Teacher of Record/EF/ES";
`Teacher in a School` ("School Personnel") → label "Decision Maker/Director".
Call agent LEAD_STATUS_LABELS + README updated. (4) Meeting Booked was a manual
gap (Paola set it by hand; nurtures kept chasing booked families) → NEW
event-based workflow 1868302723 "Lead funnel — Meeting Booked (Paola consult)
→ lead status": trigger = HubSpot meeting booked with title containing
"Tutoring Call w/" (Paola's meetings-link consults; excludes Spotlight/TSN
meetings), sets hs_lead_status = Meeting Booked; ENABLED. Cloned from the
Spotlight #5 pattern. (5) Nurture exit: added a second OR-goal
"lead status = Meeting Booked" to `Lead Pipe Line - Online` (50818589) so
booked families drop out of the New/Attempting chase. The same goal edit on
`Lead Pipe Line - Ads - Free Lesson` (149937308) FAILED via API (500 on
round-trip PUT — custom-code actions) → flow untouched, **needs a 30-second UI
edit: Settings → Goal → add "Lead status is any of Meeting Booked"**.

**Why:** Roman 2026-08-17 walkthrough of the funnel: form → New + text/email
push to book → Attempting to Contact + "inbox is full" email → Meeting Booked
(Paola's new manual step) → QTL after consult. Also surfaced: 10,064 of 11,115
contacts have NO a_persona; lead status is doing identity duty for them
(Tutors 1,249 / Student 191 / School Personnel 97 / CBQ 4,453 = families).
Persona backfill-from-status proposed, NOT run — Roman to approve. 25 Decision
Makers still carry the TOR status value — pending Roman's call.

**Files:** `ops/call_agent/call_agent.py`, `ops/call_agent/README.md`,
`ops/fleet-health/audit/backups/2026-08-17-*` (flow snapshots + created flow).

---

## 2026-08-14 — Agent-property labeling rule + TOR/DM hygiene (Roman)

**What:** (1) NEW RULE: every property an agent writes carries the `[Agent] `
label prefix + "AGENT PROPERTY — written by <script>" description (CLAUDE.md
+ registry header comment). Applied: last_tutor_name, student_first_name,
sms_opt_out relabeled in-portal (sync never relabels) and in properties.yml.
(2) TOR persona hygiene: 77 non-marketing TOR contacts set as marketing via
import; **155 hard-bounced TOR contacts ARCHIVED** (backup with associations
in ops/fleet-health/audit/backups/2026-08-14-bounced-tors/; recycle-bin
90 days); one bounced contact kept — Cynthia Rachel (IEM) — because she is
now a Decision Maker (needs a fresh email). (3) Decision Maker/Director
persona: 17 real school DMs now tagged — Covil, Hetrick, Rachel (IEM);
Chapin, Budke, Barlow, Joy, Kim, Rogers (iLEAD); Smith (Compass), Jorgensen
(Elite), Brackett (Forest), Sutton (Harvest Ridge), Corioso (Pacific
Coast), King (Sage Oak), Woodard (Taylion), Houchin (VIEDU). Title-based
sweep deliberately EXCLUDED 38 non-school "directors" (vendors, media).
Pending Roman: 5 Sage Oak mock contacts (nameless 2026-03-24 records +
Courtney Gibson) to delete — the other 28 Sage Oak contacts are real TORs
with live deals; DMs still missing for Compass/Heartland/Gorman/Blue Ridge/
Pacific Charters/Granite Mountain/Heartwood/Suncoast.
**Also flagged for Monday copy:** 81/389 personalized gap families have >1
student in last year's deals — one-student template undersells them
(decision pending: split list vs multi-student variant).
**Files:** CLAUDE.md, ops/hubspot-schema/properties.yml,
ops/fleet-health/audit/backups/2026-08-14-bounced-tors/.

---

## 2026-08-14 — Charter 26/27 launch scaffolding (Monday 08-17, DISARMED)

**What:** Segmented Monday-morning campaign per Roman ("families from charter
schools where we worked with them last year, and some where we didn't...
teachers who we worked with last year, or didn't"). 5 NEW static lists built
from gap list 3104 + Family→TOR associations (typeId 15): 3107 Families-Hot
(12), 3108 Families-Win-back (387), 3109 Families-Never-Started (30), 3110
TORs-Worked-With-Us (163), 3111 TORs-New-Outreach (8). 329/429 gap families
have a TOR association (100 without — hygiene queue candidate). Campaign
program: ops/messenger/CAMPAIGN-2026-08-17.md (cadence: Day 0 email, Day 3
follow-up, Day 7 CHARTER SALES task, goal-exit on renewal/reply); 5 copy
drafts in ops/messenger/templates/campaign-2026-08-17/ (HubSpot tokens;
never-started segment deliberately token-free). Launch rail:
ops/messenger/enroll.py + monday-launch.yml (daily 9 AM PT cron, exits unless
campaign.yml armed: true AND today == launch_date 2026-08-17; enrollment via
automation v2 per-contact endpoint). **DISARMED — blocked on Roman:** copy
approval, base branded email id (or "plain"), workflow build go (ids →
campaign.yml), armed flip.
**Files:** ops/messenger/{CAMPAIGN-2026-08-17.md,enroll.py,campaign.yml,
templates/campaign-2026-08-17/}, .github/workflows/monday-launch.yml.

---

## 2026-08-14 — EOS knowledge ingested from Monday (knowledge/eos/)

**What:** New `knowledge/eos/README.md` — synced snapshot of the FY2027 Annual
Goals (16k package hours / 900 students / 2 intervention programs / 75%
retention / 100% tutors scored / 70 referral families) and Q1 FY2027 Rocks by
seat, with Monday board ids (Goals 18419427040, Rocks 18421156386, L10
Scorecard 18402267902, L10 Agenda, Data Review Protocol) and usage guidance:
seats map to config roles:, work should cite the Rock/Goal it serves, the ops
scorecard sync feeds the L10 Scorecard, Monday stays source of truth.

**Why:** Roman: "do our agents have our EOS knowledge?" — they had none;
"check in monday.com you will find our goals for the year and our rocks."

**Files:** `knowledge/eos/README.md` (new).

---

## 2026-08-14 — NEW ENGINE: bulk messenger (on-demand email/SMS to lists)

**What:** `ops/messenger/` — on-demand bulk email + SMS to a HubSpot list,
per Roman's rail decisions: EMAIL via HubSpot marketing email (agent clones an
in-portal template, retargets the clone at the list, leaves it DRAFT with a
review link — Roman clicks Send, HubSpot suppression applies; personalization
via native contact tokens incl. student_first_name / last_tutor_name); SMS via
JustCall with from-number routing (sales +18185736644, conference
+18188506284), rendered per-contact from repo templates. Guardrails: BULK
ONLY (min_bulk 25, refuses 1:1), dry-run default + live requires
confirm=SEND, sms_opt_out contacts skipped (NEW contact property, group
master), STOP line required in every SMS template, 9:00–20:00 PT quiet hours,
E.164 normalization. Trigger: workflow_dispatch (messenger.yml); the Slack
front door + JustCall STOP-reply ingestion are phase 2 (README).
First template: templates/charter_win_back.txt (uses first-name-only
last_tutor_name). Registry: new `bulk-messenger` entry (status manual).
**WHY:** Roman 2026-08-14: "we need to have a programmed agent that can send
out custom email and text messaging to customers whenever called upon. only
for bulk options." Rail + trigger choices confirmed by Roman same day.
**Decision-log candidates (pending Roman):** bulk-only threshold (25); email
sends stay human-clicked in HubSpot for now; SMS number routing map.
**Files:** ops/messenger/{messenger.py,config.yml,README.md,templates/},
.github/workflows/messenger.yml, registry.yml, ops/hubspot-schema/properties.yml
(+sms_opt_out).

---
## 2026-08-14 — Accountability chart: roles resolve to people at config load (Roman)

**What:** New `roles:` block in email/config.yaml — the EOS-style seat map
(visionary/roman, operations/emily, scheduling_lead/mandy, scheduler_a_l/janelle,
scheduler_m_z/yolanda, charter_admin/kath, sales/danielle, charter_sales/paola).
Every functional key now names a SEAT (routing owners, scheduler_split,
escalation level2/3, recipients, cc, missing_info_dms, charter_sales, internal
fallback); cfg() resolves roles → staff keys at load time so all consumers and
tests keep seeing resolved people, and config.staff() resolves either form.
Hardcoded "paola" in main.py's pre-deal routing → charter_sales seat. Team
change = edit `roles:`, nothing else. Claude-to-Roman comms keep using NAMES
(memory rule). Seat titles are inferred from function — Roman to correct
against the real accountability chart.

**Why:** Roman: "lets give all team members a role title and that way its
never tied to anyones name... if a team member moves or leaves or gets added
i just have to add it for you."

**Files:** `email/config.yaml`, `email/src/config.py`, `email/src/main.py`,
`email/src/po_inbox.py`, `email/tests/{test_invoice_sweep,test_hourly_update,
test_po_inbox}.py` (suite 227 green).

## 2026-08-14 — Parent-chase: CHARTER SALES notified at 24h (Roman; role, not name)

**What:** Family contact info still missing 24 HOURS (calendar, configurable
`parent_chase.notify_charter_sales_after_hours`) after the chase email was
SENT → the CHARTER SALES role gets a DM to chase the TOR/school directly —
ahead of the existing Kath+Roman escalation at 2 business days. Once per chase
(parent_chase_sales_notified); unsent drafts never trigger it (the send is the
anchor). NEW RULE (Roman, same session): functional config keys and audit
actions name ROLES, never people — new `po_inbox.charter_sales: paola` role
map; change the person in config, never in code. First-pass person-named key
(notify_paola_after_hours / parent_chase_paola_notified) renamed same day,
legacy names still honored on read.

**Why:** Roman: "If a family is missing contact info for longer than 24 hours
after an email Paola must be notified too" + "make sure that no properties are
named after people. notify charter sales instead of paola."

**Files:** `email/src/po_inbox.py`, `email/config.yaml`,
`email/tests/test_po_inbox.py` (suite 227 green).

## 2026-08-14 — Draft guidelines: humans only, tracked, context-aware (Roman: "yes")

**What:** 14-day audit found 55 drafts/512 emails, 21 of them po_inbox warm
replies to vendor-admin mail nobody sends. Six-part fix, all live: (1) extractor
drafts ONLY when a named human asked A+ something — never for mass notices,
onboarding confirmations, DocuSign/portal notices, auto-acks. (2) Robot
recipients banned (`noreply/donotreply/notifications@/mailer.*`) for chase AND
reply drafts — no human to write to → 📨 gap note → 🚩 DM instead. (3) Chase
drafts to a TOR who wasn't the sender go out as FRESH emails ("Parent contact
info needed — Student (School)") — no more replies quoting portal robots;
chase records track the NEW thread so replies still auto-resolve. (4) Every
agent draft: Gmail label `A+ Agent/Draft Pending`, HubSpot BCC
(hubspot.bcc_log_address — verify on first real send) so sends log to contact
timelines; NEW _sweep_chase_drafts detects the draft leaving Drafts →
parent_chase_sent (TOR reply clock starts AT SEND, and unsent chases never
escalate the TOR) / still sitting after 4 business hours → 🚩 nag. (5) Call-
context check before chasing: recent [Call Agent] engagements on the TOR's
contact surface on the ticket ("a recent call may ALREADY have this info") and
add a P.S. to the draft — built after the Karen Mercer case (parent's name was
on her contact an hour before the chase drafted). (6) _sweep_chase_self_resolve:
open chases re-check HubSpot for a newly appeared family contact each run — the
August Vouniozos case (family called in; contact existed before anyone read a
reply) now closes itself. ALSO: Kruz Vouniozos chases resolved by hand via
call context (deals renamed to August Vouniozos, parent attached+stamped,
family→TOR to Karen Mercer, SMS armed); guidelines DM'd to Paola + Danielle.

**Why:** Roman: excessive drafts; noreply senders; "is it in any way possible
that this agent has already checked the transcript... from last call" — it
couldn't; now it does.

**Files:** `email/src/po_inbox.py`, `email/src/gmail_client.py`,
`email/src/hubspot_client.py`, `email/config.yaml`,
`email/tests/test_po_inbox.py` (suite 225 green).

## 2026-08-14 — PO improvement batch (Roman: "lets go") — 5 changes

**What:** (1) SMS flow 1603217415 rev 42: second OR-branch enrolls contacts
whose a_persona includes Family even when they also carry the TOR persona —
dual-role parents (Kristy Doyal) get their scheduling texts; pure teachers stay
blocked. (2) SLA sweep now tracks PO-inbox tickets (po_processed records carry
ticket_id + sla_due) — PO ticket breaches finally escalate (the silent Taylion
breach can't recur). (3) Chase-resolved parents get their SMS: on resolution
the agent stamps contact_level_deal_stage = "Pre-Lesson (Charter Traditional)"
on the new parent contact, arming the texting flow that fired at deal creation
when no parent existed (Charter Trad only). (4) Pending-approval sweep: order-
agreement deals log pending_po_opened; the duplicate alert (approved PO
re-arriving) logs pending_po_confirmed; unconfirmed past 16 business hours →
ONE ⏳ nag to missing_info_dms (kath+roman) + pending_po_reminded. (5) Multi-
student certificates codified (yesterday's Heartland run needed hand-cleanup):
extractor returns per-student pos[] entries (student/grade/parent per family,
synthesized '<PO>-<StudentName>' numbers), _split_pos merges them, seq numbers
per student, scheduling alert per student, and the parent chase sends ONE draft
per recipient listing all students (was 5 identical drafts to the same TOR)
with per-deal chase records; replies resolve the chases whose student they
name (multi-family threads), else all (single-family multi-month).

**Why:** Roman's approved batch, triggered by the Kristy Doyal dual-persona PO
and the Heartland 5-student certificate.

**Files:** `email/src/po_inbox.py`, `email/src/sla_sweep.py`,
`email/config.yaml`, `email/tests/test_po_inbox.py` (suite 219 green);
HubSpot flow 1603217415 rev 42.

---

## 2026-08-14 — Charter gap: tutor/student enrichment + property stamping (Roman)

**What:** `scripts/charter_gap_analysis.py` extended — Step 3b pulls each
matched gap family's most recent COMPLETED Teachworks lesson (per-customer
students → per-student lessons, the proven email-client query pattern, both
accounts) and captures tutor name + student first name; new Tab-1 columns
Last Tutor / Student First / Last Lesson; match rate printed. New OPT-IN
write stage (--write-props / workflow input write_props): stamps
`last_tutor_name` + `student_first_name` onto list-3104 gap contacts via an
UPDATE-only email-keyed import (crm.import scope — added by Roman 2026-08-13).
BOTH `last_tutor_name` and `student_first_name` newly declared as CONTACT
properties (group family) in ops/hubspot-schema/properties.yml. Registry trap
hit on the way: the pre-existing `student_first_name` at line ~407 is a DEAL
property (dealinformation) — the first declaration attempt landed in the
deals: section and created a stray empty deals/last_tutor_name (archived
immediately, no values ever written). The deal-level student_first_name is
untouched; the contact-level one is its counterpart.
**Duplicate-list flag for Roman:** the parallel session's run created static
list 3106 "Charter Re-Engagement 26/27 - Gap Families (Aug 2026)" (426
members, pre-correction cutoff). List 3104 (429, corrected cutoff) is
canonical per Roman's instructions; 3106 is a duplicate awaiting his
keep/delete call. **Also reconciles the script fork:** ece98a0 (parallel
session) had overwritten the executed PR-#68 version on main; this change
re-bases on the executed version and absorbs ece98a0's invoice-level name
fallback (customer_first_name/customer_last_name when the customer record is
missing). Base run stays read-only.
**WHY:** Roman 2026-08-14: win-back outreach personalization — "your student
X's tutor was Y" needs the last tutor on the contact record.
**Run results (2026-08-14, run 31769645948):** MATCH RATE 389/429 gap
families got a tutor name (91%) — every matched-with-invoices family that had
a completed lesson. Import 78996473 DONE; full verify: 389/429 list-3104
contacts carry BOTH last_tutor_name and student_first_name. The 40 without:
30 never-invoiced (no TW match) + 10 invoiced but no completed lesson in
window. Same-day follow-up (Roman: "tutors first name only no last names"):
last_tutor_name now holds the tutor's FIRST NAME only (parsed from
Teachworks "Last, First"); all 389 re-stamped.
**Files:** scripts/charter_gap_analysis.py,
.github/workflows/charter-gap-analysis.yml,
ops/hubspot-schema/properties.yml (+2 contact properties).

---

## 2026-08-13 — Charter re-engagement gap analysis + static list (Roman)

**What:** New reusable `scripts/charter_gap_analysis.py`: pulls charter deals
(5 pipelines, created since 2025-08-01) + associated contacts from HubSpot,
excludes school-staff email domains (student.* subdomains stay family),
classifies RENEWED (deal created ≥ 2026-06-01 OR "26/27" in dealname) vs GAP,
merges against Teachworks invoices (email match, name fallback), writes
`~/Desktop/charter_gap_analysis.xlsx` (4 tabs) + non-marketable CSV, and
creates HubSpot static list "Charter Re-Engagement 26/27 - Gap Families
(Aug 2026)" (id 3106, 426 members verified). Run results 2026-08-13:
439 families / 13 renewed / 426 gap — matched Roman's expected ~439/~11/~428.
TEACHWORKS_API_KEY only lives in Actions secrets, so a new manual workflow
`charter-gap-tw-fetch.yml` runs the read-only Teachworks fetch stage and hands
the JSON back as an artifact (`--fetch-teachworks` / `--tw-json` split).
One-off run, structured for weekly scheduling later (`--start`,
`--renewal-cutoff`, `--renewal-token`, `--skip-list`, `--list-only` flags).

**Why:** Charter re-engagement email going out tomorrow AM needs the gap-family
list + prioritized call-down sheet; repo keeps the script as the reusable
engine for a weekly cadence.

**Files:** `scripts/charter_gap_analysis.py` (new),
`.github/workflows/charter-gap-tw-fetch.yml` (new), `docs/CHANGELOG.md`.

---

## 2026-08-13 — Charter renewal gap analysis (one-off report, schedulable)

**What:** New read-only report script `scripts/charter_gap_analysis.py` +
manual workflow `.github/workflows/charter-gap-analysis.yml` (workflow_dispatch;
xlsx uploaded as a 7-day run artifact — Teachworks tokens live only in Actions
secrets, so the run happens in CI). Charter families with a 25/26 deal but no
26/27 renewal, enriched with Teachworks invoice history across both accounts.
5 charter pipelines (907748, 72281989, 88841552, 5119061, 1066195), deals since
2025-08-01; school-staff contacts excluded by email domain (student.* subdomains
stay family); RENEWED = deal created ≥2026-08-01 OR "26/27" in dealname
(cutoff tightened same day from 2026-06-01 — late spring 25/26 POs were
counting as renewals; Roman 2026-08-13).
**WHY:** 26/27 renewal season — Roman needed the call/win-back list ranked by
actual invoiced value, plus the deal-but-never-invoiced and TW-no-charter-deal
hygiene queues. First run 2026-08-13: 439 families → 13 renewed / 426 gap
(396 with invoices: 10 Hot, 386 Win-back; 30 never invoiced; 278 mismatches).
Corrected re-run same day (cutoff Aug 1): 439 families → 10 renewed / 429 gap
(399 with invoices: 12 Hot, 387 Win-back; 30 never invoiced; 278 mismatches).
HubSpot static list "Charter 26/27 Gap Families" (listId 3104) built from the
corrected gap set — all 429 contacts — with marketability audit: 378 fully
clean, 42 not marketing contacts, 4 opted out, 4 hard bounced, 1 no email.
Follow-up: the 42 were set as marketing contacts (helper list "Charter 26/27
Gap - Upgrade to Marketing", listId 3105; done via portal UI bulk action —
hs_marketable_status is API-read-only and the private app lacked crm.import;
Roman added the crm.import scope later that day — verified working, so future
status flips can use an UPDATE-only import with marketableContactImport=true).
Marketing tier after: 9,751/12,000. Reachable gap now 420/429.
**Files:** scripts/charter_gap_analysis.py, .github/workflows/charter-gap-analysis.yml
(temporary branch push trigger dropped at merge).
**Merge note:** a PARALLEL implementation of the same script landed on main
from another session (e20a8ec script + bfb0a07 charter-gap-tw-fetch.yml,
list name "Charter Re-Engagement 26/27 - Gap Families (Aug 2026)" — never
executed, no such list in the portal, no changelog entry). Superseded at merge
by this branch's executed version; charter-gap-tw-fetch.yml removed (it calls
a --fetch-teachworks flag only the superseded script had). Restore from
e20a8ec/bfb0a07 if anything from it is wanted.

---

## 2026-08-11 — iLead purge completed + one-student decision + teacher-email verdict (Roman)

**What:** Forms scope added → the two iLead intake forms ("Level up - Ilead",
"A+ Tutoring x iLEAD Tiered Support") backed up + archived, all 10 blocked
iLead scheduling properties archived, empty `level-up_ilead` group DELETED.
Roman decisions, same session: (1) ONE student per contact record — the plan
is the A+ persona system; sibling fields retire: `sibling_school`,
`student_3`, `student_3_school`, `student_4_school` ARCHIVED;
`sibling_current_grade_level` KEPT (Roman, same day: "if it's in the main
consultation form definitely keep it" — submissions API shows Get Started Now
Full Length live, last submission 2026-07-23). (2) `teacher_email_address` un-kept —
`teacher_of_record_email_address` is the teacher-email property; Roman then
redirected (same day): NOT archived — it is a Spotlight field: moved to group
`spotlight`, relabeled "Spotlight Teacher Email Address" per the Spotlight
nomenclature (live TSN Workflow 3b still reads it — flagged). (3)
`student_last_name_if_diff_from_parent` confirmed staying. Registry 42→41
contacts; KEEPERS 81→80. Pending code change before the last sibling fields
go: email/config.yaml teachworks.student_name_properties reads
student_full_name_clone_/student_3_full_name/student_4_full_name.

**Why:** Roman's verdicts on the low-fill review, 2026-08-11. Decision-log
entries pending: one-student model; canonical teacher-email property.

**Files:** `ops/hubspot-schema/properties.yml`,
`ops/hubspot-schema/consolidation/KEEPERS.md`,
`ops/fleet-health/audit/backups/2026-08-11-ilead-forms/` (new).

---

## 2026-08-13 — call_agent: Roman-answered calls hand follow-up to Paola

**What:** (refined same-day: first pass forced Paola on ALL tasks; Roman
narrowed it to his own calls + handoff context.) Two changes:
(1) `_resolve_owner()` — when JustCall `agent_name` shows ROMAN answered,
the task owner is forced to `default_task_owner` (Paola), `owner_hint`
ignored; other answerers keep hint routing with Paola default.
(2) New `handoff_note` field in the summary schema/prompt — a Claude-written
brief for the teammate who wasn't on the call (what was promised, pricing
quoted, names, timing, suggested opener). Tasks from Roman-answered calls
(action items AND the no-next-step guard task) open with a handoff block:
"HANDOFF — Roman spoke with this caller on <date>; follow-up is assigned to
Paola." + the brief.

**Why:** Roman 2026-08-13: sales calls ring Roman first, overflow to Paola,
and Paola does 100% of follow-up — but the hint mapping assigned tasks to
whoever was named on the call (both Karen Mercer call tasks, 404280341,
landed on Roman because he answered). Paola also needs enough context to
pick up a conversation she wasn't part of — hence the handoff brief.

**Files:** `ops/call_agent/call_agent.py`, `ops/call_agent/config.yml`,
`ops/call_agent/README.md`.

---

## 2026-08-13 — Verified 69-deal invoice backfill EXECUTED + PO day report

**What:** (1) The parked $17.5k backlog closed with VERIFICATION instead of
blind stamping: new email/invoice_backfill.py (+ tw-invoice-backfill workflow)
matched each swept deal to a Teachworks invoice (family + amount, service-month
due preferred, one claim per invoice, Paid/Approved/Sent only) — **64/69
verified & stamped** (invoice_submitted_date = service-month end, Invoice #,
Invoice Submitted stage; Jamie Holloway's date hand-corrected to 2026-08-13,
its "(Aug) 25/26" name tag is a year off). **5 EXCEPTIONS for Kath**: Christina
Duran/Talia Visions ×2 ($495) + Myra Garcia/Jason Gorman ($67) have NO TW
invoice (possible genuinely-unbilled); Katherine Perez ×2 ($1,200) have no
family contact on the deal (can't verify). (2) NEW daily report (Roman):
email/src/po_daily_report.py + 6 PM PT weekday cron DMs Roman the day's PO
deal count/value ⇄ how many already have TW invoices (Invoice # stamp or
amount-matched invoice dated on/after the deal), misses named.

**Why:** Roman: "yes" to verified backfill; "at the end of each day i get a
slack message that tells me the value of the POs that came in and corresponds
them to how many teachworks invoices created."

**Files:** `email/invoice_backfill.py` (new), `email/src/po_daily_report.py`
(new), `.github/workflows/{tw-invoice-backfill,email-po-daily-report}.yml`
(new), `email/tests/test_daily_summary.py` (suite 213 green).

---

## 2026-08-13 — TOR got the parent SMS (Mary Nieves) — persona-gated texting

**What:** Mary Nieves (TOR) received the parent schedule-confirmation SMS.
Chain: the agent now attaches TORs to deals AT CREATION → deal flow 1608222821
stamps contact_level_deal_stage on ALL associated contacts (no persona filter)
→ SMS flow 1603217415 enrolled her. Worse, deal flow 64686392 (Charter
Pre-Lesson) had ALREADY flipped her hs_lead_status to OPEN_DEAL — so a
status-based exclusion could never have saved her, and the flip also silently
broke the TOR name-matching pool. Fixes (all executed): (1) a_persona
"Teacher of Record/EF/ES" backfilled onto 1,170 of 1,203 TOR-status contacts
(append-only) — the persona is now the un-corruptible teacher marker.
(2) SMS flow 1603217415 enrollment now excludes a_persona containing the TOR
persona (revision 41, verified; unenroll-on-criteria ejects mid-flow slips).
(3) Agent self-healing: whenever po_inbox touches a TOR contact it re-asserts
persona + lead status (skipping dual-role Family+TOR contacts). Mary's lead
status restored in-portal. NOT changed: deal flows 1608222821/64686392 still
stamp/flip all associated contacts (their action type can't filter targets) —
harmless for texting now; the status flips on TORs heal on next agent touch.

**Why:** Roman 2026-08-13: "mary nieves received the sms ont the parent...
what do we do to make sure this doesnt happen in future."

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py` (suite 211
green); HubSpot: flow 1603217415 rev 41, 1,170 contact persona backfills.

---

## 2026-08-12 — Zie Rojas PO: net-payout misread + dropped correction + TOR variant (3 fixes)

**What:** Roman caught the Zie Rojas deals at $140/$280 when the PO he was
reading says $150/$300. TRUE root cause (recovered replies told the story):
the extractor read the OA CORRECTLY — iLEAD issued the POs at the old $70/hr
rate (140/280 = 2h/4h @ 70); Kath had already replied asking iLEAD to REISSUE
at $75/hr (=150/300), and Christina Mondolo acknowledged — but BOTH replies
were SILENTLY SKIPPED by the closed-thread guard, so nobody downstream saw the
rate dispute. Fixes: (1) closed PO threads are no longer skipped — replies
process (is_po replies trip the duplicate alert; others get a "↩️ PO-thread
reply" ticket); cursor rewound to 19:30Z and both dropped replies recovered as
tickets 47559984489 + 47563508797. (2) TOR 'Christina Mondolo' didn't link
because the portal contact is 'ChristinE' — name fallback now accepts a UNIQUE
last-name match in the TOR pool on first-name variants (her reply confirmed
christina.mondolo@ileadexploration.org). (3) Prompt guardrail added anyway:
use the PO value/'Total Cost', never a net-of-fee payout figure. Portal: both deals corrected to $150/$300,
Christine Mondolo associated (+family→TOR label, TOR fields stamped), Kath's
two tasks rewritten with AMOUNT CORRECTED flags. Also: teachworks
customers_for_family() (email + name match, active first) — the Aly Daly
inactive-dupe case; wired into calendar/schedule lookups and invoice_xref.

**Why:** Roman 2026-08-12: PO says 150; "there was a follow up email that came
from school with correct amount. but why is the teacher not tied to the deal?"

**Files:** `email/src/po_inbox.py`, `email/src/teachworks_client.py`,
`email/invoice_xref.py`, `email/tests/test_po_inbox.py` (suite 208 green),
`email/state/po_cursor.json` (rewound).

---

## 2026-08-12 — Missed 8/10 iLEAD PO recovered + seq double-count fix

**What:** Kath flagged a PO from 8/10 that never became deals. Found it: an OPS
order agreement (5 POs, 3114057042–46, Zackarias Barajas / Mari Barajas,
phonics w/ Fidal Williams, $1,630.38 total) arrived 8/10 09:45 PT — ~4 hours
BEFORE the OAs-are-POs rule deployed, and the evening replay list only covered
the two older iLEAD emails. Replayed via replay_msg_ids → 5 deals created with
the full current pipeline (TOR Mary Nieves name-matched WITH resolved email,
parent attached, pending flag, tutored=No, invoice tasks). Audit of every other
po_inbox record since 8/9 confirmed nothing else was missed. Also fixed the
bug the replay exposed: 'School N' came out 1,2,4,7,9 because the base count
was re-searched per sibling while the index caught up — the base is now
searched ONCE per email (seq_cache) and offsets applied locally; the three
misnumbered deals were renamed to iLead 3/4/5 in-portal.

**Why:** Kath's report (via Roman): "a PO came in on 8.10 that we never
caught." Root cause was rule-deployment timing, not a pipeline gap.

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py`
(suite 206 green).

---

## 2026-08-12 — TOR name + email stamped on PO deals

**What:** PO deals now stamp `teacher_of_record_name` + `teacher_of_record_email`
(the deal properties built for exactly this) via the deal_property_map. Bonus:
when the PO names the TOR without an email and the name-match fallback finds
the contact, the RESOLVED email is stamped on the deal anyway. Both fields flag
on the ticket + 🚩 DM when the PO omits the TOR entirely. Backfilled today's 13
live deals (Mary Nieves ×3, Véronique Fabre ×9, Shauna Smith ×1). Note: the
deal-level TEXT fields are convenience copies for filters/reports — the
contact-to-contact "Teacher of Record" association (#AP031) remains the source
of truth. PO-PROCESS.md property table updated.

**Why:** Roman (2026-08-12): "we need to make sure we have the teacher of
record name and email address extracted from PO as well." Extraction already
existed; the deal-level stamps did not.

**Files:** `email/src/po_inbox.py`, `email/config.yaml`,
`email/tests/test_po_inbox.py` (suite 205 green), `docs/PO-PROCESS.md`.

---

## 2026-08-11 — Low-fill review round 1: iLead scheduling + tutor credentials un-kept (Roman)

**What:** Roman's picks from low-fill-review.md: the whole Level-Up iLead
scheduling set (7 contact per-day *_schedule_preference — previously #AP029
family keepers, now un-kept; tutoring_frequency; when_would_you_like_the_
tutoring_to_start; which_days_of_the_week_do_you_prefer_) + degree_received +
university_attended. Outcome: degree_received + university_attended ARCHIVED;
the 10 scheduling fields BLOCKED by two iLead intake forms (0-10a7465d…7f48,
0-529c7788…7a66) — they archive the moment those forms are deleted (needs
forms scope or UI). DEAL-side per-day preferences remain keepers. Removed the
9 un-kept contact declarations from properties.yml (51→42 contacts);
KEEPERS.md 90→81.

**Why:** Roman 2026-08-11: "all level up ilead scheduling can be archived,
that whole group. degree received archive, university archive."

**Files:** `ops/hubspot-schema/properties.yml`,
`ops/hubspot-schema/consolidation/{KEEPERS,contacts-proposal,low-fill-review}.md`.

---

## 2026-08-11 — QuickBooks refs archived + low-fill review list (Roman's orders)

**What:** (1) "Archive all quickbooks references": the only two QBO assets in
the portal scan — workflow `Quickbooks` (323730202, was ON) and list `Ready
for Onboarding to QBO` (1176) — backed up to
`ops/fleet-health/audit/backups/2026-08-11-quickbooks/` and DELETED
(HubSpot-restorable ~90 days). (2) "All properties with under 150 contacts
presented for review": counted fills for all 454 live custom contact
properties; 378 are under 150 — organized by disposition in NEW
`ops/hubspot-schema/consolidation/low-fill-review.md` (22 keepers FYI /
168 keep-in-place / 112 storage-only / 52 already-retire / 4 new booth props /
20 system) with a tick-box column for Roman's archive picks.

**Why:** Roman 2026-08-11, verbatim orders. QBO context: no automation — Kath
marks invoices in TW, Claude cowork records payments in TW, manual QBO sync.

**Files:** `ops/hubspot-schema/consolidation/{automation-purge-proposal,low-fill-review}.md`,
`ops/fleet-health/audit/backups/2026-08-11-quickbooks/` (new).

---

## 2026-08-11 — Feedback-agent dedupe fix + automation purge proposal

**What:** (1) Fixed the feedback agent double-filing reports: Slack retries land
as second dispatches pinned to a stale commit, so the retry run read a
state.json without the first run's processed-mark (root cause of duplicate PRs
#63/#64 for Danielle's LinkedIn-op-ed report; `Ev0BPLGNF12N` appeared twice in
state.processed). Fix: `ref: main` on checkout in feedback-intake/-digest/-fix
(close-loop already had it) — the concurrency group already serializes runs, so
the second run now sees fresh state and the existing event_id dedupe catches
the retry. Removed the orphan duplicate correction file (#64's) + doubled state
entry. (2) NEW `ops/hubspot-schema/consolidation/automation-purge-proposal.md`:
the 87 workflows/lists + 43 forms + 8 misc blockers holding up the 78 blocked
retire candidates, each with DELETE (25) / EDIT (43) / VERIFY (19) verdicts,
3 high-risk callouts (TW-sync Zapier path, SMS deal-token stack, Quickbooks),
a text-scan accuracy caveat for generic names, and an authoritative
delete-probe step. PROPOSAL — pending Roman.

**Why:** Roman: "do 1 and 2" (feedback-agent diagnosis + purge proposal).
Optional relay hardening (CacheService dedupe in apps-script.gs) offered but
needs Roman's web-app redeploy — not done.

**Files:** `.github/workflows/feedback-{intake,digest,fix}.yml`,
`corrections/content-build/` (dup removed), `ops/feedback-agent/state/state.json`,
`ops/hubspot-schema/consolidation/automation-purge-proposal.md` (new).

**Addendum (Roman's answers, same day):** callout 1 RESOLVED — `Non Charter/A+
Sync to TW` is the LIVE path putting Gold + Free Trial deals into A+ Teachworks
(deal_sync covers charter POs only): flow KEEP; `sync_to_teachworks_` and
`sync_to_teachworks_slp` reclassified KEEP-IN-PLACE (only `_cap` still retires,
with the CAP flows). Callout 3 context: NO QBO automation exists — Kath marks
invoices in TW, Claude cowork records payments in TW, QBO synced manually; the
`Ready for Onboarding to QBO` list + onboarding flow are the manual queue
(KEEP; `is_the_online_tutor_ready_for_onboarding` + `business_license_on_file`
reclassified KEEP-IN-PLACE). Contacts: KEEP-IN-PLACE 185→189,
RETIRE-CANDIDATE 99→95. Verdicts now: 25 DELETE / 43 EDIT / 4 KEEP / 15 VERIFY.

---

## 2026-08-12 — Booth: role picker + attendee list + short consent

**What:** (1) NEW `aplus_event_role` (events group, dropdown
Administrator/Teacher/Support Staff), declared + synced; required pill picker
on the booth form. Role now drives the create-only persona stamp:
teacher→TOR persona+lead status, administrator→Decision Maker/Director,
support_staff→no stamp, missing→teacher default (verified e2e). (2) NEW
ACTIVE list 3103 "Sage Oak BTSC 2026 — Booth Attendees" on
aplus_event_tag=sage_oak_btsc_2026 — auto-enrolls all booth contacts;
future events get one list per appended tag option. Enrollment verified
(<30s); team test runs (Roman/Emily/Hugh Jazz/Danielle) already enrolled,
personas behaved per doctrine. (3) Consent copy shortened (Roman):
"Send my photo + A+ can reach out about tutoring for my students 📸".

**Why:** Roman 2026-08-12: role segmentation + "every contact that submits
this photo booth ends up on a hubspot list."

**Files:** `booth/worker.js`, `booth/index.html`,
`ops/hubspot-schema/properties.yml`,
`ops/hubspot-schema/consolidation/KEEPERS.md` (81→82).

---

## 2026-08-11 — Booth round 3: enum-write bugfix, frame design, delivery=All

**What:** (1) CRITICAL FIX: worker.js wrote enum LABELS ("Print") where the
HubSpot API takes internal VALUES ("print") — every booth submission failed
the contact upsert silently while photos still delivered (the fleet "read
labels" rule is about reading, not writing). Verified fixed end-to-end:
test contact created with all 6 props + TOR persona, then archived.
(2) Email timeline logging verified live: test submission → 1 email
engagement on the contact (subject/SENT), then archived. BCC workaround
declined — sender isn't a HubSpot user so BCC logging would misattribute;
API logging is deterministic. (3) Frame redesign: both logos in the header
band, fun banners ("Best. Year. Ever. ✨" etc.), 2026–2027 school year on
frame/attract/email, type sized for 2x3" prints (~600dpi: old 24-30px text
printed at ~3pt). (4) Delivery "Both" → "All 3!" (email+text+print);
aplus_booth_delivery += all (synced; "both" kept legacy). (5) Screens
scroll when content overflows (kiosk overflow:hidden clipped the 4-card
delivery screen with no way to reach the rest). (6) Photo retention is
DOCUMENTED as ephemeral: email=attachment only, text=KV 7-day TTL,
print=nothing. Archive-all option proposed to Roman, not yet approved.

**Why:** The event capture chain (contact + persona + timeline email) is the
point of the booth; the silent enum failure was defeating exactly that.

**Files:** `booth/worker.js`, `booth/index.html`,
`ops/hubspot-schema/properties.yml`.

---

## 2026-08-11 — Booth round 2: branding, TOR audience, JustCall texts, email logging

**What:** (1) Logos: Sage Oak pennant + white A+ on attract, color A+ in the
email. (2) All outbound links → wetutorathome.com/home-school-tutoring
(aplustutoring.com is NOT ours — email CTA, SMS body, photo-frame footer).
(3) TOR audience (Roman: attendees are homeschool charter TORs, not parents):
teacher-facing copy pitching one-on-one tutoring + intervention programs, and
booth-CREATED contacts stamped a_persona="Teacher of Record/EF/ES" +
hs_lead_status="Charter School Teacher TOR/EF" (create-only, mirrors
po_inbox TOR_CREATE_PROPS; existing contacts never overwritten). (4) NEW
"Text it" delivery via JustCall MMS from the main A+ line +18188506284:
photo stored in Workers KV (7-day TTL, UUID keys) and served publicly at
<worker>/photo/<uuid> as the media_url; JUSTCALL_API_KEY/SECRET set as Worker
secrets; `aplus_booth_delivery` gained option Text(text) — declared in
properties.yml and synced (R2 skipped: not enabled on the account, KV needs
nothing). (5) Booth photo emails logged to the contact's HubSpot timeline
via engagements API (assoc 198; write scope verified create+delete). (6)
Photo canvas 1200×1500 (4:5) → 1200×1800 (2:3) to fit Roman's 2x3" portable
printer (also fits 4x6); camera preview ratio matched.

**Why:** Event capture should classify TORs correctly for the fleet, deliver
photos the way teachers actually want them, and leave a full trail (email on
timeline) in HubSpot.

**Files:** `booth/worker.js`, `booth/index.html`, `booth/wrangler.toml`,
`ops/hubspot-schema/properties.yml`.

**What:** New `booth/` directory: Cloudflare Worker `sage-oak-booth`
(worker.js — `/submit` upserts the HubSpot contact with the 4 events-group
props from PR #65 and emails the framed photo via Resend) + kiosk front-end
(index.html — attract → banner → camera → form → delivery, client-side photo
composite) + wrangler.toml + README. DEPLOYED live:
Worker `https://sage-oak-booth.nameless-mountain-bafa.workers.dev` (secrets
HUBSPOT_TOKEN + RESEND_API_KEY set via wrangler), Pages
`https://sage-oak-booth.pages.dev`; CONFIG.WORKER_URL and ALLOWED_ORIGIN
cross-wired; smoke-tested (CORS preflight, input validation, Pages 200).
Sender is `photos@wetutorathome.com` — that's the Resend-verified domain
(aplustutoring.com is NOT verified there; Roman verified wetutorathome.com
in-session).

**Why:** Sage Oak BTSC 2026 event capture — booth attendees become HubSpot
contacts (event-tagged, consent recorded) with zero manual entry.

**Files:** `booth/worker.js`, `booth/index.html`, `booth/wrangler.toml`,
`booth/README.md`.

---

## 2026-08-11 — Concurrency rule: branch work in worktrees (Roman: "lfg")

**What:** New mandatory rule in `CLAUDE.md`: sessions doing branch/PR work use
a git worktree; never create/commit branches directly in the shared main
checkout.

**Why:** Two concurrent sessions collided today — a po_inbox commit from one
session landed on the other's PR branch (this one, #65) and the branch had to
be rebuilt by hand. Worktrees isolate each session's working tree while
sharing history.

**Files:** `CLAUDE.md`.

---

## 2026-08-11 — Booth properties for Sage Oak BTSC 2026 (PR #65)

**What:** Declared 4 new contact properties in the registry for the photo
booth: `aplus_event_tag` (multi-checkbox, one option `sage_oak_btsc_2026`;
future events APPEND options), `aplus_booth_goal` (banner text), `aplus_booth_delivery`
(Email/Print/Both dropdown), `aplus_marketing_consent` (Yes/No dropdown).
Added a new `events` contact property group — booth attendees can be any
persona, so none of the 5 persona groups fit. LOCKED by Roman 2026-08-11:
the `events` group + the event-tag append pattern (one multi-select property,
future events append options) — decision-log number pending. POST-MERGE
EXECUTED same day (Roman: "run"): PR #65 squash-merged, `create_properties.py`
run (4 created / 0 updated / 87 already in sync), all 4 verified live in
portal 6312752 by independent API read (labels, group, options correct),
KEEPERS.md +Events section (86→90).

**Why:** Booth capture tools need declared properties (registry rule: never
create ad hoc); event attendance is designed as one multi-select tag property
so each future event is an appended option, not a new property.

**Files:** `ops/hubspot-schema/properties.yml`.

---

## 2026-08-11 — PO hours computed from rate + Kath's invoice fields + PO-PROCESS.md

**What:** (1) Extractor now pulls the PO's HOURLY RATE; when hours aren't
stated, they're computed (amount ÷ rate, e.g. $150 ÷ $75/hr = 2, fractional ok)
and noted on the ticket — stated hours are never overwritten. (2) Kath's
convert-to-invoice task now explicitly instructs filling `invoice__` (Invoice #)
with the TW invoice number and confirming `lessons_fulfilled_date` (prefilled
to the end of the PO month = the invoice due date). (3) NEW `docs/PO-PROCESS.md`:
the complete PO-receipt reference — every stage, every property with its
decision rule, and the human ownership table. Keep it in sync with po_inbox.py.

**Why:** Roman (2026-08-11): "for PO hours, you might have to calculate. but
our rate will be in the po. kath also has to fill out the properties of
invoice number and invoice due date" + asked for the guided walkthrough.

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py`
(suite 202 green), `docs/PO-PROCESS.md` (new).

---

## 2026-08-11 — SMS workflow audited: property routes (never suppresses) + schedule stamp

**What:** Audited SMS flow 1603217415 ("Charter Traditional SMS New Deal
Created", contact-based) end-to-end via the automation API. Findings: BOTH
branches of `is_the_family_currently_being_tutored_by_us_` send the
schedule-confirmation texts — "No" only adds an internal staff email + delay
first; texts are per-CONTACT enrollment (re-armed when the flow clears
`contact_level_deal_stage`), so frequency is structurally one text pair per kid
per PO event, never daily. Two fixes from that: (1) REVERTED the sibling-deal
"Yes" suppression (texts were never per-deal; the flow fetches ONE associated
deal, so a lying sibling could skip the staff alert) — every deal now carries
the true month-scoped value; the 10 sibling deals in-portal reset to "No".
(2) The SMS inserts `{{schedule_preferences}}` from the DEAL — PO deals never
had it, so charter texts ended in a BLANK. The agent now stamps it at PO time
with the student's live TW schedule ("Wednesdays 3:30 PM with Sarah Lee"),
derived from upcoming lessons, else the recent-lesson pattern (new
upcoming_lessons/recent_lessons detail in tw.student_lesson_activity);
nothing derivable → 🚩 gap DM instead of a half-written text.

**Why:** Roman shared the live SMS workflow; reading it showed the property's
real semantics (routing, not suppression) and the blank-schedule content bug.
Roman: "yessssss. fix the schedule. i agree with it all."

**Files:** `email/src/po_inbox.py`, `email/src/teachworks_client.py`,
`email/tests/test_po_inbox.py` (suite 198 green).

---

## 2026-08-10 — PO deal naming convention + parent-chase flow (Roman: "implement")

**What:** (1) PO-created deals are now named `Parent - Student - School N - YY/YY`
(Roman's convention, e.g. "Alexandra Lauterio - Genevieve Lauterio - Taylion 1 -
26/27"): N = the student's deal count at that school this school year + 1 (staggered
across multi-PO emails), school year derived from the PO's service month (Aug–Dec =
first year), school shorthand from new `po_inbox.school_short_names` config map
(unmapped school → extracted name used + ticket flags the gap). Parent contact is
now resolved BEFORE naming; the PO number moves out of the name entirely (the
`po_number` property is canonical). Bonus: parent-led names pass deal_sync's
`_contact_matches_dealname` check, which the old "School - Student - PO #" names
failed. (2) NEW parent-chase flow: a PO with no parent info and no unique HubSpot
match creates the deal as `NEEDS PARENT - ...` and DRAFTS a parent-info request
(name + email + phone) to the TOR (else sender) on the same Gmail thread — human
sends it (agent still never sends from charter@). The reply is caught on the open
thread: Family contact auto-created (email + phone + `a_persona=Family`), associated
to the deal, deal renamed to the real parent, family→TOR link synced (#AP031), and
the Teachworks sync runs immediately — unblocking the whole downstream chain
(TW family/student → scheduling → invoice hours) with zero manual data entry.
No reply within `parent_chase.escalate_business_hours` (16 = 2 business days) →
one escalation DM to Kath. The live Taylion deal 63551218500 was renamed to the
new convention in-portal.

**Why:** Roman (2026-08-10): the deal name must lead with the parent, and a missing
parent blocks more than the name — the Teachworks sync keys the family on the deal's
contact email, so every PO without parent info silently stalled TW creation,
scheduling alerts, and invoice hour-tracking until someone chased it by hand.

Also: extracted PO numbers are normalized — a leading "PO"/"P.O.#" prefix is
stripped ("PO7514044381" → "7514044381"; letters that are PART of the number,
like Blue Ridge's "PF593736", are kept) before dedupe, the deal property, and
the audit record.

(3) Order agreements ARE POs (Roman, same session): OPS/iLEAD Vendor Agreement
Forms stamped "THIS IS NOT A PO" now get the FULL PO flow (deals per PO number,
invoice tasks, chase) with a new `pending_approval` flag — ticket + invoice task
carry "⏳ PENDING school approval — confirm in the school's ordering portal".
This partially supersedes the 2026-08-06 iLEAD thread-stays-open fix: OA threads
now close as processed POs; the approved-PO email arriving later trips the
po_number dedupe, which alerts Kath (that alert now doubles as the approval
signal). Thread guard refined: a closed thread with an OPEN parent chase still
processes replies (the TOR's parent-info answer must get through). NEW replay
tool: `PO_REPLAY_MSG_IDS` env / `replay_msg_ids` workflow input reprocesses
specific Gmail messages, bypassing guards — for backfilling under new rules
(same pattern as deal-sync's FORCE_DEAL_ID).

(4) Scheduler visibility (Roman, same session): every PO-created deal now sets
`should_this_deal_be_posted_to_a_slack_channel_="true"` — the existing HubSpot
workflow behind that checkbox posts the deal to the per-pipeline Slack channel.
And the assigned scheduler (deal owner, A-L/M-Z) gets ONE direct DM per PO email
listing the deal(s) created: "In Pre-Lesson now — get lessons scheduled to hit
the 72-hr Post-Lesson target", with the pending-approval warning when it applies.
Previously schedulers only saw deals appear in HubSpot; the sole Slack signal
was the no-lessons alert in #email-agent.

(5) TOR name-only fallback (Roman, same session — "why weren't TORs associated?"):
OPS/iLEAD PDFs name the TOR without an email, and the TOR association keyed only
on email, skipping SILENTLY. Now a bare TOR name is looked up among existing
TOR-flagged contacts (lead status "Charter School Teacher TOR/EF" OR the TOR
persona), last name via search + first name compared accent-insensitively
('Véronique' portal vs 'Veronique' PDF); a UNIQUE match is associated (+#AP031
family→TOR link) — lookup only, never created from a bare name; no/ambiguous
match now flags the ticket. Backfilled in-portal: Mary Nieves → Isaac's 3 deals,
Véronique Fabre → Evrsen's 9, Shauna Smith → Taylion, + 3 labeled family→TOR
links (Jessica→Mary, Aly→Véronique, Alexandra→Shauna).

(6) Missing-info alerting (Roman, 2026-08-11: "whenever something is missing it
is vital to send Roman and Kath Slack messages"): any gap on PO intake — fields
the PO didn't state, unmatched TOR/parent, NEEDS PARENT deals, failed uploads,
any "do it manually" follow-up — now triggers a direct 🚩 DM to EVERYONE in new
config `po_inbox.missing_info_dms` (kath + roman), with the gap list + ticket
link, on top of the ticket flags. Parent-chase escalations also go to both.

(7) `is_the_family_currently_being_tutored_by_us_` (Roman, 2026-08-11: gates the
scheduling-text workflow). THE RULE (locked with Roman same day; amended twice
in-session to its final form — student-level, CALENDAR-ONLY, stamped once at PO
time): **"Yes" = the PO's student has a lesson booked in Teachworks; "No" =
nothing on the calendar, period — the text goes out (recent lessons don't excuse
an empty calendar; a second kid with no lessons of their own is "No" even while
the sibling is active). ONE text per KID: a multi-PO email is always one student — only its FIRST
deal carries "No", same-student siblings are stamped "Yes" so the texting workflow cannot fire
9 times for a 9-PO order agreement (the Aly Daly case). Unverifiable (no parent
email / TW error) = left unset + 🚩 gap DM, never guessed; student absent from
TW = confident "No". MONTH-SCOPED: the check is against the PO's SERVICE MONTH — a September PO texts unless September itself has lessons booked (leftover August lessons do not count); month unparseable → any-upcoming fallback.** Checked against the RESOLVED parent email (PO or contact
record) via new tw.student_lesson_activity(), memoized per email; the no-lessons
scheduling alert shares the lookup, so it also works for parents resolved from
prior deals. Backfilled accordingly: Isaac's + Evrsen's FIRST deals "No", their
10 sibling deals corrected to "Yes"; Taylion left for Kath/Janelle to set once
booking is confirmed; Taylion dealtype corrected newbusiness → existingbusiness
(Genevieve had a prior deal).

**Files:** `email/src/po_inbox.py`, `email/src/hubspot_client.py`,
`email/config.yaml`, `email/src/teachworks_client.py`, `email/tests/test_po_inbox.py` (32 new tests; email suite
191 green), `.github/workflows/email-po-inbox.yml` (replay_msg_ids input).

---

## 2026-08-10 — Retire-candidate archive pass (Roman: "go")

**What:** Registry sync run (`source_agent` +fleet-retry/+branch-hygiene). All
113 retire candidates audited for usage against 342 workflows (v3+v4), 214
lists, and calculated-property formulas (forms API not scannable — token lacks
forms scope). Outcome: **30 ARCHIVED** (audit-clean; reversible 90 days),
**35 BLOCKED** by live workflow/list references, **43 BLOCKED by HubSpot's own
PROPERTY_USAGE validation** (in use by forms — incl. pre-approved
`lead_ad_prop0`), **5 HOLD** (sibling fields, pending multi-child data-model
decision). Per-property outcomes stamped into the proposal docs.

**Why:** Roman's "go" on the remaining consolidation items. The API's
delete-time usage check covered the forms gap, so nothing referenced anywhere
was archived. Unblocking the 78 BLOCKED rows means cleaning up the referencing
workflows/lists/forms first — most are dead flows (Diagnostic Testing, CAP,
summer-2021 scheduling) that are themselves retirement candidates.

**Files:** proposal docs (outcome column), `ops/hubspot-schema/consolidation/`.

---

## 2026-08-10 — Consolidation APPROVED + persona group moves executed

**What:** Roman approved the consolidation proposal. Executed the 36 remaining
persona group moves via `ops/hubspot-schema/consolidation/execute_group_moves.py`
(idempotent, PATCH groupName only — names/types/options/data untouched);
verified 41/41 keepers now sit in `family`/`tor`/`tutor`/`student`. Declared all
86 keepers in `ops/hubspot-schema/properties.yml` (46 contacts + 38 deals +
existing a_persona/tickets); enum options intentionally omitted so the portal
stays authoritative for option lists (e.g. the master school list) —
`create_properties.py --dry-run` confirms 0 creates, 86 in sync.

**Why:** "approved" (Roman, 2026-08-10) on the committed proposal. NOT done:
archives — all 113 retire candidates still require Roman's per-property
"Used in" check first (locked rule). Also pending: dry-run shows `source_agent`
wants 2 new registry options (fleet-retry, branch-hygiene) — pre-existing sync
behavior, not run.

**Files:** `ops/hubspot-schema/properties.yml`,
`ops/hubspot-schema/consolidation/execute_group_moves.py` (new),
proposal docs restamped APPROVED/EXECUTED.

---

## 2026-08-10 — HubSpot property consolidation proposal (contacts + deals)

**What:** Read-only audit of all 884 contact / 718 deal properties in portal
6312752; every custom property (479 contacts, 107 deals) assigned a proposed
disposition in `ops/hubspot-schema/consolidation/` — persona-group move
(family 26, tor 4, tutor 9, student 1), KEEP-IN-PLACE (188 / 83),
STORAGE-ONLY (119 / 10), RETIRE-CANDIDATE (97 / 14, each with fill count +
last-modified + a required manual "Used in" check), or SYSTEM (35 custom
integration-written, excluded). `KEEPERS.md` distills the 88-property
vocabulary agents should use. Rule 12 enforced: repo grepped for every
internal name; code-referenced properties are keepers regardless of fill rate.

**Why:** Finishes what the persona architecture (#AP024/#AP028/#AP029,
commits 73837d3/f22fd07/60457fc) was built to enable — a single reviewable
sorting of years of program-specific property sprawl. This session PROPOSES;
Roman approves before anything moves, syncs, or archives. `properties.yml`
deliberately untouched — keeper declarations land after approval.

**Files:** `ops/hubspot-schema/consolidation/contacts-proposal.md`,
`deals-proposal.md`, `KEEPERS.md`.

**Addendum (same day, Roman's verdicts):** `what_is_your_child_s_current_grade_level_`
is THE canonical student grade property — agents use it always; the other grade
fields are program/form capture only. `what_grade_is_your_child_in` (9 fills) and
`payment_on_file_` (270 fills) demoted to RETIRE-CANDIDATE. Roman executed the
first group moves himself: `parent_concerns_what_can_we_do_to_help_`,
`student_school`, `student_additional_information` → `family`;
`student_last_name`, `student_last_name_if_diff_from_parent` → `student`
(the latter three out of CAP form_fields). Keeper set now 86.

---

## 2026-08-06 — PO agent: parent resolved from the student's prior deal

**What:** POs typically omit parent info; Kath's manual fix — look the student
up in HubSpot and read the parent off their prior deal — is now the agent's
second resolution step (after PO-provided parent email, before the last-name
guess): search deals by student first name, narrow to names containing the
student's last name, collect the deals' non-TOR contacts (persona/tor-email
filtered), and use a UNIQUE parent; anything ambiguous falls through
unchanged. Resolution method is noted on the ticket.

**Why:** Roman — "POs typically do not include parent name; Kath does this
manually so it's possible for you to do it." No student↔parent association
exists in the portal (verified read-only), so deal names are the link.

**Files:** `email/src/po_inbox.py`, `email/src/hubspot_client.py`
(`get_deal_contacts`), `email/tests/test_po_inbox.py` (4 new tests; suite
159 green).

---

## 2026-08-06 — PO agent: one deal per PO number (multi-PO emails) + review threads stay open

**What:** (1) The extractor now returns `pos: [...]` when one email carries
several distinct POs (schools issue one per service month); deal handling
loops — one deal, invoice task, and TOR sync per PO number, scheduling alert
once per email. Fallback: comma-jammed `po_number` values split into one deal
each with amounts flagged for manual fill. (2) Thread dedupe now closes a
thread only after a REAL PO was processed (`category=new_po`); review-only
threads (order agreements marked "THIS IS NOT A PO") stay open so the actual
POs arriving as replies aren't silently dropped.

**Why:** Roman, on the live iLEAD/Jaramillo case (order agreement announcing
POs 3114047368/69/70, Aug/Sept/Oct): each PO number is its own deal. The old
code would have made one mashed deal (or skipped same-thread POs entirely).

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py`
(5 new/updated tests; suite 155 green).

---

## 2026-08-06 — PO agent: family→TOR association sync (#AP031) + persona stamping

**What:** Every incoming PO now syncs the family contact's "Teacher of Record"
association (contact→contact, typeId 15 USER_DEFINED): no-op when already
linked, create when missing, ADD-and-flag when the family is linked to a
different TOR — existing links are never auto-removed (multi-kid families).
TOR lookup falls back to secondary email before creating (prevents duplicates
like the Kristy Doyal case). Contacts CREATED by the agent are persona-stamped:
TOR → `hs_lead_status="Charter School Teacher TOR/EF"` +
`a_persona="Teacher of Record/EF/ES"`; parent → `a_persona="Family"`. Existing
contacts are never overwritten. Association labels/personas/lead-status value
verified read-only against portal 6312752 before implementation.

**Why:** #AP031 — the PO is the source-of-truth event for teacher assignment;
yesterday's ~405-association backfill goes stale without a per-PO sync.

**Files:** `email/src/po_inbox.py`, `email/src/hubspot_client.py`,
`email/tests/test_po_inbox.py` (7 new tests; suite 150 green).

---

## 2026-08-06 — Session Documentation Protocol installed

**What:** Created `CLAUDE.md` (session protocol + durable key context: property
registry, enumeration label rule, 5-persona contact model, family→TOR
association model) and this changelog.

**Why:** Claude-in-chat and Claude Code sessions were drifting — decisions made
in one surface weren't reliably visible in the other. The repo is now the
shared memory; the protocol makes documentation a mandatory session exit step.

**Files:** `CLAUDE.md`, `docs/CHANGELOG.md`.

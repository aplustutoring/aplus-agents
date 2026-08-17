# aplus-agents changelog

Session-level record of changes to agent behavior, schema, skills, or process —
the shared memory between Claude-in-chat and Claude Code sessions. Every session
that changes how the fleet behaves appends an entry here (see the Session
Documentation Protocol in `CLAUDE.md`): date, what changed, WHY, files touched.
Newest entries first.

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

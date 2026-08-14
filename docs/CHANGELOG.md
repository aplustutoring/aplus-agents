# aplus-agents changelog

Session-level record of changes to agent behavior, schema, skills, or process —
the shared memory between Claude-in-chat and Claude Code sessions. Every session
that changes how the fleet behaves appends an entry here (see the Session
Documentation Protocol in `CLAUDE.md`): date, what changed, WHY, files touched.
Newest entries first.

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
hs_marketable_status is API-read-only and the private app lacks crm.import).
Marketing tier after: 9,751/12,000. Reachable gap now 420/429.
**Files:** scripts/charter_gap_analysis.py, .github/workflows/charter-gap-analysis.yml
(temporary push trigger on the feature branch — drop after merge).

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

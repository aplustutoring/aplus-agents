# aplus-agents changelog

Session-level record of changes to agent behavior, schema, skills, or process —
the shared memory between Claude-in-chat and Claude Code sessions. Every session
that changes how the fleet behaves appends an entry here (see the Session
Documentation Protocol in `CLAUDE.md`): date, what changed, WHY, files touched.
Newest entries first.

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

**Files:** `email/src/po_inbox.py`, `email/config.yaml`,
`email/tests/test_po_inbox.py` (15 new tests; email suite 174 green),
`.github/workflows/email-po-inbox.yml` (replay_msg_ids input).

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

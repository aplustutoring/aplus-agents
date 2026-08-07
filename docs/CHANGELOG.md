# aplus-agents changelog

Session-level record of changes to agent behavior, schema, skills, or process —
the shared memory between Claude-in-chat and Claude Code sessions. Every session
that changes how the fleet behaves appends an entry here (see the Session
Documentation Protocol in `CLAUDE.md`): date, what changed, WHY, files touched.
Newest entries first.

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

# aplus-agents — session guidance for Claude

## Session Documentation Protocol (mandatory)
At the end of ANY session that changes agent behavior, schema, skills, or process:
1. Append an entry to `docs/CHANGELOG.md`: date, what changed, WHY, files touched.
2. If a decision was locked, remind Roman to log it to the A+ Decision Log (#AP### format).
3. Commit messages reference the decision number when one exists (e.g. "#AP031").
4. Before ending, output a 10-line handoff summary Roman can paste into Claude chat.
This keeps Claude-in-chat and Claude Code synchronized — the repo is the shared memory.

## Concurrency rule (mandatory — locked by Roman 2026-08-11)
Multiple Claude sessions share this checkout. Any session doing branch/PR work
must use a git worktree (EnterWorktree, or `git worktree add`); never create or
commit to a branch directly in the main checkout. Direct commits to `main` in
the main checkout are allowed only when that is the session's sole task surface.
(Why: on 2026-08-11 two concurrent sessions collided — one session's po_inbox
commit landed on the other's PR branch and had to be untangled by hand.)

## Key context for any session
- HubSpot property registry: `ops/hubspot-schema/properties.yml` is the source of truth,
  synced to portal 6312752 by `create_properties.py` (additive only). Declare new
  properties there; never create them ad hoc.
- Enumeration rule: agents ALWAYS read option LABELS, never internal values.
- Agent-property labeling (Roman 2026-08-14): any property an agent WRITES gets the
  `[Agent] ` label prefix and a description starting "AGENT PROPERTY — written by <script>".
  Humans must be able to tell agent-maintained fields from intake capture at a glance.
- Contact model: 5-persona system via `a_persona` (multi-select checkbox in the `master`
  group): Decision Maker/Director, Teacher of Record/EF/ES, Family, Tutors, Student.
- Family→TOR relationships are contact-to-contact associations with the paired label
  "Teacher of Record" (associationTypeId 15, USER_DEFINED; reverse "Family" = 14).
  The stamped text fields (teacher_of_record_name/email on family contacts) are legacy
  intake capture, not the source of truth.

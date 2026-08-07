# aplus-agents — session guidance for Claude

## Session Documentation Protocol (mandatory)
At the end of ANY session that changes agent behavior, schema, skills, or process:
1. Append an entry to `docs/CHANGELOG.md`: date, what changed, WHY, files touched.
2. If a decision was locked, remind Roman to log it to the A+ Decision Log (#AP### format).
3. Commit messages reference the decision number when one exists (e.g. "#AP031").
4. Before ending, output a 10-line handoff summary Roman can paste into Claude chat.
This keeps Claude-in-chat and Claude Code synchronized — the repo is the shared memory.

## Key context for any session
- HubSpot property registry: `ops/hubspot-schema/properties.yml` is the source of truth,
  synced to portal 6312752 by `create_properties.py` (additive only). Declare new
  properties there; never create them ad hoc.
- Enumeration rule: agents ALWAYS read option LABELS, never internal values.
- Contact model: 5-persona system via `a_persona` (multi-select checkbox in the `master`
  group): Decision Maker/Director, Teacher of Record/EF/ES, Family, Tutors, Student.
- Family→TOR relationships are contact-to-contact associations with the paired label
  "Teacher of Record" (associationTypeId 15, USER_DEFINED; reverse "Family" = 14).
  The stamped text fields (teacher_of_record_name/email on family contacts) are legacy
  intake capture, not the source of truth.

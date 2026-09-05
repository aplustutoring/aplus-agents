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

## CARE core values (mandatory for any agent that reasons)

A+ Tutoring's vision, mission and CARE values live in ONE file:
`ops/values/care-values.md`. The verbatim block in it is LOCKED and must never
be reworded, paraphrased, or copied into a prompt, skill or template.

**Every agent whose output is reasoned rather than computed carries this line in
its prompt:**

> Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.

That applies to new agents by default. Placement follows each agent's existing
prompt convention (top of the system string, or the first line of a prompt
block).

**Deterministic agents do NOT get the pointer.** Syncs, sweeps, metrics, relays
and list builders produce no language for values to shape, and a pointer inside
them is dead text that a later reader mistakes for something load-bearing. As of
2026-08-26 that is 20 of the 26 active agents and all 10 manual ones.

The skills in `marketing/skills/` are the reasoning layer for the content
engines (they are loaded by `SkillsRunner`, not by the .py entrypoints), so they
carry the pointer too.

## Investigation rule (mandatory — locked by Roman 2026-08-31)
Never close an investigation by moving on. Every incident ends with one of:
(a) a system change (code/config/process/doc) that makes the failure class
impossible, or (b) an explicit written line: "no system fix exists because X."
A plausible story + a human workaround ("forward it to us", "check the portal",
"do it manually") is NOT a resolution — first exhaust "what would the agent
need so no human ever does this again?" When evidence conflicts with your
story (a teammate says the email arrived; the log says it didn't), the story
is wrong somewhere — keep pulling until the contradiction resolves.
(Why: on 2026-08-28 Lia Beck's PO fell behind the Gmail cursor; the
investigation verified everything EXCEPT the query, declared "never arrived,"
handed Kath homework, and the email sat unread 3 more days. Roman: "never
push to move on, always ask, can this make us better.")

## Key context for any session
- HubSpot property registry: `ops/hubspot-schema/properties.yml` is the source of truth,
  synced to portal 6312752 by `create_properties.py` (additive only). Declare new
  properties there; never create them ad hoc.
- Enumeration rule: agents ALWAYS read option LABELS, never internal values.
- Outbound SENDER routing (Roman 2026-08-25, rule of thumb): emailing teachers
  to acquire MULTIPLE students → sales seat (Danielle). Messaging FAMILIES →
  charter_sales seat (Paola). Contacting a teacher about a SPECIFIC student →
  charter_sales seat (Paola). Sender identity = from-name, reply-to, sign-off,
  and follow-up task owner.
- Outbound style (Roman 2026-08-24, locked): NEVER use em dashes (—) or double
  hyphens (--) in ANY customer-facing communication — emails, SMS, drafts,
  marketing copy. No exceptions. Use periods, commas, or parentheses.
  (Internal docs/code comments are fine.)
- Agent-property labeling (Roman 2026-08-14): any property an agent WRITES gets the
  `[Agent] ` label prefix and a description starting "AGENT PROPERTY — written by <script>".
  Humans must be able to tell agent-maintained fields from intake capture at a glance.
- Contact model: 5-persona system via `a_persona` (multi-select checkbox in the `master`
  group): Decision Maker/Director, Teacher of Record/EF/ES, Family, Tutors, Student.
- Family→TOR relationships are contact-to-contact associations with the paired label
  "Teacher of Record" (associationTypeId 15, USER_DEFINED; reverse "Family" = 14).
  The stamped text fields (teacher_of_record_name/email on family contacts) are legacy
  intake capture, not the source of truth.

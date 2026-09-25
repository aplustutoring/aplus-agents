# .claude — the shared brain

This folder is committed on purpose. It is how everyone who opens this repo in
Claude gets the same rules, the same skills, and the same guardrails, without
anyone copying anything off anyone's laptop.

| Path | What it is | Committed |
|---|---|---|
| `skills/` | How A+ does a thing. Claude loads one on its own when the work matches its description. | Yes |
| `commands/` | Slash commands you type, like `/council`. | Yes |
| `agents/` | Subagent definitions, for delegated work. | Yes |
| `settings.json` | Shared permissions. What any session here may run without asking, and what it may never run. | Yes |
| `settings.local.json` | Your own machine's settings. Personal, never shared. | No |
| `worktrees/` | Isolated checkouts for in-flight branches. | No |

## The skills

- **aplus-new-agent** — how to build and ship an agent here. The registry entry,
  the workflow conventions, the dry-run brakes, the ship checklist.
- **aplus-outbound-copy** — the locked rules for anything a family, teacher or
  tutor reads. Which line, which seat, what hours, what words.
- **aplus-hubspot** — how to read and write the CRM without breaking it.

You do not have to remember these exist. Claude reads each skill's description
and loads the right one when the work calls for it. You can also ask for one by
name.

## If you are new here

Start by reading `CLAUDE.md` at the repo root. It is the house rules and it is
loaded into every session automatically. Then `ARCHITECTURE.md` for the map, and
`docs/FLEET.md` for what is currently running.

## Adding to it

A new skill is a folder in `skills/` with a `SKILL.md` inside. The frontmatter
needs a `name` and a `description`, and the description is what decides whether
Claude loads it, so write it as the situations it applies to, not as a title.
Open a PR like any other change.

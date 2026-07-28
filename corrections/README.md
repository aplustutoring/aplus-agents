# corrections/

The agent feedback log — the fleet's training diet. Captures human corrections
to agent behavior (voice, facts, judgment, timing) so the fleet can learn from
them over time. This is the standing #AP008 feedback loop.

## How records get here

**#agent-feedback** (Slack) is the front door: any staff member posts a plain
freeform message ("the blog picked a weird topic again"), and the Feedback
Agent ([ops/feedback-agent/](../ops/feedback-agent/)) classifies it and opens
a PR adding one file here. Emily merges (draft probation); merging is what
accepts a correction into the log — and triggers the close-the-loop reply in
the reporter's thread. Hand-written corrections are welcome via the same PR
path and format.

## Format

One record per file: `corrections/<agent-id>/YYYY-MM-DD-<slug>.md`, where
`<agent-id>` is the agent's `registry.yml` id (`UNKNOWN/` for behavior that
maps to no registered agent — possible shadow automation).

```markdown
---
reporter: Danielle
reporter_slack_id: U0XXXXXXX
date: 2026-07-27
agent: email-triage
agent_label: Inbox triage
type: WRONG            # BROKEN | WRONG | ANNOYING | IDEA | DEMOTE
severity: normal       # critical | normal | low
channel: C0XXXXXXX
thread_ts: "1753657200.000100"
permalink: https://…slack.com/archives/…
status: open           # open | resolved (set by the close-loop workflow)
---

## Report (Danielle)

> the original message, quoted verbatim

## Classification

One-sentence neutral summary of the issue.
```

**FERPA rule (#AP008):** if a report quotes student/family specifics, the file
stores the thread permalink and a neutral summary — never the quoted content.

Reporter identity is attached (it's a public channel), but the weekly digest
aggregates by agent, not by person — the scoreboard tracks agents, not humans.

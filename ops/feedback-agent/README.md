# ops/feedback-agent — Feedback Agent v1 ("the doorbell for demotions")

One Slack channel — **#agent-feedback** — where anyone on staff tells the fleet
what's not working, in plain freeform messages. No @ required, no format, no
fields: the channel is the address, and zero syntax to remember is the adoption
feature. The agent does the sorting; humans never need to know which repo or
agent owns what.

This is the mechanism behind two standing promises:

- the `/corrections` feedback loop (#AP008) — every report becomes a
  structured correction file, the fleet's training diet;
- "anyone affected can demote an agent instantly" (#AP011) — the DEMOTE fast
  path, honored FIRST and reviewed after.

Staff only for v1 — tutors are not invited; their path stays through Mandy
until this agent graduates and Roman revisits.

## What happens when the doorbell rings

Every human top-level message in #agent-feedback fires `feedback-intake.yml`
via the Slack Events relay. Per message, the agent (posting as **@Fleet**):

1. **Acks in thread within ~1 minute, by name.** Reporter's first name comes
   from their Slack profile ("Danielle — got it, looking at the B2B email
   drafts"). Every later reply in that thread addresses them by name too — a
   report to the fleet is a person talking; the fleet answers like one. If the
   report is ambiguous: ONE clarifying question max, then it proceeds with its
   best read. It never argues with a reporter or defends an agent —
   corrections are data, not litigation.
2. **Classifies** against `registry.yml` (the manifest is the vocabulary):
   - `agent` — a registered agent id, or `UNKNOWN` (possible shadow
     automation → feeds the Zapier census);
   - `type` — `BROKEN` (errored) · `WRONG` (ran fine, bad judgment) ·
     `ANNOYING` (noisy/mistimed/tone-off) · `IDEA` · `DEMOTE` (explicit loss
     of trust — "turn it off," "stop it," "demote," or clear equivalent);
   - `severity` — `critical` (touching families/schools wrongly right now) ·
     `normal` · `low`.
3. **Routes:**
   - All types → correction file `corrections/<agent>/YYYY-MM-DD-<slug>.md`
     (reporter, quote, classification, thread link), opened as a PR that
     Roman merges.
   - `BROKEN` or `critical` → HubSpot ticket per #AP007
     (`[AGENT]` title, `ticket_source=agent_feedback`, `source_agent=<id>`)
     so it enters the re-ping ladder. Draft probation: the ready-to-create
     payload is posted in-thread for Roman to execute.
   - `DEMOTE` → the fast path, no debate, no triage: immediate thread
     confirmation ("*<agent>* dropped to Draft — nothing goes out without
     human approval until further notice"), Roman pinged (config
     `slack.alerts_to`), and a
     one-click registry PR flipping the agent to `probation: draft`. The
     reporter is never asked to justify first. Zaps registered to the agent
     (registry `zaps:` field) are listed for pausing; none registered means
     "cross-check the Zapier census."
4. **Closes the loop.** When a correction PR merges,
   `feedback-close-loop.yml` replies in the original thread — what changed,
   when. Feedback that vanishes into a void kills the channel within a month;
   the reply-back is the feature. ("A fix shipped" replies beyond the
   correction merge stay human/v2.)

Thread replies in the channel are ignored by intake (they're conversation),
except in threads @Fleet started with a clarifying question, where the
reporter's answer is read.

**Status command:** a top-level message of just "status" (or "fleet status",
"how's the fleet", "how are my agents") is answered, not filed — a thread
reply with today's fleet rundown: latest Actions run per workflow with
green/red and PT times, failures linked, open correction/demote PR counts,
and who's on Draft probation. Deterministic keyword match, so real reports
can't be swallowed by it.

**Friday ~4 PM PT** (`feedback-digest.yml`): one post in #agent-feedback —
counts by agent and type, unresolved corrections aging, and any agent with
≥3 `WRONG`/`ANNOYING` reports in 14 days flagged as a demotion-review
candidate for the demotion ledger. The same digest lands in
`state/digest-latest.md` as input to the Integrator's Monday brief. Digests
aggregate by agent, never by person — the scoreboard tracks agents, not
humans (reporter identity IS attached to corrections; it's a public channel).

## Non-negotiables

- Labels, never internal names, in everything the team sees (#AP014).
- Never argue with a reporter, never defend an agent in-thread.
- FERPA: if a report quotes student/family specifics, the correction file
  stores the thread link, not the quoted content (#AP008 channel rules).
  Claude flags this per report; the neutral one-line summary is kept.

## Probation plan (this agent's own ledger entry)

Ships at **Draft**:

- thread replies live (low risk, high value);
- correction files are PRs Roman merges;
- tickets are drafts posted in-thread for Roman;
- the DEMOTE path opens the registry PR and pings Roman to execute — it
  never merges it.

Classification + filing graduate to autonomous after **20 clean reports**
(correction PRs merged without human edits — tracked in state, progress in
every Friday digest, per #AP011 scaling). The DEMOTE registry-flip **stays
human-executed** until the Fleet Manager exists to verify state changes — a
feedback agent that can silently misfile a demotion is worse than none.

Live/dry-run gate: everything runs `--dry-run` until the repo variable
`FEEDBACK_AGENT_LIVE=true` (same pattern as `CALL_AGENT_LIVE`).

## Wiring the doorbell (one-time setup)

1. **Slack app** — DECIDED 2026-07-27: reuse the existing **aplus** app
   (bot `U0B4KMBBAKG`; already has `chat:write`, `users:read`,
   `channels:history`, `groups:history` — no new scopes, one bot token, the
   existing `SLACK_BOT_TOKEN` repo secret). Replies therefore post as
   **@aplus**; rename the app's bot display name to "Fleet" only if you
   accept the call agent's posts renaming too.
   - #agent-feedback is **private** (channel ID `C0BL05MCJ4B`) — so Event
     Subscriptions → subscribe to bot event **`message.groups`** (add
     `message.channels` too if the channel might ever flip public).
   - `/invite @aplus` into #agent-feedback (required for a private channel —
     events only reach apps whose bot is a member).
2. **Relay** ([relay/apps-script.gs](relay/apps-script.gs)): new Apps Script
   project → paste → Deploy → Web App (Execute as **me**, access **anyone**).
   Script Properties: `CHANNEL_ID` = `C0BL05MCJ4B`, `GITHUB_REPO` =
   `aplustutoring/aplus-agents`, `GITHUB_TOKEN` (fine-grained PAT, Contents
   read/write), `SLACK_VERIFICATION_TOKEN` (aplus app → Basic Information). Paste the Web App URL
   as the Slack app's Event Subscriptions **Request URL** (the script answers
   the verification challenge). Apps Script can't read request headers, so
   the legacy verification token — not the signing secret — is the auth
   check; the agent also dedupes Slack's retries by `event_id`.
3. **Repo settings:** Settings → Actions → General → enable **"Allow GitHub
   Actions to create and approve pull requests"** (correction/demote PRs).
   Secrets: `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, `HUBSPOT_API_KEY`
   (already present for sibling agents).
4. **Config:** ping routing lives in [config.yml](config.yml)
   `slack.alerts_to` — 2026-07-31 per Roman: everything routes to Roman.
   Member IDs live in `slack.people`.
5. **HubSpot:** ticket properties `ticket_source` and `source_agent` exist
   (created 2026-07-27, declared in
   [ops/hubspot-schema/properties.yml](../hubspot-schema/properties.yml)).
   Re-run the schema sync after registering a new agent so the
   `source_agent` dropdown picks it up.

## Testing (definition of done)

```
Actions → "Feedback agent — intake" → Run workflow
  text:    "The blog picked a weird topic again"
  user:    <your Slack member ID>
  channel: <#agent-feedback channel ID>
  dry_run: true
```

Expect in the log: classification (`agent=topic-gen type=WRONG`), the
name-first ack text, the correction file body, and the PR it would open. Then
set `dry_run: false` (with `FEEDBACK_AGENT_LIVE=true`) and confirm: thread ack
under a minute opening with your first name, a correctly classified correction
PR, and — for a DEMOTE test ("demote the call agent") — Roman pinged with the
one-click registry PR ready. Digest fires Friday with real counts
(`CHECK_ONLY=true` smoke mode verifies secrets without any reads/writes).

## Files

| Path | What |
| --- | --- |
| `feedback_agent.py` | intake / digest / close-loop modes |
| `config.yml` | channel, people, model, ticket + probation + digest knobs |
| `relay/apps-script.gs` | Slack Events → `repository_dispatch` doorbell |
| `state/state.json` | dedupe ids, pending clarifications, report log, graduation counter (committed back) |
| `state/digest-latest.md` | Friday digest copy for the Integrator's Monday brief |
| `../../.github/workflows/feedback-{intake,digest,close-loop}.yml` | the three triggers |

**V2 candidates:** @Fleet mentions anywhere route into the same intake
(report from the scene of the crime); tutors invited after graduation;
"fix shipped" close-the-loop beyond correction merges; zap auto-pause once
zaps are registered per agent.

# A+ Tutoring — Automation Fleet Architecture

The full map of A+'s automation. `registry.yml` is the machine-readable source of
truth; this file is the human-readable companion. **If the two disagree, the
registry is right and this file is stale** — fix it.

Last reconciled against `.github/workflows/` on 2026-08-20: 35 registered agents
(22 active · 10 manual · 3 deprecated), every workflow on disk registered, every
registered workflow present on disk.

## Sources of truth (data)

| System | Owns | Rule |
|---|---|---|
| **HubSpot** | **Families** — all family/contact information AND all communication (contacts, deals, tickets, conversations, blog posts, properties) | Where humans act. Authoritative for anything family- or comms-related. |
| **Teachworks** | **Lessons** — all lesson, scheduling, and attendance data | Authoritative for anything lesson-related. |

Engines sync **from Teachworks (lessons) into HubSpot (family record)**. No local
cache, sheet, or state file is ever authoritative over these two.

## The eight engines

Everything below lives in ONE repo — `aplustutoring/aplus-agents` — and runs on
GitHub Actions cron. No always-on machine. State is committed back to the repo by
the runs themselves, which is why the remote is routinely dozens of commits ahead
of any local checkout.

```
              ┌──────────────────────────────────────────────┐
              │  HubSpot (families + comms) · Teachworks     │
              └──────────────────────────────────────────────┘
   ┌──────────┬──────────┬─────────┴──────┬──────────┬──────────┐
   │          │          │                │          │          │
┌──┴───┐  ┌───┴────┐  ┌──┴─────┐  ┌───────┴──┐  ┌────┴────┐  ┌──┴──────┐
│ B2B  │  │  B2C   │  │ Email/ │  │   Data   │  │  Call   │  │Messenger│
│blogs │  │spotlgts│  │inbox   │  │   sync   │  │  agent  │  │         │
└──────┘  └────────┘  └────────┘  └──────────┘  └─────────┘  └─────────┘
 marketing  marketing    email/    ops/scorecard  ops/call_    ops/
                                                   agent      messenger

        ┌──────────────────┐         ┌────────────────────────┐
        │  Feedback agent  │         │   Fleet health         │
        │ ops/feedback-... │         │  ops/fleet-health      │
        └──────────────────┘         └────────────────────────┘
         how humans correct           retry sweeper, branch
         the fleet                    hygiene, schema sync
```

| Engine | Home | Trigger | What it does |
|---|---|---|---|
| **B2B blogs** | `marketing/scripts/b2b` | topic-gen Thu 5 PM · content-build Sat 8 AM · blog-metrics Mon 9 AM | Research → topic slate → HubSpot blog drafts + graphics → Slack |
| **B2C spotlights** | `marketing/scripts/b2c` | Drive-watcher event | Spotlight intake → case-study draft + graphics/reels/carousel → Slack to Paola |
| **Email / inbox ops** | `email/` | 15-min + hourly + daily/weekly reports | Triage admin@ + HubSpot Conversations · charter PO intake · deal sync to Teachworks · invoice sweep · draft-feedback learning loop |
| **Data sync** | `ops/scorecard` | Mon 8:55 / 9:00 / 10:00 AM PT | Teachworks → HubSpot/Monday/Sheets: missed lessons, retention, scorecard |
| **Call agent** | `ops/call_agent` | daily ~5:30 PM PT | JustCall transcripts → contact match → CRM writes, tasks, coaching scores, digest |
| **Messenger** | `ops/messenger` | manual · daily gated | Bulk email/SMS to a HubSpot list · campaign enrollment launcher |
| **Feedback agent** | `ops/feedback-agent` | Slack event · Fri digest | #agent-feedback → classify → correction PR → DEMOTE fast path |
| **Fleet health** | `ops/fleet-health`, `ops/hubspot-schema` | 20-min · Mon · manual | Retry sweeper · branch hygiene · HubSpot property/enum sync |

For the per-agent detail — every trigger, every read, every write — read
`registry.yml`. It is deliberately verbose so this file doesn't have to be.

## Autonomy: what acts alone, what waits for a human

This is the distinction worth keeping straight, and it does not map to engines.

**Writes to your systems without asking:** call-agent (CRM records, tasks,
tickets, notes), email-po-inbox (creates deals + contacts + associations),
email-deal-sync (creates Teachworks customers/students), the three scorecard
syncs, spotlight-orchestrator and content-build (blog *drafts*), campaign-launch
(workflow enrollments), feedback-fix (opens PRs).

**Drafts only — nothing leaves without a human:** email-triage (drafts every
reply; two locked exceptions — junk→archive, tutor_document→fixed receipt),
feedback-agent (`probation: draft`), bulk-messenger email (leaves a HubSpot
draft for Roman to send).

**Manual dispatch only:** hubspot-schema, messenger SMS, the log-sheet tools,
rerender-textstory, and the five charter/Teachworks analysis reports.

The `probation:` field in `registry.yml` is how an agent gets demoted to
draft-only — set by the feedback agent's DEMOTE path (#AP011), honored first and
reviewed after.

## Governance

Every engine is Tier A: versioned in GitHub · scheduled on Actions · state
committed back to the repo · secrets in Actions secrets · registered in
`registry.yml`. There is no Tier B — the last local-cron holdout (the sync
engine) migrated 2026-06-29.

Rules that bind every agent:

- **Registration:** if it's not in `registry.yml`, it doesn't exist. The registry
  is also the feedback agent's classification vocabulary and the DEMOTE path's
  target list — an unregistered agent cannot be reported against or paused.
- **Enumeration:** agents always read HubSpot option LABELS, never internal values.
- **Agent-property labeling:** any property an agent writes carries the `[Agent] `
  label prefix and a description starting "AGENT PROPERTY — written by <script>".
  Humans must be able to spot agent-maintained fields at a glance.
- **Roles, not names:** config keys, properties, and audit actions name roles
  (`charter_sales`), never people. The `staff:` block is the only home for names.
- **Timezone:** every workflow sets `TZ=America/Los_Angeles`. Human-facing output
  and date-window logic are Pacific; state cursors and audit logs are explicit
  UTC. Never hardcode a PT offset — use `ZoneInfo("America/Los_Angeles")`.
- **Concurrency:** branch/PR work happens in a git worktree, never in the shared
  checkout. Direct commits to `main` only when that is the session's sole surface.
- **Schema:** new HubSpot properties are declared in
  `ops/hubspot-schema/properties.yml` and synced by workflow — never created ad hoc.

## Known weak points (as of 2026-08-20)

Honest list. These are the ways the fleet has actually misled us, not theoretical.

1. **Green ≠ working.** A script that prints failures and exits 0 shows as a
   successful Actions run, and `fleet-retry` only reacts to non-zero exits. Live
   example: on 2026-08-18 `ops/messenger/enroll.py` failed all 50 enrollments
   (v4 flow id sent to the v2 enrollment endpoint → 404), failed to publish the
   emails (403) and failed to enable the workflow (400) — and reported success.
   The campaign only shipped because Roman did all three by hand in the portal.
   **Agents must exit non-zero when their actual job fails.**
2. **Registration drifts.** Nine live workflows ran unregistered until 2026-08-20,
   three of them writing to HubSpot and one opening PRs. Nothing enforced the
   registry's own first rule; it was caught by a manual audit.
3. **This file drifts.** It described a four-engine world for roughly seven weeks
   after email folded into this repo and three engines were added.

## Service accounts (two active — do not cross-wire)

| SA | Project | Used by | Key location |
|---|---|---|---|
| `spotlight-watcher@…` | `a-plus-spotlight-watcher` | B2C spotlights (Drive ingest + log sheet) | Actions secret `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` |
| `aplus-retention@…` | `a-plus-retention` | Data sync (Sheets) | Actions secret `RETENTION_SA_JSON` |

A third, `charter-prospecting@aplus-automations-cars`, is left over from a dropped
2026-06 charter experiment and is unused. Revoke its keys.

## Not built (deliberately)

**Charter prospecting / B2B sales engine.** Discussed — never built. No code, no
automation. What does exist is five manual, read-only-by-default charter analysis
reports (`scripts/` + `email/`), registered as `manual`. If a real charter engine
is ever built, it goes in as a fresh Tier-A engine with registry entries.

## Repos in the org

`aplus-agents` (this — all live automation) · `linkedin-skills` ·
`social-media-skills` · `aplus-tutor-resources` · `skills` (public). The last four
are skill/content libraries, not scheduled automation. The old `aplus-email` repo
was folded into `email/` here at the 2026-07-21 cutover.

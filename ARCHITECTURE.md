# A+ Tutoring — Automation Fleet Architecture

The full map of A+'s automation. `registry.yml` is the machine-readable source of
truth; this file is the human-readable companion.

## Sources of truth (data)

| System | Owns | Rule |
|---|---|---|
| **HubSpot** | **Families** — all family/contact information AND all communication (contacts, deals, tickets, conversations, blog posts, properties) | Where humans act. Authoritative for anything family- or comms-related. |
| **Teachworks** | **Lessons** — all lesson, scheduling, and attendance data | Authoritative for anything lesson-related. |

Engines sync **from Teachworks (lessons) into HubSpot (family record)**. No local
cache, sheet, or state file is ever authoritative over these two.

## The five engines

```
                         ┌────────────────────────────────────┐
                         │  HubSpot (families + comms)         │
                         │  Teachworks (lessons)               │
                         └────────────────────────────────────┘
        ┌──────────────┬───────────┴───────────┬──────────────┬──────────────┐
        │              │                        │              │              │
  ┌─────┴─────┐  ┌─────┴─────┐          ┌───────┴──────┐ ┌─────┴─────┐  ┌─────┴──────┐
  │ B2B blogs │  │ B2C       │          │ Email /      │ │ Data sync │  │ Charter    │
  │           │  │ spotlights│          │ inbox ops    │ │           │  │ prospecting│
  │ marketing │  │ marketing │          │ aplus-email  │ │ aplus-sync│  │ + sales    │
  │ repo, CI  │  │ repo, CI  │          │ repo, CI     │ │ local cron│  │ local      │
  └───────────┘  └───────────┘          └──────────────┘ └───────────┘  └────────────┘
   └──── Tier A: GitHub + Actions ──────────────────┘     └─── Tier B: local/manual ──┘
```

| Engine | Home | Trigger | What it does |
|---|---|---|---|
| **B2B blogs** | `aplus-marketing-skills/marketing` | Actions: topic-gen Thu 5pm, content-build Sat 8am, blog-metrics Mon 9am | Research → topic slate → HubSpot blog drafts + graphics + Slack |
| **B2C spotlights** | `aplus-marketing-skills/marketing` | Actions: Drive-watcher event | Student spotlight intake → case-study draft + graphics/reels + Slack |
| **Email / inbox ops** | `aplus-email` repo | Actions: triage (15min+hourly), SLA sweep (hourly), digests, deal-sync, PO inbox | Triage admin@ inbox + HubSpot Conversations → enrich → classify (Claude) → ticket + SLA + draft reply. Draft-only. |
| **Data sync** | `~/aplus-sync` (local) | **local crontab**, Mon 8:55/9:00/10:00 | Teachworks → HubSpot: scorecard, retention, missed-lessons |
| **Charter prospecting + sales** | `~/charter_tool` + `~/aplus-sync/charter` | **manual** | CDE pull → tier prospects → Drive sheet → email Danielle; create HubSpot deals |

## Service accounts (three, distinct — do not cross-wire)

| SA | Project | Used by | Key location |
|---|---|---|---|
| `spotlight-watcher@…` | `a-plus-spotlight-watcher` | B2C spotlights (Drive ingest + log sheet) | GitHub Actions secret `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` |
| `aplus-retention@…` | `a-plus-retention` | Data sync (Sheets) | `~/aplus-sync/service_account.json` |
| `charter-prospecting@…` | `aplus-automations-cars` | Charter prospecting (Sheets/Drive) | `~/charter_tool/service_account.json` |

## Governance tiers

- **Tier A (the target model):** `aplus-marketing-skills`, `aplus-email`.
  Versioned in GitHub · run on GitHub Actions cron (no always-on machine) · state
  committed back to the repo · secrets in GitHub Actions secrets · documented.
- **Tier B (fragile):** `aplus-sync`, `charter_tool`.
  Un-versioned local folders · run on a Mac's crontab / manually (if the laptop
  is asleep Monday, the sync silently doesn't run) · secrets are plaintext local
  files. As of 2026-06-26 both were moved out of iCloud-synced `~/Documents` and
  locked to `600`, but they remain Tier B.

## Migration plan — promote Tier B → Tier A

Goal: every engine versioned, scheduled in the cloud, secrets out of plaintext.

**Sync engine (`aplus-sync`) → `ops/scorecard/` (this repo) or its own repo**
1. `git init` the folder (or move scripts into `ops/` here). Commit code only —
   `.gitignore` already excludes `.env` + `service_account.json` + `.bak`.
2. Add GitHub Actions workflows mirroring the 3 cron lines
   (missed-lessons Mon 8:55, retention Mon 9:00, weekly Mon 10:00 PT).
3. Move secrets to GitHub Actions secrets: `TEACHWORKS_API_KEY`, `HUBSPOT_API_KEY`,
   `MONDAY_API_KEY`, `SLACK_WEBHOOK_URL`, and the `aplus-retention` SA JSON.
4. Verify a dry run in Actions, then **remove the 3 local crontab lines**.
5. Delete the local plaintext `.env` once Actions runs green.

**Charter engine (`charter_tool` + `aplus-sync/charter`) → own repo**
1. `git init`; commit code + `charter_prospects_template.xlsx`; ignore `input/`,
   `output/`, secrets.
2. Decide trigger: keep manual (`workflow_dispatch`) or schedule the prospecting
   pull (e.g. monthly) — CDE source URLs change annually, so a manual gate is fine.
3. Secrets → Actions secrets, including the `charter-prospecting` SA JSON.

**Cross-cutting**
- One `registry.yml` (this file's companion) stays the single fleet map.
- Optional hardening: rotate the three SA keys + the API tokens (deferred 2026-06-26).
- Consider consolidating the three GCP projects' SAs if scopes allow.

## Repos in the org
`aplus-marketing-skills` (this) · `aplus-email` · `linkedin-skills` ·
`social-media-skills` · `aplus-tutor-resources` · `skills` (public). The last
four are skill/content libraries, not scheduled automation.

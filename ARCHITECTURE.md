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
  │ marketing │  │ marketing │          │ aplus-email  │ │ ops/score-│  │ + sales    │
  │ repo, CI  │  │ repo, CI  │          │ repo, CI     │ │ card · CI │  │ops/charter │
  └───────────┘  └───────────┘          └──────────────┘ └───────────┘  └────────────┘
   └──── Tier A: GitHub + Actions ──────────────────────────────────┘    └ manual ──┘
                                                                  (versioned, run locally)
```

| Engine | Home | Trigger | What it does |
|---|---|---|---|
| **B2B blogs** | `aplus-agents/marketing` | Actions: topic-gen Thu 5pm, content-build Sat 8am, blog-metrics Mon 9am | Research → topic slate → HubSpot blog drafts + graphics + Slack |
| **B2C spotlights** | `aplus-agents/marketing` | Actions: Drive-watcher event | Student spotlight intake → case-study draft + graphics/reels + Slack |
| **Email / inbox ops** | `aplus-email` repo | Actions: triage (15min+hourly), SLA sweep (hourly), digests, deal-sync, PO inbox | Triage admin@ inbox + HubSpot Conversations → enrich → classify (Claude) → ticket + SLA + draft reply. Draft-only. |
| **Data sync** | `aplus-agents/ops/scorecard` | Actions: missed-lessons Mon 8:55, retention Mon 9:00, weekly Mon 10:00 PT | Teachworks → HubSpot/Monday/Sheets: scorecard, retention, missed-lessons |
| **Charter prospecting + sales** | `aplus-agents/ops/charter` | **manual** (run locally) | CDE pull → tier prospects → Drive sheet → email Danielle; school research; create HubSpot deals |

## Service accounts (three, distinct — do not cross-wire)

| SA | Project | Used by | Key location |
|---|---|---|---|
| `spotlight-watcher@…` | `a-plus-spotlight-watcher` | B2C spotlights (Drive ingest + log sheet) | GitHub Actions secret `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` |
| `aplus-retention@…` | `a-plus-retention` | Data sync (Sheets) | GitHub Actions secret `RETENTION_SA_JSON` (dormant local copy: `~/aplus-sync/service_account.json`) |
| `charter-prospecting@…` | `aplus-automations-cars` | Charter prospecting (Sheets/Drive) | `ops/charter/service_account.json` (gitignored; legacy copy in `~/charter_tool/`) |

## Governance tiers

- **Tier A (the target model):** `aplus-agents` (incl. the data-sync engine in
  `ops/scorecard`), `aplus-email`.
  Versioned in GitHub · run on GitHub Actions cron (no always-on machine) · state
  committed back to the repo · secrets in GitHub Actions secrets · documented.
- **Tier C (versioned, manual):** charter engine in `ops/charter`.
  Versioned + documented in the repo, but **run locally by a human, not on cron** —
  the prospecting pull needs hand-downloaded CDE files + annual URL checks and runs
  twice a year, so a headless schedule is the wrong target. Secrets live in a
  gitignored `ops/charter/.env`, not Actions secrets. This is the intended end state
  for charter, not a way-station to Tier A.
- **Tier B (fragile, being retired):** none active.
  As of 2026-06-29 both former Tier B engines are migrated: data-sync → `ops/scorecard`
  (Tier A) and charter → `ops/charter` (Tier C). The legacy folders `~/aplus-sync`
  (dormant scorecard fallback) and `~/charter_tool` (legacy charter inputs/SA) remain
  on disk only as backups and can be retired.

## Migration plan — promote Tier B → Tier A

Goal: every engine versioned, scheduled in the cloud, secrets out of plaintext.

**Sync engine (`aplus-sync`) → `ops/scorecard/` — ✅ DONE 2026-06-29**
Scripts live in `ops/scorecard/` (with a `CHECK_ONLY` CI smoke-test guard added);
the 3 workflows (`scorecard-{missed-lessons,retention,weekly}.yml`) run on Actions
and went green on 2026-06-29; secrets `TEACHWORKS_API_KEY`, `HUBSPOT_API_KEY`,
`MONDAY_API_KEY`, `SLACK_WEBHOOK_URL`, `RETENTION_SA_JSON` are repo secrets; the 3
local crontab lines were removed (backup at `~/aplus-sync/crontab-local-backup.txt`).
Remaining cleanup: after one clean Actions Monday, delete the dormant `~/aplus-sync`
scorecard copies + its plaintext `.env`/SA (the folder still hosts the charter engine,
so don't delete it wholesale). Optional: rotate the `aplus-retention` SA key + tokens.

**Charter engine (`charter_tool` + `aplus-sync/charter`) → `ops/charter/` — ✅ DONE 2026-06-29 (as Tier C)**
The 4 scripts (`charter_prospecting_pull`, `research_school`, `create_charter_deals`,
`pilibos_create_contact_properties`) + the prospect template are versioned in
`ops/charter/`, with `.gitignore` (excludes `input/`, `output/`, `.env`,
`service_account.json`), a `.env.example`, and a consolidated `README.md`. Trigger
stays **manual by design** (see Tier C above) — not promoted to Actions cron. Secrets
are a gitignored `ops/charter/.env` + `service_account.json`, not Actions secrets.
Remaining cleanup: retire the legacy `~/charter_tool` folder once a cycle is run from
`ops/charter`; optionally rotate the `charter-prospecting` SA key.

**Cross-cutting**
- One `registry.yml` (this file's companion) stays the single fleet map.
- Optional hardening: rotate the three SA keys + the API tokens (deferred 2026-06-26).
- Consider consolidating the three GCP projects' SAs if scopes allow.

## Repos in the org
`aplus-agents` (this) · `aplus-email` · `linkedin-skills` ·
`social-media-skills` · `aplus-tutor-resources` · `skills` (public). The last
four are skill/content libraries, not scheduled automation.

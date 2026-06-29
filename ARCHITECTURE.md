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

## The four engines

```
                    ┌────────────────────────────────────┐
                    │  HubSpot (families + comms)         │
                    │  Teachworks (lessons)               │
                    └────────────────────────────────────┘
        ┌──────────────┬───────────┴────────────┬──────────────┐
        │              │                         │              │
  ┌─────┴─────┐  ┌─────┴─────┐          ┌────────┴─────┐ ┌─────┴─────┐
  │ B2B blogs │  │ B2C       │          │ Email /      │ │ Data sync │
  │           │  │ spotlights│          │ inbox ops    │ │           │
  │ marketing │  │ marketing │          │ aplus-email  │ │ops/score- │
  │ repo, CI  │  │ repo, CI  │          │ repo, CI     │ │ card · CI │
  └───────────┘  └───────────┘          └──────────────┘ └───────────┘
   └──────────────── Tier A: GitHub + Actions ────────────────────────┘
```

(A fifth engine — **charter prospecting + sales** — has been discussed but **nothing
is built yet**: no code in the repo, no automation. See the note in `registry.yml`.)

| Engine | Home | Trigger | What it does |
|---|---|---|---|
| **B2B blogs** | `aplus-agents/marketing` | Actions: topic-gen Thu 5pm, content-build Sat 8am, blog-metrics Mon 9am | Research → topic slate → HubSpot blog drafts + graphics + Slack |
| **B2C spotlights** | `aplus-agents/marketing` | Actions: Drive-watcher event | Student spotlight intake → case-study draft + graphics/reels + Slack |
| **Email / inbox ops** | `aplus-email` repo | Actions: triage (15min+hourly), SLA sweep (hourly), digests, deal-sync, PO inbox | Triage admin@ inbox + HubSpot Conversations → enrich → classify (Claude) → ticket + SLA + draft reply. Draft-only. |
| **Data sync** | `aplus-agents/ops/scorecard` | Actions: missed-lessons Mon 8:55, retention Mon 9:00, weekly Mon 10:00 PT | Teachworks → HubSpot/Monday/Sheets: scorecard, retention, missed-lessons |

## Service accounts (two active — do not cross-wire)

| SA | Project | Used by | Key location |
|---|---|---|---|
| `spotlight-watcher@…` | `a-plus-spotlight-watcher` | B2C spotlights (Drive ingest + log sheet) | GitHub Actions secret `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` |
| `aplus-retention@…` | `a-plus-retention` | Data sync (Sheets) | GitHub Actions secret `RETENTION_SA_JSON` (dormant local copy: `~/aplus-sync/service_account.json`) |

> A third SA, `charter-prospecting@aplus-automations-cars`, exists in GCP from an
> earlier charter experiment but is **unused** (no charter engine is built). Revoke
> its keys if charter stays unbuilt.

## Governance tiers

- **Tier A (the target model):** `aplus-agents` (incl. the data-sync engine in
  `ops/scorecard`), `aplus-email`.
  Versioned in GitHub · run on GitHub Actions cron (no always-on machine) · state
  committed back to the repo · secrets in GitHub Actions secrets · documented.
- **Tier B (fragile, local):** none active.
  As of 2026-06-29 the data-sync engine — the last Tier B holdout — is migrated to
  `ops/scorecard` (Tier A). The charter idea was never built and has been dropped (no
  repo code, no automation). All four live engines are Tier A.

## Migration history — Tier B → Tier A (✅ complete)

Goal was: every engine versioned, scheduled in the cloud, secrets out of plaintext.
With the sync migration done and charter dropped, there is no Tier B left.

**Sync engine (`aplus-sync`) → `ops/scorecard/` — ✅ DONE 2026-06-29**
Scripts live in `ops/scorecard/` (with a `CHECK_ONLY` CI smoke-test guard added);
the 3 workflows (`scorecard-{missed-lessons,retention,weekly}.yml`) run on Actions
and went green on 2026-06-29; secrets `TEACHWORKS_API_KEY`, `HUBSPOT_API_KEY`,
`MONDAY_API_KEY`, `SLACK_WEBHOOK_URL`, `RETENTION_SA_JSON` are repo secrets; the 3
local crontab lines were removed (backup at `~/aplus-sync/crontab-local-backup.txt`).
The `~/aplus-sync` folder was emptied of code + plaintext secrets on 2026-06-29 (only
the crontab backup remains) and can be deleted. Optional: rotate the `aplus-retention`
SA key + tokens.

**Charter engine — ❌ dropped 2026-06-29 (never built).**
A short-lived migration into `ops/charter/` was backed out: charter has no live
automation set up, so there's nothing to version. The old experiment folders
(`~/charter_tool`, `~/aplus-sync/charter`) can be deleted. If charter is ever built
for real, do it as a fresh Tier-A engine and add it to `registry.yml` then.

**Cross-cutting**
- One `registry.yml` (this file's companion) stays the single fleet map.
- Optional hardening: rotate the two active SA keys + the API tokens (deferred 2026-06-26).

## Repos in the org
`aplus-agents` (this) · `aplus-email` · `linkedin-skills` ·
`social-media-skills` · `aplus-tutor-resources` · `skills` (public). The last
four are skill/content libraries, not scheduled automation.

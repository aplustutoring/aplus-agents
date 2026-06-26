# ops/scorecard — data sync (Teachworks → HubSpot / Monday / Sheets)

The data-sync engine, migrated from the local-cron folder `~/aplus-sync` into this
repo so it runs on **GitHub Actions** instead of a laptop's crontab (Tier B → Tier A).

Source-of-truth: **Teachworks** = lessons, **HubSpot** = families + communication.
These scripts read Teachworks and push into HubSpot / Monday.com / Google Sheets.
They are **stateless** — nothing is persisted between runs.

## Jobs (one workflow each, weekly)

| Script | Workflow | Schedule (PT) | Needs |
|---|---|---|---|
| `aplus_missed_lessons_sync.py` | `.github/workflows/scorecard-missed-lessons.yml` | Mon ~8:55 AM | TEACHWORKS, MONDAY |
| `aplus_retention_sync.py` | `.github/workflows/scorecard-retention.yml` | Mon ~9:00 AM | TEACHWORKS, SLACK_WEBHOOK, SA JSON |
| `aplus_weekly_sync.py` | `.github/workflows/scorecard-weekly.yml` | Mon ~10:00 AM | TEACHWORKS, HUBSPOT, MONDAY |

Crons are single fixed-UTC entries pinned to PDT (so winter runs ~1h earlier in PT —
harmless for a Monday-morning sync, and avoids the double-run a dual PDT/PST cron causes).

## Secrets (GitHub Actions repo secrets)
`TEACHWORKS_API_KEY`, `HUBSPOT_API_KEY`, `MONDAY_API_KEY`, `SLACK_WEBHOOK_URL`,
and `RETENTION_SA_JSON` (the full `aplus-retention@a-plus-retention` service-account
JSON; the retention workflow writes it to `service_account.json` at runtime).

## Safe testing (no production writes)
Each workflow has a `workflow_dispatch` toggle:
- **retention** → `dry_run=true` (built-in `DRY_RUN`: real reads, skips all writes).
- **weekly / missed-lessons** → `check_only=true` (`CHECK_ONLY` guard: confirms secrets
  are wired, then exits before any read/write — they have no dry-run mode).

## Provenance
Migrated 2026-06 from `~/aplus-sync` (previously `~/Documents/aplus-sync`, un-versioned,
local crontab). On cutover the 3 local crontab lines were removed. Cataloged in the
root `registry.yml`; architecture in `ARCHITECTURE.md`.

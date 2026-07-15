# ops/

Operational agents and infrastructure that keep HubSpot (the single source of
truth) and Teachworks in sync — distinct from `marketing/`, which generates
content.

## Subdirectories

- **`scorecard/`** — the data-sync engine (weekly scorecard, retention,
  missed-lessons). Migrated 2026-06 from the local-cron folder `~/aplus-sync`;
  runs on GitHub Actions. See `scorecard/README.md`.
- **`call_agent/`** — Call Agent v1: JustCall inbound-call transcripts →
  Claude summary → HubSpot Call engagement → daily Slack digest. Scheduled
  poller on GitHub Actions. See `call_agent/README.md`.
- **`hubspot-schema/`** — placeholder for the HubSpot property/schema management
  module (baseline properties + `create_properties.py`). Not present in this repo
  yet; reserved here so the structure exists when it lands (`.gitkeep` only).

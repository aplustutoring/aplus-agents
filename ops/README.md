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
- **`feedback-agent/`** — Feedback Agent v1 "the doorbell for demotions":
  #agent-feedback Slack channel → classify → correction PRs + ticket drafts +
  the #AP011 DEMOTE fast path; Friday digest. See `feedback-agent/README.md`.
- **`hubspot-schema/`** — the HubSpot property registry: `properties.yml`
  declares every custom property the fleet writes; `create_properties.py`
  syncs it into the portal (additive only). See `hubspot-schema/README.md`.

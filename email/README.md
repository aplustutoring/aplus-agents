# aplus_email_agent

Triages A+ Tutoring's company inbox (`admin@wetutorathome.com`, HubSpot Conversations,
portal 6312752). Runs on GitHub Actions cron — no always-on server. **Draft-only** except
two locked auto-actions: `junk` → archive, `tutor_document` → send a fixed receipt.

Per inbound email: identify the contact → enrich (HubSpot CRM + Teachworks, FERPA-safe
summary only) → classify with Claude Sonnet → open a HubSpot ticket (`Needs Approval`) →
route + SLA-clock → post the proposed reply as an internal COMMENT → Slack-DM the owner →
audit. A human approves and sends from HubSpot.

## Layout
- `src/` — `main.py` (triage), `sla_sweep.py`, `digest.py`, plus clients
  (`hubspot_client`, `teachworks_client`, `slack_client`, `monday_client`), `classifier.py`,
  `router.py`, `business_hours.py`, `audit.py`, `config.py`.
- `rules.md` — the classification brain (Claude reads it).
- `config.yaml` — routing table, SLA hours, owner/Slack ids, board/sheet ids.
- `.github/workflows/` — `triage.yml` (15-min business window + hourly), `sla_sweep.yml`
  (hourly), `weekly_digest.yml` (Mon 8 AM PT).
- `state/` — `cursor.json`, `audit_log.jsonl` (committed back by CI).

## Run locally
```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill it
.venv/bin/python -m pytest -q
DRY_RUN=true .venv/bin/python smoke_test.py
```

See **SETUP.md** for the one-time HubSpot / Monday / Slack / secrets configuration.

## Guardrails
- Only the email body + a structured enrichment summary go to Claude (FERPA). No raw
  student records, attendance histories, or attachments.
- The only outbound email is the tutor-doc receipt; any other send path raises.
- Junk archive is recoverable (never deletes). A message id already in the audit log is
  never reprocessed, even if the cursor is lost.

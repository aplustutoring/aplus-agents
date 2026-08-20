# Fleet health — Automation Audit v1

READ-ONLY census of every HubSpot workflow (8 years of accumulation) so Roman
can approve a kill list, a keep list, and an absorption backlog. This script
**never modifies, disables, or deletes anything** — it only issues GET requests
(plus HubSpot's documented read-only token-introspection call, which powers the
write-scope guardrail).

The Zapier half of the audit is manual (Zapier has no listing API) — see
[zapier-census.md](zapier-census.md).

## Auth

Set `HUBSPOT_AUDIT_TOKEN`. Doctrine-preferred: a **dedicated read-only private
app token**. Scopes: `automation` (read), `crm.objects.*.read`,
`crm.schemas.*.read`. Optional extras that improve reference verification:
`crm.lists.read`, `content` (marketing-email existence checks) — without them
those references report `unverifiable`, never guessed.

**Guardrail:** on startup the script introspects the token via
`POST /oauth/v2/private-apps/get/access-token-info` and **refuses to run** if
the token carries *any* write scope, or if scopes cannot be verified at all.
This is deliberately dumb (#AP008 dry-run spirit).

**Using the existing shared app token instead:** pass
`--accept-write-scoped-token` (or tick the checkbox on the Actions dispatch
form; CI falls back to the `HUBSPOT_API_KEY` secret when no audit token is
set). The refusal becomes a loud warning, and the override is stamped into
the run summary and the report banner. This stays safe because the HTTP
client structurally blocks every non-GET request — but the shared app must
have the **Automation (read)** scope granted, or the flows API returns 403;
add it in the private app's settings if missing.

## Run

```bash
pip install -r requirements.txt
HUBSPOT_AUDIT_TOKEN=pat-... python3 audit_hubspot_workflows.py
```

Offline pipeline check (no network, no token):

```bash
python3 audit_hubspot_workflows.py --selftest
```

Or dispatch `.github/workflows/automation-audit.yml` manually (needs the
`HUBSPOT_AUDIT_TOKEN` repo secret); the report lands as a run artifact.
Not scheduled — this is a census, not a monitor.

## Outputs

| File | What |
|---|---|
| `reports/automation-audit-YYYY-MM-DD.html` | Self-contained mobile-friendly report: headline numbers, kill list (checkbox worksheet), absorption backlog, keep list, registry diff, raw inventory |
| `reports/decision-log-draft.txt` | Drafted #AP015 / #AP016 / #AP017 entries in house format — **not sent**; Roman approves, then appends via the Zapier Google Docs pipe (param key `file`, doc ID pinned, `guessed` on the file field = failed write) |
| `runs/automation-audit-YYYY-MM-DD.json` | Machine-readable run summary (future Fleet Manager reads these) |

## What the flags mean (evidence, not verdicts)

| Flag | Trigger |
|---|---|
| `ZOMBIE` | enabled, zero enrollments in 180 days (proven via zero-ever + age; the API exposes no windowed stats) |
| `DORMANT` | disabled, last edited > 365 days ago (updatedAt proxy — API exposes no disabled-at) |
| `BROKEN` | references deleted properties / lists / stages / templates |
| `DUPLICATE` | ≥80 % identical trigger+action chain to a named twin |
| `FROZEN` | last edited > 2 years ago and still touches live schema |
| `MYSTERY` | no enrollments ever, or activity unknown + disabled |

Buckets (#AP016): `DOORBELL` (trigger→notify, keep) · `PLUMBING` (mechanical,
keep) · `DECIDER` (frozen judgment → absorption backlog, ranked) · `GUARDRAIL`
(deterministic safety logic — keep dumb, keep forever). Every classification in
the report shows the signals it was derived from so a human can re-bucket.

## Doctrine honored

- Read-only; write-scoped tokens refused (#AP008)
- Enumeration labels resolved, never internal values (#AP014)
- API parameter names verified against HubSpot docs, never guessed
- Evidence, not conclusions; humans approve all kills
- Anything the API doesn't expose is `unknown`, never guessed

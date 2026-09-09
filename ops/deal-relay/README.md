# deal-sync-relay — HubSpot deal events → deal-sync runs in ~1 minute

The worker from `ops/call_agent/webhook-relay` (PR #146), deployed a second
time with deal-sync vars. A HubSpot **private-app webhook** fires on deal
creation / deal-stage change → the relay coalesces the burst → one
`workflow_dispatch` on `email-deal-sync.yml` about a minute later. The
family's schedule text + What-to-Expect email go out minutes after their
deal exists, instead of whenever GitHub's cron deigns to run (2026-09-04:
Escandon and Taheri waited hours on go-live day).

Deal-sync polls from its own cursor and dedupes everything (audit log,
one-text-per-deal, one-per-family-24h), so duplicate / coalesced / dropped
dispatches are all harmless. Cron stays as a demoted backstop.

## How it is rung (2026-09-09)

The HubSpot side is the **`[Agent] Doorbell` workflow** (portal id 1881460299),
defined in `doorbell/workflow.json` and applied by `doorbell/apply_doorbell.py`:
deal created (createdate after 2026-09-09) or dealstage changed → POST to this
worker. It replaced README step 4 (the private-app webhook), which needs a
secret only Roman holds and had never been configured — `wrangler tail`
showed zero requests on deal creation a week after deploy. `email/src/
relay_watchdog.py` DMs the visionary seat if a cron run ever finds a new deal
older than 10 minutes, i.e. the doorbell stopped ringing.

Rotating `WEBHOOK_TOKEN` = `wrangler secret put WEBHOOK_TOKEN`, then re-run
`RELAY_WEBHOOK_TOKEN=<same> python3 doorbell/apply_doorbell.py`.

## One-time setup (Roman)

1. `cd ops/deal-relay && npx wrangler deploy`
2. `npx wrangler secret put GITHUB_TOKEN` — reuse the call-relay PAT
   (fine-grained, Actions read+write, this repo only)
3. `npx wrangler secret put WEBHOOK_TOKEN` — any long random string
4. (superseded by the Doorbell workflow above; kept for reference)
   HubSpot → Settings → Integrations → **Private Apps** → the agent's app →
   **Webhooks** tab:
   - Target URL: `https://deal-sync-relay.<your-subdomain>.workers.dev/call-completed?token=<WEBHOOK_TOKEN>&delay=1`
   - Subscriptions: **deal.creation** and **deal.propertyChange → dealstage**
5. Watch one deal: create/move any test deal; `email-deal-sync.yml` should
   run within ~2 minutes.

## After it's verified live

Demote the cron in `email-deal-sync.yml` from every-15-min to hourly (the
backstop), per the no-cron-unless-necessary rule. Leave that change until a
real deal has round-tripped through the relay.

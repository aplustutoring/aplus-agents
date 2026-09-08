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

## One-time setup (Roman)

1. `cd ops/deal-relay && npx wrangler deploy`
2. `npx wrangler secret put GITHUB_TOKEN` — reuse the call-relay PAT
   (fine-grained, Actions read+write, this repo only)
3. `npx wrangler secret put WEBHOOK_TOKEN` — any long random string
4. HubSpot → Settings → Integrations → **Private Apps** → the agent's app →
   **Webhooks** tab:
   - Target URL: `https://deal-sync-relay.<your-subdomain>.workers.dev/call-completed?token=<WEBHOOK_TOKEN>&delay=1`
   - Subscriptions: **deal.creation** and **deal.propertyChange → dealstage**
5. Watch one deal: create/move any test deal; `email-deal-sync.yml` should
   run within ~2 minutes.

## After it's verified live

Demote the cron in `email-deal-sync.yml` from every-15-min to hourly (the
backstop), per the no-cron-unless-necessary rule. Leave that change until a
real deal has round-tripped through the relay.

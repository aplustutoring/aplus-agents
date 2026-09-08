# call-agent-webhook-relay — event-driven trigger for the call agent

Cloudflare Worker that turns JustCall call events into `call-agent.yml`
workflow runs, minutes after each call, replacing the every-15-min poll crons
GitHub was mostly dropping (observed 2026-08-28: ~4 of ~50 daily crons fired;
Boston Powers' morning calls sat unprocessed for 8+ hours).

```
JustCall "call completed" webhook
        │
        ▼
Worker /call-completed ──(wait ~6 min for AI transcript)──► workflow_dispatch
        ▲                                                      │
        │                                                      ▼
Worker /redispatch ◄──(transcripts still pending, retry 10m)── call-agent run
```

The agent itself is untouched: each run still polls JustCall from its cursor
and dedupes via `state/state.json`, so duplicate, coalesced, or dropped
dispatches are all harmless. The daily ~5:30 PM PT digest cron remains and is
the backstop sweep — if the relay ever dies, calls are at most a day late, not
lost. Dispatches coalesce through a single Durable Object alarm, so a burst of
back-to-back calls produces one or two runs, not one per call.

## Deploy (one-time)

```bash
cd ops/call_agent/webhook-relay
npx wrangler deploy
npx wrangler secret put GITHUB_TOKEN    # see below
npx wrangler secret put WEBHOOK_TOKEN   # e.g. openssl rand -hex 24
```

1. **GITHUB_TOKEN** — fine-grained PAT (github.com → Settings → Developer
   settings → Fine-grained tokens): repository access = `aplustutoring/
   aplus-agents` only, permissions = **Actions: Read and write**, nothing
   else. Set a ≤1-year expiry and a calendar reminder to rotate.
2. **WEBHOOK_TOKEN** — any long random string. It rides in the query string of
   every URL below, and is the only thing gating who can trigger runs.
3. **JustCall webhooks** (dashboard → APIs and Webhooks → Webhooks). Add the
   Worker URL for these events:
   - *Call completed* → `https://<worker>/call-completed?token=<WEBHOOK_TOKEN>`
   - *Missed call* → `https://<worker>/call-completed?token=<WEBHOOK_TOKEN>&delay=1`
     (missed-call alerts are metadata-only — no transcript to wait for)
4. **GitHub repo secrets** (Settings → Secrets and variables → Actions):
   - `CALL_RELAY_URL` = `https://<worker>` (no trailing slash)
   - `CALL_RELAY_TOKEN` = the WEBHOOK_TOKEN value
   These power the workflow's transcript-retry step; if unset, retries fall
   back to the daily digest sweep.

Smoke test: `curl https://<worker>/health` → `ok`, then
`curl -X POST "https://<worker>/call-completed?token=<WEBHOOK_TOKEN>&delay=0"`
and confirm a `Call agent` run appears in Actions within ~a minute.

## How the delay works

`/call-completed` schedules a dispatch `DEFAULT_DELAY_MINUTES` (6) out —
JustCall's AI transcript lags the call by a few minutes. If a run still finds
calls inside `transcript_grace_minutes`, the agent writes
`state/retry_wanted` and the workflow POSTs `/redispatch?delay=10` for another
pass. All timing knobs: `DEFAULT_DELAY_MINUTES` in `wrangler.toml`, the
`?delay=` override on either route (clamped to 0–60).

## Consent guardrail — unchanged

The relay never reads call content; it doesn't even parse the webhook body.
Which calls get transcribed is still decided entirely inside `call_agent.py`
(`require_recording`, `monitored_numbers`).

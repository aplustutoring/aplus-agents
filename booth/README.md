# booth — Sage Oak BTSC 2026 photo booth

Event capture for the A+ photo booth: attendees pick a photo banner, choose
photo delivery, and opt in/out of A+ resources. Writes the four `events`-group
contact properties (PR #65, portal 6312752) and emails photos via Resend.

## Pieces

| File | What | Where it runs |
| --- | --- | --- |
| `worker.js` | Cloudflare Worker `sage-oak-booth` — `/submit` endpoint: upserts the HubSpot contact (events-group props) and sends the photo email | Cloudflare Workers |
| `index.html` | Booth front-end — deployed to Cloudflare Pages as `sage-oak-booth`; posts to the Worker (`CONFIG.WORKER_URL`) | Cloudflare Pages |
| `wrangler.toml` | Worker config: `RESEND_FROM`, `ALLOWED_ORIGIN` (the Pages URL) | — |

## Contact properties written (labels for dropdowns, per fleet rule)

- `aplus_event_tag` — value `sage_oak_btsc_2026` (multi-checkbox; future events append options)
- `aplus_booth_goal` — banner text (free text)
- `aplus_booth_delivery` — Email / Print / Both
- `aplus_marketing_consent` — Yes / No

## Deploy

```bash
cd booth
npx wrangler deploy                                  # Worker
npx wrangler secret put HUBSPOT_TOKEN                # HubSpot private app token
npx wrangler secret put RESEND_API_KEY               # Resend
npx wrangler pages deploy . --project-name sage-oak-booth   # Pages (index.html)
```

`ALLOWED_ORIGIN` in `wrangler.toml` must match the deployed Pages URL;
`CONFIG.WORKER_URL` in `index.html` must point at the deployed Worker's
`/submit` URL. Chicken-and-egg on first deploy: deploy the Worker, create the
Pages project, then set both values and redeploy.

## Every event booth gets a SUNSET (mandatory)

Any booth Worker with a `[triggers] crons` block **must** declare a `SUNSET`
var and guard its `scheduled()` handler on it. `booth/eo/worker.js` has the
reference implementation (`pastSunset`).

```toml
SUNSET = "2026-08-22"   # last day the scheduled handler does anything
```

```js
async scheduled(event, env, ctx) {
  if (pastSunset(env)) return;   // before any branch, any KV call, any send
  ...
}
```

Why this is a rule and not a suggestion: Cloudflare crons carry **no date
component**. `17 1 * * *` means 1:17 UTC *every day, forever*, and `* * * * *`
means every minute forever. A booth Worker does not stop when the event ends;
it stops when a human deletes the triggers.

We have already proved a checklist does not do that job. `booth/eo` shipped
with a post-event checklist that named this exact step, in bold, with the
words "load-bearing, not hygiene." Nobody ran it. The every-minute cron kept
firing for 19 days past the event, burning ~1,440 Worker invocations and
~2,750 KV list operations a day against a 1,000/day free cap, on a queue that
was empty the entire time. It surfaced only as Cloudflare limit emails, and
the Worker was still in `MODE = "send"` the whole time.

The checklist was correct and was ignored, so the sunset has to live where the
Worker reads it rather than where a person is supposed to remember it.

Rules that follow from that:

- Guard `scheduled()`, never `fetch()`. Photo URLs are written onto HubSpot
  timelines and must keep resolving after the event. Killing reads breaks
  every one of those links; killing crons breaks nothing.
- Fail **open** on an unparseable `SUNSET`: log loudly and keep running. A
  booth silently dead while the room is full costs far more than a cron that
  overstays a day.
- The `SUNSET` var does not replace teardown. Deleting the triggers, purging
  KV and archiving the `EVENT-TEMP` properties still happen. It means that
  when teardown slips, the bill and the blast radius stop anyway.
- Prefer no cron at all. Per the 2026-09-04 rule, agents are event-driven
  unless the work is inherently scheduled; a booth queue driven by the
  capture request needs no every-minute tick.

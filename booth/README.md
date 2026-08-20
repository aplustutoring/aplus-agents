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

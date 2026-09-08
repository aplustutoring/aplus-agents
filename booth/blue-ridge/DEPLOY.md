# Blue Ridge BTSC 2026 — "Spin Back to School" booth

Prize wheel that gates the prize behind lead capture. Visitor spins, lands on a
prize, enters their info to claim it, and shows the claim screen to booth staff.

Modeled on `booth/` (Sage Oak BTSC 2026). Same HubSpot upsert shape, same idle
reset, same graceful-failure behavior. **No email, no MMS, no print** — the
prize is physical and handed over at the table.

| File | What | Runs on |
| --- | --- | --- |
| `worker.js` | Worker `blue-ridge-booth` — `POST /submit`, HubSpot upsert only | Cloudflare Workers |
| `spin-back-to-school.html` | Booth front end; posts to `CONFIG.WORKER_URL` | Cloudflare Pages |
| `wrangler.toml` | `ALLOWED_ORIGIN` (the Pages URL) | — |
| `test-worker.mjs` | `node booth/blue-ridge/test-worker.mjs` | local / CI |

## Order of operations (the schema gate)

**The properties PR must merge and sync BEFORE go-live.** `create_properties.py`
does not run until then, per manifest doctrine.

1. Merge the properties.yml PR (3 enum options + `aplus_booth_prize`)
2. Run `.github/workflows/hubspot-schema.yml` — **dry run first**, confirm the
   plan is exactly 1 create + 2 option updates, then run it live
3. Deploy the Worker and Pages (below)

Deploying out of order does not lose leads: an unsynced property comes back as
`PROPERTY_DOESNT_EXIST`, and the Worker drops that key and retries so the
contact is still captured. You lose the prize/role stamp, not the person.

## Deploy

```bash
cd booth/blue-ridge
npx wrangler deploy                                            # Worker
npx wrangler secret put HUBSPOT_TOKEN                          # private app token
npx wrangler pages deploy . --project-name blue-ridge-booth    # Pages
```

Chicken-and-egg on first deploy, same as Sage Oak: deploy the Worker, create the
Pages project, then set `ALLOWED_ORIGIN` in `wrangler.toml` and
`CONFIG.WORKER_URL` in the HTML, and redeploy both.

The HubSpot private app token needs **crm.objects.contacts read AND write** —
read matters here because the event tag is merged, not overwritten.

## Contact properties written

| Property | Written as | Note |
| --- | --- | --- |
| `aplus_event_tag` | `blue_ridge_btsc_2026` | multi-select, **append-only** (#AP032) |
| `aplus_event_role` | `teacher` / `parent` / `student` | internal VALUES, never labels |
| `aplus_marketing_consent` | `"true"` / `"false"` | strings, not booleans |
| `aplus_booth_prize` | prize name | EVENT-TEMP, not a KEEPERS property |
| `a_persona`, `hs_lead_status` | create-only | never overwritten on an existing contact |

Two things this build fixes relative to Sage Oak:

- **Enum values, not labels.** The Sage Oak build wrote labels and HubSpot
  silently rejected them. `test-worker.mjs` asserts no human-facing label ever
  appears in a write payload, for every role.
- **Append-only event tag.** `aplus_event_tag` is `fieldType: checkbox`, so a
  flat PATCH replaces the whole set. Sage Oak wrote it flat, which was fine as
  the only event and wrong the moment a second exists. This Worker reads the
  current value and unions. A teacher who came to Sage Oak ends up carrying
  both tags.

## Booth-staff behavior

- Idle reset returns to the attract screen after `IDLE_RESET_MS`, and the claim
  screen auto-resets after `DONE_RESET_MS`. Both clear all visitor data.
- If the Worker call fails, the claim screen still shows so the visitor gets
  their prize. The capture is queued in `localStorage` under
  `blueridge_pending` and retried on the next successful submit — check that key
  at end of day before tearing the booth down.
- Staff may fill the form in on a visitor's behalf. Tap targets are sized for
  that; the `@theblueridgeacademy.com` button exists because both `nikki@` and
  `firstname.lastname@` formats are already in HubSpot, so staff type the local
  part and tap to append.

## Not used here

`aplus_booth_goal`, `aplus_booth_delivery`, `aplus_booth_photo_url` are photo-
booth specific and are deliberately untouched. `aplus_booth_goal` in particular
must not be overloaded to hold the prize — the test asserts the Worker never
references any of the three.

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
| `pages-dist.sh` | builds `.pages-dist/` = HTML + `_redirects`, the ONLY files Pages uploads | local / CI |
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

Two ways, same result. Prefer the workflow: it runs the tests first, so a
wheel label the Worker does not accept never reaches the booth.

**From GitHub (no laptop needed).** Actions -> "Blue Ridge booth deploy
(manual)" -> Run workflow. Leave `dry_run` on for the plan, then run it again
with `dry_run` off. It deploys the Worker and Pages and then fetches
`blue-ridge-booth.pages.dev` to confirm the live page really carries the
build. One-time setup: add repository secrets `CLOUDFLARE_API_TOKEN` (scoped
to Workers Scripts:Edit and Pages:Edit) and `CLOUDFLARE_ACCOUNT_ID`.

**From a laptop.**

```bash
cd booth/blue-ridge
node test-worker.mjs                                           # gate
npx wrangler deploy                                            # Worker
npx wrangler secret put HUBSPOT_TOKEN                          # private app token, once
sh pages-dist.sh                                               # HTML + _redirects only
npx wrangler pages deploy .pages-dist --project-name blue-ridge-booth --branch main   # Pages (production)
```

Never `pages deploy .` from this directory. Pages uploads every file it is
given and ignores `.assetsignore` (a Workers static-assets feature, not a
Pages one), so a `.` deploy publishes `worker.js`, `wrangler.toml` and this
file. `pages-dist.sh` builds the upload from an allowlist instead, and the
workflow's verify step fails the run if any source file answers 200.
`--branch main` matters: wrangler infers the branch from git, so a deploy
from a worktree or feature branch lands on a preview alias, not production.

Deploy BOTH whenever the prize list changes. The wheel labels live in the
HTML and the whitelist lives in the Worker, so a Pages-only deploy ships a
prize the Worker then drops.

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

## Where a claim goes

The page picks its capture route at load, by feature detection, never by
hostname. The same file ships to both places.

| Opened from | Route | Notes |
| --- | --- | --- |
| `blue-ridge-booth.pages.dev` (the booth) | `POST` to the Worker, HubSpot upsert | unchanged behavior |
| a claude.ai artifact link (preview / backup tablet) | the artifact's own store | the Worker refuses cross-origin calls, so claims are kept with the page and pushed to HubSpot afterwards |

Either way a claim that cannot be sent is written to `localStorage` under
`blueridge_pending` and retried on the next successful send.

**Booth staff panel:** five taps on the footer line of the wheel screen. It
shows the capture route, every claim captured on that device, and a Download
CSV button. Use it to confirm claims are landing without leaving the table,
and to carry the day home if the route was the artifact store. It closes on
the idle reset like every other screen, so it never sits open in front of a
visitor.

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
  part and tap to append. `@gmail.com`, `@outlook.com` and `@yahoo.com` sit
  directly under the email field as three equal-width chips for families; the
  staff button is the full-width navy bar BELOW them (Roman 2026-09-16:
  families are most of the traffic, staff know where their button is). Any of
  them replaces whatever follows the `@`, so a wrong pick is one more tap, not
  a backspace. Laid out and tap-tested at iPad portrait (768x1024) and
  landscape (1024x768).
- Phone is optional by design. A visitor with no phone still claims the prize.
- The email field carries a no-spam line and the phone field a matching hint.
  If the promise there ever stops matching what we actually send, change the
  sending, not the line.

## The prize list

`categories` in `spin-back-to-school.html` and `PRIZES` in `worker.js` must
hold the same four names: **Bookmark Scratcher, Pop-it, Squishy Pen, Stickers**.
The wheel repeats them so the 8 segments alternate color. A name on the wheel
but not in `PRIZES` is dropped at write time and the visitor's prize never
reaches `aplus_booth_prize`, silently. `test-worker.mjs` compares the two
lists, so changing prizes means changing both files and rerunning the tests.

## Not used here

`aplus_booth_goal`, `aplus_booth_delivery`, `aplus_booth_photo_url` are photo-
booth specific and are deliberately untouched. `aplus_booth_goal` in particular
must not be overloaded to hold the prize — the test asserts the Worker never
references any of the three.

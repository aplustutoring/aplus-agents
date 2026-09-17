# booth — the A+ photo booth (Sage Oak BTSC 2026, Ceja Park Day 2026)

Event capture for the A+ photo booth: attendees pick a photo banner, take a
framed photo, choose delivery (print / email / text), and opt in or out of A+
resources. Writes the `events`-group contact properties (portal 6312752),
emails photos via Resend, texts them via JustCall MMS, prints on the Selphy.

## One Worker, one row per event

The Worker is named `sage-oak-booth` after the first event it served and keeps
that name on purpose: its four secrets and the KV photo archive live with the
name. A new event is a row in `worker.js` `EVENTS` (all the copy: email
subject, SMS body, timeline note, default role) plus a page under `public/`,
never a new Worker with secrets to re-enter the morning of the event.

| Event | Tag | Page | Served from |
| --- | --- | --- | --- |
| Sage Oak BTSC 2026 | `sage_oak_btsc_2026` | `index.html` | Cloudflare Pages `sage-oak-booth` (historical) |
| Ceja Park Day 2026 | `ceja_park_2026` | `public/ceja/index.html` | the Worker itself via `[assets]`: https://sage-oak-booth.nameless-mountain-bafa.workers.dev/ceja/ |

`GET /` on the Worker redirects to `/ceja/`, so the tablet can open the bare
Worker URL. The page posts to `/submit` same-origin, so CORS never enters into
it. (Delilah lesson, 2026-09-10: a Pages project and a Worker of the same name
collide on current wrangler; serve new event pages from the Worker.)

## Pieces

| File | What | Where it runs |
| --- | --- | --- |
| `worker.js` | Cloudflare Worker `sage-oak-booth`: `POST /submit` upserts the HubSpot contact (append-only event tag, #AP032), archives the photo in KV, sends email and/or MMS. `GET /photo/<key>` serves the archive. | Cloudflare Workers |
| `public/ceja/index.html` | Ceja booth front end; everything that names the event is in its `CONFIG` block | served by the Worker |
| `index.html` | Sage Oak booth front end (historical) | Cloudflare Pages |
| `wrangler.toml` | `ALLOWED_ORIGIN` (comma-separated), `RESEND_FROM`, `JUSTCALL_FROM`, owner seats, `[assets]` | — |
| `test-worker.mjs` | `node booth/test-worker.mjs` | local / CI |

## Contact properties written

- `aplus_event_tag`: the event's tag, APPENDED to whatever is there (#AP032)
- `aplus_event_role`: `parent` / `teacher` / `student` / `administrator` / `support_staff` (internal VALUES, never labels)
- `aplus_booth_goal`: banner text
- `aplus_booth_delivery`: `email` / `print` / `text` / `all`
- `aplus_marketing_consent`: `"true"` / `"false"`
- CREATE-ONLY: `a_persona` by role (parent -> Family, teacher -> TOR, student -> Student), `hs_lead_status` for teachers, and `hubspot_owner_id` by seat (teachers and staff -> sales, families -> charter sales). An existing contact is never re-personaed or reassigned.

If the schema has not been synced yet (a new tag option), HubSpot rejects the
tag and the Worker retries the write without it, so the contact is still
captured; the response carries `dropped: ["aplus_event_tag"]` so it shows in
`wrangler tail`.

## Ceja Park Day 2026: what is different from Sage Oak

More parents than teachers, so: the role pills are Parent, Teacher, Student
with Parent first; `@gmail.com` / `@outlook.com` / `@yahoo.com` are one-tap
chips on the email field (a chip replaces whatever follows the `@`); the email
field carries a no-spam line; the phone field is optional and says it is only
for texting the photo. Print is the first delivery card. Consent copy speaks
to a parent about their student. No em dashes anywhere a family reads.

The event name, card header, banner choices and an optional partner logo are
all in `public/ceja/index.html` `CONFIG`. To rename the event or drop in a
partner logo, edit that block only.

## Deploy

The Worker is already deployed with its secrets and KV. Shipping Ceja is one
command from a machine where wrangler is logged in (Roman's Mac):

```bash
cd booth
node test-worker.mjs          # the gate
npx wrangler deploy           # Worker + the public/ pages together
```

Then open https://sage-oak-booth.nameless-mountain-bafa.workers.dev/ on the
iPad; it lands on `/ceja/`. Before the schema sync has run, submissions still
capture (see above); after it, the event tag lands too.

**Schema gate:** `ops/hubspot-schema/properties.yml` gains the
`ceja_park_2026` option on `aplus_event_tag`. Merge, then run
`.github/workflows/hubspot-schema.yml` (dry run first: expect exactly one
option add).

**Day-of on the iPad:** Settings > Safari > Camera > Allow for the Worker
host. Add `/ceja/` to the Home Screen so it runs full screen. Printing goes
through the iPad print dialog to the Selphy over AirPrint, 4x6 (the card is
2:3, 1200x1800). One test print before the first family.

### First-time deploy of a NEW Worker (not needed for Ceja)

```bash
npx wrangler deploy
npx wrangler secret put HUBSPOT_TOKEN
npx wrangler secret put RESEND_API_KEY
npx wrangler secret put JUSTCALL_API_KEY
npx wrangler secret put JUSTCALL_API_SECRET
```

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

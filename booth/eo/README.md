# booth/eo — EO LA Valley "Minion #23" booth agent

**EVENT-TEMP. One night: Thursday 2026-08-20, 6:15–8:15 PM PT. Sunset 2026-08-22.**

Attendees get a photo. Twenty minutes later their phone buzzes three times
with research on their own company. At 8:00 PM a superhero portrait of them
arrives. Every attendee-facing message signs as **Minion #23 🤖** and carries
no A+ branding anywhere — the mystery is the demo.

## Pieces

| File | What | Runs on |
| --- | --- | --- |
| `index.html` | Booth front-end (Cloudflare Pages, `eo-booth`). Camera, 4-field form, demo-consent checkbox, and the Selphy AirPrint call. | iPad Safari |
| `worker.js` | Worker `eo-booth` — `/capture`, `/photo/<key>`, `/sms`, plus the two cron payloads | Cloudflare Workers |
| `wrangler.toml` | Vars, KV binding, both cron triggers | — |

Layout and CSS are cloned from `booth/` (Sage Oak); only the palette, copy,
and flow changed.

## The three beats

**Beat 1 — instant, and never blocked by anything else.** Print fires on the
iPad before the network is even touched. The Worker then upserts the HubSpot
contact, emails the photo, and sends one photo MMS. That MMS is the only
message that carries the opt-out line.

**Beat 2 — Payload #1 at 6:17 PM PT.** Three texts ~30 seconds apart, then the
research-brief email. Sent in three waves so the whole room's phones buzz
together — that is the effect on stage.

**Beat 3 — Payload #2 at 8:00 PM PT.** Hero-image MMS plus a Claude-composed
closing email that calls back to the earlier brief.

Between beats 1 and 2, `waitUntil()` does the slow work: Claude researches the
company (web search), Gemini generates the hero image from the selfie, both
images go to Crystal's Drive folder, and a clock check catches anyone who
walked up *after* 6:17 and sends them Payload #1 immediately.

## Consent and opt-out

Two separate things, deliberately:

- **`eo_demo_consent`** — a booth checkbox: *"You may use my number in
  tonight's live demo."* Only `true` contacts get the Payload #1 triple text
  and the Payload #2 MMS. Everyone gets their photo and every email regardless,
  so declining costs the attendee nothing.
- **STOP / UNSUBSCRIBE** — inbound on the booth line writes an `optout:` key in
  KV and excludes that number from **all** further SMS/MMS. Email still sends.

The opt-out line appears exactly once per person, on the first photo MMS.

## Failure behavior

| Fails | Result |
| --- | --- |
| Research | Retry once, then a graceful generic brief that still reads well aloud |
| Hero image | Retry once, then `eo_hero_image_url` stays empty and Payload #2 sends text-only with the superhero sentence removed — no apology, no gap |
| Drive upload | Logged, never surfaced |
| Payload #2 email compose | Falls back to a static body |

Beat 1 is sacred: nothing above can delay or block the photo.

**Double-send guard.** `eo_payload1_sent` is stamped *before* the triple text
goes out, by both the cron and the instant path. A contact captured while cron
A is mid-run sees the stamp and stands down. One send per human — a double
text here reads as a bug and kills the reveal.

## Deploy

```bash
cd booth/eo
npx wrangler deploy
npx wrangler pages deploy . --project-name eo-booth
```

Then set the seven secrets (`wrangler secret put HUBSPOT_TOKEN`,
`RESEND_API_KEY`, `JUSTCALL_API_KEY`, `JUSTCALL_API_SECRET`,
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `ZAPIER_IDEAS_HOOK`).

`ALLOWED_ORIGIN` in `wrangler.toml` must match the deployed Pages URL, and
`CONFIG.WORKER_URL` in `index.html` must match the Worker's `/capture` URL —
chicken-and-egg on a first deploy, same as the Sage Oak booth.

Sync the six event-temp properties first:

```bash
python3 ops/hubspot-schema/create_properties.py
```

## Before you flip MODE to send

Four things are unverified and will silently break sends if they are wrong:

1. **The booth number.** `JUSTCALL_FROM` is `+18185736258`, not the main A+
   line. Confirm it exists in JustCall and is MMS-verified — unverified MMS
   senders fail without a useful error.
2. **The inbound webhook payload.** `handleInboundSms` reads several possible
   field names because JustCall's shape varies by webhook version. Send one
   real text and check the logs before trusting it.
3. **The Resend sender.** `minion23@wetutorathome.com` — the domain is
   verified, but confirm the display name does not resolve to an A+ signature
   anywhere in the mail client.
4. **The two Claude system prompts** in `worker.js` are drafts standing in for
   Deliverable ③. Read them aloud before locking them.

## Test plan

1. `MODE=dry_run`. Roman captures himself through the booth. Verify: HubSpot
   upsert with tag + company + consent, print, email, MMS logged, brief lands
   in ≤3 min **and reads great aloud**, hero image has his actual face, both
   files in Crystal's Drive folder.
2. Temporarily set cron A to +5 min, `MODE=send`, Roman's contact only. Triple
   text arrives in order with the stagger, email arrives, flag stamped.
3. Capture a second test contact **after** cron A fires. Instant path sends
   immediately, no double-send.
4. `npx wrangler trigger` cron B. Hero MMS + composed email arrive. Blank
   `eo_hero_image_url` on one contact and re-run: text-only fallback is seamless.
5. Text an idea to the booth line. Row appears in the Sheet, auto-reply lands.
   Text STOP from a burner and confirm exclusion from later sends.
6. Reset: clear test flags and contacts, restore `17 1 * * *` and `0 3 * * *`,
   confirm `MODE = "send"`, redeploy.

## Post-event checklist (Aug 21+)

- [ ] Export any contacts worth keeping
- [ ] Delete the `eo_lav_agents_2026` contacts
- [ ] Delete both crons from `wrangler.toml` and redeploy — **Cloudflare crons
      have no date component**, so `17 1 * * *` fires again every single day
      until it is removed. This is load-bearing, not hygiene.
- [ ] Disable the JustCall inbound webhook on the booth line
- [ ] Purge the `eo/` and `optout:` keys from the shared KV namespace
- [ ] Archive the six `eo_*` properties via the properties.yml retire process
- [ ] Delete the `eo-booth-agent` entry from `registry.yml`, regenerate
      `docs/FLEET.md`

## Known deviations from the build brief

Three, all deliberate, all explained where they live in the code:

- **Gemini, not Higgsfield.** The brief said the Higgsfield key "already
  exists in this stack — the case-study video agent uses it." It does not.
  Both places Higgsfield appears in this repo name it as something the code
  deliberately avoids, because it is a connected app that will not run
  headless and cannot be called from a Worker. Gemini is already the proven
  image path here, including the reference-image face-lock technique.
- **Printing is client-side.** The brief put "Selphy AirPrint job" in the
  Worker pipeline. A cloud Worker has no LAN access. Printing stays in
  `index.html` via `window.print()`, which is how the Sage Oak booth already
  worked.
- **Consent checkbox added.** Not in the original brief; added at Roman's
  direction so the triple text goes only to people who agreed to be part of
  the demo.

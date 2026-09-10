# booth/delilah — Delilah's 5th birthday + Rosh Hashanah 5787 (2026-09-11)

Personal home-party photo booth. iPad on a stand, Canon Selphy over AirPrint.
Every kept photo prints automatically (the party favor); guests can optionally
type a cell number to get the photo texted as well.

Forked from `booth/` (Sage Oak) with HubSpot, email, consent and roles removed.
No cron, so no SUNSET is needed: nothing runs unattended.

| File | What | Where it runs |
| --- | --- | --- |
| `index.html` | Booth front-end (camera, countdown, framed 1200x1800 print, name+phone, auto-print, host album) | Cloudflare Pages `delilah-booth` |
| `worker.js` | `POST /submit` archives the photo in KV and texts it via JustCall MMS; `GET /photo/<key>`; `GET /photos` | Cloudflare Worker `delilah-booth` |
| `wrangler.toml` | Worker vars: `ALLOWED_ORIGIN`, `JUSTCALL_FROM`, `SMS_BODY` | |
| `test-worker.mjs` | `node test-worker.mjs` | |

## Host controls

- **Album / reprints:** on the start screen, press and hold the top-right corner
  for about a second. Every archived photo shows with a Reprint button, plus
  Print all.
- **Auto-print off:** set `AUTO_PRINT: false` in `CONFIG` inside `index.html`.

## Sender number

Roman asked for "the 6793 number". No JustCall number ends in 6793. The Worker
sends from 818-573-6293 ("Roman's line", MMS-capable, same number the EO booth
used). Change `JUSTCALL_FROM` in `wrangler.toml` and redeploy if that is wrong.

## Deploy

```bash
cd booth/delilah
npx wrangler kv namespace create DELILAH_PHOTOS      # paste id into wrangler.toml
npx wrangler deploy
npx wrangler secret put JUSTCALL_API_KEY
npx wrangler secret put JUSTCALL_API_SECRET
npx wrangler pages project create delilah-booth --production-branch main
npx wrangler pages deploy . --project-name delilah-booth
```

## Day-of checklist

1. iPad: Settings > Safari > Camera > Allow for delilah-booth.pages.dev. Add the
   page to the Home Screen so it runs full-screen.
2. Selphy on the same Wi-Fi. First print: pick the Selphy in the iOS print sheet,
   paper size 4x6 (Postcard), then it stays selected.
3. Take one test shot, confirm the print and the text arrive.
4. After the party: `GET /photos` on the Worker lists every archived shot for a
   family album; nothing needs tearing down.

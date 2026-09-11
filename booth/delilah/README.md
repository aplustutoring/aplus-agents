# booth/delilah — Delilah's 5th birthday + Rosh Hashanah 5787 (2026-09-11)

Personal home-party photo booth. iPad on a stand, Canon Selphy over AirPrint.
Every kept shot produces TWO prints (the party favors): the real photo, and a
storybook version where Gemini repaints the guests into a Rosh Hashanah
pomegranate orchard with faces preserved. Guests can optionally type a cell
number to get both texted as well.

Forked from `booth/` (Sage Oak) with HubSpot, email, consent and roles removed.
No cron, so no SUNSET is needed: nothing runs unattended.

| File | What | Where it runs |
| --- | --- | --- |
| `public/index.html` | Booth front-end (camera, countdown, framed 1200x1800 prints, name+phone, auto-print, host album) | served by the Worker (`[assets]`) |
| `worker.js` | `POST /submit` archives a print in KV, mirrors it to Google Drive, texts it via JustCall MMS; `POST /storybook` sends the un-framed capture to Gemini and returns the repaint; `POST /drive-backfill`; `GET /photo/<key>`; `GET /photos` | Cloudflare Worker `delilah-booth` |
| `wrangler.toml` | Worker vars: `ALLOWED_ORIGIN`, `JUSTCALL_FROM`, `SMS_BODY`, `STORYBOOK_SMS_BODY`, `GEMINI_MODEL`, `DRIVE_FOLDER_ID` | |
| `test-worker.mjs` | `node test-worker.mjs` | |

## Host controls

- **Album / reprints:** on the start screen, press and hold the top-right corner
  for about a second. Every archived photo shows with a Reprint button, plus
  Print all.
- **Auto-print off:** set `AUTO_PRINT: false` in `CONFIG` inside `public/index.html`.
- **Storybook off:** set `STORYBOOK: false` in the same `CONFIG` (one print per guest again).

## Storybook print (favor 2)

Flow per guest: real photo prints and is texted, then a "Painting your storybook"
screen while the Worker calls `gemini-3.1-flash-image` with the capture as a
reference image and the prompt in `worker.js` (`STORYBOOK_PROMPT`). About 10 s.
The page frames the result in the same card with the banner "Once upon a Shana
Tova", prints it, archives it (`kind: storybook` in the album) and texts it with
`STORYBOOK_SMS_BODY`. Any Gemini failure is skipped silently: the guest already
has print 1 and the done screen says to ask Roman for the storybook later.
Secret: `wrangler secret put GEMINI_API_KEY`. Model is `GEMINI_MODEL` in
`wrangler.toml`.

## The folder: Google Drive mirror

Every print (real and storybook) is copied to one Google Drive folder the moment
it is archived, named like `2026-09-11 19.05.12 Ari Cohen (storybook).jpg`
(Los Angeles time, guest name, kind). Open it here:

https://drive.google.com/drive/folders/0AFzOAF0xZUy-Uk9PVA

That is the **"Delilah's Bday" Shared Drive** in the A+ Workspace (Roman:
manager; spotlight-watcher service account: content manager). Files land at
its top level.

How: the Worker signs a service-account JWT (WebCrypto RS256) with the
`GOOGLE_SA_JSON` secret (spotlight-watcher SA), caches the access token in KV
for 50 minutes, and multipart-uploads into `DRIVE_FOLDER_ID` with
`supportsAllDrives=true`. The upload runs in `ctx.waitUntil`, after the
response, so the iPad never waits on Drive. Marker keys `drive/<key>` in KV
hold the Drive file id; `/photos` hides them.

**It must be a Shared Drive.** Google gives service accounts no storage quota,
so an SA-owned folder in My Drive accepts the folder but rejects every upload
with 403 "Service Accounts do not have storage quota". The SA also cannot
create shared drives itself ("The authenticated user cannot create new shared
drives"); a human creates the drive and adds the SA as Content manager. Shared
drive writes are eventually consistent: a file can 404 on get/delete for a few
seconds after create.

Reuse for future booths: `A+ Events` (`0ABqrqCiZrGoVUk9PVA`) is the existing
shared drive with the Sage Oak booth photos; create a folder inside it and set
`DRIVE_FOLDER_ID` to that folder.

Backfill anything archived before the mirror existed, or after a Drive outage:

```bash
curl -s -X POST -A "Mozilla/5.0 Safari" https://delilah-booth.nameless-mountain-bafa.workers.dev/drive-backfill
```

Returns `{ uploaded, skipped, failed }`. Safe to run any number of times.

## Sender number

Texts go out from 818-573-6293 ("Roman's line" in JustCall, MMS-capable, the
same number the EO booth used). Confirmed by Roman 2026-09-10. `JUSTCALL_FROM`
in `wrangler.toml`.

## Deploy

```bash
cd booth/delilah
npx wrangler kv namespace create DELILAH_PHOTOS      # paste id into wrangler.toml
npx wrangler deploy
npx wrangler secret put JUSTCALL_API_KEY
npx wrangler secret put JUSTCALL_API_SECRET
npx wrangler secret put GEMINI_API_KEY
# Drive mirror: paste the spotlight-watcher service-account JSON as ONE line
python3 -c "import json;print(json.dumps(json.load(open('/path/to/a-plus-spotlight-watcher-1323d431f814.json')),separators=(',',':')))" | npx wrangler secret put GOOGLE_SA_JSON
# The page is served by the Worker from public/ ([assets]); there is no Pages project.
```

## Day-of checklist

1. iPad: Settings > Safari > Camera > Allow for
   delilah-booth.nameless-mountain-bafa.workers.dev. Add the page to the Home
   Screen so it runs full-screen.
2. Selphy on the same Wi-Fi. First print: pick the Selphy in the iOS print sheet,
   paper size 4x6 (Postcard), then it stays selected.
3. Take one test shot, confirm both prints and both texts arrive. Two print
   sheets per guest: the host taps Print on each.
4. After the party: the Drive folder above is the family album. `GET /photos`
   on the Worker is the backup list; nothing needs tearing down.

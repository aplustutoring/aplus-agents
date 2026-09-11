# booth/aplus-2026 — APLUS+ Network 23rd Annual Conference (Anaheim, Oct 21-23, 2026)

A+ Tutoring is exhibitor table PC6 and a Preferred Partner. The booth is a
**group selfie** on a handheld iPad; every person who wants a print types a name
and email, and that row is both a HubSpot contact and a print job. A MacBook at
the table runs the print agent that feeds the Canon Selphy, so nobody taps a
print dialog all day.

| File | What | Where it runs |
| --- | --- | --- |
| `public/index.html` | Booth page: start, camera with burst of 3, pick, copies (one row per person, school from email domain, dropdown fallback), done, hidden host view (queue + reprints) | iPad Safari, served by the Worker |
| `public/schools.json` | The school picker source (copy of `schools-dropdown.json`) | |
| `public/aplus-network-logo.png`, `public/aplus-tutoring-logo.png` | Frame logos | |
| `worker.js` | `POST /group` archive + Drive mirror; `POST /copy` HubSpot upsert + MMS + print job; `GET/POST /queue...` for the agent; `/photo`, `/photos`, `/drive-backfill` | Cloudflare Worker `aplus-conference-booth` |
| `print-agent/print_agent.py` | Polls the queue, prints to the Selphy through CUPS in order, pauses on printer errors | MacBook at the table |
| `wrangler.toml` | Vars: `EVENT_TAG`, `EVENT_NAME`, `JUSTCALL_FROM` (sales seat), `SMS_BODY`, `DRIVE_FOLDER_ID` | |
| `test-worker.mjs` | `node test-worker.mjs` (58 assertions, mocked HubSpot, JustCall, Drive with a real RSA signature) | |
| `schools.yml`, `schools-dropdown.json` | Every APLUS+ member school with staff email domains (see below) | |

Live: https://aplus-conference-booth.nameless-mountain-bafa.workers.dev

## Flow per group

1. Shooter holds the iPad, taps "Take the team photo". Front camera, mirrored.
2. Shutter: 3-2-1, then a burst of three frames half a second apart. Pick one.
3. Copies screen. One row per person: first name, email, optional cell, role
   chips (Admin / Teacher / Staff). The email domain matches the school list;
   shared network domains offer the campus list; unknown domains show the
   dropdown. After the first match every new row defaults to the same school.
4. Print: the row goes to `/copy`. HubSpot contact is created or updated
   (event tag `aplus_conference_2026` appended, never replaced; persona stamped
   only on create from the role chip; photo URL on the contact; note with the
   school as entered). If a cell was typed the photo is texted from the sales
   seat line. Then a print job is queued. The queue bar shows who is printing
   and how many are waiting.
5. Done. Prints come out at the table in the order names were typed.

Every group photo is archived in KV forever and mirrored to the Drive folder
`APLUS+ Conference 2026 - Anaheim - A+ Photo Booth` inside the **A+ Events**
Shared Drive. File names carry the school. Reprints: hold the top-right corner
of the start screen for a second.

## The print queue (why a MacBook)

iPad printing opens a print sheet per copy and freezes the page while it is
open. Five copies means five taps and a stuck iPad. Instead the Worker keeps a
queue (`q/<ms>-<id>` keys in KV) and the Mac runs:

```bash
cd booth/aplus-2026/print-agent
export BOOTH_URL=https://aplus-conference-booth.nameless-mountain-bafa.workers.dev
export AGENT_TOKEN=...            # the value set with `wrangler secret put AGENT_TOKEN`
lpstat -p                          # find the Selphy's CUPS name
python3 print_agent.py --printer Canon_SELPHY_CP1500
```

It claims the oldest queued job, downloads the 4x6, `lp`s it, marks it done,
and moves on. Printer offline, out of paper, or ink: it pauses and says so,
then resumes. A failed job is re-queued at its original position. Run with
`--dry-run` to exercise the whole loop without paper.

## Network at the table

Hotel Wi-Fi blocks device-to-device traffic. Use an iPhone Personal Hotspot
with Maximize Compatibility on (2.4 GHz for the Selphy). iPad, MacBook and
Selphy all join it. First print of the day: `lpoptions -p <printer> -l | grep
-i media` and pass the 4x6 name with `--media` if the default does not fit.

## HubSpot

- `aplus_event_tag` gets the option `aplus_conference_2026` (declared in
  `ops/hubspot-schema/properties.yml`, synced additively by `create_properties.py`).
- Writes: `aplus_event_tag` (merged), `aplus_event_role`, `aplus_booth_photo_url`,
  `phone` when given, `firstname`, and on create `a_persona` from the role chip
  (Admin = Decision Maker/Director, Teacher = Teacher of Record/EF/ES + TOR lead
  status). Existing contacts are never re-stamped.
- The school is written to a timeline note as entered. The `[Agent] School`
  stamp stays with `teacher_school_stamp.py`, which derives it from the email
  domain; unknown-domain schools live in the note until a human confirms.
- Sender for texts is the sales seat (Danielle's JustCall line), per the
  2026-08-25 routing rule for teacher and admin contacts.

## Deploy

```bash
cd booth/aplus-2026
npx wrangler deploy
npx wrangler secret put HUBSPOT_TOKEN
npx wrangler secret put JUSTCALL_API_KEY
npx wrangler secret put JUSTCALL_API_SECRET
npx wrangler secret put AGENT_TOKEN
python3 -c "import json;print(json.dumps(json.load(open('/path/to/a-plus-spotlight-watcher-1323d431f814.json')),separators=(',',':')))" | npx wrangler secret put GOOGLE_SA_JSON
python3 ../../ops/hubspot-schema/create_properties.py      # adds the event-tag option
```

## Day-of checklist

1. Night before: charge iPad, MacBook, Selphy battery. Selphy joined to the
   hotspot. `lpstat -p` shows it idle.
2. Morning: hotspot on, agent running in a Terminal window, one test shot, one
   test copy with your own email and cell. Print comes out, text arrives,
   contact shows in HubSpot with the event tag, file in the Drive folder.
3. Roles: shooter in the aisle with the iPad, host at the Mac handing prints by
   name, floater getting the second and third emails typed while the first
   print runs.
4. Paper: three groups an hour, five prints a group, three days. Bring 300
   sheets and matching cartridges.
5. After: nothing to tear down. No cron, no SUNSET needed.

## The school list

`schools.yml` holds every APLUS+ member school (95, from
theaplus.org/member-schools on 2026-09-11) with region, network, website, staff
email domains and whether we already hold teacher contacts for that domain in
HubSpot, plus 13 A+ partner schools that are not APLUS+ members.
`schools-dropdown.json` is the flat picker source (108 rows, 108 domains).

How it was built: member names scraped from the APLUS+ page; domains from four
parallel web-research passes with confidence per row; cross-referenced to
1,084 Teacher of Record contacts in HubSpot by email domain and the `[Agent]
School` stamp. `in_hubspot_tor_contacts` counts the domains on the row, so
network schools repeat the network total; it is a "we already work with these
people" flag, not a per-school count.

Verify before go-live: 26 rows are medium or low confidence (Learn4Life "II"
campuses, Options for Youth and Opportunities for Learning campus domains,
Northern Summit Academy). Diego Hills Central appears closed since 2024. Gorman
has both `gormanlcn.org` (web) and `gormanlc.org` (HubSpot) on the row.

## The attendee list nobody asked for

Jeff Rice (APLUS+ founder, jeff@theaplus.org) sent Roman the full exhibitor
table within hours in 2024. In the 2026 thread with Danielle nobody asked which
schools are registered. Danielle was asked on 2026-09-11 (Slack) to request the
participating schools. When it arrives, registered schools sort to the top of
the picker.

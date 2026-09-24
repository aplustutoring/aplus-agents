# tutor-sms-relay - an inbound text fires the ticket run in about a minute

Cloudflare Worker that turns a JustCall inbound text into a `tutor-sms`
`repository_dispatch` on `tutor-issues.yml`, so a family reporting "our tutor
isn't here" gets a scheduler-owned ticket in about a minute instead of
whenever the weekday poll next wakes up.

```
JustCall sms.received webhook
        │
        ▼
Worker /sms ──(inbound? coalesce 1 min, floor 90 s)──► POST /repos/<repo>/dispatches
                                                          {"event_type": "tutor-sms"}
                                                                  │
                                                                  ▼
                                              tutor-issues.yml, live, --mode inbound
```

PR #217 built both ends of the ticket (a late text opens a ticket tied to the
tutor and the family, owned by that student's scheduler) and taught the
workflow to accept `repository_dispatch: types: [tutor-sms]`. Nothing fired
that event, so the real latency stayed at the cron: Mondays 17:00 UTC plus
every two hours on weekdays. A 10:05 report waited until noon. This worker is
the missing doorbell.

The third instance of the relay worker from `ops/call_agent/webhook-relay`
(PR #146), after `ops/deal-relay`. Same Durable Object, same single coalescing
alarm, same "throw so the platform retries" behavior on a failed dispatch.

## Duplicate dispatches are harmless

The engine keeps a stable key per event in `../state/processed.json` and
dedupes one open ticket per tutor per issue type per period, and PR #217 made
`repository_dispatch` runs commit that state exactly like scheduled runs. So a
duplicated, coalesced, or dropped dispatch all end in the same one ticket. The
weekday cron stays as the backstop: a dead relay costs hours, not reports.

## Two deliberate differences from the deal relay

**1. `repository_dispatch`, not `workflow_dispatch`.** The call and deal relays
POST `/actions/workflows/<file>/dispatches`. This one POSTs
`https://api.github.com/repos/<repo>/dispatches` with body
`{"event_type": "tutor-sms"}` and expects 204. The target lives in
`wrangler.toml` as the `EVENT_TYPE` var.

**2. A cost floor.** Deal creations are rare; inbound texts are not. A win-back
blast can draw dozens of replies in minutes, and without a floor every one of
them is an Actions run. `DEFAULT_DELAY_MINUTES = "1"` already coalesces a
burst into one run, and on top of that the Dispatcher refuses to dispatch more
often than once per `MIN_INTERVAL_SECONDS` (default 90): it remembers the last
dispatch time and pushes the alarm out when the floor has not elapsed. Worst
case a report waits 90 seconds behind the one before it, which is still 80x
better than the two-hour cron.

## Inbound only, and no line filter

Only inbound texts fire. The payload is read defensively, the way
`booth/eo/worker.js` reads the same account's SMS payloads: unwrap `data` if
present, then take the first field among `direction`, `sms_direction`, `type`
whose value looks like a direction (starts with "in" or "out"). A value
starting with "in" is inbound.

Two judgment calls are baked in, both erring toward firing:

- **No direction field at all fires anyway.** The subscribed event is named
  `sms.received`, so a missing field almost certainly means inbound. A
  spurious run of an idempotent engine costs an Actions minute; a missed one
  costs a family two hours of nobody knowing the tutor never showed.
- **A non-direction value does not count as a direction.** `type` is on the
  candidate list because JustCall might put "inbound" there, but it might
  equally hold "sms". Reading "sms" as "not inbound" would drop every late
  report, so such a value is skipped and the next candidate is tried.

There is **no filter by line or by number**. The tutor-issues engine already
reads every line on the account and decides for itself what is a report, so
filtering here could only lose reports.

## The shape log (temporary, and why it is safe)

The real inbound payload shape is **not verified**. Nobody has captured a live
`sms.received` delivery, and `booth/eo/worker.js:970` carries its own comment
saying the same thing.

So every delivery logs, as one JSON line:

```
{"at":"sms.received","keys":["data"],"data_keys":["id","contact_number","direction",...],
 "direction_field":"direction","direction_value":"inbound","inbound":true,"reason":"..."}
```

Key **names** only, plus which direction field matched and whether the text was
treated as inbound. Never a message body, never a phone number, never a contact
name. Read it off `wrangler tail` after the first real text.

**Once the shape is known, remove or reduce this log** and trim
`DIRECTION_FIELDS` in `worker.js` to the field that actually exists. Leaving a
shape probe running forever is how a log turns into a data store.

## Deploy (Roman, in this order)

```bash
cd ops/tutor-issues/sms-relay
npx wrangler deploy
npx wrangler secret put GITHUB_TOKEN     # see 1
npx wrangler secret put WEBHOOK_TOKEN    # see 2, e.g. openssl rand -hex 24
```

1. **GITHUB_TOKEN** - the SAME fine-grained PAT the call and deal relays use:
   repository access = `aplustutoring/aplus-agents` only, permissions =
   **Actions: Read and write**, nothing else.
2. **WEBHOOK_TOKEN** - a fresh random string, not the one the other relays
   use. It rides in the query string of the webhook URL and is the only thing
   gating who can trigger runs.
3. **Register the webhook with JustCall.** The inbound-SMS event type is
   `sms.received` (confirmed 2026-09-10 by a read-only `GET` against the live
   account). `v1/webhooks` returns 403; use v2.1.

   ```bash
   curl -X POST https://api.justcall.io/v2.1/webhooks \
     -H "Authorization: <JUSTCALL_API_KEY>:<JUSTCALL_API_SECRET>" \
     -H "Content-Type: application/json" \
     -d '{"type":"sms.received",
          "webhook_url":"https://tutor-sms-relay.<subdomain>.workers.dev/sms?token=<WEBHOOK_TOKEN>"}'
   ```

   **This ADDS a second url to the existing `sms.received` type. Do not remove
   or overwrite the booth's url.** `sms.received` has been Active since
   2026-08-20 pointing at
   `https://eo-booth.nameless-mountain-bafa.workers.dev/sms`, and JustCall
   supports multiple urls per event type (`call.completed` and `call.missed`
   each carry two today). Deleting the booth url would silently kill the photo
   booth's SMS leg.
4. **Verify.** Send one text to the support line (818-869-1627), then:
   - `npx wrangler tail` shows one `sms.received` line with the key names,
   - `curl https://<worker>/health` returns `ok` (a 503 names whichever secret
     is still unset),
   - a `Tutor issues` run appears in Actions within about 2 minutes.

   `curl "https://<worker>/status?token=<WEBHOOK_TOKEN>"` shows the
   Dispatcher's alarm, last scheduled time, last dispatch time, the active
   floor, and the last dispatch error. A `lastDispatchError` with no later
   `lastDispatchAt` means the GitHub call is failing (check `GITHUB_TOKEN`).

## Decision logic, worked examples

The repo has no JS test runner, so the two decisions that matter are exported
pure functions in `worker.js`. These are their contracts.

`isInbound(body)` unwraps `data` and returns `{inbound, field, value, reason}`:

| body | inbound | field |
|---|---|---|
| `{"data":{"direction":"Inbound"}}` | true | `direction` |
| `{"data":{"direction":"outbound"}}` | false | `direction` |
| `{"sms_direction":"incoming"}` | true | `sms_direction` |
| `{"type":"outgoing"}` | false | `type` |
| `{"data":{"type":"sms","id":7}}` | true | none (value is not a direction) |
| `{"data":{"id":7}}` | true | none (no direction field) |
| `{}` | true | none |

`floorWantedAt(wantedAt, lastDispatchAt, minIntervalMs)` returns when the
dispatch should actually happen:

| wantedAt | lastDispatchAt | floor | result |
|---|---|---|---|
| T+60s | none | 90s | T+60s (nothing to wait behind) |
| T+60s | T-30s | 90s | T+60s (floor already elapsed by then) |
| T+60s | T-10s | 90s | T+80s (pushed out to lastDispatch + 90s) |
| T+60s | T | 90s | T+90s |

`shapeLog(body)` returns `{keys, data_keys}` and nothing else, which is what
keeps the shape log free of PII.

# ops/tutor-issues — Tutor-issue ticketing

Issues we notice get logged as HubSpot tickets on the **tutor's** contact
record. Approved by Roman 2026-08-26. **v1 is a silent internal log**: the
tutor is never notified, and nothing here is tutor-facing (a tutor-facing
next step is v2 — nothing in this design blocks it).

## The five issue types

| type | detection | priority |
|---|---|---|
| `missed_lesson_or_late` | auto (Teachworks no-show statuses) + inbound family reports | HIGH |
| `tutor_change_requested` | inbound reports + Slack intake | HIGH |
| `notes_not_completed` | auto (Teachworks unmarked after Sunday cutoff) | LOW |
| `scheduling_flip_flop` | Slack intake | MEDIUM |
| `tech_issue_unreported` | Slack intake | MEDIUM |

Detection is automated **only where system data proves it**. Types 2/4/5
have no proving field, and a false ticket about a contractor's conduct is
worse than a missed one — so they arrive only through humans (structured
intake) or reasoned inbound reports that a human can audit.

## Ticket shape

Support Pipeline (`0`), opens in "Working on it" (`131537027`),
`hs_ticket_category` = "Tutor Issue" (matched **by label** at runtime),
owner = **Operations role** (Mandy — Aug 26 decision: escalations land on
Operations), associated to the tutor contact (`a_persona` contains
"Tutors"), `ticket_source=tutor_issues`, `source_agent=tutor-issues`, and
the `tutor_issue_*` audit fields (type, source record ids, detected-at,
last-event-at, occurrences, period) declared in
`ops/hubspot-schema/properties.yml`.

### "The tutor is late" texts (Roman 2026-09-10)

One category breaks the tutor-only shape. When an inbound text reasons to
`missed_lesson_or_late`, the sender's number is resolved to the **family**
contact (two-tier phone search ported from `ops/call_agent/call_agent.py`,
CallRail caller-ID shells skipped) and the ticket is opened with:

- **both contacts associated** (tutor first, family second, association
  type 16 on each),
- **owner = that student's scheduler** (A-L Janelle, M-Z Yolanda) instead
  of Operations, so nobody has to tell a scheduler by hand,
- **the family's own words quoted verbatim** in the body (trimmed to 500
  chars) with the sender number, the line it arrived on, and the timestamp.

The split keys on the student's SURNAME, read from
`student_last_name_if_diff_from_parent` and falling back to the family
contact's `lastname`. Not `student_last_name`: that property is labelled
"Student FIRST Name" in the registry.

Refusal still beats a guess. More than one non-junk contact on the number,
or a number whose only match is a Tutor or Teacher of Record (a tutor
texting about their own lesson is not a family report), resolves to no
family: the ticket is still created tutor-only and owned by Operations, and
the ambiguity is printed in the run report.

The `late_reports` block in `config.yml` is the switch
(`route_to_scheduler`, `associate_family`); with the block missing or
disabled the engine behaves exactly as it did before.

## Sources

- **sweep** (Mondays, last complete Sun-Sat week, both Teachworks
  accounts): no-show statuses -> `missed_lesson_or_late`; unmarked after
  the Sunday cutoff -> `notes_not_completed` (same definition as the
  scorecard's unmarked-lessons <3% metric — one source of truth).
  The lateness leg is **off** until `--probe-lateness` proves Teachworks
  records an actual start distinct from the scheduled one and Roman
  approves a threshold from the observed distribution.
- **inbound** (family says the tutor didn't show, by email or text):
  - email: consumes `email/state/audit_log.jsonl` from the LIVE triage
    agent (categories `tutor_issue`/`scheduling`/`complaint`); bodies come
    from the HubSpot Conversations thread. This engine never touches the
    triage code, its inbox, or its own family-side SLA ticket — the
    tutor-side ticket cross-links it in `tutor_issue_source_ids`.
  - SMS: inbound texts via JustCall (same account the call agent polls).
  - A Claude reasoning pass extracts tutor / type / evidence / confidence,
    and its reasoning is written into the ticket body. Resolves cleanly ->
    ticket + a scheduler notification in #tutor-issues ("ticket created").
    Can't resolve, or confidence < `inbound.min_confidence` -> **no
    ticket**; the scheduler is told to review and file manually.
- **intake** (types 2/4/5, structured Slack in #tutor-issues):

      tutor-issue <type> | <tutor email | tw:<acct>:<id> | "First Last"> | <one-line evidence>

  Anything that cannot resolve to exactly one tutor contact is rejected
  with a threaded reply saying why.

## Tutor resolution — refusal is a signal, a guess is a landmine

Teachworks employee (exact id, or exact normalized full-name match with
exactly one hit) -> employee email -> exactly one HubSpot contact by email
-> `a_persona` must contain "Tutors". Any step failing = **no ticket**,
logged as a refusal in the digest and the run report.

## Guards (non-negotiable)

- **Baseline**: first run (no `state/baseline.json`) stamps everything
  already qualifying and creates/sends NOTHING.
- **Dedupe**: one open ticket per tutor per issue type per period
  (`dedupe_period` in config: weekly for sweep types, rolling 30d for
  report types). Recurrence updates the ticket (occurrences, last-event-at,
  source ids) — never a second ticket. Closed = "Done" only for now
  (Stopped has a known isClosed gap).
- **One digest per run** to #tutor-issues; scheduler notices are
  event-driven (one inbound report -> one notice), also in-channel, never
  DMs.
- **Hard caps** (`guards:` in config) on creates and notifications: a live
  run refuses to act entirely when exceeded; a dry run reports the
  violation.
- **Idempotent**: every event has a stable key in `state/processed.json`;
  running twice on the same day produces the same result once.

## Running

    python3 tutor_issues.py --mode all|sweep|inbound|intake [--dry-run]
        [--force-sweep] [--probe-lateness] [--assume-baselined]
        [--report-json PATH] [--simulate-event PATH]

`--assume-baselined` (dry-run only) shows the would-create distribution the
real baseline run suppresses. `--simulate-event` runs one synthetic inbound
report end-to-end (verification: exactly one ticket + one digest line) and
never persists state.

On Actions: `.github/workflows/tutor-issues.yml` (manual dispatch, dry-run
default TRUE; the schedule stays commented out until the baseline is
verified and Roman flips it on).

## Latency

| path | when a "the tutor is late" text becomes a ticket |
|---|---|
| cron only | up to 2 hours (weekday polls at 16, 18, 20, 22, 00 UTC) |
| relay deployed | about 1 minute, 90 seconds worst case behind a burst |

The workflow accepts a `repository_dispatch` of type `tutor-sms`, which runs
the inbound leg live (`--mode inbound`) and commits its state like a
scheduled run. `sms-relay/` is the Cloudflare Worker that fires it: JustCall
posts its `sms.received` webhook the moment a text lands, the worker
coalesces the burst behind one alarm, and the dispatch goes out about a
minute later. Duplicate or coalesced dispatches are harmless (stable event
keys in `state/processed.json` plus the per-period dedupe), and the cron
stays as the backstop, so a dead relay costs hours rather than reports.

**Not deployed yet.** Roman runs the four steps in `sms-relay/README.md`:
`wrangler deploy`, `wrangler secret put GITHUB_TOKEN` (the same fine-grained
PAT the call and deal relays use), `wrangler secret put WEBHOOK_TOKEN` (a
fresh random string), then register the url with JustCall:

    POST https://api.justcall.io/v2.1/webhooks
    Authorization: <JUSTCALL_API_KEY>:<JUSTCALL_API_SECRET>
    {"type": "sms.received",
     "webhook_url": "https://<worker>.workers.dev/sms?token=<WEBHOOK_TOKEN>"}

That ADDS a second url to the `sms.received` type, which has been Active
since 2026-08-20 pointing at the photo booth. JustCall allows multiple urls
per type. The booth's url must not be removed.

## Setup still pending before live

1. Merge, then run the HubSpot schema sync workflow (creates the `tutor`
   ticket group + 6 `tutor_issue_*` properties + `ticket_source` option).
2. Create the #tutor-issues Slack channel, /invite the aplus bot, paste the
   channel ID into `config.yml -> slack.channel`.
3. Live baseline run (expect: 0 created, 0 sent, baseline stamped).
4. Uncomment the schedule in the workflow.

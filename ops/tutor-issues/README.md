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

## Setup still pending before live

1. Merge, then run the HubSpot schema sync workflow (creates the `tutor`
   ticket group + 6 `tutor_issue_*` properties + `ticket_source` option).
2. Create the #tutor-issues Slack channel, /invite the aplus bot, paste the
   channel ID into `config.yml -> slack.channel`.
3. Live baseline run (expect: 0 created, 0 sent, baseline stamped).
4. Uncomment the schedule in the workflow.

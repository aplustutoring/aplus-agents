# Bulk messenger

On-demand bulk email + SMS to customers, targeted at a HubSpot LIST. Built
2026-08-14 (Roman: "a programmed agent that can send out custom email and text
messaging to customers whenever called upon. only for bulk options").

## Rails (Roman's decisions, 2026-08-14)

| Channel | Rail | How |
|---|---|---|
| Email | HubSpot marketing email | Clone an in-portal template email, retarget the clone at the list, leave as **DRAFT** with a review link. Roman clicks Send in HubSpot — suppression (opt-outs, bounces, non-marketing contacts) is HubSpot-native. Personalization via native tokens (`{{contact.student_first_name}}`, `{{contact.last_tutor_name}}`). |
| SMS | JustCall | Rendered per-contact from a repo template. From-number routing: `sales` = 818-573-6644, `conference` = 818-850-6284. |

## Guardrails

- **BULK ONLY**: refuses runs under `min_bulk` (25) recipients — not a 1:1 tool.
- **Approval-first**: dry-run default everywhere; live requires `confirm=SEND`.
- **SMS**: `sms_opt_out` contacts skipped; template must contain a STOP line;
  live sends only 9:00–20:00 PT; phones normalized to E.164, unusable skipped.
- **Tutor names**: templates use `last_tutor_name` which holds FIRST names
  only (customer-facing rule, Roman 2026-08-14).
- **Journey playbook**: before contacting a family, teacher, or tutor, read
  `knowledge/journey/README.md` and pass
  `knowledge/journey/00-pre-send-checklist.md`. Act only on stages marked
  REVIEWED. Win-back rounds are stage 09.
- **Under 25 recipients, use `one_to_few.py`** (next section). It runs the
  pre-send gate per contact. The 2026-09-08 follow-ups ran from session
  scripts with none of these checks; that path is closed.

## Small sends: the one_to_few rail (1 to 24 recipients)

`one_to_few.py` is the rail for follow-ups, relays, and confirmations to a
handful of families or tutors. It does not lower `min_bulk`; it sits beside
the bulk engine and runs every recipient through the pre-send gate
(`email/src/presend.py`, the code form of
`knowledge/journey/00-pre-send-checklist.md`): opt-out, quiet hours, stage
to line, active thread on another line, unanswered reply, open scheduling
ticket, frequency, standing go, STOP line. Dry run is the default and prints
ALLOW / HOLD / BLOCK per contact with the reason and, for a hold, the seat
that owns the thread.

```
python3 ops/messenger/one_to_few.py --contacts 123,456 --purpose po_push \
  --from charter_sales --template templates/charter_r2_opened_single.txt
python3 ops/messenger/one_to_few.py --list-id 3237 --purpose tor_confirm \
  --from charter_sales --bodies bodies.json --live --confirm SEND --approved-by U05NA7UMSSV
```

`--from` and `--purpose` have no defaults (the 2026-09-09 incident was a
default). Purposes and lines are declared in `email/config.yaml`
(`presend:`); a purpose in `standing_go` sends without `--confirm`, anything
else needs it. Every send writes a HubSpot note, the two `[Agent] Last
Outbound` properties, an audit line, and `state/sends/<date>-<purpose>.jsonl`.

## Calling it

Actions → "Bulk messenger" → list id + channel + template. Dry-run first (the
default), read the summary in the log, re-dispatch with `dry_run=false` +
`confirm=SEND`.

```
gh workflow run messenger.yml -f list_id=3104 -f channel=sms \
  -f sms_template=templates/charter_win_back.txt -f sms_from=sales
```

## Phase 2 (not built)

- Slack front door: message the aplus bot ("send charter_win_back to list 3104
  via sms"), bot replies with the dry-run summary + samples, Roman replies
  "go" → bot dispatches the live run. Engine unchanged.
- API send for email (skip the in-portal Send click) once the clone+retarget
  flow has a few clean runs behind it.
- STOP-reply ingestion: poll JustCall for inbound STOP replies → stamp
  `sms_opt_out` on the contact automatically.

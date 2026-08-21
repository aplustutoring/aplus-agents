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

## Calling it

Actions → "Bulk messenger" → list id + channel + template. Dry-run first (the
default), read the summary in the log, re-dispatch with `dry_run=false` +
`confirm=SEND`.

```
gh workflow run messenger.yml -f list_id=3104 -f channel=sms \
  -f sms_template=templates/charter_win_back.txt -f sms_from=sales
```

## Campaigns

Multi-step campaigns live beside the on-demand messenger, one config + one
program doc each. `enroll.py --config <file>` enrolls list members into the
HubSpot workflows; both configs gate on `armed:` + `launch_date`.

| Config | Doc | Audience | Sender | State |
|---|---|---|---|---|
| `campaign.yml` | `CAMPAIGN-2026-08-17.md` | charter gap FAMILIES | A+ team, Paola tasks | LIVE, wave 2 sent |
| `campaign-tor.yml` | `CAMPAIGN-TOR-2026-08.md` | charter TEACHERS (TOR) | Danielle (sales seat) | DISARMED |

Keep them in separate files: arming one must never move the other.

## Phase 2 (not built)

- Slack front door: message the aplus bot ("send charter_win_back to list 3104
  via sms"), bot replies with the dry-run summary + samples, Roman replies
  "go" → bot dispatches the live run. Engine unchanged.
- API send for email (skip the in-portal Send click) once the clone+retarget
  flow has a few clean runs behind it.
- STOP-reply ingestion: poll JustCall for inbound STOP replies → stamp
  `sms_opt_out` on the contact automatically.

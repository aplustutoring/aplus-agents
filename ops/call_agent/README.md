# ops/call_agent — Call Agent v1.1 (JustCall → HubSpot family-record loop + Slack)

Polls JustCall for completed **inbound** calls on the main A+ line, pulls each
call's native AI transcript, and turns each call into CRM actions:

- **Call engagement** on the matching HubSpot contact (summary + metadata)
- **Family-record updates** — the call is checked against the contact's key
  properties ("What's going on?", "What we can do to help", student name/
  grade/school, subject, modality, referral source) and updates them per a
  per-field write policy (see below)
- **Lead status** — Claude assigns `hs_lead_status` per call (portal option
  VALUES, e.g. `We Connected` = "QTL - NEW"): prospective families →
  QTL - NEW / QTL - Charter (charter funds) / QTL - Diagnostic Sent (test
  prep or evaluate-first); school staff → School Personnel or Charter TOR/EF;
  tutor applicants → Tutors; spam/vendors → Unqualified. Existing/past
  customers → no change (the deal pipeline owns their status). Changes are
  applied every call (Claude's judgment wins) and surfaced in the digest.
- **Action items → HubSpot Tasks** with owner + due date (default owner Paola)
- **Missed-call alerts (conversion guard)** — inbound missed/abandoned/
  voicemail calls on ANY account line fire an immediate Slack alert + a
  same-day HIGH call-back task on the next poll. Metadata only (caller,
  line, time — nothing transcribed), so the consent guardrail doesn't apply
  and all lines are covered. `config.yml → missed_calls`.
- **No-next-step guard (conversion guard)** — a new family inquiry that ends
  without a concrete booked next step (assessment, first session, or a
  callback at an agreed time) is flagged `:calendar:` in the digest's
  Needs-attention section and gets a same-day HIGH task to call back and
  lock one in.
- **Negative sentiment / complaints → HIGH ticket** in the Support Pipeline
  ("Working on it") + check-in task due in 2 business days + an **immediate
  alert** to a private Slack channel
- **Daily digest** to Slack (counts, per-call one-liners, record updates,
  unmatched-caller triage), headed by a **daily-activity brief**: account-wide
  call totals for the day — ALL lines, inbound + outbound — broken down by
  person, by outcome (answered/missed/abandoned/voicemail), and by line
  (friendly names via `config.yml → justcall.line_names`). The brief posts
  every day even when no calls were processed.
- **Coaching** — every processed call is scored against [rubric.md](rubric.md)
  (11 dimensions: 5 universal, 4 new-inquiry, 2 service-recovery), attributed
  to the team member who answered (JustCall `agent_name`). Coaching cards
  (scores, went-well quotes, coaching moments with alternative phrasings,
  missed opportunities) post per-call to a PRIVATE channel
  (`config.yml → coaching.channel`, falls back to `slack.alert_channel`),
  AND the full evaluation is attached as a **Note on the matched contact**
  (`coaching.note_to_contact: true`). ⚠ Contact Notes are visible to everyone
  with HubSpot access — coaching scores are team-visible on family records;
  set `note_to_contact: false` to keep coaching Slack-only. Edit the rubric
  anchors in rubric.md — no code changes needed. Coaching failures never fail
  call processing.

A **scheduled poller, not a webhook** — one Python script
(`call_agent.py`) run by `.github/workflows/call-agent.yml` every 15 min
during business hours (~8 AM–8 PM PT, `--no-digest`: coaching cards and
alerts post per call for near-real-time feedback) plus a daily ~5:30 PM PT
digest run that flushes held entries. Same pattern as `ops/scorecard`.
Calls whose JustCall AI transcript isn't ready yet are retried on later
polls within `transcript_grace_minutes` (must stay < `overlap_minutes`). HubSpot stays the single source of truth for
families/communication; this agent only *adds* engagements, never edits
contact data.

## V1 scope decisions (locked — do not expand casually)

1. **Transcription source: JustCall native AI only.** Transcripts come from
   `GET /v2.1/calls_ai/{id}?fetch_transcription=true` (they were removed from
   the Call API in Aug 2024). There is **no** Whisper/third-party fallback:
   a call with a recording but no transcript is skipped and counted in the
   digest's "Skipped" section. That's the whole fallback.
2. **Inbound calls on monitored numbers only.** `config.yml →
   justcall.monitored_numbers`: the main A+ line, plus the customer support
   line (added 2026-07-20, recording disclosure confirmed). More lines can be
   added without code changes — but no outbound, no tutor lines, no individual
   team lines in v1.
3. **Consent guardrail (CA two-party consent).** The IVR on the main line
   announces that calls are recorded — confirmed and handled at the
   phone-system level. The agent still enforces `require_recording: true`:
   calls with no recording are never transcribed or summarized by any means,
   only counted. This keeps the guardrail intact when numbers are added to
   `monitored_numbers` later, where the disclosure hasn't yet been confirmed.
   **Before adding any number to the config, confirm its recording disclosure.**
4. **No auto-created HubSpot contacts.** Calls with no phone match go to the
   digest's "Unmatched" section with number, time, and summary — a human
   decides.

Out of scope for v1: outbound calls, SMS, webhook/real-time ingestion,
third-party transcription, sentiment analytics dashboards, Family-State
integration (future: call transcripts as genesis events).

## Files

| File | Purpose |
|---|---|
| `call_agent.py` | The whole pipeline (fetch → transcript → summarize → HubSpot → digest) |
| `config.yml` | Monitored numbers, guardrails, model, Slack channel, state path |
| `.env.example` | Env var names for local runs |
| `state/state.json` | Cursor + processed call IDs + held digest entries (committed back by the workflow) |

## Secrets

Environment variables only — never committed (`.env` is gitignored repo-wide).
GitHub Actions repo secrets:

- `JUSTCALL_API_KEY` / `JUSTCALL_API_SECRET` — JustCall dashboard → profile →
  **APIs and Webhooks**. API access needs the Team plan or above.
- `HUBSPOT_API_KEY` — same private-app token the scorecard uses. The private
  app needs CRM scopes for contact **search** plus creating **calls** and
  **notes** engagements (`crm.objects.contacts.read`, and write on engagements).
- `ANTHROPIC_API_KEY` — already a repo secret (marketing engine uses it).
- Slack: `SLACK_BOT_TOKEN` (posts to `config.yml → slack.channel`, needs
  `chat:write`) **or** `SLACK_WEBHOOK_URL` (webhook decides the channel).
  Bot token wins when both are set.

## Setup

1. Put the main A+ line's number (E.164, e.g. `+1310…`) into
   `config.yml → justcall.monitored_numbers`, replacing the placeholder.
   The script refuses to run while the placeholder is present.
2. Set the Slack channel in `config.yml → slack.channel` (bot-token mode).
3. Add the repo secrets above.
4. Run the first dry-run (below). **The deployment defaults to dry-run**: the
   scheduled workflow passes `--dry-run` until the repo *variable*
   `CALL_AGENT_LIVE` is set to `true`
   (Settings → Secrets and variables → Actions → **Variables**).

## Running

**Local dry-run** (real JustCall + Claude reads; prints what it *would* write;
no HubSpot/Slack writes; state untouched):

```bash
cd ops/call_agent
pip install -r requirements.txt
cp .env.example .env   # fill in values (or rely on the repo-root .env)
python3 call_agent.py --dry-run
```

**Actions dry-run:** trigger the `Call agent` workflow via *Run workflow*
(the `dry_run` input defaults to `true`).

**Smoke test** (no reads/writes at all, scorecard `CHECK_ONLY` convention):
dispatch with `check_only=true`, or locally `CHECK_ONLY=true python3 call_agent.py`.

**Go live:** set repo variable `CALL_AGENT_LIVE=true`. The daily cron
(~5:30 PM PT) then writes to HubSpot/Slack and commits state back.

Flags: `--since 2026-07-09T00:00:00` (UTC cursor override),
`--no-digest` (process but hold digest entries in state for a later run —
for multi-run-per-day schedules; the next digest-posting run flushes them).

## How a run works

1. **Fetch** — `GET /v2.1/calls` per monitored number
   (`call_direction=Incoming`, `from_datetime` = cursor − 60 min overlap,
   paged 100/page). Idempotent: processed call IDs live in `state/state.json`,
   so crashes/re-runs never double-process. Only `Answered` calls are
   processed (`config.yml → process_call_types`).
2. **Transcript** — `GET /v2.1/calls_ai/{id}?fetch_transcription=true`, paced
   2 s/call (JustCall burst limit is 30/min on Team). No recording → skipped
   (consent guardrail); recording but no transcript → skipped; both counted.
3. **Summarize** — Claude (`claude-opus-4-7`, the repo-standard model) with
   structured outputs (`output_config.format` JSON schema — guarantees valid
   JSON; assistant prefill is unsupported on 4.6+ models) → summary,
   caller_type, intent, sentiment, action_items
   (with owner hints), follow_up_needed, student/school names. Transcripts
   over 50k chars are truncated first (cost guard, noted in metadata).
4. **HubSpot match** — contact search on `phone`/`mobilephone` with E.164 +
   common US format variants, falling back to a `CONTAINS_TOKEN` match on the
   10-digit number. The match happens BEFORE summarization so the contact's
   current key-property values feed the prompt. No match → digest triage list
   (never auto-created).
5. **Record updates** — Claude compares the call against the current record
   and proposes updates; the script applies them per field policy:
   | Policy | Fields | Behavior |
   |---|---|---|
   | `log` | What's going on? (`parent_concerns_what_can_we_do_to_help_`), What we can do to help (`student_additional_information`) | Prepend a `[YYYY-MM-DD call]`-dated entry; previous entries preserved |
   | `overwrite` | grade, school, subject, online/in-person | Facts that legitimately change — corrected freely |
   | `fill_only` | student name, how-did-you-hear, referral | Written only when blank; conflicts surfaced in the digest for review |
   | `correction` | email, phone | Only on an explicit, confirmed-working correction stated in the call |

   ⚠️ Portal naming traps (verified live): `student_last_name` holds the
   student's FIRST name; the last name is `student_last_name_if_diff_from_parent`;
   `school` is a FB-Ads field — the real one is `student_school`. Enum option
   values for grade/subject/modality/source are pinned in `call_agent.py` and
   validated before writing.
6. **Tasks & tickets** — each action item becomes a HubSpot Task (owner from
   the caller's `owner_hint`, mapped via `config.yml → hubspot.owners`
   [roman/paola/janelle], default Paola; due next business day). Negative
   sentiment or complaint intent → HIGH ticket (Support Pipeline → "Working
   on it", source PHONE, owner Roman) + companion check-in task due in 2
   business days + immediate alert to `slack.alert_channel`.
7. **Digest** — one Slack message per day: counts (processed/matched/
   unmatched/hang-ups/tasks/updates/failed), "Needs attention" on top,
   one-liners grouped by caller type, record updates applied, proposed-but-
   kept conflicts for review, unmatched-numbers triage, skipped and failure
   sections. Per-call errors are caught and reported in the digest — one bad
   call never kills the run.

## Known API caveats (doc verification + live testing, 2026-07)

Verified live against the real account on 2026-07-10 — three places where the
API differs from its own docs (all handled in code):

- **Pagination is 0-indexed**: `page=0` is the first page. (`page=1` +
  `per_page=100` silently returns nothing.)
- **`from_datetime` is account-timezone, responses are UTC** (verified live
  2026-07-17): the list filter is interpreted in the JustCall account's
  timezone (PT for us — `config.yml → justcall.account_timezone`), while
  `call_date`/`call_time` in the response are UTC. Sending a UTC cursor reads
  as hours in the future and silently returns zero calls.
- **`call_info.type` is lowercase** (`answered`, not the documented `Answered`).
- **`recording` is nested under `call_info`**, not top-level on the call object.


- **Auth header:** official docs show plain `key:secret`; some clients need
  Basic base64. The script tries plain first and falls back automatically
  on 401.
- **Transcript array key names** aren't published in the docs — the parser
  accepts the plausible variants (`sentence`/`text`/`content`…,
  `speaker`/`speaker_id`…). If the first dry-run logs "recording but no
  transcript" for calls that clearly have transcripts in the JustCall UI,
  capture one raw `calls_ai` response and adjust `fetch_transcript()`.
- **Plan gating:** AI transcription may require the JustCall AI add-on —
  not stated in the docs; the first dry-run will reveal it.
- No documented "transcript exists" flag on the call object — the agent just
  attempts the AI endpoint and treats 404/empty as "no transcript".

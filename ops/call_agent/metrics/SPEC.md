# call-metrics — build spec

**Repo:** `aplustutoring/aplus-agents` → `ops/call_agent/metrics/` (extends `call_agent.py`; reuses the JustCall webhook → Cloudflare relay → `workflow_dispatch` rail from PR #146)
**Status:** working draft — Sep 2, 2026
**Owner:** Roman · **Reviewer:** Emily

## Purpose

Track every inbound call against the seat that was supposed to answer it, and every voicemail against how fast it was returned. Weekly per-person digest in Slack. No Monday.com anywhere.

## Locked decisions

| # | Decision |
|---|---|
| L1 | Output is Slack only (per-person DM + summary to Roman). No Monday.com, no HubSpot scorecard properties. |
| L2 | A miss is attributed to the **seat that rang and did not answer**, per ring leg. Overflow answering does not erase the miss — it is logged as `recovered_by`. |
| L3 | Scorecard bar: missed calls during phone hours = 0; voicemails returned within 2 business hours = 100%. |
| L4 | Phone hours: Mon–Fri 09:00–18:00 America/Los_Angeles. Calls outside hours are excluded from miss counts. |
| L5 | IVR: 1 → Paola → Roman; 2 → ring group Janelle + Yolanda; 3 → Danielle → Paola. |

## Working-draft assumptions (Roman to confirm or overrule)

| # | Assumption | Alternative |
|---|---|---|
| D1 | Implement as a metrics step inside `call_agent.py`, not a separate skill — one JustCall consumer, existing idempotency keyed on `call_sid`. | Standalone `~/code/skills/call-metrics` polling the JustCall Calls API cold. |
| D2 | Simultaneous ring on press 2 that nobody answers = one miss for **each** of Janelle and Yolanda, flagged `group_miss=true`. | Group miss counts against neither; reported as a team line only. |
| D3 | "Returned" = any **outbound call attempt** (answered or not) from any seat to the voicemail caller's number, **or** an outbound SMS via the SMS rail, within 2 business hours. Clock runs only inside phone hours (5:30pm Fri voicemail → due 10:30am Mon). | Answered outbound calls only; SMS doesn't count. |
| D4 | No human adjudication in v1. The digest lists every miss with `call_sid`; disputes get raised in L10 and fixed by editing JustCall agent attribution at the source. | Emily reviews a `disputed.csv` before the digest sends. |
| D5 | Digest runs **Friday 16:00 PT**, covering Sat–Fri. | Monday 07:00 PT before L10. |

## Data model

One row per **ring leg**, derived from JustCall `call.completed` webhook payloads (verify exact field names against the JustCall webhook docs before coding — do not guess).

```
ring_legs
  call_sid            str   JustCall call id (idempotency key with leg_index)
  leg_index           int   0 = first seat/group rung, 1 = overflow, …
  received_at         ts    UTC
  in_hours            bool  derived from received_at in America/Los_Angeles
  caller_number       str   E.164
  hubspot_contact_id  str?  from existing call_agent resolution
  ivr_option          str?  "1" | "2" | "3" | "0" | null  (JustCall IVR key press; if not in payload, infer from destination number/group)
  target_seat         str   JustCall agent id (one row per seat in a group ring)
  target_group        str?  "schedulers" when the leg was a group ring
  outcome             enum  answered | missed | voicemail | abandoned
  answered_by_seat    str?  set on the leg that answered
  recovered_by        str?  set on a *missed* leg when a later leg answered
  duration_sec        int
  recording_url       str?

voicemails
  call_sid            str
  seat_owner          str   seat whose voicemail box caught it (group → both schedulers)
  left_at             ts
  due_at              ts    left_at + 2 business hours (phone-hours clock)
  returned_at         ts?   first qualifying outbound call/SMS to caller_number
  returned_by_seat    str?
  on_time             bool?
```

Storage: append-only JSONL under `ops/call_agent/metrics/data/YYYY-MM.jsonl`, committed by the Actions run (same pattern as existing agent state). No external DB.

## Processing

1. **Ingest** (on each `workflow_dispatch` from the relay): parse the webhook payload → explode into ring legs → upsert by `(call_sid, leg_index)`. Skip if outside phone hours *and* not a voicemail.
2. **Recovery link**: within one `call_sid`, if leg N is `missed` and leg N+k is `answered`, set `recovered_by` on leg N.
3. **Voicemail matching** (runs each ingest + nightly backstop): for each open voicemail, scan JustCall outbound calls and SMS-rail sends to `caller_number` after `left_at`; first hit sets `returned_at`, `returned_by_seat`, `on_time`.
4. **Weekly rollup** (Fri 16:00 PT cron): per seat —
   - `calls_rung`, `answered`, `missed`, `missed_recovered`, `group_misses`
   - `voicemails_caught`, `returned_on_time`, `returned_late`, `unreturned`, median `time_to_return`
   - `avg_answer_seconds`, `talk_minutes`
5. **Digest**: Slack DM per seat (Paola, Janelle, Yolanda, Danielle) + one summary DM to Roman with all seats and every miss listed as `time · caller (contact link) · ivr_option · recovered_by`. Roman's own overflow answers appear under Paola as recovered misses, and under Roman as answered.

## Guards

- Idempotent on `(call_sid, leg_index)`; reprocessing a webhook never double-counts.
- Never remediate (Sentinel rule) — the agent reports, it does not reassign calls, edit JustCall, or message parents.
- Unknown seat id → row kept with `target_seat="unknown"`, surfaced in Roman's digest, not silently dropped.
- Numbers on the internal allowlist (staff cells, test calls from Roman) are excluded from all counts.
- If JustCall's payload lacks per-seat ring detail for group rings, fall back to the JustCall Calls API `GET /calls/{id}` before writing the row — do not fabricate legs.

## Out of scope (v1)

Outbound-call quotas, call quality/transcript scoring (that's the existing call agent), CallRail marketing numbers, HubSpot owner-based routing (parked with the workflow revamp, reminder Sep 9).

## Definition of done

- Two full weeks of digests with zero `unknown` seats and zero disputed attributions raised in L10.
- Roman can answer "who missed what, and did anyone catch it" from the Friday digest alone.

## Open for Roman

1. Confirm or overrule D1–D5.
2. Which Slack channel/DM gets the summary — you only, or you + Emily?
3. Should the digest also go to Mandy as escalation owner, even though she's not in any ring group?

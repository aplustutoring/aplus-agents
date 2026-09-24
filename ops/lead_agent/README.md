# ops/lead_agent — the reasoning lead engine

Not a workflow with templated emails.

For each active lead it assembles a dossier of everything we know, asks Claude
what the ONE next right thing is, and writes the message for that family. Then
Python decides whether it is allowed to happen.

```
   Claude DECIDES  ->  guardrails ENFORCE  ->  presend GATES  ->  code EXECUTES
```

Claude never holds the send button.

## Why not just give the model a send tool

The thing we are replacing (HubSpot flow 50818589, seven defects in
`docs/investigations/2026-09-14-online-lead-intake.md`) failed because a
machine made claims about reality it had no evidence for. It emailed families
"we could not leave a voicemail" from a branch default with no call placed, and
stamped `ATTEMPTED_TO_CONTACT` on a timer.

A model with a send tool can make that same mistake more fluently. So:

- **Every status needs its evidence in the dossier**, checked in Python
  (`status_evidence` in `config.yml`). `ATTEMPTED_TO_CONTACT` requires a real
  outbound CALL. `Meeting Booked` requires a real MEETING. `UNQUALIFIED` is
  never the agent's call at all.
- **Copy rules run on the text**, not as a polite request in a prompt. The em
  dash scrub and the STOP line are applied after the model returns.
- **Frequency and quiet hours are counted from the record**, not trusted from
  the reasoning.
- **Confidence below `high` is a human's call.**
- **A blocked send is never silence.** It becomes a task carrying the agent's
  read, its draft, and the reason it was held. Silence is how the old flow lost
  people.

## What it decides between

`send_sms` · `send_email` · `set_status` · `create_task` · `wait` · `handoff` ·
`nothing`

`wait` and `nothing` are real answers, and the prompt says so: *"An agent that
always finds a reason to send is a worse agent."*

## Draft mode

`send: false` in `config.yml`. Every outbound decision becomes a DRAFT on the
seat's task. The reasoning, the status logic, the gate and the guardrails all
still run, so a week in this mode is a rehearsal rather than a mock.

It cannot be flipped until `knowledge/journey/00-pre-send-checklist.md` and
`01-first-touch.md` are REVIEWED and `agent_readable`. See
`knowledge/journey/REVIEW-2026-09-15.md` for what is blocking that.

## Run it

```bash
cd ops/lead_agent
pip install -r requirements.txt
python3 lead_agent.py                    # plan only, one line per decision
python3 lead_agent.py --contact 3495701  # one lead, for verification
python3 lead_agent.py --live             # writes tasks, notes, statuses
python3 -m pytest tests/ -q              # 20 guardrail tests, no network
```

## Model

`model_tier: customer_copy`, resolved from `models:` in `email/config.yaml` —
the one place the fleet declares what it runs. This engine writes live customer
copy, so it sits in the top tier by risk.

Adaptive thinking, effort `high`, structured output against a fixed decision
schema so the answer is never prose we have to parse. The system prompt and the
CARE values are one cached prefix, so the per-lead cost is the dossier only.

## Relationship to ops/lead_intake

`ops/lead_intake` was the deterministic first cut: cursor selection, routing,
and a fixed cadence ladder. This engine supersedes its decision layer and keeps
its two good ideas (poll by `recent_conversion_date` cursor, exit on real
MEETING objects rather than a title match). `lead_intake` is marked
`deprecated` in `registry.yml` rather than deleted, because its templates and
cadence config are the reference for what the agent is expected to produce.

## Related

- `docs/investigations/2026-09-14-online-lead-intake.md` — the seven defects
- `docs/UNIFIED-OUTBOUND.md` — the presend spine
- `knowledge/journey/01-first-touch.md` — the ceiling on what it may do alone
- `prompts/decide.md` — the reasoning layer

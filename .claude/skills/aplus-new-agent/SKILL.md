---
name: aplus-new-agent
description: How A+ builds and ships an agent. Load this before creating any new agent, workflow, cron, or automation in aplus-agents, and before changing how an existing one is triggered or what it is allowed to send. Covers the registry entry, the workflow conventions (Pacific Time, checkout ref, dry-run switch), the ship gate, and what has to be true before an agent is allowed to talk to a human. Triggers: "build an agent", "new agent", "automate this", "add a workflow", "make it run every", "can we have something that".
---

# Building an A+ agent

Ground all reasoning and output in A+ CARE core values: `ops/values/care-values.md`.

Read this whole file before writing code. Every rule below was written after
something broke. The incident is named so you can tell which rules are load
bearing (all of them).

## 0. Before any code: what kind of agent is this

Answer these four out loud, in the PR description, before you write a line.

| Question | Why it decides the build |
|---|---|
| Does it produce language a human reads, or only data? | Reasoning agents carry the CARE pointer and the journey pointer. Deterministic agents (syncs, sweeps, metrics, relays, list builders) do NOT. A pointer inside a sync is dead text a later reader mistakes for something load bearing. |
| Does anything it produces reach a family, a teacher, or a tutor? | If yes, it passes the pre-send checklist and the copy rules. Load the `aplus-outbound-copy` skill. |
| Does it write to HubSpot? | If yes, load the `aplus-hubspot` skill. Property changes are declared in `ops/hubspot-schema/properties.yml` first, never created ad hoc. |
| Is the work inherently scheduled, or is it a reaction to an event? | Default is event driven: webhook to relay to `repository_dispatch`. Cron is for digests, sweeps, and demoted safety-net polls only. (#AP009, Roman 2026-09-04.) |

If the answer to any of these is "I am not sure", ask Roman before building.
Guessing here is how an agent ends up texting a family on a Saturday.

## 1. The registry entry comes first

`registry.yml` is the source of truth for the fleet. Its own first rule: if it
is not here, it does not exist. On 2026-08-20 an audit found **nine** live
workflows with no registry entry, three of them writing to HubSpot, running for
weeks. `ops/fleet-health/registry_check.py` is the watcher that now fails CI in
both directions, so a missing entry blocks the PR.

Write the entry before the code, because filling it in forces you to answer
what the agent reads, what it writes, and who owns it.

```yaml
  - id: my-agent                 # stable slug, becomes a HubSpot source_agent value
    runtime: github-actions
    engine: <which engine this belongs to>    # required, groups docs/FLEET.md
    name: Human label (matches the workflow `name:`)
    owner: roman@wetutorathome.com
    status: unverified           # new agents are never born "active"
    probation: draft             # nothing goes out without a human approving it
    trigger:
      type: cron | event
      schedule: ["0 17 * * 1 (Monday sweep, 09/10 PT)"]
      events: [workflow_dispatch]
      workflow: .github/workflows/my-agent.yml
    entrypoint: ops/my-agent/my_agent.py
    reads: [...]                 # every system it consumes
    writes: [...]                # everything it mutates, including repo state
    depends_on: [...]
```

Check it with `python3 ops/fleet-health/registry_check.py` before you push.

## 2. Workflow conventions that are not optional

Copy an existing workflow rather than starting blank.
`.github/workflows/tutor-issues.yml` is a good model.

```yaml
name: My agent — what it does

# Fleet convention: agents think in Pacific Time (TZ below); crons are UTC.
env:
  TZ: America/Los_Angeles

on:
  schedule:
    - cron: "0 17 * * 1"        # comment every cron with its PT meaning
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Dry run (plan + report, write nothing, send nothing)"
        required: false
        type: boolean
        default: true            # manual runs default to DRY, always

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main              # REQUIRED for any agent that commits state back
```

Three rules inside that block, each from an incident:

- **`TZ: America/Los_Angeles` in every workflow.** Naive `datetime.now()` in
  scripts then resolves to PT, which keeps human-facing labels and date-window
  logic in sync. Machine-facing values (state cursors, API epoch params, audit
  logs) stay explicit UTC.
- **`ref: main` on checkout for anything that commits state.** A queued run
  starts from the SHA at dispatch time, not from current main. On 2026-09-10
  that produced **16 duplicate HubSpot items** (PR #214). Locked.
- **Both a PDT and a PST cron** when the wall-clock hour must be stable across
  daylight saving.

If the agent is temporary (an event booth, a campaign), it carries a **SUNSET
guard**: a hard date after which it refuses to run. An every-minute cron once
ran 19 days past its event because nothing stopped it.

## 3. Born switched off

Every new agent ships with two independent brakes.

1. **`dry_run` defaults to true** on manual dispatch. A dry run plans, prints,
   and writes nothing.
2. **A repo variable gates live behavior**, named `<AGENT>_LIVE`, defaulting to
   absent, which means dry. Precedent: `FEEDBACK_AGENT_LIVE`, `CALL_AGENT_LIVE`,
   `REASONER_LIVE`. Roman flips it in Settings > Secrets and variables >
   Actions > Variables when he is satisfied, and not before.

The rule: **merged does not mean live.** A PR being approved means the code is
right. Going live is a separate, later, explicit decision by Roman.

## 4. Fail loudly, never silently

The worst failure mode in this fleet is not an agent doing the wrong thing. It
is an agent reporting success while doing nothing. On 2026-09-16 five scorecard
rows had been silently refused for nine days because the API returned HTTP 200
with the refusal in an `errors` array and the client returned `r.json()` without
reading it. Ten green runs, five wrong numbers on the leadership scorecard.

So: check the body, not just the status code. Raise on refusal. Retry only the
throttle cases. Exit non-zero at the end of a run that had any refused write,
and name every one of them in the log. A number computed against a default is a
wrong number, not a warning.

## 5. Tests

Every engine has a `tests/` directory next to it. Add tests with the agent, not
after. Run the suite before you push:

```bash
python3 -m pytest email -q
```

**Pin your own clock.** Tests that read the wall clock pass Monday to Friday and
fail every Saturday, because the business-day and quiet-hour gates are real.
Freeze an explicit instant in the test and date every fixture back from it.

## 6. What an agent is allowed to say

If the agent produces anything a family, teacher, or tutor reads:

- It carries this line in its prompt, under the CARE line:
  > Before contacting a family, teacher, or tutor, read knowledge/journey/README.md
  > and pass knowledge/journey/00-pre-send-checklist.md. Act only on stages marked REVIEWED.
- It passes the six pre-send checks in `knowledge/journey/00-pre-send-checklist.md`
  and writes the six answers into the HubSpot note or the run log before sending.
- Load the `aplus-outbound-copy` skill for the locked copy rules.

"Watch" means read and report. Relaying, posting and texting each need their own
go. An agent told to watch replies once texted a family from the wrong line, and
the mother asked how many people she was talking to at A+.

## 7. Naming

Config keys, properties, audit actions and Slack routing name **roles**
(`charter_sales`, `scheduler`, `tutor_quality_owner`), never people. The
`staff:` block in `email/config.yaml` is the only place a person's name lives,
so a team change is one edit in one file. On 2026-09-17 a scheduler told a
waiting family that a person who no longer worked here would be right with them.

## 8. Finishing

Before the PR is done:

- [ ] `registry.yml` entry, and `registry_check.py` passes
- [ ] `status: unverified`, `probation: draft`, `<AGENT>_LIVE` gate absent
- [ ] `TZ` set, crons commented with PT meaning, `ref: main` if it writes state
- [ ] Tests added and `python3 -m pytest <engine> -q` green
- [ ] CARE pointer if it reasons, no pointer if it is deterministic
- [ ] Journey pointer and pre-send gate if it can reach a human
- [ ] An entry appended to `docs/CHANGELOG.md`: date, what changed, **why**,
      files touched

If a decision got locked along the way, remind Roman to log it to the A+
Decision Log in `#AP###` format.

## 9. Never close an investigation by moving on

If you are building this agent because something broke, the incident ends one of
two ways: a system change that makes that failure class impossible, or an
explicit written line saying "no system fix exists because X". A plausible story
plus a human workaround ("forward it to us", "check the portal", "do it
manually") is not a resolution. When evidence contradicts your story, the story
is wrong somewhere. Keep pulling until the contradiction resolves.
(Roman 2026-08-31, locked.)

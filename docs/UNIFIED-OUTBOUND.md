# One outbound spine

Roman, 2026-09-14: "All of the SMSes have to work the same way. This all has to
be unified, not looking at the pieces that I crafted over six years without AI.
One feature where agents know what the other one's doing."

The spine already exists. It is `email/src/presend.py`, written 2026-09-09 after
the Gonzalez family got texted three times from the lead line while scheduling
had them on the support line. It is not a new thing to build. It is half
installed, and the biggest offender is not in this repo at all.

## What the spine already does

`presend.check(contact_id, channel, from_line, purpose, ...)` is the code form of
`knowledge/journey/00-pre-send-checklist.md`. Before any outbound it reads:

- **opt-out** (`sms_opt_out`, `hs_email_optout`) and quiet hours
- **the audience → line rule** (LOCKED 2026-09-08): lead and TOR go from
  charter_sales, scheduling and tutors from support. Wrong line is a BLOCK.
- **every other line's thread history** via the JustCall index, 14-day window.
  An active thread or an unanswered reply on another line HOLDs and names the
  seat that owns it.
- **the shared inbox** for unanswered replies
- **open tickets owned by scheduling**
- **frequency**: texts sent today across ALL lines, and
  `agent_last_outbound_at` / `agent_last_outbound_seat` on the contact, so one
  agent can see the last touch any other agent made
- **standing go** per purpose, and the STOP line on any cold SMS

`presend.record_send(...)` is the send log of record: a HubSpot note on the
contact, the two `[Agent]` properties, and an audit line. That note plus those
properties ARE "agents know what the other one's doing". The properties are
already declared in `ops/hubspot-schema/properties.yml`.

A source that cannot be read yields HOLD, never a silent ALLOW, because "quiet
phone" and "could not fetch" lead to opposite conclusions.

## Who is on the spine today

| Outbound path | On the spine? |
|---|---|
| `email/src/sms.py` — po_welcome | Yes, but shadow only |
| `ops/messenger/one_to_few.py` | Yes, fully |
| `email/src/low_balance.py` `_send_sms` | **No.** Uses `presend.lines` for the line role, then calls `sms._jc_send` direct. No check, no note, no audit. |
| `email/src/low_balance.py` — 5 Resend email sites | **No.** |
| `ops/messenger/messenger.py` — bulk `jc_send_sms` | **No.** |
| `email/src/main.py` — inbox replies via `hs.send_message` | **No.** |
| **HubSpot flow 50818589, Lead Pipe Line - Online** | **Not in the repo.** Six years old, sends an email and an SMS from 818-573-6644 with no gate, no note, no audit, no property stamp. |
| `ops/call_agent` | N/A, sends nothing outbound |

Two of roughly seven paths. And `presend.enabled: false` in `email/config.yaml`,
so even those two only log their decision as `presend_shadow` and send anyway.
The gate has never actually stopped anything.

## The three moves

### 1. Flip the switch (one line, this week)

`presend.enabled: true`. The engines already carry the shadow branch. Read a
week of `presend_shadow` audit lines first and confirm there are no false HOLDs;
that check was the whole point of shadow mode and it has been running since
2026-09-09.

### 2. Put the remaining engines on the spine (small, mechanical)

`low_balance._send_sms` and its five Resend sites, bulk messenger, and the inbox
reply path each need the same two lines that `sms.py` already has: a
`presend.check` before, a `presend.record_send` after, and a declared purpose in
`presend.purposes`. Nothing else about those engines changes.

This is the one that matters most right now: low_balance is the newest engine,
armed 2026-09-10, texting families about money, and it cannot see that
scheduling is mid-thread with the same family.

### 3. Retire the lead pipe into an agent: `ops/lead_intake/`

Flow 50818589 cannot be put on the spine, because it is a HubSpot workflow and
the spine is Python. It has to be rebuilt as an engine like every other one.
Seven defects are documented in
`docs/investigations/2026-09-14-online-lead-intake.md`; every one of them is a
symptom of living outside the fleet.

```
ops/lead_intake/
  lead_intake.py          entrypoint
  config.yml              cadence, purposes, routing
  templates/              first touch, no answer, chase
  state/cursor.json       committed back by the run
.github/workflows/lead-intake.yml   cron every 15 minutes
```

How it works, and what each line fixes:

1. **Poll by cursor, not by form.** Select contacts whose
   `recent_conversion_date` is newer than the state cursor. A cursor has no
   memory of 2023, so **F7 (past customers locked out) stops existing** — David
   Reich resubmitting on 09-10 is just a row newer than the cursor. And a new
   site form cannot fall out of the pipe, which is **F5**.
2. **Classify** with the persona logic `presend._audience` already has:
   family, teacher of record, tutor, spam.
3. **`presend.check(... "lead_first_touch")`** before the text and the email.
   The gate reads the other lines, the inbox and open tickets. The Gonzalez
   failure and the "I don't know how many people I'm talking to at A+" problem
   cannot recur for leads either.
4. **Send, then `record_send`.** One sender, one log, one note on the contact.
   The SMS body is a template in the repo, reviewed like every other template,
   so **F4** (a text reading "My name is 81494333") cannot ship.
5. **Create the alert task immediately**, owner by the 2026-08-25 routing rule.
   **F2** (the 15:30 delay, up to 23 hours) disappears because there is no
   delay-until-time-of-day; the action window handles quiet hours already.
6. **Cadence from agent state, and re-gate every follow-up.** If Paola called,
   or the family is texting scheduling, the next touch HOLDs by itself.
7. **Stamp only what is true.** The agent reads CALL engagements before writing
   `hs_lead_status`. Today the workflow stamps "Attempting to Contact" on a
   timer and emails the family "we could not leave a voicemail" when nobody
   dialed (**F1**), purely because a HubSpot branch cannot tell the difference
   between a call and a clock.

Then switch flow 50818589 off and register `lead-intake` in `registry.yml`. Per
the CARE rule it carries the values line and the journey pointer: it is a
reasoning agent that produces family-facing language.

## The order, and the honest caveat

Move 3 is weeks. F7 is costing money every day a past customer resubmits and
hears nothing. So do not let the rebuild block the bleeding:

1. **Now, in the HubSpot UI:** fix the F7 goal, delete the F2 delay, and
   re-point the F1 default branch. Minutes of work, no code.
2. **This week:** flip `presend.enabled` and put low_balance on the spine.
3. **Then:** build `ops/lead_intake/`, cut over, turn 50818589 off.

The last piece of the six-year-old stack is the one that never learned to talk
to the others. That is the whole problem, and it is one engine wide.

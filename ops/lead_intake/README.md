# ops/lead_intake — stage 01, first touch

A person submits a form. A human is told, fast, with everything they need.

That is the whole job. It is the first stage of
`knowledge/journey/01-first-touch.md`, and it replaces HubSpot flow 50818589
"Lead Pipe Line - Online", six years old and outside the fleet, whose seven
defects are traced in `docs/investigations/2026-09-14-online-lead-intake.md`.

## What it does on each poll

1. **Select** contacts whose `recent_conversion_date` is newer than the cursor
   in `state/cursor.json` and whose conversion event matches `intake_events`.
2. **Classify** into family / TOR / decision maker / tutor, persona first, lead
   status second (most contacts still have no persona).
3. **Look up prior deals.** A returning family leads the alert with its history.
4. **Run the gate.** `email/src/presend.check()` — opt-out, quiet hours, the
   locked audience-to-line rule, threads on every other JustCall line, the
   shared inbox, open scheduling tickets, frequency, the STOP line.
5. **Create the alert task** for the routing seat, due in the audience SLA
   (90 minutes for a family), carrying the gate verdict, the name of whoever
   owns an active thread, and a drafted first touch.
6. **Stamp an `[Agent]` note** on the contact.

It does **not** text or email the family, and it does **not** write a lead
status. Both are deliberate; see below.

## Why it does not send

`knowledge/journey/01-first-touch.md` sets the ceiling for this stage:

> **Alone:** classify, create the ticket with the routing table's owner and
> SLA, stamp an `[Agent]` note, log the call, stamp the lead status the call
> ladder allows.
> **Draft:** the reply, for the owning seat to send from HubSpot.

So the first reply to a human being is a draft, by our own playbook. The old
flow auto-sent an email and an SMS with no human in the loop, which is above
that ceiling. `send: false` in `config.yml` is the ceiling in code.

And it cannot be flipped yet: stages `00-pre-send-checklist.md` and
`01-first-touch.md` are both `status: DRAFT` / `agent_readable: false`. The
playbook's own rule is that an agent reads a stage only if REVIEWED, and 00
must be REVIEWED before any stage is readable. **Getting 00 and 01 signed off
is the gate on this engine sending anything.** The entrypoint refuses to run
if `send` is true, so the two cannot drift apart.

## Why it never writes a lead status

The old flow stamped `ATTEMPTED_TO_CONTACT` on a timer, and emailed families
"we could not leave a voicemail" from a branch's DEFAULT path, with no call
ever placed (verified on three contacts with zero CALL records). A HubSpot
branch cannot tell a call from a clock. This engine does not try: New (Inbox)
is the truth until a real call moves it, and the call ladder that does that
lives in `ops/call_agent/`.

## Run it

```bash
cd ops/lead_intake
pip install -r requirements.txt
python3 lead_intake.py                       # dry run, prints one row per lead
python3 lead_intake.py --contact 3495701     # one contact, for verification
python3 lead_intake.py --live                # writes tasks + notes, moves the cursor
python3 -m pytest tests/ -q
```

The first run on an empty cursor **baseline-stamps and creates nothing**, the
standard fleet guard. A run over `max_leads_per_run` aborts before any write.

## The cursor is the design

Selection is a cursor over `recent_conversion_date`. Not a list of form GUIDs,
not a goal. That single choice removes two defects structurally:

- A new landing page carrying the same intake form is covered the day it ships,
  instead of needing its GUID pinned into a workflow (F5).
- A family who has been with us before is just a row newer than the cursor. The
  old flow's exit goal was "associated deal with `start_of_tutoring_for_this_deal`
  known", and HubSpot never enrolls a contact who already meets the goal, so
  **every past customer was permanently locked out**. David Reich resubmitted on
  2026-09-10 and got nothing at all; he called us four days later (F7).

## Related

- `docs/investigations/2026-09-14-online-lead-intake.md` — the seven defects
- `docs/UNIFIED-OUTBOUND.md` — the presend spine and who is still off it
- `knowledge/journey/01-first-touch.md` — the ceiling
- `email/src/presend.py` — the gate

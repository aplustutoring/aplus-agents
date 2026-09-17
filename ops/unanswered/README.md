# ops/unanswered — somebody asked for a person and nobody got back to them

Over 2026-09-14 to 09-16, four people texted A+ asking for a named human:

| Who | What they wrote |
|---|---|
| Inna Volodinsky | "Dear Roman... Can you give me a call when you get a chance." |
| Annie Wolfstein | "Please feel free to call me at 661-904-3139." |
| A new number | "Hey Roman. Michael has the PSAT coming up in about a month." |
| Mary Gonzalez | "Janelle can you please call me", then "Yes can you call me now please" |

The team answered three of them, by phone, one within **68 seconds**. Nothing
watched that, so the only way to know was to go and look, and looking at the
text log alone produced three false alarms that accused the team of neglect
while they were on the call.

The fourth, the PSAT parent, has never been answered. Nothing noticed.

The call agent already handles the equivalent for a ringing phone: a missed
call becomes a Slack alert plus a same-day HIGH call-back task within two
minutes. A text asking for a person had no equivalent. This is it.

## Two rules it is built around

**Detection is literal.** A message counts only if it asks to be called, or
names a member of staff on a word boundary. Inferring "this sounds like
someone who wants a human" would put a neglect alert on a thread that is
going fine. A thank-you naming the person who just helped is excluded by
prefix, because that is the commonest false positive by far.

**Resolution is cross-channel and self-healing.** "Has anyone got back to
them" is answered by HubSpot's `notes_last_contacted`, which aggregates calls,
emails, texts and meetings. The moment it moves past the ask, the task is
completed and the alert forgotten. Narrowing that to one channel is exactly
the mistake this agent exists to stop making.

## What it does

1. Reads inbound texts across every line (paging from 0 — see below).
2. Keeps the ones that ask for a person.
3. Waits out `resolve.grace_minutes` (25) so a normal reply lands first.
4. Resolves the number to a contact, calculated phone index first.
5. If nobody has touched them since, opens a HIGH task on the contact and
   posts to `#calls`, tagging the named person if the message named one.
6. On every later run, re-reads each open ask and closes it the moment the
   contact is touched on any channel.

An ask from a number that does not resolve still alerts. A stranger asking us
to call them is more urgent, not less.

## Dry run over the incident week

383 inbound texts, 72 hours, **1 alert**: the PSAT parent, still unanswered
and not in HubSpot. Inna, Annie and Mary were all correctly suppressed because
the contact record showed they had been called back.

## Running

    python3 ops/unanswered/unanswered.py [--dry-run] [--report-json PATH]

First run stamps a baseline and creates nothing. That is not configurable off.

## Why this one is allowed a cron

Roman's 2026-09-04 rule is that agents avoid cron unless the work is
inherently scheduled. Here it is: the agent has to re-check, later, whether a
grace window elapsed and whether anyone has since replied. The self-healing
pass is periodic by nature.

The detection half does not have to be. Once the JustCall inbound-SMS relay
(PR #221) is deployed, a text can fire this directly and the cron shrinks to
just the closing sweep.

## Guards

- Baseline first run creates nothing.
- `max_alerts_per_run` (8) — the aging-sweep near-miss of 2026-08-25 fired 80
  DMs in a dry run; refuse to act rather than flood.
- One open ask per contact; a second text does not double-alert.
- JustCall paging starts at **page 0**. Passing `page=1` skips the newest 100
  texts, which made a monitor report "quiet" for ten hours on 2026-09-12 while
  six families were writing in.

## Core values

Ground all reasoning and output in A+ CARE core values:
`ops/values/care-values.md`. Read that file, do not restate it here.

Before contacting a family, teacher, or tutor, read knowledge/journey/README.md
and pass knowledge/journey/00-pre-send-checklist.md. Act only on stages marked
REVIEWED. (This agent is internal-only: it creates tasks and Slack alerts for
staff and never messages a family itself.)

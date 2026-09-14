# Online lead intake: where it goes wrong (2026-09-14)

Trace of what happens to a family who fills out a form on the website, from
submit to first human contact. Read-only investigation: nothing in HubSpot was
changed. Every timing claim below is measured from live records, not from the
flow definition alone.

## The pipe

One HubSpot workflow carries every web lead: **`Lead Pipe Line - Online`
(flow 50818589)**, contact-based, enabled, created 2021-01-20, last edited
2026-06-11 (the 2026-08-17 session patched only its exit goal). Definition
snapshot: `ops/fleet-health/audit/backups/2026-08-17-lead-pipe-line-online-before-goal-patch.json`.

Enrollment: an OR of **29 hard-coded form GUIDs**, re-enrollment ON.
Action window: 07:30 to 23:00, seven days a week.

Measured chain for a submit at time T:

| # | Action | When it actually fires |
|---|---|---|
| 1 | `hs_lead_status` = `NEW` ("New (Inbox)") | T |
| 2 | `hubspot_owner_id` = 81494333 (Paola Sarmiento) | T |
| 3 | Automated email `1st outreach web leads Roman` (content 196078072749) | T + ~25s (verified) |
| 15 | Delay 2 minutes | |
| 56 | SMS from 18185736644 (charter_sales line) | T + 2m (NOT verified, see F4) |
| 17 | **Delay until 15:30** | |
| 57 | Task `New Lead Alert: <name>` to Paola | **15:30 PT, verified on every task** |
| 18 | Branch: any associated engagement? | 15:30 |
| 28 | Delay 55 minutes | |
| 35 | Branch on call disposition | 16:25 PT |
| 36/40 | Follow-up email | 16:25 PT (verified) |
| 41/43 | Delay 60 minutes | |
| 42/44 | Branch | 17:25 PT |
| 48/49 | `hs_lead_status` = `ATTEMPTED_TO_CONTACT` | 17:25 PT |

Exit goal: an associated deal with `start_of_tutoring_for_this_deal` known, OR
(added 2026-08-17) lead status = Meeting Booked.

The live records match this chain to the minute, so the snapshot is an accurate
picture of what is running today.

## What it produces

42 contacts converted on the Main Intake Form between 2026-08-01 and 2026-09-14:

| Lead status | Count |
|---|---|
| Attempting to Contact | 17 |
| Check Back Quarterly | 9 |
| QTL - NEW | 6 |
| New (Inbox) | 3 |
| Dead Opportunity/Unqualified | 3 (spam fills) |
| Open deal | 2 |
| QTL - Charter | 1 |
| Teacher of Record/EF/ES | 1 |

20 of 42 are parked in New/Attempting. 2 of 42 reached Open deal.

`New Lead Alert` tasks in the same window: 57 created, **17 Not Started**. The
not-started ones cluster from 2026-09-02 on: of the last 14 tasks, 12 are
untouched.

## Findings

### F1 (worst) — the family is told we tried to call when nobody dialed

Branch 35 reads the call disposition of associated calls. Its **default** branch
is named "Did Not Connect - Voicemail not setup or Full" and sends email
41192638620, `1st Phone Call - Unable To Leave VM`. A lead with **no call at
all** has no disposition, so it lands on that default and gets the email.

Verified: contacts 247575268403 (Vaani Arora), 247775390480 (Rudy A Gonzalez)
and 246483479164 (Jacqueline Venegas) have **zero associated CALL records** and
all three carry `hs_email_last_email_name = "1st Phone Call - Unable To Leave VM"`.

Two harms. The family is told something untrue about their own voicemail. And
the record is then stamped `ATTEMPTED_TO_CONTACT` at 17:25 the same day, so the
CRM shows outreach that never happened and the lead drops out of any "New
(Inbox)" queue without a human having touched it. All 17 "Attempting to Contact"
rows above are suspect on this basis.

### F2 — the alert task is held until 15:30, so speed-to-lead is up to 23 hours

Action 17 is a delay-until-time-of-day at 15:30 sitting **before** the task
creation. Every `New Lead Alert` task in the portal is stamped 3:30 PM PT.
Measured gaps from form submit to the task Paola sees:

| Lead | Submitted (PT) | Task created (PT) | Gap |
|---|---|---|---|
| Lincoln Campbell | 2026-09-11 16:09 | 2026-09-12 15:30 | 23h 20m |
| Vishta Granados | 2026-09-09 15:50 | 2026-09-10 15:30 | 23h 40m |
| Rudy A Gonzalez | 2026-09-10 18:06 | 2026-09-11 15:30 | 21h 24m |
| Vaani Arora | 2026-09-09 23:57 | 2026-09-10 15:30 | 15h 33m |
| Sivan Radnia | 2026-09-07 23:03 | 2026-09-08 15:30 | 16h 27m |

Anything submitted after 15:30 waits for the next afternoon. The automated email
goes out in 25 seconds; the human signal takes up to a day.

### F3 — "Connected" is satisfied by our own automation, and the lead dies at NEW

Branch 18's "Connected" test is: any associated engagement whose
`hs_engagement_type` is one of CALL, CONVERSATION_SESSION, FORWARDED_EMAIL,
NOTE, INCOMING_EMAIL, MEETING, **EMAIL**. The workflow's own outbound email at
T + 25s is an EMAIL engagement, and a note logged by any other agent is a NOTE.
So the branch can read "Connected" with no human contact, and that branch has no
next action: the workflow ends, the contact stays at `NEW`, and nothing ever
re-raises it.

Live: Vishta Granados (247513507001) has been at New (Inbox) since 2026-09-09
with zero calls. Satpal Sidhu (245580383372) has been at New (Inbox) since
2026-08-31.

F1 and F3 are the two exits from branch 18 and both are wrong. Which one a lead
gets depends on whether the email engagement happened to be associated by 15:30,
so the outcome is a race.

### F4 — the SMS names the owner ID instead of a person, and may not send at all

Action 56 body, verbatim:

> Hi {{ _0_1.firstname }}, thanks so much for reaching out to us. My name is
> **{{ enrolled_object.hubspot_owner_id }}**, I am with the Student Success team
> at A+ Tutoring. ...

`hubspot_owner_id` is a numeric ID. As written the family is texted "My name is
81494333". Separately, no SMS channel is configured in the HubSpot conversations
inbox (only Email, Live Chat, Facebook Messenger, Forms), and no SMS activity
surfaced for any 2026-09 lead, so the action may be failing silently instead.
**Needs one manual check:** open a recent lead's timeline in HubSpot and see
whether an SMS from 18185736644 is logged.

The from-number itself is correct: 18185736644 is the charter_sales line, which
is the right line for a family with no deal (`email/config.yaml` presend.lines).

### F5 — enrollment is 29 pinned form GUIDs, so a new form is silent

Any form added to the site that is not one of the 29 GUIDs produces a contact
with no owner, no lead status, no email and no task. Worth auditing: contacts
converting on `Student Diagnostic Test Upload` and `Get Started Now Full Length`
are not consistently landing on Paola, which is the signature of a form that is
not in the list.

### F7 (new, worst yet) — past customers are permanently locked out of the pipe

The exit goal is "associated deal with `start_of_tutoring_for_this_deal` known".
HubSpot evaluates a goal at enrollment: a contact who already meets it is never
enrolled. So **any family who has ever started tutoring can never re-enter the
online lead pipe.** They resubmit the form and get nothing: no email, no text,
no owner, no status change, no New Lead Alert task. The 2026-08-17 second goal
("lead status = Meeting Booked") adds the same lockout for anyone ever booked.

Worked example, contact 3495701 (stored as firstname "Reich" / lastname "David",
i.e. David Reich, a 2023 customer):

| When (PT) | What |
|---|---|
| 2023-10-08 | First conversion, same Main Intake Form |
| 2023-10-09 12:26 | Danielle calls him back, 8m45s |
| 2023-10-12 | Deal `David Reich - Juliana` ($680), tutoring starts 2023-10-19 |
| 2023-11-13 | Renewal deal ($340), both closed |
| **2026-09-10 07:36** | **Resubmits the Main Intake Form. Nothing happens.** |
| 2026-09-10 to 09-14 | Silence. Zero emails (last send was the 08-31 NSSA badge), zero calls, zero tasks, no owner change, no lead-status change |
| 2026-09-14 10:51 | **He calls us**, 3m34s, for his son Nicholas and the Science Academy STEM Magnet exam |
| 2026-09-14 10:53 | Call agent logs the summary, a 4.1/5 quality eval, and three follow-up tasks to Paola; Roman notes "@Paola did you have a chance to connect with them" |

Four days and three hours of silence on the warmest lead type there is, closed
only because the parent chased us. This is the failure class the investigation
rule points at: the goal was written to mean "stop chasing once they start" and
it silently also means "never chase again, ever".

Two smaller things on the same record: his name is stored reversed (firstname
"Reich"), so every templated greeting reads "Hi Reich"; and his contact owner is
still Danielle from 2023 while the live tasks sit with Paola, against the
2026-08-25 routing rule that families go to the charter_sales seat.

### F6 — open loop from 2026-08-17

`Lead Pipe Line - Ads - Free Lesson` (149937308) still needs the Meeting Booked
exit goal added by hand; the API PUT 500'd on 2026-08-17 and no changelog entry
since records it as done. Booked families on the ads path keep getting chased.

## Proposed system fixes

Nothing here has been applied. F1 through F3 change what families receive, so
they need Roman's go.

1. **F1** Re-point branch 35's default branch to a no-op (or to the
   "Attempting to Contact" stamp only). The "voicemail not set up or full"
   email must fire only on a real call disposition, never on the default.
2. **F1b** Move actions 48/49 so `ATTEMPTED_TO_CONTACT` is stamped only when an
   actual outbound call exists. A status that means "we tried" must be written
   by a try, not by a timer.
3. **F2** Delete action 17 (the delay to 15:30). Create the task immediately
   after enrollment. If Paola should not be pinged overnight, use the existing
   07:30 to 23:00 action window rather than a fixed hour.
4. **F3** Narrow branch 18's "Connected" test to CALL and MEETING only, and give
   the Connected branch a real next step instead of a dead end.
5. **F4** Replace the SMS token with the literal "Paola", and confirm the SMS
   action is actually delivering before trusting it at all.
6. **F5** Replace the 29 pinned GUIDs with a property-based trigger
   (`recent_conversion_event_name` contains the intake form name), so a new form
   cannot silently fall out of the pipe.
7. **F6** Add the Meeting Booked goal to 149937308 in the UI.
8. **F7** Split the goal from the lockout. The exit goal should be scoped to the
   *current* re-engagement (a deal created after this enrollment, or lead status
   Meeting Booked set after this enrollment), not to any deal in the contact's
   history. Simplest safe version: replace the deal-based goal with
   "lead status is Meeting Booked OR Open deal", which a dormant past customer
   does not satisfy on resubmit. Until that lands, a returning family that
   resubmits the form is invisible, so a second trigger is worth adding: notify
   the charter_sales seat whenever `recent_conversion_date` updates on a contact
   with `lifecyclestage = customer`.

Per the investigation rule, the failure class to close is "a lead can leave the
pipe without a human, and the CRM will say otherwise". Fixes 1, 2 and 4 make
that impossible; fix 6 makes a new form impossible to miss.

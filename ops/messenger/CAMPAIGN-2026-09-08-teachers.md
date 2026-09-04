# Charter teacher outreach 26/27 — handoff (built 2026-09-04, launch Tue 2026-09-08)

Roman "Go" 2026-09-04. Council record: `docs/councils/2026-09-02-charter-teacher-outreach.md`.
Copy (source of truth): `ops/messenger/templates/teacher-outreach-2026-09/`.
Goal: teachers send students. Every teacher gets both messages (Stanford Badge,
Teacher Scholarship); the list decides the order and the rail.

## Rules that apply to everything

- Email only. No call tasks, no meeting links (Roman 2026-09-03).
- From Danielle Brodetsky. Campaign reply-to info@ so the classifier routes
  replies to the sales seat and stamps `[Agent] Campaign Replied`.
- Every student has funds; never "students with funds." The school issues the
  PO; never "we handle the PO." No em dashes. Under 120 words.
- Weekday sends, 9am to 5pm PT. Exit on reply, on `campaign_replied = Yes`, on
  a Teacher Scholarship nomination, on a new 26/27 charter deal naming the teacher.
- Scholarship cap this round: 40 students. First 40 nominations from teachers
  who have never sent us a student, one per teacher until 40, then seconds.
  Past the cap → "Does Not Qualify" stage, with a note.
- Teachers from this outreach who nominate enter the Teacher Scholarship
  teacher pipeline at "Opted Out of Call OR Met at Event – Sent Flyer", never
  at stage 1 (that stage fires the "book a call" emails).

## The audience (HubSpot static lists, built 2026-09-04)

| List | Name | Count | Rail |
|---|---|---|---|
| 3210 | 1 Worked With Us (sequence) | 159 | Sequence 1, Danielle's inbox |
| 3211 | 2 Known Schools Cold (sequence): iLEAD 130, Sage Oak 47, Blue Ridge 26 | 203 | Sequence 2, Danielle's inbox, 50/day |
| 3212 | 3 Stranger Schools Cold (campaign), 23 schools | 304 | Marketing workflow, one wave per school group |
| 3215 | 3a Wave 1 = Compass 96 + Elite 26 | 122 | Workflow 1878517306 |
| 3213 | 4 IEM Education Specialists (campaign) | 272 | Workflow 1878501648, own wave |
| 3214 | Top 30 of list 1 by charter deal $ | 30 | Hand-written day-10 note |

Excluded everywhere: 30 generic inboxes (`generic_inbox = Yes`), 56 opt-outs,
33 bounces, 22 already in the Sage Oak Summit sequence, 4 with no school, 1
no email, 1 internal. Refresh: `python3 scripts/teacher_outreach_lists.py --build-lists`.

## Sequence rail (Danielle assembles in the portal, ~10 minutes each)

Sales email templates have no API, so the two sequences are a portal step.
Copy is in `seq1_worked_with_us.md` and `seq2_known_schools.md`.

**Sequence 1 — Teacher Outreach 26/27 - Worked With Us**
1. Email 1 (day 0): "{{firstname}}, your A+ families from last year".
2. Email 2 (day 5, threaded, business days): "One name is enough".
3. Finish. Settings: business days, 9:00 to 17:00. Unenroll on reply (default).
4. Enroll list 3210 in batches of 50 per day starting Tue 9/8, 9am.
5. Day 10: for anyone on list 3214 still silent, Danielle sends a two-line
   note in the same thread naming one family from
   `python3 scripts/teacher_roster.py <email>`.
6. "Send it" replies: run the same roster script, paste.

**Sequence 2 — Teacher Outreach 26/27 - Known Schools**
1. Three versions of email 1 (iLEAD / Sage Oak / Blue Ridge opening line) or one
   template with the opening line pasted per batch; emails 2 and 3 shared.
2. Email 2 day 4, email 3 day 10, both threaded. Business days, 9:00 to 17:00.
3. Enroll list 3211 at 50 a day, iLEAD first (130), then Sage Oak, then Blue Ridge.

## Campaign rail (scripted; publish + enable on send day)

| Wave | List | Workflow | Emails (AUTOMATED_DRAFT) |
|---|---|---|---|
| 1 Compass + Elite | 3215 | 1878517306 (OFF) | 221134168440 → +4d → 221140381845 → +6d → 221140381849 |
| IEM | 3213 | 1878501648 (OFF) | 221134168444 → +4d → 221140381853 → +6d → 221140381856 |
| 2+ (remaining stranger schools) | new sub-list per group | clone of 1878517306 | same three emails, retargeted |

Send-day checklist (Roman, portal):
1. Open each draft, read once, click Publish (marketing-email publish scope is
   not available to the API at this account tier).
2. Open the workflow, confirm enrollment list and the 4 exit goals, turn ON.
   Existing list members enroll immediately; sends respect the 9 to 5 window.
3. Wave 2 opens only after wave 1's day-10 numbers, and only if the 40-student
   cap has room.

## Measurement

- Replies per list: `campaign_replied = Yes` (stamped by the info@ classifier,
  PR pending merge) plus `hs_email_last_reply_date` for inbox replies.
- Nominations per list: Teacher Scholarship family deals created, joined to the
  nominating teacher.
- Charter deals created naming a list-1 teacher within 30 days
  (`scripts/campaign_revenue_report.py` pattern).
- Opens are noise.

## Not built (needs Roman or Danielle)

- Post-trial teacher email: a workflow step at "Trial Complete" that tells the
  nominating teacher what the tutor saw and what to put on the PO. Today WF-03
  only emails Paola. This is the step that turns the scholarship into POs.
- Danielle's note to IEM central office (parallel to the IEM wave).
- The Teacher Scholarship program's own stage-1 "book a call" emails should
  become the exception, not the front door (email-only rule). Danielle's call.

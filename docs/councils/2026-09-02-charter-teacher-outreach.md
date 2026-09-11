# Council: charter teacher outreach for 26/27 (2026-09-02)

Convened by Roman via the first `/council` run. Topic: how to build a segmented
charter-teacher outreach that gets teachers to send students. Roman's thesis
under test: teachers who already worked with us get a plain "refer your funded
kids" ask with no scholarship pitch; the Teacher Scholarship Program is the
advocacy hook only for teachers who have not sent students in the last year.

## Evidence pulled first

| Fact | Source |
|---|---|
| Teacher (TOR/EF/ES) contacts: 1,084. Mailable after exclusions: 963 (30 generic inboxes, 56 opt-outs, 33 bounces, 1 no email, 1 internal). | HubSpot, `teacher_audience.py` |
| Worked-with-us teachers (list 3110): 151 mailable. Started-never-tutored (3111): 8. Cold: 804. | HubSpot lists |
| Teachers received exactly ONE email this school year: the NSSA badge send on 8/31 (931 teachers). The 8/17 teacher emails were never sent. | `hs_email_last_send_date` |
| 365 opened the 8/31 send. Zero teacher replies logged since 8/17 (`hs_email_last_reply_date`). Replies to info@ may exist but are not stamped on the contact. | HubSpot |
| Charter deal $ since Aug 2025: $589K across 238 teachers. Worked-with-us teachers: $525K (89%). Top 30 teachers = 50% of $, top 81 = 80%. | `deals_raw.json` |
| Teacher Scholarship Program: teacher nominates up to 2 students, A+ funds free 1:1 synchronous tutoring, family gets a consultation then trial. Existing teacher emails ask for a CALL first; a flyer-and-nominate path exists as the opt-out fallback. | Workflows 1855579944, 1865133871; emails 217749173540 / 219216438280 |
| Program results so far: 13 teacher deals (11 at "Opted Out of Call OR Met at Event – Sent Flyer", 2 nominated); 10 family deals (3 Ready to Schedule Trial, 3 Unresponsive Family, 1 Closed Won, 1 Closed Lost, 1 Scheduling, 1 Nominated). | Pipelines 917641511 / 918901819 |
| Family pilot (Aug 18-20): 46 sent / 18 opened (39%) / 2 replied. Lead-status exit goal silently skipped 34 families; reply-date exit works. | CHANGELOG 2026-08-20 |
| School is now a real field on every teacher (`[Agent] School`), iLEAD one bucket. IEM: 274 mailable, school unknown for 272. | PR #160 |

## Seats

**Sales seat.** The split is right. "The funding is already there" is the message, and a teacher who moved $20K of POs through us last year already knows it; pitching her a free scholarship reads as if we forgot who she is. For the worked-with-us group the ask is one sentence: which of your funded kids should we pick back up this week. I would take the top 30 personally, they are half of all charter dollars. For cold teachers the scholarship is the right first ask because it costs them no budget and no PO.

**charter_sales seat.** Every scholarship nomination becomes a consultation on my calendar and a Teacher Scholarship family deal, not a charter deal. Of the 10 family deals so far, 3 went unresponsive before a single lesson. If 300 IEM teachers each nominate two kids, the program's reputation with those teachers is set by how fast I call, and I cannot call 600 families in a week. Cap the cold wave or stage it by school.

**Ops / PO desk.** The worked-with-us ask creates charter deals through the PO flow we already run; nothing new breaks. The scholarship path creates deals in a separate pipeline with its own stages, so nothing there hits po_inbox or deal sync. The risk is the handoff at "Ready to Schedule Trial" to a real PO later; that conversion step is not automated and today has 3 deals waiting in it.

**Finance / data.** This is an account list, not a campaign. 151 teachers produced 89% of charter dollars; 30 of them produced half. Effort goes there first and gets measured in deals created, not opens. On the cold side we have one data point: 365 opens and no logged replies. There is no evidence yet that cold teachers act on email. Treat the cold wave as an experiment with a cap, not a launch.

**Risk / brand.** The scholarship is A+-funded free tutoring. A cold blast to 800 teachers is a real cost commitment if it works; decide the cap before the send. And we cannot measure the last send: replies to info@ never reached the contact record. Sending again without fixing that means another three weeks of guessing.

**The teacher's chair.** If I have funded students, I do not need convincing, I need the PO paperwork off my desk. Open with my roster, not with you. If I have never used you, a free nomination that takes two minutes and no budget is something I can do on a Tuesday. A call is not. September is the worst month to ask a teacher to book a call.

**Devil's advocate.** Why email 300 IEM teachers whose school we cannot even name, when IEM has a central office that handles POs? One conversation with the network beats 300 emails. Keep the teacher email for schools where the teacher is the PO gatekeeper (iLEAD, Compass, Sage Oak, Elite, Blue Ridge, Excel) and make IEM a partnership call.

## Convergence

**Verdict.** The thesis holds with one correction and one addition. Correction: the scholarship must be sent as a two-minute nomination (flyer + form) with the call as the follow-up, because its own pipeline shows teachers opting out of the call 11 to 2. Addition: the cold list is not one list; IEM is a network conversation, not an email wave.

| Segment | Teachers | The ask | Channel |
|---|---|---|---|
| A1. Worked with us, top 30 by $ | 30 | "Your roster from last year, who's coming back?" | Sales seat personal email + call. No sequence. |
| A2. Worked with us, rest | 121 | Same ask, reply or form. | 2 emails, Day 0 and Day 5. Reply exits. |
| B. Cold, teacher-gated schools (iLEAD, Compass, Sage Oak, Elite, Blue Ridge, Excel, …) | ~430 | Scholarship nomination, no call. Flyer + 2-minute form. Cap 2 nominations per teacher. | 3 emails, staged by school. |
| C. IEM network | ~300 | Not a teacher email. Sales seat to IEM central office first. | Hold. |
| D. Long tail (<10 teachers per school) | ~100 | Same as B, last wave. | After B results. |

**Fixes before go.**
1. Reply tracking: the info@ classifier's `campaign_school` category stamps a `[Agent] Campaign Replied` flag on the teacher, so replies count.
2. Scholarship front door: nomination form and flyer become Email 1; the call becomes the follow-up for teachers who nominate.
3. Exit rules from the family pilot: reply exits, new charter deal naming the teacher exits, no lead-status goals.

**Go line.** "Go" builds A1/A2/B lists, drafts as DRAFT for sales-seat sign-off, workflows OFF, and the two fixes. "A only" builds just the 151 worked-with-us teachers first.

Decisions locked here still need an A+ Decision Log entry (#AP### format).

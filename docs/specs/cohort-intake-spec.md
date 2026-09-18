# `cohort_intake` — HSA Cohort Onboarding Agent

**Spec v1 · 2026-09-15 · Owner: Roman · Source of truth once merged: aplustutoring/aplus-agents**
Status legend: **LOCKED** = decided by Roman/Danielle in this session or an existing fleet rule. **DRAFT** = my proposal, change freely.

---

## 1. Purpose

Turn a confirmed group on the IEM `HSA 26/27 Intervention` sheet (`APlusRegistrationList` tab) into HubSpot contacts + deals, Teachworks students, welcome emails, and a scheduler handoff — in one run, with no human drafting step.

## 2. Program facts (LOCKED — from Danielle's blueprint + Roman↔Angie June 11 thread)

| Cohort | Reg. deadline | Start | Sessions (= hrs/student) | Group total @ $150 |
|---|---|---|---|---|
| 1 | 9/14/26 | 9/21/26 | 25 | $3,750 |
| 2 | 10/12/26 | 10/19/26 | 21 | $3,150 |
| 3 | 11/2/26 | 11/9/26 | 18 | $2,700 |
| 4 | 1/11/27 | 1/25/27 | 13 | $1,950 |
| 5 | 2/1/27 | 2/8/27 | 11 | $1,650 |
| 6 | 3/8/27 | 3/15/27 | 7 | $1,050 |

- All cohorts end **5/14/27**. Session = 1 hr, once weekly.
- Slots: **Mon 10:00 AM, Wed 11:00 AM, Wed 3:00 PM** (PT).
- No-class weeks: Nov 23–27; Nov 30–Dec 4; Dec 19–Jan 17; Mar 8; Mar 29; Apr 26.
- Pricing: **$150 flat per group session**, regardless of size. Late-added group prorates at $150 × remaining sessions. Invoiced upfront per cohort to Angie Covil (acovil@ieminc.org).
- **Max group size 4** (NSSA HIT cap; target 3). Agent hard-stops on 5+.
- Cohort number derives from the **start date** in the sheet's Group/Start Date column ("1, 9/21/26") matched to the table above — never from the group number. The Intake tab's "Cohort Number" column is the GROUP number within the cohort (renamed Group #); it drives scheduler ownership, not cohort math.
- School contacts: Jamie Hetrick (jhetrick@ieminc.org, HSA Principal, rosters), Monica Presby (mpresby@ieminc.org, admin/readiness), Angie Covil (POs/funding).

## 3. Source of record (LOCKED, Roman 9/15)

A+-owned Google Sheet **"HSA 26/27 Intake (A+)"**, id `1zM7INlOeRhYEWG_lWNHEgR8cK4ANCweQJ5Iwgrh1fe4` (created by Danielle 9/15; ownership transfer to Roman requested; agent service account to be added). IEM source sheet id `1SoJ34Lnplz3HIGRwmC71U-ZTaR5lmffDf78jasmYZ5E`. IEM's "HSA 26/27 Intervention" sheet stays IEM's; the agent **never reads or writes it directly**.

| Tab | Written by | Contents |
|---|---|---|
| `Roster` | IMPORTRANGE from IEM `APlusRegistrationList` | read-only mirror, stays current without hand copying |
| `Intake` | Danielle (input cols) / agent (output cols) | one row per student. Actual headers (verified 9/15): Student ID · Student First Name · Student Last Name · Grade · School · Student Email (Not IEM email) · Parent Name · Parent Email · Contact Phone Number · ES Name · ES Email · Tutoring Subject · Notes · Day/Time · Cohort #/Start Date (e.g. "1, 9/21/26") · Group # · Status. Agent-written: HubSpot Deal ID, Teachworks ID, Cohort, Sessions, Text Sent, Welcome Sent, ES Email Sent, Tutor, Last Updated |
| `Log` | agent | one line per run: what it did, what it refused and why |

The Intake row is the compliance record: what was sent, to whom, when. Agent-written columns are never edited by hand; a human correction goes in the input columns and the agent re-runs.

## 4. Trigger and validation

- `workflow_dispatch` `{group_label}` or Slack `/cohort <group label>` (Danielle or Roman). The agent processes only Intake rows with `A+ Status = Ready` ("ready to be set up on the A+ side", Danielle 9/15).
- Hard-stop if any of Parent Email, Parent Phone, ES Email, Subject, Grade, Start Date, School, Group # is blank or unparseable. Student email equal to parent email → treat as no student email, no flag (Danielle 9/15: student has no non-IEM address). Unknown school spelling: report and add to `school-aliases.yml` (OG = Ocean Grove, SM = Sky Mountain, SS = South Sutter), never guess.
- Group size > 4: refuse, ask Danielle to split.

## 5. Run sequence

1. **Parse + validate** the group's rows. Compute cohort #, sessions, group total, per-student amount. Enforce cap 4.
2. **Dry-run summary** DM to Roman + Danielle: table of students, cohort, amounts, contacts to create/update, emails to send. **Auto-continue after 15 min unless someone replies `stop`** (DRAFT — set to 0 min once trusted).
3. **Contacts** — every property below is written on create, fill-only on existing records (never overwrite a human value). Internal names are from KEEPERS.md (#AP035/36).

   **Family contact** (upsert by Parent Email)
   | Property | Value |
   |---|---|
   | `firstname` / `lastname` | parent name split; if no last name on the sheet (e.g. "Reyna"), lastname = student last name and the row is flagged |
   | `email` / `phone` | parent email; phone normalized to E.164 |
   | `a_persona` | Family |
   | `lifecyclestage` | Customer |
   | `hubspot_owner_id` | derived from the deal owner (group parity rule) |
   | `charter_school_family_` | Yes |
   | `parent_first_name` / `parent_last_name` / `parent_email` / `parent_phone_number` | same as above (legacy capture fields, still live) |
   | `student_last_name` (label "Student FIRST Name") | student first name |
   | `student_last_name_if_diff_from_parent` | student last name |
   | `student_email_address` | student email if present and ≠ parent email |
   | `what_is_your_child_s_current_grade_level_` | grade (canonical grade prop) |
   | `student_school` | canonical school (Ocean Grove / Sky Mountain / South Sutter) |
   | `subject_need` | subject |
   | `teacher_of_record_name` / `teacher_of_record_email_address` | ES |
   | Association | Family → TOR (typeId 15) |

   **TOR contact** (upsert by ES Email; one per ES)
   | Property | Value |
   |---|---|
   | `firstname` / `lastname` / `email` | ES |
   | `a_persona` | TOR |
   | `hubspot_owner_id` | Danielle 227538487 |
   | `educational_facillitator_teacher_of_record` | Yes |
   | `charter_school_teacher` | school (master list value) |
   | `school_canonical` | canonical school |

   Jamie / Monica / Angie already exist as school staff; not touched per run.

4. **Deals** — one per student, pipeline **IEM Inc. (5119061)**, stage Pre-Lesson.
   | Property | Value |
   |---|---|
   | `dealname` | `{Parent} - {Student} - {School} - IEM HSA {Subject}` |
   | `amount` | group total ÷ students (remainder cents on first deal) |
   | `closedate` | cohort start date |
   | `hubspot_owner_id` | by **group number within the cohort**: odd group → Janelle 80047202, even group → Yolanda 86868539 (LOCKED Roman 9/15; Danielle's Group # column is the source) |
   | `online__inperson__charter` | Charter |
   | `iem_student_id` | sheet Student ID |
   | `student_first_name` / `student_last_name_if_diff_from_parent` / `student_grade` / `student_school` | from sheet |
   | `parent_email` / `parent_phone` | from sheet |
   | `teacher_of_record_name` / `teacher_of_record_email` / `tor_first_name` / `tor_last_name` | ES |
   | `number_of_hours_in_this_po` | cohort sessions (25 for C1) |
   | `start_of_tutoring_for_this_deal` / `date_of_last_lesson_in_this_deal` | first / last session date from the generated calendar |
   | `lessons_fulfilled_date` | last session date |
   | `schedule_preferences` | "{slot} PT weekly from {start}" (drives the SMS confirm variant) |
   | `monday_schedule_preference` or `wednesday_schedule_preference` | slot time |
   | `[Agent] HSA Cohort` / `HSA Group` / `HSA Sessions` / `HSA Start` / `HSA Slot` | new props (see §7) |
   | `description` | template below |
   | Associations | Family contact + TOR contact |

   **Deal description** (LOCKED structure; mirrors 25/26 IEM deals):
   ```
   IEM High School Academy {Subject} Intervention, Cohort {n} (Group {g})
   Student: {First Last}, grade {grade}, {School} (IEM ID {id})
   Parent: {name}, {email}, {phone}
   ES: {name}, {email}
   Schedule: {slot} PT, weekly, {start} through {end}. {sessions} one-hour group sessions.
   Group: {other students in the group}
   Session calendar: {dated list}
   No class: {no-class weeks}
   Notes from school: {Notes column, e.g. "4th grade on i-Ready"}
   Billing: flat $150 per group session, invoiced upfront to IEM (Angie Covil). This deal = ${amount} ({sessions} x $150 / {n} students). Hours tracked per student in Teachworks at $0/hr.
   Reports: session notes to parent + ES after every lesson; Friday attendance report to Jamie Hetrick, Monica Presby, Angie Covil.
   Schedule is fixed by IEM; change requests go to the ES, not A+.
   ```

5. **Teachworks** (via existing `deal_sync`, LOCKED outcome)
   - One student per deal, service at **$0/hr**, allocation = cohort sessions. Attendance + lesson notes per student.
   - TOR added as **additional contact** on each student so she receives session notes. *(API support: spike — if Teachworks can't do it via API, agent creates a HubSpot task for the deal owner.)*
   - One **flat invoice per group** = group total, to IEM, sent upfront. `[Agent] HSA Group` is the grouping key. Invoice sweep must ignore the $0 tracking invoices.
6. **First touch** (LOCKED principle: auto-send the moment deals are written, no drafts, and **nothing new is built that an existing rail already does**)

   The three sends and where each one lives:

   | Touch | Rail (verified in repo 9/15) | Change needed |
   |---|---|---|
   | **Family text** | `email/src/sms.py` sweep, runs from `deal_sync` every ~15 min. Qualifier = deal in a pipeline listed under `sms.pipelines` + stage label contains "pre-lesson" + `createdate` ≥ `sms.start_date` (9/3). **Not keyed on a PO** — cohort deals qualify by config alone. Grouped per family; picks `{template}_confirm` if `schedule_preferences` holds a real schedule, else `{template}_ask`. Guardrails as documented. Presend purpose `po_welcome`. | (1) `email/config.yaml`: `"5119061": { template: hsa, welcome: true, welcome_template: "templates/welcome_hsa.html", welcome_subject: … }`. (2) **LOCKED (Roman 9/15):** cohort families are told their slot by IEM and cannot deviate — no cohort text or email may ask for, or offer to change, the schedule. Copy keys `hsa_confirm` / `hsa_multi_confirm` (§8); `hsa_ask` variants point at the same copy. A parent who replies asking to change time is routed to the ES/Jamie, not rescheduled by A+. (3) Intake agent writes `schedule_preferences` = "{slot} PT weekly from {start}" on every cohort deal so the confirm variant always fires. (4) Family contact must be associated before the sweep sees the deal — same run, so satisfied. |
   | **Family email** | `_send_welcome()` in sms.py, fires on the same event. Resend, from A+ Tutoring Success Team <admin@wetutorathome.com>, reply-to admin@, HubSpot BCC stamp. **Template is hardcoded HTML; only `__FIRST_NAME__` is substituted** — no program/slot/start fields exist today. Per-pipeline `welcome_template` + `welcome_subject` already supported (gold, trial use it). | New `email/templates/welcome_hsa.html`. Either (a) keep it generic (program described, no dates — the text carries slot/start) with zero code change, or (b) extend `_send_welcome` to substitute `__STUDENT__ __SLOT__ __START__ __ES__ __NO_CLASS__` from the deal's HSA props (small change, gives the full what-to-expect). **DRAFT recommendation: (b).** |
   | **ES group email** | `ops/messenger/one_to_few` rail, presend gate uses the caller's purpose. The only new send. | Purpose `cohort_welcome`; one email per ES per group, sent by the intake agent after deals are written. |

   Failure paths found in the rail (answers part of Q7): missing family phone or no family contact → audit row `sms_skipped_unverified`, **no human is pinged**; only a 3× send failure DMs `charter_admin`. The intake validator already hard-stops on blank parent phone/email, so cohort rows can't reach that silent path — but a phone that later bounces will. DRAFT: intake agent reads the audit log after the next sweep and DMs the deal owner on any `sms_skipped` for its deals.

   Sequence: deals written → SMS rail picks them up on its next sweep (≤15 min) → welcome email rides the text → ES group email in the same agent run. Sibling deals for one family (two kids, two groups) → one text, one email, per the rail's per-family/24h rule.

   **Gate before cohort 1:** the rail's open 9/4 incident (Sanchez/Delgado 64648100449 — no BCC stamp, no SMS record) must be closed with a system change or a written no-fix before cohort deals are fed to it. Otherwise families get nothing and nobody knows.

   Tutor intro + day-before reminder: **assumed** scheduling's, sent by the scheduler after tutor confirmation — not this agent. Roman's seven first-touch questions (timing, sender, one text vs two, family checklist, ES checklist, existing copy, failure paths) are still open; §8 copy is a DRAFT written against the rail's copy rules until answered.
7. **Scheduler handoff** (LOCKED definition)
   - Slack DM to the owning scheduler: roster table (students, grade, school, parent phone, ES, slot, cohort, deal links), **the no-class dates listed explicitly as skip dates**, session count, and "confirm tutor for {slot}; book {sessions} sessions from {start} skipping the listed dates."
   - **LOCKED (Roman 9/15): no session may be booked on a no-class date.** Teachworks lesson series for cohort students are created with the no-class dates excluded; the agent verifies after creation that the scheduled lesson count equals the cohort's session count and that no lesson falls on an excluded date, and flags the scheduler + Danielle if either check fails. The tutor's intro/handoff carries the same skip list.
   - Summary post to Danielle + Roman. Audit entry in `audit_log.jsonl`.

## 6. Guards (LOCKED unless marked)

- Idempotency key `school + student_id + subject + term`; re-runs update, never duplicate.
- Agent-written props are never overwritten by portal automation (#AP049).
- Late add to an existing group: re-split existing deals' amounts, log the change on each deal, new student gets remaining-session allocation (DRAFT rule).
- Student pulled: Danielle/scheduler marks deal Stop; Teachworks allocation prorated by hand for now (DRAFT — automate later).
- Weekly attendance report (Kath, Fri 3 PM): previous week only, per participant. **LOCKED (Roman 9/15): goes to the IEM admin team only, not to ESs.** ESs get per-session notes only. Recipients (Danielle 9/15): Jamie, Monica, Angie.
- Never writes on unconfirmed rows; never emails a contact missing from the sheet.

## 7. Fleet changes required

| File | Change |
|---|---|
| `email/src/owner_assign.py` | pipeline 5119061 → group-number parity within cohort (odd Janelle / even Yolanda) |
| `email/src/student_stamp.py` | accept agent-supplied student fields (already fill-only — verify) |
| `deal_sync` | $0/hr service + allocation from `[Agent] HSA Sessions`; TOR additional contact; group flat invoice; lesson series with no-class dates excluded + count/date verification |
| `ops/hubspot-schema/properties.yml` | 5 new `[Agent] HSA *` deal props (IEM student id uses existing `iem_student_id`) |
| `school-aliases.yml` | OG / SM / SS |
| `email/config.yaml` | `sms.pipelines["5119061"]` block; `hsa_*` text copy keys |
| `email/src/sms.py` | `_send_welcome` field substitution from deal HSA props (if option b) |
| `email/templates/welcome_hsa.html` | new cohort what-to-expect email |
| `knowledge/journey/` | stage 01 charter-cohort first touch (DRAFT, PR #198 branch) |
| `registry.yml` | new agent `cohort_intake`, engine ops, trigger dispatch+Slack |
| Presend gate | `cohort_welcome` template class for the ES group email only |

Retired today: Zapier 287422699 (IEM SMS) and 348893421 (PRE LESSON → Teachworks) — off.

## 8. First-touch copy (DRAFT — written to the SMS rail's copy rules: name the kid, "their" never a gendered guess, brand voice, no personal sign-off; for Danielle's one-time approval)

**Family text** — config keys `hsa_confirm` / `hsa_multi_confirm` (no em dashes, per locked outbound rule)

> hsa_confirm: Hi {first_name}, it's A+ Tutoring! {student} is set for IEM's HSA tutoring group: {schedule}. Their tutor and session link come by email before the first session. Reply here with any questions.
>
> hsa_multi_confirm: Hi {first_name}, it's A+ Tutoring! {students} are set for IEM's HSA tutoring groups. Schedules and tutor intros come by email before the first session. Reply here with any questions.

**Family email** — `templates/welcome_hsa.html` (LOCKED content points, Roman 9/15; wording DRAFT)

> **{Student}'s tutoring starts {start}: {Subject}, {slot}**
>
> Welcome to A+ Tutoring. {Student} is enrolled in IEM's High School Academy {Subject} tutoring group (Cohort {n}), starting **{start}** and meeting every **{slot}** through May 14, 2027. One hour, online, same tutor all year. The day and time are set by IEM for the whole group.
>
> **Coming shortly in a separate email:** {Student}'s tutor profile, so you know who they'll be working with.
>
> **The lesson link.** {Student} uses one join link for every session, all year. It comes to your email with the tutor profile; reminders before each session repeat it. **If {Student} uses a school computer or a school email address, school domains block our emails, so the link will not reach them directly.** Forward it once to {ES name}, {Student}'s ES, who can pass it to {Student} inside the school system, and have {Student} save it.
>
> **After every session** you'll get lesson notes: what was covered and what to practice. {ES name} receives them too.
>
> **Session calendar** (all {sessions} dates): {dated session list generated by the agent}. No sessions during {no-class weeks}.
>
> There is nothing to pay; IEM covers this program.
>
> Questions: reply here, or text or call 818-869-1627.
>
> A+ Tutoring Success Team

**ES group email** (new; one per ES per group)

> **Your HSA {Subject} group starts {start} — A+ Tutoring**
>
> Hi {ES first name},
>
> Your {Subject} group (Cohort {n}) starts **{start}**, **{slot}**, weekly through May 14, 2027. Students: {student list with grade/school}.
>
> The day and time are fixed for the group; families have been told they cannot be changed, and any request to change comes to you, not us.
>
> **Lesson links:** each student has one join link for the whole year, sent to the parent. Students on school devices or school email cannot receive our emails (domain restriction), so parents will forward the link to you once to pass along inside the school system. Reply if you'd like the links sent to you directly as well.
>
> You'll get session notes after every lesson for each student. Tutor introduction follows once confirmed. Weekly attendance reports go to the IEM admin team.
>
> **Session calendar** (all {sessions} dates): {same dated list}.
>
> Roster changes go through Jamie/Monica on the sheet; anything else, reply here or 818-869-1627.
>
> — A+ Tutoring Success Team

## 9. Launch plan (Roman 9/15) and open items

Roman's calls 9/15: invoice timing is his, not the agent's; tutor assignment is routine; the one steady link and the tutor intro both come from the scheduler's lesson-creation email in Teachworks; schedulers know the fixed-schedule rule the moment the deal is created; no makeups and no proration, not mentioned to families; Kath builds attendance reports Sundays; Angie's later program lands on the same sheet.

Test row: Intake row 9, `TEST-001`, parent Roman Test / roman@wetutorathome.com / 818-384-4845, ES Danielle, Group 4, English 9, Mon 10:00, Status Ready. Build must support `--only-row TEST-001`. Flow: dry-run → execute → Roman reviews text, welcome email, ES email, deal on his phone → corrections → delete test deal/contact/Teachworks entry, set row Status = `Test - done` → **9:00 AM 9/16 execute on the 7 Ready rows**.


1. Danielle's edits (9/15, applied): "than they did in August"; homeschool students, so the goal line is "It's for Diego to finish the year stronger in English than they started it"; contact line "reply here or text/call the 818 for anything". Copy otherwise approved.
1a. Roman answers the seven first-touch questions; §8 and §5.6 are DRAFT until then.
1b. Close the SMS rail's 9/4 Sanchez/Delgado incident before cohort 1 is fed to it.
1c. **Danielle to confirm two calendar questions before any Wednesday cohort or the first email:** RESOLVED by Danielle 9/15: fall = Sep 21 to Dec 18, no class Thanksgiving week + week of Nov 30; spring = Jan 18 to May 14, no class the WEEKS of Mar 8, Mar 29, Apr 26 (Wednesday groups skip Mar 10, Mar 31, Apr 28 and also get 25). Jan 18 is the spring start, so MLK is a session day; Presidents' Day too.
LOCKED: the agent generates one dated session list per group from the cohort table + no-class dates; that list is the Teachworks booking list, the family email calendar, the ES email calendar, and the scheduler handoff. One source.
Assumptions in force: tutor intro + reminder are scheduling's, not this agent's; sender numbers/addresses are the rail defaults; one text per family regardless of number of kids in the cohort.
2. Teachworks API spike: additional contact + $0 service (build task).
3. Sheet template: add `A+ Status`, `Registration Date`, `Slot`, `Group label` columns if missing — Danielle confirms with Jamie.
4. Decision-log entries: group-parity ownership within cohort; per-student deal + group invoice model; max group 4; zaps retired.

## 10. Claude Code build prompt

```
Build agent `cohort_intake` in ~/code/aplus-agents per docs/specs/cohort-intake-spec.md (this file).
Source of record is the A+-owned sheet "HSA 26/27 Intake (A+)" (id via env HSA_INTAKE_SHEET_ID), tabs Roster/Intake/Log per §3.
Read Intake rows with A+ Status=Ready; write agent columns back on the same row; append to Log every run. Never touch IEM's sheet.
Read first: registry.yml, email/src/deal_sync*, email/src/owner_assign.py, email/src/student_stamp.py,
ops/hubspot-schema/properties.yml, school-aliases.yml, knowledge/journey/README.md, presend gate module.
Deliver as ONE PR:
1. agents/cohort_intake/ — parser (Google Sheets API, tab Intake of the A+ sheet), validator (hard-stops in §4, cap 4),
   cohort resolver (table §2), HubSpot writer (contacts, per-student deals, associations, props §5.4), email sender via
   one_to_few rail with template class `cohort_welcome`, scheduler DM, audit log. Idempotent on school+student_id+subject+term.
   Dry-run mode default; --execute flag; 15-min stop window via Slack.
2. owner_assign.py: pipeline 5119061 → odd GROUP number Janelle 80047202 / even GROUP number Yolanda 86868539, group number from the sheet's Group # column (numbering restarts each cohort).
3. deal_sync: when deal has [Agent] HSA Sessions → Teachworks service at $0/hr with that allocation, TOR as additional
   contact (spike API; fallback = HubSpot task on deal owner), flat group invoice = sum of sibling deal amounts keyed on
   [Agent] HSA Group, sent upfront. Invoice sweep ignores $0 invoices.
4. properties.yml: [Agent] HSA Cohort, HSA Group, HSA Sessions, HSA Start, HSA Slot (deal). Every other property in spec §5.3/5.4 already exists in KEEPERS.md; write all of them.
   Run schema sync dry-run, include diff in PR.
5. school-aliases.yml: OG/SM/SS.
6. registry.yml entry + workflow .github/workflows/cohort-intake.yml (workflow_dispatch inputs sheet_id, group_label).
7. Tests: parser/validator/cohort/split fixtures from the blueprint's Group 1 English 9 example (3 students, C1, $1,250 each).
   Late-add re-split test. Cap-5 refusal test. Presend gate test for cohort_welcome. No-class-date test: a C1 series from
   9/21 yields exactly 25 lessons, none on Nov 23-Dec 4, Dec 19-Jan 17, Mar 8, Mar 29, Apr 26. Em-dash scrub applies to
   email subjects on the ES send, not only SMS bodies.
Rules: agent-written props never overwritten by portal automation; never write on rows without A+ Status=Ready; every
failure class ends with a system change or a written "no fix because X". /health per #AP048 if any Worker is added (none expected).
8. First touch reuses existing rails — DO NOT add a send path: (a) email/config.yaml: sms.pipelines["5119061"] =
   {template: hsa, welcome: true, welcome_template: templates/welcome_hsa.html, welcome_subject: ...} plus hsa_confirm /
   hsa_multi_confirm / hsa_ask / hsa_multi_ask keys (ask = same copy as confirm); intake writes schedule_preferences on every
   cohort deal; (b) new templates/welcome_hsa.html and extend _send_welcome to substitute __STUDENT__ __SLOT__ __START__
   __ES__ __NO_CLASS__ from the deal's [Agent] HSA props (pass the deal props through; keep __FIRST_NAME__ behavior for
   all other pipelines); (c) ES group email via ops/messenger/one_to_few with presend purpose cohort_welcome; (d) after
   the next sms sweep, intake reads audit_log for sms_skipped rows on its deal ids and DMs the deal owner. Copy for all three is in spec §8 and lands via PR. Add a test that a cohort deal produces exactly
   one text + one welcome per family and one ES email per group.
```

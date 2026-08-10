# KEEPERS — the property vocabulary agents use

**86 properties.** This is the distilled keeper set the persona architecture (#AP024) was built to enable: if an agent reads or writes a contact/deal property, it should be one of these (plus HubSpot system fields like email/firstname/lastname/phone/hs_lead_status, which are out of scope here). Everything else in the portal is KEEP-IN-PLACE (forms/programs/integrations), STORAGE-ONLY, or a RETIRE-CANDIDATE — see the two proposal docs.

Rules that travel with this list:
- Agents ALWAYS read enumeration **labels**, never internal values (fleet rule; see mismatch list in contacts-proposal.md).
- Family→TOR truth is the typeId-15 contact association; the stamped TOR text fields are legacy capture but still LIVE (#AP031, #AP029).
- Multi-select `a_persona` is read FIRST by every agent (#AP024, #AP030).
- **Student grade level: agents use `what_is_your_child_s_current_grade_level_` — always** (Roman 2026-08-10). The other grade fields below are program/form capture, never the agent read/write target.

## Master

| Internal name | Label | Why | Decision |
|---|---|---|---|
| `a_persona` | A+ PERSONA | 5-persona switch, multi-select — read first, always | #AP024/#AP030 |

## Family (25)

| Internal name | Label | Why | Decision |
|---|---|---|---|
| `charter_school_family_` | Charter School Family? | Gates the TOR ask on intake; read by tor_family scripts | #AP029 |
| `friday_schedule_preference` | Friday Schedule Preference | Per-day schedule preference (family keeper set) | #AP029 |
| `how_did_you_hear_about_us_` | How Did You Hear About Us? | Attribution; call agent fill_only write | #AP029 |
| `monday_schedule_preference` | Monday Schedule Preference | Per-day schedule preference (family keeper set) | #AP029 |
| `online_or_in_person` | Online or In Person Preference | Delivery preference; call agent overwrite | #AP029 |
| `parent_concerns_what_can_we_do_to_help_` | What's going on? | DONE — moved by Roman 2026-08-10. Label "What's going on?" — intake-agent enriched (call agent log-append) | #AP029 |
| `parent_email` | Parent Email | Parent identity | #AP029 |
| `parent_first_name` | Parent First Name | Parent identity | #AP029 |
| `parent_last_name` | Parent Last Name | Parent identity | #AP029 |
| `parent_phone_number` | Parent Phone Number | Parent identity | #AP029 |
| `referral_name` | Referral Name | Referral attribution; call agent fill_only write | #AP029 |
| `saturday_schedule_preference` | Saturday Schedule Preference | Per-day schedule preference (family keeper set) | #AP029 |
| `student_3_full_name` | Student 3 Full Name | Teachworks family disambiguation (email/config.yaml) |  |
| `student_4_full_name` | Student 4 Full Name | Teachworks family disambiguation (email/config.yaml) |  |
| `student_additional_information` | What we can do to help | DONE — moved by Roman 2026-08-10 (out of CAP form_fields). Label "What we can do to help" — intake-agent enriched | #AP029 |
| `student_full_name_clone_` | Student 2 Full Name | Label "Student 2 Full Name" — Teachworks family disambiguation (email/config.yaml) |  |
| `student_school` | Student School | DONE — moved by Roman 2026-08-10 (out of CAP form_fields). Student school on intake; call agent overwrite; po_inbox deal map source | #AP029 |
| `subject_need` | Subject Need | Subject asked on intake; call agent overwrite | #AP029 |
| `sunday_schedule_preference` | Sunday Schedule Preference | Per-day schedule preference (family keeper set) | #AP029 |
| `teacher_of_record_email_address` | Teacher of Record Email Address | TOR auto-create trigger; read/written by tor_family scripts | #AP029 |
| `teacher_of_record_name` | Teacher of Record Name | Family's pointer to their teacher — legacy intake capture, superseded by typeId-15 association but still LIVE and load-bearing (auto-create trigger) | #AP029 |
| `thursday_schedule_preference` | Thursday Schedule Preference | Per-day schedule preference (family keeper set) | #AP029 |
| `tuesday_schedule_preference` | Tuesday Schedule Preference | Per-day schedule preference (family keeper set) | #AP029 |
| `wednesday_schedule_preference` | Wednesday Schedule Preference | Per-day schedule preference (family keeper set) | #AP029 |
| `what_is_your_child_s_current_grade_level_` | What grade is your child in? | CANONICAL student grade — the property agents use for grade level, always (Roman 2026-08-10); call agent overwrite target | #AP027 |

## Teacher of Record/EF/ES (4)

| Internal name | Label | Why | Decision |
|---|---|---|---|
| `charter_school_teacher` | Charter School Teacher | School dropdown = master school list; shows when TOR flag = Yes | #AP028 |
| `educational_facillitator_teacher_of_record` | Educational Facillitator/Teacher of Record | Yes/No TOR flag; conditional display drives school dropdown | #AP028 |
| `last_tor_workflow_enrollment_date` | Last TOR Workflow Enrollment Date | TOR nurture-workflow bookkeeping; belongs with TOR persona |  |
| `teacher_email_address` | Teacher Email Address | Danielle's live marketing-form field (15 fills) — not a duplicate | #AP028 |

*(conditional display: `charter_school_teacher` shows when `educational_facillitator_teacher_of_record` = Yes — #AP028)*

## Tutors (9)

| Internal name | Label | Why | Decision |
|---|---|---|---|
| `a__pay_per_hour` | A+ Pay Per Hour | Tutor pay rate — core tutor record | #AP024 |
| `completed_tutor_training` | Completed Tutor Training | Onboarding status (active 2026) | #AP024 |
| `degree_received` | Degree Received | Tutor credential | #AP024 |
| `online_in_person_` | Online or In-Person | Tutor delivery mode | #AP024 |
| `resume` | Resume | Tutor resume file (recruiting form) | #AP024 |
| `select_days_for_availability` | Select Days for Availability | Tutor availability | #AP024 |
| `tutor_profile` | Tutor Profile | Tutor bio used for matching/intro | #AP024 |
| `university_attended` | University Attended | Tutor credential | #AP024 |
| `what_subjects_do_you_feel_the_most_qualified_to_tutor_` | What subjects do you feel the most qualified to tutor? | Tutor subjects (structured checkbox) | #AP024 |

## Student (3)

| Internal name | Label | Why | Decision |
|---|---|---|---|
| `student_email_address` | Student Email Address | Student contact point (distinct from parent email) | #AP024 |
| `student_last_name` | Student FIRST Name | DONE — moved by Roman 2026-08-10. LABEL MISMATCH: label is "Student FIRST Name" — student 1 first name; Teachworks disambiguation + call agent fill_only | #AP029 |
| `student_last_name_if_diff_from_parent` | Student Last Name | DONE — moved by Roman 2026-08-10 (out of CAP form_fields). Student last name; call agent fill_only | #AP029 |

## Grade fields (#AP027 verdicts) (5)

**Canonical: `what_is_your_child_s_current_grade_level_`** (in the Family table above) — the property agents read/write for student grade level, always (Roman 2026-08-10). The fields below are program/form capture only:

| Internal name | Label | Why | Decision |
|---|---|---|---|
| `grade_level` | Grade Level | Danielle's scholarship forms — live, not a duplicate | #AP027 |
| `spotlight_grade_level` | Spotlight Grade Level | Spotlight program (live) — programs stay grouped as programs |  |
| `teacher_scholarship_nomination__student_1__student_grade_level` | Teacher Scholarship Nomination - Student 1 - Student Grade Level | Teacher Scholarship Nomination program (live) — stays grouped as program; grade verdict: KEEP | #AP027 |
| `teacher_scholarship_nomination__student_2__student_grade_level` | Teacher Scholarship Nomination - Student 2 - Student Grade Level | Teacher Scholarship Nomination program (live) — stays grouped as program; grade verdict: KEEP | #AP027 |
| `teacher_scholarship_nomination__student_3__student_grade_level` | Teacher Scholarship Nomination - Student 3 - Student Grade Level | Teacher Scholarship Nomination program (live) — stays grouped as program; grade verdict: KEEP | #AP027 |

## Programs (KEEP-IN-PLACE, agents touch only these named fields)

- **Spotlight** (`spotlight_*`, 34 fields + `spotlight_parent_additional_comments`) — live; `spotlight_grade_level` is the Spotlight grade of record (Paola).
- **Teacher Scholarship Nomination** (`teacher_scholarship_nomination__*`, `nominating_teacher_name`, tracker fields) — live (Danielle); the 3 per-student grade levels above are the grade of record.
- **Pilibos** (`pilibos_*` on contacts and deals) — live.
- **CAP `form_fields`** — dead business, form-bound, DO NOT TOUCH; re-home candidates only (locked rule 6).

## Deals (38)

| Internal name | Label | Why | Decision |
|---|---|---|---|
| `a__slp_cap_invoice__` | A+/SLP/CAP Invoice # | Invoice # variant (charter/SLP/CAP) |  |
| `aplus_contractor_pay` | APlus Contractor Pay | Contractor pay (Monday sync) |  |
| `assigned_tutor` | Assigned Tutor | Tutor match on deal |  |
| `date_of_last_lesson_in_this_deal` | Date of Last Lesson in this Deal | Deal service window end |  |
| `friday_schedule_preference` | Friday Schedule Preference | Per-day schedule preference on deal |  |
| `iem_student_id` | IEM Student ID | IEM student id (charter ops) |  |
| `invoice__` | Invoice # | Invoice # (Kath 2-step invoice flow) |  |
| `invoice_submitted_date` | Invoice Submitted Date | STEP-2 close-loop stamp (invoice sweep reads) |  |
| `lessons_fulfilled_date` | Expected Lessons Fulfilled Date | Invoice due-date stamp (po_inbox invoice_task.invoice_due_property) |  |
| `monday_schedule_preference` | Monday Schedule Preference | Per-day schedule preference on deal |  |
| `number_of_hours_in_this_po` | Number of Hours in this PO | PO hours — invoice task + sweep |  |
| `online__inperson__charter` | ONLINE, INPERSON, CHARTER | Deal delivery segment |  |
| `parent_email` | Parent Email | po_inbox deal_property_map: parent_email |  |
| `parent_phone` | Parent Phone | po_inbox deal_property_map: parent_phone |  |
| `po_number` | PO Number | PO identity — po_inbox dedup + invoice sweep key |  |
| `reason_for_stopping` | Reason for Stopping | Churn reason |  |
| `saturday_schedule_preference` | Saturday Schedule Preference | Per-day schedule preference on deal |  |
| `schedule_preferences` | Schedule Preferences | Stamped on B2C deal create (email engine main.py) |  |
| `school_name` | School Name | School on deal |  |
| `should_this_deal_be_posted_to_a_slack_channel_` | Should this deal be posted to a Slack Channel? | Slack routing flag |  |
| `start_of_tutoring_for_this_deal` | Start Date for Tutoring for this Deal | Deal service window start |  |
| `stripe_amount_paid` | Stripe Amount Paid | Stripe payment truth (Pilibos flow) |  |
| `stripe_payment_intent` | Stripe Payment Intent | Stripe payment truth |  |
| `stripe_session_id` | Stripe Session ID | Stripe payment truth |  |
| `student_first_name` | Student First Name | po_inbox deal_property_map: student_first |  |
| `student_grade` | Student Grade | po_inbox deal_property_map: grade; also stamped on B2C deal create |  |
| `student_last_name_if_diff_from_parent` | Student Last Name | po_inbox deal_property_map: student_last |  |
| `student_school` | Student School | po_inbox deal_property_map: school |  |
| `sunday_schedule_preference` | Sunday Schedule Preference | Per-day schedule preference on deal |  |
| `teacher_of_record_email` | Teacher of Record Email | TOR on deal — Monday sync dependency; retire after Teachworks low-balance alert replaces Monday |  |
| `teacher_of_record_name` | Teacher of Record Name | TOR on deal — Monday sync dependency; retire after Teachworks low-balance alert replaces Monday |  |
| `thursday_schedule_preference` | Thursday Schedule Preference | Per-day schedule preference on deal |  |
| `tor_first_name` | tor first name | TOR on deal (Monday sync batch 2025-11); same retire-after-Monday flag |  |
| `tor_last_name` | tor last name | TOR on deal (Monday sync batch 2025-11); same retire-after-Monday flag |  |
| `tuesday_schedule_preference` | Tuesday Schedule Preference | Per-day schedule preference on deal |  |
| `tutor_email` | Tutor Email | Tutor match on deal (Monday sync) |  |
| `tutor_match` | Tutor Match | Tutor match on deal |  |
| `wednesday_schedule_preference` | Wednesday Schedule Preference | Per-day schedule preference on deal |  |

*(Monday-sync dependency: the four deal TOR fields retire after the Teachworks low-balance alert replaces Monday.)*


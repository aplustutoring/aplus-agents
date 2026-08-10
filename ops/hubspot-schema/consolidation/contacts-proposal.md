# HubSpot Contact Property Consolidation — Proposal

**Status: APPROVED by Roman 2026-08-10.** Persona group moves EXECUTED same day (`execute_group_moves.py`, 41/41 verified in place); keeper set declared in `properties.yml`. RETIRE-CANDIDATEs remain **pending** — each needs Roman's per-property "Used in" check before any (reversible) archive; nothing has been archived. STORAGE-ONLY and KEEP-IN-PLACE require no action.

884 total contact properties in portal 6312752; **405 are `hubspotDefined` (HubSpot system) and out of scope**. The 479 custom properties below are each assigned a disposition. Properties referenced by agent code are marked 【code: …】 and are keepers regardless of fill rate (locked rule 12).

Known label/internal mismatches (locked rule 9 — agents read LABELS, never internal values):
- `student_last_name` → label **"Student FIRST Name"** (holds student 1 first name)
- `what_is_your_child_s_current_grade_level_` → label **"What grade is your child in?"** (the canonical family grade ask)
- `what_grade_is_your_child_in` → label **"Student Grade - FB"** (lead-ad capture despite the friendlier internal name — superseded by the canonical grade property, Roman 2026-08-10)
- `parent_concerns_what_can_we_do_to_help_` → label **"What's going on?"**
- `student_additional_information` → label **"What we can do to help"**
- `assessment_received` → label "Assessment Graded - Remote"; `assessment_uploaded` → label "Assessment Received - Remote" (swapped-looking pair)
- `ready_to_start_date` → label "Get Started Form Only - Pods"; `date_of_first_session` → label "When does the school year start for your child?"
- `pod_pay_per_hour` → label "SLP Pay Per Hour"; `we_ve_waived_cancellation` → label "Are they aware of our cancellation policy"

## Summary

| Disposition | Count |
|---|---|
| Persona → family | 25 |
| Persona → tor | 4 |
| Persona → tutor | 9 |
| Persona → student | 3 |
| KEEP-IN-PLACE | 185 |
| STORAGE-ONLY | 119 |
| RETIRE-CANDIDATE | 99 |
| SYSTEM | 35 |
| **Total custom** | **479** |

## Moved → `family` group (Family) — EXECUTED 2026-08-10

Internal names unchanged (safe, #AP024). "Current group" shows the pre-move location for the audit trail.

| Internal name | Label | Current group | Rationale | Decision |
|---|---|---|---|---|
| `charter_school_family_` | Charter School Family? | charter | Gates the TOR ask on intake; read by tor_family scripts 【code: ops】 | #AP029 |
| `friday_schedule_preference` | Friday Schedule Preference | level-up_ilead | Per-day schedule preference (family keeper set) | #AP029 |
| `how_did_you_hear_about_us_` | How Did You Hear About Us? | contactinformation | Attribution; call agent fill_only write 【code: ops】 | #AP029 |
| `monday_schedule_preference` | Monday Schedule Preference | level-up_ilead | Per-day schedule preference (family keeper set) | #AP029 |
| `online_or_in_person` | Online or In Person Preference | a__custom_fields | Delivery preference; call agent overwrite 【code: ops】 | #AP029 |
| `parent_concerns_what_can_we_do_to_help_` | What's going on? | family | DONE — moved by Roman 2026-08-10. Label "What's going on?" — intake-agent enriched (call agent log-append) 【code: ops】 | #AP029 |
| `parent_email` | Parent Email | contactinformation | Parent identity | #AP029 |
| `parent_first_name` | Parent First Name | contactinformation | Parent identity | #AP029 |
| `parent_last_name` | Parent Last Name | contactinformation | Parent identity | #AP029 |
| `parent_phone_number` | Parent Phone Number | contactinformation | Parent identity | #AP029 |
| `referral_name` | Referral Name | referral_program | Referral attribution; call agent fill_only write 【code: ops】 | #AP029 |
| `saturday_schedule_preference` | Saturday Schedule Preference | level-up_ilead | Per-day schedule preference (family keeper set) | #AP029 |
| `student_3_full_name` | Student 3 Full Name | sibling | Teachworks family disambiguation (email/config.yaml) 【code: email】 |  |
| `student_4_full_name` | Student 4 Full Name | sibling | Teachworks family disambiguation (email/config.yaml) 【code: email】 |  |
| `student_additional_information` | What we can do to help | family | DONE — moved by Roman 2026-08-10 (out of CAP form_fields). Label "What we can do to help" — intake-agent enriched 【code: ops】 | #AP029 |
| `student_full_name_clone_` | Student 2 Full Name | sibling | Label "Student 2 Full Name" — Teachworks family disambiguation (email/config.yaml) 【code: email】 |  |
| `student_school` | Student School | family | DONE — moved by Roman 2026-08-10 (out of CAP form_fields). Student school on intake; call agent overwrite; po_inbox deal map source 【code: email, marketing, ops】 | #AP029 |
| `subject_need` | Subject Need | level-up_ilead | Subject asked on intake; call agent overwrite 【code: ops】 | #AP029 |
| `sunday_schedule_preference` | Sunday Schedule Preference | level-up_ilead | Per-day schedule preference (family keeper set) | #AP029 |
| `teacher_of_record_email_address` | Teacher of Record Email Address | charter | TOR auto-create trigger; read/written by tor_family scripts 【code: ops】 | #AP029 |
| `teacher_of_record_name` | Teacher of Record Name | charter | Family's pointer to their teacher — legacy intake capture, superseded by typeId-15 association but still LIVE and load-bearing (auto-create trigger) 【code: email, ops】 | #AP029 |
| `thursday_schedule_preference` | Thursday Schedule Preference | level-up_ilead | Per-day schedule preference (family keeper set) | #AP029 |
| `tuesday_schedule_preference` | Tuesday Schedule Preference | level-up_ilead | Per-day schedule preference (family keeper set) | #AP029 |
| `wednesday_schedule_preference` | Wednesday Schedule Preference | level-up_ilead | Per-day schedule preference (family keeper set) | #AP029 |
| `what_is_your_child_s_current_grade_level_` | What grade is your child in? | contactinformation | CANONICAL student grade — the property agents use for grade level, always (Roman 2026-08-10); call agent overwrite target 【code: ops】 | #AP027 |

## Moved → `tor` group (Teacher of Record/EF/ES) — EXECUTED 2026-08-10

Internal names unchanged (safe, #AP024). "Current group" shows the pre-move location for the audit trail.

| Internal name | Label | Current group | Rationale | Decision |
|---|---|---|---|---|
| `charter_school_teacher` | Charter School Teacher | charter | School dropdown = master school list; shows when TOR flag = Yes 【code: ops】 | #AP028 |
| `educational_facillitator_teacher_of_record` | Educational Facillitator/Teacher of Record | charter | Yes/No TOR flag; conditional display drives school dropdown | #AP028 |
| `last_tor_workflow_enrollment_date` | Last TOR Workflow Enrollment Date | charter | TOR nurture-workflow bookkeeping; belongs with TOR persona |  |
| `teacher_email_address` | Teacher Email Address | contactinformation | Danielle's live marketing-form field (15 fills) — not a duplicate | #AP028 |

## Moved → `tutor` group (Tutors) — EXECUTED 2026-08-10

Internal names unchanged (safe, #AP024). "Current group" shows the pre-move location for the audit trail.

| Internal name | Label | Current group | Rationale | Decision |
|---|---|---|---|---|
| `a__pay_per_hour` | A+ Pay Per Hour | new_tutors | Tutor pay rate — core tutor record | #AP024 |
| `completed_tutor_training` | Completed Tutor Training | new_tutors | Onboarding status (active 2026) | #AP024 |
| `degree_received` | Degree Received | new_tutors | Tutor credential | #AP024 |
| `online_in_person_` | Online or In-Person | new_tutors | Tutor delivery mode | #AP024 |
| `resume` | Resume | new_tutors | Tutor resume file (recruiting form) | #AP024 |
| `select_days_for_availability` | Select Days for Availability | new_tutors | Tutor availability | #AP024 |
| `tutor_profile` | Tutor Profile | new_tutors | Tutor bio used for matching/intro | #AP024 |
| `university_attended` | University Attended | new_tutors | Tutor credential | #AP024 |
| `what_subjects_do_you_feel_the_most_qualified_to_tutor_` | What subjects do you feel the most qualified to tutor? | new_tutors | Tutor subjects (structured checkbox) | #AP024 |

## Moved → `student` group (Student) — EXECUTED 2026-08-10

Internal names unchanged (safe, #AP024). "Current group" shows the pre-move location for the audit trail.

| Internal name | Label | Current group | Rationale | Decision |
|---|---|---|---|---|
| `student_email_address` | Student Email Address | contactinformation | Student contact point (distinct from parent email) | #AP024 |
| `student_last_name` | Student FIRST Name | student | DONE — moved by Roman 2026-08-10. LABEL MISMATCH: label is "Student FIRST Name" — student 1 first name; Teachworks disambiguation + call agent fill_only 【code: email, ops】 | #AP029 |
| `student_last_name_if_diff_from_parent` | Student Last Name | student | DONE — moved by Roman 2026-08-10 (out of CAP form_fields). Student last name; call agent fill_only 【code: email, ops, registry.yml】 | #AP029 |

## KEEP-IN-PLACE (185)

Stay exactly where they are. Programs stay grouped as programs, not personas (locked rule 6); form-bound and integration-owned fields are not touched.

| Internal name | Label | Current group | Rationale | Decision |
|---|---|---|---|---|
| `a_persona` | A+ PERSONA | master | THE master persona switch, already in `master` group; declared in properties.yml 【code: email, ops】 | #AP024 |
| `area_of_need` | Area of Need | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `area_s__of_need` | Area(s) of Need | charter | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `area_s__of_need__check_all_that_apply_` | Area(s) of Need. Check all that apply. | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `booked_on_the_spot` | Booked on the Spot | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `calendar_link_sent` | Calendar Link Sent | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `call_destination_number` | Call destination number | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `call_held_date` | Call Held Date | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `call_recording_link` | Call Recording Link | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `call_scheduled_date` | Call Scheduled Date | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `caller_id` | Caller Id | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `callrail_lead_score` | CallRail Lead Score | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `contact_level_deal_stage` | Contact Level Deal Stage | contactinformation | Workflow-maintained stage mirror (2025) — verify Used-in before any change |  |
| `create_date_not_unix` | Create Date Not Unix | pilibos_program | Pilibos program (live) |  |
| `date_of_first_call` | Date of first call | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `diagnostic_submitted_date` | Diagnostic Submitted Date | pilibos_program | Pilibos program (live) |  |
| `did_you_submit_a_purchase_order__po__to_a__tutoring_` | Did you submit a Purchase Order (PO) to A+ Tutoring? | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `duration` | Duration | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `family_contacted_date` | Family Contacted Date | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `final_decision_university_` | Final Decision University: | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `first_campaign_contacted` | First campaign contacted | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `first_medium_contacted` | First medium contacted | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `first_source_contacted` | First Source Contacted | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `first_tracking_number_contacted` | First Tracking Number Contacted | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `for_el_learners__what_is_their_home_language_` | For EL learners, what is their home language? | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `form_capture_data` | Form Capture Data | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `form_sent_date` | Form Sent Date | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `formatted_duration` | Formatted Duration | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `gclid` | GCLID | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `gpa` | GPA | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `grade_level` | Grade Level | contactinformation | Danielle's scholarship forms — live, not a duplicate | #AP027 |
| `handoff_date` | Handoff Date | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `home_language` | Home Language | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `how_many_students_are_you_nominating_` | How Many Students Are You Nominating? | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `iep_504_` | IEP/504? | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `if__other___please_explain_` | If "other", please explain: | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `if_the_student_has_an_iep_or_504_plan___please_give_us_a_brief_description_to_best_support_this_stu` | If the student has an IEP or 504 plan - please give us a brief description to best support this student | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `intended_major_or_area_of_study` | Intended Major or Area of Study | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `is_the_learner_designated_el_` | Is the learner designated EL? | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `last_campaign_contacted` | Last campaign contacted | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `last_keywords` | Last Keywords | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `last_landing_page` | Last Landing Page | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `last_medium_contacted` | Last medium contacted | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `last_source_contacted` | Last Source Contacted | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `last_tracking_number_contacted` | Last Tracking Number Contacted | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `lead_explanation` | Lead Explanation | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `lead_score` | Lead Score | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `lead_source__event` | Lead Source – Event | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `meeting_outcome` | Meeting Outcome | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `monetary_value` | Monetary value | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `most_recent_call_sentiment` | Most recent call sentiment | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `nominating_teacher_name` | Nominating Teacher Name | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `nomination_form_completed` | Nomination Form Completed | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `nomination_form_sent` | Nomination Form Sent | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `nomination_status` | Nomination Status | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `nominations_received` | Nominations Received | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `outcome` | Outcome | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `pilibos_attend_afternoons` | Can Attend Afternoons (1 PM–4 PM) — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_attend_mornings` | Can Attend Mornings (9 AM–12 PM) — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_august_sat_acknowledged` | August 22 SAT Registration Acknowledged — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_cb_practice_score_report` | College Board Practice Test Score Report — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_diagnostic_math_score` | Diagnostic Math Score | pilibos_program | Pilibos program (live) |  |
| `pilibos_diagnostic_received` | Diagnostic Received | pilibos_program | Pilibos program (live) |  |
| `pilibos_diagnostic_rw_score` | Diagnostic R+W Score | pilibos_program | Pilibos program (live) |  |
| `pilibos_diagnostic_score_report` | Diagnostic Score Report | pilibos_program | Pilibos program (live) |  |
| `pilibos_diagnostic_token` | Diagnostic Upload Token | pilibos_program | Pilibos program (live) |  |
| `pilibos_payment_received` | Pilibos Payment Received | pilibos_program | Pilibos program (live) |  |
| `pilibos_psat_score_report` | PSAT October 2025 Score Report — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_role` | Pilibos Role | pilibos_program | Pilibos program (live) |  |
| `pilibos_student_email` | Student Email — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_student_first_name` | Student First Name — Contact Mirror | pilibos_program | Pilibos program (live) 【code: email】 |  |
| `pilibos_student_last_name` | Student Last Name — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_student_phone` | Student Phone — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_summer_2026` | Pilibos Summer 2026 | pilibos_program | Pilibos program (live) |  |
| `pilibos_terms_acknowledged` | Non-Refundable Terms Acknowledged — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_tier` | Program Tier — Contact Mirror | pilibos_program | Pilibos program (live) |  |
| `pilibos_upload_token` | Pilibos Upload Token | pilibos_program | Pilibos program (live) |  |
| `please_attach_a_pdf_of_the_student_s_most_recent_map_score_data__if_you_do_not_use_map__please_uplo` | Student Assessment PDF upload | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `please_share_any_unique_needs_we_should_be_made_aware_of____examples__accommodations__modifications` | Please share any unique needs we should be made aware of?  (examples: accommodations, modifications, learning supports, etc.)? | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `please_share_anything_specific__if_science__what_science___etc__` | Please share anything specific (if science, what science - etc.) | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `po_submitted_date` | PO Submitted Date | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `qualified_score` | Qualified score | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `reason_lost` | Reason Lost | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `sat_or_act` | Which Exam are you taking? (SAT or ACT) | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `sms_message` | SMS Message | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `source` | Source | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `source_s__of_data_that_point_to_the_need__check_all_that_apply_` | Source(s) of data that point to the need. Check all that apply. | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `sources_of_data_that_point_to_the_need__check_all_that_apply_` | Sources of data that point to the need. Check all that apply. | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `spotlight_assessment_type` | Spotlight Assessment Type | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_baseline_scores` | Spotlight Baseline Scores | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_before_experience` | Spotlight Before Experience | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_call_ai_summary` | Spotlight Call AI Summary | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_consent` | Spotlight Consent | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_content_link` | Spotlight Content Link | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_current_scores` | Spotlight Current Scores | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_gift_card_preference` | Spotlight Gift Card Preference | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_gift_card_sent` | Spotlight Gift Card Sent | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_grade_level` | Spotlight Grade Level | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_growth_areas` | Spotlight Growth Areas | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_has_before_scores` | Spotlight Has Before Scores | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_has_current_scores` | Spotlight Has Current Scores | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_lesson_notes_ai_summary` | Spotlight Lesson Notes AI Summary | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_nomination_date` | Spotlight Nomination Date | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_notes` | Spotlight Notes | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_parent_additional_comments` | Spotlight - Additional Comments | contactinformation | Spotlight program field living in contactinformation |  |
| `spotlight_parent_call_complete` | Spotlight Parent Call Complete | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_positive_changes` | Spotlight Positive Changes | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_review_link` | Spotlight Review Link | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_review_status` | Spotlight Review Status | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_scheduling_rating` | Spotlight Scheduling Rating | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_school_name` | Spotlight School Name | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_school_recognition` | Spotlight School Recognition | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_session_notes_rating` | Spotlight Session Notes Rating | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_status` | Spotlight Status | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_student_first_name` | Spotlight Student First Name | spotlight | Spotlight program (live) — programs stay grouped as programs 【code: email】 |  |
| `spotlight_subjects` | Spotlight Subjects | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_tor_call_complete` | Spotlight TOR Call Complete | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_tor_email` | Spotlight TOR Email | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_tor_name` | Spotlight TOR Full Name | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_tutor_email` | Spotlight Tutor Email | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_tutor_feedback` | Spotlight Tutor Feedback | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_tutor_name` | Spotlight Tutor Name | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `spotlight_tutoring_start_date` | Spotlight Tutoring Start Date | spotlight | Spotlight program (live) — programs stay grouped as programs |  |
| `stripe_amount_paid` | Stripe Amount Paid | pilibos_program | Pilibos program (live) |  |
| `stripe_payment_intent` | Stripe Payment Intent | pilibos_program | Pilibos program (live) |  |
| `stripe_session_id` | Stripe Session ID | pilibos_program | Pilibos program (live) |  |
| `student_cell_phone` | Student Cell Phone | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `success_team_member_responsible` | Success Team Member Responsible | contactinformation | Active ops routing field (2025) |  |
| `summer_2020_availability` | Summer 2020 Availability | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `tags` | Tags | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `teacher_first_name` | Teacher First Name | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `teacher_last_name` | Teacher Last Name | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `teacher_scholarship_nomination__how_many_students_are_you_nominating` | Teacher Scholarship Nomination - How Many Students Are You Nominating? | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__parent_email` | Teacher Scholarship Nomination - Parent Email | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__parent_first_name` | Teacher Scholarship Nomination - Parent First Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__parent_last_name` | Teacher Scholarship Nomination - Parent Last Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__parent_phone_number` | Teacher Scholarship Nomination - Parent Phone Number | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_1__parent_email` | Teacher Scholarship Nomination - Student 1 - Parent Email | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_1__parent_first_name` | Teacher Scholarship Nomination - Student 1 - Parent First Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_1__parent_last_name` | Teacher Scholarship Nomination - Student 1 - Parent Last Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_1__parent_phone_number` | Teacher Scholarship Nomination - Student 1 - Parent Phone Number | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_1__student_first_name` | Teacher Scholarship Nomination - Student 1 - Student First Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_1__student_grade_level` | Teacher Scholarship Nomination - Student 1 - Student Grade Level | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program; grade verdict: KEEP | #AP027 |
| `teacher_scholarship_nomination__student_1__student_information_from_teacher` | Teacher Scholarship Nomination - Student 1 - Student Information From Teacher | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_1__student_last_name` | Teacher Scholarship Nomination - Student 1 - Student Last Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_1__subjects_needing_support` | Teacher Scholarship Nomination - Student 1 - Subject(s) Needing Support | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_2__parent_email` | Teacher Scholarship Nomination - Student 2 - Parent Email | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_2__parent_first_name` | Teacher Scholarship Nomination - Student 2 - Parent First Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_2__parent_last_name` | Teacher Scholarship Nomination - Student 2 - Parent Last Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_2__parent_phone_number` | Teacher Scholarship Nomination - Student 2 - Parent Phone Number | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_2__student_first_name` | Teacher Scholarship Nomination - Student 2 - Student First Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_2__student_grade_level` | Teacher Scholarship Nomination - Student 2 - Student Grade Level | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program; grade verdict: KEEP | #AP027 |
| `teacher_scholarship_nomination__student_2__student_information_from_teacher` | Teacher Scholarship Nomination - Student 2 - Student Information From Teacher | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_2__student_last_name` | Teacher Scholarship Nomination - Student 2 - Student Last Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_2__subjects_needing_support` | Teacher Scholarship Nomination - Student 2 - Subject(s) Needing Support | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_3__parent_email` | Teacher Scholarship Nomination - Student 3 - Parent Email | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_3__parent_first_name` | Teacher Scholarship Nomination - Student 3 - Parent First Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_3__parent_phone_number` | Teacher Scholarship Nomination - Student 3 - Parent Phone Number | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_3__student_first_name` | Teacher Scholarship Nomination - Student 3 - Student First Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_3__student_grade_level` | Teacher Scholarship Nomination - Student 3 - Student Grade Level | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program; grade verdict: KEEP | #AP027 |
| `teacher_scholarship_nomination__student_3__student_information_from_teacher` | Teacher Scholarship Nomination - Student 3 - Student Information from Teacher | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_3__student_last_name` | Teacher Scholarship Nomination - Student 3 - Student Last Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_3__subjects_needing_support` | Teacher Scholarship Nomination - Student 3 - Subject(s) Needing Support | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_3_parent_last_name` | Teacher Scholarship Nomination - Student 3 -Parent Last Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_first_name` | Teacher Scholarship Nomination - Student First Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__student_last_name` | Teacher Scholarship Nomination - Student Last Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__teacher_first_name` | Teacher Scholarship Nomination - Teacher First Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__teacher_last_name` | Teacher Scholarship Nomination - Teacher Last Name | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `teacher_scholarship_nomination__yesno` | Teacher Scholarship Nomination - Yes/No | contactinformation | Teacher Scholarship Nomination program (live) — stays grouped as program |  |
| `top_3_dream_colleges` | Top 3 Dream Colleges | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `tracking_number_company_name` | Tracking Number Company Name | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `transcripts` | Transcripts | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `trial_start_date` | Trial Start Date | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `tutoring_frequency` | Tutoring Frequency | level-up_ilead | Live get-started form field (level-up_ilead) |  |
| `unresponsive_from_stage` | Unresponsive From Stage | contactinformation | Teacher Scholarship Nomination program — live pipeline tracker (Jul 2026) |  |
| `uploaded_diagnostic` | Uploaded Diagnostic | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `voice_assist_caller_email_address` | Voice Assist caller email address | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `voice_assist_caller_name` | Voice Assist caller name | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `voice_assist_caller_preferred_phone_number` | Voice Assist caller preferred phone number | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `voice_assist_message_taken` | Voice Assist message taken | analyticsinformation | CallRail / Voice Assist integration-written (live) — integration-owned, agents read-only |  |
| `was_a_po_submitted_for_this_submission` | Was a PO submitted for this submission | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `what_are_your_top_3_extracurricular_activities` | What are your top 3 Extracurricular Activities | form_fields | CAP `form_fields` group — dead business but form-bound; DO NOT TOUCH; future re-home candidate only |  |
| `what_is_the_student_s_measurable__academic_goal_for_the_requested_hours_of_tutoring_` | What is the student's measurable, academic goal for the requested hours of tutoring? | contactinformation | Charter/IEM intake form field (2025 batch, live charter program) |  |
| `when_would_you_like_the_tutoring_to_start` | When would you like the tutoring to start | level-up_ilead | Live get-started form field |  |
| `which_days_of_the_week_do_you_prefer_` | Which days of the week do you prefer? | level-up_ilead | Live get-started form field (structured days) |  |

## STORAGE-ONLY (119)

Data preserved, nothing reads or writes them going forward. No archive proposed — they simply drop out of agent vocabulary.

| Internal name | Label | Current group | Rationale | Decision |
|---|---|---|---|---|
| `abandoned_cart_counter` | Abandoned Cart Counter | abandoned_cart | Dead ecommerce cart integration |  |
| `abandoned_cart_date` | Abandoned Cart Date | abandoned_cart | Dead ecommerce cart integration |  |
| `abandoned_cart_products` | Abandoned Cart Products | abandoned_cart | Dead ecommerce cart integration |  |
| `abandoned_cart_products_categories` | Abandoned Cart Products Categories | abandoned_cart | Dead ecommerce cart integration |  |
| `abandoned_cart_products_html` | Abandoned Cart Products HTML | abandoned_cart | Dead ecommerce cart integration |  |
| `abandoned_cart_products_skus` | Abandoned Cart Products SKUs | abandoned_cart | Dead ecommerce cart integration |  |
| `abandoned_cart_recovery_workflow_conversion` | Abandoned Cart Recovery Workflow Conversion | roi_tracking | Dead ecommerce ROI workflows |  |
| `abandoned_cart_recovery_workflow_conversion_amount` | Abandoned Cart Recovery Workflow Conversion Amount | roi_tracking | Dead ecommerce ROI workflows |  |
| `abandoned_cart_recovery_workflow_conversion_date` | Abandoned Cart Recovery Workflow Conversion Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `abandoned_cart_recovery_workflow_start_date` | Abandoned Cart Recovery Workflow Start Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `abandoned_cart_subtotal` | Abandoned Cart Subtotal | abandoned_cart | Dead ecommerce cart integration |  |
| `abandoned_cart_tax_value` | Abandoned Cart Tax Value | abandoned_cart | Dead ecommerce cart integration |  |
| `abandoned_cart_total_value` | Abandoned Cart Total Value | abandoned_cart | Dead ecommerce cart integration |  |
| `abandoned_cart_url` | Abandoned Cart URL | abandoned_cart | Dead ecommerce cart integration |  |
| `account_creation_date` | Account Creation Date | rfm_fields | Dead ecommerce RFM scoring |  |
| `average_days_between_orders` | Average Days Between Orders | rfm_fields | Dead ecommerce RFM scoring |  |
| `average_order_value` | Average Order Value | rfm_fields | Dead ecommerce RFM scoring |  |
| `billing_address_line_1` | Billing Address Line 1 | shopping_cart_fields | Dead ecommerce integration |  |
| `billing_address_line_2` | Billing Address Line 2 | shopping_cart_fields | Dead ecommerce integration |  |
| `billing_city` | Billing City | shopping_cart_fields | Dead ecommerce integration |  |
| `billing_country` | Billing Country | shopping_cart_fields | Dead ecommerce integration |  |
| `billing_postal_code` | Billing Postal Code | shopping_cart_fields | Dead ecommerce integration |  |
| `billing_state` | Billing State | shopping_cart_fields | Dead ecommerce integration |  |
| `case_worker_email_address` | Case Worker Email Address | child_and_family_guidance | CFG partner-program data (2019) — keep data, program inactive |  |
| `case_worker_full_name` | Case Worker Full Name | child_and_family_guidance | CFG partner-program data (2019) — keep data, program inactive |  |
| `case_worker_phone_number` | Case Worker Phone Number | child_and_family_guidance | CFG partner-program data (2019) — keep data, program inactive |  |
| `categories_bought` | Categories Bought | categories_bought | Dead ecommerce integration |  |
| `current_abandoned_cart` | Current Abandoned Cart | abandoned_cart | Dead ecommerce cart integration |  |
| `current_roi_campaign` | Current ROI Campaign | roi_tracking | Dead ecommerce ROI workflows |  |
| `customer_group` | Customer Group/ User role | unused_properties | Ecommerce user-role remnant |  |
| `customer_new_order` | Customer New Order | roi_tracking | Dead ecommerce ROI workflows |  |
| `customer_reengagement_workflow_conversion` | Customer Reengagement Workflow Conversion | roi_tracking | Dead ecommerce ROI workflows |  |
| `customer_reengagement_workflow_conversion_amount` | Customer Reengagement Workflow Conversion Amount | roi_tracking | Dead ecommerce ROI workflows |  |
| `customer_reengagement_workflow_conversion_date` | Customer Reengagement Workflow Conversion Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `customer_reengagement_workflow_start_date` | Customer Reengagement Workflow Start Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `customer_rewards_workflow_conversion` | Customer Rewards Workflow Conversion | roi_tracking | Dead ecommerce ROI workflows |  |
| `customer_rewards_workflow_conversion_amount` | Customer Rewards Workflow Conversion Amount | roi_tracking | Dead ecommerce ROI workflows |  |
| `customer_rewards_workflow_conversion_date` | Customer Rewards Workflow Conversion Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `customer_rewards_workflow_start_date` | Customer Rewards Workflow Start Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `first_order_date` | First Order Date | rfm_fields | Dead ecommerce RFM scoring |  |
| `first_order_value` | First Order Value | rfm_fields | Dead ecommerce RFM scoring |  |
| `how_satisfied_are_you_with_the_level_of_communication_you_have_received_from_the_a__tutoring_and_yo` | How satisfied are you with the level of communication you have received from the A+ tutoring and your tutor regarding the student’s progress and any concerns? | contactinformation | 2023 satisfaction survey response data — keep data, stop using |  |
| `how_well_did_your_tutor_connect_with_the_student_on_a_personal_level_to_create_a_nurturing_and_effe` | How well did your tutor connect with the student on a personal level to create a nurturing and effective learning environment? | contactinformation | 2023 satisfaction survey response data |  |
| `ip__ecomm_bridge__ecomm_synced` | Ecommerce contact | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__ecomm_bridge__source_app_id` | Source app ID | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__ecomm_bridge__source_store_id` | Source store | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__sync_extension__external_source_account_id` | Source account ID | ip__sync_extension__sync_extension | Sync extension app plumbing |  |
| `ip__sync_extension__external_source_app_id` | Source app ID | ip__sync_extension__sync_extension | Sync extension app plumbing |  |
| `last_categories_bought` | Last Categories Bought | categories_bought | Dead ecommerce integration |  |
| `last_order_currency` | Last Order Currency | order | Dead ecommerce integration |  |
| `last_order_date` | Last Order Date | rfm_fields | Dead ecommerce RFM scoring |  |
| `last_order_fulfillment_status` | Last Order Fulfillment Status | order | Dead ecommerce integration |  |
| `last_order_order_number` | Last Order Number | order | Dead ecommerce integration |  |
| `last_order_shipment_date` | Last Order Shipment Date | order | Dead ecommerce integration |  |
| `last_order_status` | Last Order Status | order | Dead ecommerce integration |  |
| `last_order_tracking_number` | Last Order Tracking Number | order | Dead ecommerce integration |  |
| `last_order_tracking_url` | Last Order Tracking URL | order | Dead ecommerce integration |  |
| `last_order_value` | Last Order Value | rfm_fields | Dead ecommerce RFM scoring |  |
| `last_product_bought` | Last Product Bought | last_products_bought | Dead ecommerce integration |  |
| `last_product_types_bought` | Last Product Types Bought | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought` | Last Products Bought | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_html` | Last Products Bought HTML | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_1_image_url` | Last Products Bought Product 1 Image URL | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_1_name` | Last Products Bought Product 1 Name | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_1_price` | Last Products Bought Product 1 Price | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_1_url` | Last Products Bought Product 1 Url | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_2_image_url` | Last Products Bought Product 2 Image URL | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_2_name` | Last Products Bought Product 2 Name | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_2_price` | Last Products Bought Product 2 Price | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_2_url` | Last Products Bought Product 2 Url | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_3_image_url` | Last Products Bought Product 3 Image URL | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_3_name` | Last Products Bought Product 3 Name | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_3_price` | Last Products Bought Product 3 Price | last_products_bought | Dead ecommerce integration |  |
| `last_products_bought_product_3_url` | Last Products Bought Product 3 Url | last_products_bought | Dead ecommerce integration |  |
| `last_skus_bought` | Last SKUs Bought | skus_bought | Dead ecommerce integration |  |
| `last_total_number_of_products_bought` | Last Total Number Of Products Bought | last_products_bought | Dead ecommerce integration |  |
| `monetary_rating` | Monetary Rating | rfm_fields | Dead ecommerce RFM scoring |  |
| `mql_capture_nurture_conversion_conversion` | MQL Capture, Nurture & Conversion Conversion | roi_tracking | Dead ecommerce ROI workflows |  |
| `mql_capture_nurture_conversion_conversion_amount` | MQL Capture, Nurture & Conversion Conversion Amount | roi_tracking | Dead ecommerce ROI workflows |  |
| `mql_capture_nurture_conversion_conversion_date` | MQL Capture, Nurture & Conversion Conversion Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `mql_capture_nurture_conversion_start_date` | MQL Capture, Nurture & Conversion Start date | roi_tracking | Dead ecommerce ROI workflows |  |
| `new_customer_workflow_conversion` | New Customer Workflow Conversion | roi_tracking | Dead ecommerce ROI workflows |  |
| `new_customer_workflow_conversion_amount` | New Customer Workflow Conversion Amount | roi_tracking | Dead ecommerce ROI workflows |  |
| `new_customer_workflow_conversion_date` | New Customer Workflow Conversion Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `new_customer_workflow_start_date` | New Customer Workflow Start Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `newsletter_subscription` | Accepts Marketing | unused_properties | Ecommerce "Accepts Marketing" remnant |  |
| `order_frequency_rating` | Order Frequency Rating | rfm_fields | Dead ecommerce RFM scoring |  |
| `order_recency_rating` | Order Recency Rating | rfm_fields | Dead ecommerce RFM scoring |  |
| `package_preference` | Package Preference | integrations | VideoAsk / misc integration remnants |  |
| `please_provide_any_additional_comments_or_suggestions_you_have_about_your_experience_with_a__tutori` | Please provide any additional comments or suggestions you have about your experience with A+ Tutoring. We’re particularly interested in any insights that would make us even better educators. | contactinformation | 2023 satisfaction survey response data |  |
| `product_types_bought` | Product Types Bought | last_products_bought | Dead ecommerce integration |  |
| `products_bought` | Products Bought | last_products_bought | Dead ecommerce integration |  |
| `promo_code` | Promo Code | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `resume_title_and_date_of_applied` | Resume Title and Date of Applied | integrations | VideoAsk / misc integration remnants |  |
| `second_purchase_workflow_conversion` | Second Purchase Workflow Conversion | roi_tracking | Dead ecommerce ROI workflows |  |
| `second_purchase_workflow_conversion_amount` | Second Purchase Workflow Conversion Amount | roi_tracking | Dead ecommerce ROI workflows |  |
| `second_purchase_workflow_conversion_date` | Second Purchase Workflow Conversion Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `second_purchase_workflow_start_date` | Second Purchase Workflow Start Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `shipping_address_line_1` | Shipping Address Line 1 | shopping_cart_fields | Dead ecommerce integration |  |
| `shipping_address_line_2` | Shipping Address Line 2 | shopping_cart_fields | Dead ecommerce integration |  |
| `shipping_city` | Shipping City | shopping_cart_fields | Dead ecommerce integration |  |
| `shipping_country` | Shipping Country | shopping_cart_fields | Dead ecommerce integration |  |
| `shipping_postal_code` | Shipping Postal Code | shopping_cart_fields | Dead ecommerce integration |  |
| `shipping_state` | Shipping State | shopping_cart_fields | Dead ecommerce integration |  |
| `shopping_cart_customer_id` | Shopping Cart ID | customer_group | Ecommerce bridge remnant |  |
| `skus_bought` | SKUs Bought | skus_bought | Dead ecommerce integration |  |
| `third_purchase_workflow_conversion` | Third Purchase Workflow Conversion | roi_tracking | Dead ecommerce ROI workflows |  |
| `third_purchase_workflow_conversion_amount` | Third Purchase Workflow Conversion Amount | roi_tracking | Dead ecommerce ROI workflows |  |
| `third_purchase_workflow_conversion_date` | Third Purchase Workflow Conversion Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `third_purchase_workflow_start_date` | Third Purchase Workflow Start Date | roi_tracking | Dead ecommerce ROI workflows |  |
| `to_what_extent_have_you_noticed_an_improvement_in_the_student_s_academic_performance_since_beginnin` | To what extent have you noticed an improvement in the student’s academic performance since beginning sessions with A+ Tutoring? | contactinformation | 2023 satisfaction survey response data |  |
| `total_number_of_current_orders` | Total Number of Current Orders | order | Dead ecommerce integration |  |
| `total_number_of_orders` | Total Number of Orders | rfm_fields | Dead ecommerce RFM scoring |  |
| `total_number_of_products_bought` | Total Number Of Products Bought | last_products_bought | Dead ecommerce integration |  |
| `total_value_of_orders` | Total Value of Orders | rfm_fields | Dead ecommerce RFM scoring |  |
| `unused_balance` | Unused Balance | integrations | VideoAsk / misc integration remnants |  |
| `video_ask_submission_link` | Video Ask Submission Link | integrations | VideoAsk / misc integration remnants |  |
| `video_ask_transcription` | Video Ask Transcription | integrations | VideoAsk / misc integration remnants |  |
| `videoasksource` | Videoask source | contactinformation | VideoAsk integration remnant |  |

## RETIRE-CANDIDATE (99)

Every row requires Roman's manual **"Used in"** check in the HubSpot UI (property → Used in: lists, workflows, forms, reports) before any archive. Archive is reversible; nothing is retired in this session (locked rule 10).

| Internal name | Label | Current group | Fill count | Last def. update | Used-in checked | Rationale | Decision |
|---|---|---|---|---|---|---|---|
| `actively_counseling` | Actively Counseling | customer_group | 52 | 2021-07-06 | ☐ | Legacy ops flag (2021-23 era) |  |
| `actively_tutoring` | Actively Tutoring | customer_group | 3318 | 2021-07-06 | ☐ | Legacy ops flag (2021-23 era) |  |
| `additional_note` | Additional note | contactinformation | 1 | 2023-11-25 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `ap_subjects` | Which AP Subjects are you interested in? | unused_properties | 1 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `are_missing_assignments_a_concern` | Are missing assignments a concern? | lead_ads | 0 | 2020-07-07 | ☐ | FB lead-ad capture leftovers |  |
| `asked_for_a_review_` | Asked for a review? | customer_group | 115 | 2021-07-06 | ☐ | Legacy ops flag (2021-23 era) |  |
| `assessment_attended___in_house` | Assessment Attended - In House | customer_group | 7 | 2021-12-22 | ☐ | Legacy ops flag (2021-23 era) |  |
| `assessment_graded___in_house` | Assessment Graded - In House | customer_group | 7 | 2021-12-22 | ☐ | Legacy ops flag (2021-23 era) |  |
| `assessment_received` | Assessment Graded - Remote | customer_group | 77 | 2021-12-22 | ☐ | Legacy ops flag (2021-23 era) |  |
| `assessment_sent` | Assessment Sent | customer_group | 349 | 2021-09-10 | ☐ | Legacy ops flag (2021-23 era) |  |
| `assessment_uploaded` | Assessment Received - Remote | customer_group | 380 | 2021-12-22 | ☐ | Legacy ops flag (2021-23 era) |  |
| `avatar` | Avatar | customer_group | 107 | 2021-07-06 | ☐ | Legacy ops flag (2021-23 era) |  |
| `bombas_coupon_code` | Bombas Coupon Code | customer_group | 86 | 2021-07-06 | ☐ | Legacy ops flag (2021-23 era) |  |
| `business_license_on_file` | Business License on File | new_tutors | 24 | 2022-05-18 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `cancelled_covid19` | CANCELLED-COVID19 | unused_properties | 61 | 2021-02-12 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `college_test_prep` | Which Test Are You Leaning Towards Taking? | unused_properties | 3 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `contact_created_by_1st_edit` | Contact Last Edited By | contactinformation | 2707 | 2023-09-09 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `current_employer` | Current Employer | new_tutors | 35 | 2022-03-07 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `date_for_first_free_lessons` | Date For First Free Lessons | date_properties | 0 | 2021-06-01 | ☐ | Summer-2021 scheduling flow leftovers |  |
| `date_of_first_session` | When does the school year start for your child? | date_properties | 2 | 2021-05-24 | ☐ | Summer-2021 scheduling flow leftovers |  |
| `date_of_tutoring_session_for_trial` | Date of Tutoring Session for Trial | contactinformation | 0 | 2023-11-25 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `date_to_start_customer_provided` | Date To Start New Schedule - Summer Update | date_properties | 8 | 2021-05-26 | ☐ | Summer-2021 scheduling flow leftovers |  |
| `date_to_stop_lessons_for_summer_update___schedule_update` | Date To Stop Lessons for Summer Update - Schedule Update | date_properties | 3 | 2021-05-26 | ☐ | Summer-2021 scheduling flow leftovers |  |
| `day_preference` | Day Preference | contactinformation | 0 | 2023-11-02 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `decision_day` | Decision Day | customer_group | 36 | 2022-01-14 | ☐ | Legacy ops flag (2021-23 era) |  |
| `do_you_have_a_college_list_created_` | Do you have a college list created? | unused_properties | 1 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `do_you_want_to_update_your_tutoring_schedule_` | Do you want to update your tutoring schedule? | customer_group | 9 | 2021-05-24 | ☐ | Legacy ops flag (2021-23 era) |  |
| `do_you_want_your_student_to_receive_email_notifications_for_lesson_reminders_` | Do you want your student to receive email notifications for lesson reminders? | customer_group | 21 | 2023-12-28 | ☐ | Legacy ops flag (2021-23 era) |  |
| `elementary_school_subject` | Elementary School Subjects | unused_properties | 34 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `end_date_for_tutoring_for_this_deal___deal_specific` | End Date for Tutoring for this Deal - Deal Specific | date_properties | 0 | 2021-05-26 | ☐ | Summer-2021 scheduling flow leftovers |  |
| `engaged_with_teacher_` | Engaged with Teacher? | contactinformation | 1 | 2025-05-22 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `english_subjects` | English Subjects | unused_properties | 2 | 2023-08-17 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `full_name` | Full Name | contactinformation | 10189 | 2025-10-01 | ☐ | Duplicate of firstname+lastname; updatedAt 2025-10 so check Used-in carefully |  |
| `get_started_form_start_date` | Get Started Form Only - Start Date | date_properties | 348 | 2021-05-24 | ☐ | Summer-2021 scheduling flow leftovers |  |
| `has_bonus_been_paid_out_` | Has Bonus Been Paid Out? | customer_group | 8 | 2022-04-19 | ☐ | Legacy ops flag (2021-23 era) |  |
| `has_your_child_worked_with_a_tutor_before_` | Has your child worked with a tutor before? | unused_properties | 39 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `have_missing_assignments_been_an_issue_` | Have missing assignments been an issue? | unused_properties | 34 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `have_you_taken_the_sat_or_act_already_` | Have you taken the SAT or ACT before? | unused_properties | 12 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `high_school_subjects` | High School Subjects | unused_properties | 13 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `how_did_you_hear_about_this_opportunity_with_a_tutoring` | How did you hear about this opportunity with A+ Tutoring | new_tutors | 1141 | 2022-10-27 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `how_did_you_hear_about_us___cloned__original_` | How Did You Hear About Us? (Cloned)(original) | contactinformation | 6763 | 2022-11-08 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `how_many_students_will_be_in_your_small_learning_pod_` | How many students will be in your small learning pod? | unused_properties | 37 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `if_selected_when_are_you_available_to_start_tutoring_` | If selected, when are you available to start tutoring? | new_tutors | 1073 | 2021-07-06 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `if_you_have_taken_the_myers_briggs_personality_test__what_is_your_personality_type__4_letters_` | If you have taken the Myers-Briggs Personality Test, what is your personality type (4 Letters) | new_tutors | 0 | 2022-07-19 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `internal___in_person_only_or_open_to_online_preference` | Internal - In-Person Only or Open to Online Preference | contactinformation | 1 | 2022-11-28 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `is_the_online_tutor_ready_for_onboarding` | Is the Online Tutor Ready for Onboarding | new_tutors | 32 | 2022-05-17 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `is_there_anything_specific_that_you_would_like_the_student_to_be_working_on_with_the_tutor_` | Is there anything specific that you would like the student to be working on with the tutor? | contactinformation | 52 | 2025-01-13 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `lead_ad_prop0` | What grade is your child in - lead ad | lead_ads | 2 | 2021-06-23 | ☐ | Dead lead-ad capture — Roman already approved retire | approved |
| `left_a_review_` | Left a review? | customer_group | 27 | 2021-07-06 | ☐ | Legacy ops flag (2021-23 era) |  |
| `major` | Major | new_tutors | 35 | 2022-03-07 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `marketing_newsletter` | Marketing Newsletter | customer_group | 0 | 2023-08-17 | ☐ | Legacy ops flag (2021-23 era) |  |
| `middle_school_subjects` | Middle School Subjects | unused_properties | 10 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `ms_and_hs_entrance_exams` | MS and HS Entrance Exams | unused_properties | 4 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `name_of_primary_contact_for_your_pod` | Name of Primary Contact for your pod | contactinformation | 23 | 2020-08-05 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `nps` | NPS | customer_group | 0 | 2021-05-24 | ☐ | Contact NPS number — scorecard NPS now sourced from Monday boards; verify Used-in (lists/reports) before archive |  |
| `optional__please_attach_a_pdf_of_the_student_s_most_up_to_date_iep_or_504_plan_` | Optional: Please attach a PDF of the student's most up to date IEP or 504 Plan. | contactinformation | 4 | 2025-02-10 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `other_subject` | Other Subject | contactinformation | 0 | 2023-11-29 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `payment_on_file_` | Payment on File? | contactinformation | 270 | 2023-08-17 | ☐ | Roman 2026-08-10: disregard as pay-type keeper — legacy checkbox |  |
| `pod_pay_per_hour` | SLP Pay Per Hour | new_tutors | 317 | 2022-05-18 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `qualified_lead_enroll_in_workflow` | Qualified Lead, enroll in Workflow | contactinformation | 70 | 2020-08-24 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `quoted_price_per_hour` | Quoted Price Per Hour | contactinformation | 328 | 2019-08-29 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `ready_to_start_date` | Get Started Form Only - Pods | date_properties | 44 | 2021-05-24 | ☐ | Summer-2021 scheduling flow leftovers |  |
| `reason_for_stopping_last_deal` | Reason for Stopping Last Deal | contactinformation | 0 | 2021-05-21 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `referral___referred_by___email` | Referral - Referred By - Email | referral_program | 54 | 2021-02-11 | ☐ | Superseded by referral_name keeper |  |
| `referral___referred_by___name` | Referral - Referred by - Name | referral_program | 57 | 2021-02-11 | ☐ | Superseded by referral_name keeper |  |
| `resignation_date_effective` | Resignation Date Effective | new_tutors | 10 | 2022-05-10 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `schedule_preference` | Schedule Preference | customer_group | 2496 | 2021-05-24 | ☐ | Free-text schedule pref superseded by per-day fields; classifier key of same name is internal, not this property |  |
| `science_subjects` | Science Subjects | unused_properties | 3 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `sequence_for_fall` | Sequence for Fall | contactinformation | 28 | 2020-09-03 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `service_level` | Service Level | contactinformation | 347 | 2019-09-06 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `sibling_current_grade_level` | Student 2 current grade level | sibling | 403 | 2026-04-09 | ☐ | Sibling grade — pending multi-child data-model decision | #AP027 |
| `sibling_school` | Student 2 School | sibling | 210 | 2019-09-05 | ☐ | Sibling school — pending multi-child data-model decision | #AP027 |
| `slack_message_intro` | Slack Message Intro | new_tutors | 80 | 2023-10-19 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `start_date_for_tutoring_for_this_deal` | Start Date for Tutoring for the most current deal | date_properties | 1554 | 2025-08-22 | ☐ | Summer-2021 scheduling flow leftovers |  |
| `stripe` | Stripe | contactinformation | 2 | 2020-08-17 | ☐ | Boolean "Stripe" flag from 2020 — payment truth now lives on deals (stripe_*) |  |
| `student_3` | Student 3 | sibling | 4 | 2023-07-12 | ☐ | Sibling stub field — pending multi-child data-model decision | #AP027 |
| `student_3_school` | Student 3 School | sibling | 20 | 2019-09-05 | ☐ | Sibling school — pending multi-child data-model decision | #AP027 |
| `student_4_school` | Student 4 School | sibling | 2 | 2019-09-05 | ☐ | Sibling school — pending multi-child data-model decision | #AP027 |
| `subject_preference` | Subject Preference | contactinformation | 0 | 2023-11-29 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `sync_to_teachworks_` | Sync to TeachWorks A+ | contactinformation | 1941 | 2020-08-14 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `sync_to_teachworks_cap` | Sync to TeachWorks CAP | contactinformation | 68 | 2021-05-20 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `sync_to_teachworks_slp` | Sync to Teachworks - SLP | contactinformation | 751 | 2020-08-14 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `time` | Time | contactinformation | 0 | 2023-11-02 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `trigger_sales_sequence` | Trigger Sales Sequence | unused_properties | 34 | 2021-02-12 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `tutor_matches` | Tutor Matches | contactinformation | 447 | 2019-09-09 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `tutor_referral___referred_by___email` | Tutor Referral - Referred By - Email | new_tutors | 30 | 2022-04-01 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `tutor_referral___referred_by___name` | Tutor Referral - Referred by - Name | new_tutors | 43 | 2022-04-01 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `tutor_referral_gift_card_sent_` | Tutor Referral Gift Card Sent? | new_tutors | 1 | 2022-04-01 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `tutoring_plan` | Tutoring Plan | unused_properties | 34 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `type_of_enrollment` | Type of Enrollment | conversioninformation | 0 | 2021-05-12 | ☐ | Legacy enrollment-type field |  |
| `video_ask___pass_first_interview` | Video Ask - Pass First Interview | new_tutors | 794 | 2022-03-07 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `we_ve_waived_cancellation` | Are they aware of our cancellation policy | customer_group | 30 | 2023-07-17 | ☐ | Legacy ops flag (2021-23 era) |  |
| `what_grade_is_your_child_in` | Student Grade - FB | lead_ads | 9 | 2021-06-23 | ☐ | Superseded — canonical grade is what_is_your_child_s_current_grade_level_ (Roman 2026-08-10); label "Student Grade - FB" (lead-ad capture) | #AP027 |
| `what_kind_of_tutoring_are_you_looking_for` | What kind of tutoring are you looking for? | unused_properties | 0 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `what_math_is_your_child_currently_working_on_` | What Math is Your Child Currently Working On? | unused_properties | 8 | 2022-01-14 | ☐ | Group literally named unused_properties — 2021-22 quiz/intake leftovers |  |
| `when_can_we_reach_out_to_you_to_resume_` | When can we reach out to you to resume? Schedule Update | date_properties | 6 | 2021-05-26 | ☐ | Summer-2021 scheduling flow leftovers |  |
| `when_would_you_like_the_first_lesson` | When would you like the first lesson | contactinformation | 0 | 2023-11-02 | ☐ | Legacy one-off field (see fill count / Used-in) |  |
| `which_subjects_do_you_feel_you_are_most_experienced_to_tutor_` | Which subjects do you feel you are most experienced to tutor? | new_tutors | 221 | 2021-02-12 | ☐ | Tutor-recruiting leftover not in the tutor keeper set |  |
| `why_did_they_not_commit_now_` | Why did they not commit now? | contactinformation | 6 | 2023-08-31 | ☐ | Legacy one-off field (see fill count / Used-in) |  |

## SYSTEM — out of scope (35 custom integration-written, plus all `hubspotDefined` properties)

Integration-written (JustCall, Zoom). Never touch; excluded from the keeper count (locked rule 1). Listed for completeness:

`initial_zoom_webinar_attendance_average_duration`, `jc_call_status_rc`, `jc_has_responded`, `jc_inbound_time`, `jc_incoming_call_status`, `jc_incoming_sms_count`, `jc_incoming_sms_count_rc`, `jc_incoming_sms_time`, `jc_incoming_sms_time_rc`, `jc_last_call_disposition`, `jc_last_call_disposition_sd`, `jc_last_call_outcome`, `jc_last_call_status`, `jc_missed_time`, `jc_outbound_time`, `jc_outgoing_sms_count_rc`, `jc_outgoing_sms_time_rc`, `jc_sms_body`, `jc_sms_body_inbound_rc`, `jc_sms_body_outbound_rc`, `jc_sms_opt_in`, `jc_sms_optout`, `jc_total_sms_count_rc`, `last_call_time_jc_rc`, `latest_call`, `total_calls_incoming_jc_rc`, `total_calls_jc`, `total_calls_outgoing_jc_rc`, `total_inbound_minutes`, `total_minutes`, `total_outbound_minutes`, `zoom_webinar_attendance_average_duration`, `zoom_webinar_attendance_count`, `zoom_webinar_joinlink`, `zoom_webinar_registration_count`


# HubSpot Deal Property Consolidation — Proposal

**Status: APPROVED by Roman 2026-08-10 — executed.** Persona group moves done (`execute_group_moves.py`, 41/41 verified); keepers declared in `properties.yml`; archive pass run on Roman's "go" (see RETIRE-CANDIDATE section for per-property outcomes: ARCHIVED / BLOCKED / HOLD). Archives are reversible for 90 days via HubSpot's deleted-properties restore. STORAGE-ONLY and KEEP-IN-PLACE require no action.

718 total deal properties; **611 are `hubspotDefined`** (incl. all `hs_v2_*` stage timers) and out of scope. The 107 custom properties below are each assigned a disposition. `po_inbox.deal_property_map` in email/config.yaml references student_first_name, student_last_name_if_diff_from_parent, student_grade, student_school, parent_email, parent_phone — agent-load-bearing (locked rules 11-12).

Monday-sync dependency: deal TOR fields (`teacher_of_record_name`, `teacher_of_record_email`, `tor_first_name`, `tor_last_name`) are keepers **until** the Teachworks low-balance alert replaces Monday — then retire (per prior session).

## Summary

| Disposition | Count |
|---|---|
| KEEP-IN-PLACE | 83 |
| STORAGE-ONLY | 10 |
| RETIRE-CANDIDATE | 14 |
| **Total custom** | **107** |

## KEEP-IN-PLACE (83)

Stay exactly where they are. Programs stay grouped as programs, not personas (locked rule 6); form-bound and integration-owned fields are not touched.

| Internal name | Label | Current group | Rationale | Decision |
|---|---|---|---|---|
| `a__slp_cap_invoice__` | A+/SLP/CAP Invoice # | charter_schools | KEEPER: Invoice # variant (charter/SLP/CAP) |  |
| `aplus_contractor_pay` | APlus Contractor Pay | tutor_info | KEEPER: Contractor pay (Monday sync) |  |
| `assigned_tutor` | Assigned Tutor | dealinformation | KEEPER: Tutor match on deal |  |
| `calendar_link_sent` | Teacher Scholarship Meeting Calendar Link Sent | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `contact_record_id` | Contact Record ID | dealinformation | Workflow plumbing (deal→contact pointer) — verify Used-in before any change |  |
| `date_of_last_lesson_in_this_deal` | Date of Last Lesson in this Deal | dealinformation | KEEPER: Deal service window end |  |
| `diagnostic_submitted_date` | Diagnostic Submitted Date | pilibos_program | Pilibos program (live) |  |
| `do_you_want_your_student_to_receive_email_notifications_for_lesson_reminders_` | Do you want your student to receive email notifications for lesson reminders? | scheduling_information | Scheduling form field |  |
| `family_consultation_status__teacher_scholarship_program` | Family Consultation Status - Teacher Scholarship Program | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `friday_schedule_preference` | Friday Schedule Preference | scheduling_information | KEEPER: Per-day schedule preference on deal |  |
| `iem_student_id` | IEM Student ID | charter | KEEPER: IEM student id (charter ops) |  |
| `invoice__` | Invoice # | dealinformation | KEEPER: Invoice # (Kath 2-step invoice flow) |  |
| `invoice_submitted_date` | Invoice Submitted Date | deal_activity | KEEPER: STEP-2 close-loop stamp (invoice sweep reads) 【code: email, registry.yml】 |  |
| `is_the_family_currently_being_tutored_by_us_` | Is the family currently being tutored by us? | charter_schools | Charter PO intake form field (2024, live) |  |
| `lessons_fulfilled_date` | Expected Lessons Fulfilled Date | charter_schools | KEEPER: Invoice due-date stamp (po_inbox invoice_task.invoice_due_property) 【code: email, registry.yml】 |  |
| `meeting_outcome` | Teacher Scholarship Meeting Outcome | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `monday_schedule_preference` | Monday Schedule Preference | scheduling_information | KEEPER: Per-day schedule preference on deal |  |
| `nominating_teacher_first_name` | Nominating Teacher First Name | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `nomination_form_completed` | Teacher Scholarship Nomination Form Completed | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `nomination_form_sent` | Teacher Scholarship Nomination Form Sent | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `nomination_reason` | Nomination Reason | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `nominations_received` | Teacher Scholarship Nominations Received | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `number_of_hours_in_this_po` | Number of Hours in this PO | dealinformation | KEEPER: PO hours — invoice task + sweep 【code: email, registry.yml】 |  |
| `online__inperson__charter` | ONLINE, INPERSON, CHARTER | dealinformation | KEEPER: Deal delivery segment |  |
| `outcome` | Teacher Scholarship Outcome | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `parent_email` | Parent Email | dealinformation | KEEPER: po_inbox deal_property_map: parent_email 【code: email, registry.yml】 |  |
| `parent_email_from_nomination` | Parent Email (from nomination) | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `parent_first_name` | Parent First Name | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `parent_last_name` | Parent Last Name | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `parent_phone` | Parent Phone | dealinformation | KEEPER: po_inbox deal_property_map: parent_phone 【code: email, registry.yml】 |  |
| `pilibos_attend_afternoons` | Can Attend Afternoons (1 PM–4 PM) | pilibos_program | Pilibos program (live) |  |
| `pilibos_attend_mornings` | Can Attend Mornings (9 AM–12 PM) | pilibos_program | Pilibos program (live) |  |
| `pilibos_august_sat_acknowledged` | August 22 SAT Registration Acknowledged | pilibos_program | Pilibos program (live) |  |
| `pilibos_cb_practice_score_report` | College Board Practice Test Score Report | pilibos_program | Pilibos program (live) |  |
| `pilibos_diagnostic_math_score` | Diagnostic Math Score | pilibos_program | Pilibos program (live) |  |
| `pilibos_diagnostic_received` | Diagnostic Received | pilibos_program | Pilibos program (live) |  |
| `pilibos_diagnostic_rw_score` | Diagnostic R+W Score | pilibos_program | Pilibos program (live) |  |
| `pilibos_diagnostic_score_report` | Diagnostic Score Report | pilibos_program | Pilibos program (live) |  |
| `pilibos_group_id` | Group ID | pilibos_program | Pilibos program (live) |  |
| `pilibos_psat_score_report` | PSAT October 2025 Score Report | pilibos_program | Pilibos program (live) |  |
| `pilibos_student_email` | Student Email | pilibos_program | Pilibos program (live) |  |
| `pilibos_student_first_name` | Student First Name | pilibos_program | Pilibos program (live) 【code: email】 |  |
| `pilibos_student_last_name` | Student Last Name | pilibos_program | Pilibos program (live) |  |
| `pilibos_student_phone` | Student Phone | pilibos_program | Pilibos program (live) |  |
| `pilibos_terms_acknowledged` | Non-Refundable Terms Acknowledged | pilibos_program | Pilibos program (live) |  |
| `pilibos_tier` | Program Tier | pilibos_program | Pilibos program (live) |  |
| `pilibos_track_assignment` | Track Assignment | pilibos_program | Pilibos program (live) |  |
| `po_number` | PO Number | charter_schools | KEEPER: PO identity — po_inbox dedup + invoice sweep key 【code: email, registry.yml】 |  |
| `reason_for_stopping` | Reason for Stopping | dealinformation | KEEPER: Churn reason |  |
| `saturday_schedule_preference` | Saturday Schedule Preference | scheduling_information | KEEPER: Per-day schedule preference on deal |  |
| `schedule_preferences` | Schedule Preferences | dealinformation | KEEPER: Stamped on B2C deal create (email engine main.py) 【code: email】 |  |
| `school_name` | School Name | dealinformation | KEEPER: Teacher Scholarship family-deal school. WRITTEN by workflow 1861452046 "Teacher Scholarship – Create Student Deal per Form Submission" (contact `student_school` → deal `school_name`, pipeline 918901819); READ by WF-01 (1858089740) and WF-03 (1859135906) notification emails. NOT used on charter pipelines (there `student_school` is the field). A 2026-09-02 RETIRE call was reversed the same day after the writer was found — do not archive without remapping those three workflows first. Relabeled in-portal 2026-09-02 to "Teacher Scholarship Student School" (Roman) so it cannot be mistaken for a charter field; internal name unchanged. |  |
| `should_this_deal_be_posted_to_a_slack_channel_` | Should this deal be posted to a Slack Channel? | custom_deal_properties | KEEPER: Slack routing flag |  |
| `slp_tutor_pay` | SLP Tutor Pay | tutor_info | Created with Monday-sync tutor batch 2025-11 — verify Used-in with aplus_contractor_pay |  |
| `start_of_tutoring_for_this_deal` | Start Date for Tutoring for this Deal | deal_activity | KEEPER: Deal service window start |  |
| `stripe_amount_paid` | Stripe Amount Paid | pilibos_program | KEEPER: Stripe payment truth (Pilibos flow) |  |
| `stripe_payment_intent` | Stripe Payment Intent | pilibos_program | KEEPER: Stripe payment truth |  |
| `stripe_session_id` | Stripe Session ID | pilibos_program | KEEPER: Stripe payment truth |  |
| `student_assessment_pdf_upload` | Student Assessment PDF upload | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `student_first_name` | Student First Name | dealinformation | KEEPER: po_inbox deal_property_map: student_first 【code: email, ops, registry.yml】 |  |
| `student_grade` | Student Grade | dealinformation | KEEPER: po_inbox deal_property_map: grade; also stamped on B2C deal create 【code: email, registry.yml】 |  |
| `student_grade_level` | Student Grade Level | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `student_last_name_if_diff_from_parent` | Student Last Name | scheduling_information | KEEPER: po_inbox deal_property_map: student_last 【code: email, ops, registry.yml】 |  |
| `student_school` | Student School | charter | KEEPER: po_inbox deal_property_map: school 【code: email, marketing, ops】 |  |
| `subjects_needing_support` | Subject(s) Needing Support | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `sunday_schedule_preference` | Sunday Schedule Preference | scheduling_information | KEEPER: Per-day schedule preference on deal |  |
| `teacher_form_submitted` | Teacher Form Submitted | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `teacher_has_nominated` | Teacher Has Nominated | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `teacher_of_record_email` | Teacher of Record Email | dealinformation | KEEPER: TOR on deal — Monday sync dependency; retire after Teachworks low-balance alert replaces Monday |  |
| `teacher_of_record_name` | Teacher of Record Name | dealinformation | KEEPER: TOR on deal — Monday sync dependency; retire after Teachworks low-balance alert replaces Monday 【code: email, ops】 |  |
| `teacher_scholarship_meeting_booked` | Teacher Scholarship Meeting Booked | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `teacher_scholarship_meeting_date` | Teacher Scholarship Meeting Date | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `thursday_schedule_preference` | Thursday Schedule Preference | scheduling_information | KEEPER: Per-day schedule preference on deal |  |
| `tor_first_name` | tor first name | charter | KEEPER: TOR on deal (Monday sync batch 2025-11); same retire-after-Monday flag |  |
| `tor_last_name` | tor last name | charter | KEEPER: TOR on deal (Monday sync batch 2025-11); same retire-after-Monday flag |  |
| `tuesday_schedule_preference` | Tuesday Schedule Preference | scheduling_information | KEEPER: Per-day schedule preference on deal |  |
| `tutor_email` | Tutor Email | tutor_info | KEEPER: Tutor match on deal (Monday sync) |  |
| `tutor_match` | Tutor Match | dealinformation | KEEPER: Tutor match on deal |  |
| `tutor_resignation_date` | tutor resignation date | tutor_info | Created with Monday-sync tutor batch 2025-11 |  |
| `unresponsive_from_stage` | Teacher Scholarship Unresponsive From Stage | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `was_a_po_submitted_for_this_submission` | Was a PO submitted for this submission | dealinformation | Teacher Scholarship Nomination program on deals (live, Jul-Aug 2026) |  |
| `wednesday_schedule_preference` | Wednesday Schedule Preference | scheduling_information | KEEPER: Per-day schedule preference on deal |  |
| `which_days_of_the_week_do_you_prefer_` | Which days of the week do you prefer? | scheduling_information | Scheduling form field (live) |  |

## STORAGE-ONLY (10)

Data preserved, nothing reads or writes them going forward. No archive proposed — they simply drop out of agent vocabulary.

| Internal name | Label | Current group | Rationale | Decision |
|---|---|---|---|---|
| `ip__ecomm_bridge__abandoned_cart_url` | Abandoned cart URL | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__ecomm_bridge__discount_amount` | Discount savings | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__ecomm_bridge__ecomm_synced` | Ecommerce deal | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__ecomm_bridge__order_number` | Order number | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__ecomm_bridge__shipment_ids` | Shipment IDs | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__ecomm_bridge__source_app_id` | Source app ID | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__ecomm_bridge__source_store_id` | Source store | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__ecomm_bridge__tax_amount` | Tax price | ip__ecomm_bridge__ecomm_bridge | Ecomm bridge app plumbing |  |
| `ip__sync_extension__external_source_account_id` | Source account ID | ip__sync_extension__sync_extension | Sync extension app plumbing |  |
| `ip__sync_extension__external_source_app_id` | Source app ID | ip__sync_extension__sync_extension | Sync extension app plumbing |  |

## RETIRE-CANDIDATE (14) — archive pass run 2026-08-10

On Roman's "go": every candidate was audited against 342 workflows (v3+v4), 214 lists, and calculated-property formulas; audit-clean ones were archived (reversible, 90-day restore). HubSpot's own PROPERTY_USAGE validation blocked anything still referenced by a FORM (forms API not scannable with the current token scope). BLOCKED rows need the referencing workflow/list/form cleaned up first; HOLD rows await the multi-child data-model decision.

| Internal name | Label | Current group | Fill count | Last def. update | Status (2026-08-10) | Rationale | Decision |
|---|---|---|---|---|---|---|---|
| `expected_1st_lesson_date` | Expected 1st Lesson Date | deal_activity | 574 | 2021-05-28 | BLOCKED — referenced by: wf3:Get Started Now - FORM SUBMISSION to Deal Create GOLD; wf4:Get Started Now - FORM SUBMISSION to Deal Create GOLD | Legacy 2021 deal_activity field |  |
| `first_name` | First Name | dealinformation | 2833 | 2021-04-08 | BLOCKED — referenced by: wf3:Contact to Deal Properties; wf4:Contact to Deal Properties; wf4:Pipeline is "Charter Schools", deal stage is "Continued - Ou; wf4:Pipeline is "Gold Tutoring - Renewal", deal stage is "New Re… | Contact data duplicated onto deals (2020-21 webhook era) |  |
| `home_city` | Home City | dealinformation | 1300 | 2020-07-31 | BLOCKED — in use by FORM(s); HubSpot refused delete. Detach/delete the form first. | Address on deal — belongs to contact |  |
| `home_street_address` | Home Street Address | dealinformation | 860 | 2020-07-31 | BLOCKED — in use by FORM(s); HubSpot refused delete. Detach/delete the form first. | Address on deal — belongs to contact |  |
| `home_zip` | Home Zip | dealinformation | 1072 | 2020-07-31 | BLOCKED — in use by FORM(s); HubSpot refused delete. Detach/delete the form first. | Address on deal — belongs to contact |  |
| `how_did_you_hear_about_us_` | How did you hear about us? | custom_deal_properties | 0 | 2022-06-01 | BLOCKED — referenced by: list:Burlo; list:Emliy; list:RBS; list:Referral… | Attribution on deal — contact-level field is the keeper |  |
| `is_the_student_preparing_for_the_non_sat_test_` | Is the student preparing for a NON SAT Test? | workflow_properties | 3726 | 2021-07-19 | BLOCKED — referenced by: wf3:Get Started Now - CAP FORM SUBMISSION to DEAL; wf3:Julia Cap Contact Workflow post consult; wf4:Get Started Now - CAP FORM SUBMISSION to DEAL; wf4:Julia Cap Contact Workflow post consult | Legacy 2021 workflow flag |  |
| `is_the_student_preparing_for_the_sat_` | Is the student preparing for the SAT? | workflow_properties | 3723 | 2021-07-19 | BLOCKED — referenced by: wf3:Get Started Now - CAP FORM SUBMISSION to DEAL; wf3:Julia Cap Contact Workflow post consult; wf4:Get Started Now - CAP FORM SUBMISSION to DEAL; wf4:Julia Cap Contact Workflow post consult | Legacy 2021 workflow flag |  |
| `last_name` | Last Name | dealinformation | 7232 | 2020-07-31 | BLOCKED — referenced by: wf3:Contact to Deal Properties; wf4:Contact to Deal Properties; wf4:Pipeline is "Charter Schools", deal stage is "Continued - Ou; wf4:Pipeline is "Charter Schools", deal stage is "Pre-Lesson"… | Contact data duplicated onto deals |  |
| `message` | Message | dealinformation | 112 | 2022-02-10 | BLOCKED — referenced by: wf3:Get Started Now - FORM SUBMISSION to Deal Create GOLD; wf3:New 20 off submission; wf3:SMS - Incoming 5th graders - Sent First week of August; wf3:SMS - New Year Check in… | Free-text from old lead webhook |  |
| `payment_received` | Payment received | dealinformation | 61 | 2021-06-09 | BLOCKED — referenced by: wf4:Pipeline is "Charter Schools", deal stage is "Payment Receiv | Legacy 2021 flag — Stripe/deal stages are truth now |  |
| `student_email_address` | Student Email Address | dealinformation | 57 | 2024-01-09 | **ARCHIVED 2026-08-10** (audit clean: 342 workflows, 214 lists, formulas; HubSpot usage-check passed) | Student email on deal — contact-level field is the keeper |  |
| `subscription_type` | Subscription Type | custom_deal_properties | 0 | 2023-01-03 | BLOCKED — in use by FORM(s); HubSpot refused delete. Detach/delete the form first. | Legacy 2023 field |  |
| `what_s_going_on_` | What's Going On? | dealinformation | 5119 | 2022-01-28 | BLOCKED — referenced by: wf4:Pipeline is "Charter Schools", deal stage is "Pre-Lesson"; wf4:Pipeline is "Gold Tutoring", deal stage is "Pre-Lesson"; wf4:Pipeline is "In-Person", deal stage is "Pre-Lesson"; wf4:Pipeline is "Online Summer Boost", deal stage is "Pre-Lesson | Old lead webhook capture — contact-level parent_concerns… is the live field |  |


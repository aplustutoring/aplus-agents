# Low-fill contact properties — review list (Roman, requested 2026-08-11)

Every LIVE custom contact property with **fewer than 150 contacts** holding a value (378 of 454 live custom properties). Grouped by current disposition so the signal is the middle buckets: KEEP-IN-PLACE / STORAGE-ONLY rows here are properties the consolidation kept that are nearly empty — tick ☑ anything you want moved to RETIRE. Keepers are listed FYI (low fill does not unmake a keeper — several are new-program or code-referenced fields).

| Bucket | Count |
|---|---|
| KEEPER (persona/master) | 22 |
| KEEP-IN-PLACE | 168 |
| STORAGE-ONLY | 112 |
| RETIRE-CANDIDATE (already proposed) | 52 |
| NEW (post-proposal, this week) | 4 |
| SYSTEM (excluded) | 20 |

## KEEPER (persona/master) (22)

| ☐ | Fills | Internal name | Label | Group | Note |
|---|---|---|---|---|---|
| ☐ | 0 | `parent_email` | Parent Email | contactinformation | code |
| ☐ | 0 | `parent_first_name` | Parent First Name | contactinformation |  |
| ☐ | 0 | `parent_last_name` | Parent Last Name | contactinformation | code |
| ☐ | 0 | `parent_phone_number` | Parent Phone Number | contactinformation |  |
| ☐ | 1 | `sunday_schedule_preference` | Sunday Schedule Preference | level-up_ilead |  |
| ☐ | 5 | `student_4_full_name` | Student 4 Full Name  | sibling | code |
| ☐ | 6 | `saturday_schedule_preference` | Saturday Schedule Preference | level-up_ilead |  |
| ☐ | 7 | `a_persona` | A+ PERSONA | master | code |
| ☐ | 9 | `completed_tutor_training` | Completed Tutor Training | new_tutors |  |
| ☐ | 15 | `teacher_email_address` | Teacher Email Address | contactinformation |  |
| ☐ | 35 | `degree_received` | Degree Received | new_tutors |  |
| ☐ | 35 | `university_attended` | University Attended | new_tutors |  |
| ☐ | 38 | `friday_schedule_preference` | Friday Schedule Preference | level-up_ilead |  |
| ☐ | 41 | `thursday_schedule_preference` | Thursday Schedule Preference  | level-up_ilead |  |
| ☐ | 41 | `tuesday_schedule_preference` | Tuesday Schedule Preference | level-up_ilead |  |
| ☐ | 42 | `wednesday_schedule_preference` | Wednesday Schedule Preference  | level-up_ilead |  |
| ☐ | 44 | `monday_schedule_preference` | Monday Schedule Preference  | level-up_ilead |  |
| ☐ | 57 | `student_3_full_name` | Student 3 Full Name | sibling | code |
| ☐ | 90 | `subject_need` | Subject Need | level-up_ilead | code |
| ☐ | 94 | `tutor_profile` | Tutor Profile | new_tutors |  |
| ☐ | 112 | `student_last_name_if_diff_from_parent` | Student Last Name | student | code |
| ☐ | 128 | `online_in_person_` | Online or In-Person | new_tutors |  |

## KEEP-IN-PLACE (168)

| ☐ | Fills | Internal name | Label | Group | Note |
|---|---|---|---|---|---|
| ☐ | 0 | `area_s__of_need` | Area(s) of Need | charter |  |
| ☐ | 0 | `booked_on_the_spot` | Booked on the Spot | contactinformation |  |
| ☐ | 0 | `calendar_link_sent` | Calendar Link Sent | contactinformation |  |
| ☐ | 0 | `call_held_date` | Call Held Date | contactinformation |  |
| ☐ | 0 | `call_scheduled_date` | Call Scheduled Date | contactinformation |  |
| ☐ | 0 | `callrail_lead_score` | CallRail Lead Score | analyticsinformation |  |
| ☐ | 0 | `create_date_not_unix` | Create Date Not Unix | pilibos_program |  |
| ☐ | 0 | `did_you_submit_a_purchase_order__po__to_a__tutoring_` | Did you submit a Purchase Order (PO) to A+ Tutoring? | contactinformation |  |
| ☐ | 0 | `duration` | Duration | analyticsinformation | code |
| ☐ | 0 | `family_contacted_date` | Family Contacted Date | contactinformation |  |
| ☐ | 0 | `final_decision_university_` | Final Decision University: | form_fields |  |
| ☐ | 0 | `for_el_learners__what_is_their_home_language_` | For EL learners, what is their home language? | contactinformation |  |
| ☐ | 0 | `form_capture_data` | Form Capture Data | analyticsinformation |  |
| ☐ | 0 | `form_sent_date` | Form Sent Date | contactinformation |  |
| ☐ | 0 | `formatted_duration` | Formatted Duration | analyticsinformation |  |
| ☐ | 0 | `gclid` | GCLID | analyticsinformation |  |
| ☐ | 0 | `handoff_date` | Handoff Date | contactinformation |  |
| ☐ | 0 | `how_many_students_are_you_nominating_` | How Many Students Are You Nominating? | contactinformation |  |
| ☐ | 0 | `lead_explanation` | Lead Explanation | analyticsinformation |  |
| ☐ | 0 | `lead_score` | Lead Score | analyticsinformation |  |
| ☐ | 0 | `lead_source__event` | Lead Source – Event | contactinformation |  |
| ☐ | 0 | `most_recent_call_sentiment` | Most recent call sentiment | analyticsinformation |  |
| ☐ | 0 | `nominating_teacher_name` | Nominating Teacher Name | contactinformation |  |
| ☐ | 0 | `nomination_form_completed` | Nomination Form Completed | contactinformation |  |
| ☐ | 0 | `nomination_form_sent` | Nomination Form Sent | contactinformation |  |
| ☐ | 0 | `nominations_received` | Nominations Received | contactinformation |  |
| ☐ | 0 | `outcome` | Outcome | contactinformation | code |
| ☐ | 0 | `pilibos_cb_practice_score_report` | College Board Practice Test Score Report — Contact Mirror | pilibos_program |  |
| ☐ | 0 | `pilibos_diagnostic_token` | Diagnostic Upload Token | pilibos_program |  |
| ☐ | 0 | `po_submitted_date` | PO Submitted Date | contactinformation |  |
| ☐ | 0 | `reason_lost` | Reason Lost | contactinformation |  |
| ☐ | 0 | `sources_of_data_that_point_to_the_need__check_all_that_apply_` | Sources of data that point to the need. Check all that apply | contactinformation |  |
| ☐ | 0 | `spotlight_lesson_notes_ai_summary` | Spotlight Lesson Notes AI Summary | spotlight |  |
| ☐ | 0 | `spotlight_tutoring_start_date` | Spotlight Tutoring Start Date | spotlight |  |
| ☐ | 0 | `stripe_amount_paid` | Stripe Amount Paid | pilibos_program |  |
| ☐ | 0 | `stripe_payment_intent` | Stripe Payment Intent | pilibos_program |  |
| ☐ | 0 | `stripe_session_id` | Stripe Session ID | pilibos_program |  |
| ☐ | 0 | `tags` | Tags | analyticsinformation | code |
| ☐ | 0 | `teacher_first_name` | Teacher First Name | contactinformation |  |
| ☐ | 0 | `teacher_last_name` | Teacher Last Name | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__parent_email` | Teacher Scholarship Nomination - Parent Email | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__parent_first_name` | Teacher Scholarship Nomination - Parent First Name | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__parent_last_name` | Teacher Scholarship Nomination - Parent Last Name | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__parent_phone_number` | Teacher Scholarship Nomination - Parent Phone Number | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_2__parent_email` | Teacher Scholarship Nomination - Student 2 - Parent Email | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_2__parent_first_name` | Teacher Scholarship Nomination - Student 2 - Parent First Na | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_2__parent_last_name` | Teacher Scholarship Nomination - Student 2 - Parent Last Nam | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_2__parent_phone_number` | Teacher Scholarship Nomination - Student 2 - Parent Phone Nu | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_2__student_first_name` | Teacher Scholarship Nomination - Student 2 - Student First N | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_2__student_grade_level` | Teacher Scholarship Nomination - Student 2 - Student Grade L | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_2__student_information_from_teacher` | Teacher Scholarship Nomination - Student 2 - Student Informa | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_2__student_last_name` | Teacher Scholarship Nomination - Student 2 - Student Last Na | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_2__subjects_needing_support` | Teacher Scholarship Nomination - Student 2 - Subject(s) Need | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_3__parent_email` | Teacher Scholarship Nomination - Student 3 - Parent Email | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_3__parent_first_name` | Teacher Scholarship Nomination - Student 3 - Parent First Na | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_3__parent_phone_number` | Teacher Scholarship Nomination - Student 3 - Parent Phone Nu | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_3__student_first_name` | Teacher Scholarship Nomination - Student 3 - Student First N | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_3__student_grade_level` | Teacher Scholarship Nomination - Student 3 - Student Grade L | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_3__student_information_from_teacher` | Teacher Scholarship Nomination - Student 3 - Student Informa | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_3__student_last_name` | Teacher Scholarship Nomination - Student 3 - Student Last Na | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_3__subjects_needing_support` | Teacher Scholarship Nomination - Student 3 - Subject(s) Need | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_3_parent_last_name` | Teacher Scholarship Nomination - Student 3 -Parent Last Name | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_first_name` | Teacher Scholarship Nomination - Student First Name | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__student_last_name` | Teacher Scholarship Nomination - Student Last Name | contactinformation |  |
| ☐ | 0 | `teacher_scholarship_nomination__yesno` | Teacher Scholarship Nomination - Yes/No | contactinformation |  |
| ☐ | 0 | `trial_start_date` | Trial Start Date | contactinformation |  |
| ☐ | 0 | `unresponsive_from_stage` | Unresponsive From Stage | contactinformation |  |
| ☐ | 0 | `voice_assist_caller_email_address` | Voice Assist caller email address | analyticsinformation |  |
| ☐ | 0 | `voice_assist_caller_name` | Voice Assist caller name | analyticsinformation |  |
| ☐ | 0 | `voice_assist_caller_preferred_phone_number` | Voice Assist caller preferred phone number | analyticsinformation |  |
| ☐ | 0 | `voice_assist_message_taken` | Voice Assist message taken | analyticsinformation |  |
| ☐ | 1 | `spotlight_call_ai_summary` | Spotlight Call AI Summary | spotlight |  |
| ☐ | 1 | `spotlight_content_link` | Spotlight Content Link | spotlight |  |
| ☐ | 1 | `spotlight_review_link` | Spotlight Review Link | spotlight |  |
| ☐ | 1 | `was_a_po_submitted_for_this_submission` | Was a PO submitted for this submission | contactinformation |  |
| ☐ | 2 | `meeting_outcome` | Meeting Outcome | contactinformation |  |
| ☐ | 2 | `teacher_scholarship_nomination__how_many_students_are_you_nominating` | Teacher Scholarship Nomination - How Many Students Are You N | contactinformation |  |
| ☐ | 2 | `teacher_scholarship_nomination__student_1__parent_email` | Teacher Scholarship Nomination - Student 1 - Parent Email | contactinformation |  |
| ☐ | 2 | `teacher_scholarship_nomination__student_1__parent_first_name` | Teacher Scholarship Nomination - Student 1 - Parent First Na | contactinformation |  |
| ☐ | 2 | `teacher_scholarship_nomination__student_1__parent_last_name` | Teacher Scholarship Nomination - Student 1 - Parent Last Nam | contactinformation |  |
| ☐ | 3 | `diagnostic_submitted_date` | Diagnostic Submitted Date | pilibos_program |  |
| ☐ | 3 | `nomination_status` | Nomination Status | contactinformation |  |
| ☐ | 3 | `pilibos_diagnostic_math_score` | Diagnostic Math Score | pilibos_program |  |
| ☐ | 3 | `pilibos_diagnostic_received` | Diagnostic Received | pilibos_program |  |
| ☐ | 3 | `pilibos_diagnostic_rw_score` | Diagnostic R+W Score | pilibos_program |  |
| ☐ | 3 | `pilibos_diagnostic_score_report` | Diagnostic Score Report | pilibos_program |  |
| ☐ | 3 | `spotlight_notes` | Spotlight Notes | spotlight |  |
| ☐ | 3 | `teacher_scholarship_nomination__student_1__parent_phone_number` | Teacher Scholarship Nomination - Student 1 - Parent Phone Nu | contactinformation |  |
| ☐ | 3 | `teacher_scholarship_nomination__student_1__student_first_name` | Teacher Scholarship Nomination - Student 1 - Student First N | contactinformation |  |
| ☐ | 3 | `teacher_scholarship_nomination__student_1__student_grade_level` | Teacher Scholarship Nomination - Student 1 - Student Grade L | contactinformation |  |
| ☐ | 3 | `teacher_scholarship_nomination__student_1__student_information_from_teacher` | Teacher Scholarship Nomination - Student 1 - Student Informa | contactinformation |  |
| ☐ | 3 | `teacher_scholarship_nomination__student_1__student_last_name` | Teacher Scholarship Nomination - Student 1 - Student Last Na | contactinformation |  |
| ☐ | 3 | `teacher_scholarship_nomination__student_1__subjects_needing_support` | Teacher Scholarship Nomination - Student 1 - Subject(s) Need | contactinformation |  |
| ☐ | 3 | `teacher_scholarship_nomination__teacher_first_name` | Teacher Scholarship Nomination - Teacher First Name | contactinformation |  |
| ☐ | 3 | `teacher_scholarship_nomination__teacher_last_name` | Teacher Scholarship Nomination - Teacher Last Name | contactinformation |  |
| ☐ | 4 | `last_keywords` | Last Keywords | analyticsinformation |  |
| ☐ | 6 | `sms_message` | SMS Message | analyticsinformation |  |
| ☐ | 7 | `pilibos_role` | Pilibos Role | pilibos_program |  |
| ☐ | 7 | `pilibos_upload_token` | Pilibos Upload Token | pilibos_program |  |
| ☐ | 8 | `home_language` | Home Language | contactinformation |  |
| ☐ | 8 | `pilibos_attend_afternoons` | Can Attend Afternoons (1 PM–4 PM) — Contact Mirror | pilibos_program |  |
| ☐ | 8 | `pilibos_attend_mornings` | Can Attend Mornings (9 AM–12 PM) — Contact Mirror | pilibos_program |  |
| ☐ | 8 | `pilibos_august_sat_acknowledged` | August 22 SAT Registration Acknowledged — Contact Mirror | pilibos_program |  |
| ☐ | 8 | `pilibos_payment_received` | Pilibos Payment Received | pilibos_program |  |
| ☐ | 8 | `pilibos_psat_score_report` | PSAT October 2025 Score Report — Contact Mirror | pilibos_program |  |
| ☐ | 8 | `pilibos_student_email` | Student Email — Contact Mirror | pilibos_program |  |
| ☐ | 8 | `pilibos_student_first_name` | Student First Name — Contact Mirror | pilibos_program | code |
| ☐ | 8 | `pilibos_student_last_name` | Student Last Name — Contact Mirror | pilibos_program |  |
| ☐ | 8 | `pilibos_student_phone` | Student Phone — Contact Mirror | pilibos_program |  |
| ☐ | 8 | `pilibos_summer_2026` | Pilibos Summer 2026 | pilibos_program |  |
| ☐ | 8 | `pilibos_terms_acknowledged` | Non-Refundable Terms Acknowledged — Contact Mirror | pilibos_program |  |
| ☐ | 8 | `pilibos_tier` | Program Tier — Contact Mirror | pilibos_program |  |
| ☐ | 8 | `summer_2020_availability` | Summer 2020 Availability | form_fields |  |
| ☐ | 9 | `grade_level` | Grade Level | contactinformation | code |
| ☐ | 13 | `spotlight_baseline_scores` | Spotlight Baseline Scores | spotlight |  |
| ☐ | 13 | `spotlight_review_status` | Spotlight Review Status | spotlight |  |
| ☐ | 14 | `spotlight_tor_call_complete` | Spotlight TOR Call Complete | spotlight |  |
| ☐ | 16 | `if__other___please_explain_` | If "other", please explain: | contactinformation |  |
| ☐ | 16 | `spotlight_current_scores` | Spotlight Current Scores | spotlight |  |
| ☐ | 18 | `if_the_student_has_an_iep_or_504_plan___please_give_us_a_brief_description_to_best_support_this_stu` | If the student has an IEP or 504 plan - please give us a bri | contactinformation |  |
| ☐ | 18 | `spotlight_gift_card_sent` | Spotlight Gift Card Sent | spotlight |  |
| ☐ | 19 | `sat_or_act` | Which Exam are you taking? (SAT or ACT) | form_fields |  |
| ☐ | 20 | `spotlight_parent_call_complete` | Spotlight Parent Call Complete | spotlight |  |
| ☐ | 23 | `spotlight_parent_additional_comments` | Spotlight - Additional Comments | contactinformation |  |
| ☐ | 24 | `business_license_on_file` | Business License on File | new_tutors |  |
| ☐ | 24 | `spotlight_gift_card_preference` | Spotlight Gift Card Preference | spotlight |  |
| ☐ | 25 | `area_s__of_need__check_all_that_apply_` | Area(s) of Need. Check all that apply. | contactinformation |  |
| ☐ | 30 | `spotlight_assessment_type` | Spotlight Assessment Type | spotlight |  |
| ☐ | 30 | `spotlight_before_experience` | Spotlight Before Experience | spotlight |  |
| ☐ | 30 | `spotlight_consent` | Spotlight Consent | spotlight |  |
| ☐ | 30 | `spotlight_grade_level` | Spotlight Grade Level | spotlight |  |
| ☐ | 30 | `spotlight_growth_areas` | Spotlight Growth Areas | spotlight |  |
| ☐ | 30 | `spotlight_has_before_scores` | Spotlight Has Before Scores | spotlight |  |
| ☐ | 30 | `spotlight_has_current_scores` | Spotlight Has Current Scores | spotlight |  |
| ☐ | 30 | `spotlight_positive_changes` | Spotlight Positive Changes | spotlight |  |
| ☐ | 30 | `spotlight_scheduling_rating` | Spotlight Scheduling Rating | spotlight |  |
| ☐ | 30 | `spotlight_school_recognition` | Spotlight School Recognition | spotlight |  |
| ☐ | 30 | `spotlight_session_notes_rating` | Spotlight Session Notes Rating | spotlight |  |
| ☐ | 30 | `spotlight_subjects` | Spotlight Subjects | spotlight |  |
| ☐ | 30 | `spotlight_tutor_feedback` | Spotlight Tutor Feedback | spotlight |  |
| ☐ | 32 | `is_the_online_tutor_ready_for_onboarding` | Is the Online Tutor Ready for Onboarding | new_tutors |  |
| ☐ | 34 | `please_attach_a_pdf_of_the_student_s_most_recent_map_score_data__if_you_do_not_use_map__please_uplo` | Student Assessment PDF upload | contactinformation |  |
| ☐ | 38 | `intended_major_or_area_of_study` | Intended Major or Area of Study | form_fields |  |
| ☐ | 38 | `top_3_dream_colleges` | Top 3 Dream Colleges | form_fields |  |
| ☐ | 38 | `transcripts` | Transcripts | form_fields | code |
| ☐ | 38 | `what_are_your_top_3_extracurricular_activities` | What are your top 3 Extracurricular Activities | form_fields |  |
| ☐ | 40 | `gpa` | GPA | form_fields |  |
| ☐ | 49 | `please_share_anything_specific__if_science__what_science___etc__` | Please share anything specific (if science, what science - e | contactinformation |  |
| ☐ | 52 | `area_of_need` | Area of Need | contactinformation |  |
| ☐ | 52 | `is_the_learner_designated_el_` | Is the learner designated EL? | contactinformation |  |
| ☐ | 52 | `please_share_any_unique_needs_we_should_be_made_aware_of____examples__accommodations__modifications` | Please share any unique needs we should be made aware of?  ( | contactinformation |  |
| ☐ | 52 | `source_s__of_data_that_point_to_the_need__check_all_that_apply_` | Source(s) of data that point to the need. Check all that app | contactinformation |  |
| ☐ | 52 | `what_is_the_student_s_measurable__academic_goal_for_the_requested_hours_of_tutoring_` | What is the student's measurable, academic goal for the requ | contactinformation |  |
| ☐ | 53 | `tutoring_frequency` | Tutoring Frequency | level-up_ilead |  |
| ☐ | 53 | `when_would_you_like_the_tutoring_to_start` | When would you like the tutoring to start | level-up_ilead |  |
| ☐ | 68 | `spotlight_tutor_email` | Spotlight Tutor Email | spotlight |  |
| ☐ | 69 | `spotlight_nomination_date` | Spotlight Nomination Date | spotlight |  |
| ☐ | 69 | `spotlight_tor_email` | Spotlight TOR Email | spotlight |  |
| ☐ | 69 | `spotlight_tor_name` | Spotlight TOR Full Name | spotlight |  |
| ☐ | 69 | `spotlight_tutor_name` | Spotlight Tutor Name | spotlight |  |
| ☐ | 71 | `spotlight_school_name` | Spotlight School Name | spotlight |  |
| ☐ | 71 | `spotlight_student_first_name` | Spotlight Student First Name | spotlight | code |
| ☐ | 74 | `spotlight_status` | Spotlight Status | spotlight |  |
| ☐ | 77 | `iep_504_` | IEP/504? | form_fields |  |
| ☐ | 91 | `uploaded_diagnostic` | Uploaded Diagnostic | contactinformation |  |
| ☐ | 97 | `contact_level_deal_stage` | Contact Level Deal Stage | contactinformation |  |
| ☐ | 103 | `which_days_of_the_week_do_you_prefer_` | Which days of the week do you prefer? | level-up_ilead |  |
| ☐ | 105 | `student_cell_phone` | Student Cell Phone | form_fields |  |

## STORAGE-ONLY (112)

| ☐ | Fills | Internal name | Label | Group | Note |
|---|---|---|---|---|---|
| ☐ | 0 | `abandoned_cart_recovery_workflow_conversion` | Abandoned Cart Recovery Workflow Conversion | roi_tracking |  |
| ☐ | 0 | `abandoned_cart_recovery_workflow_conversion_amount` | Abandoned Cart Recovery Workflow Conversion Amount | roi_tracking |  |
| ☐ | 0 | `abandoned_cart_recovery_workflow_conversion_date` | Abandoned Cart Recovery Workflow Conversion Date | roi_tracking |  |
| ☐ | 0 | `abandoned_cart_recovery_workflow_start_date` | Abandoned Cart Recovery Workflow Start Date | roi_tracking |  |
| ☐ | 0 | `account_creation_date` | Account Creation Date | rfm_fields |  |
| ☐ | 0 | `current_roi_campaign` | Current ROI Campaign | roi_tracking |  |
| ☐ | 0 | `customer_reengagement_workflow_conversion` | Customer Reengagement Workflow Conversion | roi_tracking |  |
| ☐ | 0 | `customer_reengagement_workflow_conversion_amount` | Customer Reengagement Workflow Conversion Amount | roi_tracking |  |
| ☐ | 0 | `customer_reengagement_workflow_conversion_date` | Customer Reengagement Workflow Conversion Date | roi_tracking |  |
| ☐ | 0 | `customer_reengagement_workflow_start_date` | Customer Reengagement Workflow Start Date | roi_tracking |  |
| ☐ | 0 | `customer_rewards_workflow_conversion` | Customer Rewards Workflow Conversion | roi_tracking |  |
| ☐ | 0 | `customer_rewards_workflow_conversion_amount` | Customer Rewards Workflow Conversion Amount | roi_tracking |  |
| ☐ | 0 | `customer_rewards_workflow_conversion_date` | Customer Rewards Workflow Conversion Date | roi_tracking |  |
| ☐ | 0 | `customer_rewards_workflow_start_date` | Customer Rewards Workflow Start Date | roi_tracking |  |
| ☐ | 0 | `last_order_shipment_date` | Last Order Shipment Date | order |  |
| ☐ | 0 | `last_order_tracking_number` | Last Order Tracking Number | order |  |
| ☐ | 0 | `last_order_tracking_url` | Last Order Tracking URL | order |  |
| ☐ | 0 | `last_products_bought_product_3_image_url` | Last Products Bought Product 3 Image URL | last_products_bought |  |
| ☐ | 0 | `last_products_bought_product_3_name` | Last Products Bought Product 3 Name | last_products_bought |  |
| ☐ | 0 | `last_products_bought_product_3_price` | Last Products Bought Product 3 Price | last_products_bought |  |
| ☐ | 0 | `last_products_bought_product_3_url` | Last Products Bought Product 3 Url | last_products_bought |  |
| ☐ | 0 | `mql_capture_nurture_conversion_conversion` | MQL Capture, Nurture & Conversion Conversion | roi_tracking |  |
| ☐ | 0 | `mql_capture_nurture_conversion_conversion_amount` | MQL Capture, Nurture & Conversion Conversion Amount | roi_tracking |  |
| ☐ | 0 | `mql_capture_nurture_conversion_conversion_date` | MQL Capture, Nurture & Conversion Conversion Date | roi_tracking |  |
| ☐ | 0 | `mql_capture_nurture_conversion_start_date` | MQL Capture, Nurture & Conversion Start date | roi_tracking |  |
| ☐ | 0 | `new_customer_workflow_conversion` | New Customer Workflow Conversion | roi_tracking |  |
| ☐ | 0 | `new_customer_workflow_conversion_amount` | New Customer Workflow Conversion Amount | roi_tracking |  |
| ☐ | 0 | `new_customer_workflow_conversion_date` | New Customer Workflow Conversion Date | roi_tracking |  |
| ☐ | 0 | `new_customer_workflow_start_date` | New Customer Workflow Start Date | roi_tracking |  |
| ☐ | 0 | `promo_code` | Promo Code | ip__ecomm_bridge__ecomm_bridge |  |
| ☐ | 0 | `second_purchase_workflow_conversion` | Second Purchase Workflow Conversion | roi_tracking |  |
| ☐ | 0 | `second_purchase_workflow_conversion_amount` | Second Purchase Workflow Conversion Amount | roi_tracking |  |
| ☐ | 0 | `second_purchase_workflow_conversion_date` | Second Purchase Workflow Conversion Date | roi_tracking |  |
| ☐ | 0 | `second_purchase_workflow_start_date` | Second Purchase Workflow Start Date | roi_tracking |  |
| ☐ | 0 | `shopping_cart_customer_id` | Shopping Cart ID | customer_group |  |
| ☐ | 0 | `third_purchase_workflow_conversion` | Third Purchase Workflow Conversion | roi_tracking |  |
| ☐ | 0 | `third_purchase_workflow_conversion_amount` | Third Purchase Workflow Conversion Amount | roi_tracking |  |
| ☐ | 0 | `third_purchase_workflow_conversion_date` | Third Purchase Workflow Conversion Date | roi_tracking |  |
| ☐ | 0 | `third_purchase_workflow_start_date` | Third Purchase Workflow Start Date | roi_tracking |  |
| ☐ | 1 | `package_preference` | Package Preference | integrations |  |
| ☐ | 2 | `abandoned_cart_date` | Abandoned Cart Date | abandoned_cart |  |
| ☐ | 2 | `abandoned_cart_products` | Abandoned Cart Products | abandoned_cart |  |
| ☐ | 2 | `abandoned_cart_products_categories` | Abandoned Cart Products Categories | abandoned_cart |  |
| ☐ | 2 | `abandoned_cart_products_html` | Abandoned Cart Products HTML | abandoned_cart |  |
| ☐ | 2 | `abandoned_cart_products_skus` | Abandoned Cart Products SKUs | abandoned_cart |  |
| ☐ | 2 | `abandoned_cart_url` | Abandoned Cart URL | abandoned_cart |  |
| ☐ | 2 | `last_products_bought_product_2_image_url` | Last Products Bought Product 2 Image URL | last_products_bought |  |
| ☐ | 2 | `last_products_bought_product_2_name` | Last Products Bought Product 2 Name | last_products_bought |  |
| ☐ | 2 | `last_products_bought_product_2_price` | Last Products Bought Product 2 Price | last_products_bought |  |
| ☐ | 2 | `last_products_bought_product_2_url` | Last Products Bought Product 2 Url | last_products_bought |  |
| ☐ | 3 | `please_provide_any_additional_comments_or_suggestions_you_have_about_your_experience_with_a__tutori` | Please provide any additional comments or suggestions you ha | contactinformation |  |
| ☐ | 6 | `how_satisfied_are_you_with_the_level_of_communication_you_have_received_from_the_a__tutoring_and_yo` | How satisfied are you with the level of communication you ha | contactinformation |  |
| ☐ | 6 | `how_well_did_your_tutor_connect_with_the_student_on_a_personal_level_to_create_a_nurturing_and_effe` | How well did your tutor connect with the student on a person | contactinformation |  |
| ☐ | 6 | `shipping_address_line_2` | Shipping Address Line 2 | shopping_cart_fields |  |
| ☐ | 6 | `to_what_extent_have_you_noticed_an_improvement_in_the_student_s_academic_performance_since_beginnin` | To what extent have you noticed an improvement in the studen | contactinformation |  |
| ☐ | 7 | `billing_address_line_2` | Billing Address Line 2 | shopping_cart_fields |  |
| ☐ | 18 | `customer_new_order` | Customer New Order | roi_tracking |  |
| ☐ | 18 | `monetary_rating` | Monetary Rating | rfm_fields |  |
| ☐ | 18 | `order_frequency_rating` | Order Frequency Rating | rfm_fields |  |
| ☐ | 18 | `order_recency_rating` | Order Recency Rating | rfm_fields |  |
| ☐ | 19 | `categories_bought` | Categories Bought | categories_bought |  |
| ☐ | 19 | `last_categories_bought` | Last Categories Bought | categories_bought |  |
| ☐ | 19 | `last_product_bought` | Last Product Bought | last_products_bought |  |
| ☐ | 19 | `last_product_types_bought` | Last Product Types Bought | last_products_bought |  |
| ☐ | 19 | `last_products_bought` | Last Products Bought | last_products_bought |  |
| ☐ | 19 | `last_products_bought_html` | Last Products Bought HTML | last_products_bought |  |
| ☐ | 19 | `last_skus_bought` | Last SKUs Bought | skus_bought |  |
| ☐ | 19 | `product_types_bought` | Product Types Bought | last_products_bought |  |
| ☐ | 19 | `products_bought` | Products Bought | last_products_bought |  |
| ☐ | 19 | `skus_bought` | SKUs Bought | skus_bought |  |
| ☐ | 20 | `abandoned_cart_counter` | Abandoned Cart Counter | abandoned_cart |  |
| ☐ | 20 | `abandoned_cart_subtotal` | Abandoned Cart Subtotal | abandoned_cart |  |
| ☐ | 20 | `abandoned_cart_tax_value` | Abandoned Cart Tax Value | abandoned_cart |  |
| ☐ | 20 | `abandoned_cart_total_value` | Abandoned Cart Total Value | abandoned_cart |  |
| ☐ | 20 | `current_abandoned_cart` | Current Abandoned Cart | abandoned_cart |  |
| ☐ | 21 | `shipping_address_line_1` | Shipping Address Line 1 | shopping_cart_fields |  |
| ☐ | 21 | `shipping_city` | Shipping City | shopping_cart_fields |  |
| ☐ | 21 | `shipping_postal_code` | Shipping Postal Code | shopping_cart_fields |  |
| ☐ | 22 | `shipping_country` | Shipping Country | shopping_cart_fields |  |
| ☐ | 22 | `shipping_state` | Shipping State | shopping_cart_fields |  |
| ☐ | 23 | `average_days_between_orders` | Average Days Between Orders | rfm_fields |  |
| ☐ | 23 | `average_order_value` | Average Order Value | rfm_fields |  |
| ☐ | 23 | `billing_address_line_1` | Billing Address Line 1 | shopping_cart_fields |  |
| ☐ | 23 | `billing_postal_code` | Billing Postal Code | shopping_cart_fields |  |
| ☐ | 23 | `customer_group` | Customer Group/ User role | unused_properties |  |
| ☐ | 23 | `first_order_date` | First Order Date | rfm_fields |  |
| ☐ | 23 | `first_order_value` | First Order Value | rfm_fields |  |
| ☐ | 23 | `ip__ecomm_bridge__ecomm_synced` | Ecommerce contact | ip__ecomm_bridge__ecomm_bridge |  |
| ☐ | 23 | `ip__ecomm_bridge__source_app_id` | Source app ID | ip__ecomm_bridge__ecomm_bridge |  |
| ☐ | 23 | `ip__ecomm_bridge__source_store_id` | Source store | ip__ecomm_bridge__ecomm_bridge |  |
| ☐ | 23 | `last_order_currency` | Last Order Currency | order |  |
| ☐ | 23 | `last_order_date` | Last Order Date | rfm_fields |  |
| ☐ | 23 | `last_order_fulfillment_status` | Last Order Fulfillment Status | order |  |
| ☐ | 23 | `last_order_order_number` | Last Order Number | order |  |
| ☐ | 23 | `last_order_status` | Last Order Status | order |  |
| ☐ | 23 | `last_order_value` | Last Order Value | rfm_fields |  |
| ☐ | 23 | `last_products_bought_product_1_image_url` | Last Products Bought Product 1 Image URL | last_products_bought |  |
| ☐ | 23 | `last_products_bought_product_1_name` | Last Products Bought Product 1 Name | last_products_bought |  |
| ☐ | 23 | `last_products_bought_product_1_price` | Last Products Bought Product 1 Price | last_products_bought |  |
| ☐ | 23 | `last_products_bought_product_1_url` | Last Products Bought Product 1 Url | last_products_bought |  |
| ☐ | 23 | `last_total_number_of_products_bought` | Last Total Number Of Products Bought | last_products_bought |  |
| ☐ | 23 | `newsletter_subscription` | Accepts Marketing | unused_properties |  |
| ☐ | 23 | `total_number_of_current_orders` | Total Number of Current Orders | order |  |
| ☐ | 23 | `total_number_of_orders` | Total Number of Orders | rfm_fields |  |
| ☐ | 23 | `total_number_of_products_bought` | Total Number Of Products Bought | last_products_bought |  |
| ☐ | 23 | `total_value_of_orders` | Total Value of Orders | rfm_fields |  |
| ☐ | 24 | `billing_city` | Billing City | shopping_cart_fields |  |
| ☐ | 24 | `billing_country` | Billing Country | shopping_cart_fields |  |
| ☐ | 24 | `billing_state` | Billing State | shopping_cart_fields |  |
| ☐ | 40 | `case_worker_phone_number` | Case Worker Phone Number | child_and_family_guidance |  |
| ☐ | 43 | `case_worker_email_address` | Case Worker Email Address | child_and_family_guidance |  |
| ☐ | 43 | `case_worker_full_name` | Case Worker Full Name | child_and_family_guidance |  |

## RETIRE-CANDIDATE (already proposed) (52)

| ☐ | Fills | Internal name | Label | Group | Note |
|---|---|---|---|---|---|
| ☐ | 0 | `are_missing_assignments_a_concern` | Are missing assignments a concern? | lead_ads | BLOCKED |
| ☐ | 0 | `date_for_first_free_lessons` | Date For First Free Lessons | date_properties | BLOCKED |
| ☐ | 0 | `date_of_tutoring_session_for_trial` | Date of Tutoring Session for Trial | contactinformation | BLOCKED |
| ☐ | 0 | `day_preference` | Day Preference | contactinformation | BLOCKED |
| ☐ | 0 | `if_you_have_taken_the_myers_briggs_personality_test__what_is_your_personality_type__4_letters_` | If you have taken the Myers-Briggs Personality Test, what is | new_tutors | BLOCKED |
| ☐ | 0 | `other_subject` | Other Subject | contactinformation | BLOCKED |
| ☐ | 0 | `subject_preference` | Subject Preference | contactinformation | BLOCKED |
| ☐ | 0 | `time` | Time | contactinformation | BLOCKED |
| ☐ | 0 | `type_of_enrollment` | Type of Enrollment | conversioninformation | BLOCKED |
| ☐ | 0 | `when_would_you_like_the_first_lesson` | When would you like the first lesson | contactinformation | BLOCKED |
| ☐ | 1 | `additional_note` | Additional note | contactinformation | BLOCKED |
| ☐ | 1 | `ap_subjects` | Which AP Subjects are you interested in? | unused_properties | BLOCKED |
| ☐ | 1 | `do_you_have_a_college_list_created_` | Do you have a college list created? | unused_properties | BLOCKED |
| ☐ | 2 | `english_subjects` | English Subjects | unused_properties | BLOCKED |
| ☐ | 2 | `lead_ad_prop0` | What grade is your child in - lead ad | lead_ads | BLOCKED |
| ☐ | 2 | `student_4_school` | Student 4 School | sibling | HOLD |
| ☐ | 3 | `college_test_prep` | Which Test Are You Leaning Towards Taking? | unused_properties | BLOCKED |
| ☐ | 3 | `date_to_stop_lessons_for_summer_update___schedule_update` | Date To Stop Lessons for Summer Update - Schedule Update | date_properties | BLOCKED |
| ☐ | 3 | `science_subjects` | Science Subjects | unused_properties | BLOCKED |
| ☐ | 4 | `optional__please_attach_a_pdf_of_the_student_s_most_up_to_date_iep_or_504_plan_` | Optional: Please attach a PDF of the student's most up to da | contactinformation | BLOCKED |
| ☐ | 4 | `student_3` | Student 3 | sibling | HOLD |
| ☐ | 6 | `when_can_we_reach_out_to_you_to_resume_` | When can we reach out to you to resume? Schedule Update | date_properties | BLOCKED |
| ☐ | 7 | `assessment_attended___in_house` | Assessment Attended - In House | customer_group | BLOCKED |
| ☐ | 7 | `assessment_graded___in_house` | Assessment Graded - In House | customer_group | BLOCKED |
| ☐ | 8 | `date_to_start_customer_provided` | Date To Start New Schedule - Summer Update | date_properties | BLOCKED |
| ☐ | 8 | `has_bonus_been_paid_out_` | Has Bonus Been Paid Out? | customer_group | BLOCKED |
| ☐ | 8 | `what_math_is_your_child_currently_working_on_` | What Math is Your Child Currently Working On? | unused_properties | BLOCKED |
| ☐ | 9 | `do_you_want_to_update_your_tutoring_schedule_` | Do you want to update your tutoring schedule? | customer_group | BLOCKED |
| ☐ | 9 | `what_grade_is_your_child_in` | Student Grade - FB | lead_ads | BLOCKED |
| ☐ | 10 | `middle_school_subjects` | Middle School Subjects | unused_properties | BLOCKED |
| ☐ | 12 | `have_you_taken_the_sat_or_act_already_` | Have you taken the SAT or ACT before? | unused_properties | BLOCKED |
| ☐ | 13 | `high_school_subjects` | High School Subjects | unused_properties | BLOCKED |
| ☐ | 20 | `student_3_school` | Student 3 School   | sibling | HOLD |
| ☐ | 21 | `do_you_want_your_student_to_receive_email_notifications_for_lesson_reminders_` | Do you want your student to receive email notifications for  | customer_group | BLOCKED |
| ☐ | 23 | `name_of_primary_contact_for_your_pod` | Name of Primary Contact for your pod | contactinformation | BLOCKED |
| ☐ | 27 | `left_a_review_` | Left a review? | customer_group | BLOCKED |
| ☐ | 30 | `tutor_referral___referred_by___email` | Tutor Referral - Referred By - Email  | new_tutors | BLOCKED |
| ☐ | 34 | `have_missing_assignments_been_an_issue_` | Have missing assignments been an issue? | unused_properties | BLOCKED |
| ☐ | 34 | `tutoring_plan` | Tutoring Plan | unused_properties | BLOCKED |
| ☐ | 36 | `decision_day` | Decision Day | customer_group | BLOCKED |
| ☐ | 37 | `how_many_students_will_be_in_your_small_learning_pod_` | How many students will be in your small learning pod? | unused_properties | BLOCKED |
| ☐ | 39 | `has_your_child_worked_with_a_tutor_before_` | Has your child worked with a tutor before? | unused_properties | BLOCKED |
| ☐ | 43 | `tutor_referral___referred_by___name` | Tutor Referral - Referred by - Name  | new_tutors | BLOCKED |
| ☐ | 44 | `ready_to_start_date` | Get Started Form Only - Pods | date_properties | BLOCKED |
| ☐ | 52 | `actively_counseling` | Actively Counseling | customer_group | BLOCKED |
| ☐ | 52 | `is_there_anything_specific_that_you_would_like_the_student_to_be_working_on_with_the_tutor_` | Is there anything specific that you would like the student t | contactinformation | BLOCKED |
| ☐ | 54 | `referral___referred_by___email` | Referral - Referred By - Email | referral_program | BLOCKED |
| ☐ | 57 | `referral___referred_by___name` | Referral - Referred by - Name | referral_program | BLOCKED |
| ☐ | 68 | `sync_to_teachworks_cap` | Sync to TeachWorks CAP | contactinformation | BLOCKED |
| ☐ | 77 | `assessment_received` | Assessment Graded - Remote | customer_group | BLOCKED |
| ☐ | 107 | `avatar` | Avatar | customer_group | BLOCKED |
| ☐ | 115 | `asked_for_a_review_` | Asked for a review? | customer_group | BLOCKED |

## NEW (post-proposal, this week) (4)

| ☐ | Fills | Internal name | Label | Group | Note |
|---|---|---|---|---|---|
| ☐ | 0 | `aplus_booth_delivery` | Booth Photo Delivery | events |  |
| ☐ | 0 | `aplus_booth_goal` | Booth Photo Banner | events |  |
| ☐ | 0 | `aplus_event_tag` | Event Tag | events |  |
| ☐ | 0 | `aplus_marketing_consent` | Booth Marketing Consent | events |  |

## SYSTEM (excluded) (20)

| ☐ | Fills | Internal name | Label | Group | Note |
|---|---|---|---|---|---|
| ☐ | 0 | `initial_zoom_webinar_attendance_average_duration` | Total attendance duration percentage before Attendance API m | zoom |  |
| ☐ | 0 | `jc_has_responded` | JustCall Text Response | contactinformation |  |
| ☐ | 0 | `jc_inbound_time` | Last Inbound Call (JC) | contactinformation |  |
| ☐ | 0 | `jc_incoming_call_status` | Last Incoming Call Status | contactinformation |  |
| ☐ | 0 | `jc_incoming_sms_count` | Incoming text messages count | contactinformation |  |
| ☐ | 0 | `jc_incoming_sms_time` | Incoming Text Time | contactinformation |  |
| ☐ | 0 | `jc_last_call_disposition` | Last Call Disposition (JustCall) | contactinformation |  |
| ☐ | 0 | `jc_last_call_disposition_sd` | Last Call Disposition (SalesDialer) | contactinformation |  |
| ☐ | 0 | `jc_last_call_status` | JC Last Call Status | contactinformation |  |
| ☐ | 0 | `jc_outbound_time` | Last Outbound Call (JC) | contactinformation |  |
| ☐ | 0 | `jc_sms_body` | JustCall SMS Text | contactinformation |  |
| ☐ | 0 | `jc_sms_opt_in` | JustCall SMS Opt In | contactinformation |  |
| ☐ | 0 | `latest_call` | Last Call (JC) | contactinformation |  |
| ☐ | 0 | `zoom_webinar_attendance_average_duration` | Average Zoom webinar attendance duration | zoom |  |
| ☐ | 0 | `zoom_webinar_attendance_count` | Total number of Zoom webinars attended | zoom |  |
| ☐ | 0 | `zoom_webinar_joinlink` | Last registered Zoom webinar | zoom |  |
| ☐ | 0 | `zoom_webinar_registration_count` | Total number of Zoom webinar registrations | zoom |  |
| ☐ | 2 | `jc_sms_optout` | JustCall SMS Optout | contactinformation |  |
| ☐ | 53 | `jc_last_call_outcome` | Last Call Outcome | contactinformation |  |
| ☐ | 134 | `jc_missed_time` | Last Missed Call (JC) | contactinformation |  |

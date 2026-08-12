# Automation & form purge — proposal (unblocks the 78 blocked retire candidates)

**Status: PROPOSAL — nothing here has been executed.** Roman approves; execution then follows the
2026-07-31 purge pattern: JSON backup of every workflow into the repo -> disable -> delete after a
quiet window. Lists are exported before deletion. Then the archive pass re-runs.

Why this exists: the 2026-08-10 archive pass retired 30 properties but 78 candidates were blocked
by live references — 35 by workflows/lists (scanned), 43 by forms (HubSpot's delete-time check).
Retiring the properties requires retiring or editing what references them, in this order.

## Summary

| Verdict | Count |
|---|---|
| DELETE (dead program / dated blast / splinter list) | 25 |
| EDIT (live automation — remove only the dead-property reference) | 43 |
| KEEP (confirmed live — Roman 2026-08-11) | 3 |
| ARCHIVED 2026-08-11 (QuickBooks refs, on Roman's order) | 2 |
| VERIFY (needs a human call before anything) | 14 |
| **Referencing automations total** | **87** |
| Blocking forms (IDs below — names need the forms scope) | 43 |

**High-risk callouts (read these three first):**
1. ~~`Non Charter/A+ Sync to TW`~~ **RESOLVED (Roman 2026-08-11): KEEP.** This is the LIVE
   path putting Gold and Free Trial deals into A+ Teachworks — deal_sync covers charter POs
   only. `sync_to_teachworks_` (A+/Gold+FreeTrial) and `sync_to_teachworks_slp` (In-Person)
   are live automation triggers, reclassified KEEP-IN-PLACE; only `sync_to_teachworks_cap`
   still retires (with the CAP flows).
2. **`Contact to Deal Properties` + the SMS stage flows** — deal `first_name`/`last_name`/
   `message`/`what_s_going_on_` are dead as *data* but live as *SMS template tokens*. The swap
   (deal tokens -> contact tokens) has to land before those four deal properties can retire.
3. **QBO — RESOLVED context (Roman 2026-08-11): there is NO QBO automation.** Kath marks
   invoices in Teachworks, Claude cowork records payments in Teachworks, and QBO is synced
   manually. The `Ready for Onboarding to QBO` list + `Is the online tutor ready for
   onboarding` flow was read as the manual tutor-onboarding queue — then Roman ordered
   "archive all quickbooks references" (2026-08-11): the `Quickbooks` workflow (323730202)
   and the `Ready for Onboarding to QBO` list (1176) are DELETED, backups in
   `ops/fleet-health/audit/backups/2026-08-11-quickbooks/`. The onboarding FLOW itself
   (not QBO-named) still stands with its two properties — in the low-fill review list.

## Referencing workflows & lists (87)

"ON" = enabled in the portal today. Blocks = the retire candidates each one references
(`c:` = contact property, `d:` = deal property).

**Accuracy caveat:** this scan is text-based. For generic names (`first_name`, `last_name`,
`message`, `time`, `full_name`, `schedule_preference`, and `how_did_you_hear_about_us_` which
exists on BOTH objects), a match may be the CONTACT keeper of the same name, or even a plain
JSON key inside the workflow definition — not the retire candidate. Execution step 0 resolves
this authoritatively.

| Name | Kind | Enabled | Blocks (retire candidates) | Verdict | Rationale |
|---|---|---|---|---|---|
| $100 - REFERRAL PROGRAM NEW FAMILIES | workflow | ON | `c:referral___referred_by___name`, `d:how_did_you_hear_about_us_` | **VERIFY** | Referral program may be live (referral_name is a keeper) — these reference the old referred_by fields; if program is live, EDIT to drop the dead fields |
| Actively Tutoring - Yes | list | — | `c:actively_tutoring` | **VERIFY** | Segment list — actively_tutoring flag is set by live stage engine; if any marketing email/report uses this list, keep the flag |
| Ask for Reviews | list | — | `c:actively_tutoring`, `c:asked_for_a_review_` | **VERIFY** | Review-ask list — if review asks now run through Spotlight, DELETE |
| Avatar to Persona | workflow | ON | `c:avatar` | **DELETE** | Superseded by a_persona (#AP024) — the old avatar mapping |
| Bonus Paid | list | — | `c:has_bonus_been_paid_out_` | **DELETE** | Stale ops list (has_bonus_been_paid_out_) |
| Burlo | list | — | `d:how_did_you_hear_about_us_` | **DELETE** | Attribution splinter list off the cloned how-did-you-hear dup |
| Business License on File | list | — | `c:business_license_on_file` | **KEEP** | Tutor-compliance queue alongside the QBO onboarding pair (Roman 2026-08-11 context) |
| Charter Traditional SMS New Deal Created  | workflow | ON | `c:schedule_preference` | **EDIT** | Live new-deal SMS — templates use deal message/what_s_going_on_/first_name; swap tokens to contact/live fields, keep the workflow |
| Contact to Deal Properties | workflow | ON | `d:first_name`, `d:last_name` | **VERIFY** | Live copier feeding deal first_name/last_name — SMS flows template off them; replace tokens with contact properties, then delete, or keep the stack as-is |
| Copy Deal Start Date Property to Contact Property | workflow | ON | `c:start_date_for_tutoring_for_this_deal` | **VERIFY** | THE writer of contact start_date_for_tutoring_for_this_deal — delete both together or keep both |
| Copy Properties for Monday | workflow | ON | `c:get_started_form_start_date`, `c:schedule_preference` | **VERIFY** | Monday feeder — retires when Teachworks low-balance alert replaces Monday (same flag as deal TOR fields) |
| Create Deal when New Tutor Books Virtual Interview | workflow | ON | `d:how_did_you_hear_about_us_` | **EDIT** | Live tutor recruiting — drop dead refs (myers-briggs-era fields), keep |
| Diagnostic Testing - In House | workflow | ON | `c:assessment_attended___in_house`, `c:assessment_graded___in_house` | **DELETE** | Assessment flow from the 2021-22 diagnostic era — program dead |
| Diagnostic Testing - Remote | workflow | ON | `c:assessment_received`, `c:assessment_uploaded` | **DELETE** | Assessment flow from the 2021-22 diagnostic era — program dead |
| Emliy | list | — | `d:how_did_you_hear_about_us_` | **DELETE** | Attribution splinter list (typo of Emily) |
| Free Trial - Quality Check | workflow | ON | `c:start_date_for_tutoring_for_this_deal` | **EDIT** | Live QC reminder flow — remove the start_date_for_tutoring_for_this_deal reference (or keep the property) |
| Full Name | workflow | ON | `c:full_name` | **VERIFY** | Writes contact full_name (10k fills) — likely the Monday display-name feeder; retires with Monday |
| Get Started Now - CAP FORM SUBMISSION to DEAL | workflow | ON | `c:sync_to_teachworks_cap`, `d:is_the_student_preparing_for_the_non_sat_test_`, `d:is_the_student_preparing_for_the_sat_` | **DELETE** | CAP is a dead business |
| Get Started Now - FORM SUBMISSION to Deal Create GOLD | workflow | ON | `c:get_started_form_start_date`, `c:schedule_preference`, `d:expected_1st_lesson_date`, `d:message` | **EDIT** | LIVE lead intake (Gold) — remove refs to schedule_preference/time/get_started_form_start_date, keep the workflow |
| Gold - Quality Check New  Until Renew | workflow | ON | `c:start_date_for_tutoring_for_this_deal`, `d:message` | **EDIT** | Live QC reminder flow — remove the start_date_for_tutoring_for_this_deal reference (or keep the property) |
| Gold and In person SMS New Deal Created gold and in person | workflow | ON | `c:schedule_preference`, `d:message` | **EDIT** | Live new-deal SMS — templates use deal message/what_s_going_on_/first_name; swap tokens to contact/live fields, keep the workflow |
| How Did You Hear About Us Copied | workflow | ON | `c:how_did_you_hear_about_us___cloned__original_`, `d:how_did_you_hear_about_us_` | **DELETE** | Copies into the *_cloned__original_ dup — pure legacy plumbing |
| In- Person - Quality Check New  Until Renew | workflow | ON | `c:start_date_for_tutoring_for_this_deal`, `d:message` | **EDIT** | Live QC reminder flow — remove the start_date_for_tutoring_for_this_deal reference (or keep the property) |
| Is the online tutor ready for onboarding | workflow | ON | `c:business_license_on_file`, `c:is_the_online_tutor_ready_for_onboarding` | **KEEP** | Roman 2026-08-11: QBO is manual — this pair is the tutor-onboarding queue. Both properties reclassified KEEP-IN-PLACE |
| Julia Cap Contact Workflow post consult | workflow | ON | `c:sync_to_teachworks_cap`, `d:is_the_student_preparing_for_the_non_sat_test_`, `d:is_the_student_preparing_for_the_sat_` | **DELETE** | CAP is a dead business (locked rule 6) |
| Lead Pipe Line - Ads - Free Lesson | workflow | ON | `c:time`, `d:how_did_you_hear_about_us_` | **EDIT** | Live lead routing — remove full_name/time refs, keep |
| Lead Pipe Line - Online | workflow | ON | `c:full_name`, `c:time` | **EDIT** | Live lead routing — remove full_name/time refs, keep |
| Making active deal Customers with More than 1 deal Returning | workflow | ON | `d:how_did_you_hear_about_us_` | **EDIT** | Live returning-customer flagger — drop dead ref, keep |
| New 20 off submission | workflow | ON | `d:how_did_you_hear_about_us_`, `d:message` | **DELETE** | 2022 promo flow |
| New Tutors as Tutor Prospect | workflow | ON | `d:how_did_you_hear_about_us_` | **EDIT** | Live tutor recruiting — drop dead refs (myers-briggs-era fields), keep |
| Non Charter/A+ Sync to TW | workflow | ON | `c:sync_to_teachworks_` | **KEEP** | Roman 2026-08-11: LIVE — puts Gold + Free Trial deals into A+ Teachworks (deal_sync covers charter POs only). Property reclassified KEEP-IN-PLACE |
| Pilibos — Send welcome emails on payment to Parents | workflow | ON | `d:message` | **EDIT** | LIVE Pilibos program — drop the dead-field ref only |
| Pipeline is "CFGC", deal stage is "Package Used Up" | workflow | ON | `c:actively_tutoring` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "CFGC", deal stage is "Post-Lesson" | workflow | ON | `c:actively_tutoring` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Charter Schools", deal stage is "Continued - Ou | workflow | ON | `d:first_name`, `d:last_name` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Charter Schools", deal stage is "No Funds/Did N | workflow | ON | `c:actively_tutoring` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Charter Schools", deal stage is "Package Fulfil | workflow | ON | `c:actively_tutoring` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Charter Schools", deal stage is "Payment Receiv | workflow | ON | `d:payment_received` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Charter Schools", deal stage is "Post Lesson" | workflow | ON | `c:actively_tutoring` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Charter Schools", deal stage is "Pre-Lesson" | workflow | ON | `c:sync_to_teachworks_`, `d:last_name`, `d:what_s_going_on_` | **EDIT** | Live stage engine — the sync_to_teachworks flag it sets is LIVE (keep that); strip only the other dead refs |
| Pipeline is "College Access Plus", deal stage is "Decision D | workflow | ON | `c:actively_counseling`, `c:decision_day` | **DELETE** | CAP stage automation — dead business |
| Pipeline is "College Access Plus", deal stage is "Did Not Us | workflow | ON | `c:actively_counseling`, `c:time` | **DELETE** | CAP stage automation — dead business |
| Pipeline is "College Access Plus", deal stage is "Payment Re | workflow | ON | `c:actively_counseling`, `c:sync_to_teachworks_cap` | **DELETE** | CAP stage automation — dead business |
| Pipeline is "Free Trial", deal stage is "Pre-Lesson"  | workflow | ON | `c:schedule_preference`, `c:sync_to_teachworks_` | **EDIT** | Live stage engine — the sync_to_teachworks flag it sets is LIVE (keep that); strip only the other dead refs |
| Pipeline is "Gold Tutoring - Renewal", deal stage is "New Re | workflow | ON | `d:first_name`, `d:last_name` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Gold Tutoring", deal stage is "Post Lesson"  | workflow | ON | `c:actively_tutoring` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Gold Tutoring", deal stage is "Pre-Lesson" | workflow | ON | `c:sync_to_teachworks_`, `d:what_s_going_on_` | **EDIT** | Live stage engine — the sync_to_teachworks flag it sets is LIVE (keep that); strip only the other dead refs |
| Pipeline is "Gold Tutoring", deal stage is "Renewed" | workflow | ON | `d:last_name` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Gold Tutoring", deal stage is "Stopped For Now" | workflow | ON | `c:actively_tutoring` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "In-Person Summer Boost", deal stage is "Pre-Les | workflow | ON | `c:schedule_preference`, `c:sync_to_teachworks_slp` | **EDIT** | Live stage engine — the sync_to_teachworks flag it sets is LIVE (keep that); strip only the other dead refs |
| Pipeline is "In-Person", deal stage is "Pre-Lesson" | workflow | ON | `c:sync_to_teachworks_slp`, `d:last_name`, `d:what_s_going_on_` | **EDIT** | Live stage engine — the sync_to_teachworks flag it sets is LIVE (keep that); strip only the other dead refs |
| Pipeline is "In-Person", deal stage is "Stopped for Now" | workflow | ON | `c:actively_tutoring` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "New Tutor", deal stage is "Pass Background Chec | workflow | ON | `d:message` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "Online Summer Boost", deal stage is "Pre-Lesson | workflow | ON | `c:sync_to_teachworks_`, `d:last_name`, `d:what_s_going_on_` | **EDIT** | Live stage engine — the sync_to_teachworks flag it sets is LIVE (keep that); strip only the other dead refs |
| Pipeline is "SAT Tutoring", deal stage is "Post-Lesson" | workflow | ON | `c:actively_tutoring` | **EDIT** | Live stage engine (SMS/flags per stage) — remove dead-property references, keep the workflow |
| Pipeline is "SAT Tutoring", deal stage is "Pre-Lesson" | workflow | off | `c:sync_to_teachworks_` | **DELETE** | Already disabled |
| QTL New Customer  v2 - 10/2025 | workflow | ON | `d:how_did_you_hear_about_us_` | **EDIT** | Live qualified-lead flow — drop the dead-field ref, keep |
| QTL Workflow - Charter School 2.0 | workflow | ON | `d:how_did_you_hear_about_us_` | **EDIT** | Live qualified-lead flow — drop the dead-field ref, keep |
| Qualified Tutoring Lead Workflow - Diagnostic Sent | workflow | ON | `c:assessment_received`, `c:assessment_sent`, `c:assessment_uploaded`, `c:time` | **DELETE** | QTL diagnostic branch — assessment era, dead |
| Quality Charter, CFGC, RTI | workflow | ON | `c:start_date_for_tutoring_for_this_deal` | **EDIT** | Live QC flow — same |
| Quickbooks | workflow | — | `c:time` | **ARCHIVED 2026-08-11** | Roman: "archive all quickbooks references" — flow 323730202 deleted, backup in ops/fleet-health/audit/backups/2026-08-11-quickbooks/ |
| RBS | list | — | `d:how_did_you_hear_about_us_` | **DELETE** | Attribution splinter list |
| REFERRAL PROGRAM - NEW TEACHERS | workflow | ON | `c:how_did_you_hear_about_this_opportunity_with_a_tutoring`, `c:tutor_referral___referred_by___name`, `d:how_did_you_hear_about_us_` | **VERIFY** | Referral program may be live (referral_name is a keeper) — these reference the old referred_by fields; if program is live, EDIT to drop the dead fields |
| REFERRAL PROGRAM NEW FAMILIES | workflow | ON | `c:referral___referred_by___name`, `d:how_did_you_hear_about_us_` | **VERIFY** | Referral program may be live (referral_name is a keeper) — these reference the old referred_by fields; if program is live, EDIT to drop the dead fields |
| Ready for Onboarding to QBO | list | — | `c:is_the_online_tutor_ready_for_onboarding` | **ARCHIVED 2026-08-11** | Roman: "archive all quickbooks references" — list 1176 deleted, backup in the same folder |
| Referral | list | — | `d:how_did_you_hear_about_us_` | **VERIFY** | Attribution list — tied to referral program status |
| Resume after Stopped for Summer | list | — | `c:actively_tutoring` | **DELETE** | Summer-2021 era segment list |
| Royal | list | — | `c:how_did_you_hear_about_us___cloned__original_` | **DELETE** | Attribution splinter list |
| SMS - Incoming 5th graders - Sent First week of August | workflow | ON | `d:message` | **DELETE** | Dated one-off SMS blast (August campaign) |
| SMS - New Year Check in | workflow | ON | `d:message` | **DELETE** | Dated one-off SMS blast |
| Student Diagnostic Test Upload | workflow | ON | `c:assessment_uploaded` | **DELETE** | Assessment flow — program dead |
| Student Spotlight — Brenda Handoff (#4) | workflow | ON | `d:message` | **EDIT** | LIVE Spotlight program — drop the dead-field ref only |
| Student Spotlight — Paola Notification (#3) | workflow | ON | `d:message` | **EDIT** | LIVE Spotlight program — drop the dead-field ref only |
| Student Spotlight — Post-Survey Automation (#2) | workflow | ON | `d:message` | **EDIT** | LIVE Spotlight program — drop the dead-field ref only |
| Teacher Scholarship Program - Workflow 3b - Nomination Form  | workflow | ON | `d:message` | **EDIT** | LIVE TSN program — drop the dead-field ref only |
| Text FURA | workflow | ON | `d:message` | **DELETE** | One-off text blast (FURA) |
| Trial Gold SMS New Deal Created free trial | workflow | ON | `c:schedule_preference`, `d:message` | **EDIT** | Live new-deal SMS — templates use deal message/what_s_going_on_/first_name; swap tokens to contact/live fields, keep the workflow |
| Video Ask Celebrating Student Success | workflow | ON | `d:how_did_you_hear_about_us_` | **DELETE** | VideoAsk stack is retired (integration remnants are STORAGE-ONLY) |
| Video Ask Testimonial Responses | workflow | ON | `c:left_a_review_` | **DELETE** | VideoAsk stack is retired (integration remnants are STORAGE-ONLY) |
| WF-01 \| Student Nominated - Teacher Scholarship Program | workflow | ON | `d:message` | **EDIT** | LIVE TSN program — drop the dead-field ref only |
| WF-02 \| Consultation Scheduled - Teacher Scholarship Program | workflow | ON | `d:message` | **EDIT** | LIVE TSN program — drop the dead-field ref only |
| WF-04 \| Unresponsive Family – Teacher Scholarship Program | workflow | ON | `d:first_name`, `d:message` | **EDIT** | LIVE TSN program — drop the dead-field ref only |
| YELP ROI | list | — | `d:how_did_you_hear_about_us_` | **VERIFY** | Yelp attribution — if Yelp channel is dead, DELETE list+flow together |
| Yelp | list | — | `c:how_did_you_hear_about_us___cloned__original_`, `d:how_did_you_hear_about_us_` | **VERIFY** | Yelp attribution — if Yelp channel is dead, DELETE list+flow together |
| Yelp Virtual Consult | workflow | ON | `d:how_did_you_hear_about_us_` | **VERIFY** | Yelp attribution — if Yelp channel is dead, DELETE list+flow together |
| ilead custom program | workflow | ON | `d:how_did_you_hear_about_us_` | **VERIFY** | iLead program flow — iLead is live (Level-Up); confirm this specific flow is current |
| test support2 text messages | workflow | ON | `d:message` | **DELETE** | Literal test workflow |

## Blocking forms (43)

HubSpot refuses to archive these properties because a FORM still includes them. The API token
lacks the `forms` read scope, so only IDs are visible here. **Two ways to resolve:** (a) add the
`forms` scope to the private app (Settings -> Integrations -> Private Apps) and I enumerate names +
live/dead per form next pass, or (b) work the list in the UI (Marketing -> Forms). Old quiz/intake
forms that are unembedded can simply be deleted; that alone unblocks most of the 43.

| Form ID | Blocks |
|---|---|
| `0-08d9dfed-1e44-4d72-96b3-2a4cf2a4d00b` | `ap_subjects` |
| `0-0a4db7b1-e03a-47ee-8524-0eff89c8c70a` | `has_your_child_worked_with_a_tutor_before_`, `have_missing_assignments_been_an_issue_`, `tutoring_plan` |
| `0-0c1f5e77-570f-4001-b3ca-d414f168e9ed` | `science_subjects` |
| `0-10a7465d-5352-4280-9e23-b65887427f48` | `do_you_want_your_student_to_receive_email_notifications_for_lesson_reminders_` |
| `0-19026c7a-0e3c-4213-a97a-c1be46a55211` | `high_school_subjects` |
| `0-1a6f867e-4233-45e8-a161-6c908e14b001` | `date_to_start_customer_provided` |
| `0-1e84dde5-112a-492a-86f4-5e8d8a48c6d5` | `college_test_prep`, `have_you_taken_the_sat_or_act_already_` |
| `0-29a59d73-a262-4fc7-8253-b80f13f788ce` | `referral___referred_by___email` |
| `0-3561c536-d11a-4fc4-93a3-5c835baf3cb4` | `how_many_students_will_be_in_your_small_learning_pod_`, `ready_to_start_date` |
| `0-37bf7871-f75a-4897-9482-82b3cdf93d63` | `how_many_students_will_be_in_your_small_learning_pod_`, `ready_to_start_date` |
| `0-3a806f2d-15a7-48c5-9f39-af993c5742ca` | `referral___referred_by___email` |
| `0-3c5535a9-f98b-44e4-86f0-2affb6a47642` | `date_to_start_customer_provided`, `date_to_stop_lessons_for_summer_update___schedule_update`, `do_you_want_to_update_your_tutoring_schedule_`, `when_can_we_reach_out_to_you_to_resume_` |
| `0-40ab8985-fcec-4ae9-a5ae-e1270550bcdf` | `date_for_first_free_lessons` |
| `0-412748c8-c21d-4460-9d43-557acc1df7ab` | `date_for_first_free_lessons` |
| `0-4a6d5493-2921-4cfc-aadc-ceefd2946799` | `is_there_anything_specific_that_you_would_like_the_student_to_be_working_on_with_the_tutor_`, `optional__please_attach_a_pdf_of_the_student_s_most_up_to_date_iep_or_504_plan_` |
| `0-5982a5fe-14e4-4058-b7a4-372e293a648b` | `college_test_prep`, `do_you_have_a_college_list_created_`, `have_you_taken_the_sat_or_act_already_` |
| `0-6889a508-9a47-48f0-97bb-94e746bdbb96` | `what_math_is_your_child_currently_working_on_` |
| `0-6d4243d2-bb2a-4e66-ad3e-d329f471765d` | `date_for_first_free_lessons` |
| `0-771ccb50-1014-4009-9898-4f5278c9d7bb` | `which_subjects_do_you_feel_you_are_most_experienced_to_tutor_` |
| `0-840bf258-3fc8-4c51-855e-00637d1c5514` | `additional_note`, `date_of_tutoring_session_for_trial`, `day_preference`, `other_subject`, `subject_preference` |
| `0-8de2261e-ba3c-4bb5-acec-d99cf3cf9cf5` | `which_subjects_do_you_feel_you_are_most_experienced_to_tutor_` |
| `0-8ef27a6a-d00c-4d7a-b0ad-49655507b58f` | `has_your_child_worked_with_a_tutor_before_` |
| `0-a7c2d8c4-73ca-49a5-be09-9dfbb7f26da2` | `optional__please_attach_a_pdf_of_the_student_s_most_up_to_date_iep_or_504_plan_` |
| `0-aba64731-b133-4601-9413-bfb7b712b0b7` | `tutor_referral___referred_by___email` |
| `0-b1c9782d-eca1-4d19-8516-e47de6cb1423` | `referral___referred_by___email` |
| `0-b3b04c87-2342-4788-9328-080f4afb085e` | `english_subjects` |
| `0-be393fd2-f587-4362-806a-4630c67e5d97` | `middle_school_subjects` |
| `0-c096fcda-c3c2-4adf-bda3-ef3cc9ef02a8` | `how_many_students_will_be_in_your_small_learning_pod_`, `ready_to_start_date` |
| `0-d354012a-1633-4450-bacb-3b51f1c65d88` | `date_for_first_free_lessons` |
| `0-d80b0d2e-4bbc-4dbb-952b-ea229bcae67b` | `day_preference`, `subject_preference`, `when_would_you_like_the_first_lesson` |
| `0-df07d26f-071d-4b93-9b7e-44f4fd6bfcb2` | `referral___referred_by___email` |
| `0-f155d19e-baff-41fa-80f7-d2371b594f2e` | `name_of_primary_contact_for_your_pod` |
| `0-f268b120-e4bf-4008-ab96-b6fad441ffa1` | `tutor_referral___referred_by___email` |
| `1-66b1eecb-1ba0-4d0e-b8f3-173ea2c0dd6b-draft` | `type_of_enrollment` |
| `3-0bae95bc-09d5-4521-ab86-7f467a59ca6c` | `what_grade_is_your_child_in` |
| `3-2b1a4359-0be1-4ad3-9abf-b5e17e097748` | `what_grade_is_your_child_in` |
| `3-30ddbfc2-2928-47ba-b2b2-efc97e4d7b62` | `lead_ad_prop0` |
| `3-6629020d-20c7-4529-a2a3-78a6ac03de61` | `what_grade_is_your_child_in` |
| `3-bb4f8c75-dd71-430f-b365-e8c3583bd21e` | `are_missing_assignments_a_concern`, `what_grade_is_your_child_in` |
| `3-f4df3fc9-570f-4dd8-9685-65a0b50ced40` | `what_grade_is_your_child_in` |
| `5-5351d40b-b2bd-4b47-937c-9511a2db448f` | `if_selected_when_are_you_available_to_start_tutoring_` |
| `5-595b17b7-cd90-495c-9072-ca9464ce1dc5` | `if_selected_when_are_you_available_to_start_tutoring_` |
| `5-fc591e60-460d-4eac-b557-b16a9437a989` | `if_you_have_taken_the_myers_briggs_personality_test__what_is_your_personality_type__4_letters_` |

## Other blockers (8)

| Type | ID | Blocks |
|---|---|---|
| BOT | `331484-2548433` | `has_your_child_worked_with_a_tutor_before_` |
| DEPENDENT_CONDITIONAL_FIELD | `0-3/home_city/9086247` | `home_city` |
| DEPENDENT_CONDITIONAL_FIELD | `0-3/home_city/97052443` | `home_city` |
| DEPENDENT_CONDITIONAL_FIELD | `0-3/home_street_address/9086247` | `home_street_address` |
| DEPENDENT_CONDITIONAL_FIELD | `0-3/home_zip/9086247` | `home_zip` |
| DEPENDENT_CONDITIONAL_FIELD | `0-3/subscription_type/97052444` | `subscription_type` |
| EMAIL | `54151437464` | `referral___referred_by___email` |
| REPORT | `93196996` | `contact_created_by_1st_edit` |

`DEPENDENT_CONDITIONAL_FIELD` = another property's conditional display logic references the
candidate — edit the parent property's conditional logic in the UI. `BOT` = a chatflow;
`EMAIL` = a marketing email personalization token; `REPORT` = a report filter.

## Execution plan (after approval)

0. **Authoritative probe:** canary-test HubSpot's delete-time PROPERTY_USAGE guard on `avatar`
   (its only reference is the dead Avatar-to-Persona flow — harmless either way). If the guard
   enumerates workflow/list references like it does forms, attempt-delete ALL 35
   automation-blocked candidates: the guard either archives false-positives on the spot or
   returns the exact reference list per property — replacing the text-scan attributions above.
1. Roman answers the three high-risk callouts + the VERIFY column.
2. Backup: export JSON of every DELETE-verdict workflow + list into
   `ops/fleet-health/audit/backups/` (same as the 07-31 purge).
3. Disable DELETE-verdict workflows; delete after a quiet week. Delete splinter lists.
4. EDIT pass: remove dead-property references from live flows (each edit listed in the PR).
5. Forms pass: delete/detach dead forms (scope permitting, I enumerate; else UI session).
6. Re-run the archive pass — every property whose last reference is gone archives cleanly.

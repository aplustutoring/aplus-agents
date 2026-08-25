# Tier 4: heavy referrers (24 people). NOT A CAMPAIGN LIST.

HARD COMPLIANCE RULES (Roman 2026-08-25, locked). Do not violate any.
  1. The Badge denotes quality of program DESIGN only. Not implementation. Not
     effectiveness.
  2. No copy may imply Stanford validated our student outcomes.
  3. Never use: certified, accredited, endorsed, approved provider.
  4. No numbers about students anywhere. No counts, no percentages, no outcome
     data. (The only digits permitted in a body are the Badge term years.)
  5. No em dashes, ever.
  6. Student-centered voice. Thank teachers for trusting us with STUDENTS.
     Never thank them for sending business.
  7. Text only. No Badge image in email.

Voice: danielle-voice. Sage Oak EXCLUDED. From: Danielle.
Tokens: firstname ONLY (fallback 'there').
Scholarship spec: knowledge/programs/teacher-scholarship.md (two 45-minute
sessions, one assessment one instruction; two nominations; overflow honoured).

**These people are pulled OUT of the campaign.** Roman 2026-08-25: individual
sends from Danielle, one specific personal line each. They are not enrolled in
any workflow, they receive no automated follow-up, and no bulk email is sent to
them. If one of them appears in a campaign list, that is a bug.

They are the teachers who trusted us most. A merge-field email to someone who
sent us five or more families reads as exactly what it is.

## What Danielle needs per person, generated before the send

`scripts/charter_tor_segments.py --json` carries all of it:
  * name, school
  * the families they referred, and the students inside those deals
  * whether any have restarted this year
  * their last activity date

## The shape of each send

Same three beats as Tier 3, but the first is written by hand:

1. **One specific personal line.** Name a student, a family, or something that
   actually happened. This is the whole reason these are individual. If nothing
   specific can be said about a person, they do not belong in Tier 4.
2. The Badge paragraph. May be reused verbatim from Tier 3, which is locked:

   > You trusted us with your students last year, before any outside review of
   > how we work existed. Stanford's National Student Support Accelerator has
   > now reviewed how our tutoring program is designed and awarded us their
   > Tutoring Program Design Badge for 2026 through 2029. Thank you for
   > trusting us first.

3. The ask, about this year's caseload. No template: these get a real question.

Scholarship may be mentioned, but as an aside in Danielle's own words, not the
standard P.S. block.

## Why 24 and not 15

Roman estimated 15-25. The cut is five or more families across 25/26 and 26/27
combined, which yields 24. If Danielle wants a shorter list, raise
`TIER_4_MIN_FAMILIES` in `scripts/charter_tor_segments.py` rather than trimming
by hand, so the campaign lists stay consistent with it.

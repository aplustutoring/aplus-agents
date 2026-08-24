# B1: Anchor, 5+ families in 25/26, nothing yet in 26/27 (18 mailable, wave 1)

Voice: danielle-voice. Sage Oak EXCLUDED. From: Danielle. HIGHEST VALUE.
Tokens: firstname (fallback 'there'), tor_family_count.
Rules (Roman 2026-08-24): curiosity over bullshit; school year start is busy.

THE HOOK: a teacher never finds out what happened to the students they referred.
Nobody reports back to them. We have that data (Teachworks lesson history via
scripts/charter_gap_analysis.py: last completed lesson, tutor, whether they
stopped partway). Offering the ANSWER costs the teacher one word. Offering a
"roster" asked them to do admin in September, which is the opposite.

**CHECK BEFORE SEND:** Danielle must be able to actually answer this within a
day when they reply. The data exists; the pull is currently manual.

**Subject:** Your students from last year

Hi {{ personalization_token('contact.firstname', 'there') }},

You sent us {{contact.tor_family_count}} families last year. Some finished the
year, some stopped partway, and I doubt anyone told you which.

I can, in one email. Want it?

Danielle

*P.S. Our Teacher Scholarship Program gives a student of your choosing one free
session. Tell me who and I will set it up.*

---
## Follow-up (Day 4, only if no reply)

**Subject:** Re: Your students from last year

Hi {{ personalization_token('contact.firstname', 'there') }},

Still happy to send it. Takes me two minutes and costs you nothing either way.

Danielle

---
## Day 8: task for DANIELLE (not an email)
Call, ranked by 25/26 invoiced value. Bring the answer, not the offer.

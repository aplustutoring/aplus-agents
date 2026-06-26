---
name: aplus-inclusive-language
description: Enforce respectful, person-first SPED/ELL language in any A+ Tutoring content that mentions a student — case studies, social posts (Facebook, Instagram), captions, blog copy, and emails. Codifies A+'s SPED/ELL Strategy Card: person-first disability language ("a student who has dyslexia," not "a dyslexic student"), correct English-learner terminology (ELL, LTEL, translanguaging as a resource), and the overriding rule to follow the student's and family's stated preference. Use as a generation guide AND an enforcement/rewrite pass before any student-facing content is approved or published.
---

# A+ Inclusive Language (SPED / ELL)

## Purpose
Every piece of A+ content that describes a student must use respectful,
person-first language for disabilities and accurate, non-deficit language for
English learners. This is a brand-trust and compliance requirement, not a
style preference.

**Source of truth (canonical):**
`https://meetings.wetutorathome.com/hubfs/Internal/SPED_ELL_StrategyCard.html`
When this skill and the card ever disagree, the card wins — re-read it.

## The overriding principle
> **Always follow the student's and family's stated preference.**

Person-first is the default. If Paola's brief records that the student or
family self-identifies a different way (e.g. identity-first "dyslexic," or a
specific term they prefer), honor that exactly. Absent a stated preference,
use the person-first defaults below.

## Disability language — say this, not that

| ❌ Don't | ✅ Do |
|---|---|
| a dyslexic student / Liam is dyslexic | a student who has dyslexia / Liam, who has dyslexia |
| an ADHD kid / he's ADHD | a student who has ADHD |
| an autistic student (unless family prefers it) | a student on the autism spectrum / a student who has autism |
| special-ed kid / SPED kid | a student who receives special-education services |
| slow / behind / struggling reader | a student working below grade level / a student who has reading challenges |
| suffers from / afflicted with / victim of [condition] | has / lives with / experiences [condition] |
| confined to / wheelchair-bound | uses a wheelchair |

Person-first framing for challenges the card names explicitly:
"processing speed challenges," "working memory challenges," "output
difficulties" — describe the **challenge**, attached to the **student**, never
label the student as the deficit.

## English-learner language

- **ELL** = English Language Learner (current designation). Spell it out on
  first use, then ELL is fine.
- **LTEL** = Long-Term English Learner — a student in US schools 6+ years who
  is still designated ELL. Use precisely; not interchangeable with ELL.
- **Translanguaging** (switching languages mid-sentence/mid-task) is a
  **cognitive resource, not a deficit.** Never frame a bilingual student's
  language use as confusion, a problem, or something to "fix."
- ❌ "non-English speaker," "limited English," "ESL kid" → ✅ "English
  Language Learner," "multilingual student," "emerging bilingual student."

## What to flag / rewrite
When checking content, rewrite any of these in place (preserve meaning, voice,
and verbatim parent quotes):
1. Identity-first disability phrasing → person-first (unless family preference
   is on record).
2. Deficit/pity framing ("suffers from," "struggling," "slow," "behind").
3. Deficit framing of an English learner or of translanguaging.
4. Outdated/incorrect ELL terms.

**Never alter a verbatim parent or tutor quote** — if a quote itself uses
non-person-first language, leave the quote intact and (if needed) flag it for
human review rather than editing someone's words.

## Output (when used as an enforcement pass)
Return strict JSON, no fence:
```
{
  "violations": [
    {"rule": "person-first", "location": "<short quote>", "fix": "<replacement>"}
  ],
  "cleaned": "<the full text after applying every fix, structure unchanged>"
}
```
If the text is already compliant, return `violations: []` and `cleaned` equal
to the input verbatim. Never drop content, never touch verbatim quotes, never
change anything unrelated to inclusive language.

## Companion: anonymization disclaimer
B2C case studies open with a fixed anonymization note (handled by the
orchestrator) so readers understand the student/family identities are
protected and only the tutor is named. That disclaimer is what lets a story
mention a specific, person-first diagnosis responsibly — but only name a
diagnosis when it genuinely serves the story.

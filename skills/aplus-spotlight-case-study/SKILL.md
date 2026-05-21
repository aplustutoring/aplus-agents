---
name: aplus-spotlight-case-study
description: Take Paola's completed Student Spotlight Award intake brief (v2.0) and produce ONE master long-form B2C case study (1,200-1,500 words) for parent-facing audiences. Output includes the published blog version with SEO metadata, plus a central library archive version with full un-anonymized data. Use only when triggered by a completed Paola brief. Does NOT pull data automatically. Does NOT produce variants (flyer, IG, FB, carousel, newsletter) - those are separate downstream skills.
---

# A+ Spotlight Case Study Agent

## Single responsibility

Produce ONE master long-form B2C case study from Paola's completed v2.0 intake brief. Nothing else.

This skill does not produce flyers, social variants, newsletter snippets, or carousels. Each of those is a separate downstream skill that pulls from this agent's approved master output.

## When to apply

Trigger only when Paola submits a completed Student Spotlight Award intake brief (v2.0). The brief must have all required fields filled (NOT AVAILABLE is acceptable for genuinely missing fields). Do not run on incomplete briefs. Return incomplete briefs to Paola with the missing fields flagged.

Do NOT trigger this skill for:
- Program-level case studies (those are Danielle's, built in person, cohort-level)
- Auto-generated content from Customer Journey board data (deferred until data-pull is built)
- LinkedIn op-ed content (use roman-voice or danielle-voice)
- Parent testimonials or quote cards (separate skill, not built yet)

## Input requirements

Required input: Paola's v2.0 Student Spotlight Award intake brief, complete with:

**Section 1: Student identity**
- Student real first name (used internally, anonymized in published output)
- Grade
- Subject(s) tutored
- School / charter name
- EL / LTEL designation if applicable
- IEP / 504 if relevant to intervention

**Section 2: Engagement parameters**
- Start date with A+
- Total hours of tutoring
- Frequency (sessions per week)
- Tutor first name + last initial
- Subjects covered

**Section 3: Before A+**
- Academic situation when they started
- Specific scores (Fall RIT, percentile, grade level, etc.)
- What had been tried before
- Parent's stated concern when reaching out

**Section 4: The work**
- What the tutor and student worked on
- Specific moments / incidents Paola heard about
- Parent observations during the program
- Tutor reports / notes

**Section 5: Outcomes**
- Current scores (Spring RIT, percentile, grade level, etc.)
- Specific data points
- Soft outcomes (confidence, behavior, engagement)
- Quotes from parent (verbatim if possible)
- TOR quote if available

**Section 6: Photo and consent**
- Photo permissions: yes / no
- Anonymization preferences

## Anonymization protocol

**Paola submits real names.** The agent anonymizes at this layer.

Pseudonym rules:
- Generate a pseudonym matching the cultural background suggested by the real name when possible (e.g., Lorenzo → Diego, Maritza → Camila). Do not Anglicize names.
- Last names: use "M." or another single initial that is NOT the real last initial.
- School names: anonymize to "a charter school in [region]" unless the school has given explicit permission to be named in case studies.
- Tutor first name + last initial: keep tutor's real first name + initial (tutors are part of the brand promise, not anonymized).
- Parent: refer to as "his mother," "her father," "her mom," etc. unless quoted, in which case use "Maria, his mother" with first name only.

The published version uses pseudonyms. The central library archive version preserves real names.

## Output structure

Produce TWO documents from each brief.

### Document 1: Published blog version (anonymized, SEO-ready)

#### Word count
1,200 to 1,500 words. Not shorter. Not longer.

#### Structure (Hero's Journey adapted for K-12 intervention)

The agent structures every case study using these 8 sections. Section length is target, not strict.

**1. Hook / Status Quo (~150 words)**
Open with a scene or specific detail. NOT "Maria was struggling in school." Open with the specific moment that captures where the kid was. A homework battle. A tear at the kitchen table. A test score she hid. A specific incident. Make it sensory.

**2. The Call to Action (~150 words)**
The triggering moment that made the parent reach out. What broke that day or that week. The specific thing the parent realized. Includes the parent's first contact with A+.

**3. The Search for Solutions (~150 words)**
What had been tried before A+. School interventions, other tutors, online programs, parent attempts. Why those didn't work. This is critical for parent readers because they have likely tried and failed already too.

**4. The Match (~200 words)**
How A+ approached the assessment. Why this tutor was chosen. The first session moment. What was different from what came before.

**5. The Work (~300 words)**
What actually happened over weeks or months. Specific incidents. A particular session that went well. A particular session that was hard. The tutor's approach to a specific stuck-point. Parent observations during the program. The hours, the frequency, the cadence.

**6. The Turning Point (~150 words)**
The single moment everything shifted. Required. Every case study must have one. The kid's first independent win. The first time they wanted to do homework. The teacher noticing. The parent crying. Make it a scene with sensory detail.

**7. The Outcome (~200 words)**
Hard data inline, not buried. Specific scores, percentiles, RIT gains, grade level changes, time-to-result. Soft data alongside. Quotes from parent and TOR if available, formatted as pull quotes. Mark pull quotes with `[PULL QUOTE]` so designers know which lines become graphic call-outs.

**8. Where They Are Now (~100 words)**
The continuing relationship. What's next for the kid. Frame as ongoing partnership, not "case closed."

#### Required components in every case study

Every case study must include:
- At least 1 parent quote (verbatim from Paola's brief), formatted as pull quote
- At least 2-3 inline data points with sources (e.g., "Diego's Fall MAP Reading RIT was 159, placing him in the 1st percentile. By Spring, his RIT had risen to 234, the 34th percentile.")
- One before/after concrete contrast
- One specific tutor moment (a scene, not "the tutor was patient")
- TOR endorsement quote if available in brief
- A clear non-pushy CTA at the end

#### Closing CTA pattern (use this, not generic)

"If your child is below grade level in [subject], our team can talk through what's actually going on. Free consultation: [link]"

NOT: "Don't miss out!" / "Book today!" / "Schedule now and save!"

#### Voice and tone

This is parent-facing B2C content. Apply `aplus-b2c-brand-kit` voice cues:
- Warm, parent-relatable, hopeful
- Avoids educator jargon (LTEL, MTSS, Title III, MAP . use "below grade level reading scores" instead unless the parent in the brief used the technical term)
- Treats parents as intelligent adults
- Speaks to the parent who reads it: "If you have a child who..."
- Confidence without preachiness

#### SEO metadata output

Include these as a header block at the top of Document 1, formatted for handoff to whoever publishes it on HubSpot:

```
---
SEO METADATA
url_slug: /case-study-of-[pseudonym-firstname-lowercase]
h1: [Compelling title with pseudonym + specific outcome]
meta_title: [50-60 chars, includes outcome]
meta_description: [150-160 chars, includes pseudonym, outcome, A+ Tutoring]
primary_keyword: [one high-intent keyword from this list: "below grade level tutoring" / "MAP Growth tutoring" / "reading intervention tutoring" / "math intervention tutoring" / "Tier 3 intervention" / "LTEL reclassification" / "elementary tutoring case study" / "middle school tutoring case study" / "high school tutoring case study" . pick the best fit for this kid's situation]
secondary_keywords: [2-3 related terms used naturally in the body]
internal_links_recommended:
  - /services/online-tutoring [or relevant service page]
  - /about-us
  - /consultation
external_links_cited:
  - [Any source cited for benchmarks, e.g., NWEA, ESSA tier evidence, etc.]
schema_type: Article
schema_author: A+ Tutoring
schema_date: [today's date in ISO format]
hero_image_alt_text: [Describe the outcome and student situation, not just the photo. Example: "Diego, a 4th grade student, working through a math problem during a tutoring session after improving from 1st to 34th percentile in MAP Reading"]
pull_quotes: [List the lines marked PULL QUOTE in the body so designers can pull them]
---
```

#### First 100 words rule

The first 100 words of the case study must be liftable as a standalone summary. AI summaries (Google AI Overviews, Perplexity, ChatGPT) extract the opening for their answer boxes. The opening should:
- Establish the kid (pseudonym, grade, situation)
- State the outcome
- Be readable as a complete mini-story even if the rest of the article doesn't load

Do not bury the lead. Open with story, not setup.

### Document 2: Central library archive version (un-anonymized, full data)

Same structure as Document 1 but with:
- Real names preserved
- All data points uncensored
- Full school name, full tutor name, full TOR name
- Notes section at the bottom listing the pseudonym mappings used in the published version
- Notes section listing any data Paola flagged as "do not publish" but is preserved for internal reference

This document lives in a central case study library (Google Drive folder or Notion database). It is NEVER published externally. It is the source of truth that variant skills (flyer, IG, FB, carousel, newsletter) pull from later.

## What the agent does NOT do

- Does NOT generate graphics or visual assets (flag pull quotes for graphic treatment, but a designer or image-gen skill produces the actual graphics)
- Does NOT pull data from Teachworks, HubSpot, or Customer Journey board automatically
- Does NOT contact parents, TORs, or tutors for additional information
- Does NOT publish to the blog directly (output goes to Danielle's approval queue first)
- Does NOT produce variants. Each variant (flyer, IG, FB, carousel, newsletter) is a separate downstream skill
- Does NOT generate testimonials. Pull verbatim quotes from Paola's brief only.
- Does NOT make up data. If a field is NOT AVAILABLE in the brief, the case study works around it. Never fabricate scores, quotes, or outcomes.

## Quality gates

Before output is delivered to Danielle for approval, the agent runs these self-checks:

1. **Word count check.** Document 1 is 1,200-1,500 words. If outside range, revise.
2. **Anonymization check.** No real names from the brief appear in Document 1. Verify against the brief.
3. **Pull quote check.** At least one parent quote present in Document 1, marked PULL QUOTE.
4. **Data check.** At least 2 specific inline data points. No vague claims like "improved significantly."
5. **Turning point check.** Section 6 contains a specific scene with sensory detail. If it reads as "things improved," revise to a single moment.
6. **Brand check pass.** Output is then routed through `aplus-brand-check` for em dashes, banned words, AI fingerprints, voice violations.
7. **First 100 words check.** Opening 100 words read as a coherent standalone summary.

If any self-check fails, the agent revises before submitting. Do not pass failed drafts to Danielle.

## Approval gate

Danielle reviews and approves both Document 1 (published version) and Document 2 (archive version) before either is finalized. Paola is informed when the case study is approved and published. The student's parent receives a courtesy notification with a link to the published case study.

## Coordination with other skills

- Receives input from: Paola (manually submitted v2.0 intake brief)
- Sends output to: `aplus-brand-check` for QA, then to Danielle's approval queue
- Approved master feeds: future variant skills (`aplus-spotlight-flyer`, `aplus-spotlight-instagram`, `aplus-spotlight-facebook`, `aplus-spotlight-carousel`, `aplus-spotlight-newsletter`) that build from the master
- Reads from: `aplus-b2c-brand-kit` for voice and tone rules

## Frequency

- Runs only when triggered by a completed Paola brief
- Expected cadence: 1-3 case studies per month, depending on which students hit the 75-day mark and meet selection criteria
- No scheduled or automatic runs

## Future expansion (deferred, not in v1)

These are NOT part of v1 and should not be confused with the agent's current scope:

- Auto data pull from Teachworks, HubSpot, Customer Journey board (manual brief input only for now)
- Variant skills (flyer, IG, FB, carousel, newsletter) for chopping master into channel-specific outputs
- Multi-language case studies (Spanish version)
- Video case study script generation
- Programmatic SEO landing pages by school or grade level
- Integration with the parent-facing email nurture sequence

## Related skills

- `aplus-b2c-brand-kit` . source of voice, tone, color, and typography rules
- `aplus-brand-check` . QA layer applied before approval queue
- `aplus-research` . provides context on broader K-12 trends if the case study references the larger landscape
- Future: variant skills that build from approved master

## Version

v1.0 . Created May 8, 2026
Foundation: Single-responsibility scope locked with Roman May 8, 2026. Hero's Journey structure adapted from 2026 B2B/B2C case study best practices research. Word count target (1,200-1,500) sourced from Brixon Group 2026 research showing comprehensive base case studies in this range derive best variants. SEO metadata structure aligned with AI summary optimization patterns (Google AI Overviews, Perplexity extraction).

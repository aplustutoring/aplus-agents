---
name: aplus-blog-longform
description: Take an approved LinkedIn topic + its source materials (research brief, company post, op-eds) and produce a 1,200-1,500 word B2B blog post for blog.wetutorathome.com. Output includes the long-form article body PLUS complete SEO metadata block (slug, meta description, schema markup, internal links) ready for HubSpot publication. Use when a LinkedIn topic has earned the right to be expanded into a permanent owned asset. The blog post becomes Danielle's sales asset she can link to in pitches.
---

# A+ B2B Long-Form Blog Post Agent

## Single responsibility

Take an approved LinkedIn topic and its source materials. Produce ONE master long-form B2B blog post (1,200-1,500 words) for publication on blog.wetutorathome.com.

This skill does not produce LinkedIn posts (use aplus-b2b-brand-kit), op-eds (use voice skills), or B2C content (use aplus-spotlight-case-study). It produces blog posts only.

## When to apply

Trigger this skill when:
- A LinkedIn topic has been approved and the company post + op-eds are produced
- Roman or Danielle decide the topic deserves long-form expansion
- The topic has SEO potential (high-intent keywords school admins search for)
- The topic will be useful as a sales asset Danielle can link to in pitches for 6+ months

Do NOT trigger this skill for:
- Topics that are time-sensitive news with short shelf life (use LinkedIn-only)
- Topics that don't naturally support 1,200+ words
- B2C parent-facing content (use aplus-spotlight-case-study)
- Topics where A+ doesn't have authentic expertise or relevant data

## Input requirements

Required inputs:
1. **The topic** (title + 1-sentence angle)
2. **Source material** from the research brief (URLs, key data points, framing)
3. **The approved company LinkedIn post** (already fact-checked and brand-checked)
4. **Roman op-ed** (if produced) for conviction-angle inspiration
5. **Danielle op-ed** (if produced) for implementation-angle inspiration

Optional inputs:
- Relevant A+ case study data (iLEAD Math Tier 3, iLEAD AV combined, etc.)
- Specific Tier A partner names if the topic touches them
- Internal links to other relevant A+ pages or blog posts

## Output structure

### Document 1: Published blog version (SEO-ready)

#### Word count
1,200 to 1,500 words. Not shorter (insufficient SEO authority). Not longer (reader drop-off).

#### Audience and voice
- **Audience:** charter directors, special programs coordinators, district leaders, intervention coordinators
- **Voice:** B2B brand kit voice. Institutional but human. Data-grounded. Peer-to-coordinator tone.
- **Apply aplus-b2b-brand-kit voice cues throughout.**
- **NOT in Roman or Danielle's first-person voice** (blog posts are company-authored, not personal commentary)
- Authored by: A+ Tutoring Team OR a named expert if appropriate

#### Structure (8-section format for B2B blog)

Each section is target word count, not strict.

**1. Hook + Stakes (~150 words)**
Open with the specific moment, study, or data point that makes this topic urgent. Establish what's at stake for the reader's school or district. NOT "Education is changing." Open with a concrete fact, a study finding, or a specific scenario the reader recognizes.

**2. What's Happening (~200 words)**
The core news or finding. Cite primary sources. Use educator vocabulary appropriately (LTEL, MTSS, Title III, ESSA, etc.). This section establishes credibility . the reader should think "this writer knows what they're talking about."

**3. Why It Matters to You (~200 words)**
Make it specific to the reader's role. What does this mean for a special programs coordinator? A charter director? A district leader? Address their actual concerns: compliance, funding, outcomes, capacity. Name the operational realities they face.

**4. What the Research Actually Says (~250 words)**
Deeper into the data. Pull from authoritative sources (NWEA, Stanford, Brookings, EdSource, CDE). Cite specific studies, sample sizes, methodologies. If the topic is legislative, cite bill text. If the topic is policy, cite primary documents. This section earns the right to make recommendations later.

**5. What's Working (~200 words)**
Evidence-based interventions, models, or approaches that address the problem. **This is where A+ earns the right to mention itself, but don't pitch yet.** Describe the broader category of solutions that work, citing research where possible (high-impact tutoring, MTSS frameworks, MAP-aligned interventions, etc.).

**6. What A+ Sees in the Field (~200 words)**
**This is where A+ leverages its institutional knowledge.** What do A+'s partner schools experience? What does iLEAD Math Tier 3 show (12 students, 9 of 12 with positive growth, +20.8 percentile gain, 17 hours/student)? What does the iLEAD AV combined Tier 3 show (21 students, 17 improved, 81% improvement rate)? Use concrete data with proper attribution. Do NOT make claims A+ can't back up.

**7. What School Leaders Can Do Next (~150 words)**
Practical, actionable steps. Not "contact us." Steps the reader can take regardless of whether they ever talk to A+: review their Title III allocation, audit their LTEL caseload, examine MAP data by subgroup, request specific reports from their authorizer. Make this useful even to readers who never become A+ customers.

**8. About A+ Tutoring (~100 words)**
A short, factual closer about who A+ is and what they do. Not a sales pitch. Tone: "If you'd like to learn more about how A+ approaches this work, here's where to start." Link to the consultation page. ONE call to action, not three.

#### Required components in every blog post

- At least 3 inline data points with sources (linked when possible)
- At least 1 specific A+ outcome citation (iLEAD program data with proper attribution)
- At least 1 quote or named expert reference (Linda Darling-Hammond, Susanna Loeb, NWEA leadership, etc.) properly attributed
- 2-3 inline links to authoritative sources (CDE, NWEA, EdSource, Brookings, etc.)
- 1-2 internal links to other A+ pages (case studies, services, related blog posts)
- ONE clear CTA at the end, not throughout
- Subheadings for skimmability (H2 for major sections, H3 for sub-points)

#### Voice rules (inherited from aplus-b2b-brand-kit)

- Use educator vocabulary appropriately
- Lead with data, support with story
- Treat readers as colleagues, not prospects
- Acknowledge system-level constraints
- NO em dashes
- NO "all students"
- NO AI vocabulary (leverage, delve, harness, foster, fundamentally, streamline)
- NO rule-of-three lists
- NO generic corporate fluff (game-changer, best-in-class, industry-leading)

#### SEO metadata output

Include this header block at the top of the document, formatted for handoff to whoever publishes on HubSpot:

```
---
SEO METADATA . HUBSPOT PUBLICATION READY

url_slug: /[topic-keyword-phrase-hyphenated]
h1_title: [Compelling H1 with primary keyword + specific outcome or finding]
meta_title: [50-60 chars, includes primary keyword + A+ Tutoring]
meta_description: [150-160 chars, includes primary keyword, specific data point, and value to reader]

primary_keyword: [one high-intent keyword from this list, pick the best fit:
  - "high-dosage tutoring"
  - "high-impact tutoring"
  - "Tier 2 intervention California charter"
  - "Tier 3 intervention California charter"
  - "Title III LTEL reclassification"
  - "Title III intervention services"
  - "MAP Growth intervention"
  - "LCFF intervention services"
  - "NCB charter intervention"
  - "Flex-based charter tutoring"
  - "Special programs coordinator resources"
  - "ESSA evidence-based intervention"
]

secondary_keywords: [2-3 related terms used naturally in the body]

internal_links_recommended:
  - /case-study-ilead-math-tier3 [the published case study]
  - /services [the relevant service page]
  - /about-us
  - /consultation
  - Other relevant existing blog posts on the same topic cluster

external_links_cited: [list every external URL referenced in the body]

schema_type: Article
schema_author: A+ Tutoring Team [or specific named author if applicable]
schema_publisher: A+ Tutoring
schema_date_published: [today's date in ISO format]
schema_image: [recommended hero image alt text describing the article topic]

hero_image_alt_text: [Describes the article topic specifically. Example: "A teacher works with a small group of middle school students on math during a Tier 3 intervention session"]

pull_quotes: [List 2-3 lines from the body that should be designed as graphic pull-quotes for sharing]

reading_time: [estimated minutes, typically 5-7 for 1,200-1,500 words]

target_publish_date: [date]
target_promotion: [list of channels where this should be promoted: company LinkedIn, Roman LinkedIn share, Danielle LinkedIn share, parent newsletter, sales toolkit]
---
```

#### First 100 words rule

The first 100 words of the blog post must be liftable as a standalone summary. Google AI Overviews, Perplexity, ChatGPT, and other AI summary tools extract the opening. The opening should:

- Establish the topic specifically
- State the key finding or stakes
- Read as a complete mini-article even if the rest doesn't load
- Include the primary keyword naturally
- Make a school admin want to keep reading

Do NOT bury the lead. Do NOT open with throat-clearing ("In today's educational landscape...").

## Quality gates

Before output is delivered for approval, the agent runs these self-checks:

1. **Word count check.** 1,200-1,500 words.
2. **Source check.** At least 3 inline data points with sources cited.
3. **A+ data check.** At least 1 A+ outcome citation with proper attribution (matches what the published case studies say, NOT inventing figures).
4. **Internal link check.** At least 1 link to another A+ page.
5. **External link check.** At least 2 links to authoritative external sources.
6. **First 100 words check.** Opening reads as a standalone summary, includes primary keyword.
7. **CTA check.** Exactly ONE call to action at the end. No CTAs sprinkled through body.
8. **SEO metadata check.** All required fields filled in the metadata block.
9. **Voice check.** Routes through aplus-b2b-brand-kit voice rules.

If any self-check fails, the agent revises before submitting.

Then routes through:
1. **aplus-fact-check FIRST** (catches factual errors)
2. **aplus-brand-check SECOND** (catches voice/word violations)

If either fails, returns to agent for revision before reaching approval queue.

## Approval gate

Danielle reviews and approves before publication. Approval can be done as a single read-through; not line-by-line edits. If the post needs substantive changes, return to agent with specific direction rather than rewriting in place.

## What this skill does NOT do

- Does NOT generate graphics or images (flag pull quotes for graphic treatment in metadata, but designer or image-gen skill produces graphics)
- Does NOT publish to HubSpot directly (output goes to approval queue, then human publishes)
- Does NOT generate variants (no IG, FB, newsletter adapters from blog post . those are separate skills if needed)
- Does NOT make up data. Every statistic, quote, study citation must be verifiable.
- Does NOT replace Danielle's professional judgment on whether a topic is worth long-form treatment
- Does NOT include client-specific information (use case studies for that)

## Coordination with other skills

- Receives input from: aplus-research (topic + sources), aplus-b2b-brand-kit (the company post for tone reference), optionally roman-voice and danielle-voice op-eds for angle inspiration
- Sends output to: aplus-fact-check first, then aplus-brand-check, then Danielle approval queue
- Reads from: aplus-research target-schools.md (to know which partners might naturally fit in section 6), aplus-fact-check SKILL.md (for correct A+ outcome attributions)

## Frequency

- Default: 1 blog post per week, expanding the strongest LinkedIn topic of that week
- Ad hoc: When a specific event (CARS deadline, conference, major news) creates urgency
- Sales-driven: When Danielle needs a specific topic covered to support a pitch

## Versioning and updates

Blog posts published to HubSpot should be reviewed quarterly and updated when:
- The cited data refreshes (NWEA dashboards, ESSA flags, etc.)
- The cited bills change status (passed, vetoed, amended)
- A+ acquires new case studies that strengthen the argument
- Tier A partners change (a school moves from prospect to partner)

Updates should preserve the URL slug to maintain SEO equity.

## What blog posts become

Each published blog post becomes:
1. **A permanent owned SEO asset** that ranks for the primary keyword over time
2. **A sales tool Danielle can link to in pitches** (e.g., "Here's our perspective on Title III LTEL allocation: [link]")
3. **A reference for future LinkedIn content** (we can quote the blog post in future LinkedIn posts about related topics)
4. **A data point for engagement analysis** (track which topics drive the most blog traffic, repeat that formula)
5. **A trust-builder for organic search visitors** (a school admin Googling the topic finds A+'s perspective alongside the major publications)

## Related skills

- `aplus-research` . source of topics and source material
- `aplus-b2b-brand-kit` . voice, color, and visual rules inherited
- `aplus-fact-check` . QA layer applied first
- `aplus-brand-check` . QA layer applied second
- `roman-voice` . inspiration for conviction-angle blog topics
- `danielle-voice` . inspiration for implementation-angle blog topics
- Future: `aplus-blog-promotion` . skill to chop approved blog post into LinkedIn carousel, parent newsletter snippet, etc.

## Version

v1.0 . Created May 11, 2026
Foundation: Roman's MVP redefinition on May 11, 2026 . "MVP isn't 3 LinkedIn posts, it's one complete journey from research to permanent owned SEO asset." Built to close the gap between content generation and durable owned assets. First test topic: Getting Down to Facts (Stanford, May 7, 2026).

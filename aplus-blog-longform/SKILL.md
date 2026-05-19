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

## Pre-Draft SEO Research Phase

Before drafting any prose, the agent runs a four-step SEO research pass and captures the findings. This phase is mandatory in v1.1 and downstream sections depend on its output.

### Step 1. Call `keyword-research` with the topic's primary keyword

Capture:
- Search volume (monthly searches for the primary keyword)
- Difficulty score (how hard it is to rank)
- Intent classification (informational, commercial investigation, transactional, navigational)
- Related cluster terms (semantic neighbors the article should naturally include)

### Step 2. Call `serp-analysis` with the same keyword

Capture:
- Top 5 ranking pages (URL, title, publisher)
- SERP features present (AI Overviews, Featured Snippet, People Also Ask box, video carousel, image pack)
- Content type and length of the winners (listicle, how-to, opinion, primary research, average word count)

### Step 3. Call `content-gap-analysis` comparing A+ Tutoring to top 3 ranking competitors

Capture:
- Queries A+ does not cover that competitors do
- Topic clusters where A+ has thin coverage relative to the SERP winners
- Specific question phrasings competitors answer that A+ should also answer

### Step 4. Decision gate before drafting

Use the findings from Steps 1, 2, and 3 to refine the topic angle BEFORE drafting. Specifically:
- If `keyword-research` shows the primary keyword has zero search volume or extreme difficulty (score above 80 with no domain authority advantage), flag to Roman and ask whether to pivot to a related keyword from the cluster.
- If `serp-analysis` shows the SERP is dominated by an AI Overview or Featured Snippet, the draft must be structured to compete for that surface (covered in the GEO Optimization Pass below).
- If `content-gap-analysis` surfaces a high-value gap A+ can credibly own, the topic angle should be revised to address that gap.

The agent records all four findings in a "SEO Research Notes" section at the top of the working draft, before any prose. This block is removed before final output but is preserved as an internal artifact.

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

## GEO Optimization Pass

After the first complete draft exists, the agent runs a GEO (Generative Engine Optimization) pass before producing SEO metadata. This phase shapes the draft to maximize the chance of being cited by ChatGPT, Perplexity, Google AI Overviews, Gemini, and Claude.

### Step 1. Call `geo-content-optimizer` on the draft

The agent passes the working draft to `geo-content-optimizer` and applies its recommendations to ensure:

1. **First 100 words must directly answer the primary search query.** If a school admin Googled the primary keyword and only the first 100 words loaded, those 100 words should answer the query as a complete mini-article. No throat-clearing. No "in this article we will explore."

2. **Body must contain at least 2 question-format subheadings.** Question phrasings like "What does Michigan H.B. 5630 require of intervention providers?" match the "People Also Ask" patterns that AI engines extract. The questions should be drawn from the `serp-analysis` step's People Also Ask findings whenever possible.

3. **Named entities must be resolved in their first mention with disambiguating context.** A+ Tutoring, iLEAD, Stanford GSE, NWEA, NSSA, CDE, EdSource, FutureEd, Accelerate, and similar named entities must include enough context that AI engines can disambiguate them. Example: write "A+ Tutoring, a California K-12 virtual intervention provider working with charter schools" the first time, not just "A+ Tutoring." Same rule applies to studies, bills, and acronyms.

4. **Include at least 1 structured comparison or list that AI engines can extract.** A comparison table, a bulleted definition list, a "what works vs. what doesn't" pair, or a numbered set of design principles. AI engines extract these structures preferentially because they map cleanly to citation-ready answer fragments.

### Step 2. Revise the draft based on `geo-content-optimizer` output

The agent applies the recommendations directly to the draft before proceeding to SEO metadata. The revised draft is what flows into the next step.

#### SEO metadata output

In v1.1, SEO metadata is no longer composed by hand from the primary keyword list. Instead, the agent calls two SEO skills and uses their output to populate the metadata block.

### Step 1. Call `meta-tags-optimizer` with the draft

Pass the revised post-GEO draft to `meta-tags-optimizer` and capture 3 A/B variants of each:
- `meta_title` (50 to 60 characters, includes primary keyword and A+ Tutoring)
- `meta_description` (150 to 160 characters, includes primary keyword, a specific data point, and a value statement for the reader)

The agent picks the strongest primary variant for the published metadata block, based on the relevance/CTR ranking that `meta-tags-optimizer` returns. The two losing variants are preserved as A/B candidates for future testing.

### Step 2. Call `schema-markup-generator` with the draft

Pass the revised post-GEO draft to `schema-markup-generator` and generate the actual JSON-LD blocks for:
- **Article schema** (required on every blog post)
- **FAQ schema** (required when the post contains the question-format subheadings introduced during the GEO Optimization Pass)
- **Organization schema for A+ Tutoring** (required on every blog post; identical block across posts)

`schema-markup-generator` returns ready-to-paste JSON-LD. The agent does not hand-write schema in v1.1.

### Step 3. Assemble the metadata block

The final output bundle includes:

1. **The metadata header block** with the chosen primary variants of title and description, plus all required SEO fields:

```
---
SEO METADATA. HUBSPOT PUBLICATION READY (v1.1)

url_slug: /[topic-keyword-phrase-hyphenated]
h1_title: [Compelling H1 with primary keyword + specific outcome or finding]
meta_title: [primary variant from meta-tags-optimizer]
meta_description: [primary variant from meta-tags-optimizer]

primary_keyword: [from keyword-research output]
keyword_search_volume: [from keyword-research output]
keyword_difficulty: [from keyword-research output]
keyword_intent: [from keyword-research output]
secondary_keywords: [cluster terms from keyword-research output]

serp_features_targeted: [from serp-analysis output; e.g. "AI Overview, People Also Ask"]
serp_top_competitors: [top 3 from serp-analysis]
content_gaps_addressed: [from content-gap-analysis output]

internal_links_recommended:
  - /case-study-ilead-math-tier3
  - /services
  - /about-us
  - /consultation

external_links_cited: [every external URL referenced in the body]

schema_type: Article
schema_author: A+ Tutoring Team [or named expert]
schema_publisher: A+ Tutoring
schema_date_published: [today's date in ISO format]

hero_image_alt_text: [topic-specific descriptive text]
pull_quotes:
  - "Verbatim quote 1 from the blog body (15-25 words)"
  - "Verbatim quote 2 from the blog body"
  - "Verbatim quote 3 from the blog body"
inline_pull_quote_images:
  - pull-quote-s1-with-logo.png
  - pull-quote-s2-with-logo.png
  - pull-quote-s3-with-logo.png
carousel_slides:
  - "Slide 2 body text: an insight or data point distilled from the blog (1-2 sentences)"
  - "Slide 3 body text: a second insight or data point"
  - "Slide 4 body text: a third insight or data point"
  - "Slide 5 body text: the CTA line that drives readers to the blog or to Danielle's booking"
reading_time: [estimated minutes]
target_publish_date: [date]
target_promotion: [channels]
on_page_audit_score: [from On-Page Audit phase below]
---
```

The `pull_quotes` list and `inline_pull_quote_images` list MUST be the
same length and ordered to pair (entry N of pull_quotes maps to entry N
of inline_pull_quote_images). The `carousel_slides` list MUST contain
exactly 4 entries. These populate LinkedIn carousel slides 2 through
5 (slide 1 is auto-generated from the blog's hook).

2. **A/B variants block** with the two non-primary `meta_title` and `meta_description` candidates from `meta-tags-optimizer`, for future A/B testing.

3. **JSON-LD schema block** with the Article, FAQ (if applicable), and Organization JSON-LD output from `schema-markup-generator`, ready to paste into HubSpot's structured data field.

## On-Page Audit

After the metadata block and schema are assembled, the agent runs an on-page audit before quality gates.

### Step 1. Call `on-page-seo-auditor` on the final draft + metadata + schema

The auditor returns:
- An overall score (0 to 100)
- A prioritized list of fixes

### Step 2. Apply fixes if the score is below 80

If `on-page-seo-auditor` returns a score below 80, the agent applies the recommended fixes (heading structure, keyword placement, image alt text, internal link density, etc.) and re-runs the audit. This loop repeats until the score is 80 or higher.

### Step 3. Capture the final score

The final on-page audit score is included in the metadata block as `on_page_audit_score`. The score, plus the prioritized-fix list, is also included in the output bundle for Danielle's review.

If the score cannot reach 80 after two revision passes, the agent flags this for Roman or Danielle with a specific note about which fixes were not applicable (e.g. "could not increase internal link density because there are no other A+ blog posts on this topic cluster yet").

#### First 100 words rule

The first 100 words of the blog post must be liftable as a standalone summary. Google AI Overviews, Perplexity, ChatGPT, and other AI summary tools extract the opening. The opening should:

- Establish the topic specifically
- State the key finding or stakes
- Read as a complete mini-article even if the rest doesn't load
- Include the primary keyword naturally
- Make a school admin want to keep reading

Do NOT bury the lead. Do NOT open with throat-clearing ("In today's educational landscape...").

## Required Internal Links and CTA

Every A+ blog post must include the following links where contextually relevant. If the topic does not allow natural inclusion of a link, the agent must flag this and ask before publishing.

### A+ Tutoring approved link library

**Case studies** (cite both when discussing iLEAD outcomes):

- https://wetutorathome.com/case-study-ilead-math-tier3 (75%, 12 students, Math Tier 3)
- https://wetutorathome.com/results/ilead-tier-3-english (87.5%, 8 students, ELA Tier 3)

**Partner school pages:**

- https://wetutorathome.com/ilead-exploration (use when discussing iLEAD or homeschool charter funding)
- https://wetutorathome.com/heartwood-charter-school (use when discussing approved vendor relationships or partner schools)

**Service pages:**

- https://wetutorathome.com/services (use when describing A+ operational model or Tier 2 / Tier 3 instruction)
- https://wetutorathome.com/home-school-tutoring (use when discussing homeschool families)

### Required CTA

Every B2B blog post must close with a CTA linking to Danielle's booking page:

`https://meetings.hubspot.com/successful/danielle-meetings-for-partnerships-programs`

CTA language options (choose based on blog tone):

- "Book a 30-minute conversation with Danielle"
- "Schedule time with Danielle to discuss your school's intervention strategy"
- "Talk to Danielle about how A+ partners with charter schools like yours"

DO NOT use generic CTAs like "request a consultation" or "contact us" that point to the homepage. Always use Danielle's specific booking link.

### Minimum link requirements per blog

- 1 case study link minimum (both if iLEAD discussed)
- 1 partner school page link minimum
- 1 service page link minimum
- 1 Danielle CTA link (required)

If the blog topic genuinely does not allow natural inclusion of partner school or service links, flag this in the output and ask before finalizing.

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
10. **SEO research check (new in v1.1).** Confirms `keyword-research`, `serp-analysis`, and `content-gap-analysis` outputs were captured at the Pre-Draft SEO Research Phase and that the topic angle was informed by their findings. If any of the three step outputs is missing, the gate fails.
11. **GEO optimization check (new in v1.1).** Confirms the GEO Optimization Pass was completed: first 100 words directly answer the primary search query, at least 2 question-format subheadings exist, named entities are disambiguated on first mention, and at least 1 extractable structured comparison or list is present.
12. **On-page audit check (new in v1.1).** Confirms `on-page-seo-auditor` was run on the final draft and the score is 80 or higher. If the score is below 80, the gate fails.

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

v1.3 . Updated 2026-05-19 . Expanded meta schema with three new lists: `inline_pull_quote_images` (parallel to `pull_quotes`, pairs each verbatim quote with its image filename), `carousel_slides` (4 entries for LinkedIn carousel slides 2-5), and an implicit `instagram_post` derivative now produced alongside the 4 existing derivatives. Pull-quote graphic conventions updated to drop date / blog-name / attribution subtitle. Only verbatim quote + A+ logo remain. Graphics pipeline expanded from 8 to 14 graphics per bundle (adds 5 LinkedIn carousel slides, 1 Instagram post, 1 Instagram story, 1 data-visualization creative graphic). HubSpot uploads now use a `{type}-{YYYY-MM-DD}.png` filename convention for idempotent re-runs and clean file-manager history.

v1.2 . Updated 2026-05-15 . Added required internal links library and Danielle booking CTA requirement. Previous versions allowed generic CTAs and incomplete internal linking which weakened both SEO and conversion.

v1.1. Updated May 13, 2026
Integrated 5 new SEO/GEO skills (sourced from aaron-he-zhu/seo-geo-claude-skills) into the blog production pipeline. Added Pre-Draft SEO Research Phase (`keyword-research`, `serp-analysis`, `content-gap-analysis` before drafting). Added GEO Optimization Pass (`geo-content-optimizer` after first draft, before metadata). Replaced static SEO metadata with `meta-tags-optimizer` A/B variants and `schema-markup-generator` JSON-LD output. Added On-Page Audit phase (`on-page-seo-auditor` with 80-score minimum). Added 3 new quality gates (SEO research check, GEO optimization check, on-page audit check). Net effect: blog posts now ship with keyword data, SERP positioning intelligence, GEO-optimized structure, JSON-LD schema, A/B title variants, and a measured on-page score, in addition to the brand-voice and fact-check layers that already existed in v1.0.

v1.0. Created May 11, 2026
Foundation: Roman's MVP redefinition on May 11, 2026. "MVP isn't 3 LinkedIn posts, it's one complete journey from research to permanent owned SEO asset." Built to close the gap between content generation and durable owned assets. First test topic: Getting Down to Facts (Stanford, May 7, 2026).

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

#### Typography rules (v1.5)

The blog post must specify these fonts in the metadata block so the HubSpot CMS template applies them. They are NOT optional and they are NOT the same font for headings and body.

- **Headings (H1, H2, H3):** Playfair Display (serif, expressive, weight 700 for H1 and H2, weight 600 for H3)
- **Body copy:** DM Sans (sans-serif, weight 400 for body, weight 500 for inline emphasis)
- **All headings are capitalized in Title Case minimum.** H1 may be SET IN ALL CAPS if it improves visual weight; H2 and H3 stay Title Case. Lowercase headings are a failure mode and must be flagged.
- **Headings and body must be visually distinct fonts.** A serif heading paired with a sans-serif body is the required pairing. Same-font heading/body or two-serif/two-sans pairings fail this check.
- **Mobile-first layout.** The blog must read cleanly on a phone first, desktop second. That means short paragraphs (3-4 lines on mobile, not 8), pull-quote graphics that scale, no wide tables that force horizontal scroll, and CTAs that hit a usable tap-target on mobile.

The HubSpot draft body must include the Google Font import line at the top of the published HTML (handled by the publish script) so the fonts render in the CMS preview:
```
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
```

#### Title rules (v1.5)

- **NO trailing colons.** The H1, `meta_title`, and `og:title` must NOT end in `:`. Lines like `Title III LTEL Funding:` fail this check. Either drop the colon entirely (`Title III LTEL Funding`) or rewrite the title so the colon falls in the middle (`Title III LTEL Funding: What 2026 Charter Directors Need to Know`).
- A colon mid-title is fine. A colon at the end is never fine.
- This applies in three places: `h1_title`, `meta_title`, and any social-card title text rendered into graphics.

#### Word count
1,200 to 1,500 words. Not shorter (insufficient SEO authority). Not longer (reader drop-off). Sparse articles (under 1,200 words, or 1,200+ words with only transitional content between sections) fail this check. Every section must carry its own weight in actionable information, data, or specifics. Generalizations that could appear in any blog post are filler.

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
**This is where A+ shares its institutional knowledge.** What do A+'s partner schools experience? Use the verified iLEAD outcomes: Math Tier 3 shows 75% (9 of 12 students) reaching growth benchmarks; ELA Tier 3 shows 87.5% (7 of 8 students); Combined Tier 3 shows 80% (16 of 20 students) at 3-6x national MAP Growth benchmarks. **NEVER cite the retired 81% figure.** Use concrete data with proper attribution. Do NOT make claims A+ can't back up.

**7. What School Leaders Can Do Next (~150 words)**
Practical, actionable steps. Not "contact us." Steps the reader can take regardless of whether they ever talk to A+: review their Title III allocation, audit their LTEL caseload, examine MAP data by subgroup, request specific reports from their authorizer. Make this useful even to readers who never become A+ customers. **Required for school audiences (v1.5):** include a 5th action step specifically for administrators and federal program coordinators (e.g., "If you sit on the federal programs side of the budget, here is the one report to pull this month..."). This 5th step makes the article useful to the busy program coordinator who skims to the action list.

**Reflection questions (new in v1.5)**
At one or two strategic points in the body (typically after Section 3 and Section 5), embed a short reflection question that engages the reader's thinking rather than just delivering information. Examples:
- "When was the last time you audited your school's reclassification trajectory by subgroup?"
- "If your Tier 3 cohort were named individually, would the same students appear next year?"

These questions are formatted as a styled callout (italic, indented, or a colored box in the CMS template), not as a body paragraph. They force the reader out of skim mode for a moment.

**8. About A+ Tutoring + Proof Points + CTA (~100 words)**
A short, factual closer about who A+ is and what they do. **Required before the CTA (v1.5):** include a proof-points line citing the verified iLEAD outcomes. Example phrasing: "A+ partner schools have shown 75% of Math Tier 3 students reaching growth benchmarks, 87.5% in ELA Tier 3, and 80% in the combined Tier 3 cohort, at 3-6x national MAP Growth benchmarks." Do NOT use the retired 81% figure. Do NOT invent figures. Use only the published case-study numbers (75% / 87.5% / 80%).

Then a button CTA (see CTA rules below). ONE call to action, not three.

#### Required components in every blog post

- At least 3 inline data points with sources (linked when possible)
- At least 1 specific A+ outcome citation (iLEAD program data with proper attribution: 75% Math Tier 3, 87.5% ELA Tier 3, 80% Combined; never 81%)
- At least 1 quote or named expert reference (Linda Darling-Hammond, Susanna Loeb, NWEA leadership, etc.) **wrapped in proper quotation marks** ("..." for direct quotes; missing quotation marks on direct quotes fails brand-check in v1.2)
- 2-3 inline links to authoritative sources (CDE, NWEA, EdSource, Brookings, etc.)
- 1-2 internal links to other A+ pages (case studies, services, related blog posts)
- **Documentation links (v1.5):** when discussing compliance topics (supplement-not-supplant, Title III allowable uses, ESSA evidence tiers, CSI/ATSI procedures, etc.) link directly to the authoritative federal or state documentation. The reader should be able to verify the compliance claim in one click.
- **Clickable links to further research (v1.5):** every external study, bill, or report cited must be hyperlinked. Bare citations without links fail this check.
- 1-2 reader reflection questions at strategic points (see Section 7 + reflection callout rules)
- ONE clear CTA at the end (button format, audience-specific wording, see CTA rules below), not throughout
- Highlighted important information for busy readers: bold key terms, callout boxes for proof points and reflection questions, pull-quote graphics for the 1-2 strongest sentences
- Subheadings for skimmability (H2 for major sections, H3 for sub-points), all in Title Case minimum

#### Image alt text rules (v1.5)

Every image in the blog (hero, inline pull-quote graphics, infographics) must have alt text that is:
- **Descriptive of what is visually shown**, not just a label. "Mother and child studying together at a kitchen table" passes. "Mother en kid" or "hero image" fails.
- **Natural English**, no shorthand or typos. Brand-check v1.2 will flag broken alt text.
- **Includes the primary keyword naturally where relevant**, but not stuffed.
- **Under ~125 characters** so screen readers don't truncate.

#### Nationally-applicable language (v1.5)

A+ Tutoring serves California first, but the blog is a permanent SEO asset that will be found by school admins in other states. Use nationally-applicable language wherever possible:

- "state English proficiency assessment" instead of "ELPAC prep"
- "state academic standards" instead of "CA CCSS" (unless the post is specifically about CA standards)
- "annual federal Title III allocation" instead of "your Title III allocation per LEA via CDE"
- Spell out the state-specific acronym in parentheses when first used: "California's School Dashboard (the state's annual school accountability rating system)"

This rule applies UNLESS the topic itself is California-specific (e.g., a post about the CA Dashboard or AB 2774). For topics with national reach, default to language a Texas or Florida charter director would also recognize.

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
SEO METADATA. HUBSPOT PUBLICATION READY (v1.5)

url_slug: /[topic-keyword-phrase-hyphenated]
h1_title: [Compelling H1 with primary keyword + specific outcome or finding. NO TRAILING COLON.]
meta_title: [primary variant from meta-tags-optimizer. NO TRAILING COLON.]
meta_description: [primary variant from meta-tags-optimizer]

typography:
  heading_font: Playfair Display
  heading_weights: [600, 700]
  body_font: DM Sans
  body_weights: [400, 500]
  heading_case: Title Case

cta:
  text: [audience-specific button wording, e.g. "Let's Talk About Your School's Intervention Plan"]
  url: https://meetings.hubspot.com/successful/danielle-meetings-for-partnerships-programs
  style: button-orange

proof_points_before_cta: [iLEAD verified outcomes line. e.g. "75% of Math Tier 3 students, 87.5% in ELA Tier 3, 80% combined Tier 3."]

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
inline_pull_quote_images:
  - pull-quote-s1-with-logo.png
  - pull-quote-s2-with-logo.png

# Data viz figures that ship inline in the blog body (added v1.6)
inline_data_viz_images:
  - topic-graphic-with-logo.png
  - preset-stat-graphic-with-logo.png
inline_data_viz_anchors:
  - "exact substring from the prose where the topic graphic should appear after"
  - "exact substring from the prose where the preset stat graphic should appear after"
inline_data_viz_alt_topic-graphic-with-logo: Descriptive alt text for the topic-specific data viz.
inline_data_viz_alt_preset-stat-graphic-with-logo: A+ Tutoring iLEAD 2024-25 Tier 3 outcomes. 75 percent Math (12 students, 9 improved), 87.5 percent ELA (8 students, 7 improved), 80 percent Combined (20 students, 16 improved).
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

### Required CTA (updated in v1.5)

Every B2B blog post must close with a **BUTTON CTA** (not a plain text link) linking to Danielle's booking page:

`https://meetings.hubspot.com/successful/danielle-meetings-for-partnerships-programs`

**Button format requirements:**
- Rendered as an HTML button or styled `<a>` with button styling (A+ Orange background, white text, Playfair Display or DM Sans semibold, generous padding, mobile tap-target ≥ 44px height)
- Centered or left-aligned in its own paragraph, not inline with body text
- Appears AFTER the proof-points line (see Section 8) and ONLY at the end of the post

**Audience-specific wording (required in v1.5):**

The CTA wording must be specific to the article topic AND the audience. Generic CTAs like "Book My Free Consultation" or "Request a Consultation" fail this check.

For **school admin / charter director** audiences, choose wording that names the audience's actual problem:
- "Let's Talk About Your School's Intervention Plan"
- "Map Your Title III Allocation With Danielle"
- "Walk Your Dashboard Data With Our Team"
- "Build Your CSI Intervention Layer With A+"
- "See How A+ Partners With Charter LEAs Like Yours"

For **parent / family** audiences (B2C blog variants):
- "Get Your Child the Support They Need"
- "Find Out If A+ Is Right For Your Family"
- "Talk to A+ About Your Child's Reading Plan"

The wording must reference the article's topic OR the reader's audience role. CTAs that could be pasted unchanged onto any post on the site fail this check.

DO NOT use generic CTAs that point to the homepage. Always use Danielle's specific booking link.

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
13. **Typography check (new in v1.5).** Confirms the metadata block specifies Playfair Display headings and DM Sans body. Heading-font equals body-font fails. All-lowercase headings fail.
14. **Title colon check (new in v1.5).** Confirms `h1_title` and `meta_title` do NOT end in `:`. Mid-title colons are OK.
15. **CTA specificity check (new in v1.5).** Confirms the CTA wording is audience-specific (mentions school, intervention, Title III, Dashboard, parent, child, family, etc.) and is rendered as a button. Generic "Book My Free Consultation" or "Request a Consultation" fails.
16. **Proof-points check (new in v1.5).** Confirms the proof-points line appears immediately before the CTA and cites verified iLEAD outcomes (75% / 87.5% / 80%). Use of 81% fails.
17. **Retired figure check (new in v1.5).** Confirms 81% does not appear anywhere in the body. "21 students" (the retired combined sample) also fails.
18. **Quotation marks check (new in v1.5).** Every direct quote from a named expert is wrapped in proper quotation marks. Bare quoted text fails.
19. **Alt-text check (new in v1.5).** Every image has descriptive natural-English alt text. Broken alt text ("Mother en kid"), missing alt text, or label-only alt text ("hero image") fails.
20. **Reflection-question check (new in v1.5).** At least 1 reflection question for the reader appears in the body, formatted as a styled callout.
21. **5th-action-step check (new in v1.5).** For school-audience posts, Section 7 includes a 5th action step specifically for administrators or federal program coordinators.

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

## HubSpot SEO Properties (new in v1.7)

`scripts/publish-to-hubspot.py` now sets these HubSpot blog post properties on every draft via the `POST /cms/v3/blogs/posts` API. Each property has a meta-file source field and a sensible default; the `featuredImageAltText` property is REQUIRED (the publisher fails if missing).

| HubSpot property | Meta source field | Default | Notes |
|---|---|---|---|
| `htmlTitle` | `html_title:` | falls back to `meta_title`, then display title | The `<title>` tag for SEO. Often shorter and keyword-focused; can differ from the display title shown on the post page. |
| `linkRelCanonicalUrl` | `canonical_url:` | auto-built as `https://blog.wetutorathome.com/{slug}` | Duplicate-content control. Always set on every post. |
| `featuredImageAltText` | `hero_alt_text:` (also accepts legacy `hero_image_alt_text:`) | **REQUIRED — publisher fails if missing or < 10 chars** | Accessibility + image SEO. No more empty alt text or label-only alt ("hero image"). |
| `tagIds` | `tag_ids:` (list) | `[]` | Topic clustering. Empty list is fine while we are not yet using topic clusters. |
| `campaign` | `campaign_uuid:` | `None` | HubSpot marketing campaign UUID for attribution. Optional. |
| `headHtml` | `schema_markup:` literal block OR auto-extracted from `\`\`\`json` fenced blocks in the meta file | `""` (warning logged) | JSON-LD schema injected into the `<head>`. Primary lever for AI Overview citation. |
| `metaKeywords` | `keywords:` list (comma-joined) — falls back to `primary_keyword` + `secondary_keywords` list | `""` | Focus + secondary keywords. Lower-weight signal in 2026 but still indexed. |
| `language` | `language:` | `"en"` | Locale code. |
| `categoryId` | `category_id:` | `None` | Blog category. Optional. |

### What these properties contribute to

- **Search engine ranking:** `htmlTitle`, `linkRelCanonicalUrl`, `headHtml` schema
- **AI Overview citation:** `headHtml` JSON-LD schema markup is the #1 lever for getting cited by ChatGPT, Perplexity, Google AI Overviews, Claude, Gemini
- **Accessibility:** `featuredImageAltText`
- **Topic clustering:** `tagIds`
- **Marketing attribution:** `campaign`
- **Internationalization:** `language`

### Required meta file schema (v1.7)

Every weekly bundle's `blog-anchor-meta.md` must contain (inside the first fenced ` ``` ` block unless noted):

```
h1_title: Display title shown on the post page (NO trailing colon)
html_title: Shorter SEO title for <title> tag (often "{topic} | A+ Tutoring", NO trailing colon)
meta_title: A/B variant of htmlTitle picked by meta-tags-optimizer
url_slug: /blog-url-slug-hyphenated
canonical_url: https://blog.wetutorathome.com/blog-url-slug-hyphenated
meta_description: 150-160 char description with primary keyword
hero_alt_text: Descriptive natural-English alt text for the hero image (>=10 chars, no "Mother en kid")
language: en
campaign_uuid: null
category_id: null

primary_keyword: focus keyword phrase
keyword_search_volume: 320
keyword_difficulty: 38
keyword_intent: informational
secondary_keywords:
  - cluster term 1
  - cluster term 2
keywords:           # serialized to HubSpot metaKeywords comma-joined
  - focus_keyword
  - secondary_term_1
  - secondary_term_2

tag_ids: []         # leave empty if not yet using topic clusters
typography:
  heading_font: Playfair Display
  body_font: DM Sans

cta:
  text: Audience-specific button copy (NOT generic)
  url: https://meetings.hubspot.com/successful/danielle-meetings-for-partnerships-programs
  style: button-orange

proof_points_before_cta: 75% Math Tier 3, 87.5% ELA Tier 3, 80% Combined ...

pull_quotes:
  - "Verbatim quote 1 from blog body"
  - "Verbatim quote 2 from blog body"
inline_pull_quote_images:
  - pull-quote-s1-with-logo.png
  - pull-quote-s2-with-logo.png

inline_data_viz_images:                 # v1.6
  - topic-graphic-with-logo.png
  - preset-stat-graphic-with-logo.png
inline_data_viz_anchors:
  - "exact substring from prose for topic graphic insertion point"
  - "exact substring from prose for preset stat graphic insertion point"

carousel_slides:
  - "Carousel slide 2 body"
  - "Carousel slide 3 body"
  - "Carousel slide 4 body"
  - "Carousel slide 5 CTA body"

reading_time: 6 minutes
target_publish_date: YYYY-MM-DD
on_page_audit_score: 90
```

Then OUTSIDE the fenced block, the JSON-LD schema markup. Either form is accepted by the publisher:

**Form A (preferred):** explicit literal block at top level:
```
schema_markup: |
  <script type="application/ld+json">
  {"@context": "https://schema.org", "@type": "Article", ...}
  </script>
  <script type="application/ld+json">
  {"@context": "https://schema.org", "@type": "FAQPage", ...}
  </script>
```

**Form B (backward compatible):** multiple ` ```json ` fenced blocks under a "JSON-LD schema block" heading. The publisher auto-wraps each in `<script type="application/ld+json">...</script>` tags.

## Schema markup generation (v1.7)

After the blog body is drafted, the agent generates JSON-LD schema markup and writes it into the meta file. Preferred path:

1. **Call the `schema-markup-generator` community skill** (sourced from `aaron-he-zhu/seo-geo-claude-skills`, installed alongside the other SEO skills in v1.1). Pass the draft blog body and the SEO metadata block. The skill returns one or more ready-to-paste JSON-LD blocks.

2. **Save the output under `schema_markup:` in the meta file** so the publisher can read it. The minimum schema set per blog is:
   - `Article` (always)
   - `FAQPage` (when the blog body contains question-format subheadings or reflection questions that map to Q&A pairs)
   - `Organization` for A+ Tutoring (always; the block is identical across posts)
   - `HowTo` (only when the body contains a numbered step-by-step procedure)

### Fallback Article template

If `schema-markup-generator` is unavailable, fall back to this manual `Article` template, populated from the meta fields:

```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{h1_title}",
  "description": "{meta_description}",
  "image": "{featured_image_url}",
  "datePublished": "{schema_date_published}",
  "dateModified": "{schema_date_published}",
  "author": {
    "@type": "Organization",
    "name": "A+ Tutoring",
    "url": "https://wetutorathome.com"
  },
  "publisher": {
    "@type": "Organization",
    "name": "A+ Tutoring",
    "logo": {
      "@type": "ImageObject",
      "url": "https://wetutorathome.com/hs-fs/hubfs/Logo.png"
    }
  }
}
```

Pair the Article block with an Organization block (sameAs the canonical channel URLs from `aplus-b2c-brand-kit` v1.2) and a FAQPage block built from the blog's reflection questions or any question-format subheadings.

## LinkedIn posting workflow (new in v1.10)

LinkedIn's algorithm de-prioritizes posts that contain external URLs in the body (the system reads them as "leaving the platform" signals). Links posted as the **first comment** on a self-authored post get 2-3x more reach than the same links in the body. The weekly engine's LinkedIn derivatives are now structured around this rule.

### Required two-section split

Every LinkedIn derivative (`linkedin-company.md`, `roman-oped.md`, `danielle-oped.md`) is split into two clearly labeled sections:

```markdown
## SECTION 1: POST BODY
(paste this in the LinkedIn post text field)

[150-250 words. Hook in the first line. NO blog URL in this section. NO
"link in comments" text. Carousel slide 5 already says "Link in comments"
so the reader knows where to find it. End with a strong CTA that doesn't
include a URL — an action prompt or a direct question to the reader.]

## SECTION 2: FIRST COMMENT
(paste this as the first comment on your own post — gets 2-3x more reach
than URL in body)

Full article here →
{predicted_blog_url}
```

### Why this matters

- **Body URL = penalty.** LinkedIn's algorithm reads outbound URLs in the post body as a signal to suppress reach.
- **First-comment URL = no penalty.** Self-comments are treated as engagement, not as link-out signals. The first comment shows up high in the comment stack and is visible to readers without expanding.
- **Visual cue is already in the carousel.** Slide 5 of the LinkedIn carousel says "Read the full post" with the URL `blog.wetutorathome.com` rendered visually. Readers know to look in comments.

### Rules per LinkedIn channel

| Derivative | Section 1 body | Section 2 first comment |
|---|---|---|
| `linkedin-company.md` (A+ Tutoring company page) | 150-250 words, no URL | URL + "Full article here →" |
| `roman-oped.md` (Roman personal LinkedIn) | 80-150 words, no URL, peer-close ending | URL + "Full article here →" |
| `danielle-oped.md` (Danielle personal LinkedIn) | 120-220 words, no URL, walk-through-invite ending | URL + "Full article here →" |
| `facebook.md` (Facebook page) | **URL stays in body** — Facebook's algorithm does NOT penalize outbound URLs the way LinkedIn does | n/a |
| `instagram-story-3.md` | Link sticker (added in Instagram itself) | n/a |

### Slack delivery integration

`scripts/deliver-to-slack.py` ships the LinkedIn company / Roman / Danielle pieces with the .md file's full body (sections preserved). The LinkedIn carousel piece body_text now includes the 5-step posting workflow:

1. Copy SECTION 1 text into the post field
2. Upload all 5 carousel slides
3. Click Post
4. Immediately add SECTION 2 (blog URL) as the first comment
5. Slide 5 already shows "Link in comments" so readers know where to look

### Backward compatibility

Existing single-body LinkedIn .md files (pre-v1.10) are still accepted by `deliver-to-slack.py` — the script shows whatever the file contains. The v1.10 two-section format becomes the standard for new bundles.

## Version

v1.10 . Updated 2026-05-20 . LinkedIn derivatives (`linkedin-company.md`, `roman-oped.md`, `danielle-oped.md`) now use a two-section format: Section 1 = post body with no URL, Section 2 = first-comment text with the predicted blog URL. Aligns with LinkedIn algorithm behavior (links in first comment get 2-3x reach vs links in body). Facebook keeps URL in body (Facebook algorithm doesn't penalize outbound links). Slack delivery's LinkedIn carousel piece now includes the 5-step posting workflow in its body_text. Documented in new "LinkedIn posting workflow" section.

v1.9 . Updated 2026-05-20 . Added `predicted_blog_url:` to the meta schema. Constructed deterministically from `url_slug:` as `https://blog.wetutorathome.com/{slug}` and available BEFORE the HubSpot publish step. Used by `scripts/deliver-to-slack.py` (header link, IG Story Frame 3 piece body) and any other pre-publish reference. Companion bumps: aplus-graphic-prompts v2.2 -> v2.3 (Frame 3 placeholder removed, logo composite halo eliminated, aspect-ratio preserved).

v1.8 . Updated 2026-05-20 . Replaced the Instagram feed-post derivative (1080x1080 square photo) with a 3-frame Instagram Story sequence (1080x1920 each: Hook, Key Insight, CTA-with-link-sticker-placement). Weekly bundle derivative count remains 4 social pieces (LinkedIn company, Roman op-ed, Danielle op-ed, Facebook) plus the 3-frame IG story. New meta schema field `instagram_story_frames:` (3 entries) + optional `instagram_story_subheads:`. Hard rule from `aplus-b2c-brand-kit` v1.3 + `aplus-graphic-prompts` v2.2: NO AI-generated people on stories. The @aplustutoring grid stays curated separately for evergreen B2C content. Builder: `scripts/build-instagram-stories.py`. Slack delivery ships the 3 frames as a single labeled gallery piece replacing the prior "Instagram post" piece.

v1.7 . Updated 2026-05-20 . Added HubSpot SEO properties to the meta schema and publisher API payload: html_title, hero_alt_text (REQUIRED), canonical_url, keywords (list), tag_ids, campaign_uuid, schema_markup, language, category_id. Publisher now sets all of these via `POST /cms/v3/blogs/posts` (htmlTitle, linkRelCanonicalUrl, featuredImageAltText, tagIds, campaign, headHtml, metaKeywords, language, categoryId). JSON-LD schema markup injected via headHtml is the primary lever for AI Overview citation (ChatGPT, Perplexity, Google AI Overviews). Schema-markup-generator community skill is the preferred source; manual Article + FAQPage + Organization template is the fallback. Bump from v1.6 — the same-day v1.6 from earlier today added the inline data-viz embed schema and corrected the HubSpot edit URL form, both retained in v1.7.

v1.6 . Updated 2026-05-20 . Two changes after the first two runs:

1. **Preset stat graphic AND topic graphic now ship inline in every blog body**, not only in the Slack delivery gallery. The meta schema gains two new parallel lists:
   - `inline_data_viz_images:` filenames (preset-stat-graphic-with-logo.png and topic-graphic-with-logo.png at minimum)
   - `inline_data_viz_anchors:` parallel list of anchor text snippets from the blog prose (the figure inserts after the paragraph containing the anchor)
   Plus optional `inline_data_viz_alt_{stem}:` one-liner alt text per figure.
   
   Standard placement: preset stat graphic anchors on the paragraph that introduces the iLEAD 75/87.5/80 outcomes in Section 6 (What A+ Sees in the Field). Topic graphic anchors on the paragraph that most directly supports the visualization (state-listing paragraph, timeline-introduction paragraph, etc.).
   
   Enforced by `scripts/embed-pull-quotes.py` which now processes both pull-quote and data-viz figures from the meta.

2. **HubSpot edit URL format corrected.** All scripts that compose an edit URL (publish-to-hubspot.py, deliver-to-slack.py, embed-pull-quotes.py) now use the format `https://app.hubspot.com/blog/{PORTAL_ID}/editor/{post_id}/content`. The earlier `/edit/{post_id}` form pointed to a non-functional page.

v1.5 . Updated 2026-05-19 . Applied Danielle's feedback: typography rules (Playfair Display headings, DM Sans body, capitalized headings, visually distinct fonts for headers vs body), no trailing colons on titles/meta titles/og:titles, button CTAs with audience-specific wording (not generic), proof points before the CTA citing verified iLEAD outcomes (never 81%), quotation marks required when quoting people, nationally-applicable language (state English proficiency assessment vs ELPAC prep), documentation/resource links for compliance topics, clickable links to all external research, reflection questions for the reader at strategic points, 5th action step specifically for administrators/federal program coordinators in school audiences, descriptive natural-English image alt text (no "Mother en kid" type errors), content-density requirement (no sparse articles), mobile-first responsive layout, expanded meta schema with typography + cta + proof_points_before_cta fields.

v1.4 . Updated 2026-05-19 . Replaced the single `creative-graphic` slot with a two-graphic system: a `preset-stat-graphic` (verbatim copy of `aplus-b2b-brand-kit/ilead-outcomes-graphic.png`, the deterministic matplotlib-built iLEAD outcomes data viz, refreshed only when underlying data changes) plus a `topic-graphic` (AI-generated, topic-specific data viz or infographic for that week's blog). The preset is brand-canonical, the topic graphic is bundle-specific. Both ship in every weekly bundle and both appear in the Slack delivery's Blog assets gallery. Added requirement that every bundle ends with auto-generation of `qa-checklist.md` via `scripts/build-qa-checklist.py`. The checklist is a markdown file that Roman and Danielle walk through before publishing, covering blog gates, graphic gates, voice gates, and human sign-off lines. Bundle is NOT marked ready-to-publish until every box in qa-checklist.md is checked.

v1.3 . Updated 2026-05-19 . Expanded meta schema with three new lists: `inline_pull_quote_images` (parallel to `pull_quotes`, pairs each verbatim quote with its image filename), `carousel_slides` (4 entries for LinkedIn carousel slides 2-5), and an implicit `instagram_post` derivative now produced alongside the 4 existing derivatives. Pull-quote graphic conventions updated to drop date / blog-name / attribution subtitle. Only verbatim quote + A+ logo remain. Graphics pipeline expanded from 8 to 14 graphics per bundle (adds 5 LinkedIn carousel slides, 1 Instagram post, 1 Instagram story, 1 data-visualization creative graphic). HubSpot uploads now use a `{type}-{YYYY-MM-DD}.png` filename convention for idempotent re-runs and clean file-manager history.

v1.2 . Updated 2026-05-15 . Added required internal links library and Danielle booking CTA requirement. Previous versions allowed generic CTAs and incomplete internal linking which weakened both SEO and conversion.

v1.1. Updated May 13, 2026
Integrated 5 new SEO/GEO skills (sourced from aaron-he-zhu/seo-geo-claude-skills) into the blog production pipeline. Added Pre-Draft SEO Research Phase (`keyword-research`, `serp-analysis`, `content-gap-analysis` before drafting). Added GEO Optimization Pass (`geo-content-optimizer` after first draft, before metadata). Replaced static SEO metadata with `meta-tags-optimizer` A/B variants and `schema-markup-generator` JSON-LD output. Added On-Page Audit phase (`on-page-seo-auditor` with 80-score minimum). Added 3 new quality gates (SEO research check, GEO optimization check, on-page audit check). Net effect: blog posts now ship with keyword data, SERP positioning intelligence, GEO-optimized structure, JSON-LD schema, A/B title variants, and a measured on-page score, in addition to the brand-voice and fact-check layers that already existed in v1.0.

v1.0. Created May 11, 2026
Foundation: Roman's MVP redefinition on May 11, 2026. "MVP isn't 3 LinkedIn posts, it's one complete journey from research to permanent owned SEO asset." Built to close the gap between content generation and durable owned assets. First test topic: Getting Down to Facts (Stanford, May 7, 2026).

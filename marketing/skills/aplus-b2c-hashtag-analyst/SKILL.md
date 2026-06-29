---
name: aplus-b2c-hashtag-analyst
description: >
  Per-post research and caption builder for A+ Tutoring B2C case studies. Reads the published case study draft, identifies its specific topic themes (math recovery, parent voice, homeschool, grade level, etc.), web-searches for currently-trending Instagram hashtags in those topics from the last 30 days, and writes 5 final hashtags plus ready-to-paste Instagram, Instagram Story, and Facebook captions into metadata.md. Use this skill after a case study draft is complete and BEFORE the Slack delivery step ships graphics to Paola. Hashtags are researched fresh per case study, not pulled from a static library, because hashtag relevance decays fast.
---

# A+ Tutoring B2C Hashtag Analyst

## CRITICAL: Auto-start on load

When this skill triggers, go straight to Step 1. Do not explain what hashtag research is. Do not preview the schema.

## Prerequisites

This skill needs live web search to find currently-trending hashtags. Use this order of preference:

1. **Claude for Chrome extension** (preferred for live IG/TikTok feed scrolling)
2. **WebSearch + WebFetch tools** (acceptable, less thorough but works for trending topic discovery)
3. **Static hashtag library at `marketing/data/b2c-hashtags.md`** (last resort, if no web search available)

Pick the best available path and continue.

## Step 1. Read the case study

Read these files from the bundle directory:

1. `case-study-{pseudonym}.md` (the published case study draft)
2. `metadata.md` (existing meta fields: hero_alt_text, h1_title, pull_quotes, etc.)

Extract:
- **Student grade level** (e.g., "9th grade")
- **Subject area** (e.g., "algebra", "math recovery", "reading", "writing")
- **Story type** (e.g., "post-COVID learning loss", "confidence recovery", "homeschool support")
- **Parent voice quotes** (e.g., the "joy kick in" line)
- **School context** (charter, public, homeschool)

These are the topic themes that drive the hashtag research.

## Step 2. Web-search for currently-trending hashtags

Run these searches one by one. For each, look for hashtags that are CURRENTLY active (last 30 days) on Instagram, NOT generic forever-evergreen hashtags.

### 2a. Topic-anchored searches

For each topic theme identified in Step 1, search:

- `[topic] instagram hashtag trending 2026`
- `[grade level] [subject] parent instagram`
- `[topic] homeschool instagram`

Example for Gabriela (9th grade algebra recovery, homeschool charter):
- `9th grade math instagram hashtag trending`
- `algebra homeschool parent instagram`
- `math recovery student instagram hashtag`
- `COVID learning loss parent instagram`

### 2b. Parent-audience searches

For B2C, the audience is parents (especially mothers). Search:

- `homeschool mom instagram hashtag 2026`
- `parenting [grade] student hashtag instagram`
- `school recovery mom community instagram`

### 2c. Topic-specific journey searches

For each case study angle, search:

- `student progress instagram hashtag`
- `[subject] tutoring instagram parent`
- `child learning journey instagram`

### 2d. Verification

For each candidate hashtag, verify:

1. Has the hashtag been used in the last 30 days? (search the tag on Instagram, look at the "recent" tab)
2. Is the volume meaningful (5,000+ posts) but not so high it's dead (e.g., #parenting at 50M is just noise)?
3. Does it match the audience A+ wants to reach (parents of K-12 students, especially charter homeschool families)?

Exclude any hashtag that:
- Has not been used in the last 30 days
- Has fewer than 1,000 total posts (too obscure)
- Has more than 10,000,000 total posts (too generic, post will get buried)
- Is spammy or off-brand (e.g., #blessed, #grateful)

## Step 3. Build the 5-hashtag block

Per Roman's directive (May 27, 2026): every case study gets exactly 5 hashtags in this schema:

| # | Type | Source | Example |
|---|---|---|---|
| 1 | Solid (trending) | Topic match + last-30-day trending | #homeschoolmath |
| 2 | Solid (trending) | Audience match + last-30-day trending | #charterschoolmom |
| 3 | Solid (trending) | Specific case angle + last-30-day trending | #mathrecovery |
| 4 | Brand voice | A+ Tutoring core message | #everychildcanlearn |
| 5 | Roman voice | Roman's editorial angle | #builtoneverysmallwin |

The first 3 are SEO/discovery plays. Hashtags 4 and 5 are brand-building plays — they DON'T need to be trending. They reinforce A+ Tutoring's identity.

### Brand voice hashtag library (HASH 4)

Use one of these for the brand voice slot, picking the one that best matches the case study's angle:

- `#everychildcanlearn` (default, general A+ ethos)
- `#tutoringthatworks` (data-driven cases)
- `#beyondthegrade` (cases that go beyond test scores)
- `#confidenceinclass` (confidence-building cases)
- `#themathstoryaplus` (math-specific cases)
- `#thereadingstoryaplus` (reading-specific cases)

### Roman voice hashtag library (HASH 5)

Use one of these for the Roman voice slot, picking the one that best matches the case study's lesson:

- `#builtoneverysmallwin` (default, Roman's "small steady wins" thesis)
- `#fixthefoundation` (foundational skills cases)
- `#thelongroadworks` (mid-recovery, honest cases like Gabriela)
- `#charterschoolworks` (charter-specific cases)
- `#parentsknowit` (parent-voice-led cases)

## Step 4. Write Instagram caption

Draft an Instagram caption with this structure:

### Line 1: HOOK (one sentence, scroll-stopping)

Use one of the case study's strongest verbatim quotes or a question that stops the scroll. Per the grammar gate rule, the hook must be a complete grammatical sentence. Examples:

- "I saw her joy kick in."
- "What if math could feel like hers again?"
- "She used to love math. Then she stopped saying that."

### Lines 2-3: BODY (40-60 words, parent-relatable tone)

In Paola's voice if `voice.md` for Paola exists. Otherwise: warm, parent-relatable, NOT corporate. The body summarizes the case study WITHOUT spoiling the ending. It should make a parent want to read more.

Tone guidance:
- Use "her" and "she" (the student is the subject)
- Reference "her mom" or "the parent" (NOT "the mother" — too clinical)
- Use specific details (9th grade, algebra, three months) over abstractions ("over time")
- One sentence about the CHANGE that happened
- One sentence about WHY this story matters to other parents reading

### Line 4: CTA (one line)

"Read Gabriela's full story. Link in bio."

The pseudonym (Gabriela, not the real name) is what appears in the CTA.

### Line 5: BLANK LINE

### Lines 6-10: HASHTAGS (5 hashtags from Step 3, one per line)

Format:

```
#hashtag1
#hashtag2
#hashtag3
#hashtag4
#hashtag5
```

Hashtags are on separate lines because Instagram's algorithm reads them better that way (per 2026 IG SEO research) AND because it's easier to skim/edit.

## Step 5. Write Instagram Story captions

The IG Story is 3 frames. Each frame already has its own text rendered on the graphic. The caption is what goes in the Instagram Story TEXT field when posting (which appears as overlay text alongside the graphic).

For most cases, the caption per frame is empty (let the graphic carry the message). The exception: Frame 3 (CTA) gets a caption like:

```
Tap to read Gabriela's story →
```

## Step 6. Write Facebook caption

Facebook captions can be longer than IG (no character limit pressure). Structure:

### Paragraph 1: Hook (2 sentences)
Same hook as IG, but with one supporting sentence that gives context.

### Paragraph 2: Body (3-5 sentences, 80-120 words)
The fuller story arc, in Paola voice. References the parent (Camila), the case (math recovery), and the outcome (steady progress).

### Paragraph 3: CTA
"Read the full case study at blog.wetutorathome.com/case-study/{pseudonym}-{school-slug}"

The full URL is on Facebook because FB doesn't have "link in bio" — direct links work.

### NO hashtags on Facebook
FB algorithm de-prioritizes posts with hashtags. Skip them entirely.

## Step 7. Write to metadata.md

Append the following fields to the bundle's `metadata.md` (or update existing fields):

```
## Instagram caption (from aplus-b2c-hashtag-analyst)

instagram_caption: |
  [HOOK]

  [BODY]

  Read Gabriela's full story. Link in bio.

  #hashtag1
  #hashtag2
  #hashtag3
  #hashtag4
  #hashtag5

## Instagram Story captions (one per frame, from aplus-b2c-hashtag-analyst)

instagram_story_captions:
  - ""
  - ""
  - "Tap to read Gabriela's story →"

## Facebook caption (from aplus-b2c-hashtag-analyst)

facebook_caption: |
  [HOOK PARAGRAPH]

  [BODY PARAGRAPH]

  Read the full case study at blog.wetutorathome.com/case-study/{pseudonym}-{school-slug}

## Hashtag research log (transparency for Roman)

hashtag_research_notes:
  - "#hashtag1 — trending up in past 30 days, [N] posts total, audience match: [explanation]"
  - "#hashtag2 — [same format]"
  - "#hashtag3 — [same format]"
  - "#hashtag4 — brand voice slot: [why this brand hashtag matches this case]"
  - "#hashtag5 — Roman voice slot: [why this Roman hashtag matches this case]"
```

The `hashtag_research_notes` field exists so Roman can spot-check the research and ditch hashtags that look wrong.

## Step 8. Output to user

After writing to metadata.md, print to stdout:

```
=== B2C captions + hashtags ready for [pseudonym] case study ===

[Show the IG caption block in full]

[Show the FB caption block in full]

Hashtags chosen:
1. #hashtag1 — trending, [audience match note]
2. #hashtag2 — trending, [audience match note]
3. #hashtag3 — trending, [audience match note]
4. #hashtag4 — brand voice
5. #hashtag5 — Roman voice

Written to: marketing/aplus-content/{bundle}/metadata.md

Next step: Slack delivery picks these up automatically.
```

## Rules

- Hashtags are researched FRESH per case study. Never copy from previous cases unless verified still-trending.
- Maximum 5 hashtags per IG post. Per Roman's directive — 3 solid + 1 brand + 1 Roman voice. No exceptions.
- Zero hashtags on Facebook.
- Grammar gate applies — every quote, hook, and caption must read as complete grammatical sentences. A tutoring company never ships broken grammar.
- IG caption uses the case study's STRONGEST verbatim quote as the hook when available.
- Body uses pseudonyms (Gabriela, Camila), NEVER real names.
- Roman voice hashtags are Roman's — never claim they're a parent's voice.
- All output is honest. Honest case studies, honest captions. Mid-recovery story, mid-recovery caption.
- No em dashes anywhere.
- No straight ASCII quotes (`"`) in captions — use curly quotation marks if quoting.

## Version

v1.0 (2026-05-27). Initial draft. Modeled on charlie947/niche-research + charlie947/hook-generator patterns. Adapts the "research fresh per piece" architecture for A+ Tutoring B2C case studies. Researches hashtags per-case rather than relying on a static library. Output structure: 5 hashtags (3 trending + 1 brand voice + 1 Roman voice) + IG caption + IG Story captions + FB caption, all written to metadata.md for downstream Slack delivery to pick up.

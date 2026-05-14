---
name: aplus-graphic-prompts
description: Take an approved blog post and produce a complete graphics package - hero image prompts, social card specs, LinkedIn carousel structure, pull quote graphics, and Facebook image prompts. Outputs both image gen API prompts (Midjourney, DALL-E, Imagen, Adobe Firefly format) AND Canva-ready specifications for manual execution. Use this skill after a blog post is approved through aplus-blog-longform v1.1+.
---

# A+ Graphic Prompts Skill

## Purpose

Close the gap between text content production and visual content. Every approved blog post in v1.5+ goes through this skill to produce a complete visual package ready for image generation OR Canva manual production.

This skill does NOT generate images directly. It produces specifications and prompts. The user (or a future agent with image generation capability) executes the prompts to produce the actual visuals.

## When to apply

Run this skill AFTER:
1. Blog post passes aplus-blog-longform v1.1 quality gates (fact-check + brand-check)
2. Blog post is approved by user
3. Social derivatives (LinkedIn, op-eds, Facebook) are produced

Run this skill BEFORE:
1. Blog post is published to HubSpot
2. Social posts are scheduled or published

## Input requirements

Required inputs:
1. The approved blog post (full markdown text)
2. The blog post's meta description and target keyword
3. Suggested pull quotes from blog's meta file
4. The 4 social derivatives (LinkedIn, Roman op-ed, Danielle op-ed, Facebook)

Optional inputs:
1. Specific image gen tool the user prefers (defaults to multi-tool output)
2. Specific Canva template the user has (defaults to generic specs)
3. Preference for AI imagery vs. stock vs. mixed

## Brand visual standards

### A+ Tutoring Color Palette

Use these exact hex codes in all specs:

**Primary (B2B - school admin audience):**
- A+ Navy: #1A3A52 (primary backgrounds, dark text on light)
- A+ Orange: #EF5829 (accent, CTAs, headlines)
- White: #FFFFFF (backgrounds, text on dark)
- Charcoal: #2D2D2D (body text)

**Secondary (B2C - parent audience):**
- A+ Orange: #EF5829 (primary backgrounds, primary CTAs)
- Warm Cream: #FFF8F0 (backgrounds)
- Deep Navy: #1A3A52 (text accent)
- Soft Coral: #F4A989 (highlights)

**Never use:**
- Pure black (#000000) - too harsh, use Charcoal
- Pure red - use A+ Orange
- Bright colors not in the palette (no neon, no rainbow)
- Stock corporate blue (#0077B5) - LinkedIn's color, not ours

### Typography

**Headings:** Sans-serif, bold weight. Modern, slightly condensed. Examples: Inter Bold, Manrope Bold, Söhne Bold.

**Body:** Sans-serif, regular weight. Highly readable. Examples: Inter Regular, IBM Plex Sans Regular.

**Never use:** Comic Sans, Papyrus, anything decorative, any serif typeface for headlines.

### Photography style

CRITICAL CONTEXT - A+ DELIVERY MODEL:
A+ Tutoring is a virtual tutoring company serving California charter homeschool families. Visual depictions of A+ tutoring sessions MUST show students learning at home, NOT in traditional classroom settings. This is non-negotiable for brand accuracy.

ACCEPTABLE student settings:
- Home offices with desks
- Student bedrooms with desks
- Kitchen tables with school supplies
- Family room work areas with laptops
- Library nooks (home library or public library quiet rooms)
- Backyard shaded spaces with portable desks
- Parent-organized homeschool co-op spaces (occasional)

UNACCEPTABLE settings (NEVER generate these):
- Traditional school classrooms with rows of desks
- School cafeterias
- Bulletin-board-heavy classroom walls
- School lockers
- Gym settings
- Chalkboards or whiteboards used as primary visual element
- Any setting suggesting a traditional public school

When generating photographic prompts, default to home-based learning environments. Specify the exact home setting (e.g., "kitchen table" or "bedroom desk") rather than leaving it ambiguous.

**ALWAYS:**
- Real students in real learning environments (not models)
- Real teachers/tutors interacting authentically
- Diverse age ranges (K-12, mostly middle/high school for B2B context)
- California-specific settings when possible (charter school aesthetic)
- Natural lighting
- Genuine expressions (concentration, breakthrough moments, collaborative discussion)

**NEVER:**
- Stock photography that looks staged
- Hands-on-keyboard cliche shots
- Tutors pointing at screens with overly excited expressions
- "Diverse hands together" trope
- Models posing as students
- Generic education stock (chalkboards with apples, etc.)
- Asian student stereotyped as math prodigy
- Black student stereotyped as struggling
- Anything that doesn't pass the "would a real charter school admin recognize this as authentic?" test

### Composition principles

- **Rule of thirds** for portraits and scene compositions
- **Generous whitespace** - never crowded
- **Single focal point** - one student, one teacher, one moment
- **Diagonal energy** for engagement (not flat horizontal compositions)
- **Hands and faces** more than wide rooms

## Output structure

Produce a single markdown file: `graphics-package-[blog-slug].md`

### Section 1: Hero Image

For the main blog post hero image. Lives at the top of the published post.

#### Image gen API prompts (provide all four):

**Midjourney prompt:**
```
[Detailed scene description that captures the blog's core argument visually], natural lighting, authentic education environment, real students aged [age range from blog target], shot on Sony A7IV, 35mm lens, candid documentary photography style, no posed shots, --ar 16:9 --style raw --v 6.1
```

**DALL-E 3 / GPT Image prompt:**
```
A photorealistic image of [scene description]. The setting is [specific location type from blog]. Style: documentary photography, natural lighting, candid moment captured. Mood: [emotional tone of blog]. The composition follows rule of thirds with [subject] as the focal point. Color palette emphasizes warm tones with subtle A+ Orange (#EF5829) accents in clothing or environment.
```

**Google Imagen prompt:**
```
Candid documentary photograph of [scene]. [Specific details about subjects, action, environment]. Soft natural light from window/overhead. Shallow depth of field. Authentic moment, not posed. Color grading: warm shadows, neutral highlights. Aspect ratio 16:9.
```

**Adobe Firefly prompt:**
```
Documentary-style photography of [scene]. Real students in real classroom/learning space. Natural window light. Candid expression showing [emotion from blog]. Composition: rule of thirds, single focal point on [subject]. Style: photojournalism, not stock photography. Aspect ratio 16:9. No text overlay.
```

#### Canva-ready specifications:

If image gen produces poor results, fall back to Canva manual execution:

```
Template: Canva "Blog Hero Image" or 1920x1080 custom
Background: [Specific Canva photo library search terms - usually 3-5 specific terms]
Text overlay: None (hero image carries no text - text is in the blog body)
Color overlay (optional): 20% A+ Navy at bottom for text contrast if title overlays
Crop: 16:9, focal point per rule of thirds
File: 1920x1080 PNG, sRGB color space
```

### Section 2: Featured Image (for social card)

The image that appears when the blog URL is shared on LinkedIn, Facebook, Twitter, Slack.

#### Specifications:
- Size: 1200x630 pixels (Open Graph standard)
- Format: PNG or JPG
- File size: Under 1MB for fast preview loading

#### Image gen prompts:
[Same four-tool format as hero, with 1200x630 aspect ratio noted]

#### Canva specs:
```
Template: Canva "Facebook Post" 1200x630
Background: [scene description] OR solid A+ Navy (#1A3A52)
Headline overlay (if used): Blog's H1 in Inter Bold White, 60-72pt
Subhead (if used): Key data point from blog (e.g., "75% improvement in 17 hours")
Logo: A+ Tutoring logo bottom-right at 10% width
Text rules: NO em dashes. NO AI vocabulary. Max 10 words on image.
```

### Section 3: LinkedIn Carousel (5 slides)

LinkedIn carousels outperform single posts on engagement by 3-5x. Every approved blog gets a carousel.

#### Structure (always 5 slides):

**Slide 1: Hook**
- Format: Bold question or surprising stat from blog
- Background: A+ Navy (#1A3A52) or hero image with 60% dark overlay
- Text: 1-2 lines max, Inter Bold White
- Example: "What if 17 hours of tutoring could move a student from the 7th to the 25th percentile?"

**Slide 2: The Problem**
- Format: One sentence problem statement + supporting stat
- Background: White with A+ Orange accent strip
- Text: Inter Regular Charcoal, 24-32pt
- Example: "Reading scores have stalled at pandemic-low levels. NWEA data shows zero recovery across most subgroups."

**Slide 3: The Insight**
- Format: The blog's central argument distilled
- Background: A+ Orange (#EF5829) or split with hero image
- Text: Inter Bold White on orange, max 15 words
- Example: "What works isn't ed-tech. It's high-dosage human tutoring with real teachers."

**Slide 4: The Evidence**
- Format: A+ proof point with clear attribution
- Background: White
- Data visualization: Single key number large (e.g., "75%") with attribution line below
- Text: Includes URL or "see case study"
- Example: "75% of iLEAD Math Tier 3 students showed positive RIT growth. 17 hours of instruction. wetutorathome.com/case-study-ilead-math-tier3"

**Slide 5: CTA**
- Format: Action prompt + clear next step
- Background: A+ Navy with A+ Orange CTA button graphic
- Text: "Read the full analysis" or "See how this works for your school"
- URL: blog.wetutorathome.com/[blog-slug]
- A+ logo and tagline

#### Image gen prompts per slide:
[Per-slide prompts in all four image gen formats]

#### Canva specs:
```
Template: Canva "LinkedIn Carousel" or 1080x1350 custom
Total slides: 5
Color rules: Slides 1 and 5 dark (Navy), Slide 3 orange, Slides 2 and 4 white
Typography: Inter Bold for headlines, Inter Regular for body
NO em dashes. NO AI vocabulary words (delve, leverage, foster, fundamentally, streamline, navigating, additionally, landscape, robust, etc.)
NO rule-of-three lists
Brand watermark: A+ logo on slides 1 and 5 only
```

### Section 4: Pull Quote Graphics (3 quotes from blog)

Standalone shareable graphics. One quote per graphic.

#### Selection criteria:
- Pull quote must be in the blog body (not invented for graphic)
- Quote should be 15-25 words (fits cleanly on graphic)
- Quote should make sense out of context
- Quote should NOT contain em dashes (per brand-check)

#### Format per quote:

```
Quote: [Verbatim text from blog, 15-25 words]
Attribution: Either "From: [Blog title]" OR a named source if the quote is attributed in blog
Background: A+ Navy or hero image with overlay
Typography: Inter Bold White for quote, Inter Regular for attribution
Size: 1080x1080 (Instagram square) AND 1200x630 (Open Graph)
Brand: A+ logo in corner
```

#### Image gen prompts:
[For text-on-image graphics, typically Canva is faster than image gen. Provide Canva specs only.]

### Section 5: Facebook Post Image

For the B2C parent-facing Facebook post.

#### Different aesthetic than B2B:
- Warmer color palette (cream backgrounds, A+ Orange dominant)
- Family-friendly composition (parent + child, or smiling student alone)
- Higher saturation than B2B
- Less data-driven, more emotional

#### Specs:
```
Size: 1200x630 (Facebook recommended)
Background: A+ Orange (#EF5829) with subtle texture OR family photo with cream overlay
Text overlay: Maximum 20% of image area (Facebook ad policy)
Headline: Conversational, parent-relatable
Example: "When your child's school says 'We don't have the resources,' here's what we tell them."
```

#### Image gen prompts:
[All four tools, with B2C aesthetic notes]

#### Canva specs:
```
Template: Canva "Facebook Post" 1200x630
Background: Warm Cream (#FFF8F0) with A+ Orange accent
Photo (optional): Real family scene, not stock
Text rules: Same as B2B (no em dashes, no AI vocab, no rule-of-three)
```

## Quality gates

Before output is delivered, the agent self-checks:

1. **Brand color check:** All hex codes match approved palette. No off-brand colors.
2. **Typography check:** No serif fonts in headlines. No Comic Sans anywhere.
3. **Aspect ratio check:** All specs include correct aspect ratios for their platform.
4. **Text limit check:** No graphic has more than 20% text coverage (per Facebook policy and general design principles).
5. **Brand voice check:** All text overlays pass aplus-brand-check v1.1 rules.
6. **Pull quote verification:** Every pull quote exists verbatim in the source blog post.
7. **Photography style check:** No stock-cliche scene descriptions. All scenes specify "documentary" or "candid" aesthetic.
8. **Color contrast check:** White text only on dark backgrounds. Dark text only on light backgrounds. WCAG AA minimum.

If any check fails, revise before output.

## What this skill does NOT do

- Does NOT generate actual images
- Does NOT publish graphics anywhere
- Does NOT make Canva designs (only provides specs)
- Does NOT replace a designer's judgment on final composition
- Does NOT include video content (Synthesia, motion graphics are separate skills)
- Does NOT generate logos or brand identity elements (those are fixed assets)

## Output file location

Save to: `aplus-content/[YYYY-MM-DD-weekly]/graphics-package.md`

## Coordination with other skills

- **Receives input from:** aplus-blog-longform v1.1+ (the blog content), aplus-b2b-brand-kit (visual rules), aplus-b2c-brand-kit (B2C visual rules), aplus-brand-check v1.1 (validates text overlays)
- **Sends output to:** Human (for execution) OR future image generation agent (v2)
- **Reads from:** Approved blog post markdown, suggested pull quotes from blog meta file, all four social derivatives for cross-channel consistency

## Failure modes to watch for

1. **Stock-cliche prompts:** If the scene description sounds like a stock photo search query, rewrite it. "Diverse group of students collaborating around a laptop" = bad. "Two 7th graders working through a math problem at a kitchen table, late afternoon light" = good.

2. **Brand drift:** If text overlay starts including em dashes or AI vocabulary, brand-check should catch it. Revise immediately.

3. **Inventing pull quotes:** If a "pull quote" doesn't exist verbatim in the blog, do not use it. Either find a real quote or skip the graphic.

4. **Color creep:** If hex codes outside the palette appear, revise. Brand integrity matters more than visual variety.

5. **Generic aesthetic:** If the visuals would work for any tutoring company, they're not A+ specific. Add California charter school context, real partner school references, or A+ orange.

## Frequency

- Default: Once per approved blog post (weekly)
- Ad hoc: When existing content needs visual refresh for republishing
- Sales-driven: When Danielle needs custom graphics for a specific pitch

## Related skills

- `aplus-blog-longform` v1.1+ . source of blog content
- `aplus-b2b-brand-kit` . source of visual rules for B2B audience
- `aplus-b2c-brand-kit` . source of visual rules for B2C audience  
- `aplus-brand-check` v1.1 . validates text overlays
- Future: `aplus-image-generator` . v2 skill that calls image gen APIs directly
- Future: `aplus-canva-publisher` . v2 skill that uses Canva MCP to produce designs

## Version

v1.1 . Updated 2026-05-14 . Added critical context about A+ delivery model (virtual homeschool, not traditional classroom). Removed assumption that A+ visuals could show students in traditional classroom settings. Foundation: Roman's audit caught that v1.0 prompts produced classroom imagery that misrepresented A+'s actual home-based delivery model.

v1.0 . Created May 14, 2026
Foundation: Roman's observation that the blog pipeline produces text without visuals. Built to close the gap between text content production and visual content ready for publication.

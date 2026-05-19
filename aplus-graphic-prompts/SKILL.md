---
name: aplus-graphic-prompts
description: Rules-only skill defining how every A+ Tutoring graphic asset must be built (dimensions, typography, brand colors, content rules, logo placement, what to avoid). Applied by the weekly engine when it generates hero images, social cards, pull-quote graphics, data visualizations, LinkedIn carousel slides, Instagram posts/stories, and Facebook graphics. Does NOT generate images; defines the rulebook the image-generation skills (ai-image-generator, matplotlib builders) follow.
---

# A+ Tutoring Graphic Prompts (Rules-Only)

## Purpose

This skill is a rulebook. It defines what every A+ graphic must look like, what dimensions and typography to use, how to apply brand colors, where logos go, what to never include, and which graphic types belong in a weekly bundle. Image generation itself lives in `ai-image-generator` (Gemini / GPT Image 2 for photos and text graphics) and in `scripts/build-creative-graphic.py` and `scripts/build-ilead-outcomes-graphic.py` (matplotlib for deterministic data viz). This skill is what those generators read before producing any asset.

## When to apply

Apply this rulebook to EVERY graphic produced for an A+ weekly bundle, including:
- Hero blog image
- Open-Graph social card
- Pull-quote graphics
- Preset stat graphic (the canonical iLEAD outcomes asset)
- Topic-specific data-viz graphic
- LinkedIn carousel slides (multi-slide)
- Instagram post + Instagram story
- Facebook share graphic

Do NOT apply to:
- Internal documents (case study PDFs, sales decks) which use the full brand kit not this rulebook
- Email templates (use the email brand kit)

## Dimensions: blog-body-width, not square

The default A+ graphic dimension is blog-body-width landscape, NOT square. Square graphics are reserved for Instagram. Match the format to where the graphic will be used.

| Asset | Dimensions | Aspect | Why |
|---|---|---|---|
| Blog hero | 1536x1024 | 3:2 | Renders cleanly at HubSpot blog body width and on mobile |
| Open-Graph / Twitter social card | 1200x630 | 1.91:1 | OG card spec |
| LinkedIn link share | 1200x627 | ~1.91:1 | LinkedIn card spec |
| LinkedIn carousel slide | 1080x1350 | 4:5 | Portrait fills feed; same ratio across all slides |
| LinkedIn carousel single graphic | 1200x1200 | 1:1 | Use only when NOT a carousel (avoids accidental "swipe" indicator) |
| Pull-quote graphic | 1200x630 | 1.91:1 | Renders inline in blog body, scales to mobile |
| Topic data-viz graphic | 1200x800 | 3:2 | Renders inline in blog body |
| Preset stat graphic (canonical iLEAD) | 1080x1080 | 1:1 | Existing brand asset, do not change |
| Instagram post | 1080x1080 | 1:1 | IG feed spec |
| Instagram story | 1080x1920 | 9:16 | IG story spec |
| Facebook share | 1200x630 | 1.91:1 | FB OG spec |

**Never** ship a 1080x1080 square as the blog hero or inline body graphic. Body graphics must be landscape so they don't dominate mobile scroll.

**Carousel swipe-indicator rule:** the small chevron / "swipe" indicator at the right edge of slide 1 may appear ONLY when there are 2+ slides. Single graphics must not show a swipe indicator (it implies content that doesn't exist).

## Typography (matches blog v1.5)

All A+ graphics use the same font system as the blog so the brand reads consistently from social to article to graphic:

- **Headlines, pull quotes, hero titles:** Playfair Display (serif, weight 700 or 600)
- **Body text, captions, data labels, source attributions:** DM Sans (sans-serif, weight 400 or 500)
- **Numbers in data-viz (large stat figures):** DM Sans Bold (weight 700) OR Playfair Display 700 if the design treatment calls for it

Never use Inter, Arial, Helvetica, or any other font on a published graphic.

When the image generator cannot honor a specific font (e.g., AI photographic generation), the rule applies to text overlays added in the matplotlib / PIL composite pass, not to incidental text inside an AI photo.

## Brand colors (heavy use, not just accent)

A+ graphics must visibly use the A+ brand palette throughout, not just as a thin accent. A graphic that could be re-skinned to any other tutoring company's palette without effort has failed this check.

- **A+ Navy:** `#1A3A52` (primary, institutional weight, B2B lead)
- **A+ Orange:** `#EF5829` (accent in B2B, lead in B2C, used heavily for emphasis)
- **A+ Gold:** `#F4A261` (callouts, outcome badges, used sparingly)
- **Ring background (data viz):** `#34526F` (matplotlib ring backgrounds only)
- **Warm Off-White:** `#FAF7F2` (alternate background)
- **White:** `#FFFFFF`
- **Charcoal:** `#2E2E2E` (body text on light backgrounds)

**Rule:** every published graphic must contain at least two of the three primary brand colors (Navy, Orange, Gold). Single-color graphics, generic AI-default palettes, and "any tutoring brand could use this" palettes all fail.

## Content rules

### What every graphic must include

- A+ logo (real logo file, never AI-rendered text)
- At least two of the three primary brand colors
- Typography from the Playfair Display + DM Sans system
- Content that COMPLEMENTS the blog body, not REPEATS what the body says verbatim

### What every graphic must NOT include

- **NO date.** "May 20, 2026" or any other date does not appear on any graphic. The date is HubSpot's job to render at publication time. Static dates on graphics make assets feel stale within a week.
- **NO "A+ Tutoring blog" subtitle.** That text is redundant with the logo. Drop it.
- **NO retired data.** 81% never appears. "21 students" combined never appears. Use the verified iLEAD figures (75%, 87.5%, 80%).
- **NO AI fingerprint text.** Garbled letters, hallucinated tokens, misspelled brand names, fake percentages. Verify every text token in the graphic before shipping.
- **NO em dashes.** Same rule as the blog: use periods or colons.
- **NO straight ASCII quote marks** (`"`) on graphics where the typography supports proper curly quotes (`"` `"`). When a quote is rendered, use proper quotation marks.
- **NO generic AI aesthetic.** Graphics that look like stock AI output (washed-out gradients, generic "diverse classroom" stock-style figures, vague abstract shapes) fail this check.

### Quote rendering

When a pull quote is rendered on a graphic:
- Use proper curly quotation marks (`"` and `"`) wrapping the quote
- The quoted text is VERBATIM from the blog body, not a paraphrase
- No attribution date below the quote
- No "A+ Tutoring blog" tag below the quote
- Only the verbatim quote and the A+ logo

## Pull-quote graphic cap (new in v2.0)

**Maximum 1-2 pull-quote graphics per blog bundle.** Three pull-quote graphics per blog is TOO MANY — it dilutes the visual mix and pads the bundle. Reduce to:
- 1 pull-quote graphic for short blogs or where one quote clearly dominates
- 2 pull-quote graphics for longer blogs where two distinct quotes anchor different sections

The space freed up by reducing pull-quotes must be filled by data viz, not by extra photos.

## Data-viz emphasis (new in v2.0)

Each bundle must ship at least 2 data visualization graphics:

1. **Preset stat graphic** (canonical iLEAD outcomes, matplotlib-built, copied verbatim from `aplus-b2b-brand-kit/ilead-outcomes-graphic.png`)
2. **Topic-specific data-viz graphic** (matplotlib-built for numerical accuracy, generated fresh each week, visualizes the SPECIFIC data the blog cites: a comparison bar chart, a timeline, a ring-fill, a sankey, etc.)

Data viz beats pull-quote graphics for engagement and for AI-engine extraction (charts get cited in AI Overviews because they map to structured answer fragments). Bias the bundle toward more data viz, fewer text-on-color pull quotes.

## Hero image rules

The blog hero is photographic, not text-on-color.

- **Setting:** California homeschool charter environment (kitchen, home office, dining table, bedroom desk). NEVER a traditional classroom (rows of desks, chalkboards, school lockers).
- **People:** mid-30s to mid-40s parent or administrator, OR a parent-and-child pair, reflecting actual A+ demographic. Diverse, real-looking, no uncanny-valley AI face artifacts (verify visually before shipping).
- **Aesthetic:** documentary photography. Candid not staged. Natural light. Slightly imperfect composition.
- **Engagement:** the image should make a school admin or parent stop scrolling. A blank kitchen at golden hour is not engaging. A specific moment is.

When the hero engages the reader from the first frame, it earns the first 100 words. When it looks like generic AI output, the reader bounces.

## LinkedIn carousel rules

5-slide carousel format: hook (slide 1) + 3 insights (slides 2-4) + CTA (slide 5).

### Logo placement (critical, new in v2.0)

- The A+ logo must NEVER overlap or touch another logo, badge, or visual element on a slide. If a slide has imagery (e.g., a photo of a school), place the logo in a clean corner of the composition where no other visual element competes.
- Recommended placement: bottom-right corner, with at least 40px clearspace around the logo edge.
- The logo on white slides uses `logo.png` (two-color). The logo on navy/orange/dark slides uses `logo-white.png` (all-white variant).
- Run a visual logo-overlap check on every slide before delivery: if the logo overlaps text, illustrations, or another logo, the slide fails.

### Slide consistency

- All 5 slides use the same color palette (heavy A+ brand colors)
- All 5 slides use the same typography (Playfair Display headings + DM Sans body)
- Slide 1 hook reads as the blog's opening claim
- Slides 2-4 each carry ONE insight or data point, not three
- Slide 5 CTA wording is audience-specific, NOT generic (matches blog v1.5 CTA rules)

### Swipe indicator

- Swipe / chevron indicator appears ONLY on slide 1 of multi-slide carousels
- Single graphics never show a swipe indicator
- The indicator visually invites the reader into the carousel; on a single graphic it is misleading

## Photographic image style for B2C

For Instagram, Facebook, and parent-facing photographic graphics:

- Diverse families and children that match the California charter homeschool demographic, not stock-photo aesthetic
- Warm color palette overlay tied to A+ Orange
- Avoid uncanny valley AI face artifacts (verify visually; if any face looks subtly wrong, regenerate)
- Specifically include 1-on-1 parent-child or tutor-student moments, not classroom group shots

## What good looks like (litmus test)

A graphic passes this rulebook when:
1. A school admin or parent sees the brand colors and recognizes A+ within 0.5 seconds
2. The typography is Playfair Display + DM Sans, visibly serif-vs-sans paired
3. The content complements the blog rather than repeating it verbatim
4. The dimensions match the channel (blog-body-width landscape for blog, square for IG, story 9:16 for IG story)
5. The logo is present, in the right variant for the background, with no overlaps
6. There is no date, no "A+ Tutoring blog" text, no retired data, no AI fingerprints
7. The bundle has 1-2 pull-quote graphics max and 2+ data viz graphics
8. The hero is photographic, in a homeschool setting, candid not staged

If any of those eight points fails, the graphic must be revised before publication.

## Coordination with other skills

- Reads from: `aplus-b2b-brand-kit` and `aplus-b2c-brand-kit` (color and logo authority)
- Reads from: `aplus-blog-longform` (the blog body that the graphics complement, plus the typography decisions and proof-points)
- Applied by: `ai-image-generator` (community skill for photographic generation), `scripts/build-creative-graphic.py` (matplotlib topic graphics), `scripts/build-ilead-outcomes-graphic.py` (matplotlib preset stat graphic), `aplus-content/{date}-weekly/graphics/_batch_v2.py` (per-bundle batch generator)
- Checked by: `aplus-brand-check` v1.2 (visual failures section)
- QA against: `aplus-content/{date}-weekly/qa-checklist.md` (human walkthrough)

## Version

v2.0 . Updated 2026-05-19 . Major overhaul applying Danielle's feedback. New rules: blog-body-width dimensions (1536x1024 hero, 1200x630 social, NOT square unless Instagram); Playfair Display headings + DM Sans body across all graphics; no date on graphics; no "A+ Tutoring blog" subtitle; heavy A+ brand color use throughout (not just accent); maximum 1-2 pull-quote graphics per bundle (was 3, which is too many); 2+ data-viz graphics required per bundle; hero is photographic and homeschool-set, never classroom; LinkedIn carousel logo-overlap check required; swipe indicator only on multi-slide carousels; proper curly quotation marks when rendering quotes; verified iLEAD figures only (no 81%, no 21 students); descriptive natural-English alt text for accessibility; visual logo placement checks added to every slide pre-delivery. Replaces all v1.x conventions which lived implicitly in the brand kits.

v1.x (pre-2026-05-19): graphics rules lived embedded across aplus-b2b-brand-kit, aplus-b2c-brand-kit, and the weekly bundle generators. v2.0 consolidates the rulebook into a single skill so it can be enforced by brand-check and read by every image generator.

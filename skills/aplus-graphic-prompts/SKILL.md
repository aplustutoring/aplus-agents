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
| Instagram story (3-frame sequence) | 1080x1920 each | 9:16 | IG story spec (see Instagram Story Aesthetic below). Instagram feed posts are NO LONGER part of the weekly bundle as of v2.2 (2026-05-20). |
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

## Data-viz emphasis (new in v2.0, expanded in v2.1)

Each bundle must ship at least 2 data visualization graphics:

1. **Preset stat graphic** (canonical iLEAD outcomes, matplotlib-built, copied verbatim from `aplus-b2b-brand-kit/ilead-outcomes-graphic.png`)
2. **Topic-specific data-viz graphic** (matplotlib-built for numerical accuracy, generated fresh each week, visualizes the SPECIFIC data the blog cites: a comparison bar chart, a timeline, a ring-fill, a sankey, etc.)

Data viz beats pull-quote graphics for engagement and for AI-engine extraction (charts get cited in AI Overviews because they map to structured answer fragments). Bias the bundle toward more data viz, fewer text-on-color pull quotes.

### Inline placement in blog body (new in v2.1)

Both the preset stat graphic AND the topic graphic must be embedded inline in the published blog body (not only in the Slack delivery gallery or social variants). The rationale: the blog is the asset that compounds in SEO value over time, and readers who land on the blog from search should see the same visual proof points that LinkedIn carousels and Facebook viewers see.

Standard placement:
- **Preset stat graphic** anchors after the paragraph that introduces the iLEAD 75/87.5/80 outcomes (typically in the "What A+ Sees in the Field" section)
- **Topic graphic** anchors after the paragraph that most directly supports its visualization (state-listing paragraph for a state-deadline graphic, hook paragraph for a timeline graphic, etc.)

Mechanism: the bundle's `blog-anchor-meta.md` includes two parallel lists:
```
inline_data_viz_images:
  - topic-graphic-with-logo.png
  - preset-stat-graphic-with-logo.png
inline_data_viz_anchors:
  - "exact substring from the blog prose where topic graphic should appear after"
  - "exact substring from the blog prose where preset graphic should appear after"
```
`scripts/embed-pull-quotes.py` processes both `inline_pull_quote_images` and `inline_data_viz_images` and inserts `<figure>` tags after the paragraph containing each anchor. The script is idempotent (call with `--reset-figures` to strip existing figures and re-insert).

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

## Instagram Story Aesthetic (new in v2.2)

A+ Tutoring's Instagram presence prioritizes the @aplustutoring grid over feed flooding. Effective 2026-05-20, the weekly bundle stops generating Instagram feed posts and instead ships a **3-frame Instagram Story sequence** that runs each week.

### Why this matters

- Stories are temporal (24 hours) so they can be topical and tied to the week's blog without polluting the permanent feed grid
- Stories drive blog traffic via the link sticker, which the grid post can't carry organically
- Brand-forward design (typography + brand colors + data viz) reads cleanly at 9:16 and matches Danielle's design direction more than AI-generated lifestyle photos do

### Hard rules for Stories

1. **NO AI-generated people in stories of any kind.** Stories are typography + brand-color + data-viz. Photos of children, parents, tutors, administrators are all out. The aesthetic is the brand mark, not a face.
2. **Brand-forward typography.** Playfair Display for headlines, DM Sans for body text. The same font system as the blog. Never a system font.
3. **Heavy A+ brand colors throughout.** Navy `#1A3A52`, Orange `#EF5829`, Gold `#F4A261`. Each frame uses one primary brand color as the dominant background.
4. **Logo bottom-center on every frame.** White-variant `logo.png` chroma-keyed onto navy / orange / dark backgrounds. Consistent position across all 3 frames.
5. **1080x1920 vertical (9:16)** for every frame.
6. **Swipe → indicator** appears bottom-right on Frames 1 and 2 ONLY. Frame 3 is the final action frame and must NOT show a swipe indicator.

### The 3-frame structure

Every weekly bundle's Instagram Story sequence has exactly 3 frames in this order:

**Frame 1 — HOOK**
- Background: A+ Navy
- Center: bold Playfair Display headline (a question or stat that stops the scroll). Source: blog body opening line or one of the verbatim pull-quotes.
- Optional gold-colored DM Sans subhead beneath the headline
- Logo bottom-center (white variant)
- "Swipe →" bottom-right
- NO people, NO photo background, NO illustrated faces

**Frame 2 — KEY INSIGHT**
- Background: A+ Orange (provides palette variation across the 3-frame run)
- Center: a single large stat, percentage, or short claim rendered in Playfair Display 700. Source: the blog's strongest data point (iLEAD outcome, dosage number, state count, etc.).
- DM Sans supporting line below
- Logo bottom-center
- "Swipe →" bottom-right
- NO people

**Frame 3 — CTA WITH LINK STICKER PLACEMENT**
- Background: A+ Navy
- **Top portion of frame: intentionally minimal (v2.3 rule, 2026-05-20).** NO literal placeholder box. NO text saying "link sticker goes here" or similar artifact. The empty top region IS the cleanspace; Roman or Danielle drops the Instagram link sticker into the upper third before posting. The bottom-of-frame arrow + instruction does the cognitive work.
- Center: bold Playfair Display CTA copy ("Read the full article", "Build the pathway", etc.)
- Optional DM Sans subhead in gold
- Below the CTA: an orange "↑ Tap the link sticker above" instruction in DM Sans bold — this is the visual cue that directs the eye upward to where the sticker lands.
- Logo bottom-center
- NO swipe indicator (this is the final frame)
- NO people

### Meta schema for stories

The bundle's `blog-anchor-meta.md` must include:

```
instagram_story_frames:
  - "Frame 1 hook text (Playfair Display headline, ~22 chars per line works)"
  - "Frame 2 key insight text (one stat or short claim)"
  - "Frame 3 CTA copy (action verb)"

# Optional subheads per frame (DM Sans, smaller)
instagram_story_subheads:
  - "Frame 1 subhead in DM Sans gold"
  - "Frame 2 supporting line"
  - "Frame 3 supporting line"
```

Each frame's body text comes from one of three approved sources:
- Verbatim pull-quote text already in `pull_quotes:`
- A blog-body sentence that is short and standalone
- A concise paraphrase that Danielle would write herself if drafting from scratch

### Builder + Slack delivery

- Build with `scripts/build-instagram-stories.py --bundle aplus-content/{date}-weekly/`. The script renders all 3 frames with matplotlib + brand fonts, then composites the white logo bottom-center on each.
- `scripts/deliver-to-slack.py` ships the 3 frames as a single Slack gallery piece labeled "Instagram Story (3 frames)" with the per-frame copy from `instagram-story-1.md` / `-2.md` / `-3.md` included for verification.

## Photographic image style for B2C

For Facebook and parent-facing photographic graphics (Instagram feed posts are no longer in scope after v2.2):

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

## Logo composite rules (new in v2.3)

The PIL composite logic in `_composite_logo_v2.py` (per-bundle) and
`scripts/build-instagram-stories.py` (shared) must follow these three
rules to avoid the visible rectangular halo that appeared on textured
backgrounds (most visible on the orange carousel slide 3 before v2.3).

### 1. NO erase-rectangle step

Earlier versions painted a sample-color rectangle onto the base image
where the logo would land, intended as a clean stamp surface. The
sampled pixel often did not match the surrounding textured background
(especially on AI-generated graphics with subtle paper-grain noise),
producing a visible rectangular artifact. v2.3 removes this step.

### 2. Hard alpha threshold (binary alpha)

Every logo pixel is either fully transparent or fully opaque — no
in-between semi-transparency. Pseudocode:

```
if pixel.alpha < 128:
    pixel.alpha = 0
else:
    pixel.alpha = 255
```

This is applied:
- After the initial chroma-key (white pixels -> transparent)
- After the white-color recolor pass (for the white-variant logo)
- After any LANCZOS resize (which re-introduces soft edges)

The result: clean crisp edges with no anti-aliased halo bleeding into
dark backgrounds.

### 3. Preserve logo aspect ratio when resizing

Earlier versions resized to `(width, width)` — a square — even though
the source logo file has its own aspect ratio. v2.3 computes
`target_h = int(width * source.height / source.width)` and resizes to
`(width, target_h)`. Source logo at `~/Desktop/logo.png` is currently
512x512 (aspect 1.0) so the visible change is zero on the current
asset, but the code is now correct for any future logo replacement.

### Logo color selection rule (unchanged from v2.0)

- **White-variant logo** on orange / navy / dark / saturated backgrounds
- **Two-color logo** on white / cream / light backgrounds

If background is orange or navy, the logo MUST be white. Two-color logo
on those backgrounds is incorrect (the orange wordmark disappears into
orange bg; the navy book icon disappears into navy bg).

## Predicted blog URL (new in v2.3, used by IG Story Frame 3 + Slack delivery)

The published blog URL is constructed deterministically from the slug
in `blog-anchor-meta.md` BEFORE the HubSpot publish step:

```
predicted_blog_url = "https://blog.wetutorathome.com/" + url_slug.lstrip("/")
```

This URL is:
- Recorded in the meta file as `predicted_blog_url:`
- Logged by `scripts/publish-to-hubspot.py` for traceability
- Included in the Slack delivery header (next to the HubSpot edit URL)
- Substituted into the IG Story (3 frames) piece body via the
  `{predicted_blog_url}` placeholder in `scripts/deliver-to-slack.py`
- Pasted by Roman / Danielle into the Instagram link sticker when
  posting Frame 3

Because it is computed from the slug (not the eventual HubSpot post ID
or URL response), it is available BEFORE the publish call — so the
Slack thread can show the URL up front and the IG Story instructions
can reference it specifically.

## Coordination with other skills

- Reads from: `aplus-b2b-brand-kit` and `aplus-b2c-brand-kit` (color and logo authority)
- Reads from: `aplus-blog-longform` (the blog body that the graphics complement, plus the typography decisions and proof-points)
- Applied by: `ai-image-generator` (community skill for photographic generation), `scripts/build-creative-graphic.py` (matplotlib topic graphics), `scripts/build-ilead-outcomes-graphic.py` (matplotlib preset stat graphic), `aplus-content/{date}-weekly/graphics/_batch_v2.py` (per-bundle batch generator)
- Checked by: `aplus-brand-check` v1.2 (visual failures section)
- QA against: `aplus-content/{date}-weekly/qa-checklist.md` (human walkthrough)

## AI must NOT generate logos (new in v2.4)

**Critical rule, applies to every AI-generated graphic in the bundle:** the AI image generator (GPT Image 2, Gemini, any model) must NOT include any logo, wordmark, brand mark, watermark, signature, monogram, or company identifier anywhere in the rendered image. The real A+ logo is added in a single post-processing step by `scripts/composite-logo.py` (or the per-bundle `_composite_logo_v2.py` legacy wrapper).

### Why this rule exists

A May 20, 2026 review found that GPT Image 2 was rendering its own approximation of the A+ Tutoring wordmark in the bottom-right corner of LinkedIn carousel slides — despite a v2.2 prompt that explicitly asked it to "leave a clean ~140x140 pixel area for the A+ logo composite." When the real logo was then composited on top, the result was two overlapping logos. The model was treating "A+ Tutoring blog post" in the prompt context as a positive signal to brand the image, and the negative-space instruction was too weak to override that signal.

### The MANDATORY exclusion language

Every AI prompt in `_batch_v2.py` (and any future bundle generator) appends this exact paragraph at the end:

```
CRITICAL CONSTRAINT: Do NOT include any logo, wordmark, brand mark,
watermark, signature, monogram, or company identifier anywhere in this
image. Do NOT add an 'A+' mark, an 'A+ Tutoring' wordmark, the word
'Tutoring', the word 'aplustutoring', a chevron, a graduation cap icon,
a pencil icon, an apple icon, a book icon, or any approximation of a
tutoring-company logo. Do NOT add any badge, seal, certification mark,
or signature graphic. The bottom-right 200x200 pixel zone MUST be solid
background color with NO text, NO icons, NO graphics, NO design
elements. The bottom-left 200x200 pixel zone must also be clean. If
you generate any logo, wordmark, brand mark, or A+ approximation, the
image is a generation failure and will be discarded. The real A+ logo
is added in a separate post-processing step by a Python compositor;
your job is to produce a clean canvas with NO branded marks of any
kind. This is the single most important constraint.
```

Why this works where v2.2 didn't:
- Repeats the negative constraint multiple ways (logo, wordmark, brand mark, monogram)
- Lists specific elements GPT Image 2 commonly generates (chevron, graduation cap, pencil icon, apple icon, book icon, the word "Tutoring")
- Names what a clean canvas must look like (solid color, no text, no icons)
- States the failure mode explicitly ("the image is a generation failure")
- Ends with a priority signal ("single most important constraint")

### Enforcement

`scripts/composite-logo.py` adds a runtime check: before compositing, it samples the bottom-right logo zone and computes RGB standard deviation. High variance (std > 20) indicates AI-generated content already in the zone — the script logs a warning so QA can flag it. The composite still runs (the real logo lays on top), but the operator knows the source needs regeneration.

### Logo composite is the SOLE source of logos

- AI generation: produces clean canvases with NO logos
- `scripts/composite-logo.py`: adds exactly one logo per graphic, in the correct color variant
- The Instagram Story builder (`scripts/build-instagram-stories.py`): adds its own logo composite directly during matplotlib rendering — no AI involved, so no risk of double-logo
- The preset stat graphic: composited at brand-kit build time, copied verbatim into bundles, never re-composited

### Idempotency rule

`scripts/composite-logo.py` is idempotent by filename:
- Input: any `<name>.png` in `<bundle>/graphics/` that does NOT end in `-with-logo.png`
- Output: `<name>-with-logo.png`
- Files already named `-with-logo.png` are skipped (no re-processing)
- This prevents accidental double-composites if the script runs twice

## Version

v2.4 . Updated 2026-05-20 . Diagnosed and fixed the double-logo artifact on LinkedIn carousel slide 3 (and quietly on other slides). Root cause: GPT Image 2 rendering its own "A+ TUTORING" wordmark in the source graphic despite the prior "leave clean space" prompt. Fix: MANDATORY anti-logo exclusion paragraph appended to every AI prompt in `_batch_v2.py`. The exclusion repeats the negative constraint multiple ways and names specific logo elements GPT Image 2 commonly generates. Also created `scripts/composite-logo.py` — a centralized idempotent compositor with smart color selection (luminance + brand color detection), pre-existing-logo zone variance check (warns if AI ignored the rule), and the v2.3 alpha-threshold + aspect-preserving composite logic. Per-bundle `_composite_logo_v2.py` scripts continue to work as legacy wrappers.

v2.3 . Updated 2026-05-20 . Three fixes after Danielle's first review of the v2.2 bundle: (1) Instagram Story Frame 3 no longer renders a literal placeholder box or "[ link sticker goes here ]" text — the top region is intentionally empty and the bottom arrow + instruction does the visual work; (2) Logo composite pipeline rewrites to eliminate the rectangular halo: removed the erase-rectangle step, added hard alpha threshold (binary alpha: <128 -> 0, >=128 -> 255) after chroma-key and after every LANCZOS resize, preserved logo aspect ratio when resizing; (3) Predicted blog URL is now constructed deterministically from `url_slug:` BEFORE the HubSpot publish call so it is available to the Slack delivery header and the IG Story Frame 3 piece body via the `{predicted_blog_url}` placeholder.

v2.2 . Updated 2026-05-20 . Removed Instagram feed posts from the weekly bundle. Added 3-frame Instagram Story sequence (Hook / Key Insight / CTA-with-link-sticker-placement) with hard rules: NO AI-generated people, Playfair Display + DM Sans, heavy A+ brand colors, logo bottom-center on every frame, 1080x1920 vertical each, Swipe → indicator on frames 1 and 2 only, Frame 3 reserves top-center cleanspace for the user-added link sticker. New `instagram_story_frames:` + optional `instagram_story_subheads:` meta schema fields. Builder script: `scripts/build-instagram-stories.py`. Slack delivery ships the 3 frames as a single labeled gallery piece.

v2.1 . Updated 2026-05-20 . Added inline-blog-body placement rule for the preset stat graphic AND the topic graphic. Both must be embedded as `<figure>` tags in the published blog body (not only delivered as Slack assets or used in carousel slides). The meta schema gains `inline_data_viz_images` + `inline_data_viz_anchors` parallel lists; `scripts/embed-pull-quotes.py` processes them alongside pull-quote figures. Backward compatible with v2.0 bundles that didn't have the fields; retro-fit applied to the May 19 and May 20 bundles.

v2.0 . Updated 2026-05-19 . Major overhaul applying Danielle's feedback. New rules: blog-body-width dimensions (1536x1024 hero, 1200x630 social, NOT square unless Instagram); Playfair Display headings + DM Sans body across all graphics; no date on graphics; no "A+ Tutoring blog" subtitle; heavy A+ brand color use throughout (not just accent); maximum 1-2 pull-quote graphics per bundle (was 3, which is too many); 2+ data-viz graphics required per bundle; hero is photographic and homeschool-set, never classroom; LinkedIn carousel logo-overlap check required; swipe indicator only on multi-slide carousels; proper curly quotation marks when rendering quotes; verified iLEAD figures only (no 81%, no 21 students); descriptive natural-English alt text for accessibility; visual logo placement checks added to every slide pre-delivery. Replaces all v1.x conventions which lived implicitly in the brand kits.

v1.x (pre-2026-05-19): graphics rules lived embedded across aplus-b2b-brand-kit, aplus-b2c-brand-kit, and the weekly bundle generators. v2.0 consolidates the rulebook into a single skill so it can be enforced by brand-check and read by every image generator.

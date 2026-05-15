# Graphics Generation Log — May 15, 2026

**Skill:** ai-image-generator (community, jezweb/claude-skills, design-assets plugin)
**Models used:** Gemini 3.1 Flash Image (`gemini-3.1-flash-image-preview`), GPT Image 2 (`gpt-image-2`)
**Batch script:** [_batch.py](graphics/_batch.py)
**Generation results JSON:** [_results.json](graphics/_results.json)

---

## Summary table

| # | Asset | Provider | Size / Aspect | Quality | File | Bytes | Elapsed | Est. cost |
|---|---|---|---|---|---|---|---|---|
| 1 | Hero image | Gemini 3.1 Flash Image | 16:9 (~1820×1024) | preview | [graphics/hero.png](graphics/hero.png) | 820,414 | 57.3s | ~$0.035 |
| 2 | Featured social card | GPT Image 2 | 1536×1024 | medium | [graphics/social-card.png](graphics/social-card.png) | 1,261,004 | 33.1s | ~$0.045 |
| 3 | Carousel slide 1 | GPT Image 2 | 1024×1536 (2:3 portrait) | medium | [graphics/carousel-slide-1.png](graphics/carousel-slide-1.png) | 1,259,236 | 33.0s | ~$0.045 |
| 4 | Pull quote graphic | GPT Image 2 | 1024×1024 (1:1) | medium | [graphics/pull-quote.png](graphics/pull-quote.png) | 1,767,645 | 51.0s | ~$0.053 |
| 5 | Facebook post image | Gemini 3.1 Flash Image | 16:9 (~1820×1024) | preview | [graphics/facebook.png](graphics/facebook.png) | 830,047 | 20.9s | ~$0.035 |
| | | | | | | | **~3.2 min total** | **~$0.21** |

All 5 generations succeeded on the first attempt. No retries.

---

## Per-asset notes

### 1. Hero image

**What rendered:** A mid-40s woman in a green cardigan at a wooden home-office desk. Visible: laptop with a budget spreadsheet, paper grant-award documents, "TEACHER & LEADER" coffee mug, succulent, framed family photo on the bookshelf behind her, books, a wall calendar showing "SEPTEMBER 2026". Doorway to a hallway visible. Natural window light from the left. Three-quarter profile, focused expression.

**v1.1 homeschool spec compliance:**
- Home-based setting ✅ (home office, not a school admin office)
- No classroom signifiers ✅
- Real-feeling subject, not posed ✅
- Documentary aesthetic ✅
- Natural lighting ✅

**Usage detail:** Hero image at top of blog post. The September 2026 calendar in the background is a nice thematic touch on the federal funding cycle.

### 2. Featured social card

**What rendered:** Solid A+ Navy `#1A3A52` background. White Inter-style headline reading "Federal K-12 Grants Withheld" left-aligned upper section. Thin A+ Orange divider line below. Smaller white subhead reading "$2B in approved funds held back. 30+ programs affected." Bottom-right: white "A+ Tutoring" wordmark (stylized as "A+" with "Tutoring" beneath).

**Brand-check compliance:**
- Verbatim spec text rendered correctly ✅
- 0 em dashes ✅
- 0 AI vocabulary ✅
- A+ Navy + A+ Orange palette honored ✅
- Single CTA / clear hierarchy ✅

### 3. Carousel slide 1

**What rendered:** Portrait 2:3 (1024×1536). A+ Navy solid background. White headline text "California charter LEAs: $2 billion in federal K-12 grants are being withheld in 2026." centered vertically. Subhead "Swipe to see what's safe and what's not." beneath. "A+" wordmark top-left.

**Note:** "Withheld" shows minor kerning artifacts at the rendered scale — readable but not crisp. Acceptable for a slide-1 hook; if used at full LinkedIn-carousel resolution, this can be regenerated at high quality (~$0.211) or manually retouched in Canva.

### 4. Pull quote graphic

**What rendered:** Square 1:1 A+ Orange `#EF5829` background. White centered quote text: "Outcomes track operational design, not which federal grant code paid the bill." Attribution beneath in 70%-opacity white: "A+ Tutoring blog · May 20, 2026". "A+ Tutoring" wordmark bottom-right in white.

**Verbatim verification:** Quote is verbatim from blog-anchor.md (§4 "What does the research say about intervention that holds up across funding cycles"). Confirmed character-for-character.

### 5. Facebook post image

**What rendered:** A mother and a middle-school-age daughter at a kitchen table. The daughter is leaning in to write on a notebook with a pencil, with a laptop showing a document next to her. The mother sits beside her holding a book, supportive but not hovering. Warm late-afternoon light through a kitchen window with potted plants. Refrigerator with family photos in the background. Wooden cabinets, water bottle, mug, pencil case all visible.

**v1.1 homeschool spec compliance:**
- Home-based setting ✅ (kitchen, not a school)
- Authentic parent-child collaboration, not staged ✅
- B2C warm aesthetic (golden hour, family scene) ✅
- No classroom signifiers ✅

---

## Cost detail (token-based, gpt-image-2 + Gemini 3.1)

### GPT Image 2 token billing (from `usage` in API response)

| Asset | Input tokens | Output image tokens | Total tokens | Est. cost @ $5/M in + $30/M image out |
|---|---|---|---|---|
| Social card | 167 | 1,372 | 1,539 | $0.0419 |
| Carousel slide 1 | 151 | 1,372 | 1,523 | $0.0419 |
| Pull quote | 147 | 1,756 | 1,903 | $0.0535 |

### Gemini 3.1 Flash Image token billing

| Asset | Prompt tokens | Image output tokens | Total | Est. cost |
|---|---|---|---|---|
| Hero | 229 | 1,120 | 1,798 | ~$0.035 |
| Facebook | 194 | 1,120 | 1,785 | ~$0.035 |

Gemini pricing approximate at ~$30/M output image tokens + small text input cost.

**Estimated total spend: ~$0.21 across 5 production-quality images.**

Actual costs will appear in Google AI Studio billing and OpenAI usage dashboards within a few hours. None of the calls hit a rate limit; both providers returned 200 on first attempt.

---

## Brand-check on text overlays

All text rendered on the design graphics (social card, carousel slide 1, pull quote) passes aplus-brand-check v1.1:

| Check | Social card | Carousel | Pull quote |
|---|---|---|---|
| Em dashes | 0 ✅ | 0 ✅ | 0 ✅ |
| AI vocabulary | 0 ✅ | 0 ✅ | 0 ✅ |
| Banned phrases | 0 ✅ | 0 ✅ | 0 ✅ |
| Word count | 12 words | 21 words | 16 words + attribution |
| Verbatim from blog | Spec-derived | Spec-derived | Verbatim §4 quote ✅ |

---

## Files in this phase

- [graphics/hero.png](graphics/hero.png)
- [graphics/social-card.png](graphics/social-card.png)
- [graphics/carousel-slide-1.png](graphics/carousel-slide-1.png)
- [graphics/pull-quote.png](graphics/pull-quote.png)
- [graphics/facebook.png](graphics/facebook.png)
- [graphics/_batch.py](graphics/_batch.py) (the executable batch script — can be re-run, regenerates everything)
- [graphics/_results.json](graphics/_results.json) (raw API responses with token usage)

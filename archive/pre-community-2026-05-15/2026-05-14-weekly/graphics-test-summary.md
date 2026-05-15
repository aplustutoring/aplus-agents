# Graphics Test Summary — Canva MCP vs. DALL-E vs. Manual

**Test date:** 2026-05-14
**Bundle anchor:** Title III funding deadline blog (Sept 30, 2026)
**Brand kit verified:** A+ Tutoring (`kAF-2lh2wxg`) — live in Canva, applied to all generations

---

## Capabilities matrix

| Capability | Available via MCP? | Reliability | Notes |
|---|---|---|---|
| List brand kits | ✅ | High | Returned A+ Tutoring kit on first call |
| Generate design from a prompt with brand kit | ✅ | High | Returns 4 candidates per call; brand colors propagate from kit |
| Convert candidate to editable design | ✅ | High | Single call; returns design_id immediately |
| Read text content of a design | ✅ | High | Returns plain text per element |
| Start editing transaction | ✅ | High | Returns transaction_id + ALL element_ids + thumbnail |
| Replace text of existing element | ✅ | High | Honors verbatim string; auto-resizes element height |
| Find-and-replace within an element | ✅ | High | Useful for surgical fixes to long paragraphs |
| Delete editable element | ✅ | High | Reliable on `editable: true` elements |
| Delete `editable: false` element | ⚠️ | Mixed | API may return success but element still renders |
| Insert NEW text element from scratch | ❌ | n/a | No documented operation |
| Set text color (hex) | ✅ | High | Via `format_text.color` |
| Set font size / weight / style / alignment | ✅ | High | Via `format_text` formatting object |
| Set font family (e.g., Inter) | ❌ | n/a | Not exposed; must rely on brand kit defaults |
| Set arbitrary background fill on a page | ❌ | n/a | Only `update_fill` to swap an image asset on an existing fill element |
| Position element absolutely (top, left) | ✅ | High | Via `position_element` |
| Resize element | ✅ | High | Via `resize_element`, supports `preserve_aspect_ratio` |
| Commit transaction (persist edits) | ✅ | High | If not called, edits are PERMANENTLY LOST |
| Resize design to custom dimensions | ✅ | High | Creates a new design ID; original is preserved |
| Export to PNG / JPG / PDF | ✅ | High | Returns time-limited download URL |
| Search brand templates gallery | ❌ | n/a | Tool not exposed in current MCP surface |
| Insert new image at arbitrary position | ✅ | Medium | `insert_fill` works but requires asset_id (must `upload-asset-from-url` first) |

---

## What was actually delivered

**Three designs generated, edited, committed, and exported to PNG:**

1. **Featured social card** — 1200×630, A+ Navy background, verbatim spec text. Design `DAHJriiiTf8`. [Edit](https://www.canva.com/d/crDXGn_tk6n6oH0) · [View](https://www.canva.com/d/qPsBYWX8GcMx9f7)
2. **LinkedIn carousel Slide 1** — 1080×1350, verbatim hook text, background drifted from pure Navy to a template's orange/dark grid. Design `DAHJrjpFqjg`. [Edit](https://www.canva.com/d/zVqN73GQMWPA8UE) · [View](https://www.canva.com/d/O7uYaJcxvr0iQxT)
3. **Pull quote graphic** — 1080×1350 (needs resize to 1080×1080), A+ Orange background, verbatim blog quote, wrong font family (serif template default). Design `DAHJroD8Mbs`. [Edit](https://www.canva.com/d/b1epTpvRIaFuoo5) · [View](https://www.canva.com/d/UJj50-8SxH1lP3W)

All three text overlays pass aplus-brand-check v1.1: zero em dashes, zero AI vocabulary, zero banned phrases. All three carry verbatim, fact-check-cleared copy.

---

## The most important limitation found

**Canva AI sometimes renders substantive text as flat image assets, not editable text elements.** The first social card candidate had "Title III: $125.90 per newcomer" baked into an image with TWO typos ("omiliate" instead of "obligate" and "#2024-25" as a hashtag). The first pull quote candidate had the entire quote baked into an image with "The deadline is budget question" missing the words "not a." Neither can be fixed via the text-edit operations. The only recourse is `delete_element` on the image, which leaves a hole the MCP cannot fill (since you cannot insert new text elements from scratch).

**Implication:** Trust Canva AI for layout scaffolding and brand-color propagation, but assume the *content* of the design will need either editable-text replacement OR full re-edit in the web editor. Always inspect the generated design via `start-editing-transaction` (which returns the thumbnail) before publishing.

---

## Tool-vs-task recommendation matrix

| Use case | Best tool | Why |
|---|---|---|
| Hero image (photo of a real administrator at a desk) | **DALL-E 3 in ChatGPT Plus** | Photorealism, lighting, composition. Canva AI does not produce documentary photography at this quality level. |
| Featured social card (1200×630 flat design with text) | **Canva MCP** | Brand kit applied, text edits reliable, PNG export one call. Manual Canva web editor needed only to add logo. |
| LinkedIn carousel slide 1 (hook, single bold sentence on solid color) | **Canva MCP for draft, web editor for cleanup** | MCP generates a workable draft fast, but cleaning template-baked decorative shapes requires the web editor. |
| LinkedIn carousel slides 2-5 (multi-slide content with structured copy) | **Canva web editor with the spec as input** | Five slides in a row is faster to lay out manually than to clean five MCP outputs. Use the graphics package as the brief. |
| Pull quote graphics (text on solid color, brand-aligned) | **Canva MCP if quote is short and font family doesn't matter; web editor if Inter Bold is required** | MCP cannot set font family. The template font may override the brand kit. |
| Facebook post image (B2C parent audience, warm aesthetic) | **DALL-E 3 for the photo + Canva for text overlay** | DALL-E gets the warm documentary aesthetic right; Canva for adding the brand-compliant text overlay. |
| Facebook post image (flat design, no photo) | **Canva MCP** | Same as social card; reliable. |

---

## Estimated time savings vs. manual Canva (future weeks)

Assuming the user is a competent Canva operator producing 14 image assets per week (the full bundle per spec):

| Path | Time per week | Notes |
|---|---|---|
| Pure manual Canva from spec | 3-4 hours | Baseline; designer reads spec, opens template, lays out each asset |
| MCP-assisted (text-only assets, simple layouts) | 1.5-2 hours | MCP handles 8-10 of 14 assets (cards, slides 1+5, pull quotes); user finishes the rest manually |
| MCP-assisted + DALL-E for photo assets | 1-1.5 hours | DALL-E generates the hero + Facebook image in parallel; user assembles in Canva editor for final polish |
| Fully automated (current state) | Not possible | At minimum, logo placement, font family fixes, and decorative cleanup still need a human pass |

**Estimated savings: 50-70% of weekly graphics production time, with the residual time spent on logo placement, font fixes, and template-imposed decorative cleanup.**

---

## Recommendation

**Workflow for future weekly runs:**

1. **Always start with `aplus-graphic-prompts`** to produce the spec package. Locks the brand colors, text overlays, and pull quote selections before any generation runs.
2. **Use Canva MCP for the flat-design assets** (social card, pull quotes, carousel slides 1 and 5). One generate-design + one edit pass + one commit + one export per asset. ~3-5 minutes each.
3. **Use DALL-E 3 in ChatGPT Plus for the photographic hero and any B2C parent-facing photo composition.** Hand off the DALL-E output URL to `upload-asset-from-url` then `insert_fill` to composite it into a Canva text-overlay design.
4. **Manual web-editor pass for cleanup** — add A+ logo to corners, switch font family to Inter Bold where the template overrode it, remove residual decorative shapes. Budget 30-45 minutes for this on a 14-asset week.
5. **Do not trust AI-generated designs with substantive text until inspected.** Every design needs a `get-design-content` or `start-editing-transaction` thumbnail check before publication.

---

## Next iteration: skills to consider building

- **`aplus-canva-publisher` v0.1** — wraps the 7-step MCP flow (generate → convert → start → edit → commit → resize → export) into a single skill call with retry-on-typo-detection. Would close 80% of the residual friction.
- **`aplus-dalle-publisher` v0.1** — produces DALL-E 3 outputs with the photography prompt library from `aplus-graphic-prompts`, uploads to Canva, and inserts them into a brand-aligned text-overlay design.
- **`aplus-brand-template-loader`** — once Canva's brand-templates search is exposed in a future MCP version, this skill would let A+ keep a fixed library of approved layouts and call them by name.

=== GRAPHICS TEST COMPLETE ===

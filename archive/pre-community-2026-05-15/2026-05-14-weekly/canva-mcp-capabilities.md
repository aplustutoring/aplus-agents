# Canva MCP — Capabilities Findings

**Probe date:** 2026-05-14
**MCP server:** https://mcp.canva.com/mcp (OAuth, authenticated)
**User account state:** Authenticated paid Canva account, A+ Tutoring brand kit configured, dozens of existing designs in workspace

---

## Direct answers to the 6 capability questions

### 1. Can you create a new Canva design from scratch?

**Partially.** Canva MCP does not expose a "create blank canvas" tool. The way to create a new design is via `generate-design`, which produces AI-generated *design candidates* keyed to a query. The agent then picks a candidate and converts it to an editable design using `create-design-from-candidate`. So new designs always start from AI-generated output, not from a blank artboard.

Net effect: I cannot create a pixel-precise empty canvas and lay it out from scratch. I can ask Canva AI for a specific design type with a detailed prompt, then edit the AI's output.

### 2. Can you populate text into a Canva design?

**Yes**, after an editing transaction is opened on a design. Available text operations on existing text elements:
- `replace_text` — replace the full text of an element by `element_id`
- `find_and_replace_text` — find a substring in an element and replace it
- `update_title` — change the design's title

I cannot insert a brand-new text element from scratch; text edits operate on elements the AI-generated design already contains. If a generated layout has 3 text frames and I need 5, the constraint will bite.

### 3. Can you set custom colors and fonts?

**Colors: partial.** The `format_text` operation supports a `color` hex value for text. There is no documented operation to set arbitrary background fill colors on shape or page elements via the MCP. Background color and shape fill changes have to happen inside the Canva web editor by hand.

**Fonts: no for font family.** The `format_text` operation supports `font_size`, `font_weight` (normal or bold), `font_style` (normal or italic), `decoration`, `line_height`, `text_align`. It does NOT support font family. The skill spec explicitly notes "font (size, weight, style; family not supported)." Inter as a family must be set via the brand kit or manually in the Canva editor.

**Workaround:** Pass `brand_kit_id: kAF-2lh2wxg` (the verified A+ Tutoring brand kit) to `generate-design` so the AI uses the brand kit's color and font defaults from the start.

### 4. Can you access existing Canva templates in your account?

**Limited.** `search-designs` returns the user's existing designs (verified live: 25+ items in the first page, including "We support the students your assessments flag.", various Instagram posts, podcast covers, etc.). Brand templates (different from regular designs) require a separate `search-brand-templates` tool that is *not* exposed in the current MCP toolset visible to me. So I can find and reuse my own past designs, but I cannot pull from the official Canva template gallery via this MCP.

### 5. Can you export a design as PNG/PDF?

**Yes.** The `export-design` tool supports PNG, JPG, PDF, PPTX, GIF, and MP4. Per-format options include width/height (40-25000 px), quality, transparent background (PNG), single-image merge for multi-page (PNG), paper size (PDF), and page selection. `get-export-formats` should be called first to confirm which formats are supported for the specific design. Export returns a download URL that the user can open.

### 6. What input format does Canva MCP need?

For each tool type:
- **`generate-design`:** natural-language `query` string (the prompt), optional `design_type` (enum: poster, instagram_post, facebook_post, presentation, etc.), optional `brand_kit_id`, optional `asset_ids` for images to insert.
- **Editing:** all edits flow through a 3-step protocol — `start-editing-transaction(design_id)` → `perform-editing-operations(transaction_id, operations[], page_index, pages[])` → `commit-editing-transaction(transaction_id)`. Changes are draft until commit; if commit is skipped, edits are lost.
- **Identifiers:** Design IDs are 11 characters and start with "D" (regex: `^D[a-zA-Z0-9_-]+$`). Brand kit IDs follow a different pattern. Asset IDs start with "M" (media) based on the folder listing.

---

## Verified live findings

### A+ Tutoring brand kit exists

```
brand_kit_id: kAF-2lh2wxg
name:         A+ Tutoring
thumbnail:    200×200 PNG (returned by list-brand-kits)
```

A second unnamed brand kit exists (`kAEc0KcU3D4`) which appears to be a header/banner-shaped kit (200×50). Will use `kAF-2lh2wxg` for all generations.

### Workspace has active design history

The user's root folder contains 25+ designs, most recently:
- "We support the students your assessments flag." (4-page design, May 2026)
- "www.wetutorathome.com" (1-page)
- "TTE (Instagram Reel)" (2-page)

And one subfolder ("Emily Shulman"). Image assets exist in root including a screenshot from earlier in May. Workspace is healthy and authenticated.

---

## Capabilities matrix (what I can do via MCP, end-to-end)

| Capability | Available? | Notes |
|---|---|---|
| Authenticate | ✅ | OAuth already complete |
| List brand kits | ✅ | A+ Tutoring kit confirmed |
| Generate design from prompt | ✅ | Returns candidates, need to pick one and convert |
| Convert candidate to editable design | ✅ | `create-design-from-candidate` |
| Apply brand kit to generated design | ✅ | Pass `brand_kit_id` to `generate-design` |
| Edit existing text | ✅ | `replace_text`, `find_and_replace_text` on element_ids |
| Insert brand-new text element | ❌ | No documented operation for it |
| Set text color (hex) | ✅ | Via `format_text.color` |
| Set background fill color | ❌ | Not exposed; must be done in web editor |
| Set font family (Inter) | ❌ | Only size / weight / style; family must come from brand kit |
| Set font size / weight / style | ✅ | Via `format_text` |
| Resize design to custom dimensions | ✅ | `resize-design` with custom width/height |
| Export PNG/JPG/PDF | ✅ | Configurable size, quality, transparent bg |
| Search existing designs | ✅ | Verified live |
| List folder contents | ✅ | Verified live |
| Search brand templates gallery | ❌ | Not exposed in current toolset |
| Upload image asset by URL | ✅ | `upload-asset-from-url` |
| Insert image into design | ✅ | `insert_fill` operation, requires asset_id |
| Insert image already in workspace | ✅ | `update_fill` to replace existing image element |
| Comment on design | ✅ | For collaboration |
| Merge pages from multiple designs | ✅ | `merge-designs` |
| Generate from external URL (e.g., PDF) | ✅ | `import-design-from-url` |

---

## Practical takeaways for the graphics pipeline

**What Canva MCP is good for:**
- Spinning up first-draft designs from a brand-kit-aware prompt, fast
- Producing text-overlay variants by find-and-replacing on a master template
- Bulk-exporting finished designs as PNG/PDF for HubSpot or social
- Resizing one design into multiple platform sizes (Instagram square, LinkedIn portrait, Open Graph)

**What still requires manual web-editor work:**
- Setting an exact background fill (e.g., A+ Navy `#1A3A52` on a flat color card) when the AI didn't pick it
- Adding text elements the AI did not generate
- Precise layout adjustments (Canva AI does the composition; nudging is a hand operation)
- Anything with brand-template logic (e.g., "use my existing Title III template")

**Friction points:**
- The 3-step transaction model (start → perform → commit) means every text edit is at least 3 tool calls, plus state to track the transaction ID
- Generated designs vary in element count; if the AI didn't include a logo placeholder, I can't add one via the MCP
- No font-family control means brand-kit alignment must be a guarantee, not a hope

---

## Recommendation for Phase 3 attempt

**Strategy:** Use `generate-design` with `brand_kit_id: kAF-2lh2wxg` and a precise, A+ Navy/A+ Orange-anchored prompt for each of the three designs. After each generation, inspect the candidates, convert the best one, run a text-edit pass to lock in the verbatim copy from the graphics-package spec, then commit and export. If the AI's background color drifts from spec, flag it in the deliverable rather than spending excessive calls trying to repaint it via the MCP.

**Expected design types:**
- Featured social card → `design_type: facebook_post` (defaults to a wide landscape format close to 1200×630)
- LinkedIn carousel Slide 1 → `design_type: instagram_post` (generates 1080×1350 portrait per skill description, close to LinkedIn carousel slide spec)
- Pull quote graphic → `design_type: instagram_post`, then resize to 1080×1080 square via `resize-design`

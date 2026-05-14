# Phase 5: Slide Generation & Interactive Iteration — Detail

Build the .pptx deck from the finalized outline.

## General Design Principles

This phase generates concrete slides from the outline. **Every slide should respect the design principles in `slide-design-spec.md` Section 11**, including:

- **Signal-to-Noise Ratio** — remove anything that does not encode information
- **The Big Four** — Contrast, Repetition, Alignment, Proximity
- **Picture Superiority Effect** — pictures beat words for retention; replace decorative text with concrete imagery when possible
- **Empty space is active** — default to asymmetric layouts; don't fill margins with logos or templated decoration
- **Rule of thirds** — anchor primary subjects on the 3×3 grid intersections, not dead-center
- **Faces and eye-gaze** — orient face-direction toward the focal text/chart, never away from it
- **Full-bleed images** — default to images that bleed off all four edges
- **2D for 2D data** — never apply 3D effects to flat data
- **Logo discipline** — first and last slide only (this aligns with the speaker's existing footer convention; the footer is not a logo)
- **Minimum font size** — body text ~24pt or larger at 16:9 conference resolution
- **Visual relationships** — when an outline slide contains bulleted content, identify which of five relationships the bullets express (flow / structure / cluster / radiate / influence) and convert the bullets into a diagram form rather than a list. Bullets are the fallback only when none of the five relationships fit. See `slide-design-spec.md` §11.13.
- **Image juxtaposition** — when content is comparison-shaped (any of the contrast types from `sparkline`'s middle), prefer paired-image slides over single-image slides. Place two images side-by-side at equal weight, or use before/after with a transition arrow. See `slide-design-spec.md` §11.14.
- **Numerical narrative** — for data slides, choose one of three framing techniques: Scale (anchor against familiar magnitude), Compare (cross-domain comparison), or Context (annotate why the chart's bumps and trends look the way they do). Raw numbers without one of these framings are forgettable. See the "Numerical Narrative — Making Numbers Land" subsection in `patterns/build/vacation-photos.md`.

Speaker-style data in `slide-design-spec.md` Sections 1–10 (extracted from the speaker's actual deck corpus) takes precedence where it exists. The principles in Sections 11.1–11.14 are the default for layout decisions where the corpus is silent.

## Step 5.1: Create the Deck

Read the template path from `speaker-profile.json → infrastructure.template_pptx_path`.
Strip demo slides from template, keep layouts only.

> **Note:** The template stripping, slide deletion, and slide reordering code below
> uses undocumented python-pptx internals (`slides._sldIdLst`, `part.drop_rel()`).
> These work reliably as of python-pptx 0.6.x but could break on a major update.
> If python-pptx adds public APIs for slide deletion/reordering in the future, prefer
> those instead.

```bash
python3 scripts/strip-template.py '{template_pptx_path}' '{output_path}'
```

Then open the clean deck with the MCP: `open_presentation(file_path=...)`.

---

## Step 5.1b: Illustrations (when illustration strategy is defined)

If the outline includes an Illustration Style Anchor section, illustration
generation, build generation, and deck application are owned by the
illustrations skill. Build the deck structure first (Steps 5.2–5.4), then
delegate:

```
Skill(skill: "illustrations")
```

The skill generates missing illustrations, generates build sequences for any
slide with a `- Builds:` block, and runs `apply-illustrations-to-deck.py` to
swap images into the deck, reposition titles into Safe zones, position
IMG+TXT image+text columns, and insert build sequences. Returns control here
once images are approved and applied.

For non-illustrated slides and EXCEPTION-format slides, handle inline as
normal — the `[IMAGE NN]` placeholder resolves to a real asset that
presentation-creator inserts during the slide walk.

---

## Template Layout Map

Read the layout map from `speaker-profile.json → infrastructure.template_layouts[]`.

Each layout entry has: `index`, `name`, `placeholders[]`, and `use_for`.

### Layout Selection Logic (generic mapping)

| Outline slide type | Layout to use | Notes |
|-------------------|--------------|-------|
| Title slide | Layout with CENTER_TITLE only | Opening, section dividers |
| Title + subtitle | Layout with TITLE + SUBTITLE | Bio, shownotes, section openers |
| Bullet list | Layout with TITLE + BODY | Most content slides |
| Comparison / two lists | Layout with TITLE + 2 BODY columns | Before/after, pros/cons |
| Image/meme with title | Layout with TITLE only (no body) | Title in placeholder, image via `manage_image` |
| Full-bleed image/meme | BLANK layout (no placeholders) | Position everything manually |
| Quote / caption | Caption layout if available | Attributed quotes, epigraphs |

**Illustrated slides (FULL / IMG+TXT):** the illustrations skill owns layout
choice and positioning — this skill leaves the slide structure with a title +
empty body and the illustrations skill applies the image post-walk. See the
illustrations skill's `skills/illustrations/references/generation.md` and `skills/illustrations/references/builds.md`
for the format vocabulary, geometry, and build-insertion rules.

**EXCEPTION format:** real assets only — pick the layout per content type
(bullet list, comparison, etc.) and resolve the image source from the
`[IMAGE NN]` placeholder, not from `illustrations/`.

Also review the template catalog in `slide-design-spec.md` Section 7 for rich
patterns (SWOT, timelines, funnels, competitor matrices, etc.) that may be available
in the speaker's template.

---

## Step 5.2: Walk the Outline — Slide Generation Workflow

For each slide in the outline:

1. **Add slide** with the right layout (index from profile template_layouts):
   ```
   add_slide(layout_index=N, title="Slide Title")
   ```

2. **Populate placeholders** — title first, then body:
   ```
   populate_placeholder(slide_index=N, placeholder_idx=0, text="Title")
   populate_placeholder(slide_index=N, placeholder_idx=1, text="Body text")
   ```

3. **Or use bullet points** for list content:
   ```
   add_bullet_points(slide_index=N, placeholder_idx=1, bullet_points=[...])
   ```

4. **For image/meme slides** — use title-only or blank layout, add image:
   ```
   manage_image(slide_index=N, operation="add", image_source="path/to/image.png",
                left=1, top=1.5, width=8, height=5)
   ```

4b. **For illustrated slides (Format: FULL or IMG+TXT):**

   Build the slide structure (layout + title + footer) and skip image
   insertion. The illustrations skill applies the image after this walk
   completes — see Step 5.1b.

   **For EXCEPTION format:**
   - Use appropriate layout for the content type (bullet list, comparison, etc.)
   - Image source comes from the `[IMAGE NN]` placeholder, not from `illustrations/`

5. **For non-placeholder text** (captions, annotations):
   ```
   manage_text(slide_index=N, operation="add", text="Caption",
               left=1, top=6, width=8, height=0.5,
               font_size=14, color=[255,255,255])
   ```

6. **For shapes** (dividers, accent boxes):
   ```
   add_shape(slide_index=N, shape_type="RECTANGLE",
             left=0, top=0, width=10, height=0.3,
             fill_color=[0,188,212])
   ```

### Background Colors

Read `design_rules.background_color_strategy` from the speaker profile. Apply the
strategy when adding slides. Common strategies:
- `random_non_repeating` — pick a random saturated color, never repeat on adjacent slides
- `theme_sequence` — follow the template's built-in color rotation

Read `design_rules.white_black_reserved_for` to know when white/black backgrounds
are appropriate (typically full-bleed image/meme slides only).

### Footer

Read `design_rules.footer` from the speaker profile for exact position, font, size,
and color adaptation rules. Add footer to EVERY slide using `manage_text`. The footer
pattern template is in `footer.pattern` — substitute conference-specific values.

### Text Overflow Prevention

Template placeholders have fixed sizes. To avoid overflow:

- **Titles**: Max ~60 characters. If longer, use `manage_text` with `auto_fit=True`.
- **Body bullets**: Max 6-7 items per placeholder. For more, split across two slides.
- **Bullet text**: Keep individual bullets under ~80 characters.
- **Use `optimize_slide_text`** after populating to auto-resize if needed:
  ```
  optimize_slide_text(slide_index=N, min_font_size=12, max_font_size=28)
  ```

---

## Step 5.3: Inject Speaker Notes (python-pptx) — SEPARATE STEP

**IMPORTANT:** Speaker notes MUST be injected as a separate batch pass AFTER all
slides exist — never inline during slide creation. The MCP PPT server does not
support notes, so use python-pptx in a dedicated second pass.

Save the notes map as JSON (`{"0": "", "1": "Brief intro.", ...}`), then run:

```bash
python3 scripts/inject-speaker-notes.py path/to/deck.pptx notes.json
```

Run this AFTER MCP slide generation is complete, and BEFORE presenting to the author.

> **Keynote compatibility:** The script automatically post-processes the .pptx
> to add a `<p:notesMasterIdLst>` element to `ppt/presentation.xml`. python-pptx
> writes the `notesMaster` relationship but omits this element, which PowerPoint
> tolerates but Keynote rejects as "invalid format". The patch is idempotent and
> only runs when a `notesMaster` relationship is present, so speakers who never
> open Keynote pay zero cost.

---

## Step 5.4: Present to Author

Save and present a generation report with slide count, layouts used, and placeholders
needing author content.

## Step 5.5: Iteration Loop

Free-form conversation. The author gives feedback in whatever format is natural.

### Slide-specific changes

Author says: "Slide 12 — make the title shorter"
→ `populate_placeholder(slide_index=11, placeholder_idx=0, text="New shorter title")`

Author says: "Slide 5 — change to two columns"
→ Cannot change layout of existing slide via MCP. Instead:
  1. Note content of slide 5
  2. Generate a replacement slide with the new layout (appended at end)
  3. Use python-pptx to delete the old slide 5 and reorder the new one into position
  4. Re-open the deck with MCP `open_presentation`

### Batch changes

Read `design_rules.slide_numbers` from the speaker profile. If "never", decline
requests to add slide numbers and explain it's a design rule.

### Content delivery

Author provides an image for a placeholder slide:
→ `manage_image(slide_index=N, operation="add", image_source="/path/to/image.png", ...)`

### Structural changes (python-pptx)

The MCP PPT server cannot delete or reorder slides. Use python-pptx:

**Delete slides:**
```bash
python3 scripts/delete-slides.py path/to/deck.pptx 5 12 15   # 0-based indices
```

**Reorder slides:**
```bash
python3 scripts/reorder-slides.py path/to/deck.pptx --from 5 --to 2
```

After any python-pptx structural operation, re-open the deck with MCP
(`open_presentation`) to continue editing.

## Step 5.6: Final Save

Save the .pptx. Export and publishing happen in Phase 6.

---

## MCP Tool Quick Reference

| Operation | Tool | Key params |
|-----------|------|-----------|
| Add slide | `add_slide` | layout_index, title, background_colors=[[r,g,b]] |
| Set title/body | `populate_placeholder` | slide_index, placeholder_idx, text |
| Add bullets | `add_bullet_points` | slide_index, placeholder_idx, bullet_points[] |
| Add free text | `manage_text` | slide_index, operation="add", text, position, font |
| Add image | `manage_image` | slide_index, operation="add", image_source, position |
| Add shape | `add_shape` | slide_index, shape_type, position, colors |
| Add table | `add_table` | slide_index, rows, cols, data, position |
| Add chart | `add_chart` | slide_index, chart_type, categories, series |
| Fix text overflow | `optimize_slide_text` | slide_index, min/max_font_size |
| Inspect slide | `get_slide_info` | slide_index |
| Save | `save_presentation` | file_path |

---

## PDF Export (Final Step)

After the author declares done, export the .pptx to PDF. The method depends on the
speaker's `publishing_process.export_method` and platform.

Run the export script — it auto-detects PowerPoint (macOS AppleScript) or LibreOffice:

```bash
python3 scripts/export-pdf.py path/to/deck.pptx [path/to/output.pdf]
```

If `output.pdf` is omitted, uses the same name with `.pdf` extension.

The script prefers PowerPoint AppleScript on macOS (if installed), falls back to
LibreOffice CLI. Read `publishing_process.export_method` from the speaker profile
to know which is expected.

---

## Illustration Workflow

When the outline has an Illustration Style Anchor, illustration generation,
build generation, and deck application are owned by the illustrations skill.
See `skills/illustrations/references/generation.md`,
`skills/illustrations/references/builds.md`, and
`skills/illustrations/references/title-placement.md` for setup, edit/fix
workflow, build chaining,
and Safe-zone composition.

---

## File Locations

Read `infrastructure.presentation_file_convention` from the speaker profile for the
directory structure. Typical convention:

```
{presentations-dir}/{conference}/{year}/{talk-slug}/
├── outline.yaml                  ← source of truth (Phase 1/2/3 build it up)
├── narrative.md                  ← generated from outline.yaml (extract-narrative.py)
├── script.md                     ← generated from outline.yaml (extract-script.py)
├── slides.md                     ← generated from outline.yaml (extract-slides.py) — consumed by Phase 5
├── rhetorical-review.md          ← generated from outline.yaml (check-rhetorical.py)
├── {talk-slug}.pptx              ← the deck (Phase 5 output — pptx talks)
├── {talk-slug}.pdf               ← PDF export (Phase 5 final step)
├── {talk-slug}.md                ← renderable deck (Phase 5 output — presenterm talks)
├── assets/                        ← images, memes, screenshots (author provides)
└── illustrations/                 ← generated illustrations (Phase 5 Step 5.1b)
    ├── slide-01.jpg               ← one file per illustrated slide
    ├── slide-02.png
    ├── slide-05-v2.jpg            ← versioned iterations (--fix / --edit / -v)
    ├── builds/                    ← progressive reveal build steps (Phase 5 Step 5.1c)
    │   ├── slide-05-build-00.jpg  ← empty frame
    │   ├── slide-05-build-01.jpg  ← first element revealed
    │   └── slide-05-build-02.jpg  ← second element (full = copy of slide-05)
    └── model-comparison/          ← --compare output (Phase 2 model selection)
```

The speaker's template is read-only — never modify it.

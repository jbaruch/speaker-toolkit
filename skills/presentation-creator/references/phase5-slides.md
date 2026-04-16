# Phase 5: Slide Generation & Interactive Iteration — Detail

Build the .pptx deck from the finalized outline.

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

## Step 5.1b: Generate Illustrations (when illustration strategy is defined)

If the outline includes an Illustration Style Anchor section:

1. Run `generate-illustrations.py <outline.md> remaining` to batch-generate all
   missing illustrations
2. Review generated images with the author — delete and regenerate as needed
3. Once all images are approved, proceed to slide population

Images are stored in `illustrations/` alongside the outline file. See
**Image Generation Setup** below for prerequisites.

## Step 5.1c: Generate Builds (when outline has build specifications)

After illustrations are approved, generate progressive-reveal build images for slides
that define a `- Builds:` section in the outline.

**When to use builds:**
- Complex diagrams revealed one element at a time
- Checklists that accumulate items across the talk
- Step-by-step processes shown progressively
- Any visual that benefits from gradual reveal (NOT PowerPoint animations — these are
  separate slides with separate images)

**Backwards-chaining workflow:**
1. Start from the full slide image (`illustrations/slide-NN.ext`)
2. Use image editing to remove the last element → that's build step N-1
3. Use the N-1 output as input, remove the next element → that's N-2
4. Continue until build-00 (empty frame with title/borders only)
5. The final build step is a copy of the full slide image

This backwards approach produces better results than building up from empty, because
the model preserves the existing composition and style at each step.

**Run:**
```bash
python3 generate-illustrations.py presentation-outline.md --build 5    # one slide
python3 generate-illustrations.py presentation-outline.md --build all  # all builds
```

**Output:** `illustrations/builds/slide-NN-build-MM.jpg`

**Key instructions for build edit prompts:**
- Each step description should explicitly say what to KEEP: "keep the road",
  "keep the soldiers", etc.
- Always include: "no parchment patch", "no new frames", "solid lines not dashed"
- The edit safety suffixes ("DO NOT add any new elements", "let background continue
  naturally") are auto-appended by the script

**Review:** Check each build step image. For near-perfect results, use `--fix` for
targeted corrections rather than regenerating the entire chain.

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

**Illustration-aware formats** (when outline has an Illustration Style Anchor):

| Outline Format     | Layout to Use                 | Image Handling                                           |
|--------------------|------------------------------|----------------------------------------------------------|
| FULL               | BLANK layout                 | `manage_image` full-bleed from `illustrations/slide-NN.ext` |
| FULL + text overlay | BLANK layout                | `manage_image` full-bleed + `manage_text` overlay on top  |
| IMG+TXT            | TITLE only (no body)         | `manage_image` ~60% of slide + `manage_text` beside/below |
| EXCEPTION          | Per content type (see above) | Real asset from `[IMAGE NN]` placeholder path             |

Match these generic types to the speaker's actual layout names/indices from the profile.

**Build (progressive reveal) slide insertion:**

Build slides are inserted as separate slides in the deck (not PowerPoint animations).
Each build step is a full-bleed image from `illustrations/builds/slide-NN-build-MM.jpg`.

| Step | Source | Layout | Notes |
|------|--------|--------|-------|
| build-00 | `builds/slide-NN-build-00.jpg` | BLANK | Empty frame — first slide shown |
| build-01 | `builds/slide-NN-build-01.jpg` | BLANK | First element revealed |
| ... | ... | BLANK | Progressive reveals |
| build-N | Copy of `slide-NN.ext` | BLANK | Full image — final reveal |

Insertion rules:
- Insert build slides in order: build-00 (empty), build-01, ..., build-N (full)
- All build slides use the BLANK layout with `manage_image` full-bleed positioning
  (`left=0, top=0, width=10, height=7.5`)
- Speaker notes go ONLY on the final build step (the full image). Earlier build steps
  get empty notes — the speaker advances through them silently or with ad-lib narration
- Build slides count toward the slide budget — factor them in during Phase 4 guardrails
- The final build step (build-N) is visually identical to the parent slide. In the deck,
  the parent slide is replaced by its build sequence (not duplicated after it)

```python
# Example: inserting build slides for slide 5 with 3 build steps
builds_dir = "illustrations/builds"
for step in range(0, 4):  # build-00 through build-03
    img_path = f"{builds_dir}/slide-05-build-{step:02d}.jpg"
    # add_slide with BLANK layout
    # manage_image full-bleed
```

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

4b. **For illustrated slides** (when outline has Format: FULL or IMG+TXT):

   Resolve the image file: `illustrations/slide-{NN}.jpg` (or `.png`), where NN is
   the zero-padded slide number from the outline.

   **FULL format** (full-bleed):
   ```
   # Use BLANK layout
   manage_image(slide_index=N, operation="add",
       image_source="illustrations/slide-{NN}.jpg",
       left=0, top=0, width=10, height=7.5)
   # If text overlay specified:
   manage_text(slide_index=N, operation="add", text="...",
       left=0.5, top=5.5, width=9, height=1.5,
       font_size=36, color=[255,255,255])
   ```

   **IMG+TXT format** (illustration + text):
   ```
   # Use TITLE-only layout
   manage_image(slide_index=N, operation="add",
       image_source="illustrations/slide-{NN}.jpg",
       left=0.3, top=0.8, width=4, height=6)
   # Populate title placeholder with slide title
   # manage_text for additional text beside the image
   ```

   **EXCEPTION format**:
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

## Image Generation Setup

Before generating illustrations, ensure:

1. **API Key** — add your Gemini key to `{vault}/secrets.json` (preferred):
   ```json
   { "gemini": { "api_key": "your-key-here" } }
   ```
   Or set the `GEMINI_API_KEY` environment variable as a fallback:
   ```bash
   export GEMINI_API_KEY="your-key-here"
   ```
   Get a key from https://aistudio.google.com/app/apikey

2. **Model availability** — verify the model specified in the outline header
   is accessible with your key. The script reads the model name from the
   `**Model:** \`model-name\`` line in the Illustration Style Anchor section.

3. **Python 3** — the script uses only stdlib (`urllib`, `json`, `base64`).
   No pip install needed.

4. **Run the script:**
   ```bash
   python3 generate-illustrations.py presentation-outline.md remaining
   ```
   Options: `all`, `remaining`, or specific slide numbers (`2 5 9`, `2-10`)

5. **Model comparison** (during Phase 2 model selection):
   ```bash
   python3 generate-illustrations.py presentation-outline.md --compare 2
   ```
   Generates the same prompt across multiple Gemini image models for visual
   comparison. Results go to `illustrations/model-comparison/`.

6. **Review & iterate** — check generated images in the `illustrations/`
   directory. Delete any that need regeneration and re-run with `remaining`.

7. **Image editing** (for targeted changes to existing images):
   ```bash
   python3 generate-illustrations.py presentation-outline.md --edit 5 "Erase the bottom-right label"
   ```
   Sends the existing `slide-05` image + edit prompt to the model. Output saves as
   a new version (`slide-05-v2.jpg`). Safety suffixes are auto-appended.

8. **Targeted fix pass** (iterate on near-perfect images):
   ```bash
   python3 generate-illustrations.py presentation-outline.md --fix 5 "Make the road more prominent. Keep the soldiers."
   ```
   Finds the latest version of the slide image and applies the fix, saving as
   the next version number. Use `--fix` instead of regeneration when 90%+ of the
   image is correct.

9. **Build generation** (progressive reveals):
   ```bash
   python3 generate-illustrations.py presentation-outline.md --build 5
   python3 generate-illustrations.py presentation-outline.md --build all
   ```
   Generates backwards-chained build steps from the full slide image.
   Output: `illustrations/builds/slide-NN-build-MM.jpg`

10. **Versioned generation** (generate without overwriting):
    ```bash
    python3 generate-illustrations.py presentation-outline.md -v 2 5 9
    ```
    Saves as `slide-NN-vM.ext` instead of overwriting the base image.

---

## Illustration Editing & Iteration Guidelines

Hard-won lessons from generating large illustration sets (50+ images). These are
Gemini-specific behaviors discovered through production use — a general-purpose agent
will not know them without this context.

**When to regenerate vs. edit — the asymmetry rule:**
- **Content additions** (adding a person, changing composition, adding a new element) →
  **always regenerate from the full prompt**. Gemini's image editing strips the style
  anchor when adding content — the new element renders in a flat generic style while the
  rest of the image keeps the original style. This looks terrible and is not fixable
  with iteration. Example: asking to "add a third soldier" to a military manual style
  image will produce a flat cartoon soldier next to detailed pen-and-ink ones.
- **Content modifications** (changing a hat style, making text bigger, recoloring) →
  **regenerate, not edit**. Same problem: modifications that change the visual content
  trigger the same style-stripping behavior as additions.
- **Content removal** (erase a label, remove an element, remove an unwanted border) →
  **image editing works well**. The model preserves the existing style when only
  removing content because it doesn't need to generate new visual elements.
- **Rule of thumb**: if the edit requires the model to *draw something new*, regenerate.
  If it only requires *erasing or hiding* existing content, use image editing.

**Never simplify original prompts — the specificity rule:**
The full style anchor with ALL its specific details ("decorative military document
border ornaments, classification stamps, and technical manual header formatting") is
what produces the distinctive style. When someone shortens the anchor to save time
(e.g., "Military manual style. Pen and ink."), the result looks generic — the model
falls back to its default interpretation of "military" rather than the specific
aesthetic the anchor describes. **Only append** to the anchor (e.g., add "large bold
font", "WWII uniforms"), **never trim or paraphrase it**. When auditing prompts,
flag any prompt that is significantly shorter than the full style anchor as a
simplified-anchor anti-pattern.

**Prompt engineering for edits — three mandatory components:**
1. **Safety suffix: "DO NOT add any new elements."** — Gemini's editing mode
   aggressively adds decorative elements (frames, borders, ornamental corners) that
   were not in the original image. This suffix suppresses that behavior. Required on
   every edit prompt.
2. **Background suffix: "Let background continue naturally -- no parchment patch."** —
   when erasing content, Gemini sometimes fills the gap with a flat-colored rectangle
   ("parchment patch") instead of continuing the background texture. This suffix
   prevents that artifact. Required when erasing content.
3. **Explicit preservation list: "Keep the [X]. Keep the [Y]."** — Gemini removes
   elements it was not asked to remove. If you say "erase the label", it may also
   remove nearby soldiers, roads, or border ornaments. You must explicitly list
   everything that should remain. When auditing edit prompts, flag any removal prompt
   that lacks explicit preservation instructions.

The `--edit` and `--fix` commands auto-append suffixes #1 and #2, but you must
always add #3 (preservation list) manually — the script cannot know what to preserve.

**Versioning strategy — never overwrite during iteration:**
- Save every iteration as a new version: `slide-12-v2.jpg`, `slide-12-v3.jpg`, etc.
- Never overwrite `slide-12.jpg` during iteration — keep the original as fallback
- The `--fix` command auto-versions; `--edit` also auto-versions
- Use `-v` flag with normal generation to version instead of overwrite
- Compare versions side-by-side before promoting one to the base name
- When writing triage plans or fix commands, always specify the versioned output path

**Targeted fix passes — the 90% rule:**
- For near-perfect images (90%+ correct), use `--fix` rather than full regeneration
- Fix passes preserve most of the image while correcting specific issues
- Chain multiple fixes if needed: v2 → v3 → v4, each improving on the previous
- `--fix` automatically finds the latest version and saves the next one

**PIL/programmatic masking — never use for builds or edits:**
- Never use PIL, ImageMagick, or any programmatic image manipulation to create builds
  or fix illustrations. Pasting colored rectangles or applying masks produces visible
  texture mismatches (e.g., a flat parchment-colored rectangle on a textured
  background). Always use the model's native image editing API instead.
- When auditing fix logs, flag any use of PIL/Pillow, ImageMagick, or programmatic
  image manipulation for illustration work as a technique anti-pattern.

---

## File Locations

Read `infrastructure.presentation_file_convention` from the speaker profile for the
directory structure. Typical convention:

```
{presentations-dir}/{conference}/{year}/{talk-slug}/
├── {talk-slug}.pptx              ← the deck (Phase 5 output)
├── {talk-slug}.pdf               ← PDF export (Phase 5 final step)
├── presentation-spec.md           ← the spec: slug, mode, duration (Phase 1 output)
├── presentation-outline.md        ← the outline (Phase 3/4 output)
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

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
The deck is built by the real PowerPoint app from a flat op sequence: `BuildDeck`
opens a uniquely-named COPY of the template (for its custom layouts + masters),
deletes the template's demo slides, then creates every slide from the ops and
saves the output. You emit the ops while walking the outline (Step 5.2), then
validate and build:

```bash
python3 scripts/validate-deckops.py ops.txt
scripts/build-deck.sh '{template_copy_pptx_path}' '{output_path}' ops.txt
```

Op vocabulary, field layout, and state rules: `references/deckops-spec.md`. The
template is read-only — pass a uniquely-named copy. macOS + Microsoft PowerPoint
only; on first use walk the user through `references/deck-editing-setup.md`.

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
| Image/meme with title | Layout with TITLE only (no body) | Title in placeholder, image via an `IMAGE` op |
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

Walk the outline in order and append ops to the sequence — one slide is a `SLIDE`
op followed by its content ops. Field layout and geometry (points):
`references/deckops-spec.md`.

1. **Start the slide** with the right layout (0-based index from profile template_layouts):
   `SLIDE␟<layout_index>`

2. **Set placeholders** — title, subtitle, body:
   `TITLE␟<text>`  ·  `SUBTITLE␟<text>`  ·  `BODY␟<text>`

3. **Bullet list content** — one op per bullet, indent level 0-based:
   `BULLET␟<level>␟<text>`

4. **Image/meme slides** — title-only or blank layout, then an image:
   `IMAGE␟<left>␟<top>␟<width>␟<height>␟<path>`

4b. **For illustrated slides (Format: FULL or IMG+TXT):**

   Emit the slide structure (layout, `TITLE`, `FOOTER`) and OMIT the `IMAGE` op.
   The illustrations skill applies the image after the build completes — see
   Step 5.1b.

   **For EXCEPTION format:**
   - Use appropriate layout for the content type (bullet list, comparison, etc.)
   - Image source comes from the `[IMAGE NN]` placeholder, not from `illustrations/`

5. **Non-placeholder text** (captions, annotations):
   `TEXT␟<left>␟<top>␟<width>␟<height>␟<text>`

6. **Shapes** (dividers, accent boxes):
   `SHAPE␟<msoAutoShapeType>␟<left>␟<top>␟<width>␟<height>`

7. **Tables and charts:**
   `TABLE␟<rows>␟<cols>␟<l>␟<t>␟<w>␟<h>` then `CELL␟<row>␟<col>␟<text>` per cell;
   `CHART␟<xlChartType>␟<l>␟<t>␟<w>␟<h>` then `CAT␟<name>` and `SERIES␟<name>␟<v>␟<v>…`.

### Background Colors

Read `design_rules.background_color_strategy` from the speaker profile, then emit a
`BG␟<r>␟<g>␟<b>` op on the slide. Common strategies:
- `random_non_repeating` — pick a random saturated color, never repeat on adjacent slides
- `theme_sequence` — follow the template's built-in color rotation

Read `design_rules.white_black_reserved_for` to know when white/black backgrounds
are appropriate (typically full-bleed image/meme slides only).

### Footer

Read the footer text pattern from `design_rules.footer.pattern`, substitute
conference-specific values, and add a footer to EVERY slide with a `FOOTER␟<text>`
op. The op carries only the text — `BuildDeck` applies fixed footer geometry and
font size; the profile's position / font / size / color fields are not yet wired
into the op.

### Text Overflow Prevention

Template placeholders have fixed sizes. To avoid overflow:

- **Titles**: Max ~60 characters.
- **Body bullets**: Max 6-7 items per placeholder. For more, split across two slides.
- **Bullet text**: Keep individual bullets under ~80 characters.
- **Emit an `OPTIMIZE` op** after the slide's content to autofit each text box to its shape.

---

## Step 5.3: Inject Speaker Notes (real PowerPoint) — SEPARATE STEP

**IMPORTANT:** Speaker notes MUST be injected as a separate batch pass AFTER all
slides exist — never inline during slide creation.

Save the notes map as JSON (`{"0": "", "1": "Brief intro.", ...}`, 0-based slide
indices), then inject via the real PowerPoint app — it writes valid notes OOXML,
so the `<p:notesMasterIdLst>` Keynote patch the old python-pptx pass needed is no
longer required (see `rules/deck-editing-rules.md`):

```bash
scripts/inject-notes.sh <uniquely-named deck copy> <out.pptx> notes.json
```

Run this AFTER slide generation, and BEFORE the final `apply-backgrounds.sh`
pass (the VBA background pass must be the last write). macOS + PowerPoint only.

> **Keynote compatibility:** Real PowerPoint writes the `<p:notesMasterIdLst>`
> element natively, so notes-bearing decks open in Keynote with no patch. The
> old python-pptx pass had to post-process the `.pptx` to add it — that hack is
> retired with the python path.

---

## Step 5.4: Present to Author

Save and present a generation report with slide count, layouts used, and placeholders
needing author content.

## Step 5.5: Iteration Loop

Free-form conversation. The author gives feedback in whatever format is natural.
Edits drive the real PowerPoint app — there is no open session to mutate. Two
mechanisms cover iteration: a global text replace via `run-deck-ops.sh`'s
`replaceStr`, and build-then-assemble — rebuild the affected slide as a
one-`SLIDE` fragment with `build-deck.sh`, then position it with
`run-deck-ops.sh`'s order string (see `references/deckops-spec.md`).

### Slide-specific changes

Author says: "Slide 12 — make the title shorter"
→ global text replace (replaces every occurrence, so use distinctive text):
  `run-deck-ops.sh <deck> <out> "" "<unchanged order>" "Old long title=>Shorter"`

Author says: "Slide 5 — change to two columns"
  1. Build a one-`SLIDE` fragment on the two-column layout with `build-deck.sh`.
  2. Use `run-deck-ops.sh` to drop the old slide 5 and place the fragment in its
     position — express the FINAL slide order (see Structural changes below).

### Batch changes

Read `design_rules.slide_numbers` from the speaker profile. If "never", decline
requests to add slide numbers and explain it's a design rule.

### Content delivery

Author provides an image for a placeholder slide:
→ Rebuild that slide as a one-`SLIDE` fragment with an `IMAGE` op, then position
  it with `run-deck-ops.sh` (build-then-assemble).

### Structural changes (real PowerPoint via RunDeckOps)

Make ALL structural edits (delete / reorder / cross-deck import / global text
replace) by driving the real PowerPoint app, which serializes the file and
preserves backgrounds, fonts, masters, and Keynote-openability. python-pptx
editing strips each slide's per-slide background fill — on illustrated decks that
silently flattens full-bleed art to bare color. See `rules/deck-editing-rules.md`.

```bash
scripts/run-deck-ops.sh <basePath> <outPath> <importSpec> <orderStr> <replaceStr>
```

`orderStr` is the FINAL slide sequence as space-separated `<alias>:<1-based #>`
tokens; alias `BASE` is `basePath`. Delete by OMITTING a slide; reorder by
listing tokens in the target order; import by adding an alias to `importSpec`.

```
# drop slide 3, and move slide 6 ahead of slide 4:
"BASE:1 BASE:2 BASE:6 BASE:4 BASE:5"
```

macOS + Microsoft PowerPoint only. On first use, walk the user through
`references/deck-editing-setup.md` (enable VBA macros, import `RunDeckOps.bas`
into a `DeckOps.pptm` container, grant Automation consent). The macro writes a
COPY — the original is untouched; continue editing from the OUTPUT deck.

## Step 5.6: Final Save

Save the .pptx. Export and publishing happen in Phase 6.

---

## Deck Op Quick Reference

| Operation | Op | Fields |
|-----------|------|-----------|
| Start slide | `SLIDE` | `<0-based layout index>` |
| Set title / subtitle / body | `TITLE` / `SUBTITLE` / `BODY` | `<text>` |
| Add bullet | `BULLET` | `<0-based level>␟<text>` |
| Add free text | `TEXT` | `<l>␟<t>␟<w>␟<h>␟<text>` |
| Add image | `IMAGE` | `<l>␟<t>␟<w>␟<h>␟<path>` |
| Add shape | `SHAPE` | `<msoAutoShapeType>␟<l>␟<t>␟<w>␟<h>` |
| Slide background | `BG` | `<r>␟<g>␟<b>` |
| Footer | `FOOTER` | `<text>` |
| Autofit text | `OPTIMIZE` | — |
| Add table / cell | `TABLE` / `CELL` | `<rows>␟<cols>␟<l>␟<t>␟<w>␟<h>` / `<row>␟<col>␟<text>` |
| Add chart / category / series | `CHART` / `CAT` / `SERIES` | `<xlChartType>␟<l>␟<t>␟<w>␟<h>` / `<name>` / `<name>␟<v>…` |

Full spec (delimiter, state rules, enum values, examples): `references/deckops-spec.md`.

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

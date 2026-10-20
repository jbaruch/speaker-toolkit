# PowerPoint Construction

## Create the Deck

This step applies only when `talk.engine` is `pptx` (or null with a pptx
inference confirmed in Branch on the Engine).

Read the template path from `speaker-profile.json → infrastructure.template_pptx_path`.
The deck is built by the real PowerPoint app from a flat op sequence: `BuildDeck`
opens a uniquely-named COPY of the template (for its custom layouts + masters),
deletes the template's demo slides, then creates every slide from the ops and
saves the output. You emit the ops while walking the outline (Walk the Outline below), then
validate and build:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/validate-deckops.py" ops.txt
bash "{speaker_toolkit_root}/skills/presentation-creator/scripts/build-deck.sh" '{template_copy_pptx_path}' '{output_path}' ops.txt
```

Op vocabulary, field layout, and state rules: [deckops-spec.md](deckops-spec.md). The
template is read-only — pass a uniquely-named copy. macOS + Microsoft PowerPoint
only. Before the first pass run
`"{python_path}" "{speaker_toolkit_root}/skills/presentation-creator/scripts/deckops-doctor.py" --vault-root "{vault_root}"`
and require `status: ok`; anything else routes into
[deck-editing-setup.md](deck-editing-setup.md) at the step its `next_step` names. Do not
guess whether this is a first run — the doctor answers it, and it also catches a
closed container or a stale macro import before a long build half-finishes.

---

## Illustrations (when illustration strategy is defined)

If the outline includes an `style_anchor` block, illustration
generation, build generation, and deck application are owned by the
illustrations skill. Build the deck structure first (Walk the Outline through
Present to Author below), then delegate:

```
Skill(skill: "illustrations")
```

The skill generates missing illustrations, generates build sequences for any
slide with a `builds[]` block, and runs `apply-illustrations-to-deck.py` to
swap images into the deck, reposition titles into Safe zones, position
IMG+TXT image+text columns, and insert build sequences. Returns control here
once images are approved and applied.

For non-illustrated slides and EXCEPTION-format slides, handle inline as
normal — the `[IMAGE NN]` placeholder resolves to a real asset that
presentation-builder inserts during the slide walk.

### Which ops to omit on illustrated slides

For FULL and IMG+TXT slides, emit only the slide structure (layout, `TITLE`,
`FOOTER`) and **omit the `IMAGE` op** — the slide is left without a picture
shape. The illustrations skill fills it in the post-build apply pass: FULL slides
get a slide BACKGROUND FILL (set by the PowerPoint `apply-backgrounds.sh` pass,
so the layout's halftone-dot overlay covers them); IMG+TXT slides get a
left-column picture shape via `apply-illustrations-to-deck.py`.

When `outline.yaml`'s `style_anchor.composition` is `poster-theatrical`, also
**omit the `TITLE` and `FOOTER` ops** for the illustrated FULL slides (those
with an `image_prompt`) — the title and footer are rendered into the
illustration itself, so the only post-build inserts on those slides are the
background fill and the QR code. A FULL slide without an `image_prompt` gets no
illustration, so it keeps its `TITLE` and `FOOTER` ops.

The illustrations skill reads `outline.yaml` directly (`style_anchor` plus
per-slide `image_prompt` / `builds`) — no surfacing or format translation needed.

### Post-build pass order

The passes below renumber or overwrite each other, so run them in exactly this
order:

1. **Expand builds** — if any slide has progressive-reveal builds, expand them
   FIRST with
   `"{speaker_toolkit_root}/skills/presentation-creator/scripts/expand-builds.sh"`
   (manifest from `build-expansion-manifest.py`): it replaces each parent slide
   with its build frames as full-bleed slides. Pass the speaker-notes JSON to
   `build-expansion-manifest.py --notes` so each build parent's note rides onto
   its FINAL frame during expansion (per
   `skills/illustrations/references/builds.md`); do not re-target those parent
   indices in any later notes pass. Expansion renumbers later slides, so notes,
   backgrounds, and QR must key on the POST-expansion deck.
2. **Inject remaining speaker notes** — Inject Speaker Notes below. When the deck was
   expanded, drop the build-parent entries already carried by `--notes` and key
   the remaining notes on the post-expansion slide order. With no builds, the
   original indices apply directly.
3. **Apply backgrounds** — set the FULL-slide backgrounds via
   `"{speaker_toolkit_root}/skills/presentation-creator/scripts/apply-backgrounds.sh"`
   using the manifest from the apply pass. It must run LAST; any later
   python-pptx save would re-drop the per-slide background fills.

See `rules/deck-editing-rules.md`.

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

## Walk the Outline — Slide Generation Workflow

Walk the outline in order and append ops to the sequence — one slide is a `SLIDE`
op followed by its content ops. Field layout and geometry (points):
[deckops-spec.md](deckops-spec.md).

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
   the Illustrations section above.

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

## Inject Speaker Notes (real PowerPoint) — SEPARATE PASS

**IMPORTANT:** Speaker notes MUST be injected as a separate batch pass AFTER all
slides exist — never inline during slide creation.

Save the notes map as JSON (`{"0": "", "1": "Brief intro.", ...}`, 0-based slide
indices), then inject via the real PowerPoint app — it writes valid notes OOXML,
so the `<p:notesMasterIdLst>` Keynote patch the old python-pptx pass needed is no
longer required (see `rules/deck-editing-rules.md`):

```bash
bash "{speaker_toolkit_root}/skills/presentation-creator/scripts/inject-notes.sh" <uniquely-named deck copy> <out.pptx> notes.json
```

Run this AFTER slide generation, and BEFORE the final `apply-backgrounds.sh`
pass (the VBA background pass must be the last write). macOS + PowerPoint only.

> **Keynote compatibility:** Real PowerPoint writes the `<p:notesMasterIdLst>`
> element natively, so notes-bearing decks open in Keynote with no patch. The
> old python-pptx pass had to post-process the `.pptx` to add it — that hack is
> retired with the python path.

---

## Present to Author

Save and present a generation report with slide count, layouts used, and placeholders
needing author content.

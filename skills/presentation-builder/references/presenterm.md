# Presenterm Construction

Applies when `talk.engine` is `presenterm`. Hand-author the renderable deck as
`{slug}.md` (e.g., `devoxx-uk-2026-300-tokens.md`) using the `slides.md`
build-sheet as input:

- each slide's `text_overlay:` becomes the slide body;
- each slide's `script:` becomes the `speaker_note: |` HTML comment.

The slug-named deck travels with the talk directory; `slides.md` remains the
toolkit-canonical build-sheet.

---

Resolve `talk.engine` and `talk.deck_theme` through the non-owner outline reader.
Use the approved theme pointer; do not run PowerPoint setup or image generation.
A style anchor on a presenterm outline is not authority to run a pptx illustration
pipeline. Return to presentation-creator if the engine choice needs changing.

Run the existing renderer's probe to inspect flavor and source structure before
preview/export; its JSON describes what was found without requiring a PDF build:

```bash
"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/render-markdown-deck.py" path/to/deck.md --probe
```

Present the deck for author review. Content edits first return to the outline
owner; then regenerate the build-sheet and update the deck. Keep `slides.md` as
a generated build-sheet, not the rendered deck source. Export uses [export.md](export.md).

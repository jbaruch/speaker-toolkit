# Deck Editing Rules

How to make STRUCTURAL edits (delete / reorder / cross-deck import) to an
existing `.pptx` — distinct from generating a deck from scratch (see
`rules/slide-generation-rules.md`). The default tools silently destroy
illustrated decks; this rule says what to use instead.

## Don't Edit Illustrated Decks With python-pptx

- python-pptx (and `delete-slides.py` / `reorder-slides.py`) and any clipboard
  `Slides.Paste` apply DESTINATION formatting and drop each slide's own
  `<p:bg>` picture fill. On comic-book / illustrated decks the full-bleed art
  is usually a per-slide background fill, so a python-pptx trim flattens those
  slides to bare color (observed: a 51 MB deck cut to 6.2 MB with every
  background gone, while picture *shapes* survived).
- python-pptx editing the OOXML from outside the app also breaks relationships
  and strict OOXML, which Keynote then refuses to open.
- The cross-platform `delete-slides.py` / `reorder-slides.py` remain fine ONLY
  for plain, non-illustrated decks where no slide carries a background fill.

## Use Real PowerPoint via RunDeckOps (macOS)

- Drive the actual PowerPoint app so PowerPoint serializes the file — fonts,
  full-bleed backgrounds, masters, and relationships are preserved and the
  output stays Keynote-openable. The original is never modified (the macro
  writes a COPY).
- `skills/presentation-creator/scripts/RunDeckOps.bas` builds the target deck
  with `Slides.InsertFromFile` (the programmatic "Reuse Slides", keep-source-
  formatting — NOT clipboard paste). Invoke it through
  `skills/presentation-creator/scripts/run-deck-ops.sh`:
  ```bash
  run-deck-ops.sh <basePath> <outPath> <importSpec> <orderStr> <replaceStr>
  # orderStr: "BASE:1 BASE:2 voxxed:13 BASE:49"  (alias:1-based-slide-#)
  ```
- One-time setup is a manual, GUI-bound sequence (enable VBA macros, create the
  `DeckOps.pptm` macro container, import the `.bas`, grant Automation consent).
  Walk the user through it interactively the first time — see
  `skills/presentation-creator/references/deck-editing-setup.md`.

## macOS-Only — Untestable in CI

- This method requires the Microsoft PowerPoint app and macOS Automation, so it
  CANNOT run in Linux CI (there is no PowerPoint on Linux) and ships without
  automated tests by design. Validate output manually: re-open in PowerPoint
  AND Keynote, and confirm file size recovers and a `<p:bg>`-blipFill check
  finds the expected slides.

## Mac PowerPoint VBA Landmines (all handled in RunDeckOps)

- **Filename collision:** PowerPoint keys open decks by filename and silently
  returns an already-open same-named deck from `Presentations.Open`. Always
  operate on UNIQUELY-NAMED copies; the macro also guards and errors loudly.
- **`Slide.MoveTo` / `Slides.FindBySlideID` raise E_INVALIDARG** on current Mac
  builds — avoided by appending in target order via `InsertFromFile`.
- **`SaveCopyAs` rejects `FileFormat` / `EmbedTrueTypeFonts` enum args** — use a
  bare `SaveCopyAs FileName:=...` (base is already `.pptx`).
- **Sandboxed PowerPoint can't create a file in a Google Drive File-Provider
  folder** (E_FAIL): save to a local staging path, then move into Drive with
  the shell. `run-deck-ops.sh` does this automatically.

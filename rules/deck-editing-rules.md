---
alwaysApply: true
---

# Deck Editing Rules

How to make STRUCTURAL edits (delete / reorder / cross-deck import) to an
existing `.pptx` and how to apply illustration backgrounds — distinct from
generating slide structure (see `rules/slide-generation-rules.md`).

## Don't Edit Decks With python-pptx

- python-pptx and clipboard `Slides.Paste` drop each slide's `<p:bg>` picture
  fill, flattening illustrated decks whose full-bleed art is a background fill.
- python-pptx editing OOXML from outside the app breaks strict OOXML that
  Keynote refuses to open.
- All structural edits go through RunDeckOps — there is no python-pptx
  slide-delete / slide-reorder path.

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

## Add a Generated Illustration as a Slide Background

- A generated illustration must become the slide's BACKGROUND FILL, not a
  top-pasted picture: the layout's halftone-dot overlay sits above the slide
  background but below shapes, so a pasted picture lands above the dots.
- Don't hand-build the slide in python-pptx: a fresh deck can't borrow the
  source deck's layout (and its overlay).
- `RunDeckOps.bas`'s `MakeBgImageSlide` clones a comic template slide, sets
  `Slide.Background.Fill.UserPicture`, retitles, and saves a 1-slide deck. Pick a
  template whose title sits in the image's clear safe zone. Invoke via
  `skills/presentation-creator/scripts/make-bg-slide.sh`, then import with
  `run-deck-ops.sh` (order token `<alias>:1`).
- Generate the illustration first with the `illustrations` skill, then make it a
  background slide here.

## Set Illustration Backgrounds in Bulk at Creation Time

- When building a NEW deck, FULL-slide illustrations must also be slide
  BACKGROUND FILLS, not picture shapes — same overlay reason as above. python-pptx
  must not insert them as shapes, and must not be the last writer (it re-drops
  `<p:bg>` fills on save).
- `apply-illustrations-to-deck.py` records each FULL slide in a backgrounds
  manifest (`--backgrounds-out`) and applies only scrim + title; it does NOT
  insert FULL-slide pictures. IMG+TXT slides keep a left-column picture shape.
- `RunDeckOps.bas`'s `ApplyBackgrounds` then sets all FULL backgrounds via
  `Slide.Background.Fill.UserPicture` in one pass. Invoke via
  `skills/presentation-creator/scripts/apply-backgrounds.sh <baseCopy> <out> <manifest.json>`.
- Run this as the FINAL write of the build — after the structural walk, scrim/
  title, and speaker-note injection — so no later python-pptx save drops the fills.

## macOS-Only — VBA Layer Untestable in CI

- The PowerPoint-driving layer (VBA + AppleScript) needs the Microsoft PowerPoint
  app and macOS Automation, so it CANNOT run in Linux CI. Validate it manually:
  re-open output in PowerPoint AND Keynote; confirm size recovers and a
  `<p:bg>`-blipFill check finds the expected slides.
- The deterministic Python/shell helpers (illustration apply, manifest→spec) ARE
  unit-tested in `tests/` — only the PowerPoint-driving layer is exempt.

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

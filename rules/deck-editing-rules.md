# Deck Editing Rules

How to make STRUCTURAL edits (delete / reorder / cross-deck import) to an
existing `.pptx` — distinct from generating a deck from scratch (see
`rules/slide-generation-rules.md`). python-pptx silently destroys illustrated
decks; this rule says what to use instead.

## Don't Edit Decks With python-pptx

- python-pptx and any clipboard `Slides.Paste` apply DESTINATION formatting and
  drop each slide's own `<p:bg>` picture fill. On comic-book / illustrated decks
  the full-bleed art is usually a per-slide background fill, so a python-pptx
  trim flattens those slides to bare color (picture *shapes* survive, per-slide
  `<p:bg>` fills do not).
- python-pptx editing the OOXML from outside the app also breaks relationships
  and strict OOXML, which Keynote then refuses to open.
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
  top-pasted picture. In these comic decks the halftone-dot pattern is an
  overlay picture on the slide LAYOUT, painted above the slide background and
  below the slide's text. A picture pasted as a shape lands ABOVE that overlay
  (so the dots don't cover it) and won't match the other slides.
- Don't hand-build the slide in python-pptx either: a fresh deck can't borrow
  the source deck's layout (and thus its dot overlay).
- `RunDeckOps.bas`'s `MakeBgImageSlide` does it right: CLONE a comic template
  slide (inheriting the layout's dot overlay, the styled title box, and the
  footer), set `Slide.Background.Fill.UserPicture` to the image, retitle, and
  save a 1-slide deck. Pick a template whose title sits in the same region the
  image left clear (the title's safe zone). Invoke via
  `skills/presentation-creator/scripts/make-bg-slide.sh`, then import the
  resulting slide into the deck with `run-deck-ops.sh` (order token `<alias>:1`).
- Generate the illustration first with the `illustrations` skill (style anchor +
  title-safe-zone), then make it a background slide here.

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

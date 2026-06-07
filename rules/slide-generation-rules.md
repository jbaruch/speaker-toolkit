# Slide Generation Rules

## Build the Deck With BuildDeck — Not python-pptx, Not MCP

Slide structure is created by the real PowerPoint app via the `BuildDeck` macro
(`scripts/build-deck.sh`), driven by a flat op sequence — never python-pptx, never
the MCP PPT server. The agent emits the ops; `BuildDeck` executes them. Op
vocabulary and state rules: `skills/presentation-creator/references/deckops-spec.md`.

## Speaker Notes — Separate Batch Pass

Speaker notes MUST be injected as a separate step AFTER all slides are created,
never inline during slide creation. Inject them with the `SetSpeakerNotes` macro
(`scripts/inject-notes.sh`) — see Keynote Compatibility below.

## Template Stripping — Handled by BuildDeck

The clean deck retains only the template's layout definitions, no demo/sample
slides. `BuildDeck` deletes the template's demo slides before creating content,
so stripping is not a separate step.

## Keynote Compatibility

Keynote uses a stricter OOXML parser than PowerPoint. The rules below
prevent generated `.pptx` files from being rejected on import.

### Speaker notes — written by real PowerPoint

Inject notes via the real PowerPoint app (`scripts/inject-notes.sh` →
`SetSpeakerNotes`); it writes the required `<p:notesMasterIdLst>` element
natively. No manual patch — the python-pptx pass that omitted-then-patched it
is retired. See `rules/deck-editing-rules.md`.

### Use rectangles for decorative lines — never connectors

Connectors emit `<p:cxnSp>` elements that Keynote's parser may reject. For a
decorative line, emit a thin `SHAPE` op with a rectangle `msoAutoShapeType` (a
small height makes it read as a line) — never a connector.

### Never create slide shapes then remove them via raw XML in the same flow

This applies to any residual python-pptx editing of a deck (e.g. the scrim /
title apply pass). Do not create a shape through python-pptx and then delete it
with `element.getparent().remove(element)` in the same flow — python-pptx's
internal state diverges from the serialized XML and strict parsers (Keynote)
reject the result. If a shape is not needed, do not create it. Narrowly scoped
XML cleanup utilities that remove pre-existing elements are fine — they operate
on elements not managed by python-pptx's in-memory state.

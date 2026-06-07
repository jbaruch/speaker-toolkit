# Deck Op Sequence — Spec

The op sequence is the input to `build-deck.sh` → the `BuildDeck` VBA macro, the
whole-deck creation engine that replaces `strip-template.py` + the retired MCP
PPT-server slide walk. `BuildDeck` opens the template (for its custom layouts +
masters), deletes the template's demo slides, executes the ops, and saves a COPY.

You (the agent) emit the op sequence from `slides.md` + the profile layout map —
layout, placeholder, and content choices are your judgment. Then:

```bash
python3 scripts/validate-deckops.py ops.txt          # exit 0 + {"slides":N,"ops":M}, or exit 1 + errors
scripts/build-deck.sh <template-copy.pptx> <out.pptx> ops.txt
```

`build-deck.sh` re-runs the validator first, so a malformed sequence fails fast
with line/op context instead of part-building a deck inside PowerPoint.

## Line and Field Format

- One op per line, newline-separated.
- Each line is `OP` then fields, separated by **U+001F** (the ASCII Unit
  Separator, shown here as `␟`). It is a non-printing control char absent from
  prose, so field text needs no escaping.
- Emit the literal U+001F byte between fields. Blank lines are ignored; a
  trailing `\r` is tolerated.
- Geometry (`left`/`top`/`width`/`height`) is in **points** (72 pt = 1 inch).
- A field's text must not contain a newline or U+001F. For multi-paragraph body
  copy, emit several `BULLET` ops, not one `BODY` with embedded newlines.

## Current-Object Model

`SLIDE` starts a new slide and makes it current; every other op applies to the
current slide. `TABLE` and `CHART` set the current table / chart for the `CELL`
and `CAT`/`SERIES` ops that follow. `SLIDE` resets the current table and chart.

## Ops

| Op | Fields | Effect |
|----|--------|--------|
| `SLIDE` | `<0-based custom-layout index>` | Start a slide on the template's custom layout at that index. |
| `TITLE` | `<text>` | Set the slide's title placeholder (falls back to the Title shape). |
| `SUBTITLE` | `<text>` | Set the subtitle placeholder. |
| `BODY` | `<text>` | Set the body placeholder's text. |
| `BULLET` | `<0-based indent level>␟<text>` | Append a bullet paragraph to the body placeholder. |
| `TEXT` | `<l>␟<t>␟<w>␟<h>␟<text>` | Add a free text box. |
| `IMAGE` | `<l>␟<t>␟<w>␟<h>␟<path>` | Add an embedded picture. |
| `SHAPE` | `<msoAutoShapeType>␟<l>␟<t>␟<w>␟<h>` | Add an auto shape. |
| `BG` | `<r>␟<g>␟<b>` | Solid slide background fill (each channel 0–255). |
| `FOOTER` | `<text>` | Add a footer text box across the slide bottom. |
| `OPTIMIZE` | — | Autofit each text box on the slide to its shape. |
| `TABLE` | `<rows>␟<cols>␟<l>␟<t>␟<w>␟<h>` | Add a table; becomes the current table. |
| `CELL` | `<1-based row>␟<1-based col>␟<text>` | Set a cell's text (needs a `TABLE` first). |
| `CHART` | `<xlChartType>␟<l>␟<t>␟<w>␟<h>` | Add a chart; becomes the current chart. |
| `CAT` | `<category name>` | Append a category label to the current chart. |
| `SERIES` | `<name>␟<v>␟<v>…` | Append a data series — name then numeric values. |

## State Rules (enforced by validate-deckops.py)

- Every op except `SLIDE` needs a prior `SLIDE`.
- `CELL` needs a `TABLE` on the current slide.
- `CAT` / `SERIES` need a `CHART` on the current slide.
- A new `SLIDE` clears the current table / chart, so a `TABLE` or `CHART` does
  not carry to the next slide.
- Chart categories / series buffer and apply when the next `CHART` or `SLIDE`
  starts (or at end of input).

## Enum Values

`SHAPE` takes an `msoAutoShapeType` and `CHART` an `xlChartType` integer.
Common ones:

- `msoAutoShapeType`: `1` rectangle, `5` rounded rectangle, `9` oval, `33` right arrow.
- `xlChartType`: `51` clustered column, `52` stacked column, `4` line, `5` pie, `-4169` XY scatter.

Full enumerations: Microsoft `MsoAutoShapeType` and `XlChartType` references.

## Example

A two-slide deck — a title slide, then a content slide with a footer and two
bullets (`␟` = U+001F):

```
SLIDE␟0
TITLE␟From Tile to Plugin
SUBTITLE␟A migration story
SLIDE␟2
TITLE␟Why Rename
BG␟255␟242␟158
BULLET␟0␟Terminology consistency
BULLET␟1␟Across CLI, web, and docs
FOOTER␟jbaruch • Devoxx 2026
OPTIMIZE
```

## Build-Then-Assemble (fragments)

`BuildDeck` always builds from slide 1. To insert or replace a slide inside an
existing deck (iteration, single-slide regeneration), build a one-`SLIDE`
fragment deck with `build-deck.sh`, then position it with `run-deck-ops.sh`'s
order string — the same pattern `MakePlaceholderSlide` and `InsertQR` use,
because Mac VBA's `Slide.MoveTo` raises E_INVALIDARG. See
`rules/deck-editing-rules.md`.

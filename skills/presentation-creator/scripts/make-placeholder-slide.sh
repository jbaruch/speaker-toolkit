#!/bin/bash
# make-placeholder-slide.sh — build a loud yellow [PLACEHOLDER] slide as a 1-slide
# .pptx via the real PowerPoint app (MakePlaceholderSlide VBA macro), sized to the
# base deck. Replaces python-pptx insert-placeholder-slides.py. macOS + PowerPoint.
# See rules/deck-editing-rules.md.
#
# Mac VBA's Slide.MoveTo is broken, so placeholders are built as 1-slide decks here
# and inserted at their target positions by run-deck-ops.sh's order string. To drop
# N placeholders into a deck: build each with this script, then assemble once with
# run-deck-ops.sh, interleaving the placeholder aliases at the wanted positions, e.g.
#   make-placeholder-slide.sh base.pptx ph1.pptx "Cost Curves" "MIT SSRN viz"
#   run-deck-ops.sh base.pptx out.pptx "ph1=/abs/ph1.pptx" "BASE:1 BASE:2 ph1:1 BASE:3 ..." ""
#
# Usage:
#   make-placeholder-slide.sh <basePath> <outPath> "<TITLE>" "<SUBTITLE>"
#     basePath   deck whose slide size the placeholder should match (uniquely-named copy)
#     outPath    where to write the 1-slide placeholder .pptx
#     TITLE      placeholder title (auto-prefixed "[PLACEHOLDER] " if not already)
#     SUBTITLE   context line ("" for none)
#
# Prerequisites: RunDeckOps.bas (which defines MakePlaceholderSlide) imported into an
# OPEN macro-enabled deck (DeckOps.pptm), macros enabled, Automation consent granted.
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "usage: make-placeholder-slide.sh <basePath> <outPath> <TITLE> <SUBTITLE>" >&2
  exit 2
fi
BASE="$1"; OUT="$2"; TITLE="$3"; SUBTITLE="$4"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/ensure-drivers.sh"  # restore .applescript/.bas drivers tessl install strips
DRIVER="$HERE/make-placeholder-slide.applescript"

[[ -f "$BASE" ]]   || { echo "ERROR: base deck not found: $BASE — pass a uniquely-named copy whose slide size the placeholder should match." >&2; exit 1; }
[[ -f "$DRIVER" ]] || { echo "ERROR: driver not found: $DRIVER — reinstall the tile; make-placeholder-slide.applescript must sit next to this script." >&2; exit 1; }

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage locally, then move into place with the shell.
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
STAGE="$STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

osascript "$DRIVER" "$BASE" "$STAGE" "$TITLE" "$SUBTITLE"

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  echo "done -> $OUT"
else
  echo "ERROR: macro did not produce the staged slide. Check the PowerPoint error dialog, and confirm DeckOps.pptm is open with macros enabled and Automation consent granted — see skills/presentation-creator/references/deck-editing-setup.md." >&2
  exit 1
fi

#!/bin/bash
# make-bg-slide.sh — build a single comic-style slide whose generated illustration
# is the slide BACKGROUND FILL (so the deck's layout halftone-dot overlay covers it,
# matching the other slides), via the MakeBgImageSlide VBA macro. macOS + PowerPoint.
# See rules/deck-editing-rules.md. The output is a 1-slide .pptx meant to be imported
# into the deck with run-deck-ops.sh (orderStr token `<alias>:1`).
#
# Why a clone, not a fresh slide: a top-pasted picture sits ABOVE the layout's dot
# overlay (wrong), and a python-pptx slide can't borrow the deck's layout/overlay.
# Cloning a real comic template slide inherits the layout (overlay), the styled title
# box, and the footer; we then swap its background fill and retitle.
#
# Usage:
#   make-bg-slide.sh <basePath> <templateSlideNum> <imagePath> "<TITLE>" <outPath>
#     basePath          deck to clone the template slide from (uniquely-named copy)
#     templateSlideNum  1-based slide # of a comic FULL-bleed title slide to clone
#                       (top-positioned title recommended, to match the image's safe zone)
#     imagePath         the generated illustration to set as the slide background
#     TITLE             overlaid title text (kept in the template's font)
#     outPath           where to write the 1-slide .pptx
#
# Prerequisites: RunDeckOps.bas (which defines MakeBgImageSlide) imported into an
# OPEN macro-enabled deck (DeckOps.pptm), macros enabled, Automation consent granted.
set -euo pipefail

if [[ $# -lt 5 ]]; then
  echo "usage: make-bg-slide.sh <basePath> <templateSlideNum> <imagePath> <TITLE> <outPath>" >&2
  exit 2
fi
BASE="$1"; TEMPLATE="$2"; IMAGE="$3"; TITLE="$4"; OUT="$5"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER="$HERE/make-bg-slide.applescript"

[[ -f "$BASE" ]]   || { echo "ERROR: base deck not found: $BASE" >&2; exit 1; }
[[ -f "$IMAGE" ]]  || { echo "ERROR: image not found: $IMAGE" >&2; exit 1; }
[[ -f "$DRIVER" ]] || { echo "ERROR: driver not found: $DRIVER" >&2; exit 1; }

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage locally, then move into place with the shell.
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
STAGE="$STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

osascript "$DRIVER" "$BASE" "$TEMPLATE" "$IMAGE" "$TITLE" "$STAGE"

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  echo "done -> $OUT"
else
  echo "ERROR: macro did not produce the staged slide (see the PowerPoint error dialog)." >&2
  exit 1
fi

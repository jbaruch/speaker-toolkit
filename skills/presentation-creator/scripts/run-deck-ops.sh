#!/bin/bash
# run-deck-ops.sh — trim / reorder / cross-deck-import a PowerPoint .pptx via the
# real PowerPoint app (RunDeckOps VBA macro), preserving per-slide backgrounds.
# See rules/deck-editing-rules.md. macOS + Microsoft PowerPoint only.
#
# Usage:
#   run-deck-ops.sh <basePath> <outPath> <importSpec> <orderStr> <replaceStr>
#
#   basePath    .pptx opened as the build container (output inherits its slide
#               size + masters). Use a UNIQUELY-NAMED copy — PowerPoint keys
#               open decks by filename, so base/import/output must not collide.
#   outPath     final destination (may be a Google Drive folder; see staging note)
#   importSpec  "" or "alias=/path[;alias2=/path2]" for cross-deck slide imports
#   orderStr    final slide sequence, e.g. "BASE:1 BASE:2 voxxed:13 BASE:49"
#               (token = <alias>:<1-based slide #>; alias BASE = basePath)
#   replaceStr  "" or "find=>to||find2=>to2" global text replacements
#
# Prerequisites: RunDeckOps.bas imported into an OPEN macro-enabled deck
# (e.g. DeckOps.pptm), VBA macros enabled, Automation consent granted once.
set -euo pipefail

if [[ $# -lt 5 ]]; then
  echo "usage: run-deck-ops.sh <basePath> <outPath> <importSpec> <orderStr> <replaceStr>" >&2
  exit 2
fi
BASE="$1"; OUT="$2"; IMPORT="$3"; ORDER="$4"; REPLACE="$5"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER="$HERE/run-deck-ops.applescript"

[[ -f "$BASE" ]]   || { echo "ERROR: base deck not found: $BASE — pass a uniquely-named copy of the source .pptx as <basePath>." >&2; exit 1; }
[[ -f "$DRIVER" ]] || { echo "ERROR: driver not found: $DRIVER — reinstall the tile; run-deck-ops.applescript must sit next to this script." >&2; exit 1; }

# Sandboxed PowerPoint can READ from a Google Drive File-Provider folder but
# fails to CREATE a new file there via VBA (E_FAIL -2147467259). So save to a
# LOCAL staging path, then move into the destination with the shell, which
# writes to Drive normally.
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
STAGE="$STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

echo "staging -> $STAGE"
osascript "$DRIVER" "$BASE" "$STAGE" "$IMPORT" "$ORDER" "$REPLACE"

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  echo "done -> $OUT"
else
  echo "ERROR: macro did not produce the staged file. Check the PowerPoint error dialog, and confirm DeckOps.pptm is open with macros enabled and Automation consent granted — see skills/presentation-creator/references/deck-editing-setup.md." >&2
  exit 1
fi

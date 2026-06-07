#!/bin/bash
# build-deck.sh — build a whole deck from a flat op sequence via the real
# PowerPoint app (BuildDeck VBA macro). The unified creation engine that retires
# strip-template.py + the MCP structural walk: it opens the template, removes its
# demo slides, and builds the deck from the ops. See rules/deck-editing-rules.md
# and references/deckops-spec.md. macOS + Microsoft PowerPoint only.
#
# The agent emits the op sequence from outline.yaml / slides.md (layout,
# placeholder, and content choices are judgment), validates it with
# validate-deckops.py, then runs this.
#
# Usage:
#   build-deck.sh <templatePath> <outPath> <opsFile>
#     templatePath  the .pptx template (uniquely-named copy; its custom layouts +
#                   masters are inherited, its demo slides are stripped)
#     outPath       where to write the built deck
#     opsFile       the op sequence (see references/deckops-spec.md)
#
# Prerequisites: RunDeckOps.bas (which defines BuildDeck) imported into an OPEN
# macro-enabled deck (DeckOps.pptm), macros enabled, Automation consent granted.
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: build-deck.sh <templatePath> <outPath> <opsFile>" >&2
  exit 2
fi
TEMPLATE="$1"; OUT="$2"; OPS="$3"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER="$HERE/build-deck.applescript"

[[ -f "$TEMPLATE" ]] || { echo "ERROR: template not found: $TEMPLATE — pass a uniquely-named copy of the .pptx template." >&2; exit 1; }
[[ -f "$OPS" ]]      || { echo "ERROR: ops file not found: $OPS — emit it per references/deckops-spec.md and validate with validate-deckops.py." >&2; exit 1; }
[[ -f "$DRIVER" ]]   || { echo "ERROR: driver not found: $DRIVER — reinstall the tile; build-deck.applescript must sit next to this script." >&2; exit 1; }

# Validate the op sequence up front so malformed ops fail fast (with line/op
# context) instead of part-building a deck inside PowerPoint.
python3 "$HERE/validate-deckops.py" "$OPS" >&2

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage locally, then move into place with the shell.
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
STAGE="$STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

# osascript prints the macro's "BuildDeck returned: N" line — keep it off stdout.
osascript "$DRIVER" "$TEMPLATE" "$STAGE" "$OPS" >&2

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  python3 -c 'import json,sys; print(json.dumps({"output": sys.argv[1]}))' "$OUT"
else
  echo "ERROR: macro did not produce the staged deck. Check the PowerPoint error dialog, and confirm DeckOps.pptm is open with macros enabled and Automation consent granted — see skills/presentation-creator/references/deck-editing-setup.md." >&2
  exit 1
fi

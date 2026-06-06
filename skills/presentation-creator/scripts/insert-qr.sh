#!/bin/bash
# insert-qr.sh — place a QR PNG bottom-right on the given slides via the real
# PowerPoint app (InsertQR VBA macro), replacing any existing corner QR. Replaces
# generate-qr.py's python-pptx insert; generate-qr.py keeps URL resolve + per-slide
# background-color match + PNG generation, then calls this for the write.
# See rules/deck-editing-rules.md. macOS + Microsoft PowerPoint only.
#
# Usage:
#   insert-qr.sh <basePath> <outPath> <qr.png> <slideNumsCSV>
#     basePath       deck to read (uniquely-named copy; base/out must not collide)
#     outPath        where to write the COPY with the QR inserted
#     qr.png         the (pre-generated, color-matched) QR PNG
#     slideNumsCSV   comma-separated 1-based slide numbers, e.g. "5,12"
#
# Prerequisites: RunDeckOps.bas (which defines InsertQR) imported into an OPEN
# macro-enabled deck (DeckOps.pptm), macros enabled, Automation consent granted.
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "usage: insert-qr.sh <basePath> <outPath> <qr.png> <slideNumsCSV>" >&2
  exit 2
fi
BASE="$1"; OUT="$2"; PNG="$3"; SLIDES="$4"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER="$HERE/insert-qr.applescript"

[[ -f "$BASE" ]]   || { echo "ERROR: base deck not found: $BASE — pass a uniquely-named copy of the deck." >&2; exit 1; }
[[ -f "$PNG" ]]    || { echo "ERROR: QR PNG not found: $PNG — generate it first with generate-qr.py." >&2; exit 1; }
[[ -f "$DRIVER" ]] || { echo "ERROR: driver not found: $DRIVER — reinstall the tile; insert-qr.applescript must sit next to this script." >&2; exit 1; }

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage locally, then move into place with the shell.
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
STAGE="$STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

# osascript prints the macro's "InsertQR returned: N" line — keep it off stdout
# (stderr) so successful stdout is the documented JSON only.
osascript "$DRIVER" "$BASE" "$STAGE" "$PNG" "$SLIDES" >&2

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  # Structured stdout (per jbaruch/coding-policy: script-delegation); diagnostics go to stderr.
  # Emit via python3 so any path (quotes/backslashes/unicode) is correctly JSON-escaped.
  python3 -c 'import json,sys; print(json.dumps({"output": sys.argv[1]}))' "$OUT"
else
  echo "ERROR: macro did not produce the staged file. Check the PowerPoint error dialog, and confirm DeckOps.pptm is open with macros enabled and Automation consent granted — see skills/presentation-creator/references/deck-editing-setup.md." >&2
  exit 1
fi

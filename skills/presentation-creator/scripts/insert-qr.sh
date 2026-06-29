#!/bin/bash
# insert-qr.sh — place a QR PNG on the given slides via the real PowerPoint app
# (InsertQR VBA macro), replacing any existing QR in place. Replaces
# generate-qr.py's python-pptx insert; generate-qr.py keeps URL resolve + per-slide
# background-color match + PNG generation + content-based QR detection, then calls
# this for the write. See rules/deck-editing-rules.md. macOS + Microsoft PowerPoint only.
#
# Usage:
#   insert-qr.sh <basePath> <outPath> <qr.png> <slidesSpec>
#     basePath     deck to read (uniquely-named copy; base/out must not collide)
#     outPath      where to write the COPY with the QR inserted
#     qr.png       the (pre-generated, color-matched) QR PNG
#     slidesSpec   ";"-joined per-slide entries "<num>[:<rL,rT,rW,rH>,...]" — the
#                  rects (points) of existing QRs to replace; see InsertQR. e.g.
#                  "12:450.00,80.00,200.16,200.16;38"
#
# Prerequisites: RunDeckOps.bas (which defines InsertQR) imported into an OPEN
# macro-enabled deck (DeckOps.pptm), macros enabled, Automation consent granted.
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "usage: insert-qr.sh <basePath> <outPath> <qr.png> <slidesSpec>" >&2
  exit 2
fi
BASE="$1"; OUT="$2"; PNG="$3"; SPEC="$4"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/ensure-drivers.sh"   # restore .applescript/.bas drivers tessl install strips
source "$HERE/container-stage.sh"  # stage Google-Drive inputs into the container (no Powerbox prompts)
DRIVER="$HERE/insert-qr.applescript"

[[ -f "$BASE" ]]   || { echo "ERROR: base deck not found: $BASE — pass a uniquely-named copy of the deck." >&2; exit 1; }
[[ -f "$PNG" ]]    || { echo "ERROR: QR PNG not found: $PNG — generate it first with generate-qr.py." >&2; exit 1; }
[[ -f "$DRIVER" ]] || { echo "ERROR: driver not found: $DRIVER — reinstall the tile; insert-qr.applescript must sit next to this script." >&2; exit 1; }

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage locally, then move into place with the shell.
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
STAGE="$OUT_STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

# osascript prints the macro's "InsertQR returned: N" line — keep it off stdout
# (stderr) so successful stdout is the documented JSON only.
osascript "$DRIVER" "$(stage_base "$BASE")" "$STAGE" "$(stage_base "$PNG")" "$SPEC" >&2

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  # Structured stdout (per jbaruch/coding-policy: script-delegation); diagnostics go to stderr.
  # Emit via python3 so any path (quotes/backslashes/unicode) is correctly JSON-escaped.
  python3 -c 'import json,sys; print(json.dumps({"output": sys.argv[1]}))' "$OUT"
else
  echo "ERROR: macro did not produce the staged file. On a macro error the osascript step above already aborted with the VBA Err.Description; reaching here means the macro returned without error but wrote no file. Confirm DeckOps.pptm is open with macros enabled and Automation consent granted — see skills/presentation-creator/references/deck-editing-setup.md." >&2
  exit 1
fi

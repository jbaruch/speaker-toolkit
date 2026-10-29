#!/bin/bash
# inject-notes.sh — set per-slide speaker notes via the real PowerPoint app
# (inject-notes.applescript, through PowerPoint's AppleScript object model),
# retiring inject-speaker-notes.py. Real PowerPoint serializes valid notes OOXML,
# so the <p:notesMasterIdLst> Keynote-compat patch the python-pptx path needed is
# no longer required. See rules/deck-editing-rules.md. macOS + Microsoft PowerPoint only.
#
# Run this in the build pipeline AFTER the structural walk + illustrations apply
# and BEFORE apply-backgrounds.sh (the VBA background pass must be the final write).
#
# Usage:
#   inject-notes.sh <basePath> <outPath> <notes.json>
#     basePath    the built deck to read (uniquely-named copy)
#     outPath     where to write the COPY with notes applied
#     notes.json  {"<0-based slide #>": "notes text", ...} (the historical format)
#
# Prerequisites: Microsoft PowerPoint and Automation consent granted. This pass runs
# no VBA macro, so it does not need DeckOps.pptm.
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: inject-notes.sh <basePath> <outPath> <notes.json>" >&2
  exit 2
fi
BASE="$1"; OUT="$2"; NOTES="$3"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/ensure-drivers.sh"   # restore .applescript/.bas drivers tessl install strips
source "$HERE/container-stage.sh"  # stage Google-Drive inputs into the container (no Powerbox prompts)
DRIVER="$HERE/inject-notes.applescript"

[[ -f "$BASE" ]]   || { echo "ERROR: base deck not found: $BASE — pass a uniquely-named copy of the built deck." >&2; exit 1; }
[[ -f "$NOTES" ]]  || { echo "ERROR: notes JSON not found: $NOTES — a {\"<0-based slide #>\": \"text\"} map." >&2; exit 1; }
[[ -f "$DRIVER" ]] || { echo "ERROR: driver not found: $DRIVER — reinstall the plugin; inject-notes.applescript must sit next to this script." >&2; exit 1; }

# Validate the 0-based notes JSON against the deck's slide count and turn it into
# the driver's argument pairs (1-based slide #, note text), NUL-terminated so
# multi-line notes survive. Deterministic; unit-tested in tests/test_notes_to_packed.py.
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
ARGS_FILE="$STAGE_DIR/$(basename "$OUT").notes.args"
python3 "$HERE/notes-to-packed.py" --driver-args --deck "$BASE" "$NOTES" "$ARGS_FILE"
NOTE_ARGS=()
while IFS= read -r -d '' item; do NOTE_ARGS+=("$item"); done < "$ARGS_FILE"

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage locally, then move into place with the shell.
STAGE="$OUT_STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

echo "staging -> $STAGE"
# ${arr[@]+...} keeps an empty notes map from tripping `set -u` on bash 3.2.
osascript "$DRIVER" "$(stage_base "$BASE")" "$STAGE" ${NOTE_ARGS[@]+"${NOTE_ARGS[@]}"}

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  echo "done -> $OUT"
else
  echo "ERROR: the notes driver reported success but wrote no file at $STAGE. A driver failure aborts the osascript step above with its stage and repair; reaching here means PowerPoint saved somewhere else. Confirm PowerPoint can write to $OUT_STAGE_DIR and re-run — see skills/presentation-builder/references/deck-editing-setup.md." >&2
  exit 1
fi

#!/bin/bash
# inject-notes.sh — set per-slide speaker notes via the real PowerPoint app
# (SetSpeakerNotes VBA macro), retiring inject-speaker-notes.py. Real PowerPoint
# serializes valid notes OOXML, so the <p:notesMasterIdLst> Keynote-compat patch
# the python-pptx path needed is no longer required. See rules/deck-editing-rules.md.
# macOS + Microsoft PowerPoint only.
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
# Prerequisites: RunDeckOps.bas (which defines SetSpeakerNotes) imported into an
# OPEN macro-enabled deck (DeckOps.pptm), macros enabled, Automation consent granted.
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: inject-notes.sh <basePath> <outPath> <notes.json>" >&2
  exit 2
fi
BASE="$1"; OUT="$2"; NOTES="$3"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/ensure-drivers.sh"  # restore .applescript/.bas drivers tessl install strips
DRIVER="$HERE/inject-notes.applescript"

[[ -f "$BASE" ]]   || { echo "ERROR: base deck not found: $BASE — pass a uniquely-named copy of the built deck." >&2; exit 1; }
[[ -f "$NOTES" ]]  || { echo "ERROR: notes JSON not found: $NOTES — a {\"<0-based slide #>\": \"text\"} map." >&2; exit 1; }
[[ -f "$DRIVER" ]] || { echo "ERROR: driver not found: $DRIVER — reinstall the tile; inject-notes.applescript must sit next to this script." >&2; exit 1; }

# Pack the 0-based notes JSON into the SetSpeakerNotes wire format (1-based,
# control-char delimited). Deterministic; unit-tested in tests/test_notes_to_packed.py.
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
PACKED="$STAGE_DIR/$(basename "$OUT").notes.packed"
python3 "$HERE/notes-to-packed.py" "$NOTES" "$PACKED"

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage locally, then move into place with the shell.
STAGE="$STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

echo "staging -> $STAGE"
osascript "$DRIVER" "$BASE" "$STAGE" "$PACKED"

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  echo "done -> $OUT"
else
  echo "ERROR: macro did not produce the staged file. Check the PowerPoint error dialog, and confirm DeckOps.pptm is open with macros enabled and Automation consent granted — see skills/presentation-creator/references/deck-editing-setup.md." >&2
  exit 1
fi

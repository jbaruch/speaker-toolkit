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
# one NUL-terminated item per slide (that slide's note, or empty to leave it
# unchanged), so multi-line notes survive. Producer and this consumer are
# unit-tested in tests/test_notes_to_packed.py and tests/test_inject_notes_wrapper.py.
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
STAGED_BASE="$(stage_base "$BASE")"

echo "staging -> $STAGE"
# ${arr[@]+...} keeps an empty deck from tripping `set -u` on bash 3.2.
# PowerPoint keys open decks by file name, so the driver gets both names too.
# Its stderr is kept so a failure can tell whether this run opened a copy.
DRIVER_LOG="$STAGE_DIR/$(basename "$OUT").driver.log"
if osascript "$DRIVER" "$STAGED_BASE" "$STAGE" "$(basename "$STAGED_BASE")" "$(basename "$STAGE")" ${NOTE_ARGS[@]+"${NOTE_ARGS[@]}"} 2> "$DRIVER_LOG"; then
  cat "$DRIVER_LOG" >&2
else
  cat "$DRIVER_LOG" >&2
  # grep: 0 = the driver logged [opened], 1 = it never opened a copy, 2 = log unreadable.
  if grep -q '^\[opened\] ' "$DRIVER_LOG"; then
    CLOSE_ADVICE="This run opened a copy: close the presentation named $(basename "$STAGED_BASE") (or $(basename "$STAGE"), if it was saved) in PowerPoint without saving."
  elif [[ $? -eq 1 ]]; then
    CLOSE_ADVICE="This run opened no copy: leave every presentation that was already open as it is."
  else
    CLOSE_ADVICE="The driver log $DRIVER_LOG could not be read, so it is unknown whether this run opened a copy: close $(basename "$STAGED_BASE") only if you did not have it open before this run."
  fi
  echo "ERROR: the notes driver stopped at the last stage it logged above ([open], [slide N], [save] or [close]). $CLOSE_ADVICE Then fix the cause it reported and re-run. For a denied Automation consent see skills/presentation-builder/references/deck-editing-setup.md Step 4." >&2
  exit 1
fi

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  echo "done -> $OUT"
else
  echo "ERROR: the notes driver reported success but wrote no file at $STAGE, so PowerPoint saved somewhere else. Confirm PowerPoint can write to $OUT_STAGE_DIR and re-run — see skills/presentation-builder/references/deck-editing-setup.md." >&2
  exit 1
fi

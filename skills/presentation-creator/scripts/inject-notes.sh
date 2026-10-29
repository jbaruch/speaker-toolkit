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
if ! mkdir -p "$STAGE_DIR"; then
  echo "ERROR: cannot create $STAGE_DIR — make $HOME writable, or free disk space, and re-run." >&2
  exit 1
fi
# One fresh directory per run holds the notes' plaintext arguments, the
# opened-copy marker and the stage file, so concurrent runs never share files.
if ! RUN_DIR="$(mktemp -d "$STAGE_DIR/notes-run.XXXXXX")"; then
  echo "ERROR: cannot create a run directory in $STAGE_DIR — make it writable, or free disk space, and re-run." >&2
  exit 1
fi
# Best-effort: a cleanup failure warns and never replaces the run's outcome.
remove_run_dir() {
  if ! rm -rf -- "${RUN_DIR:?}"; then
    echo "WARNING: could not remove $RUN_DIR; it holds this run's notes text, marker and stage files, so delete it by hand." >&2
  fi
  return 0
}
# Every exit from here on, planned or not, removes the notes text, then the
# container staging that container-stage.sh's own EXIT trap used to remove.
_inject_notes_cleanup() {
  remove_run_dir
  _container_stage_cleanup
  return 0   # never let cleanup rewrite the script's exit status
}
trap _inject_notes_cleanup EXIT

ARGS_FILE="$RUN_DIR/notes.args"
if ! python3 "$HERE/notes-to-packed.py" --driver-args --deck "$BASE" "$NOTES" "$ARGS_FILE"; then
  exit 1
fi
if [[ ! -r "$ARGS_FILE" ]]; then
  echo "ERROR: notes-to-packed.py reported success but $ARGS_FILE is not readable — check $RUN_DIR's permissions and re-run." >&2
  exit 1
fi
NOTE_ARGS=()
while IFS= read -r -d '' item; do NOTE_ARGS+=("$item"); done < "$ARGS_FILE"

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage locally, then move into place with the shell.
STAGE="$OUT_STAGE_DIR/$(basename "$OUT")"
if ! rm -f "$STAGE"; then
  echo "ERROR: cannot clear the old staged output $STAGE — remove it by hand and re-run." >&2
  exit 1
fi
STAGED_BASE="$(stage_base "$BASE")"

echo "staging -> $STAGE"
# ${arr[@]+...} keeps an empty deck from tripping `set -u` on bash 3.2.
# PowerPoint keys open decks by file name, so the driver gets both names too.
# The driver creates OPENED_MARKER only after confirming no same-named deck was
# open and PowerPoint has opened its own copy; log text cannot fake a file.
OPENED_MARKER="$RUN_DIR/opened"
# The driver overwrites STAGE_FILE with a fixed token before each stage (open,
# slide N, save, close); only those tokens select a stage-specific repair.
STAGE_FILE="$RUN_DIR/stage"
if ! osascript "$DRIVER" "$STAGED_BASE" "$STAGE" "$(basename "$STAGED_BASE")" "$(basename "$STAGE")" "$OPENED_MARKER" "$STAGE_FILE" ${NOTE_ARGS[@]+"${NOTE_ARGS[@]}"}; then
  LAST_STAGE=""
  if [[ -f "$STAGE_FILE" && -r "$STAGE_FILE" ]]; then
    if ! IFS= read -r LAST_STAGE < "$STAGE_FILE"; then
      LAST_STAGE=""
    fi
  fi
  if [[ "$LAST_STAGE" == "open" ]]; then
    STAGE_ADVICE="It stopped while opening the staged copy: open $STAGED_BASE by hand to confirm PowerPoint can read it, dismiss any PowerPoint dialog, and re-run."
  elif [[ "$LAST_STAGE" =~ ^slide\ ([0-9]+)$ ]]; then
    STAGE_ADVICE="It stopped writing the note for slide ${BASH_REMATCH[1]}: open the source deck, check that slide's notes page (View > Notes Page) and its note text in notes.json, and re-run."
  elif [[ "$LAST_STAGE" == "save" ]]; then
    STAGE_ADVICE="It stopped saving to $STAGE: free disk space, confirm PowerPoint can write to $OUT_STAGE_DIR, and re-run."
  elif [[ "$LAST_STAGE" == "close" ]]; then
    STAGE_ADVICE="It stopped after saving, while closing the copy: close $(basename "$STAGE") in PowerPoint without saving, then re-run."
  else
    STAGE_ADVICE="It stopped before recording a stage: confirm $RUN_DIR is writable and that PowerPoint is running with no dialog open, then re-run."
  fi
  if [[ -e "$OPENED_MARKER" ]]; then
    CLOSE_ADVICE="This run opened its own copy (no presentation with that name was open before): close the presentation named $(basename "$STAGED_BASE") (or $(basename "$STAGE"), if it was saved) in PowerPoint without saving."
  else
    CLOSE_ADVICE="This run recorded no copy of its own: leave every presentation that was open before this run as it is."
  fi
  echo "ERROR: the notes driver failed; its message is above. If that message gives a repair, follow it. $STAGE_ADVICE $CLOSE_ADVICE For a denied Automation consent see skills/presentation-builder/references/deck-editing-setup.md Step 4." >&2
  exit 1
fi

if [[ -f "$STAGE" ]]; then
  if ! mkdir -p "$(dirname "$OUT")"; then
    echo "ERROR: PowerPoint saved the deck, but the destination folder $(dirname "$OUT") cannot be created, so nothing was delivered — choose an output path in a writable folder and re-run." >&2
    exit 1
  fi
  if ! mv -f "$STAGE" "$OUT"; then
    echo "ERROR: PowerPoint saved the deck, but moving it to $OUT failed, so nothing was delivered — make $(dirname "$OUT") writable, or free disk space, and re-run." >&2
    exit 1
  fi
  echo "done -> $OUT"
else
  echo "ERROR: the notes driver reported success but wrote no file at $STAGE, so PowerPoint saved somewhere else. Confirm PowerPoint can write to $OUT_STAGE_DIR and re-run — see skills/presentation-builder/references/deck-editing-setup.md." >&2
  exit 1
fi

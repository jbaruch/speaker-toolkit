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

if [[ -d "$OUT" ]]; then
  echo "ERROR: the output path $OUT is a directory — pass the path of the deck file to write, for example $OUT/$(basename "$BASE")." >&2
  exit 1
fi
[[ -f "$BASE" ]]   || { echo "ERROR: base deck not found: $BASE — pass a uniquely-named copy of the built deck." >&2; exit 1; }
[[ -f "$NOTES" ]]  || { echo "ERROR: notes JSON not found: $NOTES — a {\"<0-based slide #>\": \"text\"} map." >&2; exit 1; }
[[ -f "$DRIVER" ]] || { echo "ERROR: driver not found: $DRIVER — reinstall the plugin; inject-notes.applescript must sit next to this script." >&2; exit 1; }
# The base is never modified, so OUT must not be the base itself: not the same
# file (a hard link or symlink to it included), nor the same path.
SAME_AS_BASE=no
if [[ -e "$OUT" && "$OUT" -ef "$BASE" ]]; then
  SAME_AS_BASE=yes
elif [[ -d "$(dirname "$OUT")" ]]; then
  if [[ "$(cd "$(dirname "$OUT")" && pwd -P)/$(basename "$OUT")" == "$(cd "$(dirname "$BASE")" && pwd -P)/$(basename "$BASE")" ]]; then
    SAME_AS_BASE=yes
  fi
fi
if [[ "$SAME_AS_BASE" == yes ]]; then
  echo "ERROR: the output path $OUT is the base deck itself — pass a different output path; this script never modifies the base." >&2
  exit 1
fi

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
# Set while a delivery copy sits beside OUT, cleared once it is renamed into place.
DELIVERY_TMP=""
# On every exit, planned, failed or signalled, remove an unfinished delivery
# copy and the run directory with the notes text (and, without a container,
# the staged deck). container-stage.sh's single EXIT trap runs this before
# removing its own staging dir.
_inject_notes_cleanup() {
  if [[ -n "$DELIVERY_TMP" && -e "$DELIVERY_TMP" ]]; then
    if ! rm -f "$DELIVERY_TMP"; then
      echo "WARNING: could not remove the unfinished copy $DELIVERY_TMP; delete it by hand." >&2
    fi
  fi
  remove_run_dir
  return 0   # never let cleanup rewrite the script's exit status
}
container_stage_on_exit _inject_notes_cleanup
# The deck PowerPoint saves, always in a folder this run alone owns and removes
# as a whole: the container's per-run staging dir, or, without a container,
# RUN_DIR. No other run or input shares the path, and a save that finishes
# after a timeout has no folder left to land in.
if [[ -n "$CONTAINER_STAGE" ]]; then
  STAGE="$OUT_STAGE_DIR/$(basename "$OUT")"
else
  # A subfolder, so no output name can clash with the run's own files.
  if ! mkdir "$RUN_DIR/out"; then
    echo "ERROR: cannot create $RUN_DIR/out — make $STAGE_DIR writable, or free disk space, and re-run." >&2
    exit 1
  fi
  STAGE="$RUN_DIR/out/$(basename "$OUT")"
fi

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
# stage locally (STAGE, above), then deliver into place with the shell.
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
  if [[ "$LAST_STAGE" == "open" || "$LAST_STAGE" == "opening" ]]; then
    STAGE_ADVICE="It stopped while opening the staged copy: open $STAGED_BASE by hand to confirm PowerPoint can read it, dismiss any PowerPoint dialog, and re-run."
  elif [[ "$LAST_STAGE" =~ ^slide\ ([0-9]+)$ ]]; then
    STAGE_ADVICE="It stopped writing the note for slide ${BASH_REMATCH[1]}: open the source deck, check that slide's notes page (View > Notes Page) and its note text in notes.json, and re-run."
  elif [[ "$LAST_STAGE" == "save" ]]; then
    STAGE_ADVICE="It stopped saving to $STAGE, and PowerPoint may still be finishing that save: wait until PowerPoint is idle, free disk space, and re-run. This run's staging folder is removed, so a late save has nowhere to land."
  elif [[ "$LAST_STAGE" == "close" ]]; then
    STAGE_ADVICE="It stopped after saving, while closing the copy: close $(basename "$STAGE") in PowerPoint without saving, then re-run."
  else
    STAGE_ADVICE="It stopped before recording a stage: confirm $RUN_DIR is writable and that PowerPoint is running with no dialog open, then re-run."
  fi
  if [[ -e "$OPENED_MARKER" ]]; then
    CLOSE_ADVICE="This run opened its own copy (no presentation with that name was open before): close the presentation named $(basename "$STAGED_BASE") (or $(basename "$STAGE"), if it was saved) in PowerPoint without saving."
  elif [[ "$LAST_STAGE" == "opening" ]]; then
    CLOSE_ADVICE="This run asked PowerPoint to open its copy and the open did not confirm; it may still finish. No presentation named $(basename "$STAGED_BASE") was open before this run, so if one appears in PowerPoint it is this run's copy: close it without saving. Leave every other presentation as it is."
  else
    CLOSE_ADVICE="This run recorded no copy of its own: leave every presentation that was open before this run as it is."
  fi
  echo "ERROR: the notes driver failed; its message is above. If that message gives a repair, follow it: it takes precedence over this stage guess. $STAGE_ADVICE $CLOSE_ADVICE For a denied Automation consent see skills/presentation-builder/references/deck-editing-setup.md Step 4." >&2
  exit 1
fi

if [[ -f "$STAGE" ]]; then
  OUT_DIR="$(dirname "$OUT")"
  if ! mkdir -p "$OUT_DIR"; then
    echo "ERROR: PowerPoint saved the deck, but the destination folder $OUT_DIR cannot be created, so nothing was delivered — choose an output path in a writable folder and re-run." >&2
    exit 1
  fi
  # The container and the destination (often Google Drive) are different
  # filesystems, where mv is copy-then-remove and can leave a partial file. Copy
  # to a temporary file beside OUT, then rename it into place: OUT is either the
  # previous file or the complete new one, never a partial copy.
  if ! DELIVERY_TMP="$(mktemp "$OUT_DIR/.$(basename "$OUT").XXXXXX")"; then
    echo "ERROR: PowerPoint saved the deck, but no temporary file can be created in $OUT_DIR, so nothing was delivered and $OUT is unchanged — make that folder writable, or free disk space, and re-run." >&2
    exit 1
  fi
  if ! cp -p "$STAGE" "$DELIVERY_TMP"; then
    echo "ERROR: PowerPoint saved the deck, but copying it to $OUT_DIR failed, so nothing was delivered and $OUT is unchanged — free disk space in that folder and re-run." >&2
    exit 1
  fi
  # atomic-replace.py renames onto exactly OUT and refuses a directory there,
  # even one that appeared while PowerPoint was running.
  if ! python3 "$HERE/atomic-replace.py" "$DELIVERY_TMP" "$OUT"; then
    exit 1
  fi
  DELIVERY_TMP=""
  echo "done -> $OUT"
else
  echo "ERROR: the notes driver reported success but wrote no file at $STAGE, so PowerPoint saved somewhere else. Confirm PowerPoint can write to $OUT_STAGE_DIR and re-run — see skills/presentation-builder/references/deck-editing-setup.md." >&2
  exit 1
fi

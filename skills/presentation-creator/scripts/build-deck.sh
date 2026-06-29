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
source "$HERE/ensure-drivers.sh"   # restore .applescript/.bas drivers tessl install strips
source "$HERE/container-stage.sh"  # stage Google-Drive inputs into the container (no Powerbox prompts)
DRIVER="$HERE/build-deck.applescript"

[[ -f "$TEMPLATE" ]] || { echo "ERROR: template not found: $TEMPLATE — pass a uniquely-named copy of the .pptx template." >&2; exit 1; }
[[ -f "$OPS" ]]      || { echo "ERROR: ops file not found: $OPS — emit it per references/deckops-spec.md and validate with validate-deckops.py." >&2; exit 1; }
[[ -f "$DRIVER" ]]   || { echo "ERROR: driver not found: $DRIVER — reinstall the tile; build-deck.applescript must sit next to this script." >&2; exit 1; }

# Validate the op sequence up front so malformed ops fail fast (with line/op
# context) instead of part-building a deck inside PowerPoint. On failure the
# validator writes errors to stderr and exits non-zero (set -e aborts); on
# success its JSON summary on stdout is discarded — this script emits its own.
python3 "$HERE/validate-deckops.py" "$OPS" >/dev/null

# Write the output INTO the container (OUT_STAGE_DIR is per-run), then shell-move
# it to the destination. The container is the one place SaveCopyAs neither prompts
# (Powerbox) nor E_FAILs (a Google-Drive folder fails; a local ~/.deckops-staging
# subdir prompts). container-stage.sh owns the single cleanup trap — do not set
# another here, or it would override that one and leak the staged copies.
STAGE="$OUT_STAGE_DIR/$(basename "$OUT")"

# osascript prints the macro's "BuildDeck returned: N" line — keep it off stdout.
osascript "$DRIVER" "$(stage_base "$TEMPLATE")" "$STAGE" "$OPS" >&2

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  python3 -c 'import json,sys; print(json.dumps({"output": sys.argv[1]}))' "$OUT"
else
  echo "ERROR: macro did not produce the staged deck. On a macro error the osascript step above already aborted with the VBA Err.Description; reaching here means the macro returned without error but wrote no file. Confirm DeckOps.pptm is open with macros enabled and Automation consent granted — see skills/presentation-creator/references/deck-editing-setup.md." >&2
  exit 1
fi

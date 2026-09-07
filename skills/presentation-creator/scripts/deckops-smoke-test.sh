#!/bin/bash
# deckops-smoke-test.sh — verify a fresh DeckOps setup end-to-end before any real edit.
#
# Builds the shipped 3-slide op sequence (smoke-test-ops.txt) against a uniquely-
# named copy of the speaker's template and reports where the output landed, so the
# user can open it in PowerPoint AND Keynote and confirm no "Repair" prompt. Given
# the history of lost work with other deck tools, this runs before the real edit.
#
# Usage:
#   deckops-smoke-test.sh <templatePath> [outDir]
#
#   templatePath  the speaker profile's infrastructure.template_pptx_path.
#                 Read-only — the script copies it.
#   outDir        where to leave the built deck (default: a mktemp -d dir).
#
# Prerequisites: DeckOps.pptm open with the DeckOps module imported, macros
# enabled, Automation consent granted. Run deckops-doctor.py first — a
# `status` other than `ok` means this will fail for a reason already diagnosed.
#
# Stdout: one JSON object — {"ok":true,"output":"<path>","slides":3,"base":"<path>"}
# Stderr: actionable diagnostics. Exit non-zero when the build did not produce a deck.
#
# The copy is uniquely named on purpose: PowerPoint keys open decks by filename and
# silently hands back an already-open same-named deck.
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: deckops-smoke-test.sh <templatePath> [outDir]" >&2
  exit 2
fi

TEMPLATE="$1"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS="$HERE/smoke-test-ops.txt"
EXPECTED_SLIDES=3

if [[ ! -f "$TEMPLATE" ]]; then
  echo "ERROR: template not found: $TEMPLATE — pass the speaker profile's infrastructure.template_pptx_path." >&2
  exit 1
fi
if [[ ! -f "$OPS" ]]; then
  echo "ERROR: op sequence not found: $OPS — reinstall the plugin; smoke-test-ops.txt ships beside this script." >&2
  exit 1
fi

if [[ $# -eq 2 ]]; then
  OUT_DIR="$2"
  mkdir -p "$OUT_DIR"
else
  OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/deckops-smoke-XXXXXX")"
fi

STAMP="$(date +%Y%m%d-%H%M%S)-$$"
BASE="$OUT_DIR/deckops-smoke-base-$STAMP.pptx"
OUT="$OUT_DIR/deckops-smoke-out-$STAMP.pptx"

cp "$TEMPLATE" "$BASE"
bash "$HERE/build-deck.sh" "$BASE" "$OUT" "$OPS" >&2

if [[ ! -f "$OUT" ]]; then
  echo "ERROR: the smoke build produced no deck at $OUT. The build-deck.sh output above carries the macro's own diagnostic; run deckops-doctor.py to check the setup." >&2
  exit 1
fi

# Serialize with a JSON encoder, never printf: a path may contain a double quote
# or a backslash, and interpolating one produces invalid JSON behind exit 0.
python3 -c 'import json,sys; print(json.dumps({"ok":True,"output":sys.argv[1],"slides":int(sys.argv[2]),"base":sys.argv[3]}))' \
  "$OUT" "$EXPECTED_SLIDES" "$BASE"

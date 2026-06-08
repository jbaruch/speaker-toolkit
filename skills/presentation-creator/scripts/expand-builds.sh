#!/bin/bash
# expand-builds.sh — expand progressive-reveal BUILD sequences in the deck via
# the real PowerPoint app (ExpandBuilds VBA macro): each parent slide is replaced
# by its build frames as full-bleed background-fill slides, speaker notes on the
# final frame only. Structural slide insertion goes through PowerPoint, never
# python-pptx. See rules/deck-editing-rules.md and
# skills/illustrations/references/builds.md. macOS + Microsoft PowerPoint only.
#
# ORDERING: run this BEFORE the by-index passes (inject-notes.sh, apply-backgrounds.sh,
# insert-qr.sh). Expansion renumbers every slide after a build parent, so those
# passes must compute their slide numbers against the POST-expansion deck.
#
# Usage:
#   expand-builds.sh <basePath> <outPath> <buildsManifest.json>
#     basePath   the built deck to read (uniquely-named copy)
#     outPath    where to write the COPY with builds expanded
#     manifest   JSON from build-expansion-manifest.py:
#                {"schema_version":1,"builds":[{"parent":N,"frames":[...],"notes":""}]}
#
# Prerequisites: RunDeckOps.bas (which defines ExpandBuilds) imported into an OPEN
# macro-enabled deck (DeckOps.pptm), macros enabled, Automation consent granted.
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: expand-builds.sh <basePath> <outPath> <buildsManifest.json>" >&2
  exit 2
fi
BASE="$1"; OUT="$2"; MANIFEST="$3"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER="$HERE/expand-builds.applescript"

[[ -f "$BASE" ]]     || { echo "ERROR: base deck not found: $BASE — pass a uniquely-named copy of the built deck." >&2; exit 1; }
[[ -f "$MANIFEST" ]] || { echo "ERROR: builds manifest not found: $MANIFEST — generate it with build-expansion-manifest.py." >&2; exit 1; }
[[ -f "$DRIVER" ]]   || { echo "ERROR: driver not found: $DRIVER — reinstall the tile; expand-builds.applescript must sit next to this script." >&2; exit 1; }

# Pack the manifest into the ExpandBuilds wire format (descending by parent;
# deterministic, unit-tested in tests/test_build_expansion_to_packed.py).
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
PACKED="$STAGE_DIR/$(basename "$OUT").builds.packed"
python3 "$HERE/build-expansion-to-packed.py" "$MANIFEST" "$PACKED"

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

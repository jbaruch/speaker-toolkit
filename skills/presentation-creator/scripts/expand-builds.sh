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

STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"

# Sandboxed PowerPoint prompts (Powerbox) on each UserPicture of a frame image
# OUTSIDE its container (e.g. Google Drive). Stage the frames INTO the container
# first so the macro reads them prompt-free — no Full Disk Access needed. See
# rules/deck-editing-rules.md. Falls back to original paths (and per-file prompts)
# if the container is absent.
PPT_CONTAINER="$HOME/Library/Containers/com.microsoft.Powerpoint/Data"
IMG_STAGE=""
EFFECTIVE_MANIFEST="$MANIFEST"
if [[ -d "$PPT_CONTAINER" ]]; then
  IMG_STAGE="$PPT_CONTAINER/.deckops-img-staging/$$"
  STAGED_MANIFEST="$STAGE_DIR/$(basename "$OUT").builds.staged.json"
  python3 "$HERE/stage-images-into-container.py" "$MANIFEST" --stage-dir "$IMG_STAGE" --out "$STAGED_MANIFEST" >/dev/null
  EFFECTIVE_MANIFEST="$STAGED_MANIFEST"
else
  echo "WARN: PowerPoint container not found at $PPT_CONTAINER — reading frames from their original paths; macOS may prompt per file. Open PowerPoint once to create the container." >&2
fi

# Pack the (staged) manifest into the ExpandBuilds wire format (descending by
# parent; deterministic, unit-tested in tests/test_build_expansion_to_packed.py).
PACKED="$STAGE_DIR/$(basename "$OUT").builds.packed"
python3 "$HERE/build-expansion-to-packed.py" "$EFFECTIVE_MANIFEST" "$PACKED"

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage the OUTPUT deck locally, then move into place with the shell.
STAGE="$STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

echo "staging -> $STAGE"
osascript "$DRIVER" "$BASE" "$STAGE" "$PACKED"

# Staged frames are embedded into the deck by UserPicture, so they're no longer
# needed once the output deck exists.
[[ -n "$IMG_STAGE" && -d "$IMG_STAGE" ]] && rm -rf "$IMG_STAGE"

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  echo "done -> $OUT"
else
  echo "ERROR: macro did not produce the staged file. Check the PowerPoint error dialog, and confirm DeckOps.pptm is open with macros enabled and Automation consent granted — see skills/presentation-creator/references/deck-editing-setup.md." >&2
  exit 1
fi

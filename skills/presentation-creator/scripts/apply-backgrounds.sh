#!/bin/bash
# apply-backgrounds.sh — set per-slide BACKGROUND FILLS in bulk via the real
# PowerPoint app (ApplyBackgrounds VBA macro), so each illustration becomes the
# slide background (covered by the layout's halftone-dot overlay) and survives.
# This is the creation-time counterpart of make-bg-slide.sh and the FINAL write
# of the build pipeline. See rules/deck-editing-rules.md. macOS + PowerPoint only.
#
# Run this AFTER all python-pptx / MCP work (structure, scrim, title, speaker
# notes) is done — any python-pptx save after this re-drops the <p:bg> fills.
#
# Usage:
#   apply-backgrounds.sh <basePath> <outPath> <backgroundsManifest.json>
#     basePath     the built deck to read (uniquely-named copy; PowerPoint keys
#                  open decks by filename, so base/output must not collide)
#     outPath      where to write the COPY with backgrounds applied
#     manifest     JSON: {"backgrounds": {"<1-based slide #>": "/abs/image", ...}}
#                  (produced by apply-illustrations-to-deck.py --backgrounds-out)
#
# Prerequisites: RunDeckOps.bas (which defines ApplyBackgrounds) imported into an
# OPEN macro-enabled deck (DeckOps.pptm), macros enabled, Automation consent granted.
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: apply-backgrounds.sh <basePath> <outPath> <backgroundsManifest.json>" >&2
  exit 2
fi
BASE="$1"; OUT="$2"; MANIFEST="$3"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/ensure-drivers.sh"   # restore .applescript/.bas drivers tessl install strips
source "$HERE/container-stage.sh"  # stage Google-Drive inputs into the container (no Powerbox prompts)
DRIVER="$HERE/apply-backgrounds.applescript"

[[ -f "$BASE" ]]     || { echo "ERROR: base deck not found: $BASE — pass a uniquely-named copy of the built .pptx as <basePath>." >&2; exit 1; }
[[ -f "$MANIFEST" ]] || { echo "ERROR: backgrounds manifest not found: $MANIFEST — generate it with apply-illustrations-to-deck.py --backgrounds-out." >&2; exit 1; }
[[ -f "$DRIVER" ]]   || { echo "ERROR: driver not found: $DRIVER — reinstall the tile; apply-backgrounds.applescript must sit next to this script." >&2; exit 1; }

STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"

# Open the base deck from the container so the macro doesn't trigger a Powerbox
# prompt on the Google-Drive path.
BASE="$(stage_base "$BASE")"

# Sandboxed PowerPoint prompts (Powerbox) on each UserPicture of an image OUTSIDE
# its container (e.g. Google Drive). Stage the images INTO the container too so the
# macro reads them prompt-free — no Full Disk Access needed. See
# rules/deck-editing-rules.md. Falls back to original paths (and per-file prompts)
# if the container is absent.
EFFECTIVE_MANIFEST="$MANIFEST"
if [[ -n "$CONTAINER_STAGE" ]]; then
  STAGED_MANIFEST="$STAGE_DIR/$(basename "$OUT").bg.staged.json"
  python3 "$HERE/stage-images-into-container.py" "$MANIFEST" --stage-dir "$CONTAINER_STAGE/img" --out "$STAGED_MANIFEST" >/dev/null
  EFFECTIVE_MANIFEST="$STAGED_MANIFEST"
else
  echo "WARN: PowerPoint container not found — reading images from their original paths; macOS may prompt per file. Open PowerPoint once to create the container." >&2
fi

# Build the "#=path;#=path" spec from the (staged) manifest (deterministic;
# unit-tested in tests/test_backgrounds_manifest_to_spec.py). Exits non-zero with
# an actionable message on an empty or malformed manifest.
SPEC="$(python3 "$HERE/backgrounds-manifest-to-spec.py" "$EFFECTIVE_MANIFEST")"

# Write the OUTPUT into the container (SaveCopyAs there neither prompts nor
# E_FAILs), then shell-move it to the destination.
STAGE="$OUT_STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

echo "staging -> $STAGE"
osascript "$DRIVER" "$BASE" "$STAGE" "$SPEC"

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  echo "done -> $OUT"
else
  echo "ERROR: macro did not produce the staged file. On a macro error the osascript step above already aborted with the VBA Err.Description; reaching here means the macro returned without error but wrote no file. Confirm DeckOps.pptm is open with macros enabled and Automation consent granted — see skills/presentation-creator/references/deck-editing-setup.md." >&2
  exit 1
fi

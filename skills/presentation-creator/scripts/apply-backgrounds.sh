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
DRIVER="$HERE/apply-backgrounds.applescript"

[[ -f "$BASE" ]]     || { echo "ERROR: base deck not found: $BASE" >&2; exit 1; }
[[ -f "$MANIFEST" ]] || { echo "ERROR: backgrounds manifest not found: $MANIFEST" >&2; exit 1; }
[[ -f "$DRIVER" ]]   || { echo "ERROR: driver not found: $DRIVER" >&2; exit 1; }

# Build the "#=path;#=path" spec from the manifest. Deterministic JSON->spec
# normalization (sorted by slide number); fails loudly on a malformed image path.
SPEC="$(python3 - "$MANIFEST" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
bg = m.get("backgrounds", {})
if not bg:
    sys.stderr.write("ERROR: manifest has no 'backgrounds' entries\n"); sys.exit(1)
toks = []
for k in sorted(bg, key=lambda x: int(x)):
    p = bg[k]
    if ";" in p or "=" in p:
        sys.stderr.write(f"ERROR: image path contains a reserved char (;/=): {p}\n"); sys.exit(1)
    toks.append(f"{int(k)}={p}")
print(";".join(toks))
PY
)"

# Sandboxed PowerPoint can't create a file in a Google Drive folder (E_FAIL) —
# stage locally, then move into place with the shell.
STAGE_DIR="$HOME/.deckops-staging"
mkdir -p "$STAGE_DIR"
STAGE="$STAGE_DIR/$(basename "$OUT")"
rm -f "$STAGE"

echo "staging -> $STAGE"
osascript "$DRIVER" "$BASE" "$STAGE" "$SPEC"

if [[ -f "$STAGE" ]]; then
  mkdir -p "$(dirname "$OUT")"
  mv -f "$STAGE" "$OUT"
  echo "done -> $OUT"
else
  echo "ERROR: macro did not produce the staged file (see the PowerPoint error dialog)." >&2
  exit 1
fi

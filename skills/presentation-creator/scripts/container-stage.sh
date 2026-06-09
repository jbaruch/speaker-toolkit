#!/bin/bash
# container-stage.sh — stage Google-Drive inputs into PowerPoint's sandbox
# container so the sandboxed macro reads them WITHOUT a Powerbox grant prompt.
#
# macOS PowerPoint prompts (Powerbox "grant access") whenever a VBA macro opens or
# reads a file on an un-granted CloudStorage path (a Google Drive base deck, the
# template, an illustration). Copying the input INTO PowerPoint's own container —
# which the sandboxed process always reads without a prompt — eliminates the
# prompt with no Full Disk Access grant. See rules/deck-editing-rules.md.
#
# Sourced (not executed) by every deck-ops wrapper. Provides:
#   CONTAINER_STAGE   per-run staging dir inside the container ("" if no container)
#   OUT_STAGE_DIR     where the macro writes its OUTPUT (SaveCopyAs) — inside the
#                     container so the save neither prompts nor E_FAILs; the wrapper
#                     shell-moves the result to the final (Drive) destination
#   stage_base <deck> echoes a path to OPEN: a container copy of <deck>, or <deck>
#                     unchanged when the container is absent (fallback: may prompt)
# A single EXIT trap removes the per-run staging dir (covers success and early
# failure under set -e). Wrappers MUST NOT set their own EXIT trap — it would
# override this one and leak the staged copies.
#
# Why output goes through the container: SaveCopyAs to a Google-Drive folder hits
# E_FAIL, AND a local ~/.deckops-staging path is OUTSIDE the sandbox so it raises a
# Powerbox "Grant File Access" prompt (every run, for per-run subdirs). The
# container is the one place the sandboxed app writes freely and silently.

PPT_CONTAINER="$HOME/Library/Containers/com.microsoft.Powerpoint/Data"
CONTAINER_STAGE=""
if [[ -d "$PPT_CONTAINER" ]]; then
  CONTAINER_STAGE="$PPT_CONTAINER/.deckops-stage/$$"
fi
if [[ -n "$CONTAINER_STAGE" ]]; then
  OUT_STAGE_DIR="$CONTAINER_STAGE/out"
else
  OUT_STAGE_DIR="$HOME/.deckops-staging"   # fallback: no container (may prompt)
fi
mkdir -p "$OUT_STAGE_DIR"

_container_stage_cleanup() {
  [[ -n "${CONTAINER_STAGE:-}" && -d "${CONTAINER_STAGE:-}" ]] && rm -rf "$CONTAINER_STAGE"
}
trap _container_stage_cleanup EXIT

# stage_base <deckPath> — copy the deck into the container and echo the container
# path so the macro opens it prompt-free. Echoes the original path unchanged when
# the container is absent or the copy fails (graceful fallback; macOS may prompt).
stage_base() {
  local src="$1" dst
  if [[ -n "$CONTAINER_STAGE" ]]; then
    dst="$CONTAINER_STAGE/$(basename "$src")"
    if cp "$src" "$dst" 2>/dev/null; then
      printf '%s' "$dst"
      return
    fi
  fi
  printf '%s' "$src"
}

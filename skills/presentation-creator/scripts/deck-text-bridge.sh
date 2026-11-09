#!/bin/bash
# deck-text-bridge.sh — sourced by the deck wrappers, after container-stage.sh.
# Escapes text so it survives `run VB macro` intact; see deck-text-bridge.py.
#
#   TITLE="$(bridge_text "$TITLE")"        one macro argument
#   OPS="$(bridge_file "$OPS")"            an op sequence or packed spec file
#
# Both write only inside OUT_STAGE_DIR, which container-stage.sh removes on exit.
# Assign the result on its own line, as above: inside a command's arguments, a
# refusal would not stop the wrapper under `set -e`.
set -euo pipefail

_DECK_TEXT_BRIDGE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deck-text-bridge.py"

bridge_text() {
  local input
  input="$(mktemp "$OUT_STAGE_DIR/bridge-text.XXXXXX")" || return 1
  printf '%s' "$1" >"$input" || return 1
  python3 "$_DECK_TEXT_BRIDGE" scalar "$input" "$input.out" >/dev/null || return 1
  cat "$input.out"
}

bridge_file() {
  local output
  output="$(mktemp "$OUT_STAGE_DIR/bridge-file.XXXXXX")" || return 1
  python3 "$_DECK_TEXT_BRIDGE" file "$1" "$output" >/dev/null || return 1
  printf '%s\n' "$output"
}

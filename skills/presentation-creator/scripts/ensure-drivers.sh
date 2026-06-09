#!/bin/bash
# ensure-drivers.sh — restore the deck-ops drivers that tessl install strips.
#
# `tessl install` ships only .md/.py/.json/.sh/.txt and STRIPS .bas/.applescript,
# so on an installed tile RunDeckOps.bas and the eight *.applescript drivers are
# missing. This sources into every deck-ops wrapper and recreates them from their
# committed .txt mirrors (sync-deck-drivers.py materialize). Idempotent — a no-op
# in the dev tree where the real files already exist. See rules/deck-editing-rules.md.
#
# Sourced (not executed) by the wrappers, so it runs in their shell before the
# driver-existence checks.
__ED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$__ED_DIR/sync-deck-drivers.py" materialize >/dev/null 2>&1 || true

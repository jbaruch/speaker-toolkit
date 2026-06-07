#!/usr/bin/env bash
# content-only-gate.sh — decide whether the pending changes in a git work
# tree touch ONLY content paths, making a direct push to the default branch
# safe under coding-policy ci-safety's content-publishing carve-out.
# See jbaruch/coding-policy#119 for the carve-out rationale.
#
# ALLOWED_PREFIXES below is the allowlist: the only path prefixes a direct
# push may modify. Any pending change outside them forces branch + PR.
#
# Contract:
#   Usage: content-only-gate.sh [TARGET_REPO_DIR]   (default: .)
#   Considers every pending change: staged, unstaged, and untracked.
#   stdout (last line): JSON
#     {"content_only": bool, "changed": [paths], "outside": [paths]}
#   Exit 0 -> content_only true   (safe to direct-push)
#   Exit 1 -> content_only false  (use branch + PR)
#   Exit 2 -> error: not a git work tree, no HEAD, or no pending changes
#             (caller falls back to branch + PR)
set -euo pipefail

ALLOWED_PREFIXES=(
  "_talks/"
  "assets/images/thumbnails/"
)

target="${1:-.}"

err() { printf 'content-only-gate: %s\n' "$*" >&2; }

json_str() { printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }

if ! git -C "$target" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  err "not a git work tree: $target"
  exit 2
fi

if ! git -C "$target" rev-parse --verify -q HEAD >/dev/null 2>&1; then
  err "no HEAD commit in $target — cannot diff pending changes"
  exit 2
fi

content_only=true
changed_json=""
outside_json=""
seen=""

append() {
  local path="$1" allowed=false p
  case "$seen" in *"|$path|"*) return 0;; esac
  seen="$seen|$path|"
  for p in "${ALLOWED_PREFIXES[@]}"; do
    case "$path" in "$p"*) allowed=true; break;; esac
  done
  changed_json="$changed_json${changed_json:+,}$(json_str "$path")"
  if ! $allowed; then
    content_only=false
    outside_json="$outside_json${outside_json:+,}$(json_str "$path")"
  fi
}

while IFS= read -r -d '' path; do
  [ -n "$path" ] && append "$path"
done < <(git -C "$target" diff --name-only -z HEAD --)

while IFS= read -r -d '' path; do
  [ -n "$path" ] && append "$path"
done < <(git -C "$target" ls-files --others --exclude-standard -z --)

if [ -z "$changed_json" ]; then
  err "no pending changes in $target to evaluate"
  exit 2
fi

printf '{"content_only":%s,"changed":[%s],"outside":[%s]}\n' \
  "$content_only" "$changed_json" "$outside_json"

if [ "$content_only" = true ]; then exit 0; else exit 1; fi

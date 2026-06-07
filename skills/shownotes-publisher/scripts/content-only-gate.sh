#!/usr/bin/env bash
# content-only-gate.sh — decide whether a direct push to the protected branch
# would change ONLY content paths, per coding-policy ci-safety's Content-Only
# Direct-Push Carve-Out (Form B client-side gate).
#
# It enumerates the FULL set of paths the push would land on the protected
# branch — committed-but-unpushed changes (origin/<branch>..HEAD) AND pending
# work-tree changes (staged, unstaged, untracked) about to be committed — so an
# earlier non-content commit cannot ride along on the push. The push is
# content-only iff every enumerated path matches an allowlisted content prefix.
#
# ALLOWED_PREFIXES below is the allowlist. Keep it in sync with the
# authority-of-record rule (rules/shownotes-content-publish.md).
#
# Usage: content-only-gate.sh [TARGET_REPO_DIR] [PROTECTED_BRANCH]
#   TARGET_REPO_DIR   default "."
#   PROTECTED_BRANCH  default "main"
# stdout (last line): JSON
#   {"content_only": bool, "changed": [paths], "outside": [paths]}
# Exit 0 -> content_only true   (safe to direct-push)
# Exit 1 -> content_only false  (use branch + PR)
# Exit 2 -> error: not a git work tree, no HEAD, not on the protected branch,
#           no upstream to compare against, or an empty push (caller falls back
#           to branch + PR)
set -euo pipefail

ALLOWED_PREFIXES=(
  "_talks/"
  "assets/images/thumbnails/"
)

target="${1:-.}"
branch="${2:-main}"

g() { git -C "$target" "$@"; }
err() { printf 'content-only-gate: %s\n' "$*" >&2; }
json_str() { printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }

if ! g rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  err "not a git work tree: $target"
  exit 2
fi
if ! g rev-parse --verify -q HEAD >/dev/null 2>&1; then
  err "no HEAD commit in $target"
  exit 2
fi

# A direct push advances the protected branch; the gate only applies there.
current=$(g rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ "$current" != "$branch" ]; then
  err "not on protected branch '$branch' (on '$current')"
  exit 2
fi

# Refresh the upstream ref (best-effort; offline falls through to the local ref).
g fetch -q origin "$branch" 2>/dev/null || true

base=$(g rev-parse --verify -q "origin/$branch" 2>/dev/null || echo "")
if [ -z "$base" ]; then
  err "no origin/$branch to compare the push against"
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

# committed-but-unpushed changes the push would carry
while IFS= read -r -d '' path; do
  [ -n "$path" ] && append "$path"
done < <(g diff --name-only -z "$base" HEAD --)

# pending work-tree changes about to be committed (staged + unstaged)
while IFS= read -r -d '' path; do
  [ -n "$path" ] && append "$path"
done < <(g diff --name-only -z HEAD --)

# untracked files about to be added
while IFS= read -r -d '' path; do
  [ -n "$path" ] && append "$path"
done < <(g ls-files --others --exclude-standard -z --)

if [ -z "$changed_json" ]; then
  err "no changes to publish in $target — the push would be empty"
  exit 2
fi

printf '{"content_only":%s,"changed":[%s],"outside":[%s]}\n' \
  "$content_only" "$changed_json" "$outside_json"

if [ "$content_only" = true ]; then exit 0; else exit 1; fi

#!/usr/bin/env bash
# Refuse to let the Codex review output carry the subscription credential.
#
# A pull request can edit the reviewed rules/ or the review prompt to try to
# make Codex echo the token from ~/.codex/auth.json into its review output.
# This fails the run — before the verdict is posted — if any secret string from
# the auth file appears verbatim in the review output. (A collaborator editing
# the workflow itself is out of scope: same-repo PRs require write access, which
# GitHub already treats as trusted.)
#
# Usage: assert-no-secret-leak.sh <auth-json> <review-output-json>
# Exit:  0 clean; 1 the output contains credential material; 2 arg/tool error.

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is not installed; install with 'brew install jq' (macOS) or 'apt install jq' (Debian/Ubuntu) and re-run" >&2
  exit 2
fi

main() {
  if [[ $# -ne 2 ]]; then
    echo "usage: $0 <auth-json> <review-output-json>" >&2
    exit 2
  fi
  local auth="$1" out="$2"
  # Nothing to check if either file is absent — the review/seed step already
  # failed and surfaces elsewhere; treat as clean here.
  [[ -f "$auth" && -f "$out" ]] || return 0

  local tokens out_contents
  tokens=$(jq -r '.. | strings' "$auth") \
    || { echo "error: could not parse ${auth} as JSON to extract secret strings" >&2; exit 2; }
  out_contents=$(cat "$out")

  # Every string value >= 16 chars anywhere in auth.json is treated as secret
  # material. Short strings (field names, "chatgpt", timestamps) are ignored so
  # ordinary review prose never trips the guard.
  #
  # No pipeline: `grep -q` exits at the first match, which under `set -o
  # pipefail` would SIGPIPE a `printf | grep` producer and report the pipeline
  # non-zero even on a MATCH — collapsing "leak found" into "clean". A
  # here-string has no producer, so grep's own rc is authoritative: 0 match
  # (leak), 1 no match (clean), >1 a grep fault we fail CLOSED on.
  local s grc
  while IFS= read -r s; do
    (( ${#s} >= 16 )) || continue
    grc=0
    grep -qF -- "$s" <<< "$out_contents" || grc=$?
    case "$grc" in
      0) echo "SECURITY: review output contains credential material from ${auth} — refusing to post" >&2; exit 1 ;;
      1) ;;  # no match: clean, keep scanning
      *) echo "error: grep failed (rc=${grc}) scanning the review output — cannot verify the output is credential-free; failing closed" >&2; exit 2 ;;
    esac
  done <<< "$tokens"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi

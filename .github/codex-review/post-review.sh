#!/usr/bin/env bash
# Post a Codex policy-review verdict onto a pull request as a GitHub review.
#
# Reads the structured result Codex produced (the --output-last-message file,
# shaped by .github/codex-review/schema.json) and submits ONE pull-request
# review whose body carries the summary and every finding. Findings ride in
# the review body rather than as inline comments so an off-diff line can never
# trigger the HTTP 422 that would cascade-fail the whole review.
#
# The review is authored by whoever GH_TOKEN belongs to — in CI that is
# `github-actions[bot]`, which GitHub forbids from posting APPROVE (HTTP 422).
# So a clean pass is a COMMENT; a violation is REQUEST_CHANGES.
#
# Usage: post-review.sh <owner> <repo> <pr-number> <result-json-file>
# Out:   one JSON object on stdout: {"state":"posted","event":"...","findings":N}
# Exit:  0 on success; non-zero with a stderr diagnostic on failure.

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is not installed; install with 'brew install jq' (macOS) or 'apt install jq' (Debian/Ubuntu) and re-run" >&2
  exit 2
fi

main() {
  if [[ $# -ne 4 ]]; then
    echo "usage: $0 <owner> <repo> <pr-number> <result-json-file>" >&2
    exit 2
  fi
  local owner="$1" repo="$2" pr="$3" result="$4"

  if [[ ! -f "$result" ]]; then
    echo "error: result file not found: ${result} — codex exec did not write its --output-last-message file; check the review step logs" >&2
    exit 1
  fi
  if ! jq -e . "$result" >/dev/null 2>&1; then
    echo "error: ${result} is not valid JSON — codex exec did not honor --output-schema; inspect the file and the review step logs" >&2
    exit 1
  fi

  local verdict summary findings_count
  verdict=$(jq -r '.verdict // "pass"' "$result")
  summary=$(jq -r '.summary // ""' "$result")
  findings_count=$(jq '(.findings // []) | length' "$result")

  local event
  case "$verdict" in
    changes_requested) event="REQUEST_CHANGES" ;;
    pass)              event="COMMENT" ;;
    *) echo "error: unexpected verdict '${verdict}' in ${result} (want pass|changes_requested)" >&2; exit 1 ;;
  esac

  # Build the review body: summary, then a findings list (omitted when clean).
  local body findings_md
  body="$summary"
  if (( findings_count > 0 )); then
    findings_md=$(jq -r '.findings[] | "- `\(.path):\(.line)` — **\(.rule)** — \(.message)"' "$result")
    body="${body}"$'\n\n'"## Findings"$'\n'"${findings_md}"
  fi

  local payload attempt=0 max=3
  payload=$(jq -n --arg event "$event" --arg body "$body" '{event: $event, body: $body}')

  # Retry on a transient GitHub API failure (5xx / network) — a policy verdict
  # must not be lost to a blip. gh exits non-zero on HTTP errors; back off and
  # retry before giving up.
  while :; do
    attempt=$((attempt + 1))
    if printf '%s' "$payload" | gh api "repos/${owner}/${repo}/pulls/${pr}/reviews" --method POST --input - >&2; then
      break
    fi
    if (( attempt >= max )); then
      echo "error: failed to submit the review on ${owner}/${repo}#${pr} after ${max} attempts — see the gh error above (token scope, PR state, or a GitHub API outage)" >&2
      exit 1
    fi
    echo "post-review: submit attempt ${attempt} failed — retrying in $(( attempt * 5 ))s" >&2
    sleep $(( attempt * 5 ))
  done

  jq -n --arg event "$event" --argjson findings "$findings_count" \
    '{state: "posted", event: $event, findings: $findings}'
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi

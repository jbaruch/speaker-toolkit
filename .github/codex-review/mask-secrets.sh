#!/usr/bin/env bash
# Register every secret string in an auth.json with GitHub Actions log masking
# (::add-mask::) so that a prompt-injected review which prints the token has it
# redacted as *** in the (public) CI logs. Emit this BEFORE running any
# PR-controlled agent code — masking only applies to log output produced after
# the command is processed.
#
# Usage: mask-secrets.sh <auth-json>
# Out:   one `::add-mask::<value>` workflow command per secret string on stdout.
# Exit:  0 (including when the file is absent — nothing to mask); 2 on tool error.

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is not installed; install with 'brew install jq' (macOS) or 'apt install jq' (Debian/Ubuntu) and re-run" >&2
  exit 2
fi

main() {
  [[ $# -eq 1 ]] || { echo "usage: $0 <auth-json>" >&2; exit 2; }
  local auth="$1"
  [[ -f "$auth" ]] || return 0

  local tokens s
  tokens=$(jq -r '.. | strings' "$auth") \
    || { echo "error: could not parse ${auth} as JSON to extract secret strings" >&2; exit 2; }

  # Mask every string value >= 16 chars anywhere in auth.json. Short values
  # (field names, "chatgpt") are skipped so masking never redacts ordinary words.
  while IFS= read -r s; do
    (( ${#s} >= 16 )) || continue
    printf '::add-mask::%s\n' "$s"
  done <<< "$tokens"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi

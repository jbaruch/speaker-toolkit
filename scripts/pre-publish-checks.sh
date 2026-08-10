#!/usr/bin/env bash
# Composer for the publish workflow's `pre-publish-script` input, which takes a
# single path. Runs every repo-side pre-publish gate in order; the first
# failure aborts the publish.
#
# Each gate emits a JSON report on stdout and actionable diagnostics on stderr
# (script-delegation -> Script Requirements). The composer only cares about the
# exit code, so it discards the reports and lets the diagnostics through.
#
# Wired into CI by .github/workflows/publish.yml.
set -euo pipefail

main() {
  local repo_root
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

  python3 "$repo_root/scripts/check_tessl_pins.py" > /dev/null
  python3 "$repo_root/scripts/check_package_contents.py" > /dev/null
  python3 "$repo_root/scripts/check_skill_entrypoints.py" > /dev/null
  python3 "$repo_root/scripts/check_conflict_markers.py" > /dev/null
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  main "$@"
fi

#!/usr/bin/env bash
# Composer for the publish workflow's `pre-publish-script` input, which takes a
# single path. Runs every repo-side pre-publish gate in order; the first
# failure aborts the publish.
#
# Wired into CI by .github/workflows/publish.yml.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$REPO_ROOT/scripts/check-tessl-pins.sh"
"$REPO_ROOT/scripts/check-package-contents.sh"
"$REPO_ROOT/scripts/check-skill-entrypoints.sh"

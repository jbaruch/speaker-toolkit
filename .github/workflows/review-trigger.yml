name: Trigger fleet policy review

# On each pull request in this repo, starts a review of that PR against the
# jbaruch/coding-policy coding rules, so the result is available before merge. The
# jbaruch/coding-policy schedule reviews the same PRs as a backstop. Fork pull
# requests are skipped (they cannot read the secret). Dependabot pull requests are
# skipped too (the dependabot actor gets no secrets); the schedule covers them.
#
# Requires one repo secret (set it at
# https://github.com/<owner>/<repo>/settings/secrets/actions for this repo):
#   FLEET_DISPATCH_TOKEN — the token this workflow reads to start the review run in
#     jbaruch/coding-policy. Create it with Actions: Read and write on jbaruch/coding-policy.

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions: {}

concurrency:
  group: trigger-fleet-review-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  trigger:
    # Fork PRs cannot read secrets — skip them (adopt via the adopt-fork-pr skill).
    # Dependabot's actor also gets no secrets, so its request can't authenticate —
    # skip it too (the coding-policy cron poll reviews dependabot PRs instead).
    if: >-
      github.event.pull_request.head.repo.full_name == github.repository &&
      github.actor != 'dependabot[bot]'
    runs-on: ubuntu-latest
    steps:
      - name: Dispatch the single-PR review to coding-policy
        env:
          GH_TOKEN: ${{ secrets.FLEET_DISPATCH_TOKEN }}
          REPO: ${{ github.event.repository.name }}
          PR: ${{ github.event.pull_request.number }}
          BASE: ${{ github.event.pull_request.base.ref }}
        run: |
          set -euo pipefail
          if [ -z "${GH_TOKEN:-}" ]; then
            echo "error: FLEET_DISPATCH_TOKEN secret is empty — set a fine-grained token scoped to Actions: Read and write on jbaruch/coding-policy only; see this workflow's header" >&2
            exit 1
          fi
          gh workflow run fleet-review.yml \
            --repo jbaruch/coding-policy \
            -f repo="$REPO" -f pr="$PR" -f base="$BASE"

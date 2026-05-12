#!/usr/bin/env bash
# Deploy-time check for the tessl-version-floating carve-out.
#
# Walks every manifest covered by the carve-out (see
# rules/tessl-version-floating.md) and fails if any dependency uses a
# specifier other than the permitted floating value "latest" — rejecting
# literal pins, version ranges, tags, and anything else per the
# `jbaruch/coding-policy: dependency-management` clause "rejecting only
# literal pins lets a non-literal pinned/ranged value slip through".
#
# Wired into CI by .github/workflows/tests.yml.
set -euo pipefail

# Every manifest covered by the carve-out. Keep in sync with
# rules/tessl-version-floating.md → "Covered Manifests".
COVERED_MANIFESTS=(
  "tessl.json"
)

EXPECTED_SPECIFIER="latest"
status=0

for manifest in "${COVERED_MANIFESTS[@]}"; do
  if [ ! -f "$manifest" ]; then
    echo "ERROR: covered manifest $manifest not found." >&2
    echo "  rules/tessl-version-floating.md lists $manifest as a covered manifest, but it does not exist on disk." >&2
    echo "  Either restore the manifest or remove it from rules/tessl-version-floating.md → Covered Manifests." >&2
    status=1
    continue
  fi

  # Walk every dependency entry; collect anything that's not exactly "latest".
  bad=$(python3 - "$manifest" "$EXPECTED_SPECIFIER" <<'PY'
import json, sys

manifest_path, expected = sys.argv[1], sys.argv[2]
with open(manifest_path) as f:
    data = json.load(f)

violations = []
for name, spec in (data.get("dependencies") or {}).items():
    if not isinstance(spec, dict):
        violations.append((name, repr(spec)))
        continue
    version = spec.get("version")
    if version != expected:
        violations.append((name, repr(version)))

for name, found in violations:
    print(f"{name}: {found}")

sys.exit(1 if violations else 0)
PY
  ) || {
    echo "ERROR: $manifest contains dependencies with non-floating specifiers:" >&2
    echo "$bad" | sed 's/^/  /' >&2
    echo "" >&2
    echo "  Per rules/tessl-version-floating.md, every dependency in this manifest must use" >&2
    echo "  \"version\": \"latest\". Pinning here produces silent drift because \`tessl update\`" >&2
    echo "  rewrites the manifest in-place at runtime and .tessl/tiles/ is gitignored." >&2
    echo "" >&2
    echo "  Fix: change the flagged specifier(s) to \"latest\", or — if you intentionally" >&2
    echo "  want this manifest to pin — remove it from the carve-out by editing both" >&2
    echo "  rules/tessl-version-floating.md → Covered Manifests AND scripts/check-tessl-pins.sh" >&2
    echo "  → COVERED_MANIFESTS." >&2
    status=1
  }
done

if [ "$status" -ne 0 ]; then
  exit 1
fi

echo "OK: every dependency in every covered manifest uses the permitted floating specifier ($EXPECTED_SPECIFIER)."

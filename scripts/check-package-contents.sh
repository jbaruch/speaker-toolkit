#!/usr/bin/env bash
# Gate: every file the plugin manifest declares as plugin content must survive
# .tesslignore filtering into the published package.
#
# The failure this catches: .tesslignore uses gitignore pattern semantics, so an
# unanchored directory pattern ("scripts/") matches a directory of that name at
# ANY depth — including skills/<name>/scripts/. A pattern written for the
# repo-side helper directory silently strips every skill's runtime scripts from
# the package, and `tessl plugin publish` still reports success.
#
# Matching runs against a throwaway empty git repo with core.excludesFile
# pointed at .tesslignore, so only .tesslignore patterns are consulted — the
# repo's own .gitignore can neither mask a match nor invent one.
#
# Usage: check-package-contents.sh [<repo-root>]   (default: this repo)
# Exit 0 when every declared content file packs, non-zero otherwise.
#
# Wired into CI by .github/workflows/tests.yml, and into the publish run by
# scripts/pre-publish-checks.sh.
set -euo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$REPO_ROOT"
REPO_ROOT="$(pwd)"

MANIFEST=".tessl-plugin/plugin.json"
IGNORE_FILE=".tesslignore"

if [ ! -f "$MANIFEST" ]; then
  echo "ERROR: plugin manifest $MANIFEST not found under $REPO_ROOT." >&2
  echo "  Point this check at the plugin repo root, or restore the manifest." >&2
  exit 1
fi

if [ ! -f "$IGNORE_FILE" ]; then
  echo "OK: no $IGNORE_FILE present — nothing can be excluded from the package."
  exit 0
fi

# Declared content paths, one per line: every entry of `skills` and `rules`.
rc=0
declared=$(python3 - "$MANIFEST" 2>&1 <<'PY'
import json
import sys

manifest_path = sys.argv[1]
try:
    with open(manifest_path) as f:
        data = json.load(f)
except json.JSONDecodeError as e:
    # Exit 2 — malformed JSON. The wrapper switches on this to say "fix the
    # syntax" instead of the unrelated "content is excluded" message.
    print(f"MALFORMED_JSON: {e.msg} at line {e.lineno} col {e.colno}", file=sys.stderr)
    sys.exit(2)
except OSError as e:
    # Exit 3 — file present (the bash existence precheck passed) but unreadable.
    print(f"UNREADABLE_MANIFEST: {e}", file=sys.stderr)
    sys.exit(3)

# Exit 4 — wrong shape. `skills` / `rules` are each a directory-path string or
# an array of paths; anything else would crash the walk below with a traceback.
if not isinstance(data, dict):
    print(f"BAD_SHAPE: expected top-level JSON object, got {type(data).__name__}", file=sys.stderr)
    sys.exit(4)

entries = []
for field in ("skills", "rules"):
    value = data.get(field)
    if value is None:
        continue
    if isinstance(value, str):
        entries.append(value)
    elif isinstance(value, list):
        for position, item in enumerate(value):
            # A non-string item coerced with str() would be reported downstream
            # as a missing directory, sending the reader after a path that was
            # never declared. It is a manifest shape error, so say that.
            if not isinstance(item, str):
                print(
                    f"BAD_SHAPE: manifest field {field!r}[{position}] must be a "
                    f"string, got {type(item).__name__}",
                    file=sys.stderr,
                )
                sys.exit(4)
            entries.append(item)
    else:
        print(
            f"BAD_SHAPE: manifest field {field!r} must be a string or array, "
            f"got {type(value).__name__}",
            file=sys.stderr,
        )
        sys.exit(4)

# Exit 5 — a manifest declaring no content has nothing to protect, which means
# the gate would pass vacuously on a plugin that ships nothing.
if not entries:
    print("NO_CONTENT: manifest declares neither `skills` nor `rules`", file=sys.stderr)
    sys.exit(5)

for entry in entries:
    print(entry.rstrip("/"))
PY
) || rc=$?

case "$rc" in
  0)
    ;;
  2)
    echo "ERROR: $MANIFEST is not valid JSON." >&2
    echo "$declared" | sed 's/^/  /' >&2
    echo "" >&2
    echo "  Fix the JSON syntax error and re-run. The package-contents check" >&2
    echo "  can't tell what the plugin ships until the manifest parses." >&2
    exit 1
    ;;
  3)
    echo "ERROR: $MANIFEST could not be read." >&2
    echo "$declared" | sed 's/^/  /' >&2
    echo "" >&2
    echo "  Check file permissions / disk state, then re-run." >&2
    exit 1
    ;;
  4)
    echo "ERROR: $MANIFEST has the wrong shape." >&2
    echo "$declared" | sed 's/^/  /' >&2
    echo "" >&2
    echo "  \`skills\` and \`rules\` must each be a path string or an array of" >&2
    echo "  paths (see jbaruch/coding-policy: skill-authoring -> plugin.json" >&2
    echo "  Manifest Reference)." >&2
    exit 1
    ;;
  5)
    echo "ERROR: $MANIFEST declares no plugin content." >&2
    echo "$declared" | sed 's/^/  /' >&2
    echo "" >&2
    echo "  Add the plugin's \`skills\` and/or \`rules\` entries. Without them the" >&2
    echo "  published package is empty and this gate has nothing to verify." >&2
    exit 1
    ;;
  *)
    echo "ERROR: reading $MANIFEST failed (exit $rc)." >&2
    echo "$declared" | sed 's/^/  /' >&2
    exit 1
    ;;
esac

# Empty scratch repo so check-ignore consults ONLY .tesslignore.
scratch="$(mktemp -d)"
cleanup() {
  rm -rf "$scratch"
  return 0
}
trap cleanup EXIT
git init -q "$scratch"

content_list="$scratch/content.txt"
: > "$content_list"

missing=0
while IFS= read -r declared_path; do
  [ -n "$declared_path" ] || continue
  count=0
  while IFS= read -r tracked; do
    printf '%s\n' "$tracked" >> "$content_list"
    count=$((count + 1))
  done < <(git ls-files -- "$declared_path")
  if [ "$count" -eq 0 ]; then
    echo "ERROR: $MANIFEST declares \"$declared_path\" but no tracked files live there." >&2
    echo "  Restore the path, or drop it from the manifest (see" >&2
    echo "  jbaruch/coding-policy: context-artifacts -> Surface Sync)." >&2
    missing=1
  fi
done <<< "$declared"

if [ "$missing" -ne 0 ]; then
  exit 1
fi

# A manifest may declare both a directory and a path beneath it (e.g. `skills/`
# alongside `skills/release`). Every file under the narrower path is then listed
# twice, which inflates `total`, repeats each violation line, and makes the
# "excludes X of Y" counts wrong. De-duplicate after the per-path existence
# check above, which needs its own unfiltered count.
sort -u "$content_list" -o "$content_list"

total=$(wc -l < "$content_list" | tr -d ' ')

rc=0
violations=$(git -C "$scratch" -c core.excludesFile="$REPO_ROOT/$IGNORE_FILE" \
  check-ignore --no-index -v --stdin < "$content_list") || rc=$?

case "$rc" in
  1)
    # check-ignore exits 1 when no path matched — every declared file packs.
    echo "OK: all $total declared plugin content files survive $IGNORE_FILE into the package."
    exit 0
    ;;
  0)
    ;;
  *)
    echo "ERROR: git check-ignore failed (exit $rc) while testing $IGNORE_FILE patterns." >&2
    echo "$violations" | sed 's/^/  /' >&2
    exit 1
    ;;
esac

excluded=$(printf '%s\n' "$violations" | wc -l | tr -d ' ')

echo "ERROR: $IGNORE_FILE excludes $excluded of $total declared plugin content files." >&2
echo "  These are declared in $MANIFEST but would NOT ship in the published package:" >&2
echo "" >&2
printf '%s\n' "$violations" | sed 's/^/  /' >&2
echo "" >&2
echo "  Format above: <ignore-file>:<line>:<pattern>	<excluded file>" >&2
echo "" >&2
echo "  Cause: $IGNORE_FILE uses gitignore pattern semantics. A pattern with no" >&2
echo "  leading slash matches at every depth, so \"foo/\" strips a repo-root" >&2
echo "  foo/ AND skills/<name>/foo/." >&2
echo "" >&2
echo "  Fix: anchor the flagged pattern to the repo root with a leading slash" >&2
echo "  (\"scripts/\" -> \"/scripts/\"), or narrow it so it stops matching plugin" >&2
echo "  content. Re-run this check to confirm." >&2
exit 1

#!/usr/bin/env bash
# Gate: every auto-loaded SKILL.md stays inside Tessl's entrypoint token budget,
# and every relative link it carries resolves to a file that actually ships.
#
# Two failures this catches:
#
#   1. Size. A SKILL.md is loaded in full the moment its skill triggers, before
#      any task-specific reference is selected. `tessl plugin lint` reports an
#      oversized entrypoint as an advisory, so a publish still succeeds while
#      every consumer pays the context cost on every trigger.
#
#   2. Dangling references. Splitting detail out of a SKILL.md moves the content
#      behind a relative link. A typo'd or stale link is invisible to lint —
#      the agent follows the pointer at runtime, finds nothing, and silently
#      proceeds without the routing contract the split assumed.
#
# Token estimate is chars/4, which over-estimates Tessl's tokenizer: at the time
# this gate was written, a 35,162-char SKILL.md estimated 8,790 tokens here and
# `tessl plugin lint` reported 8,749. Erring high means a pass here implies a
# pass there, so the gate never green-lights a file lint would flag. The budget
# below mirrors Tessl's published recommendation.
#
# Usage: check-skill-entrypoints.sh [<repo-root>]   (default: this repo)
# Exit 0 when every entrypoint is inside budget with no dangling links.
#
# Wired into CI by tests/test_skill_entrypoints.py, and into the publish run by
# scripts/pre-publish-checks.sh.
set -euo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$REPO_ROOT"
REPO_ROOT="$(pwd)"

# Tessl's recommended maximum tokens per skill entrypoint.
TOKEN_BUDGET=5000
# Divisor for the chars-per-token estimate. See the header note on why this
# rounds against us rather than for us.
CHARS_PER_TOKEN=4

SKILLS_DIR="skills"

if [ ! -d "$SKILLS_DIR" ]; then
  echo "ERROR: no $SKILLS_DIR/ directory under $REPO_ROOT." >&2
  echo "  Point this check at the plugin repo root." >&2
  exit 1
fi

shopt -s nullglob
entrypoints=("$SKILLS_DIR"/*/SKILL.md)
shopt -u nullglob

if [ ${#entrypoints[@]} -eq 0 ]; then
  # A repo with a skills/ directory and no SKILL.md in it would otherwise pass
  # vacuously, reporting "0 entrypoints OK" on a broken layout.
  echo "ERROR: $SKILLS_DIR/ contains no */SKILL.md entrypoints." >&2
  echo "  Every skill directory needs a SKILL.md (see jbaruch/coding-policy:" >&2
  echo "  skill-authoring)." >&2
  exit 1
fi

oversized=()
dangling=()
checked=0

for skill_md in "${entrypoints[@]}"; do
  checked=$((checked + 1))
  skill_dir="$(dirname "$skill_md")"

  # Both reads below assume a readable file. Without this, an unreadable
  # entrypoint aborts on a bare "Permission denied" from a shell redirection,
  # naming no fix.
  if [ ! -r "$skill_md" ]; then
    echo "ERROR: could not scan $skill_md — not readable." >&2
    echo "  Fix the file permissions, then re-run." >&2
    exit 1
  fi

  chars=$(wc -c < "$skill_md" | tr -d ' ')
  # Ceiling, not truncation: 20,001 chars is over a 5,000-token budget, and
  # integer division would report it as exactly 5,000 and pass.
  tokens=$(((chars + CHARS_PER_TOKEN - 1) / CHARS_PER_TOKEN))
  if [ "$tokens" -gt "$TOKEN_BUDGET" ]; then
    over=$((tokens - TOKEN_BUDGET))
    oversized+=("$skill_md	~$tokens tokens ($chars chars) — $over over budget")
  fi

  # Relative markdown link targets: ](path) where path is neither a URL, an
  # anchor, nor an absolute path. Strip any #fragment before resolving.
  #
  # One awk does the whole extraction. A grep/sed pipeline needs each stage's
  # exit 1 (filtered everything out — legitimate here) told apart from exit 2
  # (bad regex) and from an unreadable file, which is what blanket `|| true`
  # collapses. awk exits 0 on "matched nothing" and non-zero only on real
  # failure, so the check below propagates exactly the failures that matter.
  if ! targets=$(awk '
        # Fenced blocks and inline code spans are sample output the skill
        # emits (a shownotes template'"'"'s `[View Slides]({slides_url})`),
        # not pointers the agent follows.
        /^[[:space:]]*(```|~~~)/ { fence = !fence; next }
        fence { next }
        {
          line = $0
          gsub(/`[^`]*`/, "", line)
          while (match(line, /\]\([^)]+\)/)) {
            target = substr(line, RSTART + 2, RLENGTH - 3)
            line = substr(line, RSTART + RLENGTH)
            if (target ~ /^[a-z][a-z0-9+.-]*:/) continue   # URL scheme
            if (target ~ /^[#\/]/) continue                # anchor or absolute
            if (target ~ /[{}]/) continue                  # runtime placeholder
            print target
          }
        }
      ' "$skill_md"); then
    echo "ERROR: could not scan $skill_md for relative links." >&2
    echo "  Check that the file is readable, then re-run." >&2
    exit 1
  fi

  while IFS= read -r target; do
    [ -n "$target" ] || continue
    resolved="$skill_dir/${target%%#*}"
    if [ ! -e "$resolved" ]; then
      dangling+=("$skill_md	$target	-> $resolved")
    fi
  done <<< "$targets"
done

fail=0

if [ ${#oversized[@]} -ne 0 ]; then
  fail=1
  echo "ERROR: ${#oversized[@]} of $checked skill entrypoints exceed the ${TOKEN_BUDGET}-token budget." >&2
  echo "" >&2
  printf '  %s\n' "${oversized[@]}" >&2
  echo "" >&2
  echo "  A SKILL.md loads in full when its skill triggers, before any" >&2
  echo "  task-specific reference is selected. Move detailed procedure into" >&2
  echo "  skills/<name>/references/<topic>.md and leave an explicit, " >&2
  echo "  deterministic loading condition in the step that needs it (see" >&2
  echo "  jbaruch/coding-policy: skill-authoring -> Keep Skills Compact)." >&2
fi

if [ ${#dangling[@]} -ne 0 ]; then
  [ "$fail" -eq 0 ] || echo "" >&2
  fail=1
  echo "ERROR: ${#dangling[@]} relative link(s) in skill entrypoints resolve to nothing." >&2
  echo "" >&2
  printf '  %s\n' "${dangling[@]}" >&2
  echo "" >&2
  echo "  Format above: <entrypoint>	<link target>	-> <resolved path>" >&2
  echo "" >&2
  echo "  A dangling pointer fails silently at runtime: the agent follows it," >&2
  echo "  finds nothing, and proceeds without the routing contract. Fix the" >&2
  echo "  path or restore the referenced file." >&2
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi

echo "OK: all $checked skill entrypoints are within ${TOKEN_BUDGET} tokens with no dangling relative links."
exit 0

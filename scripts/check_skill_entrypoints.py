#!/usr/bin/env python3
"""Gate: skill entrypoints stay inside Tessl's token budget with live links.

Two failures this catches:

1. Size. A SKILL.md is loaded in full the moment its skill triggers, before any
   task-specific reference is selected. ``tessl plugin lint`` reports an
   oversized entrypoint as an advisory, so a publish still succeeds while every
   consumer pays the context cost on every trigger.

2. Dangling references. Splitting detail out of a SKILL.md moves the content
   behind a relative link. A typo'd or stale link is invisible to lint — the
   agent follows the pointer at runtime, finds nothing, and silently proceeds
   without the routing contract the split assumed.

Token estimate is ``ceil(chars / CHARS_PER_TOKEN)``, which over-estimates
Tessl's tokenizer: at the time this gate was written, a 35,162-char SKILL.md
estimated 8,791 tokens here and ``tessl plugin lint`` reported 8,749. Erring
high means a pass here implies a pass there, so the gate never green-lights a
file lint would flag. Ceiling rather than truncation because 20,001 chars is
over a 5,000-token budget and floor division would call it exactly 5,000.

Usage: check_skill_entrypoints.py [<repo-root>]   (default: this repo)
Stdout: one JSON object describing every entrypoint checked.
Stderr: actionable diagnostics for each violation.
Exit 0 when every entrypoint is inside budget with no dangling links.

Wired into CI by tests/test_skill_entrypoints.py, and into the publish run by
scripts/pre-publish-checks.sh.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# Tessl's recommended maximum tokens per skill entrypoint.
TOKEN_BUDGET = 5000
# Divisor for the chars-per-token estimate. See the module docstring on why
# this rounds against us rather than for us.
CHARS_PER_TOKEN = 4

FENCE_PREFIXES = ("```", "~~~")


def estimate_tokens(text: str) -> int:
    """Tessl-conservative token estimate for an entrypoint body."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _strip_code(markdown: str) -> str:
    """Drop fenced blocks and inline code spans.

    Both carry sample output the skill emits — a shownotes template's
    ``[View Slides]({slides_url})`` — not pointers the agent follows.
    """
    lines: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        if line.lstrip().startswith(FENCE_PREFIXES):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Inline spans, innermost first; an unterminated backtick spans nothing.
        stripped = ""
        rest = line
        while True:
            open_tick = rest.find("`")
            if open_tick == -1:
                stripped += rest
                break
            close_tick = rest.find("`", open_tick + 1)
            if close_tick == -1:
                stripped += rest
                break
            stripped += rest[:open_tick]
            rest = rest[close_tick + 1 :]
        lines.append(stripped)
    return "\n".join(lines)


def _read_destination(text: str, start: int) -> tuple[str | None, int]:
    """Parse a CommonMark link destination beginning at ``start``.

    ``start`` indexes the character just past ``](``. Returns the destination
    and the index to resume scanning from. A destination is either an
    angle-bracket form (``<path with spaces>``) or a bare run of non-whitespace
    with balanced parentheses; either may carry backslash escapes, and either
    may be followed by a title the caller does not want. Returns ``None`` when
    the link is unterminated, which is not a dangling target — it is not a link.
    """
    i = start
    n = len(text)
    out: list[str] = []

    if i < n and text[i] == "<":
        i += 1
        while i < n:
            char = text[i]
            if char == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if char == ">":
                return "".join(out), i + 1
            if char == "\n":
                break
            out.append(char)
            i += 1
        return None, start

    depth = 0
    while i < n:
        char = text[i]
        if char == "\\" and i + 1 < n:
            out.append(text[i + 1])
            i += 2
            continue
        if char.isspace():
            # Whitespace ends the destination and begins an optional title.
            return "".join(out), i
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return "".join(out), i + 1
            depth -= 1
        out.append(char)
        i += 1
    return None, start


def extract_link_destinations(markdown: str) -> list[str]:
    """Every link destination in ``markdown``, code excluded, in source order."""
    text = _strip_code(markdown)
    destinations: list[str] = []
    i = 0
    n = len(text)
    while i < n - 1:
        if text[i] == "]" and text[i + 1] == "(":
            destination, resume = _read_destination(text, i + 2)
            if destination is None:
                i += 2
                continue
            if destination:
                destinations.append(destination)
            i = max(resume, i + 2)
            continue
        i += 1
    return destinations


def is_repo_relative(destination: str) -> bool:
    """True when the destination should resolve to a file in the plugin.

    Excludes URLs (any scheme), in-page anchors, absolute paths, and
    ``{...}`` targets substituted at runtime — none name a repo file.
    """
    if not destination or destination.startswith(("#", "/")):
        return False
    if "{" in destination or "}" in destination:
        return False
    scheme, separator, _ = destination.partition(":")
    if separator and scheme and scheme[0].isalpha():
        if all(char.isalnum() or char in "+.-" for char in scheme):
            return False
    return True


def check_entrypoint(skill_md: Path, repo_root: Path) -> dict:
    """Size and link findings for one SKILL.md.

    ``skill_md`` is absolute — reads must not depend on the caller's working
    directory — while the reported path is repo-relative so diagnostics stay
    copy-pasteable.
    """
    relative = skill_md.relative_to(repo_root).as_posix()
    try:
        body = skill_md.read_text(encoding="utf-8")
    except OSError as error:
        raise SystemExit(
            f"ERROR: could not scan {relative} — {error.strerror}.\n"
            f"  Check the file's permissions and encoding, then re-run."
        ) from error

    tokens = estimate_tokens(body)
    dangling = [
        destination
        for destination in extract_link_destinations(body)
        if is_repo_relative(destination)
        and not (skill_md.parent / destination.split("#", 1)[0]).exists()
    ]
    return {
        "path": relative,
        "chars": len(body),
        "tokens": tokens,
        "over_budget_by": max(0, tokens - TOKEN_BUDGET),
        "dangling_links": dangling,
    }


def run(repo_root: Path) -> tuple[dict, list[str]]:
    """Check every entrypoint. Returns the JSON report and diagnostic lines."""
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        raise SystemExit(
            f"ERROR: no skills/ directory under {repo_root}.\n"
            f"  Point this check at the plugin repo root."
        )

    entrypoints = sorted(skills_dir.glob("*/SKILL.md"))
    if not entrypoints:
        # A skills/ directory with no SKILL.md would otherwise pass vacuously,
        # reporting "0 entrypoints OK" on a broken layout.
        raise SystemExit(
            "ERROR: skills/ contains no */SKILL.md entrypoints.\n"
            "  Every skill directory needs a SKILL.md (see jbaruch/coding-policy:"
            " skill-authoring)."
        )

    results = [check_entrypoint(skill_md, repo_root) for skill_md in entrypoints]

    oversized = [r for r in results if r["over_budget_by"] > 0]
    dangling = [r for r in results if r["dangling_links"]]

    diagnostics: list[str] = []
    if oversized:
        diagnostics.append(
            f"ERROR: {len(oversized)} of {len(results)} skill entrypoints exceed "
            f"the {TOKEN_BUDGET}-token budget."
        )
        for r in oversized:
            diagnostics.append(
                f"  {r['path']}\t~{r['tokens']} tokens ({r['chars']} chars) — "
                f"{r['over_budget_by']} over budget"
            )
        diagnostics.append(
            "  A SKILL.md loads in full when its skill triggers, before any"
            " task-specific reference is selected. Move detailed procedure into"
            " skills/<name>/references/<topic>.md and leave an explicit,"
            " deterministic loading condition in the step that needs it (see"
            " jbaruch/coding-policy: skill-authoring -> Keep Skills Compact)."
        )
    if dangling:
        count = sum(len(r["dangling_links"]) for r in dangling)
        diagnostics.append(
            f"ERROR: {count} relative link(s) in skill entrypoints resolve to nothing."
        )
        for r in dangling:
            for destination in r["dangling_links"]:
                diagnostics.append(f"  {r['path']}\t{destination}")
        diagnostics.append(
            "  A dangling pointer fails silently at runtime: the agent follows"
            " it, finds nothing, and proceeds without the routing contract. Fix"
            " the path or restore the referenced file."
        )

    report = {
        "ok": not diagnostics,
        "token_budget": TOKEN_BUDGET,
        "chars_per_token": CHARS_PER_TOKEN,
        "checked": len(results),
        "oversized": [r["path"] for r in oversized],
        "dangling": [r["path"] for r in dangling],
        "entrypoints": results,
    }
    return report, diagnostics


def main(argv: list[str]) -> int:
    repo_root = (
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parent.parent
    )
    report, diagnostics = run(repo_root)

    print(json.dumps(report, indent=2, sort_keys=True))
    for line in diagnostics:
        print(line, file=sys.stderr)
    return 1 if diagnostics else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

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

   Existing in the working tree is not the test. A link resolving through
   ``..`` into ``tests/``, into the repo-root ``scripts/``, or out of the repo
   entirely points at a file that ships in no package, and so dangles at
   runtime exactly like a missing one. A target must resolve inside the repo,
   sit under a path the manifest declares, and survive ``.tesslignore``.

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
import subprocess
import sys
import tempfile
from pathlib import Path

MANIFEST = ".tessl-plugin/plugin.json"

# Tessl's recommended maximum tokens per skill entrypoint.
TOKEN_BUDGET = 5000
# Divisor for the chars-per-token estimate. See the module docstring on why
# this rounds against us rather than for us.
CHARS_PER_TOKEN = 4

FENCE_PREFIXES = ("```", "~~~")


class GateError(Exception):
    """An expected gate failure carrying an actionable, already-formatted message.

    A typed error rather than SystemExit so main() can honour the stdout
    contract: every run emits one JSON object, including the runs that fail
    before any entrypoint is checked. Raising SystemExit from inside the checks
    left stdout empty and made a broken repo indistinguishable from a crash.
    """


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
        lines.append(_strip_inline_code(line))
    return "\n".join(lines)


def _strip_inline_code(line: str) -> str:
    """Remove CommonMark code spans from one line.

    A span opens on a run of N backticks and closes on the next run of exactly
    N — not on the next single backtick. Pairing individual backticks splits
    ``[x](missing.md)`` at its first two characters and leaves the link in the
    text, so the gate rejects a valid skill for a link that is only sample
    output. It also lets a span carry a lone backtick, which is the whole point
    of the longer delimiter.

    An unterminated run is literal text, not an open span.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] != "`":
            out.append(line[i])
            i += 1
            continue

        run_start = i
        while i < n and line[i] == "`":
            i += 1
        run_length = i - run_start

        scan = i
        while scan < n:
            if line[scan] != "`":
                scan += 1
                continue
            close_start = scan
            while scan < n and line[scan] == "`":
                scan += 1
            if scan - close_start == run_length:
                i = scan  # Span consumed, contents dropped.
                break
        else:
            out.append(line[run_start:i])
    return "".join(out)


def _skip_whitespace(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _skip_title(text: str, i: int) -> int | None:
    """Consume an optional link title at ``i``.

    Returns the index just past it, or ``None`` when a title opens and never
    closes — which makes the whole link malformed.
    """
    if i >= len(text):
        return i
    opener = text[i]
    if opener not in "\"'(":
        return i
    closer = ")" if opener == "(" else opener
    i += 1
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            i += 2
            continue
        if char == closer:
            return i + 1
        i += 1
    return None


def _close_link(
    text: str, i: int, destination: list[str], start: int
) -> tuple[str | None, int]:
    """Require the optional title and the closing ``)`` after a destination.

    Without this, `[x](<missing.md>` and `[x](missing.md "title"` — neither of
    which is a link — yield a destination that then gets reported as a dangling
    reference, falsely blocking a publish.
    """
    i = _skip_whitespace(text, i)
    after_title = _skip_title(text, i)
    if after_title is None:
        return None, start
    i = _skip_whitespace(text, after_title)
    if i < len(text) and text[i] == ")":
        return "".join(destination), i + 1
    return None, start


def _read_destination(text: str, start: int) -> tuple[str | None, int]:
    """Parse a complete CommonMark inline link beginning at ``start``.

    ``start`` indexes the character just past ``](``. Returns the destination
    and the index to resume scanning from. A destination is either an
    angle-bracket form (``<path with spaces>``) or a bare run of non-whitespace
    with balanced parentheses; either may carry backslash escapes, and either
    may be followed by a title the caller does not want. Returns ``None`` when
    the construct is not a complete link — an unterminated destination, an
    unterminated title, or a missing closing ``)``. That is not a dangling
    target; it is not a link at all.
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
                return _close_link(text, i + 1, out, start)
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
            return _close_link(text, i, out, start)
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return "".join(out), i + 1
            depth -= 1
        out.append(char)
        i += 1
    return None, start


def _reference_definition(line: str) -> str | None:
    """The destination of a ``[label]: dest "title"`` definition, if this is one.

    CommonMark allows up to three leading spaces before the label.
    """
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3 or not stripped.startswith("["):
        return None
    close = stripped.find("]:", 1)
    if close == -1:
        return None

    rest = stripped[close + 2 :]
    i = _skip_whitespace(rest, 0)
    if i >= len(rest):
        return None

    if rest[i] == "<":
        end = rest.find(">", i + 1)
        return rest[i + 1 : end] if end != -1 else None

    out: list[str] = []
    while i < len(rest) and not rest[i].isspace():
        if rest[i] == "\\" and i + 1 < len(rest):
            out.append(rest[i + 1])
            i += 2
            continue
        out.append(rest[i])
        i += 1
    return "".join(out) or None


def extract_link_destinations(markdown: str) -> list[str]:
    """Every link destination in ``markdown``, code excluded, in source order.

    Covers both inline links (``[a](dest)``) and reference definitions
    (``[a]: dest``). A definition whose destination does not resolve is a
    dangling contract however it is referenced, so validating definitions
    closes the reference-link path without having to resolve usages.

    Usages are deliberately not matched against definitions: CommonMark's
    shortcut form makes any ``[text]`` a potential reference, and these skills
    use literal bracketed tags in prose (``[RECURRING]``, ``[NEW]``,
    ``[CONTEXTUAL]``). Treating those as undefined references would fail the
    gate on correct files.
    """
    text = _strip_code(markdown)
    destinations: list[str] = []

    for line in text.splitlines():
        definition = _reference_definition(line)
        if definition:
            destinations.append(definition)

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


def declared_content_roots(repo_root: Path) -> list[str]:
    """Repo-relative paths the plugin manifest declares as shipped content.

    A link target that exists in the working tree but sits outside these paths
    (``tests/``, repo-root ``scripts/``, anything above the repo) is absent from
    the published plugin, so following it at runtime finds nothing.
    """
    manifest_path = repo_root / MANIFEST
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as error:
        raise GateError(
            f"ERROR: could not read {MANIFEST} — {error.strerror}.\n"
            f"  Point this check at the plugin repo root."
        ) from error
    except UnicodeError as error:
        # UnicodeDecodeError is a ValueError, not an OSError, so it would
        # otherwise escape both handlers as a traceback.
        raise GateError(
            f"ERROR: {MANIFEST} is not valid UTF-8 — {error}.\n"
            f"  Re-save the manifest as UTF-8, then re-run."
        ) from error

    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GateError(
            f"ERROR: {MANIFEST} is not valid JSON — {error.msg} "
            f"at line {error.lineno} col {error.colno}.\n"
            f"  Fix the syntax; this check cannot tell what the plugin ships"
            f" until the manifest parses."
        ) from error

    roots: list[str] = []
    for field in ("skills", "rules"):
        value = manifest.get(field)
        if isinstance(value, str):
            roots.append(value.rstrip("/"))
        elif isinstance(value, list):
            roots.extend(item.rstrip("/") for item in value if isinstance(item, str))
    if not roots:
        raise GateError(
            f"ERROR: {MANIFEST} declares neither `skills` nor `rules`.\n"
            f"  Without declared content this check cannot tell what ships."
        )
    return roots


def tesslignore_excluded(repo_root: Path, relative_paths: list[str]) -> set[str]:
    """Which of ``relative_paths`` .tesslignore strips from the package.

    Matching runs against a throwaway empty git repo with core.excludesFile
    pointed at .tesslignore, so only .tesslignore patterns are consulted — the
    same technique (and therefore the same semantics) as
    scripts/check-package-contents.sh.
    """
    ignore_file = repo_root / ".tesslignore"
    if not ignore_file.is_file() or not relative_paths:
        return set()

    with tempfile.TemporaryDirectory() as scratch:
        # Exit codes are inspected rather than check=True: a CalledProcessError
        # escapes main()'s GateError handler as a traceback with empty stdout,
        # which is the contract violation this whole path exists to avoid.
        try:
            init = subprocess.run(
                ["git", "init", "-q", scratch], capture_output=True, text=True
            )
        except OSError as error:
            raise GateError(
                f"ERROR: could not run git to test .tesslignore patterns — {error}.\n"
                f"  Install git, or make it reachable on PATH, then re-run."
            ) from error
        if init.returncode != 0:
            raise GateError(
                f"ERROR: git init failed (exit {init.returncode}) while preparing"
                f" the scratch repo used to test .tesslignore patterns.\n"
                f"  {init.stderr.strip()}"
            )
        result = subprocess.run(
            [
                "git",
                "-C",
                scratch,
                "-c",
                f"core.excludesFile={ignore_file}",
                "check-ignore",
                "--no-index",
                "--stdin",
            ],
            input="\n".join(relative_paths),
            capture_output=True,
            text=True,
        )
    # 0 = something matched, 1 = nothing matched. Anything else is a real
    # failure, and treating it as "nothing excluded" would pass vacuously.
    if result.returncode not in (0, 1):
        raise GateError(
            f"ERROR: git check-ignore failed (exit {result.returncode}) while"
            f" testing .tesslignore patterns.\n"
            f"  {result.stderr.strip()}"
        )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def classify_link(
    destination: str, skill_dir: Path, repo_root: Path, roots: list[str]
) -> tuple[str, str] | None:
    """Return ``(reason, resolved-path)`` when a link will not resolve at runtime.

    Existence alone is not enough: the target must also be plugin content, or
    it ships nowhere and the agent following it at runtime finds nothing.
    """
    target = (skill_dir / destination.split("#", 1)[0]).resolve()
    try:
        relative = target.relative_to(repo_root).as_posix()
    except ValueError:
        return "escapes the repository", str(target)
    if not target.exists():
        return "missing", relative
    if not any(relative == root or relative.startswith(f"{root}/") for root in roots):
        return "not declared plugin content", relative
    return None


def check_entrypoint(
    skill_md: Path, repo_root: Path, roots: list[str]
) -> tuple[dict, list[tuple[str, str]]]:
    """Size and link findings for one SKILL.md.

    ``skill_md`` is absolute — reads must not depend on the caller's working
    directory — while the reported path is repo-relative so diagnostics stay
    copy-pasteable. Returns the record plus every in-package link target, which
    the caller batch-tests against .tesslignore.
    """
    relative = skill_md.relative_to(repo_root).as_posix()
    try:
        body = skill_md.read_text(encoding="utf-8")
    except OSError as error:
        raise GateError(
            f"ERROR: could not scan {relative} — {error.strerror}.\n"
            f"  Fix the file's permissions, then re-run."
        ) from error
    except UnicodeError as error:
        # UnicodeDecodeError is a ValueError, not an OSError — the handler
        # above never sees it.
        raise GateError(
            f"ERROR: could not scan {relative} — not valid UTF-8 ({error}).\n"
            f"  Re-save the entrypoint as UTF-8, then re-run."
        ) from error

    unresolved: list[dict] = []
    shipped: list[tuple[str, str]] = []
    for destination in extract_link_destinations(body):
        if not is_repo_relative(destination):
            continue
        finding = classify_link(destination, skill_md.parent, repo_root, roots)
        if finding is None:
            target = (skill_md.parent / destination.split("#", 1)[0]).resolve()
            shipped.append((destination, target.relative_to(repo_root).as_posix()))
            continue
        reason, resolved = finding
        unresolved.append(
            {"destination": destination, "reason": reason, "resolved": resolved}
        )

    tokens = estimate_tokens(body)
    return (
        {
            "path": relative,
            "chars": len(body),
            "tokens": tokens,
            "over_budget_by": max(0, tokens - TOKEN_BUDGET),
            "dangling_links": unresolved,
        },
        shipped,
    )


def run(repo_root: Path) -> tuple[dict, list[str]]:
    """Check every entrypoint. Returns the JSON report and diagnostic lines."""
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        raise GateError(
            f"ERROR: no skills/ directory under {repo_root}.\n"
            f"  Point this check at the plugin repo root."
        )

    entrypoints = sorted(skills_dir.glob("*/SKILL.md"))
    if not entrypoints:
        # A skills/ directory with no SKILL.md would otherwise pass vacuously,
        # reporting "0 entrypoints OK" on a broken layout.
        raise GateError(
            "ERROR: skills/ contains no */SKILL.md entrypoints.\n"
            "  Every skill directory needs a SKILL.md (see jbaruch/coding-policy:"
            " skill-authoring)."
        )

    roots = declared_content_roots(repo_root)

    results: list[dict] = []
    shipped_by_entrypoint: list[list[tuple[str, str]]] = []
    for skill_md in entrypoints:
        record, shipped = check_entrypoint(skill_md, repo_root, roots)
        results.append(record)
        shipped_by_entrypoint.append(shipped)

    # One batch call: a target can be declared plugin content and still be
    # stripped from the package by a .tesslignore pattern, which leaves the
    # same runtime-dangling pointer as a missing file.
    candidates = sorted(
        {relative for shipped in shipped_by_entrypoint for _, relative in shipped}
    )
    excluded = tesslignore_excluded(repo_root, candidates)
    for record, shipped in zip(results, shipped_by_entrypoint):
        for destination, relative in shipped:
            if relative in excluded:
                record["dangling_links"].append(
                    {
                        "destination": destination,
                        "reason": "excluded from the package by .tesslignore",
                        "resolved": relative,
                    }
                )

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
            f"ERROR: {count} relative link(s) in skill entrypoints will not"
            f" resolve in the published plugin."
        )
        for r in dangling:
            for link in r["dangling_links"]:
                diagnostics.append(
                    f"  {r['path']}\t{link['destination']}\t"
                    f"-> {link['resolved']} ({link['reason']})"
                )
        diagnostics.append(
            "  Format above: <entrypoint>\t<link target>\t-> <resolved> (<reason>)"
        )
        diagnostics.append(
            "  A pointer that resolves to nothing fails silently at runtime: the"
            " agent follows it, finds nothing, and proceeds without the routing"
            " contract. Existing in the working tree is not enough — the target"
            " must ship, so it has to sit under a path the manifest declares and"
            " survive .tesslignore. Fix the path, restore the file, or move it"
            " into the skill's own references/."
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


def _print_failure(message: str) -> None:
    """Emit the failure shape of the stdout contract."""
    print(
        json.dumps(
            {
                "ok": False,
                "error": message,
                "token_budget": TOKEN_BUDGET,
                "chars_per_token": CHARS_PER_TOKEN,
                "checked": 0,
                "oversized": [],
                "dangling": [],
                "entrypoints": [],
            },
            indent=2,
            sort_keys=True,
        )
    )


def main(argv: list[str]) -> int:
    repo_root = (
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parent.parent
    )
    try:
        report, diagnostics = run(repo_root)
    except GateError as error:
        # Every run emits one JSON object, including the ones that fail before
        # any entrypoint is checked — a consumer reading stdout must never have
        # to tell "gate said no" apart from "gate crashed" by parsing stderr.
        _print_failure(str(error).splitlines()[0])
        print(error, file=sys.stderr)
        return 1
    # outer-boundary-process-contract: stdout is this gate's machine-readable
    # result, and its callers (pre-publish-checks.sh, the tests) read an
    # unparseable stdout as the gate having produced no verdict at all. An
    # unexpected exception propagating here would print a traceback and no
    # JSON, so the catch emits the same failure object plus an actionable
    # stderr line naming the bug. Exception, not BaseException — KeyboardInterrupt
    # and SystemExit must still propagate so the process stays killable.
    except Exception as error:  # noqa: BLE001
        _print_failure(f"unexpected gate failure: {type(error).__name__}")
        print(
            f"ERROR: {Path(__file__).name} failed unexpectedly — "
            f"{type(error).__name__}: {error}\n"
            f"  This is a bug in the gate, not in the plugin. Re-run with a"
            f"  traceback (`python -X dev {Path(__file__).name}`) and report it.",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(report, indent=2, sort_keys=True))
    for line in diagnostics:
        print(line, file=sys.stderr)
    return 1 if diagnostics else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

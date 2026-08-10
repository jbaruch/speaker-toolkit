#!/usr/bin/env python3
"""Gate: every file the plugin manifest declares as content must survive packaging.

The failure this catches: .tesslignore uses gitignore pattern semantics, so an
unanchored directory pattern ("scripts/") matches a directory of that name at
ANY depth — including skills/<name>/scripts/. A pattern written for the
repo-side helper directory silently strips every skill's runtime scripts from
the package, and ``tessl plugin publish`` still reports success. That shipped:
an unanchored "scripts/" stripped all 59 skills/*/scripts/ files from 0.18.43
through 0.18.61 while publish reported success.

Matching runs against a throwaway empty git repo with core.excludesFile pointed
at .tesslignore, so only .tesslignore patterns are consulted — the repo's own
.gitignore can neither mask a match nor invent one.

A repo with no .tesslignore passes without reading the manifest's contents:
nothing can be excluded, so the question this gate asks is already answered.

Usage: check_package_contents.py [<repo-root>]   (default: this repo)
Stdout: one JSON object describing what was declared and what would be stripped.
Stderr: actionable diagnostics for each violation.
Exit 0 when every declared content file packs, 1 otherwise.

Wired into CI by .github/workflows/tests.yml, and into the publish run by
scripts/pre-publish-checks.sh.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

MANIFEST = ".tessl-plugin/plugin.json"
IGNORE_FILE = ".tesslignore"

# Manifest fields that declare shipped plugin content.
CONTENT_FIELDS = ("skills", "rules")


class GateError(Exception):
    """An expected gate failure carrying an actionable, already-formatted message.

    A typed error rather than SystemExit so main() can honour the stdout
    contract: every run emits one JSON object, including the runs that fail
    before any content is checked.
    """


def declared_content_entries(repo_root: Path) -> list[str]:
    """Repo-relative paths the manifest declares as shipped plugin content.

    Each field is a directory-path string or an array of such strings. Anything
    else is a manifest shape error rather than a missing path: a non-string
    coerced with str() would be reported downstream as a directory that does
    not exist, sending the reader after a path that was never declared.
    """
    manifest_path = repo_root / MANIFEST
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as error:
        raise GateError(
            f"ERROR: {MANIFEST} could not be read — {error.strerror}.\n"
            f"  Check file permissions / disk state, then re-run."
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
            f"  Fix the JSON syntax error and re-run. The package-contents"
            f" check can't tell what the plugin ships until the manifest parses."
        ) from error

    if not isinstance(manifest, dict):
        raise GateError(
            f"ERROR: {MANIFEST} has the wrong shape — expected a top-level JSON"
            f" object, got {type(manifest).__name__}.\n"
            f'  The manifest must be a JSON object ("{{...}}").'
        )

    entries: list[str] = []
    for field in CONTENT_FIELDS:
        value = manifest.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            entries.append(value.rstrip("/"))
            continue
        if not isinstance(value, list):
            raise GateError(
                f"ERROR: {MANIFEST} has the wrong shape — field {field!r} must"
                f" be a string or array, got {type(value).__name__}.\n"
                f"  `skills` and `rules` must each be a path string or an array"
                f" of paths (see jbaruch/coding-policy: skill-authoring ->"
                f" plugin.json Manifest Reference)."
            )
        for position, item in enumerate(value):
            if not isinstance(item, str):
                raise GateError(
                    f"ERROR: {MANIFEST} has the wrong shape — manifest field"
                    f" {field!r}[{position}] must be a string, got"
                    f" {type(item).__name__}.\n"
                    f"  `skills` and `rules` must each be a path string or an"
                    f" array of paths (see jbaruch/coding-policy:"
                    f" skill-authoring -> plugin.json Manifest Reference)."
                )
            entries.append(item.rstrip("/"))

    if not entries:
        raise GateError(
            f"ERROR: {MANIFEST} declares no plugin content.\n"
            f"  Add the plugin's `skills` and/or `rules` entries. Without them"
            f" the published package is empty and this gate has nothing to"
            f" verify."
        )
    return entries


def _run_git(
    arguments: list[str], *, purpose: str, **kwargs
) -> subprocess.CompletedProcess[str]:
    """Run one git command, turning an unrunnable git into an actionable error."""
    try:
        return subprocess.run(  # noqa: S603
            ["git", *arguments], capture_output=True, text=True, **kwargs
        )
    except OSError as error:
        raise GateError(
            f"ERROR: could not run git to {purpose} — {error}.\n"
            f"  Install git, or make it reachable on PATH, then re-run."
        ) from error


def tracked_content(repo_root: Path, entries: list[str]) -> tuple[list[str], list[str]]:
    """Tracked files under each declared entry, plus the entries that have none.

    A manifest may declare both a directory and a path beneath it (``skills/``
    alongside ``skills/release``). Every file under the narrower path is then
    listed twice, which would inflate the totals and repeat each violation, so
    the file list is de-duplicated. The per-entry emptiness check runs first,
    on the unfiltered listing it needs.
    """
    tracked: set[str] = set()
    empty: list[str] = []
    for entry in entries:
        result = _run_git(
            ["-C", str(repo_root), "ls-files", "--", entry],
            purpose=f"list tracked files under {entry!r}",
        )
        if result.returncode != 0:
            raise GateError(
                f"ERROR: git ls-files failed (exit {result.returncode}) while"
                f" listing tracked files under {entry!r}.\n"
                f"  {result.stderr.strip()}"
            )
        paths = [line for line in result.stdout.splitlines() if line]
        if not paths:
            empty.append(entry)
            continue
        tracked.update(paths)
    return sorted(tracked), empty


def tesslignore_exclusions(
    repo_root: Path, paths: list[str]
) -> list[dict[str, object]]:
    """Which of ``paths`` .tesslignore strips, with the pattern that strips it.

    Matching runs against a throwaway empty git repo with core.excludesFile
    pointed at .tesslignore, so only .tesslignore patterns are consulted — the
    same technique (and therefore the same semantics) as
    scripts/check_skill_entrypoints.py.
    """
    if not paths:
        return []

    with tempfile.TemporaryDirectory() as scratch:
        init = _run_git(["init", "-q", scratch], purpose="test .tesslignore patterns")
        if init.returncode != 0:
            raise GateError(
                f"ERROR: git init failed (exit {init.returncode}) while preparing"
                f" the scratch repo used to test {IGNORE_FILE} patterns.\n"
                f"  {init.stderr.strip()}"
            )
        result = _run_git(
            [
                "-C",
                scratch,
                "-c",
                f"core.excludesFile={repo_root / IGNORE_FILE}",
                "check-ignore",
                "--no-index",
                "-v",
                "--stdin",
            ],
            purpose=f"test {IGNORE_FILE} patterns",
            input="\n".join(paths),
        )

    # 0 = something matched, 1 = nothing matched. Anything else is a real
    # failure, and treating it as "nothing excluded" would pass vacuously.
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise GateError(
            f"ERROR: git check-ignore failed (exit {result.returncode}) while"
            f" testing {IGNORE_FILE} patterns.\n"
            f"  {result.stderr.strip()}"
        )

    exclusions: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        # `-v` output is "<source>:<line>:<pattern>\t<pathname>".
        source, _, path = line.partition("\t")
        fields = source.split(":", 2)
        exclusions.append(
            {
                "path": path,
                "pattern": fields[2] if len(fields) > 2 else source,
                "source": fields[0] if fields else IGNORE_FILE,
                "line": int(fields[1])
                if len(fields) > 1 and fields[1].isdigit()
                else 0,
                "raw": line,
            }
        )
    return exclusions


def run(repo_root: Path) -> tuple[dict[str, object], list[str]]:
    """Check one plugin repo, returning its JSON report and stderr diagnostics."""
    if not (repo_root / MANIFEST).is_file():
        raise GateError(
            f"ERROR: plugin manifest {MANIFEST} not found under {repo_root}.\n"
            f"  Point this check at the plugin repo root, or restore the manifest."
        )

    if not (repo_root / IGNORE_FILE).is_file():
        report: dict[str, object] = {
            "ok": True,
            "ignore_file_present": False,
            "declared": [],
            "checked": 0,
            "missing": [],
            "excluded": [],
        }
        return report, []

    entries = declared_content_entries(repo_root)
    tracked, missing = tracked_content(repo_root, entries)

    diagnostics: list[str] = []
    for entry in missing:
        diagnostics.append(
            f'ERROR: {MANIFEST} declares "{entry}" but no tracked files live there.'
        )
    if missing:
        diagnostics.append(
            "  Restore the path, or drop it from the manifest (see"
            " jbaruch/coding-policy: context-artifacts -> Surface Sync)."
        )
        report = {
            "ok": False,
            "ignore_file_present": True,
            "declared": entries,
            "checked": len(tracked),
            "missing": missing,
            "excluded": [],
        }
        return report, diagnostics

    excluded = tesslignore_exclusions(repo_root, tracked)
    if excluded:
        diagnostics.append(
            f"ERROR: {IGNORE_FILE} excludes {len(excluded)} of {len(tracked)}"
            f" declared plugin content files."
        )
        diagnostics.append(
            f"  These are declared in {MANIFEST} but would NOT ship in the"
            f" published package:"
        )
        diagnostics.extend(f"  {item['raw']}" for item in excluded)
        diagnostics.append(
            "  Format above: <ignore-file>:<line>:<pattern>\t<excluded file>"
        )
        diagnostics.append(
            f"  Cause: {IGNORE_FILE} uses gitignore pattern semantics. A pattern"
            f' with no leading slash matches at every depth, so "foo/" strips a'
            f" repo-root foo/ AND skills/<name>/foo/."
        )
        diagnostics.append(
            "  Fix: anchor the flagged pattern to the repo root with a leading"
            ' slash ("scripts/" -> "/scripts/"), or narrow it so it stops'
            " matching plugin content. Re-run this check to confirm."
        )

    report = {
        "ok": not excluded,
        "ignore_file_present": True,
        "declared": entries,
        "checked": len(tracked),
        "missing": [],
        "excluded": excluded,
    }
    return report, diagnostics


def _print_failure(message: str) -> None:
    """Emit the failure shape of the stdout contract."""
    print(
        json.dumps(
            {
                "ok": False,
                "error": message,
                "ignore_file_present": False,
                "declared": [],
                "checked": 0,
                "missing": [],
                "excluded": [],
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
        # any content is checked — a consumer reading stdout must never have to
        # tell "gate said no" apart from "gate crashed" by parsing stderr.
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
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

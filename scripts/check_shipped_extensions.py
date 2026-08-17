#!/usr/bin/env python3
"""Gate: every shipped file must reach consumers, whatever its extension.

The failure this catches: `tessl install` materializes only a fixed set of
extensions and silently drops the rest. Nothing warns — `tessl plugin pack`
includes the file, `tessl plugin publish` reports success, `tessl install
--verbose` logs not one word, and the file simply is not on the consumer's
disk. It ships green and breaks on arrival.

That shipped twice. The deck-ops layer lost `RunDeckOps.bas` and eight
`*.applescript` drivers (issue #85), fixed per-file with committed `.txt`
mirrors. Then `_dimensions.yaml` arrived in a different directory with a third
extension and was dropped the same way, so `audit-pattern-catalog.py` exited 1
on every clean install from 0.20.57 on — a hard stop in vault-ingress Step 1,
which meant no talk could be processed on the released plugin (issue #316).

The device is the mirror: a byte-identical `<name>.txt` beside the real file.
`.txt` is on the allowlist, so the mirror survives install and the reader falls
back to it. This gate is the repo-wide authority that every non-shipping file
has one and that it has not drifted — the check the deck-driver fix only ever
did for its own two extensions in its own one directory.

Scope is the manifest's declared content (skills, rules), read through
`git ls-files`. An untracked file is not a shipping contract, and the pack
strips OS metadata via .tesslignore.

Usage: check_shipped_extensions.py [<repo-root>]   (default: this repo)
Stdout: one JSON object listing what was checked and every mirror problem.
Stderr: actionable diagnostics naming the command that fixes each one.
Exit 0 when every non-shipping file has a current mirror, 1 otherwise.

Wired into CI by .github/workflows/tests.yml, and into the publish run by
scripts/pre-publish-checks.sh.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from check_package_contents import (
    GateError,
    _run_git,
    declared_content_entries,
    tracked_content,
)

# What `tessl install` materializes. Every other extension is dropped in
# silence, so a file carrying one needs a mirror to reach consumers. Verified
# empirically against an installed plugin: pack and install were diffed, and
# .applescript, .bas and .yaml were absent from the install while .md, .py,
# .sh, .txt and .json came through whole.
SHIPPED_SUFFIXES = frozenset({".md", ".py", ".sh", ".txt", ".json"})

MIRROR_SUFFIX = ".txt"

# A mirror is a generated file committed only because the platform cannot
# materialize its source extension, so file-hygiene's generated-artifact
# exception requires it be marked in .gitattributes. Checked per file rather
# than trusted to a glob: a directory-scoped pattern is what left
# _dimensions.yaml.txt unmarked while the deck mirrors beside it were covered.
GENERATED_ATTRS = {"linguist-generated": "true", "merge": "ours"}


def mirror_of(path: str) -> str:
    """The mirror path that carries ``path`` past the install filter."""
    return path + MIRROR_SUFFIX


def source_of(mirror: str) -> str:
    """The real file a mirror stands in for."""
    return mirror[: -len(MIRROR_SUFFIX)]


def _is_dropped(name: str) -> bool:
    """Whether install drops a file with this name, judged by its extension.

    An extensionless name is not treated as dropped. The filter is an extension
    allowlist and a bare `LICENSE` carries no extension to match, so demanding a
    mirror for one would invent a rule the evidence does not support. Both
    predicates below read this, so "needs a mirror" and "is a mirror" can never
    disagree about the same name — the disagreement that made `notes.txt` look
    like a mirror of an extensionless `notes`.
    """
    suffix = Path(name).suffix
    return bool(suffix) and suffix not in SHIPPED_SUFFIXES


def is_mirror(path: str) -> bool:
    """Whether ``path`` is a mirror rather than a plain shipped `.txt`.

    A `.txt` is a mirror only when removing that suffix leaves a name whose own
    extension would be dropped at install. `foo.applescript.txt` mirrors
    `foo.applescript`; `release-notes.txt` mirrors nothing and is content.
    """
    return path.endswith(MIRROR_SUFFIX) and _is_dropped(source_of(path))


def needs_mirror(path: str) -> bool:
    """Whether ``path`` is dropped at install and so must carry a mirror."""
    return _is_dropped(path)


def _read(repo_root: Path, relative: str) -> bytes:
    """Read a tracked file, turning an unreadable one into an actionable error.

    `git ls-files` lists what the index holds, which is not a promise about the
    working tree: a file can be deleted or made unreadable between the listing
    and the compare. Letting that OSError escape would abandon the stdout
    contract mid-run — a traceback and no JSON, which reads to a caller as the
    gate crashing rather than the gate refusing.
    """
    try:
        return (repo_root / relative).read_bytes()
    except OSError as error:
        raise GateError(
            f"ERROR: could not read tracked file {relative} to compare it with"
            f" its mirror — {error}.\n"
            f"  Restore the file or fix its permissions, then re-run."
        ) from error


def unmarked_mirrors(repo_root: Path, mirrors: list[str]) -> list[str]:
    """Mirrors missing either generated-file attribute, sorted.

    Asks git rather than parsing .gitattributes, so precedence, negation and
    later-pattern-wins are resolved the way git itself resolves them.
    """
    if not mirrors:
        return []
    attributes = sorted(GENERATED_ATTRS)
    result = _run_git(
        ["-C", str(repo_root), "check-attr", *attributes, "--", *mirrors],
        purpose="read the generated-file attributes of the .txt mirrors",
    )
    if result.returncode != 0:
        raise GateError(
            f"ERROR: git check-attr failed (exit {result.returncode}) while"
            f" reading mirror attributes.\n  {result.stderr.strip()}"
        )

    # Each line is "<path>: <attribute>: <value>"; a path unmatched by any
    # pattern reports "unspecified".
    seen: dict[str, set[str]] = {path: set() for path in mirrors}
    for line in result.stdout.splitlines():
        path, _, rest = line.partition(": ")
        attribute, _, value = rest.partition(": ")
        if path in seen and GENERATED_ATTRS.get(attribute) == value:
            seen[path].add(attribute)
    return sorted(path for path in mirrors if seen[path] != set(attributes))


def find_problems(repo_root: Path, tracked: list[str]) -> list[dict[str, str]]:
    """Mirror problems among the tracked content files, in report order.

    Four shapes, each a distinct way a consumer ends up reading something the
    repo does not say: no mirror at all (the file never arrives), a mirror that
    has drifted from its source (the consumer reads a stale copy), a mirror
    whose source is gone (the consumer reads a file the repo deleted), and a
    mirror not declared generated (its diff and its merges lie about which file
    is the source of truth).
    """
    present = set(tracked)
    problems: list[dict[str, str]] = []

    for path in tracked:
        if is_mirror(path) or not needs_mirror(path):
            continue
        mirror = mirror_of(path)
        if mirror not in present:
            problems.append({"kind": "missing", "path": path, "mirror": mirror})
            continue
        if _read(repo_root, mirror) != _read(repo_root, path):
            problems.append({"kind": "stale", "path": path, "mirror": mirror})

    mirrors = [path for path in tracked if is_mirror(path)]
    for path in mirrors:
        if source_of(path) not in present:
            problems.append({"kind": "orphan", "path": source_of(path), "mirror": path})

    for path in unmarked_mirrors(repo_root, mirrors):
        problems.append({"kind": "unmarked", "path": source_of(path), "mirror": path})

    return problems


def _diagnose(problems: list[dict[str, str]]) -> list[str]:
    """Actionable stderr lines: what is wrong, and the command that fixes it."""
    diagnostics = [
        f"ERROR: {len(problems)} file(s) would not reach consumers intact.",
        "  `tessl install` ships only "
        + " ".join(sorted(SHIPPED_SUFFIXES))
        + " and drops every other extension without warning.",
    ]
    for problem in problems:
        path, mirror = problem["path"], problem["mirror"]
        if problem["kind"] == "missing":
            diagnostics.append(
                f"  missing mirror: {path} is dropped at install and has no"
                f" {mirror} — run: cp {path} {mirror}"
            )
        elif problem["kind"] == "stale":
            diagnostics.append(
                f"  stale mirror: {mirror} differs from {path}, so consumers"
                f" read the old content — run: cp {path} {mirror}"
            )
        elif problem["kind"] == "unmarked":
            attributes = " ".join(
                f"{k}={v}" for k, v in sorted(GENERATED_ATTRS.items())
            )
            diagnostics.append(
                f"  unmarked mirror: {mirror} is a generated file — add a"
                f" .gitattributes pattern matching it with: {attributes}"
            )
        else:
            diagnostics.append(
                f"  orphan mirror: {mirror} has no source {path} — delete the"
                f" mirror, or restore the file it mirrors"
            )
    diagnostics.append(
        "  Then teach the reader to fall back to the mirror when the real file"
        " is absent, the way catalog_dimension_registry.registry_path does."
    )
    return diagnostics


def run(repo_root: Path) -> tuple[dict[str, object], list[str]]:
    """Check one plugin repo, returning its JSON report and stderr diagnostics."""
    entries = declared_content_entries(repo_root)
    tracked, _ = tracked_content(repo_root, entries)

    problems = find_problems(repo_root, tracked)
    mirrored = sorted(path for path in tracked if needs_mirror(path))
    report: dict[str, object] = {
        "ok": not problems,
        "shipped_suffixes": sorted(SHIPPED_SUFFIXES),
        "checked": len(tracked),
        "needing_mirror": mirrored,
        "problems": problems,
    }
    return report, (_diagnose(problems) if problems else [])


def _print_failure(message: str) -> None:
    """Emit the failure shape of the stdout contract."""
    print(
        json.dumps(
            {
                "ok": False,
                "error": message,
                "shipped_suffixes": sorted(SHIPPED_SUFFIXES),
                "checked": 0,
                "needing_mirror": [],
                "problems": [],
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
        # any file is checked — a consumer reading stdout must never have to
        # tell "gate said no" apart from "gate crashed" by parsing stderr.
        _print_failure(str(error))
        print(str(error), file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    for line in diagnostics:
        print(line, file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

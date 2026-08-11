#!/usr/bin/env python3
"""Deploy-time check that no conflict marker is committed to a tracked file.

A diff3 base marker (`||||||| <sha>`) survived a merge resolution and shipped
in `CHANGELOG.md`, which is published in the plugin package. Nothing caught it:
`ruff` does not read Markdown, and `git diff --check` only inspects the working
diff, so a marker that is already committed passes silently. The resolution had
stripped the three familiar markers; `merge.conflictStyle = diff3` adds a
fourth, and the leftover line does not start with `#`, so a heading-level review
of the diff never saw it.

Every tracked text file is scanned on every run — one unreadable file must not
hide a marker in the next one. Binary files are counted and skipped: a marker is
a line of text, and the repo's binary artifacts are eval fixtures.

Usage: check_conflict_markers.py [<repo-root>]   (default: this repo)
Stdout: one JSON object naming the scanned counts and every violation.
Stderr: one actionable diagnostic per violation.
Exit 0 when no tracked file carries a marker, 1 otherwise.

Wired into CI by .github/workflows/tests.yml, and into the publish run by
scripts/pre-publish-checks.sh.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# git's own default marker length, used for any path whose gitattributes do not
# set one.
DEFAULT_MARKER_SIZE = 7

# The shortest length git accepts, so a nonsense attribute value cannot shrink
# the matcher into flagging ordinary prose.
MINIMUM_MARKER_SIZE = 1


# The three markers no legitimate content produces, at the length git would
# write for that path. Matching the exact configured length rather than "seven
# or more" keeps a here-doc delimiter and a long rule legal: those run to
# arbitrary lengths, a marker does not. The trailing `( |$)` covers the rest —
# a real marker is bare or followed by a space and a label.
def unambiguous_marker_pattern(size: int) -> re.Pattern[str]:
    """Start, base, and end markers, which nothing else in a text file writes."""
    return re.compile(rf"^(<{{{size}}}|\|{{{size}}}|>{{{size}}})( |$)")


# The separator is the one ambiguous marker: a Markdown setext heading rule of
# exactly the marker length is identical to it. Flagging it outright would fail
# the build on legitimate prose, so it counts only inside a conflict a start
# marker already opened — where it cannot be a heading rule.
def separator_pattern(size: int) -> re.Pattern[str]:
    """The `=======` separator, meaningful only within an open conflict."""
    return re.compile(rf"^(={{{size}}})( |$)")


def start_pattern(size: int) -> re.Pattern[str]:
    """The `<<<<<<<` line that opens a conflict region."""
    return re.compile(rf"^(<{{{size}}})( |$)")


def end_pattern(size: int) -> re.Pattern[str]:
    """The `>>>>>>>` line that closes a conflict region."""
    return re.compile(rf"^(>{{{size}}})( |$)")


# A NUL byte in the first block means the file is not line-oriented text. Read
# far enough in that a long text preamble cannot mask it.
BINARY_SNIFF_BYTES = 8192


class MarkerScanError(Exception):
    """The scan could not run, with an actionable reason."""


def tracked_files(repo_root: Path) -> list[Path]:
    """Every path git tracks, so an untracked scratch file is never scanned."""
    try:
        listing = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as error:
        raise MarkerScanError(
            "ERROR: git is not on PATH, so the tracked-file list cannot be read.\n"
            "  Install git, or run this check from a checkout that has it."
        ) from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode("utf-8", "replace").strip()
        raise MarkerScanError(
            f"ERROR: `git ls-files` failed in {repo_root}.\n"
            f"  {detail}\n"
            "  Run this check from inside a git checkout."
        ) from error
    names = listing.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [repo_root / name for name in names if name]


def marker_sizes(repo_root: Path, paths: list[Path]) -> dict[str, int]:
    """Each path's configured marker length, from its own gitattributes.

    git writes markers at the path's `conflict-marker-size`, so a repository
    that raises it for a file whose content is full of `=======` lines still
    gets a real conflict marker — just a longer one. Assuming seven would let
    that marker through the gate it exists to fail.
    """
    if not paths:
        return {}
    names = [str(path.relative_to(repo_root)) for path in paths]
    try:
        query = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "check-attr",
                "-z",
                "--stdin",
                "conflict-marker-size",
            ],
            input="\0".join(names).encode("utf-8", "surrogateescape"),
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode("utf-8", "replace").strip()
        raise MarkerScanError(
            f"ERROR: `git check-attr conflict-marker-size` failed in {repo_root}.\n"
            f"  {detail}\n"
            "  Fix the .gitattributes it could not read, then rerun."
        ) from error
    # -z emits a flat NUL-separated <path> <attr> <value> stream.
    fields = query.stdout.decode("utf-8", "surrogateescape").split("\0")
    sizes: dict[str, int] = {}
    for index in range(0, len(fields) - 2, 3):
        name, _attribute, value = fields[index], fields[index + 1], fields[index + 2]
        if not value.isdigit():
            # `unspecified`, `unset`, or a malformed value: git falls back to
            # its own default, and so does this gate.
            continue
        size = int(value)
        if size >= MINIMUM_MARKER_SIZE:
            sizes[name] = size
    return sizes


def staged_blob(repo_root: Path, relative: str) -> bytes:
    """The index copy of a tracked path whose working-tree file is gone."""
    try:
        blob = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "blob", f":{relative}"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode("utf-8", "replace").strip()
        raise MarkerScanError(
            f"ERROR: tracked file {relative} is absent from the working tree and "
            f"its staged copy could not be read.\n"
            f"  {detail}\n"
            "  Restore the file or stage its deletion, then rerun."
        ) from error
    return blob.stdout


@dataclass(frozen=True)
class MarkerMatchers:
    """The four matchers for one marker length, compiled once."""

    unambiguous: re.Pattern[str]
    separator: re.Pattern[str]
    start: re.Pattern[str]
    end: re.Pattern[str]

    @classmethod
    def of_size(cls, size: int) -> "MarkerMatchers":
        return cls(
            unambiguous=unambiguous_marker_pattern(size),
            separator=separator_pattern(size),
            start=start_pattern(size),
            end=end_pattern(size),
        )


def violations_in(
    raw: bytes,
    relative: str,
    matchers: MarkerMatchers,
) -> list[dict[str, object]]:
    """Every marker line in one file's bytes, at that file's marker length.

    The separator is tracked rather than matched outright: `=======` is also a
    Markdown setext heading rule at that length, so it counts only between a
    start marker and its end marker, where a heading rule cannot be.
    """
    text = raw.decode("utf-8", "replace")
    found = []
    inside_conflict = False
    for number, line in enumerate(text.splitlines(), start=1):
        match = matchers.unambiguous.match(line)
        if match is None and inside_conflict:
            match = matchers.separator.match(line)
        if matchers.start.match(line):
            inside_conflict = True
        elif matchers.end.match(line):
            inside_conflict = False
        if match:
            found.append({"path": relative, "line": number, "marker": match.group(1)})
    return found


def scan(repo_root: Path) -> dict[str, object]:
    """Scan every tracked text file and report what was found."""
    scanned = 0
    binary = 0
    violations: list[dict[str, object]] = []
    tracked = tracked_files(repo_root)
    sizes = marker_sizes(repo_root, tracked)
    # One compiled matcher per distinct length, not per file.
    matchers = {
        size: MarkerMatchers.of_size(size)
        for size in {DEFAULT_MARKER_SIZE, *sizes.values()}
    }
    for path in tracked:
        relative = str(path.relative_to(repo_root))
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            # Tracked but not in the working tree — an unstaged deletion. The
            # staged blob is what a commit would ship, so that is what gets
            # scanned. Skipping it would let the gate report a clean scan of a
            # file it never read.
            raw = staged_blob(repo_root, relative)
        except OSError as error:
            raise MarkerScanError(
                f"ERROR: cannot read tracked file {relative}: {error}.\n"
                "  Fix its permissions, or remove it from the index."
            ) from error
        if b"\0" in raw[:BINARY_SNIFF_BYTES]:
            binary += 1
            continue
        scanned += 1
        file_matchers = matchers[sizes.get(relative, DEFAULT_MARKER_SIZE)]
        violations.extend(violations_in(raw, relative, file_matchers))
    return {
        "scanned_text_files": scanned,
        "skipped_binary_files": binary,
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    repo_root = Path(arguments[0]) if arguments else Path(__file__).resolve().parents[1]
    try:
        report = scan(repo_root)
    except MarkerScanError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    violations = report["violations"]
    assert isinstance(violations, list)  # scan() postcondition
    for violation in violations:
        print(
            f"ERROR: conflict marker {violation['marker']} at "
            f"{violation['path']}:{violation['line']}.\n"
            "  Finish the merge resolution and remove the marker line. "
            "`merge.conflictStyle = diff3` leaves a fourth marker (|||||||) "
            "that a three-marker cleanup misses.",
            file=sys.stderr,
        )
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())

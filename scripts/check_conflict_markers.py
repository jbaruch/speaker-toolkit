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
from pathlib import Path

# All four markers `merge.conflictStyle = diff3` can leave behind. The trailing
# `( |$)` keeps a Markdown rule (`=======` under a heading) and a shell here-doc
# from reading as a conflict: a real marker is either bare or followed by a
# space and a label.
MARKER = re.compile(r"^(<{7}|\|{7}|={7}|>{7})( |$)")

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


def violations_in(raw: bytes, relative: str) -> list[dict[str, object]]:
    """Every marker line in one file's bytes."""
    text = raw.decode("utf-8", "replace")
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = MARKER.match(line)
        if match:
            found.append({"path": relative, "line": number, "marker": match.group(1)})
    return found


def scan(repo_root: Path) -> dict[str, object]:
    """Scan every tracked text file and report what was found."""
    scanned = 0
    binary = 0
    violations: list[dict[str, object]] = []
    for path in tracked_files(repo_root):
        relative = str(path.relative_to(repo_root))
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            # Tracked but not on disk: a stale index entry, which is git's
            # problem and not a hidden marker.
            continue
        except OSError as error:
            raise MarkerScanError(
                f"ERROR: cannot read tracked file {relative}: {error}.\n"
                "  Fix its permissions, or remove it from the index."
            ) from error
        if b"\0" in raw[:BINARY_SNIFF_BYTES]:
            binary += 1
            continue
        scanned += 1
        violations.extend(violations_in(raw, relative))
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

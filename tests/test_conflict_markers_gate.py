"""Tests for scripts/check_conflict_markers.py.

A diff3 base marker survived a merge resolution and shipped in `CHANGELOG.md`,
which is published in the plugin package (#272). `ruff` does not read Markdown
and `git diff --check` only inspects the working diff, so an already-committed
marker passed every gate.

Markers are built from repeated characters rather than written out, so this file
is not itself a violation and the gate needs no exclusion list to stay green.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "check_conflict_markers.py"

OURS = "<" * 7
BASE = "|" * 7
SPLIT = "=" * 7
THEIRS = ">" * 7


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), str(repo)], capture_output=True, text=True
    )


def _report(result: subprocess.CompletedProcess) -> dict:
    """The gate's stdout verdict — one JSON object, pass or fail."""
    return json.loads(result.stdout)


def _repo(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    """A committed checkout, since the gate reads the tracked-file list."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, content in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    return tmp_path


@pytest.mark.parametrize(
    ("marker", "label"),
    [
        (OURS, " HEAD"),
        (BASE, " abc1234"),
        (THEIRS, " origin/main"),
    ],
)
def test_every_unambiguous_marker_fails_the_build(
    tmp_path: Path, marker, label
) -> None:
    """Nothing else in a text file writes these — the diff3 base one included."""
    repo = _repo(tmp_path, {"CHANGELOG.md": f"# Changelog\n\n{marker}{label}\ntext\n"})

    result = _run(repo)

    assert result.returncode == 1
    report = _report(result)
    assert report["violations"] == [
        {"path": "CHANGELOG.md", "line": 3, "marker": marker}
    ]
    assert "CHANGELOG.md:3" in result.stderr


def test_a_setext_rule_at_the_marker_length_is_not_a_marker(tmp_path: Path) -> None:
    """`=======` under a heading is a Markdown H2 rule, not a conflict.

    It is the one marker ordinary prose also writes, so flagging it outright
    would fail the build on legitimate content.
    """
    repo = _repo(tmp_path, {"doc.md": f"Heading\n{SPLIT}\n\nBody.\n"})

    result = _run(repo)

    assert result.returncode == 0, result.stderr
    assert _report(result)["violations"] == []


def test_the_separator_counts_inside_an_open_conflict(tmp_path: Path) -> None:
    """Between a start and its end, `=======` cannot be a heading rule."""
    repo = _repo(
        tmp_path,
        {
            "CHANGELOG.md": (
                f"# Changelog\n{OURS} HEAD\nours\n{SPLIT}\ntheirs\n"
                f"{THEIRS} origin/main\n"
            )
        },
    )

    result = _run(repo)

    assert result.returncode == 1
    lines = [violation["line"] for violation in _report(result)["violations"]]
    assert lines == [2, 4, 6]


def test_a_setext_rule_after_a_closed_conflict_is_not_a_marker(tmp_path: Path) -> None:
    """The end marker closes the region, so later prose reads as prose again."""
    repo = _repo(
        tmp_path,
        {
            "doc.md": (
                f"{OURS} HEAD\nours\n{SPLIT}\ntheirs\n{THEIRS} origin/main\n\n"
                f"Heading\n{SPLIT}\n\nBody.\n"
            )
        },
    )

    result = _run(repo)

    assert result.returncode == 1
    lines = [violation["line"] for violation in _report(result)["violations"]]
    assert lines == [1, 3, 5]


def test_a_clean_checkout_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"CHANGELOG.md": "# Changelog\n\nNo markers here.\n"})

    result = _run(repo)

    assert result.returncode == 0
    report = _report(result)
    assert report["violations"] == []
    assert report["scanned_text_files"] == 1


def test_this_repo_carries_no_marker() -> None:
    """The gate's own subject: nothing committed here may carry one."""
    result = _run(REPO_ROOT)

    assert result.returncode == 0, result.stderr
    assert _report(result)["violations"] == []


def test_long_rules_and_here_docs_are_not_markers(tmp_path: Path) -> None:
    """A marker is exactly its configured length; a rule runs to any length."""
    repo = _repo(
        tmp_path,
        {
            "doc.md": f"Heading\n{SPLIT}{SPLIT}\n\nBody.\n",
            "code.sh": f"printf '%s\\n' '{THEIRS}{THEIRS}'\n",
        },
    )

    result = _run(repo)

    assert result.returncode == 0
    assert _report(result)["violations"] == []


def test_binary_files_are_skipped_not_scanned(tmp_path: Path) -> None:
    """A marker is a line of text; the repo's binaries are eval fixtures."""
    repo = _repo(
        tmp_path,
        {
            "deck.pptx": b"PK\x03\x04\x00\x00binary payload",
            "notes.md": "clean\n",
        },
    )

    result = _run(repo)

    assert result.returncode == 0
    report = _report(result)
    assert report["skipped_binary_files"] == 1
    assert report["scanned_text_files"] == 1


def test_an_untracked_file_is_not_scanned(tmp_path: Path) -> None:
    """The gate guards what ships, and an untracked scratch file does not."""
    repo = _repo(tmp_path, {"notes.md": "clean\n"})
    (repo / "scratch.md").write_text(f"{OURS} HEAD\n", encoding="utf-8")

    result = _run(repo)

    assert result.returncode == 0
    assert _report(result)["violations"] == []


def test_every_marker_in_a_file_is_reported(tmp_path: Path) -> None:
    """One diagnostic per marker: a resolution usually leaves several."""
    repo = _repo(
        tmp_path,
        {
            "CHANGELOG.md": (
                f"# Changelog\n{OURS} HEAD\nours\n{BASE} abc1234\n"
                f"base\n{SPLIT}\ntheirs\n{THEIRS} origin/main\n"
            )
        },
    )

    result = _run(repo)

    assert result.returncode == 1
    lines = [violation["line"] for violation in _report(result)["violations"]]
    assert lines == [2, 4, 6, 8]


def test_a_configured_marker_length_is_recognized(tmp_path: Path) -> None:
    """git writes markers at the path's `conflict-marker-size`, not always 7.

    A repo that raises the size for a file whose content is full of `=======`
    lines still gets real conflict markers — just longer ones. Assuming seven
    would let those through the gate that exists to fail them.
    """
    long_marker = "<" * 12
    repo = _repo(
        tmp_path,
        {
            ".gitattributes": "notes.md conflict-marker-size=12\n",
            "notes.md": f"# Notes\n\n{long_marker} HEAD\ntext\n",
        },
    )

    result = _run(repo)

    assert result.returncode == 1
    report = _report(result)
    assert report["violations"] == [
        {"path": "notes.md", "line": 3, "marker": long_marker}
    ]


def test_a_configured_length_does_not_flag_the_default_length(tmp_path: Path) -> None:
    """The matcher follows the path's own size, so seven is no longer a marker."""
    repo = _repo(
        tmp_path,
        {
            ".gitattributes": "notes.md conflict-marker-size=12\n",
            "notes.md": f"# Notes\n\n{OURS} HEAD\ntext\n",
        },
    )

    result = _run(repo)

    assert result.returncode == 0
    assert _report(result)["violations"] == []


def test_a_longer_run_is_not_a_marker_at_the_default_size(tmp_path: Path) -> None:
    """A setext rule runs to any length; a marker is exactly its size."""
    repo = _repo(tmp_path, {"doc.md": f"Heading\n{'=' * 30}\n\nBody.\n"})

    result = _run(repo)

    assert result.returncode == 0
    assert _report(result)["violations"] == []


def test_paths_keep_their_own_marker_lengths(tmp_path: Path) -> None:
    """One scan, two configured sizes: each file is judged by its own."""
    long_marker = "|" * 9
    repo = _repo(
        tmp_path,
        {
            ".gitattributes": "wide.md conflict-marker-size=9\n",
            "wide.md": f"{long_marker} abc1234\n",
            "plain.md": f"{BASE} abc1234\n",
        },
    )

    result = _run(repo)

    assert result.returncode == 1
    flagged = {
        (violation["path"], violation["marker"])
        for violation in _report(result)["violations"]
    }
    assert flagged == {("wide.md", long_marker), ("plain.md", BASE)}


def test_a_directory_that_is_no_git_checkout_is_actionable(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "git ls-files" in result.stderr

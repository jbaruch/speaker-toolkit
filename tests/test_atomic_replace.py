"""Tests for atomic-replace.py — exact-target rename that refuses directories."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills/presentation-creator/scripts/atomic-replace.py"
)


def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True
    )


def test_replaces_an_existing_file_with_the_complete_source(tmp_path):
    src, dst = tmp_path / ".deck.tmp", tmp_path / "deck.pptx"
    src.write_text("new deck")
    dst.write_text("old deck")
    result = _run(src, dst)
    assert result.returncode == 0, result.stderr
    assert dst.read_text() == "new deck"
    assert not src.exists()


def test_creates_a_missing_destination(tmp_path):
    src, dst = tmp_path / ".deck.tmp", tmp_path / "deck.pptx"
    src.write_text("new deck")
    assert _run(src, dst).returncode == 0
    assert dst.read_text() == "new deck"


@pytest.mark.parametrize("as_symlink", [False, True])
def test_refuses_a_directory_destination_and_keeps_both_paths(tmp_path, as_symlink):
    src = tmp_path / ".deck.tmp"
    src.write_text("new deck")
    target = tmp_path / "decks"
    target.mkdir()
    dst = target
    if as_symlink:
        dst = tmp_path / "decks-link"
        dst.symlink_to(target, target_is_directory=True)
    result = _run(src, dst)
    assert result.returncode == 1
    assert f"{dst} is a directory, so nothing was delivered" in result.stderr
    assert "pass the path of the deck file to write" in result.stderr
    assert src.read_text() == "new deck"
    assert list(target.iterdir()) == []


def test_rename_time_directory_is_refused_by_rename_itself(tmp_path, monkeypatch):
    # Simulate a directory appearing after the check: skip the check and let
    # rename(2) see the directory.
    import importlib.util

    spec = importlib.util.spec_from_file_location("atomic_replace", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    src = tmp_path / ".deck.tmp"
    src.write_text("new deck")
    dst = tmp_path / "decks"
    dst.mkdir()
    monkeypatch.setattr(Path, "is_dir", lambda self: False)
    with pytest.raises(ValueError, match="became a directory before the rename"):
        module.replace(src, dst)
    assert src.read_text() == "new deck"
    assert list(dst.iterdir()) == []


def test_unwritable_folder_reports_the_repair(tmp_path):
    src = tmp_path / ".deck.tmp"
    src.write_text("new deck")
    result = _run(src, tmp_path / "missing" / "deck.pptx")
    assert result.returncode == 1
    assert "so " in result.stderr and "is unchanged" in result.stderr
    assert "make its folder writable" in result.stderr
    assert src.exists()


def test_usage_error_exits_2():
    assert _run("only-one-arg").returncode == 2

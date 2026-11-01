"""Tests for run-deck-ops.sh's import staging, with `osascript` faked on PATH.

The macro can't run in CI (rules/deck-editing-rules.md). What's checkable is what the
wrapper hands it: every import deck inside PowerPoint's container, since one outside
blocks the macro on a Grant File Access dialog.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

WRAPPER = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "presentation-creator"
    / "scripts"
    / "run-deck-ops.sh"
)


@pytest.fixture
def harness(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "osascript"
    # Staged decks are removed on exit, so read their bytes while they still exist.
    fake.write_text(
        f"""#!{sys.executable}
import json, os, pathlib, sys
arguments = sys.argv[2:]
imports = {{}}
for entry in filter(None, arguments[2].split(";")):
    alias, path = entry.split("=", 1)
    imports[alias] = {{"path": path, "text": pathlib.Path(path).read_text()}}
pathlib.Path(os.environ["FAKE_LOG"]).write_text(
    json.dumps({{"spec": arguments[2], "imports": imports}})
)
pathlib.Path(arguments[1]).write_bytes(b"deck")
""",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    home = tmp_path / "home"
    container = home / "Library/Containers/com.microsoft.Powerpoint/Data"
    container.mkdir(parents=True)
    log = tmp_path / "osascript.json"
    base = tmp_path / "base.pptx"
    base.write_text("base", encoding="utf-8")

    def run(import_spec: str, *, env_home: Path = home):
        return subprocess.run(
            [
                "bash",
                str(WRAPPER),
                str(base),
                str(tmp_path / "out" / "deck.pptx"),
                import_spec,
                "BASE:1",
                "",
            ],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "HOME": str(env_home),
                "FAKE_LOG": str(log),
            },
            check=False,
        )

    return run, log, container


def _deck(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_an_import_deck_reaches_the_macro_from_inside_the_container(tmp_path, harness):
    run, log, container = harness
    fragment = _deck(tmp_path / "scratch" / "frag.pptx", "fragment")

    result = run(f"sn={fragment}")

    assert result.returncode == 0, result.stderr
    staged = json.loads(log.read_text())["imports"]["sn"]
    assert Path(staged["path"]).is_relative_to(container)
    assert Path(staged["path"]).name == "frag.pptx"
    assert staged["text"] == "fragment"


def test_every_import_in_the_spec_is_staged(tmp_path, harness):
    run, log, container = harness
    first = _deck(tmp_path / "a.pptx", "first")
    second = _deck(tmp_path / "with space" / "b.pptx", "second")

    result = run(f"one={first};two={second}")

    assert result.returncode == 0, result.stderr
    imports = json.loads(log.read_text())["imports"]
    assert {alias: entry["text"] for alias, entry in imports.items()} == {
        "one": "first",
        "two": "second",
    }
    assert all(
        Path(entry["path"]).is_relative_to(container) for entry in imports.values()
    )


def test_two_imports_with_one_filename_keep_their_own_bytes(tmp_path, harness):
    run, log, _container = harness
    first = _deck(tmp_path / "left" / "deck.pptx", "left")
    second = _deck(tmp_path / "right" / "deck.pptx", "right")

    result = run(f"l={first};r={second}")

    assert result.returncode == 0, result.stderr
    imports = json.loads(log.read_text())["imports"]
    assert imports["l"]["text"] == "left"
    assert imports["r"]["text"] == "right"


def test_an_import_sharing_the_base_filename_keeps_its_own_bytes(tmp_path, harness):
    run, log, _container = harness
    twin = _deck(tmp_path / "elsewhere" / "base.pptx", "twin")

    result = run(f"t={twin}")

    assert result.returncode == 0, result.stderr
    assert json.loads(log.read_text())["imports"]["t"]["text"] == "twin"


def test_no_imports_passes_an_empty_spec(harness):
    run, log, _container = harness

    result = run("")

    assert result.returncode == 0, result.stderr
    assert json.loads(log.read_text())["spec"] == ""


def test_a_missing_import_stops_before_the_macro(tmp_path, harness):
    run, log, _container = harness

    result = run(f"gone={tmp_path / 'missing.pptx'}")

    assert result.returncode == 1
    assert "import deck 'gone' not found" in result.stderr
    assert not log.exists()


def test_a_malformed_entry_stops_before_the_macro(harness):
    run, log, _container = harness

    result = run("not-a-pair")

    assert result.returncode == 1
    assert "is not alias=/path" in result.stderr
    assert not log.exists()


def test_a_copy_that_fails_stops_instead_of_risking_the_prompt(tmp_path, harness):
    run, log, _container = harness
    fragment = _deck(tmp_path / "frag.pptx", "fragment")
    # It exists, so the check passes, but it can't be read, so the copy fails.
    fragment.chmod(0)
    if os.access(fragment, os.R_OK):  # pragma: no cover - running as root
        pytest.skip("this user can read a mode-0 file")

    result = run(f"sn={fragment}")

    assert result.returncode == 1
    assert "could not copy import deck 'sn'" in result.stderr
    assert not log.exists()


def test_with_no_container_the_original_path_passes_with_a_warning(tmp_path, harness):
    run, log, _container = harness
    fragment = _deck(tmp_path / "frag.pptx", "fragment")
    bare_home = tmp_path / "bare-home"
    bare_home.mkdir()

    result = run(f"sn={fragment}", env_home=bare_home)

    assert result.returncode == 0, result.stderr
    assert "container not found" in result.stderr
    assert json.loads(log.read_text())["spec"] == f"sn={fragment}"


def test_staged_imports_are_removed_when_the_wrapper_exits(tmp_path, harness):
    run, _log, container = harness
    fragment = _deck(tmp_path / "frag.pptx", "fragment")

    result = run(f"sn={fragment}")

    assert result.returncode == 0, result.stderr
    assert list((container / ".deckops-stage").iterdir()) == []

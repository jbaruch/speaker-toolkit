"""Tests for scripts/check_shipped_extensions.py.

The gate answers one question: will every file the manifest ships actually be
on the consumer's disk after `tessl install`? It exists because install
materializes a fixed extension allowlist and drops everything else without a
word — pack includes the file, publish reports success, and the consumer never
sees it. `_dimensions.yaml` went missing that way from 0.20.57 on (issue #316).

Its stdout is the machine-readable verdict (one JSON object, every run) and its
stderr carries the actionable diagnostics, so the assertions below read the
report for outcomes and the stderr for guidance.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "check_shipped_extensions.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), str(repo)], capture_output=True, text=True
    )


def _report(result: subprocess.CompletedProcess) -> dict:
    """The gate's stdout verdict — always one JSON object, pass or fail."""
    return json.loads(result.stdout)


def _commit(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")


@pytest.fixture()
def plugin(tmp_path: Path) -> Path:
    """A committed plugin repo whose files all carry shipped extensions."""
    repo = tmp_path / "plugin"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True
    )
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    _write(
        repo,
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "Test plugin",
                "skills": ["skills/builder"],
                "rules": ["rules/house-style.md"],
            }
        ),
    )
    _write(repo, "skills/builder/SKILL.md", "# Builder\n")
    _write(repo, "skills/builder/scripts/build.py", "print('build')\n")
    _write(repo, "skills/builder/scripts/wrap.sh", "echo wrap\n")
    _write(repo, "skills/builder/references/data.json", "{}\n")
    _write(repo, "rules/house-style.md", "# House Style\n")
    _commit(repo)
    return repo


def test_all_shipped_extensions_pass(plugin: Path) -> None:
    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    report = _report(result)
    assert report["ok"] is True
    assert report["needing_mirror"] == []


def test_a_mirrored_file_passes(plugin: Path) -> None:
    _write(plugin, "skills/builder/references/dims.yaml", "a: 1\n")
    _write(plugin, "skills/builder/references/dims.yaml.txt", "a: 1\n")
    _commit(plugin)

    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    report = _report(result)
    assert report["ok"] is True
    assert report["needing_mirror"] == ["skills/builder/references/dims.yaml"]


def test_a_missing_mirror_fails_and_names_the_fix(plugin: Path) -> None:
    """The #316 shape: a shipped file that install would drop, with no mirror."""
    _write(plugin, "skills/builder/references/dims.yaml", "a: 1\n")
    _commit(plugin)

    result = _run(plugin)
    assert result.returncode == 1
    report = _report(result)
    assert report["ok"] is False
    assert report["problems"] == [
        {
            "kind": "missing",
            "path": "skills/builder/references/dims.yaml",
            "mirror": "skills/builder/references/dims.yaml.txt",
        }
    ]
    assert (
        "cp skills/builder/references/dims.yaml"
        " skills/builder/references/dims.yaml.txt" in result.stderr
    )


def test_a_drifted_mirror_fails(plugin: Path) -> None:
    """A stale mirror is worse than none — the consumer silently reads old content."""
    _write(plugin, "skills/builder/references/dims.yaml", "a: 2\n")
    _write(plugin, "skills/builder/references/dims.yaml.txt", "a: 1\n")
    _commit(plugin)

    result = _run(plugin)
    assert result.returncode == 1
    problems = _report(result)["problems"]
    assert [p["kind"] for p in problems] == ["stale"]
    assert "stale mirror" in result.stderr


def test_an_orphan_mirror_fails(plugin: Path) -> None:
    """A mirror whose source was deleted keeps shipping a file the repo dropped."""
    _write(plugin, "skills/builder/references/dims.yaml.txt", "a: 1\n")
    _commit(plugin)

    result = _run(plugin)
    assert result.returncode == 1
    problems = _report(result)["problems"]
    assert [p["kind"] for p in problems] == ["orphan"]
    assert "orphan mirror" in result.stderr


def test_a_plain_txt_file_is_content_not_an_orphan_mirror(plugin: Path) -> None:
    """`notes.txt` mirrors nothing — only `<name>.<dropped-ext>.txt` is a mirror."""
    _write(plugin, "skills/builder/references/notes.txt", "hello\n")
    _commit(plugin)

    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    assert _report(result)["problems"] == []


def test_an_extensionless_file_is_not_flagged(plugin: Path) -> None:
    """The filter matches extensions; a bare LICENSE has none to match."""
    _write(plugin, "skills/builder/references/LICENSE", "MIT\n")
    _commit(plugin)

    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    assert _report(result)["needing_mirror"] == []


def test_an_untracked_file_is_not_a_shipping_contract(plugin: Path) -> None:
    """Only committed files are checked; .tesslignore strips untracked OS junk."""
    _write(plugin, "skills/builder/references/dims.yaml", "a: 1\n")

    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    assert _report(result)["needing_mirror"] == []


def test_every_extension_outside_the_allowlist_needs_a_mirror(plugin: Path) -> None:
    """Not a .yaml rule — the filter is an allowlist, so a fourth extension counts."""
    _write(plugin, "skills/builder/scripts/driver.applescript", "beep\n")
    _write(plugin, "skills/builder/scripts/macro.bas", "Sub Go()\n")
    _write(plugin, "skills/builder/references/table.csv", "a,b\n")
    _commit(plugin)

    result = _run(plugin)
    assert result.returncode == 1
    problems = _report(result)["problems"]
    assert {Path(p["path"]).suffix for p in problems} == {
        ".applescript",
        ".bas",
        ".csv",
    }


def test_this_repo_ships_every_file_it_declares() -> None:
    """The live tree stays in sync — this is the check that would have caught #316."""
    result = _run(REPO_ROOT)
    assert result.returncode == 0, result.stderr
    report = _report(result)
    assert report["ok"] is True
    assert (
        "skills/presentation-creator/references/patterns/_dimensions.yaml"
        in report["needing_mirror"]
    )

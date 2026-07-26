"""Tests for scripts/check-package-contents.sh.

The gate answers one question: does every file the plugin manifest declares as
plugin content survive .tesslignore filtering into the published package? It
exists because .tesslignore uses gitignore pattern semantics — an unanchored
"scripts/" strips skills/<name>/scripts/ along with the repo-root helper
directory, and the publish still succeeds.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "check-package-contents.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(GATE), str(repo)],
                          capture_output=True, text=True)


@pytest.fixture()
def plugin(tmp_path: Path) -> Path:
    """A committed plugin repo: one skill with a script, one rule, no ignores."""
    repo = tmp_path / "plugin"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)],
                   check=True, capture_output=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    _write(repo, ".tessl-plugin/plugin.json", json.dumps({
        "name": "acme/widget",
        "version": "1.0.0",
        "description": "Test plugin",
        "skills": ["skills/builder"],
        "rules": ["rules/house-style.md"],
    }))
    _write(repo, "skills/builder/SKILL.md", "# Builder\n")
    _write(repo, "skills/builder/scripts/build.py", "print('build')\n")
    _write(repo, "skills/builder/references/notes.md", "notes\n")
    _write(repo, "rules/house-style.md", "# House Style\n")
    _write(repo, "scripts/ci-helper.sh", "echo helper\n")
    _write(repo, "tests/test_build.py", "def test_x():\n    pass\n")

    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


def test_no_ignore_file_passes(plugin: Path) -> None:
    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    assert "no .tesslignore" in result.stdout


def test_clean_ignore_file_passes(plugin: Path) -> None:
    _write(plugin, ".tesslignore", "/scripts/\n/tests/\n")
    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    assert "all 4 declared plugin content files survive" in result.stdout


def test_unanchored_directory_pattern_strips_skill_scripts(plugin: Path) -> None:
    """The shipped bug: "scripts/" matches skills/<name>/scripts/ too."""
    _write(plugin, ".tesslignore", "scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "skills/builder/scripts/build.py" in result.stderr
    assert "excludes 1 of 4" in result.stderr
    assert "leading slash" in result.stderr


def test_anchored_pattern_keeps_skill_scripts(plugin: Path) -> None:
    """Anchoring excludes the repo-root helper dir and nothing deeper."""
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_unanchored_pattern_strips_skill_references(plugin: Path) -> None:
    """Any depth-crossing pattern is caught, not just the scripts/ case."""
    _write(plugin, ".tesslignore", "references/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "skills/builder/references/notes.md" in result.stderr


def test_excluded_rule_file_is_caught(plugin: Path) -> None:
    _write(plugin, ".tesslignore", "house-style.md\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "rules/house-style.md" in result.stderr


def test_repo_gitignore_cannot_mask_a_violation(plugin: Path) -> None:
    """Matching consults .tesslignore alone — .gitignore must not shadow it."""
    _write(plugin, ".gitignore", "scripts/\n")
    _write(plugin, ".tesslignore", "scripts/\n")
    _git(plugin, "add", "-A")
    _git(plugin, "commit", "-qm", "add gitignore")
    result = _run(plugin)
    assert result.returncode == 1
    assert "skills/builder/scripts/build.py" in result.stderr


def test_repo_gitignore_cannot_invent_a_violation(plugin: Path) -> None:
    _write(plugin, ".gitignore", "scripts/\n")
    _write(plugin, ".tesslignore", "/scripts/\n")
    _git(plugin, "add", "-A")
    _git(plugin, "commit", "-qm", "add gitignore")
    result = _run(plugin)
    assert result.returncode == 0, result.stderr


def test_missing_manifest_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run(empty)
    assert result.returncode == 1
    assert "plugin manifest .tessl-plugin/plugin.json not found" in result.stderr


def test_malformed_manifest_fails(plugin: Path) -> None:
    _write(plugin, ".tessl-plugin/plugin.json", "{not json")
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "not valid JSON" in result.stderr


def test_wrong_field_shape_fails(plugin: Path) -> None:
    _write(plugin, ".tessl-plugin/plugin.json", json.dumps({
        "name": "acme/widget", "version": "1.0.0", "description": "d",
        "skills": 42,
    }))
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "wrong shape" in result.stderr


def test_manifest_declaring_no_content_fails(plugin: Path) -> None:
    _write(plugin, ".tessl-plugin/plugin.json", json.dumps({
        "name": "acme/widget", "version": "1.0.0", "description": "d",
    }))
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "declares no plugin content" in result.stderr


def test_declared_path_with_no_tracked_files_fails(plugin: Path) -> None:
    _write(plugin, ".tessl-plugin/plugin.json", json.dumps({
        "name": "acme/widget", "version": "1.0.0", "description": "d",
        "skills": ["skills/builder", "skills/ghost"],
    }))
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert 'declares "skills/ghost" but no tracked files live there' in result.stderr


def test_skills_declared_as_directory_string(plugin: Path) -> None:
    """`skills` may be a directory path instead of an array of paths."""
    _write(plugin, ".tessl-plugin/plugin.json", json.dumps({
        "name": "acme/widget", "version": "1.0.0", "description": "d",
        "skills": "skills/",
    }))
    _write(plugin, ".tesslignore", "scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "skills/builder/scripts/build.py" in result.stderr


def test_this_repo_ships_every_declared_file() -> None:
    """Regression guard: speaker-toolkit's own package must be complete."""
    result = subprocess.run(["bash", str(GATE)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

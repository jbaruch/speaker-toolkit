"""Tests for scripts/check_package_contents.py.

The gate answers one question: does every file the plugin manifest declares as
plugin content survive .tesslignore filtering into the published package? It
exists because .tesslignore uses gitignore pattern semantics — an unanchored
"scripts/" strips skills/<name>/scripts/ along with the repo-root helper
directory, and the publish still succeeds.

Its stdout is the machine-readable verdict (one JSON object, every run) and its
stderr carries the actionable diagnostics, so the assertions below read the
report for outcomes and the stderr for guidance.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "check_package_contents.py"


def _load_gate():
    """Import the gate as a module — the entry-point guard keeps that side-effect free."""
    spec = importlib.util.spec_from_file_location("check_package_contents", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


@pytest.fixture()
def plugin(tmp_path: Path) -> Path:
    """A committed plugin repo: one skill with a script, one rule, no ignores."""
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
    report = _report(result)
    assert report["ok"] is True
    assert report["ignore_file_present"] is False
    # The declared-path checks still ran; only exclusion matching was skipped.
    assert report["checked"] == 4


def test_malformed_manifest_fails_without_an_ignore_file(plugin: Path) -> None:
    """No .tesslignore skips exclusion matching, never the Surface Sync checks."""
    _write(plugin, ".tessl-plugin/plugin.json", "{not json")
    result = _run(plugin)
    assert result.returncode == 1
    assert "not valid JSON" in result.stderr


def test_stale_declaration_fails_without_an_ignore_file(plugin: Path) -> None:
    _write(
        plugin,
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "d",
                "skills": ["skills/builder", "skills/ghost"],
            }
        ),
    )
    result = _run(plugin)
    assert result.returncode == 1
    assert _report(result)["missing"] == ["skills/ghost"]
    assert 'declares "skills/ghost" but no tracked files live there' in result.stderr


def test_clean_ignore_file_passes(plugin: Path) -> None:
    _write(plugin, ".tesslignore", "/scripts/\n/tests/\n")
    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    report = _report(result)
    assert report["ok"] is True
    assert report["checked"] == 4
    assert report["excluded"] == []


def test_unanchored_directory_pattern_strips_skill_scripts(plugin: Path) -> None:
    """The shipped bug: "scripts/" matches skills/<name>/scripts/ too."""
    _write(plugin, ".tesslignore", "scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    report = _report(result)
    assert report["ok"] is False
    assert report["checked"] == 4
    assert [item["path"] for item in report["excluded"]] == [
        "skills/builder/scripts/build.py"
    ]
    assert report["excluded"][0]["pattern"] == "scripts/"
    assert "skills/builder/scripts/build.py" in result.stderr
    assert "excludes 1 of 4" in result.stderr
    assert "leading slash" in result.stderr


def test_anchored_pattern_keeps_skill_scripts(plugin: Path) -> None:
    """Anchoring excludes the repo-root helper dir and nothing deeper."""
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    assert _report(result)["ok"] is True


def test_unanchored_pattern_strips_skill_references(plugin: Path) -> None:
    """Any depth-crossing pattern is caught, not just the scripts/ case."""
    _write(plugin, ".tesslignore", "references/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert [item["path"] for item in _report(result)["excluded"]] == [
        "skills/builder/references/notes.md"
    ]
    assert "skills/builder/references/notes.md" in result.stderr


def test_excluded_rule_file_is_caught(plugin: Path) -> None:
    _write(plugin, ".tesslignore", "house-style.md\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert [item["path"] for item in _report(result)["excluded"]] == [
        "rules/house-style.md"
    ]
    assert "rules/house-style.md" in result.stderr


def test_repo_gitignore_cannot_mask_a_violation(plugin: Path) -> None:
    """Matching consults .tesslignore alone — .gitignore must not shadow it."""
    _write(plugin, ".gitignore", "scripts/\n")
    _write(plugin, ".tesslignore", "scripts/\n")
    _git(plugin, "add", "-A")
    _git(plugin, "commit", "-qm", "add gitignore")
    result = _run(plugin)
    assert result.returncode == 1
    assert [item["path"] for item in _report(result)["excluded"]] == [
        "skills/builder/scripts/build.py"
    ]


def test_repo_gitignore_cannot_invent_a_violation(plugin: Path) -> None:
    _write(plugin, ".gitignore", "scripts/\n")
    _write(plugin, ".tesslignore", "/scripts/\n")
    _git(plugin, "add", "-A")
    _git(plugin, "commit", "-qm", "add gitignore")
    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    assert _report(result)["ok"] is True


def test_missing_manifest_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run(empty)
    assert result.returncode == 1
    assert _report(result)["ok"] is False
    assert "plugin manifest .tessl-plugin/plugin.json not found" in result.stderr


def test_malformed_manifest_fails(plugin: Path) -> None:
    _write(plugin, ".tessl-plugin/plugin.json", "{not json")
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "not valid JSON" in _report(result)["error"]
    assert "not valid JSON" in result.stderr


def test_wrong_field_shape_fails(plugin: Path) -> None:
    _write(
        plugin,
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "d",
                "skills": 42,
            }
        ),
    )
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "wrong shape" in _report(result)["error"]
    assert "wrong shape" in result.stderr


def test_manifest_declaring_no_content_fails(plugin: Path) -> None:
    _write(
        plugin,
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "d",
            }
        ),
    )
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "declares no plugin content" in result.stderr


def test_declared_path_with_no_tracked_files_fails(plugin: Path) -> None:
    _write(
        plugin,
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "d",
                "skills": ["skills/builder", "skills/ghost"],
            }
        ),
    )
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert _report(result)["missing"] == ["skills/ghost"]
    assert 'declares "skills/ghost" but no tracked files live there' in result.stderr


def test_skills_declared_as_directory_string(plugin: Path) -> None:
    """`skills` may be a directory path instead of an array of paths."""
    _write(
        plugin,
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "d",
                "skills": "skills/",
            }
        ),
    )
    _write(plugin, ".tesslignore", "scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert [item["path"] for item in _report(result)["excluded"]] == [
        "skills/builder/scripts/build.py"
    ]


def test_non_string_array_item_reports_a_shape_error(plugin: Path) -> None:
    """A non-string array item is a broken manifest, not a missing directory."""
    _write(
        plugin,
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "d",
                "skills": [42],
            }
        ),
    )
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert "wrong shape" in result.stderr
    assert "'skills'[0] must be a string, got int" in result.stderr
    assert "no tracked files live there" not in result.stderr


def test_overlapping_declared_paths_are_counted_once(plugin: Path) -> None:
    """Declaring a directory and a path beneath it must not double-count files."""
    _write(
        plugin,
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "d",
                "skills": ["skills/", "skills/builder"],
                "rules": ["rules/house-style.md"],
            }
        ),
    )
    # An ignore file that excludes no declared content, so the gate reaches its
    # counting path instead of short-circuiting on a missing .tesslignore.
    _write(plugin, ".tesslignore", "/build/\n")
    result = _run(plugin)
    assert result.returncode == 0, result.stderr
    # 3 skill files + 1 rule, each counted once despite the overlapping globs.
    assert _report(result)["checked"] == 4


def test_overlapping_declared_paths_report_each_violation_once(plugin: Path) -> None:
    """An excluded file under overlapping globs is reported once, not twice."""
    _write(
        plugin,
        ".tessl-plugin/plugin.json",
        json.dumps(
            {
                "name": "acme/widget",
                "version": "1.0.0",
                "description": "d",
                "skills": ["skills/", "skills/builder"],
                "rules": ["rules/house-style.md"],
            }
        ),
    )
    _write(plugin, ".tesslignore", "scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    assert len(_report(result)["excluded"]) == 1
    assert result.stderr.count("skills/builder/scripts/build.py") == 1
    assert "excludes 1 of 4" in result.stderr


@pytest.mark.parametrize(
    "manifest_body",
    [
        "{not json",
        json.dumps({"skills": 42}),
        json.dumps({"name": "acme/widget"}),
    ],
)
def test_every_failure_path_still_emits_one_json_object(
    plugin: Path, manifest_body: str
) -> None:
    """A consumer must never have to tell "gate said no" from "gate crashed"."""
    _write(plugin, ".tessl-plugin/plugin.json", manifest_body)
    _write(plugin, ".tesslignore", "/scripts/\n")
    result = _run(plugin)
    assert result.returncode == 1
    report = _report(result)
    assert report["ok"] is False
    assert report["error"]


def test_gate_is_importable_without_running() -> None:
    """file-hygiene -> Standalone Scripts: the entry-point guard makes it importable."""
    module = _load_gate()
    report, diagnostics = module.run(REPO_ROOT)
    assert report["ok"] is True, diagnostics
    assert diagnostics == []


def test_this_repo_ships_every_declared_file() -> None:
    """Regression guard: speaker-toolkit's own package must be complete."""
    result = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _report(result)["ok"] is True

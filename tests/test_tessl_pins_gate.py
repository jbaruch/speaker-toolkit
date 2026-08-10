"""Tests for scripts/check_tessl_pins.py.

The gate is the deploy-time check preconditioned by the tessl-version-floating
carve-out: every dependency in a covered manifest must use the permitted
floating specifier, and anything else — a literal pin, a range, a tag, a
non-object entry — fails the build.

Its stdout is the machine-readable verdict (one JSON object, every run) and its
stderr carries the actionable diagnostics.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "check_tessl_pins.py"


def _load_gate():
    """Import the gate as a module — the entry-point guard keeps that side-effect free."""
    spec = importlib.util.spec_from_file_location("check_tessl_pins", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), str(repo)], capture_output=True, text=True
    )


def _report(result: subprocess.CompletedProcess) -> dict:
    """The gate's stdout verdict — always one JSON object, pass or fail."""
    return json.loads(result.stdout)


def _manifest(repo: Path, body) -> None:
    text = body if isinstance(body, str) else json.dumps(body)
    (repo / "tessl.json").write_text(text)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A repo whose covered manifest floats every dependency."""
    root = tmp_path / "consumer"
    root.mkdir()
    _manifest(
        root,
        {
            "name": "acme/widget",
            "mode": "vendored",
            "dependencies": {
                "acme/policy": {"version": "latest"},
                "vendor/eval": {"version": "latest"},
            },
        },
    )
    return root


def test_all_floating_passes(repo: Path) -> None:
    result = _run(repo)
    assert result.returncode == 0, result.stderr
    report = _report(result)
    assert report["ok"] is True
    assert report["violations"] == []
    assert report["checked"] == 1


def test_literal_pin_fails(repo: Path) -> None:
    _manifest(
        repo,
        {"dependencies": {"acme/policy": {"version": "1.2.3"}}},
    )
    result = _run(repo)
    assert result.returncode == 1
    report = _report(result)
    assert report["ok"] is False
    assert report["violations"] == [
        {"manifest": "tessl.json", "dependency": "acme/policy", "specifier": "'1.2.3'"}
    ]
    assert "non-floating specifiers" in result.stderr


@pytest.mark.parametrize(
    "specifier",
    ["^1.0.0", ">=2,<3", "stable", "", "LATEST"],
)
def test_non_literal_specifiers_fail_too(repo: Path, specifier: str) -> None:
    """Rejecting only literal pins lets a range or tag slip through."""
    _manifest(repo, {"dependencies": {"acme/policy": {"version": specifier}}})
    result = _run(repo)
    assert result.returncode == 1
    assert _report(result)["violations"][0]["dependency"] == "acme/policy"


def test_missing_version_key_fails(repo: Path) -> None:
    _manifest(repo, {"dependencies": {"acme/policy": {}}})
    result = _run(repo)
    assert result.returncode == 1
    assert _report(result)["violations"][0]["specifier"] == "None"


def test_non_object_dependency_entry_fails(repo: Path) -> None:
    """A bare string entry carries no specifier, so it cannot be proven floating."""
    _manifest(repo, {"dependencies": {"acme/policy": "latest"}})
    result = _run(repo)
    assert result.returncode == 1
    assert _report(result)["violations"][0]["dependency"] == "acme/policy"


def test_non_object_dependencies_field_fails(repo: Path) -> None:
    _manifest(repo, {"dependencies": ["acme/policy"]})
    result = _run(repo)
    assert result.returncode == 1
    assert _report(result)["violations"][0]["dependency"] == "dependencies"


def test_manifest_without_dependencies_passes(repo: Path) -> None:
    """Nothing declared is nothing pinned."""
    _manifest(repo, {"name": "acme/widget"})
    result = _run(repo)
    assert result.returncode == 0, result.stderr
    assert _report(result)["ok"] is True


def test_missing_manifest_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run(empty)
    assert result.returncode == 1
    report = _report(result)
    assert report["ok"] is False
    assert report["unreadable"] == ["tessl.json"]
    assert "not found" in result.stderr
    assert "rules/tessl-version-floating.md" in result.stderr


def test_malformed_manifest_fails(repo: Path) -> None:
    _manifest(repo, "{not json")
    result = _run(repo)
    assert result.returncode == 1
    assert _report(result)["unreadable"] == ["tessl.json"]
    assert "not valid JSON" in result.stderr


def test_wrong_top_level_shape_fails(repo: Path) -> None:
    _manifest(repo, [{"version": "latest"}])
    result = _run(repo)
    assert result.returncode == 1
    assert "wrong top-level shape" in result.stderr


def test_every_failure_path_still_emits_one_json_object(repo: Path) -> None:
    """A consumer must never have to tell "gate said no" from "gate crashed"."""
    _manifest(repo, "{not json")
    result = _run(repo)
    assert result.returncode == 1
    assert _report(result)["ok"] is False


def test_gate_is_importable_without_running() -> None:
    """file-hygiene -> Standalone Scripts: the entry-point guard makes it importable."""
    module = _load_gate()
    assert (
        module.manifest_violations({"dependencies": {"a": {"version": "latest"}}}) == []
    )
    assert module.manifest_violations({"dependencies": {"a": {"version": "1.0"}}}) == [
        {"dependency": "a", "specifier": "'1.0'"}
    ]


def test_this_repo_floats_every_covered_dependency() -> None:
    """Regression guard: speaker-toolkit's own manifest must stay floating."""
    result = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _report(result)["ok"] is True

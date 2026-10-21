"""Discovery reads current taxonomy without changing scoring or speaker history."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import SCRIPTS_PC, _import_script

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/presentation-creator/scripts/pattern-menu.py"


@pytest.fixture()
def menu():
    return _import_script(str(Path(SCRIPTS_PC) / "pattern-menu.py"), "pattern_menu")


def _entry(root, name, *, phase="architecture", kind="pattern", observable=True):
    path = root / "build" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {name}\nname: {name.title()}\ntype: {kind}\n"
        f"phase_relevance: [{phase}]\nobservable: {str(observable).lower()}\n---\n"
        f"\n# {name}\n\n## Summary\nUse {name} deliberately.\n"
        "\n## Scoring Criteria\nScoring instructions are not discovery context.\n"
    )
    return path


def test_menu_selects_declared_phase_and_kind_without_scoring_or_history(
    menu, tmp_path
):
    _entry(tmp_path, "arc")
    _entry(tmp_path, "quote", phase="slides")
    _entry(tmp_path, "dense", kind="antipattern")
    report = menu.build_menu(tmp_path, "architecture", "pattern")
    assert report["entries"] == [
        {
            "id": "arc",
            "name": "Arc",
            "path": "build/arc.md",
            "summary": "Use arc deliberately.",
            "observable": True,
        }
    ]


def test_delivery_menu_preserves_unobservable_reminders(menu, tmp_path):
    _entry(tmp_path, "rehearse", phase="publishing", observable=False)
    report = menu.build_menu(tmp_path, "publishing", "pattern")
    assert report["entries"][0]["observable"] is False


@pytest.mark.parametrize(
    ("phase", "skill", "action", "step"),
    [
        ("intake", "presentation-creator", "author", 0),
        ("intent", "presentation-creator", "author", 1),
        ("architecture", "presentation-creator", "author", 2),
        ("content", "presentation-creator", "author", 3),
        ("guardrails", "presentation-creator", "author", 4),
        ("slides", "presentation-builder", "build", 1),
        ("publishing", "presentation-publisher", "delivery", 4),
    ],
)
def test_lifecycle_menu_supplies_the_task_owner(
    menu, tmp_path, phase, skill, action, step
):
    _entry(tmp_path, "selected", phase=phase)
    report = menu.build_menu(tmp_path, phase, "pattern")
    assert report["phase"] == phase
    assert report["workflow"] == {"skill": skill, "action": action, "step": step}
    assert [entry["id"] for entry in report["entries"]] == ["selected"]


@pytest.mark.parametrize(
    ("alias", "phase"),
    [
        ("Phase 5", "slides"),
        ("creator phase 5", "slides"),
        ("Phase 5: Slides", "slides"),
        ("Phase 5: Slide Generation", "slides"),
        ("Phase 6", "publishing"),
        ("Creator Phase 6", "publishing"),
        ("Phase 6: Publishing", "publishing"),
        ("  Creator   Phase 6 (Publishing / Go-Live)  ", "publishing"),
    ],
)
def test_legacy_lifecycle_labels_select_the_same_menu(menu, tmp_path, alias, phase):
    _entry(tmp_path, "selected", phase=phase)
    assert menu.build_menu(tmp_path, alias, "pattern") == menu.build_menu(
        tmp_path, phase, "pattern"
    )


def test_unknown_lifecycle_label_refuses_with_help(menu, tmp_path):
    with pytest.raises(menu.PatternMenuError, match="choose one from --help"):
        menu.build_menu(tmp_path, "creator phase 99", "pattern")


def test_discovery_does_not_touch_or_load_the_scoring_index(menu, tmp_path):
    _entry(tmp_path, "arc")
    (tmp_path / "_index.md").write_bytes(b"index content is not discovery input\xff")
    before = {
        p: hashlib.sha256(p.read_bytes()).digest()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    menu.build_menu(tmp_path, "architecture", "pattern")
    assert {p: hashlib.sha256(p.read_bytes()).digest() for p in before} == before


@pytest.mark.parametrize("fault", ["duplicate-id", "invalid-yaml", "missing-summary"])
def test_invalid_catalog_refuses_with_a_repair(menu, tmp_path, fault):
    first = _entry(tmp_path, "arc")
    second = _entry(tmp_path, "other")
    if fault == "duplicate-id":
        second.write_text(second.read_text().replace("id: other", "id: arc"))
    elif fault == "invalid-yaml":
        first.write_text(first.read_text().replace("id: arc", "id: ["))
    else:
        first.write_text(first.read_text().replace("## Summary", "## Missing"))
    if fault == "invalid-yaml":
        import yaml

        expected = yaml.YAMLError
    else:
        expected = menu.PatternMenuError
    with pytest.raises(expected):
        menu.build_menu(tmp_path, "architecture", "pattern")


def test_real_cli_returns_openable_paths_without_the_full_index():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--phase", "architecture"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["entries"]
    for entry in report["entries"]:
        assert (Path(report["catalog_root"]) / entry["path"]).is_file()
    assert len(result.stdout) < len(
        (Path(report["catalog_root"]) / "_index.md").read_text()
    )


def test_cli_legacy_publishing_label_emits_delivery_handoff_from_any_directory(
    tmp_path,
):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--phase", "Creator Phase 6"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["workflow"] == {
        "skill": "presentation-publisher",
        "action": "delivery",
        "step": 4,
    }
    followup = next(row for row in report["entries"] if row["id"] == "spaced-followup")
    assert followup["observable"] is False


def test_cli_unknown_lifecycle_label_has_no_partial_output():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--phase", "creator phase 99"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "choose one from --help" in result.stderr

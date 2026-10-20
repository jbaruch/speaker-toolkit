"""Discovery reads current taxonomy without changing scoring or speaker history."""

from __future__ import annotations

import hashlib
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
    import json

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

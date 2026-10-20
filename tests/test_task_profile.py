"""Focused requests receive selected configuration rather than the full vault profile."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import SCRIPTS_PC, _import_script

SCRIPT = Path(SCRIPTS_PC) / "read-task-profile.py"


@pytest.fixture()
def reader():
    return _import_script(str(SCRIPT), "read_task_profile")


@pytest.mark.parametrize(
    "task,expected",
    [
        ("export", {"publishing_process": {"export_format": "pdf"}}),
        ("qr", {"publishing_process": {"qr_code": {"shortener": "none"}}}),
        ("cfp", {"speaker": {"name": "A Speaker"}}),
        ("build-pptx", {"design_rules": {"slide_numbers": "never"}}),
        ("catalog", {"speaker": {"name": "A Speaker"}}),
    ],
)
def test_profile_selection_excludes_unrelated_fields_and_all_history(
    reader, task, expected
):
    profile = {
        "speaker": {"name": "A Speaker"},
        "design_rules": {"slide_numbers": "never"},
        "publishing_process": {
            "export_format": "pdf",
            "qr_code": {"shortener": "none"},
        },
        "pattern_profile": {"never_tried": ["not authorization"]},
        "visual_style_history": {"styles": ["irrelevant"]},
        "badges": ["irrelevant"],
        "secrets": {"placeholder": "must not be projected"},
    }
    assert reader.project(profile, task) == expected


def test_no_optional_missing_field_gets_a_default(reader):
    assert reader.project({"speaker": {}}, "export") == {}


def test_missing_is_optional_but_a_present_invalid_profile_is_not(reader, tmp_path):
    path = tmp_path / "speaker-profile.json"
    assert (
        reader.read_profile(path, "cfp", allow_missing=True)["profile_available"]
        is False
    )
    path.write_text("invalid json")
    with pytest.raises(ValueError):
        reader.read_profile(path, "cfp", allow_missing=True)


def test_real_cli_selects_context_without_touching_the_source(tmp_path):
    path = tmp_path / "speaker-profile.json"
    path.write_text(json.dumps({"publishing_process": {"export_format": "pdf"}}))
    before = path.read_bytes()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path), "--task", "export"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["profile"] == {
        "publishing_process": {"export_format": "pdf"}
    }
    assert path.read_bytes() == before


def test_invalid_cli_input_emits_only_the_actionable_diagnostic(tmp_path):
    path = tmp_path / "speaker-profile.json"
    path.write_text("[]")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path), "--task", "cfp", "--allow-missing"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "repair the present profile" in result.stderr

"""Tests for the stdlib-only vault-ingress runtime probe."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import runpy
import sys

import pytest


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "vault-ingress"
    / "scripts"
    / "check-runtime.py"
)
SPEC = importlib.util.spec_from_file_location("check_runtime", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check_runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_runtime)


def test_optional_lane_failure_degrades_without_blocking_core(monkeypatch) -> None:
    monkeypatch.setattr(
        check_runtime,
        "_module_available",
        lambda name: name != "pptx",
    )
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(
        ("core", "pdf", "pptx"),
        ("core",),
    )

    assert report["ok"] is True
    assert report["blocking_lanes"] == []
    assert report["degraded_lanes"] == ["pptx"]
    assert report["lanes"]["pptx"]["missing_modules"] == ["python-pptx"]


def test_explicitly_required_lane_failure_is_blocking(monkeypatch) -> None:
    monkeypatch.setattr(
        check_runtime,
        "_module_available",
        lambda name: name != "pypdf",
    )
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(
        ("core", "pdf"),
        ("core", "pdf"),
    )

    assert report["ok"] is False
    assert report["blocking_lanes"] == ["pdf"]
    assert report["lanes"]["pdf"]["missing_modules"] == ["pypdf"]


def test_core_is_always_selected_and_required(monkeypatch) -> None:
    monkeypatch.setattr(
        check_runtime,
        "_module_available",
        lambda name: name != "yaml",
    )
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(("pptx",), ())

    assert report["ok"] is False
    assert report["blocking_lanes"] == ["core"]
    assert report["lanes"]["core"]["missing_modules"] == ["PyYAML"]


def test_lane_parser_rejects_unknown_names() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="unknown lanes"):
        check_runtime._parse_lanes("core,imaginary")


def test_lane_parser_gives_recovery_for_empty_names() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="such as core"):
        check_runtime._parse_lanes("")


def test_module_probe_contains_expected_import_failures(monkeypatch) -> None:
    def unavailable(_name: str) -> None:
        raise ImportError("dependency is not installed")

    monkeypatch.setattr(check_runtime.importlib, "import_module", unavailable)

    assert check_runtime._module_available("missing") is False


def test_module_probe_does_not_hide_unexpected_failures(monkeypatch) -> None:
    def broken(_name: str) -> None:
        raise ValueError("dependency initialization is corrupt")

    monkeypatch.setattr(check_runtime.importlib, "import_module", broken)

    with pytest.raises(ValueError, match="initialization is corrupt"):
        check_runtime._module_available("broken")


def test_main_reports_blocking_lanes_with_recovery_step(monkeypatch, capsys) -> None:
    monkeypatch.setattr(check_runtime, "_module_available", lambda _name: False)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    assert check_runtime.main(["--lanes", "core"]) == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["blocking_lanes"] == ["core"]
    assert "install the missing modules or commands" in captured.err
    assert "then rerun this check" in captured.err


def test_outer_boundary_emits_one_json_failure_for_unexpected_probe_fault(
    monkeypatch, capsys
) -> None:
    def broken(_name: str) -> None:
        raise ValueError("dependency initialization is corrupt")

    monkeypatch.setattr("importlib.import_module", broken)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert raised.value.code == 2
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    payload = json.loads(captured.out)
    assert payload["blocking_lanes"] == ["runtime-probe"]
    assert payload["error"] == "ValueError: dependency initialization is corrupt"
    assert "repair the configured interpreter" in captured.err
    assert "then rerun this check" in captured.err


def test_lane_requirements_match_the_configured_interpreter_contract() -> None:
    requirements = check_runtime.LANE_REQUIREMENTS

    assert requirements["google-drive"]["modules"] == {"gdown": "gdown"}
    assert requirements["captions"]["commands"] == {}
    assert requirements["youtube-download"]["commands"] == {"yt-dlp": "yt-dlp"}
    assert requirements["pdf-render"]["commands"] == {"pdftoppm": "pdftoppm"}

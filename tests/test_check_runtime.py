"""Tests for the stdlib-only vault-ingress runtime probe."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys

import pytest


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "vault-ingress"
    / "scripts"
    / "check-runtime.py"
)
if str(SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("check_runtime", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check_runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_runtime)


def _available_probe() -> dict[str, object]:
    return {"available": True, "failure": None}


def _failed_probe(reason: str, **details: object) -> dict[str, object]:
    failure: dict[str, object] = {"reason": reason}
    failure.update(details)
    return {"available": False, "failure": failure}


def test_optional_lane_failure_degrades_without_blocking_core(monkeypatch) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "pptx":
            return _failed_probe("unavailable_import")
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(
        ("core", "pdf", "pptx"),
        ("core",),
    )

    assert report["ok"] is True
    assert report["blocking_lanes"] == []
    assert report["degraded_lanes"] == ["pptx"]
    assert report["lanes"]["pptx"]["missing_modules"] == ["python-pptx"]
    assert report["lanes"]["pptx"]["module_failures"] == {
        "python-pptx": {"reason": "unavailable_import"}
    }


def test_missing_psutil_blocks_required_pdf_and_pptx_lanes(monkeypatch) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "psutil":
            return _failed_probe("unavailable_import")
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(
        ("core", "pdf", "pptx"),
        ("core", "pdf", "pptx"),
    )

    assert report["ok"] is False
    assert report["blocking_lanes"] == ["pdf", "pptx"]
    assert report["degraded_lanes"] == []
    assert report["lanes"]["pdf"]["missing_modules"] == ["psutil"]
    assert report["lanes"]["pdf"]["module_failures"] == {
        "psutil": {"reason": "unavailable_import"}
    }
    assert report["lanes"]["pptx"]["missing_modules"] == ["psutil"]
    assert report["lanes"]["pptx"]["module_failures"] == {
        "psutil": {"reason": "unavailable_import"}
    }


def test_explicitly_required_lane_failure_is_blocking(monkeypatch) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "pypdf":
            return _failed_probe("unavailable_import")
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(
        ("core", "pdf"),
        ("core", "pdf"),
    )

    assert report["ok"] is False
    assert report["blocking_lanes"] == ["pdf"]
    assert report["lanes"]["pdf"]["missing_modules"] == ["pypdf"]


def test_core_is_always_selected_and_required(monkeypatch) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "yaml":
            return _failed_probe("unavailable_import")
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
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


def _module_on_path(monkeypatch, directory: Path, name: str, source: str) -> str:
    (directory / f"{name}.py").write_text(source, encoding="utf-8")
    existing = os.environ.get("PYTHONPATH")
    monkeypatch.setenv(
        "PYTHONPATH",
        f"{directory}{os.pathsep}{existing}" if existing else str(directory),
    )
    return name


def test_module_probe_reports_an_importable_module_despite_its_output(
    tmp_path: Path, monkeypatch
) -> None:
    name = _module_on_path(
        monkeypatch,
        tmp_path,
        "speaker_toolkit_test_noisy_initializer",
        'import os\nos.write(1, b"x" * 1_000_000)\nos.write(2, b"y" * 1_000_000)\n',
    )

    assert check_runtime._probe_module(name) == _available_probe()


def test_module_probe_reports_a_missing_module_as_unavailable_import() -> None:
    result = check_runtime._probe_module("speaker_toolkit_test_no_such_module")

    assert result == _failed_probe("unavailable_import")


def test_module_probe_reports_a_raising_initializer(
    tmp_path: Path, monkeypatch
) -> None:
    name = _module_on_path(
        monkeypatch,
        tmp_path,
        "speaker_toolkit_test_broken_initializer",
        'raise RuntimeError("initializer failed")\n',
    )

    assert check_runtime._probe_module(name) == _failed_probe("initializer_exception")


def test_module_probe_ignores_a_shadowing_module_in_the_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "speaker_toolkit_test_cwd_only.py").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = check_runtime._probe_module("speaker_toolkit_test_cwd_only")

    assert result == _failed_probe("unavailable_import")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_module_probe_reports_a_native_crash_by_signal(
    tmp_path: Path, monkeypatch
) -> None:
    name = _module_on_path(
        monkeypatch,
        tmp_path,
        "speaker_toolkit_test_aborting_initializer",
        "import os\nos.abort()\n",
    )

    assert check_runtime._probe_module(name) == _failed_probe(
        "native_crash",
        termination="signal",
        signal_number=signal.SIGABRT,
        signal_name="SIGABRT",
    )


def test_module_probe_reports_another_exit_status_as_a_native_crash(
    tmp_path: Path, monkeypatch
) -> None:
    name = _module_on_path(
        monkeypatch,
        tmp_path,
        "speaker_toolkit_test_exiting_initializer",
        "import os\nos._exit(134)\n",
    )

    assert check_runtime._probe_module(name) == _failed_probe(
        "native_crash", termination="exit", exit_code=134
    )


def test_module_probe_timeout_is_a_bounded_failure() -> None:
    def runner(
        _command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        raise subprocess.TimeoutExpired(
            cmd="module-probe",
            timeout=check_runtime.MODULE_PROBE_TIMEOUT_SECONDS,
        )

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "timeout",
        timeout_seconds=check_runtime.MODULE_PROBE_TIMEOUT_SECONDS,
    )


def test_module_probe_start_failure_is_lane_local() -> None:
    def runner(
        _command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        raise FileNotFoundError("configured interpreter disappeared")

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "probe_start_failure",
        exception_type="FileNotFoundError",
    )


def test_native_whisper_failure_degrades_when_only_core_is_required(
    monkeypatch,
) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "mlx_whisper":
            return _failed_probe(
                "native_crash",
                termination="signal",
                signal_number=signal.SIGABRT,
                signal_name="SIGABRT",
            )
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(("whisper",), ("core",))

    assert report["ok"] is True
    assert report["degraded_lanes"] == ["whisper"]
    assert report["blocking_lanes"] == []
    assert report["lanes"]["whisper"]["module_failures"]["mlx-whisper"] == {
        "reason": "native_crash",
        "termination": "signal",
        "signal_number": signal.SIGABRT,
        "signal_name": "SIGABRT",
    }


def test_native_whisper_failure_blocks_when_whisper_is_required(
    monkeypatch, capsys
) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "mlx_whisper":
            return _failed_probe(
                "native_crash",
                termination="exit",
                exit_code=134,
            )
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    exit_code = check_runtime.main(
        ["--lanes", "whisper", "--require-lanes", "core,whisper"]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["blocking_lanes"] == ["whisper"]
    assert payload["degraded_lanes"] == []
    assert payload["lanes"]["whisper"]["module_failures"]["mlx-whisper"] == {
        "reason": "native_crash",
        "termination": "exit",
        "exit_code": 134,
    }
    assert "unavailable for required lanes whisper" in captured.err
    assert "then rerun this check" in captured.err


def test_main_reports_blocking_lanes_with_recovery_step(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_runtime,
        "_probe_module",
        lambda _name: _failed_probe("unavailable_import"),
    )
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    assert check_runtime.main(["--lanes", "core"]) == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["blocking_lanes"] == ["core"]
    assert "install the missing modules or commands" in captured.err
    assert "then rerun this check" in captured.err


def test_main_reports_degraded_lane_with_one_json_and_recovery(
    monkeypatch, capsys
) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "mlx_whisper":
            return _failed_probe(
                "native_crash",
                termination="signal",
                signal_number=signal.SIGABRT,
                signal_name="SIGABRT",
            )
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    assert check_runtime.main(["--lanes", "whisper", "--require-lanes", "core"]) == 0

    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["degraded_lanes"] == ["whisper"]
    assert payload["lanes"]["whisper"]["module_failures"]["mlx-whisper"] == {
        "reason": "native_crash",
        "termination": "signal",
        "signal_number": signal.SIGABRT,
        "signal_name": "SIGABRT",
    }
    assert "degraded for optional lanes whisper" in captured.err
    assert "then rerun this check" in captured.err


def test_outer_boundary_emits_one_json_failure_for_unexpected_probe_fault(
    monkeypatch, capsys
) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise ValueError("dependency initialization is corrupt")

    monkeypatch.setattr("subprocess.run", broken)
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

    assert check_runtime.REPORT_SCHEMA_VERSION == 3
    assert requirements["outline"] == {
        "modules": {"PyYAML": "yaml", "pydantic": "pydantic"},
        "commands": {},
    }
    assert requirements["pdf"]["modules"] == {
        "pypdf": "pypdf",
        "psutil": "psutil",
    }
    assert requirements["pptx"]["modules"] == {
        "python-pptx": "pptx",
        "psutil": "psutil",
    }
    assert requirements["google-drive"]["modules"] == {"gdown": "gdown"}
    assert requirements["captions"]["commands"] == {}
    assert requirements["youtube-download"]["commands"] == {"yt-dlp": "yt-dlp"}
    assert requirements["youtube-download"]["modules"] == {"psutil": "psutil"}
    assert requirements["whisper"] == {
        "modules": {"mlx-whisper": "mlx_whisper", "psutil": "psutil"},
        "commands": {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"},
    }
    assert requirements["source-media"] == {
        "modules": {"psutil": "psutil"},
        "commands": {"ffprobe": "ffprobe"},
    }
    assert requirements["source-video"] == {
        "modules": {"psutil": "psutil"},
        "commands": {"ffprobe": "ffprobe"},
    }
    assert requirements["video"]["modules"] == {
        "filelock": "filelock",
        "imagehash": "imagehash",
        "numpy": "numpy",
        "Pillow": "PIL",
    }
    assert requirements["pdf-render"]["commands"] == {"pdftoppm": "pdftoppm"}
    assert requirements["markdown-deck-presenterm"] == {
        "modules": {},
        "commands": {"presenterm": "presenterm", "weasyprint": "weasyprint"},
    }
    assert requirements["markdown-deck-slidev"]["commands"] == {"slidev": "slidev"}
    assert requirements["markdown-deck-marp"]["commands"] == {"marp": "marp"}
    assert requirements["markdown-deck-reveal-md"]["commands"] == {
        "reveal-md": "reveal-md"
    }


def test_no_markdown_deck_lane_is_selected_or_required_by_default() -> None:
    """A vault authors decks in one tool, so none of the four is a default."""
    markdown_lanes = {
        lane
        for lane in check_runtime.LANE_REQUIREMENTS
        if lane.startswith("markdown-deck-")
    }

    assert markdown_lanes
    assert markdown_lanes.isdisjoint(check_runtime.DEFAULT_LANES)
    assert markdown_lanes.isdisjoint(check_runtime.DEFAULT_REQUIRED_LANES)


@pytest.mark.parametrize("required", [False, True])
def test_missing_media_supervision_is_lane_local(monkeypatch, required):
    monkeypatch.setattr(
        check_runtime,
        "_probe_module",
        lambda name: (
            _failed_probe("unavailable_import")
            if name == "psutil"
            else _available_probe()
        ),
    )
    monkeypatch.setattr(check_runtime, "_command_available", lambda name: True)
    lanes = ("source-media", "whisper", "captions")
    report = check_runtime.build_report(
        lanes, ("core", "source-media") if required else ("core",)
    )
    assert report["ok"] is (not required)
    assert report["lanes"]["captions"]["available"] is True
    assert report["lanes"]["source-media"]["missing_modules"] == ["psutil"]
    assert report["lanes"]["whisper"]["missing_modules"] == ["psutil"]
    assert ("source-media" in report["blocking_lanes"]) is required


def test_generic_media_gate_does_not_require_whisper_or_video_extraction(monkeypatch):
    inspected = []

    def probe(name):
        inspected.append(name)
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(
        check_runtime, "_command_available", lambda name: name == "ffprobe"
    )
    report = check_runtime.build_report(("source-media",), ("core", "source-media"))
    assert report["ok"] is True
    assert set(inspected) == {"yaml", "psutil"}


def test_an_absent_markdown_deck_lane_degrades_rather_than_blocks() -> None:
    report = check_runtime.build_report(("markdown-deck-slidev",), ("core",))
    lane = report["lanes"]["markdown-deck-slidev"]

    assert lane["required"] is False
    if not lane["available"]:
        assert "markdown-deck-slidev" in report["degraded_lanes"]
        assert "markdown-deck-slidev" not in report["blocking_lanes"]


def test_resolved_ytdlp_makes_the_download_lane_available(monkeypatch) -> None:
    monkeypatch.setattr(
        check_runtime, "_probe_module", lambda _name: _available_probe()
    )
    monkeypatch.setattr(
        check_runtime, "resolve_ytdlp", lambda: Path("/runtime/bin/yt-dlp")
    )

    report = check_runtime.build_report(("youtube-download",), ("core",))

    assert report["lanes"]["youtube-download"]["available"] is True
    assert report["degraded_lanes"] == []


def test_unresolvable_ytdlp_degrades_the_download_lane(monkeypatch) -> None:
    def missing() -> Path:
        raise check_runtime.YtDlpResolutionError("ytdlp_not_found", "not found")

    monkeypatch.setattr(
        check_runtime, "_probe_module", lambda _name: _available_probe()
    )
    monkeypatch.setattr(check_runtime, "resolve_ytdlp", missing)

    report = check_runtime.build_report(("youtube-download",), ("core",))
    lane = report["lanes"]["youtube-download"]

    assert lane["available"] is False
    assert lane["missing_commands"] == ["yt-dlp"]
    assert lane["command_failures"] == {"yt-dlp": {"reason": "ytdlp_not_found"}}
    assert report["degraded_lanes"] == ["youtube-download"]


# A probe that never answered is not a missing module (#444).


def test_a_timed_out_probe_is_reported_as_unresolved_not_merely_missing(
    monkeypatch,
) -> None:
    """An interpreter on a network filesystem reads its dependencies over the
    network on a cold import, so a healthy install can blow the probe budget."""

    def probe(name: str) -> dict[str, object]:
        if name == "pptx":
            return check_runtime._failed_module_probe("timeout", timeout_seconds=30)
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(("core", "pptx"), ("core",))

    lane = report["lanes"]["pptx"]
    assert lane["available"] is False
    assert lane["unresolved_modules"] == ["python-pptx"]
    # Still in missing_modules, so every existing reader is unaffected.
    assert lane["missing_modules"] == ["python-pptx"]
    assert check_runtime.unresolved_module_probes(report) == {"python-pptx": "timeout"}


def test_an_absent_module_is_not_reported_as_unresolved(monkeypatch) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "pptx":
            return _failed_probe("unavailable_import")
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(("core", "pptx"), ("core",))

    assert report["lanes"]["pptx"]["missing_modules"] == ["python-pptx"]
    assert report["lanes"]["pptx"]["unresolved_modules"] == []
    assert check_runtime.unresolved_module_probes(report) == {}


def test_a_healthy_lane_reports_no_unresolved_modules(monkeypatch) -> None:
    monkeypatch.setattr(check_runtime, "_probe_module", lambda _n: _available_probe())
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(("core",), ("core",))

    assert report["lanes"]["core"]["unresolved_modules"] == []
    assert check_runtime.unresolved_module_probes(report) == {}


def test_the_stderr_advice_names_the_module_and_the_warming_repair(
    monkeypatch, capsys
) -> None:
    """The message that misled this project: 'install the missing modules' for a
    package that was installed and merely cold."""

    def probe(name: str) -> dict[str, object]:
        if name == "pptx":
            return check_runtime._failed_module_probe("timeout", timeout_seconds=30)
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    exit_code = check_runtime.main(["--lanes", "core,pptx", "--require-lanes", "pptx"])

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "python-pptx (timeout)" in stderr
    assert "warm" in stderr
    assert "before reinstalling anything" in stderr


def test_the_stderr_advice_stays_silent_when_every_probe_answered(
    monkeypatch, capsys
) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "pptx":
            return _failed_probe("unavailable_import")
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    check_runtime.main(["--lanes", "core,pptx", "--require-lanes", "pptx"])

    stderr = capsys.readouterr().err
    assert "install the missing modules" in stderr
    assert "did not resolve" not in stderr

"""Tests for the stdlib-only vault-ingress runtime probe."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import signal
import subprocess
import sys
from types import SimpleNamespace

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

SUPERVISOR_SCRIPT = SCRIPT.with_name("artifact_supervisor.py")
SUPERVISOR_SPEC = importlib.util.spec_from_file_location(
    "artifact_supervisor_runtime_contract",
    SUPERVISOR_SCRIPT,
)
assert SUPERVISOR_SPEC is not None and SUPERVISOR_SPEC.loader is not None
artifact_supervisor = importlib.util.module_from_spec(SUPERVISOR_SPEC)
sys.modules[SUPERVISOR_SPEC.name] = artifact_supervisor
SUPERVISOR_SPEC.loader.exec_module(artifact_supervisor)
PYPROJECT = SCRIPT.parents[3] / "pyproject.toml"


def _available_probe() -> dict[str, object]:
    return {"available": True, "failure": None}


def _failed_probe(reason: str, **details: object) -> dict[str, object]:
    failure: dict[str, object] = {"reason": reason}
    failure.update(details)
    return {"available": False, "failure": failure}


def _completed_probe(
    command: list[str],
    payload: dict[str, object] | str | bytes | None,
    *,
    returncode: int = 0,
) -> subprocess.CompletedProcess[object]:
    if payload is not None:
        if isinstance(payload, dict):
            raw = (json.dumps(payload) + "\n").encode("utf-8")
        elif isinstance(payload, str):
            raw = payload.encode("utf-8")
        else:
            raw = payload
        Path(command[-1]).write_bytes(raw)
    return subprocess.CompletedProcess(
        args=command,
        returncode=returncode,
    )


def _assert_probe_result_removed(result_path: Path) -> None:
    assert not result_path.exists()
    assert not result_path.parent.exists()


def _plain_child_environment() -> dict[str, str]:
    """Return an environment whose child writes uncolored tracebacks.

    Python 3.13+ colorizes a traceback when `FORCE_COLOR` is set, and a
    terminal multiplexer or CI runner that exports it turns an assertion on the
    child's stderr text into an assertion on ANSI escapes.
    """
    env = os.environ.copy()
    env["PYTHON_COLORS"] = "0"
    return env


def _child_probe_environment(module_directory: Path) -> dict[str, str]:
    env = _plain_child_environment()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{module_directory}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(module_directory)
    )
    return env


def _run_child_probe(
    module_name: str,
    result_path: Path,
    *,
    module_directory: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = (
        _child_probe_environment(module_directory)
        if module_directory is not None
        else _plain_child_environment()
    )
    with result_path.open("x+b", buffering=0):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                check_runtime.MODULE_PROBE_CHILD_FLAG,
                module_name,
                str(result_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=check_runtime.MODULE_PROBE_TIMEOUT_SECONDS + 5,
        )


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
    assert report["lanes"]["pdf"]["required_module_versions"] == {"psutil": "7.2.2"}
    assert report["lanes"]["pptx"]["missing_modules"] == ["psutil"]
    assert report["lanes"]["pptx"]["module_failures"] == {
        "psutil": {"reason": "unavailable_import"}
    }
    assert report["lanes"]["pptx"]["required_module_versions"] == {"psutil": "7.2.2"}


def test_incompatible_psutil_reports_exact_version_for_supervised_lanes(
    monkeypatch,
) -> None:
    def probe(name: str) -> dict[str, object]:
        if name == "psutil":
            return _failed_probe(
                "incompatible_version",
                required_version="7.2.2",
                actual_version="7.2.1",
            )
        return _available_probe()

    monkeypatch.setattr(check_runtime, "_probe_module", probe)
    monkeypatch.setattr(check_runtime, "_command_available", lambda _name: True)

    report = check_runtime.build_report(
        ("pdf", "pptx"),
        ("core", "pdf", "pptx"),
    )

    assert report["ok"] is False
    assert report["blocking_lanes"] == ["pdf", "pptx"]
    for lane in ("pdf", "pptx"):
        assert report["lanes"][lane]["missing_modules"] == ["psutil"]
        assert report["lanes"][lane]["module_failures"]["psutil"] == {
            "reason": "incompatible_version",
            "required_version": "7.2.2",
            "actual_version": "7.2.1",
        }
        assert report["lanes"][lane]["required_module_versions"] == {"psutil": "7.2.2"}


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


def test_module_probe_child_contains_expected_import_failures(
    monkeypatch,
) -> None:
    def unavailable(_name: str) -> None:
        raise ImportError("dependency is not installed")

    monkeypatch.setattr(check_runtime.importlib, "import_module", unavailable)

    assert check_runtime._module_probe_child("missing") == {
        "available": False,
        "exception_type": "ImportError",
        "failure_reason": "unavailable_import",
        "schema_version": 1,
    }


@pytest.mark.parametrize(
    ("actual_version", "available"),
    [("7.2.2", True), ("7.2.1", False), (None, False)],
)
def test_module_probe_child_requires_exact_psutil_version(
    actual_version: str | None,
    available: bool,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        check_runtime.importlib,
        "import_module",
        lambda _name: SimpleNamespace(__version__=actual_version),
    )

    result = check_runtime._module_probe_child("psutil")

    if available:
        assert result == {"available": True, "schema_version": 1}
    else:
        assert result == {
            "actual_version": actual_version,
            "available": False,
            "failure_reason": "incompatible_version",
            "required_version": "7.2.2",
            "schema_version": 1,
        }


def test_module_probe_child_quarantines_dependency_output(
    tmp_path: Path,
) -> None:
    module_name = "speaker_toolkit_test_noisy_initializer"
    (tmp_path / f"{module_name}.py").write_text(
        'print("dependency stdout")\n'
        "import sys\n"
        'print("dependency stderr", file=sys.stderr)\n',
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"

    completed = _run_child_probe(
        module_name,
        result_path,
        module_directory=tmp_path,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert completed.stdout == ""
    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "available": True,
        "schema_version": 1,
    }


def test_child_result_protocol_supports_paths_with_spaces(tmp_path: Path) -> None:
    result_directory = tmp_path / "result directory with spaces"
    result_directory.mkdir()
    result_path = result_directory / "probe result with spaces.json"

    completed = _run_child_probe("json", result_path)

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert completed.stdout == ""
    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "available": True,
        "schema_version": 1,
    }


def test_child_path_replacement_cannot_redirect_retained_descriptors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module_name = "speaker_toolkit_test_result_path_replacement"
    decoy_payload = (
        b'{"available": false, "exception_type": "Redirected", '
        b'"failure_reason": "initializer_exception", "schema_version": 1}\n'
    )
    (tmp_path / f"{module_name}.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "result_path = Path(sys.argv[3])\n"
        "try:\n"
        "    result_path.unlink()\n"
        f"    result_path.write_bytes({decoy_payload!r})\n"
        "except OSError:\n"
        "    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "PYTHONPATH",
        _child_probe_environment(tmp_path)["PYTHONPATH"],
    )

    result = check_runtime._probe_module(module_name)

    assert result == _available_probe()


@pytest.mark.parametrize("exception_class", [RuntimeError, OSError])
def test_module_probe_child_propagates_initializer_exceptions(
    exception_class: type[Exception],
    monkeypatch,
) -> None:
    def broken(_name: str) -> None:
        raise exception_class("initializer failed")

    monkeypatch.setattr(check_runtime.importlib, "import_module", broken)

    with pytest.raises(exception_class, match="initializer failed"):
        check_runtime._module_probe_child("broken")


def test_module_probe_uses_exact_interpreter_and_bounded_timeout(monkeypatch) -> None:
    observed: dict[str, object] = {}
    configured_interpreter = "/configured/vault/.venv/bin/python3"
    monkeypatch.setattr(check_runtime.sys, "executable", configured_interpreter)

    def runner(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        observed["command"] = command
        observed["kwargs"] = kwargs
        result_path = Path(command[-1])
        assert result_path.parent.is_dir()
        completed = _completed_probe(
            command,
            {"schema_version": 1, "available": True},
        )
        assert result_path.is_file()
        return completed

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _available_probe()
    command = observed["command"]
    assert isinstance(command, list)
    assert command[:4] == [
        configured_interpreter,
        str(SCRIPT.resolve()),
        check_runtime.MODULE_PROBE_CHILD_FLAG,
        "mlx_whisper",
    ]
    assert len(command) == 5
    result_path = Path(command[4])
    assert result_path.name == "result.json"
    _assert_probe_result_removed(result_path)
    assert observed["kwargs"] == {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "check": False,
        "timeout": check_runtime.MODULE_PROBE_TIMEOUT_SECONDS,
    }


@pytest.mark.parametrize(
    ("failure_reason", "exception_type"),
    [
        ("unavailable_import", "ModuleNotFoundError"),
        ("initializer_exception", "ValueError"),
    ],
)
def test_module_probe_preserves_child_failure_reason(
    failure_reason: str,
    exception_type: str,
) -> None:
    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        return _completed_probe(
            command,
            {
                "schema_version": 1,
                "available": False,
                "failure_reason": failure_reason,
                "exception_type": exception_type,
            },
        )

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        failure_reason,
        exception_type=exception_type,
    )


@pytest.mark.parametrize(
    ("module_name", "required_version", "actual_version"),
    [
        ("psutil", "7.2.2", "7.2.1"),
        ("filelock", "3.32.2", "3.25.0"),
    ],
)
def test_module_probe_preserves_incompatible_version_report(
    module_name: str,
    required_version: str,
    actual_version: str,
) -> None:
    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        return _completed_probe(
            command,
            {
                "schema_version": 1,
                "available": False,
                "failure_reason": "incompatible_version",
                "required_version": required_version,
                "actual_version": actual_version,
            },
        )

    result = check_runtime._probe_module(module_name, runner=runner)

    assert result == _failed_probe(
        "incompatible_version",
        required_version=required_version,
        actual_version=actual_version,
    )


def test_module_probe_classifies_sigabrt_as_native_crash() -> None:
    observed_result_paths: list[Path] = []

    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        result_path = Path(command[-1])
        observed_result_paths.append(result_path)
        assert result_path.parent.is_dir()
        completed = _completed_probe(
            command,
            b"partial result",
            returncode=-signal.SIGABRT,
        )
        assert result_path.is_file()
        return completed

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "native_crash",
        termination="signal",
        signal_number=signal.SIGABRT,
        signal_name="SIGABRT",
    )
    assert len(observed_result_paths) == 1
    _assert_probe_result_removed(observed_result_paths[0])


def test_module_probe_classifies_nonzero_native_style_exit() -> None:
    observed_result_paths: list[Path] = []

    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        result_path = Path(command[-1])
        observed_result_paths.append(result_path)
        assert result_path.parent.is_dir()
        completed = _completed_probe(
            command,
            b"partial result",
            returncode=134,
        )
        assert result_path.is_file()
        return completed

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "native_crash",
        termination="exit",
        exit_code=134,
    )
    assert len(observed_result_paths) == 1
    _assert_probe_result_removed(observed_result_paths[0])


@pytest.mark.parametrize(
    ("payload", "malformation"),
    [
        (None, "empty"),
        ("", "empty"),
        (b"\xff", "invalid_utf8"),
        ("not-json\n", "invalid_json"),
        (
            '{"available": true, "available": false, "schema_version": 1}\n',
            "invalid_json",
        ),
        ('{"available": NaN, "schema_version": 1}\n', "invalid_json"),
        ('{"available": true}\n', "invalid_payload"),
        (
            '{"available": false, "exception_type": "ValueError", '
            '"failure_reason": [], "schema_version": 1}\n',
            "invalid_payload",
        ),
        (
            '{"actual_version": "7.2.1", "available": false, '
            '"failure_reason": "incompatible_version", '
            '"required_version": "7.2.1", "schema_version": 1}\n',
            "invalid_payload",
        ),
        ('{"available": true, "schema_version": 1}\nextra\n', "multiple_lines"),
    ],
)
def test_module_probe_rejects_empty_or_malformed_child_output(
    payload: str | bytes | None,
    malformation: str,
) -> None:
    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        return _completed_probe(command, payload)

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "malformed_child_output",
        malformation=malformation,
    )


def test_module_probe_rejects_oversized_child_output() -> None:
    oversized = b"x" * (check_runtime.MODULE_PROBE_MAX_OUTPUT_BYTES + 1)

    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        return _completed_probe(command, oversized)

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "malformed_child_output",
        malformation="oversized",
    )


def test_module_probe_has_no_posix_open_flag_dependency(monkeypatch) -> None:
    class OsWithoutPosixOpenFlags:
        def __getattr__(self, name: str) -> object:
            if name in {"O_NONBLOCK", "O_NOFOLLOW"}:
                raise AssertionError(f"unexpected POSIX-only flag access: {name}")
            return getattr(os, name)

    monkeypatch.setattr(check_runtime, "os", OsWithoutPosixOpenFlags())

    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        return _completed_probe(
            command,
            {"schema_version": 1, "available": True},
        )

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _available_probe()


def test_module_probe_bounds_retained_descriptor_read(monkeypatch) -> None:
    observed_payload_lengths: list[int] = []
    decode = check_runtime._decode_module_probe_child

    def recording_decode(raw: bytes) -> dict[str, object]:
        observed_payload_lengths.append(len(raw))
        return decode(raw)

    monkeypatch.setattr(
        check_runtime,
        "_decode_module_probe_child",
        recording_decode,
    )

    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        return _completed_probe(command, b"x" * 1_000_000)

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "malformed_child_output",
        malformation="oversized",
    )
    assert observed_payload_lengths == [check_runtime.MODULE_PROBE_MAX_OUTPUT_BYTES + 1]


@pytest.mark.skipif(
    not hasattr(os, "mkfifo"),
    reason="requires POSIX FIFOs",
)
def test_module_probe_reads_retained_descriptor_after_fifo_replacement() -> None:
    observed_result_paths: list[Path] = []

    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        result_path = Path(command[-1])
        observed_result_paths.append(result_path)
        assert result_path.is_file()
        result_path.unlink()
        os.mkfifo(result_path)
        return subprocess.CompletedProcess(args=command, returncode=0)

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "malformed_child_output",
        malformation="empty",
    )
    assert len(observed_result_paths) == 1
    _assert_probe_result_removed(observed_result_paths[0])


def test_module_probe_reads_retained_descriptor_after_symlink_replacement(
    tmp_path: Path,
) -> None:
    target_path = tmp_path / "valid-target.json"
    target_payload = b'{"available": true, "schema_version": 1}\n'
    target_path.write_bytes(target_payload)
    observed_result_paths: list[Path] = []

    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        result_path = Path(command[-1])
        observed_result_paths.append(result_path)
        assert result_path.is_file()
        try:
            result_path.unlink()
            result_path.symlink_to(target_path)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc}")
        return subprocess.CompletedProcess(args=command, returncode=0)

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "malformed_child_output",
        malformation="empty",
    )
    assert target_path.read_bytes() == target_payload
    assert len(observed_result_paths) == 1
    _assert_probe_result_removed(observed_result_paths[0])


@pytest.mark.parametrize("schema_version", [True, 1.0])
def test_module_probe_requires_exact_integer_schema_version(
    schema_version: object,
) -> None:
    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        return _completed_probe(
            command,
            {"schema_version": schema_version, "available": True},
        )

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "malformed_child_output",
        malformation="invalid_payload",
    )


def test_module_probe_contains_recursive_json_decoder_failure(monkeypatch) -> None:
    def recursive_json(*_args: object, **_kwargs: object) -> object:
        raise RecursionError("child JSON is too deeply nested")

    monkeypatch.setattr(check_runtime.json, "loads", recursive_json)

    result = check_runtime._decode_module_probe_child(b"{}")

    assert result == _failed_probe(
        "malformed_child_output",
        malformation="invalid_json",
    )


def test_module_probe_timeout_is_a_bounded_failure() -> None:
    observed_result_paths: list[Path] = []

    def runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        result_path = Path(command[-1])
        observed_result_paths.append(result_path)
        assert result_path.parent.is_dir()
        result_path.write_bytes(b"partial result")
        assert result_path.is_file()
        raise subprocess.TimeoutExpired(
            cmd="module-probe",
            timeout=check_runtime.MODULE_PROBE_TIMEOUT_SECONDS,
        )

    result = check_runtime._probe_module("mlx_whisper", runner=runner)

    assert result == _failed_probe(
        "timeout",
        timeout_seconds=check_runtime.MODULE_PROBE_TIMEOUT_SECONDS,
    )
    assert len(observed_result_paths) == 1
    _assert_probe_result_removed(observed_result_paths[0])


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


@pytest.mark.parametrize("exception_type", ["ValueError", "RuntimeError", "OSError"])
def test_child_outer_boundary_reports_python_initializer_exception(
    tmp_path: Path,
    exception_type: str,
) -> None:
    module_name = f"speaker_toolkit_test_{exception_type.lower()}_initializer"
    (tmp_path / f"{module_name}.py").write_text(
        f'raise {exception_type}("initializer is corrupt")\n',
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"

    completed = _run_child_probe(
        module_name,
        result_path,
        module_directory=tmp_path,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert completed.stdout == ""
    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "available": False,
        "exception_type": exception_type,
        "failure_reason": "initializer_exception",
        "schema_version": 1,
    }


def test_child_outer_boundary_does_not_reclassify_result_write_fault(
    tmp_path: Path,
) -> None:
    module_name = "speaker_toolkit_test_result_write_fault"
    (tmp_path / f"{module_name}.py").write_text(
        "import sys\n"
        "def fail_result_write(*_args, **_kwargs):\n"
        '    raise OSError("result write failed")\n'
        'sys.modules["__main__"]._write_module_probe_result = fail_result_write\n',
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"

    completed = _run_child_probe(
        module_name,
        result_path,
        module_directory=tmp_path,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "OSError: result write failed" in completed.stderr
    assert result_path.read_bytes() == b""


def test_child_outer_boundary_does_not_reclassify_output_setup_fault(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result_path = tmp_path / "result.json"

    def fail_output_setup(*_args: object, **_kwargs: object) -> None:
        raise OSError("dependency-output setup failed")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            check_runtime.MODULE_PROBE_CHILD_FLAG,
            "json",
            str(result_path),
        ],
    )

    with result_path.open("x+b", buffering=0):
        with pytest.raises(OSError, match="dependency-output setup failed"):
            runpy.run_path(
                str(SCRIPT),
                init_globals={"open": fail_output_setup},
                run_name="__main__",
            )

    assert result_path.read_bytes() == b""


def test_child_outer_boundary_does_not_reclassify_output_teardown_fault(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result_path = tmp_path / "result.json"

    class FailingTeardown:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_args: object) -> None:
            raise OSError("dependency-output teardown failed")

    monkeypatch.setattr(
        check_runtime.contextlib,
        "redirect_stderr",
        lambda _target: FailingTeardown(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            check_runtime.MODULE_PROBE_CHILD_FLAG,
            "json",
            str(result_path),
        ],
    )

    with result_path.open("x+b", buffering=0):
        with pytest.raises(OSError, match="dependency-output teardown failed"):
            runpy.run_path(str(SCRIPT), run_name="__main__")

    assert result_path.read_bytes() == b""


def test_module_probe_discards_large_process_fd_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module_name = "speaker_toolkit_test_large_fd_output"
    (tmp_path / f"{module_name}.py").write_text(
        'import os\nos.write(1, b"x" * 1_000_000)\nos.write(2, b"y" * 1_000_000)\n',
        encoding="utf-8",
    )
    existing_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath = (
        f"{tmp_path}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(tmp_path)
    )
    monkeypatch.setenv("PYTHONPATH", pythonpath)

    result = check_runtime._probe_module(module_name)

    assert result == _available_probe()


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
    assert check_runtime.MODULE_PROBE_SCHEMA_VERSION == 1
    assert check_runtime.PSUTIL_REQUIRED_VERSION == "7.2.2"
    assert check_runtime.FILELOCK_REQUIRED_VERSION == "3.32.2"
    assert check_runtime.IMAGEHASH_REQUIRED_VERSION == "4.3.2"
    assert check_runtime.NUMPY_REQUIRED_VERSION == "2.2.6"
    assert check_runtime.PILLOW_REQUIRED_VERSION == "12.3.0"
    assert check_runtime.YTDLP_REQUIRED_VERSION == "2026.8.19"
    assert check_runtime.REQUIRED_MODULE_VERSIONS == {
        "PIL": "12.3.0",
        "filelock": "3.32.2",
        "imagehash": "4.3.2",
        "numpy": "2.2.6",
        "psutil": "7.2.2",
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


def test_psutil_version_authorities_are_synchronized() -> None:
    manifest = PYPROJECT.read_text(encoding="utf-8")
    manifest_versions = re.findall(
        r'^\s*"psutil==([^"\s]+)",\s*$',
        manifest,
        flags=re.MULTILINE,
    )

    assert manifest_versions == [check_runtime.PSUTIL_REQUIRED_VERSION]
    assert (
        artifact_supervisor.PSUTIL_REQUIRED_VERSION
        == check_runtime.PSUTIL_REQUIRED_VERSION
    )


def test_ytdlp_version_authority_is_synchronized() -> None:
    manifest = PYPROJECT.read_text(encoding="utf-8")
    manifest_versions = re.findall(
        r'^\s*"yt-dlp==([^"\s]+)",\s*$',
        manifest,
        flags=re.MULTILINE,
    )

    assert manifest_versions == [check_runtime.YTDLP_REQUIRED_VERSION]


def test_ytdlp_probe_accepts_the_pinned_zero_padded_version(monkeypatch) -> None:
    monkeypatch.setattr(
        check_runtime, "resolve_ytdlp", lambda: Path("/runtime/bin/yt-dlp")
    )

    probe = check_runtime._probe_command(
        "yt-dlp",
        "yt-dlp",
        runner=lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="2026.08.19\n",
            stderr="",
        ),
    )

    assert probe == {"available": True, "failure": None}


def test_stale_ytdlp_version_degrades_the_download_lane(monkeypatch) -> None:
    monkeypatch.setattr(
        check_runtime, "_probe_module", lambda _name: _available_probe()
    )
    monkeypatch.setattr(
        check_runtime, "resolve_ytdlp", lambda: Path("/runtime/bin/yt-dlp")
    )
    monkeypatch.setattr(
        check_runtime.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="2026.06.09\n",
            stderr="",
        ),
    )

    report = check_runtime.build_report(("youtube-download",), ("core",))
    lane = report["lanes"]["youtube-download"]

    assert lane["available"] is False
    assert lane["commands"] == {"yt-dlp": False}
    assert lane["missing_commands"] == ["yt-dlp"]
    assert lane["required_command_versions"] == {"yt-dlp": "2026.8.19"}
    assert lane["command_failures"] == {
        "yt-dlp": {
            "reason": "incompatible_version",
            "required_version": "2026.8.19",
            "actual_version": "2026.06.09",
        }
    }
    assert report["degraded_lanes"] == ["youtube-download"]


def test_video_dependency_version_authorities_are_synchronized() -> None:
    manifest = PYPROJECT.read_text(encoding="utf-8")
    reference = (
        PYPROJECT.parent
        / "skills"
        / "vault-ingress"
        / "references"
        / "video-slide-extraction.md"
    ).read_text(encoding="utf-8")

    expected_versions = {
        "filelock": check_runtime.FILELOCK_REQUIRED_VERSION,
        "ImageHash": check_runtime.IMAGEHASH_REQUIRED_VERSION,
        "numpy": check_runtime.NUMPY_REQUIRED_VERSION,
        "Pillow": check_runtime.PILLOW_REQUIRED_VERSION,
    }
    for package, required_version in expected_versions.items():
        manifest_versions = re.findall(
            rf'^\s*"{package}==([^"\s]+)",\s*$',
            manifest,
            flags=re.MULTILINE,
        )
        assert manifest_versions == [required_version]
        assert f'"{package}=={required_version}"' in reference

#!/usr/bin/env python3
"""Check imports and commands in the configured vault-ingress runtime.

The installed plugin does not ship ``pyproject.toml``. This stdlib-only probe is
the executable dependency contract for the interpreter recorded in
``config.python_path``. Core failures block ingress. Recognized missing or
incompatible optional dependencies are reported as degradation unless the
caller explicitly requires that lane. Isolated import faults remain lane-local.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Callable, TypedDict

from ytdlp_runtime import (
    YTDLP_REQUIRED_VERSION,
    YtDlpResolutionError,
    normalized_ytdlp_version,
    resolve_ytdlp,
)


REPORT_SCHEMA_VERSION = 3
MODULE_PROBE_SCHEMA_VERSION = 1
MODULE_PROBE_TIMEOUT_SECONDS = 30
MODULE_PROBE_MAX_OUTPUT_BYTES = 4096
MODULE_PROBE_CHILD_FLAG = "--module-probe-child"
MINIMUM_PYTHON = (3, 10)
PSUTIL_REQUIRED_VERSION = "7.2.2"
FILELOCK_REQUIRED_VERSION = "3.32.2"
IMAGEHASH_REQUIRED_VERSION = "4.3.2"
NUMPY_REQUIRED_VERSION = "2.2.6"
PILLOW_REQUIRED_VERSION = "12.3.0"
REQUIRED_MODULE_VERSIONS = {
    "PIL": PILLOW_REQUIRED_VERSION,
    "filelock": FILELOCK_REQUIRED_VERSION,
    "imagehash": IMAGEHASH_REQUIRED_VERSION,
    "numpy": NUMPY_REQUIRED_VERSION,
    "psutil": PSUTIL_REQUIRED_VERSION,
}
LANE_REQUIREMENTS: dict[str, dict[str, dict[str, str]]] = {
    "core": {
        "modules": {"PyYAML": "yaml"},
        "commands": {},
    },
    "pdf": {
        "modules": {"pypdf": "pypdf", "psutil": "psutil"},
        "commands": {},
    },
    "pptx": {
        "modules": {"python-pptx": "pptx", "psutil": "psutil"},
        "commands": {},
    },
    "google-drive": {
        "modules": {"gdown": "gdown"},
        "commands": {},
    },
    "captions": {
        "modules": {
            "youtube-transcript-api": "youtube_transcript_api",
        },
        "commands": {},
    },
    "youtube-download": {
        "modules": {"psutil": "psutil"},
        "commands": {"yt-dlp": "yt-dlp"},
    },
    "whisper": {
        "modules": {"mlx-whisper": "mlx_whisper", "psutil": "psutil"},
        "commands": {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"},
    },
    "speech-calibration": {
        "modules": {
            "mlx-whisper": "mlx_whisper",
            "huggingface-hub": "huggingface_hub",
            "psutil": "psutil",
        },
        "commands": {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"},
    },
    "source-media": {
        "modules": {"psutil": "psutil"},
        "commands": {"ffprobe": "ffprobe"},
    },
    "source-video": {
        "modules": {"psutil": "psutil"},
        "commands": {"ffprobe": "ffprobe"},
    },
    "video": {
        "modules": {
            "filelock": "filelock",
            "imagehash": "imagehash",
            "numpy": "numpy",
            "Pillow": "PIL",
        },
        "commands": {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"},
    },
    "pdf-render": {
        "modules": {},
        "commands": {"pdftoppm": "pdftoppm"},
    },
    # One lane per markdown deck tool rather than one `markdown-deck` lane over
    # all four. A lane is an AND over its commands, and no vault authors decks
    # in every tool at once: a single lane would report a presenterm-only vault
    # as degraded for the three renderers it will never call. Each degrades on
    # its own, and `render-markdown-deck.py` requires exactly the one the deck's
    # detected flavor names.
    "markdown-deck-presenterm": {
        "modules": {},
        # presenterm shells out to weasyprint for the PDF itself.
        "commands": {"presenterm": "presenterm", "weasyprint": "weasyprint"},
    },
    "markdown-deck-slidev": {
        "modules": {},
        "commands": {"slidev": "slidev"},
    },
    "markdown-deck-marp": {
        "modules": {},
        "commands": {"marp": "marp"},
    },
    "markdown-deck-reveal-md": {
        "modules": {},
        "commands": {"reveal-md": "reveal-md"},
    },
}
DEFAULT_LANES = ("core", "pdf", "pptx")
DEFAULT_REQUIRED_LANES = ("core",)


class ModuleProbeResult(TypedDict):
    """Parent-side result for one isolated dependency import."""

    available: bool
    failure: dict[str, object] | None


class CommandProbeResult(TypedDict):
    """Result for one executable dependency probe."""

    available: bool
    failure: dict[str, object] | None


def _failed_module_probe(reason: str, **details: object) -> ModuleProbeResult:
    failure: dict[str, object] = {"reason": reason}
    failure.update(details)
    return {"available": False, "failure": failure}


def _write_module_probe_result(
    result_file: BinaryIO,
    payload: dict[str, object],
) -> None:
    """Replace the pre-created child result through its retained descriptor."""
    rendered = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    result_file.seek(0)
    result_file.truncate()
    remaining = memoryview(rendered)
    while remaining:
        written = result_file.write(remaining)
        if written is None or written <= 0:
            raise OSError("module probe result write made no progress")
        remaining = remaining[written:]
    result_file.flush()


def _module_probe_child(import_name: str) -> dict[str, object]:
    """Import one module and return the private child-process payload."""
    try:
        module = importlib.import_module(import_name)
    except ImportError as exc:
        return {
            "schema_version": MODULE_PROBE_SCHEMA_VERSION,
            "available": False,
            "failure_reason": "unavailable_import",
            "exception_type": type(exc).__name__,
        }
    required_version = REQUIRED_MODULE_VERSIONS.get(import_name)
    if required_version is not None:
        actual_version = getattr(module, "__version__", None)
        if actual_version != required_version:
            return {
                "schema_version": MODULE_PROBE_SCHEMA_VERSION,
                "available": False,
                "failure_reason": "incompatible_version",
                "required_version": required_version,
                "actual_version": (
                    actual_version
                    if isinstance(actual_version, str) and len(actual_version) <= 64
                    else None
                ),
            }
    return {
        "schema_version": MODULE_PROBE_SCHEMA_VERSION,
        "available": True,
    }


def _malformed_child_output(malformation: str) -> ModuleProbeResult:
    return _failed_module_probe(
        "malformed_child_output",
        malformation=malformation,
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonstandard_json_constant(_value: str) -> object:
    raise ValueError("non-standard JSON number")


def _decode_module_probe_child(raw: bytes) -> ModuleProbeResult:
    if len(raw) > MODULE_PROBE_MAX_OUTPUT_BYTES:
        return _malformed_child_output("oversized")
    if not raw.strip():
        return _malformed_child_output("empty")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _malformed_child_output("invalid_utf8")
    lines = decoded.splitlines()
    if len(lines) != 1:
        return _malformed_child_output("multiple_lines")
    try:
        payload = json.loads(
            lines[0],
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError):
        return _malformed_child_output("invalid_json")
    if not isinstance(payload, dict):
        return _malformed_child_output("invalid_payload")
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != MODULE_PROBE_SCHEMA_VERSION:
        return _malformed_child_output("invalid_payload")
    available = payload.get("available")
    if available is True and set(payload) == {"schema_version", "available"}:
        return {"available": True, "failure": None}
    expected_failure_keys = {
        "schema_version",
        "available",
        "failure_reason",
        "exception_type",
    }
    failure_reason = payload.get("failure_reason")
    exception_type = payload.get("exception_type")
    if (
        available is False
        and set(payload) == expected_failure_keys
        and isinstance(failure_reason, str)
        and failure_reason in {"unavailable_import", "initializer_exception"}
        and isinstance(exception_type, str)
        and bool(exception_type)
    ):
        return _failed_module_probe(
            str(failure_reason),
            exception_type=exception_type,
        )
    expected_version_failure_keys = {
        "schema_version",
        "available",
        "failure_reason",
        "required_version",
        "actual_version",
    }
    required_version = payload.get("required_version")
    actual_version = payload.get("actual_version")
    if (
        available is False
        and set(payload) == expected_version_failure_keys
        and failure_reason == "incompatible_version"
        and required_version in REQUIRED_MODULE_VERSIONS.values()
        and (
            actual_version is None
            or (isinstance(actual_version, str) and len(actual_version) <= 64)
        )
    ):
        return _failed_module_probe(
            "incompatible_version",
            required_version=required_version,
            actual_version=actual_version,
        )
    return _malformed_child_output("invalid_payload")


def _read_module_probe_child_result(result_file: BinaryIO) -> ModuleProbeResult:
    """Read one bounded result through the parent's retained descriptor."""
    try:
        result_file.seek(0)
        remaining = MODULE_PROBE_MAX_OUTPUT_BYTES + 1
        chunks: list[bytes] = []
        while remaining:
            chunk = result_file.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except OSError:
        return _malformed_child_output("unreadable")
    return _decode_module_probe_child(raw)


def _signal_name(signal_number: int) -> str:
    try:
        return signal.Signals(signal_number).name
    except ValueError:
        return f"SIG{signal_number}"


def _probe_module(
    import_name: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[object]] | None = None,
) -> ModuleProbeResult:
    """Probe one import in a bounded child of this exact interpreter."""
    run = subprocess.run if runner is None else runner
    with tempfile.TemporaryDirectory(prefix="speaker-toolkit-module-probe-") as temp:
        result_path = Path(temp) / "result.json"
        with result_path.open("x+b", buffering=0) as result_file:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                MODULE_PROBE_CHILD_FLAG,
                import_name,
                str(result_path),
            ]
            try:
                completed = run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=MODULE_PROBE_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                return _failed_module_probe(
                    "timeout",
                    timeout_seconds=MODULE_PROBE_TIMEOUT_SECONDS,
                )
            except OSError as exc:
                return _failed_module_probe(
                    "probe_start_failure",
                    exception_type=type(exc).__name__,
                )
            if completed.returncode != 0:
                if completed.returncode < 0:
                    signal_number = -completed.returncode
                    return _failed_module_probe(
                        "native_crash",
                        termination="signal",
                        signal_number=signal_number,
                        signal_name=_signal_name(signal_number),
                    )
                return _failed_module_probe(
                    "native_crash",
                    termination="exit",
                    exit_code=completed.returncode,
                )
            return _read_module_probe_child_result(result_file)


def _module_available(import_name: str) -> bool:
    """Return the legacy boolean view of an isolated module probe."""
    return _probe_module(import_name)["available"]


def _command_available(command: str) -> bool:
    return shutil.which(command) is not None


def _probe_command(
    label: str,
    command: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> CommandProbeResult:
    """Probe presence, plus the pinned version for versioned commands."""
    if label != "yt-dlp":
        available = _command_available(command)
        return {
            "available": available,
            "failure": None if available else {"reason": "not_found"},
        }

    try:
        executable = resolve_ytdlp()
    except YtDlpResolutionError as exc:
        return {
            "available": False,
            "failure": {"reason": exc.code},
        }

    run = subprocess.run if runner is None else runner
    try:
        completed = run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=MODULE_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "failure": {
                "reason": "timeout",
                "timeout_seconds": MODULE_PROBE_TIMEOUT_SECONDS,
            },
        }
    except OSError as exc:
        return {
            "available": False,
            "failure": {
                "reason": "probe_start_failure",
                "exception_type": type(exc).__name__,
            },
        }

    raw_version = completed.stdout.strip()
    actual_version = raw_version if raw_version and len(raw_version) <= 64 else None
    if completed.returncode != 0 or actual_version is None:
        return {
            "available": False,
            "failure": {
                "reason": "version_unavailable",
                "exit_code": completed.returncode,
            },
        }
    if normalized_ytdlp_version(actual_version) != normalized_ytdlp_version(
        YTDLP_REQUIRED_VERSION
    ):
        return {
            "available": False,
            "failure": {
                "reason": "incompatible_version",
                "required_version": YTDLP_REQUIRED_VERSION,
                "actual_version": actual_version,
            },
        }
    return {"available": True, "failure": None}


def _parse_lanes(value: str) -> tuple[str, ...]:
    lanes = tuple(dict.fromkeys(part.strip() for part in value.split(",")))
    if not lanes or any(not lane for lane in lanes):
        raise argparse.ArgumentTypeError(
            "lane list must not be empty; pass a comma-separated value such as core"
        )
    unknown = sorted(set(lanes) - set(LANE_REQUIREMENTS))
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown lanes {unknown}; choose from {sorted(LANE_REQUIREMENTS)}"
        )
    return lanes


def build_report(
    lanes: tuple[str, ...],
    required_lanes: tuple[str, ...],
) -> dict[str, Any]:
    """Return one deterministic report for the running interpreter."""
    selected = tuple(dict.fromkeys((*lanes, *required_lanes, "core")))
    required = frozenset((*required_lanes, "core"))
    python_supported = sys.version_info[:2] >= MINIMUM_PYTHON
    lane_reports: dict[str, dict[str, Any]] = {}
    for lane in selected:
        requirements = LANE_REQUIREMENTS[lane]
        module_probes = {
            distribution: _probe_module(import_name)
            for distribution, import_name in requirements["modules"].items()
        }
        modules = {
            distribution: probe["available"]
            for distribution, probe in module_probes.items()
        }
        module_failures = {
            distribution: probe["failure"]
            for distribution, probe in module_probes.items()
            if probe["failure"] is not None
        }
        command_probes = {
            label: _probe_command(label, command)
            for label, command in requirements["commands"].items()
        }
        commands = {
            label: probe["available"] for label, probe in command_probes.items()
        }
        command_failures = {
            label: probe["failure"]
            for label, probe in command_probes.items()
            if probe["failure"] is not None
        }
        missing_modules = sorted(
            name for name, available in modules.items() if not available
        )
        missing_commands = sorted(
            name for name, available in commands.items() if not available
        )
        available = not missing_modules and not missing_commands
        if lane == "core" and not python_supported:
            available = False
        lane_reports[lane] = {
            "available": available,
            "required": lane in required,
            "modules": modules,
            "module_failures": module_failures,
            "required_module_versions": {
                distribution: REQUIRED_MODULE_VERSIONS[import_name]
                for distribution, import_name in requirements["modules"].items()
                if import_name in REQUIRED_MODULE_VERSIONS
            },
            "commands": commands,
            "command_failures": command_failures,
            "required_command_versions": (
                {"yt-dlp": YTDLP_REQUIRED_VERSION}
                if "yt-dlp" in requirements["commands"]
                else {}
            ),
            "missing_modules": missing_modules,
            "missing_commands": missing_commands,
        }
    blocking = sorted(lane for lane in required if not lane_reports[lane]["available"])
    degraded = sorted(
        lane
        for lane, report in lane_reports.items()
        if not report["available"] and lane not in required
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": not blocking,
        "python_executable": sys.executable,
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "minimum_python": ".".join(str(part) for part in MINIMUM_PYTHON),
        "lanes": lane_reports,
        "blocking_lanes": blocking,
        "degraded_lanes": degraded,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "--lanes",
        type=_parse_lanes,
        default=DEFAULT_LANES,
        help=(
            "comma-separated lanes to inspect; choices: "
            + ",".join(sorted(LANE_REQUIREMENTS))
        ),
    )
    parser.add_argument(
        "--require-lanes",
        type=_parse_lanes,
        default=DEFAULT_REQUIRED_LANES,
        help="comma-separated lanes whose absence must produce exit 1",
    )
    args = parser.parse_args(argv)
    report = build_report(args.lanes, args.require_lanes)
    print(json.dumps(report, sort_keys=True))
    if not report["ok"]:
        blocking = ", ".join(report["blocking_lanes"])
        print(
            "vault-ingress runtime is unavailable for required lanes "
            f"{blocking}; use Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}+ "
            "and install the missing modules or commands at their required "
            "versions, or repair failed "
            f"dependency initialization, listed in the JSON in {sys.executable}, "
            "then rerun this check",
            file=sys.stderr,
        )
    elif report["degraded_lanes"]:
        degraded = ", ".join(report["degraded_lanes"])
        print(
            "vault-ingress runtime is degraded for optional lanes "
            f"{degraded}; install the missing modules or commands at their "
            "required versions, or repair "
            "failed dependency initialization, listed in the JSON in "
            f"{sys.executable}, then rerun this check",
            file=sys.stderr,
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    child_probe = len(sys.argv) == 4 and sys.argv[1] == MODULE_PROBE_CHILD_FLAG
    if child_probe:
        with Path(sys.argv[3]).open("r+b", buffering=0) as child_result_file:
            with (
                open(os.devnull, "w", encoding="utf-8") as dependency_output,
                contextlib.redirect_stdout(dependency_output),
                contextlib.redirect_stderr(dependency_output),
            ):
                try:
                    child_payload = _module_probe_child(sys.argv[2])
                # The parent silently collapses a non-zero exit without a result into
                # native_crash; emit initializer_exception because propagation would
                # erase the actionable Python initializer-failure classification.
                except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
                    child_payload = {
                        "schema_version": MODULE_PROBE_SCHEMA_VERSION,
                        "available": False,
                        "failure_reason": "initializer_exception",
                        "exception_type": type(exc).__name__,
                    }
            _write_module_probe_result(child_result_file, child_payload)
        raise SystemExit(0)
    try:
        raise SystemExit(main())
    # Callers treat a non-zero exit without report JSON as a silent precheck
    # failure; emit one failure report and recovery step because propagation
    # would suppress the machine-readable diagnostic contract.
    except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
        print(
            json.dumps(
                {
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "ok": False,
                    "python_executable": sys.executable,
                    "python_version": ".".join(
                        str(part) for part in sys.version_info[:3]
                    ),
                    "minimum_python": ".".join(str(part) for part in MINIMUM_PYTHON),
                    "lanes": {},
                    "blocking_lanes": ["runtime-probe"],
                    "degraded_lanes": [],
                    "error": f"{type(exc).__name__}: {exc}",
                },
                sort_keys=True,
            )
        )
        print(
            "vault-ingress runtime probe failed unexpectedly; repair the "
            "configured interpreter or dependency initialization named in the "
            "JSON, then rerun this check",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

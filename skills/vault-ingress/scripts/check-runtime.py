#!/usr/bin/env python3
"""Check imports and commands in the configured vault-ingress runtime.

The installed plugin does not ship ``pyproject.toml``. This stdlib-only probe
reports whether the interpreter recorded in ``config.python_path`` can import
each lane's modules and find its commands. Versions are pinned in
``pyproject.toml`` and nowhere else. Core failures block ingress. Missing
optional dependencies are reported as degradation unless the caller explicitly
requires that lane. Isolated import faults remain lane-local.
"""

from __future__ import annotations

import argparse
import json
import signal
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, TypedDict

from ytdlp_runtime import YtDlpResolutionError, resolve_ytdlp


REPORT_SCHEMA_VERSION = 3
MODULE_PROBE_TIMEOUT_SECONDS = 30
# Probe outcomes that leave the module's presence UNKNOWN rather than answered.
# A timeout is the ordinary one: the configured interpreter can live on a
# network filesystem, where a cold import reads its dependencies over the
# network and a healthy install takes minutes. Measured on a Drive-hosted vault
# venv, `import mlx_whisper` took 568s cold and 1s warm, almost all of it scipy.
UNRESOLVED_PROBE_REASONS = frozenset({"timeout", "probe_start_failure"})
MINIMUM_PYTHON = (3, 10)
LANE_REQUIREMENTS: dict[str, dict[str, dict[str, str]]] = {
    "core": {
        "modules": {"PyYAML": "yaml"},
        "commands": {},
    },
    "pdf": {
        "modules": {"pypdf": "pypdf", "psutil": "psutil"},
        "commands": {},
    },
    # outline_schema.py and the shownotes verifier import these at module load.
    "outline": {
        "modules": {"PyYAML": "yaml", "pydantic": "pydantic"},
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


# The child's exit status is the whole protocol. Python itself exits 1 on an
# uncaught exception, so a dependency whose initializer raises reads as 1; a
# missing module is caught and reported as 3 instead.
_IMPORT_PROBE_SOURCE = (
    "import importlib, sys\n"
    "try:\n"
    "    importlib.import_module(sys.argv[1])\n"
    "except ImportError:\n"
    "    sys.exit(3)\n"
)
_INITIALIZER_EXCEPTION_EXIT = 1
_UNAVAILABLE_IMPORT_EXIT = 3


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
    """Import one module in a bounded child of this exact interpreter.

    A child rather than an in-process import, because a native extension can
    crash the interpreter and a cold network filesystem can stall an import for
    minutes; either must stay local to its lane.
    """
    run = subprocess.run if runner is None else runner
    try:
        completed = run(
            [sys.executable, "-c", _IMPORT_PROBE_SOURCE, import_name],
            # `-c` puts the working directory on sys.path; pin it so a stray
            # module in the caller's directory cannot shadow the dependency.
            cwd=str(Path(__file__).resolve().parent),
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
    code = completed.returncode
    if code == 0:
        return {"available": True, "failure": None}
    if code == _UNAVAILABLE_IMPORT_EXIT:
        return _failed_module_probe("unavailable_import")
    if code == _INITIALIZER_EXCEPTION_EXIT:
        return _failed_module_probe("initializer_exception")
    if code < 0:
        return _failed_module_probe(
            "native_crash",
            termination="signal",
            signal_number=-code,
            signal_name=_signal_name(-code),
        )
    return _failed_module_probe("native_crash", termination="exit", exit_code=code)


def _command_available(command: str) -> bool:
    return shutil.which(command) is not None


def unresolved_module_probes(report: Mapping[str, Any]) -> dict[str, str]:
    """Map each module whose probe never answered to the reason it did not.

    Separated from the missing set because the two need different repairs: a
    missing module is one the probe found absent, repaired by installing it; an
    unresolved one is a module whose presence the probe never established,
    usually repaired by warming the interpreter it lives on.
    """
    unresolved: dict[str, str] = {}
    for lane in report.get("lanes", {}).values():
        failures = lane.get("module_failures", {})
        for name in lane.get("unresolved_modules", []):
            failure = failures.get(name)
            if isinstance(failure, dict):
                unresolved[name] = str(failure.get("reason"))
    return unresolved


def _unresolved_advice(report: Mapping[str, Any]) -> str:
    """Name the modules whose presence is unknown, and the repair that fits."""
    unresolved = unresolved_module_probes(report)
    if not unresolved:
        return ""
    named = ", ".join(
        f"{name} ({reason})" for name, reason in sorted(unresolved.items())
    )
    return (
        f". NOTE: the probe did not resolve {named}, so these may be installed "
        "but slow to import rather than absent — an interpreter on a network "
        "filesystem reads its dependencies over the network on a cold import. "
        "Read the package files once to warm them, then rerun this check, "
        "before reinstalling anything"
    )


def _probe_command(label: str, command: str) -> CommandProbeResult:
    """Probe presence; yt-dlp resolves through the toolkit's own order first."""
    if label != "yt-dlp":
        available = _command_available(command)
        return {
            "available": available,
            "failure": None if available else {"reason": "not_found"},
        }
    try:
        resolve_ytdlp()
    except YtDlpResolutionError as exc:
        return {"available": False, "failure": {"reason": exc.code}}
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
        # A probe that never finished says nothing about whether the module is
        # installed. Reporting one as missing sends an operator to install a
        # package that is already there — the repair for a cold interpreter on a
        # network filesystem is to warm it, not to reinstall it. `missing_modules`
        # keeps every unavailable name so existing readers are unaffected; this
        # names the subset whose answer is unknown rather than "absent".
        unresolved_modules = sorted(
            name
            for name, failure in module_failures.items()
            if isinstance(failure, dict)
            and failure.get("reason") in UNRESOLVED_PROBE_REASONS
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
            "commands": commands,
            "command_failures": command_failures,
            "missing_modules": missing_modules,
            "unresolved_modules": unresolved_modules,
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
            "and install the missing modules or commands, or repair failed "
            f"dependency initialization, listed in the JSON in {sys.executable}, "
            "then rerun this check" + _unresolved_advice(report),
            file=sys.stderr,
        )
    elif report["degraded_lanes"]:
        degraded = ", ".join(report["degraded_lanes"])
        print(
            "vault-ingress runtime is degraded for optional lanes "
            f"{degraded}; install the missing modules or commands, or repair "
            "failed dependency initialization, listed in the JSON in "
            f"{sys.executable}, then rerun this check" + _unresolved_advice(report),
            file=sys.stderr,
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
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

#!/usr/bin/env python3
"""Check imports and commands in the configured vault-ingress runtime.

The installed plugin does not ship ``pyproject.toml``. This stdlib-only probe is
the executable dependency contract for the interpreter recorded in
``config.python_path``. Core failures block ingress. Recognized missing or
incompatible optional dependencies are reported as degradation unless the
caller explicitly requires that lane. Unexpected probe faults fail visibly.
"""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
from typing import Any


REPORT_SCHEMA_VERSION = 1
MINIMUM_PYTHON = (3, 10)
LANE_REQUIREMENTS: dict[str, dict[str, dict[str, str]]] = {
    "core": {
        "modules": {"PyYAML": "yaml"},
        "commands": {},
    },
    "pdf": {
        "modules": {"pypdf": "pypdf"},
        "commands": {},
    },
    "pptx": {
        "modules": {"python-pptx": "pptx"},
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
        "modules": {},
        "commands": {"yt-dlp": "yt-dlp"},
    },
    "whisper": {
        "modules": {"mlx-whisper": "mlx_whisper"},
        "commands": {"ffprobe": "ffprobe"},
    },
    "video": {
        "modules": {"imagehash": "imagehash", "Pillow": "PIL"},
        "commands": {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"},
    },
    "pdf-render": {
        "modules": {},
        "commands": {"pdftoppm": "pdftoppm"},
    },
}
DEFAULT_LANES = ("core", "pdf", "pptx")
DEFAULT_REQUIRED_LANES = ("core",)


def _module_available(import_name: str) -> bool:
    try:
        importlib.import_module(import_name)
    except (ImportError, OSError, RuntimeError):
        return False
    return True


def _command_available(command: str) -> bool:
    return shutil.which(command) is not None


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
        modules = {
            distribution: _module_available(import_name)
            for distribution, import_name in requirements["modules"].items()
        }
        commands = {
            label: _command_available(command)
            for label, command in requirements["commands"].items()
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
            "commands": commands,
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
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
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
            f"and install the missing modules or commands listed in the JSON "
            f"into {sys.executable}, then rerun this check",
            file=sys.stderr,
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    # outer-boundary-process-contract: callers treat missing JSON as a silent
    # probe failure; emit one failure object and recovery step before exiting.
    except Exception as exc:  # noqa: BLE001
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

#!/usr/bin/env python3
"""Resolve the configured vault interpreter for standalone shownotes publishing.

Composes two owner scripts and adds no parsing of its own beyond their JSON:

1. ``read-tracking-database.py`` under the host interpreter running this script,
   on the given database path (default: the documented vault locator). The
   database must be the owner-current generation (``tracking_database``'s own
   assessment); a legacy one is the owner's to migrate.
2. The same owner read of the same path under ``config.python_path``, which must
   be an absolute interpreter path; the database and its SHA-256 must match the
   first read. The vault root is the database locator's directory, never the
   optional and possibly stale ``config.vault_root``.
3. ``check-runtime.py`` under ``config.python_path`` with the ``outline`` lane
   required: PyYAML and Pydantic v2, which ``outline_schema.py`` and
   ``verify-talk-skill.py`` import. Its JSON verdict is classified, never just
   its exit code (``classify_runtime_check``): an unsupported Python is
   ``interpreter_unsupported``, missing modules or commands are
   ``runtime_lane_unavailable``, probes that never finished (a cold interpreter
   on a network filesystem) are ``runtime_lane_unresolved``, and a probe fault
   or unreadable verdict is ``runtime_probe_failed``.

The first owner read failing is ``owner_read_failed``; the same read failing
only under ``config.python_path`` is ``interpreter_unusable``.

Stdout: one JSON object. Success is ``{"ok": true, "python_path", "vault_root",
"database_sha256"}``. Failure is ``{"ok": false, "reason_code", "error",
"handoff"}`` with a stderr diagnostic; ``handoff`` names the vault-ingress step
that repairs the configuration. Exit 0 on success, 1 on any refusal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

DEFAULT_DATABASE = "~/.claude/rhetoric-knowledge-vault/tracking-database.json"
TOOLKIT_ROOT = Path(__file__).resolve().parents[3]
OWNER_READER = TOOLKIT_ROOT / "skills/vault-ingress/scripts/read-tracking-database.py"
RUNTIME_CHECK = TOOLKIT_ROOT / "skills/vault-ingress/scripts/check-runtime.py"
REQUIRED_LANE = "outline"
# The check-runtime.py report generation this resolver reads.
RUNTIME_REPORT_SCHEMA_VERSION = 3
HANDOFF = "vault-ingress Step 1"
TIMEOUT_SECONDS = 120

# The owner's generation check is stdlib-only, so the host interpreter can run it.
sys.path.insert(0, str(TOOLKIT_ROOT / "skills/vault-ingress/scripts"))
# E402: tracking_database resolves only after the insert above puts the
# co-shipped vault-ingress scripts directory on sys.path.
from tracking_database import (  # noqa: E402
    TrackingDatabaseError,
    assess_tracking_database,
)


class RuntimeResolutionError(RuntimeError):
    """A refusal with a stable reason code and an actionable message."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeResolutionError(
            "interpreter_unusable",
            f"cannot run {command[0]} ({exc}); repair config.python_path through "
            f"{HANDOFF}",
        ) from exc


def owner_read(
    interpreter: str, database: Path, failure_code: str = "owner_read_failed"
) -> dict:
    """Run the strict owner reader and return its success report.

    ``failure_code`` names what a failure means: the database for the host's
    read, the interpreter for the configured one's.
    """
    completed = _run([interpreter, str(OWNER_READER), str(database)])
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeResolutionError(
            failure_code,
            f"the tracking-database owner reader under {interpreter} returned no "
            f"JSON (exit {completed.returncode}); run it directly to see why",
        ) from exc
    if (
        completed.returncode != 0
        or not isinstance(report, dict)
        or not report.get("ok")
    ):
        raise RuntimeResolutionError(
            failure_code,
            f"the tracking database at {database} did not read under {interpreter} "
            f"(exit {completed.returncode}); repair it through {HANDOFF}",
        )
    return report


def _version_tuple(text: object) -> tuple[int, ...] | None:
    if not isinstance(text, str):
        return None
    parts = text.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _lane_usable(report: dict, lane: str) -> bool:
    """A success verdict that actually covers the lane: nothing contradicts it."""
    version = _version_tuple(report.get("python_version"))
    minimum = _version_tuple(report.get("minimum_python"))
    lanes = report.get("lanes")
    lane_report = lanes.get(lane) if isinstance(lanes, dict) else None
    return (
        report.get("schema_version") == RUNTIME_REPORT_SCHEMA_VERSION
        and report.get("blocking_lanes") == []
        and version is not None
        and minimum is not None
        and version[:2] >= minimum[:2]
        and isinstance(lane_report, dict)
        and lane_report.get("available") is True
    )


def classify_runtime_check(returncode: int, stdout: str, lane: str) -> str | None:
    """The reason code a ``check-runtime.py`` verdict calls for; None when usable."""
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        return "runtime_probe_failed"
    if not isinstance(report, dict):
        return "runtime_probe_failed"
    if returncode == 0 and report.get("ok") is True:
        return None if _lane_usable(report, lane) else "runtime_probe_failed"
    if "runtime-probe" in (report.get("blocking_lanes") or []):
        return "runtime_probe_failed"
    version = _version_tuple(report.get("python_version"))
    minimum = _version_tuple(report.get("minimum_python"))
    if version is not None and minimum is not None and version[:2] < minimum[:2]:
        return "interpreter_unsupported"
    lanes = report.get("lanes")
    lane_report = lanes.get(lane) if isinstance(lanes, dict) else None
    if not isinstance(lane_report, dict):
        return "runtime_probe_failed"
    unresolved = set(lane_report.get("unresolved_modules") or [])
    missing = set(lane_report.get("missing_modules") or []) - unresolved
    if missing or lane_report.get("missing_commands"):
        return "runtime_lane_unavailable"
    if unresolved:
        return "runtime_lane_unresolved"
    return "runtime_probe_failed"


RUNTIME_CHECK_ACTIONS = {
    "interpreter_unsupported": "replace config.python_path with a supported Python",
    "runtime_lane_unavailable": "install the toolkit requirements into it",
    "runtime_lane_unresolved": (
        "its imports did not finish probing; warm the interpreter and re-run"
    ),
    "runtime_probe_failed": "the runtime probe itself failed; run it directly",
}


def _config_text(config: dict, field: str, database: Path) -> str:
    value = config.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeResolutionError(
            "config_incomplete",
            f"config.{field} is absent or empty in {database}; record it through "
            f"{HANDOFF}",
        )
    return value


def _require_current(database: object, locator: Path) -> dict:
    try:
        current = (
            isinstance(database, dict)
            and assess_tracking_database(database).state == "current"
        )
    except TrackingDatabaseError:
        current = False
    if not current or not isinstance(database, dict):
        raise RuntimeResolutionError(
            "database_not_current",
            f"the tracking database at {locator} is not the current owner "
            f"generation; run the owner migration through {HANDOFF}",
        )
    return database


def resolve(database: Path) -> dict:
    first = owner_read(sys.executable, database)
    config = _require_current(first.get("database"), database).get("config")
    config = config if isinstance(config, dict) else {}
    python_path = _config_text(config, "python_path", database)
    if not Path(python_path).is_absolute():
        raise RuntimeResolutionError(
            "interpreter_not_absolute",
            f"config.python_path {python_path!r} is not an absolute interpreter "
            f"path, so it would resolve through PATH or the working directory; "
            f"record the absolute path through {HANDOFF}",
        )
    second = owner_read(python_path, database, "interpreter_unusable")
    if second.get("sha256") != first.get("sha256") or second.get(
        "database"
    ) != first.get("database"):
        raise RuntimeResolutionError(
            "database_mismatch",
            f"the tracking database at {database} changed between the host and "
            "config.python_path reads; re-run once the vault is settled",
        )
    vault_root = str(Path(str(first.get("database_path", database))).parent)
    check = _run(
        [
            python_path,
            str(RUNTIME_CHECK),
            "--lanes",
            REQUIRED_LANE,
            "--require-lanes",
            REQUIRED_LANE,
        ]
    )
    reason = classify_runtime_check(check.returncode, check.stdout, REQUIRED_LANE)
    if reason is not None:
        raise RuntimeResolutionError(
            reason,
            f"config.python_path cannot serve the {REQUIRED_LANE} lane (PyYAML "
            f"and Pydantic v2; check-runtime exit {check.returncode}): "
            f"{RUNTIME_CHECK_ACTIONS[reason]}, through {HANDOFF}",
        )
    return {
        "ok": True,
        "python_path": python_path,
        "vault_root": vault_root,
        "database_sha256": first.get("sha256"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        help="Tracking database locator; the documented vault path by default",
    )
    args = parser.parse_args(argv)
    try:
        print(json.dumps(resolve(Path(args.database).expanduser())))
        return 0
    except RuntimeResolutionError as exc:
        failure = {
            "ok": False,
            "reason_code": exc.reason_code,
            "error": str(exc),
            "handoff": HANDOFF,
        }
    # The publisher reads stdout JSON to choose its interpreter; a traceback
    # would leave it no verdict and a bare python3 fallback looks like success.
    # Emit a closed ok:false object plus stderr instead.
    except Exception as exc:  # noqa: BLE001 — outer-boundary-process-contract
        failure = {
            "ok": False,
            "reason_code": "resolver_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "handoff": HANDOFF,
        }
    print(json.dumps(failure))
    print(f"FAIL: {failure['error']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

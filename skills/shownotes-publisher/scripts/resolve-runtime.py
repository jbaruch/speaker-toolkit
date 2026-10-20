#!/usr/bin/env python3
"""Resolve the configured vault interpreter for standalone shownotes publishing.

Composes two owner scripts and adds no parsing of its own beyond their JSON:

1. ``read-tracking-database.py`` under the host interpreter running this script,
   on the given database path (default: the documented vault locator). The
   database must be the owner-current generation (``tracking_database``'s own
   assessment); a legacy one is the owner's to migrate.
2. The same owner read of the same path under ``config.python_path``, which must
   be an absolute interpreter path; the database and its SHA-256 must match the
   first read. The vault root is the database locator's directory, resolved
   through ``vault_root_authority.resolve_vault_root_authority`` so a
   ``config.vault_storage_path`` naming another root refuses as
   ``vault_root_invalid``; the optional, possibly stale ``config.vault_root``
   is never an authority.
3. ``check-runtime.py`` under ``config.python_path`` with the ``outline`` lane
   required: PyYAML and Pydantic v2, which ``outline_schema.py`` and
   ``verify-talk-skill.py`` import. Its JSON verdict is classified, never just
   its exit code (``classify_runtime_check``): an unsupported Python is
   ``interpreter_unsupported``, missing modules or commands are
   ``runtime_lane_unavailable``, module probes that timed out (a cold
   interpreter on a network filesystem) are ``runtime_lane_unresolved``, and a
   probe that could not start, a probe fault, an unreadable verdict, or a check
   that did not finish in time is ``runtime_probe_failed``.

An owner read that answers with its own failure keeps the owner's
classification: its ``code`` is reported as ``owner_code`` and its remedy is in
``error``. A concurrent write (the owner's ``database_generation_conflict``) is
``database_generation_conflict``, which a rerun fixes; every other owner
failure is ``owner_read_failed``. A read that returns no owner verdict is
``owner_read_failed`` under the host interpreter and ``interpreter_unusable``
under ``config.python_path``, unless it timed out, which is
``owner_read_failed`` under either, since a read that never finished says
nothing about the interpreter. ``config.python_path`` failing to launch the
runtime check is ``interpreter_unusable``.

Stdout: one JSON object. Success is ``{"ok": true, "python_path", "vault_root",
"database_sha256"}``. Failure is ``{"ok": false, "reason_code", "error",
"handoff", "database"}``, plus ``owner_code`` when the owner classified it,
with a stderr diagnostic; ``handoff`` names the vault-ingress step that repairs
the configuration, and ``database`` is the absolute locator this run read, the
one target any repair must act on. Exit 0 on success, 1 on any refusal.
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
# The check-runtime.py module-failure reason a cold import reports; its other
# unresolved reason, a probe that could not start, is not fixed by warming.
COLD_IMPORT_REASON = "timeout"

# The owner's generation check is stdlib-only, so the host interpreter can run it.
sys.path.insert(0, str(TOOLKIT_ROOT / "skills/vault-ingress/scripts"))
# E402: tracking_database resolves only after the insert above puts the
# co-shipped vault-ingress scripts directory on sys.path.
from tracking_database import (  # noqa: E402
    TrackingDatabaseError,
    assess_tracking_database,
)
from vault_root_authority import (  # noqa: E402
    VaultRootAuthorityError,
    resolve_vault_root_authority,
)

# The owner reader's code for a write installed mid-read; a rerun fixes it.
OWNER_GENERATION_CONFLICT = "database_generation_conflict"


class RuntimeResolutionError(RuntimeError):
    """A refusal with a stable reason code and an actionable message."""

    def __init__(
        self, reason_code: str, message: str, *, owner_code: str | None = None
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.owner_code = owner_code


def _run(
    command: list[str],
    *,
    launch_failure: tuple[str, str],
    timeout_failure: tuple[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run one call; each failure pairs the call site's reason code and repair."""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        code, repair = timeout_failure
        raise RuntimeResolutionError(
            code,
            f"{Path(command[1]).name} under {command[0]} did not finish within "
            f"{TIMEOUT_SECONDS} seconds; {repair}",
        ) from exc
    except OSError as exc:
        code, repair = launch_failure
        raise RuntimeResolutionError(
            code, f"cannot run {command[0]} ({exc}); {repair}"
        ) from exc


def owner_read(
    interpreter: str, database: Path, failure_code: str = "owner_read_failed"
) -> dict:
    """Run the strict owner reader and return its success report.

    ``failure_code`` names what a failure means: the database for the host's
    read, the interpreter for the configured one's.
    """
    direct = f"run {OWNER_READER.name} under {interpreter} directly to see why"
    completed = _run(
        [interpreter, str(OWNER_READER), str(database)],
        launch_failure=(
            failure_code,
            f"repair config.python_path through {HANDOFF}"
            if failure_code == "interpreter_unusable"
            else direct,
        ),
        timeout_failure=(
            "owner_read_failed",
            f"re-run once the vault volume responds, or {direct}",
        ),
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeResolutionError(
            failure_code,
            f"the tracking-database owner reader under {interpreter} returned no "
            f"JSON (exit {completed.returncode}); {direct}",
        ) from exc
    if completed.returncode == 0 and isinstance(report, dict) and report.get("ok"):
        return report
    owner_code = report.get("code") if isinstance(report, dict) else None
    owner_error = report.get("error") if isinstance(report, dict) else None
    if isinstance(owner_code, str) and isinstance(owner_error, str):
        # The owner classified the failure; its code and remedy are the repair.
        if owner_code == OWNER_GENERATION_CONFLICT:
            raise RuntimeResolutionError(
                "database_generation_conflict",
                f"{owner_error} (read under {interpreter}); re-run the resolver",
                owner_code=owner_code,
            )
        raise RuntimeResolutionError(
            "owner_read_failed",
            f"the tracking database at {database} did not read under "
            f"{interpreter}: {owner_error}",
            owner_code=owner_code,
        )
    raise RuntimeResolutionError(
        failure_code,
        f"the tracking-database owner reader under {interpreter} returned no "
        f"verdict (exit {completed.returncode}); {direct}",
    )


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
    failures = lane_report.get("module_failures")
    failures = failures if isinstance(failures, dict) else {}

    def timed_out(name: str) -> bool:
        failure = failures.get(name)
        return isinstance(failure, dict) and failure.get("reason") == COLD_IMPORT_REASON

    # Every unresolved module must have timed out: a probe that could not start
    # is a probe fault, which warming the imports does not repair.
    if unresolved and all(timed_out(name) for name in unresolved):
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
    try:
        vault_root = str(
            resolve_vault_root_authority(
                database_path=str(first.get("database_path", database)),
                config=config,
            )
        )
    except VaultRootAuthorityError as exc:
        raise RuntimeResolutionError(
            "vault_root_invalid",
            f"the tracking database at {database} does not agree with its "
            f"config.vault_storage_path ({exc.reason_code}); pass the database at "
            "the vault root it names, or repair config.vault_storage_path through "
            f"{HANDOFF}",
        ) from exc
    check = _run(
        [
            python_path,
            str(RUNTIME_CHECK),
            "--lanes",
            REQUIRED_LANE,
            "--require-lanes",
            REQUIRED_LANE,
        ],
        launch_failure=(
            "interpreter_unusable",
            f"repair config.python_path through {HANDOFF}",
        ),
        timeout_failure=(
            "runtime_probe_failed",
            f"run {RUNTIME_CHECK.name} under it directly to see where it stalls",
        ),
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
    # The one locator this run reads, and the one any repair must act on.
    database = Path(args.database).expanduser().absolute()
    failure: dict[str, object]
    try:
        print(json.dumps(resolve(database)))
        return 0
    except RuntimeResolutionError as exc:
        failure = {
            "ok": False,
            "reason_code": exc.reason_code,
            "error": str(exc),
            "handoff": HANDOFF,
            "database": str(database),
        }
        if exc.owner_code is not None:
            failure["owner_code"] = exc.owner_code
    # The publisher reads stdout JSON to choose its interpreter; a traceback
    # would leave it no verdict and a bare python3 fallback looks like success.
    # Emit a closed ok:false object plus stderr instead.
    except Exception as exc:  # noqa: BLE001 — outer-boundary-process-contract
        failure = {
            "ok": False,
            "reason_code": "resolver_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "handoff": HANDOFF,
            "database": str(database),
        }
    print(json.dumps(failure))
    print(f"FAIL: {failure['error']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

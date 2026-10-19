#!/usr/bin/env python3
"""Resolve the configured vault interpreter for standalone shownotes publishing.

Composes two owner scripts and adds no parsing of its own beyond their JSON:

1. ``read-tracking-database.py`` under the host interpreter running this script,
   on the given database path (default: the documented vault locator).
2. The same owner read under ``config.python_path``, on
   ``{config.vault_root}/tracking-database.json``; the database and its SHA-256
   must match the first read.
3. ``check-runtime.py`` under ``config.python_path`` with the ``outline`` lane
   required: PyYAML and Pydantic v2, which ``outline_schema.py`` and
   ``verify-talk-skill.py`` import.

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
HANDOFF = "vault-ingress Step 1"
TIMEOUT_SECONDS = 120


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


def owner_read(interpreter: str, database: Path) -> dict:
    """Run the strict owner reader and return its success report."""
    completed = _run([interpreter, str(OWNER_READER), str(database)])
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeResolutionError(
            "owner_read_failed",
            f"the tracking-database owner reader under {interpreter} returned no "
            f"JSON (exit {completed.returncode}); run it directly to see why",
        ) from exc
    if (
        completed.returncode != 0
        or not isinstance(report, dict)
        or not report.get("ok")
    ):
        raise RuntimeResolutionError(
            "owner_read_failed",
            f"the tracking database at {database} did not read under {interpreter} "
            f"(exit {completed.returncode}); repair it through {HANDOFF}",
        )
    return report


def _config_text(config: dict, field: str, database: Path) -> str:
    value = config.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeResolutionError(
            "config_incomplete",
            f"config.{field} is absent or empty in {database}; record it through "
            f"{HANDOFF}",
        )
    return value


def resolve(database: Path) -> dict:
    first = owner_read(sys.executable, database)
    config = first.get("database", {}).get("config")
    config = config if isinstance(config, dict) else {}
    python_path = _config_text(config, "python_path", database)
    vault_root = _config_text(config, "vault_root", database)
    second = owner_read(python_path, Path(vault_root) / "tracking-database.json")
    if second.get("sha256") != first.get("sha256") or second.get(
        "database"
    ) != first.get("database"):
        raise RuntimeResolutionError(
            "database_mismatch",
            f"{vault_root}/tracking-database.json under config.python_path is not "
            f"the database read at {database}; re-run once the vault is settled, "
            f"or repair the locator through {HANDOFF}",
        )
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
    if check.returncode != 0:
        raise RuntimeResolutionError(
            "runtime_lane_unavailable",
            f"config.python_path lacks the {REQUIRED_LANE} lane (PyYAML and "
            f"Pydantic v2; check-runtime exit {check.returncode}); install the "
            f"toolkit requirements into it through {HANDOFF}",
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

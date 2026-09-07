#!/usr/bin/env python3
"""Resolve the toolkit interpreter from a vault's tracking database.

`config.python_path` is the interpreter authority for every operational command
in this skill. Locating and validating it is deterministic — read a JSON key,
confirm the file is executable, confirm it runs — so it belongs in a script
rather than in prose an agent re-implements each session
(`rules/script-delegation.md`).

Usage:
    resolve-interpreter.py <vault_root_or_database_path>

Stdout: {"ok": true, "python_path": "...", "vault_root": "...", "database": "..."}
Stderr: an actionable diagnostic naming the repair path.
Exit 0 when the interpreter is resolved and executes, 1 when it cannot be, 2 on
usage error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DATABASE_NAME = "tracking-database.json"
PROBE_TIMEOUT_SEC = 30
REPAIR = "run vault-ingress Step 1 to repair the configuration"


def locate_database(target: Path) -> Path:
    """The database itself, or the one inside a vault root."""
    return target if target.is_file() else target / DATABASE_NAME


def resolve(target: Path) -> dict:
    """Resolve and validate. Raises ValueError with an actionable message."""
    database = locate_database(target)
    if not database.is_file():
        raise ValueError(
            f"no {DATABASE_NAME} at {database} — pass a vault root or the database path"
        )
    try:
        payload = json.loads(database.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{database} is not valid JSON ({e}) — {REPAIR}") from e
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"cannot read {database}: {e}") from e

    # `[]` and `null` are valid JSON; .get() on them raises rather than reporting.
    if not isinstance(payload, dict):
        raise ValueError(f"{database} must contain a JSON object — {REPAIR}")

    config = payload.get("config")
    if not isinstance(config, dict):
        raise ValueError(f"{database} has no config object — {REPAIR}")

    python_path = config.get("python_path")
    if not isinstance(python_path, str) or not python_path.strip():
        raise ValueError(
            f"config.python_path is absent or empty in {database} — {REPAIR}. "
            "Never fall back to whichever python3 is on PATH."
        )

    interpreter = Path(python_path).expanduser()
    if not interpreter.is_file():
        raise ValueError(f"config.python_path does not exist: {interpreter} — {REPAIR}")

    try:
        probe = subprocess.run(
            [str(interpreter), "-c", "import sys; print(sys.version_info[0])"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise ValueError(
            f"config.python_path could not execute ({e}) — {REPAIR}"
        ) from e
    if probe.returncode != 0 or probe.stdout.strip() != "3":
        raise ValueError(
            f"config.python_path is not a working Python 3: {interpreter} "
            f"(exit {probe.returncode}) — {REPAIR}"
        )

    # The vault the caller actually pointed at wins. `config.vault_root` is a
    # stored assertion that can be stale — echoing it back over a correct
    # caller-supplied root would misdirect every step downstream.
    resolved_root = database.parent
    stored_root = config.get("vault_root")
    result = {
        "ok": True,
        "python_path": str(interpreter),
        "vault_root": str(resolved_root),
        "database": str(database),
    }
    if isinstance(stored_root, str) and stored_root.strip():
        stored = Path(stored_root).expanduser()
        if stored != resolved_root:
            result["stored_vault_root"] = str(stored)
            result["vault_root_mismatch"] = True
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Resolve the toolkit interpreter from a vault's tracking database."
    )
    ap.add_argument("vault_or_database", type=Path)
    args = ap.parse_args(argv)
    try:
        print(json.dumps(resolve(args.vault_or_database.expanduser())))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

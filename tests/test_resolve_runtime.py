"""The standalone publisher's interpreter comes from the vault, never PATH (#458)."""

from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from conftest import CURRENT_ROOT_SCHEMA_VERSION, current_tracking_config

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills/shownotes-publisher/scripts/resolve-runtime.py"
)


def _database(vault: Path, **config: object) -> Path:
    vault.mkdir(parents=True, exist_ok=True)
    path = vault / "tracking-database.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": CURRENT_ROOT_SCHEMA_VERSION,
                "config": current_tracking_config(**config),
                "talks": [],
                "pptx_catalog": [],
                "qr_codes": [],
                "resources": [],
                "thumbnails": [],
                "confirmed_intents": [],
                "improvement_goals": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _resolve(database: Path):
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--database", str(database)],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, json.loads(completed.stdout), completed.stderr


def _refused(database: Path, reason_code: str) -> str:
    code, payload, stderr = _resolve(database)
    assert code == 1
    assert payload["ok"] is False
    assert payload["reason_code"] == reason_code
    assert payload["handoff"] == "vault-ingress Step 1"
    assert payload["error"] in stderr
    return payload["error"]


def test_the_documented_symlinked_locator_resolves_the_configured_interpreter(
    tmp_path,
):
    vault = tmp_path / "drive" / "vault"
    _database(vault, python_path=sys.executable, vault_root=str(vault))
    link = tmp_path / "claude-vault"
    link.symlink_to(vault, target_is_directory=True)

    code, payload, stderr = _resolve(link / "tracking-database.json")

    assert code == 0, stderr
    assert payload["ok"] is True
    assert payload["python_path"] == sys.executable
    # The root is the locator's directory, as the caller spelled it.
    assert payload["vault_root"] == str(link)
    assert len(payload["database_sha256"]) == 64


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_absent_or_blank_python_path_is_refused(tmp_path, value):
    vault = tmp_path / "vault"
    config = {} if value is None else {"python_path": value}
    database = _database(vault, **config)
    assert "config.python_path" in _refused(database, "config_incomplete")


@pytest.mark.parametrize("value", ["python3", ".venv/bin/python"])
def test_a_bare_or_relative_interpreter_is_refused(tmp_path, value):
    """Copilot on #494: a bare name resolves through PATH and a relative one
    through whatever directory a later command runs in."""
    database = _database(tmp_path / "vault", python_path=value)
    assert value in _refused(database, "interpreter_not_absolute")


@pytest.mark.parametrize("vault_root", [None, "~/somewhere-else", "/stale/vault"])
def test_config_vault_root_is_never_the_authority(tmp_path, vault_root):
    vault = tmp_path / "vault"
    config = {"python_path": sys.executable}
    if vault_root is not None:
        config["vault_root"] = vault_root
    database = _database(vault, **config)
    code, payload, stderr = _resolve(database)
    assert code == 0, stderr
    assert payload["vault_root"] == str(vault)


def test_a_legacy_database_is_handed_to_the_owner_migration(tmp_path):
    database = _database(tmp_path / "vault", python_path=sys.executable)
    data = json.loads(database.read_text(encoding="utf-8"))
    data["schema_version"] = CURRENT_ROOT_SCHEMA_VERSION - 1
    database.write_text(json.dumps(data), encoding="utf-8")
    assert "owner migration" in _refused(database, "database_not_current")


def test_a_future_database_fails_the_owner_read(tmp_path):
    """Only a readable older generation is the owner migration's to repair."""
    database = _database(tmp_path / "vault", python_path=sys.executable)
    data = json.loads(database.read_text(encoding="utf-8"))
    data["schema_version"] = CURRENT_ROOT_SCHEMA_VERSION + 1
    database.write_text(json.dumps(data), encoding="utf-8")
    _refused(database, "owner_read_failed")


def test_an_interpreter_that_does_not_exist_is_refused_not_replaced(tmp_path):
    vault = tmp_path / "vault"
    database = _database(
        vault, python_path=str(tmp_path / "missing-python"), vault_root=str(vault)
    )
    _refused(database, "interpreter_unusable")


def _fake_interpreter(tmp_path: Path, name: str, branch: str) -> Path:
    """A strict bash wrapper: ``branch`` handles one script, the rest run for real."""
    interpreter = tmp_path / name
    interpreter.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{branch}\n"
        f'exec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    interpreter.chmod(interpreter.stat().st_mode | stat.S_IXUSR)
    return interpreter


MISSING_PYDANTIC = json.dumps(
    {
        "ok": False,
        "python_version": "3.12.4",
        "minimum_python": "3.10",
        "blocking_lanes": ["outline"],
        "lanes": {
            "outline": {
                "missing_modules": ["pydantic"],
                "unresolved_modules": [],
                "missing_commands": [],
            }
        },
    }
)


def test_an_interpreter_without_the_outline_lane_is_refused(tmp_path):
    """Only the outline lane fails, so a core-only resolver would accept it."""
    interpreter = _fake_interpreter(
        tmp_path,
        "python-without-pydantic",
        'case "$1" in *check-runtime.py)\n'
        '  case " $* " in *" --require-lanes outline "*)\n'
        f"    echo '{MISSING_PYDANTIC}'; exit 1;;\n"
        "  esac\n"
        "  exit 0;;\n"
        "esac",
    )
    vault = tmp_path / "vault"
    database = _database(vault, python_path=str(interpreter), vault_root=str(vault))
    assert "install the toolkit requirements" in _refused(
        database, "runtime_lane_unavailable"
    )


def test_an_interpreter_that_cannot_run_the_owner_read_is_unusable(tmp_path):
    """It launches but fails the second read: an interpreter repair, not a DB one."""
    interpreter = _fake_interpreter(
        tmp_path,
        "python-broken",
        'case "$1" in *read-tracking-database.py) exit 1;; esac',
    )
    database = _database(tmp_path / "vault", python_path=str(interpreter))
    _refused(database, "interpreter_unusable")


def _runtime_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("resolve_runtime_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verdict(**fields):
    report = {
        "ok": False,
        "python_version": "3.12.4",
        "minimum_python": "3.10",
        "blocking_lanes": ["outline"],
        "lanes": {
            "outline": {
                "missing_modules": [],
                "unresolved_modules": [],
                "missing_commands": [],
            }
        },
    }
    report.update(fields)
    return json.dumps(report)


@pytest.mark.parametrize(
    "returncode,stdout,expected",
    [
        (
            0,
            _verdict(
                ok=True,
                schema_version=3,
                blocking_lanes=[],
                lanes={"outline": {"available": True}},
            ),
            None,
        ),
        (0, json.dumps({"ok": True}), "runtime_probe_failed"),
        (
            0,
            _verdict(
                ok=True,
                schema_version=3,
                blocking_lanes=[],
                lanes={"outline": {"available": False}},
            ),
            "runtime_probe_failed",
        ),
        (1, _verdict(python_version="3.9.18"), "interpreter_unsupported"),
        (
            1,
            _verdict(
                lanes={
                    "outline": {
                        "missing_modules": ["pydantic"],
                        "unresolved_modules": ["pydantic"],
                        "module_failures": {"pydantic": {"reason": "timeout"}},
                        "missing_commands": [],
                    }
                }
            ),
            "runtime_lane_unresolved",
        ),
        (
            1,
            _verdict(
                lanes={
                    "outline": {
                        "missing_modules": ["pydantic", "yaml"],
                        "unresolved_modules": ["pydantic", "yaml"],
                        "module_failures": {
                            "pydantic": {"reason": "timeout"},
                            "yaml": {"reason": "probe_start_failure"},
                        },
                        "missing_commands": [],
                    }
                }
            ),
            "runtime_probe_failed",
        ),
        (
            1,
            _verdict(
                lanes={
                    "outline": {
                        "missing_modules": ["pydantic"],
                        "unresolved_modules": ["pydantic"],
                        "missing_commands": [],
                    }
                }
            ),
            "runtime_probe_failed",
        ),
        (
            1,
            _verdict(
                lanes={
                    "outline": {
                        "missing_modules": ["yaml"],
                        "unresolved_modules": [],
                        "missing_commands": [],
                    }
                }
            ),
            "runtime_lane_unavailable",
        ),
        (
            2,
            _verdict(blocking_lanes=["runtime-probe"], lanes={}),
            "runtime_probe_failed",
        ),
        (1, "not json", "runtime_probe_failed"),
    ],
    ids=[
        "ok",
        "bare-ok",
        "ok-but-lane-unavailable",
        "old-python",
        "cold-imports",
        "probe-could-not-start",
        "unresolved-without-a-reason",
        "missing-module",
        "probe-fault",
        "garbage",
    ],
)
def test_each_runtime_verdict_routes_to_its_own_repair(returncode, stdout, expected):
    module = _runtime_module()
    assert module.classify_runtime_check(returncode, stdout, "outline") == expected


def test_an_unreadable_database_is_refused(tmp_path):
    missing = tmp_path / "nowhere" / "tracking-database.json"
    _refused(missing, "owner_read_failed")


@pytest.mark.parametrize(
    "call,failure,expected",
    [
        (1, subprocess.TimeoutExpired("python", 120), "owner_read_failed"),
        (1, OSError("exec format error"), "owner_read_failed"),
        (2, subprocess.TimeoutExpired("python", 120), "owner_read_failed"),
        (2, OSError("exec format error"), "interpreter_unusable"),
        (3, subprocess.TimeoutExpired("python", 120), "runtime_probe_failed"),
        (3, OSError("exec format error"), "interpreter_unusable"),
    ],
    ids=[
        "host-read-timeout",
        "host-read-launch",
        "configured-read-timeout",
        "configured-read-launch",
        "runtime-check-timeout",
        "runtime-check-launch",
    ],
)
def test_each_call_site_names_its_own_repair(
    tmp_path, monkeypatch, call, failure, expected
):
    """A host read that hangs is never routed to replacing config.python_path."""
    module = _runtime_module()
    database = _database(tmp_path / "vault", python_path=sys.executable)
    real_run = subprocess.run
    calls: list[list[str]] = []

    def failing_at(command, **kwargs):
        calls.append(command)
        if len(calls) == call:
            raise failure
        return real_run(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", failing_at)

    with pytest.raises(module.RuntimeResolutionError) as refused:
        module.resolve(database)

    assert refused.value.reason_code == expected
    assert len(calls) == call

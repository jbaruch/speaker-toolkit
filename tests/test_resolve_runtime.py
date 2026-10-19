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


def test_an_interpreter_that_does_not_exist_is_refused_not_replaced(tmp_path):
    vault = tmp_path / "vault"
    database = _database(
        vault, python_path=str(tmp_path / "missing-python"), vault_root=str(vault)
    )
    _refused(database, "interpreter_unusable")


def test_an_interpreter_without_the_outline_lane_is_refused(tmp_path):
    """The interpreter passes the core lane and fails only the outline lane, so
    a resolver that regressed to requiring core alone would accept it."""
    interpreter = tmp_path / "python-without-pydantic"
    interpreter.write_text(
        "#!/bin/sh\n"
        'case "$1" in *check-runtime.py)\n'
        '  case " $* " in *" --require-lanes outline "*)\n'
        '    echo "missing pydantic" >&2; exit 1;;\n'
        "  esac\n"
        "  exit 0;;\n"
        "esac\n"
        f'exec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    interpreter.chmod(interpreter.stat().st_mode | stat.S_IXUSR)
    vault = tmp_path / "vault"
    database = _database(vault, python_path=str(interpreter), vault_root=str(vault))
    assert "Pydantic v2" in _refused(database, "runtime_lane_unavailable")


def test_an_unreadable_database_is_refused(tmp_path):
    missing = tmp_path / "nowhere" / "tracking-database.json"
    _refused(missing, "owner_read_failed")

"""Tests for resolve-interpreter.py — the toolkit interpreter resolver.

Locating `config.python_path`, confirming it exists and runs Python 3 is
deterministic, so it belongs in a script rather than in skill prose an agent
re-implements each session (rules/script-delegation.md).
"""

import json
import sys

import pytest


def _db(tmp_path, config, name="tracking-database.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"config": config}), encoding="utf-8")
    return path


def test_resolves_from_a_vault_root(resolve_interpreter, tmp_path):
    _db(tmp_path, {"python_path": sys.executable, "vault_root": str(tmp_path)})
    out = resolve_interpreter.resolve(tmp_path)
    assert out["ok"] is True
    assert out["python_path"] == sys.executable
    assert out["vault_root"] == str(tmp_path)


def test_resolves_from_the_database_path_directly(resolve_interpreter, tmp_path):
    db = _db(tmp_path, {"python_path": sys.executable})
    out = resolve_interpreter.resolve(db)
    assert out["python_path"] == sys.executable
    assert out["database"] == str(db)


def test_vault_root_defaults_to_the_database_parent(resolve_interpreter, tmp_path):
    db = _db(tmp_path, {"python_path": sys.executable})
    assert resolve_interpreter.resolve(db)["vault_root"] == str(tmp_path)


@pytest.mark.parametrize(
    "config,fragment",
    [
        ({}, "config.python_path is absent or empty"),
        ({"python_path": ""}, "config.python_path is absent or empty"),
        ({"python_path": "   "}, "config.python_path is absent or empty"),
        ({"python_path": 7}, "config.python_path is absent or empty"),
        ({"python_path": "/nope/python3"}, "does not exist"),
    ],
)
def test_unusable_interpreters_are_refused_with_the_repair_path(
    resolve_interpreter, tmp_path, config, fragment
):
    _db(tmp_path, config)
    with pytest.raises(ValueError) as excinfo:
        resolve_interpreter.resolve(tmp_path)
    assert fragment in str(excinfo.value)
    assert "vault-ingress Step 1" in str(excinfo.value)


def test_a_non_python_executable_is_refused(resolve_interpreter, tmp_path):
    """Existing and executable is not enough — it must actually be Python 3."""
    fake = tmp_path / "not-python"
    fake.write_text("#!/bin/sh\necho nope\n", encoding="utf-8")
    fake.chmod(0o755)
    _db(tmp_path, {"python_path": str(fake)})
    with pytest.raises(ValueError, match="not a working Python 3"):
        resolve_interpreter.resolve(tmp_path)


def test_a_missing_database_names_what_to_pass(resolve_interpreter, tmp_path):
    with pytest.raises(ValueError, match="pass a vault root or the database path"):
        resolve_interpreter.resolve(tmp_path)


def test_malformed_json_is_refused(resolve_interpreter, tmp_path):
    (tmp_path / "tracking-database.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        resolve_interpreter.resolve(tmp_path)


def test_a_database_without_a_config_object_is_refused(resolve_interpreter, tmp_path):
    (tmp_path / "tracking-database.json").write_text('{"config": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="no config object"):
        resolve_interpreter.resolve(tmp_path)


def test_main_emits_json_and_exits_zero(resolve_interpreter, tmp_path, capsys):
    _db(tmp_path, {"python_path": sys.executable})
    assert resolve_interpreter.main([str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["python_path"] == sys.executable


def test_main_exits_one_with_an_actionable_diagnostic(
    resolve_interpreter, tmp_path, capsys
):
    _db(tmp_path, {})
    assert resolve_interpreter.main([str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR:")
    assert "vault-ingress Step 1" in err

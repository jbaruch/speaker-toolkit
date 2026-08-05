"""Failure-boundary tests for the pattern-classification import bridge."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("missing classifier"),
        PermissionError("unreadable classifier"),
        SyntaxError("invalid classifier"),
        ImportError("classifier dependency unavailable"),
    ],
    ids=["missing", "unreadable", "syntax", "import"],
)
def test_runtime_load_failures_use_the_caller_contract(monkeypatch, failure):
    scripts = (
        Path(__file__).resolve().parents[1] / "skills" / "vault-profile" / "scripts"
    )
    monkeypatch.syspath_prepend(str(scripts))
    runtime = importlib.import_module("pattern_classification_runtime")
    runtime._exports.cache_clear()

    def fail_to_load(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(runtime.runpy, "run_path", fail_to_load)

    with pytest.raises(
        RuntimeError, match="classification runtime owner could not be loaded"
    ) as raised:
        runtime.validate_policy({})

    assert raised.value.__cause__ is failure
    runtime._exports.cache_clear()

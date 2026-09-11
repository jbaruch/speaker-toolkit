"""Deployment selection never uses a stale latest run or an ambiguous match."""

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills/shownotes-publisher/scripts/resolve-deploy-run.py"
)
SHA = "a" * 40
MATCH = {"databaseId": 42, "headSha": SHA, "event": "push", "headBranch": "main"}


@pytest.fixture
def resolver(monkeypatch):
    spec = importlib.util.spec_from_file_location("resolve_deploy_run", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "MAX_ATTEMPTS", 3)
    monkeypatch.setattr(module.time, "sleep", Mock())
    return module


def response(rows, code=0, stderr=""):
    return subprocess.CompletedProcess([], code, json.dumps(rows), stderr)


def invoke(module):
    return module.resolve_run("owner/site", "pages.yml", SHA, "push", "main")


def test_enqueue_latency_ignores_wrong_commit_event_and_branch(resolver, monkeypatch):
    runner = Mock(
        side_effect=[
            response([]),
            response(
                [
                    {**MATCH, "headSha": "b" * 40},
                    {**MATCH, "event": "pull_request"},
                    {**MATCH, "headBranch": "other"},
                ]
            ),
            response([MATCH]),
        ]
    )
    monkeypatch.setattr(resolver.subprocess, "run", runner)
    assert invoke(resolver) == 42
    assert runner.call_count == 3
    command = runner.call_args.args[0]
    for flag, value in [
        ("--repo", "owner/site"),
        ("--workflow", "pages.yml"),
        ("--commit", SHA),
        ("--event", "push"),
        ("--branch", "main"),
    ]:
        assert command[command.index(flag) + 1] == value
    assert resolver.time.sleep.call_count == 2


def test_ambiguous_runs_are_never_selected_by_recency(resolver, monkeypatch):
    monkeypatch.setattr(
        resolver.subprocess,
        "run",
        Mock(return_value=response([MATCH, {**MATCH, "databaseId": 43}])),
    )
    with pytest.raises(ValueError, match="Multiple deployment runs"):
        invoke(resolver)
    resolver.time.sleep.assert_not_called()


def test_missing_run_has_bounded_wait_and_actionable_failure(resolver, monkeypatch):
    runner = Mock(return_value=response([]))
    monkeypatch.setattr(resolver.subprocess, "run", runner)
    with pytest.raises(ValueError, match="No matching deployment run"):
        invoke(resolver)
    assert runner.call_count == 3
    assert resolver.time.sleep.call_count == 2


@pytest.mark.parametrize(
    "bad",
    [None, {}, [None], [{**MATCH, "databaseId": True}], [{**MATCH, "databaseId": 0}]],
)
def test_invalid_api_data_fails_without_waiting(resolver, monkeypatch, bad):
    monkeypatch.setattr(resolver.subprocess, "run", Mock(return_value=response(bad)))
    with pytest.raises(ValueError, match="invalid"):
        invoke(resolver)
    resolver.time.sleep.assert_not_called()


def test_api_failure_is_not_treated_as_enqueue_latency(resolver, monkeypatch):
    monkeypatch.setattr(
        resolver.subprocess,
        "run",
        Mock(return_value=response([], 1, "no workflow access")),
    )
    with pytest.raises(ValueError, match="no workflow access"):
        invoke(resolver)
    resolver.time.sleep.assert_not_called()


def test_process_boundary_emits_json_for_missing_gh(resolver, monkeypatch, capsys):
    monkeypatch.setattr(
        resolver.subprocess,
        "run",
        Mock(side_effect=FileNotFoundError("gh unavailable")),
    )
    assert (
        resolver.main(
            [
                "--repo",
                "owner/site",
                "--workflow",
                "pages.yml",
                "--commit",
                SHA,
                "--event",
                "push",
                "--branch",
                "main",
            ]
        )
        == 1
    )
    result = capsys.readouterr()
    assert json.loads(result.out)["ok"] is False
    assert "gh unavailable" in result.err
    assert "Traceback" not in result.err


def test_process_boundary_returns_selected_id(resolver, monkeypatch, capsys):
    monkeypatch.setattr(
        resolver.subprocess, "run", Mock(return_value=response([MATCH]))
    )
    assert (
        resolver.main(
            [
                "--repo",
                "owner/site",
                "--workflow",
                "pages.yml",
                "--commit",
                SHA,
                "--event",
                "push",
                "--branch",
                "main",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"ok": True, "database_id": 42}

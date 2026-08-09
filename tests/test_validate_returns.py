"""Tests for validate-returns.py — the read-only batch gate run after agents return.

`test_return_validation.py` covers the validation logic this script wraps. This
module covers the process contract: what the gate sees on stdout, on stderr, and
in the exit code (#203).
"""

import json
import subprocess
import sys

import pytest


def _return():
    """One minimally-valid return the batch gate accepts."""
    return {
        "filename": "2026-01-01-a-talk.md",
        "queue_claim": {
            "run_id": "reparse",
            "batch_id": "25",
            "reprocess_generation": 1,
        },
        "status": "skipped_no_sources",
    }


def test_a_clean_batch_leaves_one_json_document_on_stdout(
        validate_returns, tmp_path):
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps([_return()]), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, validate_returns.__file__, str(batch)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["input_files"] == [str(batch)]


def test_a_rejected_batch_exits_one_with_a_stderr_diagnostic(
        validate_returns, tmp_path):
    """Exit 1 is a failed validation — distinct from a failed validator."""
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps([{"filename": "x.md"}]), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, validate_returns.__file__, str(batch)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "ERROR:" in result.stderr
    assert "Traceback" not in result.stderr


# --- #203: the CLI has a closed failure boundary ---

def test_outer_boundary_reports_an_unexpected_failure_without_a_traceback(
        validate_returns, capsys, monkeypatch):
    """The gate reads a non-zero exit; it must still say what happened."""
    def explode(*_args, **_kwargs):
        raise RuntimeError("injected failure at /private/vault/returns/a.json")

    monkeypatch.setattr(validate_returns, "main", explode)

    assert validate_returns.run_cli() == 2

    captured = capsys.readouterr()
    assert captured.out == ""                     # stdout stays clean
    payload = json.loads(captured.err.splitlines()[0])
    assert payload["error"] == "validate_returns_unexpected_failure"
    assert payload["error_type"] == "RuntimeError"
    assert payload["origin"], "the failing code location must be reported"
    assert "injected failure" not in captured.err
    assert "/private/vault/returns/a.json" not in captured.err
    assert "Traceback" not in captured.err


def test_failure_note_says_the_batch_is_unvalidated_not_invalid(
        validate_returns, capsys, monkeypatch):
    """A broken validator must never read as a clean batch."""
    def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(validate_returns, "main", explode)
    validate_returns.run_cli()

    assert "UNVALIDATED" in capsys.readouterr().err


def test_outer_boundary_does_not_catch_sys_exit(validate_returns, monkeypatch):
    """main()'s own documented sys.exit(1) validation failures keep exit 1."""
    def bail(*_args, **_kwargs):
        raise SystemExit(1)

    monkeypatch.setattr(validate_returns, "main", bail)
    with pytest.raises(SystemExit) as excinfo:
        validate_returns.run_cli()
    assert excinfo.value.code == 1


def test_outer_boundary_lets_a_clean_run_report_success(
        validate_returns, monkeypatch):
    monkeypatch.setattr(validate_returns, "main", lambda *a, **k: None)
    assert validate_returns.run_cli() == 0


def test_a_failed_report_write_does_not_leave_partial_json_on_stdout(
        validate_returns, tmp_path, capsys, monkeypatch):
    """The report is serialized before it is written, so it lands whole or not at all."""
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps([_return()]), encoding="utf-8")

    real_write = validate_returns.sys.stdout.write

    def refuse_report(text):
        if text.startswith("{"):
            raise OSError("stdout closed")
        return real_write(text)

    monkeypatch.setattr(validate_returns.sys.stdout, "write", refuse_report)
    monkeypatch.setattr(sys, "argv", ["validate-returns.py", str(batch)])

    assert validate_returns.run_cli() == 2

    captured = capsys.readouterr()
    assert captured.out == "", "a truncated document is worse than none"
    payload = json.loads(captured.err.splitlines()[0])
    assert payload["error"] == "validate_returns_unexpected_failure"

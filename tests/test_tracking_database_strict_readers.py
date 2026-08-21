"""Every public tracking-database reader shares the owner strict decoder."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

import importlib as _importlib
import sys as _sys

_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "vault-ingress" / "scripts"
if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))
_FUTURE_TALK_SCHEMA_VERSION = (
    _importlib.import_module("tracking_database").TALK_RECORD_SCHEMA_VERSION + 1
)
_FUTURE_ROOT_SCHEMA_VERSION = (
    _importlib.import_module("tracking_database").TRACKING_DATABASE_SCHEMA_VERSION + 1
)


STRICT_INVALID_CASES = (
    pytest.param(
        b'{"talks": [], "talks": [{"filename": "lost.md"}]}\n',
        "duplicate object key 'talks'",
        id="duplicate-top-level",
    ),
    pytest.param(
        b'{"config": {}, "talks": [{"filename": "a.md", '
        b'"source_identity": {"video_id": "one", "video_id": "two"}}]}\n',
        "duplicate object key 'video_id'",
        id="duplicate-nested",
    ),
    pytest.param(
        b'{"config": {}, "talks": [], "value": NaN}\n',
        "non-standard JSON number NaN",
        id="nan",
    ),
    pytest.param(
        b'{"config": {}, "talks": [], "value": Infinity}\n',
        "non-standard JSON number Infinity",
        id="infinity",
    ),
    pytest.param(
        b'{"config": {}, "talks": [], "value": -Infinity}\n',
        "non-standard JSON number -Infinity",
        id="negative-infinity",
    ),
    pytest.param(
        b'{"config": {}, "talks": ["\xff"]}\n',
        "not valid UTF-8",
        id="invalid-utf8",
    ),
    pytest.param(
        b'["not", "an", "object"]\n',
        "root must be a JSON object",
        id="non-object-root",
    ),
)


def _database(tmp_path: Path, raw: bytes) -> Path:
    path = tmp_path / "tracking-database.json"
    path.write_bytes(raw)
    return path


def _closed_messages(tracking_database_io) -> set[str]:
    """The whole vocabulary a public reader may say about a read failure.

    Membership in a fixed set is itself the leak guard: a message drawn from
    these constants cannot carry the offending key, value, or host path.
    """
    return {
        text for _code, text in tracking_database_io.DATABASE_READ_DIAGNOSTICS.values()
    } | {tracking_database_io.DATABASE_READ_FALLBACK[1]}


def _says_one_closed_message(text: str, tracking_database_io) -> bool:
    return any(message in text for message in _closed_messages(tracking_database_io))


def _assert_defect_detail_absent(text: str, detail: str, tracking_database_io) -> None:
    """Assert the decoder's account of the defect never reaches ``text``.

    Two of the cases inject nothing the closed vocabulary does not already say
    — invalid UTF-8 and a non-object root — so for those the detail IS the
    closed prose and its absence cannot be asserted. Every other case names a
    key or value taken from the input, which must never surface.
    """
    if any(detail in closed for closed in _closed_messages(tracking_database_io)):
        return
    assert detail not in text


def test_owner_reader_accepts_implicit_legacy_after_schema_assessment(
    read_tracking_database,
    tmp_path: Path,
) -> None:
    raw = b'{"config":{},"talks":[]}\n'
    database = _database(tmp_path, raw)

    report = read_tracking_database.execute(database)

    assert report["ok"] is True
    assert report["database"] == {"config": {}, "talks": []}
    assert database.read_bytes() == raw


@pytest.mark.parametrize(
    "payload",
    [
        {
            # Derived, never a literal — the same hazard the talk-record case
            # below names: a pinned number stops being "future" the moment the
            # schema reaches it, and the payload then exercises a different
            # rejection path while still reading as a future-root test.
            "schema_version": _FUTURE_ROOT_SCHEMA_VERSION,
            "future_config": ["no old config/talks shape"],
        },
        {
            "config": {},
            "talks": [
                {
                    # One above the current record schema: a literal stops
                    # being "future" the moment the schema reaches it, and the
                    # payload then exercises a different rejection path.
                    "schema_version": _FUTURE_TALK_SCHEMA_VERSION,
                    "talk_id": "future-talk",
                }
            ],
        },
    ],
)
def test_owner_reader_rejects_no_usable_owner_state_without_database_output(
    read_tracking_database,
    tracking_database_io,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: dict[str, object],
) -> None:
    raw = (json.dumps(payload) + "\n").encode()
    database = _database(tmp_path, raw)

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="no usable legacy/current owner state",
    ):
        read_tracking_database.execute(database)

    result = read_tracking_database.main([str(database)])
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert result == 2
    assert output["ok"] is False
    assert "database" not in output
    assert output["error"] in _closed_messages(tracking_database_io)
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_owner_reader_reports_a_closed_code_without_echoing_the_defect(
    read_tracking_database,
    tracking_database_io,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    message: str,
) -> None:
    """Every agent-driven read goes through this script's failure path.

    A decoder message names the rejected key or value verbatim and the host
    database path — input data, never diagnostics (#275, `no-secrets`).
    """
    database = _database(tmp_path, raw)

    result = read_tracking_database.main([str(database)])

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert result == 2
    assert output["ok"] is False
    assert output["code"] in {
        "database_encoding_invalid",
        "database_json_invalid",
        "database_unreadable",
    }
    assert output["error"] in _closed_messages(tracking_database_io)
    # Neither the injected defect nor the host path rides out on either stream.
    _assert_defect_detail_absent(captured.out, message, tracking_database_io)
    _assert_defect_detail_absent(captured.err, message, tracking_database_io)
    assert str(database) not in captured.out + captured.err
    assert database.read_bytes() == raw


@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        ("missing", "pass the canonical"),
        ("symlink", "symbolic link"),
        ("directory", "not a regular file"),
    ],
)
def test_a_path_that_never_reached_the_decoder_still_says_what_to_do(
    read_tracking_database,
    tracking_database_io,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    shape: str,
    expected: str,
) -> None:
    """Redaction must not cost actionability.

    These failures never reach the decoder, so there is no rejected content to
    withhold — only the shape of the path, which is what the caller has to fix.
    Collapsing them into the generic fallback would leave a symlinked database
    reported as "could not be read", with no next step (`error-handling`).
    """
    database = tmp_path / "tracking-database.json"
    if shape == "symlink":
        database.symlink_to(tmp_path / "elsewhere.json")
    elif shape == "directory":
        database.mkdir()

    result = read_tracking_database.main([str(database)])

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert result == 2
    assert output["code"] == "database_unreadable"
    assert output["error"] in _closed_messages(tracking_database_io)
    assert expected in output["error"]
    assert str(database) not in captured.out + captured.err


def test_a_concurrent_write_still_says_to_rerun(
    read_tracking_database,
    tracking_database_io,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is wrong with the file; rerunning is the whole remedy.

    A conflict routed through the generic fallback would report "could not be
    read" and drop the one instruction that fixes it (`error-handling` →
    Actionable Messages).
    """
    database = _database(tmp_path, b'{"config":{},"talks":[]}\n')
    real_snapshot = read_tracking_database.snapshot_tracking_database

    def conflict(path):
        real_snapshot(path)
        raise tracking_database_io.TrackingDatabaseConflictError(
            "tracking database changed while it was read; rerun the operation"
        )

    monkeypatch.setattr(read_tracking_database, "snapshot_tracking_database", conflict)

    result = read_tracking_database.main([str(database)])

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert result == 2
    assert output["code"] == "database_generation_conflict"
    assert "rerun the operation" in output["error"]
    assert output["error"] in _closed_messages(tracking_database_io)
    assert str(database) not in captured.out + captured.err


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_owner_reader_rejects_every_strict_json_defect_without_rewrite(
    read_tracking_database,
    tracking_database_io,
    tmp_path: Path,
    raw: bytes,
    message: str,
) -> None:
    database = _database(tmp_path, raw)

    with pytest.raises(tracking_database_io.TrackingDatabaseIOError, match=message):
        read_tracking_database.execute(database)

    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_preflight_blocks_every_strict_json_defect_without_rewrite(
    preflight_vault,
    tmp_path: Path,
    raw: bytes,
    message: str,
) -> None:
    database = _database(tmp_path, raw)

    report = preflight_vault.run_preflight(database)

    assert report["blocking_count"] == 1
    assert report["warning_count"] == 0
    assert report["findings"][0]["code"] in {
        "database_encoding_invalid",
        "database_json_invalid",
    }
    # The public report's message is derived from the decoder's typed reason,
    # never from its text: the decoder names the offending key or value, and
    # those are input data (#200, no-secrets). The message must be one of the
    # closed set, and must not echo the detail this case injected.
    closed_messages = {
        text for _code, text in preflight_vault._DATABASE_READ_DIAGNOSTICS.values()
    } | {preflight_vault._DATABASE_READ_FALLBACK[1]}
    # Membership in a fixed set is itself the leak guard: a message drawn from
    # seven constants cannot carry the offending key or value.
    assert report["findings"][0]["message"] in closed_messages
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_source_audit_stops_before_metadata_fetch_without_rewrite(
    audit_source_identities,
    tracking_database_io,
    tmp_path: Path,
    raw: bytes,
    message: str,
) -> None:
    database = _database(tmp_path, raw)
    fetched: list[str] = []

    def unexpected_fetch(video_id: str) -> dict[str, object]:
        fetched.append(video_id)
        return {}

    report = audit_source_identities.audit_path(
        database,
        metadata_fetcher=unexpected_fetch,
        captured_at="2026-08-01T12:00:00+00:00",
    )

    assert report["complete"] is False
    assert report["findings"][0]["code"] == "database_unreadable"
    # The report is written out and read by agents, so its evidence carries the
    # typed code and closed prose, never the decoder's text (#275).
    evidence = report["findings"][0]["evidence"]
    assert evidence["error"] in _closed_messages(tracking_database_io)
    _assert_defect_detail_absent(json.dumps(report), message, tracking_database_io)
    assert fetched == []
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_analysis_reader_fails_before_output_without_rewrite(
    write_analysis,
    tracking_database_io,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    message: str,
) -> None:
    database = _database(tmp_path, raw)

    with pytest.raises(SystemExit) as stopped:
        write_analysis.load_tracking_database(database)

    captured = capsys.readouterr()
    assert stopped.value.code == 1
    assert _says_one_closed_message(captured.err, tracking_database_io)
    _assert_defect_detail_absent(captured.err, message, tracking_database_io)
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_profile_loader_fails_before_reading_other_vault_outputs(
    load_vault,
    tracking_database_io,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    message: str,
) -> None:
    database = _database(tmp_path, raw)

    result = load_vault.main(
        ["load-vault.py", str(tmp_path), "--as-of", "2026-08-01T12:00:00+00:00"]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert _says_one_closed_message(captured.err, tracking_database_io)
    _assert_defect_detail_absent(captured.err, message, tracking_database_io)
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_section15_reader_fails_before_summary_replacement(
    section15_pattern_history,
    tracking_database_io,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    message: str,
) -> None:
    database = _database(tmp_path, raw)
    profile = tmp_path / "pattern-profile.json"
    profile.write_text("{}\n", encoding="utf-8")
    summary = tmp_path / "rhetoric-style-summary.md"
    original_summary = b"## 15. Pattern History\n\nOriginal.\n"
    summary.write_bytes(original_summary)

    result = section15_pattern_history.main(
        ["replace", str(summary), str(profile), str(database)]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert _says_one_closed_message(captured.err, tracking_database_io)
    _assert_defect_detail_absent(captured.err, message, tracking_database_io)
    # The host path is the other half of what redaction keeps out of output;
    # the caller supplied it and already knows it.
    assert str(database) not in captured.err
    assert summary.read_bytes() == original_summary
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_profile_validator_rejects_live_database_before_snapshot_generation(
    validate_profile,
    tracking_database_io,
    tmp_path: Path,
    raw: bytes,
    message: str,
) -> None:
    database = _database(tmp_path, raw)

    with pytest.raises(ValueError) as caught:
        validate_profile._load_live_pattern_snapshot(tmp_path, {})

    # This error is printed and emitted in the result object, so it carries
    # closed prose rather than the decoder's text (#275).
    assert _says_one_closed_message(str(caught.value), tracking_database_io)
    _assert_defect_detail_absent(str(caught.value), message, tracking_database_io)
    assert database.read_bytes() == raw

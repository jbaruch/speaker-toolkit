"""Every public tracking-database reader shares the owner strict decoder."""

from __future__ import annotations

from pathlib import Path
import json

import pytest


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
            "schema_version": 2,
            "future_config": ["no old config/talks shape"],
        },
        {
            "config": {},
            "talks": [
                {
                    "schema_version": 6,
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
    assert database.read_bytes() == raw


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
    assert message in report["findings"][0]["evidence"]["error"]
    assert fetched == []
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_analysis_reader_fails_before_output_without_rewrite(
    write_analysis,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    message: str,
) -> None:
    database = _database(tmp_path, raw)

    with pytest.raises(SystemExit) as stopped:
        write_analysis.load_tracking_database(database)

    assert stopped.value.code == 1
    assert message in capsys.readouterr().err
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_profile_loader_fails_before_reading_other_vault_outputs(
    load_vault,
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
    assert message in captured.err
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_section15_reader_fails_before_summary_replacement(
    section15_pattern_history,
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
    assert message in captured.err
    assert summary.read_bytes() == original_summary
    assert database.read_bytes() == raw


@pytest.mark.parametrize(("raw", "message"), STRICT_INVALID_CASES)
def test_profile_validator_rejects_live_database_before_snapshot_generation(
    validate_profile,
    tmp_path: Path,
    raw: bytes,
    message: str,
) -> None:
    database = _database(tmp_path, raw)

    with pytest.raises(ValueError, match=message):
        validate_profile._load_live_pattern_snapshot(tmp_path, {})

    assert database.read_bytes() == raw

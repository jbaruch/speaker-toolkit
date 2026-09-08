"""The additive owner-root migration never changes an analysis or claim contract."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from conftest import CURRENT_ROOT_SCHEMA_VERSION as CURRENT_ROOT
import pytest

from test_tracking_database_schema import (
    _expected_migration,
    _legacy_database,
    _qr_repair_with_active_claim,
    _write_database,
)


def _root_database(tracking_database, claim_version=None):
    if claim_version is None:
        database = _expected_migration(_legacy_database())
    else:
        database = _qr_repair_with_active_claim(tracking_database, claim_version)
        database["qr_codes"][0]["schema_version"] = 1
    database["schema_version"] = 2
    return database


@pytest.mark.parametrize("claim_version", [None, *range(1, 8)])
@pytest.mark.parametrize("talk_version", [1, 5, 6, 7])
def test_root_upgrade_preserves_every_child_value_and_reader_contract(
    tracking_database, queue_state, claim_version, talk_version
):
    database = _root_database(tracking_database, claim_version)
    database["talks"][0]["schema_version"] = talk_version
    before = copy.deepcopy(database)
    claims_before = queue_state.reconstruct_run(database, "schema-test")
    assert tracking_database.assess_tracking_database(database).usable is True

    result = tracking_database.migrate_tracking_database_root(database)

    expected = copy.deepcopy(before)
    expected["schema_version"] = CURRENT_ROOT
    assert result.database == expected
    assert database == before
    assert result.changed is True
    assert (result.from_schema_version, result.to_schema_version) == (2, CURRENT_ROOT)
    assert not any(result.record_counts.values())
    assert (
        tracking_database.assess_tracking_database(result.database).state == "current"
    )
    assert queue_state.reconstruct_run(result.database, "schema-test") == claims_before
    repeat = tracking_database.migrate_tracking_database_root(result.database)
    assert repeat.database == expected
    assert repeat.changed is False


@pytest.mark.parametrize(
    "defect",
    [
        "root_missing",
        "root_zero",
        "root_one",
        "root_future",
        "root_bool",
        "config_legacy",
        "talk_future",
        "qr_unstamped",
        "claim_future",
        "claim_invalid",
        "claim_status_drift",
        "collection_missing",
        "duplicate_talk",
    ],
)
def test_root_upgrade_refuses_unrelated_or_ambiguous_owner_state(
    tracking_database, defect
):
    database = _root_database(tracking_database, 7)
    if defect == "root_missing":
        del database["schema_version"]
    elif defect.startswith("root_"):
        database["schema_version"] = {
            "root_zero": 0,
            "root_one": 1,
            "root_future": 99,
            "root_bool": True,
        }[defect]
    elif defect == "config_legacy":
        database["config"]["schema_version"] = 1
    elif defect == "talk_future":
        database["talks"][0]["schema_version"] = 99
    elif defect == "qr_unstamped":
        del database["qr_codes"][0]["schema_version"]
    elif defect == "claim_future":
        database["talks"][0]["_queue_claim"]["schema_version"] = 99
    elif defect == "claim_invalid":
        database["talks"][0]["_queue_claim"]["state"] = "invalid"
    elif defect == "claim_status_drift":
        database["talks"][0]["status"] = "processed"
    elif defect == "collection_missing":
        del database["qr_codes"]
    else:
        database["talks"].append(copy.deepcopy(database["talks"][0]))
    before = copy.deepcopy(database)
    with pytest.raises(tracking_database.TrackingDatabaseError):
        tracking_database.migrate_tracking_database_root(database)
    assert database == before


def test_root_cli_preserves_evidence_backups_and_noop_inode(
    tracking_database, migrate_tracking_database, tmp_path, capsys
):
    path = tmp_path / "tracking-database.json"
    database = _root_database(tracking_database, 7)
    # Full migration would requeue this legacy observation; root-only must not.
    completed = copy.deepcopy(database["talks"][0])
    completed.update(filename="completed.md", status="processed")
    for key in ("_queue_claim", "_queue_claim_history", "reprocess_generation"):
        completed.pop(key)
    database["talks"].append(completed)
    raw = _write_database(path, database)
    assert migrate_tracking_database.main([str(path), "--root-only"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["migration_scope"] == "root_only"
    assert preview["persisted_observations"] == {"repaired": 0, "requeued": 0}
    assert preview["database_written"] is False
    assert path.read_bytes() == raw
    assert not (tmp_path / ".backups").exists()
    for extra in ([], ["--expected-sha256", "0" * 64]):
        assert (
            migrate_tracking_database.main(
                [str(path), "--root-only", "--apply", *extra]
            )
            == 2
        )
        assert json.loads(capsys.readouterr().out)["ok"] is False
        assert path.read_bytes() == raw
        assert not (tmp_path / ".backups").exists()
    applied = migrate_tracking_database.execute(
        path, apply=True, expected_sha256=preview["input_sha256"], root_only=True
    )
    expected = copy.deepcopy(database)
    expected["schema_version"] = CURRENT_ROOT
    assert json.loads(path.read_bytes()) == expected
    assert applied["output_sha256"] == preview["output_sha256"]
    assert Path(applied["backup"]).read_bytes() == raw
    installed = path.read_bytes()
    inode = path.stat().st_ino
    repeated = migrate_tracking_database.execute(
        path, apply=True, expected_sha256=applied["output_sha256"], root_only=True
    )
    assert repeated["changed"] is False
    assert repeated["database_written"] is False
    assert repeated["backup"] is None
    assert path.read_bytes() == installed
    assert path.stat().st_ino == inode


@pytest.mark.parametrize("writer", ["queue", "results"])
def test_root_migration_rejects_stale_writers_and_allows_claim_preserving_reload(
    tracking_database,
    tracking_database_io,
    migrate_tracking_database,
    queue_state,
    persist_results,
    tmp_path,
    writer,
):
    path = tmp_path / "tracking-database.json"
    database = _root_database(tracking_database, 7)
    raw = _write_database(path, database)
    stale = tracking_database_io.snapshot_tracking_database(path)
    applied = migrate_tracking_database.execute(
        path, apply=True, expected_sha256=stale.sha256, root_only=True
    )
    installed = path.read_bytes()
    if writer == "queue":
        write, read, error = (
            queue_state.write_database_atomically,
            queue_state.load_database_snapshot,
            queue_state.QueueStateError,
        )
    else:
        write, read, error = (
            persist_results.atomic_write_json,
            persist_results.load_tracking_database,
            ValueError,
        )
    with pytest.raises(error, match="generation changed"):
        write(path, database, expected_snapshot=stale)
    assert path.read_bytes() == installed
    assert Path(applied["backup"]).read_bytes() == raw
    current, fresh = read(path)
    assert current["talks"] == database["talks"]
    assert current["schema_version"] == CURRENT_ROOT
    current["config"]["speaker_name"] = "Synthetic speaker"
    assert write(path, current, expected_snapshot=fresh).installed is True
    reloaded, _ = read(path)
    assert reloaded == current
    assert reloaded["talks"] == database["talks"]


def test_root_migration_preserves_final_window_competing_writer(
    tracking_database,
    tracking_database_io,
    migrate_tracking_database,
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "tracking-database.json"
    database = _root_database(tracking_database, 7)
    _write_database(path, database)
    preview = migrate_tracking_database.execute(
        path, apply=False, expected_sha256=None, root_only=True
    )
    competing = copy.deepcopy(database)
    competing["config"]["speaker_name"] = "Concurrent writer"
    original_stage = tracking_database_io._stage_candidate
    competing_raw = b""

    def stage_and_replace(target, candidate, mode):
        nonlocal competing_raw
        stage = original_stage(target, candidate, mode)
        replacement = tmp_path / "competing.json"
        competing_raw = _write_database(replacement, competing)
        os.replace(replacement, path)
        return stage

    monkeypatch.setattr(tracking_database_io, "_stage_candidate", stage_and_replace)
    with pytest.raises(
        migrate_tracking_database.TrackingDatabaseMigrationError,
        match="generation changed",
    ):
        migrate_tracking_database.execute(
            path, apply=True, expected_sha256=preview["input_sha256"], root_only=True
        )
    assert path.read_bytes() == competing_raw
    assert not (tmp_path / ".backups").exists()


def test_root_and_qr_modes_are_exclusive_before_any_file_access(
    migrate_tracking_database, tmp_path, capsys
):
    path = tmp_path / "absent.json"
    assert (
        migrate_tracking_database.main(
            [str(path), "--root-only", "--repair-missing-qr-versions"]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["ok"] is False
    with pytest.raises(
        migrate_tracking_database.TrackingDatabaseMigrationError, match="not both"
    ):
        migrate_tracking_database.execute(
            path,
            apply=False,
            expected_sha256=None,
            root_only=True,
            repair_missing_qr_versions=True,
        )
    assert not path.exists()


def test_full_migration_still_refuses_active_claims(tracking_database):
    database = _root_database(tracking_database, 7)
    before = copy.deepcopy(database)
    with pytest.raises(
        tracking_database.TrackingDatabaseError, match="active queue writers"
    ):
        tracking_database.migrate_tracking_database(database)
    assert database == before


@pytest.mark.parametrize("claim_version", range(1, 8))
def test_existing_claim_replays_through_current_queue_cli_after_root_migration(
    tracking_database,
    migrate_tracking_database,
    queue_state,
    tmp_path,
    capsys,
    claim_version,
):
    path = tmp_path / "tracking-database.json"
    database = _root_database(tracking_database, claim_version)
    _write_database(path, database)
    preview = migrate_tracking_database.execute(
        path, apply=False, expected_sha256=None, root_only=True
    )
    migrate_tracking_database.execute(
        path, apply=True, expected_sha256=preview["input_sha256"], root_only=True
    )
    installed = path.read_bytes()

    assert (
        queue_state.main(
            [
                str(path),
                "claim",
                "--run-id",
                "schema-test",
                "--batch-id",
                "active",
                "--now",
                "2026-07-31T12:05:00+00:00",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["idempotent_replay"] is True
    assert len(report["claimed"]) == 1
    assert report["claimed"][0]["schema_version"] == claim_version
    assert report["claimed"][0]["reprocess_generation"] == 2
    assert path.read_bytes() == installed
    assert json.loads(installed)["talks"] == database["talks"]


@pytest.mark.parametrize("start", [2, 3])
def test_a_pre_provenance_root_migrates_to_current_preserving_children(
    tracking_database, start
):
    """The root advances; no provenance is invented for a database without any."""
    database = _root_database(tracking_database)
    database["schema_version"] = start
    before = copy.deepcopy(database)

    result = tracking_database.migrate_tracking_database_root(database)

    expected = copy.deepcopy(before)
    expected["schema_version"] = CURRENT_ROOT
    assert result.database == expected
    assert "date_provenance" not in result.database
    assert (result.from_schema_version, result.to_schema_version) == (
        start,
        CURRENT_ROOT,
    )
    assert not any(result.record_counts.values())


def test_a_pre_provenance_root_carrying_the_collection_is_not_current(
    tracking_database,
):
    """The collection IS the current root shape, so an older root claiming it
    must not read as current — the fix is the migration, not a refusal."""
    database = _root_database(tracking_database)
    database["schema_version"] = 3
    database["date_provenance"] = [
        {
            "schema_version": 1,
            "talk_filename": database["talks"][0]["filename"],
            "method": "organizer_program",
            "evidence": "published schedule",
            "established_at": "2026-09-08T00:00:00Z",
        }
    ]

    assessment = tracking_database.assess_tracking_database(database)

    assert assessment.state != "current"
    migrated = tracking_database.migrate_tracking_database_root(database).database
    assert migrated["date_provenance"] == database["date_provenance"]
    assert tracking_database.assess_tracking_database(migrated).state == "current"

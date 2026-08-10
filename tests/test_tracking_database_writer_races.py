"""Every public tracking-database writer rejects a final-window generation swap."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import threading

import pytest

from conftest import current_tracking_config


def _write(path: Path, value: object) -> bytes:
    raw = json.dumps(value, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return raw


def _current_database() -> dict[str, object]:
    return {
        "schema_version": 1,
        "config": current_tracking_config(),
        "talks": [],
        "pptx_catalog": [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }


def _inject_final_window_replacement(
    tracking_database_io,
    monkeypatch: pytest.MonkeyPatch,
    concurrent_payload: dict[str, object],
) -> bytes:
    original_stage = tracking_database_io._stage_candidate
    concurrent_raw = json.dumps(concurrent_payload, indent=2).encode("utf-8") + b"\n"

    def stage_then_replace(path: Path, candidate: bytes, mode: int) -> str:
        temporary = original_stage(path, candidate, mode)
        replacement = path.parent / "concurrent-generation.json"
        replacement.write_bytes(concurrent_raw)
        os.replace(replacement, path)
        return temporary

    monkeypatch.setattr(tracking_database_io, "_stage_candidate", stage_then_replace)
    return concurrent_raw


def test_queue_writer_preserves_final_window_generation(
    queue_state,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"config": {}, "talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    concurrent = _inject_final_window_replacement(
        tracking_database_io,
        monkeypatch,
        {"config": {}, "talks": [], "writer": "concurrent"},
    )

    with pytest.raises(queue_state.QueueStateError, match="generation changed"):
        queue_state.write_database_atomically(
            path,
            {"config": {}, "talks": [], "writer": "queue"},
            expected_snapshot=expected,
        )

    assert path.read_bytes() == concurrent


def test_persist_results_writer_preserves_final_window_generation(
    persist_results,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"config": {}, "talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    concurrent = _inject_final_window_replacement(
        tracking_database_io,
        monkeypatch,
        {"config": {}, "talks": [], "writer": "concurrent"},
    )

    with pytest.raises(ValueError, match="generation changed"):
        persist_results.atomic_write_json(
            path,
            {"config": {}, "talks": [], "writer": "persist-results"},
            expected_snapshot=expected,
        )

    assert path.read_bytes() == concurrent


def test_source_repair_writer_preserves_final_window_generation(
    apply_source_repairs,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"config": {}, "talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    concurrent = _inject_final_window_replacement(
        tracking_database_io,
        monkeypatch,
        {"config": {}, "talks": [], "writer": "concurrent"},
    )

    with pytest.raises(
        apply_source_repairs.SourceRepairError,
        match="generation changed",
    ):
        apply_source_repairs.atomic_write(
            path,
            json.dumps({"config": {}, "talks": [], "writer": "source-repair"}) + "\n",
            expected_snapshot=expected,
        )

    assert path.read_bytes() == concurrent


def test_shownotes_writer_preserves_final_window_generation(
    scan_shownotes_module,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"config": {}, "talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    concurrent = _inject_final_window_replacement(
        tracking_database_io,
        monkeypatch,
        {"config": {}, "talks": [], "writer": "concurrent"},
    )

    with pytest.raises(
        scan_shownotes_module.ShownotesScanError,
        match="generation changed after the scan",
    ):
        scan_shownotes_module._atomic_write_database(
            path,
            {"config": {}, "talks": [], "writer": "shownotes"},
            expected_snapshot=expected,
        )

    assert path.read_bytes() == concurrent


def test_qr_writer_preserves_final_window_generation(
    generate_qr,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    database = _current_database()
    _write(path, database)
    expected = tracking_database_io.snapshot_tracking_database(path)
    concurrent = _inject_final_window_replacement(
        tracking_database_io,
        monkeypatch,
        {"config": {}, "talks": [], "qr_codes": [], "writer": "concurrent"},
    )

    with pytest.raises(ValueError, match="generation changed"):
        generate_qr.write_tracking_db(
            expected,
            database | {"writer": "qr"},
        )

    assert path.read_bytes() == concurrent


def test_owner_mutation_cli_preserves_final_window_generation(
    mutate_tracking_database,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, _current_database())
    plan = tmp_path / "plan.json"
    _write(
        plan,
        {
            "schema_version": 1,
            "mutations": [
                {
                    "kind": "set_config",
                    "path": ["speaker_name"],
                    "expect": {"$missing": True},
                    "value": "Ada",
                }
            ],
        },
    )
    dry_run = mutate_tracking_database.execute(
        path,
        plan,
        apply=False,
        expected_sha256=None,
    )
    concurrent = _inject_final_window_replacement(
        tracking_database_io,
        monkeypatch,
        {"config": {}, "talks": [], "writer": "concurrent"},
    )

    with pytest.raises(
        mutate_tracking_database.TrackingDatabaseMutationError,
        match="generation changed",
    ):
        mutate_tracking_database.execute(
            path,
            plan,
            apply=True,
            expected_sha256=dry_run["input_sha256"],
        )

    assert path.read_bytes() == concurrent


def test_queue_and_persistence_writers_serialize_then_reject_stale_input(
    cooperative_lock,
    queue_state,
    persist_results,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"config": {}, "talks": []})
    queue_snapshot = tracking_database_io.snapshot_tracking_database(path)
    persistence_snapshot = tracking_database_io.snapshot_tracking_database(path)
    original_stage = tracking_database_io._stage_candidate
    real_flock = cooperative_lock.fcntl.flock
    persistence_attempted = threading.Event()
    persistence_errors: list[Exception] = []
    persistence_thread: threading.Thread | None = None

    def observed_flock(descriptor: int, operation: int) -> object:
        if (
            threading.current_thread().name == "persistence-writer"
            and operation == fcntl.LOCK_EX
        ):
            persistence_attempted.set()
        return real_flock(descriptor, operation)

    def persistence_writer() -> None:
        try:
            persist_results.atomic_write_json(
                path,
                {"config": {}, "talks": [], "writer": "persistence"},
                expected_snapshot=persistence_snapshot,
            )
        except ValueError as exc:
            persistence_errors.append(exc)

    def stage_queue_and_contend(target: Path, candidate: bytes, mode: int) -> str:
        nonlocal persistence_thread
        temporary = original_stage(target, candidate, mode)
        persistence_thread = threading.Thread(
            target=persistence_writer,
            name="persistence-writer",
        )
        persistence_thread.start()
        assert persistence_attempted.wait(timeout=5)
        assert persistence_errors == []
        return temporary

    monkeypatch.setattr(cooperative_lock.fcntl, "flock", observed_flock)
    monkeypatch.setattr(
        tracking_database_io,
        "_stage_candidate",
        stage_queue_and_contend,
    )

    queue_result = queue_state.write_database_atomically(
        path,
        {"config": {}, "talks": [], "writer": "queue"},
        expected_snapshot=queue_snapshot,
    )
    assert persistence_thread is not None
    persistence_thread.join(timeout=5)

    assert not persistence_thread.is_alive()
    assert queue_result.installed is True
    assert len(persistence_errors) == 1
    assert isinstance(persistence_errors[0], ValueError)
    assert "generation changed" in str(persistence_errors[0])
    assert json.loads(path.read_text(encoding="utf-8"))["writer"] == "queue"

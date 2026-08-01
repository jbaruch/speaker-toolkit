"""Adversarial contract tests for the shared tracking-database transaction."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest


def _write(path: Path, value: object) -> bytes:
    raw = json.dumps(value, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return raw


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b'{"talks": [], "talks": [{"filename": "lost.md"}]}\n', "duplicate object key 'talks'"),
        (
            b'{"talks": [{"filename": "a.md", "source_identity": '
            b'{"video_id": "one", "video_id": "two"}}]}\n',
            "duplicate object key 'video_id'",
        ),
        (b'{"talks": [], "value": NaN}\n', "non-standard JSON number NaN"),
        (b'{"talks": [], "value": Infinity}\n', "non-standard JSON number Infinity"),
        (b'{"talks": [], "value": -Infinity}\n', "non-standard JSON number -Infinity"),
        (b'{"talks": ["\xff"]}\n', "not valid UTF-8"),
        (b'["not", "an", "object"]\n', "root must be a JSON object"),
    ],
)
def test_strict_decoder_rejects_ambiguous_json_without_changing_bytes(
    tracking_database_io,
    tmp_path: Path,
    raw: bytes,
    message: str,
) -> None:
    path = tmp_path / "tracking-database.json"
    path.write_bytes(raw)

    snapshot = tracking_database_io.snapshot_tracking_database(path)
    with pytest.raises(tracking_database_io.TrackingDatabaseIOError, match=message):
        tracking_database_io.decode_json_object(snapshot)

    assert path.read_bytes() == raw


def test_snapshot_rejects_final_symlink(tracking_database_io, tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    _write(target, {"talks": []})
    link = tmp_path / "tracking-database.json"
    link.symlink_to(target)

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="symbolic link",
    ):
        tracking_database_io.snapshot_tracking_database(link)


def test_renderer_refuses_to_create_non_standard_json(tracking_database_io) -> None:
    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="candidate is not strict JSON",
    ):
        tracking_database_io.render_json_object({"value": float("nan")})


def test_commit_refuses_an_invalid_candidate_before_locking(
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="candidate.*non-standard JSON number NaN",
    ):
        tracking_database_io.commit_tracking_database(
            expected,
            b'{"talks": [], "value": NaN}\n',
        )

    assert path.read_bytes() == original
    assert not tracking_database_io.lock_path_for(path).exists()


def test_commit_rejects_symlinked_cooperative_lock(
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    lock_target = tmp_path / "outside.lock"
    lock_target.write_bytes(b"")
    tracking_database_io.lock_path_for(path).symlink_to(lock_target)

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="cooperative tracking-database lock",
    ):
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
        )

    assert path.read_bytes() == original


def test_same_bytes_inode_replacement_fails_closed(
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    raw = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(raw)
    os.replace(replacement, path)
    replacement_generation = path.stat().st_ino

    with pytest.raises(
        tracking_database_io.TrackingDatabaseConflictError,
        match="content or generation changed",
    ):
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
        )

    assert path.read_bytes() == raw
    assert path.stat().st_ino == replacement_generation


def test_symlink_substitution_before_commit_is_preserved(
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    concurrent = tmp_path / "concurrent.json"
    concurrent_raw = _write(concurrent, {"talks": [{"filename": "new.md"}]})
    path.unlink()
    path.symlink_to(concurrent)

    with pytest.raises(tracking_database_io.TrackingDatabaseIOError, match="symbolic link"):
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
        )

    assert path.is_symlink()
    assert concurrent.read_bytes() == concurrent_raw


def test_noop_is_byte_and_inode_stable(tracking_database_io, tmp_path: Path) -> None:
    path = tmp_path / "tracking-database.json"
    raw = b'{"talks":[]}\n'
    path.write_bytes(raw)
    expected = tracking_database_io.snapshot_tracking_database(path)

    result = tracking_database_io.commit_tracking_database(expected, expected.raw)

    assert result.changed is False
    assert result.installed is False
    assert result.input_sha256 == result.output_sha256 == expected.sha256
    assert path.read_bytes() == raw
    assert path.stat().st_ino == expected.generation.inode


def test_semantic_json_noop_is_byte_and_inode_stable(
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    raw = b'{"nested":{"b":2,"a":1},"ordered":[true,1,1.0]}\n'
    path.write_bytes(raw)
    expected = tracking_database_io.snapshot_tracking_database(path)

    result = tracking_database_io.write_json_object(
        expected,
        {"ordered": [True, 1, 1.0], "nested": {"a": 1, "b": 2}},
    )

    assert result.changed is False
    assert result.installed is False
    assert path.read_bytes() == raw
    assert path.stat().st_ino == expected.generation.inode


@pytest.mark.parametrize(
    ("left", "right", "equal"),
    [
        ({"a": 1, "b": [2, 3]}, {"b": [2, 3], "a": 1}, True),
        ([1, 2], [2, 1], False),
        (True, 1, False),
        (1, 1.0, False),
        ({"$missing": 1}, {"$missing": True}, False),
    ],
)
def test_json_values_equal_is_recursive_and_type_sensitive(
    tracking_database_io,
    left: object,
    right: object,
    equal: bool,
) -> None:
    assert tracking_database_io.json_values_equal(left, right) is equal


def test_backup_collision_never_overwrites_database_or_backup(
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    backup = tmp_path / ".backups" / "tracking-database.hash.bak"
    backup.parent.mkdir()
    backup.write_bytes(b"different generation\n")
    request = tracking_database_io.BackupRequest(
        path=backup,
        input_sha256=expected.sha256,
    )

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="does not match the validated input bytes",
    ):
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
            backup=request,
        )

    assert path.read_bytes() == original
    assert backup.read_bytes() == b"different generation\n"


def test_replace_interrupt_cleans_stage_but_keeps_persistent_lock(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)

    def interrupt(_source: object, _target: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(tracking_database_io.os, "replace", interrupt)
    with pytest.raises(KeyboardInterrupt):
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
        )

    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))
    assert tracking_database_io.lock_path_for(path).is_file()


def test_commit_rejects_substituted_stage_without_unlinking_it(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    attacker = tmp_path / "attacker.json"
    attacker_raw = _write(attacker, {"attacker": True})
    original_stage = tracking_database_io._stage_candidate
    substituted: list[Path] = []

    def substitute_stage(target: Path, candidate: bytes, mode: int):
        stage = original_stage(target, candidate, mode)
        os.unlink(stage.name, dir_fd=stage.directory_descriptor)
        os.symlink(
            attacker.name,
            stage.name,
            dir_fd=stage.directory_descriptor,
        )
        substituted.append(stage.path)
        return stage

    monkeypatch.setattr(tracking_database_io, "_stage_candidate", substitute_stage)
    with pytest.raises(
        tracking_database_io.TrackingDatabaseConflictError,
        match="staged tracking-database candidate.*changed before install",
    ):
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
        )

    assert path.read_bytes() == original
    assert attacker.read_bytes() == attacker_raw
    assert substituted[0].is_symlink()


def test_initialization_rejects_substituted_stage_without_unlinking_it(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    attacker = tmp_path / "attacker.json"
    attacker_raw = _write(attacker, {"attacker": True})
    original_stage = tracking_database_io._stage_candidate
    substituted: list[Path] = []

    def substitute_stage(target: Path, candidate: bytes, mode: int):
        stage = original_stage(target, candidate, mode)
        os.unlink(stage.name, dir_fd=stage.directory_descriptor)
        os.symlink(
            attacker.name,
            stage.name,
            dir_fd=stage.directory_descriptor,
        )
        substituted.append(stage.path)
        return stage

    monkeypatch.setattr(tracking_database_io, "_stage_candidate", substitute_stage)
    with pytest.raises(
        tracking_database_io.TrackingDatabaseConflictError,
        match="staged tracking-database candidate.*changed before install",
    ):
        tracking_database_io.initialize_tracking_database(path, {"talks": []})

    assert not path.exists()
    assert attacker.read_bytes() == attacker_raw
    assert substituted[0].is_symlink()


def test_directory_fsync_failure_reports_installed_generation(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})

    def fail_directory_sync(_descriptor: int) -> None:
        raise OSError("simulated directory sync failure")

    monkeypatch.setattr(tracking_database_io, "_fsync_directory", fail_directory_sync)
    result = tracking_database_io.commit_tracking_database(expected, candidate)

    assert result.installed is True
    assert result.durability_state == "installed_directory_fsync_failed"
    assert result.output_sha256 == tracking_database_io.snapshot_tracking_database(path).sha256
    assert path.read_bytes() == candidate
    assert "inspect the installed output SHA before retrying" in result.warnings[0]


@pytest.mark.parametrize("initialize", [False, True], ids=["commit", "initialize"])
def test_directory_close_failure_is_an_installed_warning(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initialize: bool,
) -> None:
    path = tmp_path / "tracking-database.json"
    payload = {"talks": [], "config": {}}
    expected = None
    if not initialize:
        _write(path, {"talks": []})
        expected = tracking_database_io.snapshot_tracking_database(path)
    original_stage = tracking_database_io._stage_candidate
    real_close = tracking_database_io.os.close
    directory_descriptors: set[int] = set()
    injected = False

    def capture_stage(target: Path, candidate: bytes, mode: int):
        stage = original_stage(target, candidate, mode)
        directory_descriptors.add(stage.directory_descriptor)
        return stage

    def fail_directory_close(descriptor: int) -> None:
        nonlocal injected
        if descriptor in directory_descriptors and not injected:
            injected = True
            real_close(descriptor)
            raise OSError("simulated directory close failure")
        real_close(descriptor)

    monkeypatch.setattr(tracking_database_io, "_stage_candidate", capture_stage)
    monkeypatch.setattr(tracking_database_io.os, "close", fail_directory_close)
    if initialize:
        result = tracking_database_io.initialize_tracking_database(path, payload)
    else:
        assert expected is not None
        result = tracking_database_io.write_json_object(expected, payload)

    assert result.installed is True
    assert tracking_database_io.decode_json_object_bytes(path.read_bytes(), path) == payload
    assert any("could not close tracking-database directory" in w for w in result.warnings)


@pytest.mark.parametrize("initialize", [False, True], ids=["commit", "initialize"])
def test_lock_cleanup_failure_is_an_installed_warning(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initialize: bool,
) -> None:
    path = tmp_path / "tracking-database.json"
    payload = {"talks": [], "config": {}}
    expected = None
    if not initialize:
        _write(path, {"talks": []})
        expected = tracking_database_io.snapshot_tracking_database(path)
    real_flock = tracking_database_io.fcntl.flock

    def fail_unlock(descriptor: int, operation: int) -> object:
        outcome = real_flock(descriptor, operation)
        if operation == fcntl.LOCK_UN:
            raise OSError("simulated unlock failure")
        return outcome

    monkeypatch.setattr(tracking_database_io.fcntl, "flock", fail_unlock)
    if initialize:
        result = tracking_database_io.initialize_tracking_database(path, payload)
    else:
        assert expected is not None
        result = tracking_database_io.write_json_object(expected, payload)

    assert result.installed is True
    assert tracking_database_io.decode_json_object_bytes(path.read_bytes(), path) == payload
    assert any("could not unlock cooperative" in w for w in result.warnings)


@pytest.mark.parametrize("initialize", [False, True], ids=["commit", "initialize"])
def test_lock_close_failure_is_an_installed_warning(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initialize: bool,
) -> None:
    path = tmp_path / "tracking-database.json"
    payload = {"talks": [], "config": {}}
    expected = None
    if not initialize:
        _write(path, {"talks": []})
        expected = tracking_database_io.snapshot_tracking_database(path)
    lock_path = tracking_database_io.lock_path_for(path)
    real_close = tracking_database_io.os.close
    injected = False

    def fail_lock_close(descriptor: int) -> None:
        nonlocal injected
        metadata = os.fstat(descriptor)
        lock_metadata = lock_path.stat() if lock_path.exists() else None
        is_lock = lock_metadata is not None and (
            metadata.st_dev,
            metadata.st_ino,
        ) == (
            lock_metadata.st_dev,
            lock_metadata.st_ino,
        )
        if is_lock and not injected:
            injected = True
            real_close(descriptor)
            raise OSError("simulated lock close failure")
        real_close(descriptor)

    monkeypatch.setattr(tracking_database_io.os, "close", fail_lock_close)
    if initialize:
        result = tracking_database_io.initialize_tracking_database(path, payload)
    else:
        assert expected is not None
        result = tracking_database_io.write_json_object(expected, payload)

    assert result.installed is True
    assert tracking_database_io.decode_json_object_bytes(path.read_bytes(), path) == payload
    assert any("could not close cooperative" in w for w in result.warnings)


def test_postinstall_verification_failure_reports_installed_unknown_state(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})
    concurrent = tracking_database_io.render_json_object({"writer": "noncooperative"})
    original_replace = tracking_database_io._replace_staged_candidate

    def replace_then_mutate(stage, target: Path) -> None:
        original_replace(stage, target)
        target.write_bytes(concurrent)

    monkeypatch.setattr(
        tracking_database_io,
        "_replace_staged_candidate",
        replace_then_mutate,
    )
    result = tracking_database_io.commit_tracking_database(expected, candidate)

    assert result.installed is True
    assert result.durability_state == "installed_verification_failed"
    assert result.output_sha256 != tracking_database_io.snapshot_tracking_database(path).sha256
    assert path.read_bytes() == concurrent
    assert any("no longer matches" in warning for warning in result.warnings)


def test_initialization_postinstall_verification_failure_reports_installed_state(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    candidate_payload = {"talks": [], "config": {}}
    concurrent = tracking_database_io.render_json_object({"writer": "noncooperative"})
    concurrent_path = tmp_path / "concurrent.json"
    original_link = tracking_database_io._link_staged_candidate

    def link_then_replace(stage, target: Path) -> None:
        original_link(stage, target)
        concurrent_path.write_bytes(concurrent)
        os.replace(concurrent_path, target)

    monkeypatch.setattr(
        tracking_database_io,
        "_link_staged_candidate",
        link_then_replace,
    )
    result = tracking_database_io.initialize_tracking_database(
        path,
        candidate_payload,
    )

    assert result.installed is True
    assert result.durability_state == "installed_verification_failed"
    assert result.output_sha256 != tracking_database_io.snapshot_tracking_database(path).sha256
    assert path.read_bytes() == concurrent
    assert any("no longer matches" in warning for warning in result.warnings)


def test_persistent_lock_excludes_another_process(
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"talks": []})
    lock_path = tracking_database_io.lock_path_for(path)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    probe = (
        "import fcntl, os, sys\n"
        "fd = os.open(sys.argv[1], os.O_RDWR)\n"
        "try:\n"
        "    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
        "except BlockingIOError:\n"
        "    print('blocked')\n"
        "else:\n"
        "    print('acquired')\n"
        "finally:\n"
        "    os.close(fd)\n"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", probe, str(lock_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    assert completed.stdout.strip() == "blocked"


def test_cross_writer_waits_then_rejects_its_stale_generation(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"talks": []})
    first_snapshot = tracking_database_io.snapshot_tracking_database(path)
    second_snapshot = tracking_database_io.snapshot_tracking_database(path)
    first_candidate = tracking_database_io.render_json_object(
        {"talks": [], "writer": "first"}
    )
    second_candidate = tracking_database_io.render_json_object(
        {"talks": [], "writer": "second"}
    )
    original_stage = tracking_database_io._stage_candidate
    real_flock = tracking_database_io.fcntl.flock
    second_attempted = threading.Event()
    second_errors: list[Exception] = []
    second_thread: threading.Thread | None = None

    def observed_flock(descriptor: int, operation: int) -> object:
        if (
            threading.current_thread().name == "second-toolkit-writer"
            and operation == fcntl.LOCK_EX
        ):
            second_attempted.set()
        return real_flock(descriptor, operation)

    def second_writer() -> None:
        try:
            tracking_database_io.commit_tracking_database(
                second_snapshot,
                second_candidate,
            )
        except Exception as exc:
            second_errors.append(exc)

    def stage_and_contend(target: Path, candidate: bytes, mode: int) -> str:
        nonlocal second_thread
        temporary = original_stage(target, candidate, mode)
        second_thread = threading.Thread(
            target=second_writer,
            name="second-toolkit-writer",
        )
        second_thread.start()
        assert second_attempted.wait(timeout=5)
        assert second_errors == []
        return temporary

    monkeypatch.setattr(tracking_database_io.fcntl, "flock", observed_flock)
    monkeypatch.setattr(tracking_database_io, "_stage_candidate", stage_and_contend)

    first_result = tracking_database_io.commit_tracking_database(
        first_snapshot,
        first_candidate,
    )
    assert second_thread is not None
    second_thread.join(timeout=5)

    assert not second_thread.is_alive()
    assert first_result.installed is True
    assert len(second_errors) == 1
    assert isinstance(
        second_errors[0],
        tracking_database_io.TrackingDatabaseConflictError,
    )
    assert path.read_bytes() == first_candidate


def test_initialization_is_exclusive_and_reports_missing_input(
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    payload = {"config": {}, "talks": []}

    result = tracking_database_io.initialize_tracking_database(path, payload)

    assert result.input_sha256 is None
    assert result.installed is True
    assert tracking_database_io.decode_json_object(
        tracking_database_io.snapshot_tracking_database(path)
    ) == payload
    with pytest.raises(
        tracking_database_io.TrackingDatabaseConflictError,
        match="already exists",
    ):
        tracking_database_io.initialize_tracking_database(path, payload)

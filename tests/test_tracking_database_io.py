"""Adversarial contract tests for the shared tracking-database transaction."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest


def _write(path: Path, value: object) -> bytes:
    raw = json.dumps(value, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return raw


def _metadata_view(
    metadata: os.stat_result,
    *,
    inode: int | None = None,
    modified_ns: int | None = None,
    changed_ns: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        st_mode=metadata.st_mode,
        st_nlink=metadata.st_nlink,
        st_dev=metadata.st_dev,
        st_ino=metadata.st_ino if inode is None else inode,
        st_size=metadata.st_size,
        st_mtime_ns=(metadata.st_mtime_ns if modified_ns is None else modified_ns),
        st_ctime_ns=metadata.st_ctime_ns if changed_ns is None else changed_ns,
    )


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (
            b'{"talks": [], "talks": [{"filename": "lost.md"}]}\n',
            "duplicate object key 'talks'",
        ),
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


@pytest.mark.parametrize(
    "token",
    [
        "0.12345678901234567890123456789",
        "1e400",
        pytest.param(
            "1e" + "9" * 30,
            id="extreme-exponent",
        ),
        pytest.param(
            "7" * 5000,
            id="huge-integer",
        ),
    ],
)
def test_strict_decoder_rejects_numbers_that_cannot_round_trip(
    tracking_database_io,
    tmp_path: Path,
    token: str,
) -> None:
    path = tmp_path / "tracking-database.json"
    raw = f'{{"talks":[],"value":{token}}}\n'.encode()
    path.write_bytes(raw)

    snapshot = tracking_database_io.snapshot_tracking_database(path)
    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="cannot round-trip losslessly",
    ) as stopped:
        tracking_database_io.decode_json_object(snapshot)

    assert len(str(stopped.value)) < 1000
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        pytest.param(
            b'{"config":{"value":'
            + b"[" * 500
            + b"0"
            + b"]" * 500
            + b'},"talks":[]}\n',
            "maximum supported JSON nesting depth 200",
            id="decoded-depth-limit",
        ),
        pytest.param(
            b'{"config":{"value":'
            + b"[" * 10_000
            + b"0"
            + b"]" * 10_000
            + b'},"talks":[]}\n',
            "maximum supported JSON nesting depth 200",
            id="decoder-recursion-limit",
        ),
        pytest.param(
            b'{"config":{"value":"\\ud800"},"talks":[]}\n',
            "unpaired UTF-16 surrogate",
            id="unpaired-surrogate",
        ),
    ],
)
def test_strict_decoder_rejects_unsafe_tree_before_consumers(
    tracking_database_io,
    tmp_path: Path,
    raw: bytes,
    message: str,
) -> None:
    path = tmp_path / "tracking-database.json"
    path.write_bytes(raw)

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match=message,
    ) as stopped:
        tracking_database_io.decode_json_object(
            tracking_database_io.snapshot_tracking_database(path)
        )

    assert len(str(stopped.value)) < 1000
    assert path.read_bytes() == raw


def test_strict_decoder_accepts_valid_escaped_surrogate_pair(
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    raw = b'{"config":{"value":"\\ud83d\\ude00"},"talks":[]}\n'
    path.write_bytes(raw)

    decoded = tracking_database_io.decode_json_object(
        tracking_database_io.snapshot_tracking_database(path)
    )

    assert decoded["config"]["value"] == "😀"
    assert path.read_bytes() == raw


@pytest.mark.parametrize("token", ["0.1", "0.10", "1e0", "-0.0"])
def test_strict_decoder_accepts_lossless_numeric_lexical_variants(
    tracking_database_io,
    tmp_path: Path,
    token: str,
) -> None:
    path = tmp_path / "tracking-database.json"
    raw = f'{{"talks":[],"value":{token}}}\n'.encode()
    path.write_bytes(raw)

    decoded = tracking_database_io.decode_json_object(
        tracking_database_io.snapshot_tracking_database(path)
    )

    assert decoded["value"] == float(token)
    assert type(decoded["value"]) is float


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


def test_renderer_rejects_unsafe_depth_with_bounded_domain_error(
    tracking_database_io,
) -> None:
    nested: object = 0
    for _ in range(tracking_database_io.MAX_JSON_NESTING_DEPTH + 1):
        nested = [nested]

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="maximum supported JSON nesting depth 200",
    ) as stopped:
        tracking_database_io.render_json_object({"value": nested})

    assert len(str(stopped.value)) < 1000


def test_renderer_rejects_unpaired_surrogate_with_domain_error(
    tracking_database_io,
) -> None:
    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="unpaired UTF-16 surrogate",
    ):
        tracking_database_io.render_json_object({"value": "\ud800"})


def test_renderer_normalizes_recursion_error_backstop(
    tracking_database_io,
    monkeypatch,
) -> None:
    def fail_render(*_args, **_kwargs):
        raise RecursionError("synthetic renderer recursion")

    monkeypatch.setattr(tracking_database_io.json, "dumps", fail_render)

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="maximum supported JSON nesting depth 200",
    ):
        tracking_database_io.render_json_object({"value": "safe"})


def test_renderer_normalizes_unicode_encode_error_backstop(
    tracking_database_io,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        tracking_database_io.json,
        "dumps",
        lambda *_args, **_kwargs: "\ud800",
    )

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError,
        match="unpaired UTF-16 surrogate",
    ):
        tracking_database_io.render_json_object({"value": "safe"})


def test_commit_refuses_an_invalid_candidate_before_locking(
    cooperative_lock,
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
    assert not cooperative_lock.lock_path_for(path).exists()


def test_commit_rejects_symlinked_cooperative_lock(
    cooperative_lock,
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    lock_target = tmp_path / "outside.lock"
    lock_target.write_bytes(b"")
    cooperative_lock.lock_path_for(path).symlink_to(lock_target)

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

    with pytest.raises(
        tracking_database_io.TrackingDatabaseIOError, match="symbolic link"
    ):
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
    cooperative_lock,
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
    assert cooperative_lock.lock_path_for(path).is_file()


def test_lock_acquisition_interrupt_closes_descriptor(
    cooperative_lock,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    lock_path = cooperative_lock.lock_path_for(path)
    real_flock = cooperative_lock.fcntl.flock

    def interrupt_after_acquire(descriptor: int, operation: int) -> object:
        result = real_flock(descriptor, operation)
        if operation == fcntl.LOCK_EX:
            raise KeyboardInterrupt
        return result

    monkeypatch.setattr(cooperative_lock.fcntl, "flock", interrupt_after_acquire)
    with pytest.raises(KeyboardInterrupt):
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
        )

    assert path.read_bytes() == original
    probe = os.open(lock_path, os.O_RDWR)
    try:
        real_flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        real_flock(probe, fcntl.LOCK_UN)
    finally:
        os.close(probe)


def test_staging_interrupt_cleans_candidate_and_preserves_database(
    cooperative_lock,
    retained_stage,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    real_write = retained_stage._write_descriptor

    def interrupt_after_write(descriptor: int, raw: bytes) -> None:
        real_write(descriptor, raw)
        raise KeyboardInterrupt

    monkeypatch.setattr(retained_stage, "_write_descriptor", interrupt_after_write)
    with pytest.raises(KeyboardInterrupt):
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
        )

    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))
    assert cooperative_lock.lock_path_for(path).is_file()


def test_staged_timestamp_churn_retries_same_candidate_then_installs_once(
    retained_stage,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})
    original_observe = retained_stage._observe
    original_verify = tracking_database_io._verify_staged_candidate
    original_replace = tracking_database_io._replace_staged_candidate
    real_fstat = retained_stage.os.fstat
    real_stat = retained_stage.os.stat
    staged_descriptor: int | None = None
    staged_name: str | None = None
    staged_directory_descriptor: int | None = None
    descriptor_observations = 0
    name_observations = 0
    verify_windows = 0
    verification_calls = 0
    replacements = 0

    def churning_fstat(descriptor: int):
        nonlocal descriptor_observations
        metadata = real_fstat(descriptor)
        if descriptor != staged_descriptor:
            return metadata
        descriptor_observations += 1
        offset = (1, 2, 3, 3)[min(descriptor_observations - 1, 3)]
        return _metadata_view(
            metadata,
            modified_ns=metadata.st_mtime_ns + offset,
            changed_ns=metadata.st_ctime_ns + offset,
        )

    def churning_stat(
        name: object,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ):
        nonlocal name_observations
        metadata = real_stat(
            name,
            dir_fd=dir_fd,
            follow_symlinks=follow_symlinks,
        )
        if name != staged_name or dir_fd != staged_directory_descriptor:
            return metadata
        name_observations += 1
        offset = (10, 11, 12, 12)[min(name_observations - 1, 3)]
        return _metadata_view(
            metadata,
            modified_ns=metadata.st_mtime_ns + offset,
            changed_ns=metadata.st_ctime_ns + offset,
        )

    def counted_observe(stage):
        nonlocal verify_windows
        verify_windows += 1
        return original_observe(stage)

    def verify_with_initial_churn(stage, raw: bytes) -> None:
        nonlocal staged_descriptor, staged_name, staged_directory_descriptor
        nonlocal verification_calls
        verification_calls += 1
        if staged_descriptor is None:
            metadata = real_fstat(stage.descriptor)
            os.utime(
                stage.path,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
                follow_symlinks=False,
            )
            staged_descriptor = stage.descriptor
            staged_name = stage.name
            staged_directory_descriptor = stage.directory_descriptor
            monkeypatch.setattr(retained_stage.os, "fstat", churning_fstat)
            monkeypatch.setattr(retained_stage.os, "stat", churning_stat)
        original_verify(stage, raw)

    def counted_replace(stage, target: Path) -> None:
        nonlocal replacements
        replacements += 1
        original_replace(stage, target)

    monkeypatch.setattr(retained_stage, "_observe", counted_observe)
    monkeypatch.setattr(
        tracking_database_io, "_verify_staged_candidate", verify_with_initial_churn
    )
    monkeypatch.setattr(
        tracking_database_io, "_replace_staged_candidate", counted_replace
    )

    result = tracking_database_io.commit_tracking_database(expected, candidate)

    assert result.installed is True
    assert path.read_bytes() == candidate
    assert verify_windows == 3
    assert verification_calls == 2
    assert replacements == 1
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))


def test_never_stable_staged_timestamps_fail_with_bounded_typed_diagnostic(
    retained_stage,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})
    original_observe = retained_stage._observe
    original_verify = tracking_database_io._verify_staged_candidate
    real_fstat = retained_stage.os.fstat
    real_stat = retained_stage.os.stat
    staged_descriptor: int | None = None
    staged_name: str | None = None
    staged_directory_descriptor: int | None = None
    metadata_sequence = 0
    verify_windows = 0
    backup = tmp_path / "backups" / "tracking-database.bak"
    backup_request = tracking_database_io.BackupRequest(
        path=backup,
        input_sha256=expected.sha256,
    )

    def next_view(metadata: os.stat_result) -> SimpleNamespace:
        nonlocal metadata_sequence
        metadata_sequence += 1
        return _metadata_view(
            metadata,
            modified_ns=metadata.st_mtime_ns + metadata_sequence,
            changed_ns=metadata.st_ctime_ns + metadata_sequence,
        )

    def churning_fstat(descriptor: int):
        metadata = real_fstat(descriptor)
        return next_view(metadata) if descriptor == staged_descriptor else metadata

    def churning_stat(
        name: object,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ):
        metadata = real_stat(
            name,
            dir_fd=dir_fd,
            follow_symlinks=follow_symlinks,
        )
        if name == staged_name and dir_fd == staged_directory_descriptor:
            return next_view(metadata)
        return metadata

    def counted_observe(stage):
        nonlocal verify_windows
        verify_windows += 1
        return original_observe(stage)

    def verify_with_never_stable_metadata(stage, raw: bytes) -> None:
        nonlocal staged_descriptor, staged_name, staged_directory_descriptor
        staged_descriptor = stage.descriptor
        staged_name = stage.name
        staged_directory_descriptor = stage.directory_descriptor
        monkeypatch.setattr(retained_stage.os, "fstat", churning_fstat)
        monkeypatch.setattr(retained_stage.os, "stat", churning_stat)
        original_verify(stage, raw)

    monkeypatch.setattr(retained_stage, "_observe", counted_observe)
    monkeypatch.setattr(
        tracking_database_io,
        "_verify_staged_candidate",
        verify_with_never_stable_metadata,
    )

    with pytest.raises(
        tracking_database_io.StagedCandidateConflictError,
        match="invariant=timestamp_stability.*bounded observations",
    ) as stopped:
        tracking_database_io.commit_tracking_database(
            expected,
            candidate,
            backup=backup_request,
        )

    assert stopped.value.invariant == "timestamp_stability"
    assert verify_windows == tracking_database_io.STAGED_METADATA_STABILIZATION_ATTEMPTS
    assert path.read_bytes() == original
    assert not backup.exists()
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))


def test_staged_name_identity_change_fails_typed_and_cleans_owned_candidate(
    retained_stage,
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})
    original_stage = tracking_database_io._stage_candidate
    real_stat = retained_stage.os.stat
    staged_name: str | None = None
    staged_directory_descriptor: int | None = None
    substituted = False

    def changed_stat(
        name: object,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ):
        nonlocal substituted
        metadata = real_stat(
            name,
            dir_fd=dir_fd,
            follow_symlinks=follow_symlinks,
        )
        if (
            not substituted
            and name == staged_name
            and dir_fd == staged_directory_descriptor
        ):
            substituted = True
            return _metadata_view(metadata, inode=metadata.st_ino + 1)
        return metadata

    def stage_then_change_identity(target: Path, raw: bytes, mode: int):
        nonlocal staged_name, staged_directory_descriptor
        stage = original_stage(target, raw, mode)
        staged_name = stage.name
        staged_directory_descriptor = stage.directory_descriptor
        monkeypatch.setattr(tracking_database_io.os, "stat", changed_stat)
        return stage

    monkeypatch.setattr(
        tracking_database_io,
        "_stage_candidate",
        stage_then_change_identity,
    )

    with pytest.raises(
        tracking_database_io.StagedCandidateConflictError,
        match="invariant=descriptor_name_identity",
    ) as stopped:
        tracking_database_io.commit_tracking_database(expected, candidate)

    assert stopped.value.invariant == "descriptor_name_identity"
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))


def test_regular_staged_name_substitution_fails_typed_and_is_left_untouched(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})
    original_stage = tracking_database_io._stage_candidate
    replacement_raw = b"foreign regular staged name\n"
    substituted: list[Path] = []
    backup = tmp_path / "backups" / "tracking-database.bak"
    backup_request = tracking_database_io.BackupRequest(
        path=backup,
        input_sha256=expected.sha256,
    )

    def substitute_regular_name(target: Path, raw: bytes, mode: int):
        stage = original_stage(target, raw, mode)
        os.unlink(stage.name, dir_fd=stage.directory_descriptor)
        replacement_descriptor = os.open(
            stage.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=stage.directory_descriptor,
        )
        with os.fdopen(replacement_descriptor, "wb") as replacement:
            replacement.write(replacement_raw)
        substituted.append(stage.path)
        return stage

    monkeypatch.setattr(
        tracking_database_io,
        "_stage_candidate",
        substitute_regular_name,
    )

    with pytest.raises(
        tracking_database_io.StagedCandidateConflictError,
        match="invariant=descriptor_name_identity",
    ) as stopped:
        tracking_database_io.commit_tracking_database(
            expected,
            candidate,
            backup=backup_request,
        )

    assert stopped.value.invariant == "descriptor_name_identity"
    assert path.read_bytes() == original
    assert not backup.exists()
    assert substituted[0].is_file()
    assert substituted[0].read_bytes() == replacement_raw
    assert list(tmp_path.glob(".*.tracking-db.tmp")) == substituted


def test_staged_hardlink_change_fails_typed_and_removes_owned_name(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})
    original_stage = tracking_database_io._stage_candidate
    extra_link = tmp_path / "unexpected-candidate-link"

    def stage_then_link(target: Path, raw: bytes, mode: int):
        stage = original_stage(target, raw, mode)
        os.link(stage.path, extra_link)
        return stage

    monkeypatch.setattr(tracking_database_io, "_stage_candidate", stage_then_link)

    with pytest.raises(
        tracking_database_io.StagedCandidateConflictError,
        match="invariant=link_count",
    ) as stopped:
        tracking_database_io.commit_tracking_database(expected, candidate)

    assert stopped.value.invariant == "link_count"
    assert path.read_bytes() == original
    assert extra_link.read_bytes() == candidate
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))


def test_staged_size_change_fails_typed_and_cleans_candidate(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})
    original_stage = tracking_database_io._stage_candidate

    def stage_then_resize(target: Path, raw: bytes, mode: int):
        stage = original_stage(target, raw, mode)
        os.ftruncate(stage.descriptor, stage.size + 1)
        return stage

    monkeypatch.setattr(tracking_database_io, "_stage_candidate", stage_then_resize)

    with pytest.raises(
        tracking_database_io.StagedCandidateConflictError,
        match="invariant=size",
    ) as stopped:
        tracking_database_io.commit_tracking_database(expected, candidate)

    assert stopped.value.invariant == "size"
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))


def test_staged_same_size_byte_change_fails_typed_and_cleans_candidate(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})
    original_stage = tracking_database_io._stage_candidate

    def stage_then_change_bytes(target: Path, raw: bytes, mode: int):
        stage = original_stage(target, raw, mode)
        os.pwrite(stage.descriptor, b"X", 0)
        return stage

    monkeypatch.setattr(
        tracking_database_io,
        "_stage_candidate",
        stage_then_change_bytes,
    )

    with pytest.raises(
        tracking_database_io.StagedCandidateConflictError,
        match="invariant=exact_bytes",
    ) as stopped:
        tracking_database_io.commit_tracking_database(expected, candidate)

    assert stopped.value.invariant == "exact_bytes"
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))


def test_staged_digest_binding_change_fails_typed_and_cleans_candidate(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})
    original_stage = tracking_database_io._stage_candidate

    def stage_then_change_digest(target: Path, raw: bytes, mode: int):
        stage = original_stage(target, raw, mode)
        stage.sha256 = "0" * 64
        return stage

    monkeypatch.setattr(
        tracking_database_io,
        "_stage_candidate",
        stage_then_change_digest,
    )

    with pytest.raises(
        tracking_database_io.StagedCandidateConflictError,
        match="invariant=sha256",
    ) as stopped:
        tracking_database_io.commit_tracking_database(expected, candidate)

    assert stopped.value.invariant == "sha256"
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))


def test_target_timestamp_change_remains_an_exact_cas_conflict(
    tracking_database_io,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tracking-database.json"
    original = _write(path, {"talks": []})
    expected = tracking_database_io.snapshot_tracking_database(path)
    metadata = path.stat()
    os.utime(
        path,
        ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
        follow_symlinks=False,
    )
    backup = tmp_path / "backups" / "tracking-database.bak"
    backup_request = tracking_database_io.BackupRequest(
        path=backup,
        input_sha256=expected.sha256,
    )

    def unexpected_stage(*_args, **_kwargs):
        pytest.fail("target generation conflict must fail before staging")

    monkeypatch.setattr(tracking_database_io, "_stage_candidate", unexpected_stage)

    with pytest.raises(
        tracking_database_io.TrackingDatabaseConflictError,
        match="content or generation changed after validation",
    ):
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
            backup=backup_request,
        )

    assert path.read_bytes() == original
    assert path.stat().st_ino == expected.generation.inode
    assert not backup.exists()
    assert not list(tmp_path.glob(".*.tracking-db.tmp"))


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
    backup = tmp_path / "backups" / "tracking-database.bak"
    request = tracking_database_io.BackupRequest(
        path=backup,
        input_sha256=expected.sha256,
    )
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
        tracking_database_io.StagedCandidateConflictError,
        match="staged tracking-database candidate.*changed before install",
    ) as stopped:
        tracking_database_io.commit_tracking_database(
            expected,
            tracking_database_io.render_json_object({"talks": [], "config": {}}),
            backup=request,
        )

    assert stopped.value.invariant == "regular_file"
    assert path.read_bytes() == original
    assert attacker.read_bytes() == attacker_raw
    assert substituted[0].is_symlink()
    assert not backup.exists()


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
        tracking_database_io.StagedCandidateConflictError,
        match="staged tracking-database candidate.*changed before install",
    ) as stopped:
        tracking_database_io.initialize_tracking_database(path, {"talks": []})

    assert stopped.value.invariant == "regular_file"
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
    assert (
        result.output_sha256
        == tracking_database_io.snapshot_tracking_database(path).sha256
    )
    assert path.read_bytes() == candidate
    assert "inspect the installed output SHA before retrying" in result.warnings[0]


@pytest.mark.parametrize("initialize", [False, True], ids=["commit", "initialize"])
def test_directory_close_failure_is_an_installed_warning(
    retained_stage,
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
    monkeypatch.setattr(retained_stage.os, "close", fail_directory_close)
    if initialize:
        result = tracking_database_io.initialize_tracking_database(path, payload)
    else:
        assert expected is not None
        result = tracking_database_io.write_json_object(expected, payload)

    assert result.installed is True
    assert (
        tracking_database_io.decode_json_object_bytes(path.read_bytes(), path)
        == payload
    )
    assert any(
        "could not close tracking-database directory" in w for w in result.warnings
    )


@pytest.mark.parametrize("initialize", [False, True], ids=["commit", "initialize"])
def test_lock_cleanup_failure_is_an_installed_warning(
    cooperative_lock,
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
    real_flock = cooperative_lock.fcntl.flock

    def fail_unlock(descriptor: int, operation: int) -> object:
        outcome = real_flock(descriptor, operation)
        if operation == fcntl.LOCK_UN:
            raise OSError("simulated unlock failure")
        return outcome

    monkeypatch.setattr(cooperative_lock.fcntl, "flock", fail_unlock)
    if initialize:
        result = tracking_database_io.initialize_tracking_database(path, payload)
    else:
        assert expected is not None
        result = tracking_database_io.write_json_object(expected, payload)

    assert result.installed is True
    assert (
        tracking_database_io.decode_json_object_bytes(path.read_bytes(), path)
        == payload
    )
    assert any("could not unlock cooperative" in w for w in result.warnings)


@pytest.mark.parametrize("initialize", [False, True], ids=["commit", "initialize"])
def test_lock_close_failure_is_an_installed_warning(
    cooperative_lock,
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
    lock_path = cooperative_lock.lock_path_for(path)
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
    assert (
        tracking_database_io.decode_json_object_bytes(path.read_bytes(), path)
        == payload
    )
    assert any("could not close cooperative" in w for w in result.warnings)


def test_postinstall_verification_failure_reports_installed_unknown_state(
    retained_stage,
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
    assert (
        result.output_sha256
        != tracking_database_io.snapshot_tracking_database(path).sha256
    )
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
    assert (
        result.output_sha256
        != tracking_database_io.snapshot_tracking_database(path).sha256
    )
    assert path.read_bytes() == concurrent
    assert any("no longer matches" in warning for warning in result.warnings)


def test_persistent_lock_excludes_another_process(
    cooperative_lock,
    tracking_database_io,
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracking-database.json"
    _write(path, {"talks": []})
    lock_path = cooperative_lock.lock_path_for(path)
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
    cooperative_lock,
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
    real_flock = cooperative_lock.fcntl.flock
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
        except tracking_database_io.TrackingDatabaseConflictError as exc:
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

    monkeypatch.setattr(cooperative_lock.fcntl, "flock", observed_flock)
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
    assert (
        tracking_database_io.decode_json_object(
            tracking_database_io.snapshot_tracking_database(path)
        )
        == payload
    )
    with pytest.raises(
        tracking_database_io.TrackingDatabaseConflictError,
        match="already exists",
    ):
        tracking_database_io.initialize_tracking_database(path, payload)

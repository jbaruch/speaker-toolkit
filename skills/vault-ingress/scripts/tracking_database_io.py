"""Safe snapshots and cooperative write transactions for the tracking database.

Every toolkit writer must capture a :class:`TrackingDatabaseSnapshot` before
validating a mutation and commit against that same snapshot.  The commit path
uses one persistent sibling lock, then rechecks the exact bytes and file
generation before and after staging.  The lock coordinates toolkit writers;
the second no-follow generation check remains defense against a non-cooperative
filesystem edit that lands before replacement.

The lock file is never removed.  Removing or replacing it would allow two
processes to lock different inodes and is outside the cooperative contract.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, DecimalException
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Iterator, NoReturn


READ_CHUNK_SIZE = 1024 * 1024
MAX_JSON_NESTING_DEPTH = 200


class TrackingDatabaseIOError(ValueError):
    """The tracking database could not be read or installed safely."""


class TrackingDatabaseConflictError(TrackingDatabaseIOError):
    """The expected database generation is no longer current."""


@dataclass(frozen=True)
class FileGeneration:
    """Stable identity fields for one observed regular-file generation."""

    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def from_stat(cls, metadata: os.stat_result) -> "FileGeneration":
        return cls(
            device=metadata.st_dev,
            inode=metadata.st_ino,
            size=metadata.st_size,
            modified_ns=metadata.st_mtime_ns,
            changed_ns=metadata.st_ctime_ns,
        )


@dataclass(frozen=True)
class TrackingDatabaseSnapshot:
    """Exact bytes, digest, mode, and generation captured before validation."""

    path: Path
    raw: bytes
    sha256: str
    generation: FileGeneration
    mode: int


@dataclass(frozen=True)
class BackupRequest:
    """Exact-input backup required before installing a candidate generation."""

    path: Path
    input_sha256: str


@dataclass(frozen=True)
class TrackingDatabaseWriteResult:
    """Unambiguous outcome of one write transaction."""

    input_sha256: str | None
    output_sha256: str
    changed: bool
    installed: bool
    durability_state: str
    warnings: tuple[str, ...]
    backup: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "changed": self.changed,
            "database_written": self.installed,
            "durability_state": self.durability_state,
            "warnings": list(self.warnings),
            "backup": self.backup,
        }


@dataclass
class _DatabaseLock:
    """One acquired lock plus cleanup warnings collected after the body."""

    descriptor: int
    path: Path
    warnings: list[str]


@dataclass
class StagedCandidate:
    """Open, directory-anchored staged bytes retained through installation."""

    path: Path
    name: str
    descriptor: int
    directory_descriptor: int
    generation: FileGeneration
    sha256: str
    size: int


def unchanged_write_result(
    snapshot: TrackingDatabaseSnapshot,
) -> TrackingDatabaseWriteResult:
    """Describe a validated no-op without rewriting its original bytes."""
    return TrackingDatabaseWriteResult(
        input_sha256=snapshot.sha256,
        output_sha256=snapshot.sha256,
        changed=False,
        installed=False,
        durability_state="unchanged",
        warnings=(),
        backup=None,
    )


def _absolute_path(path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(Path(path).expanduser()))


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_values_equal(left: object, right: object) -> bool:
    """Compare decoded JSON values without Python's bool/number coercions."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        if not isinstance(right, dict) or set(left) != set(right):
            return False
        return all(json_values_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        if not isinstance(right, list) or len(left) != len(right):
            return False
        return all(
            json_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return left == right


def lock_path_for(path: str | os.PathLike[str]) -> Path:
    """Return the persistent cooperative lock shared by every toolkit writer."""
    database_path = _absolute_path(path)
    return database_path.parent / f".{database_path.name}.lock"


def _path_metadata(path: Path, *, subject: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise TrackingDatabaseIOError(
            f"{subject} is missing at {path}; pass its canonical file path "
            "(a regular file)"
        ) from exc
    except OSError as exc:
        raise TrackingDatabaseIOError(f"cannot inspect {subject} {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise TrackingDatabaseIOError(
            f"{subject} {path} is a symbolic link; pass its canonical regular-file path"
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise TrackingDatabaseIOError(
            f"{subject} {path} is not a regular file; repair it before retrying"
        )
    return metadata


def _read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, READ_CHUNK_SIZE)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def snapshot_tracking_database(
    path: str | os.PathLike[str],
) -> TrackingDatabaseSnapshot:
    """Read one stable regular-file generation without following the final link."""
    database_path = _absolute_path(path)
    path_before = _path_metadata(database_path, subject="tracking database")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(database_path, flags)
    except OSError as exc:
        raise TrackingDatabaseIOError(
            f"cannot open tracking database {database_path} without following "
            f"symlinks: {exc}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise TrackingDatabaseIOError(
                f"tracking database {database_path} changed to a non-regular file; retry"
            )
        if FileGeneration.from_stat(opened) != FileGeneration.from_stat(path_before):
            raise TrackingDatabaseConflictError(
                "tracking database changed while it was opened; rerun the operation"
            )
        raw = _read_descriptor(descriptor)
        read_complete = os.fstat(descriptor)
    except OSError as exc:
        raise TrackingDatabaseIOError(
            f"cannot read tracking database {database_path}: {exc}"
        ) from exc
    finally:
        os.close(descriptor)
    if FileGeneration.from_stat(read_complete) != FileGeneration.from_stat(opened):
        raise TrackingDatabaseConflictError(
            "tracking database changed while it was read; rerun the operation"
        )
    path_after = _path_metadata(database_path, subject="tracking database")
    generation = FileGeneration.from_stat(read_complete)
    if FileGeneration.from_stat(path_after) != generation:
        raise TrackingDatabaseConflictError(
            "tracking database path changed while it was read; rerun the operation"
        )
    return TrackingDatabaseSnapshot(
        path=database_path,
        raw=raw,
        sha256=_sha256(raw),
        generation=generation,
        mode=stat.S_IMODE(read_complete.st_mode),
    )


def _validate_decoded_json_tree(payload: object, *, subject: str) -> None:
    """Reject unsafe depth and non-scalar Unicode without recursive walking."""
    pending: list[tuple[object, int]] = [(payload, 0)]
    deepest_container_visits: dict[int, int] = {}
    while pending:
        value, depth = pending.pop()
        if isinstance(value, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
                raise TrackingDatabaseIOError(
                    f"{subject} contains an unpaired UTF-16 surrogate in a "
                    "JSON string"
                )
            continue
        if isinstance(value, dict):
            if depth > MAX_JSON_NESTING_DEPTH:
                raise TrackingDatabaseIOError(
                    f"{subject} exceeds maximum supported JSON nesting depth "
                    f"{MAX_JSON_NESTING_DEPTH}"
                )
            previous_depth = deepest_container_visits.get(id(value))
            if previous_depth is not None and previous_depth >= depth:
                continue
            deepest_container_visits[id(value)] = depth
            for key, child in value.items():
                pending.append((key, depth + 1))
                pending.append((child, depth + 1))
            continue
        if isinstance(value, list):
            if depth > MAX_JSON_NESTING_DEPTH:
                raise TrackingDatabaseIOError(
                    f"{subject} exceeds maximum supported JSON nesting depth "
                    f"{MAX_JSON_NESTING_DEPTH}"
                )
            previous_depth = deepest_container_visits.get(id(value))
            if previous_depth is not None and previous_depth >= depth:
                continue
            deepest_container_visits[id(value)] = depth
            pending.extend((child, depth + 1) for child in value)


def decode_json_object_bytes(
    raw: bytes,
    path: str | os.PathLike[str],
    *,
    label: str = "tracking database",
) -> dict[str, Any]:
    """Decode one bounded, Unicode-scalar, strict UTF-8 JSON object."""
    artifact_path = _absolute_path(path)

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise TrackingDatabaseIOError(
                    f"{label} {artifact_path} contains duplicate object key {key!r}"
                )
            result[key] = value
        return result

    def reject_non_finite(value: str) -> NoReturn:
        raise TrackingDatabaseIOError(
            f"{label} {artifact_path} contains non-standard JSON number {value}"
        )

    def non_roundtrippable_number(value: str) -> TrackingDatabaseIOError:
        description = (
            repr(value)
            if len(value) <= 80
            else f"with {len(value)} characters beginning {value[:32]!r}"
        )
        return TrackingDatabaseIOError(
            f"{label} {artifact_path} contains JSON number {description} that "
            "cannot round-trip losslessly through this toolkit; replace it "
            "with a string or use a supported finite number"
        )

    def parse_lossless_int(value: str) -> int:
        try:
            return int(value)
        except (ValueError, OverflowError) as exc:
            raise non_roundtrippable_number(value) from exc

    def parse_lossless_float(value: str) -> float:
        """Reject numbers that cannot round-trip through the toolkit decoder."""
        try:
            exact = Decimal(value)
            decoded = float(value)
        except (DecimalException, ValueError, OverflowError) as exc:
            raise non_roundtrippable_number(value) from exc
        if not math.isfinite(decoded) or Decimal(repr(decoded)) != exact:
            raise non_roundtrippable_number(value)
        return decoded

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
            parse_float=parse_lossless_float,
            parse_int=parse_lossless_int,
        )
    except TrackingDatabaseIOError:
        raise
    except UnicodeDecodeError as exc:
        raise TrackingDatabaseIOError(
            f"{label} {artifact_path} is not valid UTF-8: {exc}"
        ) from exc
    except RecursionError as exc:
        raise TrackingDatabaseIOError(
            f"{label} {artifact_path} exceeds maximum supported JSON nesting "
            f"depth {MAX_JSON_NESTING_DEPTH}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise TrackingDatabaseIOError(
            f"{label} {artifact_path} is not valid JSON at line {exc.lineno}, "
            f"column {exc.colno}"
        ) from exc
    _validate_decoded_json_tree(
        payload,
        subject=f"{label} {artifact_path}",
    )
    if not isinstance(payload, dict):
        raise TrackingDatabaseIOError(
            f"{label} {artifact_path} root must be a JSON object"
        )
    return payload


def decode_json_object(
    snapshot: TrackingDatabaseSnapshot,
    *,
    label: str = "tracking database",
) -> dict[str, Any]:
    """Decode a captured tracking-database snapshot through the strict contract."""
    return decode_json_object_bytes(snapshot.raw, snapshot.path, label=label)


def render_json_object(payload: dict[str, Any]) -> bytes:
    """Render the canonical human-readable tracking-database JSON form."""
    _validate_decoded_json_tree(
        payload,
        subject="tracking-database candidate",
    )
    try:
        rendered = json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    except RecursionError as exc:
        raise TrackingDatabaseIOError(
            "tracking-database candidate exceeds maximum supported JSON nesting "
            f"depth {MAX_JSON_NESTING_DEPTH}"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise TrackingDatabaseIOError(
            f"tracking-database candidate is not strict JSON: {exc}"
        ) from exc
    try:
        return rendered.encode("utf-8") + b"\n"
    except UnicodeEncodeError as exc:
        raise TrackingDatabaseIOError(
            "tracking-database candidate contains an unpaired UTF-16 surrogate "
            "and is not valid Unicode scalar text"
        ) from exc


def _lock_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _append_close_warning(
    descriptor: int,
    *,
    label: str,
    warnings: list[str],
) -> None:
    """Close a post-operation descriptor without masking the operation outcome."""
    try:
        os.close(descriptor)
    except OSError as exc:
        warnings.append(f"could not close {label}: {exc}")


@contextmanager
def _exclusive_database_lock(path: Path) -> Iterator[_DatabaseLock]:
    lock_path = lock_path_for(path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise TrackingDatabaseIOError(
            f"cannot open cooperative tracking-database lock {lock_path}: {exc}"
        ) from exc
    acquired = False
    initialized = False
    try:
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise TrackingDatabaseIOError(
                    f"cooperative tracking-database lock {lock_path} must be one regular file"
                )
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            acquired = True
            try:
                visible = lock_path.lstat()
            except OSError as exc:
                raise TrackingDatabaseIOError(
                    f"cannot verify cooperative tracking-database lock {lock_path}: {exc}"
                ) from exc
            locked = os.fstat(descriptor)
            if (
                stat.S_ISLNK(visible.st_mode)
                or not stat.S_ISREG(visible.st_mode)
                or _lock_identity(visible) != _lock_identity(locked)
                or locked.st_nlink != 1
            ):
                raise TrackingDatabaseIOError(
                    f"cooperative tracking-database lock {lock_path} changed while locking; "
                    "restore the persistent regular lock file and retry"
                )
        except OSError as exc:
            raise TrackingDatabaseIOError(
                f"cannot acquire tracking-database lock through {lock_path}: {exc}"
            ) from exc
        initialized = True
    finally:
        if not initialized:
            try:
                os.close(descriptor)
            except OSError:
                pass

    lock = _DatabaseLock(descriptor=descriptor, path=lock_path, warnings=[])
    try:
        yield lock
    finally:
        if acquired:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError as exc:
                lock.warnings.append(
                    f"could not unlock cooperative tracking-database lock "
                    f"{lock_path}: {exc}"
                )
        _append_close_warning(
            descriptor,
            label=f"cooperative tracking-database lock {lock_path}",
            warnings=lock.warnings,
        )


def _require_expected_generation(
    expected: TrackingDatabaseSnapshot,
) -> TrackingDatabaseSnapshot:
    current = snapshot_tracking_database(expected.path)
    if current.raw != expected.raw or current.generation != expected.generation:
        raise TrackingDatabaseConflictError(
            "tracking database content or generation changed after validation; "
            "rerun the operation against the current database"
        )
    return current


def _require_missing_database(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise TrackingDatabaseIOError(
            f"cannot inspect tracking-database initialization target {path}: {exc}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise TrackingDatabaseIOError(
            f"tracking-database initialization target {path} is a symbolic link; "
            "remove it or pass the canonical missing path"
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise TrackingDatabaseIOError(
            f"tracking-database initialization target {path} is not a regular file"
        )
    raise TrackingDatabaseConflictError(
        f"tracking database already exists at {path}; load and mutate that generation"
    )


def _open_directory(path: Path, *, label: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise TrackingDatabaseIOError(f"cannot open {label} {path}: {exc}") from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise TrackingDatabaseIOError(f"{label} {path} is not a directory")
    return descriptor


def _fsync_directory(descriptor: int) -> None:
    os.fsync(descriptor)


def _ensure_backup_directory(path: Path) -> int:
    created = False
    try:
        os.mkdir(path, mode=0o700)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise TrackingDatabaseIOError(
            f"cannot create tracking-database backup directory {path}: {exc}"
        ) from exc
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise TrackingDatabaseIOError(
            f"tracking-database backup directory {path} must be a real directory: {exc}"
        ) from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise TrackingDatabaseIOError(
            f"tracking-database backup directory {path} must be a real directory"
        )
    if created:
        parent_descriptor = _open_directory(path.parent, label="backup parent directory")
        try:
            _fsync_directory(parent_descriptor)
        except OSError as exc:
            os.close(descriptor)
            raise TrackingDatabaseIOError(
                f"cannot durably create tracking-database backup directory {path}: {exc}"
            ) from exc
        finally:
            os.close(parent_descriptor)
    return descriptor


def _write_exact_backup(
    request: BackupRequest,
    expected: TrackingDatabaseSnapshot,
) -> str:
    if request.input_sha256 != expected.sha256:
        raise TrackingDatabaseIOError(
            "backup input_sha256 does not match the validated tracking-database bytes"
        )
    backup_path = _absolute_path(request.path)
    directory_descriptor = _ensure_backup_directory(backup_path.parent)
    read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    read_flags |= getattr(os, "O_NOFOLLOW", 0)
    create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    create_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    created = False
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(
                backup_path.name,
                create_flags,
                expected.mode,
                dir_fd=directory_descriptor,
            )
            created = True
        except FileExistsError:
            descriptor = os.open(
                backup_path.name,
                read_flags,
                dir_fd=directory_descriptor,
            )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise TrackingDatabaseIOError(
                f"tracking-database backup {backup_path} must be a regular file"
            )
        if created:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                handle.write(expected.raw)
                handle.flush()
                os.fsync(handle.fileno())
        else:
            existing = _read_descriptor(descriptor)
            os.close(descriptor)
            descriptor = None
            if existing != expected.raw:
                raise TrackingDatabaseIOError(
                    f"existing tracking-database backup {backup_path} does not match "
                    "the validated input bytes; choose a new hash-bound backup path"
                )
        _fsync_directory(directory_descriptor)
    except OSError as exc:
        if created:
            try:
                os.unlink(backup_path.name, dir_fd=directory_descriptor)
            except OSError:
                pass
        raise TrackingDatabaseIOError(
            f"cannot durably write tracking-database backup {backup_path}: {exc}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_descriptor)
    return str(backup_path)


def _write_descriptor(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            raise OSError("staged tracking-database write made no progress")
        offset += written


def _pread_descriptor(descriptor: int, size: int) -> bytes:
    chunks: list[bytes] = []
    offset = 0
    while offset < size:
        chunk = os.pread(descriptor, min(READ_CHUNK_SIZE, size - offset), offset)
        if not chunk:
            break
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


def _visible_descriptor_identity(
    name: str,
    descriptor: int,
    directory_descriptor: int,
) -> bool:
    try:
        opened = os.fstat(descriptor)
        visible = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return False
    return (
        stat.S_ISREG(opened.st_mode)
        and stat.S_ISREG(visible.st_mode)
        and _lock_identity(opened) == _lock_identity(visible)
    )


def _unlink_staged_name(stage: StagedCandidate, warnings: list[str]) -> None:
    try:
        os.stat(
            stage.name,
            dir_fd=stage.directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    except OSError as exc:
        warnings.append(f"could not inspect staged candidate {stage.path}: {exc}")
        return
    if not _visible_descriptor_identity(
        stage.name,
        stage.descriptor,
        stage.directory_descriptor,
    ):
        warnings.append(
            f"staged candidate name {stage.path} was substituted; left it untouched"
        )
        return
    try:
        os.unlink(stage.name, dir_fd=stage.directory_descriptor)
    except OSError as exc:
        warnings.append(f"could not remove staged candidate {stage.path}: {exc}")


def _close_staged_candidate(stage: StagedCandidate, warnings: list[str]) -> None:
    _unlink_staged_name(stage, warnings)
    _append_close_warning(
        stage.descriptor,
        label=f"staged tracking-database candidate {stage.path}",
        warnings=warnings,
    )
    _append_close_warning(
        stage.directory_descriptor,
        label=f"tracking-database directory {stage.path.parent}",
        warnings=warnings,
    )


def _stage_candidate(path: Path, candidate: bytes, mode: int) -> StagedCandidate:
    directory_descriptor = _open_directory(
        path.parent,
        label="tracking-database directory",
    )
    descriptor: int | None = None
    name: str | None = None
    completed = False
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        for _ in range(128):
            candidate_name = (
                f".{path.name}.{secrets.token_hex(12)}.tracking-db.tmp"
            )
            try:
                descriptor = os.open(
                    candidate_name,
                    flags,
                    0o600,
                    dir_fd=directory_descriptor,
                )
                name = candidate_name
                break
            except FileExistsError:
                continue
        if descriptor is None or name is None:
            raise TrackingDatabaseIOError(
                f"cannot allocate a unique staged candidate beside {path}"
            )
        os.fchmod(descriptor, mode)
        _write_descriptor(descriptor, candidate)
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise TrackingDatabaseIOError(
                f"staged tracking-database candidate {path.parent / name} "
                "must be one regular file"
            )
        stage = StagedCandidate(
            path=path.parent / name,
            name=name,
            descriptor=descriptor,
            directory_descriptor=directory_descriptor,
            generation=FileGeneration.from_stat(metadata),
            sha256=_sha256(candidate),
            size=len(candidate),
        )
        _verify_staged_candidate(stage, candidate)
        completed = True
        return stage
    finally:
        if not completed:
            if descriptor is not None and name is not None:
                if _visible_descriptor_identity(name, descriptor, directory_descriptor):
                    try:
                        os.unlink(name, dir_fd=directory_descriptor)
                    except OSError:
                        pass
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            try:
                os.close(directory_descriptor)
            except OSError:
                pass


def _verify_staged_candidate(stage: StagedCandidate, candidate: bytes) -> None:
    try:
        opened_before = os.fstat(stage.descriptor)
        visible_before = os.stat(
            stage.name,
            dir_fd=stage.directory_descriptor,
            follow_symlinks=False,
        )
        raw = _pread_descriptor(stage.descriptor, stage.size)
        opened_after = os.fstat(stage.descriptor)
        visible_after = os.stat(
            stage.name,
            dir_fd=stage.directory_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise TrackingDatabaseConflictError(
            f"staged tracking-database candidate {stage.path} changed before install: {exc}"
        ) from exc
    expected_generation = stage.generation
    if (
        not stat.S_ISREG(opened_before.st_mode)
        or opened_before.st_nlink != 1
        or not stat.S_ISREG(visible_before.st_mode)
        or visible_before.st_nlink != 1
        or FileGeneration.from_stat(opened_before) != expected_generation
        or FileGeneration.from_stat(visible_before) != expected_generation
        or FileGeneration.from_stat(opened_after) != expected_generation
        or FileGeneration.from_stat(visible_after) != expected_generation
        or opened_after.st_nlink != 1
        or visible_after.st_nlink != 1
        or raw != candidate
        or _sha256(raw) != stage.sha256
    ):
        raise TrackingDatabaseConflictError(
            f"staged tracking-database candidate {stage.path} content or generation "
            "changed before install"
        )


def _replace_staged_candidate(stage: StagedCandidate, target: Path) -> None:
    if os.replace in os.supports_dir_fd:
        os.replace(
            stage.name,
            target.name,
            src_dir_fd=stage.directory_descriptor,
            dst_dir_fd=stage.directory_descriptor,
        )
    else:  # pragma: no cover - supported on the Unix platforms this plugin targets.
        os.replace(stage.path, target)


def _link_staged_candidate(stage: StagedCandidate, target: Path) -> None:
    if os.link in os.supports_dir_fd:
        os.link(
            stage.name,
            target.name,
            src_dir_fd=stage.directory_descriptor,
            dst_dir_fd=stage.directory_descriptor,
            follow_symlinks=False,
        )
    else:  # pragma: no cover - supported on the Unix platforms this plugin targets.
        os.link(stage.path, target, follow_symlinks=False)


def _installed_target_warning(
    stage: StagedCandidate,
    target: Path,
    candidate: bytes,
) -> str | None:
    try:
        opened_before = os.fstat(stage.descriptor)
        visible_before = os.stat(
            target.name,
            dir_fd=stage.directory_descriptor,
            follow_symlinks=False,
        )
        raw = _pread_descriptor(stage.descriptor, stage.size)
        opened_after = os.fstat(stage.descriptor)
        visible_after = os.stat(
            target.name,
            dir_fd=stage.directory_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        return f"could not verify installed tracking database {target}: {exc}"
    if (
        not stat.S_ISREG(opened_before.st_mode)
        or not stat.S_ISREG(visible_before.st_mode)
        or not stat.S_ISREG(opened_after.st_mode)
        or not stat.S_ISREG(visible_after.st_mode)
        or _lock_identity(opened_before) != _lock_identity(visible_before)
        or _lock_identity(opened_after) != _lock_identity(visible_after)
        or _lock_identity(opened_before) != _lock_identity(opened_after)
        or opened_before.st_size != stage.size
        or visible_before.st_size != stage.size
        or opened_after.st_size != stage.size
        or visible_after.st_size != stage.size
        or raw != candidate
        or _sha256(raw) != stage.sha256
    ):
        return (
            f"installed tracking database {target} no longer matches the staged "
            "candidate; inspect the live path and output SHA before retrying"
        )
    return None


def commit_tracking_database(
    expected: TrackingDatabaseSnapshot,
    candidate: bytes,
    *,
    backup: BackupRequest | None = None,
) -> TrackingDatabaseWriteResult:
    """Install ``candidate`` iff ``expected`` is still the exact live generation.

    Once replacement succeeds, verification and cleanup failures are returned as
    an installed result with warnings. Exceptions are reserved for failures
    observed before the replacement syscall reports success.
    """
    if not isinstance(candidate, bytes):
        raise TypeError("tracking-database candidate must be bytes")
    decode_json_object(expected)
    decode_json_object_bytes(
        candidate,
        expected.path,
        label="tracking-database candidate",
    )
    output_sha256 = _sha256(candidate)
    backup_path: str | None = None
    warnings: list[str] = []
    result: TrackingDatabaseWriteResult | None = None
    with _exclusive_database_lock(expected.path) as lock:
        current = _require_expected_generation(expected)
        if candidate == current.raw:
            result = unchanged_write_result(expected)
        else:
            stage = _stage_candidate(expected.path, candidate, current.mode)
            try:
                _require_expected_generation(expected)
                _verify_staged_candidate(stage, candidate)
                if backup is not None:
                    backup_path = _write_exact_backup(backup, expected)
                    _require_expected_generation(expected)
                    _verify_staged_candidate(stage, candidate)
                try:
                    _replace_staged_candidate(stage, expected.path)
                except OSError as exc:
                    raise TrackingDatabaseIOError(
                        f"cannot install tracking database {expected.path}: {exc}"
                    ) from exc

                durability_state = "durable"
                verification_warning = _installed_target_warning(
                    stage,
                    expected.path,
                    candidate,
                )
                if verification_warning is not None:
                    durability_state = "installed_verification_failed"
                    warnings.append(verification_warning)
                try:
                    _fsync_directory(stage.directory_descriptor)
                except OSError as exc:
                    if durability_state == "durable":
                        durability_state = "installed_directory_fsync_failed"
                    warnings.append(
                        "tracking database was installed, but its parent-directory "
                        f"fsync failed: {exc}; inspect the installed output SHA before "
                        "retrying"
                    )
                result = TrackingDatabaseWriteResult(
                    input_sha256=expected.sha256,
                    output_sha256=output_sha256,
                    changed=True,
                    installed=True,
                    durability_state=durability_state,
                    warnings=(),
                    backup=backup_path,
                )
            finally:
                _close_staged_candidate(stage, warnings)

    if result is None:  # pragma: no cover - context contract.
        raise AssertionError("tracking-database transaction produced no result")
    return TrackingDatabaseWriteResult(
        input_sha256=result.input_sha256,
        output_sha256=result.output_sha256,
        changed=result.changed,
        installed=result.installed,
        durability_state=result.durability_state,
        warnings=result.warnings + tuple(warnings) + tuple(lock.warnings),
        backup=result.backup,
    )


def initialize_tracking_database(
    path: str | os.PathLike[str],
    payload: dict[str, Any],
    *,
    mode: int = 0o600,
) -> TrackingDatabaseWriteResult:
    """Atomically create a missing database without overwriting a concurrent file."""
    database_path = _absolute_path(path)
    candidate = render_json_object(payload)
    output_sha256 = _sha256(candidate)
    warnings: list[str] = []
    result: TrackingDatabaseWriteResult | None = None
    with _exclusive_database_lock(database_path) as lock:
        _require_missing_database(database_path)
        stage = _stage_candidate(database_path, candidate, mode)
        try:
            _require_missing_database(database_path)
            _verify_staged_candidate(stage, candidate)
            try:
                _link_staged_candidate(stage, database_path)
            except FileExistsError as exc:
                raise TrackingDatabaseConflictError(
                    "tracking database appeared during initialization; load the new "
                    "generation and rerun the intended mutation"
                ) from exc
            except OSError as exc:
                raise TrackingDatabaseIOError(
                    f"cannot install initial tracking database {database_path}: {exc}"
                ) from exc

            durability_state = "durable"
            verification_warning = _installed_target_warning(
                stage,
                database_path,
                candidate,
            )
            if verification_warning is not None:
                durability_state = "installed_verification_failed"
                warnings.append(verification_warning)
            _unlink_staged_name(stage, warnings)
            try:
                _fsync_directory(stage.directory_descriptor)
            except OSError as exc:
                if durability_state == "durable":
                    durability_state = "installed_directory_fsync_failed"
                warnings.append(
                    "tracking database was initialized, but its parent-directory "
                    f"fsync failed: {exc}; inspect the output SHA before retrying"
                )
            result = TrackingDatabaseWriteResult(
                input_sha256=None,
                output_sha256=output_sha256,
                changed=True,
                installed=True,
                durability_state=durability_state,
                warnings=(),
                backup=None,
            )
        finally:
            _close_staged_candidate(stage, warnings)

    if result is None:  # pragma: no cover - context contract.
        raise AssertionError("tracking-database initialization produced no result")
    return TrackingDatabaseWriteResult(
        input_sha256=result.input_sha256,
        output_sha256=result.output_sha256,
        changed=result.changed,
        installed=result.installed,
        durability_state=result.durability_state,
        warnings=result.warnings + tuple(warnings) + tuple(lock.warnings),
        backup=result.backup,
    )


def write_json_object(
    expected: TrackingDatabaseSnapshot,
    payload: dict[str, Any],
    *,
    backup: BackupRequest | None = None,
) -> TrackingDatabaseWriteResult:
    """Commit one JSON object, preserving raw bytes for a semantic no-op."""
    current = decode_json_object(expected)
    if json_values_equal(current, payload):
        return commit_tracking_database(expected, expected.raw, backup=backup)
    return commit_tracking_database(expected, render_json_object(payload), backup=backup)

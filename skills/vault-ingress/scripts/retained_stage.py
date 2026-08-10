#!/usr/bin/env python3
"""Retained named-stage primitive shared by every owner file writer.

An owner writer that stages bytes beside its target and then renames them into
place has one hard problem: between staging and install, the staged *pathname*
is just a name in a directory anyone can write to. A writer that stages by path,
closes the descriptor, and later calls ``os.replace(name, target)`` installs
whatever the name points at by then — and reports success.

This module keeps a descriptor open on the staged inode for the whole
transaction and proves, at every observation, that the visible name still
resolves to that exact inode with the exact bytes. The invariants it enforces:

- unique ``O_NOFOLLOW`` creation of the staged file itself, with a retained
  file descriptor and a directory descriptor every later syscall anchors to;
- regular-file and single-link validation;
- exact descriptor/name device and inode identity at every preinstall
  observation;
- exact size, bytes, and candidate SHA-256 binding;
- bounded same-view ``mtime_ns``/``ctime_ns`` stabilization, without requiring
  the descriptor and path timestamp caches to agree with each other;
- immediate typed failure for identity, type, link, size, byte, or digest
  changes.

Target-specific compare-and-swap and backup behavior stay with each owner. This
module owns the staged-file lifecycle and the typed observations only.

Cleanup is truthful about what it did: a still-owned staged name is removed, a
name that now resolves to a different inode or file type is left untouched and
reported as ``staged_cleanup_name_not_owned``, and unlink/close failures surface
as structured reasons rather than being discarded. ``KeyboardInterrupt`` and
``SystemExit`` propagate untouched.
"""

from __future__ import annotations

import hashlib
import os
import sys
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path

READ_CHUNK_SIZE = 1024 * 1024

# Bounded retries for the same-view timestamp stabilization window. A busy
# filesystem can update mtime_ns/ctime_ns between the two observations that
# bracket one byte read; permanent churn is a failure, not an infinite wait.
STAGED_METADATA_STABILIZATION_ATTEMPTS = 4

# How many unique staged names to try before giving up on collision.
STAGED_NAME_ATTEMPTS = 128

# Stable cleanup reason codes. Callers route on these; prose may be reworded.
STAGED_CLEANUP_UNLINK_FAILED = "staged_cleanup_unlink_failed"
STAGED_CLEANUP_DESCRIPTOR_CLOSE_FAILED = "staged_cleanup_descriptor_close_failed"
STAGED_CLEANUP_DIRECTORY_CLOSE_FAILED = "staged_cleanup_directory_close_failed"
STAGED_CLEANUP_NAME_NOT_OWNED = "staged_cleanup_name_not_owned"
STAGED_CLEANUP_INSPECT_FAILED = "staged_cleanup_inspect_failed"


class RetainedStageError(ValueError):
    """A retained stage could not be created or kept trustworthy.

    ``reason_code`` is the stable, typed classification. Consumers route on it;
    the message is human prose and may be reworded without notice.
    """

    def __init__(self, message: str, *, reason_code: str = "staged_error") -> None:
        super().__init__(message)
        self.reason_code = reason_code


class StagedInvariantError(RetainedStageError):
    """One named staged invariant failed before installation.

    ``invariant`` names which binding broke, so a caller can branch without
    parsing prose.
    """

    def __init__(self, path: Path, invariant: str, detail: str, *, label: str) -> None:
        self.path = path
        self.invariant = invariant
        self.detail = detail
        super().__init__(
            f"staged {label} {path} changed before install: "
            f"invariant={invariant}; {detail}",
            reason_code="staged_invariant_failed",
        )


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


@dataclass
class RetainedStage:
    """Open, directory-anchored staged bytes retained through installation."""

    path: Path
    name: str
    descriptor: int
    directory_descriptor: int
    generation: FileGeneration
    sha256: str
    size: int
    label: str
    directory_label: str


@dataclass(frozen=True)
class StageCleanupReport:
    """What cleanup actually did, in stable terms a caller can report.

    ``disposition`` is one of ``removed``, ``already_absent``, or
    ``staged_cleanup_name_not_owned``. A cleanup that could not finish carries
    ``reason_codes`` alongside human ``warnings``; neither ever converts an
    installed outcome into a failure.
    """

    disposition: str
    warnings: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.reason_codes


@dataclass(frozen=True)
class _StagedObservation:
    """One descriptor/name observation around an exact staged-byte read."""

    opened_before: os.stat_result
    visible_before: os.stat_result
    raw: bytes
    opened_after: os.stat_result
    visible_after: os.stat_result


@dataclass
class _CleanupCollector:
    warnings: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)

    def add(self, reason_code: str, message: str) -> None:
        self.reason_codes.append(reason_code)
        self.warnings.append(message)


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def open_directory(path: Path, *, label: str) -> int:
    """Open a directory descriptor the stage anchors every later syscall to.

    Deliberately not ``O_NOFOLLOW``: the vault root is documented as possibly
    being a symlink to a custom location, so refusing a symlinked component
    here would break supported installs. The no-follow guarantee this module
    makes is about the staged *file* and every later name resolution, which is
    anchored to this descriptor and so cannot be redirected by a directory
    swapped after the open.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RetainedStageError(
            f"cannot open {label} {path}: {exc}",
            reason_code="staged_directory_unavailable",
        ) from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise RetainedStageError(
            f"{label} {path} is not a directory",
            reason_code="staged_directory_unavailable",
        )
    return descriptor


def _write_descriptor(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            raise OSError("staged write made no progress")
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


def visible_descriptor_identity(
    name: str,
    descriptor: int,
    directory_descriptor: int,
) -> bool:
    """Whether the visible name still resolves to the retained descriptor."""
    try:
        opened = os.fstat(descriptor)
        visible = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISREG(opened.st_mode)
        and stat.S_ISREG(visible.st_mode)
        and _identity(opened) == _identity(visible)
    )


def _warn(notes: list[str]) -> None:
    """Surface best-effort cleanup failures that have nowhere else to go.

    `error-handling` Shell Error Handling: best-effort work that legitimately
    continues past a failure emits a warning, never nothing.
    """
    for note in notes:
        print(f"WARNING: {note}", file=sys.stderr)


def _release_incomplete_stage(
    name: str | None,
    descriptor: int | None,
    directory_descriptor: int,
) -> list[str]:
    """Drop a half-built stage, returning what could not be cleaned up."""
    notes: list[str] = []
    if descriptor is not None and name is not None:
        if visible_descriptor_identity(name, descriptor, directory_descriptor):
            try:
                os.unlink(name, dir_fd=directory_descriptor)
            except OSError as exc:
                notes.append(f"could not remove incomplete staged file {name}: {exc}")
        else:
            notes.append(
                f"incomplete staged name {name} was substituted; left it untouched"
            )
        try:
            os.close(descriptor)
        except OSError as exc:
            notes.append(f"could not close incomplete staged file {name}: {exc}")
    try:
        os.close(directory_descriptor)
    except OSError as exc:
        notes.append(f"could not close staging directory descriptor: {exc}")
    return notes


def open_retained_stage(
    path: Path,
    payload: bytes,
    *,
    mode: int,
    suffix: str,
    label: str,
    directory_label: str | None = None,
    verify: bool = True,
) -> RetainedStage:
    """Create, fill, fsync, and bind one staged file beside ``path``.

    The returned stage keeps its descriptor and directory descriptor open. The
    caller owns closing it through :func:`close_retained_stage`.

    ``verify=False`` skips the initial verification so an owner that wraps
    :func:`verify_retained_stage` in its own typed-error mapping runs every
    verification through that one seam.
    """
    directory_prose = directory_label or label
    directory_descriptor = open_directory(
        path.parent, label=f"{directory_prose} directory"
    )
    descriptor: int | None = None
    name: str | None = None
    completed = False
    released = False
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        for _ in range(STAGED_NAME_ATTEMPTS):
            candidate_name = f".{path.name}.{secrets.token_hex(12)}{suffix}"
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
            raise RetainedStageError(
                f"cannot allocate a unique staged {label} beside {path}",
                reason_code="staged_name_unavailable",
            )
        os.fchmod(descriptor, mode)
        _write_descriptor(descriptor, payload)
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RetainedStageError(
                f"staged {label} {path.parent / name} must be one regular file",
                reason_code="staged_shape_invalid",
            )
        stage = RetainedStage(
            path=path.parent / name,
            name=name,
            descriptor=descriptor,
            directory_descriptor=directory_descriptor,
            generation=FileGeneration.from_stat(metadata),
            sha256=sha256_hex(payload),
            size=len(payload),
            label=label,
            directory_label=directory_prose,
        )
        if verify:
            verify_retained_stage(stage, payload)
        completed = True
        return stage
    except Exception as exc:
        released = True
        notes = _release_incomplete_stage(name, descriptor, directory_descriptor)
        if notes and isinstance(exc, RetainedStageError):
            # Attach rather than discard: an orphaned staged temp with no
            # diagnostic naming it is the exact failure this module exists to
            # stop. Attaching keeps the primary error's type and reason_code.
            raise type(exc)(
                f"{exc}; staged cleanup: {'; '.join(notes)}",
                reason_code=exc.reason_code,
            ) from exc
        _warn(notes)
        raise
    finally:
        if not completed and not released:
            # Interrupt path: cleanup still runs, and its diagnostics still go
            # somewhere. Re-raising here would replace the interrupt.
            _warn(_release_incomplete_stage(name, descriptor, directory_descriptor))


def _observe(stage: RetainedStage) -> _StagedObservation:
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
        raise StagedInvariantError(
            stage.path,
            "metadata_read",
            str(exc),
            label=stage.label,
        ) from exc
    return _StagedObservation(
        opened_before=opened_before,
        visible_before=visible_before,
        raw=raw,
        opened_after=opened_after,
        visible_after=visible_after,
    )


def _samples(
    observation: _StagedObservation,
) -> tuple[tuple[str, os.stat_result], ...]:
    return (
        ("descriptor_before", observation.opened_before),
        ("name_before", observation.visible_before),
        ("descriptor_after", observation.opened_after),
        ("name_after", observation.visible_after),
    )


def _require_invariants(
    stage: RetainedStage,
    payload: bytes,
    observation: _StagedObservation,
) -> None:
    samples = _samples(observation)
    non_regular = [
        label for label, metadata in samples if not stat.S_ISREG(metadata.st_mode)
    ]
    if non_regular:
        raise StagedInvariantError(
            stage.path,
            "regular_file",
            f"non-regular observations={non_regular}",
            label=stage.label,
        )
    expected_identity = (stage.generation.device, stage.generation.inode)
    identities = {label: _identity(metadata) for label, metadata in samples}
    if any(identity != expected_identity for identity in identities.values()):
        raise StagedInvariantError(
            stage.path,
            "descriptor_name_identity",
            f"expected={expected_identity}; observed={identities}",
            label=stage.label,
        )
    link_counts = {label: metadata.st_nlink for label, metadata in samples}
    if any(link_count != 1 for link_count in link_counts.values()):
        raise StagedInvariantError(
            stage.path,
            "link_count",
            f"expected one link; observed={link_counts}",
            label=stage.label,
        )
    sizes = {label: metadata.st_size for label, metadata in samples}
    if (
        len(payload) != stage.size
        or len(observation.raw) != stage.size
        or any(size != stage.size for size in sizes.values())
    ):
        raise StagedInvariantError(
            stage.path,
            "size",
            f"expected={stage.size}; candidate={len(payload)}; "
            f"read={len(observation.raw)}; observed={sizes}",
            label=stage.label,
        )
    if observation.raw != payload:
        raise StagedInvariantError(
            stage.path,
            "exact_bytes",
            "descriptor bytes differ from the exact candidate",
            label=stage.label,
        )
    payload_sha256 = sha256_hex(payload)
    observed_sha256 = sha256_hex(observation.raw)
    if stage.sha256 != payload_sha256 or observed_sha256 != stage.sha256:
        raise StagedInvariantError(
            stage.path,
            "sha256",
            f"expected={stage.sha256}; candidate={payload_sha256}; "
            f"observed={observed_sha256}",
            label=stage.label,
        )


def verify_retained_stage(stage: RetainedStage, payload: bytes) -> None:
    """Prove the staged name still holds the exact retained bytes.

    Stabilization compares each view against itself across one read window.
    Requiring the descriptor and path timestamp caches to agree with each other
    would fail on filesystems that update them independently.
    """
    last_timestamps: dict[str, tuple[int, int]] = {}
    last_unstable_fields: list[str] = []
    for _ in range(STAGED_METADATA_STABILIZATION_ATTEMPTS):
        observation = _observe(stage)
        _require_invariants(stage, payload, observation)
        last_timestamps = {
            label: (metadata.st_mtime_ns, metadata.st_ctime_ns)
            for label, metadata in _samples(observation)
        }
        last_unstable_fields = []
        for view in ("descriptor", "name"):
            before = last_timestamps[f"{view}_before"]
            after = last_timestamps[f"{view}_after"]
            if before[0] != after[0]:
                last_unstable_fields.append(f"{view}.mtime_ns")
            if before[1] != after[1]:
                last_unstable_fields.append(f"{view}.ctime_ns")
        if not last_unstable_fields:
            return
    raise StagedInvariantError(
        stage.path,
        "timestamp_stability",
        "staged mtime_ns/ctime_ns changed within every read window across "
        f"{STAGED_METADATA_STABILIZATION_ATTEMPTS} bounded observations; "
        f"unstable_fields={last_unstable_fields}; last_observed={last_timestamps}",
        label=stage.label,
    )


def install_retained_stage(stage: RetainedStage, target: Path) -> None:
    """Rename the staged name onto ``target`` within the anchored directory.

    Raises ``OSError`` so each owner classifies install failure in its own
    terms. Directory-anchored where the platform supports it, so a renamed or
    replaced parent directory cannot redirect the install.
    """
    if os.replace in os.supports_dir_fd:
        os.replace(
            stage.name,
            target.name,
            src_dir_fd=stage.directory_descriptor,
            dst_dir_fd=stage.directory_descriptor,
        )
    else:  # pragma: no cover - supported on the Unix platforms this plugin targets.
        os.replace(stage.path, target)


def installed_target_warning(
    stage: RetainedStage,
    target: Path,
    payload: bytes,
) -> str | None:
    """Post-install proof that ``target`` is the exact staged generation.

    Returns a warning when the installed target cannot be confirmed. The caller
    reports it as ``installed-but-verification-failed`` — never as a pre-install
    failure, because the replace already happened.
    """
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
        return f"could not verify installed {stage.label} {target}: {exc}"
    if (
        not stat.S_ISREG(opened_before.st_mode)
        or not stat.S_ISREG(visible_before.st_mode)
        or not stat.S_ISREG(opened_after.st_mode)
        or not stat.S_ISREG(visible_after.st_mode)
        or _identity(opened_before) != _identity(visible_before)
        or _identity(opened_after) != _identity(visible_after)
        or _identity(opened_before) != _identity(opened_after)
        or opened_before.st_size != stage.size
        or visible_before.st_size != stage.size
        or opened_after.st_size != stage.size
        or visible_after.st_size != stage.size
        or raw != payload
        or sha256_hex(raw) != stage.sha256
    ):
        return (
            f"installed {stage.label} {target} no longer matches the staged "
            "candidate; inspect the live path and output SHA before retrying"
        )
    return None


def _unlink_staged_name(stage: RetainedStage, collector: _CleanupCollector) -> str:
    try:
        os.stat(stage.name, dir_fd=stage.directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return "already_absent"
    except OSError as exc:
        collector.add(
            STAGED_CLEANUP_INSPECT_FAILED,
            f"could not inspect staged {stage.label} {stage.path}: {exc}",
        )
        return "already_absent"
    if not visible_descriptor_identity(
        stage.name,
        stage.descriptor,
        stage.directory_descriptor,
    ):
        # Someone else's file now answers to this name. Removing it would
        # delete a stranger's data to tidy up after ourselves.
        collector.add(
            STAGED_CLEANUP_NAME_NOT_OWNED,
            f"staged {stage.label} name {stage.path} was substituted; "
            "left it untouched",
        )
        return STAGED_CLEANUP_NAME_NOT_OWNED
    try:
        os.unlink(stage.name, dir_fd=stage.directory_descriptor)
    except OSError as exc:
        collector.add(
            STAGED_CLEANUP_UNLINK_FAILED,
            f"could not remove staged {stage.label} {stage.path}: {exc}",
        )
        return "already_absent"
    return "removed"


def release_staged_name(stage: RetainedStage) -> StageCleanupReport:
    """Unlink a still-owned staged name while keeping both descriptors open.

    For an owner that installs by hard link rather than rename: the target now
    exists, the staged name is a second link to drop, and the directory
    descriptor is still needed for the durability fsync.
    """
    collector = _CleanupCollector()
    disposition = _unlink_staged_name(stage, collector)
    return StageCleanupReport(
        disposition=disposition,
        warnings=tuple(collector.warnings),
        reason_codes=tuple(collector.reason_codes),
    )


def close_retained_stage(stage: RetainedStage) -> StageCleanupReport:
    """Unlink a still-owned staged name and close both descriptors.

    Always attempted, and always truthful: the report says what happened rather
    than silently swallowing an orphaned temp file. Callers attach it to their
    result (installed or not) instead of letting it change the outcome.
    """
    collector = _CleanupCollector()
    disposition = _unlink_staged_name(stage, collector)
    try:
        os.close(stage.descriptor)
    except OSError as exc:
        collector.add(
            STAGED_CLEANUP_DESCRIPTOR_CLOSE_FAILED,
            f"could not close staged {stage.label} {stage.path}: {exc}",
        )
    try:
        os.close(stage.directory_descriptor)
    except OSError as exc:
        collector.add(
            STAGED_CLEANUP_DIRECTORY_CLOSE_FAILED,
            f"could not close {stage.directory_label} directory {stage.path.parent}: {exc}",
        )
    return StageCleanupReport(
        disposition=disposition,
        warnings=tuple(collector.warnings),
        reason_codes=tuple(collector.reason_codes),
    )

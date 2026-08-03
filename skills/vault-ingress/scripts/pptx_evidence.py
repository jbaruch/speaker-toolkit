#!/usr/bin/env python3
"""Shared native-deck recovery and exact render-inspection receipts."""

from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import signal
import stat as stat_module
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable
from zlib import error as ZlibError


PPTX_EXTRACTION_SCHEMA_VERSION = 3
PPTX_EXTRACTION_PIPELINE_VERSION = "1.2.0"
ARCHIVE_RECOVERY_SCHEMA_VERSION = 1
NATIVE_DECK_AUDIT_SCHEMA_VERSION = 1
RENDER_INSPECTION_SCHEMA_VERSION = 1
PPTX_ARTIFACT_PROBE_SCHEMA_VERSION = 1
PPTX_ARTIFACT_PROBE_TIMEOUT_SECONDS = 10
PPTX_ARTIFACT_PROBE_MAX_RESULT_BYTES = 64 * 1024
PPTX_ARTIFACT_PROBE_MAX_RECOVERY_RECORDS = 64
PPTX_ARTIFACT_PROBE_CHILD_FLAG = "--artifact-probe-child"
PPTX_NATIVE_AUDIT_CHILD_FLAG = "--native-audit-child"
PPTX_MACOS_DATALESS_FLAG = int(
    getattr(
        stat_module,
        "SF_DATALESS",
        0x40000000 if sys.platform == "darwin" else 0,
    )
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AUDIT_FIELDS = frozenset(
    {
        "schema_version",
        "extraction_schema_version",
        "extraction_pipeline_version",
        "source_pptx_sha256",
        "source_pptx_size_bytes",
        "slide_count",
        "render_required_slide_numbers",
        "render_required_reasons",
        "extraction_receipt_sha256",
        "rendered_page_inspection",
    }
)
_RENDER_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "source_pptx_sha256",
        "rendered_pdf_sha256",
        "rendered_pdf_size_bytes",
        "rendered_page_count",
        "inspected_page_ranges",
        "inspected_required_slide_numbers",
        "complete",
        "binding_sha256",
    }
)
_RECOVERY_IMAGE_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class PptxEvidenceError(ValueError):
    """A PPTX artifact or evidence receipt violates its closed contract."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "pptx_evidence_invalid",
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = dict(details or {})


@dataclass(frozen=True)
class PptxArtifactProbe:
    """One exact readable deck generation plus any loss-recovery records."""

    slide_count: int
    source_sha256: str
    source_size_bytes: int
    archive_recovery: tuple[dict[str, object], ...]


_PPTX_ARTIFACT_PROBE_CACHE: dict[
    tuple[str, int, int, int, int, int, int],
    PptxArtifactProbe | tuple[str, str, dict[str, object]],
] = {}
_PPTX_NATIVE_AUDIT_CACHE: dict[
    tuple[str, int, int, int, int, int, int],
    dict[str, object] | tuple[str, str, dict[str, object]],
] = {}


def sha256_bytes(blob: bytes) -> str:
    """Return the lowercase SHA-256 digest for exact bytes."""
    return hashlib.sha256(blob).hexdigest()


def _canonical_sha256(value: Mapping[str, object]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise PptxEvidenceError(
            f"{label} must be a lowercase 64-character SHA-256 digest"
        )
    return value


def _file_generation(
    stat_result: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    """Return fields that identify one stable regular-file generation."""
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
        int(getattr(stat_result, "st_flags", 0)),
    )


def snapshot_regular_file(path: str | Path, *, label: str) -> bytes:
    """Read one exact non-symlink regular-file generation into memory."""
    artifact = Path(path)
    try:
        initial = artifact.lstat()
    except OSError as exc:
        raise PptxEvidenceError(
            f"{label} is unavailable at {artifact}: {exc}",
            reason_code="pptx_artifact_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    if stat_module.S_ISLNK(initial.st_mode) or not stat_module.S_ISREG(
        initial.st_mode
    ):
        raise PptxEvidenceError(
            f"{label} must be a non-symlink regular file: {artifact}",
            reason_code="pptx_artifact_unavailable",
        )
    generation = _file_generation(initial)
    try:
        with artifact.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if _file_generation(opened) != generation:
                raise PptxEvidenceError(
                    f"{label} changed while opening: {artifact}",
                    reason_code="pptx_artifact_changed",
                )
            blob = stream.read()
            after_read = os.fstat(stream.fileno())
    except PptxEvidenceError:
        raise
    except OSError as exc:
        raise PptxEvidenceError(
            f"cannot read {label} at {artifact}: {exc}",
            reason_code="pptx_artifact_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    try:
        current = artifact.lstat()
    except OSError as exc:
        raise PptxEvidenceError(
            f"{label} changed while it was read at {artifact}: {exc}",
            reason_code="pptx_artifact_changed",
            details={"exception_type": type(exc).__name__},
        ) from exc
    if (
        _file_generation(after_read) != generation
        or _file_generation(current) != generation
        or len(blob) != initial.st_size
    ):
        raise PptxEvidenceError(
            f"{label} changed while reading: {artifact}",
            reason_code="pptx_artifact_changed",
        )
    return blob


def _is_embedded_media_member(member_name: str) -> bool:
    normalized = member_name.replace("\\", "/").lstrip("/")
    return normalized.startswith("ppt/media/") and not normalized.endswith("/")


def _corrupt_zip_members(package_blob: bytes) -> list[str]:
    """Validate every ZIP member and return those whose payload is corrupt."""
    corrupt: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(package_blob)) as archive:
            for member in archive.infolist():
                try:
                    with archive.open(member) as stream:
                        while stream.read(1024 * 1024):
                            pass
                except (zipfile.BadZipFile, ZlibError):
                    corrupt.append(member.filename)
                    if (
                        len(corrupt)
                        > PPTX_ARTIFACT_PROBE_MAX_RECOVERY_RECORDS
                    ):
                        raise PptxEvidenceError(
                            "PPTX archive has more corrupt members than the "
                            "bounded recovery contract permits",
                            reason_code="pptx_probe_result_oversized",
                        )
    except zipfile.BadZipFile as exc:
        raise PptxEvidenceError(
            "invalid PPTX ZIP container; restore or re-export the source deck",
            reason_code="pptx_invalid_container",
        ) from exc
    return corrupt


def _parse_presentation(package_blob: bytes, *, recovered: bool) -> Any:
    try:
        from lxml.etree import XMLSyntaxError
        from pptx import Presentation
        from pptx.exc import PackageNotFoundError
    except ImportError as exc:
        raise PptxEvidenceError(
            "PPTX evidence requires the declared python-pptx and lxml runtime "
            "dependencies; install the speaker-toolkit project dependencies",
            reason_code="pptx_dependency_unavailable",
        ) from exc
    try:
        return Presentation(io.BytesIO(package_blob))
    except (
        zipfile.BadZipFile,
        ZlibError,
        PackageNotFoundError,
        XMLSyntaxError,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        prefix = "recovered PPTX package" if recovered else "PPTX package"
        raise PptxEvidenceError(
            f"{prefix} cannot be parsed; restore or re-export the source deck: {exc}",
            reason_code="pptx_parse_failure",
        ) from exc


def presentation_with_media_recovery(
    package_blob: bytes,
) -> tuple[Any, list[dict[str, object]]]:
    """Open a deck, replacing only CRC-damaged embedded media in memory."""
    corrupt_names = _corrupt_zip_members(package_blob)
    if not corrupt_names:
        return _parse_presentation(package_blob, recovered=False), []

    structural = [
        name for name in corrupt_names if not _is_embedded_media_member(name)
    ]
    if structural:
        raise PptxEvidenceError(
            "corrupt structural PPTX member(s) are not recoverable: "
            f"{', '.join(sorted(structural))}; restore or re-export the source deck",
            reason_code="pptx_structural_damage",
            details={"part_names": sorted(structural)},
        )

    recovered_package = io.BytesIO()
    corrupt_set = set(corrupt_names)
    try:
        with (
            zipfile.ZipFile(io.BytesIO(package_blob)) as source,
            zipfile.ZipFile(recovered_package, "w") as destination,
        ):
            for member in source.infolist():
                payload = (
                    _RECOVERY_IMAGE_BYTES
                    if member.filename in corrupt_set
                    else source.read(member)
                )
                destination.writestr(member, payload)
    except (zipfile.BadZipFile, ZlibError, OSError) as exc:
        raise PptxEvidenceError(
            "could not recover corrupt PPTX media; restore or re-export the source deck",
            reason_code="pptx_recovery_failure",
        ) from exc

    recovery = [
        {
            "schema_version": ARCHIVE_RECOVERY_SCHEMA_VERSION,
            "part_name": name,
            "member_kind": "embedded_media",
            "error_type": "crc_mismatch",
            "status": "recovered_with_placeholder_asset",
            "content_replaced": True,
            "replacement_sha256": sha256_bytes(_RECOVERY_IMAGE_BYTES),
        }
        for name in sorted(corrupt_names)
    ]
    return _parse_presentation(recovered_package.getvalue(), recovered=True), recovery


def _probe_pptx_artifact_in_process(path: str | Path) -> PptxArtifactProbe:
    """Perform the expensive deck probe inside the bounded worker only."""
    package_blob = snapshot_regular_file(path, label="PPTX artifact")
    presentation, recovery = presentation_with_media_recovery(package_blob)
    slide_count = len(presentation.slides)
    if slide_count < 1:
        raise PptxEvidenceError(
            f"PPTX artifact has no slides: {path}",
            reason_code="pptx_no_slides",
        )
    return PptxArtifactProbe(
        slide_count=slide_count,
        source_sha256=sha256_bytes(package_blob),
        source_size_bytes=len(package_blob),
        archive_recovery=tuple(dict(item) for item in recovery),
    )


_CHILD_PROBE_REASON_CODES = frozenset(
    {
        "pptx_artifact_changed",
        "pptx_artifact_unavailable",
        "pptx_archive_recovery_required",
        "pptx_dependency_unavailable",
        "pptx_evidence_invalid",
        "pptx_invalid_container",
        "pptx_no_slides",
        "pptx_parse_failure",
        "pptx_probe_exception",
        "pptx_probe_resource_unavailable",
        "pptx_probe_result_oversized",
        "pptx_recovery_failure",
        "pptx_structural_damage",
    }
)

_ARCHIVE_INTEGRITY_CONFIRMATION_REASON_CODES = frozenset(
    {
        "pptx_artifact_unavailable",
        "pptx_archive_recovery_required",
        "pptx_invalid_container",
        "pptx_parse_failure",
        "pptx_probe_result_oversized",
        "pptx_recovery_failure",
        "pptx_structural_damage",
    }
)


def _probe_failure(
    reason_code: str,
    *,
    details: Mapping[str, object] | None = None,
) -> PptxEvidenceError:
    """Create one bounded, actionable parent-side probe error."""
    normalized = dict(details or {})
    part_names = normalized.get("part_names")
    joined_parts = (
        ", ".join(str(name) for name in part_names)
        if isinstance(part_names, list)
        else ""
    )
    messages = {
        "pptx_artifact_unavailable": (
            "PPTX artifact is unavailable; restore the file and retry"
        ),
        "pptx_archive_recovery_required": (
            "PPTX artifact required placeholder archive recovery and cannot "
            "authorize a fresh native-deck audit"
            + (f": {joined_parts}" if joined_parts else "")
            + "; restore or re-export the source deck"
        ),
        "pptx_dependency_unavailable": (
            "PPTX evidence requires the declared python-pptx and lxml runtime "
            "dependencies; install the speaker-toolkit project dependencies"
        ),
        "pptx_evidence_invalid": (
            "PPTX artifact violates the evidence contract; restore or re-export "
            "the source deck"
        ),
        "pptx_invalid_container": (
            "invalid PPTX ZIP container; restore or re-export the source deck"
        ),
        "pptx_no_slides": "PPTX artifact has no slides; re-export the source deck",
        "pptx_parse_failure": (
            "PPTX package cannot be parsed; restore or re-export the source deck"
        ),
        "pptx_probe_exception": (
            "PPTX artifact probe failed unexpectedly inside its bounded worker"
        ),
        "pptx_probe_resource_unavailable": (
            "PPTX artifact probe exhausted worker resources"
        ),
        "pptx_probe_result_oversized": (
            "PPTX artifact probe produced more recovery metadata than the bounded "
            "result contract permits"
        ),
        "pptx_recovery_failure": (
            "could not recover corrupt PPTX media; restore or re-export the source deck"
        ),
        "pptx_structural_damage": (
            "corrupt structural PPTX member(s) are not recoverable"
            + (f": {joined_parts}" if joined_parts else "")
            + "; restore or re-export the source deck"
        ),
        "pptx_probe_timeout": (
            "PPTX artifact probe timed out after "
            f"{PPTX_ARTIFACT_PROBE_TIMEOUT_SECONDS} seconds; use an independent "
            "healthy evidence lane or repair/re-export the deck"
        ),
        "pptx_probe_start_failure": "could not start the bounded PPTX artifact probe",
        "pptx_probe_crash": (
            "PPTX artifact probe terminated inside its bounded worker"
        ),
        "pptx_probe_malformed_result": (
            "PPTX artifact probe returned an invalid bounded result"
        ),
        "pptx_probe_materialization_changed": (
            "PPTX artifact produced inconsistent bounded reads while cloud "
            "materialization was changing; retry after the file is fully local"
        ),
        "pptx_artifact_changed": "PPTX artifact changed while it was being probed",
        "pptx_cloud_placeholder_unavailable": (
            "PPTX artifact is a macOS dataless cloud placeholder; download the "
            "file locally before using native-deck evidence"
        ),
    }
    return PptxEvidenceError(
        messages.get(reason_code, "PPTX artifact is unavailable"),
        reason_code=reason_code,
        details=normalized,
    )


def _probe_child_failure_details(exc: PptxEvidenceError) -> dict[str, object]:
    """Copy only closed, bounded diagnostic fields into the child result."""
    details: dict[str, object] = {}
    raw_names = exc.details.get("part_names")
    if isinstance(raw_names, list):
        names = [
            name
            for name in raw_names
            if isinstance(name, str) and 0 < len(name) <= 2048
        ]
        if len(names) == len(raw_names) and len(names) <= 64:
            details["part_names"] = names
    exception_type = exc.details.get("exception_type")
    if (
        isinstance(exception_type, str)
        and exception_type
        and len(exception_type) <= 128
    ):
        details["exception_type"] = exception_type
    return details


def _pptx_probe_child(path: str | Path) -> dict[str, object]:
    """Return the closed payload written by the isolated probe worker."""
    try:
        probe = _probe_pptx_artifact_in_process(path)
    except MemoryError:
        return {
            "schema_version": PPTX_ARTIFACT_PROBE_SCHEMA_VERSION,
            "status": "unavailable",
            "reason_code": "pptx_probe_resource_unavailable",
            "details": {},
        }
    except PptxEvidenceError as exc:
        reason_code = (
            exc.reason_code
            if exc.reason_code in _CHILD_PROBE_REASON_CODES
            else "pptx_evidence_invalid"
        )
        return {
            "schema_version": PPTX_ARTIFACT_PROBE_SCHEMA_VERSION,
            "status": "unavailable",
            "reason_code": reason_code,
            "details": _probe_child_failure_details(exc),
        }
    return {
        "schema_version": PPTX_ARTIFACT_PROBE_SCHEMA_VERSION,
        "status": "available",
        "slide_count": probe.slide_count,
        "source_sha256": probe.source_sha256,
        "source_size_bytes": probe.source_size_bytes,
        "archive_recovery": [dict(item) for item in probe.archive_recovery],
    }


def _write_pptx_probe_result(
    result_file: BinaryIO,
    payload: Mapping[str, object],
) -> None:
    """Replace the private result through the child's retained descriptor."""
    rendered = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    if len(rendered) > PPTX_ARTIFACT_PROBE_MAX_RESULT_BYTES:
        rendered = (
            json.dumps(
                {
                    "schema_version": PPTX_ARTIFACT_PROBE_SCHEMA_VERSION,
                    "status": "unavailable",
                    "reason_code": "pptx_probe_result_oversized",
                    "details": {},
                },
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    result_file.seek(0)
    result_file.truncate()
    remaining = memoryview(rendered)
    while remaining:
        written = result_file.write(remaining)
        if written is None or written <= 0:
            raise OSError("PPTX probe result write made no progress")
        remaining = remaining[written:]
    result_file.flush()


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonstandard_json_constant(_value: str) -> object:
    raise ValueError("non-standard JSON number")


def _validated_recovery_records(value: object) -> tuple[dict[str, object], ...]:
    if (
        not isinstance(value, list)
        or len(value) > PPTX_ARTIFACT_PROBE_MAX_RECOVERY_RECORDS
    ):
        raise _probe_failure("pptx_probe_malformed_result")
    expected_fields = {
        "schema_version",
        "part_name",
        "member_kind",
        "error_type",
        "status",
        "content_replaced",
        "replacement_sha256",
    }
    records: list[dict[str, object]] = []
    for raw_record in value:
        if not isinstance(raw_record, dict) or set(raw_record) != expected_fields:
            raise _probe_failure("pptx_probe_malformed_result")
        part_name = raw_record.get("part_name")
        if (
            raw_record.get("schema_version") != ARCHIVE_RECOVERY_SCHEMA_VERSION
            or not isinstance(part_name, str)
            or not _is_embedded_media_member(part_name)
            or len(part_name) > 2048
            or raw_record.get("member_kind") != "embedded_media"
            or raw_record.get("error_type") != "crc_mismatch"
            or raw_record.get("status") != "recovered_with_placeholder_asset"
            or raw_record.get("content_replaced") is not True
            or raw_record.get("replacement_sha256")
            != sha256_bytes(_RECOVERY_IMAGE_BYTES)
        ):
            raise _probe_failure("pptx_probe_malformed_result")
        records.append(dict(raw_record))
    part_names = [str(record["part_name"]) for record in records]
    if part_names != sorted(set(part_names)):
        raise _probe_failure("pptx_probe_malformed_result")
    return tuple(records)


def _decode_pptx_probe_result(raw: bytes) -> PptxArtifactProbe:
    if len(raw) > PPTX_ARTIFACT_PROBE_MAX_RESULT_BYTES or not raw.strip():
        raise _probe_failure("pptx_probe_malformed_result")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _probe_failure("pptx_probe_malformed_result") from exc
    if len(decoded.splitlines()) != 1:
        raise _probe_failure("pptx_probe_malformed_result")
    try:
        payload = json.loads(
            decoded,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise _probe_failure("pptx_probe_malformed_result") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != PPTX_ARTIFACT_PROBE_SCHEMA_VERSION
    ):
        raise _probe_failure("pptx_probe_malformed_result")
    if payload.get("status") == "unavailable":
        if set(payload) != {"schema_version", "status", "reason_code", "details"}:
            raise _probe_failure("pptx_probe_malformed_result")
        reason_code = payload.get("reason_code")
        details = payload.get("details")
        if reason_code not in _CHILD_PROBE_REASON_CODES or not isinstance(details, dict):
            raise _probe_failure("pptx_probe_malformed_result")
        if set(details) - {"part_names", "exception_type"}:
            raise _probe_failure("pptx_probe_malformed_result")
        raw_names = details.get("part_names")
        if raw_names is not None and (
            not isinstance(raw_names, list)
            or len(raw_names) > 64
            or any(
                not isinstance(name, str) or not name or len(name) > 2048
                for name in raw_names
            )
        ):
            raise _probe_failure("pptx_probe_malformed_result")
        exception_type = details.get("exception_type")
        if exception_type is not None and (
            not isinstance(exception_type, str)
            or not exception_type
            or len(exception_type) > 128
        ):
            raise _probe_failure("pptx_probe_malformed_result")
        raise _probe_failure(str(reason_code), details=details)
    expected_fields = {
        "schema_version",
        "status",
        "slide_count",
        "source_sha256",
        "source_size_bytes",
        "archive_recovery",
    }
    slide_count = payload.get("slide_count")
    source_size = payload.get("source_size_bytes")
    source_sha = payload.get("source_sha256")
    if (
        payload.get("status") != "available"
        or set(payload) != expected_fields
        or isinstance(slide_count, bool)
        or not isinstance(slide_count, int)
        or slide_count < 1
        or isinstance(source_size, bool)
        or not isinstance(source_size, int)
        or source_size < 1
        or not isinstance(source_sha, str)
        or _SHA256_RE.fullmatch(source_sha) is None
    ):
        raise _probe_failure("pptx_probe_malformed_result")
    return PptxArtifactProbe(
        slide_count=slide_count,
        source_sha256=source_sha,
        source_size_bytes=source_size,
        archive_recovery=_validated_recovery_records(
            payload.get("archive_recovery")
        ),
    )


def _read_pptx_probe_result(result_file: BinaryIO) -> PptxArtifactProbe:
    try:
        result_file.seek(0)
        raw = result_file.read(PPTX_ARTIFACT_PROBE_MAX_RESULT_BYTES + 1)
    except OSError as exc:
        raise _probe_failure("pptx_probe_malformed_result") from exc
    return _decode_pptx_probe_result(raw)


def _signal_name(signal_number: int) -> str:
    try:
        return signal.Signals(signal_number).name
    except ValueError:
        return f"SIG{signal_number}"


def _run_bounded_private_worker(
    path: Path,
    *,
    child_flag: str,
    decoder: Callable[[bytes], Any],
) -> Any:
    """Run one output-silent worker and decode its private bounded result."""
    with tempfile.TemporaryDirectory(prefix="speaker-toolkit-pptx-probe-") as temp:
        result_path = Path(temp) / "result.json"
        with result_path.open("x+b", buffering=0) as result_file:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                child_flag,
                os.fspath(path),
                os.fspath(result_path),
            ]
            try:
                completed = subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=PPTX_ARTIFACT_PROBE_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise _probe_failure(
                    "pptx_probe_timeout",
                    details={
                        "timeout_seconds": PPTX_ARTIFACT_PROBE_TIMEOUT_SECONDS
                    },
                ) from exc
            except OSError as exc:
                raise _probe_failure(
                    "pptx_probe_start_failure",
                    details={"exception_type": type(exc).__name__},
                ) from exc
            if completed.returncode != 0:
                if completed.returncode < 0:
                    signal_number = -completed.returncode
                    details: dict[str, object] = {
                        "termination": "signal",
                        "signal_number": signal_number,
                        "signal_name": _signal_name(signal_number),
                    }
                else:
                    details = {
                        "termination": "exit",
                        "exit_code": completed.returncode,
                    }
                raise _probe_failure("pptx_probe_crash", details=details)
            try:
                result_file.seek(0)
                raw = result_file.read(PPTX_ARTIFACT_PROBE_MAX_RESULT_BYTES + 1)
            except OSError as exc:
                raise _probe_failure("pptx_probe_malformed_result") from exc
            return decoder(raw)


def _confirm_archive_integrity_failure(
    artifact: Path,
    key: tuple[str, int, int, int, int, int, int],
    first_error: PptxEvidenceError,
    *,
    child_flag: str,
    decoder: Callable[[bytes], Any],
) -> None:
    """Require two identical bounded failures before treating damage as stable."""
    try:
        _run_bounded_private_worker(
            artifact,
            child_flag=child_flag,
            decoder=decoder,
        )
    except PptxEvidenceError as confirmation_error:
        _confirmed_path, confirmed_key = _probe_file_identity(artifact)
        if confirmed_key != key:
            raise _probe_failure("pptx_artifact_changed") from confirmation_error
        if (
            confirmation_error.reason_code == first_error.reason_code
            and confirmation_error.details == first_error.details
        ):
            return
        raise _probe_failure(
            "pptx_probe_materialization_changed"
        ) from confirmation_error
    raise _probe_failure("pptx_probe_materialization_changed") from first_error


def _run_bounded_pptx_probe(path: Path) -> PptxArtifactProbe:
    """Probe one deck in an output-silent, time-bounded worker."""
    result = _run_bounded_private_worker(
        path,
        child_flag=PPTX_ARTIFACT_PROBE_CHILD_FLAG,
        decoder=_decode_pptx_probe_result,
    )
    if not isinstance(result, PptxArtifactProbe):
        raise _probe_failure("pptx_probe_malformed_result")
    return result


def _probe_file_identity(
    path: str | Path,
) -> tuple[Path, tuple[str, int, int, int, int, int, int]]:
    artifact = Path(path)
    try:
        initial = artifact.lstat()
    except OSError as exc:
        raise _probe_failure(
            "pptx_artifact_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    if stat_module.S_ISLNK(initial.st_mode) or not stat_module.S_ISREG(
        initial.st_mode
    ):
        raise _probe_failure("pptx_artifact_unavailable")
    canonical = artifact.resolve(strict=False)
    generation = _file_generation(initial)
    return canonical, (os.fspath(canonical), *generation)


def _copy_probe(probe: PptxArtifactProbe) -> PptxArtifactProbe:
    return PptxArtifactProbe(
        slide_count=probe.slide_count,
        source_sha256=probe.source_sha256,
        source_size_bytes=probe.source_size_bytes,
        archive_recovery=tuple(dict(item) for item in probe.archive_recovery),
    )


def _cache_probe_result(
    key: tuple[str, int, int, int, int, int, int],
    value: PptxArtifactProbe | tuple[str, str, dict[str, object]],
) -> None:
    for stale_key in [candidate for candidate in _PPTX_ARTIFACT_PROBE_CACHE if candidate[0] == key[0] and candidate != key]:
        _PPTX_ARTIFACT_PROBE_CACHE.pop(stale_key, None)
    _PPTX_ARTIFACT_PROBE_CACHE[key] = value


def clear_pptx_artifact_probe_cache() -> None:
    """Clear process-local probe memoization for tests and explicit refreshes."""
    _PPTX_ARTIFACT_PROBE_CACHE.clear()
    _PPTX_NATIVE_AUDIT_CACHE.clear()


def probe_pptx_artifact(path: str | Path) -> PptxArtifactProbe:
    """Return exact deck evidence through a bounded, generation-cached worker."""
    artifact, key = _probe_file_identity(path)
    cached = _PPTX_ARTIFACT_PROBE_CACHE.get(key)
    if isinstance(cached, PptxArtifactProbe):
        return _copy_probe(cached)
    if isinstance(cached, tuple):
        message, reason_code, details = cached
        raise PptxEvidenceError(
            message,
            reason_code=reason_code,
            details=details,
        )
    dataless_flag = PPTX_MACOS_DATALESS_FLAG
    if dataless_flag and key[-1] & dataless_flag:
        error = _probe_failure(
            "pptx_cloud_placeholder_unavailable",
            details={"st_flags": key[-1]},
        )
        cached_error = (str(error), error.reason_code, dict(error.details))
        _cache_probe_result(key, cached_error)
        raise error
    try:
        probe = _run_bounded_pptx_probe(artifact)
    except PptxEvidenceError as exc:
        try:
            _current_path, current_key = _probe_file_identity(artifact)
        except PptxEvidenceError:
            raise _probe_failure("pptx_artifact_changed") from exc
        if current_key != key:
            raise _probe_failure("pptx_artifact_changed") from exc
        if exc.reason_code in {
            "pptx_artifact_changed",
            "pptx_probe_materialization_changed",
        }:
            raise _probe_failure("pptx_probe_materialization_changed") from exc
        if exc.reason_code in _ARCHIVE_INTEGRITY_CONFIRMATION_REASON_CODES:
            _confirm_archive_integrity_failure(
                artifact,
                key,
                exc,
                child_flag=PPTX_ARTIFACT_PROBE_CHILD_FLAG,
                decoder=_decode_pptx_probe_result,
            )
        cached_error = (str(exc), exc.reason_code, dict(exc.details))
        _cache_probe_result(key, cached_error)
        raise PptxEvidenceError(
            cached_error[0],
            reason_code=cached_error[1],
            details=cached_error[2],
        ) from exc
    _between_path, between_key = _probe_file_identity(artifact)
    if between_key != key:
        raise _probe_failure("pptx_artifact_changed")
    if probe.archive_recovery:
        try:
            confirmation = _run_bounded_pptx_probe(artifact)
        except PptxEvidenceError as exc:
            raise _probe_failure("pptx_probe_materialization_changed") from exc
        _confirmed_path, confirmed_key = _probe_file_identity(artifact)
        if confirmed_key != key:
            raise _probe_failure("pptx_artifact_changed")
        if confirmation != probe:
            raise _probe_failure("pptx_probe_materialization_changed")
    _current_path, current_key = _probe_file_identity(artifact)
    if current_key != key or probe.source_size_bytes != key[3]:
        raise _probe_failure("pptx_artifact_changed")
    cached_probe = _copy_probe(probe)
    _cache_probe_result(key, cached_probe)
    return _copy_probe(cached_probe)


def normalize_page_ranges(
    ranges: object,
    *,
    page_count: int,
    allow_empty: bool,
    label: str = "inspected_page_ranges",
) -> list[list[int]]:
    """Validate inclusive page ranges and return a normalized copy."""
    if not isinstance(ranges, list) or (not ranges and not allow_empty):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise PptxEvidenceError(f"{label} must be {qualifier}")
    normalized: list[list[int]] = []
    prior_end = 0
    for index, raw_range in enumerate(ranges):
        range_label = f"{label}[{index}]"
        if not isinstance(raw_range, list) or len(raw_range) != 2:
            raise PptxEvidenceError(
                f"{range_label} must be a two-item [start, end] array"
            )
        start, end = raw_range
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 1
            or end < start
            or end > page_count
            or start <= prior_end
        ):
            raise PptxEvidenceError(
                f"{range_label} must be ascending, non-overlapping, and inside "
                f"the verified 1..{page_count} page bound"
            )
        normalized.append([start, end])
        prior_end = end
    return normalized


def pages_covered(ranges: list[list[int]]) -> set[int]:
    return {page for start, end in ranges for page in range(start, end + 1)}


def _normalize_required_slides(value: object, *, slide_count: int) -> list[int]:
    if not isinstance(value, list):
        raise PptxEvidenceError("render_required_slide_numbers must be an array")
    if any(
        isinstance(number, bool)
        or not isinstance(number, int)
        or number < 1
        or number > slide_count
        for number in value
    ):
        raise PptxEvidenceError(
            "render_required_slide_numbers must contain integers inside the "
            f"verified 1..{slide_count} slide bound"
        )
    if value != sorted(set(value)):
        raise PptxEvidenceError(
            "render_required_slide_numbers must be sorted and duplicate-free"
        )
    return list(value)


def build_native_deck_audit(
    *,
    source_pptx_sha256: str,
    source_pptx_size_bytes: int,
    slide_count: int,
    render_required_reasons: Mapping[int, list[str]],
    rendered_page_inspection: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the deterministic native-deck audit emitted by the extractor."""
    _require_sha256(source_pptx_sha256, "source_pptx_sha256")
    if (
        isinstance(source_pptx_size_bytes, bool)
        or not isinstance(source_pptx_size_bytes, int)
        or source_pptx_size_bytes < 1
    ):
        raise PptxEvidenceError("source_pptx_size_bytes must be positive")
    if (
        isinstance(slide_count, bool)
        or not isinstance(slide_count, int)
        or slide_count < 1
    ):
        raise PptxEvidenceError("slide_count must be positive")
    normalized_reasons: dict[str, list[str]] = {}
    for slide_number in sorted(render_required_reasons):
        reasons = render_required_reasons[slide_number]
        if (
            isinstance(slide_number, bool)
            or not isinstance(slide_number, int)
            or slide_number < 1
            or slide_number > slide_count
            or not isinstance(reasons, list)
            or not reasons
            or any(not isinstance(reason, str) or not reason for reason in reasons)
            or reasons != sorted(set(reasons))
        ):
            raise PptxEvidenceError(
                "render_required_reasons must map valid slide numbers to sorted, "
                "duplicate-free non-empty reason arrays"
            )
        normalized_reasons[str(slide_number)] = list(reasons)
    required = [int(number) for number in normalized_reasons]
    identity: dict[str, object] = {
        "schema_version": NATIVE_DECK_AUDIT_SCHEMA_VERSION,
        "extraction_schema_version": PPTX_EXTRACTION_SCHEMA_VERSION,
        "extraction_pipeline_version": PPTX_EXTRACTION_PIPELINE_VERSION,
        "source_pptx_sha256": source_pptx_sha256,
        "source_pptx_size_bytes": source_pptx_size_bytes,
        "slide_count": slide_count,
        "render_required_slide_numbers": required,
        "render_required_reasons": normalized_reasons,
    }
    return {
        **identity,
        "extraction_receipt_sha256": _canonical_sha256(identity),
        "rendered_page_inspection": (
            dict(rendered_page_inspection)
            if rendered_page_inspection is not None
            else None
        ),
    }


def _pdf_page_count(path: Path) -> int:
    pdf_read_error: type[Exception] = ValueError
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError as ImportedPdfReadError

        pdf_read_error = ImportedPdfReadError

        count = len(PdfReader(os.fspath(path), strict=True).pages)
    except ImportError as exc:
        raise PptxEvidenceError(
            "render receipt validation requires the declared pypdf dependency; "
            "install the speaker-toolkit project dependencies"
        ) from exc
    except (pdf_read_error, OSError, ValueError, KeyError, EOFError) as exc:
        raise PptxEvidenceError(
            f"rendered PDF is unreadable at {path}: {type(exc).__name__}"
        ) from exc
    if count < 1:
        raise PptxEvidenceError(f"rendered PDF has no pages at {path}")
    return count


def snapshot_rendered_pdf(path: str | Path) -> tuple[str, int, int]:
    """Copy, hash, and page-count one exact rendered-PDF generation."""
    artifact = Path(path)
    try:
        initial = artifact.lstat()
    except OSError as exc:
        raise PptxEvidenceError(
            f"rendered PDF is unavailable at {artifact}: {exc}"
        ) from exc
    if stat_module.S_ISLNK(initial.st_mode) or not stat_module.S_ISREG(
        initial.st_mode
    ):
        raise PptxEvidenceError(
            f"rendered PDF must be a non-symlink regular file: {artifact}"
        )
    generation = _file_generation(initial)
    digest = hashlib.sha256()
    copied_size = 0
    with tempfile.TemporaryDirectory(prefix="speaker-toolkit-render-") as temp_dir:
        snapshot = Path(temp_dir) / "rendered.pdf"
        try:
            with artifact.open("rb") as source, snapshot.open("xb") as target:
                opened = os.fstat(source.fileno())
                if _file_generation(opened) != generation:
                    raise PptxEvidenceError(
                        f"rendered PDF changed while opening: {artifact}"
                    )
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    target.write(chunk)
                    copied_size += len(chunk)
                after_read = os.fstat(source.fileno())
        except PptxEvidenceError:
            raise
        except OSError as exc:
            raise PptxEvidenceError(
                f"cannot snapshot rendered PDF at {artifact}: {exc}"
            ) from exc
        try:
            current = artifact.lstat()
        except OSError as exc:
            raise PptxEvidenceError(
                f"rendered PDF changed while it was read at {artifact}: {exc}"
            ) from exc
        if (
            _file_generation(after_read) != generation
            or _file_generation(current) != generation
            or copied_size != initial.st_size
        ):
            raise PptxEvidenceError(
                f"rendered PDF changed while reading: {artifact}"
            )
        page_count = _pdf_page_count(snapshot)
    return digest.hexdigest(), copied_size, page_count


def build_rendered_page_inspection(
    *,
    source_pptx_sha256: str,
    rendered_pdf_path: str | Path,
    inspected_page_ranges: object,
    required_slide_numbers: list[int],
    slide_count: int,
) -> dict[str, object]:
    """Bind asserted page inspection to exact PPTX and rendered-PDF identities."""
    _require_sha256(source_pptx_sha256, "source_pptx_sha256")
    if (
        isinstance(slide_count, bool)
        or not isinstance(slide_count, int)
        or slide_count < 1
    ):
        raise PptxEvidenceError("slide_count must be a positive integer")
    required = _normalize_required_slides(
        required_slide_numbers, slide_count=slide_count
    )
    pdf_sha256, pdf_size, page_count = snapshot_rendered_pdf(
        Path(rendered_pdf_path)
    )
    if page_count != slide_count:
        raise PptxEvidenceError(
            "rendered PDF page count must equal the source deck slide count; "
            f"expected {slide_count}, got {page_count}"
        )
    ranges = normalize_page_ranges(
        inspected_page_ranges,
        page_count=page_count,
        allow_empty=True,
    )
    covered = pages_covered(ranges)
    inspected_required = [number for number in required if number in covered]
    identity: dict[str, object] = {
        "schema_version": RENDER_INSPECTION_SCHEMA_VERSION,
        "source_pptx_sha256": source_pptx_sha256,
        "rendered_pdf_sha256": pdf_sha256,
        "rendered_pdf_size_bytes": pdf_size,
        "rendered_page_count": page_count,
        "inspected_page_ranges": ranges,
        "inspected_required_slide_numbers": inspected_required,
        "complete": inspected_required == required,
    }
    return {**identity, "binding_sha256": _canonical_sha256(identity)}


def validate_native_deck_audit(
    value: object,
    *,
    slide_count: int | None = None,
) -> dict[str, object]:
    """Validate a closed native-deck audit and its optional render receipt."""
    if not isinstance(value, Mapping):
        raise PptxEvidenceError("native_deck_audit must be an object")
    unknown = sorted(set(value) - _AUDIT_FIELDS)
    missing = sorted(_AUDIT_FIELDS - set(value))
    if unknown or missing:
        raise PptxEvidenceError(
            "native_deck_audit must contain exactly the schema fields; "
            f"missing={missing}, unknown={unknown}"
        )
    if value.get("schema_version") != NATIVE_DECK_AUDIT_SCHEMA_VERSION:
        raise PptxEvidenceError(
            "native_deck_audit.schema_version must be "
            f"{NATIVE_DECK_AUDIT_SCHEMA_VERSION}"
        )
    if value.get("extraction_schema_version") != PPTX_EXTRACTION_SCHEMA_VERSION:
        raise PptxEvidenceError(
            "native_deck_audit.extraction_schema_version must match the current "
            f"extractor schema {PPTX_EXTRACTION_SCHEMA_VERSION}"
        )
    if value.get("extraction_pipeline_version") != PPTX_EXTRACTION_PIPELINE_VERSION:
        raise PptxEvidenceError(
            "native_deck_audit.extraction_pipeline_version must match the current "
            f"extractor pipeline {PPTX_EXTRACTION_PIPELINE_VERSION}"
        )
    source_sha = _require_sha256(
        value.get("source_pptx_sha256"),
        "native_deck_audit.source_pptx_sha256",
    )
    size = value.get("source_pptx_size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise PptxEvidenceError(
            "native_deck_audit.source_pptx_size_bytes must be a positive integer"
        )
    recorded_slide_count = value.get("slide_count")
    if (
        isinstance(recorded_slide_count, bool)
        or not isinstance(recorded_slide_count, int)
        or recorded_slide_count < 1
    ):
        raise PptxEvidenceError(
            "native_deck_audit.slide_count must be a positive integer"
        )
    if slide_count is not None and recorded_slide_count != slide_count:
        raise PptxEvidenceError(
            "native_deck_audit.slide_count must equal structured_data.slide_count"
        )
    required = _normalize_required_slides(
        value.get("render_required_slide_numbers"),
        slide_count=recorded_slide_count,
    )
    reasons = value.get("render_required_reasons")
    if not isinstance(reasons, Mapping):
        raise PptxEvidenceError(
            "native_deck_audit.render_required_reasons must be an object"
        )
    normalized_reasons: dict[str, list[str]] = {}
    for raw_slide, raw_reasons in reasons.items():
        if not isinstance(raw_slide, str) or not raw_slide.isdigit():
            raise PptxEvidenceError(
                "native_deck_audit.render_required_reasons keys must be decimal "
                "slide-number strings"
            )
        slide_number = int(raw_slide)
        if slide_number not in required:
            raise PptxEvidenceError(
                "native_deck_audit.render_required_reasons keys must exactly "
                "match render_required_slide_numbers"
            )
        if (
            not isinstance(raw_reasons, list)
            or not raw_reasons
            or any(not isinstance(reason, str) or not reason for reason in raw_reasons)
            or raw_reasons != sorted(set(raw_reasons))
        ):
            raise PptxEvidenceError(
                "native_deck_audit.render_required_reasons values must be sorted, "
                "duplicate-free non-empty string arrays"
            )
        normalized_reasons[raw_slide] = list(raw_reasons)
    if sorted(int(number) for number in normalized_reasons) != required:
        raise PptxEvidenceError(
            "native_deck_audit.render_required_reasons keys must exactly match "
            "render_required_slide_numbers"
        )
    identity: dict[str, object] = {
        "schema_version": NATIVE_DECK_AUDIT_SCHEMA_VERSION,
        "extraction_schema_version": PPTX_EXTRACTION_SCHEMA_VERSION,
        "extraction_pipeline_version": PPTX_EXTRACTION_PIPELINE_VERSION,
        "source_pptx_sha256": source_sha,
        "source_pptx_size_bytes": size,
        "slide_count": recorded_slide_count,
        "render_required_slide_numbers": required,
        "render_required_reasons": normalized_reasons,
    }
    if value.get("extraction_receipt_sha256") != _canonical_sha256(identity):
        raise PptxEvidenceError(
            "native_deck_audit.extraction_receipt_sha256 does not bind the "
            "declared extraction identity and render requirements"
        )
    raw_receipt = value.get("rendered_page_inspection")
    receipt = (
        validate_rendered_page_inspection(
            raw_receipt,
            required_slide_numbers=required,
            slide_count=recorded_slide_count,
        )
        if raw_receipt is not None
        else None
    )
    if receipt is not None and receipt["source_pptx_sha256"] != source_sha:
        raise PptxEvidenceError(
            "rendered_page_inspection.source_pptx_sha256 must match the "
            "native-deck audit source identity"
        )
    return {
        **identity,
        "extraction_receipt_sha256": value["extraction_receipt_sha256"],
        "rendered_page_inspection": receipt,
    }


def validate_rendered_page_inspection(
    value: object,
    *,
    required_slide_numbers: list[int],
    slide_count: int,
) -> dict[str, object]:
    """Validate a closed rendered-page receipt and recompute its binding."""
    if not isinstance(value, Mapping):
        raise PptxEvidenceError("rendered_page_inspection must be an object")
    unknown = sorted(set(value) - _RENDER_RECEIPT_FIELDS)
    missing = sorted(_RENDER_RECEIPT_FIELDS - set(value))
    if unknown or missing:
        raise PptxEvidenceError(
            "rendered_page_inspection must contain exactly the schema fields; "
            f"missing={missing}, unknown={unknown}"
        )
    if value.get("schema_version") != RENDER_INSPECTION_SCHEMA_VERSION:
        raise PptxEvidenceError(
            "rendered_page_inspection.schema_version must be "
            f"{RENDER_INSPECTION_SCHEMA_VERSION}"
        )
    source_sha = _require_sha256(
        value.get("source_pptx_sha256"),
        "rendered_page_inspection.source_pptx_sha256",
    )
    pdf_sha = _require_sha256(
        value.get("rendered_pdf_sha256"),
        "rendered_page_inspection.rendered_pdf_sha256",
    )
    pdf_size = value.get("rendered_pdf_size_bytes")
    page_count = value.get("rendered_page_count")
    if isinstance(pdf_size, bool) or not isinstance(pdf_size, int) or pdf_size < 1:
        raise PptxEvidenceError(
            "rendered_page_inspection.rendered_pdf_size_bytes must be positive"
        )
    if (
        isinstance(page_count, bool)
        or not isinstance(page_count, int)
        or page_count != slide_count
    ):
        raise PptxEvidenceError(
            "rendered_page_inspection.rendered_page_count must equal the source "
            f"deck slide count {slide_count}"
        )
    ranges = normalize_page_ranges(
        value.get("inspected_page_ranges"),
        page_count=page_count,
        allow_empty=True,
    )
    required = _normalize_required_slides(
        required_slide_numbers, slide_count=slide_count
    )
    inspected_required = [
        number for number in required if number in pages_covered(ranges)
    ]
    if value.get("inspected_required_slide_numbers") != inspected_required:
        raise PptxEvidenceError(
            "rendered_page_inspection.inspected_required_slide_numbers must be "
            "derived from inspected_page_ranges"
        )
    complete = inspected_required == required
    if value.get("complete") is not complete:
        raise PptxEvidenceError(
            "rendered_page_inspection.complete must reflect coverage of every "
            "render-required slide"
        )
    identity: dict[str, object] = {
        "schema_version": RENDER_INSPECTION_SCHEMA_VERSION,
        "source_pptx_sha256": source_sha,
        "rendered_pdf_sha256": pdf_sha,
        "rendered_pdf_size_bytes": pdf_size,
        "rendered_page_count": page_count,
        "inspected_page_ranges": ranges,
        "inspected_required_slide_numbers": inspected_required,
        "complete": complete,
    }
    if value.get("binding_sha256") != _canonical_sha256(identity):
        raise PptxEvidenceError(
            "rendered_page_inspection.binding_sha256 does not bind the exact "
            "source, render, and inspected ranges"
        )
    return {**identity, "binding_sha256": value["binding_sha256"]}


def _extract_native_deck_audit_in_process(path: Path) -> dict[str, object]:
    """Recompute one audit inside the bounded native-audit worker."""
    sys.modules.setdefault("pptx_evidence", sys.modules[__name__])
    extractor_path = Path(__file__).with_name("pptx-extraction.py")
    spec = importlib.util.spec_from_file_location(
        "_speaker_toolkit_bounded_pptx_extraction",
        extractor_path,
    )
    if spec is None or spec.loader is None:
        raise PptxEvidenceError(
            "cannot load the current PPTX extractor",
            reason_code="pptx_dependency_unavailable",
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    extract = getattr(module, "extract_pptx", None)
    if not callable(extract):
        raise PptxEvidenceError(
            "current PPTX extractor has no extraction entrypoint",
            reason_code="pptx_dependency_unavailable",
        )
    payload = extract(path, ocr=False)
    if not isinstance(payload, Mapping):
        raise PptxEvidenceError(
            "current PPTX extractor returned a non-object",
            reason_code="pptx_evidence_invalid",
        )
    raw_recovery = payload.get("archive_recovery")
    if isinstance(raw_recovery, list) and raw_recovery:
        part_names = sorted(
            str(item.get("part_name", "<unknown>"))
            for item in raw_recovery
            if isinstance(item, Mapping)
        )
        raise PptxEvidenceError(
            "PPTX extraction required placeholder archive recovery",
            reason_code="pptx_archive_recovery_required",
            details={"part_names": part_names},
        )
    return validate_native_deck_audit(payload.get("native_deck_audit"))


def _native_audit_child(path: str | Path) -> dict[str, object]:
    """Return a closed native-audit payload from the isolated worker."""
    try:
        audit = _extract_native_deck_audit_in_process(Path(path))
    except MemoryError:
        return {
            "schema_version": PPTX_ARTIFACT_PROBE_SCHEMA_VERSION,
            "status": "unavailable",
            "reason_code": "pptx_probe_resource_unavailable",
            "details": {},
        }
    except PptxEvidenceError as exc:
        reason_code = (
            exc.reason_code
            if exc.reason_code in _CHILD_PROBE_REASON_CODES
            else "pptx_evidence_invalid"
        )
        return {
            "schema_version": PPTX_ARTIFACT_PROBE_SCHEMA_VERSION,
            "status": "unavailable",
            "reason_code": reason_code,
            "details": _probe_child_failure_details(exc),
        }
    return {
        "schema_version": PPTX_ARTIFACT_PROBE_SCHEMA_VERSION,
        "status": "available",
        "native_deck_audit": audit,
    }


def _decode_native_audit_result(raw: bytes) -> dict[str, object]:
    if len(raw) > PPTX_ARTIFACT_PROBE_MAX_RESULT_BYTES or not raw.strip():
        raise _probe_failure("pptx_probe_malformed_result")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _probe_failure("pptx_probe_malformed_result") from exc
    if len(decoded.splitlines()) != 1:
        raise _probe_failure("pptx_probe_malformed_result")
    try:
        payload = json.loads(
            decoded,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise _probe_failure("pptx_probe_malformed_result") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != PPTX_ARTIFACT_PROBE_SCHEMA_VERSION
    ):
        raise _probe_failure("pptx_probe_malformed_result")
    if payload.get("status") == "unavailable":
        if set(payload) != {"schema_version", "status", "reason_code", "details"}:
            raise _probe_failure("pptx_probe_malformed_result")
        reason_code = payload.get("reason_code")
        details = payload.get("details")
        if reason_code not in _CHILD_PROBE_REASON_CODES or not isinstance(details, dict):
            raise _probe_failure("pptx_probe_malformed_result")
        if set(details) - {"part_names", "exception_type"}:
            raise _probe_failure("pptx_probe_malformed_result")
        part_names = details.get("part_names")
        if part_names is not None and (
            not isinstance(part_names, list)
            or len(part_names) > 64
            or any(
                not isinstance(name, str) or not name or len(name) > 2048
                for name in part_names
            )
        ):
            raise _probe_failure("pptx_probe_malformed_result")
        exception_type = details.get("exception_type")
        if exception_type is not None and (
            not isinstance(exception_type, str)
            or not exception_type
            or len(exception_type) > 128
        ):
            raise _probe_failure("pptx_probe_malformed_result")
        raise _probe_failure(str(reason_code), details=details)
    if set(payload) != {"schema_version", "status", "native_deck_audit"} or payload.get(
        "status"
    ) != "available":
        raise _probe_failure("pptx_probe_malformed_result")
    try:
        return validate_native_deck_audit(payload.get("native_deck_audit"))
    except PptxEvidenceError as exc:
        raise _probe_failure("pptx_probe_malformed_result") from exc


def _cache_native_audit(
    key: tuple[str, int, int, int, int, int, int],
    value: dict[str, object] | tuple[str, str, dict[str, object]],
) -> None:
    stale = [
        candidate
        for candidate in _PPTX_NATIVE_AUDIT_CACHE
        if candidate[0] == key[0] and candidate != key
    ]
    for stale_key in stale:
        _PPTX_NATIVE_AUDIT_CACHE.pop(stale_key, None)
    _PPTX_NATIVE_AUDIT_CACHE[key] = value


def recompute_native_deck_audit(path: str | Path) -> dict[str, object]:
    """Recompute an exact audit through a bounded, generation-cached worker."""
    artifact, key = _probe_file_identity(path)
    cached = _PPTX_NATIVE_AUDIT_CACHE.get(key)
    if isinstance(cached, dict):
        return copy.deepcopy(cached)
    if isinstance(cached, tuple):
        message, reason_code, details = cached
        raise PptxEvidenceError(
            message,
            reason_code=reason_code,
            details=details,
        )
    dataless_flag = PPTX_MACOS_DATALESS_FLAG
    if dataless_flag and key[-1] & dataless_flag:
        error = _probe_failure(
            "pptx_cloud_placeholder_unavailable",
            details={"st_flags": key[-1]},
        )
        _cache_native_audit(
            key,
            (str(error), error.reason_code, dict(error.details)),
        )
        raise error
    try:
        result = _run_bounded_private_worker(
            artifact,
            child_flag=PPTX_NATIVE_AUDIT_CHILD_FLAG,
            decoder=_decode_native_audit_result,
        )
    except PptxEvidenceError as exc:
        _current_path, current_key = _probe_file_identity(artifact)
        if current_key != key:
            raise _probe_failure("pptx_artifact_changed") from exc
        if exc.reason_code in {
            "pptx_artifact_changed",
            "pptx_probe_materialization_changed",
        }:
            raise _probe_failure("pptx_probe_materialization_changed") from exc
        if exc.reason_code in _ARCHIVE_INTEGRITY_CONFIRMATION_REASON_CODES:
            _confirm_archive_integrity_failure(
                artifact,
                key,
                exc,
                child_flag=PPTX_NATIVE_AUDIT_CHILD_FLAG,
                decoder=_decode_native_audit_result,
            )
        cached_error = (str(exc), exc.reason_code, dict(exc.details))
        _cache_native_audit(key, cached_error)
        raise PptxEvidenceError(
            cached_error[0],
            reason_code=cached_error[1],
            details=cached_error[2],
        ) from exc
    if not isinstance(result, dict):
        raise _probe_failure("pptx_probe_malformed_result")
    _current_path, current_key = _probe_file_identity(artifact)
    if current_key != key or result.get("source_pptx_size_bytes") != key[3]:
        raise _probe_failure("pptx_artifact_changed")
    cached_result = copy.deepcopy(result)
    _cache_native_audit(key, cached_result)
    return copy.deepcopy(cached_result)


def parse_page_range_arguments(values: list[str] | None) -> list[list[int]]:
    """Parse repeated CLI PAGE or START-END values."""
    if not values:
        return []
    parsed: list[list[int]] = []
    for value in values:
        for token in value.split(","):
            candidate = token.strip()
            match = re.fullmatch(r"(\d+)(?:-(\d+))?", candidate)
            if match is None:
                raise PptxEvidenceError(
                    "--inspected-pages values must be PAGE or START-END, "
                    f"got {candidate!r}"
                )
            start = int(match.group(1))
            end = int(match.group(2) or match.group(1))
            parsed.append([start, end])
    return parsed


def ranges_cover_pages(ranges: object, pages: list[int], *, page_count: int) -> bool:
    normalized = normalize_page_ranges(
        ranges, page_count=page_count, allow_empty=True
    )
    return set(pages).issubset(pages_covered(normalized))


def finite_confidence(value: object) -> float | None:
    """Normalize an OCR confidence to a finite 0..100 float or ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0 or numeric > 100:
        return None
    return round(numeric, 3)


if __name__ == "__main__":
    child_mode = (
        sys.argv[1]
        if len(sys.argv) == 4
        and sys.argv[1]
        in {PPTX_ARTIFACT_PROBE_CHILD_FLAG, PPTX_NATIVE_AUDIT_CHILD_FLAG}
        else None
    )
    if child_mode is not None:
        with Path(sys.argv[3]).open("r+b", buffering=0) as child_result_file:
            with (
                open(os.devnull, "w", encoding="utf-8") as child_output,
                contextlib.redirect_stdout(child_output),
                contextlib.redirect_stderr(child_output),
            ):
                try:
                    child_result = (
                        _pptx_probe_child(sys.argv[2])
                        if child_mode == PPTX_ARTIFACT_PROBE_CHILD_FLAG
                        else _native_audit_child(sys.argv[2])
                    )
                # The parent classifies only a closed private result; collapse an
                # unexpected worker fault without exposing parser output.
                except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
                    child_result = {
                        "schema_version": PPTX_ARTIFACT_PROBE_SCHEMA_VERSION,
                        "status": "unavailable",
                        "reason_code": "pptx_probe_exception",
                        "details": {"exception_type": type(exc).__name__},
                    }
            _write_pptx_probe_result(child_result_file, child_result)
        raise SystemExit(0)
    raise SystemExit("pptx_evidence.py is a library; run pptx-extraction.py")

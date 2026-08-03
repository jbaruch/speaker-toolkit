#!/usr/bin/env python3
"""Bounded, exact-generation evidence for untrusted PDF artifacts."""

from __future__ import annotations

import copy
import contextlib
import hashlib
import logging
import math
import os
import re
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, cast

from artifact_metadata import (
    ArtifactAvailability,
    ArtifactMetadataMalformed,
    ArtifactMetadataReceipt,
    ArtifactMetadataUnavailable,
    MACOS_DATALESS_FLAG,
    METADATA_SCHEMA_VERSION,
    WINDOWS_CLOUD_REPARSE_TAGS,
    WINDOWS_REPARSE_POINT_ATTRIBUTE,
    WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES,
    canonicalize_trusted_artifact_locator,
    decode_artifact_metadata_payload,
    inspect_metadata_generation,
)
from artifact_supervisor import (
    DiagnosticReceipt,
    FileGeneration,
    JsonValue,
    SupervisorError,
    SupervisorLimits,
    WorkerRequest,
    WorkerResult,
    _PipeDrainer,
    isolate_protocol_output,
    read_worker_request,
    run_authenticated_worker,
    write_worker_response,
)


PDF_PROBE_SCHEMA_VERSION: Final = 1
PDF_PROBE_PIPELINE_VERSION: Final = "1.0.0"
PDF_SUPERVISED_WORKER_FLAG: Final = "--supervised-worker"
PDF_METADATA_OPERATION: Final = "pdf_metadata"
PDF_PROBE_OPERATION: Final = "pdf_probe"
PDF_MAX_PAGES: Final = 65_536
# The largest live vault PDF measured for this policy was 181,053,403 bytes.
# 512 MiB preserves substantial headroom while keeping every artifact bounded.
PDF_MAX_INPUT_BYTES: Final = 512 * 1024 * 1024
PDF_COPY_CHUNK_BYTES: Final = 1024 * 1024
_PROCESS_STDOUT_DESCRIPTOR: Final = 1
_PROCESS_STDERR_DESCRIPTOR: Final = 2
PDF_MACOS_DATALESS_FLAG: Final = MACOS_DATALESS_FLAG
PDF_WINDOWS_CLOUD_FILE_ATTRIBUTES: Final = WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES
PDF_WINDOWS_REPARSE_POINT_ATTRIBUTE: Final = WINDOWS_REPARSE_POINT_ATTRIBUTE
PDF_WINDOWS_CLOUD_REPARSE_TAGS: Final = WINDOWS_CLOUD_REPARSE_TAGS
_PDF_GENERATION_NAMES: Final = frozenset({"pdf", "pdf_root"})

PDF_METADATA_LIMITS = SupervisorLimits(
    profile_id="pdf-metadata-v1",
    wall_seconds=15,
    max_memory_bytes=256 * 1024 * 1024,
    max_input_bytes=64 * 1024,
    max_output_bytes=64 * 1024,
    max_diagnostic_bytes=64 * 1024,
    max_processes=1,
)
PDF_PROBE_LIMITS = SupervisorLimits(
    profile_id="pdf-probe-v1",
    wall_seconds=180,
    max_memory_bytes=2 * 1024 * 1024 * 1024,
    max_input_bytes=64 * 1024,
    max_output_bytes=64 * 1024,
    max_diagnostic_bytes=64 * 1024,
    max_processes=1,
)

_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_EXCEPTION_TYPE_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_CAPTURE_FAILURE_KINDS: Final = frozenset(
    {"diagnostic_drain_failed", "diagnostic_drain_timeout"}
)
_CHILD_FAILURE_REASONS: Final = frozenset(
    {
        "pdf_artifact_unavailable",
        "pdf_dependency_unavailable",
        "pdf_invalid_container",
        "pdf_no_pages",
        "pdf_page_limit",
        "pdf_parser_rejected",
        "pdf_probe_resource_unavailable",
    }
)
_CHILD_FAILURE_DETAIL_KEYS: Final = {
    "pdf_artifact_unavailable": frozenset({"exception_type"}),
    "pdf_dependency_unavailable": frozenset({"exception_type"}),
    "pdf_invalid_container": frozenset(),
    "pdf_no_pages": frozenset(),
    "pdf_page_limit": frozenset({"max_pages"}),
    "pdf_parser_rejected": frozenset({"exception_type"}),
    "pdf_probe_resource_unavailable": frozenset({"exception_type", "limit_bytes"}),
}
_STABLE_ARTIFACT_FAILURES: Final = frozenset(
    {
        "pdf_cloud_placeholder_unavailable",
        "pdf_invalid_container",
        "pdf_no_pages",
        "pdf_page_limit",
        "pdf_parser_rejected",
        "pdf_parser_repair_required",
    }
)
_CONFIRMED_ARTIFACT_FAILURES: Final = frozenset(
    {
        "pdf_invalid_container",
        "pdf_no_pages",
        "pdf_page_limit",
        "pdf_parser_rejected",
        "pdf_parser_repair_required",
    }
)


class PdfEvidenceError(ValueError):
    """A PDF artifact or its evidence violates the closed probe contract."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "pdf_evidence_invalid",
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = dict(details or {})


@dataclass(frozen=True)
class PdfArtifactProbe:
    """Closed evidence for one exact readable PDF generation."""

    generation: FileGeneration
    root_generation: FileGeneration | None
    availability: ArtifactAvailability
    page_count: int
    source_sha256: str
    source_size_bytes: int
    parser_diagnostics: DiagnosticReceipt


@dataclass(frozen=True)
class _PdfCacheKey:
    artifact_path: str
    generation: FileGeneration
    trusted_root: str | None
    root_generation: FileGeneration | None
    reparse_tag: int | None
    availability_state: str
    macos_dataless: bool
    windows_offline: bool
    windows_recall_on_open: bool
    windows_recall_on_data_access: bool
    metadata_profile_id: str
    probe_profile_id: str
    schema_generation: int
    pipeline_generation: str
    max_input_bytes: int
    max_pages: int


@dataclass(frozen=True)
class _CachedFailure:
    message: str
    reason_code: str
    details: Mapping[str, object]


_PDF_ARTIFACT_PROBE_CACHE: dict[
    _PdfCacheKey,
    PdfArtifactProbe | _CachedFailure,
] = {}


def _failure(
    reason_code: str,
    *,
    details: Mapping[str, object] | None = None,
) -> PdfEvidenceError:
    messages = {
        "pdf_artifact_changed": "PDF artifact changed during bounded inspection",
        "pdf_artifact_too_large": "PDF artifact exceeds the input-size ceiling",
        "pdf_cloud_placeholder_unavailable": (
            "PDF artifact is an offline cloud placeholder; download it locally "
            "before using PDF evidence"
        ),
        "pdf_artifact_unavailable": "PDF artifact is unavailable",
        "pdf_batch_wall_limit": "PDF batch wall deadline expired",
        "pdf_dependency_unavailable": "PDF parser dependency is unavailable",
        "pdf_evidence_invalid": "PDF evidence request is invalid",
        "pdf_invalid_container": "PDF artifact is not a valid PDF container",
        "pdf_no_pages": "PDF artifact has no pages",
        "pdf_page_limit": "PDF artifact exceeds the page-count ceiling",
        "pdf_parser_rejected": "Strict PDF parsing rejected the artifact",
        "pdf_parser_repair_required": (
            "PDF parser emitted repair diagnostics; repair or re-export the PDF"
        ),
        "pdf_probe_materialization_changed": (
            "PDF artifact produced inconsistent bounded reads while materialization "
            "was changing; retry after the file is fully local"
        ),
        "pdf_probe_crash": "PDF artifact probe terminated inside its worker",
        "pdf_probe_malformed_result": (
            "PDF artifact probe returned an invalid authenticated result"
        ),
        "pdf_probe_resource_unavailable": (
            "PDF artifact exceeds the bounded probe resources"
        ),
        "pdf_probe_request_oversized": (
            "PDF worker request exceeded its authenticated protocol limit"
        ),
        "pdf_probe_result_oversized": "PDF artifact probe result exceeded its limit",
        "pdf_probe_start_failure": "Could not start the bounded PDF artifact probe",
        "pdf_probe_timeout": "PDF artifact probe exceeded its wall limit",
    }
    return PdfEvidenceError(
        messages.get(reason_code, "PDF artifact is unavailable"),
        reason_code=reason_code,
        details=details,
    )


def _lexical_absolute(value: str | os.PathLike[str]) -> Path:
    try:
        rendered = os.fspath(value)
    except TypeError as exc:
        raise _failure("pdf_evidence_invalid") from exc
    if not isinstance(rendered, str) or not rendered or "\x00" in rendered:
        raise _failure("pdf_evidence_invalid")
    return Path(os.path.abspath(rendered))


def _worker_bound_path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SupervisorError("invalid_worker_request")
    path = Path(value)
    if not path.is_absolute() or Path(os.path.abspath(value)) != path:
        raise SupervisorError("invalid_worker_request")
    return path


def _metadata_failure_payload(exc: ArtifactMetadataUnavailable) -> dict[str, object]:
    details: dict[str, object] = {"failure_kind": exc.failure_kind}
    if exc.exception_type is not None:
        details["exception_type"] = exc.exception_type
    return {
        "schema_version": METADATA_SCHEMA_VERSION,
        "status": "unavailable",
        "reason_code": "pdf_artifact_unavailable",
        "details": details,
    }


def _metadata_child(payload: Mapping[str, object]) -> dict[str, object]:
    if set(payload) != {"pdf_path", "trusted_root"}:
        raise SupervisorError("invalid_worker_request")
    artifact = _worker_bound_path(payload.get("pdf_path"))
    root_value = payload.get("trusted_root")
    if root_value is not None and not isinstance(root_value, str):
        raise SupervisorError("invalid_worker_request")
    trusted_root = _worker_bound_path(root_value) if root_value is not None else None
    try:
        receipt = inspect_metadata_generation(
            artifact,
            trusted_root=trusted_root,
            reparse_point_attribute=PDF_WINDOWS_REPARSE_POINT_ATTRIBUTE,
            cloud_reparse_tags=PDF_WINDOWS_CLOUD_REPARSE_TAGS,
        )
    except ArtifactMetadataUnavailable as exc:
        return _metadata_failure_payload(exc)
    except ArtifactMetadataMalformed as exc:
        raise SupervisorError("invalid_worker_request") from exc
    return {
        "schema_version": METADATA_SCHEMA_VERSION,
        "status": "available",
        "generation": receipt.generation.to_dict(),
        "root_generation": (
            receipt.root_generation.to_dict()
            if receipt.root_generation is not None
            else None
        ),
        "reparse_tag": receipt.reparse_tag,
    }


def _decode_metadata_payload(payload: object) -> ArtifactMetadataReceipt:
    try:
        return decode_artifact_metadata_payload(
            payload,
            unavailable_reason_code="pdf_artifact_unavailable",
            reparse_point_attribute=PDF_WINDOWS_REPARSE_POINT_ATTRIBUTE,
            cloud_reparse_tags=PDF_WINDOWS_CLOUD_REPARSE_TAGS,
        )
    except ArtifactMetadataUnavailable as exc:
        details: dict[str, object] = {"failure_kind": exc.failure_kind}
        if exc.exception_type is not None:
            details["exception_type"] = exc.exception_type
        raise _failure("pdf_artifact_unavailable", details=details) from exc
    except ArtifactMetadataMalformed as exc:
        raise _failure("pdf_probe_malformed_result") from exc


def _limits_before_deadline(
    limits: SupervisorLimits,
    deadline_monotonic: float | None,
) -> SupervisorLimits:
    if deadline_monotonic is None:
        return limits
    if (
        isinstance(deadline_monotonic, bool)
        or not isinstance(deadline_monotonic, (int, float))
        or not math.isfinite(float(deadline_monotonic))
    ):
        raise _failure("pdf_evidence_invalid")
    remaining = float(deadline_monotonic) - time.monotonic() - limits.cleanup_seconds
    if remaining <= 0:
        raise _failure("pdf_batch_wall_limit")
    if remaining >= limits.wall_seconds:
        return limits
    return replace(limits, wall_seconds=remaining)


def _worker_command() -> list[str]:
    return [
        sys.executable,
        os.fspath(Path(__file__).absolute()),
        PDF_SUPERVISED_WORKER_FLAG,
    ]


def _invoke_metadata_worker(
    command: list[str],
    payload: dict[str, object],
    sensitive_values: tuple[Path, ...],
    limits: SupervisorLimits,
) -> WorkerResult:
    """Narrow injection seam for metadata protocol tests."""
    return run_authenticated_worker(
        command,
        PDF_METADATA_OPERATION,
        {},
        cast(Any, payload),
        limits,
        sensitive_values=sensitive_values,
        schema_generation=PDF_PROBE_SCHEMA_VERSION,
        pipeline_generation=PDF_PROBE_PIPELINE_VERSION,
    )


def _run_bounded_metadata_worker(
    artifact: Path,
    *,
    trusted_root: Path | None,
    deadline_monotonic: float | None,
) -> ArtifactMetadataReceipt:
    payload: dict[str, object] = {
        "pdf_path": os.fspath(artifact),
        "trusted_root": os.fspath(trusted_root) if trusted_root is not None else None,
    }
    sensitive = (artifact,) if trusted_root is None else (artifact, trusted_root)
    limits = _limits_before_deadline(PDF_METADATA_LIMITS, deadline_monotonic)
    deadline_limited = limits.wall_seconds < PDF_METADATA_LIMITS.wall_seconds
    try:
        result = _invoke_metadata_worker(_worker_command(), payload, sensitive, limits)
    except SupervisorError as exc:
        if deadline_limited and exc.reason_code == "worker_timeout":
            raise _failure("pdf_batch_wall_limit") from exc
        raise _supervisor_failure(
            exc,
            timeout_seconds=limits.wall_seconds,
            max_diagnostic_bytes=limits.max_diagnostic_bytes,
        ) from exc
    diagnostics = _validated_diagnostic_receipt(
        result.diagnostics,
        max_diagnostic_bytes=limits.max_diagnostic_bytes,
    )
    if diagnostics.byte_count:
        raise _failure(
            "pdf_probe_malformed_result",
            details=_diagnostic_details(diagnostics),
        )
    receipt = _decode_metadata_payload(result.payload)
    if (trusted_root is None) != (receipt.root_generation is None):
        raise _failure("pdf_probe_malformed_result")
    return receipt


def _availability(generation: FileGeneration) -> ArtifactAvailability:
    return ArtifactAvailability.from_generation(
        generation,
        macos_dataless_flag=PDF_MACOS_DATALESS_FLAG,
        windows_cloud_file_attributes=PDF_WINDOWS_CLOUD_FILE_ATTRIBUTES,
    )


def _cache_key(
    artifact: Path,
    trusted_root: Path | None,
    receipt: ArtifactMetadataReceipt,
) -> _PdfCacheKey:
    availability = _availability(receipt.generation)
    return _PdfCacheKey(
        artifact_path=os.fspath(artifact),
        generation=receipt.generation,
        trusted_root=os.fspath(trusted_root) if trusted_root is not None else None,
        root_generation=receipt.root_generation,
        reparse_tag=receipt.reparse_tag,
        availability_state=availability.state,
        macos_dataless=availability.macos_dataless,
        windows_offline=availability.windows_offline,
        windows_recall_on_open=availability.windows_recall_on_open,
        windows_recall_on_data_access=availability.windows_recall_on_data_access,
        metadata_profile_id=PDF_METADATA_LIMITS.profile_id,
        probe_profile_id=PDF_PROBE_LIMITS.profile_id,
        schema_generation=PDF_PROBE_SCHEMA_VERSION,
        pipeline_generation=PDF_PROBE_PIPELINE_VERSION,
        max_input_bytes=PDF_MAX_INPUT_BYTES,
        max_pages=PDF_MAX_PAGES,
    )


def _copy_probe(probe: PdfArtifactProbe) -> PdfArtifactProbe:
    return PdfArtifactProbe(
        generation=probe.generation,
        root_generation=probe.root_generation,
        availability=probe.availability,
        page_count=probe.page_count,
        source_sha256=probe.source_sha256,
        source_size_bytes=probe.source_size_bytes,
        parser_diagnostics=probe.parser_diagnostics,
    )


def _cache_result(
    key: _PdfCacheKey,
    value: PdfArtifactProbe | _CachedFailure,
) -> None:
    stale_keys = [
        candidate
        for candidate in _PDF_ARTIFACT_PROBE_CACHE
        if candidate.artifact_path == key.artifact_path
        and candidate.trusted_root == key.trusted_root
        and candidate != key
    ]
    for stale_key in stale_keys:
        _PDF_ARTIFACT_PROBE_CACHE.pop(stale_key, None)
    _PDF_ARTIFACT_PROBE_CACHE[key] = value


def _purge_cached_path(artifact: Path) -> None:
    for key in [
        candidate
        for candidate in _PDF_ARTIFACT_PROBE_CACHE
        if candidate.artifact_path == os.fspath(artifact)
    ]:
        _PDF_ARTIFACT_PROBE_CACHE.pop(key, None)


def clear_pdf_artifact_probe_cache() -> None:
    """Clear process-local exact-generation PDF probe memoization."""
    _PDF_ARTIFACT_PROBE_CACHE.clear()


def _cached_failure(error: PdfEvidenceError) -> _CachedFailure:
    return _CachedFailure(str(error), error.reason_code, copy.deepcopy(error.details))


def _raise_cached(error: _CachedFailure) -> None:
    raise PdfEvidenceError(
        error.message,
        reason_code=error.reason_code,
        details=copy.deepcopy(error.details),
    )


def _diagnostic_details(receipt: DiagnosticReceipt) -> dict[str, object]:
    return {"diagnostic_receipt": receipt.to_dict()}


def _diagnostic_receipt_shape(
    value: object,
    *,
    max_diagnostic_bytes: int,
) -> DiagnosticReceipt:
    if not isinstance(value, DiagnosticReceipt):
        raise _failure("pdf_probe_malformed_result")
    if (
        type(value.byte_count) is not int
        or value.byte_count < 0
        or not isinstance(value.sha256, str)
        or _SHA256_RE.fullmatch(value.sha256) is None
        or type(value.truncated) is not bool
        or (value.byte_count == 0 and value.sha256 != hashlib.sha256(b"").hexdigest())
        or (value.byte_count > 0 and value.sha256 == hashlib.sha256(b"").hexdigest())
        or value.truncated != (value.byte_count > max_diagnostic_bytes)
    ):
        raise _failure("pdf_probe_malformed_result")
    return value


def _validated_diagnostic_receipt(
    value: object,
    *,
    max_diagnostic_bytes: int,
) -> DiagnosticReceipt:
    receipt = _diagnostic_receipt_shape(
        value,
        max_diagnostic_bytes=max_diagnostic_bytes,
    )
    if receipt.truncated:
        raise _failure(
            "pdf_probe_resource_unavailable",
            details=_diagnostic_details(receipt),
        )
    return receipt


def _unavailable_payload(
    reason_code: str,
    *,
    exception_type: str | None = None,
    limit_bytes: int | None = None,
    max_pages: int | None = None,
) -> dict[str, object]:
    details: dict[str, object] = {}
    if exception_type is not None:
        details["exception_type"] = exception_type
    if limit_bytes is not None:
        details["limit_bytes"] = limit_bytes
    if max_pages is not None:
        details["max_pages"] = max_pages
    return {
        "schema_version": PDF_PROBE_SCHEMA_VERSION,
        "status": "unavailable",
        "reason_code": reason_code,
        "details": details,
    }


def _worker_generation_change(*names: str) -> SupervisorError:
    normalized = sorted(set(names))
    if not normalized or any(name not in _PDF_GENERATION_NAMES for name in normalized):
        return SupervisorError("invalid_worker_request")
    generation_names: list[JsonValue] = list(normalized)
    details: dict[str, JsonValue] = {"generation_names": generation_names}
    return SupervisorError(
        "worker_generation_changed",
        details,
    )


def _closed_generation_names(details: Mapping[str, object]) -> list[str]:
    raw = details.get("generation_names")
    if not isinstance(raw, list) or any(type(name) is not str for name in raw):
        return []
    normalized = sorted(set(cast(list[str], raw)))
    if raw != normalized or any(
        name not in _PDF_GENERATION_NAMES for name in normalized
    ):
        return []
    return normalized


def _source_open_flags() -> int:
    flags = os.O_RDONLY
    flags |= int(getattr(os, "O_BINARY", 0))
    flags |= int(getattr(os, "O_CLOEXEC", 0))
    flags |= int(getattr(os, "O_NOFOLLOW", 0))
    return flags


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("private PDF snapshot write made no progress")
        remaining = remaining[written:]


def _copy_and_hash_source(
    artifact: Path,
    snapshot: Path,
    *,
    expected_generation: FileGeneration,
    max_input_bytes: int,
) -> tuple[str, int, bytes]:
    try:
        source_descriptor = os.open(artifact, _source_open_flags())
    except OSError as exc:
        raise _failure(
            "pdf_artifact_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    destination_descriptor: int | None = None
    try:
        try:
            before = FileGeneration.from_stat(os.fstat(source_descriptor))
        except OSError as exc:
            raise _failure(
                "pdf_artifact_unavailable",
                details={"exception_type": type(exc).__name__},
            ) from exc
        if before != expected_generation:
            raise _worker_generation_change("pdf")
        try:
            destination_descriptor = os.open(
                snapshot,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | int(getattr(os, "O_BINARY", 0)),
                0o600,
            )
        except OSError as exc:
            raise _failure(
                "pdf_probe_resource_unavailable",
                details={"exception_type": type(exc).__name__},
            ) from exc

        digest = hashlib.sha256()
        byte_count = 0
        header = bytearray()
        while True:
            try:
                chunk = os.read(source_descriptor, PDF_COPY_CHUNK_BYTES)
            except OSError as exc:
                raise _failure(
                    "pdf_artifact_unavailable",
                    details={"exception_type": type(exc).__name__},
                ) from exc
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > max_input_bytes:
                raise _failure(
                    "pdf_probe_resource_unavailable",
                    details={"limit_bytes": max_input_bytes},
                )
            if byte_count > expected_generation.size:
                raise _worker_generation_change("pdf")
            if len(header) < 5:
                header.extend(chunk[: 5 - len(header)])
            digest.update(chunk)
            try:
                _write_all(destination_descriptor, chunk)
            except OSError as exc:
                raise _failure(
                    "pdf_probe_resource_unavailable",
                    details={"exception_type": type(exc).__name__},
                ) from exc
        try:
            after = FileGeneration.from_stat(os.fstat(source_descriptor))
        except OSError as exc:
            raise _failure(
                "pdf_artifact_unavailable",
                details={"exception_type": type(exc).__name__},
            ) from exc
        if after != before or byte_count != expected_generation.size:
            raise _worker_generation_change("pdf")
        return digest.hexdigest(), byte_count, bytes(header)
    finally:
        try:
            if destination_descriptor is not None:
                os.close(destination_descriptor)
        finally:
            os.close(source_descriptor)


def _strict_pdf_page_count(snapshot: Path, *, max_pages: int) -> int:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise _failure(
            "pdf_dependency_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc

    logger = logging.getLogger("pypdf")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    prior_level = logger.level
    prior_propagate = logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        try:
            with snapshot.open("rb") as stream:
                reader = PdfReader(stream, strict=True)
                page_count = len(reader.pages)
                if page_count > max_pages:
                    raise _failure(
                        "pdf_page_limit",
                        details={"max_pages": max_pages},
                    )
                # Access every page so a successful receipt covers the complete
                # inherited page tree rather than only the catalog and /Count.
                for index in range(page_count):
                    reader.pages[index]
        except PdfReadError as exc:
            raise _failure(
                "pdf_parser_rejected",
                details={"exception_type": type(exc).__name__},
            ) from exc
        except OSError as exc:
            raise _failure(
                "pdf_probe_resource_unavailable",
                details={"exception_type": type(exc).__name__},
            ) from exc
        except (
            EOFError,
            IndexError,
            KeyError,
            OverflowError,
            RecursionError,
            TypeError,
            UnicodeError,
            ValueError,
            ZeroDivisionError,
        ) as exc:
            raise _failure(
                "pdf_parser_rejected",
                details={"exception_type": type(exc).__name__},
            ) from exc
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(prior_level)
        logger.propagate = prior_propagate
    if page_count < 1:
        raise _failure("pdf_no_pages")
    return page_count


def _probe_pdf_snapshot_in_process(
    artifact: Path,
    *,
    expected_generation: FileGeneration,
    max_input_bytes: int,
    max_pages: int,
) -> dict[str, object]:
    try:
        temporary = tempfile.TemporaryDirectory(prefix="speaker-toolkit-pdf-")
    except OSError as exc:
        raise _failure(
            "pdf_probe_resource_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    with temporary as directory:
        snapshot = Path(directory) / "snapshot.pdf"
        source_sha256, source_size, header = _copy_and_hash_source(
            artifact,
            snapshot,
            expected_generation=expected_generation,
            max_input_bytes=max_input_bytes,
        )
        if header != b"%PDF-":
            raise _failure("pdf_invalid_container")
        page_count = _strict_pdf_page_count(snapshot, max_pages=max_pages)
    return {
        "schema_version": PDF_PROBE_SCHEMA_VERSION,
        "status": "available",
        "page_count": page_count,
        "source_sha256": source_sha256,
        "source_size_bytes": source_size,
    }


class _ContainedDiagnosticCapture:
    """Capture Python and descriptor diagnostics inside a supervised worker."""

    def __init__(self, limit_bytes: int) -> None:
        self._limit_bytes = limit_bytes
        self._read_stream: Any | None = None
        self._text_stream: Any | None = None
        self._text_descriptor: int | None = None
        self._drainer: _PipeDrainer | None = None
        self._drainer_started = False
        self._saved_stdout: int | None = None
        self._saved_stderr: int | None = None
        self._write_descriptor: int | None = None
        self._stdout_redirect: Any | None = None
        self._stderr_redirect: Any | None = None
        self._receipt: DiagnosticReceipt | None = None

    @staticmethod
    def _close_descriptor(descriptor: int | None) -> str | None:
        if descriptor is None:
            return None
        try:
            os.close(descriptor)
        except OSError as exc:
            return type(exc).__name__
        return None

    def _restore_descriptors(self) -> str | None:
        error_type: str | None = None
        for target, saved in (
            (_PROCESS_STDOUT_DESCRIPTOR, self._saved_stdout),
            (_PROCESS_STDERR_DESCRIPTOR, self._saved_stderr),
        ):
            if saved is None:
                continue
            try:
                os.dup2(saved, target)
            except OSError as exc:
                error_type = error_type or type(exc).__name__
            close_error = self._close_descriptor(saved)
            error_type = error_type or close_error
        self._saved_stdout = None
        self._saved_stderr = None
        close_error = self._close_descriptor(self._write_descriptor)
        self._write_descriptor = None
        return error_type or close_error

    def _close_text_stream(self) -> str | None:
        error_type: str | None = None
        if self._text_stream is not None:
            try:
                self._text_stream.flush()
            except (MemoryError, OSError, RuntimeError, ValueError) as exc:
                error_type = type(exc).__name__
            try:
                self._text_stream.close()
            except (MemoryError, OSError, RuntimeError, ValueError) as exc:
                error_type = error_type or type(exc).__name__
            self._text_stream = None
        close_error = self._close_descriptor(self._text_descriptor)
        self._text_descriptor = None
        return error_type or close_error

    def _finish_drainer(self) -> tuple[str | None, str | None]:
        if self._drainer is None or not self._drainer_started:
            error_type: str | None = None
            if self._read_stream is not None:
                try:
                    self._read_stream.close()
                except (MemoryError, OSError, RuntimeError, ValueError) as exc:
                    error_type = type(exc).__name__
            self._read_stream = None
            return error_type, None
        try:
            self._drainer.join(1.0)
        except RuntimeError as exc:
            return type(exc).__name__, None
        if self._drainer.alive:
            self._drainer.close()
            try:
                self._drainer.join(1.0)
            except RuntimeError as exc:
                return type(exc).__name__, None
            if self._drainer.alive:
                return None, "diagnostic_drain_timeout"
        try:
            receipt = self._drainer.receipt
            self._drainer.close()
        except (MemoryError, RuntimeError, ValueError) as exc:
            return type(exc).__name__, None
        self._read_stream = None
        if self._drainer.failed:
            return None, "diagnostic_drain_failed"
        self._receipt = receipt
        return None, None

    def _exit_redirects(
        self,
        exception_type: object = None,
        exception: object = None,
        traceback: object = None,
    ) -> str | None:
        error_type: str | None = None
        for redirect in (self._stderr_redirect, self._stdout_redirect):
            if redirect is None:
                continue
            try:
                redirect.__exit__(exception_type, exception, traceback)
            except (
                AttributeError,
                IndexError,
                MemoryError,
                OSError,
                RuntimeError,
                ValueError,
            ) as exc:
                error_type = error_type or type(exc).__name__
        self._stderr_redirect = None
        self._stdout_redirect = None
        return error_type

    @staticmethod
    def _resource_failure(
        *,
        exception_type: str | None = None,
        capture_failure_kind: str | None = None,
    ) -> PdfEvidenceError:
        details: dict[str, object] = {}
        if exception_type is not None:
            details["exception_type"] = exception_type
        if capture_failure_kind is not None:
            details["capture_failure_kind"] = capture_failure_kind
        return _failure("pdf_probe_resource_unavailable", details=details)

    def __enter__(self) -> _ContainedDiagnosticCapture:
        read_descriptor: int | None = None
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            read_descriptor, self._write_descriptor = os.pipe()
            os.set_inheritable(read_descriptor, False)
            os.set_inheritable(self._write_descriptor, False)
            self._read_stream = os.fdopen(read_descriptor, "rb", buffering=0)
            read_descriptor = None
            self._drainer = _PipeDrainer(self._read_stream, self._limit_bytes)
            self._drainer.start()
            self._drainer_started = True
            self._saved_stdout = os.dup(_PROCESS_STDOUT_DESCRIPTOR)
            self._saved_stderr = os.dup(_PROCESS_STDERR_DESCRIPTOR)
            os.set_inheritable(self._saved_stdout, False)
            os.set_inheritable(self._saved_stderr, False)
            os.dup2(self._write_descriptor, _PROCESS_STDOUT_DESCRIPTOR)
            os.dup2(self._write_descriptor, _PROCESS_STDERR_DESCRIPTOR)
            close_error = self._close_descriptor(self._write_descriptor)
            self._write_descriptor = None
            if close_error is not None:
                raise OSError("cannot close contained diagnostic writer")
            self._text_descriptor = os.dup(_PROCESS_STDERR_DESCRIPTOR)
            self._text_stream = os.fdopen(
                self._text_descriptor,
                "w",
                encoding="utf-8",
                errors="replace",
                buffering=1,
                closefd=False,
            )
            stdout_redirect = contextlib.redirect_stdout(self._text_stream)
            stdout_redirect.__enter__()
            self._stdout_redirect = stdout_redirect
            stderr_redirect = contextlib.redirect_stderr(self._text_stream)
            stderr_redirect.__enter__()
            self._stderr_redirect = stderr_redirect
        except (
            AttributeError,
            IndexError,
            MemoryError,
            OSError,
            RuntimeError,
            ValueError,
        ) as exc:
            self._close_descriptor(read_descriptor)
            self._exit_redirects()
            self._close_text_stream()
            self._restore_descriptors()
            self._finish_drainer()
            raise self._resource_failure(exception_type=type(exc).__name__) from exc
        return self

    def __exit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> bool:
        redirect_error = self._exit_redirects(
            exception_type,
            exception,
            traceback,
        )
        stream_error = self._close_text_stream()
        restore_error = self._restore_descriptors()
        drain_error, capture_failure_kind = self._finish_drainer()
        failure_type = redirect_error or stream_error or restore_error or drain_error
        if failure_type is not None:
            raise self._resource_failure(exception_type=failure_type)
        if capture_failure_kind is not None:
            raise self._resource_failure(
                capture_failure_kind=capture_failure_kind,
            )
        return False

    @property
    def receipt(self) -> DiagnosticReceipt | None:
        return self._receipt


def _inspect_pdf_in_contained_worker(
    artifact: Path,
    *,
    expected_generation: FileGeneration,
) -> tuple[str, int, int]:
    """Apply the PDF probe policy inside an already-supervised worker."""
    if expected_generation.size > PDF_MAX_INPUT_BYTES:
        raise _failure(
            "pdf_artifact_too_large",
            details={"limit_bytes": PDF_MAX_INPUT_BYTES},
        )
    capture = _ContainedDiagnosticCapture(PDF_PROBE_LIMITS.max_diagnostic_bytes)
    payload: dict[str, object] | None = None
    child_error: PdfEvidenceError | None = None
    try:
        with capture:
            try:
                payload = _probe_pdf_snapshot_in_process(
                    artifact,
                    expected_generation=expected_generation,
                    max_input_bytes=PDF_MAX_INPUT_BYTES,
                    max_pages=PDF_MAX_PAGES,
                )
            except MemoryError:
                child_error = _failure("pdf_probe_resource_unavailable")
    except PdfEvidenceError as exc:
        child_error = exc
    raw_diagnostics = capture.receipt
    if raw_diagnostics is None:
        if child_error is not None:
            raise child_error
        raise _failure(
            "pdf_probe_resource_unavailable",
            details={"capture_failure_kind": "diagnostic_drain_failed"},
        )
    diagnostics = _validated_diagnostic_receipt(
        raw_diagnostics,
        max_diagnostic_bytes=PDF_PROBE_LIMITS.max_diagnostic_bytes,
    )
    if child_error is not None:
        details = dict(child_error.details)
        if diagnostics.byte_count:
            details.update(_diagnostic_details(diagnostics))
        details = _validated_contained_pdf_failure_details(
            child_error.reason_code,
            details,
        )
        raise PdfEvidenceError(
            str(child_error),
            reason_code=child_error.reason_code,
            details=details,
        ) from child_error
    try:
        probe = _decode_probe_payload(
            payload,
            receipt=ArtifactMetadataReceipt(
                generation=expected_generation,
                root_generation=None,
                reparse_tag=None,
            ),
            diagnostics=diagnostics,
        )
    except PdfEvidenceError as exc:
        details = dict(exc.details)
        if diagnostics.byte_count:
            details.update(_diagnostic_details(diagnostics))
        details = _validated_contained_pdf_failure_details(
            exc.reason_code,
            details,
        )
        raise PdfEvidenceError(
            str(exc),
            reason_code=exc.reason_code,
            details=details,
        ) from exc
    return probe.source_sha256, probe.source_size_bytes, probe.page_count


def _closed_child_failure_details(error: PdfEvidenceError) -> dict[str, object]:
    details: dict[str, object] = {}
    allowed = _CHILD_FAILURE_DETAIL_KEYS.get(error.reason_code, frozenset())
    exception_type = error.details.get("exception_type")
    if (
        "exception_type" in allowed
        and isinstance(exception_type, str)
        and _EXCEPTION_TYPE_RE.fullmatch(exception_type) is not None
    ):
        details["exception_type"] = exception_type
    limit_bytes = error.details.get("limit_bytes")
    if (
        "limit_bytes" in allowed
        and type(limit_bytes) is int
        and limit_bytes == PDF_MAX_INPUT_BYTES
    ):
        details["limit_bytes"] = limit_bytes
    max_pages = error.details.get("max_pages")
    if "max_pages" in allowed and type(max_pages) is int and max_pages == PDF_MAX_PAGES:
        details["max_pages"] = max_pages
    return details


def _pdf_probe_child(
    artifact: Path,
    *,
    expected_generation: FileGeneration,
    max_input_bytes: int,
    max_pages: int,
) -> dict[str, object]:
    try:
        return _probe_pdf_snapshot_in_process(
            artifact,
            expected_generation=expected_generation,
            max_input_bytes=max_input_bytes,
            max_pages=max_pages,
        )
    except MemoryError:
        return _unavailable_payload("pdf_probe_resource_unavailable")
    except PdfEvidenceError as exc:
        reason = (
            exc.reason_code
            if exc.reason_code in _CHILD_FAILURE_REASONS
            else "pdf_parser_rejected"
        )
        return {
            "schema_version": PDF_PROBE_SCHEMA_VERSION,
            "status": "unavailable",
            "reason_code": reason,
            "details": _closed_child_failure_details(exc),
        }


def _metadata_receipt_in_probe_worker(
    artifact: Path,
    trusted_root: Path | None,
) -> ArtifactMetadataReceipt:
    try:
        return inspect_metadata_generation(
            artifact,
            trusted_root=trusted_root,
            reparse_point_attribute=PDF_WINDOWS_REPARSE_POINT_ATTRIBUTE,
            cloud_reparse_tags=PDF_WINDOWS_CLOUD_REPARSE_TAGS,
        )
    except (ArtifactMetadataMalformed, ArtifactMetadataUnavailable) as exc:
        names = ("pdf",) if trusted_root is None else ("pdf", "pdf_root")
        raise _worker_generation_change(*names) from exc


def _probe_payload_values(
    payload: Mapping[str, object],
) -> tuple[Path, Path | None, int, int]:
    if set(payload) != {
        "pdf_path",
        "trusted_root",
        "max_input_bytes",
        "max_pages",
    }:
        raise SupervisorError("invalid_worker_request")
    artifact = _worker_bound_path(payload.get("pdf_path"))
    root_value = payload.get("trusted_root")
    if root_value is not None and not isinstance(root_value, str):
        raise SupervisorError("invalid_worker_request")
    trusted_root = _worker_bound_path(root_value) if root_value is not None else None
    max_input_bytes = payload.get("max_input_bytes")
    max_pages = payload.get("max_pages")
    if max_input_bytes != PDF_MAX_INPUT_BYTES or max_pages != PDF_MAX_PAGES:
        raise SupervisorError("invalid_worker_request")
    return artifact, trusted_root, PDF_MAX_INPUT_BYTES, PDF_MAX_PAGES


def _dispatch_supervised_worker(
    request: WorkerRequest,
) -> tuple[dict[str, object], dict[str, FileGeneration]]:
    if request.schema_generation != PDF_PROBE_SCHEMA_VERSION:
        raise SupervisorError("invalid_worker_request")
    if request.pipeline_generation != PDF_PROBE_PIPELINE_VERSION:
        raise SupervisorError("invalid_worker_request")
    if not isinstance(request.payload, Mapping):
        raise SupervisorError("invalid_worker_request")

    if request.operation == PDF_METADATA_OPERATION:
        if (
            request.limit_profile_id != PDF_METADATA_LIMITS.profile_id
            or request.expected_generations
        ):
            raise SupervisorError("invalid_worker_request")
        return _metadata_child(request.payload), {}
    if request.operation != PDF_PROBE_OPERATION:
        raise SupervisorError("invalid_worker_operation")
    if request.limit_profile_id != PDF_PROBE_LIMITS.profile_id:
        raise SupervisorError("invalid_worker_request")

    artifact, trusted_root, max_input_bytes, max_pages = _probe_payload_values(
        request.payload
    )
    expected_names = {"pdf"}
    if trusted_root is not None:
        expected_names.add("pdf_root")
    if set(request.expected_generations) != expected_names:
        raise SupervisorError("invalid_worker_request")
    before = _metadata_receipt_in_probe_worker(artifact, trusted_root)
    observed: dict[str, FileGeneration] = {"pdf": before.generation}
    if before.root_generation is not None:
        observed["pdf_root"] = before.root_generation
    changed_before = sorted(
        name
        for name in observed
        if observed[name] != request.expected_generations[name]
    )
    if changed_before:
        raise _worker_generation_change(*changed_before)
    if _availability(before.generation).state != "local":
        raise _worker_generation_change("pdf")

    payload = _pdf_probe_child(
        artifact,
        expected_generation=before.generation,
        max_input_bytes=max_input_bytes,
        max_pages=max_pages,
    )
    after = _metadata_receipt_in_probe_worker(artifact, trusted_root)
    changed_after: list[str] = []
    if after.generation != before.generation:
        changed_after.append("pdf")
    if after.root_generation != before.root_generation:
        changed_after.append("pdf_root")
    if changed_after:
        raise _worker_generation_change(*changed_after)
    return payload, observed


def _invoke_probe_worker(
    command: list[str],
    expected_generations: Mapping[str, FileGeneration],
    payload: dict[str, object],
    sensitive_values: tuple[Path, ...],
    limits: SupervisorLimits,
) -> WorkerResult:
    """Narrow injection seam for authenticated probe protocol tests."""
    return run_authenticated_worker(
        command,
        PDF_PROBE_OPERATION,
        expected_generations,
        cast(Any, payload),
        limits,
        sensitive_values=sensitive_values,
        schema_generation=PDF_PROBE_SCHEMA_VERSION,
        pipeline_generation=PDF_PROBE_PIPELINE_VERSION,
    )


def _supervisor_failure(
    exc: SupervisorError,
    *,
    timeout_seconds: float,
    max_diagnostic_bytes: int = PDF_PROBE_LIMITS.max_diagnostic_bytes,
) -> PdfEvidenceError:
    reason = exc.reason_code
    diagnostics = _diagnostic_receipt_shape(
        exc.diagnostics,
        max_diagnostic_bytes=max_diagnostic_bytes,
    )

    def details(**values: object) -> dict[str, object]:
        normalized = dict(values)
        if diagnostics.byte_count or diagnostics.truncated:
            normalized.update(_diagnostic_details(diagnostics))
        return normalized

    if reason == "worker_generation_changed":
        generation_names = _closed_generation_names(exc.details)
        return _failure(
            "pdf_artifact_changed",
            details=details(
                **({"generation_names": generation_names} if generation_names else {})
            ),
        )
    if reason == "worker_timeout":
        return _failure(
            "pdf_probe_timeout",
            details=details(timeout_seconds=timeout_seconds),
        )
    if reason in {
        "worker_memory_limit_exceeded",
        "worker_process_limit_exceeded",
        "worker_monitor_unavailable",
        "worker_monitor_identity_changed",
        "worker_containment_unavailable",
        "worker_diagnostic_limit_exceeded",
    }:
        return _failure(
            "pdf_probe_resource_unavailable",
            details=details(supervisor_reason_code=reason),
        )
    if reason in {
        "worker_start_failed",
        "worker_pipe_setup_failed",
        "worker_exit_before_barrier",
        "worker_request_write_failed",
        "invalid_worker_command",
        "unsafe_worker_process_metadata",
    }:
        return _failure(
            "pdf_probe_start_failure",
            details=details(supervisor_reason_code=reason),
        )
    if reason == "worker_output_limit_exceeded":
        return _failure(
            "pdf_probe_result_oversized",
            details=details(supervisor_reason_code=reason),
        )
    if reason == "worker_input_limit_exceeded":
        return _failure(
            "pdf_probe_request_oversized",
            details=details(supervisor_reason_code=reason),
        )
    if reason in {
        "worker_exit",
        "worker_process_tree_leak",
        "worker_cleanup_failed",
        "worker_diagnostic_read_failed",
        "worker_output_read_failed",
    }:
        return _failure(
            "pdf_probe_crash",
            details=details(supervisor_reason_code=reason),
        )
    return _failure(
        "pdf_probe_malformed_result",
        details=details(supervisor_reason_code=reason),
    )


def _validated_unavailable_details(
    reason_code: str,
    value: object,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise _failure("pdf_probe_malformed_result")
    detail_keys = set(value)
    allowed = _CHILD_FAILURE_DETAIL_KEYS.get(reason_code)
    if allowed is None or not detail_keys <= allowed:
        raise _failure("pdf_probe_malformed_result")
    if reason_code in {
        "pdf_artifact_unavailable",
        "pdf_dependency_unavailable",
        "pdf_parser_rejected",
    } and detail_keys != {"exception_type"}:
        raise _failure("pdf_probe_malformed_result")
    if reason_code == "pdf_page_limit" and detail_keys != {"max_pages"}:
        raise _failure("pdf_probe_malformed_result")
    if reason_code in {"pdf_invalid_container", "pdf_no_pages"} and detail_keys:
        raise _failure("pdf_probe_malformed_result")
    if reason_code == "pdf_probe_resource_unavailable" and frozenset(
        detail_keys
    ) not in {
        frozenset(),
        frozenset({"exception_type"}),
        frozenset({"limit_bytes"}),
    }:
        raise _failure("pdf_probe_malformed_result")
    details: dict[str, object] = {}
    exception_type = value.get("exception_type")
    if exception_type is not None:
        if (
            not isinstance(exception_type, str)
            or _EXCEPTION_TYPE_RE.fullmatch(exception_type) is None
        ):
            raise _failure("pdf_probe_malformed_result")
        details["exception_type"] = exception_type
    limit_bytes = value.get("limit_bytes")
    if limit_bytes is not None:
        if type(limit_bytes) is not int or limit_bytes != PDF_MAX_INPUT_BYTES:
            raise _failure("pdf_probe_malformed_result")
        details["limit_bytes"] = limit_bytes
    max_pages = value.get("max_pages")
    if max_pages is not None:
        if type(max_pages) is not int or max_pages != PDF_MAX_PAGES:
            raise _failure("pdf_probe_malformed_result")
        details["max_pages"] = max_pages
    return details


def _validated_contained_pdf_failure_details(
    reason_code: str,
    value: object,
) -> dict[str, object]:
    """Validate the closed PDF-error schema crossing the PPTX worker."""
    if not isinstance(value, Mapping):
        raise _failure("pdf_probe_malformed_result")
    base_key_sets: dict[str, frozenset[frozenset[str]]] = {
        "pdf_artifact_too_large": frozenset({frozenset({"limit_bytes"})}),
        "pdf_artifact_unavailable": frozenset(
            {frozenset(), frozenset({"exception_type"})}
        ),
        "pdf_dependency_unavailable": frozenset({frozenset({"exception_type"})}),
        "pdf_invalid_container": frozenset({frozenset()}),
        "pdf_no_pages": frozenset({frozenset()}),
        "pdf_page_limit": frozenset({frozenset({"max_pages"})}),
        "pdf_parser_rejected": frozenset({frozenset({"exception_type"})}),
        "pdf_parser_repair_required": frozenset({frozenset({"diagnostic_receipt"})}),
        "pdf_probe_malformed_result": frozenset({frozenset()}),
        "pdf_probe_resource_unavailable": frozenset(
            {
                frozenset(),
                frozenset({"exception_type"}),
                frozenset({"limit_bytes"}),
                frozenset({"diagnostic_receipt"}),
                frozenset({"capture_failure_kind"}),
            }
        ),
    }
    base_sets = base_key_sets.get(reason_code)
    if base_sets is None:
        raise _failure("pdf_probe_malformed_result")
    allowed_sets = set(base_sets)
    if reason_code != "pdf_parser_repair_required":
        allowed_sets.update(keys | {"diagnostic_receipt"} for keys in base_sets)
    keys = frozenset(value)
    if keys not in allowed_sets:
        raise _failure("pdf_probe_malformed_result")

    details: dict[str, object] = {}
    exception_type = value.get("exception_type")
    if exception_type is not None:
        if (
            not isinstance(exception_type, str)
            or _EXCEPTION_TYPE_RE.fullmatch(exception_type) is None
        ):
            raise _failure("pdf_probe_malformed_result")
        details["exception_type"] = exception_type
    limit_bytes = value.get("limit_bytes")
    if limit_bytes is not None:
        if type(limit_bytes) is not int or limit_bytes != PDF_MAX_INPUT_BYTES:
            raise _failure("pdf_probe_malformed_result")
        details["limit_bytes"] = limit_bytes
    max_pages = value.get("max_pages")
    if max_pages is not None:
        if type(max_pages) is not int or max_pages != PDF_MAX_PAGES:
            raise _failure("pdf_probe_malformed_result")
        details["max_pages"] = max_pages
    capture_failure_kind = value.get("capture_failure_kind")
    if capture_failure_kind is not None:
        if (
            not isinstance(capture_failure_kind, str)
            or capture_failure_kind not in _CAPTURE_FAILURE_KINDS
        ):
            raise _failure("pdf_probe_malformed_result")
        details["capture_failure_kind"] = capture_failure_kind
    raw_diagnostics = value.get("diagnostic_receipt")
    if raw_diagnostics is not None:
        if not isinstance(raw_diagnostics, Mapping) or set(raw_diagnostics) != {
            "byte_count",
            "sha256",
            "truncated",
        }:
            raise _failure("pdf_probe_malformed_result")
        receipt = _diagnostic_receipt_shape(
            DiagnosticReceipt(
                byte_count=cast(Any, raw_diagnostics.get("byte_count")),
                sha256=cast(Any, raw_diagnostics.get("sha256")),
                truncated=cast(Any, raw_diagnostics.get("truncated")),
            ),
            max_diagnostic_bytes=PDF_PROBE_LIMITS.max_diagnostic_bytes,
        )
        if receipt.truncated and reason_code != "pdf_probe_resource_unavailable":
            raise _failure("pdf_probe_malformed_result")
        if reason_code == "pdf_parser_repair_required" and (
            receipt.truncated or receipt.byte_count == 0
        ):
            raise _failure("pdf_probe_malformed_result")
        details["diagnostic_receipt"] = receipt.to_dict()
    return details


def _decode_probe_payload(
    payload: object,
    *,
    receipt: ArtifactMetadataReceipt,
    diagnostics: DiagnosticReceipt,
) -> PdfArtifactProbe:
    diagnostics = _validated_diagnostic_receipt(
        diagnostics,
        max_diagnostic_bytes=PDF_PROBE_LIMITS.max_diagnostic_bytes,
    )
    if not isinstance(payload, Mapping):
        raise _failure("pdf_probe_malformed_result")
    if payload.get("schema_version") != PDF_PROBE_SCHEMA_VERSION:
        raise _failure("pdf_probe_malformed_result")
    if payload.get("status") == "unavailable":
        if set(payload) != {"schema_version", "status", "reason_code", "details"}:
            raise _failure("pdf_probe_malformed_result")
        reason = payload.get("reason_code")
        if not isinstance(reason, str) or reason not in _CHILD_FAILURE_REASONS:
            raise _failure("pdf_probe_malformed_result")
        details = _validated_unavailable_details(reason, payload.get("details"))
        if diagnostics.byte_count:
            details.update(_diagnostic_details(diagnostics))
        raise _failure(reason, details=details)

    expected_fields = {
        "schema_version",
        "status",
        "page_count",
        "source_sha256",
        "source_size_bytes",
    }
    page_count = payload.get("page_count")
    source_sha256 = payload.get("source_sha256")
    source_size = payload.get("source_size_bytes")
    if (
        payload.get("status") != "available"
        or set(payload) != expected_fields
        or type(page_count) is not int
        or not 1 <= page_count <= PDF_MAX_PAGES
        or not isinstance(source_sha256, str)
        or _SHA256_RE.fullmatch(source_sha256) is None
        or type(source_size) is not int
        or source_size != receipt.generation.size
        or not 1 <= source_size <= PDF_MAX_INPUT_BYTES
    ):
        raise _failure("pdf_probe_malformed_result")
    if diagnostics.byte_count:
        raise _failure(
            "pdf_parser_repair_required",
            details=_diagnostic_details(diagnostics),
        )
    return PdfArtifactProbe(
        generation=receipt.generation,
        root_generation=receipt.root_generation,
        availability=_availability(receipt.generation),
        page_count=page_count,
        source_sha256=source_sha256,
        source_size_bytes=source_size,
        parser_diagnostics=diagnostics,
    )


def _run_bounded_pdf_probe(
    artifact: Path,
    *,
    trusted_root: Path | None,
    receipt: ArtifactMetadataReceipt,
    deadline_monotonic: float | None,
) -> PdfArtifactProbe:
    expected_generations = {"pdf": receipt.generation}
    if receipt.root_generation is not None:
        expected_generations["pdf_root"] = receipt.root_generation
    payload: dict[str, object] = {
        "pdf_path": os.fspath(artifact),
        "trusted_root": os.fspath(trusted_root) if trusted_root is not None else None,
        "max_input_bytes": PDF_MAX_INPUT_BYTES,
        "max_pages": PDF_MAX_PAGES,
    }
    sensitive = (artifact,) if trusted_root is None else (artifact, trusted_root)
    limits = _limits_before_deadline(PDF_PROBE_LIMITS, deadline_monotonic)
    deadline_limited = limits.wall_seconds < PDF_PROBE_LIMITS.wall_seconds
    try:
        result = _invoke_probe_worker(
            _worker_command(),
            expected_generations,
            payload,
            sensitive,
            limits,
        )
    except SupervisorError as exc:
        if deadline_limited and exc.reason_code == "worker_timeout":
            raise _failure("pdf_batch_wall_limit") from exc
        raise _supervisor_failure(
            exc,
            timeout_seconds=limits.wall_seconds,
            max_diagnostic_bytes=limits.max_diagnostic_bytes,
        ) from exc
    return _decode_probe_payload(
        result.payload,
        receipt=receipt,
        diagnostics=result.diagnostics,
    )


def _confirm_same_generation(
    artifact: Path,
    *,
    trusted_root: Path | None,
    admitted: ArtifactMetadataReceipt,
    deadline_monotonic: float | None,
) -> None:
    try:
        current = _run_bounded_metadata_worker(
            artifact,
            trusted_root=trusted_root,
            deadline_monotonic=deadline_monotonic,
        )
    except PdfEvidenceError:
        raise
    if current != admitted:
        raise _failure("pdf_artifact_changed")


def _confirm_artifact_failure(
    artifact: Path,
    *,
    trusted_root: Path | None,
    admitted: ArtifactMetadataReceipt,
    first_error: PdfEvidenceError,
    deadline_monotonic: float | None,
) -> None:
    """Require an identical second bounded parse before caching damage."""
    try:
        _run_bounded_pdf_probe(
            artifact,
            trusted_root=trusted_root,
            receipt=admitted,
            deadline_monotonic=deadline_monotonic,
        )
    except PdfEvidenceError as confirmation_error:
        if confirmation_error.reason_code == "pdf_batch_wall_limit":
            raise
        _confirm_same_generation(
            artifact,
            trusted_root=trusted_root,
            admitted=admitted,
            deadline_monotonic=deadline_monotonic,
        )
        if confirmation_error.reason_code not in _CONFIRMED_ARTIFACT_FAILURES:
            raise
        if (
            confirmation_error.reason_code == first_error.reason_code
            and confirmation_error.details == first_error.details
        ):
            return
        raise _failure("pdf_probe_materialization_changed") from confirmation_error
    _confirm_same_generation(
        artifact,
        trusted_root=trusted_root,
        admitted=admitted,
        deadline_monotonic=deadline_monotonic,
    )
    raise _failure("pdf_probe_materialization_changed") from first_error


def probe_pdf_artifact(
    path: str | os.PathLike[str],
    *,
    trusted_root: str | os.PathLike[str] | None = None,
    deadline_monotonic: float | None = None,
) -> PdfArtifactProbe:
    """Return exact PDF evidence without whole-file work in the parent process."""
    artifact = _lexical_absolute(path)
    root = _lexical_absolute(trusted_root) if trusted_root is not None else None
    artifact, root = canonicalize_trusted_artifact_locator(artifact, root)
    try:
        receipt = _run_bounded_metadata_worker(
            artifact,
            trusted_root=root,
            deadline_monotonic=deadline_monotonic,
        )
    except PdfEvidenceError:
        _purge_cached_path(artifact)
        raise
    key = _cache_key(artifact, root, receipt)
    cached = _PDF_ARTIFACT_PROBE_CACHE.get(key)
    if isinstance(cached, PdfArtifactProbe):
        return _copy_probe(cached)
    if isinstance(cached, _CachedFailure):
        _raise_cached(cached)

    if key.availability_state != "local":
        error = _failure(
            "pdf_cloud_placeholder_unavailable",
            details={
                "availability": _availability(receipt.generation).to_dict(),
                "reparse_tag": receipt.reparse_tag,
            },
        )
        _cache_result(key, _cached_failure(error))
        raise error
    if receipt.generation.size > PDF_MAX_INPUT_BYTES:
        error = _failure(
            "pdf_artifact_too_large",
            details={"limit_bytes": PDF_MAX_INPUT_BYTES},
        )
        _cache_result(key, _cached_failure(error))
        raise error

    try:
        probe = _run_bounded_pdf_probe(
            artifact,
            trusted_root=root,
            receipt=receipt,
            deadline_monotonic=deadline_monotonic,
        )
    except PdfEvidenceError as exc:
        if exc.reason_code == "pdf_batch_wall_limit":
            raise
        _confirm_same_generation(
            artifact,
            trusted_root=root,
            admitted=receipt,
            deadline_monotonic=deadline_monotonic,
        )
        if exc.reason_code in _STABLE_ARTIFACT_FAILURES:
            if exc.reason_code in _CONFIRMED_ARTIFACT_FAILURES:
                _confirm_artifact_failure(
                    artifact,
                    trusted_root=root,
                    admitted=receipt,
                    first_error=exc,
                    deadline_monotonic=deadline_monotonic,
                )
            cached_error = _cached_failure(exc)
            _cache_result(key, cached_error)
            _raise_cached(cached_error)
        raise PdfEvidenceError(
            str(exc),
            reason_code=exc.reason_code,
            details=dict(exc.details),
        ) from exc

    _confirm_same_generation(
        artifact,
        trusted_root=root,
        admitted=receipt,
        deadline_monotonic=deadline_monotonic,
    )
    cached_probe = _copy_probe(probe)
    _cache_result(key, cached_probe)
    return _copy_probe(cached_probe)


def _run_supervised_worker_child() -> int:
    request = read_worker_request(max_input_bytes=PDF_METADATA_LIMITS.max_input_bytes)
    protocol_output = isolate_protocol_output()
    try:
        try:
            payload, observed = _dispatch_supervised_worker(request)
            write_worker_response(
                request,
                payload=payload,
                observed_generations=observed,
                stream=protocol_output,
                max_output_bytes=PDF_PROBE_LIMITS.max_output_bytes,
            )
        except SupervisorError as exc:
            write_worker_response(
                request,
                error=SupervisorError(exc.reason_code, exc.details),
                observed_generations=request.expected_generations,
                stream=protocol_output,
                max_output_bytes=PDF_PROBE_LIMITS.max_output_bytes,
            )
    finally:
        protocol_output.close()
    return 0


def _main() -> int:
    if sys.argv[1:] != [PDF_SUPERVISED_WORKER_FLAG]:
        raise SystemExit("pdf_evidence.py is a library")
    try:
        return _run_supervised_worker_child()
    except SupervisorError:
        return 2
    # The caller treats a silent nonzero child as a bounded crash; a traceback
    # could leak paths and violate its authenticated one-frame response shape.
    # outer-boundary-process-contract: emit exit 2 for that caller-visible failure.
    except Exception:  # noqa: BLE001
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "PDF_MAX_INPUT_BYTES",
    "PDF_MAX_PAGES",
    "PDF_METADATA_LIMITS",
    "PDF_PROBE_LIMITS",
    "PDF_PROBE_PIPELINE_VERSION",
    "PDF_PROBE_SCHEMA_VERSION",
    "PDF_SUPERVISED_WORKER_FLAG",
    "PdfArtifactProbe",
    "PdfEvidenceError",
    "clear_pdf_artifact_probe_cache",
    "probe_pdf_artifact",
]

#!/usr/bin/env python3
"""Bounded, exact-generation evidence for local delivery-video artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, BinaryIO, Final, Iterator, Literal, NoReturn, cast

from artifact_locator import (
    ArtifactLocatorError,
    materialize_artifact_locator,
    materialize_native_root,
)
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


VIDEO_PROBE_SCHEMA_VERSION: Final = 1
VIDEO_PROBE_PIPELINE_VERSION: Final = "1.0.0"
VIDEO_SUPERVISED_WORKER_FLAG: Final = "--supervised-worker"
VIDEO_METADATA_OPERATION: Final = "video_metadata"
VIDEO_PROBE_OPERATION: Final = "video_probe"

VIDEO_MAX_INPUT_BYTES: Final = 8 * 1024**3
VIDEO_MAX_STREAMS: Final = 64
VIDEO_FFPROBE_STDOUT_BYTES: Final = 256 * 1024
VIDEO_FFPROBE_STDERR_BYTES: Final = 64 * 1024
VIDEO_DIGEST_CHUNK_BYTES: Final = 1024 * 1024

VIDEO_MACOS_DATALESS_FLAG: Final = MACOS_DATALESS_FLAG
VIDEO_WINDOWS_CLOUD_FILE_ATTRIBUTES: Final = WINDOWS_UNAVAILABLE_CLOUD_ATTRIBUTES
VIDEO_WINDOWS_REPARSE_POINT_ATTRIBUTE: Final = WINDOWS_REPARSE_POINT_ATTRIBUTE
VIDEO_WINDOWS_CLOUD_REPARSE_TAGS: Final = WINDOWS_CLOUD_REPARSE_TAGS

VIDEO_METADATA_LIMITS = SupervisorLimits(
    profile_id="video-metadata-v1",
    wall_seconds=15,
    max_memory_bytes=256 * 1024 * 1024,
    max_input_bytes=64 * 1024,
    max_output_bytes=64 * 1024,
    max_diagnostic_bytes=64 * 1024,
    max_processes=1,
)
VIDEO_PROBE_LIMITS = SupervisorLimits(
    profile_id="video-probe-v1",
    wall_seconds=300,
    max_memory_bytes=512 * 1024 * 1024,
    max_input_bytes=64 * 1024,
    max_output_bytes=64 * 1024,
    max_diagnostic_bytes=64 * 1024,
    max_processes=2,
)

ContainerFamily = Literal["iso_bmff", "matroska_webm"]
DurationSource = Literal["format", "stream"]

_CONTAINER_FAMILY_BY_SUFFIX: Final[dict[str, ContainerFamily]] = {
    ".mp4": "iso_bmff",
    ".mov": "iso_bmff",
    ".webm": "matroska_webm",
    ".mkv": "matroska_webm",
}
_ISO_BMFF_FORMAT_NAMES: Final = frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"})
_MATROSKA_FORMAT_NAMES: Final = frozenset({"matroska", "webm"})
_VIDEO_GENERATION_NAMES: Final = frozenset({"video", "video_root"})
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_EXCEPTION_TYPE_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

_CHILD_FAILURE_REASONS: Final = frozenset(
    {
        "video_artifact_unavailable",
        "video_dependency_unavailable",
        "video_duration_unavailable",
        "video_invalid_container",
        "video_no_video_stream",
        "video_parser_rejected",
        "video_parser_repair_required",
        "video_probe_resource_unavailable",
        "video_stream_limit",
    }
)
_STABLE_GENERATION_FAILURES: Final = frozenset(
    {
        "video_artifact_too_large",
        "video_cloud_placeholder_unavailable",
        "video_duration_unavailable",
        "video_invalid_container",
        "video_no_video_stream",
        "video_parser_rejected",
        "video_parser_repair_required",
        "video_stream_limit",
    }
)


class VideoEvidenceError(ValueError):
    """A path-neutral rejection from the closed video-evidence boundary."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "video_evidence_invalid",
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = dict(details or {})


@dataclass(frozen=True)
class VideoArtifactProbe:
    """Immutable facts bound to one exact local video-file generation."""

    generation: FileGeneration
    root_generation: FileGeneration | None
    availability: ArtifactAvailability
    source_sha256: str
    source_size_bytes: int
    duration_seconds: float
    duration_source: DurationSource
    container_family: ContainerFamily
    stream_count: int
    video_stream_count: int
    audio_stream_count: int
    attached_picture_count: int
    other_stream_count: int
    parser_diagnostics: DiagnosticReceipt


@dataclass(frozen=True)
class _CachedFailure:
    message: str
    reason_code: str
    details: Mapping[str, object]


_Outcome = VideoArtifactProbe | _CachedFailure


@dataclass(frozen=True)
class _AssessmentRequestKey:
    artifact_path: str
    trusted_root: str | None
    expected_container_family: ContainerFamily


@dataclass(frozen=True)
class _VideoCacheKey:
    request: _AssessmentRequestKey
    generation: FileGeneration
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
    max_streams: int


@dataclass
class _AssessmentState:
    lock: threading.RLock = field(default_factory=threading.RLock)
    exact_outcomes: dict[_VideoCacheKey, _Outcome] = field(default_factory=dict)
    transient_outcomes: dict[_AssessmentRequestKey, _CachedFailure] = field(
        default_factory=dict
    )


class VideoEvidenceAssessment:
    """One operation-local probe scope with externally immutable identity.

    Successful and deterministic outcomes are revalidated against metadata on
    every lookup, then reused only for the same exact generation. A transient
    failure is retained for this path for the rest of the assessment, avoiding
    a hidden confirmation probe inside one top-level operation.
    """

    __slots__ = ("_state",)

    def __init__(self) -> None:
        object.__setattr__(self, "_state", _AssessmentState())

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VideoEvidenceAssessment is immutable")

    def probe(
        self,
        path: str | os.PathLike[str],
        *,
        trusted_root: str | os.PathLike[str] | None = None,
        deadline_monotonic: float | None = None,
    ) -> VideoArtifactProbe:
        artifact, root, expected_family = _materialize_public_request(
            path,
            trusted_root=trusted_root,
        )
        request_key = _request_key(artifact, root, expected_family)
        with self._state.lock:
            transient = self._state.transient_outcomes.get(request_key)
        if transient is not None:
            _raise_cached(transient)

        try:
            receipt = _run_bounded_metadata_worker(
                artifact,
                trusted_root=root,
                deadline_monotonic=deadline_monotonic,
            )
        except VideoEvidenceError as exc:
            cached = _cached_failure(exc)
            with self._state.lock:
                self._state.transient_outcomes.setdefault(request_key, cached)
                selected = self._state.transient_outcomes[request_key]
            _raise_cached(selected)

        key = _cache_key(request_key, receipt)
        with self._state.lock:
            prior = self._state.exact_outcomes.get(key)
        if prior is not None:
            return _outcome_value(prior)

        try:
            outcome = _probe_generation_singleflight(
                artifact,
                trusted_root=root,
                receipt=receipt,
                key=key,
                deadline_monotonic=deadline_monotonic,
                assessment_state=self._state,
            )
        except VideoEvidenceError as exc:
            cached = _cached_failure(exc)
            with self._state.lock:
                if exc.reason_code in _STABLE_GENERATION_FAILURES:
                    self._state.exact_outcomes.setdefault(key, cached)
                    selected = self._state.exact_outcomes[key]
                else:
                    self._state.transient_outcomes.setdefault(request_key, cached)
                    selected = self._state.transient_outcomes[request_key]
            return _outcome_value(selected)

        with self._state.lock:
            self._state.exact_outcomes.setdefault(key, outcome)
            selected = self._state.exact_outcomes[key]
        return _outcome_value(selected)


@dataclass
class _GlobalFlight:
    leader_state: _AssessmentState
    event: threading.Event = field(default_factory=threading.Event)
    outcome: _Outcome | None = None
    assessment_outcome: _Outcome | None = None


@dataclass(frozen=True)
class _PreparedVideoSource:
    source_descriptor: int
    probe_descriptor: int
    probe_artifact: Path
    probe_generation: FileGeneration


_GLOBAL_CACHE_LOCK = threading.RLock()
_GLOBAL_PROBE_CACHE: dict[_VideoCacheKey, _Outcome] = {}
_GLOBAL_PROBE_FLIGHTS: dict[_VideoCacheKey, _GlobalFlight] = {}
_GLOBAL_CACHE_EPOCH = 0


def _failure(
    reason_code: str,
    *,
    details: Mapping[str, object] | None = None,
) -> VideoEvidenceError:
    messages = {
        "video_artifact_changed": "Video artifact changed during bounded inspection",
        "video_artifact_too_large": "Video artifact exceeds the input-size ceiling",
        "video_artifact_unavailable": "Video artifact is unavailable",
        "video_batch_wall_limit": "Video evidence operation deadline expired",
        "video_cloud_placeholder_unavailable": (
            "Video artifact is an offline cloud placeholder; download it locally "
            "before using video evidence"
        ),
        "video_dependency_unavailable": (
            "Video evidence requires its declared runtime dependencies"
        ),
        "video_duration_unavailable": (
            "Video artifact has no positive finite media duration"
        ),
        "video_evidence_invalid": "Video evidence request is invalid",
        "video_invalid_container": "Video artifact has an invalid media container",
        "video_no_video_stream": "Video artifact has no usable video stream",
        "video_parser_rejected": "ffprobe rejected the video artifact",
        "video_parser_repair_required": (
            "ffprobe emitted diagnostics; repair or re-export the video artifact"
        ),
        "video_probe_containment_unavailable": (
            "Bounded video worker process containment is unavailable"
        ),
        "video_probe_crash": "Bounded video evidence worker terminated unexpectedly",
        "video_probe_malformed_result": (
            "Bounded video evidence worker returned an invalid authenticated result"
        ),
        "video_probe_monitor_identity_changed": (
            "Bounded video worker process identity changed during inspection"
        ),
        "video_probe_monitor_unavailable": (
            "Bounded video worker process monitoring is unavailable"
        ),
        "video_probe_request_oversized": (
            "Bounded video worker request exceeded its input contract"
        ),
        "video_probe_resource_unavailable": (
            "Video evidence exceeded a configured worker resource limit"
        ),
        "video_probe_result_oversized": (
            "Bounded video worker result exceeded its output contract"
        ),
        "video_probe_start_failure": "Could not start the bounded video worker",
        "video_probe_timeout": "Bounded video evidence operation timed out",
        "video_stream_limit": "Video artifact exceeds the stream-count ceiling",
    }
    return VideoEvidenceError(
        messages.get(reason_code, "Video artifact is unavailable"),
        reason_code=reason_code,
        details=details,
    )


def _cached_failure(error: VideoEvidenceError) -> _CachedFailure:
    return _CachedFailure(
        message=str(error),
        reason_code=error.reason_code,
        details=copy.deepcopy(error.details),
    )


def _raise_cached(error: _CachedFailure) -> NoReturn:
    raise VideoEvidenceError(
        error.message,
        reason_code=error.reason_code,
        details=copy.deepcopy(error.details),
    )


def _outcome_value(outcome: _Outcome) -> VideoArtifactProbe:
    if isinstance(outcome, _CachedFailure):
        _raise_cached(outcome)
    return outcome


def _globally_shareable_outcome(outcome: _Outcome | None) -> _Outcome | None:
    if isinstance(outcome, VideoArtifactProbe):
        return outcome
    if isinstance(outcome, _CachedFailure) and outcome.reason_code in (
        _STABLE_GENERATION_FAILURES
    ):
        return outcome
    return None


def _materialize_public_request(
    path: object,
    *,
    trusted_root: object | None,
) -> tuple[Path, Path | None, ContainerFamily]:
    try:
        root = (
            materialize_native_root(trusted_root) if trusted_root is not None else None
        )
        artifact = materialize_artifact_locator(path, trusted_root=root)
    except ArtifactLocatorError as exc:
        raise _failure(
            "video_evidence_invalid",
            details={"locator_failure": exc.reason_code},
        ) from exc
    suffix = artifact.suffix.casefold()
    expected_family = _CONTAINER_FAMILY_BY_SUFFIX.get(suffix)
    if expected_family is None:
        raise _failure(
            "video_evidence_invalid",
            details={"locator_failure": "video_suffix_unsupported"},
        )
    try:
        artifact, root = canonicalize_trusted_artifact_locator(artifact, root)
    except ArtifactMetadataMalformed as exc:
        raise _failure(
            "video_evidence_invalid",
            details={
                "locator_failure": exc.locator_failure or "artifact_locator_invalid"
            },
        ) from exc
    return artifact, root, expected_family


def _worker_bound_paths(
    artifact_value: object,
    root_value: object | None,
) -> tuple[Path, Path | None]:
    try:
        root = materialize_native_root(root_value) if root_value is not None else None
        artifact = materialize_artifact_locator(artifact_value, trusted_root=root)
    except ArtifactLocatorError as exc:
        raise SupervisorError(
            "invalid_worker_request",
            {"locator_failure": exc.reason_code},
        ) from exc
    return artifact, root


def _request_key(
    artifact: Path,
    trusted_root: Path | None,
    expected_family: ContainerFamily,
) -> _AssessmentRequestKey:
    return _AssessmentRequestKey(
        artifact_path=os.fspath(artifact),
        trusted_root=(os.fspath(trusted_root) if trusted_root is not None else None),
        expected_container_family=expected_family,
    )


def _availability(generation: FileGeneration) -> ArtifactAvailability:
    return ArtifactAvailability.from_generation(
        generation,
        macos_dataless_flag=VIDEO_MACOS_DATALESS_FLAG,
        windows_cloud_file_attributes=VIDEO_WINDOWS_CLOUD_FILE_ATTRIBUTES,
    )


def _cache_key(
    request: _AssessmentRequestKey,
    receipt: ArtifactMetadataReceipt,
) -> _VideoCacheKey:
    availability = _availability(receipt.generation)
    return _VideoCacheKey(
        request=request,
        generation=receipt.generation,
        root_generation=receipt.root_generation,
        reparse_tag=receipt.reparse_tag,
        availability_state=availability.state,
        macos_dataless=availability.macos_dataless,
        windows_offline=availability.windows_offline,
        windows_recall_on_open=availability.windows_recall_on_open,
        windows_recall_on_data_access=availability.windows_recall_on_data_access,
        metadata_profile_id=VIDEO_METADATA_LIMITS.profile_id,
        probe_profile_id=VIDEO_PROBE_LIMITS.profile_id,
        schema_generation=VIDEO_PROBE_SCHEMA_VERSION,
        pipeline_generation=VIDEO_PROBE_PIPELINE_VERSION,
        max_input_bytes=VIDEO_MAX_INPUT_BYTES,
        max_streams=VIDEO_MAX_STREAMS,
    )


def clear_video_artifact_probe_cache() -> None:
    """Clear completed process-global results without cancelling live leaders."""
    global _GLOBAL_CACHE_EPOCH
    with _GLOBAL_CACHE_LOCK:
        _GLOBAL_CACHE_EPOCH += 1
        _GLOBAL_PROBE_CACHE.clear()


def _metadata_failure_payload(exc: ArtifactMetadataUnavailable) -> dict[str, object]:
    details: dict[str, object] = {"failure_kind": exc.failure_kind}
    if exc.exception_type is not None:
        details["exception_type"] = exc.exception_type
    return {
        "schema_version": METADATA_SCHEMA_VERSION,
        "status": "unavailable",
        "reason_code": "video_artifact_unavailable",
        "details": details,
    }


def _metadata_child(payload: Mapping[str, object]) -> dict[str, object]:
    if set(payload) != {"video_path", "trusted_root"}:
        raise SupervisorError("invalid_worker_request")
    root_value = payload.get("trusted_root")
    if root_value is not None and not isinstance(root_value, str):
        raise SupervisorError("invalid_worker_request")
    artifact, trusted_root = _worker_bound_paths(payload.get("video_path"), root_value)
    try:
        receipt = inspect_metadata_generation(
            artifact,
            trusted_root=trusted_root,
            reparse_point_attribute=VIDEO_WINDOWS_REPARSE_POINT_ATTRIBUTE,
            cloud_reparse_tags=VIDEO_WINDOWS_CLOUD_REPARSE_TAGS,
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
            unavailable_reason_code="video_artifact_unavailable",
            reparse_point_attribute=VIDEO_WINDOWS_REPARSE_POINT_ATTRIBUTE,
            cloud_reparse_tags=VIDEO_WINDOWS_CLOUD_REPARSE_TAGS,
        )
    except ArtifactMetadataUnavailable as exc:
        details: dict[str, object] = {"failure_kind": exc.failure_kind}
        if exc.exception_type is not None:
            details["exception_type"] = exc.exception_type
        raise _failure("video_artifact_unavailable", details=details) from exc
    except ArtifactMetadataMalformed as exc:
        raise _failure("video_probe_malformed_result") from exc


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
        raise _failure("video_evidence_invalid")
    remaining = float(deadline_monotonic) - time.monotonic() - limits.cleanup_seconds
    if remaining <= 0:
        raise _failure("video_batch_wall_limit")
    if remaining >= limits.wall_seconds:
        return limits
    return replace(limits, wall_seconds=remaining)


def _wait_for_flight(
    flight: _GlobalFlight,
    deadline_monotonic: float | None,
    assessment_state: _AssessmentState,
) -> _Outcome | None:
    if deadline_monotonic is None:
        flight.event.wait()
    else:
        if (
            isinstance(deadline_monotonic, bool)
            or not isinstance(deadline_monotonic, (int, float))
            or not math.isfinite(float(deadline_monotonic))
        ):
            raise _failure("video_evidence_invalid")
        remaining = float(deadline_monotonic) - time.monotonic()
        if remaining <= 0 or not flight.event.wait(timeout=remaining):
            raise _failure("video_batch_wall_limit")
    if flight.leader_state is assessment_state:
        return flight.assessment_outcome
    return flight.outcome


def _worker_command() -> list[str]:
    return [
        sys.executable,
        os.fspath(Path(__file__).absolute()),
        VIDEO_SUPERVISED_WORKER_FLAG,
    ]


def _invoke_metadata_worker(
    command: Sequence[str | os.PathLike[str]],
    payload: dict[str, object],
    sensitive_values: tuple[Path, ...],
    limits: SupervisorLimits,
) -> WorkerResult:
    """Narrow injection seam for metadata protocol tests."""
    return run_authenticated_worker(
        command,
        VIDEO_METADATA_OPERATION,
        {},
        cast(Any, payload),
        limits,
        # The interpreter and this module's own path are fixed process
        # identity, not leaked secrets. Without saying so, a vault whose
        # configured interpreter lives INSIDE the trusted root — the layout
        # `check-runtime` recommends — has its own argv[0] flagged as sensitive
        # metadata and every video probe fails `unsafe_worker_process_metadata`.
        # Every PPTX worker already passes this; the video workers did not.
        immutable_process_identity=command[:2],
        sensitive_values=sensitive_values,
        schema_generation=VIDEO_PROBE_SCHEMA_VERSION,
        pipeline_generation=VIDEO_PROBE_PIPELINE_VERSION,
    )


def _run_bounded_metadata_worker(
    artifact: Path,
    *,
    trusted_root: Path | None,
    deadline_monotonic: float | None,
) -> ArtifactMetadataReceipt:
    payload: dict[str, object] = {
        "video_path": os.fspath(artifact),
        "trusted_root": (os.fspath(trusted_root) if trusted_root is not None else None),
    }
    sensitive = (artifact,) if trusted_root is None else (artifact, trusted_root)
    limits = _limits_before_deadline(VIDEO_METADATA_LIMITS, deadline_monotonic)
    deadline_limited = limits.wall_seconds < VIDEO_METADATA_LIMITS.wall_seconds
    try:
        result = _invoke_metadata_worker(_worker_command(), payload, sensitive, limits)
    except SupervisorError as exc:
        if deadline_limited and exc.reason_code == "worker_timeout":
            raise _failure("video_batch_wall_limit") from exc
        raise _supervisor_failure(
            exc,
            timeout_seconds=limits.wall_seconds,
            max_diagnostic_bytes=limits.max_diagnostic_bytes,
        ) from exc
    diagnostics = _validated_diagnostic_receipt(
        result.diagnostics,
        max_diagnostic_bytes=limits.max_diagnostic_bytes,
    )
    if diagnostics.byte_count or diagnostics.truncated:
        raise _failure(
            "video_probe_malformed_result",
            details=_diagnostic_details(diagnostics),
        )
    receipt = _decode_metadata_payload(result.payload)
    if (trusted_root is None) != (receipt.root_generation is None):
        raise _failure("video_probe_malformed_result")
    return receipt


def _probe_generation_singleflight(
    artifact: Path,
    *,
    trusted_root: Path | None,
    receipt: ArtifactMetadataReceipt,
    key: _VideoCacheKey,
    deadline_monotonic: float | None,
    assessment_state: _AssessmentState,
) -> VideoArtifactProbe:
    flight: _GlobalFlight | None = None
    leader = False
    epoch = -1
    while True:
        local_transient: _CachedFailure | None = None
        with _GLOBAL_CACHE_LOCK:
            with assessment_state.lock:
                local_transient = assessment_state.transient_outcomes.get(key.request)
            if local_transient is None:
                cached = _GLOBAL_PROBE_CACHE.get(key)
                if cached is not None:
                    return _outcome_value(cached)
                flight = _GLOBAL_PROBE_FLIGHTS.get(key)
                if flight is None:
                    flight = _GlobalFlight(leader_state=assessment_state)
                    _GLOBAL_PROBE_FLIGHTS[key] = flight
                    leader = True
                    epoch = _GLOBAL_CACHE_EPOCH
                else:
                    leader = False
                    epoch = -1
        if local_transient is not None:
            _raise_cached(local_transient)
        if flight is None:
            raise _failure("video_probe_malformed_result")
        if not leader:
            outcome = _wait_for_flight(
                flight,
                deadline_monotonic,
                assessment_state,
            )
            if outcome is None:
                continue
            return _outcome_value(outcome)
        break
    if flight is None:
        raise _failure("video_probe_malformed_result")
    leader_flight = flight

    outcome: _Outcome | None = None
    try:
        try:
            probe = _compute_generation_outcome(
                artifact,
                trusted_root=trusted_root,
                receipt=receipt,
                key=key,
                deadline_monotonic=deadline_monotonic,
            )
        except VideoEvidenceError as exc:
            outcome = _cached_failure(exc)
        else:
            outcome = probe
        if isinstance(outcome, VideoArtifactProbe) or (
            isinstance(outcome, _CachedFailure)
            and outcome.reason_code in _STABLE_GENERATION_FAILURES
        ):
            with _GLOBAL_CACHE_LOCK:
                if epoch == _GLOBAL_CACHE_EPOCH:
                    stale_keys = [
                        candidate
                        for candidate in _GLOBAL_PROBE_CACHE
                        if candidate.request == key.request and candidate != key
                    ]
                    for stale_key in stale_keys:
                        _GLOBAL_PROBE_CACHE.pop(stale_key, None)
                    _GLOBAL_PROBE_CACHE[key] = outcome
        return _outcome_value(outcome)
    finally:
        with _GLOBAL_CACHE_LOCK:
            current = _GLOBAL_PROBE_FLIGHTS.get(key)
            if current is leader_flight:
                # A transient result belongs to the leader's own assessment and
                # deadline.  Wake waiters without publishing it so each waiter
                # can retry under its own remaining budget.
                shareable = _globally_shareable_outcome(outcome)
                assessment_outcome = outcome
                if isinstance(outcome, _CachedFailure) and shareable is None:
                    with assessment_state.lock:
                        assessment_state.transient_outcomes.setdefault(
                            key.request,
                            outcome,
                        )
                        assessment_outcome = assessment_state.transient_outcomes[
                            key.request
                        ]
                leader_flight.assessment_outcome = assessment_outcome
                leader_flight.outcome = shareable
                _GLOBAL_PROBE_FLIGHTS.pop(key, None)
                leader_flight.event.set()


def _compute_generation_outcome(
    artifact: Path,
    *,
    trusted_root: Path | None,
    receipt: ArtifactMetadataReceipt,
    key: _VideoCacheKey,
    deadline_monotonic: float | None,
) -> VideoArtifactProbe:
    availability = _availability(receipt.generation)
    if availability.state != "local":
        raise _failure(
            "video_cloud_placeholder_unavailable",
            details={
                "availability": availability.to_dict(),
                "reparse_tag": receipt.reparse_tag,
            },
        )
    if receipt.generation.size == 0:
        raise _failure("video_invalid_container")
    if receipt.generation.size > VIDEO_MAX_INPUT_BYTES:
        raise _failure(
            "video_artifact_too_large",
            details={"limit_bytes": VIDEO_MAX_INPUT_BYTES},
        )
    return _run_bounded_video_probe(
        artifact,
        trusted_root=trusted_root,
        receipt=receipt,
        expected_container_family=key.request.expected_container_family,
        deadline_monotonic=deadline_monotonic,
    )


def _invoke_probe_worker(
    command: Sequence[str | os.PathLike[str]],
    expected_generations: Mapping[str, FileGeneration],
    payload: dict[str, object],
    sensitive_values: tuple[Path, ...],
    limits: SupervisorLimits,
) -> WorkerResult:
    """Narrow injection seam for authenticated probe protocol tests."""
    return run_authenticated_worker(
        command,
        VIDEO_PROBE_OPERATION,
        expected_generations,
        cast(Any, payload),
        limits,
        # The interpreter and this module's own path are fixed process
        # identity, not leaked secrets. Without saying so, a vault whose
        # configured interpreter lives INSIDE the trusted root — the layout
        # `check-runtime` recommends — has its own argv[0] flagged as sensitive
        # metadata and every video probe fails `unsafe_worker_process_metadata`.
        # Every PPTX worker already passes this; the video workers did not.
        immutable_process_identity=command[:2],
        sensitive_values=sensitive_values,
        schema_generation=VIDEO_PROBE_SCHEMA_VERSION,
        pipeline_generation=VIDEO_PROBE_PIPELINE_VERSION,
    )


def _run_bounded_video_probe(
    artifact: Path,
    *,
    trusted_root: Path | None,
    receipt: ArtifactMetadataReceipt,
    expected_container_family: ContainerFamily,
    deadline_monotonic: float | None,
) -> VideoArtifactProbe:
    expected_generations = {"video": receipt.generation}
    if receipt.root_generation is not None:
        expected_generations["video_root"] = receipt.root_generation
    payload: dict[str, object] = {
        "video_path": os.fspath(artifact),
        "trusted_root": (os.fspath(trusted_root) if trusted_root is not None else None),
        "expected_container_family": expected_container_family,
        "max_input_bytes": VIDEO_MAX_INPUT_BYTES,
        "max_streams": VIDEO_MAX_STREAMS,
        "ffprobe_stdout_bytes": VIDEO_FFPROBE_STDOUT_BYTES,
        "ffprobe_stderr_bytes": VIDEO_FFPROBE_STDERR_BYTES,
        "digest_chunk_bytes": VIDEO_DIGEST_CHUNK_BYTES,
    }
    sensitive = (artifact,) if trusted_root is None else (artifact, trusted_root)
    limits = _limits_before_deadline(VIDEO_PROBE_LIMITS, deadline_monotonic)
    deadline_limited = limits.wall_seconds < VIDEO_PROBE_LIMITS.wall_seconds
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
            raise _failure("video_batch_wall_limit") from exc
        raise _supervisor_failure(
            exc,
            timeout_seconds=limits.wall_seconds,
            max_diagnostic_bytes=limits.max_diagnostic_bytes,
        ) from exc
    return _decode_probe_payload(
        result.payload,
        receipt=receipt,
        diagnostics=result.diagnostics,
        expected_container_family=expected_container_family,
    )


def _diagnostic_details(receipt: DiagnosticReceipt) -> dict[str, object]:
    return {"diagnostic_receipt": receipt.to_dict()}


def _validated_diagnostic_receipt(
    value: object,
    *,
    max_diagnostic_bytes: int,
) -> DiagnosticReceipt:
    if not isinstance(value, DiagnosticReceipt):
        raise _failure("video_probe_malformed_result")
    if (
        type(value.byte_count) is not int
        or value.byte_count < 0
        or not isinstance(value.sha256, str)
        or _SHA256_RE.fullmatch(value.sha256) is None
        or type(value.truncated) is not bool
        or (not value.truncated and value.byte_count > max_diagnostic_bytes)
    ):
        raise _failure("video_probe_malformed_result")
    return value


def _closed_generation_names(details: Mapping[str, object]) -> list[str]:
    raw = details.get("generation_names")
    if not isinstance(raw, list):
        return []
    names = sorted(
        {
            name
            for name in raw
            if isinstance(name, str) and name in _VIDEO_GENERATION_NAMES
        }
    )
    return names


def _supervisor_failure(
    exc: SupervisorError,
    *,
    timeout_seconds: float,
    max_diagnostic_bytes: int,
) -> VideoEvidenceError:
    diagnostics = _validated_diagnostic_receipt(
        exc.diagnostics,
        max_diagnostic_bytes=max_diagnostic_bytes,
    )

    def details(**values: object) -> dict[str, object]:
        closed = dict(values)
        if diagnostics.byte_count or diagnostics.truncated:
            closed.update(_diagnostic_details(diagnostics))
        return closed

    reason = exc.reason_code
    if reason == "worker_generation_changed":
        names = _closed_generation_names(exc.details)
        return _failure(
            "video_artifact_changed",
            details=details(**({"generation_names": names} if names else {})),
        )
    if reason == "worker_timeout":
        return _failure(
            "video_probe_timeout",
            details=details(timeout_seconds=timeout_seconds),
        )
    if reason == "worker_monitor_unavailable":
        if exc.details.get("dependency") == "psutil":
            return _failure(
                "video_dependency_unavailable",
                details=details(dependency="psutil"),
            )
        return _failure("video_probe_monitor_unavailable", details=details())
    if reason == "worker_monitor_identity_changed":
        return _failure(
            "video_probe_monitor_identity_changed",
            details=details(supervisor_reason_code=reason),
        )
    if reason in {
        "worker_containment_unavailable",
        "worker_process_tree_leak",
        "worker_cleanup_failed",
    }:
        return _failure(
            "video_probe_containment_unavailable",
            details=details(supervisor_reason_code=reason),
        )
    if reason in {
        "worker_memory_limit_exceeded",
        "worker_process_limit_exceeded",
        "worker_diagnostic_limit_exceeded",
    }:
        return _failure(
            "video_probe_resource_unavailable",
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
            "video_probe_start_failure",
            details=details(supervisor_reason_code=reason),
        )
    if reason == "worker_output_limit_exceeded":
        return _failure(
            "video_probe_result_oversized",
            details=details(supervisor_reason_code=reason),
        )
    if reason == "worker_input_limit_exceeded":
        return _failure(
            "video_probe_request_oversized",
            details=details(supervisor_reason_code=reason),
        )
    if reason in {
        "worker_exit",
        "worker_diagnostic_read_failed",
        "worker_output_read_failed",
    }:
        return _failure(
            "video_probe_crash",
            details=details(supervisor_reason_code=reason),
        )
    return _failure(
        "video_probe_malformed_result",
        details=details(supervisor_reason_code=reason),
    )


def _diagnostic_from_mapping(value: object, *, limit: int) -> DiagnosticReceipt:
    if not isinstance(value, Mapping) or set(value) != {
        "byte_count",
        "sha256",
        "truncated",
    }:
        raise _failure("video_probe_malformed_result")
    receipt = DiagnosticReceipt(
        byte_count=cast(Any, value.get("byte_count")),
        sha256=cast(Any, value.get("sha256")),
        truncated=cast(Any, value.get("truncated")),
    )
    return _validated_diagnostic_receipt(
        receipt,
        max_diagnostic_bytes=limit,
    )


def _validated_child_failure_details(
    reason_code: str,
    raw: object,
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise _failure("video_probe_malformed_result")
    keys = set(raw)
    details: dict[str, object] = {}
    if reason_code == "video_dependency_unavailable":
        if keys != {"dependency"} or raw.get("dependency") != "ffprobe":
            raise _failure("video_probe_malformed_result")
        return {"dependency": "ffprobe"}
    if reason_code == "video_stream_limit":
        if keys != {"max_streams"} or raw.get("max_streams") != VIDEO_MAX_STREAMS:
            raise _failure("video_probe_malformed_result")
        return {"max_streams": VIDEO_MAX_STREAMS}
    if reason_code in {
        "video_invalid_container",
        "video_no_video_stream",
        "video_duration_unavailable",
    }:
        if keys:
            raise _failure("video_probe_malformed_result")
        return {}
    if reason_code == "video_artifact_unavailable":
        if keys not in (set(), {"exception_type"}):
            raise _failure("video_probe_malformed_result")
    elif reason_code == "video_parser_repair_required":
        if keys != {"diagnostic_receipt"}:
            raise _failure("video_probe_malformed_result")
    elif reason_code == "video_parser_rejected":
        if keys not in (
            set(),
            {"exception_type"},
            {"diagnostic_receipt"},
        ):
            raise _failure("video_probe_malformed_result")
    elif reason_code == "video_probe_resource_unavailable":
        if keys not in (
            {"exception_type"},
            {"limit_kind", "limit_bytes"},
        ):
            raise _failure("video_probe_malformed_result")
    else:
        raise _failure("video_probe_malformed_result")

    exception_type = raw.get("exception_type")
    if exception_type is not None:
        if (
            not isinstance(exception_type, str)
            or _EXCEPTION_TYPE_RE.fullmatch(exception_type) is None
        ):
            raise _failure("video_probe_malformed_result")
        details["exception_type"] = exception_type
    diagnostic_value = raw.get("diagnostic_receipt")
    if diagnostic_value is not None:
        receipt = _diagnostic_from_mapping(
            diagnostic_value,
            limit=VIDEO_FFPROBE_STDERR_BYTES,
        )
        if receipt.byte_count == 0 or receipt.truncated:
            raise _failure("video_probe_malformed_result")
        details["diagnostic_receipt"] = receipt.to_dict()
    limit_kind = raw.get("limit_kind")
    limit_bytes = raw.get("limit_bytes")
    if limit_kind is not None:
        expected_limits = {
            "ffprobe_stdout": VIDEO_FFPROBE_STDOUT_BYTES,
            "ffprobe_stderr": VIDEO_FFPROBE_STDERR_BYTES,
        }
        if (
            not isinstance(limit_kind, str)
            or limit_kind not in expected_limits
            or type(limit_bytes) is not int
            or limit_bytes != expected_limits[limit_kind]
        ):
            raise _failure("video_probe_malformed_result")
        details["limit_kind"] = limit_kind
        details["limit_bytes"] = limit_bytes
    return details


def _decode_probe_payload(
    payload: object,
    *,
    receipt: ArtifactMetadataReceipt,
    diagnostics: DiagnosticReceipt,
    expected_container_family: ContainerFamily,
) -> VideoArtifactProbe:
    diagnostics = _validated_diagnostic_receipt(
        diagnostics,
        max_diagnostic_bytes=VIDEO_PROBE_LIMITS.max_diagnostic_bytes,
    )
    if not isinstance(payload, Mapping):
        raise _failure("video_probe_malformed_result")
    if payload.get("schema_version") != VIDEO_PROBE_SCHEMA_VERSION:
        raise _failure("video_probe_malformed_result")
    if payload.get("status") == "unavailable":
        if set(payload) != {"schema_version", "status", "reason_code", "details"}:
            raise _failure("video_probe_malformed_result")
        reason = payload.get("reason_code")
        if not isinstance(reason, str) or reason not in _CHILD_FAILURE_REASONS:
            raise _failure("video_probe_malformed_result")
        details = _validated_child_failure_details(reason, payload.get("details"))
        if diagnostics.byte_count or diagnostics.truncated:
            details.update(_diagnostic_details(diagnostics))
        raise _failure(reason, details=details)

    expected_fields = {
        "schema_version",
        "status",
        "source_sha256",
        "source_size_bytes",
        "duration_seconds",
        "duration_source",
        "container_family",
        "stream_count",
        "video_stream_count",
        "audio_stream_count",
        "attached_picture_count",
        "other_stream_count",
    }
    if payload.get("status") != "available" or set(payload) != expected_fields:
        raise _failure("video_probe_malformed_result")
    source_sha256 = payload.get("source_sha256")
    source_size = payload.get("source_size_bytes")
    duration = payload.get("duration_seconds")
    duration_source = payload.get("duration_source")
    container_family = payload.get("container_family")
    counts = [
        payload.get("stream_count"),
        payload.get("video_stream_count"),
        payload.get("audio_stream_count"),
        payload.get("attached_picture_count"),
        payload.get("other_stream_count"),
    ]
    if (
        not isinstance(source_sha256, str)
        or _SHA256_RE.fullmatch(source_sha256) is None
        or type(source_size) is not int
        or source_size != receipt.generation.size
        or not 1 <= source_size <= VIDEO_MAX_INPUT_BYTES
        or isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(float(duration))
        or float(duration) <= 0
        or duration_source not in {"format", "stream"}
        or container_family != expected_container_family
        or any(type(count) is not int for count in counts)
    ):
        raise _failure("video_probe_malformed_result")
    stream_count, video_count, audio_count, attached_count, other_count = cast(
        list[int], counts
    )
    if (
        not 1 <= stream_count <= VIDEO_MAX_STREAMS
        or video_count < 1
        or min(audio_count, attached_count, other_count) < 0
        or video_count + audio_count + attached_count + other_count != stream_count
    ):
        raise _failure("video_probe_malformed_result")
    if diagnostics.byte_count or diagnostics.truncated:
        raise _failure(
            "video_probe_malformed_result",
            details=_diagnostic_details(diagnostics),
        )
    return VideoArtifactProbe(
        generation=receipt.generation,
        root_generation=receipt.root_generation,
        availability=_availability(receipt.generation),
        source_sha256=source_sha256,
        source_size_bytes=source_size,
        duration_seconds=float(duration),
        duration_source=cast(DurationSource, duration_source),
        container_family=cast(ContainerFamily, container_family),
        stream_count=stream_count,
        video_stream_count=video_count,
        audio_stream_count=audio_count,
        attached_picture_count=attached_count,
        other_stream_count=other_count,
        parser_diagnostics=diagnostics,
    )


def _worker_generation_change(*names: str) -> SupervisorError:
    closed = sorted({name for name in names if name in _VIDEO_GENERATION_NAMES})
    return SupervisorError(
        "worker_generation_changed",
        cast(Mapping[str, JsonValue], {"generation_names": closed}),
    )


def _metadata_receipt_in_probe_worker(
    artifact: Path,
    trusted_root: Path | None,
) -> ArtifactMetadataReceipt:
    try:
        return inspect_metadata_generation(
            artifact,
            trusted_root=trusted_root,
            reparse_point_attribute=VIDEO_WINDOWS_REPARSE_POINT_ATTRIBUTE,
            cloud_reparse_tags=VIDEO_WINDOWS_CLOUD_REPARSE_TAGS,
        )
    except (ArtifactMetadataMalformed, ArtifactMetadataUnavailable) as exc:
        names = ("video",) if trusted_root is None else ("video", "video_root")
        raise _worker_generation_change(*names) from exc


def _probe_payload_values(
    payload: Mapping[str, object],
) -> tuple[Path, Path | None, ContainerFamily]:
    if set(payload) != {
        "video_path",
        "trusted_root",
        "expected_container_family",
        "max_input_bytes",
        "max_streams",
        "ffprobe_stdout_bytes",
        "ffprobe_stderr_bytes",
        "digest_chunk_bytes",
    }:
        raise SupervisorError("invalid_worker_request")
    root_value = payload.get("trusted_root")
    if root_value is not None and not isinstance(root_value, str):
        raise SupervisorError("invalid_worker_request")
    artifact, trusted_root = _worker_bound_paths(payload.get("video_path"), root_value)
    expected_family = payload.get("expected_container_family")
    if expected_family not in {"iso_bmff", "matroska_webm"}:
        raise SupervisorError("invalid_worker_request")
    expected_constants = {
        "max_input_bytes": VIDEO_MAX_INPUT_BYTES,
        "max_streams": VIDEO_MAX_STREAMS,
        "ffprobe_stdout_bytes": VIDEO_FFPROBE_STDOUT_BYTES,
        "ffprobe_stderr_bytes": VIDEO_FFPROBE_STDERR_BYTES,
        "digest_chunk_bytes": VIDEO_DIGEST_CHUNK_BYTES,
    }
    if any(payload.get(name) != value for name, value in expected_constants.items()):
        raise SupervisorError("invalid_worker_request")
    return artifact, trusted_root, cast(ContainerFamily, expected_family)


def _dispatch_supervised_worker(
    request: WorkerRequest,
) -> tuple[dict[str, object], dict[str, FileGeneration]]:
    if request.schema_generation != VIDEO_PROBE_SCHEMA_VERSION:
        raise SupervisorError("invalid_worker_request")
    if request.pipeline_generation != VIDEO_PROBE_PIPELINE_VERSION:
        raise SupervisorError("invalid_worker_request")
    if not isinstance(request.payload, Mapping):
        raise SupervisorError("invalid_worker_request")
    if request.operation == VIDEO_METADATA_OPERATION:
        if (
            request.limit_profile_id != VIDEO_METADATA_LIMITS.profile_id
            or request.expected_generations
        ):
            raise SupervisorError("invalid_worker_request")
        return _metadata_child(request.payload), {}
    if request.operation != VIDEO_PROBE_OPERATION:
        raise SupervisorError("invalid_worker_operation")
    if request.limit_profile_id != VIDEO_PROBE_LIMITS.profile_id:
        raise SupervisorError("invalid_worker_request")

    artifact, trusted_root, expected_family = _probe_payload_values(request.payload)
    expected_names = {"video"}
    if trusted_root is not None:
        expected_names.add("video_root")
    if set(request.expected_generations) != expected_names:
        raise SupervisorError("invalid_worker_request")
    before = _metadata_receipt_in_probe_worker(artifact, trusted_root)
    observed: dict[str, FileGeneration] = {"video": before.generation}
    if before.root_generation is not None:
        observed["video_root"] = before.root_generation
    changed_before = sorted(
        name
        for name in observed
        if observed[name] != request.expected_generations[name]
    )
    if changed_before:
        raise _worker_generation_change(*changed_before)
    if _availability(before.generation).state != "local":
        raise _worker_generation_change("video")
    if before.generation.size <= 0 or before.generation.size > VIDEO_MAX_INPUT_BYTES:
        raise _worker_generation_change("video")

    media_facts: dict[str, object] | None = None
    media_failure: VideoEvidenceError | None = None
    digest: str | None = None
    digest_failure: VideoEvidenceError | None = None
    preparation_failure: VideoEvidenceError | None = None
    try:
        with _prepared_video_source(artifact, before.generation) as prepared:
            try:
                media_facts = _probe_media_with_ffprobe(
                    prepared.probe_artifact,
                    expected_container_family=expected_family,
                )
            except MemoryError:
                media_failure = _failure(
                    "video_probe_resource_unavailable",
                    details={"exception_type": "MemoryError"},
                )
            except VideoEvidenceError as exc:
                media_failure = exc

            middle = _metadata_receipt_in_probe_worker(artifact, trusted_root)
            _require_same_receipt(before, middle)
            _require_descriptor_generation(
                prepared.source_descriptor,
                before.generation,
            )
            if media_failure is None:
                try:
                    digest = _digest_exact_generation(
                        prepared.probe_artifact,
                        prepared.probe_generation,
                        source_descriptor=prepared.probe_descriptor,
                    )
                except MemoryError:
                    digest_failure = _failure(
                        "video_probe_resource_unavailable",
                        details={"exception_type": "MemoryError"},
                    )
                except VideoEvidenceError as exc:
                    digest_failure = exc
            _require_descriptor_generation(
                prepared.source_descriptor,
                before.generation,
            )
    except MemoryError:
        preparation_failure = _failure(
            "video_probe_resource_unavailable",
            details={"exception_type": "MemoryError"},
        )
    except VideoEvidenceError as exc:
        preparation_failure = exc

    after = _metadata_receipt_in_probe_worker(artifact, trusted_root)
    _require_same_receipt(before, after)
    failure = preparation_failure or media_failure or digest_failure
    if failure is not None:
        reason = (
            failure.reason_code
            if failure.reason_code in _CHILD_FAILURE_REASONS
            else "video_parser_rejected"
        )
        return _unavailable_payload(reason, failure.details), observed
    if media_facts is None or digest is None:
        raise SupervisorError("invalid_worker_response")
    payload = {
        "schema_version": VIDEO_PROBE_SCHEMA_VERSION,
        "status": "available",
        "source_sha256": digest,
        "source_size_bytes": before.generation.size,
        **media_facts,
    }
    return payload, observed


def _require_same_receipt(
    expected: ArtifactMetadataReceipt,
    observed: ArtifactMetadataReceipt,
) -> None:
    changed: list[str] = []
    if observed.generation != expected.generation:
        changed.append("video")
    if observed.root_generation != expected.root_generation:
        changed.append("video_root")
    if observed.reparse_tag != expected.reparse_tag and "video" not in changed:
        changed.append("video")
    if changed:
        raise _worker_generation_change(*changed)


def _unavailable_payload(
    reason_code: str,
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": VIDEO_PROBE_SCHEMA_VERSION,
        "status": "unavailable",
        "reason_code": reason_code,
        "details": dict(details or {}),
    }


def _source_open_flags() -> int:
    return (
        os.O_RDONLY
        | int(getattr(os, "O_BINARY", 0))
        | int(getattr(os, "O_CLOEXEC", 0))
        | int(getattr(os, "O_NOFOLLOW", 0))
    )


def _open_source_descriptor(
    artifact: Path,
    expected_generation: FileGeneration,
) -> int:
    try:
        descriptor = os.open(artifact, _source_open_flags())
    except OSError as exc:
        raise _failure(
            "video_artifact_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    try:
        _require_descriptor_generation(descriptor, expected_generation)
    except (SupervisorError, VideoEvidenceError):
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    return descriptor


def _require_descriptor_generation(
    descriptor: int,
    expected_generation: FileGeneration,
) -> None:
    try:
        observed = FileGeneration.from_stat(os.fstat(descriptor))
    except OSError as exc:
        raise _failure(
            "video_artifact_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    if observed != expected_generation:
        raise _worker_generation_change("video")


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("private video snapshot write made no progress")
        remaining = remaining[written:]


def _copy_source_snapshot(
    source_descriptor: int,
    snapshot_descriptor: int,
    expected_generation: FileGeneration,
) -> FileGeneration:
    try:
        os.lseek(source_descriptor, 0, os.SEEK_SET)
        os.lseek(snapshot_descriptor, 0, os.SEEK_SET)
    except OSError as exc:
        raise _failure(
            "video_artifact_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    total = 0
    while True:
        try:
            chunk = os.read(source_descriptor, VIDEO_DIGEST_CHUNK_BYTES)
        except OSError as exc:
            raise _failure(
                "video_artifact_unavailable",
                details={"exception_type": type(exc).__name__},
            ) from exc
        if not chunk:
            break
        total += len(chunk)
        if total > expected_generation.size:
            raise _worker_generation_change("video")
        try:
            _write_all(snapshot_descriptor, chunk)
        except OSError as exc:
            raise _failure(
                "video_probe_resource_unavailable",
                details={"exception_type": type(exc).__name__},
            ) from exc
    _require_descriptor_generation(source_descriptor, expected_generation)
    if total != expected_generation.size:
        raise _worker_generation_change("video")
    try:
        snapshot_generation = FileGeneration.from_stat(os.fstat(snapshot_descriptor))
    except OSError as exc:
        raise _failure(
            "video_probe_resource_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    if snapshot_generation.size != expected_generation.size:
        raise _failure("video_probe_resource_unavailable")
    return snapshot_generation


@contextmanager
def _prepared_video_source(
    artifact: Path,
    expected_generation: FileGeneration,
) -> Iterator[_PreparedVideoSource]:
    source_descriptor = _open_source_descriptor(artifact, expected_generation)
    probe_descriptor = source_descriptor
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    try:
        try:
            temporary_directory = tempfile.TemporaryDirectory(
                prefix="speaker-toolkit-video-",
                ignore_cleanup_errors=True,
            )
            snapshot = Path(temporary_directory.name) / f"source{artifact.suffix}"
            probe_descriptor = os.open(
                snapshot,
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | int(getattr(os, "O_BINARY", 0))
                | int(getattr(os, "O_CLOEXEC", 0)),
                0o600,
            )
        except OSError as exc:
            raise _failure(
                "video_probe_resource_unavailable",
                details={"exception_type": type(exc).__name__},
            ) from exc
        snapshot_generation = _copy_source_snapshot(
            source_descriptor,
            probe_descriptor,
            expected_generation,
        )
        prepared = _PreparedVideoSource(
            source_descriptor=source_descriptor,
            probe_descriptor=probe_descriptor,
            probe_artifact=snapshot,
            probe_generation=snapshot_generation,
        )
        yield prepared
    finally:
        for descriptor in {probe_descriptor, source_descriptor}:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_directory is not None:
            temporary_directory.cleanup()


def _digest_open_descriptor(
    descriptor: int,
    expected_generation: FileGeneration,
) -> str:
    _require_descriptor_generation(descriptor, expected_generation)
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
    except OSError as exc:
        raise _failure(
            "video_artifact_unavailable",
            details={"exception_type": type(exc).__name__},
        ) from exc
    digest = hashlib.sha256()
    total = 0
    while True:
        try:
            chunk = os.read(descriptor, VIDEO_DIGEST_CHUNK_BYTES)
        except OSError as exc:
            raise _failure(
                "video_artifact_unavailable",
                details={"exception_type": type(exc).__name__},
            ) from exc
        if not chunk:
            break
        total += len(chunk)
        if total > expected_generation.size:
            raise _worker_generation_change("video")
        digest.update(chunk)
    _require_descriptor_generation(descriptor, expected_generation)
    if total != expected_generation.size:
        raise _worker_generation_change("video")
    return digest.hexdigest()


def _digest_exact_generation(
    artifact: Path,
    expected_generation: FileGeneration,
    *,
    source_descriptor: int | None = None,
) -> str:
    if source_descriptor is not None:
        return _digest_open_descriptor(source_descriptor, expected_generation)
    descriptor = _open_source_descriptor(artifact, expected_generation)
    try:
        return _digest_open_descriptor(descriptor, expected_generation)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _ffprobe_command(executable: str, artifact: Path) -> list[str]:
    return [
        executable,
        "-v",
        "warning",
        "-show_entries",
        (
            "format=format_name,duration:"
            "stream=index,codec_type,duration:stream_disposition=attached_pic"
        ),
        "-of",
        "json",
        os.fspath(artifact),
    ]


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            return
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            return


def _run_ffprobe(artifact: Path) -> tuple[bytes, DiagnosticReceipt, int]:
    executable = shutil.which("ffprobe")
    if executable is None:
        raise _failure(
            "video_dependency_unavailable",
            details={"dependency": "ffprobe"},
        )
    try:
        process = subprocess.Popen(
            _ffprobe_command(executable, artifact),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            close_fds=True,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise _failure(
            "video_dependency_unavailable",
            details={"dependency": "ffprobe"},
        ) from exc
    if process.stdout is None or process.stderr is None:
        _stop_process(process)
        raise _failure(
            "video_parser_rejected",
            details={"exception_type": "PipeSetupError"},
        )
    stdout_reader = _PipeDrainer(
        cast(BinaryIO, process.stdout), VIDEO_FFPROBE_STDOUT_BYTES
    )
    stderr_reader = _PipeDrainer(
        cast(BinaryIO, process.stderr), VIDEO_FFPROBE_STDERR_BYTES
    )
    stdout_reader.start()
    stderr_reader.start()
    try:
        while process.poll() is None:
            if stdout_reader.overflowed or stderr_reader.overflowed:
                _stop_process(process)
                break
            time.sleep(0.01)
        exit_code = process.wait()
        stdout_reader.join(1)
        stderr_reader.join(1)
        if stdout_reader.alive or stderr_reader.alive:
            stdout_reader.close()
            stderr_reader.close()
            stdout_reader.join(1)
            stderr_reader.join(1)
        if stdout_reader.overflowed:
            raise _failure(
                "video_probe_resource_unavailable",
                details={
                    "limit_kind": "ffprobe_stdout",
                    "limit_bytes": VIDEO_FFPROBE_STDOUT_BYTES,
                },
            )
        if stderr_reader.overflowed:
            raise _failure(
                "video_probe_resource_unavailable",
                details={
                    "limit_kind": "ffprobe_stderr",
                    "limit_bytes": VIDEO_FFPROBE_STDERR_BYTES,
                },
            )
        if stdout_reader.failed or stderr_reader.failed:
            raise _failure(
                "video_parser_rejected",
                details={"exception_type": "PipeReadError"},
            )
        return stdout_reader.data, stderr_reader.receipt, exit_code
    finally:
        _stop_process(process)
        stdout_reader.close()
        stderr_reader.close()


def _reject_json_constant(_value: str) -> NoReturn:
    raise ValueError("non-finite JSON number")


def _decode_ffprobe_document(raw: bytes) -> Mapping[str, object]:
    try:
        document = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise _failure(
            "video_parser_rejected",
            details={"exception_type": type(exc).__name__},
        ) from exc
    if not isinstance(document, Mapping):
        raise _failure("video_parser_rejected")
    return document


def _positive_finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = float(value)
    except (OverflowError, ValueError):
        return None
    return parsed if parsed > 0 and math.isfinite(parsed) else None


def _container_family(format_name: object) -> ContainerFamily | None:
    if not isinstance(format_name, str) or not format_name:
        return None
    names = frozenset(part.strip().casefold() for part in format_name.split(","))
    if names & _MATROSKA_FORMAT_NAMES:
        return "matroska_webm"
    if names & _ISO_BMFF_FORMAT_NAMES:
        return "iso_bmff"
    return None


def _attached_picture(stream: Mapping[str, object]) -> bool:
    disposition = stream.get("disposition")
    if disposition is None:
        return False
    if not isinstance(disposition, Mapping):
        raise _failure("video_parser_rejected")
    value = disposition.get("attached_pic", 0)
    if type(value) is not int or value not in {0, 1}:
        raise _failure("video_parser_rejected")
    return value == 1


def _probe_media_with_ffprobe(
    artifact: Path,
    *,
    expected_container_family: ContainerFamily,
) -> dict[str, object]:
    raw_stdout, stderr_receipt, exit_code = _run_ffprobe(artifact)
    if exit_code != 0:
        details = (
            _diagnostic_details(stderr_receipt) if stderr_receipt.byte_count else {}
        )
        raise _failure("video_parser_rejected", details=details)
    if stderr_receipt.byte_count:
        raise _failure(
            "video_parser_repair_required",
            details=_diagnostic_details(stderr_receipt),
        )
    document = _decode_ffprobe_document(raw_stdout)
    if set(document) - {"format", "streams", "programs", "stream_groups"}:
        raise _failure("video_parser_rejected")
    if document.get("programs", []) != [] or document.get("stream_groups", []) != []:
        raise _failure("video_parser_rejected")
    raw_format = document.get("format")
    raw_streams = document.get("streams")
    if not isinstance(raw_format, Mapping) or not isinstance(raw_streams, list):
        raise _failure("video_invalid_container")
    family = _container_family(raw_format.get("format_name"))
    if family != expected_container_family:
        raise _failure("video_invalid_container")
    if len(raw_streams) > VIDEO_MAX_STREAMS:
        raise _failure(
            "video_stream_limit",
            details={"max_streams": VIDEO_MAX_STREAMS},
        )

    video_count = 0
    audio_count = 0
    attached_count = 0
    other_count = 0
    stream_durations: list[float] = []
    for stream in raw_streams:
        if not isinstance(stream, Mapping):
            raise _failure("video_parser_rejected")
        codec_type = stream.get("codec_type")
        if not isinstance(codec_type, str):
            raise _failure("video_parser_rejected")
        attached = codec_type == "video" and _attached_picture(stream)
        if attached:
            attached_count += 1
        elif codec_type == "video":
            video_count += 1
        elif codec_type == "audio":
            audio_count += 1
        else:
            other_count += 1
        if codec_type == "audio" or (codec_type == "video" and not attached):
            duration = _positive_finite_number(stream.get("duration"))
            if duration is not None:
                stream_durations.append(duration)
    if video_count == 0:
        raise _failure("video_no_video_stream")
    format_duration = _positive_finite_number(raw_format.get("duration"))
    if format_duration is not None:
        duration_seconds = format_duration
        duration_source: DurationSource = "format"
    elif stream_durations:
        duration_seconds = max(stream_durations)
        duration_source = "stream"
    else:
        raise _failure("video_duration_unavailable")
    return {
        "duration_seconds": duration_seconds,
        "duration_source": duration_source,
        "container_family": family,
        "stream_count": len(raw_streams),
        "video_stream_count": video_count,
        "audio_stream_count": audio_count,
        "attached_picture_count": attached_count,
        "other_stream_count": other_count,
    }


def probe_video_artifact(
    path: str | os.PathLike[str],
    *,
    trusted_root: str | os.PathLike[str] | None = None,
    deadline_monotonic: float | None = None,
    assessment: VideoEvidenceAssessment | None = None,
) -> VideoArtifactProbe:
    """Return bounded video evidence, optionally shared within one operation."""
    selected = assessment or VideoEvidenceAssessment()
    if not isinstance(selected, VideoEvidenceAssessment):
        raise _failure("video_evidence_invalid")
    return selected.probe(
        path,
        trusted_root=trusted_root,
        deadline_monotonic=deadline_monotonic,
    )


def _run_supervised_worker_child() -> int:
    request = read_worker_request(max_input_bytes=VIDEO_METADATA_LIMITS.max_input_bytes)
    protocol_output = isolate_protocol_output()
    try:
        try:
            payload, observed = _dispatch_supervised_worker(request)
            write_worker_response(
                request,
                payload=cast(JsonValue, payload),
                observed_generations=observed,
                stream=protocol_output,
                max_output_bytes=VIDEO_PROBE_LIMITS.max_output_bytes,
            )
        except SupervisorError as exc:
            write_worker_response(
                request,
                error=SupervisorError(exc.reason_code, exc.details),
                observed_generations=request.expected_generations,
                stream=protocol_output,
                max_output_bytes=VIDEO_PROBE_LIMITS.max_output_bytes,
            )
    finally:
        protocol_output.close()
    return 0


def _main() -> int:
    if sys.argv[1:] != [VIDEO_SUPERVISED_WORKER_FLAG]:
        raise SystemExit("video_evidence.py is a library")
    try:
        return _run_supervised_worker_child()
    except SupervisorError as exc:
        print(
            f"video supervised worker failed: {exc.reason_code}",
            file=sys.stderr,
            flush=True,
        )
        return 2
    # The supervisor owns this process boundary and converts a nonzero exit to
    # one closed crash reason. No traceback, artifact path, or parser output may
    # cross it. outer-boundary-process-contract.
    except Exception:  # noqa: BLE001
        print(
            "video supervised worker failed: unexpected_error",
            file=sys.stderr,
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "VIDEO_DIGEST_CHUNK_BYTES",
    "VIDEO_FFPROBE_STDERR_BYTES",
    "VIDEO_FFPROBE_STDOUT_BYTES",
    "VIDEO_MAX_INPUT_BYTES",
    "VIDEO_MAX_STREAMS",
    "VIDEO_METADATA_LIMITS",
    "VIDEO_PROBE_LIMITS",
    "VIDEO_PROBE_PIPELINE_VERSION",
    "VIDEO_PROBE_SCHEMA_VERSION",
    "VIDEO_SUPERVISED_WORKER_FLAG",
    "VideoArtifactProbe",
    "VideoEvidenceAssessment",
    "VideoEvidenceError",
    "clear_video_artifact_probe_cache",
    "probe_video_artifact",
]

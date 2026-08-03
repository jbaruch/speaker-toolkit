#!/usr/bin/env python3
"""Authenticated supervision for trusted workers parsing untrusted artifacts.

The worker command is intentionally constant.  Requests, artifact names, and the
per-invocation authentication key travel only through a framed stdin pipe.  A
worker must return one framed, HMAC-authenticated response on stdout.

This module is deliberately independent of PPTX parsing.  Callers provide an
operation name and JSON payload, while worker entry points use
``read_worker_request`` and ``write_worker_response`` to implement the operation.
"""

from __future__ import annotations

import base64
import binascii
import ctypes
import hashlib
import hmac
import importlib
import json
import math
import os
import re
import secrets
import signal
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Final, TypeAlias, cast


PROTOCOL_VERSION: Final = "artifact-worker-v1"
PSUTIL_REQUIRED_VERSION: Final = "7.2.2"
_FRAME_HEADER_BYTES: Final = 4
_REQUEST_ID_BYTES: Final = 32
_AUTH_KEY_BYTES: Final = 32
_DIGEST_HEX_LENGTH: Final = 64
_MAX_JSON_INTEGER_DIGITS: Final = 32
_MAX_BINDINGS_BYTES: Final = 64 * 1024
_MAX_BINDINGS_B64_CHARS: Final = ((_MAX_BINDINGS_BYTES + 2) // 3) * 4
_MAX_OUTER_NAME_CHARS: Final = 64
_MISSING: Final = object()
_OPERATION_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_BINDING_RE: Final = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_REASON_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_GENERATION_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_PROFILE_RE: Final = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_WINDOWS_PATH_RE: Final = re.compile(
    r"(?i)(?:[a-z]:[\\/](?:[^\s\x00<>:\"|?*]+[\\/]?)+|"
    r"\\\\[^\s\\/]+[\\/][^\s]+)"
)
_POSIX_PATH_RE: Final = re.compile(r"(?<![A-Za-z0-9_.-])/(?:[^\s\x00/]+/)*[^\s\x00/]*")

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

# The supervisor is imported by shared ingress modules used by transcript- and
# PDF-only runs.  Keep the optional PPTX-lane dependency lazy so its absence
# disables worker supervision without making those independent lanes
# unimportable.  Tests may also inject a psutil-compatible module here.
psutil: Any | None = None


class SupervisorError(RuntimeError):
    """A stable, path-free failure emitted by the supervisor."""

    def __init__(
        self,
        reason_code: str,
        details: Mapping[str, JsonValue] | None = None,
        diagnostics: DiagnosticReceipt | None = None,
    ) -> None:
        if not _REASON_RE.fullmatch(reason_code):
            raise ValueError("invalid supervisor reason code")
        self.reason_code = reason_code
        self.details = dict(details or {})
        self.diagnostics = diagnostics or DiagnosticReceipt.empty()
        super().__init__(reason_code)


@dataclass(frozen=True)
class FileGeneration:
    """Path-free identity snapshot used to bind requests and responses."""

    size: int
    mtime_ns: int
    ctime_ns: int
    device: int
    inode: int
    mode: int
    flags: int | None = None
    file_attributes: int | None = None

    @classmethod
    def from_stat(cls, value: os.stat_result) -> FileGeneration:
        return cls(
            size=int(value.st_size),
            mtime_ns=int(value.st_mtime_ns),
            ctime_ns=int(value.st_ctime_ns),
            device=int(value.st_dev),
            inode=int(value.st_ino),
            mode=int(value.st_mode),
            flags=_optional_stat_int(value, "st_flags"),
            file_attributes=_optional_stat_int(value, "st_file_attributes"),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> FileGeneration:
        expected = {
            "size",
            "mtime_ns",
            "ctime_ns",
            "device",
            "inode",
            "mode",
            "flags",
            "file_attributes",
        }
        if set(value) != expected:
            raise ValueError("invalid file generation fields")
        return cls(
            size=_strict_int(value["size"], "size"),
            mtime_ns=_strict_int(value["mtime_ns"], "mtime_ns"),
            ctime_ns=_strict_int(value["ctime_ns"], "ctime_ns"),
            device=_strict_int(value["device"], "device"),
            inode=_strict_int(value["inode"], "inode"),
            mode=_strict_int(value["mode"], "mode"),
            flags=_optional_strict_int(value["flags"], "flags"),
            file_attributes=_optional_strict_int(
                value["file_attributes"], "file_attributes"
            ),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "ctime_ns": self.ctime_ns,
            "device": self.device,
            "inode": self.inode,
            "mode": self.mode,
            "flags": self.flags,
            "file_attributes": self.file_attributes,
        }


@dataclass(frozen=True)
class SupervisorLimits:
    """Protocol limits plus platform process and sampled-resource limits.

    Windows Job Objects provide a kernel process-tree boundary.  POSIX workers
    run in a dedicated process group and known descendants are sampled and
    cleaned up, but this is not a portable sandbox against a worker that
    deliberately creates a new session.
    """

    profile_id: str = "artifact-default-v1"
    wall_seconds: float = 30.0
    max_memory_bytes: int = 4 * 1024 * 1024 * 1024
    max_input_bytes: int = 64 * 1024
    max_output_bytes: int = 1024 * 1024
    max_diagnostic_bytes: int = 64 * 1024
    max_processes: int = 16
    sample_interval_seconds: float = 0.05
    cleanup_seconds: float = 2.0

    def __post_init__(self) -> None:
        if not _PROFILE_RE.fullmatch(self.profile_id):
            raise ValueError("invalid supervisor limit profile id")
        integer_limits = (
            self.max_memory_bytes,
            self.max_input_bytes,
            self.max_output_bytes,
            self.max_diagnostic_bytes,
            self.max_processes,
        )
        if any(type(value) is not int or value <= 0 for value in integer_limits):
            raise ValueError("integer supervisor limits must be positive integers")
        duration_limits = (
            self.wall_seconds,
            self.sample_interval_seconds,
            self.cleanup_seconds,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
            or not math.isfinite(value)
            for value in duration_limits
        ):
            raise ValueError("duration supervisor limits must be positive and finite")


@dataclass(frozen=True)
class WorkerCredentials:
    """Per-invocation credentials; never place these in argv or environment."""

    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key, bytes) or len(self.key) != _AUTH_KEY_BYTES:
            raise ValueError("worker authentication key must contain 32 bytes")

    @classmethod
    def generate(cls) -> WorkerCredentials:
        return cls(secrets.token_bytes(_AUTH_KEY_BYTES))


@dataclass(frozen=True)
class WorkerRequest:
    request_id: str
    operation: str
    request_sha256: str
    limit_profile_id: str
    schema_generation: int
    pipeline_generation: str
    expected_generations: Mapping[str, FileGeneration]
    payload: JsonValue
    key: bytes = field(repr=False)


@dataclass(frozen=True)
class WorkerResult:
    payload: JsonValue
    observed_generations: Mapping[str, FileGeneration]
    diagnostics: DiagnosticReceipt = field(
        default_factory=lambda: DiagnosticReceipt.empty()
    )


@dataclass(frozen=True)
class DiagnosticReceipt:
    """Path-free receipt for worker diagnostics; raw stderr never escapes."""

    byte_count: int
    sha256: str
    truncated: bool

    @classmethod
    def empty(cls) -> DiagnosticReceipt:
        return cls(0, hashlib.sha256(b"").hexdigest(), False)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class _PendingRequest:
    request: WorkerRequest
    document: dict[str, JsonValue]


def build_worker_request(
    operation: str,
    expected_generations: Mapping[str, FileGeneration | Mapping[str, object]],
    payload: JsonValue,
    *,
    credentials: WorkerCredentials | None = None,
    request_id: str | None = None,
    limit_profile_id: str = "artifact-default-v1",
    schema_generation: int = 1,
    pipeline_generation: str = PROTOCOL_VERSION,
) -> WorkerRequest:
    """Create a strictly validated request suitable for framed stdin."""

    if not _OPERATION_RE.fullmatch(operation):
        raise ValueError("invalid worker operation")
    _validate_generation_bindings(
        limit_profile_id, schema_generation, pipeline_generation
    )
    normalized_generations = _normalize_generations(expected_generations)
    normalized_payload = _normalize_json(payload)
    selected_credentials = credentials or WorkerCredentials.generate()
    selected_request_id = request_id or secrets.token_hex(_REQUEST_ID_BYTES)
    if not _is_digest(selected_request_id):
        raise ValueError("request id must be 64 lowercase hexadecimal characters")
    binding: dict[str, JsonValue] = {
        "protocol": PROTOCOL_VERSION,
        "request_id": selected_request_id,
        "operation": operation,
        "limit_profile_id": limit_profile_id,
        "schema_generation": schema_generation,
        "pipeline_generation": pipeline_generation,
        "expected_generations": _generation_document(normalized_generations),
        "payload": normalized_payload,
    }
    request_sha256 = hashlib.sha256(_canonical_json(binding)).hexdigest()
    return WorkerRequest(
        request_id=selected_request_id,
        operation=operation,
        request_sha256=request_sha256,
        limit_profile_id=limit_profile_id,
        schema_generation=schema_generation,
        pipeline_generation=pipeline_generation,
        expected_generations=normalized_generations,
        payload=normalized_payload,
        key=selected_credentials.key,
    )


def read_worker_request(
    stream: BinaryIO | None = None,
    *,
    max_input_bytes: int = 64 * 1024,
) -> WorkerRequest:
    """Read exactly one strict framed request and require stdin EOF."""

    selected_stream = stream or sys.stdin.buffer
    try:
        raw = _read_one_frame(selected_stream, max_input_bytes, require_eof=True)
        document = _strict_json_object(raw)
        return _parse_request_document(document)
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        RecursionError,
        json.JSONDecodeError,
    ) as exc:
        raise SupervisorError("invalid_worker_request") from exc


def write_worker_response(
    request: WorkerRequest,
    *,
    payload: JsonValue | object = _MISSING,
    observed_generations: Mapping[str, FileGeneration | Mapping[str, object]]
    | None = None,
    error: SupervisorError | None = None,
    stream: BinaryIO | None = None,
    max_output_bytes: int = 32 * 1024 * 1024,
) -> None:
    """Write one response authenticated and bound to the exact request."""

    if (payload is _MISSING) == (error is None):
        raise ValueError("provide exactly one of payload or error")
    selected_stream = stream or sys.stdout.buffer
    normalized_observed = _normalize_generations(observed_generations or {})
    bindings: dict[str, JsonValue] = {
        "expected_generations": _generation_document(request.expected_generations),
        "observed_generations": _generation_document(normalized_observed),
    }
    bindings_bytes = _canonical_json(bindings)
    if len(bindings_bytes) > _MAX_BINDINGS_BYTES:
        raise SupervisorError(
            "worker_output_limit_exceeded",
            {"binding_limit_bytes": _MAX_BINDINGS_BYTES},
        )
    unsigned: dict[str, JsonValue] = {
        "protocol": PROTOCOL_VERSION,
        "request_id": request.request_id,
        "operation": request.operation,
        "request_sha256": request.request_sha256,
        "limit_profile_id": request.limit_profile_id,
        "schema_generation": request.schema_generation,
        "pipeline_generation": request.pipeline_generation,
        "ok": error is None,
        "bindings_sha256": hashlib.sha256(bindings_bytes).hexdigest(),
        "bindings_b64": base64.b64encode(bindings_bytes).decode("ascii"),
    }
    if error is None:
        body: dict[str, JsonValue] = {"payload": _normalize_json(payload)}
    else:
        body = {
            "error": {
                "reason_code": error.reason_code,
                "details": _normalize_json(dict(error.details)),
            }
        }
    body_bytes = _canonical_json(body)
    unsigned["body_sha256"] = hashlib.sha256(body_bytes).hexdigest()
    unsigned["body_b64"] = base64.b64encode(body_bytes).decode("ascii")
    signature = hmac.new(
        request.key, _canonical_json(unsigned), hashlib.sha256
    ).hexdigest()
    document = dict(unsigned)
    document["hmac_sha256"] = signature
    _write_frame(selected_stream, document, max_output_bytes)


def isolate_protocol_output() -> BinaryIO:
    """Reserve original stdout for protocol and route incidental stdout to stderr.

    Call this immediately after reading the request and before importing or
    invoking artifact parsers.  The returned binary stream owns a duplicate of
    the original stdout descriptor and should be closed by the worker.
    """

    try:
        protocol_fd: int | None = None
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            protocol_fd = os.dup(sys.stdout.fileno())
            os.set_inheritable(protocol_fd, False)
            os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
            stream = os.fdopen(protocol_fd, "wb", buffering=0)
            protocol_fd = None
            return stream
        finally:
            if protocol_fd is not None:
                os.close(protocol_fd)
    except (OSError, ValueError) as exc:
        raise SupervisorError("protocol_isolation_failed") from exc


def run_authenticated_worker(
    command: Sequence[str | os.PathLike[str]],
    operation: str,
    expected_generations: Mapping[str, FileGeneration | Mapping[str, object]],
    payload: JsonValue,
    limits: SupervisorLimits,
    *,
    credentials: WorkerCredentials | None = None,
    sensitive_values: Sequence[str | os.PathLike[str]] = (),
    schema_generation: int = 1,
    pipeline_generation: str = PROTOCOL_VERSION,
    process_backend: Callable[..., subprocess.Popen[bytes]] | None = None,
    monitor_factory: Callable[[int, SupervisorLimits], _ProcessTreeMonitor]
    | None = None,
    clock: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> WorkerResult:
    """Run one authenticated worker behind protocol and platform process bounds.

    The process is created first, then attached to a Windows Job Object or a
    dedicated POSIX process group and sampled by psutil.  Only after both
    barriers succeed is the request written, so a worker without those baseline
    controls never learns an artifact path or authentication key.  POSIX process
    groups are cleanup boundaries for trusted worker code, not portable security
    sandboxes against a worker that deliberately creates another session.
    """

    command_parts = _validate_command(command)
    selected_credentials = credentials or WorkerCredentials.generate()
    pending = _prepare_request(
        operation,
        expected_generations,
        payload,
        credentials=selected_credentials,
        limit_profile_id=limits.profile_id,
        schema_generation=schema_generation,
        pipeline_generation=pipeline_generation,
    )
    request_frame = _encode_frame(pending.document, limits.max_input_bytes)
    inferred_sensitive = _payload_sensitive_strings(pending.request.payload)
    declared_sensitive = tuple(str(value) for value in sensitive_values if str(value))
    redactions = tuple(dict.fromkeys((*declared_sensitive, *inferred_sensitive)))
    _reject_sensitive_process_metadata(command_parts, redactions)
    environment = _sanitized_environment(redactions)
    response_redactions = (
        *redactions,
        base64.b64encode(selected_credentials.key).decode("ascii"),
        base64.urlsafe_b64encode(selected_credentials.key).decode("ascii"),
        selected_credentials.key.hex(),
        selected_credentials.key.hex().upper(),
    )
    popen_factory = process_backend or cast(
        Callable[..., subprocess.Popen[bytes]], subprocess.Popen
    )
    monitor_builder = monitor_factory or _ProcessTreeMonitor
    clock_fn = clock if clock is not None else time.monotonic
    sleep_fn = sleeper if sleeper is not None else time.sleep
    started = clock_fn()
    process: subprocess.Popen[bytes] | None = None
    controller: _ProcessController | None = None
    monitor: _ProcessTreeMonitor | None = None
    stdout_reader: _PipeDrainer | None = None
    stderr_reader: _PipeDrainer | None = None
    stdin_writer: _PipeWriter | None = None
    primary_error: SupervisorError | None = None
    response_bytes = b""
    diagnostic_receipt = DiagnosticReceipt.empty()
    exit_code: int | None = None

    try:
        popen_kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "bufsize": 0,
            "close_fds": True,
            "env": environment,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        elif os.name == "nt":
            popen_kwargs["creationflags"] = _windows_creation_flags()
        try:
            process = cast(
                subprocess.Popen[bytes], popen_factory(command_parts, **popen_kwargs)
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise SupervisorError("worker_start_failed") from exc

        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise SupervisorError("worker_pipe_setup_failed")

        # Own every raw Popen pipe before a containment barrier can fail. The
        # wrappers are started only after both barriers succeed, but cleanup can
        # already close the underlying descriptors on every earlier exit.
        stdout_reader = _PipeDrainer(
            cast(BinaryIO, process.stdout),
            limits.max_output_bytes + _FRAME_HEADER_BYTES,
        )
        stderr_reader = _PipeDrainer(
            cast(BinaryIO, process.stderr), limits.max_diagnostic_bytes
        )
        stdin_writer = _PipeWriter(cast(BinaryIO, process.stdin), request_frame)

        # The child has no request yet.  Establish every containment/monitoring
        # mechanism before allowing it to learn the artifact path or key.
        controller = _ProcessController(process, limits)
        controller.establish()
        monitor = monitor_builder(process.pid, limits)
        try:
            monitor.establish()
        except SupervisorError as exc:
            if process.poll() is not None:
                raise SupervisorError(
                    "worker_exit_before_barrier",
                    {"exit_nonzero": process.returncode != 0},
                ) from exc
            raise

        deadline = started + limits.wall_seconds
        if clock_fn() >= deadline:
            raise SupervisorError("worker_timeout")

        stdout_reader.start()
        stderr_reader.start()
        stdin_writer.start()

        while process.poll() is None:
            if stdout_reader.overflowed:
                raise SupervisorError("worker_output_limit_exceeded")
            if stderr_reader.overflowed:
                raise SupervisorError("worker_diagnostic_limit_exceeded")
            if stdin_writer.failed:
                raise SupervisorError("worker_request_write_failed")
            now = clock_fn()
            if now >= deadline:
                raise SupervisorError("worker_timeout")
            try:
                monitor.sample()
            except SupervisorError as exc:
                # The direct child can become a zombie after poll() above and
                # before psutil walks it. Popen is the root-process authority.
                if process.poll() is not None:
                    break
                if exc.reason_code == "worker_monitor_identity_changed":
                    settle_timeout = min(
                        limits.sample_interval_seconds,
                        max(0.0, deadline - clock_fn()),
                    )
                    if settle_timeout > 0:
                        try:
                            process.wait(timeout=settle_timeout)
                        except subprocess.TimeoutExpired:
                            pass
                        else:
                            break
                raise
            sleep_fn(min(limits.sample_interval_seconds, max(0.0, deadline - now)))

        exit_code = process.wait(timeout=0)
        _join_io_threads(
            stdin_writer,
            stdout_reader,
            stderr_reader,
            timeout=min(0.5, max(0.0, deadline - clock_fn())),
            clock=clock_fn,
        )
        if stdin_writer.failed:
            raise SupervisorError("worker_request_write_failed")
        if stdout_reader.failed:
            raise SupervisorError("worker_output_read_failed")
        if stderr_reader.failed:
            raise SupervisorError("worker_diagnostic_read_failed")
        if stdout_reader.overflowed:
            raise SupervisorError("worker_output_limit_exceeded")
        if stderr_reader.overflowed:
            raise SupervisorError("worker_diagnostic_limit_exceeded")
        response_bytes = stdout_reader.data
        diagnostic_receipt = stderr_reader.receipt
        if exit_code != 0:
            raise SupervisorError("worker_exit", {"exit_nonzero": True})
        if monitor.has_live_descendants():
            raise SupervisorError("worker_process_tree_leak")
    except SupervisorError as exc:
        primary_error = exc
    finally:
        cleanup_error = _cleanup_invocation(
            process,
            controller,
            monitor,
            stdin_writer,
            stdout_reader,
            stderr_reader,
            limits.cleanup_seconds,
            clock=clock_fn,
        )
        if stdout_reader is not None:
            response_bytes = stdout_reader.data
        if stderr_reader is not None:
            diagnostic_receipt = stderr_reader.receipt
        if cleanup_error is not None:
            raise SupervisorError(
                "worker_cleanup_failed",
                {
                    "prior_reason_code": primary_error.reason_code
                    if primary_error
                    else None
                },
                diagnostic_receipt,
            ) from cleanup_error
        late_pipe_error = _pipe_error_after_cleanup(
            stdin_writer,
            stdout_reader,
            stderr_reader,
        )
        if primary_error is None and late_pipe_error is not None:
            raise SupervisorError(
                late_pipe_error,
                diagnostics=diagnostic_receipt,
            )
        if primary_error is not None:
            raise SupervisorError(
                primary_error.reason_code,
                _sanitize_details(primary_error.details, redactions),
                diagnostic_receipt,
            ) from primary_error

    return _verify_response(
        response_bytes,
        pending.request,
        diagnostic_receipt,
        response_redactions,
        max_output_bytes=limits.max_output_bytes,
    )


def _prepare_request(
    operation: str,
    expected_generations: Mapping[str, FileGeneration | Mapping[str, object]],
    payload: JsonValue,
    *,
    credentials: WorkerCredentials,
    limit_profile_id: str,
    schema_generation: int,
    pipeline_generation: str,
) -> _PendingRequest:
    request = build_worker_request(
        operation,
        expected_generations,
        payload,
        credentials=credentials,
        limit_profile_id=limit_profile_id,
        schema_generation=schema_generation,
        pipeline_generation=pipeline_generation,
    )
    document: dict[str, JsonValue] = {
        "protocol": PROTOCOL_VERSION,
        "request_id": request.request_id,
        "operation": request.operation,
        "request_sha256": request.request_sha256,
        "limit_profile_id": request.limit_profile_id,
        "schema_generation": request.schema_generation,
        "pipeline_generation": request.pipeline_generation,
        "expected_generations": _generation_document(request.expected_generations),
        "payload": request.payload,
        "key_b64": base64.b64encode(request.key).decode("ascii"),
    }
    return _PendingRequest(request=request, document=document)


def _parse_request_document(document: Mapping[str, object]) -> WorkerRequest:
    expected_fields = {
        "protocol",
        "request_id",
        "operation",
        "request_sha256",
        "limit_profile_id",
        "schema_generation",
        "pipeline_generation",
        "expected_generations",
        "payload",
        "key_b64",
    }
    if set(document) != expected_fields or document.get("protocol") != PROTOCOL_VERSION:
        raise ValueError("invalid request envelope")
    request_id = _strict_string(document["request_id"], "request_id")
    operation = _strict_string(document["operation"], "operation")
    supplied_digest = _strict_string(document["request_sha256"], "request_sha256")
    limit_profile_id = _strict_string(document["limit_profile_id"], "limit_profile_id")
    schema_generation = _strict_int(document["schema_generation"], "schema_generation")
    pipeline_generation = _strict_string(
        document["pipeline_generation"], "pipeline_generation"
    )
    _validate_generation_bindings(
        limit_profile_id, schema_generation, pipeline_generation
    )
    if not _is_digest(request_id) or not _OPERATION_RE.fullmatch(operation):
        raise ValueError("invalid request binding")
    if not _is_digest(supplied_digest):
        raise ValueError("invalid request digest")
    expected_document = _strict_mapping(
        document["expected_generations"], "expected_generations"
    )
    expected = _normalize_generations(expected_document)
    payload = _normalize_json(document["payload"])
    key_text = _strict_string(document["key_b64"], "key_b64")
    try:
        key = base64.b64decode(key_text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid request key") from exc
    if len(key) != _AUTH_KEY_BYTES:
        raise ValueError("invalid request key")
    binding: dict[str, JsonValue] = {
        "protocol": PROTOCOL_VERSION,
        "request_id": request_id,
        "operation": operation,
        "limit_profile_id": limit_profile_id,
        "schema_generation": schema_generation,
        "pipeline_generation": pipeline_generation,
        "expected_generations": _generation_document(expected),
        "payload": payload,
    }
    actual_digest = hashlib.sha256(_canonical_json(binding)).hexdigest()
    if not hmac.compare_digest(actual_digest, supplied_digest):
        raise ValueError("request digest mismatch")
    return WorkerRequest(
        request_id=request_id,
        operation=operation,
        request_sha256=supplied_digest,
        limit_profile_id=limit_profile_id,
        schema_generation=schema_generation,
        pipeline_generation=pipeline_generation,
        expected_generations=expected,
        payload=payload,
        key=key,
    )


def _verify_response(
    framed_response: bytes,
    request: WorkerRequest,
    diagnostics: DiagnosticReceipt,
    sensitive_values: Sequence[str],
    *,
    max_output_bytes: int | None = None,
) -> WorkerResult:
    output_limit = (
        len(framed_response) if max_output_bytes is None else max_output_bytes
    )
    try:
        raw = _decode_one_frame(framed_response, max(0, output_limit))
        document = _strict_response_envelope(raw, output_limit)
    except (
        UnicodeError,
        ValueError,
        TypeError,
        RecursionError,
        json.JSONDecodeError,
    ) as exc:
        raise SupervisorError(
            "invalid_worker_response", diagnostics=diagnostics
        ) from exc

    ok = cast(bool, document["ok"])
    signature = cast(str, document["hmac_sha256"])
    if not _is_digest(signature):
        raise SupervisorError(
            "worker_response_authentication_failed", diagnostics=diagnostics
        )
    unsigned = dict(document)
    del unsigned["hmac_sha256"]
    try:
        expected_signature = hmac.new(
            request.key,
            _canonical_json(cast(JsonValue, unsigned)),
            hashlib.sha256,
        ).hexdigest()
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SupervisorError(
            "invalid_worker_response", diagnostics=diagnostics
        ) from exc
    if not hmac.compare_digest(signature, expected_signature):
        raise SupervisorError(
            "worker_response_authentication_failed", diagnostics=diagnostics
        )
    if (
        document.get("protocol") != PROTOCOL_VERSION
        or document.get("request_id") != request.request_id
        or document.get("operation") != request.operation
        or document.get("request_sha256") != request.request_sha256
        or document.get("limit_profile_id") != request.limit_profile_id
        or document.get("schema_generation") != request.schema_generation
        or document.get("pipeline_generation") != request.pipeline_generation
    ):
        raise SupervisorError(
            "worker_response_binding_mismatch", diagnostics=diagnostics
        )

    bindings_digest = cast(str, document["bindings_sha256"])
    bindings_text = cast(str, document["bindings_b64"])
    if not _is_digest(bindings_digest):
        raise SupervisorError(
            "invalid_worker_response_bindings", diagnostics=diagnostics
        )
    try:
        bindings_bytes = base64.b64decode(bindings_text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SupervisorError(
            "invalid_worker_response_bindings", diagnostics=diagnostics
        ) from exc
    if len(bindings_bytes) > _MAX_BINDINGS_BYTES or not hmac.compare_digest(
        hashlib.sha256(bindings_bytes).hexdigest(), bindings_digest
    ):
        raise SupervisorError(
            "worker_response_bindings_mismatch", diagnostics=diagnostics
        )
    try:
        bindings = _strict_json_object(bindings_bytes)
        if set(bindings) != {"expected_generations", "observed_generations"}:
            raise ValueError("invalid generation-binding fields")
        echoed_expected = _normalize_generations(
            _strict_mapping(bindings["expected_generations"], "expected_generations")
        )
        observed = _normalize_generations(
            _strict_mapping(bindings["observed_generations"], "observed_generations")
        )
    except (
        UnicodeError,
        ValueError,
        TypeError,
        RecursionError,
        json.JSONDecodeError,
    ) as exc:
        raise SupervisorError(
            "invalid_worker_response_bindings", diagnostics=diagnostics
        ) from exc
    if echoed_expected != dict(request.expected_generations):
        raise SupervisorError(
            "worker_response_binding_mismatch", diagnostics=diagnostics
        )
    if set(observed) != set(request.expected_generations):
        raise SupervisorError(
            "worker_generation_binding_mismatch", diagnostics=diagnostics
        )
    if any(observed[name] != request.expected_generations[name] for name in observed):
        raise SupervisorError("worker_generation_changed", diagnostics=diagnostics)

    # The potentially large, deeply nested worker payload remains opaque until
    # authentication and every request/profile/schema/file-generation binding
    # has succeeded.
    body_digest = cast(str, document["body_sha256"])
    body_text = cast(str, document["body_b64"])
    if not _is_digest(body_digest):
        raise SupervisorError("invalid_worker_response", diagnostics=diagnostics)
    try:
        body_bytes = base64.b64decode(body_text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SupervisorError(
            "invalid_worker_response", diagnostics=diagnostics
        ) from exc
    if not hmac.compare_digest(hashlib.sha256(body_bytes).hexdigest(), body_digest):
        raise SupervisorError("worker_response_body_mismatch", diagnostics=diagnostics)
    try:
        body = _strict_json_object(body_bytes)
    except (
        UnicodeError,
        ValueError,
        TypeError,
        RecursionError,
        json.JSONDecodeError,
    ) as exc:
        raise SupervisorError(
            "invalid_worker_response_body", diagnostics=diagnostics
        ) from exc

    if ok is False:
        try:
            if set(body) != {"error"}:
                raise ValueError("invalid error body")
            error = _strict_mapping(body["error"], "error")
            if set(error) != {"reason_code", "details"}:
                raise ValueError("invalid error fields")
            reason = _strict_string(error["reason_code"], "reason_code")
            if not _REASON_RE.fullmatch(reason):
                raise ValueError("invalid worker reason code")
            details = _strict_mapping(error["details"], "details")
            normalized_details = _normalize_json(details)
        except (TypeError, ValueError, RecursionError) as exc:
            raise SupervisorError(
                "invalid_worker_response_body", diagnostics=diagnostics
            ) from exc
        raise SupervisorError(
            reason,
            _sanitize_details(normalized_details, sensitive_values),
            diagnostics,
        )

    try:
        if set(body) != {"payload"}:
            raise ValueError("invalid success body")
        result_payload = _normalize_json(body["payload"])
    except (TypeError, ValueError, RecursionError) as exc:
        raise SupervisorError(
            "invalid_worker_response", diagnostics=diagnostics
        ) from exc
    return WorkerResult(
        payload=result_payload,
        observed_generations=observed,
        diagnostics=diagnostics,
    )


class _PipeDrainer:
    def __init__(self, stream: BinaryIO, limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self._data = bytearray()
        self._byte_count = 0
        self._sha256 = hashlib.sha256()
        self._overflow = threading.Event()
        self._failed = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    @property
    def data(self) -> bytes:
        return bytes(self._data)

    @property
    def overflowed(self) -> bool:
        return self._overflow.is_set()

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    @property
    def receipt(self) -> DiagnosticReceipt:
        return DiagnosticReceipt(
            byte_count=self._byte_count,
            sha256=self._sha256.hexdigest(),
            truncated=self.overflowed,
        )

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float) -> None:
        self._thread.join(timeout)

    def close(self) -> None:
        try:
            self._stream.close()
        except OSError:
            self._failed.set()

    def _run(self) -> None:
        try:
            while True:
                chunk = self._stream.read(64 * 1024)
                if not chunk:
                    return
                self._byte_count += len(chunk)
                self._sha256.update(chunk)
                remaining = self._limit - len(self._data)
                if remaining > 0:
                    self._data.extend(chunk[:remaining])
                if len(chunk) > max(remaining, 0):
                    self._overflow.set()
        except (OSError, ValueError):
            self._failed.set()


class _PipeWriter:
    def __init__(self, stream: BinaryIO, data: bytes) -> None:
        self._stream = stream
        self._data = data
        self._failed = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float) -> None:
        self._thread.join(timeout)

    def close(self) -> None:
        try:
            self._stream.close()
        except OSError:
            self._failed.set()

    def _run(self) -> None:
        try:
            self._stream.write(self._data)
            self._stream.flush()
        except (BrokenPipeError, OSError, ValueError):
            self._failed.set()
        finally:
            try:
                self._stream.close()
            except OSError:
                self._failed.set()


class _ProcessTreeMonitor:
    """Fail-closed psutil process-tree accounting."""

    def __init__(self, pid: int, limits: SupervisorLimits) -> None:
        self._pid = pid
        self._limits = limits
        self._psutil: Any | None = None
        self._root: Any | None = None
        self._root_create_time: float | None = None
        self._seen: dict[tuple[int, float], Any] = {}

    def establish(self) -> None:
        psutil_module = _load_psutil()
        self._psutil = psutil_module
        try:
            root = psutil_module.Process(self._pid)
            root_create_time = root.create_time()
            self._root = root
            self._root_create_time = root_create_time
            self.sample()
        except SupervisorError:
            raise
        except (psutil_module.Error, OSError, RuntimeError) as exc:
            raise SupervisorError("worker_monitor_unavailable") from exc

    def sample(self) -> tuple[int, int]:
        psutil_module = self._psutil
        if (
            psutil_module is None
            or self._root is None
            or self._root_create_time is None
        ):
            raise SupervisorError("worker_monitor_unavailable")
        try:
            if self._root.create_time() != self._root_create_time:
                raise SupervisorError("worker_monitor_identity_changed")
            candidates = [self._root, *self._root.children(recursive=True)]
        except psutil_module.NoSuchProcess as exc:
            # Callers sample only while Popen still reports the child running.
            # Disappearance here is therefore a containment/identity failure,
            # not a clean exit.
            raise SupervisorError("worker_monitor_identity_changed") from exc
        except (
            psutil_module.AccessDenied,
            psutil_module.ZombieProcess,
            OSError,
        ) as exc:
            raise SupervisorError("worker_monitor_unavailable") from exc

        live: list[Any] = []
        rss = 0
        for candidate in candidates:
            try:
                identity = (candidate.pid, candidate.create_time())
                memory = candidate.memory_info().rss
                if not candidate.is_running():
                    if candidate.pid == self._pid:
                        raise SupervisorError("worker_monitor_identity_changed")
                    continue
            except psutil_module.NoSuchProcess as exc:
                if candidate.pid == self._pid:
                    raise SupervisorError("worker_monitor_identity_changed") from exc
                continue
            except (
                psutil_module.AccessDenied,
                psutil_module.ZombieProcess,
                OSError,
            ) as exc:
                raise SupervisorError("worker_monitor_unavailable") from exc
            self._seen[identity] = candidate
            live.append(candidate)
            rss += int(memory)
        if len(live) > self._limits.max_processes:
            raise SupervisorError(
                "worker_process_limit_exceeded",
                {"limit": self._limits.max_processes},
            )
        if rss > self._limits.max_memory_bytes:
            raise SupervisorError(
                "worker_memory_limit_exceeded",
                {"limit_bytes": self._limits.max_memory_bytes},
            )
        return (len(live), rss)

    def has_live_descendants(self) -> bool:
        psutil_module = self._psutil
        if psutil_module is None:
            raise SupervisorError("worker_monitor_unavailable")
        for process in self._seen.values():
            if process.pid == self._pid:
                continue
            if _same_process_is_alive(process, psutil_module):
                return True
        return False

    def kill_seen(self, timeout: float = 0.5) -> None:
        psutil_module = self._psutil
        if psutil_module is None:
            raise SupervisorError("worker_monitor_unavailable")
        processes = [
            process
            for process in self._seen.values()
            if _same_process_is_alive(process, psutil_module)
        ]
        for process in processes:
            try:
                process.kill()
            except psutil_module.NoSuchProcess:
                continue
            except (
                psutil_module.AccessDenied,
                psutil_module.ZombieProcess,
                OSError,
            ) as exc:
                raise SupervisorError("worker_cleanup_failed") from exc
        try:
            _, alive = psutil_module.wait_procs(processes, timeout=max(0.0, timeout))
        except (psutil_module.Error, OSError) as exc:
            raise SupervisorError("worker_cleanup_failed") from exc
        if any(_same_process_is_alive(process, psutil_module) for process in alive):
            raise SupervisorError("worker_cleanup_failed")

    def any_seen_alive(self) -> bool:
        psutil_module = self._psutil
        if psutil_module is None:
            raise SupervisorError("worker_monitor_unavailable")
        return any(
            _same_process_is_alive(process, psutil_module)
            for process in self._seen.values()
        )


class _ProcessController:
    """Windows Job containment or POSIX trusted-worker group cleanup."""

    def __init__(
        self, process: subprocess.Popen[bytes], limits: SupervisorLimits
    ) -> None:
        self._process = process
        self._limits = limits
        self._windows_job: _WindowsJob | None = None

    def establish(self) -> None:
        if os.name == "nt":
            try:
                job = _WindowsJob(self._limits)
                self._windows_job = job
                retained = False
                try:
                    job.assign(self._process.pid)
                    retained = True
                finally:
                    if not retained:
                        self.close()
            except OSError as exc:
                raise SupervisorError("worker_containment_unavailable") from exc
        elif os.name != "posix":
            raise SupervisorError("worker_containment_unavailable")

    def terminate(self, timeout: float | None = None) -> None:
        failures: list[OSError] = []
        if self._windows_job is not None:
            try:
                self._windows_job.terminate()
            except OSError as exc:
                failures.append(exc)
        elif os.name == "posix" and self._process.poll() is None:
            # poll() reaps an exited child.  Never address a process group by
            # that stale numeric identity: the PID/PGID may already belong to
            # an unrelated process.  A still-unreaped live child reserves its
            # PID while killpg runs; sampled descendants are killed below by
            # _ProcessTreeMonitor even after the root has exited.
            try:
                os.killpg(self._process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError as exc:
                # Darwin reports EPERM for a group whose only member exited
                # after poll() but remains an unreaped zombie. Confirm that
                # exit through a bounded Popen wait charged to the caller's
                # cleanup budget. A live root keeps EPERM fatal, and monitor
                # cleanup still proves no sampled descendant survives.
                darwin_group_gone = False
                if sys.platform == "darwin":
                    settle_budget = (
                        self._limits.cleanup_seconds
                        if timeout is None
                        else max(0.0, timeout)
                    )
                    settle_timeout = min(
                        self._limits.sample_interval_seconds,
                        settle_budget,
                    )
                    if settle_timeout > 0:
                        try:
                            self._process.wait(timeout=settle_timeout)
                        except (OSError, subprocess.TimeoutExpired):
                            pass
                        else:
                            darwin_group_gone = True
                if not darwin_group_gone:
                    failures.append(exc)
            except OSError as exc:
                failures.append(exc)
        if self._process.poll() is None:
            try:
                self._process.kill()
            except ProcessLookupError:
                # The process group kill can win the race after poll() but
                # before this direct-child fallback. ESRCH means the cleanup
                # already achieved its goal; other OS failures remain fatal.
                pass
            except OSError as exc:
                failures.append(exc)
        if failures:
            raise SupervisorError("worker_cleanup_failed") from failures[0]

    def close(self) -> None:
        if self._windows_job is not None:
            self._windows_job.close()
            self._windows_job = None


class _WindowsJob:
    """Minimal Windows Job Object with kill, memory, and process-count limits."""

    _JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    _JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def __init__(self, limits: SupervisorLimits) -> None:
        self._kernel32: Any
        self._handle: Any = None
        if os.name != "nt":
            raise OSError("Windows Job Objects are unavailable")
        kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
        _configure_windows_job_api(kernel32)
        self._kernel32 = kernel32
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise _windows_error()
        configured = False
        try:
            information = _JobObjectExtendedLimitInformation()
            information.BasicLimitInformation.LimitFlags = (
                self._JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                | self._JOB_OBJECT_LIMIT_JOB_MEMORY
                | self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            information.BasicLimitInformation.ActiveProcessLimit = limits.max_processes
            information.JobMemoryLimit = limits.max_memory_bytes
            ok = kernel32.SetInformationJobObject(
                self._handle,
                self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                ctypes.byref(information),
                ctypes.sizeof(information),
            )
            if not ok:
                raise _windows_error()
            configured = True
        finally:
            if not configured:
                self.close()

    def assign(self, pid: int) -> None:
        process_handle = self._kernel32.OpenProcess(
            self._PROCESS_TERMINATE
            | self._PROCESS_SET_QUOTA
            | self._PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )
        if not process_handle:
            raise _windows_error()
        try:
            if not self._kernel32.AssignProcessToJobObject(
                self._handle, process_handle
            ):
                raise _windows_error()
            assigned = ctypes.c_int(0)
            if not self._kernel32.IsProcessInJob(
                process_handle, self._handle, ctypes.byref(assigned)
            ):
                raise _windows_error()
            if assigned.value != 1:
                raise OSError("worker process was not assigned to its Job Object")
        finally:
            if not self._kernel32.CloseHandle(process_handle):
                raise _windows_error()

    def terminate(self) -> None:
        if self._handle and not self._kernel32.TerminateJobObject(self._handle, 1):
            raise _windows_error()

    def close(self) -> None:
        if self._handle:
            if not self._kernel32.CloseHandle(self._handle):
                raise _windows_error()
            self._handle = None


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _configure_windows_job_api(kernel32: Any) -> None:
    """Declare Win32 pointer widths explicitly before any HANDLE crosses Python."""

    handle = ctypes.c_void_p
    bool_type = ctypes.c_int
    dword = ctypes.c_uint32
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.CreateJobObjectW.restype = handle
    kernel32.SetInformationJobObject.argtypes = [
        handle,
        ctypes.c_int,
        ctypes.c_void_p,
        dword,
    ]
    kernel32.SetInformationJobObject.restype = bool_type
    kernel32.OpenProcess.argtypes = [dword, bool_type, dword]
    kernel32.OpenProcess.restype = handle
    kernel32.AssignProcessToJobObject.argtypes = [handle, handle]
    kernel32.AssignProcessToJobObject.restype = bool_type
    kernel32.IsProcessInJob.argtypes = [handle, handle, ctypes.POINTER(bool_type)]
    kernel32.IsProcessInJob.restype = bool_type
    kernel32.TerminateJobObject.argtypes = [handle, dword]
    kernel32.TerminateJobObject.restype = bool_type
    kernel32.CloseHandle.argtypes = [handle]
    kernel32.CloseHandle.restype = bool_type


def _windows_error() -> OSError:
    get_last_error = getattr(ctypes, "get_last_error", lambda: 0)
    error_code = int(get_last_error())
    win_error = getattr(ctypes, "WinError", None)
    if win_error is not None:
        return cast(OSError, win_error(error_code))
    return OSError(error_code, "Windows process containment failed")


def _cleanup_invocation(
    process: subprocess.Popen[bytes] | None,
    controller: _ProcessController | None,
    monitor: _ProcessTreeMonitor | None,
    writer: _PipeWriter | None,
    stdout_reader: _PipeDrainer | None,
    stderr_reader: _PipeDrainer | None,
    timeout: float,
    *,
    clock: Callable[[], float] | None = None,
) -> Exception | None:
    clock_fn = clock if clock is not None else time.monotonic
    deadline = clock_fn() + max(0.0, timeout)
    outcome: list[Exception | None] = []

    def cleanup() -> None:
        outcome.append(
            _cleanup_invocation_before_deadline(
                process,
                controller,
                monitor,
                writer,
                stdout_reader,
                stderr_reader,
                deadline,
                clock=clock_fn,
            )
        )

    cleanup_thread = threading.Thread(
        target=cleanup,
        name="artifact-supervisor-cleanup",
        daemon=True,
    )
    try:
        cleanup_thread.start()
    except RuntimeError as exc:
        emergency_error = _emergency_cleanup_after_thread_start_failure(
            process,
            controller,
            monitor,
            writer,
            stdout_reader,
            stderr_reader,
        )
        return emergency_error or exc
    cleanup_thread.join(max(0.0, deadline - clock_fn()))
    if cleanup_thread.is_alive():
        return TimeoutError("worker cleanup deadline exceeded")
    if not outcome:
        return RuntimeError("worker cleanup did not report an outcome")
    return outcome[0]


def _emergency_cleanup_after_thread_start_failure(
    process: subprocess.Popen[bytes] | None,
    controller: _ProcessController | None,
    monitor: _ProcessTreeMonitor | None,
    writer: _PipeWriter | None,
    stdout_reader: _PipeDrainer | None,
    stderr_reader: _PipeDrainer | None,
) -> Exception | None:
    """Make one non-waiting kill/close pass when cleanup cannot be scheduled."""

    failures: list[Exception] = []
    if process is not None:
        try:
            if controller is not None:
                controller.terminate(0.0)
            elif process.poll() is None:
                process.kill()
        except (OSError, SupervisorError) as exc:
            failures.append(exc)
        if monitor is not None:
            try:
                monitor.kill_seen(0.0)
            except SupervisorError as exc:
                failures.append(exc)
    for pipe in (writer, stdout_reader, stderr_reader):
        if pipe is not None:
            pipe.close()
    if controller is not None:
        try:
            controller.close()
        except OSError as exc:
            failures.append(exc)
    return failures[0] if failures else None


def _cleanup_invocation_before_deadline(
    process: subprocess.Popen[bytes] | None,
    controller: _ProcessController | None,
    monitor: _ProcessTreeMonitor | None,
    writer: _PipeWriter | None,
    stdout_reader: _PipeDrainer | None,
    stderr_reader: _PipeDrainer | None,
    deadline: float,
    *,
    clock: Callable[[], float] | None = None,
) -> Exception | None:
    """Run ordered cleanup while one outer thread enforces the hard deadline."""

    failures: list[Exception] = []
    clock_fn = clock if clock is not None else time.monotonic

    def remaining() -> float:
        return max(0.0, deadline - clock_fn())

    def deadline_failure() -> TimeoutError:
        return TimeoutError("worker cleanup deadline exceeded")

    if process is not None:
        # Always tear down the platform boundary. A child may have exited
        # between samples after creating a descendant that inherited a pipe.
        # Windows Job termination is a process-tree boundary; POSIX group kill
        # plus kill_seen covers cooperative workers and sampled descendants.
        if remaining() <= 0:
            return deadline_failure()
        try:
            if controller is not None:
                controller.terminate(remaining())
            elif process.poll() is None:
                process.kill()
        except (OSError, SupervisorError) as exc:
            failures.append(exc)
        if remaining() <= 0:
            return deadline_failure()
        try:
            process.wait(timeout=remaining())
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(exc)
        if monitor is not None:
            if remaining() <= 0:
                return deadline_failure()
            try:
                monitor.kill_seen(remaining())
            except SupervisorError as exc:
                failures.append(exc)

    for pipe in (writer, stdout_reader, stderr_reader):
        if pipe is not None:
            if remaining() <= 0:
                return deadline_failure()
            pipe.close()
    if remaining() <= 0:
        return deadline_failure()
    _join_io_threads(
        writer,
        stdout_reader,
        stderr_reader,
        timeout=remaining(),
        clock=clock_fn,
    )
    if remaining() <= 0:
        return deadline_failure()
    if any(
        pipe is not None and pipe.alive
        for pipe in (writer, stdout_reader, stderr_reader)
    ):
        failures.append(RuntimeError("pipe thread did not terminate"))
    if controller is not None:
        if remaining() <= 0:
            return deadline_failure()
        try:
            controller.close()
        except OSError as exc:
            failures.append(exc)
    if remaining() <= 0:
        return deadline_failure()
    if process is not None and process.poll() is None:
        failures.append(RuntimeError("worker process did not terminate"))
    if monitor is not None:
        if remaining() <= 0:
            return deadline_failure()
        try:
            if monitor.any_seen_alive():
                failures.append(RuntimeError("worker process tree did not terminate"))
        except SupervisorError as exc:
            failures.append(exc)
    return failures[0] if failures else None


def _pipe_error_after_cleanup(
    writer: _PipeWriter | None,
    stdout_reader: _PipeDrainer | None,
    stderr_reader: _PipeDrainer | None,
) -> str | None:
    """Return any I/O failure first observed during the final bounded drain."""

    if writer is not None and writer.failed:
        return "worker_request_write_failed"
    if stdout_reader is not None and stdout_reader.failed:
        return "worker_output_read_failed"
    if stderr_reader is not None and stderr_reader.failed:
        return "worker_diagnostic_read_failed"
    if stdout_reader is not None and stdout_reader.overflowed:
        return "worker_output_limit_exceeded"
    if stderr_reader is not None and stderr_reader.overflowed:
        return "worker_diagnostic_limit_exceeded"
    return None


def _join_io_threads(
    writer: _PipeWriter | None,
    stdout_reader: _PipeDrainer | None,
    stderr_reader: _PipeDrainer | None,
    *,
    timeout: float,
    clock: Callable[[], float] | None = None,
) -> None:
    clock_fn = clock if clock is not None else time.monotonic
    deadline = clock_fn() + timeout
    for pipe in (writer, stdout_reader, stderr_reader):
        if pipe is not None and pipe.alive:
            pipe.join(max(0.0, deadline - clock_fn()))


def _write_frame(
    stream: BinaryIO, document: Mapping[str, JsonValue], limit: int
) -> None:
    frame = _encode_frame(
        document,
        limit,
        limit_reason="worker_output_limit_exceeded",
    )
    stream.write(frame)
    stream.flush()


def _encode_frame(
    document: Mapping[str, JsonValue],
    limit: int,
    *,
    limit_reason: str = "worker_input_limit_exceeded",
) -> bytes:
    if limit_reason not in {
        "worker_input_limit_exceeded",
        "worker_output_limit_exceeded",
    }:
        raise ValueError("frame limit reason must identify input or output")
    payload = _canonical_json(_normalize_json(document))
    if not payload or len(payload) > limit:
        raise SupervisorError(limit_reason, {"limit_bytes": limit})
    return struct.pack(">I", len(payload)) + payload


def _read_one_frame(stream: BinaryIO, limit: int, *, require_eof: bool) -> bytes:
    header = _read_exact(stream, _FRAME_HEADER_BYTES)
    length = struct.unpack(">I", header)[0]
    if length == 0 or length > limit:
        raise ValueError("invalid frame length")
    payload = _read_exact(stream, length)
    if require_eof and stream.read(1) != b"":
        raise ValueError("trailing framed input")
    return payload


def _decode_one_frame(data: bytes, limit: int) -> bytes:
    if len(data) < _FRAME_HEADER_BYTES:
        raise ValueError("partial frame header")
    length = struct.unpack(">I", data[:_FRAME_HEADER_BYTES])[0]
    if length == 0 or length > limit:
        raise ValueError("invalid frame length")
    if len(data) != _FRAME_HEADER_BYTES + length:
        raise ValueError("partial or trailing framed output")
    return data[_FRAME_HEADER_BYTES:]


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise ValueError("partial framed input")
        chunks.extend(chunk)
    return bytes(chunks)


def _strict_response_envelope(raw: bytes, output_limit: int) -> dict[str, object]:
    """Parse the fixed outer response without recursively decoding JSON values.

    Every valid outer value is an ASCII string, one bounded integer, or one
    boolean.  Bindings and the worker body stay base64 text until after HMAC
    verification.  Parsing bytes directly prevents a forged object/array value
    or unknown member from triggering recursive semantic allocation before the
    authentication gate.
    """

    expected_fields = {
        "protocol",
        "request_id",
        "operation",
        "request_sha256",
        "limit_profile_id",
        "schema_generation",
        "pipeline_generation",
        "ok",
        "bindings_sha256",
        "bindings_b64",
        "body_sha256",
        "body_b64",
        "hmac_sha256",
    }
    string_limits = {
        "protocol": _MAX_OUTER_NAME_CHARS,
        "request_id": _DIGEST_HEX_LENGTH,
        "operation": _MAX_OUTER_NAME_CHARS,
        "request_sha256": _DIGEST_HEX_LENGTH,
        "limit_profile_id": _MAX_OUTER_NAME_CHARS,
        "pipeline_generation": _MAX_OUTER_NAME_CHARS,
        "bindings_sha256": _DIGEST_HEX_LENGTH,
        "bindings_b64": _MAX_BINDINGS_B64_CHARS,
        "body_sha256": _DIGEST_HEX_LENGTH,
        # The caller's framed-output budget includes the encoded body and all
        # envelope overhead.  It is therefore also a strict upper bound for
        # this one opaque string; raw body bytes have only ~3/4 of that budget.
        "body_b64": output_limit,
        "hmac_sha256": _DIGEST_HEX_LENGTH,
    }
    if output_limit <= 0 or not raw or len(raw) > output_limit:
        raise ValueError("response envelope exceeds output limit")

    cursor = _skip_json_whitespace(raw, 0)
    if cursor >= len(raw) or raw[cursor] != ord("{"):
        raise ValueError("response envelope must be an object")
    cursor += 1
    result: dict[str, object] = {}
    cursor = _skip_json_whitespace(raw, cursor)
    while cursor < len(raw) and raw[cursor] != ord("}"):
        key, cursor = _parse_outer_ascii_string(
            raw,
            cursor,
            _MAX_OUTER_NAME_CHARS,
        )
        if key not in expected_fields:
            raise ValueError("unknown response envelope field")
        if key in result:
            raise ValueError("duplicate response envelope field")
        cursor = _skip_json_whitespace(raw, cursor)
        if cursor >= len(raw) or raw[cursor] != ord(":"):
            raise ValueError("missing response envelope separator")
        cursor = _skip_json_whitespace(raw, cursor + 1)

        if key in string_limits:
            value, cursor = _parse_outer_ascii_string(
                raw,
                cursor,
                string_limits[key],
            )
        elif key == "schema_generation":
            value, cursor = _parse_outer_bounded_integer(raw, cursor)
        elif key == "ok":
            if raw.startswith(b"true", cursor):
                value = True
                cursor += 4
            elif raw.startswith(b"false", cursor):
                value = False
                cursor += 5
            else:
                raise ValueError("invalid response boolean")
        else:  # pragma: no cover - exact expected field partition above
            raise ValueError("unsupported response envelope field")
        result[key] = value

        cursor = _skip_json_whitespace(raw, cursor)
        if cursor < len(raw) and raw[cursor] == ord(","):
            cursor = _skip_json_whitespace(raw, cursor + 1)
            if cursor >= len(raw) or raw[cursor] == ord("}"):
                raise ValueError("trailing response envelope comma")
            continue
        break

    if cursor >= len(raw) or raw[cursor] != ord("}"):
        raise ValueError("unterminated response envelope")
    cursor = _skip_json_whitespace(raw, cursor + 1)
    if cursor != len(raw) or set(result) != expected_fields:
        raise ValueError("invalid response envelope fields")
    return result


def _skip_json_whitespace(raw: bytes, cursor: int) -> int:
    while cursor < len(raw) and raw[cursor] in b" \t\r\n":
        cursor += 1
    return cursor


def _parse_outer_ascii_string(
    raw: bytes,
    cursor: int,
    max_chars: int,
) -> tuple[str, int]:
    """Parse one unescaped printable-ASCII outer string within its field cap."""

    if cursor >= len(raw) or raw[cursor] != ord('"'):
        raise ValueError("response envelope value must be a string")
    start = cursor + 1
    cursor = start
    while cursor < len(raw) and raw[cursor] != ord('"'):
        character = raw[cursor]
        if character < 0x20 or character > 0x7E or character == ord("\\"):
            raise ValueError("response envelope strings must be plain ASCII")
        if cursor - start >= max_chars:
            raise ValueError("response envelope string exceeds field limit")
        cursor += 1
    if cursor >= len(raw):
        raise ValueError("unterminated response envelope string")
    return raw[start:cursor].decode("ascii"), cursor + 1


def _parse_outer_bounded_integer(raw: bytes, cursor: int) -> tuple[int, int]:
    start = cursor
    if cursor < len(raw) and raw[cursor] == ord("-"):
        cursor += 1
    digits_start = cursor
    while cursor < len(raw) and ord("0") <= raw[cursor] <= ord("9"):
        cursor += 1
    digits = raw[digits_start:cursor]
    if (
        not digits
        or len(digits) > _MAX_JSON_INTEGER_DIGITS
        or (len(digits) > 1 and digits[0] == ord("0"))
    ):
        raise ValueError("invalid bounded response integer")
    return int(raw[start:cursor]), cursor


def _strict_json_object(raw: bytes) -> dict[str, object]:
    def reject_constant(_: str) -> object:
        raise ValueError("non-finite number is not valid JSON")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    def parse_bounded_int(text: str) -> int:
        digits = text[1:] if text.startswith("-") else text
        if len(digits) > _MAX_JSON_INTEGER_DIGITS:
            raise ValueError("JSON integer exceeds digit limit")
        return int(text)

    def parse_bounded_float(text: str) -> float:
        if len(text) > _MAX_JSON_INTEGER_DIGITS * 2:
            raise ValueError("JSON float exceeds character limit")
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("non-finite number is not valid JSON")
        return value

    decoded = raw.decode("utf-8", errors="strict")
    value = json.loads(
        decoded,
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
        parse_int=parse_bounded_int,
        parse_float=parse_bounded_float,
    )
    if not isinstance(value, dict):
        raise ValueError("protocol document must be an object")
    return cast(dict[str, object], value)


def _canonical_json(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _normalize_json(value: object, *, depth: int = 0) -> JsonValue:
    if depth > 64:
        raise ValueError("JSON value exceeds nesting limit")
    if value is None or type(value) in (bool, int, str):
        return cast(JsonScalar, value)
    if type(value) is float:
        if not math.isfinite(cast(float, value)):
            raise ValueError("non-finite number is not valid JSON")
        return cast(float, value)
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            normalized[key] = _normalize_json(item, depth=depth + 1)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item, depth=depth + 1) for item in value]
    raise TypeError("value is not JSON serializable")


def _normalize_generations(
    values: Mapping[str, object],
) -> dict[str, FileGeneration]:
    if not isinstance(values, Mapping):
        raise TypeError("generation bindings must be an object")
    normalized: dict[str, FileGeneration] = {}
    for name, value in values.items():
        if not isinstance(name, str) or not _BINDING_RE.fullmatch(name):
            raise ValueError("invalid generation binding name")
        if isinstance(value, FileGeneration):
            normalized[name] = value
        elif isinstance(value, Mapping):
            normalized[name] = FileGeneration.from_dict(value)
        else:
            raise TypeError("invalid file generation")
    return normalized


def _generation_document(
    generations: Mapping[str, FileGeneration],
) -> dict[str, JsonValue]:
    return {name: value.to_dict() for name, value in generations.items()}


def _optional_stat_int(value: os.stat_result, name: str) -> int | None:
    result = getattr(value, name, None)
    return (
        int(result)
        if isinstance(result, int) and not isinstance(result, bool)
        else None
    )


def _strict_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return cast(int, value)


def _optional_strict_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    return _strict_int(value, name)


def _strict_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _strict_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _is_digest(value: str) -> bool:
    return len(value) == _DIGEST_HEX_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def _validate_generation_bindings(
    limit_profile_id: str,
    schema_generation: int,
    pipeline_generation: str,
) -> None:
    if not _PROFILE_RE.fullmatch(limit_profile_id):
        raise ValueError("invalid supervisor limit profile id")
    if type(schema_generation) is not int or schema_generation < 1:
        raise ValueError("schema generation must be a positive integer")
    if not _GENERATION_RE.fullmatch(pipeline_generation):
        raise ValueError("invalid pipeline generation")


def _validate_command(command: Sequence[str | os.PathLike[str]]) -> list[str]:
    if not command:
        raise SupervisorError("invalid_worker_command")
    result: list[str] = []
    for part in command:
        text = os.fspath(part)
        if not text or "\x00" in text:
            raise SupervisorError("invalid_worker_command")
        result.append(text)
    return result


def _payload_sensitive_strings(payload: JsonValue) -> tuple[str, ...]:
    found: list[str] = []

    def visit(value: JsonValue) -> None:
        if isinstance(value, str):
            if os.path.isabs(value) or _WINDOWS_PATH_RE.fullmatch(value):
                found.append(value)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(key)
                visit(item)

    visit(payload)
    return tuple(dict.fromkeys(found))


def _reject_sensitive_process_metadata(
    command: Sequence[str], values: Sequence[str]
) -> None:
    if any(value and value in part for value in values for part in command):
        raise SupervisorError("unsafe_worker_process_metadata")


def _sanitized_environment(sensitive_values: Sequence[str]) -> dict[str, str]:
    environment: dict[str, str] = {}
    for name, value in os.environ.items():
        if any(
            sensitive and (sensitive in name or sensitive in value)
            for sensitive in sensitive_values
        ):
            continue
        environment[name] = value
    return environment


def _sanitize_diagnostics(raw: bytes, values: Sequence[str], limit: int) -> str:
    text = raw[:limit].decode("utf-8", errors="replace")
    for value in sorted((item for item in values if item), key=len, reverse=True):
        text = text.replace(value, "<redacted>")
    text = _WINDOWS_PATH_RE.sub("<path>", text)
    text = _POSIX_PATH_RE.sub("<path>", text)
    return "".join(
        character if character in "\n\r\t" or ord(character) >= 32 else "�"
        for character in text
    )


def _sanitize_details(
    value: object, sensitive_values: Sequence[str]
) -> dict[str, JsonValue]:
    normalized = _normalize_json(value)
    if not isinstance(normalized, dict):
        return {}

    def sanitize(item: JsonValue) -> JsonValue:
        if isinstance(item, str):
            data = item.encode("utf-8", errors="replace")
            return _sanitize_diagnostics(data, sensitive_values, 4096)
        if isinstance(item, list):
            return [sanitize(child) for child in item]
        if isinstance(item, dict):
            result: dict[str, JsonValue] = {}
            for key, child in item.items():
                sanitized_key = _sanitize_diagnostics(
                    key.encode("utf-8", errors="replace"),
                    sensitive_values,
                    4096,
                )
                candidate = sanitized_key
                suffix = 2
                while candidate in result:
                    candidate = f"{sanitized_key}#{suffix}"
                    suffix += 1
                result[candidate] = sanitize(child)
            return result
        return item

    return cast(dict[str, JsonValue], sanitize(normalized))


def _load_psutil() -> Any:
    """Load the optional PPTX-lane monitor dependency at first supervision."""

    global psutil
    if psutil is None:
        try:
            loaded = importlib.import_module("psutil")
        except (ImportError, OSError, RuntimeError) as exc:
            raise SupervisorError(
                "worker_monitor_unavailable",
                {"dependency": "psutil"},
            ) from exc
        psutil = loaded
    else:
        loaded = psutil
    actual_version = getattr(loaded, "__version__", None)
    if actual_version != PSUTIL_REQUIRED_VERSION:
        raise SupervisorError(
            "worker_monitor_unavailable",
            {
                "dependency": "psutil",
                "required_version": PSUTIL_REQUIRED_VERSION,
                "actual_version": (
                    actual_version
                    if isinstance(actual_version, str) and len(actual_version) <= 64
                    else None
                ),
            },
        )
    return loaded


def _same_process_is_alive(process: Any, psutil_module: Any) -> bool:
    try:
        return process.is_running() and process.status() != psutil_module.STATUS_ZOMBIE
    except (psutil_module.NoSuchProcess, psutil_module.ZombieProcess):
        return False
    except (psutil_module.AccessDenied, OSError) as exc:
        raise SupervisorError("worker_monitor_unavailable") from exc


def _windows_creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


__all__ = [
    "FileGeneration",
    "DiagnosticReceipt",
    "PROTOCOL_VERSION",
    "PSUTIL_REQUIRED_VERSION",
    "SupervisorError",
    "SupervisorLimits",
    "WorkerCredentials",
    "WorkerRequest",
    "WorkerResult",
    "build_worker_request",
    "isolate_protocol_output",
    "read_worker_request",
    "run_authenticated_worker",
    "write_worker_response",
]

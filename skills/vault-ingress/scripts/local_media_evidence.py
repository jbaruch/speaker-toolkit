#!/usr/bin/env python3
"""Authenticated, bounded inspection of generic audio and video-with-audio."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any, Iterator, NoReturn, cast

from artifact_locator import (
    ArtifactLocatorError,
    materialize_artifact_locator,
    materialize_native_root,
)
from artifact_metadata import (
    ArtifactMetadataMalformed,
    ArtifactMetadataReceipt,
    ArtifactMetadataUnavailable,
    METADATA_SCHEMA_VERSION,
    WINDOWS_REPARSE_POINT_ATTRIBUTE,
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
    isolate_protocol_output,
    read_worker_request,
    run_authenticated_worker,
    write_worker_response,
)
from local_media_contract import (
    CONTAINER_BY_SUFFIX,
    MEDIA_DIGEST_CHUNK_BYTES,
    MEDIA_FFPROBE_STDERR_BYTES,
    MEDIA_FFPROBE_STDOUT_BYTES,
    MEDIA_METADATA_LIMITS,
    MEDIA_PIPELINE_VERSION,
    MEDIA_PROBE_LIMITS,
    MEDIA_SCHEMA_VERSION,
    LocalMediaError,
    MediaArtifactProbe,
    decode_media_probe,
    parse_media_facts,
    refuse,
    validate_available_generation,
)
from local_media_process import run_media_tool


WORKER_FLAG = "--supervised-worker"
METADATA_OPERATION = "local_media_metadata"
PROBE_OPERATION = "local_media_probe"
CHECK_OPERATION = "local_media_check"
_LOCAL_FAILURES = frozenset(
    {
        "media_artifact_unavailable",
        "media_cloud_placeholder_unavailable",
        "media_size_limit",
        "media_duration_limit",
        "media_duration_unavailable",
        "media_stream_limit",
        "media_no_audio_stream",
        "media_no_usable_audio_stream",
        "media_invalid_container",
        "media_parser_rejected",
        "media_parser_repair_required",
        "media_dependency_unavailable",
        "media_generation_changed",
        "media_ffprobe_stdout_limit",
        "media_ffprobe_stderr_limit",
        "media_pipe_failed",
        "media_private_workspace_unavailable",
        "media_cleanup_failed",
    }
)


def _worker_command() -> list[str]:
    return [sys.executable, str(Path(__file__).resolve()), WORKER_FLAG]


def _invoke_worker(
    operation: str,
    expected: dict[str, FileGeneration],
    payload: dict[str, Any],
    limits: SupervisorLimits,
) -> WorkerResult:
    command = _worker_command()
    try:
        result = run_authenticated_worker(
            command,
            operation,
            expected,
            cast(JsonValue, payload),
            limits,
            immutable_process_identity=command[:2],
            sensitive_values=tuple(
                value
                for value in (payload.get("media_path"), payload.get("trusted_root"))
                if value
            ),
            schema_generation=MEDIA_SCHEMA_VERSION,
            pipeline_generation=MEDIA_PIPELINE_VERSION,
        )
    except SupervisorError as exc:
        reason = exc.reason_code
        if reason in _LOCAL_FAILURES:
            raise LocalMediaError(reason) from exc
        if reason == "worker_generation_changed":
            reason = "media_generation_changed"
        elif reason == "worker_timeout":
            reason = "media_worker_timeout"
        elif reason in {
            "worker_memory_limit_exceeded",
            "worker_process_limit_exceeded",
            "worker_input_limit_exceeded",
            "worker_output_limit_exceeded",
            "worker_diagnostic_limit_exceeded",
        }:
            reason = "media_worker_resource_limit"
        elif reason == "worker_cleanup_failed":
            reason = "media_cleanup_failed"
        else:
            reason = "media_worker_failed"
        raise LocalMediaError(reason) from exc
    if result.diagnostics != DiagnosticReceipt.empty():
        refuse("media_probe_malformed_result")
    return result


def _request_paths(path: Any, trusted_root: Any) -> tuple[Path, Path | None]:
    try:
        root = (
            materialize_native_root(trusted_root) if trusted_root is not None else None
        )
        artifact = materialize_artifact_locator(path, trusted_root=root)
    except ArtifactLocatorError as exc:
        raise LocalMediaError("media_locator_invalid") from exc
    if artifact.suffix.lower() not in CONTAINER_BY_SUFFIX:
        refuse("media_unsupported_suffix")
    return artifact, root


def _path_payload(artifact: Path, root: Path | None) -> dict[str, Any]:
    return {
        "media_path": str(artifact),
        "trusted_root": str(root) if root is not None else None,
        "workspace": None,
    }


def _bindings(receipt: ArtifactMetadataReceipt) -> dict[str, FileGeneration]:
    result = {"media": receipt.generation}
    if receipt.root_generation is not None:
        result["media_root"] = receipt.root_generation
    return result


def _decode_metadata(value: Any, root: Path | None) -> ArtifactMetadataReceipt:
    if not isinstance(value, Mapping) or type(value.get("schema_version")) is not int:
        refuse("media_probe_malformed_result")
    try:
        receipt = decode_artifact_metadata_payload(
            value,
            unavailable_reason_code="media_artifact_unavailable",
            cloud_reparse_tags=frozenset(),
        )
    except ArtifactMetadataUnavailable as exc:
        raise LocalMediaError("media_artifact_unavailable") from exc
    except ArtifactMetadataMalformed as exc:
        raise LocalMediaError("media_probe_malformed_result") from exc
    if (root is None) != (receipt.root_generation is None):
        refuse("media_probe_malformed_result")
    validate_available_generation(receipt.generation)
    return receipt


def probe_local_media(path: Any, *, trusted_root: Any = None) -> MediaArtifactProbe:
    """Do no byte I/O in the owner; admit metadata before the probe worker starts."""
    artifact, root = _request_paths(path, trusted_root)
    payload = _path_payload(artifact, root)
    metadata = _invoke_worker(METADATA_OPERATION, {}, payload, MEDIA_METADATA_LIMITS)
    receipt = _decode_metadata(metadata.payload, root)
    with private_media_workspace() as workspace:
        payload["workspace"] = workspace
        result = _invoke_worker(
            PROBE_OPERATION, _bindings(receipt), payload, MEDIA_PROBE_LIMITS
        )
        return decode_media_probe(
            result.payload, receipt.generation, receipt.root_generation
        )


@contextmanager
def private_media_workspace() -> Iterator[dict[str, Any]]:
    """The owner cleans up even after a timed-out or killed worker cannot.

    Only toolkit-created scratch paths are touched here, never source media.
    TemporaryDirectory also restores read-only permissions during Windows cleanup.
    """
    try:
        directory = tempfile.TemporaryDirectory(prefix="speaker-toolkit-local-media-")
    except OSError as exc:
        raise LocalMediaError("media_private_workspace_unavailable") from exc
    try:
        try:
            path = Path(directory.name)
            os.chmod(path, 0o700)
            workspace = {
                "path": str(path),
                "generation": FileGeneration.from_stat(path.lstat()).to_dict(),
            }
        except OSError as exc:
            raise LocalMediaError("media_private_workspace_unavailable") from exc
        yield workspace
    finally:
        try:
            directory.cleanup()
        except OSError as exc:
            raise LocalMediaError("media_cleanup_failed") from exc


def _admit_workspace(value: Any) -> Path:
    if not isinstance(value, Mapping) or set(value) != {"path", "generation"}:
        raise SupervisorError("invalid_worker_request")
    try:
        path = materialize_native_root(value["path"])
        generation = FileGeneration.from_dict(value["generation"])
    except (ArtifactLocatorError, TypeError, ValueError) as exc:
        raise SupervisorError("invalid_worker_request") from exc
    try:
        actual = FileGeneration.from_stat(path.lstat())
        if (
            actual != generation
            or not stat.S_ISDIR(actual.mode)
            or (actual.file_attributes or 0) & WINDOWS_REPARSE_POINT_ATTRIBUTE
        ):
            refuse("media_private_workspace_unavailable")
        with os.scandir(path) as entries:
            if next(entries, None) is not None:
                refuse("media_private_workspace_unavailable")
    except OSError as exc:
        raise LocalMediaError("media_private_workspace_unavailable") from exc
    return path


def check_media_generation(
    path: Any, probe: MediaArtifactProbe, *, trusted_root: Any = None
) -> None:
    """Recheck metadata through a bounded worker immediately before bundle commit."""
    artifact, root = _request_paths(path, trusted_root)
    receipt = ArtifactMetadataReceipt(probe.generation, probe.root_generation, None)
    result = _invoke_worker(
        CHECK_OPERATION,
        _bindings(receipt),
        _path_payload(artifact, root),
        MEDIA_METADATA_LIMITS,
    )
    current = _decode_metadata(result.payload, root)
    if current != receipt:
        refuse("media_generation_changed")


def _inspect(path: Path, root: Path | None) -> ArtifactMetadataReceipt:
    try:
        receipt = inspect_metadata_generation(
            path, trusted_root=root, cloud_reparse_tags=frozenset()
        )
    except ArtifactMetadataUnavailable as exc:
        raise LocalMediaError("media_artifact_unavailable") from exc
    except ArtifactMetadataMalformed as exc:
        raise LocalMediaError("media_locator_invalid") from exc
    validate_available_generation(receipt.generation)
    return receipt


def _metadata_payload(receipt: ArtifactMetadataReceipt) -> dict[str, Any]:
    return {
        "schema_version": METADATA_SCHEMA_VERSION,
        "status": "available",
        "generation": receipt.generation.to_dict(),
        "root_generation": receipt.root_generation.to_dict()
        if receipt.root_generation is not None
        else None,
        "reparse_tag": receipt.reparse_tag,
    }


def _require_descriptor(descriptor: int, expected: FileGeneration) -> None:
    actual = FileGeneration.from_stat(os.fstat(descriptor))
    validate_available_generation(actual)
    if actual != expected:
        refuse("media_generation_changed")


@contextmanager
def _private_snapshot(
    path: Path, expected: FileGeneration, workspace: Path
) -> Iterator[tuple[Path, str, int]]:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_BINARY", 0),
        )
    except OSError as exc:
        raise LocalMediaError("media_artifact_unavailable") from exc
    try:
        _require_descriptor(descriptor, expected)
        snapshot = workspace / f"source{path.suffix.lower()}"
        digest = hashlib.sha256()
        copied = 0
        with snapshot.open("xb") as output:
            os.chmod(snapshot, 0o600)
            while chunk := os.read(descriptor, MEDIA_DIGEST_CHUNK_BYTES):
                copied += len(chunk)
                if copied > expected.size:
                    refuse("media_generation_changed")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if copied != expected.size:
            refuse("media_generation_changed")
        _require_descriptor(descriptor, expected)
        os.chmod(snapshot, stat.S_IREAD)
        yield snapshot, digest.hexdigest(), descriptor
    except OSError as exc:
        raise LocalMediaError("media_artifact_unavailable") from exc
    finally:
        os.close(descriptor)


def _run_ffprobe(path: Path) -> tuple[bytes, DiagnosticReceipt]:
    executable = shutil.which("ffprobe")
    if executable is None:
        refuse("media_dependency_unavailable")
    command = [
        executable,
        "-v",
        "error",
        "-show_entries",
        "format=format_name,duration:stream=codec_type,codec_name,channels,sample_rate,duration:stream_disposition=attached_pic",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = run_media_tool(
            command,
            stdout_limit=MEDIA_FFPROBE_STDOUT_BYTES,
            stderr_limit=MEDIA_FFPROBE_STDERR_BYTES,
        )
    except LocalMediaError as exc:
        reason = {
            "media_tool_stdout_limit": "media_ffprobe_stdout_limit",
            "media_tool_stderr_limit": "media_ffprobe_stderr_limit",
        }.get(exc.reason_code, exc.reason_code)
        raise LocalMediaError(reason) from exc
    if result.returncode:
        refuse("media_parser_rejected")
    if result.diagnostics.byte_count:
        refuse("media_parser_repair_required")
    return result.stdout, result.diagnostics


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            refuse("media_parser_rejected")
        result[key] = value
    return result


def _reject_constant(_value: str) -> NoReturn:
    refuse("media_parser_rejected")


def _probe(
    path: Path, root: Path | None, before: ArtifactMetadataReceipt, workspace: Path
) -> dict[str, Any]:
    with _private_snapshot(path, before.generation, workspace) as (
        snapshot,
        digest,
        descriptor,
    ):
        snapshot_generation = FileGeneration.from_stat(snapshot.lstat())
        raw, diagnostics = _run_ffprobe(snapshot)
        try:
            document = json.loads(
                raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant
            )
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise LocalMediaError("media_parser_rejected") from exc
        facts = parse_media_facts(document, CONTAINER_BY_SUFFIX[path.suffix.lower()])
        if (
            FileGeneration.from_stat(snapshot.lstat()) != snapshot_generation
            or _inspect(path, root) != before
        ):
            refuse("media_generation_changed")
        _require_descriptor(descriptor, before.generation)
        return {
            "schema_version": MEDIA_SCHEMA_VERSION,
            "source_sha256": digest,
            "source_size_bytes": before.generation.size,
            "parser_diagnostics": diagnostics.to_dict(),
            **facts,
        }


def _dispatch(
    request: WorkerRequest,
) -> tuple[dict[str, Any], dict[str, FileGeneration]]:
    if (
        request.schema_generation != MEDIA_SCHEMA_VERSION
        or request.pipeline_generation != MEDIA_PIPELINE_VERSION
    ):
        raise SupervisorError("invalid_worker_request")
    payload = request.payload
    if not isinstance(payload, Mapping) or set(payload) != {
        "media_path",
        "trusted_root",
        "workspace",
    }:
        raise SupervisorError("invalid_worker_request")
    expected_profile = (
        MEDIA_PROBE_LIMITS
        if request.operation == PROBE_OPERATION
        else MEDIA_METADATA_LIMITS
    )
    if (
        request.operation not in {METADATA_OPERATION, CHECK_OPERATION, PROBE_OPERATION}
        or request.limit_profile_id != expected_profile.profile_id
    ):
        raise SupervisorError("invalid_worker_request")
    if request.operation != PROBE_OPERATION and payload["workspace"] is not None:
        raise SupervisorError("invalid_worker_request")
    if request.operation == METADATA_OPERATION and request.expected_generations:
        raise SupervisorError("invalid_worker_request")
    try:
        path, root = canonicalize_trusted_artifact_locator(
            payload["media_path"], payload["trusted_root"]
        )
    except ArtifactMetadataMalformed as exc:
        raise SupervisorError("invalid_worker_request") from exc
    if path.suffix.lower() not in CONTAINER_BY_SUFFIX:
        raise SupervisorError("invalid_worker_request")
    before = _inspect(path, root)
    observed = _bindings(before)
    if request.operation == METADATA_OPERATION:
        return _metadata_payload(before), {}
    if set(request.expected_generations) != set(observed):
        raise SupervisorError("invalid_worker_request")
    if observed != request.expected_generations:
        refuse("media_generation_changed")
    if request.operation == CHECK_OPERATION:
        return _metadata_payload(before), observed
    result = _probe(path, root, before, _admit_workspace(payload["workspace"]))
    if _inspect(path, root) != before:
        refuse("media_generation_changed")
    return result, observed


def _worker_main() -> int:
    request = read_worker_request(max_input_bytes=MEDIA_METADATA_LIMITS.max_input_bytes)
    stream = isolate_protocol_output()
    try:
        try:
            payload, observed = _dispatch(request)
            write_worker_response(
                request,
                payload=cast(JsonValue, payload),
                observed_generations=observed,
                stream=stream,
                max_output_bytes=MEDIA_PROBE_LIMITS.max_output_bytes,
            )
        except (LocalMediaError, SupervisorError) as exc:
            reason = (
                exc.reason_code
                if isinstance(exc, SupervisorError)
                or exc.reason_code in _LOCAL_FAILURES
                else "media_artifact_unavailable"
            )
            write_worker_response(
                request,
                error=SupervisorError(reason),
                observed_generations=request.expected_generations,
                stream=stream,
                max_output_bytes=MEDIA_PROBE_LIMITS.max_output_bytes,
            )
    finally:
        stream.close()
    return 0


def _main() -> int:
    if sys.argv[1:] != [WORKER_FLAG]:
        print(
            "local_media_evidence.py is a library; use fetch-transcript.py",
            file=sys.stderr,
        )
        return 2
    try:
        return _worker_main()
    except SupervisorError as exc:
        print(f"local media worker failed: {exc.reason_code}", file=sys.stderr)
        return 2
    # A nonzero child with no authenticated frame is the supervisor's closed
    # crash signal. Emit no traceback/path/provider payload: propagation would
    # leak parser state onto that boundary. outer-boundary-process-contract.
    except Exception:  # noqa: BLE001
        print("local media worker failed: unexpected_error", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())

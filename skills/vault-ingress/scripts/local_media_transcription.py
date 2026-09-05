#!/usr/bin/env python3
"""Run local Whisper in an authenticated worker bound to established media facts.

An existing video/media probe is reused without another probe, copy, or hash.
The worker holds a source descriptor and rechecks its generation and pathname
around transcription. The caller rechecks again immediately before committing
the transcript bundle. No transcript or receipt is written by this module.
"""

from __future__ import annotations

from collections.abc import Mapping
import importlib
import os
from pathlib import Path
import sys
from typing import Any, cast

from artifact_metadata import canonicalize_trusted_artifact_locator
from artifact_supervisor import (
    FileGeneration,
    JsonValue,
    SupervisorError,
    WorkerRequest,
    isolate_protocol_output,
    read_worker_request,
    run_authenticated_worker,
    write_worker_response,
)
from local_media_contract import (
    MEDIA_PIPELINE_VERSION,
    MEDIA_SCHEMA_VERSION,
    MEDIA_WHISPER_LIMITS,
    LocalMediaError,
    MediaArtifactProbe,
    bounded_whisper_result,
    refuse,
    reuse_video_probe,
)
from local_media_evidence import (
    _bindings,
    _inspect,
    _path_payload,
    _request_paths,
    _require_descriptor,
    check_media_generation,
    probe_local_media,
)


WORKER_FLAG = "--supervised-worker"
WHISPER_OPERATION = "local_media_transcribe"
WHISPER_FAILURES = frozenset(
    {
        "whisper_dependency_unavailable",
        "whisper_provider_failed",
        "whisper_result_invalid",
        "whisper_text_limit",
        "whisper_language_invalid",
        "whisper_segments_invalid",
        "whisper_segment_limit",
        "whisper_segment_text_limit",
        "media_generation_changed",
        "media_artifact_unavailable",
        "media_cloud_placeholder_unavailable",
        "media_size_limit",
    }
)
_PROVIDER_ERRORS = (
    ImportError,
    OSError,
    RuntimeError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)


def _model(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 512
        or "\0" in value
    ):
        refuse("whisper_model_invalid")
    return value


def transcribe_local_media(
    path: Any,
    model: str,
    *,
    probe: Any = None,
    trusted_root: Any = None,
) -> tuple[MediaArtifactProbe, dict[str, Any]]:
    """Return established media facts and bounded speech; never write a bundle."""
    model = _model(model)
    artifact, root = _request_paths(path, trusted_root)
    if probe is None:
        established = probe_local_media(artifact, trusted_root=root)
    elif isinstance(probe, MediaArtifactProbe):
        established = probe
    else:
        established = reuse_video_probe(probe)
    check_media_generation(artifact, established, trusted_root=root)
    expected = {"media": established.generation}
    if established.root_generation is not None:
        expected["media_root"] = established.root_generation
    payload = _path_payload(artifact, root)
    payload.pop("workspace")
    payload["model"] = model
    command = [sys.executable, str(Path(__file__).resolve()), WORKER_FLAG]
    try:
        result = run_authenticated_worker(
            command,
            WHISPER_OPERATION,
            expected,
            cast(JsonValue, payload),
            MEDIA_WHISPER_LIMITS,
            immutable_process_identity=command[:2],
            sensitive_values=(str(artifact), model),
            schema_generation=MEDIA_SCHEMA_VERSION,
            pipeline_generation=MEDIA_PIPELINE_VERSION,
        )
    except SupervisorError as exc:
        reason = exc.reason_code
        if reason not in WHISPER_FAILURES:
            reason = {
                "worker_generation_changed": "media_generation_changed",
                "worker_timeout": "whisper_worker_timeout",
                "worker_memory_limit_exceeded": "whisper_worker_resource_limit",
                "worker_process_limit_exceeded": "whisper_worker_resource_limit",
                "worker_input_limit_exceeded": "whisper_worker_resource_limit",
                "worker_output_limit_exceeded": "whisper_worker_resource_limit",
                "worker_diagnostic_limit_exceeded": "whisper_worker_resource_limit",
                "worker_cleanup_failed": "media_cleanup_failed",
            }.get(reason, "whisper_worker_failed")
        raise LocalMediaError(reason) from exc
    if not isinstance(result.payload, Mapping) or set(result.payload) != {
        "text",
        "language",
        "segments",
    }:
        refuse("whisper_result_invalid")
    speech = bounded_whisper_result(result.payload)
    check_media_generation(artifact, established, trusted_root=root)
    return established, speech


def _transcribe_with_mlx(path: Path, model: str) -> dict[str, Any]:
    """Only the actual Apple-Silicon provider call is platform-bound."""
    try:
        provider = importlib.import_module("mlx_whisper")
    except _PROVIDER_ERRORS as exc:
        raise LocalMediaError("whisper_dependency_unavailable") from exc
    try:
        value = provider.transcribe(str(path), path_or_hf_repo=model)
    except _PROVIDER_ERRORS as exc:
        raise LocalMediaError("whisper_provider_failed") from exc
    return bounded_whisper_result(value)


def _dispatch(
    request: WorkerRequest,
) -> tuple[dict[str, Any], dict[str, FileGeneration]]:
    payload = request.payload
    if (
        request.operation != WHISPER_OPERATION
        or request.limit_profile_id != MEDIA_WHISPER_LIMITS.profile_id
        or request.schema_generation != MEDIA_SCHEMA_VERSION
        or request.pipeline_generation != MEDIA_PIPELINE_VERSION
        or not isinstance(payload, Mapping)
        or set(payload) != {"media_path", "trusted_root", "model"}
    ):
        raise SupervisorError("invalid_worker_request")
    model = _model(payload["model"])
    path, root = canonicalize_trusted_artifact_locator(
        payload["media_path"], payload["trusted_root"]
    )
    before = _inspect(path, root)
    observed = _bindings(before)
    if observed != request.expected_generations:
        refuse("media_generation_changed")
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
        _require_descriptor(descriptor, before.generation)
        speech = _transcribe_with_mlx(path, model)
        _require_descriptor(descriptor, before.generation)
        if _inspect(path, root) != before:
            refuse("media_generation_changed")
        return speech, observed
    except OSError as exc:
        raise LocalMediaError("media_artifact_unavailable") from exc
    finally:
        os.close(descriptor)


def _worker_main() -> int:
    request = read_worker_request(max_input_bytes=MEDIA_WHISPER_LIMITS.max_input_bytes)
    stream = isolate_protocol_output()
    try:
        try:
            speech, observed = _dispatch(request)
            write_worker_response(
                request,
                payload=cast(JsonValue, speech),
                observed_generations=observed,
                stream=stream,
                max_output_bytes=MEDIA_WHISPER_LIMITS.max_output_bytes,
            )
        except (LocalMediaError, SupervisorError) as exc:
            reason = (
                exc.reason_code
                if isinstance(exc, SupervisorError)
                or exc.reason_code in WHISPER_FAILURES
                else "whisper_worker_failed"
            )
            write_worker_response(
                request,
                error=SupervisorError(reason),
                observed_generations=request.expected_generations,
                stream=stream,
                max_output_bytes=MEDIA_WHISPER_LIMITS.max_output_bytes,
            )
    finally:
        stream.close()
    return 0


def _main() -> int:
    if sys.argv[1:] != [WORKER_FLAG]:
        print(
            "local_media_transcription.py is a library; use fetch-transcript.py",
            file=sys.stderr,
        )
        return 2
    try:
        return _worker_main()
    except SupervisorError as exc:
        print(f"Whisper worker failed: {exc.reason_code}", file=sys.stderr)
        return 2
    # A nonzero child without an authenticated response is the supervisor's
    # closed crash signal. Emit only a fixed diagnostic; an unhandled traceback
    # would leak model/path/provider data. outer-boundary-process-contract.
    except Exception:  # noqa: BLE001
        print("Whisper worker failed: unexpected_error", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())

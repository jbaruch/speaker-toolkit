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
import importlib.metadata
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
    _admit_workspace,
    _bindings,
    _inspect,
    _path_payload,
    _request_paths,
    _require_descriptor,
    check_media_generation,
    probe_local_media,
    private_media_workspace,
)
from local_media_sampling import extract_speech_clip, validate_sample_window
from local_media_words import (
    DEFAULT_WORD_MODEL,
    WORD_VALIDATION_FAILURES,
    WordSampleError,
    normalize_word_result,
    validate_word_sample,
)


WORKER_FLAG = "--supervised-worker"
WHISPER_OPERATION = "local_media_transcribe"
WORDS_OPERATION = "local_media_sample_words"
WHISPER_FAILURES = frozenset(
    {
        *WORD_VALIDATION_FAILURES,
        "whisper_dependency_unavailable",
        "whisper_provider_failed",
        "whisper_result_invalid",
        "whisper_repetitive_text",
        "whisper_text_limit",
        "whisper_language_invalid",
        "whisper_segments_invalid",
        "whisper_segment_limit",
        "whisper_segment_text_limit",
        "media_generation_changed",
        "media_artifact_unavailable",
        "media_cloud_placeholder_unavailable",
        "media_size_limit",
        "whisper_word_sample_invalid",
        "whisper_sample_window_invalid",
        "whisper_sample_decode_failed",
        "whisper_sample_duration_mismatch",
        "whisper_model_download_failed",
        "whisper_provider_version_unsupported",
        "media_private_workspace_unavailable",
        "media_cleanup_failed",
        "media_dependency_unavailable",
        "media_tool_stdout_limit",
        "media_tool_stderr_limit",
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


def transcribe_local_words(
    path: Any,
    *,
    sample_start_seconds: float,
    sample_duration_seconds: float,
    probe: Any = None,
    trusted_root: Any = None,
) -> tuple[MediaArtifactProbe, dict[str, Any]]:
    """Sample fresh real word timing; never consume or write catalog transcripts."""
    artifact, root = _request_paths(path, trusted_root)
    if probe is None:
        established = probe_local_media(artifact, trusted_root=root)
    elif isinstance(probe, MediaArtifactProbe):
        established = probe
    else:
        established = reuse_video_probe(probe)
    validate_sample_window(
        sample_start_seconds, sample_duration_seconds, established.duration_seconds
    )
    check_media_generation(artifact, established, trusted_root=root)
    expected = {"media": established.generation}
    if established.root_generation is not None:
        expected["media_root"] = established.root_generation
    payload = _path_payload(artifact, root)
    payload.update(
        source_sha256=established.source_sha256,
        source_duration_seconds=established.duration_seconds,
        sample_start_seconds=sample_start_seconds,
        sample_duration_seconds=sample_duration_seconds,
    )
    command = [sys.executable, str(Path(__file__).resolve()), WORKER_FLAG]
    try:
        with private_media_workspace() as workspace:
            payload["workspace"] = workspace
            result = run_authenticated_worker(
                command,
                WORDS_OPERATION,
                expected,
                cast(JsonValue, payload),
                MEDIA_WHISPER_LIMITS,
                immutable_process_identity=command[:2],
                sensitive_values=(str(artifact),),
                schema_generation=MEDIA_SCHEMA_VERSION,
                pipeline_generation=MEDIA_PIPELINE_VERSION,
            )
            speech = validate_word_sample(result.payload)
            if (
                speech["source_sha256"] != established.source_sha256
                or speech["source_duration_seconds"] != established.duration_seconds
                or speech["sample_start_seconds"] != sample_start_seconds
                or abs(speech["sample_duration_seconds"] - sample_duration_seconds)
                > 1 / 16000
                or speech["model"] != DEFAULT_WORD_MODEL
            ):
                refuse("whisper_word_sample_invalid")
            check_media_generation(artifact, established, trusted_root=root)
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
        if reason == "whisper_word_sample_invalid_word_segment" and set(
            exc.details
        ) == {"word_timing"}:
            raise WordSampleError(exc.details["word_timing"]) from exc
        raise LocalMediaError(reason) from exc
    return established, speech


def _word_model_path() -> tuple[str, str]:
    """Resolve the supported immutable weights before the native provider call."""
    try:
        version = importlib.metadata.version("mlx-whisper")
        hub = importlib.import_module("huggingface_hub")
    except _PROVIDER_ERRORS as exc:
        raise LocalMediaError("whisper_dependency_unavailable") from exc
    # Native language-detection integration is verified against this API.
    # Renew with the optional whisper manifest pin in a focused change.
    if version != "0.4.3":
        refuse("whisper_provider_version_unsupported")
    try:
        path = hub.snapshot_download(
            repo_id=DEFAULT_WORD_MODEL["id"],
            revision=DEFAULT_WORD_MODEL["revision"],
            allow_patterns=["config.json", "weights.safetensors", "weights.npz"],
            max_workers=1,
            token=False,
        )
    except _PROVIDER_ERRORS as exc:
        raise LocalMediaError("whisper_model_download_failed") from exc
    return _model(path), version


def _transcribe_with_mlx(
    path: Path, model: str, *, word_timestamps: bool = False
) -> dict[str, Any]:
    """Only the actual Apple-Silicon provider call is platform-bound."""
    try:
        provider = importlib.import_module("mlx_whisper")
    except _PROVIDER_ERRORS as exc:
        raise LocalMediaError("whisper_dependency_unavailable") from exc
    try:
        if not word_timestamps:
            value = provider.transcribe(
                str(path),
                path_or_hf_repo=model,
                temperature=0.0,
                condition_on_previous_text=False,
                verbose=None,
            )
        else:
            value = provider.transcribe(
                str(path),
                path_or_hf_repo=model,
                word_timestamps=True,
                temperature=0.0,
                condition_on_previous_text=False,
                verbose=None,
            )
            if not isinstance(value, Mapping):
                refuse("whisper_word_sample_invalid")
            # mlx-whisper returns a language label, not its probability. Obtain
            # that probability from the same model's real first-30-second probe.
            native = importlib.import_module("mlx_whisper.transcribe")
            dtype = native.mx.float16
            network = native.ModelHolder.get_model(model, dtype)
            mel = native.log_mel_spectrogram(
                str(path), n_mels=network.dims.n_mels, padding=native.N_SAMPLES
            )
            segment = native.pad_or_trim(mel, native.N_FRAMES, axis=-2).astype(dtype)
            _, probabilities = network.detect_language(segment)
            probability = float(probabilities[value["language"]])
            return {"raw": value, "language_probability": probability}
    except LocalMediaError:
        raise
    except _PROVIDER_ERRORS as exc:
        raise LocalMediaError("whisper_provider_failed") from exc
    return bounded_whisper_result(value)


def _sampled_words(path: Path, payload: Mapping) -> dict[str, Any]:
    validate_sample_window(
        payload["sample_start_seconds"],
        payload["sample_duration_seconds"],
        payload["source_duration_seconds"],
    )
    workspace = _admit_workspace(payload["workspace"])
    clip = extract_speech_clip(
        path,
        workspace,
        start=payload["sample_start_seconds"],
        duration=payload["sample_duration_seconds"],
    )
    model, version = _word_model_path()
    with clip.path.open("rb") as descriptor:
        _require_descriptor(descriptor.fileno(), clip.generation)
        if _inspect(clip.path, None).generation != clip.generation:
            refuse("media_generation_changed")
        result = _transcribe_with_mlx(clip.path, model, word_timestamps=True)
        _require_descriptor(descriptor.fileno(), clip.generation)
        if _inspect(clip.path, None).generation != clip.generation:
            refuse("media_generation_changed")
    return normalize_word_result(
        result["raw"],
        source_sha256=payload["source_sha256"],
        sample_sha256=clip.sha256,
        source_duration_seconds=payload["source_duration_seconds"],
        sample_start_seconds=payload["sample_start_seconds"],
        sample_duration_seconds=clip.duration_seconds,
        provider_version=version,
        model=DEFAULT_WORD_MODEL,
        language_probability=result["language_probability"],
    )


def _dispatch(
    request: WorkerRequest,
) -> tuple[dict[str, Any], dict[str, FileGeneration]]:
    payload = request.payload
    if (
        request.operation not in {WHISPER_OPERATION, WORDS_OPERATION}
        or request.limit_profile_id != MEDIA_WHISPER_LIMITS.profile_id
        or request.schema_generation != MEDIA_SCHEMA_VERSION
        or request.pipeline_generation != MEDIA_PIPELINE_VERSION
        or not isinstance(payload, Mapping)
    ):
        raise SupervisorError("invalid_worker_request")
    fields = {"media_path", "trusted_root"} | (
        {"model"}
        if request.operation == WHISPER_OPERATION
        else {
            "source_sha256",
            "source_duration_seconds",
            "sample_start_seconds",
            "sample_duration_seconds",
            "workspace",
        }
    )
    if set(payload) != fields:
        raise SupervisorError("invalid_worker_request")
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
        speech = (
            _transcribe_with_mlx(path, _model(payload["model"]))
            if request.operation == WHISPER_OPERATION
            else _sampled_words(path, payload)
        )
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
                error=SupervisorError(
                    reason,
                    {"word_timing": exc.word_timing}
                    if isinstance(exc, WordSampleError)
                    else None,
                ),
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

#!/usr/bin/env python3
"""Bounded YouTube metadata/download workers with owner-owned private cleanup.

Download bytes stream from yt-dlp stdout into one literal file with an enforced
byte ceiling. No provider-controlled output template, postprocessor, playlist,
user configuration or plugin can authorize additional artifacts. The downloaded
file still needs the generic-media probe before Whisper may read it.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Iterator, cast

from artifact_supervisor import (
    JsonValue,
    SupervisorError,
    WorkerRequest,
    isolate_protocol_output,
    read_worker_request,
    run_authenticated_worker,
    write_worker_response,
)
from local_media_contract import (
    MEDIA_DOWNLOAD_LIMITS,
    MEDIA_MAX_INPUT_BYTES,
    MEDIA_PIPELINE_VERSION,
    MEDIA_PROVIDER_METADATA_LIMITS,
    MEDIA_SCHEMA_VERSION,
    LocalMediaError,
    positive_duration,
    refuse,
)
from local_media_evidence import _admit_workspace, _inspect, private_media_workspace
from local_media_process import MediaToolResult, run_media_tool
from ytdlp_runtime import YtDlpResolutionError, resolve_ytdlp


WORKER_FLAG = "--supervised-worker"
METADATA_OPERATION = "youtube_media_metadata"
DOWNLOAD_OPERATION = "youtube_media_download"
YOUTUBE_PLAYER_CLIENTS = (None, "mweb", "web_safari", "ios", "tv")
YTDLP_METADATA_BYTES = 1024 * 1024
YTDLP_DIAGNOSTIC_BYTES = 64 * 1024
DOWNLOAD_EXTENSIONS = frozenset({"m4a", "webm", "mp3"})
DOWNLOAD_FORMAT = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio[ext=mp3]"
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
_FORMAT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_DOWNLOAD_FAILURES = frozenset(
    {
        "ytdlp_dependency_unavailable",
        "ytdlp_provider_rejected",
        "ytdlp_metadata_invalid",
        "ytdlp_identity_mismatch",
        "ytdlp_duration_unavailable",
        "ytdlp_format_unavailable",
        "ytdlp_stdout_limit",
        "ytdlp_stderr_limit",
        "ytdlp_download_size_limit",
        "ytdlp_output_invalid",
        "media_pipe_failed",
        "media_cleanup_failed",
        "media_private_workspace_unavailable",
        "media_artifact_unavailable",
        "media_size_limit",
    }
)


def _video_id(value: Any) -> str:
    if not isinstance(value, str) or _VIDEO_ID.fullmatch(value) is None:
        refuse("ytdlp_identity_mismatch")
    return value


def _worker(operation: str, payload: dict[str, Any]) -> Any:
    command = [sys.executable, str(Path(__file__).resolve()), WORKER_FLAG]
    limits = (
        MEDIA_DOWNLOAD_LIMITS
        if operation == DOWNLOAD_OPERATION
        else MEDIA_PROVIDER_METADATA_LIMITS
    )
    try:
        result = run_authenticated_worker(
            command,
            operation,
            {},
            cast(JsonValue, payload),
            limits,
            immutable_process_identity=command[:2],
            schema_generation=MEDIA_SCHEMA_VERSION,
            pipeline_generation=MEDIA_PIPELINE_VERSION,
        )
    except SupervisorError as exc:
        reason = exc.reason_code
        if reason not in _DOWNLOAD_FAILURES:
            reason = {
                "worker_timeout": "ytdlp_worker_timeout",
                "worker_memory_limit_exceeded": "ytdlp_worker_resource_limit",
                "worker_process_limit_exceeded": "ytdlp_worker_resource_limit",
                "worker_input_limit_exceeded": "ytdlp_worker_resource_limit",
                "worker_output_limit_exceeded": "ytdlp_worker_resource_limit",
                "worker_diagnostic_limit_exceeded": "ytdlp_worker_resource_limit",
                "worker_cleanup_failed": "media_cleanup_failed",
            }.get(reason, "ytdlp_worker_failed")
        raise LocalMediaError(reason) from exc
    return result.payload


def _payload(video_id: str, ytdlp: Any, workspace: dict[str, Any]) -> dict[str, Any]:
    if ytdlp is not None and (
        not isinstance(ytdlp, (str, Path)) or not Path(ytdlp).is_absolute()
    ):
        refuse("ytdlp_dependency_unavailable")
    return {
        "video_id": _video_id(video_id),
        "ytdlp": str(ytdlp) if ytdlp is not None else None,
        "workspace": workspace,
    }


def _decode_result(value: Any, video_id: str, *, download: bool) -> dict[str, Any]:
    fields = {"video_id", "duration_seconds"} | (
        {"artifact_name"} if download else set()
    )
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("video_id") != video_id
        or positive_duration(value.get("duration_seconds")) is None
    ):
        refuse("ytdlp_metadata_invalid")
    if download and (
        not isinstance(value["artifact_name"], str)
        or value["artifact_name"] not in {f"audio.{ext}" for ext in DOWNLOAD_EXTENSIONS}
    ):
        refuse("ytdlp_output_invalid")
    return dict(value)


def probe_youtube_media_duration(video_id: str, *, ytdlp: Any = None) -> float:
    """Return one identity-bound provider duration; no media download occurs."""
    with private_media_workspace() as workspace:
        payload = _payload(video_id, ytdlp, workspace)
        value = _decode_result(
            _worker(METADATA_OPERATION, payload), video_id, download=False
        )
        return float(value["duration_seconds"])


@contextmanager
def download_youtube_audio(
    video_id: str, *, ytdlp: Any = None
) -> Iterator[tuple[Path, float]]:
    """Yield one private artifact and provider duration; clean up on every exit."""
    with private_media_workspace() as workspace:
        payload = _payload(video_id, ytdlp, workspace)
        value = _decode_result(
            _worker(DOWNLOAD_OPERATION, payload), video_id, download=True
        )
        yield (
            Path(workspace["path"]) / value["artifact_name"],
            float(value["duration_seconds"]),
        )


def _command(executable: Path, video_id: str, client: str | None) -> list[str]:
    command = [
        str(executable),
        "--ignore-config",
        "--no-plugin-dirs",
        "--no-cache-dir",
        "--no-playlist",
        "--no-progress",
        "--no-colors",
        "--socket-timeout",
        "30",
        "--retries",
        "1",
        "--fragment-retries",
        "1",
        "--abort-on-unavailable-fragments",
    ]
    if client is not None:
        command += ["--extractor-args", f"youtube:player_client={client}"]
    return command + [f"https://www.youtube.com/watch?v={video_id}"]


def _run(
    command: list[str], workspace: Path, *, output: Path | None = None
) -> MediaToolResult:
    try:
        return run_media_tool(
            command,
            stdout_limit=MEDIA_MAX_INPUT_BYTES
            if output is not None
            else YTDLP_METADATA_BYTES,
            stderr_limit=YTDLP_DIAGNOSTIC_BYTES,
            output=output,
            cwd=workspace,
        )
    except LocalMediaError as exc:
        reason = {
            "media_tool_stdout_limit": "ytdlp_download_size_limit"
            if output is not None
            else "ytdlp_stdout_limit",
            "media_tool_stderr_limit": "ytdlp_stderr_limit",
            "media_dependency_unavailable": "ytdlp_dependency_unavailable",
        }.get(exc.reason_code, exc.reason_code)
        raise LocalMediaError(reason) from exc


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            refuse("ytdlp_metadata_invalid")
        result[key] = value
    return result


def _reject_constant(_value: str) -> Any:
    refuse("ytdlp_metadata_invalid")


def _metadata(
    command: list[str], workspace: Path, video_id: str, *, download: bool
) -> dict[str, Any]:
    extra = ["--dump-single-json", "--skip-download"]
    if download:
        extra += ["-f", DOWNLOAD_FORMAT]
    response = _run(command[:-1] + extra + command[-1:], workspace)
    if response.returncode != 0:
        refuse("ytdlp_provider_rejected")
    try:
        value = json.loads(
            response.stdout,
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LocalMediaError("ytdlp_metadata_invalid") from exc
    if not isinstance(value, Mapping) or value.get("id") != video_id:
        refuse("ytdlp_identity_mismatch")
    duration = positive_duration(value.get("duration"))
    if (
        duration is None
        or value.get("is_live") is True
        or value.get("live_status") in ("is_live", "is_upcoming")
    ):
        refuse("ytdlp_duration_unavailable")
    result = {"video_id": video_id, "duration_seconds": duration}
    if download:
        extension, format_id = value.get("ext"), value.get("format_id")
        if (
            not isinstance(extension, str)
            or extension not in DOWNLOAD_EXTENSIONS
            or not isinstance(format_id, str)
            or _FORMAT_ID.fullmatch(format_id) is None
            or value.get("vcodec") != "none"
            or not isinstance(value.get("acodec"), str)
            or value["acodec"] in ("none", "unknown", "")
        ):
            refuse("ytdlp_format_unavailable")
        size = value.get("filesize")
        if size is not None and (
            type(size) is not int or not 0 < size <= MEDIA_MAX_INPUT_BYTES
        ):
            refuse("ytdlp_download_size_limit")
        result.update(extension=extension, format_id=format_id)
    return result


def _require_only_artifact(workspace: Path, artifact: Path) -> None:
    with os.scandir(workspace) as entries:
        first = next(entries, None)
        if (
            first is None
            or first.name != artifact.name
            or next(entries, None) is not None
        ):
            refuse("ytdlp_output_invalid")
    _inspect(artifact, workspace)


def _download(executable: Path, workspace: Path, video_id: str) -> dict[str, Any]:
    for client in YOUTUBE_PLAYER_CLIENTS:
        command = _command(executable, video_id, client)
        try:
            metadata = _metadata(command, workspace, video_id, download=True)
        except LocalMediaError as exc:
            if exc.reason_code != "ytdlp_provider_rejected":
                raise
            continue
        candidate = workspace / f"audio.{metadata['extension']}"
        download = _run(
            command[:-1]
            + [
                "-f",
                metadata["format_id"],
                "-o",
                "-",
                "--no-part",
                "--max-filesize",
                str(MEDIA_MAX_INPUT_BYTES),
            ]
            + command[-1:],
            workspace,
            output=candidate,
        )
        if download.returncode == 0 and download.streamed_bytes > 0:
            _require_only_artifact(workspace, candidate)
            os.chmod(candidate, stat.S_IREAD)
            return {
                "video_id": video_id,
                "duration_seconds": metadata["duration_seconds"],
                "artifact_name": candidate.name,
            }
        # Only the literal exclusive-create file from this failed attempt is removed.
        # A resource, identity or malformed-output failure never reaches a retry.
        candidate.unlink()
        with os.scandir(workspace) as entries:
            if next(entries, None) is not None:
                refuse("ytdlp_output_invalid")
    refuse("ytdlp_provider_rejected")


def _dispatch(request: WorkerRequest) -> dict[str, Any]:
    payload = request.payload
    limits = (
        MEDIA_DOWNLOAD_LIMITS
        if request.operation == DOWNLOAD_OPERATION
        else MEDIA_PROVIDER_METADATA_LIMITS
    )
    if (
        request.operation not in {METADATA_OPERATION, DOWNLOAD_OPERATION}
        or request.limit_profile_id != limits.profile_id
        or request.expected_generations
        or request.schema_generation != MEDIA_SCHEMA_VERSION
        or request.pipeline_generation != MEDIA_PIPELINE_VERSION
        or not isinstance(payload, Mapping)
        or set(payload) != {"video_id", "ytdlp", "workspace"}
    ):
        raise SupervisorError("invalid_worker_request")
    video_id = _video_id(payload["video_id"])
    workspace = _admit_workspace(payload["workspace"])
    override = payload["ytdlp"]
    if override is not None and (
        not isinstance(override, str) or not Path(override).is_absolute()
    ):
        refuse("ytdlp_dependency_unavailable")
    try:
        executable = Path(override) if override is not None else resolve_ytdlp()
    except YtDlpResolutionError as exc:
        raise LocalMediaError("ytdlp_dependency_unavailable") from exc
    if request.operation == DOWNLOAD_OPERATION:
        return _download(executable, workspace, video_id)
    return _metadata(
        _command(executable, video_id, None), workspace, video_id, download=False
    )


def _worker_main() -> int:
    request = read_worker_request(max_input_bytes=MEDIA_DOWNLOAD_LIMITS.max_input_bytes)
    stream = isolate_protocol_output()
    try:
        try:
            value = _dispatch(request)
            write_worker_response(
                request,
                payload=cast(JsonValue, value),
                observed_generations={},
                stream=stream,
                max_output_bytes=MEDIA_DOWNLOAD_LIMITS.max_output_bytes,
            )
        except (LocalMediaError, SupervisorError, OSError) as exc:
            reason = (
                exc.reason_code
                if isinstance(exc, SupervisorError)
                or (
                    isinstance(exc, LocalMediaError)
                    and exc.reason_code in _DOWNLOAD_FAILURES
                )
                else "ytdlp_worker_failed"
            )
            write_worker_response(
                request,
                error=SupervisorError(reason),
                observed_generations={},
                stream=stream,
                max_output_bytes=MEDIA_DOWNLOAD_LIMITS.max_output_bytes,
            )
    finally:
        stream.close()
    return 0


def _main() -> int:
    if sys.argv[1:] != [WORKER_FLAG]:
        print(
            "local_media_download.py is a library; use fetch-transcript.py",
            file=sys.stderr,
        )
        return 2
    try:
        return _worker_main()
    except SupervisorError as exc:
        print(f"YouTube media worker failed: {exc.reason_code}", file=sys.stderr)
        return 2
    # A nonzero child without an authenticated response is the supervisor's
    # closed crash signal. Emit only a fixed diagnostic; propagation would leak
    # provider URLs, paths and credentials. outer-boundary-process-contract.
    except Exception:  # noqa: BLE001
        print("YouTube media worker failed: unexpected_error", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())

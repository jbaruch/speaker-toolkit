"""Closed, path-neutral facts and resource policy for generic speech media.

This contract does not open an artifact or authenticate a caller-supplied receipt.
The local-media owner supplies facts from its authenticated worker, or explicitly
converts a VideoArtifactProbe already established in the same assessment.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
import re
import stat
from typing import Any, NoReturn

from artifact_metadata import ArtifactAvailability, WINDOWS_REPARSE_POINT_ATTRIBUTE
from artifact_supervisor import DiagnosticReceipt, FileGeneration, SupervisorLimits


MEDIA_SCHEMA_VERSION = 1
MEDIA_PIPELINE_VERSION = "1.0.0"
MEDIA_MAX_INPUT_BYTES = 8 * 1024**3
MEDIA_MAX_DURATION_SECONDS = 8 * 60 * 60
MEDIA_MAX_STREAMS = 64
MEDIA_FFPROBE_STDOUT_BYTES = 256 * 1024
MEDIA_FFPROBE_STDERR_BYTES = 64 * 1024
MEDIA_DIGEST_CHUNK_BYTES = 1024 * 1024
WHISPER_MAX_TEXT_BYTES = 2 * 1024 * 1024
WHISPER_MAX_SEGMENTS = 20000
WHISPER_MAX_SEGMENT_TEXT_BYTES = 16384
WHISPER_MAX_LANGUAGE_LENGTH = 32

MEDIA_METADATA_LIMITS = SupervisorLimits(
    profile_id="local-media-metadata-v1",
    wall_seconds=15,
    max_memory_bytes=256 * 1024**2,
    max_input_bytes=64 * 1024,
    max_output_bytes=64 * 1024,
    max_diagnostic_bytes=64 * 1024,
    max_processes=1,
)
MEDIA_PROBE_LIMITS = SupervisorLimits(
    profile_id="local-media-probe-v1",
    wall_seconds=300,
    max_memory_bytes=512 * 1024**2,
    max_input_bytes=64 * 1024,
    max_output_bytes=64 * 1024,
    max_diagnostic_bytes=64 * 1024,
    max_processes=2,
)
MEDIA_DOWNLOAD_LIMITS = SupervisorLimits(
    profile_id="local-media-download-v1",
    wall_seconds=600,
    max_memory_bytes=1024**3,
    max_input_bytes=64 * 1024,
    max_output_bytes=64 * 1024,
    max_diagnostic_bytes=64 * 1024,
    max_processes=4,
)
MEDIA_PROVIDER_METADATA_LIMITS = SupervisorLimits(
    profile_id="local-media-provider-metadata-v1",
    wall_seconds=120,
    max_memory_bytes=1024**3,
    max_input_bytes=64 * 1024,
    max_output_bytes=64 * 1024,
    max_diagnostic_bytes=64 * 1024,
    max_processes=4,
)
MEDIA_WHISPER_LIMITS = SupervisorLimits(
    profile_id="local-media-whisper-v1",
    wall_seconds=900,
    max_memory_bytes=16 * 1024**3,
    max_input_bytes=64 * 1024,
    max_output_bytes=8 * 1024**2,
    max_diagnostic_bytes=64 * 1024,
    max_processes=16,
)

CONTAINER_BY_SUFFIX = {
    ".mp3": "mp3",
    ".wav": "wav",
    ".m4a": "iso_bmff",
    ".mp4": "iso_bmff",
    ".mov": "iso_bmff",
    ".mkv": "matroska_webm",
    ".webm": "matroska_webm",
}
FORMAT_NAMES_BY_CONTAINER = {
    "mp3": frozenset({"mp3"}),
    "wav": frozenset({"wav"}),
    "iso_bmff": frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}),
    "matroska_webm": frozenset({"matroska", "webm"}),
}
COUNT_FIELDS = (
    "video_stream_count",
    "audio_stream_count",
    "attached_picture_count",
    "other_stream_count",
)
FACT_FIELDS = frozenset(
    {
        "duration_seconds",
        "duration_source",
        "container_family",
        "stream_count",
        *COUNT_FIELDS,
    }
)
PROBE_FIELDS = FACT_FIELDS | {
    "schema_version",
    "source_sha256",
    "source_size_bytes",
    "parser_diagnostics",
}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_LANGUAGE = re.compile(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*\Z")


class LocalMediaError(ValueError):
    """A typed acquisition refusal; raw paths and provider output stay private."""

    def __init__(self, reason_code: str) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason_code) is None:
            raise ValueError("invalid local-media failure code")
        self.reason_code = reason_code
        super().__init__(
            f"{reason_code}; inspect the source and rerun the bounded media owner"
        )


def refuse(reason: str) -> NoReturn:
    raise LocalMediaError(reason)


def positive_duration(value: Any) -> float | None:
    if type(value) not in {int, float} or not 0 < value <= MEDIA_MAX_DURATION_SECONDS:
        return None
    return float(value) if math.isfinite(value) else None


def validate_media_size(value: Any) -> int:
    if type(value) is not int or not 0 < value <= MEDIA_MAX_INPUT_BYTES:
        refuse("media_size_limit")
    return value


def validate_available_generation(generation: FileGeneration) -> None:
    try:
        FileGeneration.from_dict(generation.to_dict())
    except (TypeError, ValueError) as exc:
        raise LocalMediaError("media_probe_malformed_result") from exc
    if not stat.S_ISREG(generation.mode) or (
        (generation.file_attributes or 0) & WINDOWS_REPARSE_POINT_ATTRIBUTE
    ):
        refuse("media_artifact_unavailable")
    if ArtifactAvailability.from_generation(generation).state != "local":
        refuse("media_cloud_placeholder_unavailable")
    validate_media_size(generation.size)


def parse_media_facts(document: Any, expected_container: str) -> dict[str, Any]:
    """Validate bounded ffprobe JSON; audio is mandatory and video is optional."""
    if (
        not isinstance(document, Mapping)
        or set(document) - {"format", "streams", "programs", "stream_groups"}
        or document.get("programs", []) != []
        or document.get("stream_groups", []) != []
    ):
        refuse("media_parser_rejected")
    media_format, streams = document.get("format"), document.get("streams")
    if not isinstance(media_format, Mapping) or not isinstance(streams, list):
        refuse("media_invalid_container")
    format_names = media_format.get("format_name")
    allowed = FORMAT_NAMES_BY_CONTAINER.get(expected_container)
    if (
        not allowed
        or not isinstance(format_names, str)
        or not format_names
        or not set(format_names.split(",")) <= allowed
    ):
        refuse("media_invalid_container")
    if len(streams) > MEDIA_MAX_STREAMS:
        refuse("media_stream_limit")
    counts: dict[str, int] = dict.fromkeys(COUNT_FIELDS, 0)
    usable_audio = 0
    durations = []
    for stream in streams:
        if not isinstance(stream, Mapping) or not isinstance(
            stream.get("codec_type"), str
        ):
            refuse("media_parser_rejected")
        kind = stream["codec_type"]
        disposition = stream.get("disposition", {})
        if not isinstance(disposition, Mapping):
            refuse("media_parser_rejected")
        attached_flag = disposition.get("attached_pic", 0)
        if type(attached_flag) not in {int, str} or attached_flag not in (
            0,
            1,
            "0",
            "1",
        ):
            refuse("media_parser_rejected")
        attached = kind == "video" and attached_flag in (1, "1")
        if kind == "audio" and _usable_audio_stream(stream):
            usable_audio += 1
        if attached:
            counts["attached_picture_count"] += 1
        elif kind in {"video", "audio"}:
            counts[f"{kind}_stream_count"] += 1
        else:
            counts["other_stream_count"] += 1
        if kind == "audio" or (kind == "video" and not attached):
            duration = _probe_duration(stream.get("duration"))
            if duration is not None:
                durations.append(duration)
    if counts["audio_stream_count"] == 0:
        refuse("media_no_audio_stream")
    if usable_audio == 0:
        refuse("media_no_usable_audio_stream")
    duration = _probe_duration(media_format.get("duration"))
    source = "format"
    if duration is None:
        duration = max(durations) if durations else None
        source = "stream"
    if duration is None:
        refuse("media_duration_unavailable")
    if positive_duration(duration) is None:
        refuse("media_duration_limit")
    return {
        "duration_seconds": duration,
        "duration_source": source,
        "container_family": expected_container,
        "stream_count": len(streams),
        **counts,
    }


def _usable_audio_stream(stream: Mapping[str, Any]) -> bool:
    codec = stream.get("codec_name")
    channels = stream.get("channels")
    sample_rate = stream.get("sample_rate")
    return (
        isinstance(codec, str)
        and re.fullmatch(r"[a-z0-9_]{1,64}", codec) is not None
        and codec not in {"unknown", "none"}
        and type(channels) is int
        and channels > 0
        and isinstance(sample_rate, str)
        and len(sample_rate) <= 10
        and sample_rate.isascii()
        and sample_rate.isdecimal()
        and int(sample_rate) > 0
    )


def _probe_duration(value: Any) -> float | None:
    if value is None or value == "N/A":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        refuse("media_parser_rejected")
    try:
        result = float(value)
    except OverflowError as exc:
        raise LocalMediaError("media_duration_limit") from exc
    except ValueError as exc:
        raise LocalMediaError("media_parser_rejected") from exc
    if not math.isfinite(result) or result <= 0:
        refuse("media_parser_rejected")
    if result > MEDIA_MAX_DURATION_SECONDS:
        refuse("media_duration_limit")
    return result


@dataclass(frozen=True)
class MediaArtifactProbe:
    generation: FileGeneration
    root_generation: FileGeneration | None
    source_sha256: str
    source_size_bytes: int
    duration_seconds: float
    duration_source: str
    container_family: str
    stream_count: int
    video_stream_count: int
    audio_stream_count: int
    attached_picture_count: int
    other_stream_count: int
    parser_diagnostics: DiagnosticReceipt


def decode_media_probe(
    payload: Any, generation: FileGeneration, root_generation: FileGeneration | None
) -> MediaArtifactProbe:
    if not isinstance(payload, Mapping) or set(payload) != PROBE_FIELDS:
        refuse("media_probe_malformed_result")
    if (
        type(payload["schema_version"]) is not int
        or payload["schema_version"] != MEDIA_SCHEMA_VERSION
    ):
        refuse("media_probe_malformed_result")
    validate_available_generation(generation)
    size = validate_media_size(payload["source_size_bytes"])
    digest = payload["source_sha256"]
    if (
        size != generation.size
        or not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
    ):
        refuse("media_probe_malformed_result")
    if (
        positive_duration(payload["duration_seconds"]) is None
        or payload["duration_source"] not in ("format", "stream")
        or not isinstance(payload["container_family"], str)
        or payload["container_family"] not in FORMAT_NAMES_BY_CONTAINER
    ):
        refuse("media_probe_malformed_result")
    for name in ("stream_count", *COUNT_FIELDS):
        if (
            type(payload[name]) is not int
            or not 0 <= payload[name] <= MEDIA_MAX_STREAMS
        ):
            refuse("media_probe_malformed_result")
    if (
        payload["audio_stream_count"] == 0
        or sum(payload[name] for name in COUNT_FIELDS) != payload["stream_count"]
    ):
        refuse("media_probe_malformed_result")
    diagnostic = payload["parser_diagnostics"]
    if (
        not isinstance(diagnostic, Mapping)
        or set(diagnostic) != {"byte_count", "sha256", "truncated"}
        or type(diagnostic["byte_count"]) is not int
        or diagnostic["byte_count"] != 0
        or diagnostic["sha256"] != DiagnosticReceipt.empty().sha256
        or diagnostic["truncated"] is not False
    ):
        refuse("media_probe_malformed_result")
    return MediaArtifactProbe(
        generation=generation,
        root_generation=root_generation,
        source_sha256=digest,
        source_size_bytes=size,
        duration_seconds=float(payload["duration_seconds"]),
        duration_source=payload["duration_source"],
        container_family=payload["container_family"],
        stream_count=payload["stream_count"],
        **{name: payload[name] for name in COUNT_FIELDS},
        parser_diagnostics=DiagnosticReceipt.empty(),
    )


def reuse_video_probe(probe: Any) -> MediaArtifactProbe:
    """Convert established video facts without probing, copying, hashing, or statting."""
    from video_evidence import VideoArtifactProbe

    if not isinstance(probe, VideoArtifactProbe):
        refuse("media_probe_malformed_result")
    if probe.audio_stream_count == 0:
        refuse("media_no_audio_stream")
    return decode_media_probe(
        {
            "schema_version": MEDIA_SCHEMA_VERSION,
            "source_sha256": probe.source_sha256,
            "source_size_bytes": probe.source_size_bytes,
            **{name: getattr(probe, name) for name in sorted(FACT_FIELDS)},
            "parser_diagnostics": probe.parser_diagnostics.to_dict(),
        },
        probe.generation,
        probe.root_generation,
    )


def bounded_whisper_result(value: Any) -> dict[str, Any]:
    """Strip provider-only payloads before a worker returns bounded speech data.

    Missing timing remains optional. A present unbounded/malformed container is
    a resource/result failure, not an invitation to enumerate a provider iterator.
    Segment timing semantics remain with the transcript-timing owner.
    """
    if not isinstance(value, Mapping):
        refuse("whisper_result_invalid")
    text = value.get("text")
    if not isinstance(text, str) or not text.strip():
        refuse("whisper_result_invalid")
    _bounded_text(text, WHISPER_MAX_TEXT_BYTES, "whisper_text_limit")
    language = value.get("language")
    if language is not None and (
        not isinstance(language, str)
        or len(language) > WHISPER_MAX_LANGUAGE_LENGTH
        or _LANGUAGE.fullmatch(language) is None
    ):
        refuse("whisper_language_invalid")
    raw_segments = value.get("segments")
    segments = None
    if raw_segments is not None:
        if not isinstance(raw_segments, list):
            refuse("whisper_segments_invalid")
        if len(raw_segments) > WHISPER_MAX_SEGMENTS:
            refuse("whisper_segment_limit")
        segments = []
        timing_valid = True
        total_segment_bytes = 0
        for segment in raw_segments:
            if not isinstance(segment, Mapping):
                refuse("whisper_segments_invalid")
            segment_text = segment.get("text")
            if not isinstance(segment_text, str):
                refuse("whisper_segments_invalid")
            _bounded_text(
                segment_text,
                WHISPER_MAX_SEGMENT_TEXT_BYTES,
                "whisper_segment_text_limit",
            )
            total_segment_bytes += len(segment_text.encode("utf-8"))
            if total_segment_bytes > WHISPER_MAX_TEXT_BYTES:
                refuse("whisper_segment_text_limit")
            start, end = segment.get("start"), segment.get("end")
            if not all(_segment_offset(number) for number in (start, end)):
                # Bounded semantic timing failure: keep speech, omit timing.
                timing_valid = False
            else:
                segments.append({"start": start, "end": end, "text": segment_text})
        if not timing_valid:
            segments = None
    return {"text": text, "language": language, "segments": segments}


def _segment_offset(value: Any) -> bool:
    return type(value) in {int, float} and 0 <= value <= MEDIA_MAX_DURATION_SECONDS


def _bounded_text(value: str, maximum: int, reason: str) -> None:
    if len(value) > maximum:
        refuse(reason)
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise LocalMediaError("whisper_result_invalid") from exc
    if len(encoded) > maximum:
        refuse(reason)

"""Bounded audio clipping inside the authenticated ingress transcription worker.

The caller holds the admitted original descriptor and verifies its generation
around this operation. The parent owns the private workspace and its cleanup,
including timeout/kill paths. Only a decoded interval is materialized here;
source media is never changed. PCM byte count establishes actual clip duration.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import stat
from typing import Any
import wave

from artifact_supervisor import FileGeneration
from local_media_contract import LocalMediaError, refuse
from local_media_evidence import _inspect, _require_descriptor
from local_media_process import run_media_tool
from local_media_words import WORDS_MAX_SAMPLE_SECONDS, WORDS_MAX_SOURCE_SECONDS


SAMPLE_RATE = 16000
PCM_BYTES_PER_SECOND = SAMPLE_RATE * 2
SAMPLE_DIAGNOSTIC_BYTES = 64 * 1024
CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class SpeechClip:
    path: Path
    generation: FileGeneration
    sha256: str
    duration_seconds: float


def validate_sample_window(start: Any, duration: Any, source_duration: Any) -> None:
    if (
        type(source_duration) not in (int, float)
        or not 0 < source_duration <= WORDS_MAX_SOURCE_SECONDS
        or type(start) not in (int, float)
        or not 0 <= start < source_duration
        or type(duration) not in (int, float)
        or not 0 < duration <= WORDS_MAX_SAMPLE_SECONDS
        or start + duration > source_duration
    ):
        refuse("whisper_sample_window_invalid")


def extract_speech_clip(
    path: Path, workspace: Path, *, start: float, duration: float
) -> SpeechClip:
    """Worker-only: decode one bounded interval to private 16-kHz mono PCM/WAV."""
    validate_sample_window(start, duration, WORDS_MAX_SOURCE_SECONDS)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        refuse("media_dependency_unavailable")
    pcm, wav = workspace / "sample.pcm", workspace / "sample.wav"
    result = run_media_tool(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-xerror",
            "-ss",
            str(start),
            "-i",
            str(path),
            "-t",
            str(duration),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            "-f",
            "s16le",
            "pipe:1",
        ],
        stdout_limit=int(duration * PCM_BYTES_PER_SECOND) + 2,
        stderr_limit=SAMPLE_DIAGNOSTIC_BYTES,
        output=pcm,
        cwd=workspace,
    )
    if result.returncode or result.diagnostics.byte_count:
        refuse("whisper_sample_decode_failed")
    size = result.streamed_bytes
    actual_duration = size / PCM_BYTES_PER_SECOND
    if size <= 0 or size % 2 or abs(actual_duration - duration) > 1 / SAMPLE_RATE:
        refuse("whisper_sample_duration_mismatch")
    try:
        os.chmod(pcm, 0o600)
        with pcm.open("rb") as source, wav.open("xb") as output:
            os.chmod(wav, 0o600)
            with wave.open(output, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(SAMPLE_RATE)
                audio.setnframes(size // 2)
                while chunk := source.read(CHUNK_BYTES):
                    audio.writeframesraw(chunk)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(wav, stat.S_IREAD)
        generation = _inspect(wav, None).generation
        digest = hashlib.sha256()
        with wav.open("rb") as source:
            _require_descriptor(source.fileno(), generation)
            while chunk := source.read(CHUNK_BYTES):
                digest.update(chunk)
            _require_descriptor(source.fileno(), generation)
        if _inspect(wav, None).generation != generation:
            refuse("media_generation_changed")
    except (OSError, wave.Error) as exc:
        raise LocalMediaError("whisper_sample_decode_failed") from exc
    return SpeechClip(wav, generation, digest.hexdigest(), actual_duration)

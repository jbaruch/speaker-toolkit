#!/usr/bin/env python3
"""Fetch a talk transcript, validate it, and write it only if it is real.

This exists because the previous transcript fetch was an inline `python3 -c`
heredoc. When `youtube-transcript-api` 1.0 removed the `YouTubeTranscriptApi.
get_transcript` classmethod, every call raised, and the heredoc's traceback was
written to the transcript path. Its error handler then raised too (`NameError:
name 'sys' is not defined`), so the failure path failed as well.

Four vault "transcripts" are that traceback. Two more are zero bytes. Nothing
validated the output, so a talk with a stack trace for a transcript was
indistinguishable from a talk with a transcript, and one talk was marked
`processed` off an empty file.

The fix is not a better heredoc. Per `rules/script-delegation.md` Scripts Are
Real Files, a deterministic operation gets a real file with an exit code, a
stderr channel, and tests. The validation below is the part that matters, and it
is pure so CI can test every failure mode without a network.

Sources, in order:
  1. YouTube caption track (fast, no audio download)
  2. Local Whisper transcription of the downloaded audio (fallback, and the only
     option when a video has no caption track)

Usage:
    fetch-transcript.py <video-id-or-url> --out <path> [--languages en,ru,he]
                        [--method auto|captions|whisper] [--force]
                        [--existing-source youtube_auto|whisper|manual|unknown]
                        [--duration-seconds N] [--min-words N]
    fetch-transcript.py <label> --audio <file> --out <path>   # non-YouTube talk

`--audio` transcribes a local audio or video file instead of downloading one, so
InfoQ / Vimeo / conference-platform talks route through this script rather than
through hand-rolled `mlx_whisper.transcribe()` calls in skill prose. The
positional argument is then just a label for the JSON output.

Output: one JSON object on stdout, on EVERY exit path including argument errors —
    {"ok": bool, "video_id": "...", "method": "captions|whisper|existing|none",
     "words": int, "path": "...", "timed_path": "..."|null,
     "quality_path": "..."|null,
     "reason": "...", "language": "en"|null}

`language` is the caption track's own language code, or Whisper's detected
language — the source of the talk's `delivery_language`. It is null on the
`existing` path, because a file already on disk carries no language signal.
Exit:   0 wrote a valid transcript, or kept a valid existing transcript
        1 could not obtain a valid transcript — nothing was written
        2 argument or tool-state error

An existing transcript is never replaced without ``--force``. Transcript,
timing, and quality artifacts are staged together and restored byte-for-byte
after a caught replacement failure. Timing and acquisition provenance live in
schema-v2 ``<stem>.segments.json``; malformed optional segments are discarded
rather than poisoning valid semantic text. The exact applied quality policy and
its source-owned provenance live independently in ``<stem>.quality.json``. Both
receipts hash exact transcript bytes, so replacement invalidates both.
``--min-words`` can tighten the trusted floor but cannot lower it.
``--duration-seconds`` is only an expected value: it must match a YouTube
provider probe or ``ffprobe`` of the exact local media before it can authorize a
short-talk threshold.
"""

import argparse
import hashlib
import importlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, TypeVar

from transcript_timing import (
    ensure_bundle_destinations_are_not_symlinks,
    local_media_timing_provenance,
    load_verified_quality_receipt,
    load_verified_segments,
    normalize_segments,
    quality_sidecar_path,
    sidecar_path,
    timing_enrichment_equivalent,
    validate_timing_receipt,
    write_atomically,
    write_quality_receipt,
    write_timing_receipt,
    write_transcript_bundle,
    youtube_timing_provenance,
    timing_extent_is_foreign,
    timing_extent_overrun_ratio,
)
from transcript_quality import (
    DEFAULT_MIN_WORDS,
    VTT_TIMING_TAG,
    build_quality_policy,
    count_words,
    normalize_duration,
    receipt_claims_source_duration,
    receipt_duration_cannot_hold,
    receipt_matches_media_digest,
    validate_transcript,
)

__all__ = ["VTT_TIMING_TAG", "write_atomically"]


# YouTube serves media per player client, and it blocks them unevenly: a client
# that 403s today may work tomorrow and the reverse. Trying one client and
# giving up turns a transient block into "this talk has no transcript", which
# is how the Whisper fallback went silently dead while mlx-whisper sat
# installed and working. `None` runs yt-dlp's own default chain first, so a
# healthy environment pays nothing; the named clients are only reached after it
# fails. Order is cheapest-first, not preference — every entry produces the
# same audio when it works.
YOUTUBE_PLAYER_CLIENTS: tuple[str | None, ...] = (
    None,
    "mweb",
    "web_safari",
    "ios",
    "tv",
)


VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_LaneResult = TypeVar("_LaneResult")
CAPTION_LANE_ERRORS = (
    ImportError,
    OSError,
    RuntimeError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)
WHISPER_LANE_ERRORS = (
    ImportError,
    OSError,
    RuntimeError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)
TIMING_PAYLOAD_ERRORS = (
    RuntimeError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


@dataclass(frozen=True)
class MediaSnapshot:
    """One private local-media snapshot used by every acquisition step."""

    source_path: Path
    source_descriptor: int
    source_identity: tuple[int, int, int, int, int]
    path: Path
    sha256: str
    identity: tuple[int, int, int, int, int]

    def assert_unchanged(self, *, verify_source_digest: bool = False) -> None:
        """Fail before a write when the source binding or snapshot drifted."""
        try:
            source_entry = self.source_path.lstat()
            source_descriptor_state = os.fstat(self.source_descriptor)
            current = self.path.lstat()
        except OSError as exc:
            raise ValueError(
                f"local-media source or snapshot became unavailable: {exc}; "
                "no transcript bundle was written"
            ) from exc
        if (
            not stat.S_ISREG(source_entry.st_mode)
            or _stat_identity(source_entry) != self.source_identity
            or _stat_identity(source_descriptor_state) != self.source_identity
        ):
            raise ValueError(
                "local-media source changed or was replaced during acquisition; "
                "no transcript bundle was written"
            )
        if verify_source_digest:
            os.lseek(self.source_descriptor, 0, os.SEEK_SET)
            source_digest = hashlib.sha256()
            while chunk := os.read(self.source_descriptor, 1024 * 1024):
                source_digest.update(chunk)
            source_after_hash = os.fstat(self.source_descriptor)
            if (
                _stat_identity(source_after_hash) != self.source_identity
                or source_digest.hexdigest() != self.sha256
            ):
                raise ValueError(
                    "local-media source changed during acquisition; no transcript "
                    "bundle was written"
                )
        if (
            not stat.S_ISREG(current.st_mode)
            or _stat_identity(current) != self.identity
            or media_sha256(self.path) != self.sha256
        ):
            raise ValueError(
                "local-media snapshot changed during probe or transcription; "
                "no transcript bundle was written"
            )


@contextmanager
def immutable_media_snapshot(source: Path) -> Iterator[MediaSnapshot]:
    """Copy a stable regular source twice-verified through one open descriptor."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise ValueError(
            f"cannot open --audio media as a non-symlink regular file: {exc}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("--audio media must be a regular file")
        with tempfile.TemporaryDirectory(prefix="speaker-toolkit-media-") as work_dir:
            snapshot_path = Path(work_dir) / source.name
            first_digest = hashlib.sha256()
            with snapshot_path.open("xb") as snapshot_stream:
                while chunk := os.read(descriptor, 1024 * 1024):
                    first_digest.update(chunk)
                    snapshot_stream.write(chunk)
                snapshot_stream.flush()
                os.fsync(snapshot_stream.fileno())
            after_copy = os.fstat(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            second_digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1024 * 1024):
                second_digest.update(chunk)
            after_verify = os.fstat(descriptor)
            if (
                _stat_identity(before) != _stat_identity(after_copy)
                or _stat_identity(before) != _stat_identity(after_verify)
                or first_digest.digest() != second_digest.digest()
            ):
                raise ValueError(
                    "--audio media changed while its immutable snapshot was being "
                    "created; no transcript bundle was written"
                )
            snapshot_path.chmod(stat.S_IRUSR)
            snapshot_stat = snapshot_path.lstat()
            snapshot = MediaSnapshot(
                source_path=source,
                source_descriptor=descriptor,
                source_identity=_stat_identity(after_verify),
                path=snapshot_path,
                sha256=first_digest.hexdigest(),
                identity=_stat_identity(snapshot_stat),
            )
            snapshot.assert_unchanged()
            yield snapshot
    finally:
        os.close(descriptor)


def _call_with_provider_stdout_isolated(
    call: Callable[[], _LaneResult],
) -> _LaneResult:
    """Route optional-provider chatter away from the CLI JSON channel."""
    saved_stdout = os.dup(1)
    try:
        sys.stdout.flush()
        os.dup2(2, 1)
        with redirect_stdout(sys.stderr):
            return call()
    finally:
        sys.stderr.flush()
        os.dup2(saved_stdout, 1)
        os.close(saved_stdout)


def run_optional_lane(
    label: str,
    call: Callable[[], _LaneResult],
    *,
    expected_errors: tuple[type[Exception], ...],
) -> tuple[_LaneResult | None, str]:
    """Downgrade enumerated provider failures to an unavailable lane."""
    try:
        return _call_with_provider_stdout_isolated(call), ""
    except expected_errors as failure:
        reason = (
            f"{label} failed safely ({type(failure).__name__}: {failure}); "
            "trying the next source"
        )
        print(reason, file=sys.stderr)
        return None, reason


def resolve_video_id(value):
    """Accept a bare 11-character id or any YouTube URL carrying one."""
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    match = VIDEO_ID.search(value)
    return match.group(1) if match else None


def media_sha256(path: Path) -> str:
    """Hash the exact local media bytes that owned a duration probe."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _positive_duration(value: object) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        return None
    return normalize_duration(value)


def probe_youtube_duration(video_id: str) -> tuple[float | None, str]:
    """Read source-owned duration for one exact YouTube identity via yt-dlp."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        completed = subprocess.run(
            [
                "yt-dlp",
                "--dump-single-json",
                "--skip-download",
                "--no-playlist",
                url,
            ],
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as exc:
        return None, (
            f"cannot probe trusted YouTube duration ({exc}) — install yt-dlp "
            "with `brew install yt-dlp` or `pip install yt-dlp`"
        )
    if completed.returncode != 0:
        detail = completed.stderr.strip()[:400] or "provider metadata unavailable"
        return None, f"yt-dlp could not probe duration for {video_id}: {detail}"
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, f"yt-dlp returned invalid duration metadata for {video_id}: {exc}"
    if not isinstance(payload, dict) or payload.get("id") != video_id:
        returned_id = payload.get("id") if isinstance(payload, dict) else None
        return None, (
            "yt-dlp duration metadata identity mismatch: requested "
            f"{video_id}, received {returned_id!r}"
        )
    duration = _positive_duration(payload.get("duration"))
    if duration is None:
        return None, (
            f"yt-dlp metadata for {video_id} has no positive finite duration; "
            "cannot authorize a short-talk threshold"
        )
    return duration, f"trusted yt-dlp duration for YouTube video {video_id}"


def probe_local_media_duration(path: Path) -> tuple[float | None, str]:
    """Read duration from the exact local media bytes via ffprobe."""
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError) as exc:
        return None, (
            f"cannot probe trusted local-media duration ({exc}) — install "
            "ffprobe with `brew install ffmpeg`"
        )
    if completed.returncode != 0:
        detail = completed.stderr.strip()[:400] or "media duration unavailable"
        return None, f"ffprobe could not read duration from {path}: {detail}"
    try:
        raw_duration = float(completed.stdout.strip())
    except ValueError:
        return None, f"ffprobe returned an invalid duration for {path}"
    duration = _positive_duration(raw_duration)
    if duration is None:
        return None, f"ffprobe returned no positive finite duration for {path}"
    return duration, f"trusted ffprobe duration for local media {path}"


def duration_matches_expected(expected: int, trusted: float) -> bool:
    """Match an integer CLI expectation to a source probe's subsecond value."""
    return abs(float(expected) - trusted) <= 1.0


def fixed_quality_provenance() -> dict[str, object]:
    """Return provenance for the non-relaxable fixed quality floor."""
    return {"kind": "fixed_default"}


def youtube_quality_provenance(
    video_id: str, duration_seconds: float
) -> dict[str, object]:
    """Bind a duration policy to one exact provider identity."""
    return {
        "kind": "youtube_duration",
        "video_id": video_id,
        "duration_seconds": normalize_duration(duration_seconds),
    }


def local_media_quality_provenance(
    media_digest: str, duration_seconds: float
) -> dict[str, object]:
    """Bind a duration policy to one exact local media digest."""
    if _SHA256.fullmatch(media_digest) is None:
        raise ValueError("local-media quality provenance requires a SHA-256 digest")
    return {
        "kind": "local_media_duration",
        "media_sha256": media_digest,
        "duration_seconds": normalize_duration(duration_seconds),
    }


def segments_to_text(segments: Iterable[object]) -> str:
    """Flatten caption segments to text.

    Handles both shapes the library has used: dicts with a "text" key (<=0.6)
    and objects with a .text attribute (>=1.0). Pinning to one shape is what
    broke the previous fetch.
    """
    lines = []
    for segment in segments:
        text = (
            segment.get("text")
            if isinstance(segment, dict)
            else getattr(segment, "text", None)
        )
        if text:
            lines.append(text)
    return "\n".join(lines)


def fetch_captions(
    video_id: str, languages: list[str]
) -> tuple[str | None, str | None, Iterable[object] | None]:
    """Call the caption API; the caller owns enumerated lane isolation."""
    return _fetch_captions_from_api(video_id, languages)


def _fetch_captions_from_api(
    video_id: str, languages: list[str]
) -> tuple[str | None, str | None, Iterable[object] | None]:
    """Return ``(text, language, timed segments)`` or three ``None`` values.

    The 1.0 API is instance-based (`YouTubeTranscriptApi().fetch`); the older one
    was a classmethod (`.get_transcript`). Both are tried so the script survives
    the next rename instead of writing a traceback into the corpus.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api import YouTubeTranscriptApiException
    except (ImportError, AttributeError, OSError, RuntimeError) as exc:
        print(
            "youtube-transcript-api caption lane is unavailable "
            f"({type(exc).__name__}: {exc}) — `pip install "
            "youtube-transcript-api`, or pass --method whisper",
            file=sys.stderr,
        )
        return None, None, None

    try:
        api = YouTubeTranscriptApi()
        fetcher: Any = getattr(api, "fetch", None)
        legacy_fetcher: Any = getattr(YouTubeTranscriptApi, "get_transcript", None)
        if callable(fetcher):
            segments = fetcher(video_id, languages=languages)
        elif callable(legacy_fetcher):
            segments = legacy_fetcher(video_id, languages=languages)
        else:
            print(
                "youtube-transcript-api exposes neither .fetch nor .get_transcript; "
                "the API changed again — update fetch_captions()",
                file=sys.stderr,
            )
            return None, None, None
    except YouTubeTranscriptApiException as exc:
        # Every "this video has no usable caption track" case — subtitles
        # disabled, no track in the requested languages, age restriction, IP
        # block. All are normal and all must fall through to Whisper rather than
        # propagating: an uncaught library exception here is precisely how the
        # previous fetch ended up writing its own traceback into the corpus.
        print(
            f"caption track unavailable for {video_id}: "
            f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
            file=sys.stderr,
        )
        return None, None, None
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(
            "youtube-transcript-api caption lane failed safely for "
            f"{video_id} ({type(exc).__name__}: {exc}); trying the next source",
            file=sys.stderr,
        )
        return None, None, None
    # The track's own language, not the first preference we asked for — they
    # differ whenever the requested language is unavailable and the API falls
    # back. `delivery_language` is derived from this, so guessing is not an option.
    if not isinstance(segments, Iterable) or isinstance(segments, (str, bytes)):
        print(
            "youtube-transcript-api returned a non-iterable transcript; "
            "the API changed again — update fetch_captions()",
            file=sys.stderr,
        )
        return None, None, None
    # The track's own language, read before materializing — `list()` keeps the
    # segments and drops the object's attributes.
    raw_language = getattr(segments, "language_code", None)
    language = raw_language if isinstance(raw_language, str) else None
    # Materialize here, inside the lane the caller wrapped in its expected-error
    # boundary. A lazy track that raises mid-consumption must read as a caption
    # lane failure and fall through to Whisper; consumed outside this function
    # the same exception reaches the process boundary and ends the run. Doing it
    # once also means the text and the returned segments are the same data —
    # `segments_to_text` would otherwise exhaust a one-shot track and hand the
    # caller an empty one.
    materialized = list(segments)
    return segments_to_text(materialized), language, materialized


def enrich_existing_caption_timing(
    transcript_path: Path,
    existing: str,
    video_id: str,
    languages: list[str],
    *,
    existing_source: str,
    duration_seconds: int | float | None = None,
) -> tuple[Path | None, str]:
    """Add caption timing only after exact text/provenance authorization.

    The transcript file is never rewritten. Only a talk already owned as
    ``youtube_auto`` may acquire caption provenance, and fetched caption text
    must equal the existing text modulo whitespace runs. Manual, Whisper,
    edited, or unknown-provenance text remains untouched and timing-unavailable.
    """
    if existing_source != "youtube_auto":
        return None, (
            "timing unavailable: existing transcript provenance is "
            f"{existing_source!r}, not 'youtube_auto'"
        )
    if duration_seconds is None:
        return None, (
            "timing unavailable: trusted YouTube duration could not be verified"
        )
    caption_result, lane_reason = run_optional_lane(
        "youtube-transcript-api caption lane",
        lambda: fetch_captions(video_id, languages),
        expected_errors=CAPTION_LANE_ERRORS,
    )
    if caption_result is None:
        return None, f"timing unavailable: {lane_reason}"
    fetched, _language, segments = caption_result
    if fetched is None or not normalize_segments(segments):
        return None, "timing unavailable: caption segments could not be fetched"
    if not timing_enrichment_equivalent(existing, fetched):
        return None, (
            "timing unavailable: fetched captions differ from the existing "
            "transcript beyond whitespace layout"
        )
    timing_path = write_timing_receipt(
        transcript_path,
        existing,
        segments,
        source="captions",
        provenance=youtube_timing_provenance("captions", video_id, duration_seconds),
    )
    return timing_path, (
        "caption timing enriched after exact text equivalence modulo whitespace"
    )


def transcribe_audio(
    audio_path: Path, video_id: str, model: str
) -> tuple[str | None, str | None, Iterable[object] | None]:
    """Call local Whisper; the caller owns enumerated lane isolation."""
    return _transcribe_audio_with_mlx(audio_path, video_id, model)


def _transcribe_audio_with_mlx(
    audio_path: Path, video_id: str, model: str
) -> tuple[str | None, str | None, Iterable[object] | None]:
    """Return ``(text, language, timed segments)`` from local Whisper."""
    try:
        mlx_whisper = importlib.import_module("mlx_whisper")
    except (ImportError, AttributeError, OSError, RuntimeError) as exc:
        print(
            "mlx-whisper lane is unavailable "
            f"({type(exc).__name__}: {exc}) (Apple Silicon only) — "
            "`pip install 'speaker-toolkit[whisper]'`, or supply the transcript "
            "by hand. On other platforms use a caption track or an external "
            "transcription service.",
            file=sys.stderr,
        )
        return None, None, None

    try:
        result = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=model)
    except (AttributeError, OSError, TypeError, ValueError, RuntimeError) as exc:
        # Model download failure, unreadable audio, or an unsupported runtime.
        # Must not escape as a traceback — callers parse this script's stdout.
        print(
            f"mlx_whisper could not transcribe {video_id}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None, None, None
    text = result.get("text") if isinstance(result, dict) else None
    if not isinstance(text, str) or not text.strip():
        print(f"mlx_whisper returned no text for {video_id}", file=sys.stderr)
        return None, None, None
    # Whisper detects the spoken language; this is the only language signal on
    # the audio path, and `delivery_language` is derived from it.
    raw_language = result.get("language") if isinstance(result, dict) else None
    language = raw_language if isinstance(raw_language, str) else None
    segments = result.get("segments") if isinstance(result, dict) else None
    return text, language, segments if isinstance(segments, Iterable) else None


def fetch_whisper(
    video_id: str, work_dir: str, model: str
) -> tuple[str | None, str | None, Iterable[object] | None]:
    """Download audio and return Whisper text, language, and timed segments."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    audio: Path | None = None
    failures: list[str] = []
    # Each attempt downloads into its own directory. Sharing one path let a
    # refused attempt leave a partial file behind, and the next attempt's
    # "did the audio appear" check would accept those bytes as its own success
    # — the retry chain would stop early and transcribe whatever the failure
    # left. Isolation makes the check answer only for the attempt that ran.
    for index, client in enumerate(YOUTUBE_PLAYER_CLIENTS):
        attempt_dir = Path(work_dir) / f"download-{index}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        command = [
            "yt-dlp",
            "-x",
            "--audio-format",
            "mp3",
            "--no-playlist",
            "-o",
            str(attempt_dir / "audio.%(ext)s"),
        ]
        if client is not None:
            command += ["--extractor-args", f"youtube:player_client={client}"]
        command.append(url)
        try:
            download = subprocess.run(command, capture_output=True, text=True)
        except (FileNotFoundError, OSError) as exc:
            # A missing yt-dlp must not escape as a traceback: this script's
            # callers parse its stdout JSON, and a script that dies without
            # emitting it is the same silent-failure shape the whole file
            # exists to prevent.
            print(
                f"cannot run yt-dlp ({exc}) — install it with "
                "`brew install yt-dlp` or `pip install yt-dlp`",
                file=sys.stderr,
            )
            return None, None, None
        candidate = attempt_dir / "audio.mp3"
        # A zero-byte artifact is a failed extraction wearing a filename.
        if (
            download.returncode == 0
            and candidate.exists()
            and candidate.stat().st_size > 0
        ):
            audio = candidate
            break
        failures.append(f"{client or 'default'}: {download.stderr.strip()[:200]}")
    else:
        print(
            f"yt-dlp could not download audio for {video_id} under any player "
            f"client — {'; '.join(failures)}",
            file=sys.stderr,
        )
        return None, None, None

    return transcribe_audio(audio, video_id, model)


def prepare_optional_timing(
    text: str,
    segments: Iterable[object] | None,
    *,
    source: str,
    provenance: dict[str, object] | None,
) -> tuple[list[object] | None, dict[str, object] | None, str]:
    """Keep valid transcript text when optional provider timing is unusable."""
    if provenance is None:
        return (
            None,
            None,
            ("timing unavailable: trusted source duration/provenance is missing"),
        )
    raw_segments = list(segments or [])
    valid, reason = validate_timing_receipt(
        text,
        raw_segments,
        source=source,
        provenance=provenance,
    )
    if not valid:
        return None, None, f"timing unavailable: {reason}"
    return raw_segments, provenance, reason


def prepare_optional_timing_safely(
    text: str,
    segments: Iterable[object] | None,
    *,
    source: str,
    provenance: dict[str, object] | None,
) -> tuple[list[object] | None, dict[str, object] | None, str]:
    """Downgrade an enumerated provider-segment failure to no timing."""
    prepared, lane_reason = run_optional_lane(
        "optional provider timing payload",
        lambda: prepare_optional_timing(
            text,
            segments,
            source=source,
            provenance=provenance,
        ),
        expected_errors=TIMING_PAYLOAD_ERRORS,
    )
    if prepared is None:
        return None, None, f"timing unavailable: {lane_reason}"
    return prepared


def emit(
    ok,
    video_id,
    method,
    words,
    path,
    reason,
    code,
    language=None,
    timed_path=None,
    quality_path=None,
) -> NoReturn:
    """Print the contract object and exit. Never returns — hence `NoReturn`.

    The annotation is load-bearing, not decoration: callers rely on `emit` ending
    the process, and without it a type checker reads the code after an `emit` as
    reachable and every value guarded by one as possibly unbound.
    """
    print(
        json.dumps(
            {
                "ok": ok,
                "video_id": video_id,
                "method": method,
                "words": words,
                "path": str(path),
                "reason": reason,
                "language": language,
                "timed_path": str(timed_path) if timed_path else None,
                "quality_path": (str(quality_path) if quality_path else None),
            }
        )
    )
    sys.exit(code)


def _handle_local_audio(
    args: argparse.Namespace,
    requested_min_words: int | None,
) -> NoReturn:
    """Process ``--audio`` through one private, byte-stable media snapshot."""
    audio_path = Path(args.audio)
    if not audio_path.is_file():
        emit(
            False,
            args.video,
            "none",
            0,
            args.out,
            f"--audio file does not exist or is not a file: {audio_path}",
            2,
        )
    out = Path(args.out)
    ensure_bundle_destinations_are_not_symlinks(out)

    with immutable_media_snapshot(audio_path) as media:
        trusted_duration, duration_reason = probe_local_media_duration(media.path)
        media.assert_unchanged()
        if args.duration_seconds is not None:
            if trusted_duration is None:
                emit(
                    False,
                    args.video,
                    "none",
                    0,
                    out,
                    f"cannot verify --duration-seconds: {duration_reason}",
                    2,
                )
            if not duration_matches_expected(
                args.duration_seconds,
                trusted_duration,
            ):
                emit(
                    False,
                    args.video,
                    "none",
                    0,
                    out,
                    "--duration-seconds does not match ffprobe for the immutable "
                    f"local-media snapshot (expected {args.duration_seconds}, "
                    f"source reports {trusted_duration})",
                    2,
                )
        if trusted_duration is None:
            print(
                f"{duration_reason}; applying the fixed "
                f"{DEFAULT_MIN_WORDS}-word quality floor",
                file=sys.stderr,
            )
            quality_provenance = fixed_quality_provenance()
        else:
            quality_provenance = local_media_quality_provenance(
                media.sha256,
                trusted_duration,
            )
        quality_policy = build_quality_policy(
            requested_min_words,
            trusted_duration_seconds=trusted_duration,
        )
        timing_provenance = (
            local_media_timing_provenance(media.sha256, trusted_duration)
            if trusted_duration is not None
            else None
        )

        if out.exists() and not args.force:
            try:
                existing = out.read_bytes().decode("utf-8")
            except UnicodeDecodeError as exc:
                emit(
                    False,
                    args.video,
                    "none",
                    0,
                    out,
                    f"existing transcript is not valid UTF-8: {exc}",
                    2,
                )
            except OSError as exc:
                emit(
                    False,
                    args.video,
                    "none",
                    0,
                    out,
                    f"existing transcript unreadable: {exc}",
                    2,
                )
            policy_min_words = quality_policy["min_words"]
            if not isinstance(policy_min_words, int):
                emit(
                    False,
                    args.video,
                    "none",
                    0,
                    out,
                    "internal quality policy has no integer word floor",
                    2,
                )
            ok, reason = validate_transcript(
                existing,
                min_words=policy_min_words,
                duration_seconds=trusted_duration,
            )
            if not ok:
                emit(
                    False,
                    args.video,
                    "existing",
                    count_words(existing),
                    out,
                    f"existing transcript is not usable: {reason}; inspect it and "
                    "pass --force to authorize replacement",
                    1,
                )
            receipt, _receipt_reason = load_verified_quality_receipt(out, existing)
            expected_receipt = {
                "policy": quality_policy,
                "provenance": quality_provenance,
            }
            # Same rule as the YouTube branch: a probe that could not read the
            # media leaves the fixed default in hand, and writing that over a
            # receipt already recording a source-owned duration trades evidence
            # for its absence. One condition this branch adds — the stored
            # receipt is only the stronger one while it still describes these
            # bytes. A receipt for different media is stale, not strong, so the
            # digest must match before it is preserved.
            would_discard_source_duration = (
                trusted_duration is None
                and receipt_claims_source_duration(receipt)
                and receipt_matches_media_digest(receipt, media.sha256)
            )
            if receipt != expected_receipt and not would_discard_source_duration:
                media.assert_unchanged(verify_source_digest=True)
                try:
                    write_quality_receipt(
                        out,
                        existing,
                        quality_policy,
                        quality_provenance,
                    )
                except (OSError, ValueError) as exc:
                    emit(
                        False,
                        args.video,
                        "existing",
                        count_words(existing),
                        out,
                        "existing transcript is valid but its quality receipt "
                        f"could not be written: {exc}",
                        2,
                    )
            timed_segments, timing_reason = load_verified_segments(
                out,
                existing,
                owner_source=args.existing_source,
                owner_media_sha256=media.sha256,
                owner_duration_seconds=trusted_duration,
            )
            media.assert_unchanged(verify_source_digest=True)
            emit(
                True,
                args.video,
                "existing",
                count_words(existing),
                out,
                f"kept existing transcript ({reason}); {timing_reason}",
                0,
                timed_path=sidecar_path(out) if timed_segments else None,
                quality_path=quality_sidecar_path(out),
            )

        transcription, lane_reason = run_optional_lane(
            "mlx-whisper transcription lane",
            lambda: transcribe_audio(media.path, args.video, args.whisper_model),
            expected_errors=WHISPER_LANE_ERRORS,
        )
        if transcription is None:
            emit(
                False,
                args.video,
                "none",
                0,
                out,
                f"local transcription failed — {lane_reason}; inspect stderr and "
                "install or repair the whisper lane before retrying",
                1,
            )
        text, language, segments = transcription
        if text is None:
            emit(
                False,
                args.video,
                "none",
                0,
                out,
                "local transcription produced no text — inspect stderr, then "
                "repair the audio or whisper runtime before retrying",
                1,
            )
        policy_min_words = quality_policy["min_words"]
        if not isinstance(policy_min_words, int):
            emit(
                False,
                args.video,
                "none",
                0,
                out,
                "internal quality policy has no integer word floor",
                2,
            )
        ok, reason = validate_transcript(
            text,
            min_words=policy_min_words,
            duration_seconds=trusted_duration,
        )
        if not ok:
            if trusted_duration is None and count_words(text) < DEFAULT_MIN_WORDS:
                reason += (
                    "; a lower short-talk floor is unavailable because no "
                    f"trusted media duration was available ({duration_reason})"
                )
            emit(
                False,
                args.video,
                "whisper",
                count_words(text),
                out,
                reason,
                1,
                language,
            )
        bundle_segments, bundle_timing_provenance, timing_reason = (
            prepare_optional_timing_safely(
                text,
                segments,
                source="whisper",
                provenance=timing_provenance,
            )
        )
        media.assert_unchanged(verify_source_digest=True)
        try:
            timed_path = write_transcript_bundle(
                out,
                text,
                bundle_segments,
                source="whisper",
                timing_provenance=bundle_timing_provenance,
                quality_policy=quality_policy,
                quality_policy_provenance=quality_provenance,
                force=args.force,
            )
        except (OSError, ValueError) as exc:
            print(
                f"cannot write the transcript bundle to {out}: {exc}", file=sys.stderr
            )
            emit(
                False,
                args.video,
                "whisper",
                count_words(text),
                out,
                f"transcript produced but its bundle could not be written: {exc}",
                2,
                language,
            )
        emit(
            True,
            args.video,
            "whisper",
            count_words(text),
            out,
            reason if timed_path else f"{reason}; {timing_reason}",
            0,
            language,
            timed_path,
            quality_sidecar_path(out),
        )


def main(argv: list[str] | None = None) -> NoReturn:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("video", help="YouTube video id, or any URL containing one")
    parser.add_argument("--out", required=True, help="transcript output path")
    parser.add_argument(
        "--languages",
        default="en,ru,he,fr,de",
        help="comma-separated caption language preference",
    )
    parser.add_argument(
        "--method", default="auto", choices=("auto", "captions", "whisper")
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="refetch even when a valid transcript already exists",
    )
    parser.add_argument(
        "--existing-source",
        choices=("youtube_auto", "whisper", "manual", "unknown"),
        default="unknown",
        help=(
            "owner-recorded provenance of an existing transcript; only "
            "youtube_auto authorizes non-destructive caption timing enrichment"
        ),
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=None,
        help="expected runtime; must match a source-owned probe",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=None,
        help=(
            "tighten the trusted word floor; values below the safe derived "
            "floor cannot relax it"
        ),
    )
    parser.add_argument(
        "--whisper-model", default="mlx-community/whisper-large-v3-turbo"
    )
    parser.add_argument(
        "--audio",
        default=None,
        help="transcribe this local audio/video file instead of "
        "downloading one (non-YouTube talks)",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse writes usage to stderr and exits without stdout. The contract
        # promises one JSON object on EVERY non-zero exit, so a wrapper parsing
        # stdout must not get silence when the arguments are wrong. `--help`
        # exits 0 and is re-raised untouched.
        if exc.code:
            emit(False, "", "none", 0, "", "invalid arguments — see stderr", 2)
        raise

    requested_min_words = args.min_words
    try:
        build_quality_policy(requested_min_words)
        normalize_duration(args.duration_seconds)
    except ValueError as exc:
        emit(False, args.video, "none", 0, args.out, str(exc), 2)

    if args.audio:
        try:
            _handle_local_audio(args, requested_min_words)
        except (OSError, ValueError) as exc:
            emit(
                False,
                args.video,
                "none",
                0,
                args.out,
                f"local-media acquisition failed: {exc}; inspect the source file "
                "and retry with a stable regular media artifact",
                2,
            )

    video_id = resolve_video_id(args.video)
    if not video_id:
        print(
            f"cannot find an 11-character video id in {args.video!r} — "
            "pass a bare id, a YouTube URL, or use --audio for a "
            "non-YouTube talk",
            file=sys.stderr,
        )
        emit(
            False,
            args.video,
            "none",
            0,
            args.out,
            "no YouTube video id in the argument; use --audio for a non-YouTube talk",
            2,
        )

    languages = [
        lang.strip() for lang in (args.languages or "").split(",") if lang.strip()
    ]
    out = Path(args.out)
    expected_name = f"{video_id}.txt"
    if out.name != expected_name:
        emit(
            False,
            video_id,
            "none",
            0,
            out,
            "YouTube transcript output identity mismatch: expected basename "
            f"{expected_name!r}",
            2,
        )
    try:
        ensure_bundle_destinations_are_not_symlinks(out)
    except ValueError as exc:
        emit(
            False,
            video_id,
            "none",
            0,
            out,
            f"unsafe transcript bundle destination: {exc}; replace the symlink "
            "with regular artifact paths before retrying",
            2,
        )
    trusted_duration: float | None = None
    quality_provenance: dict[str, object] = fixed_quality_provenance()
    duration_reason = "trusted YouTube duration was not probed"
    if out.exists() and not args.force:
        try:
            existing = out.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            print(
                f"existing transcript at {out} is not valid UTF-8: {exc} — "
                "replace it with UTF-8 text or refetch with --force",
                file=sys.stderr,
            )
            emit(
                False,
                video_id,
                "none",
                0,
                out,
                f"existing transcript is not valid UTF-8: {exc}",
                2,
            )
        except OSError as exc:
            # Unreadable existing file: emit rather than traceback. Refusing is
            # deliberate — silently refetching would overwrite a file we could
            # not inspect, and the point of this script is never to destroy data
            # it has not validated.
            print(
                f"cannot read the existing transcript at {out}: {exc} — "
                "fix the permissions, or delete the file to refetch",
                file=sys.stderr,
            )
            emit(
                False,
                video_id,
                "none",
                0,
                out,
                f"existing transcript unreadable: {exc}",
                2,
            )
        existing_words = count_words(existing)
        receipt, _receipt_reason = load_verified_quality_receipt(out, existing)
        # Stored duration authority is never trusted as its own proof. Re-probe
        # the current provider owner before a duration can bound the floor.
        #
        # The stored duration is also read here, but only to decide whether to
        # spend a probe. Gating the probe on the transcript looking too short
        # made the duration bound reachable only from below, so a caption track
        # covering a whole session block was never measured against the
        # recording it claims to describe. A receipt whose own duration cannot
        # hold this many words is grounds to go ask the provider — never
        # grounds to reject, which still requires the probe.
        needs_duration_probe = (
            args.duration_seconds is not None
            or existing_words < DEFAULT_MIN_WORDS
            or sidecar_path(out).exists()
            or receipt_claims_source_duration(receipt)
            or receipt_duration_cannot_hold(receipt, existing_words)
            or (
                args.existing_source == "youtube_auto"
                and args.method in {"auto", "captions"}
            )
        )
        if needs_duration_probe:
            trusted_duration, duration_reason = probe_youtube_duration(video_id)
            if trusted_duration is not None:
                quality_provenance = youtube_quality_provenance(
                    video_id,
                    trusted_duration,
                )
        if args.duration_seconds is not None:
            if trusted_duration is None:
                emit(
                    False,
                    video_id,
                    "existing",
                    existing_words,
                    out,
                    f"cannot verify --duration-seconds: {duration_reason}",
                    2,
                )
            if not duration_matches_expected(
                args.duration_seconds,
                trusted_duration,
            ):
                emit(
                    False,
                    video_id,
                    "existing",
                    existing_words,
                    out,
                    "--duration-seconds does not match the trusted receipt or "
                    f"provider probe (expected {args.duration_seconds}, source "
                    f"reports {trusted_duration})",
                    2,
                )
        quality_policy = build_quality_policy(
            requested_min_words,
            trusted_duration_seconds=trusted_duration,
        )
        policy_min_words = quality_policy["min_words"]
        if not isinstance(policy_min_words, int):
            emit(
                False,
                video_id,
                "none",
                0,
                out,
                "internal quality policy has no integer word floor",
                2,
            )
        ok, reason = validate_transcript(
            existing,
            min_words=policy_min_words,
            duration_seconds=trusted_duration,
        )
        if not ok:
            if trusted_duration is None and existing_words < DEFAULT_MIN_WORDS:
                reason += (
                    "; a lower short-talk floor is unavailable because no trusted "
                    f"provider duration was available ({duration_reason})"
                )
            emit(
                False,
                video_id,
                "existing",
                existing_words,
                out,
                f"existing transcript is not usable: {reason}; inspect it and "
                "pass --force to authorize replacement",
                1,
            )

        expected_receipt = {
            "policy": quality_policy,
            "provenance": quality_provenance,
        }
        # A probe that could not reach the provider leaves the fixed default in
        # hand. Writing that over a receipt that already records a source-owned
        # duration trades evidence for the absence of evidence, and the next
        # run inherits a transcript nothing can bound. Keep the stronger
        # receipt and let a run that reaches the provider refresh it.
        would_discard_source_duration = (
            trusted_duration is None and receipt_claims_source_duration(receipt)
        )
        if receipt != expected_receipt and not would_discard_source_duration:
            try:
                write_quality_receipt(
                    out,
                    existing,
                    quality_policy,
                    quality_provenance,
                )
            except (OSError, ValueError) as exc:
                print(
                    f"cannot write transcript quality receipt at {out}: {exc}",
                    file=sys.stderr,
                )
                emit(
                    False,
                    video_id,
                    "existing",
                    existing_words,
                    out,
                    "existing transcript is valid but its quality receipt "
                    f"could not be written: {exc}",
                    2,
                )
        timed_segments, timing_reason = load_verified_segments(
            out,
            existing,
            owner_source=args.existing_source,
            owner_video_id=video_id,
            owner_duration_seconds=trusted_duration,
        )
        timed_path = sidecar_path(out) if timed_segments else None
        if (
            timed_path is None
            and args.existing_source == "youtube_auto"
            and args.method in {"auto", "captions"}
        ):
            try:
                timed_path, timing_reason = enrich_existing_caption_timing(
                    out,
                    existing,
                    video_id,
                    languages,
                    existing_source=args.existing_source,
                    duration_seconds=trusted_duration,
                )
            except (OSError, ValueError) as exc:
                print(
                    f"caption timing enrichment failed safely for {out}: {exc}",
                    file=sys.stderr,
                )
                timing_reason = f"timing unavailable: receipt write failed: {exc}"
        elif timed_path is None and args.method == "whisper":
            timing_reason = (
                "timing unavailable: --method whisper forbids caption "
                "enrichment of an existing transcript"
            )
        emit(
            True,
            video_id,
            "existing",
            existing_words,
            out,
            f"kept existing transcript ({reason}); {timing_reason}",
            0,
            timed_path=timed_path,
            quality_path=quality_sidecar_path(out),
        )

    if trusted_duration is None:
        trusted_duration, duration_reason = probe_youtube_duration(video_id)
        if trusted_duration is not None:
            quality_provenance = youtube_quality_provenance(
                video_id,
                trusted_duration,
            )
        elif args.duration_seconds is not None:
            emit(
                False,
                video_id,
                "none",
                0,
                out,
                f"cannot verify --duration-seconds: {duration_reason}",
                2,
            )
        else:
            print(
                f"{duration_reason}; applying the fixed "
                f"{DEFAULT_MIN_WORDS}-word quality floor",
                file=sys.stderr,
            )
            quality_provenance = fixed_quality_provenance()
    if (
        args.duration_seconds is not None
        and trusted_duration is not None
        and not (duration_matches_expected(args.duration_seconds, trusted_duration))
    ):
        emit(
            False,
            video_id,
            "none",
            0,
            out,
            "--duration-seconds does not match the YouTube provider probe "
            f"(expected {args.duration_seconds}, source reports "
            f"{trusted_duration})",
            2,
        )
    quality_policy = build_quality_policy(
        requested_min_words,
        trusted_duration_seconds=trusted_duration,
    )

    attempts = [
        name for name in ("captions", "whisper") if args.method in ("auto", name)
    ]

    failures = []
    for name in attempts:
        if name == "captions":
            lane_result, lane_reason = run_optional_lane(
                "youtube-transcript-api caption lane",
                lambda: fetch_captions(video_id, languages),
                expected_errors=CAPTION_LANE_ERRORS,
            )
        else:
            with tempfile.TemporaryDirectory() as work_dir:
                lane_result, lane_reason = run_optional_lane(
                    "YouTube Whisper lane",
                    lambda: fetch_whisper(video_id, work_dir, args.whisper_model),
                    expected_errors=WHISPER_LANE_ERRORS,
                )
        if lane_result is None:
            failures.append(f"{name}: {lane_reason}")
            continue
        text, language, segments = lane_result
        if text is None:
            failures.append(f"{name}: unavailable")
            continue
        # Captions only. A caption track can belong to a different recording —
        # a venue's session block served to one talk's video — and cues running
        # far past the duration are the direct evidence of it. Whisper cannot
        # be foreign: it transcribes the audio in hand. Its timestamps are
        # merely sometimes sloppy, and this same talk has already produced
        # "malformed or zero-duration segments" from that lane. Applying the
        # check there would discard a sound transcript over bad timing, and
        # since Whisper is the last fallback the talk would end with nothing.
        if name == "captions" and timing_extent_is_foreign(segments, trusted_duration):
            overrun = timing_extent_overrun_ratio(segments, trusted_duration) or 0.0
            failures.append(
                f"{name}: caption track covers {overrun:.1f}x this recording's "
                "duration — it belongs to a longer video"
            )
            continue
        policy_min_words = quality_policy["min_words"]
        if not isinstance(policy_min_words, int):
            emit(
                False,
                video_id,
                "none",
                0,
                out,
                "internal quality policy has no integer word floor",
                2,
            )
        ok, reason = validate_transcript(
            text,
            min_words=policy_min_words,
            duration_seconds=trusted_duration,
        )
        if ok:
            timing_provenance = (
                youtube_timing_provenance(
                    name,
                    video_id,
                    trusted_duration,
                )
                if trusted_duration is not None
                else None
            )
            bundle_segments, bundle_timing_provenance, timing_reason = (
                prepare_optional_timing_safely(
                    text,
                    segments,
                    source=name,
                    provenance=timing_provenance,
                )
            )
            try:
                timed_path = write_transcript_bundle(
                    out,
                    text,
                    bundle_segments,
                    source=name,
                    timing_provenance=bundle_timing_provenance,
                    quality_policy=quality_policy,
                    quality_policy_provenance=quality_provenance,
                    force=args.force,
                )
            except (OSError, ValueError) as exc:
                # The bundle writer rolls back every attempted replacement.
                print(
                    f"cannot write the transcript bundle to {out}: {exc}",
                    file=sys.stderr,
                )
                emit(
                    False,
                    video_id,
                    name,
                    count_words(text),
                    out,
                    f"transcript fetched but its bundle could not be written: {exc}",
                    2,
                    language,
                )
            emit(
                True,
                video_id,
                name,
                count_words(text),
                out,
                reason if timed_path else f"{reason}; {timing_reason}",
                0,
                language,
                timed_path,
                quality_sidecar_path(out),
            )
        if trusted_duration is None and count_words(text) < DEFAULT_MIN_WORDS:
            reason += (
                "; a lower short-talk floor is unavailable because no trusted "
                f"provider duration was available ({duration_reason})"
            )
        failures.append(f"{name}: {reason}")

    emit(
        False,
        video_id,
        "none",
        0,
        out,
        "no source produced a valid transcript — " + "; ".join(failures),
        1,
    )


if __name__ == "__main__":
    try:
        main()
    # outer-boundary-process-contract: callers treat missing JSON as a silent
    # failure; emit one failure object because propagation breaks orchestration.
    except Exception as exc:  # noqa: BLE001
        print(
            f"unexpected transcript fetch failure: {type(exc).__name__}: {exc}; "
            "inspect this diagnostic, repair the named input or dependency, and retry",
            file=sys.stderr,
        )
        emit(
            False,
            "",
            "none",
            0,
            "",
            f"unexpected fetch failure: {exc}; inspect stderr, repair the named "
            "input or dependency, and retry",
            2,
        )

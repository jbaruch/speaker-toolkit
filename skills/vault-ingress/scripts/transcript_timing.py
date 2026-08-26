#!/usr/bin/env python3
"""Own transcript timing and quality receipts used by vault-ingress.

Plain ``transcripts/<id>.txt`` remains the human- and model-readable transcript.
When source timing is available, the writer also creates
``transcripts/<id>.segments.json`` with this shape::

    {
      "schema_version": 2,
      "transcript_sha256": "...",
      "source": "captions|whisper|vtt",
      "provenance": {
        "kind": "youtube_captions",
        "video_id": "...",
        "duration_seconds": 212.125
      },
      "segments": [
        {"text": "...", "start_seconds": 1.2, "end_seconds": 3.4}
      ]
    }

Timing/acquisition identity lives only in ``<id>.segments.json``. Transcript
quality authority lives independently in ``<id>.quality.json``::

    {
      "schema_version": 1,
      "transcript_sha256": "...",
      "policy": {
        "schema_version": 1,
        "min_words": 400,
        "duration_seconds": null
      },
      "provenance": {"kind": "fixed_default"}
    }

Both receipts hash the exact text. Timing schema v2 additionally binds the
receipt to the source owner or exact local artifact, requires segment text to
equal the transcript modulo whitespace layout, and checks source time bounds.
Schema v1 remains archival and is never current provenance authority. Bundle
writes stage every artifact and roll back all replacements when a write fails.
Keeping separate files lets an already-valid transcript gain a quality receipt
without inventing timing or acquisition provenance.

This module is deterministic and intentionally contains no network or model
logic. Fetchers supply source segments; persistence uses :func:`resolve_quote`
to verify model-supplied quotes and stamp engine-owned line/time locations.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from transcript_quality import (
    build_quality_policy,
    normalize_duration,
    validate_quality_policy,
)

SIDECAR_SCHEMA_VERSION = 2
SIDECAR_SOURCES = frozenset({"captions", "whisper", "vtt"})
TIMING_RECEIPT_FIELDS = frozenset(
    {"schema_version", "transcript_sha256", "source", "provenance", "segments"}
)
TIMING_PROVENANCE_KINDS = frozenset(
    {"youtube_captions", "youtube_whisper", "local_media_whisper", "vtt_artifact"}
)
TIMING_OWNER_SOURCES = frozenset(
    {"youtube_auto", "whisper", "manual", "unknown", "vtt"}
)
# A caption cue carries display time, not speech time, so the final cue
# routinely outlives the recording by a second or two. Measured across a
# 12-talk sample of this vault's caption-sourced transcripts, the overhang runs
# -10.88s to +2.32s and 7 of the 12 sat between 1.4s and 2.32s — so a 1.0s
# bound discarded the timed evidence of most talks that had any. Negative
# values are equally ordinary: captions often stop before the video does.
#
# The bound only has to absorb that format artifact. Whether the cues describe
# a different recording is FOREIGN_TIMING_EXTENT_RATIO's question, and it has
# its own headroom — on a 318s video it fires at ~80s of overrun, so nothing
# this tolerance admits can hide from it.
TIMING_BOUND_TOLERANCE_SECONDS = 5.0
# Past the tolerance above, timing is merely untrustworthy — a caption track
# routinely trails its video by a rounding artifact. Past this ratio it is not
# this recording's track at all: the segments describe more speech than the
# recording can physically hold, which is what a venue's whole session block
# looks like when YouTube serves it to one talk's video. The two thresholds
# answer different questions, so they are separate constants; this one is
# deliberately loose because its verdict throws the transcript away.
FOREIGN_TIMING_EXTENT_RATIO = 1.25


def timing_extent_overrun_ratio(
    segments: object, duration_seconds: object
) -> float | None:
    """Return how far timed segments run past a source-owned duration.

    `None` when the question cannot be asked — no usable duration, or no
    segment carrying a readable end. A ratio of 1.0 means the final cue lands
    exactly on the end of the recording. Normalization is shared with the rest
    of this module, so a raw caption object and a stored segment dict are read
    the same way.
    """
    if (
        not isinstance(duration_seconds, (int, float))
        or isinstance(duration_seconds, bool)
        or not math.isfinite(float(duration_seconds))
        or float(duration_seconds) <= 0
    ):
        return None
    if segments is None or isinstance(segments, (str, bytes)):
        return None
    if not isinstance(segments, Iterable):
        return None
    normalized = normalize_segments(segments)
    ends = [
        float(end)
        for item in normalized
        for end in (item.get("end_seconds"),)
        if isinstance(end, (int, float)) and not isinstance(end, bool)
    ]
    if not ends:
        return None
    return max(ends) / float(duration_seconds)


def timing_extent_is_foreign(segments: object, duration_seconds: object) -> bool:
    """Return whether timed segments describe a different recording."""
    ratio = timing_extent_overrun_ratio(segments, duration_seconds)
    return ratio is not None and ratio > FOREIGN_TIMING_EXTENT_RATIO


QUALITY_RECEIPT_SCHEMA_VERSION = 1
QUALITY_RECEIPT_FIELDS = frozenset(
    {"schema_version", "transcript_sha256", "policy", "provenance"}
)
QUALITY_PROVENANCE_KINDS = frozenset(
    {"fixed_default", "youtube_duration", "local_media_duration"}
)
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SPACE = re.compile(r"\s+")
_SMART_PUNCTUATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
)


def normalize_for_match(text: str) -> str:
    """Normalize harmless transcript/quote typography without paraphrasing."""
    normalized = unicodedata.normalize("NFKC", text).translate(_SMART_PUNCTUATION)
    return _SPACE.sub(" ", normalized).strip().casefold()


def transcript_sha256(text: str) -> str:
    """Hash the exact UTF-8 transcript bytes represented by ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def transcript_file_sha256(
    transcript_path: str | os.PathLike[str],
) -> tuple[str | None, str]:
    """Hash exact on-disk bytes without newline or decoding normalization."""
    path = Path(transcript_path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, f"transcript artifact is missing: {path}"
    except OSError as exc:
        return None, f"cannot read transcript artifact {path}: {exc}"
    return hashlib.sha256(raw).hexdigest(), "verified exact transcript bytes"


def sidecar_path(transcript_path: str | os.PathLike[str]) -> Path:
    """Return ``<stem>.segments.json`` beside a transcript path."""
    return Path(transcript_path).with_suffix(".segments.json")


def quality_sidecar_path(transcript_path: str | os.PathLike[str]) -> Path:
    """Return ``<stem>.quality.json`` beside a transcript path."""
    return Path(transcript_path).with_suffix(".quality.json")


def ensure_bundle_destinations_are_not_symlinks(
    transcript_path: str | os.PathLike[str],
) -> None:
    """Reject final-component symlinks for every transcript bundle artifact.

    ``Path.exists()`` is intentionally insufficient here: it returns ``False``
    for a dangling symlink. Atomic replacement would otherwise replace the link
    entry itself and make rollback semantics depend on what its target did.
    """
    transcript = Path(transcript_path)
    for destination in (
        transcript,
        sidecar_path(transcript),
        quality_sidecar_path(transcript),
    ):
        if destination.is_symlink():
            raise ValueError(
                f"refusing transcript bundle destination symlink: {destination}"
            )


def validate_vtt_artifact_path(
    transcript_path: str | os.PathLike[str],
    artifact_path: str | os.PathLike[str],
) -> tuple[Path, PurePosixPath]:
    """Validate one VTT artifact before any caller reads or opens it.

    The transcript directory is the trust root. Both the lexical path and the
    resolved path must remain below it, every component below that root must be
    a non-symlink, and the final entry must already be a regular file.
    """
    transcript_root = Path(os.path.abspath(Path(transcript_path).parent))
    artifact_input = Path(artifact_path)
    if ".." in artifact_input.parts:
        raise ValueError("VTT timing artifact path must not contain '..'")
    artifact = Path(os.path.abspath(artifact_input))
    try:
        lexical_relative = artifact.relative_to(transcript_root)
    except ValueError as exc:
        raise ValueError(
            "VTT timing artifact must be lexically inside the transcript directory"
        ) from exc
    if not lexical_relative.parts:
        raise ValueError("VTT timing artifact must name a file")

    cursor = transcript_root
    final_stat: os.stat_result | None = None
    for part in lexical_relative.parts:
        cursor /= part
        try:
            component_stat = cursor.lstat()
        except FileNotFoundError as exc:
            raise ValueError("VTT timing artifact must exist") from exc
        except OSError as exc:
            raise ValueError(
                f"cannot inspect VTT timing artifact component {cursor}: {exc}"
            ) from exc
        if stat.S_ISLNK(component_stat.st_mode):
            raise ValueError("VTT timing artifact path must not contain symlinks")
        final_stat = component_stat

    if final_stat is None or not stat.S_ISREG(final_stat.st_mode):
        raise ValueError("VTT timing artifact must be a regular file")

    try:
        resolved_root = transcript_root.resolve(strict=True)
        resolved_artifact = artifact.resolve(strict=True)
        resolved_artifact.relative_to(resolved_root)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(
            "VTT timing artifact must resolve inside the transcript directory"
        ) from exc
    return artifact, PurePosixPath(*lexical_relative.parts)


def _field(segment: object, name: str) -> Any:
    if isinstance(segment, dict):
        return segment.get(name)
    return getattr(segment, name, None)


def normalize_segments(segments: Iterable[object] | None) -> list[dict[str, object]]:
    """Convert caption-library and Whisper segment shapes to the sidecar shape.

    A segment without text or a finite non-negative start/end pair cannot locate
    evidence and is omitted. Output is ordered by time so quote resolution is
    deterministic even if an upstream library returns an unusual collection.
    """
    normalized: list[dict[str, object]] = []
    for segment in segments or []:
        text = _field(segment, "text")
        start = _field(segment, "start_seconds")
        if start is None:
            start = _field(segment, "start")
        end = _field(segment, "end_seconds")
        if end is None:
            end = _field(segment, "end")
        if end is None:
            duration = _field(segment, "duration")
            if isinstance(start, (int, float)) and isinstance(duration, (int, float)):
                end = float(start) + float(duration)
        if (
            not isinstance(text, str)
            or not text.strip()
            or isinstance(start, bool)
            or not isinstance(start, (int, float))
            or isinstance(end, bool)
            or not isinstance(end, (int, float))
            or not math.isfinite(float(start))
            or not math.isfinite(float(end))
            or float(start) < 0
            or float(end) <= float(start)
        ):
            continue
        rounded_start = round(float(start), 3)
        rounded_end = round(float(end), 3)
        if rounded_end <= rounded_start:
            continue
        normalized.append(
            {
                "text": text.strip(),
                "start_seconds": rounded_start,
                "end_seconds": rounded_end,
            }
        )
    normalized.sort(key=lambda item: (item["start_seconds"], item["end_seconds"]))
    return normalized


def write_atomically(path: str | os.PathLike[str], text: str) -> None:
    """Write exact UTF-8 bytes through a same-directory file, then replace.

    Binary mode is intentional: platform newline translation would make the
    bytes on disk disagree with the transcript digest already recorded in its
    timing and quality receipts.
    """
    destination = Path(path)
    if destination.is_symlink():
        raise ValueError(f"refusing atomic-write destination symlink: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(destination.parent), suffix=".partial")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(text.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if destination.is_symlink():
            raise OSError(f"atomic-write destination became a symlink: {destination}")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _stage_bytes(destination: Path, raw: bytes) -> Path:
    """Stage exact bytes beside their destination without replacing it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(destination.parent), suffix=".partial")
    temporary_path = Path(temporary)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
    return temporary_path


def _replace_transactionally(replacements: list[tuple[Path, bytes | None]]) -> None:
    """Replace a small artifact set and restore exact prior bytes on failure.

    There is no portable multi-file rename transaction. New files and exact
    backups are staged first; a caught replacement failure restores every path
    already attempted. A process death between renames can still leave a
    partial bundle. Hash checks reject changed-text mixtures; byte-identical
    replacement can expose an already valid new receipt before restart.
    """
    destinations = [destination for destination, _raw in replacements]
    if len(destinations) != len(set(destinations)):
        raise ValueError("transactional artifact destinations must be unique")
    for destination in destinations:
        if destination.is_symlink():
            raise ValueError(
                f"refusing transactional destination symlink: {destination}"
            )

    staged_new: dict[Path, Path] = {}
    staged_old: dict[Path, Path] = {}
    attempted: list[Path] = []
    try:
        for destination, raw in replacements:
            try:
                original = destination.read_bytes()
            except FileNotFoundError:
                original = None
            if original is not None:
                staged_old[destination] = _stage_bytes(destination, original)
            if raw is not None:
                staged_new[destination] = _stage_bytes(destination, raw)

        for destination, raw in replacements:
            if destination.is_symlink():
                raise OSError(
                    f"transactional destination became a symlink: {destination}"
                )
            attempted.append(destination)
            if raw is None:
                destination.unlink(missing_ok=True)
            else:
                os.replace(staged_new[destination], destination)
                staged_new.pop(destination)
    except OSError as exc:
        rollback_errors: list[str] = []
        for destination in reversed(attempted):
            try:
                if destination.is_symlink():
                    rollback_errors.append(
                        f"{destination}: destination became a symlink; left untouched"
                    )
                    continue
                backup = staged_old.pop(destination, None)
                if backup is None:
                    destination.unlink(missing_ok=True)
                else:
                    os.replace(backup, destination)
            except OSError as rollback_exc:
                rollback_errors.append(f"{destination}: {rollback_exc}")
        if rollback_errors:
            raise OSError(
                f"artifact transaction failed ({exc}); rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    finally:
        for temporary in (*staged_new.values(), *staged_old.values()):
            temporary.unlink(missing_ok=True)


def youtube_timing_provenance(
    source: str,
    video_id: str,
    duration_seconds: int | float | None,
) -> dict[str, object]:
    """Bind caption or Whisper timing to one exact YouTube owner."""
    if source not in {"captions", "whisper"}:
        raise ValueError("YouTube timing source must be captions or whisper")
    provenance = {
        "kind": "youtube_captions" if source == "captions" else "youtube_whisper",
        "video_id": video_id,
        "duration_seconds": normalize_duration(duration_seconds),
    }
    return _normalize_timing_provenance(source, provenance)


def local_media_timing_provenance(
    media_sha256: str,
    duration_seconds: int | float | None,
) -> dict[str, object]:
    """Bind Whisper timing to exact local-media bytes."""
    return _normalize_timing_provenance(
        "whisper",
        {
            "kind": "local_media_whisper",
            "media_sha256": media_sha256,
            "duration_seconds": normalize_duration(duration_seconds),
        },
    )


def vtt_timing_provenance(
    transcript_path: str | os.PathLike[str],
    artifact_path: str | os.PathLike[str],
    artifact_sha256: str,
    cue_extent_seconds: int | float | None,
) -> dict[str, object]:
    """Bind imported timing to one exact VTT path and byte digest."""
    _artifact, relative_artifact = validate_vtt_artifact_path(
        transcript_path,
        artifact_path,
    )
    return _normalize_timing_provenance(
        "vtt",
        {
            "kind": "vtt_artifact",
            "artifact_path": relative_artifact.as_posix(),
            "artifact_sha256": artifact_sha256,
            "cue_extent_seconds": normalize_duration(cue_extent_seconds),
        },
    )


def _normalize_timing_provenance(
    source: str,
    provenance: object,
) -> dict[str, object]:
    """Validate one closed timing provenance object for its declared source."""
    if source not in SIDECAR_SOURCES:
        raise ValueError(
            f"unsupported transcript timing source {source!r}; "
            f"expected one of {sorted(SIDECAR_SOURCES)}"
        )
    if not isinstance(provenance, dict):
        raise ValueError("transcript timing provenance must be an object")
    kind = provenance.get("kind")
    if kind not in TIMING_PROVENANCE_KINDS:
        raise ValueError("transcript timing provenance kind is unsupported")

    if kind in {"youtube_captions", "youtube_whisper"}:
        expected_source = "captions" if kind == "youtube_captions" else "whisper"
        if source != expected_source:
            raise ValueError(f"{kind} provenance is incompatible with {source!r}")
        if set(provenance) != {"kind", "video_id", "duration_seconds"}:
            raise ValueError(
                f"{kind} provenance requires exactly video_id and duration_seconds"
            )
        video_id = provenance.get("video_id")
        if not isinstance(video_id, str) or _YOUTUBE_ID.fullmatch(video_id) is None:
            raise ValueError(f"{kind} provenance requires an 11-character video_id")
        raw_duration = provenance.get("duration_seconds")
        if not isinstance(raw_duration, (int, float)) or isinstance(raw_duration, bool):
            raise ValueError(f"{kind} provenance requires a trusted duration")
        return {
            "kind": kind,
            "video_id": video_id,
            "duration_seconds": normalize_duration(raw_duration),
        }

    if kind == "local_media_whisper":
        if source != "whisper":
            raise ValueError("local_media_whisper provenance requires whisper source")
        if set(provenance) != {"kind", "media_sha256", "duration_seconds"}:
            raise ValueError(
                "local_media_whisper provenance requires exactly media_sha256 "
                "and duration_seconds"
            )
        media_digest = provenance.get("media_sha256")
        if not isinstance(media_digest, str) or _SHA256.fullmatch(media_digest) is None:
            raise ValueError(
                "local_media_whisper provenance requires a lowercase SHA-256 digest"
            )
        raw_duration = provenance.get("duration_seconds")
        if not isinstance(raw_duration, (int, float)) or isinstance(raw_duration, bool):
            raise ValueError(
                "local_media_whisper provenance requires a trusted duration"
            )
        return {
            "kind": kind,
            "media_sha256": media_digest,
            "duration_seconds": normalize_duration(raw_duration),
        }

    if source != "vtt":
        raise ValueError("vtt_artifact provenance requires vtt source")
    if set(provenance) != {
        "kind",
        "artifact_path",
        "artifact_sha256",
        "cue_extent_seconds",
    }:
        raise ValueError(
            "vtt_artifact provenance requires exactly artifact_path, "
            "artifact_sha256, and cue_extent_seconds"
        )
    artifact_path = provenance.get("artifact_path")
    artifact_digest = provenance.get("artifact_sha256")
    if not isinstance(artifact_path, str) or not artifact_path:
        raise ValueError("vtt_artifact provenance requires a non-empty artifact_path")
    portable_path = PurePosixPath(artifact_path)
    if (
        portable_path.is_absolute()
        or artifact_path != portable_path.as_posix()
        or any(part in {"", ".", ".."} for part in portable_path.parts)
    ):
        raise ValueError(
            "vtt_artifact artifact_path must be a safe transcript-relative POSIX path"
        )
    if (
        not isinstance(artifact_digest, str)
        or _SHA256.fullmatch(artifact_digest) is None
    ):
        raise ValueError("vtt_artifact provenance requires a lowercase SHA-256 digest")
    raw_cue_extent = provenance.get("cue_extent_seconds")
    if not isinstance(raw_cue_extent, (int, float)) or isinstance(raw_cue_extent, bool):
        raise ValueError("vtt_artifact provenance requires a positive cue extent")
    return {
        "kind": kind,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_digest,
        "cue_extent_seconds": normalize_duration(raw_cue_extent),
    }


def write_transcript_bundle(
    transcript_path: str | os.PathLike[str],
    text: str,
    segments: Iterable[object] | None,
    *,
    source: str,
    timing_provenance: dict[str, object] | None,
    quality_policy: dict[str, object] | None = None,
    quality_policy_provenance: dict[str, object] | None = None,
    force: bool = False,
) -> Path | None:
    """Transactionally replace transcript text plus independent receipts.

    Missing segments or trusted timing provenance removes any older timing
    sidecar in the same transaction and returns ``None``. A supplied quality
    policy requires exact provenance. Existing transcript bytes are never
    replaced unless ``force`` is true. A caught write failure restores all
    prior transcript and receipt bytes.
    """
    transcript = Path(transcript_path)
    ensure_bundle_destinations_are_not_symlinks(transcript)
    if transcript.exists() and not force:
        raise FileExistsError(
            f"transcript already exists at {transcript}; pass force=True to replace it"
        )
    if (quality_policy is None) != (quality_policy_provenance is None):
        raise ValueError(
            "transcript quality policy and provenance must be supplied together"
        )
    raw_segments = list(segments or [])
    timing_path = sidecar_path(transcript)
    replacements: list[tuple[Path, bytes | None]] = []
    normalized_segments: list[dict[str, object]] = []
    if timing_provenance is not None and raw_segments:
        timing_payload, normalized_segments = _build_timing_receipt(
            text,
            raw_segments,
            source=source,
            provenance=timing_provenance,
        )
        replacements.append(
            (
                timing_path,
                (
                    json.dumps(timing_payload, indent=2, ensure_ascii=False) + "\n"
                ).encode("utf-8"),
            )
        )
    else:
        # A fresh transcript without trustworthy bounded timing must invalidate
        # any older receipt, including when replacement text is byte-identical.
        replacements.append((timing_path, None))
    if quality_policy is not None and quality_policy_provenance is not None:
        quality_payload = _build_quality_receipt(
            text,
            quality_policy,
            quality_policy_provenance,
        )
        replacements.append(
            (
                quality_sidecar_path(transcript),
                (
                    json.dumps(quality_payload, indent=2, ensure_ascii=False) + "\n"
                ).encode("utf-8"),
            )
        )
    replacements.append((transcript, text.encode("utf-8")))
    _replace_transactionally(replacements)
    return timing_path if normalized_segments else None


def write_timing_receipt(
    transcript_path: str | os.PathLike[str],
    text: str,
    segments: Iterable[object] | None,
    *,
    source: str,
    provenance: dict[str, object],
) -> Path:
    """Write only a timing receipt, preserving the transcript bytes.

    This is the safe enrichment primitive for an already-valid transcript. The
    caller must establish source/text equivalence before using it. Current
    timing requires at least one usable segment and trusted source bounds;
    callers without them must not call this writer.
    """
    payload, _normalized = _build_timing_receipt(
        text,
        segments,
        source=source,
        provenance=provenance,
    )
    timing_path = sidecar_path(transcript_path)
    write_atomically(
        timing_path,
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
    )
    return timing_path


def _build_timing_receipt(
    text: str,
    segments: Iterable[object] | None,
    *,
    source: str,
    provenance: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Build one canonical schema-v2 timing receipt without writing it."""
    raw_segments = list(segments or [])
    if not raw_segments:
        raise ValueError("a current timing receipt requires at least one segment")
    normalized_segments = normalize_segments(raw_segments)
    if len(normalized_segments) != len(raw_segments):
        raise ValueError(
            "transcript timing contains malformed or zero-duration segments"
        )
    normalized_provenance = _normalize_timing_provenance(source, provenance)
    _validate_timing_semantics(text, normalized_segments, normalized_provenance)
    return {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "transcript_sha256": transcript_sha256(text),
        "source": source,
        "provenance": normalized_provenance,
        "segments": normalized_segments,
    }, normalized_segments


def validate_timing_receipt(
    text: str,
    segments: Iterable[object] | None,
    *,
    source: str,
    provenance: dict[str, object],
) -> tuple[bool, str]:
    """Preflight optional timing without weakening the strict receipt writer.

    Fetchers use this boundary to keep valid semantic transcript text when a
    provider's optional segment payload is malformed, incomplete, or outside
    its trusted time bound. Direct receipt writers remain strict and still
    raise ``ValueError`` for the same payload.
    """
    try:
        _payload, normalized = _build_timing_receipt(
            text,
            segments,
            source=source,
            provenance=provenance,
        )
    except ValueError as exc:
        return False, str(exc)
    return True, f"{len(normalized)} source-bound timed segments"


def _validate_timing_semantics(
    transcript_text: str,
    segments: list[dict[str, object]],
    provenance: dict[str, object],
) -> None:
    """Require complete segment text plus source-owned timing bounds."""
    if segments:
        segment_text = "\n".join(str(segment["text"]) for segment in segments)
        if not timing_enrichment_equivalent(transcript_text, segment_text):
            raise ValueError(
                "timed segment text does not equal the transcript modulo whitespace"
            )

    end_values: list[float] = []
    for segment in segments:
        raw_end = segment.get("end_seconds")
        if (
            isinstance(raw_end, bool)
            or not isinstance(raw_end, (int, float))
            or not math.isfinite(float(raw_end))
        ):
            raise ValueError("timed segment has an invalid end_seconds value")
        end_values.append(float(raw_end))
    maximum_end = max(end_values, default=None)
    kind = provenance.get("kind")
    if kind == "vtt_artifact":
        cue_extent = provenance.get("cue_extent_seconds")
        if not isinstance(cue_extent, (int, float)) or isinstance(cue_extent, bool):
            raise ValueError("VTT timing with segments requires cue_extent_seconds")
        if maximum_end is None:  # pragma: no cover - receipt builder rejects empty
            raise ValueError("VTT timing requires at least one segment")
        if float(cue_extent) != maximum_end:
            raise ValueError(
                "VTT cue_extent_seconds must equal the final timed cue boundary"
            )
        return

    duration = provenance.get("duration_seconds")
    if (
        maximum_end is not None
        and isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and maximum_end > float(duration) + TIMING_BOUND_TOLERANCE_SECONDS
    ):
        raise ValueError(
            f"timed segments overhang the source-owned duration by "
            f"{maximum_end - float(duration):.2f}s, beyond the "
            f"{TIMING_BOUND_TOLERANCE_SECONDS:.0f}s tolerance — delete the "
            "transcript's .segments.json sidecar and re-run "
            "fetch-transcript.py to rebuild timing from the current "
            "recording; an overhang that is a large multiple of the duration "
            "means the track belongs to a different video, so re-fetch the "
            "transcript itself"
        )


def timing_enrichment_equivalent(existing: str, fetched: str) -> bool:
    """Require exact caption text modulo Unicode whitespace runs only.

    Legacy caption transcripts were often stored as one long line while the
    current fetcher emits one line per segment. Collapsing whitespace admits
    only that layout difference: case, punctuation, words, and order must stay
    byte-for-character identical. A manually edited transcript therefore cannot
    acquire caption provenance through this check.
    """
    if not isinstance(existing, str) or not isinstance(fetched, str):
        return False
    normalized_existing = _SPACE.sub(" ", existing).strip()
    normalized_fetched = _SPACE.sub(" ", fetched).strip()
    return bool(normalized_existing) and normalized_existing == normalized_fetched


def _normalize_quality_provenance(
    provenance: object,
    policy: dict[str, object],
) -> dict[str, object]:
    """Validate and normalize the exact authority behind a quality policy."""
    if not isinstance(provenance, dict):
        raise ValueError("quality policy provenance must be an object")
    kind = provenance.get("kind")
    if kind not in QUALITY_PROVENANCE_KINDS:
        raise ValueError(
            "quality policy provenance kind must be fixed_default, "
            "youtube_duration, or local_media_duration"
        )
    raw_policy_duration = policy.get("duration_seconds")
    if raw_policy_duration is not None and not isinstance(
        raw_policy_duration, (int, float)
    ):
        raise ValueError("quality policy duration is invalid")
    policy_duration = normalize_duration(raw_policy_duration)
    if kind == "fixed_default":
        if set(provenance) != {"kind"} or policy_duration is not None:
            raise ValueError(
                "fixed_default provenance requires no duration and no extra fields"
            )
        return {"kind": "fixed_default"}
    raw_duration = provenance.get("duration_seconds")
    if not isinstance(raw_duration, (int, float)) or isinstance(raw_duration, bool):
        raise ValueError("quality policy provenance duration is invalid")
    duration = normalize_duration(raw_duration)
    if policy_duration is None or duration != policy_duration:
        raise ValueError(f"{kind} provenance must exactly match policy duration")
    if kind == "youtube_duration":
        if set(provenance) != {"kind", "video_id", "duration_seconds"}:
            raise ValueError(
                "youtube_duration provenance requires exactly video_id and "
                "duration_seconds"
            )
        video_id = provenance.get("video_id")
        if not isinstance(video_id, str) or _YOUTUBE_ID.fullmatch(video_id) is None:
            raise ValueError(
                "youtube_duration provenance requires an 11-character video_id"
            )
        return {
            "kind": "youtube_duration",
            "video_id": video_id,
            "duration_seconds": duration,
        }
    if set(provenance) != {"kind", "media_sha256", "duration_seconds"}:
        raise ValueError(
            "local_media_duration provenance requires exactly media_sha256 and "
            "duration_seconds"
        )
    media_sha256 = provenance.get("media_sha256")
    if not isinstance(media_sha256, str) or _SHA256.fullmatch(media_sha256) is None:
        raise ValueError(
            "local_media_duration provenance requires a lowercase SHA-256 digest"
        )
    return {
        "kind": "local_media_duration",
        "media_sha256": media_sha256,
        "duration_seconds": duration,
    }


def write_quality_receipt(
    transcript_path: str | os.PathLike[str],
    text: str,
    policy: dict[str, object],
    provenance: dict[str, object],
) -> Path:
    """Atomically write one exact, transcript-hash-bound quality receipt."""
    payload = _build_quality_receipt(text, policy, provenance)
    receipt_path = quality_sidecar_path(transcript_path)
    write_atomically(
        receipt_path,
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
    )
    return receipt_path


def _build_quality_receipt(
    text: str,
    policy: dict[str, object],
    provenance: dict[str, object],
) -> dict[str, object]:
    """Build one canonical quality receipt without writing it."""
    policy_ok, policy_reason = validate_quality_policy(policy)
    if not policy_ok:
        raise ValueError(f"transcript quality policy is invalid: {policy_reason}")
    min_words = policy.get("min_words")
    duration = policy.get("duration_seconds")
    if not isinstance(min_words, int) or isinstance(min_words, bool):
        raise ValueError("transcript quality policy min_words is invalid")
    if duration is not None and (
        not isinstance(duration, (int, float)) or isinstance(duration, bool)
    ):
        raise ValueError("transcript quality policy duration is invalid")
    normalized_policy = build_quality_policy(
        min_words,
        trusted_duration_seconds=duration,
    )
    normalized_provenance = _normalize_quality_provenance(
        provenance,
        normalized_policy,
    )
    return {
        "schema_version": QUALITY_RECEIPT_SCHEMA_VERSION,
        "transcript_sha256": transcript_sha256(text),
        "policy": normalized_policy,
        "provenance": normalized_provenance,
    }


def load_verified_quality_receipt(
    transcript_path: str | os.PathLike[str], _text: str
) -> tuple[dict[str, object] | None, str]:
    """Read policy plus provenance iff the receipt matches the exact text."""
    receipt_path = quality_sidecar_path(transcript_path)
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"transcript quality sidecar is missing: {receipt_path}"
    except OSError as exc:
        return None, f"cannot read transcript quality sidecar {receipt_path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, (
            f"transcript quality sidecar {receipt_path} is invalid JSON: {exc}"
        )
    if not isinstance(payload, dict) or set(payload) != QUALITY_RECEIPT_FIELDS:
        return None, (
            f"transcript quality sidecar {receipt_path} is not an exact receipt"
        )
    if payload.get("schema_version") != QUALITY_RECEIPT_SCHEMA_VERSION:
        return None, (
            f"transcript quality sidecar {receipt_path} has unsupported schema"
        )
    transcript_digest, digest_reason = transcript_file_sha256(transcript_path)
    if transcript_digest is None:
        return None, digest_reason
    if payload.get("transcript_sha256") != transcript_digest:
        return None, (
            f"transcript quality sidecar {receipt_path} does not match the transcript"
        )
    policy = payload.get("policy")
    policy_ok, policy_reason = validate_quality_policy(policy)
    if not policy_ok or not isinstance(policy, dict):
        return None, f"verified sidecar has an invalid quality policy: {policy_reason}"
    try:
        provenance = _normalize_quality_provenance(
            payload.get("provenance"),
            policy,
        )
    except ValueError as exc:
        return None, f"verified sidecar has invalid quality provenance: {exc}"
    if (
        provenance.get("kind") == "youtube_duration"
        and Path(transcript_path).name != f"{provenance.get('video_id')}.txt"
    ):
        return None, (
            "verified sidecar has youtube_duration provenance for a different "
            "transcript identity"
        )
    return {
        "policy": dict(policy),
        "provenance": provenance,
    }, "verified transcript quality receipt"


def load_verified_quality_policy(
    transcript_path: str | os.PathLike[str], text: str
) -> tuple[dict[str, object] | None, str]:
    """Return the exact policy from a hash-current quality receipt."""
    receipt, reason = load_verified_quality_receipt(transcript_path, text)
    if receipt is None:
        return None, reason
    policy = receipt.get("policy")
    if not isinstance(policy, dict):
        return None, "verified transcript quality receipt has no policy object"
    return dict(policy), reason


def load_verified_transcript_source(
    transcript_path: str | os.PathLike[str],
    _text: str,
    *,
    owner_source: str,
    owner_video_id: str | None = None,
    owner_media_sha256: str | None = None,
    owner_duration_seconds: int | float | None = None,
) -> tuple[str | None, str]:
    """Return acquisition provenance only when the recorded owner agrees."""
    payload, reason = _load_verified_timing_receipt(transcript_path)
    if payload is None:
        return None, reason
    owner_ok, owner_reason = _timing_owner_matches(
        payload,
        owner_source=owner_source,
        owner_video_id=owner_video_id,
        owner_media_sha256=owner_media_sha256,
        owner_duration_seconds=owner_duration_seconds,
    )
    if not owner_ok:
        return None, owner_reason
    return str(payload["source"]), "verified owner-bound transcript provenance"


def load_verified_segments(
    transcript_path: str | os.PathLike[str],
    _text: str,
    *,
    owner_source: str,
    owner_video_id: str | None = None,
    owner_media_sha256: str | None = None,
    owner_duration_seconds: int | float | None = None,
) -> tuple[list[dict[str, object]], str]:
    """Load timing iff schema, text, source artifact, and owner are current.

    Returns ``(segments, reason)``. An empty list is never silently ambiguous:
    ``reason`` states whether timing is absent, stale, malformed, or simply
    unavailable from the source.
    """
    payload, reason = _load_verified_timing_receipt(transcript_path)
    if payload is None:
        return [], reason
    owner_ok, owner_reason = _timing_owner_matches(
        payload,
        owner_source=owner_source,
        owner_video_id=owner_video_id,
        owner_media_sha256=owner_media_sha256,
        owner_duration_seconds=owner_duration_seconds,
    )
    if not owner_ok:
        return [], owner_reason
    raw_segments = payload["segments"]
    if not isinstance(raw_segments, list):  # pragma: no cover - loader owns shape
        return [], "verified timing receipt has no segments array"
    segments = [dict(segment) for segment in raw_segments]
    if not segments:
        return [], (
            "transcript source recorded no timed segments in "
            f"{sidecar_path(transcript_path)}"
        )
    return segments, f"{len(segments)} verified owner-bound timed segments"


def _load_verified_timing_receipt(
    transcript_path: str | os.PathLike[str],
) -> tuple[dict[str, object] | None, str]:
    """Load one exact schema-v2 timing receipt and validate its artifact."""
    timing_path = sidecar_path(transcript_path)
    try:
        payload = json.loads(timing_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"timed transcript sidecar is missing: {timing_path}"
    except OSError as exc:
        return None, f"cannot read timed transcript sidecar {timing_path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"timed transcript sidecar {timing_path} is invalid JSON: {exc}"
    if not isinstance(payload, dict) or set(payload) != TIMING_RECEIPT_FIELDS:
        return None, f"timed transcript sidecar {timing_path} is not an exact receipt"
    if payload.get("schema_version") != SIDECAR_SCHEMA_VERSION:
        return None, (
            f"timed transcript sidecar {timing_path} has unsupported schema_version "
            f"{payload.get('schema_version')!r}; regenerate schema v2 timing"
        )
    source = payload.get("source")
    if source not in SIDECAR_SOURCES:
        return None, (
            f"timed transcript sidecar {timing_path} has unsupported source "
            f"{source!r}; regenerate it"
        )
    transcript = Path(transcript_path)
    try:
        transcript_bytes = transcript.read_bytes()
    except FileNotFoundError:
        return None, f"transcript artifact is missing: {transcript}"
    except OSError as exc:
        return None, f"cannot read transcript artifact {transcript}: {exc}"
    try:
        transcript_text = transcript_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, f"transcript artifact is not valid UTF-8: {exc}"
    transcript_digest = hashlib.sha256(transcript_bytes).hexdigest()
    if payload.get("transcript_sha256") != transcript_digest:
        return None, (
            f"timed transcript sidecar {timing_path} does not match the transcript; "
            "regenerate both files together"
        )
    try:
        normalized_provenance = _normalize_timing_provenance(
            str(source), payload.get("provenance")
        )
    except ValueError as exc:
        return (
            None,
            f"timed transcript sidecar {timing_path} has invalid provenance: {exc}",
        )
    if normalized_provenance != payload.get("provenance"):
        return None, f"timed transcript sidecar {timing_path} is not canonical"
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        return None, f"timed transcript sidecar {timing_path} has no segments array"
    segments = normalize_segments(raw_segments)
    if segments != raw_segments:
        return None, (
            f"timed transcript sidecar {timing_path} contains malformed or "
            "noncanonical segments; regenerate it"
        )
    try:
        _validate_timing_semantics(
            transcript_text,
            segments,
            normalized_provenance,
        )
    except ValueError as exc:
        return None, f"timed transcript sidecar {timing_path} is invalid: {exc}"

    if normalized_provenance.get("kind") == "vtt_artifact":
        artifact_relative = PurePosixPath(str(normalized_provenance["artifact_path"]))
        artifact_path = Path(transcript_path).parent.joinpath(*artifact_relative.parts)
        try:
            resolved_artifact, _relative = validate_vtt_artifact_path(
                transcript_path,
                artifact_path,
            )
        except ValueError as exc:
            return None, f"VTT timing source artifact is unsafe: {exc}"
        try:
            artifact_digest = hashlib.sha256(resolved_artifact.read_bytes()).hexdigest()
        except OSError as exc:
            return None, (
                f"cannot read VTT timing source artifact {resolved_artifact}: {exc}"
            )
        if artifact_digest != normalized_provenance.get("artifact_sha256"):
            return None, "VTT timing source artifact digest does not match the receipt"

    return {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "transcript_sha256": transcript_digest,
        "source": source,
        "provenance": normalized_provenance,
        "segments": segments,
    }, "verified schema-v2 timing receipt"


def _timing_owner_matches(
    payload: dict[str, object],
    *,
    owner_source: str,
    owner_video_id: str | None,
    owner_media_sha256: str | None,
    owner_duration_seconds: int | float | None,
) -> tuple[bool, str]:
    """Check timing acquisition identity against owner-recorded provenance."""
    if owner_source not in TIMING_OWNER_SOURCES:
        return False, f"unsupported owner transcript source {owner_source!r}"
    source = payload.get("source")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):  # pragma: no cover - loader owns shape
        return False, "timing receipt has no provenance object"
    kind = provenance.get("kind")

    if source == "captions":
        if owner_source != "youtube_auto":
            return False, (
                "timing owner mismatch: caption timing cannot relabel "
                f"{owner_source!r} transcript provenance"
            )
        if owner_video_id is None or provenance.get("video_id") != owner_video_id:
            return False, "timing owner mismatch: caption video_id differs"
    elif source == "whisper":
        if owner_source != "whisper":
            return False, (
                "timing owner mismatch: Whisper timing cannot relabel "
                f"{owner_source!r} transcript provenance"
            )
        if kind == "youtube_whisper":
            if owner_video_id is None or provenance.get("video_id") != owner_video_id:
                return False, "timing owner mismatch: Whisper video_id differs"
        elif kind == "local_media_whisper":
            if (
                owner_media_sha256 is None
                or provenance.get("media_sha256") != owner_media_sha256
            ):
                return False, "timing owner mismatch: local-media digest differs"
        else:  # pragma: no cover - provenance validator owns compatibility
            return False, "timing owner mismatch: Whisper provenance is invalid"
    elif source != "vtt":  # pragma: no cover - loader owns source allowlist
        return False, "timing owner mismatch: unsupported source"

    recorded_duration = provenance.get("duration_seconds")
    if source != "vtt":
        if owner_duration_seconds is None:
            return False, "timing owner mismatch: trusted owner duration is missing"
        try:
            owner_duration = normalize_duration(owner_duration_seconds)
        except ValueError as exc:
            return False, f"timing owner duration is invalid: {exc}"
        if (
            owner_duration is None
            or not isinstance(recorded_duration, (int, float))
            or isinstance(recorded_duration, bool)
            or abs(float(recorded_duration) - owner_duration) > 1.0
        ):
            return False, "timing owner mismatch: source duration differs"
    return True, "timing receipt matches owner-recorded provenance"


def _joined_offsets(
    parts: Iterable[tuple[int, str]],
) -> tuple[str, list[tuple[int, int, int]]]:
    joined: list[str] = []
    offsets: list[tuple[int, int, int]] = []
    cursor = 0
    for identity, raw_text in parts:
        text = normalize_for_match(raw_text)
        if not text:
            continue
        if joined:
            joined.append(" ")
            cursor += 1
        start = cursor
        joined.append(text)
        cursor += len(text)
        offsets.append((identity, start, cursor))
    return "".join(joined), offsets


def _unique_span(haystack: str, needle: str) -> tuple[int, int] | None:
    def word_character(character: str) -> bool:
        return character == "_" or character.isalnum()

    matches: list[tuple[int, int]] = []
    cursor = 0
    while True:
        start = haystack.find(needle, cursor)
        if start < 0:
            break
        end = start + len(needle)
        starts_inside_word = (
            start > 0
            and word_character(haystack[start - 1])
            and word_character(haystack[start])
        )
        ends_inside_word = (
            end < len(haystack)
            and word_character(haystack[end - 1])
            and word_character(haystack[end])
        )
        if not starts_inside_word and not ends_inside_word:
            matches.append((start, end))
            if len(matches) > 1:
                raise ValueError(
                    "quote appears more than once in the transcript; provide a "
                    "longer unique quote"
                )
        cursor = start + 1
    return matches[0] if matches else None


def _identities_for_span(
    offsets: list[tuple[int, int, int]], start: int, end: int
) -> list[int]:
    return [
        identity
        for identity, item_start, item_end in offsets
        if item_end > start and item_start < end
    ]


def resolve_quote(
    transcript_text: str,
    quote: str,
    *,
    segments: Iterable[object] | None = None,
) -> dict[str, object]:
    """Verify one unique quote and return engine-owned line/time locations.

    Raises ``ValueError`` for missing or ambiguous quotes. A caller may supply a
    verified sidecar's segments; when their text cannot resolve the same quote,
    line locations still succeed but no timestamps are invented.
    """
    normalized_quote = normalize_for_match(quote)
    if not normalized_quote:
        raise ValueError("quote is empty after normalization")

    line_haystack, line_offsets = _joined_offsets(
        (line_number, line)
        for line_number, line in enumerate(transcript_text.splitlines(), 1)
    )
    span = _unique_span(line_haystack, normalized_quote)
    if span is None:
        raise ValueError("quote does not appear verbatim in the transcript")
    line_numbers = _identities_for_span(line_offsets, *span)
    if not line_numbers:
        raise ValueError(
            "quote matched transcript text but could not be assigned to a line"
        )
    resolved: dict[str, object] = {
        "line_start": line_numbers[0],
        "line_end": line_numbers[-1],
    }

    normalized_segments = normalize_segments(segments)
    if normalized_segments:
        segment_haystack, segment_offsets = _joined_offsets(
            (index, str(segment["text"]))
            for index, segment in enumerate(normalized_segments)
        )
        try:
            segment_span = _unique_span(segment_haystack, normalized_quote)
        except ValueError:
            # Cumulative/overlapping caption tracks can repeat text that is
            # unique in the canonical transcript. Line proof remains valid;
            # timing is unavailable unless the sidecar has one unique span.
            segment_span = None
        if segment_span is not None:
            segment_indexes = _identities_for_span(segment_offsets, *segment_span)
            if segment_indexes:
                first = normalized_segments[segment_indexes[0]]
                last = normalized_segments[segment_indexes[-1]]
                resolved["start_seconds"] = first["start_seconds"]
                resolved["end_seconds"] = last["end_seconds"]
    return resolved

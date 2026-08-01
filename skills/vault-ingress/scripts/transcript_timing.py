#!/usr/bin/env python3
"""Own the timed-transcript sidecar used by vault-ingress.

Plain ``transcripts/<id>.txt`` remains the human- and model-readable transcript.
When caption or Whisper segment timing is available, the writer also creates
``transcripts/<id>.segments.json`` with this shape::

    {
      "schema_version": 1,
      "transcript_sha256": "...",
      "source": "captions|whisper|vtt",
      "segments": [
        {"text": "...", "start_seconds": 1.2, "end_seconds": 3.4}
      ]
    }

The hash binds the sidecar to the exact text file. Readers reject a stale or
partially-written pair rather than applying old timestamps to new words. The
sidecar is written before the transcript: if the second atomic replace fails,
the new hash cannot match the old transcript and the sidecar safely reads as
unusable.

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
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable

SIDECAR_SCHEMA_VERSION = 1
SIDECAR_SOURCES = frozenset({"captions", "whisper", "vtt"})
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


def sidecar_path(transcript_path: str | os.PathLike[str]) -> Path:
    """Return ``<stem>.segments.json`` beside a transcript path."""
    return Path(transcript_path).with_suffix(".segments.json")


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
    """Write text through a same-directory temporary file, then replace."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(destination.parent), suffix=".partial")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_transcript_bundle(
    transcript_path: str | os.PathLike[str],
    text: str,
    segments: Iterable[object] | None,
    *,
    source: str,
) -> Path | None:
    """Atomically write transcript text plus its hash-bound timing sidecar.

    An empty ``segments`` collection still writes a valid empty sidecar. That
    invalidates any older timing file whose text no longer matches while making
    the absence of timing explicit. The return is the sidecar path only when it
    contains usable timed segments.
    """
    if source not in SIDECAR_SOURCES:
        raise ValueError(
            f"unsupported transcript timing source {source!r}; "
            f"expected one of {sorted(SIDECAR_SOURCES)}"
        )
    normalized = normalize_segments(segments)
    timing_path = sidecar_path(transcript_path)
    payload = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "transcript_sha256": transcript_sha256(text),
        "source": source,
        "segments": normalized,
    }
    write_atomically(
        timing_path,
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
    )
    write_atomically(transcript_path, text)
    return timing_path if normalized else None


def load_verified_segments(
    transcript_path: str | os.PathLike[str], text: str
) -> tuple[list[dict[str, object]], str]:
    """Load a sidecar iff its schema and transcript hash are current.

    Returns ``(segments, reason)``. An empty list is never silently ambiguous:
    ``reason`` states whether timing is absent, stale, malformed, or simply
    unavailable from the source.
    """
    timing_path = sidecar_path(transcript_path)
    try:
        payload = json.loads(timing_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], f"timed transcript sidecar is missing: {timing_path}"
    except OSError as exc:
        return [], f"cannot read timed transcript sidecar {timing_path}: {exc}"
    except json.JSONDecodeError as exc:
        return [], f"timed transcript sidecar {timing_path} is invalid JSON: {exc}"
    if not isinstance(payload, dict):
        return [], f"timed transcript sidecar {timing_path} is not a JSON object"
    if payload.get("schema_version") != SIDECAR_SCHEMA_VERSION:
        return [], (
            f"timed transcript sidecar {timing_path} has unsupported schema_version "
            f"{payload.get('schema_version')!r}; regenerate it"
        )
    if payload.get("source") not in SIDECAR_SOURCES:
        return [], (
            f"timed transcript sidecar {timing_path} has unsupported source "
            f"{payload.get('source')!r}; regenerate it"
        )
    if payload.get("transcript_sha256") != transcript_sha256(text):
        return [], (
            f"timed transcript sidecar {timing_path} does not match the transcript; "
            "regenerate both files together"
        )
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        return [], f"timed transcript sidecar {timing_path} has no segments array"
    segments = normalize_segments(raw_segments)
    if len(segments) != len(raw_segments):
        return [], (
            f"timed transcript sidecar {timing_path} contains malformed or "
            "zero-duration segments; regenerate it"
        )
    if not segments:
        return [], f"transcript source recorded no timed segments in {timing_path}"
    return segments, f"{len(segments)} verified timed segments"


def _joined_offsets(parts: Iterable[tuple[int, str]]) -> tuple[str, list[tuple[int, int, int]]]:
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
    first = haystack.find(needle)
    if first < 0:
        return None
    if haystack.find(needle, first + 1) >= 0:
        raise ValueError(
            "quote appears more than once in the transcript; provide a longer unique quote"
        )
    return first, first + len(needle)


def _identities_for_span(
    offsets: list[tuple[int, int, int]], start: int, end: int
) -> list[int]:
    return [identity for identity, item_start, item_end in offsets if item_end > start and item_start < end]


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
        (line_number, line) for line_number, line in enumerate(transcript_text.splitlines(), 1)
    )
    span = _unique_span(line_haystack, normalized_quote)
    if span is None:
        raise ValueError("quote does not appear verbatim in the transcript")
    line_numbers = _identities_for_span(line_offsets, *span)
    if not line_numbers:
        raise ValueError("quote matched transcript text but could not be assigned to a line")
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
        segment_span = _unique_span(segment_haystack, normalized_quote)
        if segment_span is not None:
            segment_indexes = _identities_for_span(segment_offsets, *segment_span)
            if segment_indexes:
                first = normalized_segments[segment_indexes[0]]
                last = normalized_segments[segment_indexes[-1]]
                resolved["start_seconds"] = first["start_seconds"]
                resolved["end_seconds"] = last["end_seconds"]
    return resolved

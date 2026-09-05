"""Closed sampled-word receipts owned by the ingress media-acquisition lane.

This pure boundary validates and normalizes provider data; it does not acquire
media or authenticate a caller-supplied digest. Times are sample-relative, never
interpolated from segment timestamps. Only punctuation-only tokens are omitted,
with an explicit index/reason record. Invalid lexical spans refuse the sample.
"""

from __future__ import annotations

from collections.abc import Mapping
import copy
import math
from numbers import Real
import re
from typing import Any, NoReturn

from local_media_contract import LocalMediaError


WORDS_PIPELINE_VERSION = "sampled-words-v2"
WORDS_MAX_SAMPLE_SECONDS = 1200
WORDS_MAX_SOURCE_SECONDS = 14400
WORDS_MAX_COUNT = 50000
WORDS_MAX_SEGMENTS = 5000
WORDS_MAX_TOKEN_BYTES = 1024
WORD_VALIDATION_FAILURES = frozenset(
    {
        "whisper_word_sample_invalid",
        "whisper_word_sample_invalid_token",
        "whisper_word_sample_invalid_word_span",
        "whisper_word_sample_invalid_word_overlap",
        "whisper_word_sample_invalid_word_nonpositive_span",
        "whisper_word_sample_invalid_word_probability",
        "whisper_word_sample_invalid_segment_span",
        "whisper_word_sample_invalid_word_segment",
    }
)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_MODEL = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")
_LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*\Z")

# Renew the model pin quarterly in a dedicated dependency/capability change.
# Verify native word alignment and language detection before accepting a new
# revision. The Python packages retain their own manifest/Dependabot pins.
DEFAULT_WORD_MODEL = {
    "id": "mlx-community/whisper-large-v3-turbo",
    "revision": "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
}


def _refuse(detail: str = "") -> NoReturn:
    code = "whisper_word_sample_invalid" + ("_" + detail if detail else "")
    if code not in WORD_VALIDATION_FAILURES:
        raise ValueError("unsupported word-validation diagnostic")
    raise LocalMediaError(code)


def _token_bytes(text: str) -> int:
    try:
        return len(text.encode("utf-8"))
    except UnicodeEncodeError:
        _refuse()


def _object(value: Any, fields: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        _refuse()
    return value


def _number(value: Any, low: float, high: float) -> float:
    if type(value) not in (int, float) or not low <= value <= high:
        _refuse()
    result = float(value)
    if not math.isfinite(result):
        _refuse()
    return result


def validate_word_diagnostic(value: Any) -> dict:
    """Closed numeric-only failure evidence, never source locators or words."""
    diagnostic = _object(
        value,
        {
            "schema_version",
            "word_index",
            "word_count",
            "word_start_seconds",
            "word_end_seconds",
            "segment_index",
            "segment_count",
            "segment_start_seconds",
            "segment_end_seconds",
        },
    )
    if (
        type(diagnostic["schema_version"]) is not int
        or diagnostic["schema_version"] != 1
    ):
        _refuse()
    for field, maximum in (
        ("word_count", WORDS_MAX_COUNT),
        ("segment_count", WORDS_MAX_SEGMENTS),
    ):
        if type(diagnostic[field]) is not int or not 1 <= diagnostic[field] <= maximum:
            _refuse()
    index = diagnostic["word_index"]
    if type(index) is not int or not 0 <= index < diagnostic["word_count"]:
        _refuse()
    begin = _number(diagnostic["word_start_seconds"], 0, WORDS_MAX_SAMPLE_SECONDS)
    end = _number(diagnostic["word_end_seconds"], begin, WORDS_MAX_SAMPLE_SECONDS)
    if end <= begin:
        _refuse()
    index = diagnostic["segment_index"]
    if index is None:
        if (
            diagnostic["segment_start_seconds"] is not None
            or diagnostic["segment_end_seconds"] is not None
        ):
            _refuse()
    else:
        if type(index) is not int or not 0 <= index < diagnostic["segment_count"]:
            _refuse()
        start = _number(
            diagnostic["segment_start_seconds"], 0, WORDS_MAX_SAMPLE_SECONDS
        )
        finish = _number(
            diagnostic["segment_end_seconds"], start, WORDS_MAX_SAMPLE_SECONDS
        )
        if finish <= start:
            _refuse()
    return diagnostic


class WordSampleError(LocalMediaError):
    """A segment-membership refusal with bounded numeric worker diagnostics."""

    def __init__(self, diagnostic: Any):
        self.word_timing = copy.deepcopy(validate_word_diagnostic(diagnostic))
        super().__init__("whisper_word_sample_invalid_word_segment")


def _provider_number(value: Any) -> Any:
    # Native alignment returns NumPy real scalars. Project those losslessly to
    # Python floats at this boundary; persisted receipts still require plain
    # JSON numbers. This does not alter, interpolate or repair a timestamp.
    if type(value) in (int, float) or not isinstance(value, Real):
        return value
    if isinstance(value, bool):
        return value
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError):
        _refuse()
    if converted != value:
        _refuse()
    return converted


def validate_word_model(value: Any) -> dict:
    model = _object(value, {"id", "revision"})
    if (
        not isinstance(model["id"], str)
        or len(model["id"]) > 120
        or _MODEL.fullmatch(model["id"]) is None
        or not isinstance(model["revision"], str)
        or _REVISION.fullmatch(model["revision"]) is None
    ):
        _refuse()
    return model


def validate_word_sample(value: Any) -> dict:
    sample = _object(
        value,
        {
            "schema_version",
            "pipeline_version",
            "source_sha256",
            "sample_sha256",
            "source_duration_seconds",
            "sample_start_seconds",
            "sample_duration_seconds",
            "provider",
            "provider_version",
            "model",
            "language",
            "language_probability",
            "language_probe_seconds",
            "words",
            "segments",
            "token_exclusions",
        },
    )
    if (
        type(sample["schema_version"]) is not int
        or sample["schema_version"] != 2
        or sample["pipeline_version"] != WORDS_PIPELINE_VERSION
        or sample["provider"] != "mlx-whisper"
        or not isinstance(sample["provider_version"], str)
        or _VERSION.fullmatch(sample["provider_version"]) is None
    ):
        _refuse()
    for key in ("source_sha256", "sample_sha256"):
        if not isinstance(sample[key], str) or _SHA.fullmatch(sample[key]) is None:
            _refuse()
    validate_word_model(sample["model"])
    duration = _number(sample["sample_duration_seconds"], 0, WORDS_MAX_SAMPLE_SECONDS)
    source_duration = _number(
        sample["source_duration_seconds"], 0, WORDS_MAX_SOURCE_SECONDS
    )
    start = _number(sample["sample_start_seconds"], 0, source_duration)
    if duration <= 0 or start + duration > source_duration:
        _refuse()
    if (
        not isinstance(sample["language"], str)
        or _LANGUAGE.fullmatch(sample["language"]) is None
    ):
        _refuse()
    _number(sample["language_probability"], 0, 1)
    probe_seconds = _number(sample["language_probe_seconds"], 0, min(duration, 30))
    if probe_seconds <= 0:
        _refuse()
    words = sample["words"]
    if not isinstance(words, list) or not 1 <= len(words) <= WORDS_MAX_COUNT:
        _refuse()
    previous_end = 0.0
    for word in words:
        word = _object(
            word,
            {"text", "start_seconds", "end_seconds", "probability", "segment_index"},
        )
        text = word["text"]
        if (
            not isinstance(text, str)
            or not text
            or _token_bytes(text) > WORDS_MAX_TOKEN_BYTES
            or any(ord(char) < 32 for char in text)
            or any(char.isspace() for char in text)
            or not any(char.isalnum() for char in text)
        ):
            _refuse("token")
        try:
            begin = _number(word["start_seconds"], 0, duration)
            end = _number(word["end_seconds"], 0, duration)
        except LocalMediaError:
            _refuse("word_span")
        if begin < previous_end:
            _refuse("word_overlap")
        if end <= begin:
            _refuse("word_nonpositive_span")
        try:
            _number(word["probability"], 0, 1)
        except LocalMediaError:
            _refuse("word_probability")
        previous_end = end
    segments = sample["segments"]
    if not isinstance(segments, list) or not 1 <= len(segments) <= WORDS_MAX_SEGMENTS:
        _refuse()
    previous_end = 0.0
    for segment in segments:
        segment = _object(
            segment,
            {
                "start_seconds",
                "end_seconds",
                "compression_ratio",
                "average_log_probability",
                "no_speech_probability",
            },
        )
        try:
            begin = _number(segment["start_seconds"], previous_end, duration)
            end = _number(segment["end_seconds"], begin, duration)
        except LocalMediaError:
            _refuse("segment_span")
        if end <= begin:
            _refuse("segment_span")
        _number(segment["compression_ratio"], 0, 10000)
        _number(segment["average_log_probability"], -10000, 0)
        _number(segment["no_speech_probability"], 0, 1)
        previous_end = end
    # Preserve the provider's explicit membership, not a guessed containing box.
    # MLX median-duration adjustments can place boundary words across the retained
    # segment timestamp. Positive overlap binds quality metadata without changing
    # either timestamp. Word/segment ordering and sample bounds still apply.
    previous_index = 0
    for word_index, word in enumerate(words):
        index = word["segment_index"]
        if type(index) is not int or not previous_index <= index < len(segments):
            _refuse("word_segment")
        previous_index = index
        segment = segments[index]
        if not (
            segment["start_seconds"] < word["end_seconds"]
            and word["start_seconds"] < segment["end_seconds"]
        ):
            raise WordSampleError(
                {
                    "schema_version": 1,
                    "word_index": word_index,
                    "word_count": len(words),
                    "word_start_seconds": word["start_seconds"],
                    "word_end_seconds": word["end_seconds"],
                    "segment_index": index,
                    "segment_count": len(segments),
                    "segment_start_seconds": segment["start_seconds"],
                    "segment_end_seconds": segment["end_seconds"],
                }
            )
    exclusions = sample["token_exclusions"]
    if not isinstance(exclusions, list) or len(exclusions) > WORDS_MAX_COUNT:
        _refuse()
    previous_index = -1
    for item in exclusions:
        item = _object(item, {"token_index", "reason"})
        if (
            type(item["token_index"]) is not int
            or not previous_index < item["token_index"] < WORDS_MAX_COUNT
            or item["reason"] != "punctuation_only"
        ):
            _refuse()
        previous_index = item["token_index"]
    return sample


def normalize_word_result(
    value: Any,
    *,
    source_sha256: str,
    sample_sha256: str,
    source_duration_seconds: float,
    sample_start_seconds: float,
    sample_duration_seconds: float,
    provider_version: str,
    model: dict,
    language_probability: float,
) -> dict:
    """Project bounded provider output; never make up word times or confidence."""
    if not isinstance(value, Mapping) or not isinstance(value.get("segments"), list):
        _refuse()
    if not 1 <= len(value["segments"]) <= WORDS_MAX_SEGMENTS:
        _refuse()
    words, segments, exclusions = [], [], []
    token_index = 0
    for segment_index, segment in enumerate(value["segments"]):
        if not isinstance(segment, Mapping) or not isinstance(
            segment.get("words"), list
        ):
            _refuse()
        segments.append(
            {
                "start_seconds": _provider_number(segment.get("start")),
                "end_seconds": _provider_number(segment.get("end")),
                "compression_ratio": _provider_number(segment.get("compression_ratio")),
                "average_log_probability": _provider_number(segment.get("avg_logprob")),
                "no_speech_probability": _provider_number(
                    segment.get("no_speech_prob")
                ),
            }
        )
        if token_index + len(segment["words"]) > WORDS_MAX_COUNT:
            _refuse()
        for word in segment["words"]:
            if not isinstance(word, Mapping) or not isinstance(word.get("word"), str):
                _refuse()
            text = word["word"].strip()
            if (
                not text
                or _token_bytes(text) > WORDS_MAX_TOKEN_BYTES
                or any(ord(char) < 32 for char in text)
            ):
                _refuse()
            if not any(char.isalnum() for char in text):
                exclusions.append(
                    {"token_index": token_index, "reason": "punctuation_only"}
                )
            else:
                words.append(
                    {
                        "text": text,
                        "start_seconds": _provider_number(word.get("start")),
                        "end_seconds": _provider_number(word.get("end")),
                        "probability": _provider_number(word.get("probability")),
                        "segment_index": segment_index,
                    }
                )
            token_index += 1
    return validate_word_sample(
        {
            "schema_version": 2,
            "pipeline_version": WORDS_PIPELINE_VERSION,
            "source_sha256": source_sha256,
            "sample_sha256": sample_sha256,
            "source_duration_seconds": source_duration_seconds,
            "sample_start_seconds": sample_start_seconds,
            "sample_duration_seconds": sample_duration_seconds,
            "provider": "mlx-whisper",
            "provider_version": provider_version,
            "model": copy.deepcopy(model),
            "language": value.get("language"),
            "language_probability": language_probability,
            "language_probe_seconds": min(30.0, sample_duration_seconds),
            "words": words,
            "segments": segments,
            "token_exclusions": exclusions,
        }
    )

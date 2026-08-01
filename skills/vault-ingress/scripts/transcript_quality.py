"""Pure quality contract for transcript artifacts used by vault ingress.

The fixed 400-word floor is the safe default when source duration is unknown.
A lower floor is valid only when a source-owned duration proves that the whole
recording is genuinely short. ``min_words`` is therefore a tightening knob,
never an escape hatch: values below the derived floor cannot relax it.
"""

from __future__ import annotations

import math
import re


FAILURE_SIGNATURES = (
    "Traceback (most recent call last)",
    "AttributeError:",
    "NameError:",
    "ModuleNotFoundError:",
    "ImportError:",
)
FAILURE_SCAN_CHARS = 400
VTT_TIMING_TAG = re.compile(r"<(?:\d{2}:)?\d{2}:\d{2}\.\d{3}>|</?c(?:\.[^>]*)?>")
VTT_SCAN_CHARS = 4000
NON_SPEECH_MARKERS = ("[Music]", "[Applause]", "[Laughter]", "[музыка]")
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
DEFAULT_MIN_WORDS = 400
MIN_WORDS_PER_MINUTE = 30
QUALITY_POLICY_SCHEMA_VERSION = 1
QUALITY_POLICY_FIELDS = frozenset({"schema_version", "min_words", "duration_seconds"})


def count_words(text: str) -> int:
    """Count Unicode speech words, including Cyrillic and accented Latin."""
    return len(WORD.findall(text))


def normalize_duration(duration_seconds: int | float | None) -> float | None:
    """Return one stable trusted-duration value or reject an invalid value."""
    if duration_seconds is None:
        return None
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not math.isfinite(float(duration_seconds))
        or float(duration_seconds) <= 0
    ):
        raise ValueError(
            "transcript duration bound is invalid; pass a positive finite "
            "trusted duration in seconds"
        )
    return round(float(duration_seconds), 3)


def effective_min_words(
    requested_min_words: int | None = None,
    *,
    trusted_duration_seconds: int | float | None = None,
) -> int:
    """Return the canonical word floor for one trusted validation policy.

    The duration is trusted by the caller (for example, an exact YouTube
    provider probe or ``ffprobe`` of the local media). A low requested value
    never relaxes either the fixed default or the duration-derived short-talk
    floor. Any requested value above the derived floor deliberately tightens
    the policy.
    """
    if requested_min_words is not None and (
        isinstance(requested_min_words, bool)
        or not isinstance(requested_min_words, int)
        or requested_min_words < 1
    ):
        raise ValueError(
            "minimum transcript word count is invalid; pass a positive integer "
            "word floor"
        )
    duration = normalize_duration(trusted_duration_seconds)
    derived_floor = DEFAULT_MIN_WORDS
    if duration is not None:
        derived_floor = min(
            DEFAULT_MIN_WORDS,
            max(1, math.ceil(duration / 60.0 * MIN_WORDS_PER_MINUTE)),
        )
    return (
        derived_floor
        if requested_min_words is None
        else max(derived_floor, requested_min_words)
    )


def build_quality_policy(
    requested_min_words: int | None = None,
    *,
    trusted_duration_seconds: int | float | None = None,
) -> dict[str, object]:
    """Build the exact reusable policy applied to transcript bytes."""
    duration = normalize_duration(trusted_duration_seconds)
    return {
        "schema_version": QUALITY_POLICY_SCHEMA_VERSION,
        "min_words": effective_min_words(
            requested_min_words,
            trusted_duration_seconds=duration,
        ),
        "duration_seconds": duration,
    }


def validate_quality_policy(policy: object) -> tuple[bool, str]:
    """Validate that a stored policy is exact, canonical, and non-bypassable."""
    if not isinstance(policy, dict) or set(policy) != QUALITY_POLICY_FIELDS:
        return False, (
            "quality policy must contain exactly schema_version, min_words, "
            "and duration_seconds"
        )
    if policy.get("schema_version") != QUALITY_POLICY_SCHEMA_VERSION:
        return False, "quality policy has an unsupported schema_version"
    min_words = policy.get("min_words")
    duration = policy.get("duration_seconds")
    if not isinstance(min_words, int) or isinstance(min_words, bool):
        return False, (
            "minimum transcript word count is invalid; pass a positive integer "
            "word floor"
        )
    if duration is not None and (
        not isinstance(duration, (int, float)) or isinstance(duration, bool)
    ):
        return False, (
            "transcript duration bound is invalid; pass a positive finite "
            "trusted duration in seconds"
        )
    try:
        canonical = build_quality_policy(
            min_words,
            trusted_duration_seconds=duration,
        )
    except ValueError as exc:
        return False, str(exc)
    if canonical != policy:
        return False, (
            "quality policy word floor is below the safe fixed or "
            "duration-derived minimum"
        )
    return True, "canonical transcript quality policy"


def validate_transcript(
    text: str,
    *,
    min_words: int | None = None,
    duration_seconds: int | float | None = None,
) -> tuple[bool, str]:
    """Return whether text is a plausible full-talk transcript and why."""
    if not text or not text.strip():
        return False, "transcript is empty"
    try:
        duration = normalize_duration(duration_seconds)
        word_floor = effective_min_words(
            min_words,
            trusted_duration_seconds=duration,
        )
    except ValueError as exc:
        return False, str(exc)

    head = text[:FAILURE_SCAN_CHARS]
    for signature in FAILURE_SIGNATURES:
        if signature in head:
            return False, (
                f"transcript begins with a Python error ({signature.rstrip(':')}) — "
                "this is a captured crash, not speech; re-fetch it"
            )

    if VTT_TIMING_TAG.search(text[:VTT_SCAN_CHARS]):
        return False, (
            "transcript is a raw VTT caption payload — it carries inline "
            "timing tags and duplicate caption text; clean it with "
            "vtt-cleanup.py before use"
        )
    marker_chars = sum(
        text.count(marker) * len(marker) for marker in NON_SPEECH_MARKERS
    )
    if marker_chars > len(text) * 0.5:
        return False, (
            "transcript is mostly non-speech markers ([Music]/[Applause]) — "
            "the caption track carries no usable speech; transcribe the audio"
        )
    words = count_words(text)
    if words < word_floor:
        return False, (
            f"transcript has {words} words, below the "
            f"{word_floor}-word floor — "
            "too short to be a talk; the fetch probably returned a stub"
        )
    if duration is not None:
        minutes = duration / 60.0
        words_per_minute = words / minutes
        if words_per_minute < MIN_WORDS_PER_MINUTE:
            return False, (
                f"transcript has {words} words for {minutes:.0f} minutes "
                f"({words_per_minute:.0f} wpm), below the "
                f"{MIN_WORDS_PER_MINUTE} wpm floor — it likely covers only "
                "part of the talk"
            )
    return True, f"{words} words"

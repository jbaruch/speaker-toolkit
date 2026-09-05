"""Fixed provider-boundary data, never a model call or a media acquisition."""

import copy
from pathlib import Path

import pytest
import numpy as np

from conftest import SCRIPTS_VI, _import_script


@pytest.fixture
def words():
    return _import_script(
        Path(SCRIPTS_VI) / "local_media_words.py", "local_media_words"
    )


def raw_result():
    return {
        "language": "en",
        "segments": [
            {
                "start": 0.0,
                "end": 3.0,
                "compression_ratio": 1.1,
                "avg_logprob": -0.1,
                "no_speech_prob": 0.01,
                "words": [
                    {"word": " First", "start": 0.5, "end": 1.0, "probability": 0.9},
                    {"word": " word.", "start": 1.5, "end": 2.0, "probability": 0.95},
                ],
            }
        ],
    }


def normalized(words, raw=None):
    return words.normalize_word_result(
        raw_result() if raw is None else raw,
        source_sha256="a" * 64,
        sample_sha256="b" * 64,
        source_duration_seconds=60,
        sample_start_seconds=20,
        sample_duration_seconds=3,
        provider_version="0.4.3",
        model=words.DEFAULT_WORD_MODEL,
        language_probability=0.99,
    )


def test_normalization_retains_actual_word_times_and_source_binding(words):
    result = normalized(words)
    assert result["words"] == [
        {
            "text": "First",
            "start_seconds": 0.5,
            "end_seconds": 1.0,
            "probability": 0.9,
            "segment_index": 0,
        },
        {
            "text": "word.",
            "start_seconds": 1.5,
            "end_seconds": 2.0,
            "probability": 0.95,
            "segment_index": 0,
        },
    ]
    assert result["source_sha256"] == "a" * 64
    assert result["sample_start_seconds"] == 20
    assert result["model"] == words.DEFAULT_WORD_MODEL
    assert result["language_probe_seconds"] == 3
    assert result["token_exclusions"] == []


def test_punctuation_only_token_is_reported_not_counted(words):
    raw = raw_result()
    raw["segments"][0]["words"].append(
        {"word": "…", "start": 2.0, "end": 2.0, "probability": 1.0}
    )
    result = normalized(words, raw)
    assert len(result["words"]) == 2
    assert result["token_exclusions"] == [
        {"token_index": 2, "reason": "punctuation_only"}
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("start", True),
        ("start", -1),
        ("end", 0.5),
        ("end", 7),
        ("probability", float("nan")),
        ("probability", 1.1),
        ("word", "two words"),
        ("word", "word\ud800"),
        ("word", "word\u0000"),
    ],
)
def test_invalid_lexical_word_is_not_repaired(words, field, value):
    raw = raw_result()
    raw["segments"][0]["words"][0][field] = value
    with pytest.raises(words.LocalMediaError, match="whisper_word_sample_invalid"):
        normalized(words, raw)


def test_segment_only_timing_cannot_become_word_evidence(words):
    raw = raw_result()
    del raw["segments"][0]["words"]
    with pytest.raises(words.LocalMediaError):
        normalized(words, raw)


def test_native_numeric_scalars_normalize_losslessly_at_provider_boundary(words):
    raw = raw_result()
    for segment in raw["segments"]:
        for key in (
            "start",
            "end",
            "compression_ratio",
            "avg_logprob",
            "no_speech_prob",
        ):
            segment[key] = np.float64(segment[key])
        for word in segment["words"]:
            for key in ("start", "end", "probability"):
                word[key] = np.float64(word[key])
    receipt = normalized(words, raw)
    assert receipt == normalized(words)
    assert all(
        type(word[key]) is float
        for word in receipt["words"]
        for key in ("start_seconds", "end_seconds", "probability")
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 1),
        ("schema_version", 3),
        ("source_sha256", "unknown"),
        ("language_probability", -0.1),
        ("sample_duration_seconds", 1201),
        ("sample_start_seconds", 59),
        ("provider_version", "latest"),
        ("words", []),
        ("segments", []),
    ],
)
def test_malformed_receipt_refuses(words, field, value):
    result = normalized(words)
    result[field] = value
    with pytest.raises(words.LocalMediaError):
        words.validate_word_sample(result)


def test_overlapping_words_and_words_disjoint_from_segments_refuse(words):
    result = normalized(words)
    result["words"][1]["start_seconds"] = 0.8
    with pytest.raises(words.LocalMediaError):
        words.validate_word_sample(result)
    result = normalized(words)
    result["segments"][0]["end_seconds"] = 1.5
    with pytest.raises(words.LocalMediaError):
        words.validate_word_sample(result)


@pytest.mark.parametrize(
    "defect,reason",
    [
        ("zero", "whisper_word_sample_invalid_word_nonpositive_span"),
        ("overlap", "whisper_word_sample_invalid_word_overlap"),
        ("outside", "whisper_word_sample_invalid_word_segment"),
    ],
)
def test_bad_alignment_diagnostics_do_not_disclose_words(words, defect, reason):
    result = normalized(words)
    if defect == "zero":
        result["words"][0]["end_seconds"] = result["words"][0]["start_seconds"]
    elif defect == "overlap":
        result["words"][1]["start_seconds"] = 0.8
    else:
        result["segments"][0]["end_seconds"] = 1.5
    with pytest.raises(words.LocalMediaError) as exc:
        words.validate_word_sample(result)
    assert exc.value.reason_code == reason
    assert "First" not in str(exc.value)


def test_model_revision_is_explicit_and_copy_is_independent(words):
    result = normalized(words)
    result["model"]["revision"] = "main"
    with pytest.raises(words.LocalMediaError):
        words.validate_word_sample(result)
    assert words.DEFAULT_WORD_MODEL["revision"] != "main"
    valid = normalized(words)
    before = copy.deepcopy(valid)
    assert words.validate_word_sample(valid) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("word_index", True),
        ("word_index", 2),
        ("word_count", 50001),
        ("word_start_seconds", -1),
        ("word_end_seconds", 1201),
        ("segment_count", 0),
        ("segment_index", 1),
        ("segment_end_seconds", "private"),
        ("schema_version", True),
        ("private_locator", "/private/source"),
    ],
)
def test_untrusted_diagnostics_refuse_instead_of_echoing_values(words, field, value):
    receipt = normalized(words)
    receipt["segments"][0]["end_seconds"] = 1.5
    with pytest.raises(words.WordSampleError) as exc:
        words.validate_word_sample(receipt)
    diagnostic = exc.value.word_timing
    diagnostic[field] = value
    with pytest.raises(words.LocalMediaError) as invalid:
        words.WordSampleError(diagnostic)
    assert "private" not in str(invalid.value)


@pytest.mark.parametrize("edge", ["start", "end"])
def test_native_boundary_straddling_keeps_exact_times_and_membership(words, edge):
    # Native MLX alignment may adjust a boundary word using its median duration
    # while retaining the segment timestamp. Neither time is a containment box.
    raw = raw_result()
    if edge == "start":
        raw["segments"][0]["start"] = 0.68
    else:
        raw["segments"][0]["end"] = 1.8
    receipt = normalized(words, raw)
    assert receipt["schema_version"] == 2
    assert receipt["words"] == normalized(words)["words"]
    assert receipt["segments"][0][f"{edge}_seconds"] == raw["segments"][0][edge]


@pytest.mark.parametrize("index", [True, -1, 1, 0.0, None])
def test_invalid_explicit_segment_membership_refuses(words, index):
    receipt = normalized(words)
    receipt["words"][0]["segment_index"] = index
    with pytest.raises(words.LocalMediaError):
        words.validate_word_sample(receipt)


def test_word_cannot_borrow_another_segments_quality_metadata(words):
    raw = raw_result()
    second = copy.deepcopy(raw["segments"][0])
    raw["segments"][0]["end"] = 1.0
    raw["segments"][0]["words"] = raw["segments"][0]["words"][:1]
    second["start"] = 1.0
    second["words"] = second["words"][1:]
    raw["segments"].append(second)
    receipt = normalized(words, raw)
    assert [word["segment_index"] for word in receipt["words"]] == [0, 1]
    receipt["words"][1]["segment_index"] = 0
    with pytest.raises(words.WordSampleError):
        words.validate_word_sample(receipt)

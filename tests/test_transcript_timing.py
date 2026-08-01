"""Tests for the transcript/timing artifact contract."""

import json

import pytest


def test_normalizes_caption_and_whisper_segment_shapes(transcript_timing):
    class Caption:
        text = "caption text"
        start = 1.25
        duration = 2.5

    assert transcript_timing.normalize_segments(
        [Caption(), {"text": "whisper text", "start": 4.0, "end": 6.0}]
    ) == [
        {"text": "caption text", "start_seconds": 1.25, "end_seconds": 3.75},
        {"text": "whisper text", "start_seconds": 4.0, "end_seconds": 6.0},
    ]


def test_normalization_rejects_nonfinite_and_zero_duration_segments(transcript_timing):
    assert transcript_timing.normalize_segments(
        [
            {"text": "zero", "start": 1.0, "end": 1.0},
            {"text": "nan", "start": float("nan"), "end": 2.0},
            {"text": "infinite", "start": 1.0, "end": float("inf")},
            {"text": "rounds to zero", "start": 1.0001, "end": 1.0002},
        ]
    ) == []


def test_bundle_rejects_an_unknown_source(transcript_timing, tmp_path):
    with pytest.raises(ValueError, match="unsupported transcript timing source"):
        transcript_timing.write_transcript_bundle(
            tmp_path / "talk.txt",
            "Real transcript text.",
            [{"text": "Real transcript text.", "start": 0.0, "end": 1.0}],
            source="model_guess",
        )


def test_bundle_hash_binds_sidecar_to_exact_transcript(transcript_timing, tmp_path):
    transcript = tmp_path / "talk.txt"
    timed = transcript_timing.write_transcript_bundle(
        transcript,
        "The opening claim.\nNow the explanation.",
        [
            {"text": "The opening claim.", "start": 2.0, "duration": 3.0},
            {"text": "Now the explanation.", "start": 5.0, "duration": 4.0},
        ],
        source="captions",
    )

    assert timed == tmp_path / "talk.segments.json"
    payload = json.loads(timed.read_text(encoding="utf-8"))
    assert payload["schema_version"] == transcript_timing.SIDECAR_SCHEMA_VERSION
    assert payload["source"] == "captions"
    segments, reason = transcript_timing.load_verified_segments(
        transcript, transcript.read_text(encoding="utf-8")
    )
    assert len(segments) == 2
    assert "verified timed segments" in reason

    transcript.write_text("A different transcript.", encoding="utf-8")
    segments, reason = transcript_timing.load_verified_segments(
        transcript, transcript.read_text(encoding="utf-8")
    )
    assert segments == []
    assert "does not match" in reason


def test_empty_timing_invalidates_an_older_sidecar(transcript_timing, tmp_path):
    transcript = tmp_path / "talk.txt"
    transcript_timing.write_transcript_bundle(
        transcript,
        "First version.",
        [{"text": "First version.", "start": 1.0, "end": 2.0}],
        source="captions",
    )
    timed = transcript_timing.write_transcript_bundle(
        transcript, "Replacement without timing.", [], source="whisper"
    )
    assert timed is None
    segments, reason = transcript_timing.load_verified_segments(
        transcript, transcript.read_text(encoding="utf-8")
    )
    assert segments == []
    assert "recorded no timed segments" in reason


def test_reader_rejects_a_partially_malformed_sidecar(transcript_timing, tmp_path):
    transcript = tmp_path / "talk.txt"
    text = "A real transcript."
    transcript.write_text(text, encoding="utf-8")
    sidecar = tmp_path / "talk.segments.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": transcript_timing.SIDECAR_SCHEMA_VERSION,
                "transcript_sha256": transcript_timing.transcript_sha256(text),
                "source": "captions",
                "segments": [
                    {"text": text, "start_seconds": 0.0, "end_seconds": 1.0},
                    {"text": "bad", "start_seconds": 2.0, "end_seconds": 2.0},
                ],
            }
        ),
        encoding="utf-8",
    )

    segments, reason = transcript_timing.load_verified_segments(transcript, text)
    assert segments == []
    assert "malformed or zero-duration" in reason


def test_resolves_unique_quote_to_engine_owned_lines_and_times(transcript_timing):
    transcript = "Welcome everyone.\nThe deploy went out on Friday.\nWe restored it by noon."
    resolved = transcript_timing.resolve_quote(
        transcript,
        "The deploy went out on Friday. We restored it by noon.",
        segments=[
            {"text": "Welcome everyone.", "start": 0.0, "end": 1.0},
            {"text": "The deploy went out on Friday.", "start": 1.0, "end": 4.0},
            {"text": "We restored it by noon.", "start": 4.0, "end": 6.5},
        ],
    )
    assert resolved == {
        "line_start": 2,
        "line_end": 3,
        "start_seconds": 1.0,
        "end_seconds": 6.5,
    }


def test_rejects_missing_or_ambiguous_quotes(transcript_timing):
    with pytest.raises(ValueError, match="does not appear verbatim"):
        transcript_timing.resolve_quote("A real sentence.", "An invented sentence.")
    with pytest.raises(ValueError, match="more than once"):
        transcript_timing.resolve_quote("same phrase\nsame phrase", "same phrase")

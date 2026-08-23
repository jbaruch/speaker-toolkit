"""Tests for the transcript/timing artifact contract."""

import json

import pytest

VIDEO_ID = "eg6gqvUFh6Q"
SOURCE_DURATION = 600.0


def _youtube_timing(transcript_timing, source="captions", duration=SOURCE_DURATION):
    return transcript_timing.youtube_timing_provenance(
        source,
        VIDEO_ID,
        duration,
    )


def _owner(source="captions", duration=SOURCE_DURATION):
    return {
        "owner_source": "youtube_auto" if source == "captions" else "whisper",
        "owner_video_id": VIDEO_ID,
        "owner_duration_seconds": duration,
    }


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
    assert (
        transcript_timing.normalize_segments(
            [
                {"text": "zero", "start": 1.0, "end": 1.0},
                {"text": "nan", "start": float("nan"), "end": 2.0},
                {"text": "infinite", "start": 1.0, "end": float("inf")},
                {"text": "rounds to zero", "start": 1.0001, "end": 1.0002},
            ]
        )
        == []
    )


def test_bundle_rejects_an_unknown_source(transcript_timing, tmp_path):
    with pytest.raises(ValueError, match="unsupported transcript timing source"):
        transcript_timing.write_transcript_bundle(
            tmp_path / "talk.txt",
            "Real transcript text.",
            [{"text": "Real transcript text.", "start": 0.0, "end": 1.0}],
            source="model_guess",
            timing_provenance={},
        )


@pytest.mark.parametrize("symlink_artifact", ["transcript", "timing", "quality"])
def test_bundle_rejects_destination_symlinks_including_dangling_entries(
    transcript_timing, tmp_path, symlink_artifact
):
    transcript = tmp_path / "talk.txt"
    destinations = {
        "transcript": transcript,
        "timing": transcript.with_suffix(".segments.json"),
        "quality": transcript.with_suffix(".quality.json"),
    }
    destination = destinations[symlink_artifact]
    target = tmp_path / f"outside-{symlink_artifact}"
    if symlink_artifact == "transcript":
        target.write_bytes(b"external transcript target")
    destination.symlink_to(target)
    target_before = target.read_bytes() if target.exists() else None

    with pytest.raises(ValueError, match="destination symlink"):
        transcript_timing.write_transcript_bundle(
            transcript,
            "Real transcript text.",
            [{"text": "Real transcript text.", "start": 0.0, "end": 1.0}],
            source="captions",
            timing_provenance=_youtube_timing(transcript_timing),
            quality_policy={
                "schema_version": 1,
                "min_words": 400,
                "duration_seconds": None,
            },
            quality_policy_provenance={"kind": "fixed_default"},
            force=True,
        )

    assert destination.is_symlink()
    if target_before is None:
        assert not target.exists()
    else:
        assert target.read_bytes() == target_before


@pytest.mark.parametrize("receipt_kind", ["timing", "quality"])
def test_direct_receipt_writers_reject_dangling_destination_symlinks(
    transcript_timing, tmp_path, receipt_kind
):
    transcript = tmp_path / "talk.txt"
    transcript.write_text("Real transcript text.", encoding="utf-8")
    destination = (
        transcript.with_suffix(".segments.json")
        if receipt_kind == "timing"
        else transcript.with_suffix(".quality.json")
    )
    outside = tmp_path / f"absent-{receipt_kind}"
    destination.symlink_to(outside)

    with pytest.raises(ValueError, match="destination symlink"):
        if receipt_kind == "timing":
            transcript_timing.write_timing_receipt(
                transcript,
                "Real transcript text.",
                [
                    {
                        "text": "Real transcript text.",
                        "start": 0.0,
                        "end": 1.0,
                    }
                ],
                source="captions",
                provenance=_youtube_timing(transcript_timing),
            )
        else:
            transcript_timing.write_quality_receipt(
                transcript,
                "Real transcript text.",
                {
                    "schema_version": 1,
                    "min_words": 400,
                    "duration_seconds": None,
                },
                {"kind": "fixed_default"},
            )

    assert destination.is_symlink()
    assert not outside.exists()


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
        timing_provenance=_youtube_timing(transcript_timing),
    )

    assert timed == tmp_path / "talk.segments.json"
    payload = json.loads(timed.read_text(encoding="utf-8"))
    assert payload["schema_version"] == transcript_timing.SIDECAR_SCHEMA_VERSION
    assert payload["source"] == "captions"
    segments, reason = transcript_timing.load_verified_segments(
        transcript, transcript.read_text(encoding="utf-8"), **_owner()
    )
    assert len(segments) == 2
    assert "verified owner-bound timed segments" in reason

    transcript.write_text("A different transcript.", encoding="utf-8")
    segments, reason = transcript_timing.load_verified_segments(
        transcript, transcript.read_text(encoding="utf-8"), **_owner()
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
        timing_provenance=_youtube_timing(transcript_timing),
    )
    timed = transcript_timing.write_transcript_bundle(
        transcript,
        "Replacement without timing.",
        [],
        source="whisper",
        timing_provenance=None,
        force=True,
    )
    assert timed is None
    segments, reason = transcript_timing.load_verified_segments(
        transcript, transcript.read_text(encoding="utf-8"), **_owner("whisper")
    )
    assert segments == []
    assert "sidecar is missing" in reason


def test_quality_receipt_is_independent_when_no_timing_exists(
    transcript_timing, tmp_path
):
    transcript = tmp_path / "talk.txt"
    text = " ".join(["synthetic"] * 500)
    timed = transcript_timing.write_transcript_bundle(
        transcript,
        text,
        [],
        source="captions",
        timing_provenance=None,
        quality_policy={
            "schema_version": 1,
            "min_words": 400,
            "duration_seconds": None,
        },
        quality_policy_provenance={"kind": "fixed_default"},
    )

    assert timed is None
    assert not transcript_timing.sidecar_path(transcript).exists()
    assert transcript_timing.quality_sidecar_path(transcript).exists()
    segments, timing_reason = transcript_timing.load_verified_segments(
        transcript,
        text,
        **_owner(),
    )
    policy, quality_reason = transcript_timing.load_verified_quality_policy(
        transcript,
        text,
    )
    assert segments == []
    assert "sidecar is missing" in timing_reason
    assert policy == {
        "schema_version": 1,
        "min_words": 400,
        "duration_seconds": None,
    }
    assert quality_reason == "verified transcript quality receipt"


def test_transcript_digest_drift_invalidates_timing_and_quality_receipts(
    transcript_timing, tmp_path
):
    transcript = tmp_path / "eg6gqvUFh6Q.txt"
    text = " ".join(["original"] * 500)
    transcript_timing.write_transcript_bundle(
        transcript,
        text,
        [{"text": text, "start": 0.0, "end": 180.0}],
        source="captions",
        timing_provenance=_youtube_timing(transcript_timing, duration=180.0),
        quality_policy={
            "schema_version": 1,
            "min_words": 90,
            "duration_seconds": 180.0,
        },
        quality_policy_provenance={
            "kind": "youtube_duration",
            "video_id": "eg6gqvUFh6Q",
            "duration_seconds": 180.0,
        },
    )

    replacement = " ".join(["replacement"] * 500)
    transcript.write_text(replacement, encoding="utf-8")

    segments, timing_reason = transcript_timing.load_verified_segments(
        transcript,
        replacement,
        **_owner(duration=180.0),
    )
    policy, quality_reason = transcript_timing.load_verified_quality_policy(
        transcript,
        replacement,
    )
    assert segments == []
    assert "does not match" in timing_reason
    assert policy is None
    assert "does not match" in quality_reason


def test_bundle_write_is_byte_exact_and_crlf_normalization_invalidates_receipts(
    transcript_timing, tmp_path
):
    transcript = tmp_path / "byte-exact.txt"
    text = "A byte exact first line with substantive speech.\r\n" + " ".join(
        ["evidence"] * 500
    )
    transcript_timing.write_transcript_bundle(
        transcript,
        text,
        [{"text": text, "start": 0.0, "end": 180.0}],
        source="captions",
        timing_provenance=_youtube_timing(transcript_timing),
        quality_policy={
            "schema_version": 1,
            "min_words": 400,
            "duration_seconds": None,
        },
        quality_policy_provenance={"kind": "fixed_default"},
    )

    assert transcript.read_bytes() == text.encode("utf-8")
    segments, timing_reason = transcript_timing.load_verified_segments(
        transcript, text, **_owner()
    )
    policy, quality_reason = transcript_timing.load_verified_quality_policy(
        transcript, text
    )
    assert segments
    assert "verified owner-bound timed segments" in timing_reason
    assert policy is not None
    assert quality_reason == "verified transcript quality receipt"

    transcript.write_bytes(text.encode("utf-8").replace(b"\r\n", b"\n"))
    segments, timing_reason = transcript_timing.load_verified_segments(
        transcript, text, **_owner()
    )
    policy, quality_reason = transcript_timing.load_verified_quality_policy(
        transcript, text
    )
    assert segments == []
    assert policy is None
    assert "does not match" in timing_reason
    assert "does not match" in quality_reason


def test_newline_byte_replacement_invalidates_both_receipts(
    transcript_timing, tmp_path
):
    transcript = tmp_path / "eg6gqvUFh6Q.txt"
    crlf_text = "first synthetic line\r\nsecond synthetic line\r\n"
    transcript_timing.write_transcript_bundle(
        transcript,
        crlf_text,
        [{"text": crlf_text, "start": 0.0, "end": 2.0}],
        source="captions",
        timing_provenance=_youtube_timing(transcript_timing),
        quality_policy={
            "schema_version": 1,
            "min_words": 400,
            "duration_seconds": None,
        },
        quality_policy_provenance={"kind": "fixed_default"},
    )
    assert transcript.read_bytes().endswith(b"\r\n")
    assert transcript_timing.load_verified_segments(transcript, crlf_text, **_owner())[
        0
    ]
    assert (
        transcript_timing.load_verified_quality_policy(
            transcript,
            crlf_text,
        )[0]
        is not None
    )

    lf_text = crlf_text.replace("\r\n", "\n")
    transcript.write_bytes(lf_text.encode("utf-8"))

    segments, timing_reason = transcript_timing.load_verified_segments(
        transcript,
        lf_text,
        **_owner(),
    )
    policy, quality_reason = transcript_timing.load_verified_quality_policy(
        transcript,
        lf_text,
    )
    assert segments == []
    assert "does not match" in timing_reason
    assert policy is None
    assert "does not match" in quality_reason


def test_quality_receipt_requires_exact_duration_provenance(
    transcript_timing, tmp_path
):
    transcript = tmp_path / "eg6gqvUFh6Q.txt"
    text = " ".join(["synthetic"] * 500)
    policy = {
        "schema_version": 1,
        "min_words": 90,
        "duration_seconds": 180.0,
    }

    with pytest.raises(ValueError, match="exactly match policy duration"):
        transcript_timing.write_quality_receipt(
            transcript,
            text,
            policy,
            {
                "kind": "youtube_duration",
                "video_id": "eg6gqvUFh6Q",
                "duration_seconds": 179.0,
            },
        )


def test_quality_receipt_rejects_a_noncanonical_low_floor(transcript_timing, tmp_path):
    with pytest.raises(ValueError, match="below the safe"):
        transcript_timing.write_quality_receipt(
            tmp_path / "talk.txt",
            "stub",
            {
                "schema_version": 1,
                "min_words": 1,
                "duration_seconds": None,
            },
            {"kind": "fixed_default"},
        )


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
                "provenance": _youtube_timing(transcript_timing),
                "segments": [
                    {"text": text, "start_seconds": 0.0, "end_seconds": 1.0},
                    {"text": "bad", "start_seconds": 2.0, "end_seconds": 2.0},
                ],
            }
        ),
        encoding="utf-8",
    )

    segments, reason = transcript_timing.load_verified_segments(
        transcript, text, **_owner()
    )
    assert segments == []
    assert "malformed or noncanonical" in reason


@pytest.mark.parametrize("failure_shape", ["missing", "directory", "invalid-json"])
def test_timing_reader_fails_closed_without_crashing(
    transcript_timing, tmp_path, failure_shape
):
    transcript = tmp_path / "eg6gqvUFh6Q.txt"
    transcript.write_text("A real transcript.", encoding="utf-8")
    sidecar = transcript_timing.sidecar_path(transcript)
    if failure_shape == "directory":
        sidecar.mkdir()
    elif failure_shape == "invalid-json":
        sidecar.write_text("{not-json", encoding="utf-8")

    segments, reason = transcript_timing.load_verified_segments(
        transcript, "A real transcript.", **_owner()
    )

    assert segments == []
    assert failure_shape.split("-")[0] in reason.casefold()


def test_legacy_minimal_sidecar_cannot_supply_source_or_timing(
    transcript_timing, tmp_path
):
    transcript = tmp_path / "eg6gqvUFh6Q.txt"
    text = "A real transcript."
    transcript.write_text(text, encoding="utf-8")
    transcript_timing.sidecar_path(transcript).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "transcript_sha256": transcript_timing.transcript_sha256(text),
                "source": "captions",
            }
        ),
        encoding="utf-8",
    )

    source, source_reason = transcript_timing.load_verified_transcript_source(
        transcript, text, **_owner()
    )
    segments, timing_reason = transcript_timing.load_verified_segments(
        transcript, text, **_owner()
    )

    assert source is None
    assert segments == []
    assert "exact receipt" in source_reason
    assert "exact receipt" in timing_reason


def test_caption_receipt_cannot_relabel_manual_owner(transcript_timing, tmp_path):
    transcript = tmp_path / "eg6gqvUFh6Q.txt"
    text = "A real transcript."
    transcript_timing.write_transcript_bundle(
        transcript,
        text,
        [{"text": text, "start": 0.0, "end": 1.0}],
        source="captions",
        timing_provenance=_youtube_timing(transcript_timing),
    )

    source, source_reason = transcript_timing.load_verified_transcript_source(
        transcript,
        text,
        owner_source="manual",
        owner_video_id=VIDEO_ID,
        owner_duration_seconds=SOURCE_DURATION,
    )
    segments, timing_reason = transcript_timing.load_verified_segments(
        transcript,
        text,
        owner_source="manual",
        owner_video_id=VIDEO_ID,
        owner_duration_seconds=SOURCE_DURATION,
    )

    assert source is None
    assert segments == []
    assert "cannot relabel" in source_reason
    assert "cannot relabel" in timing_reason


def test_timing_reader_rejects_segment_text_and_duration_mismatch(
    transcript_timing, tmp_path
):
    transcript = tmp_path / "eg6gqvUFh6Q.txt"
    text = "Canonical transcript text."
    transcript.write_text(text, encoding="utf-8")
    sidecar = transcript_timing.sidecar_path(transcript)
    base = {
        "schema_version": transcript_timing.SIDECAR_SCHEMA_VERSION,
        "transcript_sha256": transcript_timing.transcript_sha256(text),
        "source": "captions",
        "provenance": _youtube_timing(transcript_timing, duration=10.0),
    }
    sidecar.write_text(
        json.dumps(
            {
                **base,
                "segments": [
                    {
                        "text": "Different source words.",
                        "start_seconds": 0.0,
                        "end_seconds": 1.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    segments, text_reason = transcript_timing.load_verified_segments(
        transcript, text, **_owner(duration=10.0)
    )
    assert segments == []
    assert "does not equal" in text_reason

    sidecar.write_text(
        json.dumps(
            {
                **base,
                "segments": [
                    {
                        "text": text,
                        "start_seconds": 0.0,
                        "end_seconds": 12.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    segments, bound_reason = transcript_timing.load_verified_segments(
        transcript, text, **_owner(duration=10.0)
    )
    assert segments == []
    assert "duration bound" in bound_reason


def test_direct_timing_writer_remains_strict_on_semantic_mismatch(
    transcript_timing, tmp_path
):
    transcript = tmp_path / f"{VIDEO_ID}.txt"
    text = "Canonical transcript text."
    transcript.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="does not equal"):
        transcript_timing.write_timing_receipt(
            transcript,
            text,
            [
                {
                    "text": "Different optional segment text.",
                    "start_seconds": 0.0,
                    "end_seconds": 1.0,
                }
            ],
            source="captions",
            provenance=_youtube_timing(transcript_timing, duration=10.0),
        )

    assert not transcript_timing.sidecar_path(transcript).exists()


def test_youtube_and_local_timing_require_trusted_duration(transcript_timing):
    with pytest.raises(ValueError, match="trusted duration"):
        transcript_timing.youtube_timing_provenance("captions", VIDEO_ID, None)
    with pytest.raises(ValueError, match="trusted duration"):
        transcript_timing.local_media_timing_provenance("a" * 64, None)


def test_vtt_provenance_is_portable_and_rejects_unsafe_paths(
    transcript_timing, tmp_path
):
    transcript = tmp_path / "talk.txt"
    source = tmp_path / "talk.en.vtt"
    source.write_bytes(b"WEBVTT synthetic")
    provenance = transcript_timing.vtt_timing_provenance(
        transcript,
        source,
        transcript_timing.hashlib.sha256(source.read_bytes()).hexdigest(),
        4.0,
    )
    assert provenance["artifact_path"] == "talk.en.vtt"

    outside = tmp_path.parent / "outside.vtt"
    outside.write_bytes(b"outside")
    try:
        with pytest.raises(ValueError, match="inside the transcript directory"):
            transcript_timing.vtt_timing_provenance(
                transcript,
                outside,
                transcript_timing.hashlib.sha256(outside.read_bytes()).hexdigest(),
                4.0,
            )
    finally:
        outside.unlink()

    symlink = tmp_path / "linked.vtt"
    symlink.symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        transcript_timing.vtt_timing_provenance(
            transcript,
            symlink,
            transcript_timing.hashlib.sha256(source.read_bytes()).hexdigest(),
            4.0,
        )


def test_bundle_failure_rolls_back_exact_transcript_and_receipts(
    transcript_timing, tmp_path, monkeypatch
):
    transcript = tmp_path / "eg6gqvUFh6Q.txt"
    original = " ".join(["original"] * 500)
    replacement = " ".join(["replacement"] * 500)
    quality_policy = {
        "schema_version": 1,
        "min_words": 400,
        "duration_seconds": None,
    }
    transcript_timing.write_transcript_bundle(
        transcript,
        original,
        [{"text": original, "start": 0.0, "end": 180.0}],
        source="captions",
        timing_provenance=_youtube_timing(transcript_timing),
        quality_policy=quality_policy,
        quality_policy_provenance={"kind": "fixed_default"},
    )
    paths = [
        transcript,
        transcript_timing.sidecar_path(transcript),
        transcript_timing.quality_sidecar_path(transcript),
    ]
    before = {path: path.read_bytes() for path in paths}
    real_replace = transcript_timing.os.replace
    calls = 0

    def fail_final_commit(source, destination):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("synthetic transcript replacement failure")
        return real_replace(source, destination)

    monkeypatch.setattr(transcript_timing.os, "replace", fail_final_commit)
    with pytest.raises(OSError, match="synthetic transcript replacement failure"):
        transcript_timing.write_transcript_bundle(
            transcript,
            replacement,
            [{"text": replacement, "start": 0.0, "end": 180.0}],
            source="captions",
            timing_provenance=_youtube_timing(transcript_timing),
            quality_policy=quality_policy,
            quality_policy_provenance={"kind": "fixed_default"},
            force=True,
        )

    assert {path: path.read_bytes() for path in paths} == before
    assert not list(tmp_path.glob("*.partial"))


def test_resolves_unique_quote_to_engine_owned_lines_and_times(transcript_timing):
    transcript = (
        "Welcome everyone.\nThe deploy went out on Friday.\nWe restored it by noon."
    )
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


@pytest.mark.parametrize(
    "quote",
    [
        "cat is very nicely",
        "bobcat is very nice",
        "cat is very nice",
    ],
)
def test_quote_matching_rejects_spans_inside_larger_words(transcript_timing, quote):
    transcript = "The bobcat is very nicely trained today."

    with pytest.raises(ValueError, match="does not appear verbatim"):
        transcript_timing.resolve_quote(transcript, quote)


def test_quote_matching_preserves_unicode_and_punctuation_normalization(
    transcript_timing,
):
    resolved = transcript_timing.resolve_quote(
        "She said, \u201cCaf\u00e9 systems are production-ready.\u201d",
        'She said, "Caf\u00e9 systems are production-ready."',
    )

    assert resolved == {"line_start": 1, "line_end": 1}


def test_quote_matching_treats_underscores_as_word_characters(transcript_timing):
    with pytest.raises(ValueError, match="does not appear verbatim"):
        transcript_timing.resolve_quote(
            "prefix_exact four word quote_suffix",
            "exact four word quote",
        )


def test_quote_uniqueness_counts_only_boundary_valid_matches(transcript_timing):
    resolved = transcript_timing.resolve_quote(
        "A bobcat is very nice. A cat is very nice.",
        "cat is very nice",
    )

    assert resolved == {"line_start": 1, "line_end": 1}


def test_overlapping_caption_text_does_not_invalidate_line_location(
    transcript_timing,
):
    resolved = transcript_timing.resolve_quote(
        "This exact four word quote is unique.",
        "exact four word quote",
        segments=[
            {
                "text": "This exact four word quote",
                "start": 1.0,
                "end": 3.0,
            },
            {
                "text": "exact four word quote is unique",
                "start": 2.0,
                "end": 4.0,
            },
        ],
    )

    assert resolved == {"line_start": 1, "line_end": 1}


def test_a_session_block_caption_track_is_foreign(transcript_timing):
    """Kl6tLcQ5hGI: a 5.3-minute video served the venue's whole block."""
    segments = [{"text": "later talk", "start": 2990.0, "duration": 10.0}]
    assert transcript_timing.timing_extent_is_foreign(segments, 318.0) is True
    ratio = transcript_timing.timing_extent_overrun_ratio(segments, 318.0)
    assert round(ratio, 1) == 9.4


def test_a_cue_trailing_its_video_by_seconds_is_not_foreign(transcript_timing):
    """Rounding at the end of an hour-long talk must not throw it away."""
    segments = [{"text": "closing", "start": 3600.0, "duration": 3.0}]
    assert transcript_timing.timing_extent_is_foreign(segments, 3600.0) is False


def test_a_cue_landing_exactly_on_the_end_is_not_foreign(transcript_timing):
    segments = [{"text": "closing", "start": 300.0, "duration": 18.0}]
    assert transcript_timing.timing_extent_is_foreign(segments, 318.0) is False


def test_the_foreign_question_is_unanswerable_without_both_sides(
    transcript_timing,
):
    """No duration, no segments, or unreadable timing must not accuse anyone."""
    good = [{"text": "x", "start": 0.0, "duration": 1.0}]
    for segments, duration in (
        (good, None),
        (good, 0),
        (good, -1),
        (good, float("nan")),
        (good, True),
        (None, 318.0),
        ([], 318.0),
        ("not-segments", 318.0),
        ([{"text": "x"}], 318.0),
    ):
        assert transcript_timing.timing_extent_overrun_ratio(segments, duration) is None
        assert transcript_timing.timing_extent_is_foreign(segments, duration) is False

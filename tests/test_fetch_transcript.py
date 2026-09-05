"""Tests for fetch-transcript.py — the validation that keeps crashes out of the corpus.

Regression coverage for the defect that motivated the script: an inline fetch
heredoc wrote its own Python traceback to the transcript path when
`youtube-transcript-api` 1.0 removed `get_transcript`. Four vault transcripts
are that traceback and two are zero bytes; nothing noticed, and one talk was
marked `processed` off an empty file.

Every check here is on pure functions, so the whole failure surface is testable
in CI without a network, without YouTube, and without Apple-Silicon Whisper.
"""

import hashlib
from contextlib import contextmanager
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TRACEBACK_FIXTURE = """Traceback (most recent call last):
  File "<string>", line 4, in <module>
    transcript = YouTubeTranscriptApi.get_transcript('eg6gqvUFh6Q', languages=['en'])
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: type object 'YouTubeTranscriptApi' has no attribute 'get_transcript'
"""

MUSIC_FIXTURE = "\n".join(["[Music]", "[Applause]"] * 60 + ["then", "with them"])


def _talk(words=600, word="alpha"):
    return " ".join([word] * words)


def test_traceback_is_rejected(fetch_transcript):
    """The exact corpus defect: a crash report sitting where speech belongs."""
    ok, reason = fetch_transcript.validate_transcript(TRACEBACK_FIXTURE)
    assert not ok
    assert "Python error" in reason and "re-fetch" in reason


def test_traceback_padded_to_length_is_still_rejected(fetch_transcript):
    """Length alone cannot clear a crash — the signature check comes first."""
    ok, reason = fetch_transcript.validate_transcript(TRACEBACK_FIXTURE + _talk(800))
    assert not ok
    assert "Python error" in reason


@pytest.mark.parametrize("text", ["", "   \n  \t "])
def test_empty_is_rejected(fetch_transcript, text):
    ok, reason = fetch_transcript.validate_transcript(text)
    assert not ok
    assert "empty" in reason


def test_short_stub_is_rejected(fetch_transcript):
    ok, reason = fetch_transcript.validate_transcript(_talk(125))
    assert not ok
    assert "125 words" in reason


def test_low_minimum_without_trusted_duration_cannot_authorize_a_stub(
    fetch_transcript,
):
    policy = fetch_transcript.build_quality_policy(1)

    assert policy == {
        "schema_version": 1,
        "min_words": fetch_transcript.DEFAULT_MIN_WORDS,
        "duration_seconds": None,
    }
    ok, reason = fetch_transcript.validate_transcript(
        _talk(125),
        min_words=1,
    )
    assert not ok
    assert "400-word floor" in reason


def test_trusted_short_duration_derives_a_floor_that_low_minimum_cannot_bypass(
    fetch_transcript,
):
    policy = fetch_transcript.build_quality_policy(
        1,
        trusted_duration_seconds=180,
    )

    assert policy == {
        "schema_version": 1,
        "min_words": 90,
        "duration_seconds": 180.0,
    }
    assert (
        fetch_transcript.build_quality_policy(
            100,
            trusted_duration_seconds=180,
        )["min_words"]
        == 100
    )
    assert (
        fetch_transcript.validate_transcript(
            _talk(89),
            min_words=policy["min_words"],
            duration_seconds=policy["duration_seconds"],
        )[0]
        is False
    )
    assert (
        fetch_transcript.validate_transcript(
            _talk(90),
            min_words=policy["min_words"],
            duration_seconds=policy["duration_seconds"],
        )[0]
        is True
    )


def _raw_vtt(lines=200):
    """YouTube's karaoke caption payload: each line once tagged, once plain."""
    out = []
    for n in range(lines):
        stamp = f"00:00:{n // 60:02d}.{n % 60:03d}"
        out.append(
            f"so<{stamp}><c> before</c><{stamp}><c> we</c><{stamp}><c> start</c>"
        )
        out.append("so before we start")
    return "\n".join(out)


RAW_VTT_FIXTURE = _raw_vtt()


def test_raw_vtt_payload_is_rejected(fetch_transcript):
    """A raw VTT dump has MORE words than the cleaned text, so the length floor
    cannot catch it — 26 corpus transcripts sat in this shape reading 3.6x their
    true length, and a meetup talk read as an 18,543-word two-hour session."""
    ok, reason = fetch_transcript.validate_transcript(RAW_VTT_FIXTURE)
    assert not ok
    assert "raw VTT" in reason and "vtt-cleanup.py" in reason


def test_raw_vtt_is_caught_despite_passing_the_word_floor(fetch_transcript):
    """Guard the guard: prove the fixture is long enough to clear the floor."""
    stripped = fetch_transcript.VTT_TIMING_TAG.sub("", RAW_VTT_FIXTURE)
    assert fetch_transcript.count_words(stripped) > fetch_transcript.DEFAULT_MIN_WORDS
    assert fetch_transcript.validate_transcript(stripped)[0] is True


def test_mostly_non_speech_markers_is_rejected(fetch_transcript):
    """A caption track of [Music]/[Applause] parses fine and says nothing."""
    ok, reason = fetch_transcript.validate_transcript(MUSIC_FIXTURE, min_words=10)
    assert not ok
    assert "non-speech markers" in reason


def test_transcript_far_too_short_for_runtime_is_rejected(fetch_transcript):
    """A caption track that returned only its opening minute."""
    ok, reason = fetch_transcript.validate_transcript(
        _talk(500), duration_seconds=60 * 60
    )
    assert not ok
    assert "wpm" in reason


def test_caption_track_covering_more_than_the_recording_is_rejected(
    fetch_transcript,
):
    """The real shape: a 5-minute segment served the session block's captions.

    Reproduces Kl6tLcQ5hGI — 1568 words against a provider-probed 318s, which
    opened as the right talk and closed inside a different speaker's.
    """
    ok, reason = fetch_transcript.validate_transcript(_talk(1568), duration_seconds=318)
    assert not ok
    assert "wpm" in reason
    assert "ceiling" in reason


def test_a_fast_talker_is_not_mistaken_for_a_foreign_caption_track(
    fetch_transcript,
):
    """The ceiling catches a wrong recording, never a brisk delivery."""
    ok, _reason = fetch_transcript.validate_transcript(
        _talk(200 * 30), duration_seconds=30 * 60
    )
    assert ok


def test_the_observed_vault_word_rates_all_clear_the_ceiling(fetch_transcript):
    """Every genuine receipt in the vault sat at 110-132 wpm."""
    for words, seconds in ((2389, 18 * 60), (1067, 492), (6626, 53 * 60)):
        ok, reason = fetch_transcript.validate_transcript(
            _talk(words), duration_seconds=seconds
        )
        assert ok, reason


def test_receipt_whose_duration_cannot_hold_the_words_asks_for_a_probe(
    fetch_transcript,
):
    """The Kl6tLcQ5hGI receipt: 318s recorded, 1609 words on disk."""
    receipt = {"policy": {"duration_seconds": 318.0}}
    assert fetch_transcript.receipt_duration_cannot_hold(receipt, 1609) is True


def test_a_receipt_that_comfortably_holds_its_words_asks_for_nothing(
    fetch_transcript,
):
    receipt = {"policy": {"duration_seconds": 53 * 60}}
    assert fetch_transcript.receipt_duration_cannot_hold(receipt, 6626) is False


def test_an_absent_or_unusable_receipt_screens_nothing(fetch_transcript):
    """Screening must never manufacture a probe from a missing duration."""
    for receipt in (
        None,
        {},
        {"policy": {}},
        {"policy": {"duration_seconds": None}},
        {"policy": {"duration_seconds": 0}},
        {"policy": {"duration_seconds": -5}},
        {"policy": {"duration_seconds": True}},
        {"policy": {"duration_seconds": float("inf")}},
        {"policy": "not-an-object"},
    ):
        assert fetch_transcript.receipt_duration_cannot_hold(receipt, 99999) is False


def test_a_receipt_with_a_probed_duration_asks_to_be_reprobed(fetch_transcript):
    """Re-deriving without asking the provider would write the weaker receipt."""
    receipt = {"policy": {"duration_seconds": 318.0}}
    assert fetch_transcript.receipt_claims_source_duration(receipt) is True


def test_a_receipt_without_a_duration_claims_nothing(fetch_transcript):
    for receipt in (
        None,
        {},
        {"policy": {}},
        {"policy": {"duration_seconds": None}},
        {"policy": "not-an-object"},
    ):
        assert fetch_transcript.receipt_claims_source_duration(receipt) is False


def test_a_receipt_for_these_exact_media_bytes_is_preservable(fetch_transcript):
    receipt = {"provenance": {"media_sha256": "a" * 64}}
    assert fetch_transcript.receipt_matches_media_digest(receipt, "a" * 64) is True


def test_a_receipt_for_other_media_is_stale_not_strong(fetch_transcript):
    """Preserving it would pin a duration to bytes nobody is reading."""
    receipt = {"provenance": {"media_sha256": "a" * 64}}
    assert fetch_transcript.receipt_matches_media_digest(receipt, "b" * 64) is False


def test_a_receipt_with_no_media_digest_never_matches(fetch_transcript):
    """The YouTube provenance forms answer a different question."""
    for receipt in (
        None,
        {},
        {"provenance": {}},
        {"provenance": {"video_id": "Kl6tLcQ5hGI"}},
        {"provenance": {"media_sha256": None}},
        {"provenance": "not-an-object"},
    ):
        assert fetch_transcript.receipt_matches_media_digest(receipt, "a" * 64) is False
    assert (
        fetch_transcript.receipt_matches_media_digest(
            {"provenance": {"media_sha256": "a" * 64}}, None
        )
        is False
    )


def _mock_media_probe(fetch_transcript, monkeypatch, path, duration=600.0):
    """Supply trusted synthetic facts; real worker admission has its own suite."""
    from artifact_supervisor import DiagnosticReceipt, FileGeneration

    probe = fetch_transcript.MediaArtifactProbe(
        generation=FileGeneration.from_stat(path.lstat()),
        root_generation=None,
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_size_bytes=path.stat().st_size,
        duration_seconds=duration,
        duration_source="format",
        container_family="iso_bmff",
        stream_count=2,
        video_stream_count=1,
        audio_stream_count=1,
        attached_picture_count=0,
        other_stream_count=0,
        parser_diagnostics=DiagnosticReceipt.empty(),
    )
    monkeypatch.setattr(fetch_transcript, "probe_local_media", lambda *a, **kw: probe)
    return probe


def test_whisper_download_reuses_the_bound_probe_and_cleans_before_return(
    fetch_transcript,
    monkeypatch,
    tmp_path,
):
    media = tmp_path / "audio.mp4"
    media.write_bytes(b"synthetic audio")
    probe = _mock_media_probe(fetch_transcript, monkeypatch, media)
    seen = []

    @contextmanager
    def downloaded(video_id, *, ytdlp):
        seen.append((video_id, ytdlp))
        try:
            yield media, 600.0
        finally:
            seen.append("cleaned")

    def transcribed(path, model, *, probe, trusted_root):
        assert path == media
        assert trusted_root == media.parent
        assert probe.source_sha256 == hashlib.sha256(b"synthetic audio").hexdigest()
        return probe, {"text": "spoken words", "language": "en", "segments": None}

    monkeypatch.setattr(fetch_transcript, "download_youtube_audio", downloaded)
    monkeypatch.setattr(fetch_transcript, "transcribe_local_media", transcribed)
    executable = tmp_path / "yt-dlp"
    result = fetch_transcript.fetch_whisper(
        "Kl6tLcQ5hGI", str(tmp_path), "tiny", ytdlp=executable
    )
    assert tuple(result) == ("spoken words", "en", None)
    assert result.duration_seconds == probe.duration_seconds
    assert seen == [("Kl6tLcQ5hGI", executable), "cleaned"]


def test_whisper_download_duration_must_match_probed_media(
    fetch_transcript,
    monkeypatch,
    tmp_path,
):
    media = tmp_path / "audio.mp4"
    media.write_bytes(b"synthetic audio")
    _mock_media_probe(fetch_transcript, monkeypatch, media)

    @contextmanager
    def downloaded(*args, **kwargs):
        yield media, 900.0

    monkeypatch.setattr(fetch_transcript, "download_youtube_audio", downloaded)
    monkeypatch.setattr(
        fetch_transcript,
        "transcribe_local_media",
        lambda *a, **kw: pytest.fail("mismatched source was transcribed"),
    )
    with pytest.raises(
        fetch_transcript.LocalMediaError, match="ytdlp_media_duration_mismatch"
    ):
        fetch_transcript.fetch_whisper("Kl6tLcQ5hGI", str(tmp_path), "tiny")


def test_whisper_download_refusal_stops_before_transcription(
    fetch_transcript,
    monkeypatch,
    tmp_path,
):
    @contextmanager
    def refused(*args, **kwargs):
        raise fetch_transcript.LocalMediaError("ytdlp_provider_rejected")
        yield  # pragma: no cover - context manager protocol

    monkeypatch.setattr(fetch_transcript, "download_youtube_audio", refused)
    monkeypatch.setattr(
        fetch_transcript,
        "transcribe_local_media",
        lambda *a, **kw: pytest.fail("refused download was transcribed"),
    )
    with pytest.raises(
        fetch_transcript.LocalMediaError, match="ytdlp_provider_rejected"
    ):
        fetch_transcript.fetch_whisper("Kl6tLcQ5hGI", str(tmp_path), "tiny")


def test_plausible_transcript_passes(fetch_transcript):
    ok, reason = fetch_transcript.validate_transcript(
        _talk(7000), duration_seconds=50 * 60
    )
    assert ok
    assert "7000 words" in reason


def test_cyrillic_words_are_counted(fetch_transcript):
    """A Russian talk must not read as empty — `[a-z]` would count zero words."""
    russian = " ".join(["получается"] * 600)
    assert fetch_transcript.count_words(russian) == 600
    ok, _ = fetch_transcript.validate_transcript(russian)
    assert ok


@pytest.mark.parametrize(
    "value,expected",
    [
        ("eg6gqvUFh6Q", "eg6gqvUFh6Q"),
        ("https://www.youtube.com/watch?v=eg6gqvUFh6Q", "eg6gqvUFh6Q"),
        ("https://youtu.be/wb2C2ju_xRg", "wb2C2ju_xRg"),
        ("https://www.youtube.com/embed/0MGvxG-sc6g", "0MGvxG-sc6g"),
        ("https://www.youtube.com/watch?v=OeTtYIjcxpc&t=42s", "OeTtYIjcxpc"),
    ],
)
def test_video_id_resolution(fetch_transcript, value, expected):
    assert fetch_transcript.resolve_video_id(value) == expected


def test_video_id_resolution_rejects_a_non_url(fetch_transcript):
    assert (
        fetch_transcript.resolve_video_id("https://www.infoq.com/presentations/x")
        is None
    )


def test_segments_accepts_both_library_shapes(fetch_transcript):
    """Pinning to one shape is exactly what broke the previous fetch."""

    class Segment:
        def __init__(self, text):
            self.text = text

    assert (
        fetch_transcript.segments_to_text([{"text": "hello"}, {"text": "world"}])
        == "hello\nworld"
    )
    assert (
        fetch_transcript.segments_to_text([Segment("hello"), Segment("world")])
        == "hello\nworld"
    )


def test_caption_errors_fall_through_instead_of_propagating(
    fetch_transcript, monkeypatch
):
    """A video with captions disabled must return None, never raise.

    This is the original defect's exact shape one layer up: the first cut of
    this script let `TranscriptsDisabled` propagate, so a talk with no caption
    track crashed the fetcher instead of falling back to Whisper — and a
    crashing fetcher is what wrote tracebacks into the corpus.
    """
    from youtube_transcript_api import TranscriptsDisabled, YouTubeTranscriptApi

    def boom(self, *args, **kwargs):
        raise TranscriptsDisabled("eg6gqvUFh6Q")

    monkeypatch.setattr(YouTubeTranscriptApi, "fetch", boom, raising=False)
    assert fetch_transcript.fetch_captions("eg6gqvUFh6Q", ["en"]) == (
        None,
        None,
        None,
    )


def test_a_one_shot_caption_track_is_materialized_by_the_lane(
    fetch_transcript, monkeypatch
):
    """Text and segments must be the same data, both readable.

    `segments_to_text` consumes the track. Returning the consumed iterable
    would hand the caller an empty one, and materializing later — outside this
    lane — would put the consumption beyond the caller's expected-error
    boundary.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    cues = [
        {"text": "first cue", "start": 0.0, "duration": 2.0},
        {"text": "second cue", "start": 2.0, "duration": 2.0},
    ]

    def one_shot(self, *_args, **_kwargs):
        return (cue for cue in cues)

    monkeypatch.setattr(YouTubeTranscriptApi, "fetch", one_shot, raising=False)

    text, _language, segments = fetch_transcript.fetch_captions("eg6gqvUFh6Q", ["en"])

    assert text and "first cue" in text and "second cue" in text
    assert isinstance(segments, list)
    assert len(list(segments)) == 2, "the segments must survive a second read"
    assert len(list(segments)) == 2


def test_a_caption_track_raising_mid_read_degrades_to_the_next_lane(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    """Consumption happens inside the lane, so a failure is not fatal.

    Materialized outside the caller's expected-error boundary, this exception
    would reach the process boundary and end the run instead of recording a
    caption-lane failure and trying Whisper.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    def exploding(self, *_args, **_kwargs):
        def cues():
            yield {"text": "first cue", "start": 0.0, "duration": 2.0}
            raise ValueError("synthetic mid-read caption failure")

        return cues()

    monkeypatch.setattr(YouTubeTranscriptApi, "fetch", exploding, raising=False)
    whisper_text = _talk(800)
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _v: (318.0, "trusted synthetic duration"),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_whisper",
        lambda *_a, **_k: (whisper_text, "en", None),
    )
    out = tmp_path / "eg6gqvUFh6Q.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["eg6gqvUFh6Q", "--out", str(out)])

    assert exited.value.code == 0
    assert json.loads(capsys.readouterr().out)["method"] == "whisper"


def test_broken_caption_constructor_degrades_only_caption_lane(
    fetch_transcript, monkeypatch
):
    import youtube_transcript_api

    def broken_constructor():
        raise RuntimeError("synthetic optional dependency breakage")

    monkeypatch.setattr(
        youtube_transcript_api,
        "YouTubeTranscriptApi",
        broken_constructor,
    )

    assert fetch_transcript.fetch_captions("eg6gqvUFh6Q", ["en"]) == (
        None,
        None,
        None,
    )


def test_direct_caption_call_propagates_an_unisolated_import_failure(
    fetch_transcript, monkeypatch
):
    import builtins

    real_import = builtins.__import__

    def broken_optional_import(name, *args, **kwargs):
        if name == "youtube_transcript_api":
            raise ValueError("synthetic import-time package failure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_optional_import)

    with pytest.raises(ValueError, match="synthetic import-time package failure"):
        fetch_transcript.fetch_captions("eg6gqvUFh6Q", ["en"])


@pytest.mark.parametrize("failure_point", ["constructor", "api"])
def test_enumerated_caption_failure_falls_through_to_whisper_and_one_json(
    fetch_transcript, monkeypatch, tmp_path, capsys, failure_point
):
    import youtube_transcript_api

    if failure_point == "constructor":

        def broken_constructor():
            raise KeyError("synthetic constructor failure")

        monkeypatch.setattr(
            youtube_transcript_api,
            "YouTubeTranscriptApi",
            broken_constructor,
        )
    else:

        def broken_api(self, *args, **kwargs):
            raise KeyError("synthetic provider result failure")

        monkeypatch.setattr(
            youtube_transcript_api.YouTubeTranscriptApi,
            "fetch",
            broken_api,
            raising=False,
        )

    text = _talk(600)
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _video_id: (600.0, "trusted synthetic duration"),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_whisper",
        lambda *_args: (
            text,
            "en",
            [{"text": text, "start": 0.0, "end": 600.0}],
        ),
    )
    out = tmp_path / "eg6gqvUFh6Q.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["eg6gqvUFh6Q", "--out", str(out)])

    assert exited.value.code == 0
    captured = capsys.readouterr()
    stdout_lines = captured.out.splitlines()
    assert len(stdout_lines) == 1
    payload = json.loads(stdout_lines[0])
    assert payload["ok"] is True
    assert payload["method"] == "whisper"
    assert payload["timed_path"] == str(out.with_suffix(".segments.json"))
    assert out.read_text(encoding="utf-8") == text


def test_provider_stdout_is_quarantined_from_the_one_json_contract(
    fetch_transcript, monkeypatch, tmp_path, capfd
):
    text = _talk(600)

    def noisy_captions(_video_id, _languages):
        print("synthetic provider chatter")
        os.write(1, b"synthetic native provider chatter\n")
        return text, "en", [{"text": text, "start": 0.0, "end": 600.0}]

    monkeypatch.setattr(fetch_transcript, "fetch_captions", noisy_captions)
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _video_id: (600.0, "trusted synthetic duration"),
    )
    out = tmp_path / "eg6gqvUFh6Q.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["eg6gqvUFh6Q", "--out", str(out)])

    assert exited.value.code == 0
    captured = capfd.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert json.loads(captured.out)["ok"] is True
    assert "synthetic provider chatter" in captured.err
    assert "synthetic native provider chatter" in captured.err


def test_unenumerated_provider_exception_reaches_the_process_boundary(
    fetch_transcript,
):
    class ProviderContractChanged(Exception):
        pass

    def changed_provider():
        raise ProviderContractChanged("new provider failure shape")

    with pytest.raises(ProviderContractChanged, match="new provider failure shape"):
        fetch_transcript.run_optional_lane(
            "synthetic provider",
            changed_provider,
            expected_errors=(ValueError,),
        )


def test_direct_whisper_call_uses_the_bounded_owner(
    fetch_transcript,
    monkeypatch,
    tmp_path,
):
    audio = tmp_path / "audio.mp4"
    audio.write_bytes(b"synthetic")
    probe = _mock_media_probe(fetch_transcript, monkeypatch, audio)
    calls = []

    def transcribed(path, model, **kwargs):
        calls.append((path, model, kwargs["probe"]))
        return probe, {"text": "spoken words", "language": "en", "segments": None}

    monkeypatch.setattr(fetch_transcript, "transcribe_local_media", transcribed)
    assert fetch_transcript.transcribe_audio(
        audio, "local-talk", "model", probe=probe
    ) == ("spoken words", "en", None)
    assert calls == [(audio, "model", probe)]


def test_direct_whisper_call_preserves_a_typed_provider_failure(
    fetch_transcript,
    monkeypatch,
    tmp_path,
):
    def failed(*args, **kwargs):
        raise fetch_transcript.LocalMediaError("whisper_provider_failed")

    monkeypatch.setattr(fetch_transcript, "transcribe_local_media", failed)
    with pytest.raises(
        fetch_transcript.LocalMediaError, match="whisper_provider_failed"
    ):
        fetch_transcript.transcribe_audio(tmp_path / "audio.mp3", "local-talk", "model")


def test_captions_report_the_track_language(fetch_transcript, monkeypatch):
    """`delivery_language` derives from this, so the TRACK's language is what counts.

    It differs from the first requested preference whenever that language has no
    track and the API falls back — returning the request would silently mislabel
    every such talk.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    class Segment:
        def __init__(self, text, start=1.0, duration=2.0):
            self.text = text
            self.start = start
            self.duration = duration

    class Fetched(list):
        language_code = "ru"

    monkeypatch.setattr(
        YouTubeTranscriptApi,
        "fetch",
        lambda self, *a, **k: Fetched([Segment("привет")]),
        raising=False,
    )
    text, language, segments = fetch_transcript.fetch_captions("x", ["en", "ru"])
    assert text == "привет"
    assert language == "ru"
    assert segments[0].start == 1.0


def test_youtube_duration_probe_is_bound_to_the_exact_video_id(
    fetch_transcript,
    monkeypatch,
    tmp_path,
):
    seen = []

    def bounded(video_id, *, ytdlp):
        seen.append((video_id, ytdlp))
        return 179.625

    monkeypatch.setattr(fetch_transcript, "probe_youtube_media_duration", bounded)
    executable = tmp_path / "yt-dlp"
    duration, reason = fetch_transcript.probe_youtube_duration(
        "eg6gqvUFh6Q", ytdlp=executable
    )
    assert duration == 179.625
    assert "bounded yt-dlp duration" in reason
    assert seen == [("eg6gqvUFh6Q", executable)]
    assert fetch_transcript.youtube_quality_provenance("eg6gqvUFh6Q", duration) == {
        "kind": "youtube_duration",
        "video_id": "eg6gqvUFh6Q",
        "duration_seconds": 179.625,
    }


def test_youtube_duration_probe_rejects_provider_identity_drift(
    fetch_transcript, monkeypatch
):
    def rejected(*args, **kwargs):
        raise fetch_transcript.LocalMediaError("ytdlp_identity_mismatch")

    monkeypatch.setattr(fetch_transcript, "probe_youtube_media_duration", rejected)
    duration, reason = fetch_transcript.probe_youtube_duration("eg6gqvUFh6Q")
    assert duration is None
    assert "ytdlp_identity_mismatch" in reason


def test_local_duration_provenance_uses_established_exact_media_facts(
    fetch_transcript, monkeypatch, tmp_path
):
    media = tmp_path / "recording.mp4"
    media.write_bytes(b"synthetic local media bytes")
    probe = _mock_media_probe(fetch_transcript, monkeypatch, media, duration=61.25)
    source = fetch_transcript.AssessedMediaSource(media, probe)
    assert fetch_transcript.local_media_quality_provenance(
        source.sha256, probe.duration_seconds
    ) == {
        "kind": "local_media_duration",
        "media_sha256": "2d252575385bde1cab2b5ee3f23e77129478a0412fef2ddecd53a07b650b9e14",
        "duration_seconds": 61.25,
    }


def _existing_local_audio_bundle(fetch_transcript, tmp_path, receipt_digest):
    """An on-disk transcript plus a local-media receipt naming `receipt_digest`."""
    media = tmp_path / "recording.mp4"
    media.write_bytes(b"stable local media bytes")
    out = tmp_path / "local-talk.txt"
    text = _talk(600)
    out.write_text(text, encoding="utf-8")
    policy = fetch_transcript.build_quality_policy(None, trusted_duration_seconds=600.0)
    out.with_suffix(".quality.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "transcript_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "policy": policy,
                "provenance": {
                    "kind": "local_media_duration",
                    "media_sha256": receipt_digest,
                    "duration_seconds": 600.0,
                },
            }
        ),
        encoding="utf-8",
    )
    return media, out


@pytest.mark.parametrize(
    "stored_digest",
    [
        hashlib.sha256(b"stable local media bytes").hexdigest(),
        "f" * 64,
    ],
)
def test_failed_local_probe_preserves_every_receipt_without_fallback_relabeling(
    fetch_transcript,
    monkeypatch,
    tmp_path,
    capsys,
    stored_digest,
):
    media, out = _existing_local_audio_bundle(fetch_transcript, tmp_path, stored_digest)
    timing = out.with_suffix(".segments.json")
    timing.write_bytes(b"existing timing")
    paths = [out, out.with_suffix(".quality.json"), timing]
    before = {path: path.read_bytes() for path in paths}

    def unavailable(*args, **kwargs):
        raise fetch_transcript.LocalMediaError("media_dependency_unavailable")

    monkeypatch.setattr(fetch_transcript, "probe_local_media", unavailable)
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["local-talk", "--audio", str(media), "--out", str(out)])
    assert exited.value.code == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert {path: path.read_bytes() for path in paths} == before


def test_a_foreign_caption_track_falls_through_to_whisper(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    """The Kl6tLcQ5hGI shape, handled end to end.

    A 318-second video served a caption track whose cues run to 3000 seconds.
    That track must not become the transcript, and rejecting it must hand the
    talk to Whisper rather than leaving it with nothing.
    """
    caption_text = _talk(1600)
    whisper_text = _talk(800)
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _v: (318.0, "trusted synthetic duration"),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_captions",
        lambda *_a, **_k: (
            caption_text,
            "en",
            [{"text": "a later talk", "start": 2990.0, "duration": 10.0}],
        ),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_whisper",
        lambda *_a, **_k: (whisper_text, "en", None),
    )
    out = tmp_path / "Kl6tLcQ5hGI.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["Kl6tLcQ5hGI", "--out", str(out)])

    assert exited.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["method"] == "whisper"
    assert out.read_text(encoding="utf-8") == whisper_text, (
        "the session-block caption track must never reach the corpus"
    )


def test_a_one_shot_segment_iterable_does_not_bypass_the_guard(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    """A generator must not disable the check by being read twice.

    The extent check reads the segments and the timing bundle reads them
    again. If the lane hands back a one-shot iterable and nothing materializes
    it, the second reader gets an exhausted iterator and the guard silently
    passes a foreign track.
    """
    caption_text = _talk(1600)
    whisper_text = _talk(800)
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _v: (318.0, "trusted synthetic duration"),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_captions",
        lambda *_a, **_k: (
            caption_text,
            "en",
            (s for s in [{"text": "a later talk", "start": 2990.0, "duration": 10.0}]),
        ),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_whisper",
        lambda *_a, **_k: (whisper_text, "en", None),
    )
    out = tmp_path / "Kl6tLcQ5hGI.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["Kl6tLcQ5hGI", "--out", str(out)])

    assert exited.value.code == 0
    assert json.loads(capsys.readouterr().out)["method"] == "whisper"
    assert out.read_text(encoding="utf-8") == whisper_text


def test_overlong_whisper_timestamps_do_not_discard_the_transcript(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    """Whisper cannot be a foreign track — it transcribed the audio in hand.

    Its timestamps are merely sometimes sloppy. Applying the caption guard to
    the final fallback would leave a talk with nothing despite having valid
    transcript text.
    """
    whisper_text = _talk(800)
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _v: (318.0, "trusted synthetic duration"),
    )
    monkeypatch.setattr(
        fetch_transcript, "fetch_captions", lambda *_a, **_k: (None, None, None)
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_whisper",
        lambda *_a, **_k: (
            whisper_text,
            "en",
            [{"text": "drifted cue", "start": 2990.0, "duration": 10.0}],
        ),
    )
    out = tmp_path / "Kl6tLcQ5hGI.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["Kl6tLcQ5hGI", "--out", str(out)])

    assert exited.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["method"] == "whisper"
    assert out.read_text(encoding="utf-8") == whisper_text


def test_a_caption_track_within_its_recording_is_kept(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    """The guard must not push ordinary captions into the Whisper lane."""
    caption_text = _talk(800)
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _v: (318.0, "trusted synthetic duration"),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_captions",
        lambda *_a, **_k: (
            caption_text,
            "en",
            [{"text": "closing", "start": 300.0, "duration": 18.0}],
        ),
    )

    def unreachable(*_a, **_k):  # pragma: no cover - asserted by not running
        raise AssertionError("a sound caption track must not reach Whisper")

    monkeypatch.setattr(fetch_transcript, "fetch_whisper", unreachable)
    out = tmp_path / "Kl6tLcQ5hGI.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["Kl6tLcQ5hGI", "--out", str(out)])

    assert exited.value.code == 0
    assert json.loads(capsys.readouterr().out)["method"] == "captions"


def test_local_audio_transcription_and_receipts_reuse_one_assessment(
    fetch_transcript,
    monkeypatch,
    tmp_path,
    capsys,
):
    media = tmp_path / "recording.mp4"
    media.write_bytes(b"stable local media bytes")
    probe = _mock_media_probe(fetch_transcript, monkeypatch, media)
    text = _talk(600)
    seen = []

    def transcribe(path, _label, _model, *, probe):
        seen.append((path, probe))
        return text, "en", [{"text": text, "start": 0.0, "end": 600.0}]

    monkeypatch.setattr(fetch_transcript, "transcribe_audio", transcribe)
    out = tmp_path / "local-talk.txt"
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["local-talk", "--audio", str(media), "--out", str(out)])
    assert exited.value.code == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert seen == [(media, probe)]
    for suffix in (".quality.json", ".segments.json"):
        receipt = json.loads(out.with_suffix(suffix).read_text())
        assert receipt["provenance"]["media_sha256"] == probe.source_sha256
        assert receipt["provenance"]["duration_seconds"] == 600.0


@pytest.mark.parametrize("phase", ["after_probe", "transcription", "bundle_staging"])
def test_local_media_generation_changes_preserve_the_entire_prior_bundle(
    fetch_transcript,
    transcript_timing,
    monkeypatch,
    tmp_path,
    capsys,
    phase,
):
    media = tmp_path / "recording.mp4"
    media.write_bytes(b"stable local media bytes")
    probe = _mock_media_probe(fetch_transcript, monkeypatch, media)
    text = _talk(600)
    out = tmp_path / "local-talk.txt"
    paths = [out, out.with_suffix(".quality.json"), out.with_suffix(".segments.json")]
    for path in paths:
        path.write_bytes(b"prior " + path.suffix.encode())
    before = {path: path.read_bytes() for path in paths}

    def mutate():
        media.write_bytes(b"changed source bytes")

    if phase == "after_probe":

        def changed_probe(*args, **kwargs):
            mutate()
            return probe

        monkeypatch.setattr(fetch_transcript, "probe_local_media", changed_probe)

    def transcribe(path, _label, _model, **kwargs):
        if phase == "transcription":
            mutate()
        return text, "en", [{"text": text, "start": 0.0, "end": 600.0}]

    monkeypatch.setattr(fetch_transcript, "transcribe_audio", transcribe)
    if phase == "bundle_staging":
        stage = transcript_timing._stage_bytes

        def changed_during_stage(*args, **kwargs):
            result = stage(*args, **kwargs)
            mutate()
            return result

        monkeypatch.setattr(transcript_timing, "_stage_bytes", changed_during_stage)
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            ["local-talk", "--audio", str(media), "--out", str(out), "--force"]
        )
    assert exited.value.code == 2
    assert "media_generation_changed" in json.loads(capsys.readouterr().out)["reason"]
    assert {path: path.read_bytes() for path in paths} == before
    assert not list(tmp_path.glob("*.partial"))


def test_local_audio_source_replacement_during_transcription_fails_closed(
    fetch_transcript,
    monkeypatch,
    tmp_path,
    capsys,
):
    media = tmp_path / "recording.mp4"
    media.write_bytes(b"stable local media bytes")
    _mock_media_probe(fetch_transcript, monkeypatch, media)
    text = _talk(600)

    def replace_source(*args, **kwargs):
        replacement = tmp_path / "replacement.mp4"
        replacement.write_bytes(b"different media bytes")
        os.replace(replacement, media)
        return text, "en", [{"text": text, "start": 0, "end": 600}]

    monkeypatch.setattr(fetch_transcript, "transcribe_audio", replace_source)
    out = tmp_path / "local-talk.txt"
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["local-talk", "--audio", str(media), "--out", str(out)])
    assert exited.value.code == 2
    assert "media_generation_changed" in json.loads(capsys.readouterr().out)["reason"]
    assert not any(
        path.exists()
        for path in [
            out,
            out.with_suffix(".quality.json"),
            out.with_suffix(".segments.json"),
        ]
    )


def test_expected_duration_must_match_source_probe(fetch_transcript):
    assert fetch_transcript.duration_matches_expected(180, 179.625) is True
    assert fetch_transcript.duration_matches_expected(60, 179.625) is False


@pytest.mark.parametrize("change", ["source", "transcript"])
def test_existing_local_quality_refresh_rechecks_after_staging(
    fetch_transcript,
    transcript_timing,
    monkeypatch,
    tmp_path,
    capsys,
    change,
):
    media, out = _existing_local_audio_bundle(fetch_transcript, tmp_path, "f" * 64)
    _mock_media_probe(fetch_transcript, monkeypatch, media)
    quality, timing = (
        out.with_suffix(".quality.json"),
        out.with_suffix(".segments.json"),
    )
    timing.write_bytes(b"prior timing")
    before = {path: path.read_bytes() for path in (out, quality, timing)}
    original_stage = transcript_timing._stage_bytes

    def stage(*args, **kwargs):
        result = original_stage(*args, **kwargs)
        if change == "source":
            media.write_bytes(b"replaced source")
        else:
            out.write_bytes(b"new user transcript")
        return result

    monkeypatch.setattr(transcript_timing, "_stage_bytes", stage)
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["local-talk", "--audio", str(media), "--out", str(out)])
    assert exited.value.code == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert quality.read_bytes() == before[quality]
    assert timing.read_bytes() == before[timing]
    assert out.read_bytes() == (
        before[out] if change == "source" else b"new user transcript"
    )
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.parametrize(
    "reason",
    [
        "whisper_worker_timeout",
        "whisper_worker_resource_limit",
        "whisper_worker_failed",
        "whisper_provider_failed",
        "whisper_result_invalid",
        "whisper_repetitive_text",
        "whisper_text_limit",
        "whisper_language_invalid",
        "whisper_segment_limit",
        "whisper_segment_text_limit",
        "media_cleanup_failed",
        "media_generation_changed",
    ],
)
def test_local_worker_failure_retains_prior_bundle_and_one_json(
    fetch_transcript,
    monkeypatch,
    tmp_path,
    capsys,
    reason,
):
    media, out = _existing_local_audio_bundle(fetch_transcript, tmp_path, "f" * 64)
    _mock_media_probe(fetch_transcript, monkeypatch, media)
    paths = [out, out.with_suffix(".quality.json"), out.with_suffix(".segments.json")]
    paths[-1].write_bytes(b"prior timing")
    before = {path: path.read_bytes() for path in paths}

    def failed(*args, **kwargs):
        raise fetch_transcript.LocalMediaError(reason)

    monkeypatch.setattr(fetch_transcript, "transcribe_audio", failed)
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            ["local-talk", "--audio", str(media), "--out", str(out), "--force"]
        )
    assert exited.value.code == 1
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert reason in json.loads(captured.out)["reason"]
    assert {path: path.read_bytes() for path in paths} == before
    assert not list(tmp_path.glob("*.partial"))


def test_downloaded_whisper_duration_supplies_its_own_quality_provenance(
    fetch_transcript,
    monkeypatch,
    tmp_path,
    capsys,
):
    video_id = "eg6gqvUFh6Q"
    out = tmp_path / f"{video_id}.txt"
    text = _talk(150)
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda *a, **kw: (None, "transient metadata refusal"),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_whisper",
        lambda *a, **kw: fetch_transcript.WhisperAcquisition(text, "en", None, 180.0),
    )
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main([video_id, "--out", str(out), "--method", "whisper"])
    assert exited.value.code == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    receipt = json.loads(out.with_suffix(".quality.json").read_text())
    assert receipt["provenance"] == {
        "kind": "youtube_duration",
        "video_id": video_id,
        "duration_seconds": 180.0,
    }
    assert receipt["policy"]["duration_seconds"] == 180.0


def test_downloaded_whisper_duration_drift_preserves_prior_bundle(
    fetch_transcript,
    monkeypatch,
    tmp_path,
    capsys,
):
    video_id = "eg6gqvUFh6Q"
    out = tmp_path / f"{video_id}.txt"
    paths = [out, out.with_suffix(".quality.json"), out.with_suffix(".segments.json")]
    for path in paths:
        path.write_bytes(b"prior " + path.suffix.encode())
    before = {path: path.read_bytes() for path in paths}
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda *a, **kw: (600.0, "trusted duration"),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_whisper",
        lambda *a, **kw: fetch_transcript.WhisperAcquisition(
            _talk(600), "en", None, 900.0
        ),
    )
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [video_id, "--out", str(out), "--method", "whisper", "--force"]
        )
    assert exited.value.code == 1
    assert "duration changed" in json.loads(capsys.readouterr().out)["reason"]
    assert {path: path.read_bytes() for path in paths} == before


def test_transcript_receipt_docs_keep_quality_separate_from_timing(
    fetch_transcript,
):
    repo = Path(fetch_transcript.__file__).resolve().parents[3]
    ingress = repo / "skills" / "vault-ingress"
    skill = (ingress / "SKILL.md").read_text(encoding="utf-8")
    documents = {
        "processing": (ingress / "references" / "processing-rules.md").read_text(
            encoding="utf-8"
        ),
        "schemas": (ingress / "references" / "schemas-db.md").read_text(
            encoding="utf-8"
        ),
        "worker": (ingress / "references" / "subagent-instructions.md").read_text(
            encoding="utf-8"
        ),
        "authority": (repo / "rules" / "transcript-fetch-authority.md").read_text(
            encoding="utf-8"
        ),
    }

    for text in documents.values():
        assert ".segments.json" in text
        assert ".quality.json" in text
    assert "references/subagent-instructions.md" in skill
    assert "fixed_default" in documents["schemas"]
    assert "youtube_duration" in documents["schemas"]
    assert "local_media_duration" in documents["schemas"]
    assert "worker-returned" in documents["authority"].lower()
    assert "v5 scoring" in documents["processing"]


def test_write_is_atomic_and_leaves_no_partial(fetch_transcript, tmp_path):
    out = tmp_path / "nested" / "abc.txt"
    fetch_transcript.write_atomically(out, "content")
    assert out.read_text(encoding="utf-8") == "content"
    assert not list(tmp_path.rglob("*.partial"))


def test_cli_rejects_an_unresolvable_video(fetch_transcript, tmp_path):
    """Resolution fails before any network call, so this test never leaves the box.

    The argument is deliberately long: `not-a-video` is 11 characters drawn from
    the id alphabet, so it IS a well-formed video id and the first version of
    this test reached YouTube.
    """
    result = subprocess.run(
        [
            sys.executable,
            fetch_transcript.__file__,
            "https://www.infoq.com/presentations/java-puzzle/",
            "--out",
            str(tmp_path / "x.txt"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "11-character video id" in result.stderr
    assert json.loads(result.stdout)["ok"] is False
    assert not (tmp_path / "x.txt").exists()


def test_cli_emits_json_on_an_argument_error(fetch_transcript, tmp_path):
    """The contract promises JSON on every non-zero exit, argparse included.

    A wrapper that parses stdout must not get silence when the invocation is
    malformed — silence is the failure mode this whole script exists to end.
    """
    result = subprocess.run(
        [sys.executable, fetch_transcript.__file__, "eg6gqvUFh6Q"],  # no --out
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["ok"] is False


@pytest.mark.parametrize(
    "invalid_args,recovery",
    [
        (["--min-words", "-1"], "pass a positive integer word floor"),
        (["--duration-seconds", "-1"], "pass a positive finite trusted duration"),
    ],
)
def test_cli_quality_argument_errors_retain_actionable_recovery_guidance(
    fetch_transcript, tmp_path, capsys, invalid_args, recovery
):
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "eg6gqvUFh6Q",
                "--out",
                str(tmp_path / "eg6gqvUFh6Q.txt"),
                *invalid_args,
            ]
        )

    assert exited.value.code == 2
    assert recovery in json.loads(capsys.readouterr().out)["reason"]


def test_cli_emits_json_when_the_existing_transcript_is_unreadable(
    fetch_transcript, tmp_path
):
    """An unreadable file must not traceback past the JSON contract.

    It also must not be silently refetched — overwriting a file the script could
    not inspect is exactly the data loss it exists to prevent.
    """
    out = tmp_path / "eg6gqvUFh6Q.txt"
    out.write_text(_talk(900), encoding="utf-8")
    out.chmod(0o000)
    try:
        result = subprocess.run(
            [
                sys.executable,
                fetch_transcript.__file__,
                "eg6gqvUFh6Q",
                "--out",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
    finally:
        out.chmod(0o644)
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "unreadable" in payload["reason"]
    assert out.read_text(encoding="utf-8") == _talk(900), "existing file was clobbered"


def test_cli_rejects_invalid_utf8_without_writing_a_quality_receipt(
    fetch_transcript, tmp_path
):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    original = b"valid opening then invalid byte: \xff"
    out.write_bytes(original)

    result = subprocess.run(
        [
            sys.executable,
            fetch_transcript.__file__,
            "eg6gqvUFh6Q",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "not valid UTF-8" in payload["reason"]
    assert out.read_bytes() == original
    assert not (tmp_path / "eg6gqvUFh6Q.quality.json").exists()


def test_cli_rejects_a_dangling_transcript_destination_symlink(
    fetch_transcript, tmp_path
):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    outside = tmp_path / "missing-external-target"
    out.symlink_to(outside)

    result = subprocess.run(
        [
            sys.executable,
            fetch_transcript.__file__,
            "eg6gqvUFh6Q",
            "--out",
            str(out),
            "--force",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "destination symlink" in json.loads(result.stdout)["reason"]
    assert out.is_symlink()
    assert not outside.exists()


def test_cli_help_still_exits_zero(fetch_transcript):
    """`--help` is a success path and must not be turned into a JSON error."""
    result = subprocess.run(
        [sys.executable, fetch_transcript.__file__, "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--audio" in result.stdout


def test_cli_rejects_a_missing_audio_file(fetch_transcript, tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            fetch_transcript.__file__,
            "infoq-java-puzzlers",
            "--audio",
            str(tmp_path / "absent.mp3"),
            "--out",
            str(tmp_path / "x.txt"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "media_artifact_unavailable" in payload["reason"]
    assert not (tmp_path / "x.txt").exists()


def test_cli_keeps_a_valid_existing_transcript_without_refetching(
    fetch_transcript, tmp_path
):
    """No network: a good file short-circuits before any fetch is attempted."""
    out = tmp_path / "eg6gqvUFh6Q.txt"
    out.write_text(_talk(900), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, fetch_transcript.__file__, "eg6gqvUFh6Q", "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["method"] == "existing"
    assert payload["words"] == 900
    assert payload["timed_path"] is None
    quality_path = tmp_path / "eg6gqvUFh6Q.quality.json"
    assert payload["quality_path"] == str(quality_path)
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    text = _talk(900)
    assert quality == {
        "schema_version": 1,
        "transcript_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "policy": {
            "schema_version": 1,
            "min_words": 400,
            "duration_seconds": None,
        },
        "provenance": {"kind": "fixed_default"},
    }

    first_receipt = quality_path.read_bytes()
    repeated = subprocess.run(
        [
            sys.executable,
            fetch_transcript.__file__,
            "eg6gqvUFh6Q",
            "--out",
            str(out),
            "--min-words",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert json.loads(repeated.stdout)["quality_path"] == str(quality_path)
    assert quality_path.read_bytes() == first_receipt
    assert out.read_text(encoding="utf-8") == text


def test_stricter_minimum_cannot_authorize_provider_overwrite(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    text = _talk(900)
    out.write_text(text, encoding="utf-8")
    quality_path = fetch_transcript.write_quality_receipt(
        out,
        text,
        fetch_transcript.build_quality_policy(),
        {"kind": "fixed_default"},
    )
    before = {out: out.read_bytes(), quality_path: quality_path.read_bytes()}

    def must_not_fetch(*_args, **_kwargs):
        raise AssertionError("provider fetch must require --force")

    monkeypatch.setattr(fetch_transcript, "fetch_captions", must_not_fetch)
    monkeypatch.setattr(fetch_transcript, "fetch_whisper", must_not_fetch)
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "eg6gqvUFh6Q",
                "--out",
                str(out),
                "--min-words",
                "1000",
            ]
        )

    assert exited.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert "pass --force" in payload["reason"]
    assert {path: path.read_bytes() for path in before} == before


def test_stricter_minimum_cannot_authorize_local_audio_overwrite(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    audio = tmp_path / "recording.mp4"
    audio.write_bytes(b"synthetic local media")
    out = tmp_path / "local-talk.txt"
    text = _talk(900)
    out.write_text(text, encoding="utf-8")
    quality = out.with_suffix(".quality.json")
    timing = out.with_suffix(".segments.json")
    quality.write_bytes(b"trusted-old-quality")
    timing.write_bytes(b"trusted-old-timing")
    before = {
        out: out.read_bytes(),
        quality: quality.read_bytes(),
        timing: timing.read_bytes(),
    }
    _mock_media_probe(fetch_transcript, monkeypatch, audio)

    def must_not_transcribe(*_args, **_kwargs):
        raise AssertionError("local transcription must require --force")

    monkeypatch.setattr(fetch_transcript, "transcribe_audio", must_not_transcribe)
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "local-talk",
                "--audio",
                str(audio),
                "--out",
                str(out),
                "--min-words",
                "1000",
            ]
        )

    assert exited.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert "pass --force" in payload["reason"]
    assert {path: path.read_bytes() for path in before} == before


def test_failed_forced_local_transcription_preserves_existing_bundle(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    audio = tmp_path / "recording.mp4"
    audio.write_bytes(b"synthetic local media")
    out = tmp_path / "local-talk.txt"
    out.write_bytes(b"trusted transcript")
    quality = out.with_suffix(".quality.json")
    timing = out.with_suffix(".segments.json")
    quality.write_bytes(b"trusted quality")
    timing.write_bytes(b"trusted timing")
    before = {
        out: out.read_bytes(),
        quality: quality.read_bytes(),
        timing: timing.read_bytes(),
    }
    _mock_media_probe(fetch_transcript, monkeypatch, audio)
    monkeypatch.setattr(
        fetch_transcript,
        "transcribe_audio",
        lambda *_args, **_kwargs: (None, None, None),
    )

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "local-talk",
                "--audio",
                str(audio),
                "--out",
                str(out),
                "--force",
            ]
        )

    assert exited.value.code == 1
    json.loads(capsys.readouterr().out)
    assert {path: path.read_bytes() for path in before} == before


def test_mismatched_whisper_timing_does_not_poison_semantic_bundle(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    audio = tmp_path / "recording.mp4"
    audio.write_bytes(b"synthetic local media")
    out = tmp_path / "local-talk.txt"
    out.write_bytes(b"old transcript")
    stale_timing = out.with_suffix(".segments.json")
    stale_timing.write_bytes(b"stale timing")
    text = _talk(600)
    _mock_media_probe(fetch_transcript, monkeypatch, audio)
    monkeypatch.setattr(
        fetch_transcript,
        "transcribe_audio",
        lambda *_args, **_kwargs: (
            text,
            "en",
            [{"text": "different optional segment text", "start": 0.0, "end": 1.0}],
        ),
    )

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "local-talk",
                "--audio",
                str(audio),
                "--out",
                str(out),
                "--force",
            ]
        )

    assert exited.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["method"] == "whisper"
    assert payload["timed_path"] is None
    assert "timing unavailable" in payload["reason"]
    assert "does not equal" in payload["reason"]
    assert out.read_text(encoding="utf-8") == text
    assert Path(payload["quality_path"]).is_file()
    assert not stale_timing.exists()


def test_stored_short_talk_duration_is_reprobed_before_use(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    text = _talk(100)
    out.write_text(text, encoding="utf-8")
    quality_path = fetch_transcript.write_quality_receipt(
        out,
        text,
        fetch_transcript.build_quality_policy(trusted_duration_seconds=120.0),
        fetch_transcript.youtube_quality_provenance("eg6gqvUFh6Q", 120.0),
    )
    before = {out: out.read_bytes(), quality_path: quality_path.read_bytes()}
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _video_id: (None, "provider unavailable"),
    )

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(["eg6gqvUFh6Q", "--out", str(out)])

    assert exited.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert "provider unavailable" in payload["reason"]
    assert {path: path.read_bytes() for path in before} == before


def test_cli_reports_a_verified_existing_timing_sidecar(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    text = _talk(900)
    fetch_transcript.write_transcript_bundle(
        out,
        text,
        [{"text": text, "start": 0.0, "end": 600.0}],
        source="captions",
        timing_provenance=fetch_transcript.youtube_timing_provenance(
            "captions", "eg6gqvUFh6Q", 600.0
        ),
    )
    timing_path = tmp_path / "eg6gqvUFh6Q.segments.json"
    timing_before = timing_path.read_bytes()

    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _video_id: (600.0, "trusted synthetic duration"),
    )
    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "eg6gqvUFh6Q",
                "--out",
                str(out),
                "--existing-source",
                "youtube_auto",
            ]
        )

    assert exited.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["method"] == "existing"
    assert payload["timed_path"] == str(timing_path)
    assert payload["quality_path"] == str(tmp_path / "eg6gqvUFh6Q.quality.json")
    assert timing_path.read_bytes() == timing_before


def test_existing_caption_sidecar_cannot_override_manual_owner(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    text = _talk(900)
    fetch_transcript.write_transcript_bundle(
        out,
        text,
        [{"text": text, "start": 0.0, "end": 600.0}],
        source="captions",
        timing_provenance=fetch_transcript.youtube_timing_provenance(
            "captions", "eg6gqvUFh6Q", 600.0
        ),
    )
    timing_path = out.with_suffix(".segments.json")
    timing_before = timing_path.read_bytes()
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _video_id: (600.0, "trusted synthetic duration"),
    )

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "eg6gqvUFh6Q",
                "--out",
                str(out),
                "--existing-source",
                "manual",
            ]
        )

    assert exited.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["method"] == "existing"
    assert payload["timed_path"] is None
    assert "cannot relabel" in payload["reason"]
    assert timing_path.read_bytes() == timing_before


def test_existing_youtube_caption_text_gains_timing_without_byte_replacement(
    fetch_transcript,
    monkeypatch,
    tmp_path,
    capsys,
):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    first = _talk(450, "alpha")
    second = _talk(450, "beta")
    existing = f"{first}   {second}"
    out.write_text(existing, encoding="utf-8")
    original_bytes = out.read_bytes()
    segments = [
        {"text": first, "start": 0.0, "duration": 300.0},
        {"text": second, "start": 300.0, "duration": 300.0},
    ]
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_captions",
        lambda _video_id, _languages: (f"{first}\n{second}", "en", segments),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "probe_youtube_duration",
        lambda _video_id: (600.0, "trusted synthetic duration"),
    )

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "eg6gqvUFh6Q",
                "--out",
                str(out),
                "--existing-source",
                "youtube_auto",
            ]
        )

    assert exited.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["method"] == "existing"
    assert payload["timed_path"] == str(tmp_path / "eg6gqvUFh6Q.segments.json")
    assert "exact text equivalence modulo whitespace" in payload["reason"]
    assert out.read_bytes() == original_bytes
    timing = json.loads(Path(payload["timed_path"]).read_text(encoding="utf-8"))
    assert timing["source"] == "captions"
    assert timing["schema_version"] == 2
    assert timing["provenance"] == {
        "kind": "youtube_captions",
        "video_id": "eg6gqvUFh6Q",
        "duration_seconds": 600.0,
    }
    assert timing["transcript_sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert len(timing["segments"]) == 2


def test_existing_edited_transcript_does_not_gain_caption_timing(
    fetch_transcript,
    monkeypatch,
    tmp_path,
):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    existing = _talk(450, "alpha") + " manually edited"
    out.write_text(existing, encoding="utf-8")
    monkeypatch.setattr(
        fetch_transcript,
        "fetch_captions",
        lambda _video_id, _languages: (
            _talk(450, "alpha"),
            "en",
            [{"text": _talk(450, "alpha"), "start": 0.0, "end": 60.0}],
        ),
    )

    timed_path, reason = fetch_transcript.enrich_existing_caption_timing(
        out,
        existing,
        "eg6gqvUFh6Q",
        ["en"],
        existing_source="youtube_auto",
        duration_seconds=60.0,
    )

    assert timed_path is None
    assert "differ" in reason and "beyond whitespace" in reason
    assert not out.with_suffix(".segments.json").exists()


def test_manual_existing_transcript_is_never_relabelled_as_captions(
    fetch_transcript,
    monkeypatch,
    tmp_path,
):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    existing = _talk(450)
    out.write_text(existing, encoding="utf-8")

    def must_not_fetch(_video_id, _languages):
        raise AssertionError("manual provenance must short-circuit caption fetch")

    monkeypatch.setattr(fetch_transcript, "fetch_captions", must_not_fetch)
    timed_path, reason = fetch_transcript.enrich_existing_caption_timing(
        out,
        existing,
        "eg6gqvUFh6Q",
        ["en"],
        existing_source="manual",
    )

    assert timed_path is None
    assert "not 'youtube_auto'" in reason
    assert not out.with_suffix(".segments.json").exists()


def test_provider_auto_existing_transcript_never_fetches_youtube_captions(
    fetch_transcript,
    monkeypatch,
    tmp_path,
):
    out = tmp_path / "provider.txt"
    existing = _talk(450)
    out.write_text(existing, encoding="utf-8")

    def must_not_fetch(_video_id, _languages):
        raise AssertionError("provider captions must not enter the YouTube lane")

    monkeypatch.setattr(fetch_transcript, "fetch_captions", must_not_fetch)
    timed_path, reason = fetch_transcript.enrich_existing_caption_timing(
        out,
        existing,
        "eg6gqvUFh6Q",
        ["en"],
        existing_source="provider_auto",
    )

    assert timed_path is None
    assert "not 'youtube_auto'" in reason
    assert not out.with_suffix(".segments.json").exists()

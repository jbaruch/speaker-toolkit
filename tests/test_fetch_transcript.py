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
import json
import pathlib
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


def _blocking_yt_dlp(fetch_transcript, monkeypatch, serving_client, attempts):
    """Mock yt-dlp as YouTube currently behaves: one client works, others 403.

    Writes the audio file only for `serving_client`, exactly as a real download
    does, so the caller's "did a file appear" check decides the outcome.
    """

    def run(command, **_kwargs):
        client = None
        if "--extractor-args" in command:
            client = command[command.index("--extractor-args") + 1].split("=")[-1]
        attempts.append(client)
        if client != serving_client:
            return subprocess.CompletedProcess(
                command, 1, stdout="", stderr="HTTP Error 403: Forbidden"
            )
        target = command[command.index("-o") + 1]
        pathlib.Path(target.replace("%(ext)s", "mp3")).write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(fetch_transcript.subprocess, "run", run)


def test_a_refused_player_client_advances_to_the_next(
    fetch_transcript, monkeypatch, tmp_path
):
    """The 403 that killed the fallback: a later client must still be tried."""
    attempts: list[str | None] = []
    _blocking_yt_dlp(fetch_transcript, monkeypatch, "mweb", attempts)
    monkeypatch.setattr(
        fetch_transcript,
        "transcribe_audio",
        lambda *a, **k: ("spoken words here", "en", None),
    )

    text, language, _segments = fetch_transcript.fetch_whisper(
        "Kl6tLcQ5hGI", str(tmp_path), "tiny"
    )

    assert text == "spoken words here"
    assert language == "en"
    assert attempts[0] is None, "the default chain must be tried first"
    assert "mweb" in attempts, "the serving client must be reached"


def test_a_working_default_client_never_pays_for_the_fallbacks(
    fetch_transcript, monkeypatch, tmp_path
):
    attempts: list[str | None] = []
    _blocking_yt_dlp(fetch_transcript, monkeypatch, None, attempts)
    monkeypatch.setattr(
        fetch_transcript,
        "transcribe_audio",
        lambda *a, **k: ("spoken words here", "en", None),
    )

    text, _language, _segments = fetch_transcript.fetch_whisper(
        "Kl6tLcQ5hGI", str(tmp_path), "tiny"
    )

    assert text == "spoken words here"
    assert attempts == [None], "a healthy environment must make exactly one attempt"


def test_every_player_client_refusing_reports_failure(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    """Exhaustion is a failure that names what was tried, not a traceback."""
    attempts: list[str | None] = []
    _blocking_yt_dlp(fetch_transcript, monkeypatch, "no-such-client", attempts)

    text, language, segments = fetch_transcript.fetch_whisper(
        "Kl6tLcQ5hGI", str(tmp_path), "tiny"
    )

    assert (text, language, segments) == (None, None, None)
    assert len(attempts) == len(fetch_transcript.YOUTUBE_PLAYER_CLIENTS)
    stderr = capsys.readouterr().err
    assert "under any player client" in stderr
    assert "403" in stderr


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


def test_direct_whisper_call_propagates_an_unisolated_import_failure(
    fetch_transcript, monkeypatch, tmp_path
):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"synthetic")

    def broken_import(_name):
        raise TypeError("synthetic optional dependency import failure")

    monkeypatch.setattr(fetch_transcript.importlib, "import_module", broken_import)

    with pytest.raises(TypeError, match="synthetic optional dependency"):
        fetch_transcript.transcribe_audio(audio, "local-talk", "model")


def test_direct_whisper_call_propagates_an_unisolated_api_failure(
    fetch_transcript, monkeypatch, tmp_path
):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"synthetic")

    class BrokenWhisper:
        @staticmethod
        def transcribe(*_args, **_kwargs):
            raise KeyError("synthetic result-shape failure")

    monkeypatch.setattr(
        fetch_transcript.importlib,
        "import_module",
        lambda _name: BrokenWhisper,
    )

    with pytest.raises(KeyError, match="synthetic result-shape failure"):
        fetch_transcript.transcribe_audio(audio, "local-talk", "model")


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
    fetch_transcript, monkeypatch
):
    seen = []

    def completed(command, **kwargs):
        seen.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"id": "eg6gqvUFh6Q", "duration": 179.625}),
            stderr="",
        )

    monkeypatch.setattr(fetch_transcript.subprocess, "run", completed)

    duration, reason = fetch_transcript.probe_youtube_duration("eg6gqvUFh6Q")

    assert duration == 179.625
    assert "trusted yt-dlp duration" in reason
    assert seen == [
        (
            [
                "yt-dlp",
                "--dump-single-json",
                "--skip-download",
                "--no-playlist",
                "https://www.youtube.com/watch?v=eg6gqvUFh6Q",
            ],
            {"capture_output": True, "text": True},
        )
    ]
    assert fetch_transcript.youtube_quality_provenance(
        "eg6gqvUFh6Q",
        duration,
    ) == {
        "kind": "youtube_duration",
        "video_id": "eg6gqvUFh6Q",
        "duration_seconds": 179.625,
    }


def test_youtube_duration_probe_rejects_provider_identity_drift(
    fetch_transcript, monkeypatch
):
    monkeypatch.setattr(
        fetch_transcript.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"id": "wb2C2ju_xRg", "duration": 179.625}),
            stderr="",
        ),
    )

    duration, reason = fetch_transcript.probe_youtube_duration("eg6gqvUFh6Q")

    assert duration is None
    assert "identity mismatch" in reason


def test_local_duration_provenance_hashes_the_exact_media(
    fetch_transcript, monkeypatch, tmp_path
):
    media = tmp_path / "recording.mp4"
    media.write_bytes(b"synthetic local media bytes")
    monkeypatch.setattr(
        fetch_transcript.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="61.250000\n",
            stderr="",
        ),
    )

    duration, reason = fetch_transcript.probe_local_media_duration(media)

    assert duration == 61.25
    assert "trusted ffprobe duration" in reason
    provenance = fetch_transcript.local_media_quality_provenance(
        fetch_transcript.media_sha256(media),
        duration,
    )
    assert provenance == {
        "kind": "local_media_duration",
        "media_sha256": (
            "2d252575385bde1cab2b5ee3f23e77129478a0412fef2ddecd53a07b650b9e14"
        ),
        "duration_seconds": 61.25,
    }


def test_local_audio_probe_transcription_and_receipts_share_one_snapshot(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    media = tmp_path / "recording.mp4"
    media_bytes = b"stable local media bytes"
    media.write_bytes(media_bytes)
    text = _talk(600)
    seen: dict[str, Path] = {}

    def probe(path):
        seen["probe"] = path
        return 600.0, "trusted synthetic duration"

    def transcribe(path, _label, _model):
        seen["transcribe"] = path
        return text, "en", [{"text": text, "start": 0.0, "end": 600.0}]

    monkeypatch.setattr(fetch_transcript, "probe_local_media_duration", probe)
    monkeypatch.setattr(fetch_transcript, "transcribe_audio", transcribe)
    out = tmp_path / "local-talk.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "local-talk",
                "--audio",
                str(media),
                "--out",
                str(out),
            ]
        )

    assert exited.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert seen["probe"] == seen["transcribe"]
    assert seen["probe"] != media
    digest = hashlib.sha256(media_bytes).hexdigest()
    quality = json.loads(out.with_suffix(".quality.json").read_text(encoding="utf-8"))
    timing = json.loads(out.with_suffix(".segments.json").read_text(encoding="utf-8"))
    assert quality["provenance"]["media_sha256"] == digest
    assert timing["provenance"]["media_sha256"] == digest


@pytest.mark.parametrize("mutation_phase", ["probe", "transcription"])
def test_local_audio_snapshot_mutation_fails_closed_without_a_bundle(
    fetch_transcript, monkeypatch, tmp_path, capsys, mutation_phase
):
    media = tmp_path / "recording.mp4"
    media.write_bytes(b"stable local media bytes")
    text = _talk(600)

    def mutate(path):
        path.chmod(0o600)
        path.write_bytes(b"provider-mutated snapshot")

    def probe(path):
        if mutation_phase == "probe":
            mutate(path)
        return 600.0, "trusted synthetic duration"

    def transcribe(path, _label, _model):
        if mutation_phase == "transcription":
            mutate(path)
        return text, "en", [{"text": text, "start": 0.0, "end": 600.0}]

    monkeypatch.setattr(fetch_transcript, "probe_local_media_duration", probe)
    monkeypatch.setattr(fetch_transcript, "transcribe_audio", transcribe)
    out = tmp_path / "local-talk.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "local-talk",
                "--audio",
                str(media),
                "--out",
                str(out),
            ]
        )

    assert exited.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "snapshot changed" in payload["reason"]
    assert not out.exists()
    assert not out.with_suffix(".quality.json").exists()
    assert not out.with_suffix(".segments.json").exists()


def test_local_audio_source_replacement_during_transcription_fails_closed(
    fetch_transcript, monkeypatch, tmp_path, capsys
):
    media = tmp_path / "recording.mp4"
    media.write_bytes(b"stable local media bytes")
    text = _talk(600)

    monkeypatch.setattr(
        fetch_transcript,
        "probe_local_media_duration",
        lambda _path: (600.0, "trusted synthetic duration"),
    )

    def replace_source(_snapshot_path, _label, _model):
        replacement = tmp_path / "replacement.mp4"
        replacement.write_bytes(b"different media bytes")
        os.replace(replacement, media)
        return text, "en", [{"text": text, "start": 0.0, "end": 600.0}]

    monkeypatch.setattr(fetch_transcript, "transcribe_audio", replace_source)
    out = tmp_path / "local-talk.txt"

    with pytest.raises(SystemExit) as exited:
        fetch_transcript.main(
            [
                "local-talk",
                "--audio",
                str(media),
                "--out",
                str(out),
            ]
        )

    assert exited.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "source changed or was replaced" in payload["reason"]
    assert not out.exists()
    assert not out.with_suffix(".quality.json").exists()
    assert not out.with_suffix(".segments.json").exists()


def test_expected_duration_must_match_source_probe(fetch_transcript):
    assert fetch_transcript.duration_matches_expected(180, 179.625) is True
    assert fetch_transcript.duration_matches_expected(60, 179.625) is False


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
    assert "does not exist" in payload["reason"]
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
    monkeypatch.setattr(
        fetch_transcript,
        "probe_local_media_duration",
        lambda _path: (600.0, "trusted synthetic duration"),
    )

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
    monkeypatch.setattr(
        fetch_transcript,
        "probe_local_media_duration",
        lambda _path: (600.0, "trusted synthetic duration"),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "transcribe_audio",
        lambda *_args: (None, None, None),
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
    monkeypatch.setattr(
        fetch_transcript,
        "probe_local_media_duration",
        lambda _path: (600.0, "trusted synthetic duration"),
    )
    monkeypatch.setattr(
        fetch_transcript,
        "transcribe_audio",
        lambda *_args: (
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

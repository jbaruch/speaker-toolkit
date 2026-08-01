"""Tests for fetch-transcript.py — the validation that keeps crashes out of the corpus.

Regression coverage for the defect that motivated the script: an inline fetch
heredoc wrote its own Python traceback to the transcript path when
`youtube-transcript-api` 1.0 removed `get_transcript`. Four vault transcripts
are that traceback and two are zero bytes; nothing noticed, and one talk was
marked `processed` off an empty file.

Every check here is on pure functions, so the whole failure surface is testable
in CI without a network, without YouTube, and without Apple-Silicon Whisper.
"""

import json
import subprocess
import sys

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


def _raw_vtt(lines=200):
    """YouTube's karaoke caption payload: each line once tagged, once plain."""
    out = []
    for n in range(lines):
        stamp = f"00:00:{n // 60:02d}.{n % 60:03d}"
        out.append(f"so<{stamp}><c> before</c><{stamp}><c> we</c><{stamp}><c> start</c>")
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
        _talk(500), duration_seconds=60 * 60)
    assert not ok
    assert "wpm" in reason


def test_plausible_transcript_passes(fetch_transcript):
    ok, reason = fetch_transcript.validate_transcript(
        _talk(7000), duration_seconds=50 * 60)
    assert ok
    assert "7000 words" in reason


def test_cyrillic_words_are_counted(fetch_transcript):
    """A Russian talk must not read as empty — `[a-z]` would count zero words."""
    russian = " ".join(["получается"] * 600)
    assert fetch_transcript.count_words(russian) == 600
    ok, _ = fetch_transcript.validate_transcript(russian)
    assert ok


@pytest.mark.parametrize("value,expected", [
    ("eg6gqvUFh6Q", "eg6gqvUFh6Q"),
    ("https://www.youtube.com/watch?v=eg6gqvUFh6Q", "eg6gqvUFh6Q"),
    ("https://youtu.be/wb2C2ju_xRg", "wb2C2ju_xRg"),
    ("https://www.youtube.com/embed/0MGvxG-sc6g", "0MGvxG-sc6g"),
    ("https://www.youtube.com/watch?v=OeTtYIjcxpc&t=42s", "OeTtYIjcxpc"),
])
def test_video_id_resolution(fetch_transcript, value, expected):
    assert fetch_transcript.resolve_video_id(value) == expected


def test_video_id_resolution_rejects_a_non_url(fetch_transcript):
    assert fetch_transcript.resolve_video_id("https://www.infoq.com/presentations/x") is None


def test_segments_accepts_both_library_shapes(fetch_transcript):
    """Pinning to one shape is exactly what broke the previous fetch."""
    class Segment:
        def __init__(self, text):
            self.text = text

    assert fetch_transcript.segments_to_text(
        [{"text": "hello"}, {"text": "world"}]) == "hello\nworld"
    assert fetch_transcript.segments_to_text(
        [Segment("hello"), Segment("world")]) == "hello\nworld"


def test_caption_errors_fall_through_instead_of_propagating(fetch_transcript, monkeypatch):
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

    monkeypatch.setattr(YouTubeTranscriptApi, "fetch",
                        lambda self, *a, **k: Fetched([Segment("привет")]),
                        raising=False)
    text, language, segments = fetch_transcript.fetch_captions("x", ["en", "ru"])
    assert text == "привет"
    assert language == "ru"
    assert segments[0].start == 1.0


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
        [sys.executable, fetch_transcript.__file__,
         "https://www.infoq.com/presentations/java-puzzle/",
         "--out", str(tmp_path / "x.txt")],
        capture_output=True, text=True,
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
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["ok"] is False


def test_cli_emits_json_when_the_existing_transcript_is_unreadable(
        fetch_transcript, tmp_path):
    """An unreadable file must not traceback past the JSON contract.

    It also must not be silently refetched — overwriting a file the script could
    not inspect is exactly the data loss it exists to prevent.
    """
    out = tmp_path / "eg6gqvUFh6Q.txt"
    out.write_text(_talk(900), encoding="utf-8")
    out.chmod(0o000)
    try:
        result = subprocess.run(
            [sys.executable, fetch_transcript.__file__, "eg6gqvUFh6Q",
             "--out", str(out)],
            capture_output=True, text=True,
        )
    finally:
        out.chmod(0o644)
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "unreadable" in payload["reason"]
    assert out.read_text(encoding="utf-8") == _talk(900), "existing file was clobbered"


def test_cli_help_still_exits_zero(fetch_transcript):
    """`--help` is a success path and must not be turned into a JSON error."""
    result = subprocess.run(
        [sys.executable, fetch_transcript.__file__, "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--audio" in result.stdout


def test_cli_rejects_a_missing_audio_file(fetch_transcript, tmp_path):
    result = subprocess.run(
        [sys.executable, fetch_transcript.__file__, "infoq-java-puzzlers",
         "--audio", str(tmp_path / "absent.mp3"),
         "--out", str(tmp_path / "x.txt")],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "does not exist" in payload["reason"]
    assert not (tmp_path / "x.txt").exists()


def test_cli_keeps_a_valid_existing_transcript_without_refetching(
        fetch_transcript, tmp_path):
    """No network: a good file short-circuits before any fetch is attempted."""
    out = tmp_path / "eg6gqvUFh6Q.txt"
    out.write_text(_talk(900), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, fetch_transcript.__file__, "eg6gqvUFh6Q", "--out", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["method"] == "existing"
    assert payload["words"] == 900
    assert payload["timed_path"] is None


def test_cli_reports_a_verified_existing_timing_sidecar(fetch_transcript, tmp_path):
    out = tmp_path / "eg6gqvUFh6Q.txt"
    text = _talk(900)
    fetch_transcript.write_transcript_bundle(
        out,
        text,
        [{"text": text, "start": 0.0, "end": 600.0}],
        source="captions",
    )

    result = subprocess.run(
        [sys.executable, fetch_transcript.__file__, "eg6gqvUFh6Q", "--out", str(out)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["method"] == "existing"
    assert payload["timed_path"] == str(tmp_path / "eg6gqvUFh6Q.segments.json")

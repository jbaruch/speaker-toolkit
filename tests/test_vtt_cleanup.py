"""Tests for vtt-cleanup.py — WebVTT to plain text conversion."""

import json
import subprocess
import sys


def test_strip_webvtt_header(vtt_cleanup):
    raw = "WEBVTT\nKind: captions\nLanguage: en\n\n00:00:01.000 --> 00:00:03.000\nHello world"
    assert vtt_cleanup.clean_vtt(raw) == "Hello world"


def test_strip_timestamps(vtt_cleanup):
    raw = "00:00:01.234 --> 00:00:04.567\nLine one\n00:01:00.000 --> 00:01:02.000\nLine two"
    assert vtt_cleanup.clean_vtt(raw) == "Line one\nLine two"


def test_strip_cue_identifiers(vtt_cleanup):
    raw = "1\n00:00:01.000 --> 00:00:02.000\nFirst\n2\n00:00:03.000 --> 00:00:04.000\nSecond"
    assert vtt_cleanup.clean_vtt(raw) == "First\nSecond"


def test_strip_position_markers(vtt_cleanup):
    raw = "align:start position:0%\nHello\nsize:100%\nWorld"
    assert vtt_cleanup.clean_vtt(raw) == "Hello\nWorld"


def test_dedup_consecutive_lines(vtt_cleanup):
    raw = "Hello\nHello\nHello\nWorld\nWorld"
    assert vtt_cleanup.clean_vtt(raw) == "Hello\nWorld"


def test_non_consecutive_duplicates_kept(vtt_cleanup):
    raw = "Hello\nWorld\nHello"
    assert vtt_cleanup.clean_vtt(raw) == "Hello\nWorld\nHello"


def test_strip_html_tags(vtt_cleanup):
    raw = "<c>Hello</c> <b>world</b>"
    assert vtt_cleanup.clean_vtt(raw) == "Hello world"


def test_note_word_inside_a_cue_is_speech_not_a_control_block(vtt_cleanup):
    raw = "00:00:01.000 --> 00:00:03.000\nNOTE that this is important"
    text, segments = vtt_cleanup.parse_vtt(raw)
    assert text == "NOTE that this is important"
    assert segments[0]["text"] == "NOTE that this is important"


def test_skip_blank_lines(vtt_cleanup):
    raw = "Line one\n\n\n\nLine two"
    assert vtt_cleanup.clean_vtt(raw) == "Line one\nLine two"


def test_full_vtt_file(vtt_cleanup):
    vtt = """\
WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000
align:start position:0%
Hello everyone

00:00:03.000 --> 00:00:05.000
Hello everyone
welcome to the talk

00:00:05.000 --> 00:00:08.000
<c>Let's get started</c>
"""
    result = vtt_cleanup.clean_vtt(vtt)
    assert result == "Hello everyone\nwelcome to the talk\nLet's get started"


def test_rolling_captions_keep_timing_aligned_with_deduplicated_text(vtt_cleanup):
    raw = """\
WEBVTT

00:00:01.000 --> 00:00:03.000
Hello everyone

00:00:03.000 --> 00:00:05.000
Hello everyone
welcome to the talk

00:00:05.000 --> 00:00:08.000
welcome to the talk
Let's get started
"""
    text, segments = vtt_cleanup.parse_vtt(raw)
    assert text == "Hello everyone\nwelcome to the talk\nLet's get started"
    assert segments == [
        {"text": "Hello everyone", "start_seconds": 1.0, "end_seconds": 3.0},
        {"text": "welcome to the talk", "start_seconds": 3.0, "end_seconds": 5.0},
        {"text": "Let's get started", "start_seconds": 5.0, "end_seconds": 8.0},
    ]


def test_parse_vtt_preserves_cue_timing(vtt_cleanup):
    raw = """\
WEBVTT

00:00:01.250 --> 00:00:03.500
The opening claim

00:00:03.500 --> 00:00:07.000
Now the explanation
continues here
"""
    text, segments = vtt_cleanup.parse_vtt(raw)
    assert text == "The opening claim\nNow the explanation\ncontinues here"
    assert segments == [
        {
            "text": "The opening claim",
            "start_seconds": 1.25,
            "end_seconds": 3.5,
        },
        {
            "text": "Now the explanation continues here",
            "start_seconds": 3.5,
            "end_seconds": 7.0,
        },
    ]


def test_cli_writes_plain_text_and_timed_sidecar(vtt_cleanup, tmp_path):
    source = tmp_path / "talk.en.vtt"
    output = tmp_path / "talk.txt"
    source.write_text(
        "WEBVTT\n\n00:00:02.000 --> 00:00:04.000\nOpening words\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, vtt_cleanup.__file__, str(source), str(output)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert output.read_text(encoding="utf-8") == "Opening words"
    assert payload["timed_path"] == str(tmp_path / "talk.segments.json")
    sidecar = json.loads((tmp_path / "talk.segments.json").read_text(encoding="utf-8"))
    assert sidecar["segments"][0]["start_seconds"] == 2.0

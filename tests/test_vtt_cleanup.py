"""Tests for vtt-cleanup.py — WebVTT to plain text conversion."""


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

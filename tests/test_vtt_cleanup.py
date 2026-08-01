"""Tests for vtt-cleanup.py — WebVTT to plain text conversion."""

import json
import os
import subprocess
import sys


def test_strip_webvtt_header(vtt_cleanup):
    raw = "WEBVTT\nKind: captions\nLanguage: en\n\n00:00:01.000 --> 00:00:03.000\nHello world"
    assert vtt_cleanup.clean_vtt(raw) == "Hello world"


def test_strip_timestamps(vtt_cleanup):
    raw = "00:00:01.234 --> 00:00:04.567\nLine one\n00:01:00.000 --> 00:01:02.000\nLine two"
    assert vtt_cleanup.clean_vtt(raw) == "Line one\nLine two"


def test_strip_cue_identifiers(vtt_cleanup):
    raw = "1\n00:00:01.000 --> 00:00:02.000\nFirst\n\n2\n00:00:03.000 --> 00:00:04.000\nSecond"
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


def test_parse_vtt_accepts_timestamps_without_hours(vtt_cleanup):
    raw = "WEBVTT\n\n01:02.250 --> 01:04.500\nShort-form timestamp\n"

    text, segments = vtt_cleanup.parse_vtt(raw)

    assert text == "Short-form timestamp"
    assert segments == [
        {
            "text": "Short-form timestamp",
            "start_seconds": 62.25,
            "end_seconds": 64.5,
        }
    ]


def test_hourless_cue_preserves_numeric_spoken_content(vtt_cleanup):
    raw = "WEBVTT\n\n01:02.250 --> 01:04.500\n2026\n"

    text, segments = vtt_cleanup.parse_vtt(raw)

    assert text == "2026"
    assert segments == [
        {
            "text": "2026",
            "start_seconds": 62.25,
            "end_seconds": 64.5,
        }
    ]


def test_numeric_cue_identifier_is_not_transcript_content(vtt_cleanup):
    raw = "WEBVTT\n\n42\n01:02.250 --> 01:04.500\nActual cue text\n"

    text, segments = vtt_cleanup.parse_vtt(raw)

    assert text == "Actual cue text"
    assert segments[0]["text"] == "Actual cue text"


def test_numeric_content_before_unseparated_next_timing_is_preserved(vtt_cleanup):
    raw = "WEBVTT\n\n01:02.250 --> 01:04.500\n2026\n01:04.500 --> 01:06.000\nNext cue\n"

    text, segments = vtt_cleanup.parse_vtt(raw)

    assert text == "2026\nNext cue"
    assert [segment["text"] for segment in segments] == ["2026", "Next cue"]


def test_named_cue_identifier_is_dropped_only_between_cues(vtt_cleanup):
    raw = "WEBVTT\n\nspeaker-intro\n01:02.250 --> 01:04.500\nActual cue text\n"

    text, segments = vtt_cleanup.parse_vtt(raw)

    assert text == "Actual cue text"
    assert segments[0]["text"] == "Actual cue text"


def test_cli_writes_plain_text_and_timed_sidecar(vtt_cleanup, tmp_path):
    source = tmp_path / "talk.en.vtt"
    output = tmp_path / "talk.txt"
    speech = " ".join(["Opening"] * 400)
    source.write_text(
        f"WEBVTT\n\n00:00:02.000 --> 00:10:00.000\n{speech}\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, vtt_cleanup.__file__, str(source), str(output)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert output.read_text(encoding="utf-8") == speech
    assert payload["timed_path"] == str(tmp_path / "talk.segments.json")
    assert payload["quality_path"] == str(tmp_path / "talk.quality.json")
    sidecar = json.loads((tmp_path / "talk.segments.json").read_text(encoding="utf-8"))
    assert sidecar["segments"][0]["start_seconds"] == 2.0
    assert sidecar["schema_version"] == 2
    assert sidecar["provenance"]["artifact_path"] == "talk.en.vtt"
    assert sidecar["provenance"]["cue_extent_seconds"] == 600.0


def test_cli_requires_explicit_output_to_avoid_language_collision(
    vtt_cleanup, tmp_path
):
    source = tmp_path / "talk.en.vtt"
    source.write_text("WEBVTT\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, vtt_cleanup.__file__, str(source)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["ok"] is False
    assert not (tmp_path / "talk.txt").exists()


def test_cli_preserves_existing_bundle_without_force(vtt_cleanup, tmp_path):
    source = tmp_path / "talk.ru.vtt"
    speech = " ".join(["replacement"] * 400)
    source.write_text(
        f"WEBVTT\n\n00:00:00.000 --> 00:10:00.000\n{speech}\n",
        encoding="utf-8",
    )
    output = tmp_path / "talk.txt"
    quality = tmp_path / "talk.quality.json"
    timing = tmp_path / "talk.segments.json"
    output.write_bytes(b"trusted transcript")
    quality.write_bytes(b"trusted quality")
    timing.write_bytes(b"trusted timing")
    before = {
        output: output.read_bytes(),
        quality: quality.read_bytes(),
        timing: timing.read_bytes(),
    }

    result = subprocess.run(
        [sys.executable, vtt_cleanup.__file__, str(source), str(output)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--force" in json.loads(result.stdout)["reason"]
    assert {path: path.read_bytes() for path in before} == before


def test_cli_force_replaces_the_complete_vtt_bundle(vtt_cleanup, tmp_path):
    source = tmp_path / "talk.en.vtt"
    speech = " ".join(["replacement"] * 400)
    source.write_text(
        f"WEBVTT\n\n00:00:00.000 --> 00:10:00.000\n{speech}\n",
        encoding="utf-8",
    )
    output = tmp_path / "talk.txt"
    output.write_text("old transcript", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            vtt_cleanup.__file__,
            str(source),
            str(output),
            "--force",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == speech
    assert (tmp_path / "talk.quality.json").exists()
    assert (tmp_path / "talk.segments.json").exists()


def test_cli_rejects_short_vtt_without_writing(vtt_cleanup, tmp_path):
    source = tmp_path / "short.en.vtt"
    output = tmp_path / "short.txt"
    source.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nToo short\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, vtt_cleanup.__file__, str(source), str(output)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "400-word floor" in json.loads(result.stdout)["reason"]
    assert not output.exists()
    assert not output.with_suffix(".segments.json").exists()
    assert not output.with_suffix(".quality.json").exists()


def test_cli_rejects_an_outside_vtt_before_reading_it(vtt_cleanup, tmp_path):
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    source = tmp_path / "outside.vtt"
    source.write_bytes(b"outside bytes that must not be imported")
    output = transcript_dir / "talk.txt"

    result = subprocess.run(
        [sys.executable, vtt_cleanup.__file__, str(source), str(output)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "lexically inside" in json.loads(result.stdout)["reason"]
    assert not output.exists()


def test_cli_rejects_a_vtt_below_a_symlinked_parent(vtt_cleanup, tmp_path):
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    source = outside_dir / "talk.vtt"
    source.write_bytes(b"outside bytes that must not be imported")
    linked_parent = transcript_dir / "linked"
    linked_parent.symlink_to(outside_dir, target_is_directory=True)
    output = transcript_dir / "talk.txt"

    result = subprocess.run(
        [
            sys.executable,
            vtt_cleanup.__file__,
            str(linked_parent / "talk.vtt"),
            str(output),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "symlink" in json.loads(result.stdout)["reason"]
    assert not output.exists()


def test_cli_rejects_a_fifo_vtt_without_blocking_on_open(vtt_cleanup, tmp_path):
    source = tmp_path / "talk.vtt"
    os.mkfifo(source)
    output = tmp_path / "talk.txt"

    result = subprocess.run(
        [sys.executable, vtt_cleanup.__file__, str(source), str(output)],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 2
    assert "regular file" in json.loads(result.stdout)["reason"]
    assert not output.exists()


def test_cli_rejects_a_dangling_output_symlink_before_force(vtt_cleanup, tmp_path):
    source = tmp_path / "talk.en.vtt"
    source.write_text("WEBVTT\n", encoding="utf-8")
    output = tmp_path / "talk.txt"
    outside = tmp_path / "missing-external-target"
    output.symlink_to(outside)

    result = subprocess.run(
        [
            sys.executable,
            vtt_cleanup.__file__,
            str(source),
            str(output),
            "--force",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "destination symlink" in json.loads(result.stdout)["reason"]
    assert output.is_symlink()
    assert not outside.exists()


def test_cli_explains_how_to_repair_a_vtt_without_timed_cues(vtt_cleanup, tmp_path):
    source = tmp_path / "talk.en.vtt"
    source.write_text(" ".join(["speech"] * 400), encoding="utf-8")
    output = tmp_path / "talk.txt"

    result = subprocess.run(
        [sys.executable, vtt_cleanup.__file__, str(source), str(output)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    reason = json.loads(result.stdout)["reason"]
    assert "timestamped cues" in reason
    assert "cue-bearing VTT" in reason
    assert not output.exists()

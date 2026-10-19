"""extract-local-audio.py: a recording's audio, bounded and owner-verified (#485).

Fixture recordings are synthesized by ffmpeg in ``tmp_path``; nothing reads the
wall clock or a checked-in binary.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from conftest import SCRIPTS_VI

SCRIPT = os.path.join(SCRIPTS_VI, "extract-local-audio.py")


def _recording(directory: Path, *, audio: bool = True, seconds: int = 3) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    recording = directory / "room-camera.mp4"
    inputs = ["-f", "lavfi", "-i", f"testsrc=size=64x64:rate=5:duration={seconds}"]
    if audio:
        inputs += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=16000:duration={seconds}",
        ]
    codecs = ["-c:v", "mpeg4"] + (["-c:a", "aac"] if audio else [])
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", *inputs]
        + codecs
        + ["-y", str(recording)],
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return recording


def _run(*arguments: str, env: dict[str, str] | None = None):
    completed = subprocess.run(
        [sys.executable, SCRIPT, *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return completed.returncode, json.loads(completed.stdout), completed.stderr


def _extract(recording: Path, output: Path):
    return _run("--recording", str(recording), "--output", str(output))


def _staged(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir() if ".partial" in path.name)


def _audio_streams(path: Path) -> list[str]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        timeout=60,
    )
    return [stream["codec_type"] for stream in json.loads(result.stdout)["streams"]]


@pytest.mark.parametrize("suffix,mode", [(".m4a", "copy"), (".wav", "pcm_s16le")])
def test_the_audio_stream_is_extracted_verified_and_reported(
    tmp_path, suffix, mode
):
    recording = _recording(tmp_path / "videos")
    output = tmp_path / "recordings" / f"talk{suffix}"
    output.parent.mkdir()

    code, payload, stderr = _extract(recording, output)

    assert code == 0, stderr
    assert payload["ok"] is True
    assert payload["written"] is True
    assert payload["mode"] == mode
    assert payload["output"] == str(output)
    assert payload["size_bytes"] == output.stat().st_size
    assert 2.5 <= payload["duration_seconds"] <= 3.5
    assert _audio_streams(output) == ["audio"]
    assert _staged(output.parent) == []


def test_a_replay_with_the_same_bytes_is_an_unchanged_success(tmp_path):
    recording = _recording(tmp_path / "videos")
    output = tmp_path / "talk.m4a"
    _code, first, _stderr = _extract(recording, output)
    installed = output.stat()

    code, replay, stderr = _extract(recording, output)

    assert code == 0, stderr
    assert replay["written"] is False
    assert replay["media_sha256"] == first["media_sha256"]
    assert output.stat().st_ino == installed.st_ino
    assert _staged(tmp_path) == []


def test_different_audio_already_at_the_output_is_never_replaced(tmp_path):
    recording = _recording(tmp_path / "videos")
    output = tmp_path / "talk.m4a"
    output.write_bytes(b"audio a receipt may already bind")

    code, payload, _stderr = _extract(recording, output)

    assert code == 2
    assert payload["reason_code"] == "output_exists"
    assert output.read_bytes() == b"audio a receipt may already bind"
    assert _staged(tmp_path) == []


def test_a_recording_without_audio_is_refused_and_leaves_nothing(tmp_path):
    recording = _recording(tmp_path / "videos", audio=False)
    output = tmp_path / "talk.m4a"

    code, payload, stderr = _extract(recording, output)

    assert code == 2
    assert payload["reason_code"] == "extraction_failed"
    assert payload["error"] in stderr
    assert not output.exists()
    assert _staged(tmp_path) == []


@pytest.mark.parametrize("name", ["talk.mp4", "talk.aac", "talk"])
def test_an_output_the_declaration_cannot_name_is_refused(tmp_path, name):
    recording = _recording(tmp_path / "videos")
    code, payload, _stderr = _extract(recording, tmp_path / name)
    assert code == 2
    assert payload["reason_code"] == "invalid_arguments"
    assert ".m4a" in payload["error"]


def test_a_missing_recording_is_refused(tmp_path):
    code, payload, _stderr = _extract(tmp_path / "absent.mp4", tmp_path / "a.m4a")
    assert code == 2
    assert payload["reason_code"] == "recording_unreadable"


def test_ffmpeg_missing_from_path_is_named(tmp_path):
    recording = _recording(tmp_path / "videos")
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    code, payload, _stderr = _run(
        "--recording",
        str(recording),
        "--output",
        str(tmp_path / "a.m4a"),
        env={**os.environ, "PATH": str(empty)},
    )
    assert code == 2
    assert payload["reason_code"] == "ffmpeg_unavailable"


def test_audio_at_the_owner_ceiling_is_refused_and_removed(
    tmp_path, extract_local_audio
):
    recording = _recording(tmp_path / "videos", seconds=10)
    output = tmp_path / "talk.wav"
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output, max_output_bytes=4096)
    assert caught.value.reason_code == "output_over_ceiling"
    assert not output.exists()
    assert _staged(tmp_path) == []


def test_a_recording_that_changes_mid_extraction_is_refused(
    tmp_path, extract_local_audio, monkeypatch
):
    recording = _recording(tmp_path / "videos")
    output = tmp_path / "talk.m4a"
    real_run = extract_local_audio._run_ffmpeg

    def run_then_touch(command, timeout_seconds):
        completed = real_run(command, timeout_seconds)
        with recording.open("ab") as handle:
            handle.write(b"\0")
        return completed

    monkeypatch.setattr(extract_local_audio, "_run_ffmpeg", run_then_touch)
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output)
    assert caught.value.reason_code == "recording_changed"
    assert not output.exists()
    assert _staged(tmp_path) == []


def test_an_ffmpeg_that_overruns_its_budget_is_stopped(
    tmp_path, extract_local_audio, monkeypatch
):
    recording = _recording(tmp_path / "videos")
    fake = tmp_path / "slow-bin" / "ffmpeg"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\nexec /bin/sleep 30\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(fake.parent))
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(
            recording, tmp_path / "talk.m4a", timeout_seconds=0.5
        )
    assert caught.value.reason_code == "extraction_timeout"
    assert _staged(tmp_path) == []

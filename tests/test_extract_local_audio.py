"""extract-local-audio.py: a recording's audio, bounded and owner-verified (#485).

Fixture recordings are synthesized by ffmpeg in ``tmp_path``; nothing reads the
wall clock or a checked-in binary.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
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
def test_the_audio_stream_is_extracted_verified_and_reported(tmp_path, suffix, mode):
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
    assert payload["reason_code"] == "recording_has_no_audio"
    assert ".wav" not in payload["error"]
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

    def run_then_touch(command, timeout_seconds, *, held):
        completed = real_run(command, timeout_seconds, held=held)
        with recording.open("ab") as handle:
            handle.write(b"\0")
        return completed

    monkeypatch.setattr(extract_local_audio, "_run_ffmpeg", run_then_touch)
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output)
    assert caught.value.reason_code == "recording_changed"
    assert not output.exists()
    assert _staged(tmp_path) == []


def test_an_in_place_rewrite_that_restores_the_mtime_is_refused(
    tmp_path, extract_local_audio, monkeypatch
):
    """Same size, same inode, same mtime: only the ctime shows the rewrite."""
    recording = _recording(tmp_path / "videos")
    output = tmp_path / "talk.m4a"
    real_run = extract_local_audio._run_ffmpeg

    def run_then_rewrite(command, timeout_seconds, *, held):
        completed = real_run(command, timeout_seconds, held=held)
        before = recording.stat()
        with recording.open("r+b") as handle:
            handle.seek(before.st_size // 2)
            handle.write(b"\xff" * 64)
        os.utime(recording, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = recording.stat()
        assert (after.st_size, after.st_mtime_ns) == (
            before.st_size,
            before.st_mtime_ns,
        )
        return completed

    monkeypatch.setattr(extract_local_audio, "_run_ffmpeg", run_then_rewrite)
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output)
    assert caught.value.reason_code == "recording_changed"
    assert not output.exists()
    assert _staged(tmp_path) == []


def test_ffmpeg_reads_the_held_recording_not_a_swapped_path(
    tmp_path, extract_local_audio, monkeypatch
):
    """A link repointed for the run and restored after leaves no stat trace."""
    original = _recording(tmp_path / "videos", seconds=3)
    other = _recording(tmp_path / "other", seconds=8)
    recording = tmp_path / "link.mp4"
    recording.symlink_to(original)
    output = tmp_path / "talk.m4a"
    real_run = extract_local_audio._run_ffmpeg

    def _point(target):
        staged_link = tmp_path / "link.next"
        staged_link.symlink_to(target)
        os.replace(staged_link, recording)

    def swap_for_the_run(command, timeout_seconds, *, held):
        _point(other)
        try:
            return real_run(command, timeout_seconds, held=held)
        finally:
            _point(original)

    monkeypatch.setattr(extract_local_audio, "_run_ffmpeg", swap_for_the_run)
    result = extract_local_audio.extract(recording, output)

    # The 3-second recording it held, never the 8-second one the path named.
    assert result["duration_seconds"] < 5


def test_a_recording_renamed_over_mid_run_is_refused(
    tmp_path, extract_local_audio, monkeypatch
):
    """Unlinking the held file moves its ctime, so the swap never installs."""
    recording = _recording(tmp_path / "videos", seconds=3)
    other = _recording(tmp_path / "other", seconds=8)
    output = tmp_path / "talk.m4a"
    real_run = extract_local_audio._run_ffmpeg

    def swap_then_run(command, timeout_seconds, *, held):
        os.replace(other, recording)
        return real_run(command, timeout_seconds, held=held)

    monkeypatch.setattr(extract_local_audio, "_run_ffmpeg", swap_then_run)
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output)
    assert caught.value.reason_code == "recording_changed"
    assert not output.exists()


def test_an_ffmpeg_error_is_refused_even_when_it_exits_zero(
    tmp_path, extract_local_audio, monkeypatch
):
    """ffmpeg can log a decode error, drop the audio, and still exit 0."""
    recording = _recording(tmp_path / "videos")
    real = shutil.which("ffmpeg")
    assert real is not None
    fake = tmp_path / "noisy-bin" / "ffmpeg"
    fake.parent.mkdir()
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'"{real}" "$@"\n'
        "echo '[aac @ 0x1] Error decoding frame' >&2\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{fake.parent}{os.pathsep}{os.environ['PATH']}")
    output = tmp_path / "talk.m4a"
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output)
    assert caught.value.reason_code == "extraction_failed"
    assert "Error decoding frame" in str(caught.value)
    assert not output.exists()
    assert _staged(tmp_path) == []


def test_a_rerun_after_a_failed_directory_sync_completes_it(
    tmp_path, extract_local_audio, monkeypatch
):
    """The first run installs and fails to sync; the identical rerun syncs."""
    recording = _recording(tmp_path / "videos")
    output = tmp_path / "talk.m4a"
    real_fsync = os.fsync
    synced: list[int] = []

    def failing_fsync(_descriptor):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(extract_local_audio.os, "fsync", failing_fsync)
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output)
    assert caught.value.reason_code == "output_write_failed"
    assert output.exists()

    def recording_fsync(descriptor):
        synced.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(extract_local_audio.os, "fsync", recording_fsync)
    result = extract_local_audio.extract(recording, output)

    assert result["written"] is False
    assert synced, "the unchanged rerun must sync the output's directory"


@pytest.mark.parametrize("suffix", [".m4a", ".wav"])
@pytest.mark.parametrize("fraction", [0.3, 0.6, 0.9, 0.99])
def test_an_extraction_stopped_by_the_ceiling_is_never_installed(
    tmp_path, extract_local_audio, suffix, fraction
):
    """ffmpeg's -fs stop leaves the file at or over the limit, never under it."""
    recording = _recording(tmp_path / "videos", seconds=10)
    whole = extract_local_audio.extract(recording, tmp_path / f"whole{suffix}")
    ceiling = int(int(whole["size_bytes"]) * fraction)
    output = tmp_path / f"talk{suffix}"
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output, max_output_bytes=ceiling)
    assert caught.value.reason_code == "output_over_ceiling"
    assert not output.exists()


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


def test_a_volume_without_hard_links_installs_by_exclusive_copy(
    tmp_path, extract_local_audio, monkeypatch
):
    recording = _recording(tmp_path / "videos")
    output = tmp_path / "talk.m4a"

    def no_links(_source, _target):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(extract_local_audio.os, "link", no_links)
    result = extract_local_audio.extract(recording, output)

    assert result["written"] is True
    assert extract_local_audio._sha256(output) == result["media_sha256"]
    assert _staged(tmp_path) == []


def test_a_file_that_appears_before_the_fallback_copy_is_never_replaced(
    tmp_path, extract_local_audio, monkeypatch
):
    recording = _recording(tmp_path / "videos")
    output = tmp_path / "talk.m4a"

    def racer_then_no_links(_source, _target):
        output.write_bytes(b"a racing writer's audio")
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(extract_local_audio.os, "link", racer_then_no_links)
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output)

    assert caught.value.reason_code == "output_exists"
    assert output.read_bytes() == b"a racing writer's audio"
    assert _staged(tmp_path) == []


@pytest.mark.parametrize(
    "reason_code,advice,not_advice",
    [
        ("media_parser_rejected", ".wav output", None),
        ("media_no_usable_audio_stream", ".wav output", None),
        ("media_dependency_unavailable", "install ffmpeg", ".wav"),
        ("media_worker_timeout", "less loaded", ".wav"),
        ("media_size_limit", "smallest output", ".wav"),
        ("media_something_new", "local_media_contract.py", ".wav"),
    ],
)
def test_a_probe_refusal_names_the_action_its_reason_calls_for(
    tmp_path, extract_local_audio, monkeypatch, reason_code, advice, not_advice
):
    recording = _recording(tmp_path / "videos")

    def refusing_probe(_path, *, trusted_root=None):
        raise extract_local_audio.LocalMediaError(reason_code)

    monkeypatch.setattr(extract_local_audio, "probe_local_media", refusing_probe)
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, tmp_path / "talk.m4a")

    assert caught.value.reason_code == "output_unusable"
    assert reason_code in str(caught.value)
    assert advice in str(caught.value)
    if not_advice is not None:
        assert not_advice not in str(caught.value)
    assert _staged(tmp_path) == []


def test_a_filesystem_failure_is_a_structured_refusal(
    tmp_path, extract_local_audio, monkeypatch
):
    recording = _recording(tmp_path / "videos")
    output = tmp_path / "talk.m4a"
    output.write_bytes(b"existing audio")

    def unreadable(_path):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(extract_local_audio, "_sha256", unreadable)
    with pytest.raises(extract_local_audio.ExtractionError) as caught:
        extract_local_audio.extract(recording, output)

    assert caught.value.reason_code == "io_failed"
    assert "Permission denied" in str(caught.value)
    assert output.read_bytes() == b"existing audio"
    assert _staged(tmp_path) == []


def test_an_unexpected_failure_leaves_stdout_empty_and_exits_3(
    tmp_path, extract_local_audio, monkeypatch, capsys
):
    def broken(*_args, **_kwargs):
        raise RuntimeError("/private/host/path should never be printed")

    monkeypatch.setattr(extract_local_audio, "extract", broken)
    code = extract_local_audio.run_cli(
        ["--recording", str(tmp_path / "r.mp4"), "--output", str(tmp_path / "a.m4a")]
    )

    captured = capsys.readouterr()
    assert code == 3
    assert captured.out == ""
    document = json.loads(captured.err.splitlines()[0])
    assert document["error"] == "audio_extraction_unexpected_failure"
    assert document["error_type"] == "RuntimeError"
    assert "/private/host/path" not in captured.err


@pytest.mark.parametrize(
    "stderr_tail,reason,advice",
    [
        (
            "av_interleaved_write_frame(): No space left on device",
            "io_failed",
            "free space",
        ),
        ("talk.m4a: Permission denied", "io_failed", "permissions"),
        (
            "Stream map '0:a:0' matches no streams.",
            "recording_has_no_audio",
            "no audio",
        ),
        (
            "Could not find tag for codec opus in stream #0, codec not currently "
            "supported in container",
            "extraction_failed",
            ".wav output",
        ),
        ("moov atom not found", "extraction_failed", "read ffmpeg's message"),
    ],
    ids=["disk-full", "permission", "no-audio", "codec-container", "unknown"],
)
def test_an_ffmpeg_failure_names_the_repair_it_needs(
    extract_local_audio, stderr_tail, reason, advice
):
    got_reason, got_advice = extract_local_audio.classify_ffmpeg_failure(
        stderr_tail, ".m4a"
    )
    assert got_reason == reason
    assert advice in got_advice
    if reason != "extraction_failed" or advice != ".wav output":
        assert ".wav" not in got_advice


@pytest.mark.parametrize(
    "arguments",
    [("--recording", "a.mp4"), ("--output", "a.m4a"), ("--bogus", "x")],
    ids=["no-output", "no-recording", "unknown-flag"],
)
def test_bad_arguments_get_the_json_verdict(arguments):
    code, payload, stderr = _run(*arguments)
    assert code == 2
    assert payload["ok"] is False
    assert payload["reason_code"] == "invalid_arguments"
    assert payload["error"] in stderr


def test_help_still_prints_and_exits_cleanly():
    completed = subprocess.run(
        [sys.executable, SCRIPT, "--help"], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0
    assert "--recording" in completed.stdout


def test_a_relative_output_is_resolved_against_the_working_directory(tmp_path):
    recording = _recording(tmp_path / "videos")
    (tmp_path / "recordings").mkdir()
    completed = subprocess.run(
        [
            sys.executable,
            SCRIPT,
            "--recording",
            str(recording),
            "--output",
            "recordings/talk.m4a",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["output"] == str(tmp_path / "recordings" / "talk.m4a")
    assert (tmp_path / "recordings" / "talk.m4a").is_file()

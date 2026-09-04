"""Full-decode integrity, independent stream extents, and failure boundaries."""

import copy
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


SCRIPTS = Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts"
sys.path.insert(0, str(SCRIPTS))
integrity = importlib.import_module("video_integrity")


def _metadata(*, duration="10", video_duration="10", audio_duration="10"):
    return {
        "format": {"duration": duration, "start_time": "0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "duration": video_duration,
                "avg_frame_rate": "30/1",
                "disposition": {"attached_pic": 0},
            },
            {"index": 1, "codec_type": "audio", "duration": audio_duration},
        ],
    }


def _progress(seconds):
    return f"out_time_us={int(seconds * 1_000_000)}\nprogress=end\n".encode()


@pytest.fixture
def recording(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "install ffmpeg; real integrity tests may not be skipped"
    output = tmp_path / "recording.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "10",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return output


def test_complete_recording_has_independent_decoded_stream_receipts(recording):
    before = recording.read_bytes()
    result = integrity.verify_video_integrity(recording)
    assert result["ok"] is True
    assert result["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert result["source_size_bytes"] == len(before)
    assert {stream["kind"] for stream in result["streams"]} == {"video", "audio"}
    assert all(stream["decoded_seconds"] >= 9.9 for stream in result["streams"])
    assert recording.read_bytes() == before


def test_late_nal_damage_passes_metadata_but_fails_full_decode(recording):
    ffprobe = shutil.which("ffprobe")
    assert ffprobe, "install ffprobe; corruption regression must run"
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_packets",
            "-show_entries",
            "packet=pts_time,pos,size",
            "-of",
            "json",
            str(recording),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    packets = json.loads(result.stdout)["packets"]
    packet = next(item for item in packets if float(item["pts_time"]) >= 8)
    data = bytearray(recording.read_bytes())
    position = int(packet["pos"])
    data[position : position + 4] = b"\xff\xff\xff\xf0"
    recording.write_bytes(data)
    # Header/container inspection is not decode verification: the prior gate
    # accepts this file even though an interior H.264 packet is damaged.
    assert integrity.video.probe_video_artifact(recording).duration_seconds == 10
    with pytest.raises(integrity.SupervisorError, match="integrity_decode_failed"):
        integrity.verify_video_integrity(recording)
    assert recording.read_bytes() == data


def _fake_tools(monkeypatch, metadata, extents):
    outputs = iter([json.dumps(metadata).encode(), *map(_progress, extents)])
    monkeypatch.setattr(integrity.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(integrity, "_run_tool", lambda command: next(outputs))


def test_intact_audio_cannot_hide_short_video(monkeypatch):
    _fake_tools(monkeypatch, _metadata(), [4, 10])
    with pytest.raises(integrity.VideoIntegrityError) as caught:
        integrity.decode_recording(Path("recording.mp4"))
    assert caught.value.code == "integrity_duration_gap"
    assert caught.value.details["kind"] == "video"
    assert caught.value.details["decoded_seconds"] == 4


def test_decoded_extent_beyond_declared_stream_is_rejected(monkeypatch):
    _fake_tools(monkeypatch, _metadata(), [14, 10])
    with pytest.raises(integrity.VideoIntegrityError, match="duration_mismatch"):
        integrity.decode_recording(Path("recording.mp4"))


def test_intact_video_cannot_hide_short_audio(monkeypatch):
    _fake_tools(monkeypatch, _metadata(), [10, 4])
    with pytest.raises(integrity.VideoIntegrityError) as caught:
        integrity.decode_recording(Path("recording.mp4"))
    assert caught.value.code == "integrity_duration_gap"
    assert caught.value.details["kind"] == "audio"


def test_short_declared_streams_cannot_hide_container_gap(monkeypatch):
    _fake_tools(monkeypatch, _metadata(video_duration="4", audio_duration="4"), [4, 4])
    with pytest.raises(
        integrity.VideoIntegrityError, match="integrity_container_duration_gap"
    ):
        integrity.decode_recording(Path("recording.mp4"))


def test_intentionally_shorter_video_and_audio_outro_are_valid(monkeypatch):
    _fake_tools(monkeypatch, _metadata(video_duration="8"), [8, 10])
    assert len(integrity.decode_recording(Path("recording.mp4"))["streams"]) == 2


def test_nonzero_start_time_and_rounding_are_valid(monkeypatch):
    metadata = _metadata()
    metadata["format"]["start_time"] = "20"
    metadata["streams"][0].update({"start_time": "22", "duration": "8"})
    metadata["streams"][1]["start_time"] = "20"
    _fake_tools(monkeypatch, metadata, [7.967, 10])
    result = integrity.decode_recording(Path("recording.mp4"))
    assert result["streams"][0]["start_offset_seconds"] == 2


@pytest.mark.parametrize("value", [None, {}, [], True, "NaN", "inf", "-2", "0"])
def test_invalid_container_duration_is_not_verified(value):
    with pytest.raises(integrity.VideoIntegrityError, match="metadata_invalid"):
        integrity.stream_specs(_metadata(duration=value))


@pytest.mark.parametrize(
    "change",
    [
        {"index": True},
        {"index": -1},
        {"codec_type": []},
        {"disposition": []},
        {"start_time": "nan"},
    ],
)
def test_invalid_stream_metadata_fails_closed(change):
    metadata = _metadata()
    metadata["streams"][0].update(change)
    with pytest.raises(integrity.VideoIntegrityError):
        integrity.stream_specs(metadata)


def test_cover_art_and_subtitles_are_not_treated_as_video():
    metadata = _metadata()
    metadata["streams"][0]["disposition"]["attached_pic"] = 1
    metadata["streams"].append({"index": 2, "codec_type": "subtitle"})
    with pytest.raises(integrity.VideoIntegrityError, match="no_video_stream"):
        integrity.stream_specs(metadata)


def test_duplicate_stream_ids_are_rejected():
    metadata = _metadata()
    metadata["streams"].append(copy.deepcopy(metadata["streams"][0]))
    with pytest.raises(integrity.VideoIntegrityError, match="metadata_invalid"):
        integrity.stream_specs(metadata)


@pytest.mark.parametrize(
    "output",
    [
        b"",
        b"out_time_us=10000000\nprogress=continue\n",
        b"out_time_us=N/A\nprogress=end\n",
        b"out_time_us=NaN\nprogress=end\n",
        b"out_time_us=-1\nprogress=end\n",
        b"out_time_us=0\nprogress=end\n",
        b"out_time_us=10000000\nprogress=end\ngarbage",
        b"\xff",
        b"out_time_us=10000000\nprogress=end\nprogress=end\n",
    ],
)
def test_incomplete_or_invalid_progress_never_proves_integrity(output):
    with pytest.raises(integrity.VideoIntegrityError):
        integrity.decoded_extent(output)


def test_only_final_extent_is_authoritative():
    assert (
        integrity.decoded_extent(
            b"out_time_us=1000000\nprogress=continue\nout_time_us=2000000\nprogress=end\n"
        )
        == 2
    )


@pytest.mark.parametrize(
    "diagnostic",
    [
        "Invalid NAL unit size",
        "Error splitting the input into NAL units",
        "missing picture",
        "a future decoder error never seen before",
    ],
)
def test_any_error_diagnostic_rejects_even_with_zero_exit(diagnostic):
    with pytest.raises(integrity.VideoIntegrityError) as caught:
        integrity._run_tool(
            [sys.executable, "-c", f"import sys; sys.stderr.write({diagnostic!r})"]
        )
    assert caught.value.code == "integrity_decode_failed"
    assert diagnostic not in json.dumps(caught.value.details)
    assert caught.value.details["diagnostics"]["byte_count"] == len(diagnostic)


def test_nonzero_exit_without_stderr_is_rejected():
    with pytest.raises(integrity.VideoIntegrityError, match="decode_failed"):
        integrity._run_tool([sys.executable, "-c", "raise SystemExit(7)"])


def test_tool_output_is_bounded():
    with pytest.raises(integrity.VideoIntegrityError, match="output_limit"):
        integrity._run_tool(
            [
                sys.executable,
                "-c",
                f"import sys; sys.stdout.write('x' * {integrity.TOOL_OUTPUT_BYTES + 1})",
            ]
        )


def test_missing_tool_is_actionable(monkeypatch):
    monkeypatch.setattr(integrity.shutil, "which", lambda name: None)
    with pytest.raises(integrity.VideoIntegrityError) as caught:
        integrity.decode_recording(Path("recording.mp4"))
    assert caught.value.details == {"dependency": "ffmpeg"}
    assert "retry" in str(caught.value)


@pytest.mark.parametrize(
    "timeout", [True, "10", 0, -1, float("nan"), float("inf"), 21601]
)
def test_invalid_deadline_rejected_before_reading(timeout, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid timeout read the recording")

    monkeypatch.setattr(integrity.video, "probe_video_artifact", forbidden)
    with pytest.raises(integrity.VideoIntegrityError, match="timeout_invalid"):
        integrity.verify_video_integrity("missing.mp4", timeout_seconds=timeout)


def test_generation_change_between_probe_and_decode_is_rejected(recording, monkeypatch):
    run = integrity.run_authenticated_worker

    def replaced(*args, **kwargs):
        recording.write_bytes(recording.read_bytes() + b"changed")
        return run(*args, **kwargs)

    monkeypatch.setattr(integrity, "run_authenticated_worker", replaced)
    with pytest.raises(integrity.SupervisorError, match="generation_changed"):
        integrity.verify_video_integrity(recording)


def test_decode_deadline_is_enforced(recording):
    with pytest.raises(integrity.SupervisorError, match="worker_timeout"):
        integrity.verify_video_integrity(recording, timeout_seconds=0.001)


def test_cli_reports_missing_input_as_one_json_object(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "video_integrity.py"),
            str(tmp_path / "missing.mp4"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False
    assert "do not use this recording" in result.stderr


@pytest.mark.parametrize(
    "arguments,code", [([], 2), (["--help"], 0), (["--unknown"], 2)]
)
def test_usage_and_help_are_structured(arguments, code):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "video_integrity.py"), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == code
    assert json.loads(result.stdout)["usage"] == integrity.USAGE


def test_unexpected_failure_reports_json_without_exception_text(monkeypatch, capsys):
    def explode():
        raise RuntimeError("private parser output")

    monkeypatch.setattr(integrity, "main", explode)
    monkeypatch.setattr(sys, "argv", ["video_integrity.py"])
    assert integrity.run_cli() == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["code"] == "integrity_unexpected_failure"
    assert "private parser output" not in captured.out + captured.err


def test_interrupt_is_not_swallowed(monkeypatch):
    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(integrity, "main", interrupt)
    monkeypatch.setattr(sys, "argv", ["video_integrity.py"])
    with pytest.raises(KeyboardInterrupt):
        integrity.run_cli()

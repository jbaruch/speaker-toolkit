"""Generic-media admission, worker boundaries, generation races and cleanup."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from conftest import SCRIPTS_VI, _import_script


@pytest.fixture
def media():
    return _import_script(
        Path(SCRIPTS_VI) / "local_media_evidence.py", "local_media_evidence"
    )


def _audio(path, codec):
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "1",
            "-c:a",
            codec,
            "-y",
            str(path),
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return path.read_bytes()


@pytest.mark.parametrize(
    "suffix,codec,container",
    [
        (".mp3", "libmp3lame", "mp3"),
        (".wav", "pcm_s16le", "wav"),
        (".m4a", "aac", "iso_bmff"),
        (".mp4", "aac", "iso_bmff"),
        (".mov", "aac", "iso_bmff"),
        (".mkv", "flac", "matroska_webm"),
        (".webm", "libopus", "matroska_webm"),
    ],
)
def test_real_worker_accepts_audio_only_and_binds_exact_bytes(
    media, tmp_path, suffix, codec, container
):
    path = tmp_path / f"speech{suffix}"
    raw = _audio(path, codec)
    result = media.probe_local_media(path.name, trusted_root=tmp_path)
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.source_size_bytes == len(raw)
    assert result.generation == media.FileGeneration.from_stat(path.lstat())
    assert result.container_family == container
    assert result.duration_seconds == pytest.approx(1.0, abs=0.15)
    assert result.audio_stream_count == 1
    assert result.video_stream_count == 0
    assert result.stream_count == 1
    media.check_media_generation(path.name, result, trusted_root=tmp_path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "case,reason",
    [
        ("empty", "media_size_limit"),
        ("corrupt", "media_parser_rejected"),
        ("wrong_suffix", "media_invalid_container"),
        ("truncated", "media_parser_rejected"),
        ("directory", "media_artifact_unavailable"),
        ("missing", "media_artifact_unavailable"),
    ],
)
def test_real_worker_rejects_invalid_media_without_exposing_paths(
    media, tmp_path, case, reason
):
    path = tmp_path / "private-recording.mp3"
    if case == "empty":
        path.touch()
    elif case == "corrupt":
        path.write_bytes(b"not an audio container")
    elif case == "wrong_suffix":
        wav = tmp_path / "source.wav"
        path.write_bytes(_audio(wav, "pcm_s16le"))
    elif case == "truncated":
        path.write_bytes(_audio(path, "libmp3lame")[:10])
    elif case == "directory":
        path.mkdir()
    with pytest.raises(media.LocalMediaError) as caught:
        media.probe_local_media(path.name, trusted_root=tmp_path)
    assert caught.value.reason_code == reason
    assert str(path) not in str(caught.value)


def test_real_worker_refuses_a_recording_without_audio(media, tmp_path):
    path = tmp_path / "silent.mp4"
    created = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=2",
            "-t",
            "1",
            "-an",
            "-c:v",
            "mpeg4",
            str(path),
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert created.returncode == 0, created.stderr.decode("utf-8", errors="replace")
    with pytest.raises(media.LocalMediaError, match="media_no_audio_stream"):
        media.probe_local_media(path, trusted_root=tmp_path)


@pytest.mark.parametrize("path", ["../private.mp3", "bad\0path.mp3", "speech.avi"])
def test_invalid_locator_does_not_launch_a_worker(media, tmp_path, monkeypatch, path):
    monkeypatch.setattr(
        media,
        "run_authenticated_worker",
        lambda *a, **kw: pytest.fail("invalid locator launched worker"),
    )
    with pytest.raises(media.LocalMediaError):
        media.probe_local_media(path, trusted_root=tmp_path)


@pytest.mark.parametrize("attribute", [0x1000, 0x40000, 0x400000, 0x400])
def test_cloud_flags_block_all_byte_io(media, tmp_path, monkeypatch, attribute):
    generation = media.FileGeneration(
        100, 1, 2, 3, 4, stat.S_IFREG | 0o600, file_attributes=attribute
    )
    receipt = media.ArtifactMetadataReceipt(generation, None, None)
    monkeypatch.setattr(media, "inspect_metadata_generation", lambda *a, **kw: receipt)
    monkeypatch.setattr(
        media.os, "open", lambda *a, **kw: pytest.fail("cloud placeholder opened")
    )
    with pytest.raises(media.LocalMediaError):
        media._inspect(tmp_path / "speech.mp3", None)


def test_dataless_mac_metadata_blocks_before_copy(media, tmp_path, monkeypatch):
    # Inject the platform-independent interpretation; do not depend on runner OS.
    import artifact_metadata

    generation = media.FileGeneration(
        100, 1, 2, 3, 4, stat.S_IFREG | 0o600, flags=0x40000000
    )
    unavailable = artifact_metadata.ArtifactAvailability.from_generation(
        generation, macos_dataless_flag=0x40000000
    )
    monkeypatch.setattr(
        artifact_metadata.ArtifactAvailability,
        "from_generation",
        lambda value: unavailable,
    )
    receipt = media.ArtifactMetadataReceipt(generation, None, None)
    monkeypatch.setattr(media, "inspect_metadata_generation", lambda *a, **kw: receipt)
    monkeypatch.setattr(
        media.os, "open", lambda *a, **kw: pytest.fail("dataless source opened")
    )
    with pytest.raises(
        media.LocalMediaError, match="media_cloud_placeholder_unavailable"
    ):
        media._inspect(tmp_path / "speech.mp3", None)


@pytest.mark.parametrize(
    "failure,reason",
    [
        ("worker_timeout", "media_worker_timeout"),
        ("worker_memory_limit_exceeded", "media_worker_resource_limit"),
        ("worker_process_limit_exceeded", "media_worker_resource_limit"),
        ("worker_input_limit_exceeded", "media_worker_resource_limit"),
        ("worker_output_limit_exceeded", "media_worker_resource_limit"),
        ("worker_diagnostic_limit_exceeded", "media_worker_resource_limit"),
        ("worker_generation_changed", "media_generation_changed"),
        ("worker_cleanup_failed", "media_cleanup_failed"),
        ("worker_exit", "media_worker_failed"),
        ("worker_monitor_unavailable", "media_worker_failed"),
        ("worker_response_authentication_failed", "media_worker_failed"),
    ],
)
def test_supervisor_failure_mapping_is_closed_and_redacted(
    media, monkeypatch, failure, reason
):
    def fail(*args, **kwargs):
        raise media.SupervisorError(failure, {"private": "/private/recording.mp3"})

    monkeypatch.setattr(media, "run_authenticated_worker", fail)
    with pytest.raises(media.LocalMediaError) as caught:
        media._invoke_worker(
            media.METADATA_OPERATION, {}, {}, media.MEDIA_METADATA_LIMITS
        )
    assert caught.value.reason_code == reason
    assert "/private/recording.mp3" not in str(caught.value)


@pytest.mark.parametrize(
    "failure", ["worker_timeout", "worker_exit", "worker_cleanup_failed"]
)
def test_owner_removes_partial_workspace_after_worker_failure(
    media, tmp_path, monkeypatch, failure
):
    path = tmp_path / "speech.wav"
    _audio(path, "pcm_s16le")
    original = media.run_authenticated_worker
    workspaces = []

    def invoke(command, operation, expected, payload, limits, **kwargs):
        if operation == media.PROBE_OPERATION:
            workspace = Path(payload["workspace"]["path"])
            workspaces.append(workspace)
            partial = workspace / "source.wav"
            partial.write_bytes(b"partial private copy")
            partial.chmod(stat.S_IREAD)
            raise media.SupervisorError(failure)
        return original(command, operation, expected, payload, limits, **kwargs)

    monkeypatch.setattr(media, "run_authenticated_worker", invoke)
    with pytest.raises(media.LocalMediaError):
        media.probe_local_media(path, trusted_root=tmp_path)
    assert len(workspaces) == 1
    assert not workspaces[0].exists()


def test_workspace_is_fresh_private_and_cleanup_is_not_suppressed(media, monkeypatch):
    from tempfile import TemporaryDirectory

    original = TemporaryDirectory.cleanup
    workspaces = []
    directories = []

    def directory_factory(**kwargs):
        directory = TemporaryDirectory(**kwargs)
        directories.append(directory)
        return directory

    monkeypatch.setattr(media.tempfile, "TemporaryDirectory", directory_factory)

    def cannot_cleanup(self):
        raise OSError("private cleanup failure")

    with pytest.raises(media.LocalMediaError, match="media_cleanup_failed"):
        with media.private_media_workspace() as workspace:
            path = Path(workspace["path"])
            workspaces.append(path)
            assert list(path.iterdir()) == []
            if os.name != "nt":
                assert stat.S_IMODE(path.stat().st_mode) == 0o700
            monkeypatch.setattr(TemporaryDirectory, "cleanup", cannot_cleanup)
    monkeypatch.setattr(TemporaryDirectory, "cleanup", original)
    assert len(workspaces) == 1
    original(directories[0])
    assert not workspaces[0].exists()


@pytest.mark.parametrize("cover_art", [False, True])
def test_real_worker_distinguishes_delivery_video_from_cover_art(
    media, tmp_path, cover_art
):
    path = tmp_path / ("cover-art.m4a" if cover_art else "delivery.mp4")
    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=160x90:r=2",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=16000",
        "-t",
        "1",
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:a",
        "aac",
        "-c:v",
        "mjpeg" if cover_art else "mpeg4",
    ]
    if cover_art:
        command += ["-frames:v", "1", "-disposition:v", "attached_pic"]
    created = subprocess.run(
        command + [str(path)], capture_output=True, check=False, timeout=30
    )
    assert created.returncode == 0, created.stderr.decode("utf-8", errors="replace")
    probe = media.probe_local_media(path, trusted_root=tmp_path)
    assert probe.audio_stream_count == 1
    assert probe.video_stream_count == int(not cover_art)
    assert probe.attached_picture_count == int(cover_art)
    assert probe.stream_count == 2


@pytest.mark.parametrize("change", ["replace", "mutate", "truncate"])
def test_source_generation_races_reject_before_any_probe(
    media, tmp_path, monkeypatch, change
):
    path = tmp_path / "speech.wav"
    _audio(path, "pcm_s16le")
    before = media._inspect(path, tmp_path)
    if change == "replace":
        replacement = tmp_path / "replacement.wav"
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
    elif change == "mutate":
        path.write_bytes(b"different" + path.read_bytes()[9:])
    else:
        path.write_bytes(b"short")
    monkeypatch.setattr(
        media, "_run_ffprobe", lambda *a: pytest.fail("stale source reached ffprobe")
    )
    with media.private_media_workspace() as workspace:
        with pytest.raises(media.LocalMediaError, match="media_generation_changed"):
            media._probe(path, tmp_path, before, Path(workspace["path"]))


@pytest.mark.parametrize("target", ["source", "snapshot"])
def test_probe_rejects_mutation_during_parser(media, tmp_path, monkeypatch, target):
    path = tmp_path / "speech.wav"
    raw = _audio(path, "pcm_s16le")
    before = media._inspect(path, tmp_path)

    def probe(snapshot):
        selected = path if target == "source" else snapshot
        selected.chmod(stat.S_IREAD | stat.S_IWRITE)
        selected.write_bytes(b"changed" + raw[7:])
        return json.dumps(
            {
                "format": {"format_name": "wav", "duration": "1"},
                "streams": [
                    {
                        "codec_type": "audio",
                        "codec_name": "pcm_s16le",
                        "channels": 1,
                        "sample_rate": "16000",
                    }
                ],
            }
        ).encode(), media.DiagnosticReceipt.empty()

    monkeypatch.setattr(media, "_run_ffprobe", probe)
    with media.private_media_workspace() as workspace:
        with pytest.raises(media.LocalMediaError, match="media_generation_changed"):
            media._probe(path, tmp_path, before, Path(workspace["path"]))


@pytest.mark.parametrize(
    "program,reason",
    [
        (
            "import sys; sys.stdout.buffer.write(b'x' * 262145)",
            "media_ffprobe_stdout_limit",
        ),
        (
            "import sys; sys.stderr.buffer.write(b'x' * 65537)",
            "media_ffprobe_stderr_limit",
        ),
        (
            "import sys; sys.stderr.write('/private/source.wav')",
            "media_parser_repair_required",
        ),
        ("raise SystemExit(3)", "media_parser_rejected"),
    ],
)
def test_parser_output_limits_and_nonzero_are_typed(
    media, tmp_path, monkeypatch, program, reason
):
    real_popen = subprocess.Popen
    monkeypatch.setattr(media.shutil, "which", lambda name: sys.executable)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda command, **kwargs: real_popen([sys.executable, "-c", program], **kwargs),
    )
    with pytest.raises(media.LocalMediaError) as caught:
        media._run_ffprobe(tmp_path / "speech.wav")
    assert caught.value.reason_code == reason
    assert "/private/source.wav" not in str(caught.value)


@pytest.mark.parametrize(
    "raw", [b'{"format":{},"format":{}}', b'{"value":NaN}', b"\xff", b"[]"]
)
def test_malformed_parser_json_is_not_evidence(media, tmp_path, monkeypatch, raw):
    path = tmp_path / "speech.wav"
    _audio(path, "pcm_s16le")
    before = media._inspect(path, tmp_path)
    monkeypatch.setattr(
        media, "_run_ffprobe", lambda path: (raw, media.DiagnosticReceipt.empty())
    )
    with media.private_media_workspace() as workspace:
        with pytest.raises(media.LocalMediaError, match="media_parser_rejected"):
            media._probe(path, tmp_path, before, Path(workspace["path"]))


def test_generation_recheck_rejects_replaced_source(media, tmp_path):
    path = tmp_path / "speech.wav"
    _audio(path, "pcm_s16le")
    probe = media.probe_local_media(path, trusted_root=tmp_path)
    path.write_bytes(b"replaced source")
    with pytest.raises(media.LocalMediaError, match="media_generation_changed"):
        media.check_media_generation(path, probe, trusted_root=tmp_path)

"""Real FFmpeg sampling and pure bound checks, no network or speech model."""

import hashlib
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from conftest import SCRIPTS_VI, _import_script


@pytest.fixture
def sampler():
    return _import_script(
        Path(SCRIPTS_VI) / "local_media_sampling.py", "local_media_sampling"
    )


@pytest.fixture
def media(tmp_path):
    path = tmp_path / "source.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x01\x00" * 4000 + b"\x02\x00" * 8000 + b"\x03\x00" * 4000)
    return path


def test_real_sample_binds_only_requested_interval_and_preserves_source(
    sampler, media, tmp_path
):
    before = media.read_bytes()
    work = tmp_path / "private"
    work.mkdir()
    clip = sampler.extract_speech_clip(media, work, start=0.25, duration=0.5)
    assert clip.duration_seconds == 0.5
    assert clip.sha256 == hashlib.sha256(clip.path.read_bytes()).hexdigest()
    with wave.open(str(clip.path), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getframerate() == 16000
        assert audio.getnframes() == 8000
        assert audio.readframes(8000) == b"\x02\x00" * 8000
    assert media.read_bytes() == before


@pytest.mark.parametrize(
    "start,duration,source",
    [
        (True, 1, 5),
        (0, True, 5),
        (0, 1, True),
        (-1, 1, 5),
        (5, 1, 5),
        (4, 2, 5),
        (0, 0, 5),
        (0, 1201, 3600),
        (0, 1, 14401),
        (0, float("nan"), 5),
        (float("inf"), 1, 5),
        pytest.param(0, 1, 10**10000, id="huge-source-duration"),
    ],
)
def test_bad_windows_refuse_without_decoding(sampler, start, duration, source):
    with pytest.raises(sampler.LocalMediaError, match="whisper_sample_window_invalid"):
        sampler.validate_sample_window(start, duration, source)


@pytest.mark.parametrize(
    "code,diagnostics,size,reason",
    [
        (1, 0, 16000, "whisper_sample_decode_failed"),
        (0, 10, 16000, "whisper_sample_decode_failed"),
        (0, 0, 0, "whisper_sample_duration_mismatch"),
        (0, 0, 15999, "whisper_sample_duration_mismatch"),
        (0, 0, 8000, "whisper_sample_duration_mismatch"),
    ],
)
def test_decoder_error_or_partial_output_never_becomes_a_clip(
    sampler, media, tmp_path, monkeypatch, code, diagnostics, size, reason
):
    monkeypatch.setattr(
        sampler,
        "run_media_tool",
        lambda *a, **k: SimpleNamespace(
            returncode=code,
            diagnostics=SimpleNamespace(byte_count=diagnostics),
            streamed_bytes=size,
        ),
    )
    with pytest.raises(sampler.LocalMediaError, match=reason):
        sampler.extract_speech_clip(media, tmp_path, start=0.25, duration=0.5)
    assert not (tmp_path / "sample.wav").exists()


def test_missing_decoder_is_actionable(sampler, media, tmp_path, monkeypatch):
    monkeypatch.setattr(sampler.shutil, "which", lambda name: None)
    with pytest.raises(sampler.LocalMediaError, match="media_dependency_unavailable"):
        sampler.extract_speech_clip(media, tmp_path, start=0.25, duration=0.5)

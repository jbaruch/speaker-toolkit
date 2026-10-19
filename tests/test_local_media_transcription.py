"""Bounded Whisper orchestration uses synthetic providers, never model downloads."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import wave

import pytest

from conftest import SCRIPTS_VI, _import_script


@pytest.fixture
def whisper():
    return _import_script(
        Path(SCRIPTS_VI) / "local_media_transcription.py", "local_media_transcription"
    )


@pytest.fixture
def speech_file(tmp_path):
    path = tmp_path / "private-speech.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 16000)
    return path


def _fake_provider_worker(
    whisper, tmp_path, monkeypatch, body, *, timeout=None, result_limit=None
):
    script = tmp_path / "synthetic_whisper_worker.py"
    script.write_text(
        "import sys\nfrom types import SimpleNamespace\nfrom dataclasses import replace\n"
        f"sys.path.insert(0, {str(Path(SCRIPTS_VI).resolve())!r})\n"
        "import local_media_transcription as owner\n"
        + (
            f"owner.MEDIA_WHISPER_LIMITS = replace(owner.MEDIA_WHISPER_LIMITS, max_output_bytes={result_limit})\n"
            if result_limit is not None
            else ""
        )
        + "def transcribe(path, **kwargs):\n"
        + "\n".join("    " + line for line in body.splitlines())
        + "\nsys.modules['mlx_whisper'] = SimpleNamespace(transcribe=transcribe)\n"
        + "raise SystemExit(owner._main())\n",
        encoding="utf-8",
    )
    real = whisper.run_authenticated_worker

    def invoke(command, operation, expected, payload, limits, **kwargs):
        command = [sys.executable, str(script), whisper.WORKER_FLAG]
        kwargs["immutable_process_identity"] = command[:2]
        if timeout is not None:
            limits = replace(limits, wall_seconds=timeout)
        return real(command, operation, expected, payload, limits, **kwargs)

    monkeypatch.setattr(whisper, "run_authenticated_worker", invoke)


def test_real_protocol_keeps_provider_stdout_out_of_result(
    whisper, speech_file, tmp_path, monkeypatch
):
    _fake_provider_worker(
        whisper,
        tmp_path,
        monkeypatch,
        "print('private provider chatter')\n"
        "return {'text': 'Synthetic speech', 'language': 'en', 'segments': [{'start': 0, 'end': 1, 'text': 'Synthetic speech', 'tokens': [1,2]}], 'private': path}",
    )
    probe, result = whisper.transcribe_local_media(
        speech_file, "synthetic-model", trusted_root=tmp_path
    )
    assert probe.audio_stream_count == 1
    assert result == {
        "text": "Synthetic speech",
        "language": "en",
        "segments": [{"start": 0, "end": 1, "text": "Synthetic speech"}],
    }
    assert "private" not in repr(result)


@pytest.mark.parametrize(
    "body,reason",
    [
        ("raise OSError('private/path provider failure')", "whisper_provider_failed"),
        ("return {'text': ''}", "whisper_result_invalid"),
        (
            "return {'text': 'Complete useful speech. ' + 'eda' * 220}",
            "whisper_repetitive_text",
        ),
        ("return {'text': 'x' * (2 * 1024 * 1024 + 1)}", "whisper_text_limit"),
        (
            "return {'text': 'speech', 'language': 'private/path'}",
            "whisper_language_invalid",
        ),
        (
            "return {'text': 'speech', 'segments': [None] * 20001}",
            "whisper_segment_limit",
        ),
        (
            "return {'text': 'speech', 'segments': [{'text': 'x' * 16385}]}",
            "whisper_segment_text_limit",
        ),
        ("raise ZeroDivisionError('private/path crash')", "whisper_worker_failed"),
        (
            "import sys\nsys.stderr.write('x' * 65537)\nreturn {'text': 'speech'}",
            "whisper_worker_resource_limit",
        ),
    ],
)
def test_real_worker_failure_is_closed_and_does_not_write_bundle(
    whisper, speech_file, tmp_path, monkeypatch, body, reason
):
    prior = {}
    for suffix in (".txt", ".quality.json", ".segments.json"):
        path = tmp_path / f"prior{suffix}"
        path.write_bytes(b"original " + suffix.encode())
        prior[path] = path.read_bytes()
    _fake_provider_worker(whisper, tmp_path, monkeypatch, body)
    with pytest.raises(whisper.LocalMediaError) as caught:
        whisper.transcribe_local_media(
            speech_file, "synthetic-model", trusted_root=tmp_path
        )
    assert caught.value.reason_code == reason
    assert "private/path" not in str(caught.value)
    assert {path: path.read_bytes() for path in prior} == prior


def test_real_worker_timeout_is_internal_and_killable(
    whisper, speech_file, tmp_path, monkeypatch
):
    _fake_provider_worker(
        whisper,
        tmp_path,
        monkeypatch,
        "import time\ntime.sleep(30)\nreturn {'text': 'speech'}",
        timeout=1.0,
    )
    with pytest.raises(whisper.LocalMediaError, match="whisper_worker_timeout"):
        whisper.transcribe_local_media(
            speech_file, "synthetic-model", trusted_root=tmp_path
        )


def test_worker_result_serialization_limit_is_preserved_as_resource_failure(
    whisper, speech_file, tmp_path, monkeypatch
):
    _fake_provider_worker(
        whisper,
        tmp_path,
        monkeypatch,
        "return {'text': 'speech ' * 1200}",
        result_limit=4096,
    )
    with pytest.raises(whisper.LocalMediaError, match="whisper_worker_resource_limit"):
        whisper.transcribe_local_media(
            speech_file, "synthetic-model", trusted_root=tmp_path
        )


def test_established_probe_reuse_does_not_probe_copy_or_hash_again(
    whisper, speech_file, tmp_path, monkeypatch
):
    import video_evidence
    from artifact_metadata import ArtifactAvailability

    probe = whisper.probe_local_media(speech_file, trusted_root=tmp_path)
    # VideoArtifactProbe is the existing owner's trusted in-memory boundary.
    # Its original video counts are distinct from the generic audio-only policy.
    video = video_evidence.VideoArtifactProbe(
        **{field: getattr(probe, field) for field in probe.__dataclass_fields__},
        availability=ArtifactAvailability.from_generation(probe.generation),
    )
    _fake_provider_worker(
        whisper, tmp_path, monkeypatch, "return {'text': 'Synthetic speech'}"
    )

    def forbidden(*args, **kwargs):
        pytest.fail("reused media facts performed a second probe/copy/hash")

    monkeypatch.setattr(whisper, "probe_local_media", forbidden)
    for name in (
        "probe_video_artifact",
        "_run_bounded_video_probe",
        "_copy_source_snapshot",
        "_digest_exact_generation",
    ):
        monkeypatch.setattr(video_evidence, name, forbidden)
    result_probe, result = whisper.transcribe_local_media(
        speech_file, "synthetic-model", probe=video, trusted_root=tmp_path
    )
    assert result_probe == probe
    assert result["text"] == "Synthetic speech"


@pytest.mark.parametrize(
    "failure,reason",
    [
        ("worker_timeout", "whisper_worker_timeout"),
        ("worker_generation_changed", "media_generation_changed"),
        ("worker_memory_limit_exceeded", "whisper_worker_resource_limit"),
        ("worker_process_limit_exceeded", "whisper_worker_resource_limit"),
        ("worker_output_limit_exceeded", "whisper_worker_resource_limit"),
        ("worker_input_limit_exceeded", "whisper_worker_resource_limit"),
        ("worker_diagnostic_limit_exceeded", "whisper_worker_resource_limit"),
        ("worker_cleanup_failed", "media_cleanup_failed"),
        ("worker_monitor_unavailable", "whisper_worker_failed"),
        ("worker_containment_unavailable", "whisper_worker_failed"),
        ("invalid_worker_response", "whisper_worker_failed"),
    ],
)
def test_supervisor_failures_are_typed(
    whisper, speech_file, tmp_path, monkeypatch, failure, reason
):
    probe = whisper.probe_local_media(speech_file, trusted_root=tmp_path)

    def fail(*args, **kwargs):
        raise whisper.SupervisorError(failure, {"private": str(speech_file)})

    monkeypatch.setattr(whisper, "run_authenticated_worker", fail)
    with pytest.raises(whisper.LocalMediaError) as caught:
        whisper.transcribe_local_media(
            speech_file, "synthetic-model", probe=probe, trusted_root=tmp_path
        )
    assert caught.value.reason_code == reason
    assert str(speech_file) not in str(caught.value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"text": "speech", "language": None, "segments": None, "private": "payload"},
    ],
)
def test_authenticated_but_wrong_result_shape_is_not_trusted(
    whisper, speech_file, tmp_path, monkeypatch, value
):
    probe = whisper.probe_local_media(speech_file, trusted_root=tmp_path)
    monkeypatch.setattr(
        whisper,
        "run_authenticated_worker",
        lambda *a, **kw: SimpleNamespace(payload=value),
    )
    with pytest.raises(whisper.LocalMediaError, match="whisper_result_invalid"):
        whisper.transcribe_local_media(
            speech_file, "synthetic-model", probe=probe, trusted_root=tmp_path
        )


def test_generation_change_after_worker_result_is_not_accepted(
    whisper, speech_file, tmp_path, monkeypatch
):
    probe = whisper.probe_local_media(speech_file, trusted_root=tmp_path)

    def replace_after_result(*args, **kwargs):
        speech_file.write_bytes(b"changed after response")
        return SimpleNamespace(
            payload={"text": "speech", "language": None, "segments": None}
        )

    monkeypatch.setattr(whisper, "run_authenticated_worker", replace_after_result)
    with pytest.raises(whisper.LocalMediaError, match="media_generation_changed"):
        whisper.transcribe_local_media(
            speech_file, "synthetic-model", probe=probe, trusted_root=tmp_path
        )


@pytest.mark.parametrize(
    "error",
    [
        ImportError,
        OSError,
        RuntimeError,
        AttributeError,
        TypeError,
        ValueError,
        KeyError,
    ],
)
def test_optional_provider_import_failure_is_path_neutral(whisper, monkeypatch, error):
    def fail(name):
        raise error("private/model/path")

    monkeypatch.setattr(whisper.importlib, "import_module", fail)
    with pytest.raises(
        whisper.LocalMediaError, match="whisper_dependency_unavailable"
    ) as caught:
        whisper._transcribe_with_mlx(Path("unused.wav"), "model")
    assert "private/model/path" not in str(caught.value)


@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit])
def test_process_control_signals_are_not_swallowed(whisper, monkeypatch, signal):
    def interrupt(path, **kwargs):
        raise signal()

    monkeypatch.setattr(
        whisper.importlib,
        "import_module",
        lambda name: SimpleNamespace(transcribe=interrupt),
    )
    with pytest.raises(signal):
        whisper._transcribe_with_mlx(Path("unused.wav"), "model")


def test_native_full_transcription_uses_greedy_independent_windows(
    whisper, monkeypatch
):
    def transcribe(
        path, *, path_or_hf_repo, temperature, condition_on_previous_text, verbose
    ):
        assert path == "speech.wav"
        assert path_or_hf_repo == "model"
        assert temperature == 0.0
        assert condition_on_previous_text is False
        assert verbose is None
        return {"text": "Complete useful speech.", "language": "en"}

    monkeypatch.setitem(
        sys.modules, "mlx_whisper", SimpleNamespace(transcribe=transcribe)
    )
    assert whisper._transcribe_with_mlx(Path("speech.wav"), "model") == {
        "text": "Complete useful speech.",
        "language": "en",
        "segments": None,
    }


# ── #487: decode a verified snapshot, never the pathname ───────────────


def test_a_source_swapped_and_restored_mid_decode_never_reaches_the_speech(
    whisper, speech_file, tmp_path, monkeypatch
):
    """Copilot on #496: rename the original aside, substitute another recording
    during the decode, restore it. Only the original's change time moves, so the
    decode must have read a snapshot of the established bytes."""
    import hashlib
    import json

    original = hashlib.sha256(speech_file.read_bytes()).hexdigest()
    record = tmp_path / "decoded.json"
    _fake_provider_worker(
        whisper,
        tmp_path,
        monkeypatch,
        "import hashlib, json, os\n"
        f"source = {str(speech_file)!r}\n"
        "os.rename(source, source + '.aside')\n"
        "with open(source, 'wb') as other:\n"
        "    other.write(b'a different recording')\n"
        "decoded = hashlib.sha256(open(path, 'rb').read()).hexdigest()\n"
        "os.replace(source + '.aside', source)\n"
        f"open({str(record)!r}, 'w').write(json.dumps({{'path': path, 'sha': decoded}}))\n"
        "return {'text': 'Synthetic speech', 'language': 'en', 'segments': []}",
    )

    _probe, result = whisper.transcribe_local_media(
        speech_file, "synthetic-model", trusted_root=tmp_path
    )

    decoded = json.loads(record.read_text(encoding="utf-8"))
    assert decoded["sha"] == original
    assert decoded["path"] != str(speech_file)
    assert result["text"] == "Synthetic speech"


def test_a_source_changed_mid_decode_is_refused_before_commit(
    whisper, speech_file, tmp_path, monkeypatch
):
    """The decode read the snapshot; the owner's precommit check still refuses
    a source whose bytes changed underneath it."""
    _fake_provider_worker(
        whisper,
        tmp_path,
        monkeypatch,
        f"open({str(speech_file)!r}, 'r+b').write(b'X')\n"
        "return {'text': 'speech', 'language': 'en', 'segments': []}",
    )
    with pytest.raises(whisper.LocalMediaError, match="media_generation_changed"):
        whisper.transcribe_local_media(
            speech_file, "synthetic-model", trusted_root=tmp_path
        )


def test_word_samples_are_extracted_from_the_snapshot(
    whisper, speech_file, tmp_path, monkeypatch
):
    import json

    record = tmp_path / "extracted.json"
    script = tmp_path / "synthetic_words_worker.py"
    script.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {str(Path(SCRIPTS_VI).resolve())!r})\n"
        "import local_media_transcription as owner\n"
        "def extract(path, workspace, **kwargs):\n"
        f"    open({str(record)!r}, 'w').write(json.dumps(str(path)))\n"
        "    raise owner.LocalMediaError('whisper_sample_decode_failed')\n"
        "owner.extract_speech_clip = extract\n"
        "raise SystemExit(owner._main())\n",
        encoding="utf-8",
    )
    real = whisper.run_authenticated_worker

    def invoke(command, operation, expected, payload, limits, **kwargs):
        command = [sys.executable, str(script), whisper.WORKER_FLAG]
        kwargs["immutable_process_identity"] = command[:2]
        return real(command, operation, expected, payload, limits, **kwargs)

    monkeypatch.setattr(whisper, "run_authenticated_worker", invoke)
    with pytest.raises(whisper.LocalMediaError, match="whisper_sample_decode_failed"):
        whisper.transcribe_local_words(
            speech_file,
            sample_start_seconds=0.0,
            sample_duration_seconds=0.5,
            trusted_root=tmp_path,
        )
    extracted = json.loads(record.read_text(encoding="utf-8"))
    assert extracted != str(speech_file)
    assert Path(extracted).name.startswith("source")

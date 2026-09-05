"""Authenticated sampling with a synthetic native boundary; no model downloads."""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import wave

import pytest

from conftest import SCRIPTS_VI, _import_script


@pytest.fixture
def owner():
    return _import_script(
        Path(SCRIPTS_VI) / "local_media_transcription.py", "local_media_transcription"
    )


@pytest.fixture
def media(tmp_path):
    path = tmp_path / "original.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 16000)
    return path


def raw_words():
    return {
        "language": "en",
        "segments": [
            {
                "start": 0,
                "end": 0.5,
                "compression_ratio": 1.1,
                "avg_logprob": -0.1,
                "no_speech_prob": 0.01,
                "words": [
                    {"word": " First", "start": 0.1, "end": 0.2, "probability": 0.95},
                    {"word": " word.", "start": 0.3, "end": 0.4, "probability": 0.98},
                ],
            }
        ],
    }


def synthetic_worker(owner, tmp_path, monkeypatch, *, body=None, timeout=None):
    native = body or f"return {{'raw': {raw_words()!r}, 'language_probability': 0.99}}"
    script = tmp_path / "synthetic_words_worker.py"
    script.write_text(
        f"import sys\nsys.path.insert(0, {str(Path(SCRIPTS_VI).resolve())!r})\n"
        "import local_media_transcription as owner\n"
        "owner._word_model_path = lambda: ('fixture-model', '0.4.3')\n"
        "def native(path, model, **options):\n"
        + "\n".join("    " + line for line in native.splitlines())
        + "\nowner._transcribe_with_mlx = native\nraise SystemExit(owner._main())\n",
        encoding="utf-8",
    )
    real = owner.run_authenticated_worker
    workspaces = []

    def invoke(command, operation, expected, payload, limits, **kwargs):
        assert operation == owner.WORDS_OPERATION
        assert "original.wav" not in repr(command)
        workspaces.append(Path(payload["workspace"]["path"]))
        command = [sys.executable, str(script), owner.WORKER_FLAG]
        kwargs["immutable_process_identity"] = command[:2]
        if timeout is not None:
            limits = replace(limits, wall_seconds=timeout)
        return real(command, operation, expected, payload, limits, **kwargs)

    monkeypatch.setattr(owner, "run_authenticated_worker", invoke)
    return workspaces


def test_real_worker_returns_fresh_words_and_cleans_private_samples(
    owner, media, tmp_path, monkeypatch
):
    before = media.read_bytes()
    probe = owner.probe_local_media(media, trusted_root=tmp_path)
    workspaces = synthetic_worker(owner, tmp_path, monkeypatch)

    def forbidden(*args, **kwargs):
        pytest.fail("an established source was reprobed")

    monkeypatch.setattr(owner, "probe_local_media", forbidden)
    established, receipt = owner.transcribe_local_words(
        media,
        sample_start_seconds=0.25,
        sample_duration_seconds=0.5,
        probe=probe,
        trusted_root=tmp_path,
    )
    assert established is probe
    assert receipt["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert receipt["source_duration_seconds"] == 1
    assert receipt["sample_duration_seconds"] == 0.5
    assert receipt["sample_start_seconds"] == 0.25
    assert receipt["language_probability"] == 0.99
    assert receipt["model"] == owner.DEFAULT_WORD_MODEL
    assert [word["text"] for word in receipt["words"]] == ["First", "word."]
    assert all(not path.exists() for path in workspaces)
    assert media.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "original.wav",
        "synthetic_words_worker.py",
    ]


@pytest.mark.parametrize(
    "body,reason",
    [
        ("raise RuntimeError('private failure')", "whisper_worker_failed"),
        (
            "return {'raw': {'segments': []}, 'language_probability': 0.99}",
            "whisper_word_sample_invalid",
        ),
        (
            "from pathlib import Path\nPath(path).chmod(0o600)\nPath(path).write_bytes(b'changed')\nreturn {}",
            "media_generation_changed",
        ),
        (
            "import sys\nsys.stderr.write('x' * 65537)\nreturn {}",
            "whisper_worker_resource_limit",
        ),
    ],
)
def test_failed_worker_retains_old_artifacts_and_cleans_sample(
    owner, media, tmp_path, monkeypatch, body, reason
):
    prior = tmp_path / "speech-rate-profile.json"
    prior.write_bytes(b"prior profile")
    workspaces = synthetic_worker(owner, tmp_path, monkeypatch, body=body)
    with pytest.raises(owner.LocalMediaError, match=reason):
        owner.transcribe_local_words(
            media, sample_start_seconds=0.25, sample_duration_seconds=0.5
        )
    assert prior.read_bytes() == b"prior profile"
    assert workspaces and all(not path.exists() for path in workspaces)


def test_timeout_removes_sample_even_after_worker_killed(
    owner, media, tmp_path, monkeypatch
):
    workspaces = synthetic_worker(
        owner, tmp_path, monkeypatch, body="import time\ntime.sleep(30)", timeout=1.0
    )
    with pytest.raises(owner.LocalMediaError, match="whisper_worker_timeout"):
        owner.transcribe_local_words(
            media, sample_start_seconds=0.25, sample_duration_seconds=0.5
        )
    assert workspaces and all(not path.exists() for path in workspaces)


def test_original_mutation_during_sample_transcription_refuses(
    owner, media, tmp_path, monkeypatch
):
    body = f"from pathlib import Path\nPath({str(media)!r}).write_bytes(b'changed original')\nreturn {{'raw': {raw_words()!r}, 'language_probability': 0.99}}"
    synthetic_worker(owner, tmp_path, monkeypatch, body=body)
    with pytest.raises(owner.LocalMediaError, match="media_generation_changed"):
        owner.transcribe_local_words(
            media, sample_start_seconds=0.25, sample_duration_seconds=0.5
        )


def test_final_source_recheck_rejects_change_after_worker_response(
    owner, media, tmp_path, monkeypatch
):
    synthetic_worker(owner, tmp_path, monkeypatch)
    actual = owner.run_authenticated_worker

    def mutate(*args, **kwargs):
        result = actual(*args, **kwargs)
        media.write_bytes(b"changed after worker")
        return result

    monkeypatch.setattr(owner, "run_authenticated_worker", mutate)
    with pytest.raises(owner.LocalMediaError, match="media_generation_changed"):
        owner.transcribe_local_words(
            media, sample_start_seconds=0.25, sample_duration_seconds=0.5
        )


def test_cleanup_failure_never_returns_usable_receipt(
    owner, media, tmp_path, monkeypatch
):
    synthetic_worker(owner, tmp_path, monkeypatch)
    real = owner.private_media_workspace

    @contextmanager
    def failed_cleanup():
        with real() as directory:
            yield directory
        raise owner.LocalMediaError("media_cleanup_failed")

    monkeypatch.setattr(owner, "private_media_workspace", failed_cleanup)
    with pytest.raises(owner.LocalMediaError, match="media_cleanup_failed"):
        owner.transcribe_local_words(
            media, sample_start_seconds=0.25, sample_duration_seconds=0.5
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sha256", "f" * 64),
        ("sample_start_seconds", 0.1),
        ("source_duration_seconds", 2),
    ],
)
def test_authenticated_receipt_with_wrong_source_binding_refuses(
    owner, media, tmp_path, monkeypatch, field, value
):
    synthetic_worker(owner, tmp_path, monkeypatch)
    actual = owner.run_authenticated_worker

    def change(*args, **kwargs):
        result = actual(*args, **kwargs)
        receipt = dict(result.payload)
        receipt[field] = value
        return SimpleNamespace(payload=receipt)

    monkeypatch.setattr(owner, "run_authenticated_worker", change)
    with pytest.raises(owner.LocalMediaError, match="whisper_word_sample_invalid"):
        owner.transcribe_local_words(
            media, sample_start_seconds=0.25, sample_duration_seconds=0.5
        )


def test_native_options_preserve_real_word_timing_and_language_probability(
    owner, monkeypatch
):
    observed = []

    def transcribe(path, **options):
        observed.append(options)
        return raw_words()

    network = SimpleNamespace(
        dims=SimpleNamespace(n_mels=128),
        detect_language=lambda mel: (None, {"en": 0.987, "ru": 0.013}),
    )
    native = SimpleNamespace(
        mx=SimpleNamespace(float16="f16"),
        N_SAMPLES=480000,
        N_FRAMES=3000,
        ModelHolder=SimpleNamespace(get_model=lambda path, dtype: network),
        log_mel_spectrogram=lambda *a, **k: "mel",
        pad_or_trim=lambda *a, **k: SimpleNamespace(astype=lambda dtype: "features"),
    )
    monkeypatch.setattr(
        owner.importlib,
        "import_module",
        lambda name: (
            SimpleNamespace(transcribe=transcribe) if name == "mlx_whisper" else native
        ),
    )
    result = owner._transcribe_with_mlx(
        Path("synthetic.wav"), "snapshot", word_timestamps=True
    )
    assert observed == [
        {
            "path_or_hf_repo": "snapshot",
            "word_timestamps": True,
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "verbose": None,
        }
    ]
    assert result["raw"] == raw_words()
    assert result["language_probability"] == 0.987


def test_model_resolution_pins_revision_and_downloads_no_remote_code(
    owner, monkeypatch
):
    observed = []
    monkeypatch.setattr(owner.importlib.metadata, "version", lambda name: "0.4.3")
    monkeypatch.setattr(
        owner.importlib,
        "import_module",
        lambda name: SimpleNamespace(
            snapshot_download=lambda **kwargs: (
                observed.append(kwargs) or "/synthetic/snapshot"
            )
        ),
    )
    assert owner._word_model_path() == ("/synthetic/snapshot", "0.4.3")
    assert observed == [
        {
            "repo_id": owner.DEFAULT_WORD_MODEL["id"],
            "revision": owner.DEFAULT_WORD_MODEL["revision"],
            "allow_patterns": ["config.json", "weights.safetensors", "weights.npz"],
            "max_workers": 1,
            "token": False,
        }
    ]


def test_unsupported_native_version_refuses_before_download(owner, monkeypatch):
    monkeypatch.setattr(owner.importlib.metadata, "version", lambda name: "0.0.1")
    monkeypatch.setattr(
        owner.importlib, "import_module", lambda name: SimpleNamespace()
    )
    with pytest.raises(
        owner.LocalMediaError, match="whisper_provider_version_unsupported"
    ):
        owner._word_model_path()


def test_numeric_segment_diagnostics_cross_worker_without_words(
    owner, media, tmp_path, monkeypatch
):
    raw = raw_words()
    raw["segments"][0]["end"] = 0.1
    workspaces = synthetic_worker(
        owner,
        tmp_path,
        monkeypatch,
        body=f"return {{'raw': {raw!r}, 'language_probability': 0.99}}",
    )
    with pytest.raises(owner.WordSampleError) as exc:
        owner.transcribe_local_words(
            media, sample_start_seconds=0.25, sample_duration_seconds=0.5
        )
    assert exc.value.word_timing == {
        "schema_version": 1,
        "word_index": 0,
        "word_count": 2,
        "word_start_seconds": 0.1,
        "word_end_seconds": 0.2,
        "segment_index": 0,
        "segment_count": 1,
        "segment_start_seconds": 0,
        "segment_end_seconds": 0.1,
    }
    assert "First" not in repr(exc.value.word_timing)
    assert "private" not in repr(exc.value.word_timing)
    assert workspaces and all(not path.exists() for path in workspaces)

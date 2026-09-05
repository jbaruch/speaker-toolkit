"""Command-level calibration preserves catalog and artifact ownership."""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conftest import SCRIPTS_VP, _import_script
from test_speech_calibration import sample


@pytest.fixture
def command():
    return _import_script(Path(SCRIPTS_VP) / "calibrate-speech.py", "calibrate_speech")


def talk(name="one", *, local=True):
    return {
        "filename": name + ".md",
        "status": "processed",
        "date": "2020-06-01",
        "video_path": f"recordings/{name}.wav" if local else None,
        "youtube_id": "abcdefghijk" if not local else None,
        "structured_data": {
            "talk_family": "family one",
            "mode": "demo",
            "delivery_language": "en",
            "co_presenter": False,
        },
    }


def vault(tmp_path, rows=None, **config):
    database = {
        "config": {
            "python_path": sys.executable,
            "speaker_name": "Fixture speaker",
            **config,
        },
        "talks": [talk()] if rows is None else rows,
    }
    path = tmp_path / "tracking-database.json"
    path.write_text(json.dumps(database), encoding="utf-8")
    return path


def options(tmp_path, **updates):
    return argparse.Namespace(
        vault_root=str(tmp_path),
        speaker="Fixture speaker",
        language="en",
        run=updates.get("run", False),
        allow_download=updates.get("allow_download", False),
        maximum_recordings=12,
        demo_mode=["demo"],
        as_of="2024-06-01T12:00:00Z",
    )


def runtime_ok(command, monkeypatch):
    real = command._owner_script
    observed = []

    def load(name):
        if name != "check-runtime.py":
            return real(name)

        def report(lanes, required):
            observed.append(required)
            return {"schema_version": 1, "ok": True}

        return SimpleNamespace(build_report=report)

    monkeypatch.setattr(command, "_owner_script", load)
    return observed


def test_plan_is_read_only_and_never_opens_recordings(command, tmp_path, monkeypatch):
    path = vault(tmp_path)
    before = path.read_bytes()
    lanes = runtime_ok(command, monkeypatch)

    def forbidden(*args, **kwargs):
        pytest.fail("metadata plan acquired or transcribed source audio")

    monkeypatch.setattr(command, "probe_local_media", forbidden)
    monkeypatch.setattr(command, "download_youtube_audio", forbidden)
    monkeypatch.setattr(command, "transcribe_local_words", forbidden)
    result = command.execute(options(tmp_path))
    assert result["status"] == "plan_only"
    assert result["profile"] is None
    assert result["cohort"]["selected_recording_ids"] == ["one.md"]
    assert lanes == [("core",)]
    assert path.read_bytes() == before


def test_real_plan_command_and_json_help(command, tmp_path):
    vault(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            command.__file__,
            str(tmp_path),
            "--speaker",
            "Fixture speaker",
            "--language",
            "en",
            "--as-of",
            "2024-06-01T12:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"]["status"] == "plan_only"
    help_result = subprocess.run(
        [sys.executable, command.__file__, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--run" in json.loads(help_result.stdout)["data"]["help"]


def test_run_consumes_owner_words_and_preserves_all_exclusions(
    command, tmp_path, monkeypatch
):
    excluded = talk("excluded")
    excluded["structured_data"]["co_presenter"] = True
    path = vault(tmp_path, [talk(), excluded])
    prior = tmp_path / "speech-rate-profile.json"
    prior.write_bytes(b"existing profile")
    before = path.read_bytes()
    lanes = runtime_ok(command, monkeypatch)
    probe = SimpleNamespace(duration_seconds=3600)
    seen = []
    monkeypatch.setattr(command, "probe_local_media", lambda *a, **k: probe)

    def transcribe(path, **kwargs):
        seen.append((path, kwargs))
        receipt = sample()["words"]
        receipt["sample_start_seconds"] = kwargs["sample_start_seconds"]
        return probe, receipt

    monkeypatch.setattr(command, "transcribe_local_words", transcribe)
    result = command.execute(options(tmp_path, run=True))
    assert result["status"] == "low_confidence"
    assert result["profile"]["summary"]["recording_count"] == 1
    assert result["profile"]["exclusions"] == [
        {
            "schema_version": 1,
            "recording_id": "excluded.md",
            "reasons": ["multiple_speakers"],
        }
    ]
    assert seen[0][0] == "recordings/one.wav"
    assert seen[0][1] == {
        "probe": probe,
        "trusted_root": tmp_path,
        "sample_start_seconds": 1500.0,
        "sample_duration_seconds": 600.0,
    }
    assert lanes == [("core", "source-media", "speech-calibration")]
    assert path.read_bytes() == before
    assert prior.read_bytes() == b"existing profile"


def test_missing_local_source_remains_excluded_without_fallback(
    command, tmp_path, monkeypatch
):
    vault(tmp_path)
    runtime_ok(command, monkeypatch)

    def fail(*args, **kwargs):
        raise command.LocalMediaError("media_artifact_unavailable")

    monkeypatch.setattr(command, "probe_local_media", fail)
    result = command.execute(options(tmp_path, run=True))
    assert result["profile"]["summary"]["recording_count"] == 0
    assert result["profile"]["exclusions"][0]["reasons"] == [
        "media_artifact_unavailable"
    ]
    assert result["status"] == "low_confidence"


def test_segment_failure_logs_only_closed_numeric_evidence(
    command, tmp_path, monkeypatch, capsys
):
    vault(tmp_path)
    runtime_ok(command, monkeypatch)
    monkeypatch.setattr(
        command,
        "probe_local_media",
        lambda *a, **k: SimpleNamespace(duration_seconds=3600),
    )
    diagnostic = {
        "schema_version": 1,
        "word_index": 0,
        "word_count": 2,
        "word_start_seconds": 0.1,
        "word_end_seconds": 0.2,
        "segment_index": 0,
        "segment_count": 1,
        "segment_start_seconds": 0.3,
        "segment_end_seconds": 0.5,
    }

    def fail(*args, **kwargs):
        raise command.WordSampleError(diagnostic)

    monkeypatch.setattr(command, "transcribe_local_words", fail)
    result = command.execute(options(tmp_path, run=True))
    captured = capsys.readouterr()
    records = [
        json.loads(line) for line in captured.err.splitlines() if line.startswith("{")
    ]
    assert records == [
        {
            "schema_version": 1,
            "code": "whisper_word_sample_invalid_word_segment",
            "word_timing": diagnostic,
        }
    ]
    assert result["profile"]["exclusions"] == [
        {
            "schema_version": 1,
            "recording_id": "one.md",
            "reasons": ["whisper_word_sample_invalid_word_segment"],
        }
    ]
    assert str(tmp_path) not in captured.err
    assert "recordings/one.wav" not in captured.err


def test_download_requires_option_and_cleanup_precedes_admission(
    command, tmp_path, monkeypatch
):
    vault(tmp_path, [talk(local=False)])
    lanes = runtime_ok(command, monkeypatch)
    consumed = []

    @contextmanager
    def download(video_id):
        consumed.append(video_id)
        yield tmp_path / "private-audio.wav", 3600
        raise command.LocalMediaError("media_cleanup_failed")

    monkeypatch.setattr(command, "download_youtube_audio", download)
    no_download = command.execute(options(tmp_path, run=True))
    assert no_download["profile"]["summary"]["recording_count"] == 0
    assert consumed == []
    monkeypatch.setattr(
        command,
        "probe_local_media",
        lambda *a, **k: SimpleNamespace(duration_seconds=3600),
    )
    monkeypatch.setattr(
        command, "transcribe_local_words", lambda *a, **k: (None, sample()["words"])
    )
    with pytest.raises(command.LocalMediaError, match="media_cleanup_failed"):
        command.execute(options(tmp_path, run=True, allow_download=True))
    assert consumed == ["abcdefghijk"]
    assert lanes[-1] == (
        "core",
        "source-media",
        "speech-calibration",
        "youtube-download",
    )


def test_catalog_change_before_output_refuses_candidate(command, tmp_path, monkeypatch):
    path = vault(tmp_path)
    runtime_ok(command, monkeypatch)
    monkeypatch.setattr(
        command,
        "probe_local_media",
        lambda *a, **k: SimpleNamespace(duration_seconds=3600),
    )

    def change(*args, **kwargs):
        path.write_bytes(path.read_bytes() + b"\n")
        return None, sample()["words"]

    monkeypatch.setattr(command, "transcribe_local_words", change)
    with pytest.raises(command.SpeechRateError) as exc:
        command.execute(options(tmp_path, run=True))
    assert exc.value.code == "pace_catalog_changed"


def test_configured_interpreter_is_required(command, tmp_path):
    vault(tmp_path, python_path="/wrong/private/python")
    with pytest.raises(command.SpeechRateError) as exc:
        command.execute(options(tmp_path))
    assert exc.value.code == "pace_interpreter_mismatch"
    assert "private/python" not in str(exc.value)


def test_strict_reader_rejects_duplicate_keys(command, tmp_path, capsys):
    (tmp_path / "tracking-database.json").write_bytes(
        b'{"private_key":1,"private_key":2}'
    )
    assert (
        command.main(
            [str(tmp_path), "--speaker", "Fixture speaker", "--language", "en"]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "pace_catalog_unavailable"
    assert "private_key" not in captured.out + captured.err


def test_usage_refusal_is_json_without_private_arguments(command, capsys):
    assert command.main(["--private-source"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "pace_usage_invalid"
    assert "private-source" not in captured.out + captured.err


def test_missing_runtime_refuses_before_acquisition(command, tmp_path, monkeypatch):
    vault(tmp_path)
    real = command._owner_script
    monkeypatch.setattr(
        command,
        "_owner_script",
        lambda name: (
            SimpleNamespace(build_report=lambda *a: {"ok": False})
            if name == "check-runtime.py"
            else real(name)
        ),
    )
    with pytest.raises(command.SpeechRateError) as exc:
        command.execute(options(tmp_path, run=True))
    assert exc.value.code == "pace_runtime_unavailable"

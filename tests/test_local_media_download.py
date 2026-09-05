"""Synthetic yt-dlp providers exercise download isolation without network I/O."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from conftest import SCRIPTS_VI, _import_script


VIDEO_ID = "abcdefghijk"


@pytest.fixture
def download():
    return _import_script(
        Path(SCRIPTS_VI) / "local_media_download.py", "local_media_download"
    )


def _metadata(**updates):
    return {
        "id": VIDEO_ID,
        "duration": 60.25,
        "ext": "mp3",
        "format_id": "140",
        "acodec": "mp3",
        "vcodec": "none",
        **updates,
    }


def _synthetic_worker(
    download, tmp_path, monkeypatch, body, *, timeout=None, byte_limit=None
):
    # The provider is a Python program selected by a test-only worker bootstrap.
    # The runtime's actual child protocol, pipe caps and literal sink remain real.
    provider = tmp_path / "synthetic_ytdlp.py"
    provider.write_text(
        "import sys, json\nfrom pathlib import Path\n" + body + "\n", encoding="utf-8"
    )
    script = tmp_path / "synthetic_download_worker.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(Path(SCRIPTS_VI).resolve())!r})\n"
        "import local_media_download as owner\n"
        "original = owner._command\n"
        f"owner._command = lambda executable, video_id, client: [sys.executable, {str(provider)!r}] + original(executable, video_id, client)[1:]\n"
        + (
            f"owner.MEDIA_MAX_INPUT_BYTES = {byte_limit}\n"
            if byte_limit is not None
            else ""
        )
        + "raise SystemExit(owner._main())\n",
        encoding="utf-8",
    )
    real = download.run_authenticated_worker
    workspaces = []

    def invoke(command, operation, expected, payload, limits, **kwargs):
        workspaces.append(Path(payload["workspace"]["path"]))
        command = [sys.executable, str(script), download.WORKER_FLAG]
        kwargs["immutable_process_identity"] = command[:2]
        if timeout is not None:
            limits = replace(limits, wall_seconds=timeout)
        return real(command, operation, expected, payload, limits, **kwargs)

    monkeypatch.setattr(download, "run_authenticated_worker", invoke)
    return workspaces


def test_real_protocol_metadata_is_identity_bound_and_cleaned(
    download, tmp_path, monkeypatch
):
    workspaces = _synthetic_worker(
        download, tmp_path, monkeypatch, f"print(json.dumps({_metadata()!r}))"
    )
    assert (
        download.probe_youtube_media_duration(VIDEO_ID, ytdlp=tmp_path / "yt-dlp")
        == 60.25
    )
    assert len(workspaces) == 1
    assert not workspaces[0].exists()


def test_download_is_literal_private_and_removed_after_consumer_failure(
    download, tmp_path, monkeypatch
):
    workspaces = _synthetic_worker(
        download,
        tmp_path,
        monkeypatch,
        "if '--dump-single-json' in sys.argv:\n"
        f"    print(json.dumps({_metadata()!r}))\n"
        "else:\n    sys.stdout.buffer.write(b'synthetic media bytes')",
    )
    with pytest.raises(ValueError, match="consumer failed"):
        with download.download_youtube_audio(VIDEO_ID, ytdlp=tmp_path / "yt-dlp") as (
            path,
            duration,
        ):
            assert path.name == "audio.mp3"
            assert path.read_bytes() == b"synthetic media bytes"
            assert duration == 60.25
            assert list(path.parent.iterdir()) == [path]
            raise ValueError("consumer failed")
    assert not workspaces[0].exists()


def test_download_retries_only_provider_refusals_with_no_partial_reuse(
    download, tmp_path, monkeypatch
):
    workspaces = _synthetic_worker(
        download,
        tmp_path,
        monkeypatch,
        "if '--dump-single-json' in sys.argv:\n"
        f"    print(json.dumps({_metadata()!r}))\n"
        "elif 'youtube:player_client=mweb' in sys.argv:\n"
        "    assert list(Path.cwd().iterdir()) == [Path.cwd() / 'audio.mp3']\n"
        "    assert (Path.cwd() / 'audio.mp3').stat().st_size == 0\n"
        "    sys.stdout.buffer.write(b'complete retry bytes')\n"
        "else:\n    sys.stdout.buffer.write(b'failed partial')\n    sys.exit(1)",
    )
    with download.download_youtube_audio(VIDEO_ID, ytdlp=tmp_path / "yt-dlp") as (
        path,
        _,
    ):
        assert path.read_bytes() == b"complete retry bytes"
    assert not workspaces[0].exists()


@pytest.mark.parametrize("empty_first", [False, True])
def test_first_usable_download_stops_retries(
    download, tmp_path, monkeypatch, empty_first
):
    calls = tmp_path / "provider-calls.txt"
    workspaces = _synthetic_worker(
        download,
        tmp_path,
        monkeypatch,
        f"with Path({str(calls)!r}).open('a') as log:\n"
        "    log.write(('metadata' if '--dump-single-json' in sys.argv else 'download') + '\\n')\n"
        "if '--dump-single-json' in sys.argv:\n"
        f"    print(json.dumps({_metadata()!r}))\n"
        f"elif {empty_first!r} and '--extractor-args' not in sys.argv:\n"
        "    pass\n"
        "else:\n"
        "    assert (Path.cwd() / 'audio.mp3').stat().st_size == 0\n"
        "    sys.stdout.buffer.write(b'complete media')",
    )
    with download.download_youtube_audio(VIDEO_ID, ytdlp=tmp_path / "yt-dlp") as (
        path,
        _,
    ):
        assert path.read_bytes() == b"complete media"
        assert calls.read_text().splitlines() == ["metadata", "download"] * (
            2 if empty_first else 1
        )
    assert not workspaces[0].exists()


def test_all_zero_byte_downloads_fail_and_cleanup(download, tmp_path, monkeypatch):
    workspaces = _synthetic_worker(
        download,
        tmp_path,
        monkeypatch,
        f"if '--dump-single-json' in sys.argv:\n    print(json.dumps({_metadata()!r}))",
    )
    with pytest.raises(download.LocalMediaError, match="ytdlp_provider_rejected"):
        with download.download_youtube_audio(VIDEO_ID, ytdlp=tmp_path / "yt-dlp"):
            pytest.fail("zero-byte download became usable")
    assert not workspaces[0].exists()


@pytest.mark.parametrize(
    "body,reason",
    [
        ("print('not JSON')", "ytdlp_metadata_invalid"),
        (
            'print(\'{"id":"abcdefghijk","id":"abcdefghijk"}\')',
            "ytdlp_metadata_invalid",
        ),
        (
            f"print(json.dumps({_metadata(id='different-id')!r}))",
            "ytdlp_identity_mismatch",
        ),
        (f"print(json.dumps({_metadata(duration=0)!r}))", "ytdlp_duration_unavailable"),
        (
            f"print(json.dumps({_metadata(is_live=True)!r}))",
            "ytdlp_duration_unavailable",
        ),
        (
            f"print(json.dumps({_metadata(ext='../private/path')!r}))",
            "ytdlp_format_unavailable",
        ),
        ("sys.stdout.buffer.write(b'x' * (1024 * 1024 + 1))", "ytdlp_stdout_limit"),
        ("sys.stderr.write('x' * 65537)", "ytdlp_stderr_limit"),
        (
            "sys.stderr.write('private provider detail'); sys.exit(1)",
            "ytdlp_provider_rejected",
        ),
    ],
)
def test_invalid_provider_output_stops_and_cleans_without_redaction_leak(
    download, tmp_path, monkeypatch, body, reason
):
    workspaces = _synthetic_worker(download, tmp_path, monkeypatch, body)
    with pytest.raises(download.LocalMediaError) as caught:
        with download.download_youtube_audio(VIDEO_ID, ytdlp=tmp_path / "yt-dlp"):
            pytest.fail("invalid download became usable")
    assert caught.value.reason_code == reason
    assert "private" not in str(caught.value)
    assert not workspaces[0].exists()


@pytest.mark.parametrize(
    "body,reason",
    [
        ("sys.stdout.buffer.write(b'x' * 262144)", "ytdlp_download_size_limit"),
        (
            "sys.stdout.buffer.write(b'partial'); import time; time.sleep(30)",
            "ytdlp_worker_timeout",
        ),
        (
            "sys.stdout.buffer.write(b'media'); Path('extra-output').write_bytes(b'bad')",
            "ytdlp_output_invalid",
        ),
    ],
)
def test_download_resource_and_output_failures_leave_no_workspace(
    download, tmp_path, monkeypatch, body, reason
):
    program = (
        "if '--dump-single-json' in sys.argv:\n"
        + f"    print(json.dumps({_metadata()!r}))\nelse:\n"
        + "\n".join("    " + line for line in body.splitlines())
    )
    workspaces = _synthetic_worker(
        download,
        tmp_path,
        monkeypatch,
        program,
        timeout=1.0 if reason == "ytdlp_worker_timeout" else None,
        byte_limit=65536,
    )
    with pytest.raises(download.LocalMediaError) as caught:
        with download.download_youtube_audio(VIDEO_ID, ytdlp=tmp_path / "yt-dlp"):
            pytest.fail("failed download became usable")
    assert caught.value.reason_code == reason
    assert not workspaces[0].exists()


def test_literal_download_output_must_be_regular(download, tmp_path):
    candidate = tmp_path / "audio.mp3"
    candidate.mkdir()
    with pytest.raises(download.LocalMediaError, match="media_artifact_unavailable"):
        download._require_only_artifact(tmp_path, candidate)


@pytest.mark.parametrize(
    "failure,reason",
    [
        ("worker_timeout", "ytdlp_worker_timeout"),
        ("worker_memory_limit_exceeded", "ytdlp_worker_resource_limit"),
        ("worker_process_limit_exceeded", "ytdlp_worker_resource_limit"),
        ("worker_input_limit_exceeded", "ytdlp_worker_resource_limit"),
        ("worker_output_limit_exceeded", "ytdlp_worker_resource_limit"),
        ("worker_diagnostic_limit_exceeded", "ytdlp_worker_resource_limit"),
        ("worker_cleanup_failed", "media_cleanup_failed"),
        ("worker_containment_unavailable", "ytdlp_worker_failed"),
        ("worker_monitor_unavailable", "ytdlp_worker_failed"),
        ("invalid_worker_response", "ytdlp_worker_failed"),
    ],
)
def test_supervisor_refusal_mapping_is_closed(download, monkeypatch, failure, reason):
    def failed(*args, **kwargs):
        raise download.SupervisorError(failure)

    monkeypatch.setattr(download, "run_authenticated_worker", failed)
    with pytest.raises(download.LocalMediaError) as caught:
        download.probe_youtube_media_duration(VIDEO_ID)
    assert caught.value.reason_code == reason


@pytest.mark.parametrize(
    "name", [None, [], "../escape.mp3", "/private/audio.mp3", "audio.exe"]
)
def test_malformed_result_never_selects_an_arbitrary_artifact(
    download, monkeypatch, name
):
    monkeypatch.setattr(
        download,
        "run_authenticated_worker",
        lambda *a, **kw: SimpleNamespace(
            payload={
                "video_id": VIDEO_ID,
                "duration_seconds": 60.25,
                "artifact_name": name,
            }
        ),
    )
    with pytest.raises(download.LocalMediaError, match="ytdlp_output_invalid"):
        with download.download_youtube_audio(VIDEO_ID):
            pytest.fail("malformed artifact selector accepted")


def test_download_command_closes_unrelated_provider_writes(download, tmp_path):
    command = download._command(tmp_path / "yt-dlp", VIDEO_ID, "mweb")
    assert {
        "--ignore-config",
        "--no-plugin-dirs",
        "--no-cache-dir",
        "--no-playlist",
        "--abort-on-unavailable-fragments",
    } <= set(command)
    assert command[-1] == f"https://www.youtube.com/watch?v={VIDEO_ID}"
    assert "youtube:player_client=mweb" in command

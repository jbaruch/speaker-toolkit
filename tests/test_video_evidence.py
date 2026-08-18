"""Bounded source-video evidence and operation-scope regression tests."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import threading
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "vault-ingress"
    / "scripts"
    / "video_evidence.py"
)
SCRIPT_DIR = SCRIPT.parent
if os.fspath(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_DIR))
video_evidence = importlib.import_module("video_evidence")
artifact_supervisor = importlib.import_module("artifact_supervisor")
artifact_metadata = importlib.import_module("artifact_metadata")


def _generation(
    *,
    size: int = 1_024,
    inode: int = 31,
    flags: int | None = None,
    file_attributes: int | None = None,
) -> Any:
    return video_evidence.FileGeneration(
        size=size,
        mtime_ns=11,
        ctime_ns=12,
        device=13,
        inode=inode,
        mode=0o100600,
        flags=flags,
        file_attributes=file_attributes,
    )


def _root_generation(*, inode: int = 41) -> Any:
    return video_evidence.FileGeneration(
        size=0,
        mtime_ns=0,
        ctime_ns=0,
        device=13,
        inode=inode,
        mode=0o040700,
        flags=None,
        file_attributes=None,
    )


def _receipt(
    generation: Any,
    root_generation: Any | None = None,
    *,
    reparse_tag: int | None = None,
) -> Any:
    return video_evidence.ArtifactMetadataReceipt(
        generation=generation,
        root_generation=root_generation,
        reparse_tag=reparse_tag,
    )


def _probe(
    generation: Any,
    *,
    root_generation: Any | None = None,
    digest: str = "a" * 64,
) -> Any:
    return video_evidence.VideoArtifactProbe(
        generation=generation,
        root_generation=root_generation,
        availability=video_evidence.ArtifactAvailability.from_generation(generation),
        source_sha256=digest,
        source_size_bytes=generation.size,
        duration_seconds=1.0,
        duration_source="format",
        container_family="iso_bmff",
        stream_count=1,
        video_stream_count=1,
        audio_stream_count=0,
        attached_picture_count=0,
        other_stream_count=0,
        parser_diagnostics=video_evidence.DiagnosticReceipt.empty(),
    )


def _worker_result(
    generation: Any,
    *,
    payload: dict[str, object] | None = None,
    diagnostics: Any | None = None,
) -> Any:
    selected_payload = payload or {
        "schema_version": video_evidence.VIDEO_PROBE_SCHEMA_VERSION,
        "status": "available",
        "source_sha256": "a" * 64,
        "source_size_bytes": generation.size,
        "duration_seconds": 1.0,
        "duration_source": "format",
        "container_family": "iso_bmff",
        "stream_count": 1,
        "video_stream_count": 1,
        "audio_stream_count": 0,
        "attached_picture_count": 0,
        "other_stream_count": 0,
    }
    return video_evidence.WorkerResult(
        payload=selected_payload,
        observed_generations={"video": generation},
        diagnostics=diagnostics or video_evidence.DiagnosticReceipt.empty(),
    )


def _create_mp4(path: Path, *, duration: float = 1.0) -> bytes:
    created = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=2",
            "-t",
            str(duration),
            "-pix_fmt",
            "yuv420p",
            "-y",
            os.fspath(path),
        ],
        capture_output=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr.decode("utf-8", errors="replace")
    return path.read_bytes()


@pytest.fixture(autouse=True)
def _clear_probe_cache() -> None:
    video_evidence.clear_video_artifact_probe_cache()


def test_declared_limits_and_public_receipts_are_immutable() -> None:
    assert video_evidence.VIDEO_MAX_INPUT_BYTES == 8 * 1024**3
    assert video_evidence.VIDEO_MAX_STREAMS == 64
    assert video_evidence.VIDEO_FFPROBE_STDOUT_BYTES == 256 * 1024
    assert video_evidence.VIDEO_FFPROBE_STDERR_BYTES == 64 * 1024
    assert video_evidence.VIDEO_DIGEST_CHUNK_BYTES == 1024 * 1024
    assert video_evidence.VIDEO_METADATA_LIMITS.wall_seconds == 15
    assert video_evidence.VIDEO_METADATA_LIMITS.max_memory_bytes == 256 * 1024**2
    assert video_evidence.VIDEO_METADATA_LIMITS.max_processes == 1
    assert video_evidence.VIDEO_PROBE_LIMITS.wall_seconds == 300
    assert video_evidence.VIDEO_PROBE_LIMITS.max_memory_bytes == 512 * 1024**2
    assert video_evidence.VIDEO_PROBE_LIMITS.max_processes == 2

    probe = _probe(_generation())
    with pytest.raises(FrozenInstanceError):
        probe.duration_seconds = 2.0
    assessment = video_evidence.VideoEvidenceAssessment()
    with pytest.raises(AttributeError, match="immutable"):
        assessment.extra = True


def test_invalid_public_locators_are_path_neutral_and_do_not_start_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign = "/foreign/talk.mp4" if os.name == "nt" else r"C:\talk.mp4"
    cases = [
        ("talk.mp4", None, "artifact_locator_trusted_root_required"),
        ("../talk.mp4", tmp_path, "artifact_locator_dot_segment"),
        ("bad\x00name.mp4", tmp_path, "artifact_locator_nul_byte"),
        ("talk.avi", tmp_path, "video_suffix_unsupported"),
        (foreign, None, "artifact_locator_foreign_absolute"),
    ]
    monkeypatch.setattr(
        video_evidence,
        "_invoke_metadata_worker",
        lambda *_args, **_kwargs: pytest.fail("invalid locator started metadata"),
    )

    for locator, root, expected in cases:
        with pytest.raises(video_evidence.VideoEvidenceError) as caught:
            video_evidence.probe_video_artifact(locator, trusted_root=root)
        assert caught.value.reason_code == "video_evidence_invalid"
        assert caught.value.details == {"locator_failure": expected}
        assert str(locator) not in str(caught.value)
        assert str(locator) not in repr(caught.value.details)


def test_metadata_child_closes_root_escape_symlink_and_nonregular_failures(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    redirected = root / "redirected.mp4"
    directory = root / "directory.mp4"
    directory.mkdir()

    cases = [
        (outside, "root_escape"),
        (directory, "not_regular"),
    ]
    try:
        redirected.symlink_to(outside)
    except OSError:
        pass
    else:
        cases.append((redirected, "symlink_or_reparse"))
    for artifact, failure_kind in cases:
        payload = video_evidence._metadata_child(
            {
                "video_path": os.fspath(artifact),
                "trusted_root": os.fspath(root),
            }
        )
        assert payload["status"] == "unavailable"
        assert payload["reason_code"] == "video_artifact_unavailable"
        assert payload["details"]["failure_kind"] == failure_kind
        assert os.fspath(artifact) not in repr(payload)


def test_real_worker_probes_tiny_mp4_and_reuses_only_same_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "talk.mp4"
    source = _create_mp4(artifact)
    assessment = video_evidence.VideoEvidenceAssessment()

    first = assessment.probe("talk.mp4", trusted_root=tmp_path)

    assert first.source_sha256 == hashlib.sha256(source).hexdigest()
    assert first.source_size_bytes == len(source)
    assert first.duration_seconds == pytest.approx(1.0, abs=0.05)
    assert first.duration_source == "format"
    assert first.container_family == "iso_bmff"
    assert first.stream_count == 1
    assert first.video_stream_count == 1
    assert first.audio_stream_count == 0
    assert first.attached_picture_count == 0
    assert first.other_stream_count == 0
    assert first.parser_diagnostics == video_evidence.DiagnosticReceipt.empty()

    monkeypatch.setattr(
        video_evidence,
        "_invoke_probe_worker",
        lambda *_args, **_kwargs: pytest.fail(
            "same generation should reuse the immutable probe"
        ),
    )
    second = assessment.probe(artifact, trusted_root=tmp_path)
    assert second == first


@pytest.mark.parametrize(
    ("suffix", "codec", "expected_family"),
    [
        (".mov", "mpeg4", "iso_bmff"),
        (".webm", "libvpx-vp9", "matroska_webm"),
        (".mkv", "ffv1", "matroska_webm"),
    ],
)
def test_real_worker_accepts_each_declared_container_family(
    tmp_path: Path,
    suffix: str,
    codec: str,
    expected_family: str,
) -> None:
    artifact = tmp_path / f"talk{suffix}"
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
            codec,
            "-pix_fmt",
            "yuv420p",
            "-y",
            os.fspath(artifact),
        ],
        capture_output=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr.decode("utf-8", errors="replace")

    probe = video_evidence.VideoEvidenceAssessment().probe(
        artifact.name,
        trusted_root=tmp_path,
    )

    assert probe.container_family == expected_family
    assert probe.video_stream_count == 1
    assert probe.duration_seconds == pytest.approx(1.0, abs=0.1)


def test_assessment_revalidates_success_and_reprobes_a_new_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_generation = _generation(inode=1)
    second_generation = _generation(inode=2)
    receipts = iter(
        [
            _receipt(first_generation, _root_generation()),
            _receipt(second_generation, _root_generation()),
        ]
    )
    probes: list[int] = []
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: next(receipts),
    )

    def run_probe(
        _artifact: Path,
        *,
        receipt: Any,
        **_kwargs: object,
    ) -> Any:
        probes.append(receipt.generation.inode)
        return _probe(
            receipt.generation,
            root_generation=receipt.root_generation,
            digest=("a" if receipt.generation.inode == 1 else "b") * 64,
        )

    monkeypatch.setattr(video_evidence, "_run_bounded_video_probe", run_probe)
    assessment = video_evidence.VideoEvidenceAssessment()

    first = assessment.probe("talk.mp4", trusted_root=tmp_path)
    second = assessment.probe("talk.mp4", trusted_root=tmp_path)

    assert probes == [1, 2]
    assert first.source_sha256 != second.source_sha256


def test_transient_failure_is_reused_in_one_assessment_but_not_globally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    metadata_calls = 0
    probe_calls = 0

    def metadata(*_args: object, **_kwargs: object) -> Any:
        nonlocal metadata_calls
        metadata_calls += 1
        return _receipt(generation, _root_generation())

    def probe(*_args: object, **_kwargs: object) -> Any:
        nonlocal probe_calls
        probe_calls += 1
        if probe_calls == 1:
            raise video_evidence._failure("video_probe_timeout")
        return _probe(generation, root_generation=_root_generation())

    monkeypatch.setattr(video_evidence, "_run_bounded_metadata_worker", metadata)
    monkeypatch.setattr(video_evidence, "_run_bounded_video_probe", probe)
    first_assessment = video_evidence.VideoEvidenceAssessment()

    for _ in range(2):
        with pytest.raises(video_evidence.VideoEvidenceError) as caught:
            first_assessment.probe("talk.mp4", trusted_root=tmp_path)
        assert caught.value.reason_code == "video_probe_timeout"

    result = video_evidence.VideoEvidenceAssessment().probe(
        "talk.mp4", trusted_root=tmp_path
    )
    assert result.generation == generation
    assert metadata_calls == 2
    assert probe_calls == 2


def test_stable_generation_failure_is_revalidated_then_reused_globally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    metadata_calls = 0
    probe_calls = 0

    def metadata(*_args: object, **_kwargs: object) -> Any:
        nonlocal metadata_calls
        metadata_calls += 1
        return _receipt(generation, _root_generation())

    def rejected(*_args: object, **_kwargs: object) -> Any:
        nonlocal probe_calls
        probe_calls += 1
        raise video_evidence._failure("video_invalid_container")

    monkeypatch.setattr(video_evidence, "_run_bounded_metadata_worker", metadata)
    monkeypatch.setattr(video_evidence, "_run_bounded_video_probe", rejected)

    for _ in range(2):
        with pytest.raises(video_evidence.VideoEvidenceError) as caught:
            video_evidence.VideoEvidenceAssessment().probe(
                "talk.mp4", trusted_root=tmp_path
            )
        assert caught.value.reason_code == "video_invalid_container"

    assert metadata_calls == 2
    assert probe_calls == 1


@pytest.mark.parametrize(
    ("flags", "file_attributes"),
    [
        pytest.param(
            video_evidence.VIDEO_MACOS_DATALESS_FLAG,
            None,
            marks=pytest.mark.skipif(
                video_evidence.VIDEO_MACOS_DATALESS_FLAG == 0,
                reason="macOS dataless flag is unavailable on this platform",
            ),
        ),
        (None, artifact_metadata.WINDOWS_OFFLINE_ATTRIBUTE),
        (None, artifact_metadata.WINDOWS_RECALL_ON_OPEN_ATTRIBUTE),
        (None, artifact_metadata.WINDOWS_RECALL_ON_DATA_ACCESS_ATTRIBUTE),
    ],
)
def test_placeholder_short_circuits_before_probe_or_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flags: int | None,
    file_attributes: int | None,
) -> None:
    generation = _generation(flags=flags, file_attributes=file_attributes)
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: _receipt(generation, _root_generation()),
    )
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_video_probe",
        lambda *_args, **_kwargs: pytest.fail("placeholder reached probe or digest"),
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.probe_video_artifact("talk.mp4", trusted_root=tmp_path)

    assert caught.value.reason_code == "video_cloud_placeholder_unavailable"
    assert caught.value.details["availability"]["state"] == "unavailable"
    assert caught.value.details["reparse_tag"] is None


def test_windows_cloud_reparse_placeholder_stops_before_probe_or_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cloud_tag = min(video_evidence.VIDEO_WINDOWS_CLOUD_REPARSE_TAGS)
    generation = _generation(
        file_attributes=(
            video_evidence.VIDEO_WINDOWS_REPARSE_POINT_ATTRIBUTE
            | artifact_metadata.WINDOWS_OFFLINE_ATTRIBUTE
        )
    )
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: _receipt(
            generation,
            _root_generation(),
            reparse_tag=cloud_tag,
        ),
    )
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_video_probe",
        lambda *_args, **_kwargs: pytest.fail(
            "cloud reparse placeholder reached ffprobe or digest"
        ),
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.probe_video_artifact("talk.mp4", trusted_root=tmp_path)

    assert caught.value.reason_code == "video_cloud_placeholder_unavailable"
    assert caught.value.details["availability"]["state"] == "unavailable"
    assert caught.value.details["reparse_tag"] == cloud_tag


def test_size_ceiling_short_circuits_before_probe_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation(size=video_evidence.VIDEO_MAX_INPUT_BYTES + 1)
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: _receipt(generation, _root_generation()),
    )
    monkeypatch.setattr(
        video_evidence,
        "_invoke_probe_worker",
        lambda *_args, **_kwargs: pytest.fail("oversized input started probe"),
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.probe_video_artifact("large.mp4", trusted_root=tmp_path)

    assert caught.value.reason_code == "video_artifact_too_large"
    assert caught.value.details == {"limit_bytes": video_evidence.VIDEO_MAX_INPUT_BYTES}


@pytest.mark.parametrize(
    ("failure_kind", "expected_lane"),
    [
        ("missing", "missing"),
        ("io", "unavailable"),
        ("not_regular", "unreadable"),
        ("root_escape", "unreadable"),
        ("symlink_or_reparse", "unreadable"),
    ],
)
def test_metadata_failure_taxonomy_is_closed_for_preflight_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
    expected_lane: str,
) -> None:
    del expected_lane
    error = video_evidence._failure(
        "video_artifact_unavailable",
        details={"failure_kind": failure_kind, "exception_type": "OSError"},
    )
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.probe_video_artifact("talk.mp4", trusted_root=tmp_path)

    assert caught.value.reason_code == "video_artifact_unavailable"
    assert caught.value.details == {
        "failure_kind": failure_kind,
        "exception_type": "OSError",
    }


def test_ffprobe_success_diagnostics_require_repair_without_raw_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "private-speaker-name.mp4"
    raw_diagnostic = b"private-speaker-name.mp4: non-fatal edit-list warning"
    receipt = video_evidence.DiagnosticReceipt(
        byte_count=len(raw_diagnostic),
        sha256=hashlib.sha256(raw_diagnostic).hexdigest(),
        truncated=False,
    )
    monkeypatch.setattr(
        video_evidence,
        "_run_ffprobe",
        lambda _artifact: (b"{}", receipt, 0),
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence._probe_media_with_ffprobe(
            artifact,
            expected_container_family="iso_bmff",
        )

    assert caught.value.reason_code == "video_parser_repair_required"
    assert caught.value.details == {"diagnostic_receipt": receipt.to_dict()}
    assert "private-speaker-name" not in str(caught.value)
    assert "private-speaker-name" not in repr(caught.value.details)
    assert raw_diagnostic.decode() not in repr(caught.value.details)


def test_missing_ffprobe_is_a_closed_dependency_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "private-name.mp4"
    monkeypatch.setattr(video_evidence.shutil, "which", lambda _name: None)

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence._run_ffprobe(artifact)

    assert caught.value.reason_code == "video_dependency_unavailable"
    assert caught.value.details == {"dependency": "ffprobe"}
    assert "private-name" not in str(caught.value)
    assert "private-name" not in repr(caught.value.details)


def test_duration_prefers_format_then_falls_back_to_usable_media_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "talk.mp4"

    def run(document: bytes) -> dict[str, object]:
        monkeypatch.setattr(
            video_evidence,
            "_run_ffprobe",
            lambda _artifact: (
                document,
                video_evidence.DiagnosticReceipt.empty(),
                0,
            ),
        )
        return video_evidence._probe_media_with_ffprobe(
            artifact,
            expected_container_family="iso_bmff",
        )

    format_result = run(
        b'{"format":{"format_name":"mov,mp4","duration":"3.5"},'
        b'"streams":[{"codec_type":"video","duration":"2.0"}]}'
    )
    fallback_result = run(
        b'{"format":{"format_name":"mov,mp4","duration":"N/A"},'
        b'"streams":[{"codec_type":"video","duration":"2.0"},'
        b'{"codec_type":"audio","duration":"2.5"}]}'
    )

    assert format_result["duration_seconds"] == 3.5
    assert format_result["duration_source"] == "format"
    assert fallback_result["duration_seconds"] == 2.5
    assert fallback_result["duration_source"] == "stream"


def test_attached_picture_is_not_a_usable_video_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = (
        b'{"format":{"format_name":"mov,mp4","duration":"1"},'
        b'"streams":[{"codec_type":"audio"},'
        b'{"codec_type":"video","disposition":{"attached_pic":1}}]}'
    )
    monkeypatch.setattr(
        video_evidence,
        "_run_ffprobe",
        lambda _artifact: (
            document,
            video_evidence.DiagnosticReceipt.empty(),
            0,
        ),
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence._probe_media_with_ffprobe(
            tmp_path / "album-art.mp4",
            expected_container_family="iso_bmff",
        )

    assert caught.value.reason_code == "video_no_video_stream"


def test_wrong_container_and_stream_ceiling_are_closed_rejections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "talk.mp4"
    documents = iter(
        [
            b'{"format":{"format_name":"matroska,webm","duration":"1"},'
            b'"streams":[{"codec_type":"video"}]}',
            (
                b'{"format":{"format_name":"mov,mp4","duration":"1"},'
                b'"streams":['
                + b",".join(b'{"codec_type":"video"}' for _ in range(65))
                + b"]}"
            ),
        ]
    )
    monkeypatch.setattr(
        video_evidence,
        "_run_ffprobe",
        lambda _artifact: (
            next(documents),
            video_evidence.DiagnosticReceipt.empty(),
            0,
        ),
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as wrong:
        video_evidence._probe_media_with_ffprobe(
            artifact, expected_container_family="iso_bmff"
        )
    with pytest.raises(video_evidence.VideoEvidenceError) as streams:
        video_evidence._probe_media_with_ffprobe(
            artifact, expected_container_family="iso_bmff"
        )

    assert wrong.value.reason_code == "video_invalid_container"
    assert streams.value.reason_code == "video_stream_limit"
    assert streams.value.details == {"max_streams": 64}


@pytest.mark.parametrize(
    ("supervisor_reason", "supervisor_details", "public_reason"),
    [
        ("worker_timeout", {}, "video_probe_timeout"),
        ("worker_monitor_unavailable", {}, "video_probe_monitor_unavailable"),
        (
            "worker_monitor_unavailable",
            {"dependency": "psutil"},
            "video_dependency_unavailable",
        ),
        (
            "worker_monitor_identity_changed",
            {},
            "video_probe_monitor_identity_changed",
        ),
        (
            "worker_containment_unavailable",
            {},
            "video_probe_containment_unavailable",
        ),
        (
            "worker_process_tree_leak",
            {},
            "video_probe_containment_unavailable",
        ),
        (
            "worker_cleanup_failed",
            {},
            "video_probe_containment_unavailable",
        ),
        (
            "worker_memory_limit_exceeded",
            {},
            "video_probe_resource_unavailable",
        ),
        (
            "worker_process_limit_exceeded",
            {},
            "video_probe_resource_unavailable",
        ),
        (
            "worker_diagnostic_limit_exceeded",
            {},
            "video_probe_resource_unavailable",
        ),
        ("worker_input_limit_exceeded", {}, "video_probe_request_oversized"),
        ("worker_output_limit_exceeded", {}, "video_probe_result_oversized"),
        ("worker_start_failed", {}, "video_probe_start_failure"),
        ("worker_pipe_setup_failed", {}, "video_probe_start_failure"),
        ("worker_exit_before_barrier", {}, "video_probe_start_failure"),
        ("worker_request_write_failed", {}, "video_probe_start_failure"),
        ("invalid_worker_command", {}, "video_probe_start_failure"),
        ("unsafe_worker_process_metadata", {}, "video_probe_start_failure"),
        ("worker_exit", {}, "video_probe_crash"),
        ("worker_diagnostic_read_failed", {}, "video_probe_crash"),
        ("worker_output_read_failed", {}, "video_probe_crash"),
        (
            "worker_response_authentication_failed",
            {},
            "video_probe_malformed_result",
        ),
        (
            "worker_generation_changed",
            {"generation_names": ["video", "private/path.mp4"]},
            "video_artifact_changed",
        ),
    ],
)
def test_supervisor_failures_map_distinctly_without_raw_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supervisor_reason: str,
    supervisor_details: dict[str, object],
    public_reason: str,
) -> None:
    generation = _generation()
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: _receipt(generation, _root_generation()),
    )

    def failed(*_args: object, **_kwargs: object) -> Any:
        raise video_evidence.SupervisorError(
            supervisor_reason,
            cast_supervisor_details(supervisor_details),
        )

    monkeypatch.setattr(video_evidence, "_invoke_probe_worker", failed)

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.probe_video_artifact("talk.mp4", trusted_root=tmp_path)

    assert caught.value.reason_code == public_reason
    assert "private/path.mp4" not in repr(caught.value.details)
    if public_reason == "video_artifact_changed":
        assert caught.value.details == {"generation_names": ["video"]}


def cast_supervisor_details(value: dict[str, object]) -> Any:
    """Keep test-side construction explicit without weakening production types."""
    return value


def test_malformed_authenticated_success_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: _receipt(generation, _root_generation()),
    )
    malformed = _worker_result(
        generation,
        payload={
            "schema_version": video_evidence.VIDEO_PROBE_SCHEMA_VERSION,
            "status": "available",
            "source_sha256": "not-a-digest",
            "source_size_bytes": generation.size,
            "duration_seconds": 1.0,
            "duration_source": "format",
            "container_family": "iso_bmff",
            "stream_count": 1,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "attached_picture_count": 0,
            "other_stream_count": 0,
        },
    )
    monkeypatch.setattr(
        video_evidence,
        "_invoke_probe_worker",
        lambda *_args, **_kwargs: malformed,
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.probe_video_artifact("talk.mp4", trusted_root=tmp_path)

    assert caught.value.reason_code == "video_probe_malformed_result"


def test_private_snapshot_is_distinct_and_digest_bound_to_source(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "talk.mp4"
    original = b"platform-neutral-source-generation"
    artifact.write_bytes(original)
    generation = video_evidence.FileGeneration.from_stat(artifact.stat())

    with video_evidence._prepared_video_source(artifact, generation) as prepared:
        assert prepared.probe_artifact != artifact
        assert prepared.probe_artifact.read_bytes() == original
        digest = video_evidence._digest_exact_generation(
            prepared.probe_artifact,
            prepared.probe_generation,
            source_descriptor=prepared.probe_descriptor,
        )

    assert digest == hashlib.sha256(original).hexdigest()


@pytest.mark.skipif(
    os.name == "nt",
    reason="concrete directory-swap reproduction requires POSIX rename semantics",
)
def test_ffprobe_facts_and_digest_share_one_snapshot_during_path_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    current = root / "current"
    alternate = root / "alternate"
    saved = root / "saved"
    current.mkdir(parents=True)
    alternate.mkdir()
    artifact = current / "talk.mp4"
    original = b"original-generation-a"
    replacement = b"replacement-generation-b"
    artifact.write_bytes(original)
    (alternate / artifact.name).write_bytes(replacement)
    before = video_evidence.inspect_metadata_generation(
        artifact,
        trusted_root=root,
        reparse_point_attribute=video_evidence.VIDEO_WINDOWS_REPARSE_POINT_ATTRIBUTE,
        cloud_reparse_tags=video_evidence.VIDEO_WINDOWS_CLOUD_REPARSE_TAGS,
    )
    assert before.root_generation is not None

    def parse_snapshot(
        probe_artifact: Path,
        **_kwargs: object,
    ) -> dict[str, object]:
        current.rename(saved)
        alternate.rename(current)
        try:
            parsed = probe_artifact.read_bytes()
        finally:
            current.rename(alternate)
            saved.rename(current)
        return {
            "duration_seconds": 1.0 if parsed == original else 999.0,
            "duration_source": "format",
            "container_family": "iso_bmff",
            "stream_count": 1,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "attached_picture_count": 0,
            "other_stream_count": 0,
        }

    monkeypatch.setattr(
        video_evidence,
        "_probe_media_with_ffprobe",
        parse_snapshot,
    )
    request = artifact_supervisor.build_worker_request(
        video_evidence.VIDEO_PROBE_OPERATION,
        {
            "video": before.generation,
            "video_root": before.root_generation,
        },
        {
            "video_path": os.fspath(artifact),
            "trusted_root": os.fspath(root),
            "expected_container_family": "iso_bmff",
            "max_input_bytes": video_evidence.VIDEO_MAX_INPUT_BYTES,
            "max_streams": video_evidence.VIDEO_MAX_STREAMS,
            "ffprobe_stdout_bytes": video_evidence.VIDEO_FFPROBE_STDOUT_BYTES,
            "ffprobe_stderr_bytes": video_evidence.VIDEO_FFPROBE_STDERR_BYTES,
            "digest_chunk_bytes": video_evidence.VIDEO_DIGEST_CHUNK_BYTES,
        },
        limit_profile_id=video_evidence.VIDEO_PROBE_LIMITS.profile_id,
        schema_generation=video_evidence.VIDEO_PROBE_SCHEMA_VERSION,
        pipeline_generation=video_evidence.VIDEO_PROBE_PIPELINE_VERSION,
    )

    payload, observed = video_evidence._dispatch_supervised_worker(request)
    after = video_evidence.inspect_metadata_generation(
        artifact,
        trusted_root=root,
        reparse_point_attribute=video_evidence.VIDEO_WINDOWS_REPARSE_POINT_ATTRIBUTE,
        cloud_reparse_tags=video_evidence.VIDEO_WINDOWS_CLOUD_REPARSE_TAGS,
    )

    assert before == after
    assert observed == {
        "video": before.generation,
        "video_root": before.root_generation,
    }
    assert payload["duration_seconds"] == 1.0
    assert payload["source_sha256"] == hashlib.sha256(original).hexdigest()


def test_generation_change_between_ffprobe_and_digest_is_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "talk.mp4"
    artifact.write_bytes(b"source generation")
    generation = video_evidence.FileGeneration.from_stat(artifact.stat())
    changed = _generation(inode=2)
    receipts = iter([_receipt(generation), _receipt(changed)])
    monkeypatch.setattr(
        video_evidence,
        "_metadata_receipt_in_probe_worker",
        lambda *_args, **_kwargs: next(receipts),
    )
    monkeypatch.setattr(
        video_evidence,
        "_probe_media_with_ffprobe",
        lambda *_args, **_kwargs: {
            "duration_seconds": 1.0,
            "duration_source": "format",
            "container_family": "iso_bmff",
            "stream_count": 1,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "attached_picture_count": 0,
            "other_stream_count": 0,
        },
    )
    monkeypatch.setattr(
        video_evidence,
        "_digest_exact_generation",
        lambda *_args, **_kwargs: pytest.fail("changed generation reached digest"),
    )
    request = artifact_supervisor.build_worker_request(
        video_evidence.VIDEO_PROBE_OPERATION,
        {"video": generation},
        {
            "video_path": os.fspath(tmp_path / "talk.mp4"),
            "trusted_root": None,
            "expected_container_family": "iso_bmff",
            "max_input_bytes": video_evidence.VIDEO_MAX_INPUT_BYTES,
            "max_streams": video_evidence.VIDEO_MAX_STREAMS,
            "ffprobe_stdout_bytes": video_evidence.VIDEO_FFPROBE_STDOUT_BYTES,
            "ffprobe_stderr_bytes": video_evidence.VIDEO_FFPROBE_STDERR_BYTES,
            "digest_chunk_bytes": video_evidence.VIDEO_DIGEST_CHUNK_BYTES,
        },
        limit_profile_id=video_evidence.VIDEO_PROBE_LIMITS.profile_id,
        schema_generation=video_evidence.VIDEO_PROBE_SCHEMA_VERSION,
        pipeline_generation=video_evidence.VIDEO_PROBE_PIPELINE_VERSION,
    )

    with pytest.raises(video_evidence.SupervisorError) as caught:
        video_evidence._dispatch_supervised_worker(request)

    assert caught.value.reason_code == "worker_generation_changed"
    assert caught.value.details == {"generation_names": ["video"]}


def test_generation_change_wins_over_stable_ffprobe_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "talk.mp4"
    artifact.write_bytes(b"source generation")
    generation = video_evidence.FileGeneration.from_stat(artifact.stat())
    changed = _generation(inode=2)
    receipts = iter([_receipt(generation), _receipt(changed)])
    monkeypatch.setattr(
        video_evidence,
        "_metadata_receipt_in_probe_worker",
        lambda *_args, **_kwargs: next(receipts),
    )
    monkeypatch.setattr(
        video_evidence,
        "_probe_media_with_ffprobe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            video_evidence._failure("video_invalid_container")
        ),
    )
    monkeypatch.setattr(
        video_evidence,
        "_digest_exact_generation",
        lambda *_args, **_kwargs: pytest.fail("failed parser reached digest"),
    )
    request = artifact_supervisor.build_worker_request(
        video_evidence.VIDEO_PROBE_OPERATION,
        {"video": generation},
        {
            "video_path": os.fspath(tmp_path / "talk.mp4"),
            "trusted_root": None,
            "expected_container_family": "iso_bmff",
            "max_input_bytes": video_evidence.VIDEO_MAX_INPUT_BYTES,
            "max_streams": video_evidence.VIDEO_MAX_STREAMS,
            "ffprobe_stdout_bytes": video_evidence.VIDEO_FFPROBE_STDOUT_BYTES,
            "ffprobe_stderr_bytes": video_evidence.VIDEO_FFPROBE_STDERR_BYTES,
            "digest_chunk_bytes": video_evidence.VIDEO_DIGEST_CHUNK_BYTES,
        },
        limit_profile_id=video_evidence.VIDEO_PROBE_LIMITS.profile_id,
        schema_generation=video_evidence.VIDEO_PROBE_SCHEMA_VERSION,
        pipeline_generation=video_evidence.VIDEO_PROBE_PIPELINE_VERSION,
    )

    with pytest.raises(video_evidence.SupervisorError) as caught:
        video_evidence._dispatch_supervised_worker(request)

    assert caught.value.reason_code == "worker_generation_changed"
    assert caught.value.details == {"generation_names": ["video"]}


def test_digest_growth_maps_to_generation_change_not_ffprobe_output_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "talk.mp4"
    artifact.write_bytes(b"x")
    expected = video_evidence.FileGeneration.from_stat(artifact.stat())
    reads = iter([b"xx", b""])
    monkeypatch.setattr(video_evidence.os, "read", lambda *_args: next(reads))

    with pytest.raises(video_evidence.SupervisorError) as caught:
        video_evidence._digest_exact_generation(artifact, expected)

    assert caught.value.reason_code == "worker_generation_changed"
    assert caught.value.details == {"generation_names": ["video"]}


def test_singleflight_waiter_deadline_does_not_cancel_leader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    receipt = _receipt(generation, _root_generation())
    leader_started = threading.Event()
    release_leader = threading.Event()
    probe_calls = 0
    leader_results: list[Any] = []
    leader_errors: list[Any] = []

    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )

    def slow_probe(*_args: object, **_kwargs: object) -> Any:
        nonlocal probe_calls
        probe_calls += 1
        leader_started.set()
        assert release_leader.wait(timeout=2)
        return _probe(generation, root_generation=receipt.root_generation)

    monkeypatch.setattr(video_evidence, "_run_bounded_video_probe", slow_probe)
    leader_assessment = video_evidence.VideoEvidenceAssessment()
    waiter_assessment = video_evidence.VideoEvidenceAssessment()
    clock = [100.0]
    waiter_deadline = 100.1
    monkeypatch.setattr(video_evidence.time, "monotonic", lambda: clock[0])

    def lead() -> None:
        try:
            leader_results.append(
                leader_assessment.probe("talk.mp4", trusted_root=tmp_path)
            )
        except video_evidence.VideoEvidenceError as exc:
            leader_errors.append(exc)

    thread = threading.Thread(target=lead)
    thread.start()
    assert leader_started.wait(timeout=1)

    clock[0] = waiter_deadline
    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        waiter_assessment.probe(
            "talk.mp4",
            trusted_root=tmp_path,
            deadline_monotonic=waiter_deadline,
        )
    assert caught.value.reason_code == "video_batch_wall_limit"
    assert thread.is_alive()

    release_leader.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert not leader_errors
    assert len(leader_results) == 1
    assert probe_calls == 1

    with pytest.raises(video_evidence.VideoEvidenceError) as repeated:
        waiter_assessment.probe("talk.mp4", trusted_root=tmp_path)
    assert repeated.value.reason_code == "video_batch_wall_limit"
    assert probe_calls == 1


def test_transient_short_deadline_leader_does_not_poison_unrelated_waiter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    receipt = _receipt(generation, _root_generation())
    leader_started = threading.Event()
    waiter_joined = threading.Event()
    release_leader = threading.Event()
    probe_calls = 0
    leader_errors: list[str] = []
    waiter_errors: list[str] = []
    waiter_results: list[Any] = []

    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )

    def flaky_probe(*_args: object, **kwargs: object) -> Any:
        nonlocal probe_calls
        probe_calls += 1
        if probe_calls == 1:
            assert kwargs["deadline_monotonic"] == leader_deadline
            leader_started.set()
            assert release_leader.wait(timeout=2)
            video_evidence._limits_before_deadline(
                video_evidence.VIDEO_PROBE_LIMITS,
                leader_deadline,
            )
            raise AssertionError("expired controlled deadline was accepted")
        assert kwargs["deadline_monotonic"] is None
        return _probe(generation, root_generation=receipt.root_generation)

    monkeypatch.setattr(video_evidence, "_run_bounded_video_probe", flaky_probe)
    original_wait = video_evidence._wait_for_flight

    def observed_wait(*args: object, **kwargs: object) -> Any:
        waiter_joined.set()
        return original_wait(*args, **kwargs)

    monkeypatch.setattr(video_evidence, "_wait_for_flight", observed_wait)
    leader_assessment = video_evidence.VideoEvidenceAssessment()
    waiter_assessment = video_evidence.VideoEvidenceAssessment()
    clock = [100.0]
    leader_deadline = clock[0] + video_evidence.VIDEO_PROBE_LIMITS.cleanup_seconds + 1.0
    monkeypatch.setattr(video_evidence.time, "monotonic", lambda: clock[0])

    def lead() -> None:
        try:
            leader_assessment.probe(
                "talk.mp4",
                trusted_root=tmp_path,
                deadline_monotonic=leader_deadline,
            )
        except video_evidence.VideoEvidenceError as exc:
            leader_errors.append(exc.reason_code)

    def wait() -> None:
        try:
            waiter_results.append(
                waiter_assessment.probe("talk.mp4", trusted_root=tmp_path)
            )
        except video_evidence.VideoEvidenceError as exc:
            waiter_errors.append(exc.reason_code)

    leader_thread = threading.Thread(target=lead)
    waiter_thread = threading.Thread(target=wait)
    leader_thread.start()
    assert leader_started.wait(timeout=1)
    waiter_thread.start()
    try:
        assert waiter_joined.wait(timeout=1)
        clock[0] = leader_deadline
    finally:
        release_leader.set()
    leader_thread.join(timeout=2)
    waiter_thread.join(timeout=2)

    assert not leader_thread.is_alive()
    assert not waiter_thread.is_alive()
    assert leader_errors == ["video_batch_wall_limit"]
    assert not waiter_errors
    assert len(waiter_results) == 1
    assert probe_calls == 2
    assert (
        waiter_assessment.probe("talk.mp4", trusted_root=tmp_path) == waiter_results[0]
    )
    assert probe_calls == 2


def test_transient_leader_failure_is_shared_with_waiter_in_same_assessment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation()
    receipt = _receipt(generation, _root_generation())
    leader_started = threading.Event()
    waiter_joined = threading.Event()
    release_leader = threading.Event()
    probe_calls = 0
    errors: list[str] = []

    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: receipt,
    )

    def transient_probe(*_args: object, **_kwargs: object) -> Any:
        nonlocal probe_calls
        probe_calls += 1
        leader_started.set()
        assert release_leader.wait(timeout=2)
        raise video_evidence._failure("video_probe_timeout")

    monkeypatch.setattr(video_evidence, "_run_bounded_video_probe", transient_probe)
    original_wait = video_evidence._wait_for_flight

    def observed_wait(*args: object, **kwargs: object) -> Any:
        waiter_joined.set()
        return original_wait(*args, **kwargs)

    monkeypatch.setattr(video_evidence, "_wait_for_flight", observed_wait)
    assessment = video_evidence.VideoEvidenceAssessment()

    def run() -> None:
        try:
            assessment.probe("talk.mp4", trusted_root=tmp_path)
        except video_evidence.VideoEvidenceError as exc:
            errors.append(exc.reason_code)

    leader_thread = threading.Thread(target=run)
    waiter_thread = threading.Thread(target=run)
    leader_thread.start()
    assert leader_started.wait(timeout=1)
    waiter_thread.start()
    try:
        assert waiter_joined.wait(timeout=1)
    finally:
        release_leader.set()
    leader_thread.join(timeout=2)
    waiter_thread.join(timeout=2)

    assert not leader_thread.is_alive()
    assert not waiter_thread.is_alive()
    assert errors == ["video_probe_timeout", "video_probe_timeout"]
    assert probe_calls == 1
    with pytest.raises(video_evidence.VideoEvidenceError) as repeated:
        assessment.probe("talk.mp4", trusted_root=tmp_path)
    assert repeated.value.reason_code == "video_probe_timeout"
    assert probe_calls == 1


def test_real_worker_rejects_audio_only_wrong_container_and_corrupt_inputs(
    tmp_path: Path,
) -> None:
    audio_only = tmp_path / "audio.mp4"
    created_audio = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.25",
            "-vn",
            "-c:a",
            "aac",
            "-y",
            os.fspath(audio_only),
        ],
        capture_output=True,
        check=False,
    )
    assert created_audio.returncode == 0, created_audio.stderr

    wrong_container = tmp_path / "renamed.mp4"
    created_webm = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=1",
            "-t",
            "0.25",
            "-c:v",
            "ffv1",
            "-f",
            "matroska",
            "-y",
            os.fspath(wrong_container),
        ],
        capture_output=True,
        check=False,
    )
    assert created_webm.returncode == 0, created_webm.stderr

    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not a media container")
    valid_for_truncation = tmp_path / "valid-for-truncation.mp4"
    valid_source = _create_mp4(valid_for_truncation)
    truncated = tmp_path / "truncated.mp4"
    truncated.write_bytes(valid_source[: max(1, len(valid_source) // 4)])

    expected = {
        audio_only: "video_no_video_stream",
        wrong_container: "video_invalid_container",
        corrupt: "video_parser_rejected",
        truncated: "video_parser_rejected",
    }
    for artifact, reason_code in expected.items():
        with pytest.raises(video_evidence.VideoEvidenceError) as caught:
            video_evidence.probe_video_artifact(artifact, trusted_root=tmp_path)
        assert caught.value.reason_code == reason_code
        assert os.fspath(artifact) not in str(caught.value)
        assert os.fspath(artifact) not in repr(caught.value.details)


def test_empty_container_rejects_before_probe_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation(size=0)
    monkeypatch.setattr(
        video_evidence,
        "_run_bounded_metadata_worker",
        lambda *_args, **_kwargs: _receipt(generation, _root_generation()),
    )
    monkeypatch.setattr(
        video_evidence,
        "_invoke_probe_worker",
        lambda *_args, **_kwargs: pytest.fail("empty input started ffprobe worker"),
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.probe_video_artifact("empty.mp4", trusted_root=tmp_path)

    assert caught.value.reason_code == "video_invalid_container"


def _venv_root_link(root: Path) -> Path:
    """Link the running venv to a path under `root`, on either platform.

    The condition under test is that the interpreter's own path contains the
    trusted root — the live vault's `<vault>/.venv/bin/python3`. Reproducing it
    needs a link, not a copy: a copied interpreter loses the venv and fails on
    its own dependencies, which would test the fixture instead of the
    supervisor.

    POSIX gets a symlink. Windows gets a directory junction, which needs no
    privilege where `os.symlink` does. The link is deliberately UNRESOLVED —
    resolving follows through to the base installation and drops the venv's
    site-packages.
    """
    link = root / ".venv"
    if link.exists():
        return link
    source = Path(sys.executable).parent.parent
    if os.name == "nt":
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", os.fspath(link), os.fspath(source)],
            capture_output=True,
            check=False,
        )
        assert created.returncode == 0, created.stderr.decode("utf-8", errors="replace")
    else:
        link.symlink_to(source)
    return link


def _interpreter_under(root: Path) -> Path:
    """The linked venv's interpreter, named as this platform names it."""
    executable = Path(sys.executable)
    return _venv_root_link(root) / executable.parent.name / executable.name


def test_a_video_probe_runs_under_an_interpreter_inside_the_trusted_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The supervisor must not flag the worker's own interpreter as a secret.

    With `config.python_path` inside the vault, `sys.executable` contains the
    trusted root, and without an `immutable_process_identity` declaration the
    guard refuses to start the worker — every video probe failed
    `video_probe_start_failure`.
    """
    artifact = tmp_path / "talk.mp4"
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
            "-pix_fmt",
            "yuv420p",
            "-y",
            os.fspath(artifact),
        ],
        capture_output=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr.decode("utf-8", errors="replace")
    monkeypatch.setattr(sys, "executable", os.fspath(_interpreter_under(tmp_path)))

    probe = video_evidence.VideoEvidenceAssessment().probe(
        artifact.name,
        trusted_root=tmp_path,
    )

    assert probe.duration_seconds == pytest.approx(1.0, abs=0.1)
    assert probe.video_stream_count == 1


def test_source_receipt_round_trips_and_agrees_with_its_own_probe() -> None:
    probe = _probe(_generation())
    receipt = video_evidence.build_video_source_receipt(probe)

    assert video_evidence.validate_video_source_receipt(receipt) == receipt
    assert video_evidence.video_source_receipt_lineage_drift(receipt, probe) == ()
    assert video_evidence.video_source_receipt_generation_drift(receipt, probe) == ()
    assert receipt["probe_schema_version"] == (
        video_evidence.VIDEO_PROBE_SCHEMA_VERSION
    )
    assert receipt["probe_pipeline_version"] == (
        video_evidence.VIDEO_PROBE_PIPELINE_VERSION
    )


def test_source_receipt_is_path_neutral_and_carries_no_parser_output() -> None:
    generation = _generation()
    probe = video_evidence.VideoArtifactProbe(
        generation=generation,
        root_generation=_root_generation(),
        availability=video_evidence.ArtifactAvailability.from_generation(generation),
        source_sha256="b" * 64,
        source_size_bytes=generation.size,
        duration_seconds=1.0,
        duration_source="format",
        container_family="iso_bmff",
        stream_count=1,
        video_stream_count=1,
        audio_stream_count=0,
        attached_picture_count=0,
        other_stream_count=0,
        parser_diagnostics=video_evidence.DiagnosticReceipt(
            byte_count=512,
            sha256="c" * 64,
            truncated=True,
        ),
    )

    receipt = video_evidence.build_video_source_receipt(probe)

    assert set(receipt) == set(video_evidence.VIDEO_SOURCE_RECEIPT_FIELDS)
    assert "parser_diagnostics" not in receipt
    assert "c" * 64 not in json.dumps(receipt)
    assert "/" not in json.dumps(receipt)


@pytest.mark.parametrize(
    ("mutate", "field"),
    [
        (lambda receipt: receipt.pop("container_family"), "source_receipt"),
        (
            lambda receipt: receipt.update(artifact_path="/vault/talk.mp4"),
            ("source_receipt"),
        ),
        (lambda receipt: receipt.update(schema_version=2), "schema_version"),
        (
            lambda receipt: receipt.update(probe_schema_version=99),
            ("probe_schema_version"),
        ),
        (
            lambda receipt: receipt.update(source_sha256="not-a-digest"),
            ("source_sha256"),
        ),
        (lambda receipt: receipt.update(source_size_bytes=0), "source_size_bytes"),
        (lambda receipt: receipt.update(duration_seconds=0), "duration_seconds"),
        (lambda receipt: receipt.update(duration_source="guess"), "duration_source"),
        (lambda receipt: receipt.update(container_family="ogg"), "container_family"),
        (lambda receipt: receipt.update(audio_stream_count=7), "stream_count"),
        (lambda receipt: receipt.update(video_stream_count=0), "video_stream_count"),
        (
            lambda receipt: receipt.update(source_generation={"size": 1}),
            ("source_generation"),
        ),
    ],
)
def test_source_receipt_rejects_a_shape_no_probe_could_have_produced(
    mutate: Any,
    field: str,
) -> None:
    receipt = video_evidence.build_video_source_receipt(_probe(_generation()))
    mutate(receipt)

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.validate_video_source_receipt(receipt)

    assert caught.value.reason_code == "video_source_receipt_invalid"
    assert caught.value.details == {"field": field}


def test_source_receipt_generation_must_agree_with_the_probed_byte_count() -> None:
    receipt = video_evidence.build_video_source_receipt(_probe(_generation(size=1_024)))
    receipt["source_generation"] = dict(receipt["source_generation"], size=2_048)

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.validate_video_source_receipt(receipt)

    assert caught.value.details == {"field": "source_generation"}


def test_dataless_placeholder_generation_can_never_back_a_receipt() -> None:
    """A cloud stub stays unavailable; hydration is the only way forward."""
    receipt = video_evidence.build_video_source_receipt(_probe(_generation()))
    receipt["source_generation"] = dict(
        receipt["source_generation"],
        flags=video_evidence.VIDEO_MACOS_DATALESS_FLAG,
    )

    with pytest.raises(video_evidence.VideoEvidenceError) as caught:
        video_evidence.validate_video_source_receipt(receipt)

    assert caught.value.details == {"field": "source_generation"}


def test_replacement_at_the_same_path_is_lineage_drift_not_a_fresh_source() -> None:
    original = _probe(_generation(inode=31), digest="a" * 64)
    replacement = _probe(_generation(inode=77), digest="d" * 64)
    receipt = video_evidence.build_video_source_receipt(original)

    assert video_evidence.video_source_receipt_lineage_drift(receipt, replacement) == (
        ("source_sha256",)
    )


def test_generation_drift_is_bound_inside_a_run_but_not_across_hosts() -> None:
    """Same bytes, moved vault: content holds, the host-local generation does not."""
    original = _probe(_generation(inode=31))
    moved = _probe(_generation(inode=77))
    receipt = video_evidence.build_video_source_receipt(original)

    assert video_evidence.video_source_receipt_lineage_drift(receipt, moved) == ()
    assert video_evidence.video_source_receipt_generation_drift(receipt, moved) == (
        ("source_generation",)
    )


def test_duration_reparse_within_tolerance_is_not_drift() -> None:
    receipt = video_evidence.build_video_source_receipt(_probe(_generation()))
    tolerance = video_evidence.VIDEO_SOURCE_RECEIPT_DURATION_TOLERANCE_SECONDS
    probe = _probe(_generation())

    receipt["duration_seconds"] = probe.duration_seconds + tolerance / 2
    assert video_evidence.video_source_receipt_lineage_drift(receipt, probe) == ()

    receipt["duration_seconds"] = probe.duration_seconds + tolerance * 10
    assert video_evidence.video_source_receipt_lineage_drift(receipt, probe) == (
        ("duration_seconds",)
    )


def test_probe_contract_version_is_part_of_the_lineage_claim() -> None:
    probe = _probe(_generation())
    receipt = video_evidence.build_video_source_receipt(probe)
    receipt["probe_pipeline_version"] = "0.9.0"

    assert video_evidence.video_source_receipt_lineage_drift(receipt, probe) == (
        ("probe_pipeline_version",)
    )

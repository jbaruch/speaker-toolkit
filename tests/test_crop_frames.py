"""Real media sampling, bounded failure paths, and closed frame manifests."""

import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(
    0, str(Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts")
)
import crop_frames as crops


@pytest.fixture
def recording(tmp_path):
    binary = shutil.which("ffmpeg")
    assert binary, "install ffmpeg; crop sampling tests require the real decoder"
    output = tmp_path / "talk.mp4"
    subprocess.run(
        [
            binary,
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=10",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return output


@pytest.fixture
def bundle(recording):
    directory = recording.parent / "frames"
    crops.sample_video(recording, directory, count=6)
    return directory


def test_real_sample_has_individual_frames_and_separate_sheet(recording):
    from PIL import Image

    before = recording.read_bytes()
    target = recording.parent / "frames"
    result = crops.sample_video(recording, target)
    loaded = crops.load_frame_bundle(result["manifest"])
    manifest = loaded["manifest"]
    assert result["frames"] == 12
    assert not result["reused"]
    assert manifest["source"]["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert [
        frame["timestamp_seconds"] for frame in manifest["frames"]
    ] == crops.sample_times(3, 12)
    assert len({frame["sha256"] for frame in manifest["frames"]}) == 12
    for frame in manifest["frames"]:
        with Image.open(target / frame["file"]) as picture:
            assert picture.size == (960, 540)
        assert (
            frame["sha256"]
            == hashlib.sha256((target / frame["file"]).read_bytes()).hexdigest()
        )
    with Image.open(target / "contact-sheet.jpg") as picture:
        assert picture.size == (1440, 2032)
    assert recording.read_bytes() == before
    snapshots = {path.name: path.read_bytes() for path in target.iterdir()}
    replay = crops.sample_video(recording, target)
    assert replay["reused"]
    assert snapshots == {path.name: path.read_bytes() for path in target.iterdir()}


@pytest.mark.parametrize("count", [0, 4, 5, 49, True, 6.0, "12"])
def test_invalid_count_never_reads_media(count, monkeypatch):
    monkeypatch.setattr(
        crops.video, "probe_video_artifact", lambda *args: pytest.fail("read media")
    )
    with pytest.raises(crops.CropFramesError, match="count_invalid"):
        crops.sample_video("absent.mp4", "output", count=count)


@pytest.mark.parametrize(
    "timeout", [0, -1, float("nan"), float("inf"), 3601, True, "10"]
)
def test_invalid_timeout_fails_before_input_io(timeout, monkeypatch):
    monkeypatch.setattr(
        crops.video, "probe_video_artifact", lambda *args: pytest.fail("read media")
    )
    with pytest.raises(crops.CropFramesError, match="timeout_invalid"):
        crops.sample_video("absent.mp4", "output", timeout_seconds=timeout)


def test_unexpected_worker_failure_is_closed_and_interruptible(monkeypatch, capsys):
    def fail():
        raise RuntimeError("private parser state")

    monkeypatch.setattr(crops, "_worker", fail)
    assert crops.run_worker() == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "private parser state" not in output.err

    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(crops, "_worker", interrupt)
    with pytest.raises(KeyboardInterrupt):
        crops.run_worker()


@pytest.mark.parametrize("duration", [0, -1, float("inf"), float("nan"), True, "3"])
def test_invalid_duration_rejected(duration):
    with pytest.raises(crops.CropFramesError, match="duration_invalid"):
        crops.sample_times(duration, 6)


def test_new_count_preserves_existing_bundle(recording, bundle):
    before = {path.name: path.read_bytes() for path in bundle.iterdir()}
    with pytest.raises(crops.CropFramesError, match="output_conflict"):
        crops.sample_video(recording, bundle, count=12)
    assert before == {path.name: path.read_bytes() for path in bundle.iterdir()}


def test_timeout_publishes_nothing(recording):
    output = recording.parent / "frames"
    with pytest.raises(crops.SupervisorError, match="worker_timeout"):
        crops.sample_video(recording, output, count=6, timeout_seconds=0.001)
    assert not output.exists()
    assert not list(recording.parent.glob(".crop-stage-*"))


def test_changed_source_never_publishes(recording, monkeypatch):
    invoke = crops._invoke

    def changed(operation, *args, **kwargs):
        recording.write_bytes(recording.read_bytes() + b"changed")
        return invoke(operation, *args, **kwargs)

    monkeypatch.setattr(crops, "_invoke", changed)
    with pytest.raises(crops.SupervisorError, match="generation_changed"):
        crops.sample_video(recording, recording.parent / "frames", count=6)
    assert not (recording.parent / "frames").exists()


def test_dataless_frame_fails_before_byte_reads(tmp_path, monkeypatch):
    source = tmp_path / "frame.jpg"
    source.write_bytes(b"not opened")
    receipt = crops.inspect_metadata_generation(source, trusted_root=tmp_path)
    receipt = replace(
        receipt, generation=replace(receipt.generation, file_attributes=0x001000)
    )
    monkeypatch.setattr(
        crops, "inspect_metadata_generation", lambda *args, **kwargs: receipt
    )
    monkeypatch.setattr(
        crops.video,
        "_prepared_video_source",
        lambda *args: pytest.fail("opened placeholder"),
    )
    with pytest.raises(crops.CropFramesError, match="artifact_unavailable"):
        crops._read_local(source, 1024)


@pytest.mark.parametrize("change", ["missing", "damaged", "sheet", "symlink"])
def test_bad_individual_frame_prevents_reviewer_input(bundle, change):
    frame = bundle / "frame-001.jpg"
    if change == "missing":
        frame.unlink()
    elif change == "damaged":
        frame.write_bytes(b"corrupt")
    elif change == "sheet":
        frame.write_bytes((bundle / "contact-sheet.jpg").read_bytes())
    else:
        frame.unlink()
        frame.symlink_to(bundle / "frame-002.jpg")
    with pytest.raises(crops.SupervisorError):
        crops.load_frame_bundle(bundle / "manifest.json")


@pytest.mark.parametrize(
    "change",
    [
        "future",
        "unknown",
        "path",
        "timestamp",
        "index",
        "bool",
        "sheet_digest",
        "sheet_shape",
    ],
)
def test_manifest_is_closed_before_frame_io(bundle, change):
    document = json.loads((bundle / "manifest.json").read_text())
    document = copy.deepcopy(document)
    if change == "future":
        document["schema_version"] = 2
    elif change == "unknown":
        document["unexpected"] = "field"
    elif change == "path":
        document["frames"][0]["file"] = "../secret.jpg"
    elif change == "timestamp":
        document["frames"][0]["timestamp_seconds"] = float("nan")
    elif change == "index":
        document["frames"][0]["index"] = 2
    elif change == "bool":
        document["frames"][0]["width"] = True
    elif change == "sheet_digest":
        document["frames"][0]["sha256"] = document["contact_sheet"]["sha256"]
    else:
        document["contact_sheet"]["width"] = 1
    with pytest.raises(crops.CropFramesError):
        crops.validate_manifest(document)


@pytest.mark.parametrize(
    "raw", [b'{"schema_version":1,"schema_version":1}', b'{"value":NaN}', b"\xff"]
)
def test_ambiguous_json_is_rejected(raw):
    with pytest.raises(crops.CropFramesError):
        crops._strict_json(raw)


@pytest.mark.parametrize(
    "arguments,code",
    [([], 2), (["--help"], 0), (["--unknown"], 2), (["absent.mp4", "output"], 1)],
)
def test_cli_reports_one_json_object(arguments, code):
    script = Path(crops.__file__).with_name("build-contact-sheet.py")
    result = subprocess.run(
        [sys.executable, str(script), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == code
    assert isinstance(json.loads(result.stdout), dict)
    if code:
        assert result.stderr


def test_unexpected_cli_error_is_redacted_and_interrupts_propagate(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location(
        "contact_cli", Path(crops.__file__).with_name("build-contact-sheet.py")
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def fail():
        raise RuntimeError("private token")

    monkeypatch.setattr(module, "main", fail)
    assert module.run_cli() == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "crop_unexpected_failure"
    assert "private token" not in output.out + output.err

    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "main", interrupt)
    with pytest.raises(KeyboardInterrupt):
        module.run_cli()

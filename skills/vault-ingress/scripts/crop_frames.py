#!/usr/bin/env python3
"""Bounded, source-bound frame sampling for human crop review.

The sampler emits individual JPEGs, a separate classification sheet, and a
versioned manifest. Samples never establish full-video integrity or approval.
All media decoding, snapshot reads, and image validation run in the shared
authenticated supervisor. A complete bundle is published to a fresh directory;
an identical existing bundle is reusable, and conflicting outputs are preserved.

This module owns the manifest contract; see references/crop-review.md.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import replace
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, cast

from artifact_metadata import ArtifactAvailability, inspect_metadata_generation
from artifact_supervisor import (
    JsonValue,
    SupervisorError,
    SupervisorLimits,
    isolate_protocol_output,
    read_worker_request,
    run_authenticated_worker,
    write_worker_response,
)
import video_evidence as video
from video_integrity import VideoIntegrityError, _run_tool


SCHEMA_VERSION = 1
PIPELINE_VERSION = "crop-frames-v1"
DEFAULT_FRAMES = 12
MIN_FRAMES = 6
MAX_FRAMES = 48
FRAME_EDGE = 960
FRAME_BYTES = 1024 * 1024
SHEET_BYTES = 8 * 1024 * 1024
MANIFEST_BYTES = 128 * 1024
SHEET_COLUMNS = 3
SHEET_CELL = 480
LIMITS = SupervisorLimits(
    profile_id=PIPELINE_VERSION,
    wall_seconds=300,
    max_memory_bytes=2 * 1024**3,
    max_output_bytes=96 * 1024**2,
    max_diagnostic_bytes=64 * 1024,
    max_processes=8,
)
WORKER_FLAG = "--supervised-worker"


class CropFramesError(ValueError):
    """Closed failure code; inputs and parser diagnostics stay private."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(
            f"{code}: check the local inputs, dependencies, and sampling limits; "
            "use a fresh output directory for changed inputs and retry"
        )


def sample_times(duration: float, count: int) -> list[float]:
    if type(count) is not int or not MIN_FRAMES <= count <= MAX_FRAMES:
        raise CropFramesError("crop_frame_count_invalid")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise CropFramesError("crop_duration_invalid")
    return [duration * index / (count + 1) for index in range(1, count + 1)]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_path(path: str | os.PathLike[str]) -> Path:
    # Configured parent roots may be symlinks; the artifact leaf is never resolved.
    target = Path(os.path.abspath(path))
    return target.parent.resolve(strict=True) / target.name


def _read_local(path: Path, limit: int) -> bytes:
    """Snapshot one bounded, regular, available file inside a worker only."""
    before = inspect_metadata_generation(path, trusted_root=path.parent)
    if ArtifactAvailability.from_generation(before.generation).state != "local":
        raise CropFramesError("crop_artifact_unavailable")
    if not 0 < before.generation.size <= limit:
        raise CropFramesError("crop_artifact_size_invalid")
    with video._prepared_video_source(path, before.generation) as prepared:
        os.lseek(prepared.probe_descriptor, 0, os.SEEK_SET)
        with os.fdopen(os.dup(prepared.probe_descriptor), "rb") as stream:
            data = stream.read(limit + 1)
        digest = video._digest_open_descriptor(
            prepared.source_descriptor, before.generation
        )
        if len(data) != before.generation.size or _digest(data) != digest:
            raise CropFramesError("crop_artifact_changed")
    after = inspect_metadata_generation(path, trusted_root=path.parent)
    if after != before:
        raise CropFramesError("crop_artifact_changed")
    return data


def _image(data: bytes, *, max_edge: int):
    """Decode a bounded JPEG only in the supervised worker."""
    from PIL import Image, UnidentifiedImageError

    try:
        picture = Image.open(io.BytesIO(data))
        if picture.format != "JPEG" or not all(
            0 < dimension <= max_edge for dimension in picture.size
        ):
            raise CropFramesError("crop_image_invalid")
        picture.load()
        return picture.convert("RGB")
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as exc:
        raise CropFramesError("crop_image_invalid") from exc


def _image_record(name: str, data: bytes, size: tuple[int, int]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "file": name,
        "sha256": _digest(data),
        "size_bytes": len(data),
        "width": size[0],
        "height": size[1],
    }


def _sample_snapshot(path: Path, duration: float, count: int) -> dict[str, Any]:
    """Sample an immutable private recording, not a live pathname."""
    from PIL import Image, ImageDraw, ImageOps

    binary = shutil.which("ffmpeg")
    if binary is None:
        raise CropFramesError("crop_ffmpeg_missing")
    times = sample_times(duration, count)
    pictures = []
    records = []
    artifacts = {}
    for index, timestamp in enumerate(times, 1):
        data = _run_tool(
            [
                binary,
                "-hide_banner",
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-threads",
                "2",
                "-ss",
                f"{timestamp:.9f}",
                "-i",
                str(path),
                "-map",
                "0:V:0",
                "-frames:v",
                "1",
                "-an",
                "-sn",
                "-dn",
                "-vf",
                f"scale={FRAME_EDGE}:{FRAME_EDGE}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
                "-filter_threads",
                "1",
                "-threads",
                "2",
                "-q:v",
                "3",
                "-f",
                "image2pipe",
                "-c:v",
                "mjpeg",
                "pipe:1",
            ]
        )
        picture = _image(data, max_edge=FRAME_EDGE)
        name = f"frame-{index:03d}.jpg"
        records.append(
            {
                **_image_record(name, data, picture.size),
                "index": index,
                "timestamp_seconds": timestamp,
            }
        )
        artifacts[name] = base64.b64encode(data).decode("ascii")
        pictures.append(picture)
    rows = math.ceil(count / SHEET_COLUMNS)
    sheet = Image.new(
        "RGB", (SHEET_CELL * SHEET_COLUMNS, (SHEET_CELL + 28) * rows), "#16181c"
    )
    draw = ImageDraw.Draw(sheet)
    for index, picture in enumerate(pictures):
        thumb = ImageOps.contain(picture, (SHEET_CELL, SHEET_CELL))
        x = index % SHEET_COLUMNS * SHEET_CELL
        y = index // SHEET_COLUMNS * (SHEET_CELL + 28)
        sheet.paste(thumb, (x + (SHEET_CELL - thumb.width) // 2, y))
        draw.text((x + 8, y + SHEET_CELL + 5), f"{times[index]:.2f}s", fill="white")
    output = io.BytesIO()
    sheet.save(output, format="JPEG", quality=85)
    data = output.getvalue()
    if len(data) > SHEET_BYTES:
        raise CropFramesError("crop_sheet_size_invalid")
    name = "contact-sheet.jpg"
    artifacts[name] = base64.b64encode(data).decode("ascii")
    return {
        "frames": records,
        "contact_sheet": _image_record(name, data, sheet.size),
        "artifacts": artifacts,
    }


def _strict_json(data: bytes) -> Any:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise CropFramesError("crop_manifest_invalid")
            result[key] = value
        return result

    def constant(value):
        raise CropFramesError("crop_manifest_invalid")

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CropFramesError("crop_manifest_invalid") from exc


def validate_manifest(document: object) -> dict[str, Any]:
    """Validate the closed owner schema before touching any named frame."""
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "pipeline_version",
        "source",
        "frames",
        "contact_sheet",
    }:
        raise CropFramesError("crop_manifest_invalid")
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != SCHEMA_VERSION
        or document["pipeline_version"] != PIPELINE_VERSION
    ):
        raise CropFramesError("crop_manifest_unsupported")
    source = video.validate_video_source_receipt(document["source"])
    frames = document["frames"]
    if not isinstance(frames, list):
        raise CropFramesError("crop_manifest_invalid")
    times = sample_times(cast(float, source["duration_seconds"]), len(frames))
    sheet = document["contact_sheet"]
    base_fields = {"schema_version", "file", "sha256", "size_bytes", "width", "height"}
    for index, item in enumerate([*frames, sheet]):
        is_frame = index < len(frames)
        expected_fields = base_fields | (
            {"index", "timestamp_seconds"} if is_frame else set()
        )
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise CropFramesError("crop_manifest_invalid")
        name = f"frame-{index + 1:03d}.jpg" if is_frame else "contact-sheet.jpg"
        limit = FRAME_BYTES if is_frame else SHEET_BYTES
        edge = (
            FRAME_EDGE
            if is_frame
            else (SHEET_CELL + 28) * math.ceil(MAX_FRAMES / SHEET_COLUMNS)
        )
        if (
            type(item["schema_version"]) is not int
            or item["schema_version"] != SCHEMA_VERSION
            or item["file"] != name
            or not isinstance(item["sha256"], str)
            or len(item["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in item["sha256"])
            or type(item["size_bytes"]) is not int
            or not 0 < item["size_bytes"] <= limit
            or any(
                type(item[key]) is not int or not 0 < item[key] <= edge
                for key in ("width", "height")
            )
        ):
            raise CropFramesError("crop_manifest_invalid")
        if is_frame and (
            type(item["index"]) is not int
            or item["index"] != index + 1
            or type(item["timestamp_seconds"]) not in (float, int)
            or item["timestamp_seconds"] != times[index]
        ):
            raise CropFramesError("crop_manifest_invalid")
    if sheet["width"] != SHEET_COLUMNS * SHEET_CELL or sheet["height"] != math.ceil(
        len(frames) / SHEET_COLUMNS
    ) * (SHEET_CELL + 28):
        raise CropFramesError("crop_manifest_invalid")
    if any(frame["sha256"] == sheet["sha256"] for frame in frames):
        raise CropFramesError("crop_tiled_frame_rejected")
    return document


def _load_bundle(path: Path) -> dict[str, Any]:
    raw = _read_local(path, MANIFEST_BYTES)
    manifest = validate_manifest(_strict_json(raw))
    artifacts = {}
    for item in [*manifest["frames"], manifest["contact_sheet"]]:
        data = _read_local(path.parent / item["file"], item["size_bytes"])
        if _digest(data) != item["sha256"] or len(data) != item["size_bytes"]:
            raise CropFramesError("crop_frame_digest_mismatch")
        edge = max(item["width"], item["height"])
        picture = _image(data, max_edge=edge)
        if picture.size != (item["width"], item["height"]):
            raise CropFramesError("crop_frame_dimensions_mismatch")
        artifacts[item["file"]] = base64.b64encode(data).decode("ascii")
    if _read_local(path, MANIFEST_BYTES) != raw:
        raise CropFramesError("crop_artifact_changed")
    return {
        "manifest": manifest,
        "manifest_sha256": _digest(raw),
        "artifacts": artifacts,
    }


def _validated_timeout(timeout_seconds: object) -> float:
    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(cast(float, timeout_seconds))
        or not 0 < cast(float, timeout_seconds) <= 3600
    ):
        raise CropFramesError("crop_timeout_invalid")
    return float(cast(float, timeout_seconds))


def _invoke(
    operation: str,
    payload: dict,
    generations: Mapping | None = None,
    *,
    timeout_seconds: float = LIMITS.wall_seconds,
):
    timeout_seconds = _validated_timeout(timeout_seconds)
    command = [sys.executable, str(Path(__file__).resolve()), WORKER_FLAG]
    result = run_authenticated_worker(
        command,
        operation,
        generations or {},
        cast(JsonValue, payload),
        replace(LIMITS, wall_seconds=timeout_seconds),
        immutable_process_identity=command[:2],
        pipeline_generation=PIPELINE_VERSION,
    )
    if result.diagnostics.byte_count or not isinstance(result.payload, dict):
        raise CropFramesError("crop_worker_result_invalid")
    return result.payload


def load_frame_bundle(path: str | os.PathLike[str]) -> dict[str, Any]:
    return _invoke("crop_load", {"path": str(_canonical_path(path))})


def sample_video(
    path: str | os.PathLike[str],
    output: str | os.PathLike[str],
    *,
    count: int = DEFAULT_FRAMES,
    timeout_seconds: float = LIMITS.wall_seconds,
) -> dict[str, Any]:
    sample_times(1, count)
    timeout_seconds = _validated_timeout(timeout_seconds)
    artifact = _canonical_path(path)
    destination = _canonical_path(output)
    probe = video.probe_video_artifact(artifact)
    source = video.build_video_source_receipt(probe)
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_dir():
            raise CropFramesError("crop_output_conflict")
        prior = load_frame_bundle(destination / "manifest.json")
        if (
            prior["manifest"]["source"] != source
            or len(prior["manifest"]["frames"]) != count
        ):
            raise CropFramesError("crop_output_conflict")
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "reused": True,
            "manifest": str(destination / "manifest.json"),
            "frames": count,
        }
    report = _invoke(
        "crop_sample",
        {"path": str(artifact), "source": source, "count": count},
        {"video": probe.generation},
        timeout_seconds=timeout_seconds,
    )
    manifest = validate_manifest(
        {
            "schema_version": SCHEMA_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "source": source,
            "frames": report.get("frames"),
            "contact_sheet": report.get("contact_sheet"),
        }
    )
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {
        item["file"] for item in [*manifest["frames"], manifest["contact_sheet"]]
    }:
        raise CropFramesError("crop_worker_result_invalid")
    with tempfile.TemporaryDirectory(
        prefix=".crop-stage-", dir=destination.parent
    ) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir(mode=0o700)
        for item in [*manifest["frames"], manifest["contact_sheet"]]:
            try:
                encoded = artifacts[item["file"]]
                if not isinstance(encoded, str):
                    raise CropFramesError("crop_worker_result_invalid")
                data = base64.b64decode(encoded, validate=True)
            except (TypeError, ValueError, binascii.Error) as exc:
                raise CropFramesError("crop_worker_result_invalid") from exc
            if _digest(data) != item["sha256"] or len(data) != item["size_bytes"]:
                raise CropFramesError("crop_worker_result_invalid")
            (stage / item["file"]).write_bytes(data)
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        try:
            from filelock import FileLock
        except ImportError as exc:
            raise CropFramesError("crop_lock_dependency_missing") from exc
        lock_name = _digest(os.fsencode(destination)) + ".crop.lock"
        with FileLock(str(Path(tempfile.gettempdir()) / lock_name), timeout=10):
            if destination.exists() or destination.is_symlink():
                raise CropFramesError("crop_output_conflict")
            stage.rename(destination)
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "reused": False,
        "manifest": str(destination / "manifest.json"),
        "frames": count,
    }


def _worker() -> int:
    request = read_worker_request(max_input_bytes=LIMITS.max_input_bytes)
    output = isolate_protocol_output()
    try:
        try:
            if (
                request.schema_generation != SCHEMA_VERSION
                or request.pipeline_generation != PIPELINE_VERSION
                or request.limit_profile_id != LIMITS.profile_id
                or not isinstance(request.payload, dict)
            ):
                raise SupervisorError("invalid_worker_request")
            payload = request.payload
            if (
                request.operation == "crop_load"
                and set(payload) == {"path"}
                and not request.expected_generations
                and isinstance(payload["path"], str)
            ):
                report = _load_bundle(Path(payload["path"]))
            elif (
                request.operation == "crop_sample"
                and set(payload) == {"path", "source", "count"}
                and set(request.expected_generations) == {"video"}
                and isinstance(payload["path"], str)
            ):
                artifact = Path(payload["path"])
                source = video.validate_video_source_receipt(payload["source"])
                expected = request.expected_generations["video"]
                before = video._metadata_receipt_in_probe_worker(artifact, None)
                if (
                    before.generation != expected
                    or video._availability(expected).state != "local"
                    or source["source_generation"] != expected.to_dict()
                ):
                    raise SupervisorError("worker_generation_changed")
                with video._prepared_video_source(artifact, expected) as prepared:
                    report = _sample_snapshot(
                        prepared.probe_artifact,
                        cast(float, source["duration_seconds"]),
                        cast(int, payload["count"]),
                    )
                    digest = video._digest_open_descriptor(
                        prepared.source_descriptor, expected
                    )
                    snapshot = video._digest_open_descriptor(
                        prepared.probe_descriptor, prepared.probe_generation
                    )
                    if digest != source["source_sha256"] or snapshot != digest:
                        raise SupervisorError("worker_generation_changed")
                if (
                    video._metadata_receipt_in_probe_worker(artifact, None).generation
                    != expected
                ):
                    raise SupervisorError("worker_generation_changed")
            else:
                raise SupervisorError("invalid_worker_request")
            write_worker_response(
                request,
                payload=cast(JsonValue, report),
                observed_generations=request.expected_generations,
                stream=output,
                max_output_bytes=LIMITS.max_output_bytes,
            )
        except (
            CropFramesError,
            SupervisorError,
            video.VideoEvidenceError,
            VideoIntegrityError,
            OSError,
            ValueError,
        ) as exc:
            code = (
                exc.code
                if isinstance(exc, (CropFramesError, VideoIntegrityError))
                else exc.reason_code
                if isinstance(exc, (SupervisorError, video.VideoEvidenceError))
                else "crop_input_unavailable"
            )
            write_worker_response(
                request,
                error=SupervisorError(code),
                observed_generations=request.expected_generations,
                stream=output,
                max_output_bytes=LIMITS.max_output_bytes,
            )
    finally:
        output.close()
    return 0


def run_worker() -> int:
    try:
        return _worker()
    # The supervisor reads a missing authenticated response plus nonzero exit
    # as a worker crash. Emit a closed diagnostic; a traceback would leak paths.
    # outer-boundary-process-contract
    except Exception:  # noqa: BLE001
        print("crop worker failed; check the runtime and retry", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if sys.argv[1:] != [WORKER_FLAG]:
        print(json.dumps({"ok": False, "code": "crop_worker_only"}))
        print("run build-contact-sheet.py or build-crop-reviewer.py", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(run_worker())

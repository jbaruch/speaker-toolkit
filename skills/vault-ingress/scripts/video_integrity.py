#!/usr/bin/env python3
"""Decode-verify one recording; never infer integrity from stderr vocabulary.

Usage: video_integrity.py VIDEO [--timeout-seconds 1800]
Stdout is one JSON report. Exit 0 means every non-cover audio/video stream
decoded without an error and reached its declared extent. Exit 1 rejects the
recording; exit 2 reports invalid usage. No file is modified. Reports bind the
verification to a source digest/generation, not merely a pathname. Verification
is not speaker, delivery, crop, or transcript authority.

ffprobe supplies declared stream durations (format duration is the fallback).
ffmpeg decodes streams individually to null with strict error detection and
machine-readable progress. Per-stream comparisons prevent healthy audio from
masking truncated video. No stream copy, frame sampling, or error-text regex
can satisfy this gate. Short timestamp rounding differences are allowed by
the documented tolerance in stream_specs().

The existing video probe owns metadata-only placeholder checks and immutable
source preparation. Its shared supervisor bounds the decode worker's process
tree, memory, wall time, and output. Tool stderr is never copied into reports.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, BinaryIO, NoReturn, cast

from artifact_supervisor import (
    JsonValue,
    SupervisorError,
    SupervisorLimits,
    _PipeDrainer,
    isolate_protocol_output,
    read_worker_request,
    run_authenticated_worker,
    write_worker_response,
)
import video_evidence as video


SCHEMA_VERSION = 1
PIPELINE_VERSION = "video-integrity-v1"
LIMITS = SupervisorLimits(
    profile_id=PIPELINE_VERSION,
    wall_seconds=1800,
    max_memory_bytes=2 * 1024**3,
    max_output_bytes=256 * 1024,
    max_diagnostic_bytes=64 * 1024,
    max_processes=8,
)
TOOL_OUTPUT_BYTES = 1024 * 1024
WORKER_FLAG = "--supervised-worker"
USAGE = "video_integrity.py VIDEO [--timeout-seconds 1800]"


class VideoIntegrityError(ValueError):
    """Closed diagnostic with caller-actionable recovery, never parser text."""

    def __init__(self, code: str, details: Mapping[str, object] | None = None):
        self.code = code
        self.details = dict(details or {})
        super().__init__(
            f"{code}: do not use this recording as verified evidence; check the "
            "reported dependency or limit, or obtain a complete recording and retry"
        )


class IntegrityArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(f"invalid integrity command; usage: {USAGE}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "ok": False,
                    "code": "integrity_usage_invalid",
                    "usage": USAGE,
                }
            )
        )
        raise SystemExit(2)


def _positive(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _timestamp(value: object) -> float:
    if value is None or value == "N/A":
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise VideoIntegrityError("integrity_metadata_invalid")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise VideoIntegrityError("integrity_metadata_invalid") from exc
    if not math.isfinite(number):
        raise VideoIntegrityError("integrity_metadata_invalid")
    return number


def stream_specs(document: object) -> tuple[list[dict[str, Any]], float]:
    """Project strict stream identities, declared extents, and rounding margins.

    Margin is 100 ms or two video frames, whichever is larger, capped at 1 s.
    """
    if not isinstance(document, Mapping):
        raise VideoIntegrityError("integrity_metadata_invalid")
    fmt = document.get("format")
    if not isinstance(fmt, Mapping):
        raise VideoIntegrityError("integrity_metadata_invalid")
    duration = _positive(fmt.get("duration"))
    streams = document.get("streams")
    if duration is None or not isinstance(streams, list) or not streams:
        raise VideoIntegrityError("integrity_metadata_invalid")
    format_start = _timestamp(fmt.get("start_time"))
    if len(streams) > video.VIDEO_MAX_STREAMS:
        raise VideoIntegrityError("integrity_stream_limit")
    result = []
    seen = set()
    for stream in streams:
        if not isinstance(stream, Mapping):
            raise VideoIntegrityError("integrity_metadata_invalid")
        index = stream.get("index")
        if type(index) is not int or index < 0 or index in seen:
            raise VideoIntegrityError("integrity_metadata_invalid")
        seen.add(index)
        kind = stream.get("codec_type")
        if not isinstance(kind, str):
            raise VideoIntegrityError("integrity_metadata_invalid")
        disposition = stream.get("disposition", {})
        if not isinstance(disposition, Mapping):
            raise VideoIntegrityError("integrity_metadata_invalid")
        if kind not in {"video", "audio"} or disposition.get("attached_pic") == 1:
            continue
        offset = max(0.0, _timestamp(stream.get("start_time")) - format_start)
        expected = _positive(stream.get("duration")) or (duration - offset)
        if expected <= 0:
            raise VideoIntegrityError("integrity_metadata_invalid")
        margin = 0.1
        if kind == "video":
            rate = stream.get("avg_frame_rate")
            if isinstance(rate, str) and rate.count("/") == 1:
                numerator, denominator = map(_positive, rate.split("/"))
                if numerator is not None and denominator is not None:
                    margin = min(1.0, max(margin, 2 * denominator / numerator))
        result.append(
            {
                "index": index,
                "kind": kind,
                "declared_seconds": expected,
                "tolerance_seconds": margin,
                "start_offset_seconds": offset,
            }
        )
    if not any(item["kind"] == "video" for item in result):
        raise VideoIntegrityError("integrity_no_video_stream")
    return result, duration


def decoded_extent(output: bytes) -> float:
    """Read terminal progress, rejecting missing/invalid timestamps or frames."""
    try:
        lines = output.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise VideoIntegrityError("integrity_progress_invalid") from exc
    current: dict[str, str] = {}
    terminal: dict[str, str] | None = None
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator:
            raise VideoIntegrityError("integrity_progress_invalid")
        current[key.strip()] = value.strip()
        if key == "progress":
            if value not in {"continue", "end"} or terminal is not None:
                raise VideoIntegrityError("integrity_progress_invalid")
            if value == "end":
                terminal = current
            current = {}
    if current or terminal is None:
        raise VideoIntegrityError("integrity_progress_incomplete")
    micros = _positive(terminal.get("out_time_us"))
    if micros is None:
        raise VideoIntegrityError("integrity_progress_invalid")
    return micros / 1_000_000


def _run_tool(command: list[str]) -> bytes:
    """Drain bounded pipes inside the already-supervised worker process tree."""
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            close_fds=True,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise VideoIntegrityError("integrity_tool_unavailable") from exc
    if process.stdout is None or process.stderr is None:
        video._stop_process(process)
        raise VideoIntegrityError("integrity_pipe_failure")
    stdout = _PipeDrainer(cast(BinaryIO, process.stdout), TOOL_OUTPUT_BYTES)
    stderr = _PipeDrainer(cast(BinaryIO, process.stderr), LIMITS.max_diagnostic_bytes)
    stdout.start()
    stderr.start()
    try:
        while process.poll() is None:
            if stdout.overflowed or stderr.overflowed:
                video._stop_process(process)
                break
            time.sleep(0.01)
        code = process.wait()
        stdout.join(1)
        stderr.join(1)
        if stdout.alive or stderr.alive or stdout.failed or stderr.failed:
            raise VideoIntegrityError("integrity_pipe_failure")
        if stdout.overflowed or stderr.overflowed:
            raise VideoIntegrityError("integrity_output_limit")
        if code != 0 or stderr.receipt.byte_count:
            raise VideoIntegrityError(
                "integrity_decode_failed",
                {"exit_code": code, "diagnostics": stderr.receipt.to_dict()},
            )
        return stdout.data
    finally:
        video._stop_process(process)
        stdout.close()
        stderr.close()


def decode_recording(path: Path) -> dict[str, object]:
    """Decode each declared audio/video stream; called only in the worker."""
    binaries = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
    for name, binary in binaries.items():
        if binary is None:
            raise VideoIntegrityError(
                "integrity_dependency_missing", {"dependency": name}
            )
    raw = _run_tool(
        [
            str(binaries["ffprobe"]),
            "-v",
            "error",
            "-show_entries",
            "format=duration,start_time:stream=index,codec_type,duration,start_time,avg_frame_rate:stream_disposition=attached_pic",
            "-of",
            "json",
            os.fspath(path),
        ]
    )
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise VideoIntegrityError("integrity_metadata_invalid") from exc
    specs, container_duration = stream_specs(document)
    reports = []
    for spec in specs:
        command = [
            str(binaries["ffmpeg"]),
            "-hide_banner",
            "-nostdin",
            "-nostats",
            "-v",
            "error",
            "-xerror",
            "-max_error_rate",
            "0",
            "-err_detect",
            "explode",
            "-threads",
            "2",
            "-i",
            os.fspath(path),
            "-map",
            f"0:{spec['index']}",
            "-progress",
            "pipe:1",
            "-stats_period",
            "5",
        ]
        if spec["kind"] == "video":
            command.extend(["-vf", "setpts=PTS-STARTPTS", "-fps_mode", "passthrough"])
        else:
            command.extend(["-af", "asetpts=PTS-STARTPTS"])
        command.extend(["-filter_threads", "1", "-f", "null", "-"])
        extent = decoded_extent(_run_tool(command))
        gap = spec["declared_seconds"] - extent
        report = {**spec, "decoded_seconds": extent, "gap_seconds": max(0.0, gap)}
        if gap > spec["tolerance_seconds"]:
            raise VideoIntegrityError("integrity_duration_gap", report)
        if -gap > spec["tolerance_seconds"]:
            raise VideoIntegrityError("integrity_duration_mismatch", report)
        reports.append(report)
    container_extent = max(
        item["start_offset_seconds"] + item["decoded_seconds"] for item in reports
    )
    if abs(container_duration - container_extent) > max(
        item["tolerance_seconds"] for item in reports
    ):
        raise VideoIntegrityError(
            "integrity_container_duration_gap",
            {
                "declared_seconds": container_duration,
                "decoded_seconds": container_extent,
            },
        )
    return {"container_duration_seconds": container_duration, "streams": reports}


def verify_video_integrity(
    path: str | os.PathLike[str], *, timeout_seconds: float = LIMITS.wall_seconds
) -> dict[str, object]:
    """Return a generation-bound receipt, or fail without altering the input."""
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or _positive(timeout_seconds) is None
        or timeout_seconds > 21600
    ):
        raise VideoIntegrityError("integrity_timeout_invalid")
    artifact = Path(os.path.abspath(path))
    probe = video.probe_video_artifact(artifact)
    command = [sys.executable, os.fspath(Path(__file__).resolve()), WORKER_FLAG]
    result = run_authenticated_worker(
        command,
        "video_integrity",
        {"video": probe.generation},
        {"path": os.fspath(artifact), "sha256": probe.source_sha256},
        replace(LIMITS, wall_seconds=timeout_seconds),
        immutable_process_identity=command[:2],
        sensitive_values=(artifact,),
        pipeline_generation=PIPELINE_VERSION,
    )
    if result.diagnostics.byte_count or not isinstance(result.payload, dict):
        raise VideoIntegrityError("integrity_result_invalid")
    if set(result.payload) != {"container_duration_seconds", "streams"}:
        raise VideoIntegrityError("integrity_result_invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "source_sha256": probe.source_sha256,
        "source_size_bytes": probe.source_size_bytes,
        "source_generation": probe.generation.to_dict(),
        "pipeline_version": PIPELINE_VERSION,
        **result.payload,
    }


def _worker() -> int:
    request = read_worker_request(max_input_bytes=LIMITS.max_input_bytes)
    output = isolate_protocol_output()
    try:
        try:
            if (
                request.operation != "video_integrity"
                or request.pipeline_generation != PIPELINE_VERSION
                or request.schema_generation != SCHEMA_VERSION
                or request.limit_profile_id != LIMITS.profile_id
                or set(request.expected_generations) != {"video"}
                or not isinstance(request.payload, dict)
                or set(request.payload) != {"path", "sha256"}
                or not isinstance(request.payload["path"], str)
                or not isinstance(request.payload["sha256"], str)
            ):
                raise SupervisorError("invalid_worker_request")
            artifact = Path(request.payload["path"])
            expected = request.expected_generations["video"]
            before = video._metadata_receipt_in_probe_worker(artifact, None)
            if (
                before.generation != expected
                or video._availability(expected).state != "local"
            ):
                raise SupervisorError("worker_generation_changed")
            with video._prepared_video_source(artifact, expected) as prepared:
                report = decode_recording(prepared.probe_artifact)
                digest = video._digest_open_descriptor(
                    prepared.source_descriptor, expected
                )
                snapshot_digest = video._digest_open_descriptor(
                    prepared.probe_descriptor, prepared.probe_generation
                )
                if digest != request.payload["sha256"] or snapshot_digest != digest:
                    raise SupervisorError("worker_generation_changed")
            after = video._metadata_receipt_in_probe_worker(artifact, None)
            if after.generation != expected:
                raise SupervisorError("worker_generation_changed")
            write_worker_response(
                request,
                payload=cast(JsonValue, report),
                observed_generations={"video": after.generation},
                stream=output,
                max_output_bytes=LIMITS.max_output_bytes,
            )
        except (SupervisorError, VideoIntegrityError, video.VideoEvidenceError) as exc:
            code = exc.code if isinstance(exc, VideoIntegrityError) else exc.reason_code
            write_worker_response(
                request,
                error=SupervisorError(code, cast(Mapping[str, JsonValue], exc.details)),
                observed_generations=request.expected_generations,
                stream=output,
                max_output_bytes=LIMITS.max_output_bytes,
            )
    finally:
        output.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments in (["--help"], ["-h"]):
        print(
            json.dumps({"schema_version": SCHEMA_VERSION, "ok": True, "usage": USAGE})
        )
        return 0
    parser = IntegrityArgumentParser(add_help=False)
    parser.add_argument("video", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=LIMITS.wall_seconds)
    args = parser.parse_args(arguments)
    try:
        report = verify_video_integrity(
            args.video, timeout_seconds=args.timeout_seconds
        )
    except (VideoIntegrityError, video.VideoEvidenceError, SupervisorError) as exc:
        code = exc.code if isinstance(exc, VideoIntegrityError) else exc.reason_code
        error = VideoIntegrityError(code, exc.details)
        print(str(error), file=sys.stderr)
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "ok": False,
                    "code": code,
                    "error": str(error),
                    "details": error.details,
                }
            )
        )
        return 1
    print(json.dumps(report))
    return 0


def run_cli() -> int:
    try:
        return _worker() if sys.argv[1:] == [WORKER_FLAG] else main()
    # Agent callers need one failure report; a traceback would drop the JSON
    # contract and could expose parser paths. Emit a closed failure instead.
    # outer-boundary-process-contract
    except Exception:  # noqa: BLE001
        print(
            "integrity check failed unexpectedly; repair the runtime and retry",
            file=sys.stderr,
        )
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "ok": False,
                    "code": "integrity_unexpected_failure",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())

#!/usr/bin/env python3
"""Check a rendered short's pixels, sound and QR, and build its review sheet.

Usage:
    verify-short.py --plan <plan.json> --clip <id>

Reads ``<out_dir>/<id>.mp4`` and the intermediates ``render-short.py`` left in
``<work_dir>/<id>/``. Checks, with tolerances in the named constants below:
streams (H.264 1080x1920 yuv420p, AAC 48 kHz, the planned duration), a clean
full decode, integrated loudness and true peak, a caption highlight that moves
from word to word, each planned deck page on screen after its change, and the
QR card decoding to ``qr_url`` (Apple Vision, ``vision.swift.txt``). It also
writes ``<work_dir>/<id>/review.jpg``, six frames for the agent to look at.

Stdout: ``{"ok", "clip", "checks", "failures", "review"}``. Exit 0 when every
check passes, 1 when any fails (``failures`` names each), 2 on a usage error.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import numpy as np
from PIL import Image

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import shorts_plan  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "render_short", SCRIPTS / "render-short.py"
)
assert _spec is not None and _spec.loader is not None
layout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout)

DURATION_TOLERANCE = 0.1
LOUDNESS_TARGET = -14.0
LOUDNESS_TOLERANCE = 1.0
MAX_TRUE_PEAK = -1.0
MAX_SLIDE_ERROR = 6.0
HIGHLIGHT_SAMPLES = 6
MIN_DISTINCT_HIGHLIGHTS = 3
MIN_HIGHLIGHT_PIXELS = 300
REVIEW_FRACTIONS = (0.02, 0.2, 0.4, 0.6, 0.8, 0.98)
TOOL_TIMEOUT_SECONDS = 30 * 60


class VerifyError(RuntimeError):
    """Verification could not run; the message says what to do."""


def _run(command: list[str], what: str) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise VerifyError(f"{what}: {command[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise VerifyError(f"{what} took over {TOOL_TIMEOUT_SECONDS}s") from exc
    if completed.returncode != 0:
        raise VerifyError(
            f"{what} failed ({completed.returncode}): {completed.stderr.strip()[-800:]}"
        )
    return completed


def grab(video: Path, at: float, path: Path) -> Image.Image:
    _run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{at:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(path),
        ],
        f"grabbing {at:.2f}s",
    )
    with Image.open(path) as image:
        return image.convert("RGB")


def check_streams(video: Path, duration: float) -> list[str]:
    info = json.loads(
        _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,pix_fmt,sample_rate:format=duration",
                "-of",
                "json",
                str(video),
            ],
            "probing the short",
        ).stdout
    )
    failures = []
    video_streams = [s for s in info["streams"] if s["codec_type"] == "video"]
    audio_streams = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not video_streams or (
        video_streams[0]["codec_name"],
        video_streams[0]["width"],
        video_streams[0]["height"],
        video_streams[0]["pix_fmt"],
    ) != ("h264", layout.CANVAS[0], layout.CANVAS[1], "yuv420p"):
        failures.append(
            f"video stream is {video_streams[:1]}, not h264 {layout.CANVAS} yuv420p"
        )
    if not audio_streams or (
        audio_streams[0]["codec_name"],
        audio_streams[0]["sample_rate"],
    ) != ("aac", "48000"):
        failures.append(f"audio stream is {audio_streams[:1]}, not aac 48000 Hz")
    actual = float(info["format"]["duration"])
    if abs(actual - duration) > DURATION_TOLERANCE:
        failures.append(
            f"duration {actual:.3f}s differs from the planned {duration:.3f}s"
        )
    decode = _run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-f",
            "null",
            "-",
        ],
        "decoding the short",
    )
    if decode.stderr.strip():
        failures.append(f"decoding logged errors: {decode.stderr.strip()[-400:]}")
    return failures


def check_loudness(video: Path) -> tuple[dict[str, float], list[str]]:
    stderr = _run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-i",
            str(video),
            "-vn",
            "-af",
            "loudnorm=print_format=json",
            "-f",
            "null",
            "-",
        ],
        "measuring loudness",
    ).stderr
    found = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr)
    if found is None:
        return {}, ["ffmpeg printed no loudness measurement"]
    measured = json.loads(found.group(0))
    result = {
        "integrated": float(measured["input_i"]),
        "true_peak": float(measured["input_tp"]),
    }
    failures = []
    if abs(result["integrated"] - LOUDNESS_TARGET) > LOUDNESS_TOLERANCE:
        failures.append(
            f"integrated loudness {result['integrated']} LUFS is off the {LOUDNESS_TARGET} target"
        )
    if result["true_peak"] > MAX_TRUE_PEAK:
        failures.append(
            f"true peak {result['true_peak']} dBTP is above {MAX_TRUE_PEAK}"
        )
    return result, failures


def highlight_bounds(frame: Image.Image) -> list[int] | None:
    x, y, w, h = layout.CAPTION_BOX
    pixels = np.asarray(frame.crop((x, y, x + w, y + h)), dtype=np.int16)
    lime = np.array(
        [int(layout.LIME[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.int16
    )
    mask = np.abs(pixels - lime).sum(axis=2) < 60
    ys, xs = np.nonzero(mask)
    if len(xs) < MIN_HIGHLIGHT_PIXELS:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def check_highlights(
    video: Path, words: list[dict[str, Any]], folder: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    candidates = [w for w in words if w["end"] - w["start"] > 0.3]
    if not candidates:
        return [], ["no caption word lasts long enough to sample its highlight"]
    step = max(1, len(candidates) // HIGHLIGHT_SAMPLES)
    samples = []
    for i, word in enumerate(candidates[::step][:HIGHLIGHT_SAMPLES]):
        at = word["start"] + 0.15
        bounds = highlight_bounds(grab(video, at, folder / f"highlight-{i}.png"))
        samples.append({"word": word["text"], "at": round(at, 3), "bounds": bounds})
    distinct = {tuple(s["bounds"]) for s in samples if s["bounds"]}
    if len(distinct) < MIN_DISTINCT_HIGHLIGHTS:
        return samples, [
            f"the highlight sat in {len(distinct)} places across {len(samples)} words"
        ]
    return samples, []


def check_slides(
    video: Path, clip: dict[str, Any], folder: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    x, y, w, h = layout.SLIDE_BOX
    results, failures = [], []
    for index, (offset, page) in enumerate(clip["slides"]):
        frame = grab(video, offset + 0.2, folder / f"slide-check-{index}.png")
        with Image.open(folder / f"slide-{index:02d}.png") as expected:
            want = np.asarray(expected.convert("RGB"), dtype=np.float32)
        got = np.asarray(frame.crop((x, y, x + w, y + h)), dtype=np.float32)
        error = float(np.abs(got - want).mean())
        results.append(
            {"page": page, "at": offset + 0.2, "mean_error": round(error, 2)}
        )
        if error > MAX_SLIDE_ERROR:
            failures.append(
                f"page {page} is not on screen at {offset + 0.2:.2f}s (error {error:.1f})"
            )
    return results, failures


def _scan_qr(plan: dict[str, Any], image: Path) -> list[str]:
    """Apple Vision's QR payloads for one image."""
    script = shorts_plan.vision_script(plan)
    rows = json.loads(
        _run(["swift", str(script), "qr", str(image)], "scanning the QR").stdout
    )
    return rows[0].get("payloads", []) if rows else []


def check_qr(
    plan: dict[str, Any], video: Path, url: str | None, folder: Path
) -> tuple[list[str], list[str]]:
    if url is None:
        return [], []
    frame = grab(video, 1.0, folder / "qr-check.png")
    card = folder / "qr-card-check.png"
    x, y, w, h = layout.QR_CARD
    frame.crop((x, y, x + w, y + h)).save(card)
    payloads = _scan_qr(plan, card)
    return payloads, (
        [] if url in payloads else [f"the QR card decodes to {payloads}, not {url}"]
    )


def review_sheet(video: Path, duration: float, folder: Path) -> Path:
    tiles = []
    for i, fraction in enumerate(REVIEW_FRACTIONS):
        frame = grab(video, duration * fraction, folder / f"review-{i}.png")
        frame.thumbnail((360, 640))
        tiles.append(frame)
    sheet = Image.new("RGB", (360 * len(tiles), 640), "#101723")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (i * 360, 0))
    path = folder / "review.jpg"
    sheet.save(path, quality=88)
    return path


def verify(plan_path: Path, clip_id: str) -> dict[str, Any]:
    plan = shorts_plan.load(plan_path)
    clip = shorts_plan.clip(plan, clip_id)
    shorts_plan.require_render_fields(clip)
    folder = shorts_plan.clip_dir(plan, clip_id)
    video = plan["out_dir"] / f"{clip_id}.mp4"
    if not video.exists():
        raise VerifyError(f"{video} does not exist — run render-short.py first")
    try:
        words = json.loads((folder / "caption-alignment.json").read_text())["words"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        raise VerifyError(
            f"caption-alignment.json is missing ({exc}) — re-run render-short.py"
        ) from exc
    duration = clip["end"] - clip["start"]
    failures = check_streams(video, duration)
    loudness, more = check_loudness(video)
    failures += more
    highlights, more = check_highlights(video, words, folder)
    failures += more
    slides, more = check_slides(video, clip, folder)
    failures += more
    payloads, more = check_qr(plan, video, plan.get("qr_url"), folder)
    failures += more
    return {
        "ok": not failures,
        "clip": clip_id,
        "checks": {
            "loudness": loudness,
            "highlights": highlights,
            "slides": slides,
            "qr_payloads": payloads,
        },
        "failures": failures,
        "review": str(review_sheet(video, duration, folder)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--clip", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(args.plan, args.clip)
    except (shorts_plan.PlanError, VerifyError, layout.RenderError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

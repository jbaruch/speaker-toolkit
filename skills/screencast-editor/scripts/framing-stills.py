#!/usr/bin/env python3
"""Render a proxy still for every framing cue in a shot plan, plus a contact sheet.

Each still is the exact frame at the cue (decoded from the start, because the
TSCC2 screen codec does not seek accurately), cropped to the planned framing,
with the picture-in-picture footprint outlined. Look at every still: a page
load or a correct crop in numbers is not a visual pass.

Usage:
    framing-stills.py <recording.trec> <shot-plan.json> --out <dir> [--stream 0:0]

Writes <dir>/still-NN.png and <dir>/sheet.png. Exit 0 on success, 1 when
ffmpeg fails, 2 on usage error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camtasia_model as model  # noqa: E402

SAMPLE_FPS = 10
SETTLE = 0.4  # seconds after a cue, so the move has finished


def crop_for(
    zoom: float, x: float, y: float, width: int, height: int, canvas: model.Canvas
) -> tuple[int, int, int, int]:
    """ffmpeg crop (w, h, x, y) in source pixels for a planned framing."""
    x0, y0, x1, y1 = model.visible_rect(zoom, x, y, canvas)
    return (
        round((x1 - x0) * width),
        round((y1 - y0) * height),
        round(x0 * width),
        round(y0 * height),
    )


def cue_frames(plan: dict) -> list[tuple[int, list[float]]]:
    frames = []
    for shot in plan["shots"]:
        if shot["kind"] != "screen":
            continue
        for cue in shot["cues"]:
            t = min(cue[0] + SETTLE, shot["end"] - 0.2)
            frames.append((round(t * SAMPLE_FPS), cue))
    return sorted(frames, key=lambda f: f[0])


def launch(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as e:
        raise ValueError(
            f"cannot run {command[0]} ({e}); install ffmpeg, e.g. `brew install ffmpeg`"
        ) from e


def run(command: list[str]) -> None:
    result = launch(command)
    if result.returncode != 0:
        raise ValueError(f"{command[0]} failed: {result.stderr.strip()[-400:]}")


def clear_outputs(out: Path) -> None:
    """Remove this script's earlier outputs, so a shorter plan leaves no stale stills."""
    for pattern in ("still-*.png", "raw-*.png", "sheet.png"):
        for old in out.glob(pattern):
            old.unlink()


def render(recording: Path, plan: dict, out: Path, stream: str) -> list[Path]:
    """Render into a staging directory; replace the previous set only on success."""
    staging = out.with_name(f".{out.name}.staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        produced = render_into(recording, plan, staging, stream)
    except (ValueError, OSError):
        shutil.rmtree(staging)
        raise
    out.mkdir(parents=True, exist_ok=True)
    clear_outputs(out)
    for item in [*produced, staging / "sheet.png"]:
        item.replace(out / item.name)
    shutil.rmtree(staging)
    return [out / p.name for p in produced]


def render_into(recording: Path, plan: dict, out: Path, stream: str) -> list[Path]:
    frames = cue_frames(plan)
    probe = launch(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            stream.split(":", 1)[-1],
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(recording),
        ],
    )
    if probe.returncode != 0:
        raise ValueError(f"ffprobe failed: {probe.stderr.strip()[-400:]}")
    streams = json.loads(probe.stdout or "{}").get("streams") or []
    if not streams or "width" not in streams[0]:
        raise ValueError(f"no video stream {stream} in {recording}")
    info = streams[0]
    width, height = int(info["width"]), int(info["height"])
    canvas = model.plan_canvas(plan)
    select = "+".join(f"eq(n,{n})" for n, _ in frames)
    raw = out / "raw-%03d.png"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(recording),
            "-map",
            stream,
            "-vf",
            f"fps={SAMPLE_FPS},select='{select}'",
            "-fps_mode",
            "passthrough",
            str(raw),
        ]
    )
    inset = plan.get("inset", {})
    box_h = round(inset.get("height", 324))
    box_w = round(inset.get("width", box_h * 16 / 9))
    box_x = round(canvas.width / 2 + inset.get("x", 640) - box_w / 2)
    box_y = round(canvas.height / 2 - inset.get("y", -346) - box_h / 2)
    stills = []
    for i, (_, cue) in enumerate(frames, 1):
        cw, ch, cx, cy = crop_for(cue[1], cue[2], cue[3], width, height, canvas)
        still = out / f"still-{i:02d}.png"
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(out / f"raw-{i:03d}.png"),
                "-vf",
                f"crop={cw}:{ch}:{cx}:{cy},scale={int(canvas.width)}:{int(canvas.height)},"
                f"drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:color=red@0.6:t=6",
                str(still),
            ]
        )
        (out / f"raw-{i:03d}.png").unlink()
        stills.append(still)
    columns = 3
    rows = -(-len(stills) // columns)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(out / "still-%02d.png"),
            "-vf",
            f"scale=960:-1,tile={columns}x{rows}",
            "-frames:v",
            "1",
            str(out / "sheet.png"),
        ]
    )
    return stills


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("recording", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stream", default="0:0")
    args = parser.parse_args(argv)
    try:
        plan = model.load_plan(args.plan)
    except ValueError as e:
        print(f"framing-stills: {e}", file=sys.stderr)
        return 2
    try:
        stills = render(args.recording, plan, args.out, args.stream)
    except ValueError as e:
        print(f"framing-stills: {e}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"stills": [str(s) for s in stills], "sheet": str(args.out / "sheet.png")}
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

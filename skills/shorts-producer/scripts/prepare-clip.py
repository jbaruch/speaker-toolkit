#!/usr/bin/env python3
"""Measure and sample one planned clip so the agent can finish its plan entry.

Usage:
    prepare-clip.py --plan <plan.json> --clip <id>

Reads the plan's ``source`` and ``deck_pdf`` and the clip's ``start``/``end``.
The window is the clip plus ``shorts_plan.CONTEXT_SECONDS`` on each side,
clamped to the recording. Writes into ``<work_dir>/<clip id>/``:

- ``words.json``: measured word timings over the window, in source seconds,
  from the vault's pinned word transcriber (``transcribe_local_words``).
- ``frames/<source seconds>.jpg``: ``FRAME_RATE`` frames per second of the
  window, named by their source time.
- ``faces.json``: Apple Vision face boxes for every frame (``vision.swift``).
- ``contact.jpg``: one frame every ``CONTACT_STEP_SECONDS`` of the clip,
  labeled with its clip offset, over a 10% grid with the detected faces drawn.

Once per plan it also renders the deck to ``<work_dir>/deck/page-NNN.png`` and
``deck/contact.jpg`` (page numbers on thumbnails). Rerunning replaces the clip's
files and keeps the rendered deck.

Stdout: ``{"ok": true, "clip", "window", "words", "frames", "faces",
"contact", "deck_contact"}``. A refusal is ``{"ok": false, "error"}`` on
stdout with the same message on stderr, exit 1. Usage errors exit 2.
Needs macOS: ffmpeg, pdftoppm, swift, and the vault venv with mlx-whisper.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFont

SCRIPTS = Path(__file__).resolve().parent
INGRESS = SCRIPTS.parents[1] / "vault-ingress" / "scripts"
for _path in (SCRIPTS, INGRESS):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import shorts_plan  # noqa: E402
from local_media_contract import LocalMediaError  # noqa: E402
from local_media_evidence import probe_local_media  # noqa: E402
from local_media_transcription import transcribe_local_words  # noqa: E402

FRAME_RATE = 2
FRAME_MAX_WIDTH = 1920
CONTACT_STEP_SECONDS = 2.0
CONTACT_TILE_WIDTH = 384
CONTACT_COLUMNS = 5
DECK_TILE_WIDTH = 240
DECK_COLUMNS = 8
TOOL_TIMEOUT_SECONDS = 15 * 60


class PrepareError(RuntimeError):
    """A refusal; the message says what to do."""


def _run(command: list[str], what: str) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise PrepareError(
            f"{what}: {command[0]} is not installed — install it and re-run"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PrepareError(
            f"{what} took over {TOOL_TIMEOUT_SECONDS}s — re-run on a local copy"
        ) from exc
    if completed.returncode != 0:
        raise PrepareError(
            f"{what} failed ({completed.returncode}): {completed.stderr.strip()[-800:]}"
        )
    return completed.stdout


def source_duration(source: Path) -> float:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(source),
        ],
        f"probing {source}",
    )
    try:
        return float(out.strip())
    except ValueError as exc:
        raise PrepareError(
            f"ffprobe gave no duration for {source} — check the file plays"
        ) from exc


def window(clip: dict[str, Any], duration: float) -> tuple[float, float]:
    if clip["end"] > duration:
        raise PrepareError(
            f"clip {clip['id']} ends at {clip['end']}s but the recording is {duration:.2f}s"
        )
    return max(0.0, clip["start"] - shorts_plan.CONTEXT_SECONDS), min(
        duration, clip["end"] + shorts_plan.CONTEXT_SECONDS
    )


def measure_words(
    source: Path, folder: Path, start: float, end: float
) -> list[dict[str, Any]]:
    audio = folder / "audio.wav"
    _run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{end - start:.3f}",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio),
        ],
        "extracting the clip audio",
    )
    try:
        probe = probe_local_media(audio, trusted_root=folder)
        _, receipt = transcribe_local_words(
            audio,
            probe=probe,
            trusted_root=folder,
            sample_start_seconds=0.0,
            sample_duration_seconds=probe.duration_seconds,
        )
    except LocalMediaError as exc:
        raise PrepareError(
            f"word timing failed ({exc.reason_code}): {exc} — repair the vault runtime "
            "with check-runtime.py and re-run"
        ) from exc
    return [
        {
            "text": word["text"].strip(),
            "start": round(start + word["start_seconds"], 3),
            "end": round(start + word["end_seconds"], 3),
        }
        for word in receipt["words"]
        if word["text"].strip()
    ]


def sample_frames(source: Path, frames: Path, start: float, end: float) -> list[Path]:
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    _run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{end - start:.3f}",
            "-i",
            str(source),
            "-vf",
            f"fps={FRAME_RATE},scale='min({FRAME_MAX_WIDTH},iw)':-2",
            "-q:v",
            "3",
            str(frames / "%05d.jpg"),
        ],
        "sampling frames",
    )
    named = []
    for index, path in enumerate(sorted(frames.glob("*.jpg"))):
        target = frames / f"{start + index / FRAME_RATE:09.2f}.jpg"
        path.rename(target)
        named.append(target)
    if not named:
        raise PrepareError(
            "ffmpeg wrote no frames — check the clip times against the recording"
        )
    return named


def frame_time(path: Path) -> float:
    return float(path.stem)


def detect_faces(plan: dict[str, Any], frames: Path) -> list[dict[str, Any]]:
    script = shorts_plan.vision_script(plan)
    rows = json.loads(
        _run(["swift", str(script), "faces", str(frames)], "detecting faces")
    )
    return [
        {
            "t": frame_time(Path(row["file"])),
            **{k: v for k, v in row.items() if k != "file"},
        }
        for row in rows
    ]


def _label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def contact_sheet(
    clip: dict[str, Any], named: list[Path], faces: list[dict[str, Any]], out: Path
) -> None:
    by_time = {row["t"]: row.get("faces", []) for row in faces}
    duration = clip["end"] - clip["start"]
    offsets = []
    offset = 0.0
    while offset <= duration:
        offsets.append(offset)
        offset += CONTACT_STEP_SECONDS
    with Image.open(named[0]) as first:
        height = round(CONTACT_TILE_WIDTH * first.height / first.width)
    rows = (len(offsets) + CONTACT_COLUMNS - 1) // CONTACT_COLUMNS
    sheet = Image.new(
        "RGB", (CONTACT_TILE_WIDTH * CONTACT_COLUMNS, height * rows), "#101723"
    )
    font = _label_font(22)
    for i, offset in enumerate(offsets):
        frame = min(named, key=lambda p: abs(frame_time(p) - (clip["start"] + offset)))
        with Image.open(frame) as image:
            tile = image.convert("RGB").resize((CONTACT_TILE_WIDTH, height))
        draw = ImageDraw.Draw(tile, "RGBA")
        for step in range(1, 10):
            x, y = CONTACT_TILE_WIDTH * step / 10, height * step / 10
            draw.line((x, 0, x, height), fill=(255, 255, 255, 60))
            draw.line((0, y, CONTACT_TILE_WIDTH, y), fill=(255, 255, 255, 60))
        for face in by_time.get(frame_time(frame), []):
            box = (
                face["x"] * CONTACT_TILE_WIDTH,
                face["y"] * height,
                (face["x"] + face["w"]) * CONTACT_TILE_WIDTH,
                (face["y"] + face["h"]) * height,
            )
            draw.rectangle(box, outline=(255, 64, 64, 255), width=2)
        draw.rectangle((0, 0, 92, 30), fill=(0, 0, 0, 170))
        draw.text((6, 4), f"+{offset:.0f}s", font=font, fill="white")
        sheet.paste(
            tile,
            (
                (i % CONTACT_COLUMNS) * CONTACT_TILE_WIDTH,
                (i // CONTACT_COLUMNS) * height,
            ),
        )
    sheet.save(out, quality=85)


def render_deck(plan: dict[str, Any]) -> Path:
    folder = shorts_plan.deck_dir(plan)
    sheet = folder / "contact.jpg"
    if sheet.exists():
        return sheet
    folder.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "pdftoppm",
            "-png",
            "-scale-to-x",
            "1080",
            "-scale-to-y",
            "-1",
            str(plan["deck_pdf"]),
            str(folder / "raw"),
        ],
        f"rendering {plan['deck_pdf']}",
    )
    raw = sorted(folder.glob("raw-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    if not raw:
        raise PrepareError(
            f"pdftoppm wrote no pages for {plan['deck_pdf']} — check the PDF opens"
        )
    pages = []
    for path in raw:
        target = shorts_plan.deck_page(plan, int(path.stem.split("-")[-1]))
        path.rename(target)
        pages.append(target)
    with Image.open(pages[0]) as first:
        height = round(DECK_TILE_WIDTH * first.height / first.width)
    rows = (len(pages) + DECK_COLUMNS - 1) // DECK_COLUMNS
    contact = Image.new(
        "RGB", (DECK_TILE_WIDTH * DECK_COLUMNS, height * rows), "#101723"
    )
    font = _label_font(20)
    for i, page in enumerate(pages, start=1):
        with Image.open(page) as image:
            tile = image.convert("RGB").resize((DECK_TILE_WIDTH, height))
        draw = ImageDraw.Draw(tile, "RGBA")
        draw.rectangle((0, 0, 50, 26), fill=(0, 0, 0, 190))
        draw.text((5, 3), str(i), font=font, fill="white")
        contact.paste(
            tile,
            (
                ((i - 1) % DECK_COLUMNS) * DECK_TILE_WIDTH,
                ((i - 1) // DECK_COLUMNS) * height,
            ),
        )
    contact.save(sheet, quality=85)
    return sheet


def prepare(plan_path: Path, clip_id: str) -> dict[str, Any]:
    plan = shorts_plan.load(plan_path)
    clip = shorts_plan.clip(plan, clip_id)
    folder = shorts_plan.clip_dir(plan, clip_id)
    folder.mkdir(parents=True, exist_ok=True)
    start, end = window(clip, source_duration(plan["source"]))
    words = measure_words(plan["source"], folder, start, end)
    (folder / "words.json").write_text(
        json.dumps(
            {"schema_version": 1, "window": [start, end], "words": words}, indent=1
        )
        + "\n"
    )
    named = sample_frames(plan["source"], folder / "frames", start, end)
    faces = detect_faces(plan, folder / "frames")
    (folder / "faces.json").write_text(
        json.dumps({"schema_version": 1, "rows": faces}, indent=1) + "\n"
    )
    contact_sheet(clip, named, faces, folder / "contact.jpg")
    deck_contact = render_deck(plan)
    return {
        "ok": True,
        "clip": clip_id,
        "window": [start, end],
        "words": str(folder / "words.json"),
        "frames": str(folder / "frames"),
        "faces": str(folder / "faces.json"),
        "contact": str(folder / "contact.jpg"),
        "deck_contact": str(deck_contact),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--clip", required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.plan, args.clip)
    except (shorts_plan.PlanError, PrepareError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

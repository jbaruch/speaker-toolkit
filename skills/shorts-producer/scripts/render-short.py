#!/usr/bin/env python3
"""Render one planned clip into a vertical short with live captions.

Usage:
    render-short.py --plan <plan.json> --clip <id>

Needs the clip prepared (``prepare-clip.py``) and its render fields filled in
(``shorts_plan.require_render_fields``). The layout is fixed: hook headline,
the deck page timed by ``slides``, the speaker cropped from the recording by
face tracking inside ``speaker_region``, captions over the speaker with the
spoken word highlighted, and a card with the shownotes QR when ``qr_url`` is
set. Everything that carries meaning stays clear of the platform's overlays. Geometry, colors and fonts are the named constants below.

The corrected ``captions`` are aligned onto the measured words. A correction
that strays from what was said is refused: see ``MIN_SPOKEN_KEPT``,
``MIN_CAPTION_MATCHED`` and ``MAX_EDIT_WORDS``. Every edit is listed in the
result and in ``caption-alignment.json``.

Writes ``<out_dir>/<id>.mp4``, ``<id>.srt`` and ``<id>.txt``; intermediates go
to ``<work_dir>/<id>/``. Stdout: ``{"ok": true, "clip", "video", "srt",
"txt", "duration", "caption_edits", "crop"}``. A refusal is ``{"ok": false,
"error"}`` on stdout with the same message on stderr, exit 1. Usage errors
exit 2. Needs ffmpeg and the macOS system fonts named below.
"""

from __future__ import annotations

import argparse
import difflib
from functools import lru_cache
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFont
import qrcode
from qrcode.constants import ERROR_CORRECT_M

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import shorts_plan  # noqa: E402

CANVAS = (1080, 1920)
# YouTube Shorts draws its own UI over the top 7% and the bottom 22% of the
# frame, and a button rail on the right from 40% to 85% of the height. The
# hook, captions and QR card stay clear of all three; the speaker's torso fills
# the bottom band, and only the slide's lower right corner reaches the rail.
SAFE_TOP, SAFE_BOTTOM = 134, 1498
RAIL = (929, 768, 151, 864)
TOP_TEXT_Y = 60
HOOK_BOX = (48, 138, 984, 152)
SLIDE_BOX = (0, 300, 1080, 608)
BAR_BOX = (0, 908, 1080, 12)
PRESENTER_BOX = (0, 920, 1080, 1000)
QR_CARD = (28, 944, 270, 314)
CAPTION_BOX = (40, 1286, 860, 210)
QR_SIZE = 246
INK, LIME, PAPER, MUTED = "#0c131d", "#dcff6b", "#fcfbf4", "#a8b2bf"
HEAD_FONT = ("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", 0)
BODY_FONT = ("/System/Library/Fonts/Avenir Next.ttc", 8)  # Avenir Next Heavy
CTA = "SCAN FOR THE FULL TALK"

# Caption fidelity: the share of spoken words the captions keep, the share of
# caption words that were spoken, and the longest run of words a correction
# may put in. Deletions (stutters, false starts) count only against the first.
MIN_SPOKEN_KEPT = 0.85
MIN_CAPTION_MATCHED = 0.85
MAX_EDIT_WORDS = 3
MAX_BLOCK_WORDS = 4
BLOCK_GAP_SECONDS = 0.6
BLOCK_HOLD_SECONDS = 0.25
POP_SECONDS = 0.08
CAPTION_FONT_START = 76
CAPTION_LINE_WIDTH = 800

# Speaker crop: Vision's default confidence admits passers-by; the crop is
# FACE_TO_CROP face heights tall with the face center FACE_AT down from its top.
MIN_FACE_CONFIDENCE = 0.6
FACE_TO_CROP = 5.0
FACE_AT = 0.27
GROUP_WIDTH_MARGIN = 1.6
MIN_TRACK_POINTS = 3
SMOOTH_POINTS = 5
DEADBAND_SHARE = 0.03

LOUDNESS = "I=-14:TP=-1.5:LRA=11"
AUDIO_PREFILTER = "highpass=f=75"
FADE_OUT_SECONDS = 0.12
TOOL_TIMEOUT_SECONDS = 60 * 60


class RenderError(RuntimeError):
    """A refusal; the message says what to change."""


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def spoken_words(
    words: list[dict[str, Any]], start: float, end: float
) -> list[dict[str, Any]]:
    """The measured words inside the clip, in clip seconds."""
    duration = end - start
    return [
        {
            "text": w["text"],
            "start": max(0.0, w["start"] - start),
            "end": min(duration, w["end"] - start),
        }
        for w in words
        if start - 0.05 <= w["start"] < end and _norm(w["text"])
    ]


def align_captions(
    spoken: list[dict[str, Any]], captions: str
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Time each caption word from the speech; refuse a correction that strays."""
    caption = captions.split()
    if not spoken:
        raise RenderError(
            "no measured words fall inside the clip — check start/end and re-prepare"
        )
    a = [_norm(w["text"]) for w in spoken]
    b = [_norm(t) for t in caption]
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    times: list[tuple[float, float] | None] = [None] * len(caption)
    edits: list[dict[str, str]] = []
    matched = 0
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            matched += i2 - i1
            for offset in range(i2 - i1):
                times[j1 + offset] = (
                    spoken[i1 + offset]["start"],
                    spoken[i1 + offset]["end"],
                )
            continue
        edits.append(
            {
                "op": op,
                "spoken": " ".join(w["text"] for w in spoken[i1:i2]),
                "caption": " ".join(caption[j1:j2]),
            }
        )
        if j2 - j1 > MAX_EDIT_WORDS:
            raise RenderError(
                f"the correction {edits[-1]} puts in {j2 - j1} words; keep corrections to "
                f"{MAX_EDIT_WORDS} words or fewer so the captions match the speech"
            )
        if op == "replace":
            begin, finish = spoken[i1]["start"], spoken[i2 - 1]["end"]
        elif op == "insert":
            begin = spoken[i1 - 1]["end"] if i1 else spoken[0]["start"]
            finish = spoken[i1]["start"] if i1 < len(spoken) else spoken[-1]["end"]
            finish = max(finish, begin)
        else:
            continue
        lengths = [max(1, len(t)) for t in caption[j1:j2]]
        cursor = begin
        for offset, length in enumerate(lengths):
            step = (finish - begin) * length / sum(lengths)
            times[j1 + offset] = (cursor, cursor + step)
            cursor += step
    kept, faithful = matched / len(spoken), matched / len(caption)
    if kept < MIN_SPOKEN_KEPT or faithful < MIN_CAPTION_MATCHED:
        raise RenderError(
            f"the captions keep {kept:.0%} of the spoken words and {faithful:.0%} of them "
            f"were spoken (need {MIN_SPOKEN_KEPT:.0%} and {MIN_CAPTION_MATCHED:.0%}); "
            f"correct less — edits: {edits}"
        )
    aligned = []
    previous = 0.0
    for text, span in zip(caption, times):
        assert span is not None
        begin = max(span[0], previous)
        aligned.append({"text": text, "start": begin, "end": max(span[1], begin)})
        previous = begin
    return aligned, edits


def caption_blocks(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    blocks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        if current and (
            len(current) >= MAX_BLOCK_WORDS
            or word["start"] - current[-1]["end"] > BLOCK_GAP_SECONDS
            or (
                len(current) >= 2
                and current[-1]["text"].rstrip("'\")").endswith((".", "?", "!"))
            )
        ):
            blocks.append(current)
            current = []
        current.append(word)
    if current:
        blocks.append(current)
    return blocks


def caption_timeline(
    blocks: list[list[dict[str, Any]]], duration: float
) -> list[tuple[int, int, bool, float, float]]:
    """(block, active word or -1, pop, start, end) states covering the clip."""
    states: list[tuple[int, int, bool, float, float]] = []
    for index, block in enumerate(blocks):
        next_start = (
            blocks[index + 1][0]["start"] if index + 1 < len(blocks) else duration
        )
        block_end = min(next_start, block[-1]["end"] + BLOCK_HOLD_SECONDS, duration)
        for position, word in enumerate(block):
            begin = word["start"]
            finish = (
                block[position + 1]["start"]
                if position + 1 < len(block)
                else block[-1]["end"]
            )
            finish = min(max(finish, begin), block_end)
            if finish - begin > POP_SECONDS * 2:
                states.append((index, position, True, begin, begin + POP_SECONDS))
                begin += POP_SECONDS
            if finish > begin:
                states.append((index, position, False, begin, finish))
        last = states[-1][4] if states else block[0]["start"]
        if block_end > last:
            states.append((index, -1, False, last, block_end))
    return states


@lru_cache(maxsize=64)
def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    path, index = HEAD_FONT if kind == "head" else BODY_FONT
    try:
        return ImageFont.truetype(path, size, index=index)
    except OSError as exc:
        raise RenderError(
            f"font {path} is missing — this skill renders with macOS system fonts"
        ) from exc


def _fitted(text: str, size: int, width: int, kind: str) -> ImageFont.FreeTypeFont:
    while size > 10 and _font(kind, size).getlength(text) > width:
        size -= 1
    return _font(kind, size)


def _block_layout(
    block: list[dict[str, Any]],
) -> tuple[int, list[list[tuple[int, float]]]]:
    size = CAPTION_FONT_START
    while True:
        font = _font("body", size)
        lines: list[list[tuple[int, float]]] = [[]]
        width = 0.0
        for i, word in enumerate(block):
            slot = font.getlength(word["text"].upper()) * 1.08 + 31
            if width + slot > CAPTION_LINE_WIDTH and lines[-1]:
                lines.append([])
                width = 0.0
            lines[-1].append((i, slot))
            width += slot
        if len(lines) <= 2 or size <= 30:
            return size, lines
        size -= 2


def caption_card(
    block: list[dict[str, Any]], active: int, pop: bool, path: Path
) -> None:
    size, lines = _block_layout(block)
    image = Image.new("RGBA", CAPTION_BOX[2:], (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    middle = CAPTION_BOX[3] / 2
    for row, line in enumerate(lines):
        x = (CAPTION_BOX[2] - sum(slot for _, slot in line)) / 2
        y = middle + (row - (len(lines) - 1) / 2) * (size + 23)
        for i, slot in line:
            text = block[i]["text"].upper()
            is_active = i == active
            font = _font("body", round(size * (1.055 if is_active and pop else 1)))
            center = x + slot / 2
            if is_active:
                width = font.getlength(text)
                pad = 15 if pop else 12
                draw.rounded_rectangle(
                    (
                        center - width / 2 - pad,
                        y - size * 0.57 - 9,
                        center + width / 2 + pad,
                        y + size * 0.54 + 9,
                    ),
                    radius=14,
                    fill=LIME,
                )
                draw.text((center, y), text, font=font, fill=INK, anchor="mm")
            else:
                draw.text(
                    (center + 2, y + 4),
                    text,
                    font=font,
                    fill=(0, 0, 0, 150),
                    stroke_width=8,
                    stroke_fill=(0, 0, 0, 150),
                    anchor="mm",
                )
                draw.text(
                    (center, y),
                    text,
                    font=font,
                    fill="#ffffff",
                    stroke_width=5,
                    stroke_fill="#07101a",
                    anchor="mm",
                )
            x += slot
    image.save(path, compress_level=3)


def _clock(seconds: float) -> str:
    ms = round(max(0.0, seconds) * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_captions(
    blocks: list[list[dict[str, Any]]], duration: float, folder: Path, frame_rate: str
) -> tuple[Path, str]:
    cards = folder / "cards"
    cards.mkdir(exist_ok=True)
    for stale in cards.glob("*.png"):
        stale.unlink()
    blank = cards / "blank.png"
    Image.new("RGBA", CAPTION_BOX[2:], (0, 0, 0, 0)).save(blank)
    rows = ["ffconcat version 1.0"]
    cursor = 0.0
    for number, (block, active, pop, begin, finish) in enumerate(
        caption_timeline(blocks, duration)
    ):
        if begin > cursor:
            rows += [
                f"file '{blank.relative_to(folder)}'",
                f"option framerate {frame_rate}",
                f"duration {begin - cursor:.6f}",
            ]
        card = cards / f"{number:05d}.png"
        caption_card(blocks[block], active, pop, card)
        rows += [
            f"file '{card.relative_to(folder)}'",
            f"option framerate {frame_rate}",
            f"duration {finish - begin:.6f}",
        ]
        cursor = finish
    if cursor < duration:
        rows += [
            f"file '{blank.relative_to(folder)}'",
            f"option framerate {frame_rate}",
            f"duration {duration - cursor:.6f}",
        ]
    rows += [f"file '{blank.relative_to(folder)}'", f"option framerate {frame_rate}"]
    concat = folder / "captions.ffconcat"
    concat.write_text("\n".join(rows) + "\n")
    srt = []
    for index, block in enumerate(blocks, start=1):
        srt.append(
            f"{index}\n{_clock(block[0]['start'])} --> {_clock(block[-1]['end'])}\n"
            + " ".join(w["text"] for w in block)
            + "\n"
        )
    return concat, "\n".join(srt)


def qr_image(url: str) -> Image.Image:
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=1, border=4)
    code.add_data(url)
    code.make(fit=True)
    modules = (
        code.make_image(fill_color="black", back_color="white")
        .get_image()
        .convert("RGB")
    )
    scale = QR_SIZE // modules.width
    if scale < 4:
        raise RenderError(
            f"the QR for {url} needs {modules.width} modules; shorten the link"
        )
    sharp = modules.resize(
        (modules.width * scale, modules.width * scale), Image.Resampling.NEAREST
    )
    square = Image.new("RGB", (QR_SIZE, QR_SIZE), "white")
    square.paste(sharp, ((QR_SIZE - sharp.width) // 2, (QR_SIZE - sharp.width) // 2))
    return square


def background(plan: dict[str, Any], clip: dict[str, Any], path: Path) -> None:
    image = Image.new("RGB", CANVAS, INK)
    draw = ImageDraw.Draw(image)
    draw.text(
        (40, TOP_TEXT_Y),
        f"{plan['handle']}  ·  {plan['website']}",
        font=_font("body", 24),
        fill=LIME,
        anchor="lm",
    )
    draw.text(
        (1040, TOP_TEXT_Y),
        plan["event"].upper(),
        font=_font("body", 22),
        fill=MUTED,
        anchor="rm",
    )
    x, y, w, h = HOOK_BOX
    hook = clip["hook"]
    centers = [y + h / 4, y + 3 * h / 4] if len(hook) == 2 else [y + h / 2]
    for row, (line, center) in enumerate(zip(hook, centers)):
        color = LIME if row == 1 else PAPER
        draw.text(
            (x + w / 2, center),
            line,
            font=_fitted(line, 94, w, "head"),
            fill=color,
            anchor="mm",
        )
    x, y, w, h = BAR_BOX
    draw.rectangle((x, y, x + w, y + h), fill=LIME)
    image.save(path)


def qr_card(url: str, path: Path) -> None:
    """The shownotes QR and its call to action, laid over the speaker."""
    width, height = QR_CARD[2:]
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=18, fill=INK)
    margin = (width - QR_SIZE) // 2
    card.paste(qr_image(url), (margin, margin))
    draw.text(
        (width / 2, (margin + QR_SIZE + height) / 2),
        CTA,
        font=_fitted(CTA, 40, width - 2 * margin, "head"),
        fill=PAPER,
        anchor="mm",
    )
    card.save(path)


def slide_panel(page: Path, path: Path) -> None:
    try:
        source = Image.open(page).convert("RGB")
    except OSError as exc:
        raise RenderError(
            f"cannot read deck page {page} — re-run prepare-clip.py"
        ) from exc
    width, height = SLIDE_BOX[2:]
    source.thumbnail((width, height), Image.Resampling.LANCZOS)
    panel = Image.new("RGB", (width, height), INK)
    panel.paste(source, ((width - source.width) // 2, (height - source.height) // 2))
    panel.save(path)


def crop_track(
    rows: list[dict[str, Any]],
    region: list[float],
    start: float,
    end: float,
    size: tuple[int, int],
) -> tuple[tuple[int, int], list[tuple[float, float, float]]]:
    """Crop size and smoothed (t, x, y) keyframes following the speaker."""
    src_w, src_h = size
    rx, ry, rw, rh = region
    points = []
    for row in rows:
        if not start - 1 <= row["t"] <= end + 1:
            continue
        faces = [
            f
            for f in row.get("faces", [])
            if f["confidence"] >= MIN_FACE_CONFIDENCE
            and rx <= f["x"] + f["w"] / 2 <= rx + rw
            and ry <= f["y"] + f["h"] / 2 <= ry + rh
        ]
        if not faces:
            continue
        left = min(f["x"] for f in faces) * src_w
        right = max(f["x"] + f["w"] for f in faces) * src_w
        top = min(f["y"] for f in faces) * src_h
        bottom = max(f["y"] + f["h"] for f in faces) * src_h
        tallest = max(f["h"] for f in faces) * src_h
        points.append(
            (
                row["t"] - start,
                (left + right) / 2,
                (top + bottom) / 2,
                tallest,
                right - left,
            )
        )
    if len(points) < MIN_TRACK_POINTS:
        raise RenderError(
            f"only {len(points)} frames show a face inside speaker_region {region}; widen the "
            "region around the speaker in contact.jpg or pick a clip where the speaker is visible"
        )
    aspect = PRESENTER_BOX[2] / PRESENTER_BOX[3]
    crop_h = statistics.median(p[3] for p in points) * FACE_TO_CROP
    crop_w = max(
        crop_h * aspect, statistics.median(p[4] for p in points) * GROUP_WIDTH_MARGIN
    )
    crop_h = crop_w / aspect
    if crop_w > src_w:
        crop_w, crop_h = src_w, src_w / aspect
    if crop_h > src_h:
        crop_w, crop_h = src_h * aspect, src_h
    crop = (int(crop_w) & ~1, int(crop_h) & ~1)
    keyframes = []
    for i, point in enumerate(points):
        window = points[max(0, i - SMOOTH_POINTS // 2) : i + SMOOTH_POINTS // 2 + 1]
        cx = statistics.median(p[1] for p in window)
        cy = statistics.median(p[2] for p in window)
        x = min(max(cx - crop[0] / 2, 0), src_w - crop[0])
        y = min(max(cy - FACE_AT * crop[1], 0), src_h - crop[1])
        if (
            keyframes
            and max(abs(x - keyframes[-1][1]), abs(y - keyframes[-1][2]))
            < DEADBAND_SHARE * crop[0]
        ):
            continue
        keyframes.append((point[0], x, y))
    return crop, keyframes


def crop_expression(keyframes: list[tuple[float, float, float]], axis: int) -> str:
    """A piecewise-linear ffmpeg expression in t through the keyframes."""
    parts = [f"{keyframes[0][axis]:.1f}"]
    for a, b in zip(keyframes, keyframes[1:]):
        delta = b[axis] - a[axis]
        if abs(delta) >= 0.5:
            span = max(b[0] - a[0], 0.01)
            parts.append(f"{delta:+.1f}*clip((t-{a[0]:.3f})/{span:.3f},0,1)")
    return "".join(parts)


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
        raise RenderError(
            f"{what}: {command[0]} is not installed — install ffmpeg and re-run"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(
            f"{what} took over {TOOL_TIMEOUT_SECONDS}s — render on a local copy"
        ) from exc
    if completed.returncode != 0:
        raise RenderError(
            f"{what} failed ({completed.returncode}): {completed.stderr.strip()[-1200:]}"
        )
    return completed


def probe_video(source: Path) -> tuple[tuple[int, int], str]:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-of",
            "json",
            str(source),
        ],
        f"probing {source}",
    ).stdout
    stream = json.loads(out)["streams"][0]
    return (int(stream["width"]), int(stream["height"])), stream["r_frame_rate"]


def loudness_filter(source: Path, start: float, duration: float) -> str:
    """Two-pass loudnorm: measure the clip, then normalize it linearly."""
    measured = _run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
            "-vn",
            "-af",
            f"{AUDIO_PREFILTER},loudnorm={LOUDNESS}:print_format=json",
            "-f",
            "null",
            "-",
        ],
        "measuring loudness",
    ).stderr
    found = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", measured)
    if found is None:
        raise RenderError(
            "ffmpeg printed no loudness measurement — check the clip has audio"
        )
    m = json.loads(found.group(0))
    return (
        f"{AUDIO_PREFILTER},loudnorm={LOUDNESS}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
        f":offset={m['target_offset']}:linear=true,aresample=48000,afade=t=in:d=0.01,"
        f"afade=t=out:st={max(0.0, duration - FADE_OUT_SECONDS):.3f}:d={FADE_OUT_SECONDS}"
    )


def render(plan_path: Path, clip_id: str) -> dict[str, Any]:
    plan = shorts_plan.load(plan_path)
    clip = shorts_plan.clip(plan, clip_id)
    shorts_plan.require_render_fields(clip)
    folder = shorts_plan.clip_dir(plan, clip_id)
    try:
        words_doc = json.loads((folder / "words.json").read_text())
        faces_doc = json.loads((folder / "faces.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(
            f"clip {clip_id} is not prepared ({exc}) — run prepare-clip.py first"
        ) from exc
    first, last = words_doc["window"]
    if clip["start"] < first or clip["end"] > last:
        raise RenderError(
            f"clip {clip_id} now runs {clip['start']}–{clip['end']}s, outside the prepared "
            f"{first}–{last}s; re-run prepare-clip.py"
        )
    start, end = clip["start"], clip["end"]
    duration = end - start
    size, frame_rate = probe_video(plan["source"])
    words, edits = align_captions(
        spoken_words(words_doc["words"], start, end), clip["captions"]
    )
    (folder / "caption-alignment.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "captions": clip["captions"],
                "edits": edits,
                "words": words,
            },
            indent=1,
        )
        + "\n"
    )
    blocks = caption_blocks(words)
    concat, srt = write_captions(blocks, duration, folder, frame_rate)
    crop, keyframes = crop_track(
        faces_doc["rows"], clip["speaker_region"], start, end, size
    )
    background(plan, clip, folder / "background.png")
    panels = []
    for index, (offset, page) in enumerate(clip["slides"]):
        panel = folder / f"slide-{index:02d}.png"
        slide_panel(shorts_plan.deck_page(plan, page), panel)
        panels.append((offset, panel))
    audio = loudness_filter(plan["source"], start, duration)

    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(plan["source"]),
        "-loop",
        "1",
        "-framerate",
        frame_rate,
        "-i",
        str(folder / "background.png"),
    ]
    for _, panel in panels:
        command += ["-loop", "1", "-framerate", frame_rate, "-i", str(panel)]
    if plan.get("qr_url"):
        qr_card(plan["qr_url"], folder / "qr-card.png")
        command += [
            "-loop",
            "1",
            "-framerate",
            frame_rate,
            "-i",
            str(folder / "qr-card.png"),
        ]
    captions_input = 2 + len(panels) + (1 if plan.get("qr_url") else 0)
    command += ["-f", "concat", "-safe", "0", "-i", str(concat)]
    px, py, pw, ph = PRESENTER_BOX
    graph = [
        f"[0:v]setpts=PTS-STARTPTS,crop={crop[0]}:{crop[1]}:x='{crop_expression(keyframes, 1)}'"
        f":y='{crop_expression(keyframes, 2)}',scale={pw}:{ph},setsar=1[speaker]",
        "[1:v]setsar=1[bg]",
        f"[bg][speaker]overlay={px}:{py}:shortest=1[layer0]",
    ]
    for index, (offset, _) in enumerate(panels):
        enable = f":enable='gte(t,{offset})'" if index else ""
        graph.append(
            f"[layer{index}][{index + 2}:v]overlay={SLIDE_BOX[0]}:{SLIDE_BOX[1]}:shortest=1{enable}[layer{index + 1}]"
        )
    under_captions = f"layer{len(panels)}"
    if plan.get("qr_url"):
        graph.append(
            f"[{under_captions}][{captions_input - 1}:v]overlay={QR_CARD[0]}:{QR_CARD[1]}:shortest=1[carded]"
        )
        under_captions = "carded"
    graph.append(
        f"[{under_captions}][{captions_input}:v]overlay={CAPTION_BOX[0]}:{CAPTION_BOX[1]}:eof_action=repeat:format=auto,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709,format=yuv420p[v]"
    )
    graph.append(f"[0:a]asetpts=PTS-STARTPTS,{audio}[a]")
    out_dir = plan["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    video = out_dir / f"{clip_id}.mp4"
    command += [
        "-filter_complex",
        ";".join(graph),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        f"{duration:.3f}",
        "-r",
        frame_rate,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        "-metadata",
        f"title={clip['title']}",
        str(video),
    ]
    (folder / "render-command.json").write_text(json.dumps(command, indent=1) + "\n")
    _run(command, "rendering the short")
    srt_path, txt_path = video.with_suffix(".srt"), video.with_suffix(".txt")
    srt_path.write_text(srt)
    txt_path.write_text(clip["captions"].strip() + "\n")
    return {
        "ok": True,
        "clip": clip_id,
        "video": str(video),
        "srt": str(srt_path),
        "txt": str(txt_path),
        "duration": round(duration, 3),
        "caption_edits": edits,
        "crop": {"size": list(crop), "keyframes": len(keyframes)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--clip", required=True)
    args = parser.parse_args(argv)
    try:
        result = render(args.plan, args.clip)
    except (shorts_plan.PlanError, RenderError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

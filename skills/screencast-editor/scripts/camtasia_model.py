"""Shared model for Camtasia screencast editing: time, framing, projects, pointer.

Imported by the sibling CLIs in this directory. Pure functions and small file
helpers; the only external process is `lsof`, to tell whether Camtasia has a
project open.
"""

from __future__ import annotations

import hashlib
import json
import math
import plistlib
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FPS = 30
MIN_SHOT_SECONDS = 1.0  # a visible shot shorter than this reads as a glitch
MOVE_SECONDS = 0.8  # the ease into each framing cue
MENUBAR_POINTS = 28  # macOS menu bar height at 1920x1080 points
PROJECT_FILE = "project.tscproj"
OPEN_PROJECT_FILE = "~project.tscproj"

# GUIDs of the records inside a .trec's TSCM atom, as raw bytes.
POINTER_PATH_GUID = bytes.fromhex("2b7b6af27a1f11e283d00017f200be7f")
CAPTURE_RECT_GUID = bytes.fromhex("2b7b6af67a1f11e283d00017f200be7f")

SENTENCE_END = re.compile(r"[.?!][\"”’)]?$")


def tick(seconds: float, edit_rate: int, fps: int = FPS) -> int:
    """Seconds to Camtasia ticks, snapped to a frame boundary."""
    return round(seconds * fps) * edit_rate // fps


def normalize(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", word.lower().replace("’", "'"))


# --------------------------------------------------------------------- framing


@dataclass(frozen=True)
class Canvas:
    width: float = 1920.0
    height: float = 1080.0
    menubar: float = MENUBAR_POINTS  # canvas pixels hidden at the top at fit


def min_zoom(canvas: Canvas = Canvas()) -> float:
    """Smallest zoom that hides the menu bar without exposing the bottom edge."""
    return canvas.height / (canvas.height - canvas.menubar)


def frame(
    zoom: float, x: float, y: float, canvas: Canvas = Canvas()
) -> dict[str, float]:
    """Canvas framing for full-screen footage at `zoom` around focal point (x, y).

    (x, y) is normalized source position, top-left origin. Camtasia translation
    is center-relative in canvas pixels with y UP. The result never exposes a
    canvas edge and never reveals the menu bar; a zoom too small to do both is
    refused.
    """
    if zoom < min_zoom(canvas) - 1e-9:
        raise ValueError(
            f"zoom {zoom} cannot hide the menu bar without exposing an edge; "
            f"use at least {min_zoom(canvas):.3f}"
        )
    w, h = canvas.width * zoom, canvas.height * zoom
    half_w, half_h = canvas.width / 2, canvas.height / 2
    tx = max(-(w / 2 - half_w), min(w / 2 - half_w, (0.5 - x) * w))
    ty = (y - 0.5) * h
    lowest = half_h - h / 2 + canvas.menubar * zoom  # image top stays above the bar
    ty = max(lowest, min(h / 2 - half_h, ty))
    return {"zoom": zoom, "translation0": tx, "translation1": ty}


def visible_rect(
    zoom: float, x: float, y: float, canvas: Canvas = Canvas()
) -> tuple[float, float, float, float]:
    """Normalized source rectangle (x0, y0, x1, y1) that `frame` puts on screen."""
    f = frame(zoom, x, y, canvas)
    cx = 0.5 - f["translation0"] / (canvas.width * zoom)
    cy = 0.5 + f["translation1"] / (canvas.height * zoom)
    half = 0.5 / zoom
    return (cx - half, cy - half, cx + half, cy + half)


# --------------------------------------------------------------------- plan


def _number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def plan_canvas(plan: dict[str, Any]) -> Canvas:
    c = plan.get("canvas", {})
    if not isinstance(c, dict):
        raise ValueError("'canvas' must be an object")
    values = {
        k: c.get(k, d)
        for k, d in (("width", 1920), ("height", 1080), ("menubar", MENUBAR_POINTS))
    }
    if not all(_number(v) for v in values.values()):
        raise ValueError("canvas width, height and menubar must be finite numbers")
    if (
        values["width"] <= 0
        or values["height"] <= 0
        or not 0 <= values["menubar"] < values["height"]
    ):
        raise ValueError(
            "canvas needs a positive size and a menu bar shorter than its height"
        )
    return Canvas(
        float(values["width"]), float(values["height"]), float(values["menubar"])
    )


def load_plan(path: Path) -> dict[str, Any]:
    """Read and validate a shot plan. Raises ValueError with the first problem."""
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"cannot read shot plan {path}: {e}") from e
    if (
        not isinstance(plan, dict)
        or not isinstance(plan.get("shots"), list)
        or not plan["shots"]
    ):
        raise ValueError(f"{path}: needs a non-empty 'shots' list")
    shots = plan["shots"]
    canvas = plan_canvas(plan)
    floor = min_zoom(canvas)
    for i, s in enumerate(shots):
        where = f"{path}: shot {i + 1}"
        if not isinstance(s, dict):
            raise ValueError(f"{where}: must be an object")
        if s.get("kind") not in ("speaker", "screen"):
            raise ValueError(f"{where}: kind must be 'speaker' or 'screen'")
        if not (_number(s.get("start")) and _number(s.get("end"))):
            raise ValueError(f"{where}: start and end must be numbers (source seconds)")
        if s["start"] < 0:
            raise ValueError(f"{where}: starts before the recording (negative time)")
        if s["end"] <= s["start"]:
            raise ValueError(f"{where}: ends before it starts")
        if s["end"] - s["start"] < MIN_SHOT_SECONDS:
            raise ValueError(f"{where}: shorter than {MIN_SHOT_SECONDS} s")
        if s["kind"] != "screen":
            continue
        cues = s.get("cues")
        if not isinstance(cues, list) or not cues:
            raise ValueError(f"{where}: screen shots need cues of [time, zoom, x, y]")
        for c in cues:
            if not (isinstance(c, list) and len(c) == 4 and all(_number(v) for v in c)):
                raise ValueError(
                    f"{where}: every cue must be [time, zoom, x, y] numbers"
                )
        if any(not (0 <= c[2] <= 1 and 0 <= c[3] <= 1) for c in cues):
            raise ValueError(
                f"{where}: a cue's focal point must lie within the screen (0 to 1)"
            )
        if cues[0][0] != s["start"]:
            raise ValueError(f"{where}: the first cue must sit at the shot start")
        if any(not (s["start"] <= c[0] <= s["end"]) for c in cues):
            raise ValueError(f"{where}: a cue falls outside the shot")
        if any(b[0] <= a[0] for a, b in zip(cues, cues[1:])):
            raise ValueError(
                f"{where}: cue times must strictly increase; sort the cues and drop duplicates"
            )
        if any(c[1] < floor - 1e-9 for c in cues):
            raise ValueError(
                f"{where}: zoom below {floor:.3f} exposes the canvas edge or the menu bar"
            )
    for i, (a, b) in enumerate(zip(shots, shots[1:])):
        if a["end"] != b["start"]:
            raise ValueError(
                f"{path}: gap or overlap between shots {i + 1} and {i + 2}"
            )
    return plan


# --------------------------------------------------------------------- project


def project_file(target: Path) -> Path:
    """The saved project file of a bundle (or the file itself)."""
    if target.suffix == ".tscproj":
        return target
    candidate = target / PROJECT_FILE
    if candidate.is_file() and candidate.stat().st_size > 0:
        return candidate
    raise ValueError(
        f"no saved {PROJECT_FILE} in {target} — save the project in Camtasia first"
    )


def camtasia_open_files() -> list[str]:
    """Paths Camtasia holds open. Empty when Camtasia is not running or cannot run here.

    A failure to ask is an error, never "nothing open": treating it as closed
    would let a caption pass overwrite a live project.
    """
    if sys.platform != "darwin":
        return []
    for tool in ("pgrep", "lsof"):
        if shutil.which(tool) is None:
            raise ValueError(
                f"cannot tell whether Camtasia has the project open: {tool} is missing"
            )
    running = subprocess.run(
        ["pgrep", "-x", "Camtasia"], capture_output=True, text=True, check=False
    )
    if running.returncode == 1:
        return []
    if running.returncode != 0:
        raise ValueError(
            f"cannot tell whether Camtasia is running: {running.stderr.strip()}"
        )
    result = subprocess.run(
        ["lsof", "-Fn", "-c", "Camtasia"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0 or not result.stdout:
        raise ValueError(
            f"cannot list Camtasia's open files ({result.stderr.strip() or 'lsof exit ' + str(result.returncode)}); "
            "quit Camtasia or close the project, then rerun"
        )
    return [line[1:] for line in result.stdout.splitlines() if line.startswith("n")]


def ensure_closed(bundle: Path, open_files: list[str] | None = None) -> None:
    """Refuse to write a project Camtasia has open; its next save would undo the edit.

    A closed bundle keeps an empty open-copy marker, so the marker only counts
    when it has content. An open project also holds its recording open.
    """
    marker = bundle / OPEN_PROJECT_FILE
    if marker.is_file() and marker.stat().st_size > 0:
        raise ValueError(
            f"{bundle} is open in Camtasia — save and close it, then rerun"
        )
    prefix = str(bundle.resolve()) + "/"
    held = camtasia_open_files() if open_files is None else open_files
    if any(path.startswith(prefix) for path in held):
        raise ValueError(
            f"{bundle} is open in Camtasia — save and close it, then rerun"
        )


def atomic_write_text(path: Path, text: str) -> None:
    """Write beside the target, then replace it in one step."""
    staging = path.with_name(f".{path.name}.writing")
    staging.write_text(text, encoding="utf-8")
    staging.replace(path)


def load_project(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"cannot read Camtasia project {path}: {e}") from e


def tracks(project: dict[str, Any]) -> list[dict[str, Any]]:
    return project["timeline"]["sceneTrack"]["scenes"][0]["csml"]["tracks"]


def audio_source_track(project: dict[str, Any]) -> dict[str, Any]:
    """The first audio track in the source bin, which carries Camtasia's transcript."""
    for source in project["sourceBin"]:
        for track in source.get("sourceTracks", []):
            if track.get("type") == 2:
                return track
    raise ValueError("the project has no audio source track")


def transcript_words(project: dict[str, Any]) -> list[tuple[float, str]]:
    """(source seconds, word) from Camtasia's recognition, pause markers removed."""
    params = audio_source_track(project).get("parameters", {})
    keyframes = params.get("transcription", {}).get("keyframes")
    if not keyframes:
        raise ValueError(
            "no Camtasia transcript — add dynamic captions in Camtasia, save, and close"
        )
    rate = project["editRate"]
    return [(k["time"] / rate, k["value"]) for k in keyframes if k["value"] != "%GAP"]


def companion_bytes() -> dict[str, bytes]:
    """The files Camtasia's Open dialog expects next to project.tscproj."""
    return {
        "bookmarks.plist": plistlib.dumps({}),
        "docPrefs": plistlib.dumps(
            {"DocPrefPlayheadTime": "0", "SaveAsStandaloneProject": 1}
        ),
    }


def write_companions(bundle: Path) -> None:
    for sub in ("media", "originals", "recordings"):
        (bundle / sub).mkdir(parents=True, exist_ok=True)
    for name, data in companion_bytes().items():
        (bundle / name).write_bytes(data)


def file_digest(path: Path) -> str:
    """SHA-256 of a file, read in chunks: recordings run to gigabytes."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------- .trec pointer


def _atom_header(read, offset: int, total: int) -> tuple[int, bytes, int]:
    size, kind = struct.unpack(">I4s", read(offset, 8))
    header = 8
    if size == 1:
        size = struct.unpack(">Q", read(offset + 8, 8))[0]
        header = 16
    elif size == 0:
        size = total - offset
    if size < header:
        raise ValueError("malformed MP4 atom header")
    return size, kind, header


def top_level_atom(data: bytes, kind: bytes) -> bytes:
    """Body of the first top-level MP4 atom of `kind`, honouring 64-bit sizes."""
    offset = 0
    while offset + 8 <= len(data):
        size, found, header = _atom_header(
            lambda o, n: data[o : o + n], offset, len(data)
        )
        if found == kind:
            return data[offset + header : offset + size]
        offset += size
    raise ValueError(f"no {kind.decode()} atom — not a Camtasia recording")


def read_top_level_atom(path: Path, kind: bytes) -> bytes:
    """Like `top_level_atom`, but seeks through the file: recordings run to gigabytes."""
    try:
        with path.open("rb") as f:
            total = f.seek(0, 2)

            def read(offset: int, n: int) -> bytes:
                f.seek(offset)
                return f.read(n)

            offset = 0
            while offset + 8 <= total:
                size, found, header = _atom_header(read, offset, total)
                if found == kind:
                    return read(offset + header, size - header)
                offset += size
    except OSError as e:
        raise ValueError(f"cannot read {path}: {e}") from e
    raise ValueError(f"no {kind.decode()} atom — not a Camtasia recording")


def tscm_records(blob: bytes) -> dict[bytes, bytes]:
    """Records of a TSCM atom body, keyed by GUID bytes.

    Layout per record: <u32 BE count> b'DATA' <u64 BE length> <16-byte GUID>
    <payload>, where length spans the whole record from the count field on.
    """
    records: dict[bytes, bytes] = {}
    offset = 0
    while True:
        at_data = blob.find(b"DATA", offset)
        if at_data < 0 or at_data + 28 > len(blob):
            break
        length = struct.unpack(">Q", blob[at_data + 4 : at_data + 12])[0]
        guid = blob[at_data + 12 : at_data + 28]
        end = at_data - 4 + length
        if length < 32 or end > len(blob):
            raise ValueError("malformed TSCM record")
        records.setdefault(guid, blob[at_data + 28 : end])
        offset = end
    return records


def capture_rect(records: dict[bytes, bytes]) -> tuple[int, int, int, int]:
    """Captured display rectangle in global points: x, y, width, height."""
    body = records.get(CAPTURE_RECT_GUID)
    if body is None or len(body) < 32:
        raise ValueError("the recording has no capture rectangle record")
    _version, entry = struct.unpack("<II", body[:8])
    if entry != 24:
        raise ValueError(f"unexpected capture rectangle entry size {entry}")
    _time, x, y, width, height = struct.unpack("<diiii", body[8:32])
    return x, y, width, height


def pointer_path(records: dict[bytes, bytes]) -> list[tuple[float, int, int]]:
    """(seconds, x, y) pointer samples in global points."""
    body = records.get(POINTER_PATH_GUID)
    if body is None or len(body) < 8:
        raise ValueError("the recording has no pointer path record")
    _version, entry = struct.unpack("<II", body[:8])
    if entry != 16:
        raise ValueError(f"unexpected pointer sample size {entry}")
    count = (len(body) - 8) // 16
    return [struct.unpack("<dii", body[8 + i * 16 : 24 + i * 16]) for i in range(count)]

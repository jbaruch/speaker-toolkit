"""Shared model for Camtasia screencast editing: time, framing, projects, pointer.

Imported by the sibling CLIs in this directory. Pure functions and small file
helpers only; nothing here talks to Camtasia, ffmpeg, or the network.
"""

from __future__ import annotations

import json
import plistlib
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FPS = 30
MENUBAR_POINTS = 28  # macOS menu bar height at 1920x1080 points
PROJECT_FILE = "project.tscproj"
OPEN_PROJECT_FILE = "~project.tscproj"

# GUIDs of the records inside a .trec's TSCM atom, as raw little-endian bytes.
POINTER_PATH_GUID = bytes.fromhex("2b7b6af27a1f11e283d00017f200be7f")
CAPTURE_RECT_GUID = bytes.fromhex("2b7b6af67a1f11e283d00017f200be7f")


def tick(seconds: float, edit_rate: int, fps: int = FPS) -> int:
    """Seconds to Camtasia ticks, snapped to a frame boundary."""
    return round(seconds * fps) * edit_rate // fps


# --------------------------------------------------------------------- framing


@dataclass(frozen=True)
class Canvas:
    width: float = 1920.0
    height: float = 1080.0
    menubar: float = MENUBAR_POINTS  # canvas pixels hidden at the top at fit


def frame(
    zoom: float, x: float, y: float, canvas: Canvas = Canvas()
) -> dict[str, float]:
    """Canvas framing for full-screen footage at `zoom` around focal point (x, y).

    (x, y) is normalized source position, top-left origin. Camtasia translation
    is center-relative in canvas pixels with y UP. The result never exposes a
    canvas edge and never reveals the menu bar.
    """
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
    for i, s in enumerate(shots):
        where = f"{path}: shot {i + 1}"
        if s.get("kind") not in ("speaker", "screen"):
            raise ValueError(f"{where}: kind must be 'speaker' or 'screen'")
        if not (
            isinstance(s.get("start"), (int, float))
            and isinstance(s.get("end"), (int, float))
        ):
            raise ValueError(f"{where}: start and end must be numbers (source seconds)")
        if s["end"] <= s["start"]:
            raise ValueError(f"{where}: ends before it starts")
        if s["end"] - s["start"] < 1.0:
            raise ValueError(f"{where}: shorter than one second")
        if s["kind"] == "screen":
            cues = s.get("cues")
            if not cues or any(len(c) != 4 for c in cues):
                raise ValueError(
                    f"{where}: screen shots need cues of [time, zoom, x, y]"
                )
            if cues[0][0] != s["start"]:
                raise ValueError(f"{where}: the first cue must sit at the shot start")
            if any(not (s["start"] <= c[0] <= s["end"]) for c in cues):
                raise ValueError(f"{where}: a cue falls outside the shot")
            if any(c[1] < 1.0 for c in cues):
                raise ValueError(f"{where}: zoom below 1.0 exposes the canvas edge")
    for i, (a, b) in enumerate(zip(shots, shots[1:])):
        if a["end"] != b["start"]:
            raise ValueError(
                f"{path}: gap or overlap between shots {i + 1} and {i + 2}"
            )
    return plan


def plan_canvas(plan: dict[str, Any]) -> Canvas:
    c = plan.get("canvas", {})
    return Canvas(
        float(c.get("width", 1920)),
        float(c.get("height", 1080)),
        float(c.get("menubar", MENUBAR_POINTS)),
    )


# --------------------------------------------------------------------- project


def project_file(target: Path) -> Path:
    """The .tscproj for a bundle, a saved project file, or Camtasia's open copy."""
    if target.suffix == ".tscproj":
        return target
    for name in (PROJECT_FILE, OPEN_PROJECT_FILE):
        candidate = target / name
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    raise ValueError(
        f"no saved {PROJECT_FILE} in {target} — save the project in Camtasia first"
    )


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


def write_companions(bundle: Path) -> None:
    """The files Camtasia's Open dialog expects next to project.tscproj."""
    for sub in ("media", "originals", "recordings"):
        (bundle / sub).mkdir(parents=True, exist_ok=True)
    (bundle / "bookmarks.plist").write_bytes(plistlib.dumps({}))
    (bundle / "docPrefs").write_bytes(
        plistlib.dumps({"DocPrefPlayheadTime": "0", "SaveAsStandaloneProject": 1})
    )


# --------------------------------------------------------------------- .trec pointer


def top_level_atom(data: bytes, kind: bytes) -> bytes:
    """Body of the first top-level MP4 atom of `kind`, honouring 64-bit sizes."""
    offset = 0
    while offset + 8 <= len(data):
        size, found = struct.unpack(">I4s", data[offset : offset + 8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", data[offset + 8 : offset + 16])[0]
            header = 16
        elif size == 0:
            size = len(data) - offset
        if size < header:
            raise ValueError("malformed MP4 atom header")
        if found == kind:
            return data[offset + header : offset + size]
        offset += size
    raise ValueError(f"no {kind.decode()} atom — not a Camtasia recording")


def tscm_records(data: bytes) -> dict[bytes, bytes]:
    """Records of the trailing TSCM atom, keyed by GUID bytes.

    Layout per record: <u32 BE count> b'DATA' <u64 BE length> <16-byte GUID>
    <payload>, where length spans the whole record from the count field on.
    """
    blob = top_level_atom(data, b"TSCM")
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


# --------------------------------------------------------------------- captions text

SENTENCE_END = re.compile(r"[.?!][\"”’)]?$")


def normalize(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", word.lower().replace("’", "'"))

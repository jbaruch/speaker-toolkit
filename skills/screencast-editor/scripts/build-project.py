#!/usr/bin/env python3
"""Generate a speaker-first Camtasia edit from a take and a shot plan.

Input is the project Camtasia created for a screen + camera + mic recording
(track 0: the screen, track 1: the camera and mic as one UnifiedMedia clip).
Output is a NEW .cmproj bundle: the recording cloned inside it, the screen
evidence zoomed per cue on track 0, the presenter inset and the one continuous
audio clip on track 1, and full-frame presenter shots on a muted track 2.

Usage:
    build-project.py <recording-project> <shot-plan.json> --out <new.cmproj>

Refuses to overwrite. Exit 0 on success, 1 on an invalid template or plan,
2 on usage error. Open the result in Camtasia and export from there, so
Camtasia's own audio effects are included.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camtasia_model as model  # noqa: E402

EFFECTS = Path(__file__).resolve().parent / "camtasia-effects.json"
MOVE_SECONDS = 0.8
DEFAULT_INSET = {
    "height": 324.0,
    "x": 640.0,
    "y": -346.0,
    "corner_radius": 120.0,
    "border_color": "#A78BFA",
    "border_width": 4,
}


def clone(source: Path, target: Path) -> None:
    """Copy the recording into the bundle; an APFS clone on macOS costs no space."""
    if sys.platform == "darwin":
        subprocess.run(["cp", "-c", str(source), str(target)], check=True)
    else:
        shutil.copy2(source, target)


def build(template: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    p = copy.deepcopy(template)
    rate = p["editRate"]
    canvas = model.plan_canvas(plan)
    shots = plan["shots"]
    t0, t1 = shots[0]["start"], shots[-1]["end"]

    def tick(s: float) -> int:
        return model.tick(s, rate)

    def place(media: dict[str, Any], a: float, b: float) -> None:
        media.update(
            start=tick(a) - tick(t0),
            duration=tick(b) - tick(a),
            mediaStart=tick(a),
            mediaDuration=tick(b) - tick(a),
        )

    tr = model.tracks(p)
    if len(tr) < 2 or not tr[0]["medias"] or not tr[1]["medias"]:
        raise ValueError(
            "template must have the screen on track 0 and camera + mic on track 1"
        )
    screen0, unified = tr[0]["medias"][0], tr[1]["medias"][0]
    if screen0.get("_type") != "ScreenVMFile" or unified.get("_type") != "UnifiedMedia":
        raise ValueError(
            "template tracks are not Camtasia's screen + camera recording layout"
        )
    if tick(t1) > min(screen0["mediaDuration"], unified["mediaDuration"]):
        raise ValueError("the plan runs past the end of the recording")
    base_scale = canvas.height / source_height(p, screen0["src"])
    next_id = max(m["id"] for t in tr for m in t["medias"]) + 100

    screens = []
    for shot in shots:
        if shot["kind"] != "screen":
            continue
        m = copy.deepcopy(screen0)
        next_id += 1
        m["id"] = next_id
        m["attributes"]["ident"] = shot.get("label", "")
        place(m, shot["start"], shot["end"])
        cues = shot["cues"]

        def params(z: float, x: float, y: float) -> dict[str, float]:
            f = model.frame(z, x, y, canvas)
            return {
                "scale0": base_scale * z,
                "scale1": base_scale * z,
                "translation0": f["translation0"],
                "translation1": f["translation1"],
            }

        base = params(*cues[0][1:])
        animated: dict[str, dict[str, Any]] = {
            k: {"type": "double", "defaultValue": v, "interp": "eioe", "keyframes": []}
            for k, v in base.items()
        }
        visual = []
        for raw, z, x, y in cues[1:]:
            end = tick(raw) - tick(shot["start"])
            length = min(tick(MOVE_SECONDS), end)
            visual.append({"endTime": end, "duration": length})
            for k, v in params(z, x, y).items():
                animated[k]["keyframes"].append(
                    {
                        "time": end - length,
                        "endTime": end,
                        "duration": length,
                        "value": v,
                    }
                )
        for k, v in animated.items():
            m["parameters"][k] = v if v["keyframes"] else base[k]
        m["animationTracks"] = {"visual": visual} if visual else {}
        screens.append(m)
    tr[0]["medias"] = screens

    inset = {**DEFAULT_INSET, **plan.get("inset", {})}
    effects = json.loads(EFFECTS.read_text(encoding="utf-8"))
    place(unified, t0, t1)
    for part in (unified["video"], unified["audio"]):
        place(part, t0, t1)
    camera_height = source_height(
        p, unified["video"]["src"], track=unified["video"]["trackNumber"]
    )
    camera_scale = canvas.height / camera_height
    inset_scale = float(inset["height"]) / camera_height
    unified["video"]["parameters"].update(
        scale0=inset_scale,
        scale1=inset_scale,
        translation0=inset["x"],
        translation1=inset["y"],
    )
    rounded, border = (
        copy.deepcopy(effects["RoundCorners"]),
        copy.deepcopy(effects["Border"]),
    )
    rounded["parameters"]["radius"]["defaultValue"] = float(inset["corner_radius"])
    color = inset["border_color"].lstrip("#")
    for i, channel in enumerate(("red", "green", "blue")):
        border["parameters"][f"color-{channel}"]["defaultValue"] = (
            int(color[i * 2 : i * 2 + 2], 16) / 255
        )
    border["parameters"]["width"]["defaultValue"] = inset["border_width"]
    border["parameters"]["type"] = 1
    unified["video"]["effects"] = [rounded, border]
    if plan.get("noise_removal", 0.8):
        noise = copy.deepcopy(effects["NoiseRemoval"])
        noise["parameters"]["Amount"] = float(plan.get("noise_removal", 0.8))
        unified["audio"]["effects"] = [noise]

    speaker = []
    for shot in shots:
        if shot["kind"] != "speaker":
            continue
        next_id += 1
        m = {
            "id": next_id,
            "_type": "VMFile",
            "src": unified["video"]["src"],
            "trackNumber": unified["video"]["trackNumber"],
            "attributes": {"ident": shot.get("label", "")},
            "parameters": {
                "scale0": camera_scale,
                "scale1": camera_scale,
                "translation0": 0,
                "translation1": 0,
            },
            "effects": [],
            "scalar": 1,
            "animationTracks": {},
        }
        place(m, shot["start"], shot["end"])
        speaker.append(m)
    tr[2:] = [{"trackIndex": 2, "medias": speaker, "parameters": {}}]
    attrs = p["timeline"]["trackAttributes"]
    attrs[0]["ident"], attrs[1]["ident"] = "Screen", "Presenter inset + audio"
    speaker_attrs = copy.deepcopy(attrs[0])
    speaker_attrs.update(ident="Speaker full frame", audioMuted=True)
    p["timeline"]["trackAttributes"] = attrs[:2] + [speaker_attrs]
    if plan.get("title"):
        p["title"] = plan["title"]
    if sum(m["duration"] for m in screens + speaker) != unified["duration"]:
        raise ValueError("shots do not tile the edit exactly")
    return p


def source_height(project: dict[str, Any], src: int, track: int = 0) -> float:
    for source in project["sourceBin"]:
        if source["id"] == src:
            rect = source["sourceTracks"][track]["trackRect"]
            return float(rect[3] - rect[1])
    raise ValueError(f"source {src} is not in the source bin")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "template",
        type=Path,
        help="the recording's Camtasia project (bundle or .tscproj)",
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument(
        "--out", type=Path, required=True, help="new .cmproj bundle to create"
    )
    args = parser.parse_args(argv)
    if args.out.exists():
        print(
            f"build-project: {args.out} already exists; refusing to overwrite",
            file=sys.stderr,
        )
        return 2
    try:
        template = model.load_project(model.project_file(args.template))
        plan = model.load_plan(args.plan)
        project = build(template, plan)
        recording = Path(project["sourceBin"][0]["src"])
        if not recording.is_absolute():
            recording = model.project_file(args.template).parent / recording
        if not recording.is_file():
            raise ValueError(
                f"recording {recording} is missing — Camtasia's temporary folder is not an archive"
            )
    except ValueError as e:
        print(f"build-project: {e}", file=sys.stderr)
        return 1
    model.write_companions(args.out)
    clone(recording, args.out / "media" / recording.name)
    project["sourceBin"][0]["src"] = f"./media/{recording.name}"
    (args.out / model.PROJECT_FILE).write_text(
        json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (args.out / "shot-plan.json").write_text(
        json.dumps(plan, indent=1), encoding="utf-8"
    )
    screens = sum(s["kind"] == "screen" for s in plan["shots"])
    print(
        json.dumps(
            {
                "project": str(args.out),
                "screen_shots": screens,
                "speaker_shots": len(plan["shots"]) - screens,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

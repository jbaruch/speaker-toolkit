#!/usr/bin/env python3
"""Generate a speaker-first Camtasia edit from a take and a shot plan.

Input is the project Camtasia created for a screen + camera + mic recording
(track 0: the screen, track 1: the camera and mic as one UnifiedMedia clip).
Output is a NEW .cmproj bundle: the recording cloned inside it, the screen
evidence zoomed per cue on track 0, the presenter inset and the one continuous
audio clip on track 1, and full-frame presenter shots on a muted track 2.

Usage:
    build-project.py <recording-project> <shot-plan.json> --out <new.cmproj>

The bundle is staged beside the target and renamed into place only when
complete. Rerunning with the same inputs is a no-op; a different existing
bundle is never overwritten. Effects the user applied to the template's camera
and mic clips are kept; this script only owns the rounded inset (RoundCorners,
Border) and AI noise removal. Exit 0 on success, 1 on an invalid template or
plan, 2 on usage error or a conflicting existing bundle. Export from Camtasia,
so its audio effects are included.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from collections.abc import Callable
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camtasia_model as model  # noqa: E402

EFFECTS = Path(__file__).resolve().parent / "camtasia-effects.json"
DEFAULT_INSET = {
    "height": 324.0,
    "x": 640.0,
    "y": -346.0,
    "corner_radius": 120.0,
    "border_color": "#A78BFA",
    "border_width": 4,
}
OWNED_VIDEO_EFFECTS = ("RoundCorners", "Border")
NOISE_EFFECT = "VSTEffect-DFN3NoiseRemoval"


def source_height(project: dict[str, Any], src: int, track: int = 0) -> float:
    for source in project["sourceBin"]:
        if source["id"] == src:
            rect = source["sourceTracks"][track]["trackRect"]
            return float(rect[3] - rect[1])
    raise ValueError(f"source {src} is not in the source bin")


def inset_effects(
    existing: list[dict[str, Any]], inset: dict[str, Any], library: dict[str, Any]
) -> list[dict[str, Any]]:
    """User effects first, then this script's rounded inset in its required order."""
    rounded, border = (
        copy.deepcopy(library["RoundCorners"]),
        copy.deepcopy(library["Border"]),
    )
    rounded["parameters"]["radius"]["defaultValue"] = float(inset["corner_radius"])
    color = str(inset["border_color"]).lstrip("#")
    for i, channel in enumerate(("red", "green", "blue")):
        border["parameters"][f"color-{channel}"]["defaultValue"] = (
            int(color[i * 2 : i * 2 + 2], 16) / 255
        )
    border["parameters"]["width"]["defaultValue"] = inset["border_width"]
    border["parameters"]["type"] = 1
    kept = [e for e in existing if e.get("effectName") not in OWNED_VIDEO_EFFECTS]
    return kept + [rounded, border]


def noise_effects(
    existing: list[dict[str, Any]], amount: float, library: dict[str, Any]
) -> list[dict[str, Any]]:
    """User effects kept; noise removal set to `amount`, or removed at 0."""
    kept = [e for e in existing if e.get("effectName") != NOISE_EFFECT]
    if amount <= 0:
        return kept
    noise = copy.deepcopy(library["NoiseRemoval"])
    noise["parameters"]["Amount"] = float(amount)
    return kept + [noise]


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

    def params(z: float, x: float, y: float) -> dict[str, float]:
        f = model.frame(z, x, y, canvas)
        return {
            "scale0": base_scale * z,
            "scale1": base_scale * z,
            "translation0": f["translation0"],
            "translation1": f["translation1"],
        }

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
        base = params(*cues[0][1:])
        animated: dict[str, dict[str, Any]] = {
            k: {"type": "double", "defaultValue": v, "interp": "eioe", "keyframes": []}
            for k, v in base.items()
        }
        visual = []
        for raw, z, x, y in cues[1:]:
            end = tick(raw) - tick(shot["start"])
            length = min(tick(model.MOVE_SECONDS), end)
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
    library = json.loads(EFFECTS.read_text(encoding="utf-8"))
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
    unified["video"]["effects"] = inset_effects(
        unified["video"].get("effects", []), inset, library
    )
    unified["audio"]["effects"] = noise_effects(
        unified["audio"].get("effects", []),
        float(plan.get("noise_removal", 0.8)),
        library,
    )

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
            "effects": [
                e
                for e in unified["video"]["effects"]
                if e.get("effectName") not in OWNED_VIDEO_EFFECTS
            ],
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


def clone(source: Path, target: Path) -> None:
    """Copy the recording into the bundle, as an APFS clone where one is possible.

    A clone costs no space but only works within one APFS volume; anywhere else
    this falls back to an ordinary copy rather than failing.
    """
    if sys.platform == "darwin":
        cloned = subprocess.run(
            ["cp", "-c", str(source), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if cloned.returncode == 0:
            return
        if target.exists():
            target.unlink()
    shutil.copy2(source, target)


def bundle_differences(
    out: Path, project: dict[str, Any], plan: dict[str, Any], recording: Path
) -> list[str]:
    """What in an existing bundle differs from what this run would write.

    Every member is compared by content; a member that cannot be read counts as
    different, so a damaged bundle is reported rather than crashing the check.
    """
    expected: dict[str, Callable[[Path], bool]] = {
        model.PROJECT_FILE: lambda f: (
            f.read_text(encoding="utf-8") == serialize(project)
        ),
        "shot-plan.json": lambda f: json.loads(f.read_text(encoding="utf-8")) == plan,
        f"media/{recording.name}": lambda f: (
            model.file_digest(f) == model.file_digest(recording)
        ),
    }
    for name, data in model.companion_bytes().items():
        expected[name] = lambda f, data=data: f.read_bytes() == data
    differences = []
    for name, matches in expected.items():
        member = out / name
        try:
            same = member.is_file() and matches(member)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            same = False
        if not same:
            differences.append(name)
    return differences


def serialize(project: dict[str, Any]) -> str:
    return json.dumps(project, indent=2, ensure_ascii=False)


def write_bundle(
    out: Path, project: dict[str, Any], plan: dict[str, Any], recording: Path
) -> None:
    """Stage the complete bundle beside `out`, then rename it into place."""
    staging = out.with_name(f".{out.name}.staging")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        model.write_companions(staging)
        clone(recording, staging / "media" / recording.name)
        (staging / model.PROJECT_FILE).write_text(serialize(project), encoding="utf-8")
        (staging / "shot-plan.json").write_text(
            json.dumps(plan, indent=1), encoding="utf-8"
        )
        staging.rename(out)
    except OSError:
        if staging.exists():
            shutil.rmtree(staging)
        raise


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
    try:
        template_path = model.project_file(args.template)
        template = model.load_project(template_path)
        plan = model.load_plan(args.plan)
        project = build(template, plan)
        recording = Path(project["sourceBin"][0]["src"])
        if not recording.is_absolute():
            recording = template_path.parent / recording
        if not recording.is_file():
            raise ValueError(
                f"recording {recording} is missing — Camtasia's temporary folder is not an archive"
            )
    except ValueError as e:
        print(f"build-project: {e}", file=sys.stderr)
        return 1
    project["sourceBin"][0]["src"] = f"./media/{recording.name}"
    summary = {
        "project": str(args.out),
        "screen_shots": sum(s["kind"] == "screen" for s in plan["shots"]),
        "speaker_shots": sum(s["kind"] == "speaker" for s in plan["shots"]),
    }
    if args.out.exists():
        differences = bundle_differences(args.out, project, plan, recording)
        if not differences:
            print(json.dumps({**summary, "unchanged": True}))
            return 0
        print(
            f"build-project: {args.out} already exists and differs in {', '.join(differences)}; "
            "choose a new --out",
            file=sys.stderr,
        )
        return 2
    try:
        write_bundle(args.out, project, plan, recording)
    except OSError as e:
        print(
            f"build-project: could not write {args.out}: {e}; nothing was left behind",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())

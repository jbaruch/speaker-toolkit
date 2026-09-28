#!/usr/bin/env python3
"""Replace Camtasia's dynamic-caption words with corrected text, and restyle them.

Camtasia recognizes speech once and stores one keyframe per word on the source
audio track; the dynamic-caption callout renders from it. Its onsets are good
and its words are not. This keeps the onsets and replaces the words with a
corrected transcript: names fixed, punctuation added (a caption block starts
at each sentence), false starts dropped, grammar corrected.

Usage:
    apply-captions.py <project.cmproj> <captions.txt> [--override WORD=SECONDS ...]
        [--width 700] [--height 170] [--font-size 64] [--x 0] [--y -430]

The project must be saved and CLOSED in Camtasia. The previous project file is
kept as before-captions-<UTC>.tscproj inside the bundle. Exit 0 on success, 1
when the project has no transcript or no dynamic-caption callout, 2 on usage
error.
"""

from __future__ import annotations

import argparse
import bisect
import difflib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camtasia_model as model  # noqa: E402

GAP = "%GAP"


def align(heard: list[tuple[int, str]], text: list[str]) -> tuple[list[int], int]:
    """Onset ticks for each corrected word; returns (times, matched_count).

    Equal-length runs take Camtasia's onsets one to one. A false start that
    collapses into fewer words takes the onsets of the LAST words spoken. More
    words than were heard spread across the heard span. Anything left over is
    interpolated between its matched neighbours.
    """
    a = [model.normalize(w) for _, w in heard]
    b = [model.normalize(w) for w in text]
    times: list[int | None] = [None] * len(text)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        if tag in ("equal", "replace") and i2 - i1 == j2 - j1:
            for d in range(j2 - j1):
                times[j1 + d] = heard[i1 + d][0]
        elif tag == "replace" and j2 - j1 < i2 - i1:
            for d in range(j2 - j1):
                times[j1 + d] = heard[i2 - (j2 - j1) + d][0]
        elif tag == "replace":
            start = heard[i1][0]
            stop = heard[i2][0] if i2 < len(heard) else heard[i2 - 1][0]
            for d in range(j2 - j1):
                times[j1 + d] = start + (stop - start) * d // (j2 - j1)
    matched = sum(t is not None for t in times)
    known = [i for i, t in enumerate(times) if t is not None]
    if not known:
        raise ValueError(
            "the corrected text shares no words with Camtasia's transcript"
        )
    filled: list[int] = []
    for i, t in enumerate(times):
        if t is None:
            k = bisect.bisect(known, i)
            lo = known[k - 1] if k else known[0]
            hi = known[k] if k < len(known) else lo
            lo_t, hi_t = times[lo], times[hi]
            assert lo_t is not None and hi_t is not None
            t = lo_t if hi == lo else lo_t + (hi_t - lo_t) * (i - lo) // (hi - lo)
        filled.append(t)
    return filled, matched


def rebuild(
    keyframes: list[dict[str, Any]], text: list[str], overrides: dict[str, int]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    heard = [(k["time"], k["value"]) for k in keyframes if k["value"] != GAP]
    gaps = [k["time"] for k in keyframes if k["value"] == GAP and k["time"] > 0]
    times, matched = align(heard, text)
    for i, w in enumerate(text):
        if model.normalize(w) in overrides:
            times[i] = overrides[model.normalize(w)]
    for a, b in zip(times, times[1:]):
        if a > b:
            raise ValueError("word times go backwards — check the --override values")
    # A pause ends a caption block only at a sentence end; mid-sentence
    # hesitations would blank the caption halfway through a line.
    kept = []
    for g in gaps:
        before = bisect.bisect_right(times, g) - 1
        if before >= 0 and model.SENTENCE_END.search(text[before]):
            kept.append((g, before))
    events = sorted(
        [(t, i, 1, w) for i, (t, w) in enumerate(zip(times, text))]
        + [(g, i, 2, GAP) for g, i in kept]
    )
    out = [{"endTime": 0, "time": 0, "value": GAP, "duration": 0}]
    out += [
        {"endTime": t, "time": t, "value": v, "duration": 0} for t, _, _, v in events
    ]
    if out[-1]["value"] != GAP:
        last = out[-1]["time"] + 1
        out.append({"endTime": last, "time": last, "value": GAP, "duration": 0})
    return out, {
        "words": len(text),
        "matched": matched,
        "interpolated": len(text) - matched,
        "pauses": len(kept),
    }


def caption_callout(project: dict[str, Any]) -> dict[str, Any]:
    for track in model.tracks(project):
        for m in track["medias"]:
            if (
                m.get("_type") == "Callout"
                and m.get("def", {}).get("modifier") == "dynamicCaption"
            ):
                return m
    raise ValueError(
        "no dynamic-caption callout — add dynamic captions in Camtasia, save, and close"
    )


def restyle(
    callout: dict[str, Any],
    width: float,
    height: float,
    font_size: float,
    x: float,
    y: float,
) -> None:
    d = callout["def"]
    d["width"], d["height"] = width, height
    d["font"]["size"] = font_size
    for keyframe in d.get("textAttributes", {}).get("keyframes", []):
        for attribute in keyframe["value"]:
            if attribute["name"] == "fontSize":
                attribute["value"] = font_size
    callout["parameters"]["translation0"] = x
    callout["parameters"]["translation1"] = y


def parse_overrides(values: list[str], rate: int) -> dict[str, int]:
    out = {}
    for v in values:
        word, sep, seconds = v.partition("=")
        if not sep:
            raise ValueError(f"--override needs WORD=SECONDS, got {v!r}")
        out[model.normalize(word)] = round(float(seconds) * rate)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("captions", type=Path, help="corrected transcript, plain text")
    parser.add_argument(
        "--override", action="append", default=[], help="WORD=SECONDS measured onset"
    )
    parser.add_argument("--width", type=float, default=700.0)
    parser.add_argument("--height", type=float, default=170.0)
    parser.add_argument("--font-size", type=float, default=64.0)
    parser.add_argument("--x", type=float, default=0.0)
    parser.add_argument("--y", type=float, default=-430.0)
    args = parser.parse_args(argv)
    try:
        path = model.project_file(args.project)
        project = model.load_project(path)
        track = model.audio_source_track(project)
        keyframes = (
            track.get("parameters", {}).get("transcription", {}).get("keyframes")
        )
        if not keyframes:
            raise ValueError(
                "no Camtasia transcript — add dynamic captions in Camtasia, save, and close"
            )
        callout = caption_callout(project)
        text = args.captions.read_text(encoding="utf-8").split()
        overrides = parse_overrides(args.override, project["editRate"])
        new_keyframes, stats = rebuild(keyframes, text, overrides)
    except (ValueError, OSError) as e:
        print(f"apply-captions: {e}", file=sys.stderr)
        return 1
    track["parameters"]["transcription"]["keyframes"] = new_keyframes
    restyle(callout, args.width, args.height, args.font_size, args.x, args.y)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.parent / f"before-captions-{stamp}.tscproj"
    shutil.copy2(path, backup)
    path.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({**stats, "backup": str(backup)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

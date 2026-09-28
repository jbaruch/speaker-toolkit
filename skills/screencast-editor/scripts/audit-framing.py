#!/usr/bin/env python3
"""Check that the pointer stays inside the framed view of every screen shot.

A zoom that moves the row the presenter is pointing at out of frame looks fine
in every still, because the pointer is not in the screen pixels. This replays
the recorded pointer path against the shot plan's framing.

Usage:
    audit-framing.py <shot-plan.json> <pointer.json> [--step 0.25]

A sample outside the view is `pointing` when the pointer has come to rest there
after moving during this shot: the presenter put it on something the framing
cuts off. A pointer still where an earlier shot left it is `resting`, and one
travelling into frame is neither; neither is a framing error. Stdout: JSON per screen shot. Exit 0 when no shot has a
`pointing` miss, 1 when one does, 2 on usage error.
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camtasia_model as model  # noqa: E402

TRANSITION = 0.8  # seconds a framing move takes; samples inside it are skipped


def audit(plan: dict, samples: list[list[float]], step: float = 0.25) -> list[dict]:
    canvas = model.plan_canvas(plan)
    times = [s[0] for s in samples]

    def pointer_at(t: float) -> tuple[float, float]:
        i = max(0, bisect.bisect_right(times, t) - 1)
        return samples[i][1], samples[i][2]

    def moved_between(a: float, b: float) -> bool:
        lo = max(0, bisect.bisect_right(times, a) - 1)
        hi = bisect.bisect_right(times, b)
        return len({(s[1], s[2]) for s in samples[lo:hi]}) > 1

    report = []
    for shot in plan["shots"]:
        if shot["kind"] != "screen":
            continue
        cues = shot["cues"]
        misses = []
        t = shot["start"]
        while t < shot["end"]:
            if any(0 < c[0] - t < TRANSITION for c in cues[1:]):
                t += step
                continue
            cue = [c for c in cues if c[0] <= t][-1]
            x0, y0, x1, y1 = model.visible_rect(cue[1], cue[2], cue[3], canvas)
            px, py = pointer_at(t)
            if not (x0 <= px <= x1 and y0 <= py <= y1):
                if moved_between(t - step, t):
                    kind = "travelling"
                elif moved_between(shot["start"], t):
                    kind = "pointing"
                else:
                    kind = "resting"
                misses.append({"t": round(t, 2), "pointer": [px, py], "kind": kind})
            t += step
        report.append(
            {
                "label": shot.get("label", ""),
                "start": shot["start"],
                "pointing": [m for m in misses if m["kind"] == "pointing"],
                "resting_samples": sum(m["kind"] == "resting" for m in misses),
            }
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("plan", type=Path)
    parser.add_argument("pointer", type=Path)
    parser.add_argument("--step", type=float, default=0.25)
    args = parser.parse_args(argv)
    try:
        plan = model.load_plan(args.plan)
        samples = json.loads(args.pointer.read_text(encoding="utf-8"))["samples"]
    except (ValueError, OSError, KeyError) as e:
        print(f"audit-framing: {e}", file=sys.stderr)
        return 2
    report = audit(plan, samples, args.step)
    print(json.dumps(report, indent=1))
    failed = [r for r in report if r["pointing"]]
    for r in failed:
        first = r["pointing"][0]
        print(
            f"audit-framing: '{r['label']}' frames out the pointer at {first['t']}s "
            f"(pointer at {first['pointer']}); hold a framing that contains it",
            file=sys.stderr,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

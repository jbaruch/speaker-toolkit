#!/usr/bin/env python3
"""Turn chapter phrases into YouTube chapter lines timed from the captions.

Each chapter names the phrase it starts on; the time is that phrase's first
caption word after the previous chapter, minus the edit's head trim. YouTube
requires the first chapter at 0:00 and every chapter to last 10 seconds.

Usage:
    chapters.py <project.cmproj> <chapters.json> [--trim-start SECONDS]

chapters.json: [{"title": "...", "phrase": "words it starts on" | null}, ...]
A null phrase means 0:00. The head trim defaults to the first shot of the
bundle's shot-plan.json. Stdout: {"chapters": [{"seconds", "clock", "title"}],
"lines": "<the description block>"}. YouTube needs at least three chapters.
Exit 0 when valid, 1 when a phrase is missing, a chapter is too short, or there
are fewer than three, 2 on usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The sibling module resolves only after the sys.path insert above.
import camtasia_model as model  # noqa: E402

MIN_CHAPTER = 10.0
MIN_CHAPTERS = 3


def clock(seconds: float) -> str:
    whole = int(seconds)
    return (
        f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"
        if whole >= 3600
        else f"{whole // 60}:{whole % 60:02d}"
    )


def place(
    words: list[tuple[float, str]], chapters: list[dict], trim: float, end: float
) -> list[tuple[float, str]]:
    if not chapters or chapters[0].get("phrase") is not None:
        raise ValueError("the first chapter must start at 0:00 (give it a null phrase)")
    norm = [model.normalize(w) for _, w in words]
    out: list[tuple[float, str]] = []
    cursor = 0
    for c in chapters:
        if c.get("phrase") is None:
            out.append((0.0, c["title"]))
            continue
        target = [model.normalize(w) for w in c["phrase"].split()]
        for i in range(cursor, len(norm) - len(target) + 1):
            if norm[i : i + len(target)] == target:
                out.append((max(0.0, words[i][0] - trim), c["title"]))
                cursor = i + len(target)
                break
        else:
            raise ValueError(
                f"phrase not found after the previous chapter: {c['phrase']!r}"
            )
    if not out or out[0][0] != 0.0:
        raise ValueError("the first chapter must start at 0:00 (give it a null phrase)")
    if len(out) < MIN_CHAPTERS:
        raise ValueError(
            f"YouTube needs at least {MIN_CHAPTERS} chapters, got {len(out)}"
        )
    starts = [t for t, _ in out] + [end]
    short = [title for (t, title), nxt in zip(out, starts[1:]) if nxt - t < MIN_CHAPTER]
    if short:
        raise ValueError(
            f"chapters shorter than {MIN_CHAPTER:.0f}s: {short} — merge them"
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("chapters", type=Path)
    parser.add_argument("--trim-start", type=float)
    args = parser.parse_args(argv)
    try:
        path = model.project_file(args.project)
        words = model.transcript_words(model.load_project(path))
        chapters = json.loads(args.chapters.read_text(encoding="utf-8"))
        trim, end = args.trim_start, None
        plan_path = path.parent / "shot-plan.json"
        if plan_path.is_file():
            shots = model.load_plan(plan_path)["shots"]
            trim = shots[0]["start"] if trim is None else trim
            end = shots[-1]["end"] - trim
        if trim is None:
            raise ValueError("no shot-plan.json in the bundle — pass --trim-start")
        placed = place(
            words, chapters, trim, end if end is not None else words[-1][0] - trim
        )
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f"chapters: {e}", file=sys.stderr)
        return 1
    rows = [
        {"seconds": round(t, 2), "clock": clock(t), "title": title}
        for t, title in placed
    ]
    lines = "\n".join(f"{r['clock']} {r['title']}" for r in rows)
    print(json.dumps({"chapters": rows, "lines": lines}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

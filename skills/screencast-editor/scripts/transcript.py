#!/usr/bin/env python3
"""Export Camtasia's word-level transcript of a take, for planning cuts.

Camtasia recognizes speech when dynamic captions are added, and stores one
keyframe per word on the source audio track. Its word onsets were measured more
accurate than Whisper's, so shot boundaries are planned from these.

Usage:
    transcript.py <project.cmproj | project.tscproj>

Stdout: {"words": [[seconds, word], ...], "sentences": [{"start", "end", "text"}]}
Times are source seconds. Exit 0 on success, 1 when the project has no
transcript, 2 on usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camtasia_model as model  # noqa: E402


def sentences(words: list[tuple[float, str]]) -> list[dict]:
    """Group words into sentences; `end` is the onset of the next sentence.

    The last sentence has no `end`: nothing after it marks where its final word
    stops, and inventing one would cut that word off.
    """
    out: list[dict] = []
    current: list[tuple[float, str]] = []
    for t, w in words:
        current.append((t, w))
        if model.SENTENCE_END.search(w):
            out.append(
                {"start": current[0][0], "text": " ".join(x for _, x in current)}
            )
            current = []
    if current:
        out.append({"start": current[0][0], "text": " ".join(x for _, x in current)})
    for a, b in zip(out, out[1:]):
        a["end"] = b["start"]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("project", type=Path)
    args = parser.parse_args(argv)
    try:
        project = model.load_project(model.project_file(args.project))
        words = model.transcript_words(project)
    except ValueError as e:
        print(f"transcript: {e}", file=sys.stderr)
        return 1
    json.dump(
        {"words": [[round(t, 3), w] for t, w in words], "sentences": sentences(words)},
        sys.stdout,
        indent=1,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

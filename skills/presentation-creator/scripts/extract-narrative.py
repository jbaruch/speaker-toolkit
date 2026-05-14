#!/usr/bin/env python3
"""extract-narrative.py — render outline.yaml as narrative.md.

A prose distillation of the talk's argument, organized by chapter. Drops
production directives (image prompts, builds, format), drops the script
(speaker dialogue lives in script.md), drops structural ledgers (those
surface in rhetorical-review.md). Each chapter's argument_beats are
joined as paragraphs; slide references appearing naturally in beat text
are preserved as written.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import yaml  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import outline_schema as _os  # noqa: E402


def render(outline: _os.Outline) -> str:
    lines: list[str] = []

    lines.append(f"# {outline.talk.title} — Narrative Read")
    lines.append("")
    speakers_csv = " · ".join(outline.talk.speakers)
    lines.append(
        f"**{outline.talk.venue}** · {outline.talk.duration_min:g} min "
        f"· {speakers_csv}",
    )
    lines.append("")
    lines.append(
        "> A prose distillation of the outline. No image prompts, no "
        "stage directions, no per-slide layout. Read top-to-bottom; the "
        "argument is preserved, the production noise is stripped.",
    )
    lines.append("")

    if outline.talk.thesis:
        lines.append("## Thesis")
        lines.append("")
        for para in outline.talk.thesis.strip().split("\n\n"):
            lines.append(para.strip())
            lines.append("")

    chapter_total = sum(c.target_min for c in outline.chapters)
    lines.append("## Part 1 — The Talk as a Narrative")
    lines.append("")
    lines.append(
        f"*Chapter time targets sum to {chapter_total:g} min "
        f"(talk slot: {outline.talk.duration_min:g} min).*",
    )
    lines.append("")

    for chapter in outline.chapters:
        header = f"### {chapter.title} (~{chapter.target_min:g} min)"
        if chapter.cuttable:
            header += " — *cuttable*"
        lines.append(header)
        lines.append("")

        if not chapter.argument_beats:
            lines.append("*(no argument beats declared)*")
            lines.append("")
            continue

        for beat in chapter.argument_beats:
            text = beat.text.strip()
            if beat.slide_refs:
                refs = ", ".join(f"slide {n}" for n in beat.slide_refs)
                lines.append(f"{text}  ")
                lines.append(f"*[{refs}]*")
            else:
                lines.append(text)
            lines.append("")

    # Collapse blank runs, ensure single trailing newline
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()
    cleaned.append("")
    return "\n".join(cleaned)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: extract-narrative.py <outline.yaml>\n"
            "       prints narrative.md to stdout",
            file=sys.stderr,
        )
        return 2
    try:
        outline = _os.load_outline(argv[1])
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"failed to load {argv[1]}: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(render(outline))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

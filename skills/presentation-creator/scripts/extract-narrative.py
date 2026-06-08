#!/usr/bin/env python3
"""extract-narrative.py — render outline.yaml as narrative.md.

narrative.md is the reader's walk of the deck: a TL;DR of the idea, then a
one-line-per-slide breakdown of what's on each slide. It drops production
directives (image prompts, builds, format), the script (speaker dialogue
lives in script.md), and structural ledgers (those surface in
rhetorical-review.md).

The TL;DR renders `talk.tldr` verbatim — a short distillation of the
elaborated `talk.thesis`. The full thesis is never reprinted here.

Two shapes, chosen by whether any slide is authored yet:
  • full  (slides present)  — TL;DR + per-slide walk, grouped by chapter,
                              with interludes inlined at their anchor.
  • partial (no slides yet) — TL;DR + the Phase 2 narrative scaffold
                              (chapters + argument_beats), so the author can
                              review the arc before slides exist.
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


def render(outline: "_os.Outline | _os.PartialOutline") -> str:
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
        "> The idea up top, then one line per slide — a quick walk of the "
        "deck. No image prompts, no stage directions, no script; those live "
        "in slides.md and script.md.",
    )
    lines.append("")

    if outline.talk.tldr:
        lines.append("## TL;DR")
        lines.append("")
        lines.append(outline.talk.tldr.strip())
        lines.append("")

    if outline.slides:
        _render_slide_walk(outline, lines)
    else:
        _render_narrative_scaffold(outline, lines)

    return _finalize(lines)


def _slide_synopsis(slide: "_os.Slide") -> str:
    """One-line gist of what's on the slide.

    Prefers the on-screen `text_overlay`, falls back to `visual`. Collapses to
    the first line and ignores the literal `none` placeholder authors use when
    a slide carries no overlay.
    """
    for source in (slide.text_overlay, slide.visual):
        if not source:
            continue
        first = source.strip().splitlines()[0].strip()
        if first and first.lower() != "none":
            return first
    return ""


def _render_slide_walk(
    outline: "_os.Outline | _os.PartialOutline", lines: list[str],
) -> None:
    """Full view: one line per slide, grouped by chapter, interludes inlined."""
    lines.append("## The Deck, Slide by Slide")
    lines.append("")

    chapters_by_id = {c.id: c for c in outline.chapters}

    # Unified timeline: slides sort by number, interludes sort immediately
    # after the slide they follow (after_slide).
    timeline: list[tuple[tuple[int, int], str, object]] = []
    for s in outline.slides:
        timeline.append(((s.n, 0), "slide", s))
    for il in outline.interludes:
        timeline.append(((il.after_slide, 1), "interlude", il))
    timeline.sort(key=lambda entry: entry[0])

    current_chapter: str | None = None
    for _, kind, obj in timeline:
        chapter_id = obj.chapter  # type: ignore[attr-defined]
        if chapter_id != current_chapter:
            current_chapter = chapter_id
            chapter = chapters_by_id.get(chapter_id)
            if chapter is not None:
                if lines and lines[-1].strip() != "":
                    lines.append("")
                header = f"### {chapter.title} (~{chapter.target_min:g} min)"
                if chapter.cuttable:
                    header += " — *cuttable*"
                lines.append(header)
                lines.append("")

        if kind == "slide":
            synopsis = _slide_synopsis(obj)  # type: ignore[arg-type]
            entry = f"- **{obj.n}. {obj.title}**"  # type: ignore[attr-defined]
            if synopsis:
                entry += f" — {synopsis}"
            lines.append(entry)
        else:
            lines.append(f"- *{obj.title} — live demo*")  # type: ignore[attr-defined]

    lines.append("")


def _render_narrative_scaffold(
    outline: "_os.Outline | _os.PartialOutline", lines: list[str],
) -> None:
    """Partial view (no slides yet): the Phase 2 chapter + argument-beat arc."""
    lines.append("## The Talk as a Narrative")
    lines.append("")
    if not outline.chapters:
        lines.append(
            "*Narrative arc not yet authored — chapters and argument beats "
            "appear after Phase 2 (Rhetorical Architecture).*",
        )
        lines.append("")
        return

    chapter_total = sum(c.target_min for c in outline.chapters)
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
            lines.append(beat.text.strip())
            lines.append("")


def _finalize(lines: list[str]) -> str:
    """Collapse blank runs, ensure a single trailing newline."""
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
    args = argv[1:]
    partial = "--partial" in args
    args = [a for a in args if a != "--partial"]
    if len(args) != 1:
        print(
            "usage: extract-narrative.py [--partial] <outline.yaml>\n"
            "       prints narrative.md to stdout\n"
            "       --partial: render the Phase 1–2 narrative scaffold "
            "(talk + chapters, before slides are authored)",
            file=sys.stderr,
        )
        return 2
    loader = _os.load_outline_partial if partial else _os.load_outline
    try:
        outline = loader(args[0])
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"failed to load {args[0]}: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(render(outline))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

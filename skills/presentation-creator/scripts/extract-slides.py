"""extract-slides.py — render outline.yaml as a build-ready slides.md.

Walks slides[] only — interludes are not part of the deck build (the
speaker switches to the live terminal for those; nothing to render).
Emits the format, visual concept, on-screen text, image prompt, builds,
placeholders, and structural ledger entries for each slide. Skips
speaker dialogue (lives in script.md) and chapter narrative (lives in
narrative.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import outline_schema as _os  # noqa: E402


def _format_applied_pattern(p: _os.AppliedPattern) -> str:
    """Compact one-line summary of a pattern application + instance data."""
    parts = [p.id]
    if p.flavors:
        parts.append(f"flavors={[f.value for f in p.flavors]}")
    if p.subtype:
        parts.append(f"subtype={p.subtype.value}")
    if p.resistance_vector:
        parts.append(f"resistance={p.resistance_vector.value}")
    if p.story_id:
        parts.append(f"story={p.story_id}")
    if p.beat:
        parts.append(f"beat={p.beat.value}")
    if p.plant_id:
        parts.append(f"plant={p.plant_id}")
    if p.big_idea_text:
        parts.append(f"big_idea={p.big_idea_text!r}")
    if p.asks:
        parts.append(f"asks={ {k.value: v for k, v in p.asks.items()} }")
    return " · ".join(parts)


def _format_callback(cb: _os.Callback) -> str:
    suffix = f" — {cb.variation}" if cb.variation else ""
    return f"{cb.kind}: {cb.id}{suffix}"


def render(outline: _os.Outline) -> str:
    lines: list[str] = []
    lines.append(f"# {outline.talk.title} — Slides")
    lines.append("")
    expanded_count = sum(max(len(s.builds), 1) for s in outline.slides)
    lines.append(
        f"**{outline.talk.venue}** · slide budget {outline.talk.slide_budget} "
        f"· entries {len(outline.slides)} "
        f"· deck count (builds expanded) {expanded_count}",
    )
    lines.append("")

    if outline.style_anchor:
        lines.append("## Illustration Style Anchor")
        lines.append("")
        lines.append(f"**Model:** `{outline.style_anchor.model}`")
        lines.append("")
        lines.append("### FULL (1920×1080)")
        lines.append("")
        lines.append("> " + outline.style_anchor.full.strip().replace("\n", "\n> "))
        lines.append("")
        lines.append("### IMG+TXT (1024×1536)")
        lines.append("")
        lines.append("> " + outline.style_anchor.imgtxt.strip().replace("\n", "\n> "))
        lines.append("")
        lines.append("### Conventions")
        lines.append("")
        lines.append(outline.style_anchor.conventions.strip())
        lines.append("")

    for slide in outline.slides:
        lines.append("---")
        lines.append("")
        header = f"## Slide {slide.n} — {slide.title}"
        if slide.format:
            header += f" *[{slide.format.value}]*"
        lines.append(header)
        if slide.cuttable:
            lines.append("")
            lines.append("> *Cuttable for short slot.*")
        lines.append("")

        if slide.big_idea:
            lines.append("**🎯 Big Idea slide** — single-sentence thesis declaration.")
            lines.append("")
        if slide.thesis:
            lines.append(f"**Thesis:** {slide.thesis}")
            lines.append("")

        if slide.format == _os.SlideFormat.exception and slide.format_justification:
            lines.append(f"**EXCEPTION justification:** {slide.format_justification}")
            lines.append("")

        if slide.visual:
            lines.append(f"- **Visual:** {slide.visual}")
        if slide.text_overlay:
            ovl = slide.text_overlay.strip()
            if ovl.lower() == "none":
                lines.append("- **Text overlay:** *(none — image-only)*")
            else:
                lines.append("- **Text overlay:**")
                for line in ovl.splitlines():
                    lines.append(f"  - `{line}`")
        if slide.image_prompt:
            lines.append("- **Image prompt:**")
            lines.append("")
            lines.append("  ```")
            for line in slide.image_prompt.strip().splitlines():
                lines.append(f"  {line}")
            lines.append("  ```")

        if slide.builds:
            lines.append("")
            lines.append(f"- **Builds:** {len(slide.builds)} steps")
            for b in slide.builds:
                lines.append(f"  - `build-{b.step:02d}`: {b.desc}")

        if slide.placeholders:
            lines.append("")
            lines.append("- **Placeholders:** " + ", ".join(
                f"`{p}`" for p in slide.placeholders
            ))

        if slide.applied_patterns:
            lines.append("")
            lines.append("- **Patterns:**")
            for p in slide.applied_patterns:
                lines.append(f"  - {_format_applied_pattern(p)}")

        if slide.callbacks:
            lines.append("")
            lines.append("- **Callbacks:**")
            for cb in slide.callbacks:
                lines.append(f"  - {_format_callback(cb)}")

        if slide.progressive_lists:
            lines.append("")
            lines.append("- **Progressive lists:**")
            for pl in slide.progressive_lists:
                lines.append(f"  - `{pl.id}` item #{pl.item_index}")

        if slide.running_gags:
            lines.append("")
            lines.append("- **Running gags:**")
            for rg in slide.running_gags:
                lines.append(f"  - `{rg.id}` appearance #{rg.appearance_index}")

        lines.append("")

    # Collapse runs of blank lines to at most one, ensure single trailing newline
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
            "usage: extract-slides.py <outline.yaml>\n"
            "       prints slides.md to stdout",
            file=sys.stderr,
        )
        return 2
    try:
        outline = _os.load_outline(argv[1])
    except Exception as exc:
        print(f"failed to load {argv[1]}: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(render(outline))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

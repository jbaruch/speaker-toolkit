"""extract-script.py — render outline.yaml as a screenplay-form script.md.

Walks slides[] and interleaves interludes by their `after_slide` anchor.
Emits Markdown with speaker-grouped dialogue blocks. Drops image prompts,
visual descriptions, applied_patterns, and structural ledgers — none of
that goes on stage.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sibling outline_schema importable when run as a script
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import outline_schema as _os  # noqa: E402


def _strip_parens(s: str) -> str:
    """Drop wrapping parentheses if present so we can re-add them uniformly."""
    s = s.strip()
    if s.startswith("(") and s.endswith(")"):
        return s[1:-1].strip()
    return s


def _render_script_items(items: list[_os.ScriptItem]) -> list[str]:
    """Render a list of ScriptItem into screenplay-form Markdown lines.

    Consecutive items with the same `speaker` group under one bolded
    speaker header. Cues stand alone in bold brackets. Floating
    parentheticals (no speaker) stand alone in italics.
    """
    out: list[str] = []
    current_speaker: str | None = None

    def _break_block() -> None:
        nonlocal current_speaker
        if current_speaker is not None:
            out.append("")
            current_speaker = None

    for item in items:
        if item.cue is not None:
            _break_block()
            out.append(f"**[{item.cue}]**")
            out.append("")
            continue

        if item.parenthetical is not None:
            inner = _strip_parens(item.parenthetical)
            if item.speaker is None:
                _break_block()
                out.append(f"*({inner})*")
                out.append("")
            else:
                if item.speaker != current_speaker:
                    _break_block()
                    out.append(f"**{item.speaker.upper()}**")
                    current_speaker = item.speaker
                out.append(f"*({inner})*")
                out.append("")
            continue

        if item.line is not None:
            if item.speaker is None:
                # Single-speaker mode: lines are unattributed, no header
                _break_block()
                out.append(item.line)
                out.append("")
            else:
                if item.speaker != current_speaker:
                    _break_block()
                    out.append(f"**{item.speaker.upper()}**")
                    current_speaker = item.speaker
                out.append(item.line)
                out.append("")

    _break_block()
    return out


def _ordered_events(outline: _os.Outline) -> list[tuple[str, object]]:
    """Return slides and interludes in presentation order.

    Interludes anchored `after_slide: N` appear immediately after slide N.
    If multiple interludes share an anchor, they keep their declaration
    order in the YAML.
    """
    by_anchor: dict[int, list[_os.Interlude]] = {}
    for il in outline.interludes:
        by_anchor.setdefault(il.after_slide, []).append(il)

    events: list[tuple[str, object]] = []
    for slide in outline.slides:
        events.append(("slide", slide))
        for il in by_anchor.get(slide.n, []):
            events.append(("interlude", il))
    return events


def render(outline: _os.Outline) -> str:
    """Render the full script.md content."""
    lines: list[str] = []
    speakers_csv = " · ".join(outline.talk.speakers)
    lines.append(f"# {outline.talk.title} — Script")
    lines.append("")
    lines.append(
        f"**{outline.talk.venue}** · {outline.talk.duration_min:g} min "
        f"· {speakers_csv} · pacing {outline.talk.pacing_wpm[0]}–"
        f"{outline.talk.pacing_wpm[1]} WPM",
    )
    lines.append("")
    lines.append("> Read top to bottom. Bold-bracketed lines are production "
                 "cues. Italic parentheticals are delivery notes — pause, "
                 "tone, audience interaction. Bolded ALL-CAPS names are "
                 "speaker headers; consecutive items under one header are "
                 "the same speaker.")
    lines.append("")

    for kind, ev in _ordered_events(outline):
        lines.append("---")
        lines.append("")
        if kind == "slide":
            slide: _os.Slide = ev  # type: ignore[assignment]
            lines.append(f"## Slide {slide.n} — {slide.title}")
            if slide.cuttable:
                lines.append("")
                lines.append("> *Cuttable for short slot.*")
            lines.append("")
            if slide.text_overlay and slide.text_overlay.strip().lower() != "none":
                lines.append("*On screen:*")
                lines.append("")
                for ovl in slide.text_overlay.strip().splitlines():
                    lines.append(f"> {ovl}")
                lines.append("")
        else:
            il: _os.Interlude = ev  # type: ignore[assignment]
            lines.append(f"## {il.title}")
            if il.cuttable:
                lines.append("")
                lines.append("> *Cuttable for short slot.*")
            lines.append("")

        script = ev.script if hasattr(ev, "script") else []
        lines.extend(_render_script_items(script))

    # Collapse runs of blank lines to at most one
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank
    # Ensure single trailing newline
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()
    cleaned.append("")
    return "\n".join(cleaned)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: extract-script.py <outline.yaml>\n"
            "       prints script.md to stdout",
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

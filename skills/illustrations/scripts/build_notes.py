"""Split a build parent's speaker notes across its frames; re-key notes for the expanded deck.

A progressive-reveal parent slide becomes one deck slide per build frame when
ExpandBuilds runs. Each frame must carry the words spoken while it is on screen,
so the parent's note is split at its cue lines.

The cue marker is canonical. Each outline.yaml script item is one notes line,
and a `cue: "BUILD 01"` item becomes the line `[BUILD 01]`: the cue text in
square brackets, the step zero-padded to two digits as in `slide-NN-build-MM`.

- Text before the first cue goes on frame 00, the first frame shown.
- Text after `[BUILD NN]` goes on frame NN, up to the next cue.
- The cue lines themselves are dropped; the frame change is the cue.
- Each segment loses its leading and trailing whitespace; inner lines are kept.

Validation (`BuildNotesError`, a ValueError carrying the repair):

- a `[BUILD NN]` past the slide's last frame;
- cues out of increasing order, or repeated;
- a bracketed `[BUILD 1]` that is not zero-padded;
- a note whose cue sequence differs from the outline script's bare
  `cue: "BUILD NN"` items, which catches a notes map rendered without markers.

A build parent whose note has no cue at all, and whose outline script has none,
keeps its whole note on frame 00 with a warning: the speaker starts talking on
the first frame. A bracketed line that names a build step without being a bare
cue (`[SLIDE 2 UP — BUILD 00]`, `**[BUILD 01]**`) stays in the text with a
warning, since it moves nothing.

`expanded_notes_map` re-keys a 0-based notes map onto the deck after
ExpandBuilds: every non-parent slide moves past the extra frames inserted
before it, and each parent's key is replaced by one key per frame carrying that
frame's segment. The result is the input `inject-notes.sh` takes.

This module is imported by `build-expansion-manifest.py`; it has no CLI.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

# The bare outline cue: `cue: "BUILD 01"`.
_OUTLINE_CUE = re.compile(r"BUILD (\d+)")
# A notes line that is exactly one cue marker, once surrounding space is gone.
_MARKER_LINE = re.compile(r"\[BUILD (\d+)\]")
# Any bracketed text naming a build step: a near-miss that moves nothing.
_NEAR_MISS = re.compile(r"\[[^\]]*\bBUILD\s+\d+[^\]]*\]")


class BuildNotesError(ValueError):
    """A build parent's notes cannot be split; the message carries the repair."""


def cue_marker(step: int) -> str:
    """The canonical notes line for build step ``step``: ``[BUILD 01]``."""
    return f"[BUILD {step:02d}]"


def outline_cues(cues: Iterable[str | None]) -> list[int]:
    """Steps named by the bare ``BUILD NN`` cues among a slide's script cues.

    ``cues`` is each script item's ``cue`` value (None for lines and
    parentheticals). A compound cue such as ``SLIDE 2 UP — BUILD 00`` is not a
    frame cue and is skipped.
    """
    steps = []
    for cue in cues:
        if cue is None:
            continue
        match = _OUTLINE_CUE.fullmatch(cue.strip())
        if match is not None:
            steps.append(int(match.group(1)))
    return steps


def _labels(steps: Sequence[int]) -> str:
    return ", ".join(cue_marker(s) for s in steps) if steps else "no cue"


def split_note(
    note: str,
    frame_count: int,
    slide: str,
    script_cues: Sequence[int] | None = None,
) -> tuple[list[str], list[str]]:
    """Return ``(segments, warnings)``: one note per build frame, in frame order.

    ``slide`` names the parent in messages. ``script_cues`` is the outline's
    bare cue steps for the slide (``outline_cues``); when given, the note's cue
    sequence must equal it. Raises BuildNotesError on an invalid cue.
    """
    if frame_count < 1:
        raise BuildNotesError(
            f"slide {slide} has no build frames; declare its `builds` steps in "
            "outline.yaml"
        )
    empty = [""] * frame_count
    if not note.strip():
        return empty, []

    lines: list[list[str]] = [[] for _ in range(frame_count)]
    marks: list[int] = []
    warnings: list[str] = []
    current = 0
    last = frame_count - 1
    for line in note.splitlines(keepends=True):
        stripped = line.strip()
        match = _MARKER_LINE.fullmatch(stripped)
        if match is None:
            if _NEAR_MISS.search(stripped):
                warnings.append(
                    f"WARN: slide {slide}'s note line {stripped!r} names a build "
                    "step but is not a bare cue line, so it stays in the text "
                    f"and moves nothing; write the cue as its own line, e.g. "
                    f"{cue_marker(1)}"
                )
            lines[current].append(line)
            continue
        digits = match.group(1)
        step = int(digits)
        if digits != f"{step:02d}":
            raise BuildNotesError(
                f"slide {slide}'s note cue {stripped!r} is not zero-padded; write "
                f"it as {cue_marker(step)} in notes.json"
            )
        if step > last:
            raise BuildNotesError(
                f"slide {slide}'s note cues {cue_marker(step)}, but the slide has "
                f"{frame_count} build frame(s), {cue_marker(0)} to "
                f"{cue_marker(last)}; renumber the cue in notes.json and the "
                "outline script, or add the build step to outline.yaml"
            )
        if marks and step <= marks[-1]:
            raise BuildNotesError(
                f"slide {slide}'s note cues {cue_marker(step)} after "
                f"{cue_marker(marks[-1])}; cues must name each frame once, in "
                "increasing order. Reorder or renumber the cue lines in "
                "notes.json and the outline script"
            )
        marks.append(step)
        current = step

    if script_cues is not None and list(script_cues) != marks:
        raise BuildNotesError(
            f"slide {slide}'s outline script cues {_labels(script_cues)}, but its "
            f'note marks {_labels(marks)}; render each `cue: "BUILD NN"` script '
            "item as its own [BUILD NN] line in notes.json, or correct the "
            "outline, then re-run"
        )
    if not marks:
        if frame_count > 1:
            warnings.append(
                f"WARN: slide {slide} has {frame_count} build frames but its note "
                f"has no cue line, so the whole note goes on frame 00, the first "
                f"frame shown. To move text onto a later frame, add a "
                f'`cue: "BUILD 01"` script item and a {cue_marker(1)} line '
                "where that frame appears"
            )
        return [note.strip(), *empty[1:]], warnings
    return ["".join(segment).strip() for segment in lines], warnings


def normalize_notes_map(notes_map: object) -> dict[int, str]:
    """A ``{"<0-based slide #>": "text"}`` map as ``{index: text}``.

    A null note becomes "". Raises BuildNotesError on a non-object map, a key
    that is not a plain 0-based slide number, two keys naming one slide
    ("6" and "06"), or a note that is not a string.
    """
    if not isinstance(notes_map, dict):
        raise BuildNotesError(
            'notes JSON must be an object {"<0-based slide #>": "text", ...}'
        )
    out: dict[int, str] = {}
    for key, text in notes_map.items():
        if not (isinstance(key, str) and key.isascii() and key.isdigit()):
            raise BuildNotesError(
                f"notes key {key!r} is not a 0-based slide number; key each note "
                'by its slide index on the built deck, e.g. "0" for the first slide'
            )
        index = int(key)
        if index in out:
            raise BuildNotesError(
                f"notes keys name slide index {index} twice (one is {key!r}); keep "
                "one key per slide in notes.json"
            )
        if text is None:
            text = ""
        if not isinstance(text, str):
            raise BuildNotesError(
                f"note for slide index {index} (notes key {key!r}) must be a "
                f"string, got {type(text).__name__}; write it as a JSON string"
            )
        out[index] = text
    return out


def expanded_notes_map(
    notes: Mapping[int, str], frame_notes: Mapping[int, Sequence[str]]
) -> dict[str, str]:
    """Re-key 0-based notes (``normalize_notes_map``) onto the deck after ExpandBuilds.

    ``frame_notes`` maps each build parent's 1-based position on the
    pre-expansion deck (the manifest's ``parent``) to its per-frame notes. A
    parent's own entry in ``notes`` is replaced by its frames; every other note
    moves past the frames inserted before it. Keys come back as 0-based strings
    in slide order. Raises BuildNotesError on a parent with no frames.
    """
    for position, frames in frame_notes.items():
        if position < 1 or not frames:
            raise BuildNotesError(
                f"build parent {position} needs a positive slide position and at "
                "least one frame; regenerate the manifest"
            )

    def shift(position: int) -> int:
        """Extra slides ExpandBuilds inserts before 1-based ``position``."""
        return sum(len(f) - 1 for p, f in frame_notes.items() if p < position)

    out: dict[int, str] = {}
    for index, text in notes.items():
        if index + 1 not in frame_notes:
            out[index + shift(index + 1)] = text
    for position, frames in frame_notes.items():
        first = position - 1 + shift(position)
        for step, text in enumerate(frames):
            out[first + step] = text
    return {str(index): out[index] for index in sorted(out)}

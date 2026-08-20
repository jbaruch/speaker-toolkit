#!/usr/bin/env python3
"""Deterministic reading of a markdown-authored slide deck.

Four tools author decks as markdown — presenterm, Slidev, Marp, reveal-md —
and each owns its own separator syntax and its own incremental-reveal markers.
This module reads the source text only: which tool wrote the deck, how many
slides the source declares, and where the author asked for a staged reveal. It
renders nothing and shells out to nothing.

The slide count here is a CROSS-CHECK, never the authority. Each renderer owns
its own pagination, so ``render-markdown-deck.py`` takes the authored slide
count from the exported page count and reports this module's count beside it.
A disagreement is surfaced, never reconciled: a wrong number that agrees with
itself is worse than two numbers that visibly do not.

Detection and segmentation both work from closed literal vocabularies declared
at the top of this file. Nothing here infers intent from prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


DECK_STRUCTURE_SCHEMA_VERSION = 1

PRESENTERM = "presenterm"
SLIDEV = "slidev"
MARP = "marp"
REVEAL_MD = "reveal-md"
FLAVORS: tuple[str, ...] = (PRESENTERM, SLIDEV, MARP, REVEAL_MD)

# A definitive marker names exactly one tool and is written by no other: the
# `marp` headmatter directive Marp requires, presenterm's own slide terminator,
# the Slidev CLI in a sibling manifest. One definitive hit decides the flavor.
# A corroborating marker is strong but not exclusive, and only decides when it
# is the sole flavor matched.
_DEFINITIVE_HEADMATTER_KEYS: dict[str, tuple[str, ...]] = {
    MARP: ("marp",),
}
_DEFINITIVE_BODY_MARKERS: dict[str, tuple[str, ...]] = {
    PRESENTERM: ("<!-- end_slide -->",),
}
_CORROBORATING_HEADMATTER_KEYS: dict[str, tuple[str, ...]] = {
    # Slidev headmatter keys no other tool reads.
    SLIDEV: (
        "colorSchema",
        "drawings",
        "exportFilename",
        "highlighter",
        "mdc",
        "routerMode",
        "themeConfig",
    ),
    # presenterm nests every knob under `options:` and its own `theme:` map.
    PRESENTERM: ("options",),
}
_CORROBORATING_BODY_MARKERS: dict[str, tuple[str, ...]] = {
    PRESENTERM: (
        "<!-- pause -->",
        "<!-- column_layout:",
        "<!-- column:",
        "<!-- reset_layout -->",
        "<!-- jump_to_middle -->",
        "<!-- incremental_lists:",
        "<!-- new_lines:",
        "<!-- no_footer -->",
    ),
    SLIDEV: (
        "<v-click",
        "<v-clicks",
        "<v-switch",
        "v-click=",
        "v-clicks=",
        "::right::",
        "::left::",
    ),
    REVEAL_MD: ("<!-- .slide:", "<!-- .element:"),
}
# The npm package that owns each flavor, read from a sibling `package.json`.
_MANIFEST_PACKAGES: dict[str, tuple[str, ...]] = {
    SLIDEV: ("@slidev/cli",),
    MARP: ("@marp-team/marp-cli",),
    REVEAL_MD: ("reveal-md",),
}

# Incremental-reveal markers: the author's own request for a staged reveal.
# These are structure, not observed motion — a build run is ordered cumulative
# content, never evidence that anything animated on screen.
#
# One compiled alternation per flavor, never a list of substrings counted
# independently: `<v-clicks>` contains `<v-click`, so counting both tokens
# scored one marker twice. A single left-to-right scan consumes each match, so
# overlapping spellings cannot double-count. Longest alternative first.
_REVEAL_PATTERNS: dict[str, re.Pattern[str] | None] = {
    PRESENTERM: re.compile(r"<!--\s*pause\s*-->"),
    SLIDEV: re.compile(r"<v-clicks?\b|<v-switch\b|v-clicks?\s*=|v-after\b"),
    REVEAL_MD: re.compile(r"""class\s*=\s*["']fragment"""),
    # Marp renders a fragmented list whole in a PDF export. Nothing in the
    # source declares a build the export preserves, so nothing is counted.
    MARP: None,
}
# Headmatter switches that make an explicit marker count a FLOOR rather than an
# exact one: the tool stages content the source never marks.
_IMPLICIT_REVEAL_SWITCHES: dict[str, tuple[tuple[str, ...], ...]] = {
    PRESENTERM: (("options", "incremental_lists"),),
}
# Slidev pulls slides from another file with a per-slide `src:` key. That one
# source slide can render as many, so a count taken here is a floor. Verified
# against the Slidev demo deck, whose `src: ./pages/imported-slides.md` slide
# reads as one and renders as however many the imported file holds.
_SLIDEV_IMPORT_KEY = re.compile(r"^src\s*:\s*(\S.*?)\s*$")

_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_YAML_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*\s*:(\s|$)")
_HORIZONTAL_RULE = re.compile(r"^-{3,}\s*$")
_VERTICAL_RULE = re.compile(r"^--\s*$")
# presenterm renders a title slide from the headmatter when any of these is set.
# Verified against presenterm 0.16.1: `author:` alone adds a page, `theme:` and
# `options:` alone do not.
_PRESENTERM_INTRO_KEYS = ("title", "sub_title", "author", "authors")


class MarkdownDeckError(ValueError):
    """The deck source cannot be read as a markdown-authored deck."""


@dataclass(frozen=True)
class FlavorDecision:
    """Which tool authored the deck, and the literal that decided it."""

    flavor: str
    decided_by: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "flavor": self.flavor,
            "decided_by": self.decided_by,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class SlideStructure:
    """One authored slide's source span and its declared reveal markers."""

    index: int
    first_line: int
    last_line: int
    reveal_markers: int

    def to_dict(self) -> dict[str, int]:
        return {
            "index": self.index,
            "first_line": self.first_line,
            "last_line": self.last_line,
            "reveal_markers": self.reveal_markers,
        }


@dataclass(frozen=True)
class DeckStructure:
    """What the deck source declares, before any renderer has run."""

    flavor: str
    slides: tuple[SlideStructure, ...]
    headmatter_readable: bool
    reveal_markers_are_a_floor: bool
    floor_causes: tuple[str, ...]
    imported_files: tuple[str, ...]

    @property
    def slide_count(self) -> int:
        return len(self.slides)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DECK_STRUCTURE_SCHEMA_VERSION,
            "flavor": self.flavor,
            "slide_count": self.slide_count,
            "headmatter_readable": self.headmatter_readable,
            "slides_with_reveal_markers": sum(
                1 for slide in self.slides if slide.reveal_markers
            ),
            "reveal_marker_total": sum(slide.reveal_markers for slide in self.slides),
            "reveal_markers_are_a_floor": self.reveal_markers_are_a_floor,
            "floor_causes": list(self.floor_causes),
            # A deck that imports slides from another file renders more slides
            # than this reading counts, so `slide_count` above is a floor.
            "imported_files": list(self.imported_files),
            "slide_count_is_a_floor": bool(self.imported_files),
            "slides": [slide.to_dict() for slide in self.slides],
        }


def _fence_mask(lines: Sequence[str]) -> list[bool]:
    """Return, per line, whether it sits inside a fenced code block."""
    inside = [False] * len(lines)
    open_fence: str | None = None
    for number, line in enumerate(lines):
        match = _FENCE.match(line)
        if open_fence is None:
            if match is not None:
                open_fence = match.group(1)[0]
                inside[number] = True
            continue
        inside[number] = True
        if match is not None and match.group(1)[0] == open_fence:
            open_fence = None
    return inside


def _headmatter_span(lines: Sequence[str]) -> tuple[int, int] | None:
    """Return the inclusive line span of a leading frontmatter block."""
    if not lines or not _HORIZONTAL_RULE.match(lines[0]):
        return None
    for number in range(1, len(lines)):
        if _HORIZONTAL_RULE.match(lines[number]) or lines[number].rstrip() == "...":
            return (0, number)
    return None


def read_headmatter(source: str) -> tuple[Mapping[str, Any] | None, bool]:
    """Return the parsed leading frontmatter and whether it parsed at all."""
    lines = source.splitlines()
    span = _headmatter_span(lines)
    if span is None:
        return (None, True)
    block = "\n".join(lines[span[0] + 1 : span[1]])
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return (None, False)
    if parsed is None:
        return ({}, True)
    if not isinstance(parsed, Mapping):
        return (None, False)
    return (parsed, True)


def _manifest_packages(deck_path: Path) -> dict[str, str]:
    """Return flavor -> package for each deck tool the deck's sibling manifest declares.

    Only the deck's own directory is read. Walking up would pick a workspace
    root's manifest and name a tool that belongs to a different deck in the
    same repository.
    """
    found: dict[str, str] = {}
    try:
        text = (deck_path.parent / "package.json").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return found
    for flavor, packages in _MANIFEST_PACKAGES.items():
        for package in packages:
            if f'"{package}"' in text:
                found.setdefault(flavor, package)
    return found


def _matched_flavors(
    source: str,
    headmatter: Mapping[str, Any] | None,
    markers: Mapping[str, tuple[str, ...]],
    keys: Mapping[str, tuple[str, ...]],
) -> dict[str, tuple[str, str]]:
    """Return flavor -> (decided_by, evidence) for every vocabulary that hits."""
    matched: dict[str, tuple[str, str]] = {}
    for flavor, key_names in keys.items():
        for key in key_names:
            if headmatter is not None and key in headmatter:
                matched.setdefault(flavor, ("headmatter_key", key))
    for flavor, literals in markers.items():
        for literal in literals:
            if literal in source:
                matched.setdefault(flavor, ("body_marker", literal))
    return matched


def detect_flavor(source: str, *, deck_path: Path | None = None) -> FlavorDecision:
    """Decide which tool authored the deck, or refuse to guess.

    Definitive vocabularies decide alone. Corroborating ones decide only when
    they match a single flavor. Anything else raises: an operator naming
    ``--flavor`` is a better answer than a coin flip that silently renders the
    deck with the wrong tool.
    """
    headmatter, _ = read_headmatter(source)
    definitive = _matched_flavors(
        source,
        headmatter,
        _DEFINITIVE_BODY_MARKERS,
        _DEFINITIVE_HEADMATTER_KEYS,
    )
    if deck_path is not None:
        for flavor, package in _manifest_packages(deck_path).items():
            definitive.setdefault(flavor, ("sibling_manifest", package))
    if len(definitive) == 1:
        flavor, (decided_by, evidence) = next(iter(definitive.items()))
        return FlavorDecision(flavor=flavor, decided_by=decided_by, evidence=evidence)
    if len(definitive) > 1:
        raise MarkdownDeckError(
            "deck carries definitive markers for more than one tool "
            f"({', '.join(sorted(definitive))}); pass --flavor to name the "
            "one that authored it"
        )
    corroborating = _matched_flavors(
        source,
        headmatter,
        _CORROBORATING_BODY_MARKERS,
        _CORROBORATING_HEADMATTER_KEYS,
    )
    if len(corroborating) == 1:
        flavor, (decided_by, evidence) = next(iter(corroborating.items()))
        return FlavorDecision(flavor=flavor, decided_by=decided_by, evidence=evidence)
    if len(corroborating) > 1:
        raise MarkdownDeckError(
            "deck carries markers for more than one tool "
            f"({', '.join(sorted(corroborating))}); pass --flavor to name the "
            "one that authored it"
        )
    raise MarkdownDeckError(
        "no marker in the deck names an authoring tool; pass --flavor with one "
        f"of {', '.join(FLAVORS)}"
    )


def _boundaries_presenterm(
    lines: Sequence[str],
    inside_fence: Sequence[bool],
    headmatter: Mapping[str, Any] | None,
) -> list[int]:
    """Return the first line of each slide, splitting on the slide terminator."""
    span = _headmatter_span(lines)
    start = 0 if span is None else span[1] + 1
    boundaries = [start]
    for number in range(start, len(lines)):
        if inside_fence[number]:
            continue
        if lines[number].strip() == "<!-- end_slide -->":
            boundaries.append(number + 1)
    if headmatter and any(key in headmatter for key in _PRESENTERM_INTRO_KEYS):
        # The headmatter renders as its own title slide ahead of the body.
        boundaries.insert(0, 0)
    return boundaries


def _boundaries_slidev(
    lines: Sequence[str],
    inside_fence: Sequence[bool],
) -> list[int]:
    """Return the first line of each slide for Slidev's separator syntax.

    A `---` opens a slide. When the line right after it reads as a YAML key and
    a later `---` closes the block before any other separator, that closing
    `---` is the slide's own frontmatter terminator, not a second slide.
    """
    span = _headmatter_span(lines)
    start = 0 if span is None else span[1] + 1
    boundaries = [start]
    number = start
    while number < len(lines):
        if inside_fence[number] or not _HORIZONTAL_RULE.match(lines[number]):
            number += 1
            continue
        boundaries.append(number + 1)
        following = number + 1
        if following < len(lines) and _YAML_KEY.match(lines[following]):
            closing = following
            while closing < len(lines):
                if not inside_fence[closing] and _HORIZONTAL_RULE.match(lines[closing]):
                    break
                closing += 1
            if closing < len(lines):
                boundaries[-1] = closing + 1
                number = closing + 1
                continue
        number += 1
    return boundaries


def _boundaries_ruled(
    lines: Sequence[str],
    inside_fence: Sequence[bool],
    *,
    vertical: bool,
) -> list[int]:
    """Return the first line of each slide for plain rule-separated decks."""
    span = _headmatter_span(lines)
    start = 0 if span is None else span[1] + 1
    boundaries = [start]
    for number in range(start, len(lines)):
        if inside_fence[number]:
            continue
        if _HORIZONTAL_RULE.match(lines[number]):
            boundaries.append(number + 1)
        elif vertical and _VERTICAL_RULE.match(lines[number]):
            boundaries.append(number + 1)
    return boundaries


def _nested(headmatter: Mapping[str, Any] | None, path: Sequence[str]) -> Any:
    current: Any = headmatter
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def read_deck(source: str, flavor: str) -> DeckStructure:
    """Return the slide spans and reveal markers the deck source declares."""
    if flavor not in FLAVORS:
        raise MarkdownDeckError(
            f"unknown flavor {flavor!r}; choose from {', '.join(FLAVORS)}"
        )
    lines = source.splitlines()
    inside_fence = _fence_mask(lines)
    headmatter, headmatter_readable = read_headmatter(source)
    if flavor == PRESENTERM:
        boundaries = _boundaries_presenterm(lines, inside_fence, headmatter)
    elif flavor == SLIDEV:
        boundaries = _boundaries_slidev(lines, inside_fence)
    else:
        boundaries = _boundaries_ruled(
            lines,
            inside_fence,
            vertical=flavor == REVEAL_MD,
        )
    # A deck that ends on a separator puts a boundary at EOF. That separator
    # closes the slide before it; treating it as the start of another invents
    # an empty slide with a first_line past the end of the file, and inflates
    # the count the render's page count is checked against.
    boundaries = [start for start in boundaries if start < len(lines)]
    pattern = _REVEAL_PATTERNS[flavor]
    slides: list[SlideStructure] = []
    for position, start in enumerate(boundaries):
        # A boundary is the index of a slide's FIRST line, so the next boundary
        # minus one is the separator that ended this slide — excluded from the
        # body. Reported line numbers are 1-based, which makes the same integer
        # both the exclusive 0-based body end and the inclusive 1-based last
        # content line. Named separately so neither reading has to be inferred.
        body_end = (
            boundaries[position + 1] - 1
            if position + 1 < len(boundaries)
            else len(lines)
        )
        body = "\n".join(
            line
            for number, line in enumerate(lines[start:body_end], start=start)
            if not inside_fence[number]
        )
        slides.append(
            SlideStructure(
                index=position + 1,
                first_line=start + 1,
                # A separator-only slide has no content line; report its own
                # first line rather than a span that runs backwards.
                last_line=max(body_end, start + 1),
                reveal_markers=(0 if pattern is None else len(pattern.findall(body))),
            )
        )
    floor_causes = tuple(
        ".".join(path)
        for path in _IMPLICIT_REVEAL_SWITCHES.get(flavor, ())
        if _nested(headmatter, path) is True
    )
    imported: list[str] = []
    if flavor == SLIDEV:
        for number, line in enumerate(lines):
            if inside_fence[number]:
                continue
            match = _SLIDEV_IMPORT_KEY.match(line)
            if match is not None:
                imported.append(match.group(1))
    return DeckStructure(
        flavor=flavor,
        slides=tuple(slides),
        headmatter_readable=headmatter_readable,
        reveal_markers_are_a_floor=bool(floor_causes),
        floor_causes=floor_causes,
        imported_files=tuple(imported),
    )


if __name__ == "__main__":  # pragma: no cover - module is imported, not run
    raise SystemExit("markdown_deck is a library; run render-markdown-deck.py instead")

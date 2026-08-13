"""Read a deck's deterministic identity facts out of its OPC package (#176).

`pptx_talk_identity` decides which talk a deck belongs to from facts someone
else observed. This module is that observer for a deck already on disk: it
opens the package, reads two small metadata parts and the title slide, and
returns the mapping `deck_identity_facts` accepts.

Three properties shape it.

* **Bounded.** Only `docProps/core.xml`, `docProps/app.xml`, and the first
  slide are read, each under an expanded-size cap. A catalog row is persisted
  state, and persisted state is a hint, never a licence to decompress an
  arbitrary host file (`stateful-artifacts` -> Hints, Not Authority).
* **Never fatal.** An unreadable, damaged, or absent deck returns the facts
  gathered so far with a reason code. Damage must weaken the evidence, never
  the identity requirements, so the caller still assesses the deck from its
  path rather than skipping it.
* **Nothing invented.** A part that is missing or malformed contributes no
  fact. Absence is reported as absence; the identity module's `unknown`
  verdict already means "this deck does not carry that fact".

## Why the title slide and not every slide title

`docProps/app.xml` lists every slide's title, and feeding that list in as
rendered text is actively wrong. Measured against the live vault's 74 bound
decks, passing all 95 slide titles of one deck made 69 of the 74 assessments
`identity_ambiguous_candidates`: a deck that mentions another talk's title on
some interior slide agrees with that talk, and agreeing with everything is
indistinguishable from knowing nothing.

The title slide cannot do that. Its runs are this deck's own title and
subtitle, which is what the catalog's title is being compared against.
"""

from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from artifact_locator import (
    ArtifactLocatorError,
    classify_artifact_locator,
    materialize_artifact_locator,
)
from pptx_catalog_selection import open_contained_descriptor

DECK_FACTS_SCHEMA_VERSION = 1

# Reason codes are closed. They report why a fact is absent, never what the
# host filesystem or the archive's bytes look like (`no-secrets` -> Logging).
DECK_FACTS_OK = "deck_facts_read"
DECK_FACTS_LOCATOR_INVALID = "deck_facts_locator_invalid"
DECK_FACTS_UNREADABLE = "deck_facts_unreadable"
DECK_FACTS_NOT_A_PACKAGE = "deck_facts_not_a_package"
DECK_FACTS_PACKAGE_OVERSIZED = "deck_facts_package_oversized"
DECK_FACTS_PART_UNREADABLE = "deck_facts_part_unreadable"
DECK_FACTS_PARTS_ABSENT = "deck_facts_parts_absent"

DECK_FACTS_REASON_CODES = frozenset(
    {
        DECK_FACTS_OK,
        DECK_FACTS_LOCATOR_INVALID,
        DECK_FACTS_UNREADABLE,
        DECK_FACTS_NOT_A_PACKAGE,
        DECK_FACTS_PACKAGE_OVERSIZED,
        DECK_FACTS_PART_UNREADABLE,
        DECK_FACTS_PARTS_ABSENT,
    }
)

_CORE_PART = "docProps/core.xml"
_APP_PART = "docProps/app.xml"
_TITLE_SLIDE_PART = "ppt/slides/slide1.xml"

# A metadata part and one slide are small. These caps bound decompression on a
# path chosen by persisted state; a real deck's parts are orders below them.
_MAX_PART_EXPANDED_BYTES = 8 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 65_536

# Beyond the title, the title slide's remaining runs are the subtitle and
# speaker/venue line. Bounded so a text-heavy first slide cannot reintroduce
# the agree-with-everything failure the module docstring describes.
_MAX_RENDERED_FOOTERS = 8
_MAX_HASHTAGS = 16
_MAX_TEXT_CHARS = 500

_EXT_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
_VT_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}"
_DC_NS = "{http://purl.org/dc/elements/1.1/}"
_DCTERMS_NS = "{http://purl.org/dc/terms/}"
_DRAWING_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

_SLIDE_TITLES_HEADING = "Slide Titles"
_HASHTAG_RE = re.compile(r"#\w+", re.UNICODE)
_YEAR_PREFIX_RE = re.compile(r"\A(?:19|20)\d{2}")


@dataclass(frozen=True)
class DeckFactsReading:
    """One deck's observed identity facts plus why anything is missing.

    `facts` is always a mapping `deck_identity_facts` accepts, even when the
    package could not be opened: `pptx_path` alone is a valid observation, and
    the path's own venue and year signals are exactly what must survive damage.
    """

    pptx_path: str
    facts: dict[str, Any]
    reason_code: str
    slide_count: int | None = None
    parts_read: tuple[str, ...] = field(default=())

    @property
    def package_read(self) -> bool:
        return self.reason_code == DECK_FACTS_OK

    def as_json(self) -> dict[str, Any]:
        return {
            "schema_version": DECK_FACTS_SCHEMA_VERSION,
            "pptx_path": self.pptx_path,
            "reason_code": self.reason_code,
            "slide_count": self.slide_count,
            "parts_read": list(self.parts_read),
            "facts": dict(self.facts),
        }


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.split())
    if not collapsed:
        return None
    return collapsed[:_MAX_TEXT_CHARS]


def _slide_titles(app_xml: bytes) -> list[str]:
    """Read `TitlesOfParts` slice that `HeadingPairs` labels as slide titles.

    `TitlesOfParts` concatenates several categories — fonts, themes, then slide
    titles — and only `HeadingPairs` says where each begins. Slicing by a fixed
    offset would read font names as titles on any deck with a different theme
    count.
    """
    root = ET.fromstring(app_xml)
    pairs = root.find(f"{_EXT_NS}HeadingPairs")
    parts = root.find(f"{_EXT_NS}TitlesOfParts")
    if pairs is None or parts is None:
        return []
    pair_vector = pairs.find(f"{_VT_NS}vector")
    counts: list[tuple[str, int]] = []
    label: str | None = None
    for variant in [] if pair_vector is None else list(pair_vector):
        for child in variant:
            if child.tag == f"{_VT_NS}lpstr":
                label = child.text
            elif child.tag == f"{_VT_NS}i4" and label is not None:
                try:
                    counts.append((label, int(child.text or "")))
                except ValueError:
                    return []
                label = None
    part_vector = parts.find(f"{_VT_NS}vector")
    names = (
        []
        if part_vector is None
        else [element.text or "" for element in part_vector.findall(f"{_VT_NS}lpstr")]
    )
    offset = 0
    for name, count in counts:
        if count < 0:
            return []
        if name == _SLIDE_TITLES_HEADING:
            return names[offset : offset + count]
        offset += count
    return []


def _slide_count(app_xml: bytes) -> int | None:
    root = ET.fromstring(app_xml)
    raw = root.findtext(f"{_EXT_NS}Slides")
    try:
        count = int((raw or "").strip())
    except ValueError:
        return None
    return count if count >= 0 else None


def _title_slide_runs(slide_xml: bytes) -> list[str]:
    root = ET.fromstring(slide_xml)
    runs: list[str] = []
    for element in root.iter(f"{_DRAWING_NS}t"):
        text = _text(element.text)
        if text is not None:
            runs.append(text)
    return runs


def _resolve_descriptor(pptx_path: str, pptx_source_dir: object) -> int | None:
    """Open the deck under its configured root, refusing every symlink below it.

    Containment is `pptx_catalog_selection`'s rule and is reused rather than
    restated: the sweep must not be able to read a file the evidence classifier
    would have refused.
    """
    if pptx_source_dir is None:
        return None
    try:
        if classify_artifact_locator(pptx_path) != "relative":
            return None
        resolved = materialize_artifact_locator(pptx_path, pptx_source_dir)
        parts = resolved.relative_to(Path(str(pptx_source_dir))).parts
    except (ArtifactLocatorError, TypeError, ValueError):
        return None
    return open_contained_descriptor(pptx_source_dir, parts)


def _read_part(archive: zipfile.ZipFile, name: str) -> bytes | None:
    """Read one part, refusing a member that expands past the cap."""
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > _MAX_PART_EXPANDED_BYTES:
        return None
    try:
        with archive.open(info) as stream:
            return stream.read(_MAX_PART_EXPANDED_BYTES + 1)
    except (zipfile.BadZipFile, OSError, EOFError, ValueError):
        return None


def read_deck_identity_facts(
    pptx_path: object,
    pptx_source_dir: object,
) -> DeckFactsReading:
    """Observe one catalog deck's identity facts, or report why it could not be.

    Returns a reading whose `facts` always at least names the deck, so a caller
    can hand it straight to `assess_pptx_talk_identity` regardless of outcome.
    """
    path_text = _text(pptx_path)
    if path_text is None:
        return DeckFactsReading(
            pptx_path="",
            facts={"pptx_path": ""},
            reason_code=DECK_FACTS_LOCATOR_INVALID,
        )
    facts: dict[str, Any] = {"pptx_path": path_text}
    descriptor = _resolve_descriptor(path_text, pptx_source_dir)
    if descriptor is None:
        return DeckFactsReading(
            pptx_path=path_text,
            facts=facts,
            reason_code=DECK_FACTS_UNREADABLE,
        )
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            return _read_from_stream(handle, path_text, facts)
    except (OSError, ValueError):
        return DeckFactsReading(
            pptx_path=path_text,
            facts=facts,
            reason_code=DECK_FACTS_UNREADABLE,
        )


def _read_from_stream(
    handle: Any,
    pptx_path: str,
    facts: dict[str, Any],
) -> DeckFactsReading:
    try:
        archive = zipfile.ZipFile(handle)
    except (zipfile.BadZipFile, OSError, EOFError, ValueError):
        return DeckFactsReading(
            pptx_path=pptx_path,
            facts=facts,
            reason_code=DECK_FACTS_NOT_A_PACKAGE,
        )
    with archive:
        try:
            members = archive.namelist()
        except (zipfile.BadZipFile, OSError, ValueError):
            return DeckFactsReading(
                pptx_path=pptx_path,
                facts=facts,
                reason_code=DECK_FACTS_NOT_A_PACKAGE,
            )
        if len(members) > _MAX_ARCHIVE_MEMBERS:
            return DeckFactsReading(
                pptx_path=pptx_path,
                facts=facts,
                reason_code=DECK_FACTS_PACKAGE_OVERSIZED,
            )
        return _read_parts(archive, pptx_path, facts)


def _read_parts(
    archive: zipfile.ZipFile,
    pptx_path: str,
    facts: dict[str, Any],
) -> DeckFactsReading:
    parts_read: list[str] = []
    malformed = False
    slide_count: int | None = None
    hashtag_sources: list[str] = []

    core_xml = _read_part(archive, _CORE_PART)
    if core_xml is not None:
        try:
            root = ET.fromstring(core_xml)
        except ET.ParseError:
            malformed = True
        else:
            parts_read.append(_CORE_PART)
            document_title = _text(root.findtext(f"{_DC_NS}title"))
            if document_title is not None:
                facts["document_title"] = document_title
            created = _text(root.findtext(f"{_DCTERMS_NS}created"))
            if created is not None and _YEAR_PREFIX_RE.match(created):
                facts["document_created_year"] = created[:4]

    app_xml = _read_part(archive, _APP_PART)
    titles: list[str] = []
    if app_xml is not None:
        try:
            titles = [
                text
                for text in (_text(item) for item in _slide_titles(app_xml))
                if text
            ]
            slide_count = _slide_count(app_xml)
        except ET.ParseError:
            malformed = True
        else:
            parts_read.append(_APP_PART)
            hashtag_sources.extend(titles)

    slide_xml = _read_part(archive, _TITLE_SLIDE_PART)
    runs: list[str] = []
    if slide_xml is not None:
        try:
            runs = _title_slide_runs(slide_xml)
        except ET.ParseError:
            malformed = True
        else:
            parts_read.append(_TITLE_SLIDE_PART)
            hashtag_sources.extend(runs)

    # The title slide's first run is this deck's own headline; app.xml's first
    # slide title is the same string as PowerPoint recorded it. Either is the
    # deck's title, and the slide is preferred because it keeps the subtitle
    # runs that follow it in the same reading.
    rendered_title = runs[0] if runs else (titles[0] if titles else None)
    if rendered_title is not None:
        facts["rendered_title"] = rendered_title
    if len(runs) > 1:
        facts["rendered_footers"] = runs[1 : 1 + _MAX_RENDERED_FOOTERS]

    hashtags: list[str] = []
    for text in hashtag_sources:
        for tag in _HASHTAG_RE.findall(text):
            if tag not in hashtags:
                hashtags.append(tag)
    if hashtags:
        facts["hashtags"] = hashtags[:_MAX_HASHTAGS]

    if malformed:
        reason_code = DECK_FACTS_PART_UNREADABLE
    elif not parts_read:
        reason_code = DECK_FACTS_PARTS_ABSENT
    else:
        reason_code = DECK_FACTS_OK
    return DeckFactsReading(
        pptx_path=pptx_path,
        facts=facts,
        reason_code=reason_code,
        slide_count=slide_count,
        parts_read=tuple(parts_read),
    )


__all__ = [
    "DECK_FACTS_LOCATOR_INVALID",
    "DECK_FACTS_NOT_A_PACKAGE",
    "DECK_FACTS_OK",
    "DECK_FACTS_PACKAGE_OVERSIZED",
    "DECK_FACTS_PARTS_ABSENT",
    "DECK_FACTS_PART_UNREADABLE",
    "DECK_FACTS_REASON_CODES",
    "DECK_FACTS_SCHEMA_VERSION",
    "DECK_FACTS_UNREADABLE",
    "DeckFactsReading",
    "read_deck_identity_facts",
]

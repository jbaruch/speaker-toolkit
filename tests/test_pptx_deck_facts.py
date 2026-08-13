"""Tests for reading a deck's identity facts out of its OPC package (#176).

Every package is built in-test from fixed literals — no binary fixture is
checked in, and no test reads the clock or a live vault, so a run today and a
run next year agree.
"""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pptx_deck_facts = _load("pptx_deck_facts")


CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/">
<dc:title>{title}</dc:title>
<dcterms:created>{created}</dcterms:created>
</cp:coreProperties>"""

_APP_HEAD = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties
 xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Slides>{slides}</Slides>
<HeadingPairs><vt:vector size="4" baseType="variant">
<vt:variant><vt:lpstr>Fonts Used</vt:lpstr></vt:variant>
<vt:variant><vt:i4>{fonts}</vt:i4></vt:variant>
<vt:variant><vt:lpstr>Slide Titles</vt:lpstr></vt:variant>
<vt:variant><vt:i4>{titles}</vt:i4></vt:variant>
</vt:vector></HeadingPairs>
<TitlesOfParts><vt:vector size="{total}" baseType="lpstr">{parts}</vt:vector>
</TitlesOfParts></Properties>"""

SLIDE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>{runs}</p:spTree></p:cSld></p:sld>"""


def app_xml(*, fonts: list[str], slide_titles: list[str], slides: int) -> str:
    """Build an app.xml whose TitlesOfParts really does concatenate categories.

    The font block is not decoration: it is what makes a fixed-offset reader
    return font names where slide titles belong.
    """
    parts = "".join(f"<vt:lpstr>{name}</vt:lpstr>" for name in [*fonts, *slide_titles])
    return _APP_HEAD.format(
        slides=slides,
        fonts=len(fonts),
        titles=len(slide_titles),
        total=len(fonts) + len(slide_titles),
        parts=parts,
    )


def slide_xml(runs: list[str]) -> str:
    body = "".join(
        f"<p:sp><p:txBody><a:p><a:r><a:t>{run}</a:t></a:r></a:p></p:txBody></p:sp>"
        for run in runs
    )
    return SLIDE_XML.format(runs=body)


def write_deck(root: Path, relative: str, members: dict[str, str]) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return path


def full_deck_members(
    *,
    document_title: str = "This is your presentation title",
    created: str = "2025-01-17T09:00:00Z",
    slide_titles: list[str] | None = None,
    runs: list[str] | None = None,
    slides: int = 42,
) -> dict[str, str]:
    return {
        "docProps/core.xml": CORE_XML.format(title=document_title, created=created),
        "docProps/app.xml": app_xml(
            fonts=["Calibri", "Bangers"],
            slide_titles=slide_titles
            if slide_titles is not None
            else ["DevOps for Developers", "shownotes"],
            slides=slides,
        ),
        "ppt/slides/slide1.xml": slide_xml(
            runs
            if runs is not None
            else ["DevOps for Developers", "and the path beyond", "#VoxxedTicino"]
        ),
    }


@pytest.fixture()
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "Presentations"
    root.mkdir()
    return root


class TestReadingAWholeDeck:
    def test_every_part_contributes_its_own_fact(self, source_root: Path) -> None:
        write_deck(source_root, "Voxxed/2025/Deck.pptx", full_deck_members())
        reading = pptx_deck_facts.read_deck_identity_facts(
            "Voxxed/2025/Deck.pptx", source_root
        )
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_OK
        assert reading.facts["document_title"] == "This is your presentation title"
        assert reading.facts["document_created_year"] == "2025"
        assert reading.facts["rendered_title"] == "DevOps for Developers"
        assert reading.facts["rendered_footers"] == [
            "and the path beyond",
            "#VoxxedTicino",
        ]
        assert reading.facts["hashtags"] == ["#VoxxedTicino"]
        assert reading.slide_count == 42

    def test_the_facts_are_accepted_by_the_identity_module(
        self, source_root: Path
    ) -> None:
        """The two modules share one shape, and this is where that is proven."""
        identity = _load("pptx_talk_identity")
        write_deck(source_root, "Voxxed/2025/Deck.pptx", full_deck_members())
        reading = pptx_deck_facts.read_deck_identity_facts(
            "Voxxed/2025/Deck.pptx", source_root
        )
        facts = identity.deck_identity_facts(reading.facts)
        assert facts.pptx_path == "Voxxed/2025/Deck.pptx"
        assert facts.rendered_title == "DevOps for Developers"

    def test_slide_titles_are_sliced_by_their_heading_pair(
        self, source_root: Path
    ) -> None:
        """A fixed offset would read `Calibri` as this deck's title."""
        write_deck(
            source_root,
            "Deck.pptx",
            {
                "docProps/app.xml": app_xml(
                    fonts=["Calibri", "Bangers", "Sniglet"],
                    slide_titles=["The Real Title"],
                    slides=1,
                )
            },
        )
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert reading.facts["rendered_title"] == "The Real Title"

    def test_the_title_slide_wins_over_the_recorded_slide_title(
        self, source_root: Path
    ) -> None:
        """PowerPoint records a truncated title; the slide carries the whole one."""
        write_deck(
            source_root,
            "Deck.pptx",
            full_deck_members(
                slide_titles=["Devops... reframed"],
                runs=["Devops... reframed", "Embracing the Path"],
            ),
        )
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert reading.facts["rendered_title"] == "Devops... reframed"
        assert reading.facts["rendered_footers"] == ["Embracing the Path"]


class TestInteriorSlidesNeverBecomeRenderedText:
    def test_only_the_title_slide_supplies_rendered_text(
        self, source_root: Path
    ) -> None:
        """The failure this bound: a deck agreeing with every talk it mentions.

        Interior slide titles name other talks. Feeding them in as rendered
        text made 69 of the live vault's 74 bound decks ambiguous, because a
        deck that agrees with everything is indistinguishable from one that
        carries no evidence at all.
        """
        write_deck(
            source_root,
            "Deck.pptx",
            full_deck_members(
                slide_titles=[
                    "DevOps for Developers",
                    "Securing the Software Supply Chain",
                    "Coding Fast and Slow",
                ],
                runs=["DevOps for Developers"],
            ),
        )
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert reading.facts["rendered_title"] == "DevOps for Developers"
        assert "rendered_footers" not in reading.facts

    def test_rendered_footers_are_bounded(self, source_root: Path) -> None:
        write_deck(
            source_root,
            "Deck.pptx",
            full_deck_members(runs=["Title", *[f"line {n}" for n in range(40)]]),
        )
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert len(reading.facts["rendered_footers"]) == 8


class TestHashtags:
    def test_hashtags_are_deduplicated_in_first_seen_order(
        self, source_root: Path
    ) -> None:
        write_deck(
            source_root,
            "Deck.pptx",
            full_deck_members(
                slide_titles=["#VoxxedTicino kickoff"],
                runs=["Title", "#VoxxedTicino", "#DevOps", "#VoxxedTicino"],
            ),
        )
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert reading.facts["hashtags"] == ["#VoxxedTicino", "#DevOps"]

    def test_a_deck_with_no_hashtag_reports_none(self, source_root: Path) -> None:
        write_deck(
            source_root,
            "Deck.pptx",
            full_deck_members(slide_titles=["Plain"], runs=["Plain"]),
        )
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert "hashtags" not in reading.facts


class TestDamageWeakensEvidenceNotRequirements:
    def test_a_missing_deck_still_names_itself(self, source_root: Path) -> None:
        reading = pptx_deck_facts.read_deck_identity_facts(
            "Voxxed/2025/Absent.pptx", source_root
        )
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_UNREADABLE
        assert reading.facts == {"pptx_path": "Voxxed/2025/Absent.pptx"}

    def test_a_file_that_is_not_a_package_reports_so(self, source_root: Path) -> None:
        (source_root / "Deck.pptx").write_text("not a zip", encoding="utf-8")
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_NOT_A_PACKAGE
        assert reading.facts == {"pptx_path": "Deck.pptx"}

    def test_a_malformed_part_keeps_the_parts_that_parsed(
        self, source_root: Path
    ) -> None:
        members = full_deck_members()
        members["docProps/app.xml"] = "<Properties><unclosed>"
        write_deck(source_root, "Deck.pptx", members)
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_PART_UNREADABLE
        assert reading.facts["document_created_year"] == "2025"
        assert reading.facts["rendered_title"] == "DevOps for Developers"

    def test_a_package_with_no_known_parts_reports_absent(
        self, source_root: Path
    ) -> None:
        write_deck(source_root, "Deck.pptx", {"ppt/presentation.xml": "<p/>"})
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_PARTS_ABSENT
        assert reading.facts == {"pptx_path": "Deck.pptx"}

    def test_an_oversized_part_is_refused_rather_than_expanded(
        self, source_root: Path
    ) -> None:
        members = full_deck_members()
        members["docProps/core.xml"] = "<a>" + ("x" * (9 * 1024 * 1024)) + "</a>"
        write_deck(source_root, "Deck.pptx", members)
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", source_root)
        assert "document_created_year" not in reading.facts
        assert reading.facts["rendered_title"] == "DevOps for Developers"


class TestContainment:
    def test_an_absolute_locator_is_refused(self, source_root: Path) -> None:
        write_deck(source_root, "Deck.pptx", full_deck_members())
        reading = pptx_deck_facts.read_deck_identity_facts(
            str(source_root / "Deck.pptx"), source_root
        )
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_UNREADABLE

    def test_an_escaping_locator_is_refused(self, source_root: Path) -> None:
        reading = pptx_deck_facts.read_deck_identity_facts(
            "../outside.pptx", source_root
        )
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_UNREADABLE

    def test_a_symlinked_component_is_refused(self, source_root: Path) -> None:
        outside = source_root.parent / "outside"
        outside.mkdir()
        write_deck(outside, "Deck.pptx", full_deck_members())
        (source_root / "link").symlink_to(outside, target_is_directory=True)
        reading = pptx_deck_facts.read_deck_identity_facts(
            "link/Deck.pptx", source_root
        )
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_UNREADABLE

    def test_no_source_root_reads_nothing(self, source_root: Path) -> None:
        write_deck(source_root, "Deck.pptx", full_deck_members())
        reading = pptx_deck_facts.read_deck_identity_facts("Deck.pptx", None)
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_UNREADABLE


class TestInputValidation:
    @pytest.mark.parametrize("value", [None, "", "   ", 17, ["Deck.pptx"]])
    def test_a_locator_that_is_not_text_reports_its_own_code(
        self, value: object, source_root: Path
    ) -> None:
        reading = pptx_deck_facts.read_deck_identity_facts(value, source_root)
        assert reading.reason_code == pptx_deck_facts.DECK_FACTS_LOCATOR_INVALID
        assert reading.facts == {"pptx_path": ""}

    def test_every_reason_code_is_in_the_closed_set(self) -> None:
        codes = {
            pptx_deck_facts.DECK_FACTS_OK,
            pptx_deck_facts.DECK_FACTS_LOCATOR_INVALID,
            pptx_deck_facts.DECK_FACTS_UNREADABLE,
            pptx_deck_facts.DECK_FACTS_NOT_A_PACKAGE,
            pptx_deck_facts.DECK_FACTS_PACKAGE_OVERSIZED,
            pptx_deck_facts.DECK_FACTS_PART_UNREADABLE,
            pptx_deck_facts.DECK_FACTS_PARTS_ABSENT,
        }
        assert codes == set(pptx_deck_facts.DECK_FACTS_REASON_CODES)


class TestSerialization:
    def test_the_reading_round_trips_as_json(self, source_root: Path) -> None:
        write_deck(source_root, "Voxxed/2025/Deck.pptx", full_deck_members())
        reading = pptx_deck_facts.read_deck_identity_facts(
            "Voxxed/2025/Deck.pptx", source_root
        )
        payload = reading.as_json()
        assert payload["schema_version"] == pptx_deck_facts.DECK_FACTS_SCHEMA_VERSION
        assert payload["pptx_path"] == "Voxxed/2025/Deck.pptx"
        assert payload["slide_count"] == 42
        assert "docProps/app.xml" in payload["parts_read"]

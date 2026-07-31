"""Structural guards on the Presentation Patterns catalog.

The catalog is prose, so nothing mechanically enforced its own conventions and
one of them drifted. The 2026-07-27 full-vault reparse surfaced the cost: 26 of
28 antipattern files scored on an INVERTED scale where "Strong signal (2 pts)"
described the antipattern being ABSENT, while the two newest files used the
direct scale. Subagents record `confidence` in `antipatterns_detected` meaning
"how strongly present", so the same value meant opposite things depending on
which file a scorer happened to open — across 3,228 corpus observations. Five
independent reparse agents reported it before it was believed.

These are deliberately structural: they check the contract a scorer reads, not
prose quality. Every assertion below was verified against the catalog as it
stands, so a failure means real drift rather than an invented convention.
"""

import glob
import os
import re

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = os.path.join(
    REPO_ROOT, "skills", "presentation-creator", "references", "patterns")
INDEX = os.path.join(PATTERNS, "_index.md")

STRONG_RE = re.compile(r"^- Strong signal \(2 pts([^)]*)\):", re.M)
MODERATE_RE = re.compile(r"^- Moderate signal \(1 pt\):", re.M)
ABSENT_RE = re.compile(r"^- Absent \(0 pts([^)]*)\):", re.M)

ENTRY_FILES = sorted(f for f in glob.glob(os.path.join(PATTERNS, "*", "*.md")))
ANTI_FILES = [f for f in ENTRY_FILES if os.path.basename(f).startswith("_anti_")]
ENTRY_BY_ID = {
    os.path.basename(path)[:-3].removeprefix("_anti_"): path
    for path in ENTRY_FILES
}

NAME_TRAP_GUARDS = {
    "make-it-rain": (
        "physical object in the room",
        "screen-based demonstration does not qualify",
    ),
    "dead-demo": (
        '"dead" means narratively lifeless, not technically failed',
        "Judge the demo's narrative purpose",
    ),
    "cave-painting": (
        "not a synonym for pictorial or wordless slides",
        "one spatial canvas",
    ),
    "exuberant-title-top": (
        "not a static title layout",
        "flattened final-state slide alone is not evidence",
    ),
    "flyover": (
        "not a high-level or abbreviated treatment of a topic",
        "status or belonging comparison",
    ),
    "bookends": (
        "repeated section-boundary slides",
        "not for symmetry between the opening and closing",
    ),
}

EVIDENCE_SOURCE_VALUES = frozenset({
    "static_slides",
    "native_deck",
    "delivery_video",
    "transcript",
    "source_comparison",
})
EVIDENCE_GATE_FIELDS = frozenset({
    "evaluable_from",
    "evidence_requirements",
    "not_evaluable_when",
})
REQUIRED_EVIDENCE_GATES = {
    "progressive-reveal": frozenset({
        "static_slides", "native_deck", "delivery_video"}),
    "composite-animation": frozenset({"native_deck", "delivery_video"}),
    "invisibility": frozenset({"native_deck", "source_comparison"}),
    "exuberant-title-top": frozenset({"native_deck", "delivery_video"}),
    "gradual-consistency": frozenset({"native_deck", "source_comparison"}),
    "traveling-highlights": frozenset({
        "static_slides", "native_deck", "delivery_video"}),
}


def _ids(files):
    return [os.path.basename(f)[:-3] for f in files]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _front(path, key):
    m = re.search(rf"^{key}:\s*(\S+)\s*$", _read(path), re.M)
    return m.group(1) if m else None


def _metadata(path):
    parts = _read(path).split("---", 2)
    assert len(parts) == 3, f"{os.path.basename(path)}: malformed frontmatter"
    metadata = yaml.safe_load(parts[1])
    assert isinstance(metadata, dict), (
        f"{os.path.basename(path)}: frontmatter is not a mapping")
    return metadata


def _path_for_id(pattern_id):
    matches = [path for path in ENTRY_FILES
               if _front(path, "id") == pattern_id]
    assert len(matches) == 1, f"expected one catalog entry for {pattern_id!r}"
    return matches[0]


def test_catalog_is_present():
    """Guard the guard: a bad glob would make every parametrized test vacuous."""
    assert len(ENTRY_FILES) == 111, f"expected 111 entries, found {len(ENTRY_FILES)}"
    assert len(ANTI_FILES) == 28, f"expected 28 antipatterns, found {len(ANTI_FILES)}"


@pytest.mark.parametrize("path", ANTI_FILES, ids=_ids(ANTI_FILES))
def test_antipattern_scoring_polarity_is_direct(path):
    """`Strong signal` must mean the antipattern is PRESENT.

    An inverted file makes `confidence: strong` in `antipatterns_detected`
    ambiguous — a scorer cannot tell "strongly present" from "strongly clean"
    without opening the individual file.
    """
    strong = STRONG_RE.search(_read(path))
    assert strong, f"{os.path.basename(path)}: no 'Strong signal (2 pts...)' bullet"
    assert "antipattern present" in strong.group(1), (
        f"{os.path.basename(path)} scores on the inverted scale: "
        f"'Strong signal (2 pts)' must read '(2 pts — antipattern present)'")


@pytest.mark.parametrize("path", ANTI_FILES, ids=_ids(ANTI_FILES))
def test_antipattern_absent_bullet_is_labelled(path):
    absent = ABSENT_RE.search(_read(path))
    assert absent, f"{os.path.basename(path)}: no 'Absent (0 pts...)' bullet"
    assert "not present" in absent.group(1), (
        f"{os.path.basename(path)}: 'Absent (0 pts)' must read "
        f"'(0 pts — antipattern not present)' so the scale reads unambiguously")


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_scoring_block_is_complete(path):
    """A partial scale is worse than none — a scorer fills the gap by guessing."""
    text = _read(path)
    assert "## Scoring Criteria" in text, f"{os.path.basename(path)}: no scoring block"
    assert STRONG_RE.search(text), f"{os.path.basename(path)}: missing Strong bullet"
    assert MODERATE_RE.search(text), f"{os.path.basename(path)}: missing Moderate bullet"
    assert ABSENT_RE.search(text), f"{os.path.basename(path)}: missing Absent bullet"


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_id_matches_filename(path):
    """Prevents the invented-id class: prior passes scored six ids that did not
    exist in the catalog, `terminal-as-deck` fourteen times."""
    expected = os.path.basename(path)[:-3].removeprefix("_anti_")
    assert _front(path, "id") == expected, (
        f"{os.path.basename(path)}: frontmatter id is {_front(path, 'id')!r}")


def test_ids_are_unique():
    seen = {}
    for f in ENTRY_FILES:
        pid = _front(f, "id")
        assert pid not in seen, f"duplicate id {pid!r}: {seen.get(pid)} and {f}"
        seen[pid] = f


@pytest.mark.parametrize(
    "pattern_id,required_phrases",
    NAME_TRAP_GUARDS.items(),
    ids=NAME_TRAP_GUARDS,
)
def test_name_traps_have_explicit_disqualifiers(pattern_id, required_phrases):
    """Known false friends must tell a fast scanner what does not qualify."""
    text = _read(ENTRY_BY_ID[pattern_id])
    assert "**NAME TRAP" in text, f"{pattern_id}: missing explicit name-trap guard"
    missing = [phrase for phrase in required_phrases if phrase not in text]
    assert not missing, f"{pattern_id}: missing disambiguators {missing}"


def test_catalog_references_resolve():
    """Every related/inverse reference must name a real catalog entry."""
    ids = set(ENTRY_BY_ID)
    dangling = []
    for path in ENTRY_FILES:
        metadata = _metadata(path)
        for field in ("related_patterns", "inverse_of"):
            references = metadata.get(field)
            assert isinstance(references, list), (
                f"{metadata.get('id')}: {field} must be a list")
            dangling.extend(
                (metadata.get("id"), field, target)
                for target in references
                if target not in ids
            )
    assert not dangling, f"dangling catalog references: {dangling}"


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_type_matches_anti_prefix(path):
    """`_anti_` prefix and `type:` must agree — a scorer that trusts one and a
    validator that trusts the other would disagree about what may be scored."""
    declared = _front(path, "type")
    is_anti = os.path.basename(path).startswith("_anti_")
    assert declared == ("antipattern" if is_anti else "pattern"), (
        f"{os.path.basename(path)}: type is {declared!r}")


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_evidence_gate_frontmatter_is_well_formed(path):
    """An evidence gate must be complete and use the documented source enum."""
    metadata = _metadata(path)
    present = EVIDENCE_GATE_FIELDS.intersection(metadata)
    if not present:
        return

    assert present == EVIDENCE_GATE_FIELDS, (
        f"{os.path.basename(path)}: partial evidence gate; present={sorted(present)}")

    sources = metadata["evaluable_from"]
    requirements = metadata["evidence_requirements"]
    disqualifiers = metadata["not_evaluable_when"]
    assert isinstance(sources, list) and sources, (
        f"{os.path.basename(path)}: evaluable_from must be a non-empty list")
    assert all(isinstance(source, str) for source in sources), (
        f"{os.path.basename(path)}: evidence sources must be strings")
    assert set(sources) <= EVIDENCE_SOURCE_VALUES, (
        f"{os.path.basename(path)}: unknown evidence sources "
        f"{sorted(set(sources) - EVIDENCE_SOURCE_VALUES)}")
    assert len(sources) == len(set(sources)), (
        f"{os.path.basename(path)}: duplicate evidence sources")
    for field, values in (("evidence_requirements", requirements),
                          ("not_evaluable_when", disqualifiers)):
        assert isinstance(values, list) and values, (
            f"{os.path.basename(path)}: {field} must be a non-empty list")
        assert all(isinstance(value, str) and value.strip() for value in values), (
            f"{os.path.basename(path)}: {field} values must be non-empty strings")


@pytest.mark.parametrize(
    ("pattern_id", "expected_sources"),
    sorted(REQUIRED_EVIDENCE_GATES.items()),
)
def test_animation_dependent_patterns_have_required_evidence_gates(
        pattern_id, expected_sources):
    """The six known source traps must never fall back to visual guesswork."""
    path = _path_for_id(pattern_id)
    metadata = _metadata(path)
    assert set(metadata["evaluable_from"]) == expected_sources
    assert len(metadata["evidence_requirements"]) >= 2
    assert len(metadata["not_evaluable_when"]) >= 2
    assert "## Evidence Gate" in _read(path)


def test_evidence_source_enum_is_documented_in_index():
    index = _read(INDEX)
    section = index[index.index("## Evidence-Source Contract"):
                    index.index("## Pattern Catalog")]
    for source in EVIDENCE_SOURCE_VALUES:
        assert f"`{source}`" in section, f"index does not document {source!r}"


def test_unobservable_files_match_the_index():
    """The index's go-live tables are what a reader consults; the per-file
    `observable: false` flag is what a scorer consults. Drift between them means
    an entry gets scored that the index says cannot be, or vice versa.
    """
    flagged = {str(_front(f, "id")) for f in ENTRY_FILES
               if _front(f, "observable") == "false"}
    index = _read(INDEX)
    section = index[index.index("## Unobservable Patterns"):]
    listed = set(re.findall(r"^\| ([a-z0-9-]+) \|", section, re.M))
    assert flagged == listed, (
        f"only in files: {sorted(flagged - listed)}; "
        f"only in index: {sorted(listed - flagged)}")


def test_index_summary_statistics_are_accurate():
    """The counts are quoted into briefs and skill prose; a stale total sends
    scorers looking for entries that do not exist."""
    index = _read(INDEX)
    total = len(ENTRY_FILES)
    anti = len(ANTI_FILES)
    unobs = sum(1 for f in ENTRY_FILES if _front(f, "observable") == "false")
    unobs_anti = sum(1 for f in ANTI_FILES if _front(f, "observable") == "false")
    assert f"**Total entries:** {total} ({total - anti} patterns + {anti} antipatterns)" in index
    assert (f"**Observable (vault-scorable):** {total - unobs} "
            f"({total - anti - (unobs - unobs_anti)} patterns + "
            f"{anti - unobs_anti} antipatterns)") in index
    assert (f"**Unobservable (go-live checklist):** {unobs} "
            f"({unobs - unobs_anti} patterns + {unobs_anti} antipatterns)") in index

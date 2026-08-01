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
    assert len(parts) == 3, f"{path}: missing YAML frontmatter"
    return yaml.safe_load(parts[1])


def _entry(pattern_id):
    return next(path for path in ENTRY_FILES if _metadata(path)["id"] == pattern_id)


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


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_type_matches_anti_prefix(path):
    """`_anti_` prefix and `type:` must agree — a scorer that trusts one and a
    validator that trusts the other would disagree about what may be scored."""
    declared = _front(path, "type")
    is_anti = os.path.basename(path).startswith("_anti_")
    assert declared == ("antipattern" if is_anti else "pattern"), (
        f"{os.path.basename(path)}: type is {declared!r}")


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


def test_evidence_channels_use_the_closed_source_channel_vocabulary():
    allowed = {
        "transcript",
        "timed_transcript",
        "slides",
        "slide_sequence",
        "video",
        "talk_metadata",
    }
    for path in ENTRY_FILES:
        channels = _metadata(path).get("evidence_channels")
        if _metadata(path).get("observable") is not False:
            assert isinstance(channels, list) and channels, (
                f"{os.path.basename(path)}: every observable entry needs a "
                "non-empty evidence_channels list")
            assert set(channels) <= allowed, (
                f"{os.path.basename(path)}: unknown channels {set(channels) - allowed}")


def test_metadata_channel_declares_the_fields_it_can_use():
    for path in ENTRY_FILES:
        metadata = _metadata(path)
        channels = metadata.get("evidence_channels") or []
        fields = metadata.get("evidence_metadata_fields") or []
        assert bool(fields) == ("talk_metadata" in channels), (
            f"{os.path.basename(path)}: talk_metadata and evidence_metadata_fields "
            "must be declared together")
        assert len(fields) == len(set(fields)), (
            f"{os.path.basename(path)}: duplicate evidence metadata fields")


@pytest.mark.parametrize(
    "pattern_id,channels",
    [
        ("opening-punch", {"timed_transcript", "slides", "video"}),
        ("call-to-adventure", {"timed_transcript", "video"}),
        ("progressive-reveal", {"slide_sequence", "video"}),
        ("composite-animation", {"video"}),
        ("preroll", {"video"}),
        ("make-it-rain", {"video"}),
        ("weatherman", {"video"}),
        ("ant-fonts", {"slides", "video"}),
        ("three-part-close", {"slide_sequence", "video"}),
        ("screen-blackout", {"video"}),
        ("takahashi", {"slides", "slide_sequence", "video"}),
    ],
)
def test_channel_sensitive_patterns_cannot_fall_back_to_transcript_guessing(
        pattern_id, channels):
    assert set(_metadata(_entry(pattern_id))["evidence_channels"]) == channels


def test_hidden_process_and_provenance_ids_are_not_auto_scorable():
    hidden = {
        "abstract-attorney",
        "borrowed-shoes",
        "concurrent-creation",
        "crucible",
        "fourthought",
        "know-your-audience",
        "peer-review",
        "proposed",
        "required",
        "social-media-advertising",
    }
    assert {
        pattern_id
        for pattern_id in hidden
        if _metadata(_entry(pattern_id)).get("observable") is not False
    } == set()


@pytest.mark.parametrize(
    "pattern_id,anchors",
    [
        ("takahashi", ("one word, phrase, or image per slide", "hundreds of slides")),
        ("cookie-cutter", ("forcing each idea into exactly one slide",)),
        ("progressive-reveal", ("same base image", "adding one annotation per slide")),
        ("meme-as-argument", ("internet memes", "argumentative devices")),
        ("dead-demo", ("time filler", "no narrative connection")),
        ("three-part-close", ("three distinct slides", "summary, call to action, thanks")),
        ("anti-sell", ("products, employer, or credentials", "expects a pitch")),
        ("negative-ignorance", ('who here is not familiar with x?',)),
        ("shortchanged", ("last-minute reduction", "previous speakers running long")),
    ],
)
def test_stable_ids_retain_their_distinguishing_source_meaning(pattern_id, anchors):
    text = _read(_entry(pattern_id)).casefold()
    for anchor in anchors:
        assert anchor.casefold() in text, f"{pattern_id}: missing source-meaning anchor {anchor!r}"

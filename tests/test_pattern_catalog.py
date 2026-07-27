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

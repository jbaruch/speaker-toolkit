"""Contract tests for reading a markdown-authored deck's source.

Every deck here is built in the test. Nothing renders, nothing shells out, and
no fixture depends on a markdown tool being installed.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
markdown_deck = importlib.import_module("markdown_deck")


PRESENTERM_DECK = """\
---
title: Cracking Java Snapshots
author: A Speaker
---

# Opening

first point

<!-- pause -->

second point

<!-- end_slide -->

# Demo

```bash
---
echo "a horizontal rule inside a fence is not a slide break"
---
```

<!-- end_slide -->

# Close

thanks
"""

SLIDEV_DECK = """\
---
theme: seriph
mdc: true
---

# Title

intro

---
layout: two-cols
---

# Two columns

::right::

right side

---

# Plain slide

<v-click>

revealed later

</v-click>
"""

MARP_DECK = """\
---
marp: true
theme: default
---

# One

---

# Two

---

# Three
"""

REVEAL_MD_DECK = """\
# Horizontal one

<!-- .element: class="fragment" -->

--

# Vertical under one

---

# Horizontal two
"""


def test_presenterm_deck_is_named_by_its_slide_terminator():
    decision = markdown_deck.detect_flavor(PRESENTERM_DECK)

    assert decision.flavor == markdown_deck.PRESENTERM
    assert decision.decided_by == "body_marker"
    assert decision.evidence == "<!-- end_slide -->"


def test_marp_deck_is_named_by_its_required_headmatter_directive():
    decision = markdown_deck.detect_flavor(MARP_DECK)

    assert decision.flavor == markdown_deck.MARP
    assert decision.decided_by == "headmatter_key"
    assert decision.evidence == "marp"


def test_slidev_deck_is_named_by_its_own_headmatter_keys():
    decision = markdown_deck.detect_flavor(SLIDEV_DECK)

    assert decision.flavor == markdown_deck.SLIDEV
    assert decision.evidence in {"mdc", "::right::", "<v-click"}


def test_reveal_md_deck_is_named_by_its_slide_attribute_comments():
    decision = markdown_deck.detect_flavor(REVEAL_MD_DECK)

    assert decision.flavor == markdown_deck.REVEAL_MD


def test_a_sibling_manifest_names_the_flavor_of_an_unmarked_deck(tmp_path):
    deck = tmp_path / "slides.md"
    deck.write_text("# Only a heading\n\n---\n\n# And another\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"devDependencies": {"@slidev/cli": "^0.49.0"}}',
        encoding="utf-8",
    )

    decision = markdown_deck.detect_flavor(
        deck.read_text(encoding="utf-8"),
        deck_path=deck,
    )

    assert decision.flavor == markdown_deck.SLIDEV
    assert decision.decided_by == "sibling_manifest"
    assert decision.evidence == "@slidev/cli"


def test_an_unmarked_deck_is_refused_rather_than_guessed():
    with pytest.raises(markdown_deck.MarkdownDeckError) as excinfo:
        markdown_deck.detect_flavor("# Just a heading\n\nand a paragraph\n")

    assert "--flavor" in str(excinfo.value)


def test_a_deck_marked_for_two_tools_is_refused_rather_than_ranked():
    hybrid = MARP_DECK + "\n<!-- end_slide -->\n"

    with pytest.raises(markdown_deck.MarkdownDeckError) as excinfo:
        markdown_deck.detect_flavor(hybrid)

    message = str(excinfo.value)
    assert "marp" in message
    assert "presenterm" in message


def test_presenterm_headmatter_with_a_title_renders_its_own_slide():
    structure = markdown_deck.read_deck(PRESENTERM_DECK, markdown_deck.PRESENTERM)

    # One intro slide from the headmatter plus the three authored slides.
    assert structure.slide_count == 4


def test_presenterm_headmatter_without_intro_keys_adds_no_slide():
    deck = PRESENTERM_DECK.replace("title: Cracking Java Snapshots\n", "").replace(
        "author: A Speaker\n", "theme:\n  name: dark\n"
    )

    structure = markdown_deck.read_deck(deck, markdown_deck.PRESENTERM)

    assert structure.slide_count == 3


def test_a_rule_inside_a_code_fence_is_not_a_slide_break():
    fenced = MARP_DECK.replace(
        "# Two",
        "# Two\n\n```yaml\n---\nnot: a slide break\n---\n```",
    )

    structure = markdown_deck.read_deck(fenced, markdown_deck.MARP)

    assert structure.slide_count == 3


def test_a_reveal_marker_inside_a_code_fence_is_not_a_reveal():
    fenced = PRESENTERM_DECK.replace(
        "# Close",
        "# Close\n\n```markdown\n<!-- pause -->\n```",
    )

    structure = markdown_deck.read_deck(fenced, markdown_deck.PRESENTERM)

    assert structure.to_dict()["reveal_marker_total"] == 1


def test_slidev_per_slide_frontmatter_closes_without_opening_a_slide():
    structure = markdown_deck.read_deck(SLIDEV_DECK, markdown_deck.SLIDEV)

    assert structure.slide_count == 3


def test_reveal_md_counts_vertical_slides_as_slides():
    structure = markdown_deck.read_deck(REVEAL_MD_DECK, markdown_deck.REVEAL_MD)

    assert structure.slide_count == 3


def test_marp_counts_every_rule_as_a_page_break():
    structure = markdown_deck.read_deck(MARP_DECK, markdown_deck.MARP)

    assert structure.slide_count == 3


def test_reveal_markers_are_counted_per_slide():
    structure = markdown_deck.read_deck(PRESENTERM_DECK, markdown_deck.PRESENTERM)
    payload = structure.to_dict()

    assert payload["reveal_marker_total"] == 1
    assert payload["slides_with_reveal_markers"] == 1
    assert [slide["reveal_markers"] for slide in payload["slides"]] == [0, 1, 0, 0]


def test_marp_declares_no_reveal_markers_its_export_would_preserve():
    structure = markdown_deck.read_deck(
        MARP_DECK.replace("# Two", "* one\n* two\n\n# Two"),
        markdown_deck.MARP,
    )

    assert structure.to_dict()["reveal_marker_total"] == 0


def test_an_implicit_reveal_switch_makes_the_marker_count_a_floor():
    deck = (
        "---\noptions:\n  incremental_lists: true\n---\n\n"
        "# One\n\n* a\n* b\n\n<!-- end_slide -->\n\n# Two\n"
    )

    structure = markdown_deck.read_deck(deck, markdown_deck.PRESENTERM)

    assert structure.reveal_markers_are_a_floor is True
    assert structure.floor_causes == ("options.incremental_lists",)


def test_unparseable_headmatter_is_reported_rather_than_swallowed():
    deck = "---\n: : not yaml : :\n\t- broken\n---\n\n# One\n"

    structure = markdown_deck.read_deck(deck, markdown_deck.PRESENTERM)

    assert structure.headmatter_readable is False


def test_an_unknown_flavor_is_refused():
    with pytest.raises(markdown_deck.MarkdownDeckError) as excinfo:
        markdown_deck.read_deck("# One\n", "powerpoint")

    assert "powerpoint" in str(excinfo.value)


def test_every_declared_flavor_has_a_reveal_vocabulary():
    for flavor in markdown_deck.FLAVORS:
        assert flavor in markdown_deck._REVEAL_PATTERNS


def test_a_v_clicks_block_counts_once_not_twice():
    """`<v-clicks>` contains `<v-click`; two tokens once scored it twice."""
    deck = SLIDEV_DECK.replace(
        "<v-click>\n\nrevealed later\n\n</v-click>",
        "<v-clicks>\n\n- one\n- two\n\n</v-clicks>",
    )

    structure = markdown_deck.read_deck(deck, markdown_deck.SLIDEV)

    assert structure.to_dict()["reveal_marker_total"] == 1


def test_slidev_click_spellings_each_count_once():
    deck = (
        "---\nmdc: true\n---\n\n"
        "# One\n\n"
        '<div v-click="3">a</div>\n'
        "<v-switch>b</v-switch>\n"
        "<div v-after>c</div>\n"
        "<v-clicks>\n- d\n</v-clicks>\n"
    )

    structure = markdown_deck.read_deck(deck, markdown_deck.SLIDEV)

    assert structure.to_dict()["reveal_marker_total"] == 4


def test_an_imported_slide_file_makes_the_slide_count_a_floor():
    deck = SLIDEV_DECK + "\n---\nsrc: ./pages/imported-slides.md\n---\n\n"

    payload = markdown_deck.read_deck(deck, markdown_deck.SLIDEV).to_dict()

    assert payload["imported_files"] == ["./pages/imported-slides.md"]
    assert payload["slide_count_is_a_floor"] is True


def test_a_deck_that_imports_nothing_is_not_a_floor():
    payload = markdown_deck.read_deck(SLIDEV_DECK, markdown_deck.SLIDEV).to_dict()

    assert payload["imported_files"] == []
    assert payload["slide_count_is_a_floor"] is False


def test_the_reported_span_brackets_exactly_the_slide_s_own_lines():
    """1-based inclusive, separator excluded — for every slide, not just the last."""
    lines = MARP_DECK.splitlines()
    structure = markdown_deck.read_deck(MARP_DECK, markdown_deck.MARP)

    spans = [
        lines[slide.first_line - 1 : slide.last_line] for slide in structure.slides
    ]

    assert [line for span in spans for line in span if line.startswith("#")] == [
        "# One",
        "# Two",
        "# Three",
    ]
    # The separator that ended each slide belongs to no slide's span.
    assert not [line for span in spans for line in span if line.strip() == "---"]

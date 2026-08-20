"""End-to-end renders against the real markdown deck tools.

`tests/test_render_markdown_deck.py` drives stand-ins to pin the wrapper's
contract — lane refusal, failure containment, the receipt. These drive the
actual renderers, which is the only place the claim that matters is testable:
one exported page is one authored slide. A tool that starts emitting a page per
click fails here and nowhere else.

CI installs all four (`scripts/install_deck_renderers.py`). Locally they may be
absent, so each render skips on its own missing command — and
`test_ci_carries_every_renderer` fails rather than skips when the installer was
supposed to have run, so a broken install cannot pass as a quiet green.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "render-markdown-deck.py"
SPEC = importlib.util.spec_from_file_location("render_markdown_deck_live", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
render_markdown_deck = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = render_markdown_deck
SPEC.loader.exec_module(render_markdown_deck)

# Slidev and reveal-md each start a dev server and drive a headless browser; a
# cold first render pays for both. Generous rather than tuned — the point of
# the limit is that a wedged renderer fails the job instead of running out its
# 25-minute budget.
LIVE_RENDER_TIMEOUT_SEC = 600

# Three authored slides each, one of them carrying an incremental reveal, so a
# per-click export would show up as more pages than slides.
DECKS: dict[str, str] = {
    "presenterm": """\
# One

alpha

<!-- pause -->

beta

<!-- end_slide -->

# Two

gamma

<!-- end_slide -->

# Three

delta
""",
    "slidev": """\
---
theme: none
mdc: true
---

# One

alpha

---

# Two

<v-clicks>

- beta
- gamma

</v-clicks>

---

# Three

delta
""",
    "marp": """\
---
marp: true
---

# One

alpha

---

# Two

* beta
* gamma

---

# Three

delta
""",
    "reveal-md": """\
# One

alpha

---

# Two

beta

<!-- .element: class="fragment" -->

---

# Three

delta
""",
}
AUTHORED_SLIDES = 3


def _absent(flavor: str) -> list[str]:
    return render_markdown_deck.missing_commands(render_markdown_deck.RENDERERS[flavor])


@pytest.mark.parametrize("flavor", sorted(DECKS))
def test_a_real_render_emits_one_page_per_authored_slide(tmp_path, flavor):
    absent = _absent(flavor)
    if absent:
        pytest.skip(f"{flavor} renderer unavailable: {', '.join(absent)} not on PATH")
    deck = tmp_path / "slides.md"
    deck.write_text(DECKS[flavor], encoding="utf-8")

    receipt = render_markdown_deck.execute(
        deck,
        output=tmp_path / "slides" / "talk.pdf",
        flavor=flavor,
        timeout_seconds=LIVE_RENDER_TIMEOUT_SEC,
    )

    assert receipt["flavor"] == flavor
    assert receipt["rendered"] is True
    assert receipt["slide_count_basis"] == "rendered_pages"
    # The claim the whole design rests on: the export is not per-click.
    assert receipt["page_count"] == AUTHORED_SLIDES
    assert receipt["source_slide_count"] == AUTHORED_SLIDES
    assert receipt["slide_count_agrees_with_source"] is True
    assert (tmp_path / "slides" / "talk.pdf").is_file()


@pytest.mark.parametrize("flavor", sorted(DECKS))
def test_the_deck_is_detected_without_being_told(tmp_path, flavor):
    """Every fixture deck carries a marker that names its own tool."""
    deck = tmp_path / "slides.md"
    deck.write_text(DECKS[flavor], encoding="utf-8")

    receipt = render_markdown_deck.execute(
        deck,
        output=None,
        flavor=None,
        timeout_seconds=LIVE_RENDER_TIMEOUT_SEC,
    )

    assert receipt["flavor"] == flavor


@pytest.mark.skipif(
    not os.environ.get("CI"),
    reason="the renderer install runs in CI, not on a developer's machine",
)
def test_ci_carries_every_renderer():
    """A broken install must fail the job, not quietly skip the live renders."""
    missing = {flavor: _absent(flavor) for flavor in DECKS if _absent(flavor)}

    assert not missing, (
        f"scripts/install_deck_renderers.py left renderers absent: {missing}. "
        "`ci-safety` Install, Don't Skip — the live render tests must not skip "
        "in CI."
    )


@pytest.mark.skipif(
    not os.environ.get("CI"),
    reason="node is pinned by the workflow, not by a developer's machine",
)
def test_ci_runs_the_node_major_the_renderers_declare():
    """reveal-md refuses a node outside its engine range, loudly and late."""
    node = shutil.which("node")

    assert node, "the workflow must put node on PATH before the renderer tests"
    reported = subprocess.run(
        [node, "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    installer = importlib.util.spec_from_file_location(
        "install_deck_renderers_node_pin",
        Path(__file__).parents[1] / "scripts" / "install_deck_renderers.py",
    )
    assert installer is not None and installer.loader is not None
    module = importlib.util.module_from_spec(installer)
    installer.loader.exec_module(module)

    assert reported.startswith(f"v{module.REQUIRED_NODE_MAJOR}.")

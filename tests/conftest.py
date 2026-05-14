"""Shared fixtures and helpers for speaker-toolkit tests."""

import importlib.util
import os
import sys
import types

import pytest
from lxml import etree
from pptx import Presentation
from pptx.util import Inches

# ── Script import helper ──────────────────────────────────────────────

SCRIPTS_PC = os.path.join(
    os.path.dirname(__file__), os.pardir,
    "skills", "presentation-creator", "scripts",
)
SCRIPTS_VI = os.path.join(
    os.path.dirname(__file__), os.pardir,
    "skills", "vault-ingress", "scripts",
)
SCRIPTS_ILL = os.path.join(
    os.path.dirname(__file__), os.pardir,
    "skills", "illustrations", "scripts",
)


def _import_script(path, name):
    """Import a standalone .py script as a module (no package required).

    If the module name is already in `sys.modules` (typically because a
    sibling script imported it under the same name via Python's normal
    import machinery — e.g., `extract-script.py` doing
    `import outline_schema`), reuse that cached instance instead of
    overwriting it. Replacing the cached module creates two distinct
    module objects with non-identical enums/classes, which silently
    breaks `isinstance` and identity checks across tests.
    """
    path = os.path.abspath(path)
    script_dir = os.path.dirname(path)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Session-scoped script modules ────────────────────────────────────

@pytest.fixture(scope="session")
def strip_template():
    return _import_script(os.path.join(SCRIPTS_PC, "strip-template.py"), "strip_template")


@pytest.fixture(scope="session")
def delete_slides():
    return _import_script(os.path.join(SCRIPTS_PC, "delete-slides.py"), "delete_slides")


@pytest.fixture(scope="session")
def reorder_slides():
    return _import_script(os.path.join(SCRIPTS_PC, "reorder-slides.py"), "reorder_slides")


@pytest.fixture(scope="session")
def insert_placeholder():
    return _import_script(
        os.path.join(SCRIPTS_PC, "insert-placeholder-slides.py"), "insert_placeholder"
    )


@pytest.fixture(scope="session")
def inject_speaker_notes():
    return _import_script(
        os.path.join(SCRIPTS_PC, "inject-speaker-notes.py"), "inject_speaker_notes"
    )


@pytest.fixture(scope="session")
def generate_qr():
    return _import_script(os.path.join(SCRIPTS_PC, "generate-qr.py"), "generate_qr")


@pytest.fixture(scope="session")
def pptx_extraction():
    return _import_script(os.path.join(SCRIPTS_VI, "pptx-extraction.py"), "pptx_extraction")


@pytest.fixture(scope="session")
def vtt_cleanup():
    return _import_script(os.path.join(SCRIPTS_VI, "vtt-cleanup.py"), "vtt_cleanup")


@pytest.fixture(scope="session")
def extract_resources():
    return _import_script(
        os.path.join(SCRIPTS_PC, "extract-resources.py"), "extract_resources"
    )


@pytest.fixture(scope="session")
def guardrail_check():
    return _import_script(os.path.join(SCRIPTS_PC, "guardrail-check.py"), "guardrail_check")


@pytest.fixture(scope="session")
def outline_schema():
    return _import_script(os.path.join(SCRIPTS_PC, "outline_schema.py"), "outline_schema")


@pytest.fixture(scope="session")
def extract_script():
    return _import_script(os.path.join(SCRIPTS_PC, "extract-script.py"), "extract_script")


@pytest.fixture(scope="session")
def extract_slides():
    return _import_script(os.path.join(SCRIPTS_PC, "extract-slides.py"), "extract_slides")


@pytest.fixture(scope="session")
def extract_narrative():
    return _import_script(os.path.join(SCRIPTS_PC, "extract-narrative.py"), "extract_narrative")


@pytest.fixture(scope="session")
def check_rhetorical():
    return _import_script(os.path.join(SCRIPTS_PC, "check-rhetorical.py"), "check_rhetorical")


@pytest.fixture(scope="session")
def generate_illustrations():
    return _import_script(
        os.path.join(SCRIPTS_ILL, "generate-illustrations.py"), "generate_illustrations"
    )


@pytest.fixture(scope="session")
def generate_thumbnail():
    return _import_script(
        os.path.join(SCRIPTS_ILL, "generate-thumbnail.py"), "generate_thumbnail"
    )


@pytest.fixture(scope="session")
def pptx_repair():
    return _import_script(os.path.join(SCRIPTS_PC, "_pptx_repair.py"), "_pptx_repair")


@pytest.fixture(scope="session")
def video_slide_extraction():
    return _import_script(
        os.path.join(SCRIPTS_VI, "video-slide-extraction.py"), "video_slide_extraction"
    )


@pytest.fixture(scope="session")
def export_pdf():
    return _import_script(os.path.join(SCRIPTS_PC, "export-pdf.py"), "export_pdf")


@pytest.fixture(scope="session")
def apply_illustrations():
    return _import_script(
        os.path.join(SCRIPTS_ILL, "apply-illustrations-to-deck.py"), "apply_illustrations"
    )


@pytest.fixture(scope="session")
def suggest_scrim_color():
    return _import_script(
        os.path.join(SCRIPTS_ILL, "suggest-scrim-color.py"), "suggest_scrim_color"
    )


@pytest.fixture(scope="session")
def generate_talk_timings():
    return _import_script(
        os.path.join(SCRIPTS_PC, "generate-talk-timings.py"), "generate_talk_timings"
    )


# ── PPTX fixture builders ────────────────────────────────────────────

NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _make_deck(slide_count, *, slide_width=None, slide_height=None):
    """Create a minimal PPTX with *slide_count* blank slides."""
    prs = Presentation()
    if slide_width:
        prs.slide_width = slide_width
    if slide_height:
        prs.slide_height = slide_height
    blank = prs.slide_layouts[6]  # Blank layout
    for _ in range(slide_count):
        prs.slides.add_slide(blank)
    return prs


@pytest.fixture
def five_slide_deck(tmp_path):
    """Return (Presentation, path) for a 5-slide deck saved to tmp_path."""
    prs = _make_deck(5)
    path = str(tmp_path / "five.pptx")
    prs.save(path)
    return prs, path


@pytest.fixture
def three_slide_deck(tmp_path):
    """Return (Presentation, path) for a 3-slide deck saved to tmp_path."""
    prs = _make_deck(3)
    path = str(tmp_path / "three.pptx")
    prs.save(path)
    return prs, path


@pytest.fixture
def deck_with_text(tmp_path):
    """Return (Presentation, path) for a 3-slide deck with text on each slide."""
    prs = Presentation()
    layout = prs.slide_layouts[1]  # Title + Content
    for i in range(3):
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = f"Slide {i + 1} Title"
    path = str(tmp_path / "text_deck.pptx")
    prs.save(path)
    return prs, path


def make_deck(slide_count):
    """Public helper for tests that need a Presentation without saving."""
    return _make_deck(slide_count)

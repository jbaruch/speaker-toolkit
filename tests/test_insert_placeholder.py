"""Tests for insert-placeholder-slides.py — placeholder slide insertion."""

from pptx import Presentation
from pptx.dml.color import RGBColor

from conftest import make_deck


def test_yellow_background(insert_placeholder, tmp_path):
    prs = make_deck(3)
    slide = insert_placeholder.add_placeholder_slide(prs, "Test Title")
    # Check that a shape has the yellow fill
    found_yellow = False
    for shape in slide.shapes:
        try:
            if shape.fill.fore_color.rgb == RGBColor(0xFF, 0xF2, 0x9E):
                found_yellow = True
                break
        except Exception:
            continue
    assert found_yellow


def test_placeholder_title_text(insert_placeholder, tmp_path):
    prs = make_deck(3)
    slide = insert_placeholder.add_placeholder_slide(prs, "My Section")
    texts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            texts.append(shape.text_frame.text)
    assert any("[PLACEHOLDER] My Section" in t for t in texts)


def test_subtitle_present(insert_placeholder, tmp_path):
    prs = make_deck(3)
    slide = insert_placeholder.add_placeholder_slide(prs, "Title", "Subtitle text")
    texts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            texts.append(shape.text_frame.text)
    assert any("Subtitle text" in t for t in texts)


def test_multi_insert_positioning(insert_placeholder, tmp_path):
    prs = make_deck(3)
    path = str(tmp_path / "deck.pptx")
    prs.save(path)

    prs2 = Presentation(path)
    # Insert at positions 1 and 3 (1-indexed, final positions)
    insert_placeholder.add_placeholder_slide(prs2, "Second insert")
    insert_placeholder.move_slide(prs2, len(prs2.slides) - 1, 2)  # pos 3 (0-indexed=2)
    insert_placeholder.add_placeholder_slide(prs2, "First insert")
    insert_placeholder.move_slide(prs2, len(prs2.slides) - 1, 0)  # pos 1 (0-indexed=0)

    assert len(prs2.slides) == 5


def test_slide_count_increases(insert_placeholder, tmp_path):
    prs = make_deck(3)
    insert_placeholder.add_placeholder_slide(prs, "New Slide")
    assert len(prs.slides) == 4


def test_move_slide(insert_placeholder, tmp_path):
    prs = make_deck(3)
    # Add a placeholder at the end, then move to front
    insert_placeholder.add_placeholder_slide(prs, "Should be first")
    insert_placeholder.move_slide(prs, 3, 0)

    # Verify the slide was moved — the new first slide should have our text
    first_slide = prs.slides[0]
    texts = []
    for shape in first_slide.shapes:
        if shape.has_text_frame:
            texts.append(shape.text_frame.text)
    assert any("[PLACEHOLDER] Should be first" in t for t in texts)


def test_output_flag(insert_placeholder, tmp_path):
    """Saving to a different output path preserves the original."""
    prs = make_deck(3)
    original = str(tmp_path / "original.pptx")
    prs.save(original)

    prs2 = Presentation(original)
    insert_placeholder.add_placeholder_slide(prs2, "Added")
    output = str(tmp_path / "modified.pptx")
    prs2.save(output)

    # Original unchanged
    assert len(Presentation(original).slides) == 3
    # Output has the new slide
    assert len(Presentation(output).slides) == 4

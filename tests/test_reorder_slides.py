"""Tests for reorder-slides.py — slide reordering."""

import pytest
from pptx import Presentation

from conftest import make_deck


def _get_slide_rids(prs):
    """Return ordered list of relationship IDs for all slides."""
    ns_r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    return [s.get(f'{{{ns_r}}}id') for s in prs.slides._sldIdLst]


def test_forward_move(reorder_slides, tmp_path):
    prs = make_deck(5)
    rids = _get_slide_rids(prs)
    reorder_slides.reorder_slide(prs, 0, 3)
    new_rids = _get_slide_rids(prs)
    # Slide 0 moved to position 3
    assert new_rids[3] == rids[0]


def test_backward_move(reorder_slides, tmp_path):
    prs = make_deck(5)
    rids = _get_slide_rids(prs)
    reorder_slides.reorder_slide(prs, 4, 1)
    new_rids = _get_slide_rids(prs)
    assert new_rids[1] == rids[4]


def test_same_position_noop(reorder_slides, tmp_path):
    prs = make_deck(5)
    rids_before = _get_slide_rids(prs)
    reorder_slides.reorder_slide(prs, 2, 2)
    rids_after = _get_slide_rids(prs)
    assert rids_before == rids_after


def test_out_of_range_raises(reorder_slides, tmp_path):
    prs = make_deck(3)
    with pytest.raises(IndexError):
        reorder_slides.reorder_slide(prs, 99, 0)


def test_move_to_end(reorder_slides, tmp_path):
    prs = make_deck(5)
    rids = _get_slide_rids(prs)
    reorder_slides.reorder_slide(prs, 0, 99)  # beyond range → append
    new_rids = _get_slide_rids(prs)
    assert new_rids[-1] == rids[0]


def test_slide_count_unchanged(reorder_slides, tmp_path):
    prs = make_deck(5)
    reorder_slides.reorder_slide(prs, 1, 3)
    assert len(prs.slides) == 5

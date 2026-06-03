"""Tests for notes-to-packed.py — 0-based notes JSON to the SetSpeakerNotes wire format."""

import pytest

RS = "\x1e"
US = "\x1f"


def test_packs_one_based_sorted_dropping_empties(notes_to_packed):
    # 0-based keys -> 1-based; empty/None dropped; sorted by slide number.
    packed = notes_to_packed.pack_notes(
        {"2": "third", "0": "", "1": "second", "4": None}
    )
    assert packed == f"2{US}second{RS}3{US}third"


def test_single_note(notes_to_packed):
    assert notes_to_packed.pack_notes({"0": "intro"}) == f"1{US}intro"


def test_all_empty_yields_empty_string(notes_to_packed):
    assert notes_to_packed.pack_notes({"0": "", "1": None}) == ""


def test_multiline_unicode_text_preserved(notes_to_packed):
    text = "Line one — with an em-dash.\nLine two: “smart quotes”."
    packed = notes_to_packed.pack_notes({"0": text})
    assert packed == f"1{US}{text}"


def test_non_object_raises(notes_to_packed):
    with pytest.raises(ValueError):
        notes_to_packed.pack_notes(["not", "a", "map"])


def test_non_integer_key_raises(notes_to_packed):
    with pytest.raises(ValueError):
        notes_to_packed.pack_notes({"intro": "text"})


def test_non_string_text_raises(notes_to_packed):
    with pytest.raises(ValueError):
        notes_to_packed.pack_notes({"0": 123})


def test_reserved_control_char_in_text_raises(notes_to_packed):
    with pytest.raises(ValueError):
        notes_to_packed.pack_notes({"0": f"bad{RS}text"})
    with pytest.raises(ValueError):
        notes_to_packed.pack_notes({"0": f"bad{US}text"})

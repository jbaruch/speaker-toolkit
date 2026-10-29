"""Tests for notes-to-packed.py — 0-based notes JSON to the packed format and the notes driver arguments."""

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


def test_negative_index_rejected_upfront(notes_to_packed):
    # 0-based indices must be >= 0 — reject here, not later inside PowerPoint.
    with pytest.raises(ValueError):
        notes_to_packed.pack_notes({"-1": "text"})


def test_reserved_control_char_in_text_raises(notes_to_packed):
    with pytest.raises(ValueError):
        notes_to_packed.pack_notes({"0": f"bad{RS}text"})
    with pytest.raises(ValueError):
        notes_to_packed.pack_notes({"0": f"bad{US}text"})


def _deck(tmp_path, slide_ids):
    """Write a minimal .pptx-shaped zip whose presentation.xml lists slide_ids."""
    import zipfile

    ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i}"/>' for i in range(slide_ids))
    xml = (
        f'<p:presentation xmlns:p="{ns}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>"
    )
    path = tmp_path / "deck.pptx"
    with zipfile.ZipFile(path, "w") as deck:
        deck.writestr("ppt/presentation.xml", xml)
    return path


def test_driver_args_are_one_based_pairs_with_unicode_intact(notes_to_packed):
    items = notes_to_packed.driver_args(
        {"2": "third", "0": "", "1": "PORT → Factories ⚡ 日本"}, slide_count=5
    )
    assert items == ["2", "PORT → Factories ⚡ 日本", "3", "third"]


def test_driver_args_keep_separator_chars_the_packed_format_rejects(notes_to_packed):
    # Arguments need no RS/US framing, so those chars pass through untouched.
    assert notes_to_packed.driver_args({"0": f"a{RS}b{US}c"}, slide_count=1) == [
        "1",
        f"a{RS}b{US}c",
    ]


def test_driver_args_reject_slide_past_the_deck(notes_to_packed):
    with pytest.raises(ValueError, match="has 3 slides"):
        notes_to_packed.driver_args({"3": "fourth"}, slide_count=3)


def test_driver_args_reject_nul(notes_to_packed):
    with pytest.raises(ValueError, match="NUL"):
        notes_to_packed.driver_args({"0": "bad\x00text"}, slide_count=1)


def test_driver_args_reject_over_budget(notes_to_packed):
    big = "x" * (notes_to_packed.DRIVER_ARGS_BUDGET + 1)
    with pytest.raises(ValueError, match="split notes.json"):
        notes_to_packed.driver_args({"0": big}, slide_count=1)


def test_driver_args_share_note_validation(notes_to_packed):
    with pytest.raises(ValueError):
        notes_to_packed.driver_args({"-1": "text"}, slide_count=3)
    with pytest.raises(ValueError):
        notes_to_packed.driver_args({"intro": "text"}, slide_count=3)


def test_deck_slide_count_reads_presentation_xml(notes_to_packed, tmp_path):
    assert notes_to_packed.deck_slide_count(_deck(tmp_path, 3)) == 3


def test_deck_slide_count_rejects_non_pptx(notes_to_packed, tmp_path):
    not_a_deck = tmp_path / "notes.pptx"
    not_a_deck.write_text("plain text", encoding="utf-8")
    with pytest.raises(ValueError, match="not a .pptx"):
        notes_to_packed.deck_slide_count(not_a_deck)


def test_cli_driver_args_writes_nul_terminated_items(notes_to_packed, tmp_path, capsys):
    import json

    notes = tmp_path / "notes.json"
    notes.write_text(
        json.dumps({"0": "line one\nline two →", "2": "third"}), encoding="utf-8"
    )
    out = tmp_path / "out.args"
    deck = _deck(tmp_path, 3)
    rc = notes_to_packed.main(
        ["--driver-args", "--deck", str(deck), str(notes), str(out)]
    )
    assert rc == 0
    assert (
        out.read_text(encoding="utf-8") == "1\x00line one\nline two →\x003\x00third\x00"
    )
    assert json.loads(capsys.readouterr().out) == {"records": 2, "output": str(out)}


def test_cli_driver_args_out_of_range_exits_1(notes_to_packed, tmp_path, capsys):
    import json

    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"9": "x"}), encoding="utf-8")
    out = tmp_path / "out.args"
    rc = notes_to_packed.main(
        ["--driver-args", "--deck", str(_deck(tmp_path, 3)), str(notes), str(out)]
    )
    assert rc == 1
    assert "has 3 slides" in capsys.readouterr().err
    assert not out.exists()


def test_cli_packed_mode_unchanged(notes_to_packed, tmp_path, capsys):
    import json

    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"1": "second"}), encoding="utf-8")
    out = tmp_path / "out.packed"
    assert notes_to_packed.main([str(notes), str(out)]) == 0
    assert out.read_text(encoding="utf-8") == f"2{US}second"

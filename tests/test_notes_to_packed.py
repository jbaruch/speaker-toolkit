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


TRANSITIONAL = "http://schemas.openxmlformats.org/presentationml/2006/main"
STRICT = "http://purl.oclc.org/ooxml/presentationml/main"


def _deck(tmp_path, slide_ids, ns=TRANSITIONAL, name="deck.pptx"):
    """Write a minimal .pptx-shaped zip whose presentation.xml lists slide_ids."""
    import zipfile

    ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i}"/>' for i in range(slide_ids))
    xml = (
        f'<p:presentation xmlns:p="{ns}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>"
    )
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as deck:
        deck.writestr("ppt/presentation.xml", xml)
    return path


def test_driver_args_are_one_item_per_slide_with_unicode_intact(notes_to_packed):
    items = notes_to_packed.driver_args(
        {"2": "third", "0": "", "1": "PORT → Factories ⚡ 日本"}, slide_count=5
    )
    # Item N is slide N; "" leaves that slide's notes unchanged.
    assert items == ["", "PORT → Factories ⚡ 日本", "third", "", ""]


def test_driver_args_for_empty_map_leave_every_slide_unchanged(notes_to_packed):
    assert notes_to_packed.driver_args({}, slide_count=3) == ["", "", ""]


def test_driver_args_keep_separator_chars_the_packed_format_rejects(notes_to_packed):
    # Arguments need no RS/US framing, so those chars pass through untouched.
    assert notes_to_packed.driver_args({"0": f"a{RS}b{US}c"}, slide_count=1) == [
        f"a{RS}b{US}c"
    ]


def test_driver_args_reject_slide_past_the_deck(notes_to_packed):
    with pytest.raises(ValueError, match="has 3 slides"):
        notes_to_packed.driver_args({"3": "fourth"}, slide_count=3)


def test_driver_args_reject_nul(notes_to_packed):
    with pytest.raises(ValueError, match="NUL"):
        notes_to_packed.driver_args({"0": "bad\x00text"}, slide_count=1)


def test_driver_args_reject_a_single_note_over_budget_with_shorten_advice(
    notes_to_packed,
):
    big = "x" * (notes_to_packed.DRIVER_ARGS_BUDGET + 1)
    with pytest.raises(ValueError, match="notes for slide 1 .* shorten that note"):
        notes_to_packed.driver_args({"1": big}, slide_count=2)


def test_note_that_fits_only_without_the_other_slides_terminators_is_shortened(
    notes_to_packed,
):
    # On a 2-slide deck one run carries the other slide's empty item too, so a
    # note sized to the bare budget can never fit, however the map is split.
    budget = notes_to_packed.DRIVER_ARGS_BUDGET
    exact = "x" * (budget - 1)
    with pytest.raises(ValueError, match="notes for slide 0 .* shorten that note"):
        notes_to_packed.driver_args({"0": exact}, slide_count=2)
    # One byte less than the 2-slide capacity fits.
    assert notes_to_packed.driver_args({"0": "x" * (budget - 2)}, slide_count=2)


def test_three_notes_over_half_the_budget_get_three_chained_maps(notes_to_packed):
    # No two fit together, so two maps can never hold them.
    big = "x" * (notes_to_packed.DRIVER_ARGS_BUDGET * 6 // 10)
    with pytest.raises(ValueError) as exc:
        notes_to_packed.driver_args({"0": big, "1": big, "2": big}, slide_count=3)
    message = str(exc.value)
    assert "map 1: slides 0; map 2: slides 1; map 3: slides 2" in message
    assert "passing each run's output deck as the next run's base" in message


def test_split_plan_runs_each_fit_and_cover_every_noted_slide_once(notes_to_packed):
    budget = notes_to_packed.DRIVER_ARGS_BUDGET
    sizes = [budget // 4] * 9 + [0, budget // 2, 7]
    capacity = budget - len(sizes)
    runs = notes_to_packed.split_into_runs(sizes, capacity)
    assert sorted(s for run in runs for s in run) == [
        i for i, n in enumerate(sizes) if n
    ]
    assert all(sum(sizes[s] for s in run) <= capacity for run in runs)
    assert len(runs) == 4  # 2.75 budgets of text, packed into four runs


def test_over_budget_message_lists_a_plan_that_fits(notes_to_packed):
    budget = notes_to_packed.DRIVER_ARGS_BUDGET
    quarter = "x" * (budget // 4)
    notes = {str(i): quarter for i in range(9)}
    with pytest.raises(ValueError) as exc:
        notes_to_packed.driver_args(notes, slide_count=9)
    message = str(exc.value)
    assert "map 1: slides 0, 1, 2; map 2: slides 3, 4, 5; map 3: slides 6, 7, 8" in (
        message
    )


def test_driver_args_share_note_validation(notes_to_packed):
    with pytest.raises(ValueError):
        notes_to_packed.driver_args({"-1": "text"}, slide_count=3)
    with pytest.raises(ValueError):
        notes_to_packed.driver_args({"intro": "text"}, slide_count=3)


def test_deck_slide_count_reads_transitional_presentation_xml(
    notes_to_packed, tmp_path
):
    assert notes_to_packed.deck_slide_count(_deck(tmp_path, 3)) == 3


def test_deck_slide_count_reads_strict_ooxml(notes_to_packed, tmp_path):
    assert notes_to_packed.deck_slide_count(_deck(tmp_path, 4, ns=STRICT)) == 4


def test_deck_slide_count_rejects_unknown_root(notes_to_packed, tmp_path):
    deck = _deck(tmp_path, 2, ns="urn:example:not-presentationml")
    with pytest.raises(ValueError, match="unrecognized presentation.xml root"):
        notes_to_packed.deck_slide_count(deck)


def test_deck_slide_count_rejects_non_pptx(notes_to_packed, tmp_path):
    not_a_deck = tmp_path / "notes.pptx"
    not_a_deck.write_text("plain text", encoding="utf-8")
    with pytest.raises(ValueError, match="not a .pptx"):
        notes_to_packed.deck_slide_count(not_a_deck)


def test_cli_driver_args_writes_one_nul_terminated_item_per_slide(
    notes_to_packed, tmp_path, capsys
):
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
    assert out.read_text(encoding="utf-8") == "line one\nline two →\x00\x00third\x00"
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


def test_cli_unwritable_output_exits_1_with_repair(notes_to_packed, tmp_path, capsys):
    import json

    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"0": "x"}), encoding="utf-8")
    out = tmp_path / "missing-dir" / "out.args"
    rc = notes_to_packed.main(
        ["--driver-args", "--deck", str(_deck(tmp_path, 1)), str(notes), str(out)]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert f"cannot write {out}" in err
    assert "existing, writable directory" in err


def test_cli_packed_mode_unchanged(notes_to_packed, tmp_path, capsys):
    import json

    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"1": "second"}), encoding="utf-8")
    out = tmp_path / "out.packed"
    assert notes_to_packed.main([str(notes), str(out)]) == 0
    assert out.read_text(encoding="utf-8") == f"2{US}second"


def _cli(notes_to_packed, tmp_path, notes_path, deck_path):
    out = tmp_path / "out.args"
    rc = notes_to_packed.main(
        ["--driver-args", "--deck", str(deck_path), str(notes_path), str(out)]
    )
    return rc, out


def test_cli_missing_notes_file_exits_1_with_repair(notes_to_packed, tmp_path, capsys):
    rc, out = _cli(
        notes_to_packed, tmp_path, tmp_path / "nope.json", _deck(tmp_path, 1)
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "cannot read notes JSON" in err
    assert "existing, readable notes.json" in err
    assert not out.exists()


def test_cli_invalid_json_exits_1_with_repair(notes_to_packed, tmp_path, capsys):
    notes = tmp_path / "notes.json"
    notes.write_text("{not json", encoding="utf-8")
    rc, out = _cli(notes_to_packed, tmp_path, notes, _deck(tmp_path, 1))
    assert rc == 1
    err = capsys.readouterr().err
    assert "is not valid JSON" in err
    assert "regenerate it" in err
    assert not out.exists()


def test_cli_non_utf8_notes_exit_1_with_repair(notes_to_packed, tmp_path, capsys):
    notes = tmp_path / "notes.json"
    notes.write_bytes(b'{"0": "caf\xe9"}')
    rc, _ = _cli(notes_to_packed, tmp_path, notes, _deck(tmp_path, 1))
    assert rc == 1
    assert "re-save it as UTF-8" in capsys.readouterr().err


def test_cli_missing_deck_exits_1_with_repair(notes_to_packed, tmp_path, capsys):
    import json

    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"0": "x"}), encoding="utf-8")
    rc, out = _cli(notes_to_packed, tmp_path, notes, tmp_path / "nope.pptx")
    assert rc == 1
    err = capsys.readouterr().err
    assert "cannot read deck" in err
    assert "built deck copy" in err
    assert not out.exists()


def test_cli_malformed_presentation_xml_exits_1_with_repair(
    notes_to_packed, tmp_path, capsys
):
    import json
    import zipfile

    deck = tmp_path / "broken.pptx"
    with zipfile.ZipFile(deck, "w") as z:
        z.writestr("ppt/presentation.xml", "<p:presentation")
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"0": "x"}), encoding="utf-8")
    rc, out = _cli(notes_to_packed, tmp_path, notes, deck)
    assert rc == 1
    err = capsys.readouterr().err
    assert "malformed ppt/presentation.xml" in err
    assert "re-save the deck from PowerPoint" in err
    assert not out.exists()


def test_validation_messages_carry_a_repair(notes_to_packed):
    with pytest.raises(ValueError, match="0-based slide number"):
        notes_to_packed.note_pairs({"intro": "x"})
    with pytest.raises(ValueError, match="write the note as a JSON string"):
        notes_to_packed.note_pairs({"0": 1})
    with pytest.raises(ValueError, match="remove it from the note"):
        notes_to_packed.pack_notes({"0": f"a{RS}b"})
    with pytest.raises(ValueError, match="remove it from the note"):
        notes_to_packed.driver_args({"0": "a\x00b"}, slide_count=1)


def test_cli_lone_surrogate_exits_1_with_repair_in_both_modes(
    notes_to_packed, tmp_path, capsys
):
    notes = tmp_path / "notes.json"
    notes.write_text('{"0": "bad \\ud800 text"}', encoding="utf-8")
    deck = _deck(tmp_path, 1)
    for argv in (
        ["--driver-args", "--deck", str(deck), str(notes), str(tmp_path / "o.args")],
        [str(notes), str(tmp_path / "o.packed")],
    ):
        assert notes_to_packed.main(argv) == 1
        err = capsys.readouterr().err
        assert "notes for slide 0" in err
        assert "lone surrogate" in err
        assert "replace or remove it in notes.json" in err
        assert "cannot write" not in err

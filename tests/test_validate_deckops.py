"""Tests for validate-deckops.py — the deterministic deck op-sequence validator.

BuildDeck (the VBA interpreter) is manual-validation-only; this validator is the
deterministic half that catches typos / wrong arity / bad state before PowerPoint
part-builds a deck. Fields are US (\\x1f) delimited.
"""

import sys

import pytest

US = "\x1f"


def line(op, *fields):
    return US.join([op, *[str(f) for f in fields]])


# A well-formed sequence exercising every op and state dependency.
VALID = "\n".join([
    line("SLIDE", 0),
    line("TITLE", "Hello"),
    line("SUBTITLE", "World"),
    line("BODY", "Body text"),
    line("BULLET", 0, "First point"),
    line("BULLET", 1, "Sub point"),
    line("TEXT", 10, 20, 300, 80, "A box"),
    line("IMAGE", 10, 20, 100, 100, "/tmp/x.png"),
    line("SHAPE", 1, 10, 20, 50, 50),
    line("BG", 255, 242, 158),
    line("FOOTER", "footer text"),
    line("TABLE", 2, 3, 10, 20, 400, 200),
    line("CELL", 1, 1, "r1c1"),
    line("CHART", 51, 10, 20, 400, 300),
    line("CAT", "Q1"),
    line("CAT", "Q2"),
    line("SERIES", "Revenue", 10, 20),
    line("OPTIMIZE"),
    line("SLIDE", 2),
    line("TITLE", "Second slide"),
])


def test_valid_sequence_has_no_errors(validate_deckops):
    assert validate_deckops.validate_ops(VALID) == []


def test_blank_and_crlf_lines_ignored(validate_deckops):
    text = line("SLIDE", 0) + "\r\n\n   \n" + line("TITLE", "x") + "\r"
    assert validate_deckops.validate_ops(text) == []


def test_unknown_op_reported(validate_deckops):
    errors = validate_deckops.validate_ops(line("SLIDE", 0) + "\n" + line("WIDGET", "x"))
    assert any("unknown op" in e and "WIDGET" in e for e in errors)


def test_wrong_arity_too_few(validate_deckops):
    # BULLET needs 3 fields (op, level, text); give it 2.
    errors = validate_deckops.validate_ops(line("SLIDE", 0) + "\n" + line("BULLET", 0))
    assert any("BULLET" in e and "fields" in e for e in errors)


def test_wrong_arity_too_many(validate_deckops):
    # TITLE is exactly 2 fields; give it 3.
    errors = validate_deckops.validate_ops(line("SLIDE", 0) + "\n" + line("TITLE", "a", "b"))
    assert any("TITLE" in e and "fields" in e for e in errors)


def test_variadic_series_accepts_many_values(validate_deckops):
    text = "\n".join([
        line("SLIDE", 0),
        line("CHART", 51, 10, 20, 400, 300),
        line("SERIES", "S", 1, 2, 3, 4, 5),
    ])
    assert validate_deckops.validate_ops(text) == []


def test_int_field_rejects_non_integer(validate_deckops):
    # SLIDE layout index must be an int.
    errors = validate_deckops.validate_ops(line("SLIDE", "abc"))
    assert any("integer" in e for e in errors)


def test_float_field_rejects_non_number(validate_deckops):
    errors = validate_deckops.validate_ops(
        line("SLIDE", 0) + "\n" + line("TEXT", "x", 20, 300, 80, "t")
    )
    assert any("number" in e for e in errors)


def test_series_value_must_be_number(validate_deckops):
    text = "\n".join([
        line("SLIDE", 0),
        line("CHART", 51, 10, 20, 400, 300),
        line("SERIES", "S", "notanumber"),
    ])
    errors = validate_deckops.validate_ops(text)
    assert any("SERIES" in e and "number" in e for e in errors)


def test_series_requires_at_least_one_value(validate_deckops):
    # SERIES with a name but no values would build an empty series — reject it.
    text = "\n".join([
        line("SLIDE", 0),
        line("CHART", 51, 10, 20, 400, 300),
        line("SERIES", "Revenue"),
    ])
    errors = validate_deckops.validate_ops(text)
    assert any("SERIES" in e and "fields" in e for e in errors)


def test_chart_without_series_rejected(validate_deckops):
    # A CHART with no SERIES keeps PowerPoint's default sample data.
    text = "\n".join([
        line("SLIDE", 0),
        line("CHART", 51, 10, 20, 400, 300),
        line("CAT", "Q1"),
    ])
    errors = validate_deckops.validate_ops(text)
    assert any("CHART has no SERIES" in e for e in errors)


def test_negative_slide_layout_index_rejected(validate_deckops):
    errors = validate_deckops.validate_ops(line("SLIDE", -1))
    assert any("layout index must be >= 0" in e for e in errors)


def test_bg_channel_out_of_range(validate_deckops):
    errors = validate_deckops.validate_ops(line("SLIDE", 0) + "\n" + line("BG", 300, 0, 0))
    assert any("0-255" in e for e in errors)


def test_bg_channel_in_range_ok(validate_deckops):
    assert validate_deckops.validate_ops(line("SLIDE", 0) + "\n" + line("BG", 0, 128, 255)) == []


def test_op_before_any_slide(validate_deckops):
    errors = validate_deckops.validate_ops(line("TITLE", "orphan"))
    assert any("before any SLIDE" in e for e in errors)


def test_cell_before_table(validate_deckops):
    errors = validate_deckops.validate_ops(line("SLIDE", 0) + "\n" + line("CELL", 1, 1, "x"))
    assert any("CELL before any TABLE" in e for e in errors)


def test_cat_and_series_before_chart(validate_deckops):
    errors = validate_deckops.validate_ops(line("SLIDE", 0) + "\n" + line("CAT", "Q1"))
    assert any("CAT before any CHART" in e for e in errors)


def test_table_state_resets_on_new_slide(validate_deckops):
    # A TABLE on slide 1 must not satisfy a CELL on slide 2.
    text = "\n".join([
        line("SLIDE", 0),
        line("TABLE", 2, 2, 10, 20, 300, 200),
        line("SLIDE", 1),
        line("CELL", 1, 1, "x"),
    ])
    errors = validate_deckops.validate_ops(text)
    assert any("CELL before any TABLE" in e for e in errors)


def test_chart_state_resets_on_new_slide(validate_deckops):
    # The slide-1 chart gets its own SERIES so the only error is the slide-2
    # SERIES landing with no chart in scope.
    text = "\n".join([
        line("SLIDE", 0),
        line("CHART", 51, 10, 20, 400, 300),
        line("SERIES", "S1", 1, 2),
        line("SLIDE", 1),
        line("SERIES", "S2", 1, 2),
    ])
    errors = validate_deckops.validate_ops(text)
    assert any("SERIES before any CHART" in e for e in errors)
    assert not any("CHART has no SERIES" in e for e in errors)


def test_op_name_is_case_insensitive(validate_deckops):
    assert validate_deckops.validate_ops("slide\x1f0\ntitle\x1fHi") == []


def test_main_missing_file_actionable_error(validate_deckops, capsys, monkeypatch, tmp_path):
    missing = tmp_path / "nope.txt"
    monkeypatch.setattr(sys, "argv", ["validate-deckops.py", str(missing)])
    with pytest.raises(SystemExit) as exc:
        validate_deckops.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "not found" in err and str(missing) in err


def test_main_valid_file_prints_summary(validate_deckops, capsys, monkeypatch, tmp_path):
    ops = tmp_path / "ops.txt"
    ops.write_text(line("SLIDE", 0) + "\n" + line("TITLE", "Hi"), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["validate-deckops.py", str(ops)])
    validate_deckops.main()
    out = capsys.readouterr().out
    assert '"slides": 1' in out and '"ops": 2' in out

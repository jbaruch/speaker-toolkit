"""Tests for verify-deck-text.py, the smoke test's check that text arrived intact."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills" / "presentation-creator" / "scripts"
)
VERIFY = SCRIPTS / "verify-deck-text.py"
SMOKE_OPS = SCRIPTS / "smoke-test-ops.txt"
DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
US = "\x1f"


def _deck(path: Path, *slides: list[str]) -> Path:
    """A deck whose slide parts hold the given runs, slide by slide."""
    with zipfile.ZipFile(path, "w") as archive:
        for number, runs in enumerate(slides, start=1):
            body = "".join(f"<a:t>{escape(run)}</a:t>" for run in runs)
            archive.writestr(
                f"ppt/slides/slide{number}.xml",
                f'<root xmlns:a="{DRAWING}">{body}</root>',
            )
        archive.writestr("ppt/presentation.xml", "<root/>")
    return path


def _ops(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _run(deck: Path, ops: Path):
    return subprocess.run(
        [sys.executable, str(VERIFY), str(deck), str(ops)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_intact_text_passes_and_reports_what_it_checked(tmp_path):
    deck = _deck(tmp_path / "deck.pptx", ["Port → GitHub"], ["Second", "body & more"])
    ops = _ops(
        tmp_path / "ops.txt",
        f"SLIDE{US}0\nTITLE{US}Port → GitHub\nSLIDE{US}0\nTITLE{US}Second\n"
        f"TEXT{US}1{US}2{US}3{US}4{US}body & more\n",
    )

    result = _run(deck, ops)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True, "slides": 2, "checked": 3}


def test_a_question_mark_in_place_of_a_character_fails_and_names_it(tmp_path):
    deck = _deck(tmp_path / "deck.pptx", ["Port ? GitHub"])
    ops = _ops(tmp_path / "ops.txt", f"SLIDE{US}0\nTITLE{US}Port → GitHub\n")

    result = _run(deck, ops)

    assert result.returncode == 1
    assert "slide 1 is missing 'Port → GitHub'" in result.stderr
    assert "deckops-doctor.py" in result.stderr
    assert result.stdout == ""


def test_text_powerpoint_split_across_runs_still_matches(tmp_path):
    deck = _deck(tmp_path / "deck.pptx", ["Launch ", "🚀", " now"])
    ops = _ops(tmp_path / "ops.txt", f"SLIDE{US}0\nTITLE{US}Launch 🚀 now\n")

    assert _run(deck, ops).returncode == 0


def test_every_text_op_is_compared_at_its_own_field(tmp_path):
    deck = _deck(tmp_path / "deck.pptx", ["subtitle body bullet text cell"])
    ops = _ops(
        tmp_path / "ops.txt",
        f"SLIDE{US}0\nSUBTITLE{US}subtitle\nBODY{US}body\nBULLET{US}0{US}bullet\n"
        f"TEXT{US}1{US}2{US}3{US}4{US}text\nTABLE{US}1{US}1{US}0{US}0{US}1{US}1\n"
        f"CELL{US}1{US}1{US}cell\n",
    )

    result = _run(deck, ops)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["checked"] == 5


def test_text_on_the_wrong_slide_doesnt_count(tmp_path):
    deck = _deck(tmp_path / "deck.pptx", ["other"], ["Title"])
    ops = _ops(
        tmp_path / "ops.txt",
        f"SLIDE{US}0\nTITLE{US}Title\nSLIDE{US}0\nTITLE{US}other\n",
    )

    assert _run(deck, ops).returncode == 1


def test_a_different_slide_count_fails(tmp_path):
    deck = _deck(tmp_path / "deck.pptx", ["Only"])
    ops = _ops(tmp_path / "ops.txt", f"SLIDE{US}0\nTITLE{US}Only\nSLIDE{US}0\n")

    result = _run(deck, ops)

    assert result.returncode == 1
    assert "the ops build 2 slides; the deck has 1" in result.stderr


def test_slide_parts_are_read_in_numeric_order(tmp_path):
    runs = [[f"slide-{number}"] for number in range(1, 12)]
    deck = _deck(tmp_path / "deck.pptx", *runs)
    lines = "".join(f"SLIDE{US}0\nTITLE{US}slide-{n}\n" for n in range(1, 12))

    assert _run(deck, _ops(tmp_path / "ops.txt", lines)).returncode == 0


def test_a_file_that_isnt_a_deck_is_refused(tmp_path):
    bad = tmp_path / "deck.pptx"
    bad.write_bytes(b"not a zip")
    ops = _ops(tmp_path / "ops.txt", f"SLIDE{US}0\n")

    result = _run(bad, ops)

    assert result.returncode == 1
    assert "cannot compare" in result.stderr


SLIDE_ONE = "ppt/slides/slide1.xml"


def _central_entry(data: bytearray, name: str) -> int:
    """Offset of the central-directory header naming `name`."""
    encoded = name.encode("ascii")
    offset = data.find(b"PK\x01\x02")
    while offset != -1:
        length = int.from_bytes(data[offset + 28 : offset + 30], "little")
        if bytes(data[offset + 46 : offset + 46 + length]) == encoded:
            return offset
        offset = data.find(b"PK\x01\x02", offset + 4)
    raise AssertionError(f"{name} has no central-directory entry")


def _mark_encrypted(data: bytearray) -> None:
    entry = _central_entry(data, SLIDE_ONE)
    flags = int.from_bytes(data[entry + 8 : entry + 10], "little") | 0x1
    data[entry + 8 : entry + 10] = flags.to_bytes(2, "little")


def _unsupported_method(data: bytearray) -> None:
    entry = _central_entry(data, SLIDE_ONE)
    data[entry + 10 : entry + 12] = (99).to_bytes(2, "little")


def _corrupt_stream(data: bytearray) -> None:
    entry = _central_entry(data, SLIDE_ONE)
    local = int.from_bytes(data[entry + 42 : entry + 46], "little")
    name_length = int.from_bytes(data[local + 26 : local + 28], "little")
    extra_length = int.from_bytes(data[local + 28 : local + 30], "little")
    start = local + 30 + name_length + extra_length
    data[start : start + 8] = b"\xff" * 8


def test_a_slide_part_zipfile_cant_read_is_refused(tmp_path):
    for damage in (_mark_encrypted, _unsupported_method, _corrupt_stream):
        deck = tmp_path / f"{damage.__name__}.pptx"
        with zipfile.ZipFile(deck, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                SLIDE_ONE, f'<root xmlns:a="{DRAWING}"><a:t>{"x" * 200}</a:t></root>'
            )
        data = bytearray(deck.read_bytes())
        damage(data)
        deck.write_bytes(bytes(data))

        result = _run(deck, _ops(tmp_path / "ops.txt", f"SLIDE{US}0\n"))

        assert result.returncode == 1, damage.__name__
        assert "cannot compare" in result.stderr, damage.__name__
        assert SLIDE_ONE in result.stderr, damage.__name__
        assert "Traceback" not in result.stderr, damage.__name__


def test_the_shipped_smoke_ops_exercise_text_mac_roman_cant_hold():
    """The check is only worth running while its own ops would catch the loss."""
    text = SMOKE_OPS.read_text(encoding="utf-8")

    assert text.encode("mac_roman", errors="replace").decode("mac_roman") != text

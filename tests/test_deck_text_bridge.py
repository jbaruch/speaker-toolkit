"""Tests for deck-text-bridge.py and the wrappers that use it.

`run VB macro` can't run in CI (rules/deck-editing-rules.md), so `osascript` is faked
on PATH and everything around it runs for real: the escaping, the macro-version gate,
and what each wrapper hands its driver. `DecodeBridgeText` itself is VBA, so the
decoder below only restates its algorithm to pin the wire format. The real one is
validated by the Step 5 smoke test.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills" / "presentation-creator" / "scripts"
)
BRIDGE = SCRIPTS / "deck-text-bridge.py"
SHIPPED_STAMP = re.search(
    r'DECKOPS_STAMP As String = "([0-9a-f]+)"',
    (SCRIPTS / "RunDeckOps.bas").read_text(encoding="utf-8"),
).group(1)  # pyright: ignore[reportOptionalMemberAccess] -- a missing stamp should raise here
MARKER = "\x1c"
ARROW_TITLE = "Port → GitHub ⚡ 🚀 — done"


def _decode(text: str) -> str:
    """The wire format as DecodeBridgeText reads it."""
    units = bytearray()
    index = 0
    while index < len(text):
        if text[index] == MARKER:
            units += bytes.fromhex(text[index + 1 : index + 5])
            index += 5
        else:
            units += text[index].encode("utf-16-be")
            index += 1
    return units.decode("utf-16-be")


@pytest.fixture(scope="module")
def bridge():
    import importlib.util

    spec = importlib.util.spec_from_file_location("deck_text_bridge", BRIDGE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _keep(bridge, mode: str) -> frozenset[str]:
    if mode == "file":
        return bridge.PRINTABLE_ASCII | bridge.FILE_STRUCTURE
    return bridge.PRINTABLE_ASCII


def test_pure_ascii_passes_through_untouched(bridge):
    text = "Plain title, with (punctuation) & 100% ASCII ~"

    assert bridge.escape_text(text, keep=_keep(bridge, "scalar")) == (text, 0)


@pytest.mark.parametrize(
    ("text", "units"),
    [
        ("→", 1),
        ("⚡", 1),
        ("—", 1),
        ("é", 1),
        ("🚀", 2),
        (" ", 1),
        ("\x7f", 1),
    ],
    ids=["arrow", "bolt", "em-dash", "accent", "emoji", "nbsp", "del"],
)
def test_everything_outside_printable_ascii_is_escaped(bridge, text, units):
    escaped, count = bridge.escape_text(text, keep=_keep(bridge, "scalar"))

    assert count == units
    assert escaped.isascii()
    assert _decode(escaped) == text


@pytest.mark.parametrize("mode", ["scalar", "file"])
def test_mixed_text_round_trips(bridge, mode):
    escaped, _count = bridge.escape_text(ARROW_TITLE, keep=_keep(bridge, mode))

    assert all(
        character == MARKER or 0x20 <= ord(character) < 0x7F for character in escaped
    )
    assert _decode(escaped) == ARROW_TITLE


def test_file_mode_keeps_the_structure_the_macro_splits_on(bridge):
    ops = "SLIDE\x1f0\r\nTITLE\x1fPort → GitHub\nTEXT\x1f1\x1f2\x1f3\x1f4\x1fa\x1db\x1ec\td\n"

    escaped, count = bridge.escape_text(ops, keep=_keep(bridge, "file"))

    assert count == 1
    assert escaped.replace(f"{MARKER}2192", "→") == ops


def test_scalar_mode_escapes_a_newline_so_the_shell_cant_strip_it(bridge):
    escaped, count = bridge.escape_text("a\n", keep=_keep(bridge, "scalar"))

    assert escaped == f"a{MARKER}000A"
    assert count == 1


@pytest.mark.parametrize("mode", ["scalar", "file"])
def test_text_holding_the_marker_is_refused(bridge, mode):
    with pytest.raises(bridge.BridgeRefusal, match="U\\+001C"):
        bridge.escape_text(f"a{MARKER}2192", keep=_keep(bridge, mode))


# --- the gate and the wrappers, with osascript faked --------------------------


def _fake_osascript(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "osascript"
    fake.write_text(
        f"""#!{sys.executable}
import json, os, pathlib, sys
driver = pathlib.Path(sys.argv[1]).name
arguments = sys.argv[2:]
log = pathlib.Path(os.environ["FAKE_LOG"])
record = {{"driver": driver, "args": arguments}}
if driver == "deckops-version.applescript":
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\\n")
    print(os.environ.get("FAKE_PROBE", "").replace("|", "\\n"))
    sys.stderr.write(os.environ.get("FAKE_PROBE_STDERR", ""))
    sys.exit(int(os.environ.get("FAKE_PROBE_RC", "0")))
for key, index in (("build-deck.applescript", 2), ("expand-builds.applescript", 2)):
    if driver == key:
        record["file_text"] = pathlib.Path(arguments[index]).read_bytes().decode("ascii")
with log.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(record) + "\\n")
output_index = {{"make-bg-slide.applescript": 4}}.get(driver, 1)
pathlib.Path(arguments[output_index]).write_bytes(b"deck")
""",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def harness(tmp_path):
    bin_dir = tmp_path / "bin"
    _fake_osascript(bin_dir)
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "osascript.log"
    log.touch()
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(home),
        "FAKE_LOG": str(log),
        "FAKE_PROBE": f"state=ok|stamp={SHIPPED_STAMP}",
    }

    def calls(driver: str | None = None) -> list[dict]:
        records = [
            json.loads(line)
            for line in log.read_text(encoding="utf-8").splitlines()
            if line
        ]
        return [r for r in records if driver is None or r["driver"] == driver]

    return environment, calls


def _bridge_cli(environment, mode, source, target):
    return subprocess.run(
        [sys.executable, str(BRIDGE), mode, str(source), str(target)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def test_cli_reports_what_it_wrote(tmp_path, harness):
    environment, calls = harness
    source = tmp_path / "in.txt"
    source.write_text(ARROW_TITLE, encoding="utf-8")
    target = tmp_path / "out.txt"

    result = _bridge_cli(environment, "scalar", source, target)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"output": str(target), "escaped": 5}
    assert _decode(target.read_text(encoding="ascii")) == ARROW_TITLE
    assert [record["driver"] for record in calls()] == ["deckops-version.applescript"]


def test_pure_ascii_never_asks_powerpoint_anything(tmp_path, harness):
    environment, calls = harness
    source = tmp_path / "in.txt"
    source.write_text("Plain title", encoding="utf-8")
    target = tmp_path / "out.txt"

    result = _bridge_cli(
        {**environment, "FAKE_PROBE": "state=not_running"}, "scalar", source, target
    )

    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="ascii") == "Plain title"
    assert calls() == []


@pytest.mark.parametrize(
    ("probe", "needle"),
    [
        ("state=ok|stamp=0123456789abcdef", "Re-import RunDeckOps.bas"),
        ("state=not_running", "PowerPoint isn't running"),
        ("state=macro_unreachable|detail=no macro", "Open DeckOps.pptm"),
    ],
    ids=["stale", "not-running", "unreachable"],
)
def test_text_needing_the_decoder_is_refused_without_it(
    tmp_path, harness, probe, needle
):
    environment, _calls = harness
    source = tmp_path / "in.txt"
    source.write_text(ARROW_TITLE, encoding="utf-8")
    target = tmp_path / "out.txt"

    result = _bridge_cli({**environment, "FAKE_PROBE": probe}, "scalar", source, target)

    assert result.returncode == 1
    assert needle in result.stderr
    assert "No deck was changed" in result.stderr
    assert not target.exists()


def test_a_failed_probe_is_reported_with_its_detail(tmp_path, harness):
    environment, _calls = harness
    source = tmp_path / "in.txt"
    source.write_text(ARROW_TITLE, encoding="utf-8")
    target = tmp_path / "out.txt"

    result = _bridge_cli(
        {**environment, "FAKE_PROBE_RC": "1", "FAKE_PROBE_STDERR": "consent denied"},
        "scalar",
        source,
        target,
    )

    assert result.returncode == 1
    assert "consent denied" in result.stderr
    assert "deckops-doctor.py" in result.stderr
    assert not target.exists()


def test_input_that_isnt_utf8_is_refused(tmp_path, harness):
    environment, _calls = harness
    source = tmp_path / "in.txt"
    source.write_bytes(b"caf\xe9")
    target = tmp_path / "out.txt"

    result = _bridge_cli(environment, "file", source, target)

    assert result.returncode == 1
    assert "not valid UTF-8" in result.stderr
    assert not target.exists()


def test_a_missing_input_is_refused(tmp_path, harness):
    environment, _calls = harness

    result = _bridge_cli(
        environment, "file", tmp_path / "missing.txt", tmp_path / "out.txt"
    )

    assert result.returncode == 1
    assert "cannot read" in result.stderr


def _run_wrapper(environment, wrapper, *arguments):
    return subprocess.run(
        ["bash", str(SCRIPTS / wrapper), *map(str, arguments)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def _wrapper_case(name, tmp_path):
    """(wrapper, argv, driver, read-the-bridged-text) for one text-carrying wrapper."""
    base = tmp_path / "base.pptx"
    base.write_bytes(b"pptx")
    out = tmp_path / "out" / "deck.pptx"
    if name == "make-placeholder-title":
        return (
            "make-placeholder-slide.sh",
            [base, out, ARROW_TITLE, "plain"],
            "make-placeholder-slide.applescript",
            lambda record: record["args"][2],
        )
    if name == "make-placeholder-subtitle":
        return (
            "make-placeholder-slide.sh",
            [base, out, "plain", ARROW_TITLE],
            "make-placeholder-slide.applescript",
            lambda record: record["args"][3],
        )
    if name == "make-bg":
        image = tmp_path / "image.png"
        image.write_bytes(b"png")
        return (
            "make-bg-slide.sh",
            [base, "1", image, ARROW_TITLE, out],
            "make-bg-slide.applescript",
            lambda record: record["args"][3],
        )
    if name == "run-deck-ops":
        return (
            "run-deck-ops.sh",
            [base, out, "", "BASE:1", f"old=>{ARROW_TITLE}"],
            "run-deck-ops.applescript",
            lambda record: record["args"][4],
        )
    if name == "build-deck":
        ops = tmp_path / "ops.txt"
        ops.write_text(f"SLIDE\x1f0\nTITLE\x1f{ARROW_TITLE}\n", encoding="utf-8")
        return (
            "build-deck.sh",
            [base, out, ops],
            "build-deck.applescript",
            lambda record: record["file_text"],
        )
    assert name == "expand-builds"
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")
    manifest = tmp_path / "builds.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "builds": [{"parent": 2, "frames": [str(frame)], "notes": ARROW_TITLE}],
            }
        ),
        encoding="utf-8",
    )
    return (
        "expand-builds.sh",
        [base, out, manifest],
        "expand-builds.applescript",
        lambda record: record["file_text"],
    )


WRAPPER_CASES = [
    "make-placeholder-title",
    "make-placeholder-subtitle",
    "make-bg",
    "run-deck-ops",
    "build-deck",
    "expand-builds",
]


@pytest.mark.parametrize("name", WRAPPER_CASES)
def test_each_wrapper_hands_its_macro_only_ascii_that_decodes_back(
    name, tmp_path, harness
):
    environment, calls = harness
    wrapper, arguments, driver, read_text = _wrapper_case(name, tmp_path)

    result = _run_wrapper(environment, wrapper, *arguments)

    assert result.returncode == 0, result.stderr
    bridged = read_text(calls(driver)[0])
    assert bridged.isascii()
    assert "→" not in bridged
    assert ARROW_TITLE in _decode(bridged)


@pytest.mark.parametrize("name", WRAPPER_CASES)
def test_each_wrapper_stops_before_its_macro_on_a_stale_import(name, tmp_path, harness):
    environment, calls = harness
    wrapper, arguments, driver, _read_text = _wrapper_case(name, tmp_path)

    result = _run_wrapper(
        {**environment, "FAKE_PROBE": "state=ok|stamp=0123456789abcdef"},
        wrapper,
        *arguments,
    )

    assert result.returncode != 0
    assert "Re-import RunDeckOps.bas" in result.stderr
    assert calls(driver) == []
    assert not (tmp_path / "out" / "deck.pptx").exists()


def test_a_wrapper_with_ascii_text_works_on_an_old_macro(tmp_path, harness):
    """Plain decks keep building until the user gets round to the re-import."""
    environment, calls = harness
    base = tmp_path / "base.pptx"
    base.write_bytes(b"pptx")
    out = tmp_path / "out" / "deck.pptx"

    result = _run_wrapper(
        {**environment, "FAKE_PROBE": "state=ok|stamp=0123456789abcdef"},
        "make-placeholder-slide.sh",
        base,
        out,
        "Plain title",
        "",
    )

    assert result.returncode == 0, result.stderr
    assert calls("make-placeholder-slide.applescript")[0]["args"][2:] == [
        "Plain title",
        "",
    ]
    assert calls("deckops-version.applescript") == []
    assert out.read_bytes() == b"deck"


@pytest.mark.parametrize(
    ("macro", "parameters"),
    [
        ("RunDeckOps", ["replaceStr"]),
        ("MakeBgImageSlide", ["titleText"]),
        ("ExpandBuilds", ["packedSpec"]),
        ("MakePlaceholderSlide", ["titleText", "subtitleText"]),
        ("BuildDeck", ["opsText"]),
    ],
)
def test_every_macro_taking_text_decodes_it_before_using_it(macro, parameters):
    """VBA can't run in CI. A macro that forgot the decoder would put escape codes
    on slides, so the one thing checkable here is pinned at the source."""
    module = (SCRIPTS / "RunDeckOps.bas").read_text(encoding="utf-8")
    body = re.search(rf"Public Function {macro}\(.*?\nEnd Function", module, re.DOTALL)
    assert body is not None
    source = body.group(0)
    for parameter in parameters:
        decode = source.find(f"{parameter} = DecodeBridgeText({parameter})")
        assert decode != -1, parameter
        assert decode < source.index("AssertNotOpen")

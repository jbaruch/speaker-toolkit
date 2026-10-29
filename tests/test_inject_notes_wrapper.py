"""Tests for inject-notes.sh — the shell wrapper's deterministic behavior: the
NUL-framed consumer that turns notes-to-packed.py --driver-args output into the
driver's argv, the preflight refusal, staging/move, and the driver-failure
path, with `osascript` (the real PowerPoint call) faked on PATH. Only the
AppleScript's PowerPoint interaction is the manual-validation gap.
"""

import json
import os
import subprocess
import zipfile
from pathlib import Path

WRAPPER = (
    Path(__file__).resolve().parents[1]
    / "skills/presentation-creator/scripts/inject-notes.sh"
)
DRIVER = WRAPPER.with_name("inject-notes.applescript")
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _deck(tmp_path, slides):
    ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i}"/>' for i in range(slides))
    path = tmp_path / "deck.pptx"
    with zipfile.ZipFile(path, "w") as deck:
        deck.writestr(
            "ppt/presentation.xml",
            f'<p:presentation xmlns:p="{PRESENTATION_NS}" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>",
        )
    return path


def _fake_osascript(dirpath, *, succeed, stderr=""):
    """Write a fake `osascript` that records its argv NUL-separated.

    The wrapper calls `osascript <driver> <base> <STAGE> <base name>
    <STAGE name> <note 1>...`, so the staged output path is $3. On success the
    fake touches it, as PowerPoint's save would; on failure it prints `stderr`
    (the driver's stage log and error) and exits non-zero like the driver.
    """
    record = dirpath / "argv.bin"
    p = dirpath / "osascript"
    body = f"printf '%s\\0' \"$@\" > '{record}'\n"
    if succeed:
        body += 'touch "$3"\necho "Notes applied: 1"\n'
    else:
        body += f"printf '%s' '{stderr}' >&2\nexit 1\n"
    p.write_text("#!/bin/bash\n" + body)
    p.chmod(0o755)
    return record


def _run(tmp_path, base, notes_map):
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps(notes_map, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out" / "deck-with-notes.pptx"
    env = dict(os.environ)
    env["PATH"] = f"{tmp_path}:{env['PATH']}"  # shadow the real osascript
    env["HOME"] = str(tmp_path)  # no PowerPoint container: isolated staging
    result = subprocess.run(
        ["bash", str(WRAPPER), str(base), str(out), str(notes)],
        capture_output=True,
        text=True,
        env=env,
    )
    return result, out


def _argv(record):
    items = record.read_bytes().decode("utf-8").split("\0")
    assert items[-1] == ""  # every item is NUL-terminated
    return items[:-1]


def test_unicode_multiline_and_unchanged_slides_reach_the_driver_intact(tmp_path):
    record = _fake_osascript(tmp_path, succeed=True)
    base = _deck(tmp_path, 4)
    first = "PORT → Factories ⚡\n[cue] line two\n  indented — “quoted” 日本"
    third = "-n looks like a flag; $HOME stays literal"
    result, out = _run(tmp_path, base, {"0": first, "2": third, "1": ""})
    assert result.returncode == 0, result.stderr
    argv = _argv(record)
    assert argv[0] == str(DRIVER)
    assert argv[1] == str(base)
    assert Path(argv[2]).name == out.name
    # The driver gets both file names, so it parses no paths itself.
    assert argv[3:5] == [base.name, out.name]
    # One argument per slide, in order; "" leaves a slide's notes unchanged.
    assert argv[5:] == [first, "", third, ""]
    assert out.exists()
    assert f"done -> {out}" in result.stdout


def test_empty_map_passes_one_empty_argument_per_slide(tmp_path):
    record = _fake_osascript(tmp_path, succeed=True)
    result, _ = _run(tmp_path, _deck(tmp_path, 3), {})
    assert result.returncode == 0, result.stderr
    assert _argv(record)[5:] == ["", "", ""]


def test_zero_slide_deck_passes_no_note_arguments(tmp_path):
    record = _fake_osascript(tmp_path, succeed=True)
    result, _ = _run(tmp_path, _deck(tmp_path, 0), {})
    assert result.returncode == 0, result.stderr
    assert len(_argv(record)) == 5


def test_out_of_range_note_is_refused_before_powerpoint_runs(tmp_path):
    record = _fake_osascript(tmp_path, succeed=True)
    result, out = _run(tmp_path, _deck(tmp_path, 3), {"9": "x"})
    assert result.returncode != 0
    assert "has 3 slides" in result.stderr
    assert not record.exists()  # osascript never ran
    assert not out.exists()


def test_failure_after_open_says_to_close_the_copy_this_run_opened(tmp_path):
    _fake_osascript(
        tmp_path,
        succeed=False,
        stderr="[open] /x/deck.pptx\n[opened] deck.pptx\n[save] /x/out.pptx\n"
        "PowerPoint got an error (-50)\n",
    )
    result, out = _run(tmp_path, _deck(tmp_path, 2), {"0": "x"})
    assert result.returncode == 1
    assert "[save]" in result.stderr
    assert "stopped at the last stage it logged above" in result.stderr
    assert "This run opened a copy: close the presentation named deck.pptx" in (
        result.stderr
    )
    assert not out.exists()


def test_already_open_collision_leaves_the_users_deck_alone(tmp_path):
    _fake_osascript(
        tmp_path,
        succeed=False,
        stderr="[open] /x/deck.pptx\nERROR: inject-notes failed at [open]: a "
        "presentation named deck.pptx is already open\n",
    )
    result, out = _run(tmp_path, _deck(tmp_path, 2), {"0": "x"})
    assert result.returncode == 1
    assert "already open" in result.stderr
    assert "This run opened no copy" in result.stderr
    assert "leave every presentation that was already open" in result.stderr
    assert "without saving" not in result.stderr
    assert not out.exists()


def test_missing_notes_json_fails_with_actionable_error(tmp_path):
    _fake_osascript(tmp_path, succeed=True)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}", HOME=str(tmp_path))
    result = subprocess.run(
        [
            "bash",
            str(WRAPPER),
            str(_deck(tmp_path, 1)),
            str(tmp_path / "o.pptx"),
            str(tmp_path / "nope.json"),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "notes JSON not found" in result.stderr

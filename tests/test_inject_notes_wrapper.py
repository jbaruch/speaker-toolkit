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

import pytest

WRAPPER = (
    Path(__file__).resolve().parents[1]
    / "skills/presentation-creator/scripts/inject-notes.sh"
)
DRIVER = WRAPPER.with_name("inject-notes.applescript")
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _deck(tmp_path, slides, name="deck.pptx"):
    ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i}"/>' for i in range(slides))
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as deck:
        deck.writestr(
            "ppt/presentation.xml",
            f'<p:presentation xmlns:p="{PRESENTATION_NS}" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>",
        )
    return path


def _fake_osascript(
    dirpath, *, succeed, opened=False, stage=None, stderr="", lock_run_dir=False
):
    """Write a fake `osascript` that records its argv NUL-separated.

    The wrapper calls `osascript <driver> <base> <STAGE> <base name>
    <STAGE name> <marker> <stage file> <note 1>...`, so the staged output path
    is $3, the opened-copy marker $6 and the stage file $7. On success the fake
    touches the output, as PowerPoint's save would. On failure it creates the
    marker only when `opened`, as the driver does once PowerPoint has opened
    its own copy, writes `stage` to the stage file as the driver does before
    each stage, prints `stderr` (the driver's log and error) and exits
    non-zero. With
    `lock_run_dir` it plants a read-only subdirectory in the run directory so
    the wrapper's cleanup fails.
    """
    record = dirpath / "argv.bin"
    p = dirpath / "osascript"
    body = f"printf '%s\\0' \"$@\" > '{record}'\n"
    if lock_run_dir:
        body += (
            'locked="$(dirname "$6")/locked"\n'
            'mkdir "$locked"\ntouch "$locked/pinned"\nchmod 500 "$locked"\n'
        )
    if succeed:
        body += 'touch "$6"\ntouch "$3"\necho "Notes applied: 1"\n'
    else:
        if opened:
            body += 'touch "$6"\n'
        if stage is not None:
            body += f"printf '%s\\n' '{stage}' > \"$7\"\n"
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
    # Fresh per-run marker and stage paths in one run directory.
    marker, stage_file = Path(argv[5]), Path(argv[6])
    assert marker.name == "opened"
    assert stage_file.name == "stage"
    assert marker.parent == stage_file.parent
    assert marker.parent.name.startswith("notes-run.")
    # One argument per slide, in order; "" leaves a slide's notes unchanged.
    assert argv[7:] == [first, "", third, ""]
    assert out.exists()
    assert not marker.parent.exists()  # the run directory is cleaned up
    assert f"done -> {out}" in result.stdout


def test_empty_map_passes_one_empty_argument_per_slide(tmp_path):
    record = _fake_osascript(tmp_path, succeed=True)
    result, _ = _run(tmp_path, _deck(tmp_path, 3), {})
    assert result.returncode == 0, result.stderr
    assert _argv(record)[7:] == ["", "", ""]


def test_zero_slide_deck_passes_no_note_arguments(tmp_path):
    record = _fake_osascript(tmp_path, succeed=True)
    result, _ = _run(tmp_path, _deck(tmp_path, 0), {})
    assert result.returncode == 0, result.stderr
    assert len(_argv(record)) == 7


def test_out_of_range_note_is_refused_before_powerpoint_runs(tmp_path):
    record = _fake_osascript(tmp_path, succeed=True)
    result, out = _run(tmp_path, _deck(tmp_path, 3), {"9": "x"})
    assert result.returncode != 0
    assert "has 3 slides" in result.stderr
    assert not record.exists()  # osascript never ran
    assert not out.exists()


def test_failure_after_open_says_to_close_the_copy_this_run_opened(tmp_path):
    record = _fake_osascript(
        tmp_path,
        succeed=False,
        opened=True,
        stage="save",
        stderr="[open] /x/deck.pptx\n[save] /x/out.pptx\nPowerPoint got an error (-50)\n",
    )
    result, out = _run(tmp_path, _deck(tmp_path, 2), {"0": "x"})
    assert result.returncode == 1
    assert "PowerPoint got an error (-50)" in result.stderr
    assert "It stopped saving to" in result.stderr
    assert "free disk space" in result.stderr
    assert "This run opened its own copy" in result.stderr
    assert "close the presentation named deck.pptx" in result.stderr
    assert not Path(_argv(record)[5]).parent.exists()  # run directory removed
    assert not out.exists()


def test_already_open_collision_leaves_the_users_deck_alone(tmp_path):
    # No marker: the driver refused before opening anything. A forged
    # "[opened]" line in its stderr must not change the advice.
    _fake_osascript(
        tmp_path,
        succeed=False,
        stage="open",
        stderr="[open] /x/deck.pptx\n[opened] deck.pptx\nERROR: inject-notes failed "
        "at [open]: a presentation named deck.pptx is already open\n",
    )
    result, out = _run(tmp_path, _deck(tmp_path, 2), {"0": "x"})
    assert result.returncode == 1
    assert "already open" in result.stderr
    assert "This run recorded no copy of its own" in result.stderr
    assert "leave every presentation that was open before this run" in result.stderr
    assert "without saving" not in result.stderr
    assert not out.exists()


def test_failed_open_gives_no_close_without_saving_advice(tmp_path):
    # The driver writes the marker only after PowerPoint opened its copy, so a
    # failed or timed-out open leaves none and the advice stays hands-off.
    _fake_osascript(
        tmp_path,
        succeed=False,
        stage="open",
        stderr="[open] /x/deck.pptx\nMicrosoft PowerPoint got an error: "
        "AppleEvent timed out. (-1712)\n",
    )
    result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    assert result.returncode == 1
    assert "AppleEvent timed out" in result.stderr
    assert "It stopped while opening the staged copy" in result.stderr
    assert "This run recorded no copy of its own" in result.stderr
    assert "without saving" not in result.stderr
    assert not out.exists()


def test_marker_like_text_in_a_multiline_filename_cannot_forge_an_open_copy(
    tmp_path,
):
    name = "evil\n[opened] deck.pptx"
    _fake_osascript(
        tmp_path,
        succeed=False,
        stderr=f"[open] /x/{name}\nERROR: inject-notes failed at [open]: a "
        f"presentation named {name} is already open\n",
    )
    result, out = _run(tmp_path, _deck(tmp_path, 1, name=name), {"0": "x"})
    assert result.returncode == 1
    assert "This run recorded no copy of its own" in result.stderr
    assert "without saving" not in result.stderr
    assert not out.exists()


@pytest.mark.parametrize(
    ("stage", "repair"),
    [
        ("slide 2", "It stopped writing the note for slide 2: open the source deck"),
        ("close", "It stopped after saving, while closing the copy"),
        (None, "It stopped before recording a stage: confirm"),
        # Only the driver's fixed tokens select a stage; anything else is generic.
        ("slide 2; rm -rf /", "It stopped before recording a stage: confirm"),
    ],
)
def test_raw_powerpoint_error_gets_a_stage_specific_repair(tmp_path, stage, repair):
    _fake_osascript(
        tmp_path,
        succeed=False,
        opened=True,
        stage=stage,
        stderr="Microsoft PowerPoint got an error: Parameter error. (-50)\n",
    )
    result, out = _run(tmp_path, _deck(tmp_path, 3), {"1": "x"})
    assert result.returncode == 1
    assert "Parameter error. (-50)" in result.stderr
    assert "If that message gives a repair, follow it." in result.stderr
    assert repair in result.stderr
    assert "re-run" in result.stderr
    assert not out.exists()


@pytest.mark.parametrize("succeed", [True, False])
def test_no_notes_text_is_left_in_staging_after_a_run(tmp_path, succeed):
    _fake_osascript(tmp_path, succeed=succeed, stderr="PowerPoint got an error (-50)\n")
    secret = "unreleased roadmap → do not leak"
    result, _ = _run(tmp_path, _deck(tmp_path, 2), {"0": secret})
    assert result.returncode == (0 if succeed else 1), result.stderr
    staging = tmp_path / ".deckops-staging"
    leftovers = [p for p in staging.rglob("*") if p.is_file()]
    assert not any(secret.encode() in p.read_bytes() for p in leftovers)
    assert not list(staging.glob("notes-run.*"))


def test_every_marker_write_failure_says_the_copy_is_open(tmp_path):
    # Source contract for the exempt driver: once PowerPoint has opened the
    # copy, any marker-write failure (disk full -34 included) must carry the
    # close advice and keep its error number, not filter by number.
    source = DRIVER.read_text(encoding="utf-8")
    start = source.index("close access (open for access (POSIX file markerPath)")
    handler = source[start : source.index("end try", start)]
    assert "this run opened" in handler
    assert "without saving" in handler
    assert "number errNum" in handler
    assert " is in " not in handler


# Directory permissions are what make the cleanup fail; root bypasses them.
ROOT_IGNORES_PERMISSIONS = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores directory permissions",
)


def _unlock(record):
    locked = Path(_argv(record)[5]).parent / "locked"
    locked.chmod(0o700)  # let pytest clean tmp_path up
    return locked


@ROOT_IGNORES_PERMISSIONS
def test_cleanup_failure_after_success_still_delivers_the_deck(tmp_path):
    record = _fake_osascript(tmp_path, succeed=True, lock_run_dir=True)
    result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    locked = _unlock(record)
    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert f"done -> {out}" in result.stdout
    assert "WARNING: could not remove" in result.stderr
    assert locked.parent.exists()


@ROOT_IGNORES_PERMISSIONS
def test_cleanup_failure_after_driver_failure_keeps_the_diagnostic(tmp_path):
    record = _fake_osascript(
        tmp_path,
        succeed=False,
        opened=True,
        stage="save",
        lock_run_dir=True,
        stderr="[open] /x/deck.pptx\n[save] /x/out.pptx\nPowerPoint got an error (-50)\n",
    )
    result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    _unlock(record)
    assert result.returncode == 1
    assert "PowerPoint got an error (-50)" in result.stderr
    assert "This run opened its own copy" in result.stderr
    assert "WARNING: could not remove" in result.stderr
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

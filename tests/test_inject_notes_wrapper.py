"""Tests for inject-notes.sh — the shell wrapper's deterministic behavior: the
NUL-framed consumer that turns notes-to-packed.py --driver-args output into the
driver's argv, the preflight refusal, staging/move, and the driver-failure
path, with `osascript` (the real PowerPoint call) faked on PATH. Only the
AppleScript's PowerPoint interaction is the manual-validation gap.
"""

import json
import os
import re
import subprocess
import time
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
    dirpath,
    *,
    succeed,
    opened=False,
    stage=None,
    stderr="",
    lock_run_dir=False,
    saved="",
    before_save="",
):
    """Write a fake `osascript` that records its argv NUL-separated.

    The wrapper calls `osascript <driver> <base> <STAGE> <base name>
    <STAGE name> <marker> <stage file> <note 1>...`, so the staged output path
    is $3, the opened-copy marker $6 and the stage file $7. On success the fake
    touches the output, as PowerPoint's save would. On failure it creates the
    marker only when `opened`, as the driver does once PowerPoint has opened
    its own copy, writes `stage` to the stage file as the driver does before
    each stage, prints `stderr` (the driver's log and error) and exits
    non-zero. On success it writes `saved` as the staged deck's content after
    running the shell snippet `before_save`. With
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
        body += before_save + "\n"
        body += (
            f'touch "$6"\nprintf \'%s\' \'{saved}\' > "$3"\necho "Notes applied: 1"\n'
        )
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
    # PowerPoint opens a run-unique copy of the base and saves a run-unique
    # name; the driver gets both names, so it parses no paths itself.
    marker, stage_file = Path(argv[5]), Path(argv[6])
    run_id = marker.parent.name
    assert run_id.startswith("notes-run.")
    staged_base, staged_out = Path(argv[1]), Path(argv[2])
    assert staged_base.name == f"{run_id}-base-{base.name}"
    assert staged_out.name == f"{run_id}-{out.name}"
    assert argv[3:5] == [staged_base.name, staged_out.name]
    assert marker.name == "opened"
    assert stage_file.name == "stage"
    assert marker.parent == stage_file.parent
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
    assert re.search(
        r"close the presentation named notes-run\.\S+-base-deck\.pptx", result.stderr
    )
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


def test_refused_before_opening_gives_no_close_without_saving_advice(tmp_path):
    # Stopped at the "open" stage, before the open was attempted: hands-off.
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


def test_timed_out_open_says_close_the_unique_copy_only_if_it_appears(tmp_path):
    # A timeout does not cancel PowerPoint's open, so the copy may appear later.
    # The driver recorded "opening" after confirming no same-named deck was open.
    _fake_osascript(
        tmp_path,
        succeed=False,
        stage="opening",
        stderr="[open] /x/deck.pptx\nMicrosoft PowerPoint got an error: "
        "AppleEvent timed out. (-1712)\n",
    )
    result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    assert result.returncode == 1
    assert "the open did not confirm; it may still finish" in result.stderr
    assert "if one appears in PowerPoint it is this run's copy" in result.stderr
    assert re.search(
        r"No presentation named notes-run\.\S+-base-deck\.pptx was open before this run",
        result.stderr,
    )
    assert "This run opened its own copy" not in result.stderr
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
    assert (
        "If that message gives a repair, follow it: it takes precedence over this "
        "stage guess." in result.stderr
    )
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


def test_destination_folder_failure_is_actionable_and_leaves_no_notes(tmp_path):
    _fake_osascript(tmp_path, succeed=True)
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a regular file where the output folder should be")
    notes = tmp_path / "notes.json"
    secret = "delivery failure must not leak this note"
    notes.write_text(json.dumps({"0": secret}), encoding="utf-8")
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}", HOME=str(tmp_path))
    result = subprocess.run(
        [
            "bash",
            str(WRAPPER),
            str(_deck(tmp_path, 1)),
            str(blocker / "out.pptx"),
            str(notes),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "cannot be created, so nothing was delivered" in result.stderr
    assert "choose an output path in a writable folder" in result.stderr
    staging = tmp_path / ".deckops-staging"
    assert not list(staging.glob("notes-run.*"))
    assert not any(
        secret.encode() in p.read_bytes() for p in staging.rglob("*") if p.is_file()
    )


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
def test_unwritable_destination_is_actionable_and_leaves_no_notes(tmp_path):
    _fake_osascript(tmp_path, succeed=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_dir.chmod(0o500)  # the folder exists but refuses new files
    try:
        result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    finally:
        out_dir.chmod(0o700)
    assert result.returncode == 1
    assert "no temporary file can be created in" in result.stderr
    assert f"{out} is unchanged" in result.stderr
    assert not list((tmp_path / ".deckops-staging").glob("notes-run.*"))
    assert not out.exists()


def test_mid_copy_failure_keeps_the_previous_output_and_no_partial(tmp_path):
    _fake_osascript(tmp_path, succeed=True)
    # A cp that writes half a file and fails, like a full Drive volume.
    fake_cp = tmp_path / "cp"
    fake_cp.write_text(
        "#!/bin/bash\nfor last; do :; done\n"
        'case "$(basename "$last")" in\n'
        '  .deck-with-notes.pptx.*) printf partial > "$last"; exit 1 ;;\n'
        '  *) exec /bin/cp "$@" ;;\n'
        "esac\n"
    )
    fake_cp.chmod(0o755)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    previous = out_dir / "deck-with-notes.pptx"
    previous.write_text("the previous good deck")
    result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    assert result.returncode == 1
    assert "copying it to" in result.stderr
    assert f"so nothing was delivered and {out} is unchanged" in result.stderr
    assert out.read_text() == "the previous good deck"
    assert [p.name for p in out_dir.iterdir()] == ["deck-with-notes.pptx"]


def test_interrupted_delivery_leaves_no_partial_copy(tmp_path):
    _fake_osascript(tmp_path, succeed=True)
    # A cp that writes half a file, then the wrapper is sent SIGTERM mid-copy.
    fake_cp = tmp_path / "cp"
    fake_cp.write_text(
        "#!/bin/bash\nfor last; do :; done\n"
        'case "$(basename "$last")" in\n'
        "  .deck-with-notes.pptx.*)\n"
        '    printf partial > "$last"; kill -TERM $PPID; sleep 1; exit 1 ;;\n'
        '  *) exec /bin/cp "$@" ;;\n'
        "esac\n"
    )
    fake_cp.chmod(0o755)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "deck-with-notes.pptx").write_text("the previous good deck")
    result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    assert result.returncode != 0
    assert "done ->" not in result.stdout
    assert out.read_text() == "the previous good deck"
    assert [p.name for p in out_dir.iterdir()] == ["deck-with-notes.pptx"]
    assert not list((tmp_path / ".deckops-staging").glob("notes-run.*"))


@pytest.mark.parametrize("as_symlink", [False, True])
def test_directory_destination_is_rejected_before_powerpoint_runs(tmp_path, as_symlink):
    record = _fake_osascript(tmp_path, succeed=True)
    real_dir = tmp_path / "decks"
    real_dir.mkdir()
    out = real_dir
    if as_symlink:
        out = tmp_path / "decks-link"
        out.symlink_to(real_dir, target_is_directory=True)
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"0": "x"}), encoding="utf-8")
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}", HOME=str(tmp_path))
    result = subprocess.run(
        ["bash", str(WRAPPER), str(_deck(tmp_path, 1)), str(out), str(notes)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert f"the output path {out} is a directory" in result.stderr
    assert "pass the path of the deck file to write" in result.stderr
    assert not record.exists()  # osascript never ran
    assert list(real_dir.iterdir()) == []


def test_success_replaces_the_previous_output_with_the_complete_copy(tmp_path):
    _fake_osascript(tmp_path, succeed=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "deck-with-notes.pptx").write_text("the previous deck")
    result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    assert result.returncode == 0, result.stderr
    assert out.read_text() == ""  # the fake save's empty file, not the old one
    assert [p.name for p in out_dir.iterdir()] == ["deck-with-notes.pptx"]


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


@ROOT_IGNORES_PERMISSIONS
def test_container_stage_cleanup_failure_keeps_a_successful_delivery(tmp_path):
    # A PowerPoint container makes container-stage.sh stage into
    # .deckops-stage/<pid>/; the fake plants a read-only folder there so the
    # EXIT trap's container cleanup really fails.
    (tmp_path / "Library/Containers/com.microsoft.Powerpoint/Data").mkdir(parents=True)
    record = tmp_path / "argv.bin"
    p = tmp_path / "osascript"
    p.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\0' \"$@\" > '{record}'\n"
        'locked="$(dirname "$(dirname "$3")")/locked"\n'
        'mkdir "$locked"\ntouch "$locked/pinned"\nchmod 500 "$locked"\n'
        'touch "$6"\ntouch "$3"\necho "Notes applied: 1"\n'
    )
    p.chmod(0o755)
    try:
        result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    finally:
        stage_root = Path(_argv(record)[2]).parent.parent
        (stage_root / "locked").chmod(0o700)
    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert f"done -> {out}" in result.stdout
    assert "WARNING: could not remove the PowerPoint staging folder" in result.stderr


def _staging_holds(tmp_path, text):
    staging = tmp_path / ".deckops-staging"
    return any(
        text.encode() in p.read_bytes() for p in staging.rglob("*") if p.is_file()
    )


def test_success_leaves_no_staged_deck_behind(tmp_path):
    deck = "STAGED DECK WITH ITS NOTES"
    _fake_osascript(tmp_path, succeed=True, saved=deck)
    result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    assert result.returncode == 0, result.stderr
    assert out.read_text() == deck
    assert not _staging_holds(tmp_path, deck)


@ROOT_IGNORES_PERMISSIONS
def test_failure_after_save_leaves_no_staged_deck_behind(tmp_path):
    deck = "STAGED DECK WITH ITS NOTES"
    _fake_osascript(tmp_path, succeed=True, saved=deck)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_dir.chmod(0o500)
    try:
        result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    finally:
        out_dir.chmod(0o700)
    assert result.returncode == 1
    assert not out.exists()
    assert not _staging_holds(tmp_path, deck)


def test_destination_that_becomes_a_directory_during_the_run_is_refused(tmp_path):
    out = tmp_path / "out" / "deck-with-notes.pptx"
    # Passes the up-front check, then turns into a directory while "PowerPoint" runs.
    _fake_osascript(
        tmp_path, succeed=True, saved="deck", before_save=f"mkdir -p '{out}'"
    )
    result, _ = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    assert result.returncode == 1
    assert f"{out} is a directory, so nothing was delivered" in result.stderr
    assert "done ->" not in result.stdout
    assert out.is_dir() and list(out.iterdir()) == []
    assert [p.name for p in out.parent.iterdir()] == ["deck-with-notes.pptx"]


@pytest.mark.parametrize("via_symlink", [False, True])
def test_output_that_is_the_base_itself_is_refused(tmp_path, via_symlink):
    record = _fake_osascript(tmp_path, succeed=True, saved="new")
    base = _deck(tmp_path, 1)
    before = base.read_bytes()
    out = base
    if via_symlink:
        out = tmp_path / "same-deck.pptx"
        out.symlink_to(base)
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"0": "x"}), encoding="utf-8")
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}", HOME=str(tmp_path))
    result = subprocess.run(
        ["bash", str(WRAPPER), str(base), str(out), str(notes)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "is the base deck itself" in result.stderr
    assert not record.exists()
    assert base.read_bytes() == before


def test_base_at_the_old_shared_staging_path_is_preserved(tmp_path):
    # Before stages were run-owned, ~/.deckops-staging/<output name> was the
    # staged deck; a base living there must survive the run untouched.
    _fake_osascript(tmp_path, succeed=True, saved="new deck")
    staging = tmp_path / ".deckops-staging"
    staging.mkdir()
    base = _deck(staging, 1, name="deck-with-notes.pptx")
    before = base.read_bytes()
    result, out = _run(tmp_path, base, {"0": "x"})
    assert result.returncode == 0, result.stderr
    assert base.read_bytes() == before
    assert out.read_text() == "new deck"


def test_concurrent_runs_with_the_same_output_name_never_share_a_stage(tmp_path):
    # Each fake save sleeps, then records its run directory and the two
    # PowerPoint-visible names it was given; shared paths or names would let
    # one run deliver or delete the other's deck, or collide inside PowerPoint.
    p = tmp_path / "osascript"
    p.write_text(
        "#!/bin/bash\n"
        'touch "$6"\nsleep 1\n'
        'printf \'%s|%s|%s\' "$(basename "$(dirname "$6")")" "$4" "$5" > "$3"\n'
        'echo "Notes applied: 1"\n'
    )
    p.chmod(0o755)
    base = _deck(tmp_path, 1)
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"0": "x"}), encoding="utf-8")
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}", HOME=str(tmp_path))
    outs = [tmp_path / f"run{i}" / "deck-with-notes.pptx" for i in (1, 2)]
    procs = [
        subprocess.Popen(
            ["bash", str(WRAPPER), str(base), str(out), str(notes)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for out in outs
    ]
    results = [proc.communicate() + (proc.returncode,) for proc in procs]
    assert all(rc == 0 for _, _, rc in results), results
    runs = [out.read_text().split("|") for out in outs]
    assert all(run_dir.startswith("notes-run.") for run_dir, _, _ in runs)
    assert runs[0][0] != runs[1][0]  # each run delivered its own stage
    names = [name for _, base_name, out_name in runs for name in (base_name, out_name)]
    assert len(set(names)) == 4  # no PowerPoint-visible name is shared
    assert all(name.startswith("notes-run.") for name in names)
    assert not list((tmp_path / ".deckops-staging").glob("notes-run.*"))


def test_save_that_finishes_after_cleanup_has_nowhere_to_land(tmp_path):
    # A timed-out save can complete later. The late writer waits, as a barrier,
    # until the run directory is gone, then tries to save and reports that it
    # tried; the test waits for that report before asserting.
    attempted = tmp_path / "late-save-attempted"
    late_log = tmp_path / "late-save.log"
    p = tmp_path / "osascript"
    p.write_text(
        "#!/bin/bash\n"
        'printf \'save\\n\' > "$7"\ntouch "$6"\n'
        'run_dir="$(dirname "$6")"\n'
        "(\n"
        '  while [ -d "$run_dir" ]; do sleep 0.05; done\n'
        "  if printf 'LATE NOTES-BEARING DECK' > \"$3\"; then echo wrote; fi\n"
        f"  touch '{attempted}'\n"
        f") > '{late_log}' 2>&1 &\n"
        'echo "Microsoft PowerPoint got an error: AppleEvent timed out. (-1712)" >&2\n'
        "exit 1\n"
    )
    p.chmod(0o755)
    result, out = _run(tmp_path, _deck(tmp_path, 1), {"0": "x"})
    for _ in range(200):  # the barrier releases once cleanup has run
        if attempted.exists():
            break
        time.sleep(0.05)
    assert attempted.exists(), "the late save never ran"
    assert result.returncode == 1
    assert "PowerPoint may still be finishing that save" in result.stderr
    assert "a late save has nowhere to land" in result.stderr
    assert "wrote" not in late_log.read_text()  # the save had no folder to land in
    assert not out.exists()
    assert not _staging_holds(tmp_path, "LATE NOTES-BEARING DECK")
    assert not list((tmp_path / ".deckops-staging").glob("notes-run.*"))


@pytest.mark.parametrize("hook_fails", [False, True])
def test_container_stage_runs_registered_hooks_without_changing_status(
    tmp_path, hook_fails
):
    (tmp_path / "Library/Containers/com.microsoft.Powerpoint/Data").mkdir(parents=True)
    ran = tmp_path / "hook-ran"
    script = tmp_path / "wrapper.sh"
    script.write_text(
        "set -euo pipefail\n"
        f"source '{WRAPPER.with_name('container-stage.sh')}'\n"
        f"my_cleanup() {{ touch '{ran}'; {'return 1' if hook_fails else 'return 0'}; }}\n"
        "container_stage_on_exit my_cleanup\n"
        'echo "$CONTAINER_STAGE"\n'
        "exit 3\n"
    )
    env = dict(os.environ, HOME=str(tmp_path))
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, env=env
    )
    assert result.returncode == 3
    assert ran.exists()
    assert not Path(result.stdout.strip()).exists()  # staging dir removed too
    assert ("cleanup step my_cleanup failed" in result.stderr) is hook_fails


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

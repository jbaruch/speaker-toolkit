"""Tests for sync-deck-drivers.py — the driver materializer + mirror guard.

tessl install strips .bas/.applescript, so each driver ships a committed .txt
mirror that survives install; the tool recreates the real files from the mirrors
on a consumer machine and keeps the mirrors in sync with the source drivers.

Two layers here:
- behavior tests on a synthetic temp dir (deterministic, no real drivers)
- a repo guard asserting the committed mirrors are actually in sync (so a forgotten
  `sync-deck-drivers.py mirror` after editing a driver fails CI, not the install)
"""

import os

SCRIPTS_PC = os.path.join(
    os.path.dirname(__file__), os.pardir, "skills", "presentation-creator", "scripts",
)


def _write(p, data: bytes):
    p.write_bytes(data)
    return p


def test_mirror_then_materialize_roundtrip(sync_deck_drivers, tmp_path):
    bas = _write(tmp_path / "Foo.bas", b"Attribute VB_Name=\"Foo\"\nSub X()\nEnd Sub\n")
    scpt = _write(tmp_path / "do-thing.applescript", b"on run\nreturn 1\nend run\n")

    # mirror: real -> .txt
    written = sync_deck_drivers.regenerate_mirrors(tmp_path)
    assert {p.name for p in written} == {"Foo.bas.txt", "do-thing.applescript.txt"}
    assert (tmp_path / "Foo.bas.txt").read_bytes() == bas.read_bytes()
    assert (tmp_path / "do-thing.applescript.txt").read_bytes() == scpt.read_bytes()

    # simulate the install strip: remove the real files, keep mirrors
    bas.unlink()
    scpt.unlink()

    # materialize: .txt -> real
    made = sync_deck_drivers.materialize(tmp_path)
    assert {p.name for p in made} == {"Foo.bas", "do-thing.applescript"}
    assert (tmp_path / "Foo.bas").read_bytes() == (tmp_path / "Foo.bas.txt").read_bytes()
    assert (tmp_path / "do-thing.applescript").read_bytes() == (tmp_path / "do-thing.applescript.txt").read_bytes()


def test_materialize_is_create_if_missing_by_default(sync_deck_drivers, tmp_path):
    _write(tmp_path / "Foo.bas", b"NEW")
    _write(tmp_path / "Foo.bas.txt", b"OLD-MIRROR")
    # real exists -> default materialize must NOT clobber it
    made = sync_deck_drivers.materialize(tmp_path)
    assert made == []
    assert (tmp_path / "Foo.bas").read_bytes() == b"NEW"


def test_materialize_force_overwrites(sync_deck_drivers, tmp_path):
    _write(tmp_path / "Foo.bas", b"STALE")
    _write(tmp_path / "Foo.bas.txt", b"FRESH")
    made = sync_deck_drivers.materialize(tmp_path, force=True)
    assert {p.name for p in made} == {"Foo.bas"}
    assert (tmp_path / "Foo.bas").read_bytes() == b"FRESH"


def test_check_flags_missing_and_drifted_mirrors(sync_deck_drivers, tmp_path):
    _write(tmp_path / "A.bas", b"aaa")               # mirror missing
    _write(tmp_path / "B.applescript", b"bbb")
    _write(tmp_path / "B.applescript.txt", b"DIFFERENT")  # drifted
    problems = sync_deck_drivers.check(tmp_path)
    joined = "\n".join(problems)
    assert "A.bas.txt" in joined and "missing mirror" in joined
    assert "B.applescript.txt" in joined and "out of sync" in joined


def test_check_flags_orphan_mirror(sync_deck_drivers, tmp_path):
    _write(tmp_path / "Ghost.bas.txt", b"no source")  # mirror with no real
    problems = sync_deck_drivers.check(tmp_path)
    assert any("orphan mirror" in p and "Ghost.bas.txt" in p for p in problems)


def test_check_passes_when_in_sync(sync_deck_drivers, tmp_path):
    _write(tmp_path / "Foo.bas", b"same")
    _write(tmp_path / "Foo.bas.txt", b"same")
    assert sync_deck_drivers.check(tmp_path) == []


def test_committed_repo_mirrors_are_in_sync(sync_deck_drivers):
    """The real guard: the committed .txt mirrors must match the real drivers.

    If this fails, someone edited a .bas/.applescript without running
    `sync-deck-drivers.py mirror` — the install-restore would ship a stale driver.
    """
    from pathlib import Path
    problems = sync_deck_drivers.check(Path(SCRIPTS_PC).resolve())
    assert problems == [], "deck-driver mirror drift:\n" + "\n".join(problems)

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

import pytest

SCRIPTS_PC = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    "skills",
    "presentation-creator",
    "scripts",
)


def _write(p, data: bytes):
    p.write_bytes(data)
    return p


def test_mirror_then_materialize_roundtrip(sync_deck_drivers, tmp_path):
    bas = _write(tmp_path / "Foo.bas", b'Attribute VB_Name="Foo"\nSub X()\nEnd Sub\n')
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
    assert (tmp_path / "Foo.bas").read_bytes() == (
        tmp_path / "Foo.bas.txt"
    ).read_bytes()
    assert (tmp_path / "do-thing.applescript").read_bytes() == (
        tmp_path / "do-thing.applescript.txt"
    ).read_bytes()


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
    _write(tmp_path / "A.bas", b"aaa")  # mirror missing
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


# --- content stamp -----------------------------------------------------------
#
# The stamp rides INSIDE RunDeckOps.bas because a saved DeckOps.pptm gives up no
# VBA source: asking the running PowerPoint for DeckOpsVersion() is the only way
# to see which build was imported. Content-addressed rather than hand-bumped, so
# an editor cannot ship a lie by forgetting to bump a counter.


def _stamped(sync_deck_drivers, tmp_path, body: str, stamp: str = "0" * 16):
    p = tmp_path / sync_deck_drivers.STAMP_DRIVER
    p.write_text(
        f"{body}\n{sync_deck_drivers.STAMP_PREFIX}{stamp}"
        f"{sync_deck_drivers.STAMP_SUFFIX}\n",
        encoding="utf-8",
    )
    return p


def test_restamp_writes_a_digest_and_is_idempotent(sync_deck_drivers, tmp_path):
    _stamped(sync_deck_drivers, tmp_path, "Sub A()\nEnd Sub")
    first, changed = sync_deck_drivers.restamp(tmp_path)
    assert changed is True
    assert len(first) == sync_deck_drivers.STAMP_LEN
    second, changed_again = sync_deck_drivers.restamp(tmp_path)
    assert (second, changed_again) == (first, False)


def test_stamp_changes_when_the_macro_body_changes(sync_deck_drivers, tmp_path):
    _stamped(sync_deck_drivers, tmp_path, "Sub A()\nEnd Sub")
    before, _ = sync_deck_drivers.restamp(tmp_path)
    _stamped(sync_deck_drivers, tmp_path, "Sub A()\n' behaviour change\nEnd Sub", before)
    after, changed = sync_deck_drivers.restamp(tmp_path)
    assert changed is True
    assert after != before


def test_stamp_does_not_depend_on_the_stamp_already_there(sync_deck_drivers, tmp_path):
    """Otherwise the digest would chase its own tail and never converge."""
    _stamped(sync_deck_drivers, tmp_path, "Sub A()\nEnd Sub", "deadbeefdeadbeef")
    from_one, _ = sync_deck_drivers.restamp(tmp_path)
    _stamped(sync_deck_drivers, tmp_path, "Sub A()\nEnd Sub", "0123456789abcdef")
    from_other, _ = sync_deck_drivers.restamp(tmp_path)
    assert from_one == from_other


def test_check_flags_a_stale_stamp(sync_deck_drivers, tmp_path):
    p = _stamped(sync_deck_drivers, tmp_path, "Sub A()\nEnd Sub", "stalestalestale0")
    (tmp_path / (p.name + ".txt")).write_bytes(p.read_bytes())  # mirror is in sync
    problems = sync_deck_drivers.check(tmp_path)
    assert any("content stamp is stale" in x for x in problems)


def test_mirror_stamps_before_mirroring(sync_deck_drivers, tmp_path):
    """A mirror carrying a stale stamp would restore a driver that lies about itself."""
    p = _stamped(sync_deck_drivers, tmp_path, "Sub A()\nEnd Sub", "stalestalestale0")
    sync_deck_drivers.regenerate_mirrors(tmp_path)
    mirror = tmp_path / (p.name + ".txt")
    assert mirror.read_bytes() == p.read_bytes()
    assert sync_deck_drivers.check(tmp_path) == []


def test_missing_stamp_line_is_a_named_error(sync_deck_drivers, tmp_path):
    (tmp_path / sync_deck_drivers.STAMP_DRIVER).write_text("Sub A()\nEnd Sub\n")
    with pytest.raises(ValueError, match="has no"):
        sync_deck_drivers.restamp(tmp_path)


def test_duplicate_stamp_lines_are_a_named_error(sync_deck_drivers, tmp_path):
    line = f"{sync_deck_drivers.STAMP_PREFIX}{'0' * 16}{sync_deck_drivers.STAMP_SUFFIX}"
    (tmp_path / sync_deck_drivers.STAMP_DRIVER).write_text(f"{line}\n{line}\n")
    with pytest.raises(ValueError, match="more than one"):
        sync_deck_drivers.restamp(tmp_path)


def test_committed_bas_carries_a_current_stamp(sync_deck_drivers):
    """The shipped module must state its own identity truthfully."""
    from pathlib import Path

    src = Path(SCRIPTS_PC).resolve() / sync_deck_drivers.STAMP_DRIVER
    text = src.read_text(encoding="utf-8")
    assert sync_deck_drivers.read_stamp(text) == sync_deck_drivers.compute_stamp(text)


def test_committed_bas_exposes_the_stamp_to_applescript(sync_deck_drivers):
    """deckops-doctor.py reads it by calling this macro; without it, no staleness check."""
    from pathlib import Path

    text = (Path(SCRIPTS_PC).resolve() / sync_deck_drivers.STAMP_DRIVER).read_text(
        encoding="utf-8"
    )
    assert "Public Function DeckOpsVersion()" in text
    assert "DeckOpsVersion = DECKOPS_STAMP" in text


# --- export ------------------------------------------------------------------


def test_export_copies_the_bas_to_a_reachable_directory(sync_deck_drivers, tmp_path):
    src_dir, dest_dir = tmp_path / "plugin", tmp_path / "vault" / ".deckops"
    src_dir.mkdir()
    _stamped(sync_deck_drivers, src_dir, "Sub A()\nEnd Sub")
    dest = sync_deck_drivers.export_stamped_driver(src_dir, dest_dir)
    assert dest == dest_dir / sync_deck_drivers.STAMP_DRIVER
    assert dest.read_bytes() == (src_dir / sync_deck_drivers.STAMP_DRIVER).read_bytes()


def test_export_materializes_from_the_mirror_when_the_real_bas_is_stripped(
    sync_deck_drivers, tmp_path
):
    """The installed-plugin case: tessl install ships only the .txt mirror."""
    src_dir, dest_dir = tmp_path / "plugin", tmp_path / "out"
    src_dir.mkdir()
    p = _stamped(sync_deck_drivers, src_dir, "Sub A()\nEnd Sub")
    (src_dir / (p.name + ".txt")).write_bytes(p.read_bytes())
    p.unlink()  # the strip
    dest = sync_deck_drivers.export_stamped_driver(src_dir, dest_dir)
    assert dest.exists()
    assert dest.read_bytes() == (src_dir / (p.name + ".txt")).read_bytes()


def test_export_is_idempotent(sync_deck_drivers, tmp_path):
    src_dir, dest_dir = tmp_path / "plugin", tmp_path / "out"
    src_dir.mkdir()
    _stamped(sync_deck_drivers, src_dir, "Sub A()\nEnd Sub")
    first = sync_deck_drivers.export_stamped_driver(src_dir, dest_dir)
    mtime = first.stat().st_mtime_ns
    again = sync_deck_drivers.export_stamped_driver(src_dir, dest_dir)
    assert again == first
    assert again.stat().st_mtime_ns == mtime


def test_export_refreshes_a_stale_copy(sync_deck_drivers, tmp_path):
    src_dir, dest_dir = tmp_path / "plugin", tmp_path / "out"
    src_dir.mkdir()
    dest_dir.mkdir()
    (dest_dir / sync_deck_drivers.STAMP_DRIVER).write_text("old export")
    _stamped(sync_deck_drivers, src_dir, "Sub A()\nEnd Sub")
    dest = sync_deck_drivers.export_stamped_driver(src_dir, dest_dir)
    assert dest.read_bytes() == (src_dir / sync_deck_drivers.STAMP_DRIVER).read_bytes()


def test_export_without_a_source_or_mirror_names_the_fix(sync_deck_drivers, tmp_path):
    src_dir = tmp_path / "plugin"
    src_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="reinstall the plugin"):
        sync_deck_drivers.export_stamped_driver(src_dir, tmp_path / "out")

"""Tests for the retained named-stage primitive shared by owner writers (#243).

The defect that motivated extraction: `write-analysis.py` staged by pathname,
closed the descriptor, and installed with `os.replace(name, target)`. Anything
able to write to the output directory could substitute the staged name between
those steps and have the writer install its bytes while reporting success.

These tests pin the primitive itself and prove both consumers now inherit its
invariants rather than reimplementing or omitting them.
"""

import os
from pathlib import Path

import pytest


@pytest.fixture()
def staged(retained_stage, tmp_path: Path):
    """One retained stage over known bytes, released after the test."""
    payload = b"the exact staged bytes\n"
    target = tmp_path / "target.txt"
    stage = retained_stage.open_retained_stage(
        target,
        payload,
        mode=0o600,
        suffix=".test.tmp",
        label="test artifact",
    )
    try:
        yield stage, payload, target
    finally:
        if stage.descriptor is not None:
            # No suppression: a cleanup failure here is a leaked descriptor or
            # a leaked temp file, and the test should say so.
            retained_stage.close_retained_stage(stage)


# --- the invariants ----------------------------------------------------------


def test_a_clean_stage_verifies_and_installs(retained_stage, staged) -> None:
    stage, payload, target = staged
    retained_stage.verify_retained_stage(stage, payload)
    retained_stage.install_retained_stage(stage, target)
    assert target.read_bytes() == payload
    assert retained_stage.installed_target_warning(stage, target, payload) is None


def test_pathname_substitution_fails_before_install(retained_stage, staged) -> None:
    """Acceptance test 2: a real regular file at the staged name is refused.

    This is the live defect. Before extraction the analysis writer installed the
    substituted bytes here and reported success.
    """
    stage, payload, _target = staged
    foreign = b"attacker-supplied content\n"
    os.unlink(stage.path)
    stage.path.write_bytes(foreign)

    with pytest.raises(retained_stage.StagedInvariantError) as caught:
        retained_stage.verify_retained_stage(stage, payload)

    assert caught.value.invariant == "descriptor_name_identity"
    # The foreign file is someone else's data — cleanup must not delete it.
    report = retained_stage.close_retained_stage(stage)
    assert report.disposition == retained_stage.STAGED_CLEANUP_NAME_NOT_OWNED
    assert stage.path.read_bytes() == foreign
    stage.descriptor = None


def test_hard_link_fails_the_link_count_invariant(
    retained_stage, staged, tmp_path: Path
) -> None:
    stage, payload, _target = staged
    os.link(stage.path, tmp_path / "second-link")

    with pytest.raises(retained_stage.StagedInvariantError) as caught:
        retained_stage.verify_retained_stage(stage, payload)

    assert caught.value.invariant == "link_count"


def test_size_change_fails_the_size_invariant(retained_stage, staged) -> None:
    stage, payload, _target = staged
    os.pwrite(stage.descriptor, b"extra", len(payload))

    with pytest.raises(retained_stage.StagedInvariantError) as caught:
        retained_stage.verify_retained_stage(stage, payload)

    assert caught.value.invariant == "size"


def test_same_size_byte_change_fails_the_exact_bytes_invariant(
    retained_stage, staged
) -> None:
    """A rewrite that preserves length still has to be caught."""
    stage, payload, _target = staged
    os.pwrite(stage.descriptor, b"X", 0)

    with pytest.raises(retained_stage.StagedInvariantError) as caught:
        retained_stage.verify_retained_stage(stage, payload)

    assert caught.value.invariant == "exact_bytes"


def test_digest_binding_fails_when_the_caller_swaps_the_payload(
    retained_stage, staged
) -> None:
    stage, payload, _target = staged
    assert len(payload) > 1
    different = b"Y" * len(payload)

    with pytest.raises(retained_stage.StagedInvariantError) as caught:
        retained_stage.verify_retained_stage(stage, different)

    assert caught.value.invariant == "exact_bytes"


def test_a_directory_at_the_staged_name_is_refused(retained_stage, staged) -> None:
    stage, payload, _target = staged
    os.unlink(stage.path)
    stage.path.mkdir()

    with pytest.raises(retained_stage.StagedInvariantError) as caught:
        retained_stage.verify_retained_stage(stage, payload)

    assert caught.value.invariant in {"descriptor_name_identity", "regular_file"}
    report = retained_stage.close_retained_stage(stage)
    assert report.disposition == retained_stage.STAGED_CLEANUP_NAME_NOT_OWNED
    assert stage.path.is_dir()
    stage.descriptor = None


# --- cleanup reporting (#240, folded in) -------------------------------------


def test_clean_cleanup_removes_the_owned_name(retained_stage, staged) -> None:
    stage, _payload, _target = staged
    report = retained_stage.close_retained_stage(stage)
    assert report.disposition == "removed"
    assert report.clean is True
    assert report.reason_codes == ()
    assert not stage.path.exists()
    stage.descriptor = None


def test_an_already_absent_name_is_reported_not_failed(retained_stage, staged) -> None:
    stage, _payload, _target = staged
    os.unlink(stage.path)
    report = retained_stage.close_retained_stage(stage)
    assert report.disposition == "already_absent"
    assert report.clean is True
    stage.descriptor = None


def test_descriptor_close_failure_is_reported_with_a_stable_reason(
    retained_stage, staged, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage, _payload, _target = staged
    real_close = os.close
    failed = {"done": False}

    def failing_close(descriptor: int) -> None:
        if descriptor == stage.descriptor and not failed["done"]:
            failed["done"] = True
            real_close(descriptor)
            raise OSError("simulated descriptor close failure")
        real_close(descriptor)

    monkeypatch.setattr(retained_stage.os, "close", failing_close)
    report = retained_stage.close_retained_stage(stage)

    assert retained_stage.STAGED_CLEANUP_DESCRIPTOR_CLOSE_FAILED in report.reason_codes
    assert report.clean is False
    assert any("could not close" in warning for warning in report.warnings)
    stage.descriptor = None


def test_unlink_failure_is_reported_with_a_stable_reason(
    retained_stage, staged, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage, _payload, _target = staged

    def failing_unlink(*_args, **_kwargs):
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(retained_stage.os, "unlink", failing_unlink)
    report = retained_stage.close_retained_stage(stage)

    assert retained_stage.STAGED_CLEANUP_UNLINK_FAILED in report.reason_codes
    # The diagnostic names the orphan explicitly rather than leaving it silent.
    assert any(str(stage.path) in warning for warning in report.warnings)
    stage.descriptor = None


def test_interrupts_propagate_through_staging(
    retained_stage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance test 12: cleanup runs, then the interrupt keeps going."""
    real_write = retained_stage._write_descriptor

    def interrupt_after_write(descriptor: int, raw: bytes) -> None:
        real_write(descriptor, raw)
        raise KeyboardInterrupt

    monkeypatch.setattr(retained_stage, "_write_descriptor", interrupt_after_write)

    with pytest.raises(KeyboardInterrupt):
        retained_stage.open_retained_stage(
            tmp_path / "target.txt",
            b"body\n",
            mode=0o600,
            suffix=".test.tmp",
            label="test artifact",
        )

    assert not list(tmp_path.glob(".*.test.tmp"))


# --- both consumers actually share it ----------------------------------------


def test_both_owner_writers_install_through_the_shared_primitive() -> None:
    """Acceptance test 1: one implementation, not two copies.

    A grep-level assertion on purpose: the point of the extraction is that
    neither owner carries its own staging lifecycle any more.
    """
    scripts = Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts"
    analysis = (scripts / "write-analysis.py").read_text(encoding="utf-8")
    database = (scripts / "tracking_database_io.py").read_text(encoding="utf-8")

    for source in (analysis, database):
        assert "from retained_stage import" in source
        assert "open_retained_stage" in source
        assert (
            "install_retained_stage" in source or "_replace_staged_candidate" in source
        )

    # The analysis writer must not fall back to a pathname-only stage-and-rename.
    assert (
        'tempfile.mkstemp(\n        prefix=f".{basename}.", suffix=".stage"'
        not in analysis
    )


def test_analysis_writer_refuses_a_substituted_stage(
    write_analysis, retained_stage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end proof of the live defect, through the real batch writer.

    Before the extraction this installed the foreign bytes and returned
    normally. The batch must now fail closed and leave the target absent.
    """
    target = tmp_path / "analysis.md"
    rendered = [("talk", str(target), "THE REAL ANALYSIS BODY\n")]
    real_stage_text = write_analysis._stage_text
    substituted: dict[str, Path] = {}

    def substituting_stage_text(path, body):
        stage = real_stage_text(path, body)
        os.unlink(stage.path)
        stage.path.write_bytes(b"attacker-supplied content\n")
        substituted["path"] = stage.path
        return stage

    monkeypatch.setattr(write_analysis, "_stage_text", substituting_stage_text)

    with pytest.raises(write_analysis.AnalysisBatchWriteError):
        write_analysis.atomic_write_batch(rendered)

    assert not target.exists()
    # The foreign file was left alone rather than deleted during cleanup.
    assert substituted["path"].read_bytes() == b"attacker-supplied content\n"


def test_analysis_writer_still_writes_a_clean_batch(
    write_analysis, tmp_path: Path
) -> None:
    """The guard must not cost the ordinary path."""
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    write_analysis.atomic_write_batch(
        [("one", str(first), "first body\n"), ("two", str(second), "second body\n")]
    )
    assert first.read_text(encoding="utf-8") == "first body\n"
    assert second.read_text(encoding="utf-8") == "second body\n"
    assert not list(tmp_path.glob(".*.stage"))


def test_stage_verification_failure_carries_its_cleanup_detail(
    tracking_database_io, retained_stage, tmp_path: Path, monkeypatch
) -> None:
    """A pre-install failure must not swallow a failed cleanup.

    This is the #240 shape one level up: the owner catches the invariant error,
    runs cleanup, and would otherwise drop the report on the floor — leaving an
    orphaned staged temp with no diagnostic naming it.
    """
    path = tmp_path / "tracking-database.json"
    path.write_bytes(b'{\n  "talks": []\n}\n')
    expected = tracking_database_io.snapshot_tracking_database(path)
    candidate = tracking_database_io.render_json_object({"talks": [], "config": {}})

    def failing_verify(stage, raw: bytes) -> None:
        raise tracking_database_io.StagedCandidateConflictError(
            stage.path, "exact_bytes", "injected verification failure"
        )

    def failing_unlink(*_args, **_kwargs):
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(
        tracking_database_io, "_verify_staged_candidate", failing_verify
    )
    monkeypatch.setattr(retained_stage.os, "unlink", failing_unlink)

    with pytest.raises(tracking_database_io.StagedCandidateConflictError) as caught:
        tracking_database_io.commit_tracking_database(expected, candidate)

    assert caught.value.invariant == "exact_bytes"
    assert "injected verification failure" in caught.value.detail
    # Both the primary invariant and the cleanup failure are reported.
    assert "staged cleanup" in caught.value.detail
    assert "could not remove" in caught.value.detail


def test_incomplete_stage_cleanup_failure_is_not_swallowed(
    retained_stage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`except OSError: pass` here would orphan a temp with no diagnostic.

    The primary error keeps its type and reason_code; the cleanup detail is
    appended rather than discarded.
    """

    def failing_write(descriptor: int, raw: bytes) -> None:
        raise retained_stage.RetainedStageError(
            "injected staging failure", reason_code="staged_shape_invalid"
        )

    def failing_unlink(*_args, **_kwargs):
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(retained_stage, "_write_descriptor", failing_write)
    monkeypatch.setattr(retained_stage.os, "unlink", failing_unlink)

    with pytest.raises(retained_stage.RetainedStageError) as caught:
        retained_stage.open_retained_stage(
            tmp_path / "target.txt",
            b"body\n",
            mode=0o600,
            suffix=".test.tmp",
            label="test artifact",
        )

    assert "injected staging failure" in str(caught.value)
    assert "staged cleanup" in str(caught.value)
    assert "could not remove incomplete staged file" in str(caught.value)
    assert caught.value.reason_code == "staged_shape_invalid"


def test_incomplete_stage_cleanup_failure_warns_when_it_cannot_attach(
    retained_stage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A non-RetainedStageError still gets its cleanup detail surfaced."""

    def failing_write(descriptor: int, raw: bytes) -> None:
        raise ValueError("injected non-staged failure")

    def failing_unlink(*_args, **_kwargs):
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(retained_stage, "_write_descriptor", failing_write)
    monkeypatch.setattr(retained_stage.os, "unlink", failing_unlink)

    with pytest.raises(ValueError):
        retained_stage.open_retained_stage(
            tmp_path / "target.txt",
            b"body\n",
            mode=0o600,
            suffix=".test.tmp",
            label="test artifact",
        )

    assert "could not remove incomplete staged file" in capsys.readouterr().err

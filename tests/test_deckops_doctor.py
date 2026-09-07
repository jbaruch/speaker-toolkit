"""Tests for deckops-doctor.py — the deck-layer setup probe.

The doctor answers three questions the skill previously guessed at: is this the
user's first use, where is the macro container, and is the imported macro current.
The live half drives PowerPoint and cannot run in CI (rules/deck-editing-rules.md);
everything deterministic — path derivation, probe-output parsing, and the verdict
table — is covered here by feeding `verdict()` synthetic probe results.
"""

from pathlib import Path

import pytest


def _ok_probe(stamp="abc123"):
    return {"state": "ok", "stamp": stamp}


def _verdict(deckops_doctor, **kw):
    base = {
        "platform": "darwin",
        "driver_problems": [],
        "container_exists": True,
        "expected_stamp": "abc123",
        "probe": _ok_probe(),
    }
    base.update(kw)
    return deckops_doctor.verdict(**base)


# --- container paths ---------------------------------------------------------


def test_container_paths_are_derived_from_the_vault_root(deckops_doctor, tmp_path):
    paths = deckops_doctor.container_paths(tmp_path)
    assert paths["container"] == tmp_path / ".deckops" / "DeckOps.pptm"
    assert paths["import_source"] == tmp_path / ".deckops" / "RunDeckOps.bas"
    assert paths["dir"] == tmp_path / ".deckops"


def test_import_source_sits_outside_the_plugin_tree(deckops_doctor, tmp_path):
    """The whole point: a path the VBA-editor Import panel can actually show.

    An installed plugin lives under a hidden `.tessl/` directory, so the .bas must
    be reachable from the vault instead.
    """
    paths = deckops_doctor.container_paths(tmp_path)
    assert ".tessl" not in str(paths["import_source"])
    assert paths["import_source"].parent == paths["container"].parent


# --- probe parsing -----------------------------------------------------------


def test_parse_probe_reads_key_value_lines(deckops_doctor):
    fields = deckops_doctor.parse_probe("state=ok\nstamp=deadbeef\n")
    assert fields == {"state": "ok", "stamp": "deadbeef"}


def test_parse_probe_keeps_equals_and_semicolons_in_a_value(deckops_doctor):
    """Container paths are user-chosen; they may contain the delimiters."""
    weird = "/Users/x/My Drive/a=b;c/.deckops/DeckOps.pptm"
    fields = deckops_doctor.parse_probe(f"state=ok\nstamp=aa\ncontainer={weird}")
    assert fields["container"] == weird


def test_parse_probe_drops_unparseable_lines(deckops_doctor):
    fields = deckops_doctor.parse_probe("state=ok\nnoise without a delimiter\n\n")
    assert fields == {"state": "ok"}


def test_parse_probe_of_empty_output_yields_no_state(deckops_doctor):
    assert deckops_doctor.parse_probe("") == {}


# --- verdict -----------------------------------------------------------------


def test_verdict_ok_when_everything_lines_up(deckops_doctor):
    assert _verdict(deckops_doctor) == "ok"


def test_verdict_flags_a_foreign_platform_first(deckops_doctor):
    assert (
        _verdict(deckops_doctor, platform="linux", container_exists=False)
        == "unsupported_platform"
    )


def test_verdict_driver_drift_outranks_a_missing_container(deckops_doctor):
    """Drift means the shipped drivers cannot be trusted, so report that first."""
    assert (
        _verdict(deckops_doctor, driver_problems=["mirror X drifted"], container_exists=False)
        == "driver_drift"
    )


def test_verdict_setup_required_when_the_container_is_absent(deckops_doctor):
    assert _verdict(deckops_doctor, container_exists=False) == "setup_required"


def test_verdict_distinguishes_powerpoint_closed_from_macro_missing(deckops_doctor):
    """Two different asks: launch the app, versus finish the one-time import."""
    assert (
        _verdict(deckops_doctor, probe={"state": "not_running"})
        == "powerpoint_not_running"
    )
    assert (
        _verdict(deckops_doctor, probe={"state": "macro_unreachable", "detail": "-18"})
        == "macro_unreachable"
    )


def test_verdict_catches_a_stale_import(deckops_doctor):
    """The finding nothing could see before: the macro runs, but it is OLD code."""
    assert (
        _verdict(deckops_doctor, probe=_ok_probe("0000old"), expected_stamp="abc123")
        == "macro_stale"
    )


def test_verdict_without_a_stamp_in_the_probe_is_stale_not_ok(deckops_doctor):
    assert _verdict(deckops_doctor, probe={"state": "ok"}) == "macro_stale"


def test_verdict_missing_state_is_unreachable_not_ok(deckops_doctor):
    assert _verdict(deckops_doctor, probe={}) == "macro_unreachable"


def test_verdict_offline_stops_at_the_container_check(deckops_doctor):
    """--offline answers first-use and location, and claims nothing about liveness."""
    assert _verdict(deckops_doctor, probe=None) == "ok"
    assert _verdict(deckops_doctor, probe=None, container_exists=False) == "setup_required"


# --- report ------------------------------------------------------------------


def _scripts_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "skills"
        / "presentation-creator"
        / "scripts"
    )


def test_diagnose_offline_reports_setup_required_on_an_empty_vault(
    deckops_doctor, tmp_path
):
    report = deckops_doctor.diagnose(tmp_path, _scripts_dir(), True, "darwin")
    assert report["status"] == "setup_required"
    assert report["setup_complete"] is False
    assert report["container"]["exists"] is False
    assert report["live"] == {"state": "skipped"}
    assert report["drivers"]["problems"] == []
    # the stamp the doctor compares a live macro against comes from the shipped .bas
    assert len(report["expected_stamp"]) == 16


def test_diagnose_offline_is_ok_once_the_container_exists(deckops_doctor, tmp_path):
    container = tmp_path / ".deckops" / "DeckOps.pptm"
    container.parent.mkdir(parents=True)
    container.write_bytes(b"not a real pptm, but present")
    report = deckops_doctor.diagnose(tmp_path, _scripts_dir(), True, "darwin")
    assert report["status"] == "ok"
    assert report["setup_complete"] is True


def test_diagnose_tracks_whether_the_exported_bas_is_current(deckops_doctor, tmp_path):
    """A .bas exported before a plugin update must not read as current."""
    scripts = _scripts_dir()
    deckops = tmp_path / ".deckops"
    deckops.mkdir()
    (deckops / "DeckOps.pptm").write_bytes(b"present")

    (deckops / "RunDeckOps.bas").write_text("stale copy", encoding="utf-8")
    stale = deckops_doctor.diagnose(tmp_path, scripts, True, "darwin")
    assert stale["import_source"]["exists"] is True
    assert stale["import_source"]["current"] is False

    (deckops / "RunDeckOps.bas").write_bytes((scripts / "RunDeckOps.bas").read_bytes())
    fresh = deckops_doctor.diagnose(tmp_path, scripts, True, "darwin")
    assert fresh["import_source"]["current"] is True


def test_every_status_has_a_formattable_next_step(deckops_doctor):
    """next_step is what the agent acts on — an unformattable one would KeyError."""
    for status, template in deckops_doctor.STATUSES.items():
        rendered = template.format(
            container="/v/.deckops/DeckOps.pptm", found="aaa", expected="bbb"
        )
        assert rendered and "{" not in rendered, status


def test_main_rejects_a_missing_vault_root(deckops_doctor, tmp_path, capsys):
    rc = deckops_doctor.main(["--vault-root", str(tmp_path / "nope"), "--offline"])
    assert rc == 1
    assert "vault root not found" in capsys.readouterr().err


def test_main_exits_zero_with_a_verdict_when_setup_is_missing(
    deckops_doctor, tmp_path, capsys
):
    """A verdict IS success — the caller reads `status`, not the exit code."""
    import json

    rc = deckops_doctor.main(["--vault-root", str(tmp_path), "--offline"])
    out = capsys.readouterr()
    assert rc == 0
    assert json.loads(out.out)["status"] == "setup_required"
    assert "setup_required" in out.err


# --- the smoke-test fixture --------------------------------------------------


def test_smoke_test_fixture_is_a_valid_three_slide_op_sequence(validate_deckops):
    """Step 5 of the setup walkthrough ships this instead of asking for a deck."""
    ops = (_scripts_dir() / "smoke-test-ops.txt").read_text(encoding="utf-8")
    assert validate_deckops.validate_ops(ops) == []
    assert sum(1 for ln in ops.splitlines() if ln.startswith("SLIDE")) == 3


@pytest.mark.parametrize("layout_dependent_op", ["BULLET", "BODY"])
def test_smoke_test_fixture_avoids_layout_dependent_placeholders(layout_dependent_op):
    """It runs against an unknown template, so it must not need a body placeholder."""
    ops = (_scripts_dir() / "smoke-test-ops.txt").read_text(encoding="utf-8")
    assert layout_dependent_op not in ops

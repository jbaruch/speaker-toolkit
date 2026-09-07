"""Tests for deckops-doctor.py — the deck-layer setup probe.

The doctor answers three questions the skill previously guessed at: is this the
user's first use, where is the macro container, and is the imported macro current.
The live half drives PowerPoint and cannot run in CI (rules/deck-editing-rules.md);
everything deterministic — path derivation, probe-output parsing, and the verdict
table — is covered here by feeding `verdict()` synthetic probe results.
"""

import json
from pathlib import Path

import pytest


@pytest.fixture
def on_darwin(deckops_doctor, monkeypatch):
    """Pin the platform `main()` reads.

    main() takes it from sys.platform, so on the Ubuntu CI runner every verdict
    short-circuits to unsupported_platform and a test asserting anything else
    passes locally on a Mac and fails in CI. verdict() takes platform as an
    argument and needs no patching; only the main()/diagnose() paths do.
    """
    monkeypatch.setattr(deckops_doctor.sys, "platform", "darwin")


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
        _verdict(
            deckops_doctor, driver_problems=["mirror X drifted"], container_exists=False
        )
        == "driver_drift"
    )


def test_verdict_setup_required_when_no_container_exists_or_is_open(deckops_doctor):
    """Absent on disk AND absent from the running PowerPoint — nothing set up."""
    assert (
        _verdict(
            deckops_doctor,
            container_exists=False,
            probe={"state": "macro_unreachable"},
        )
        == "setup_required"
    )


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


def test_verdict_offline_stops_at_the_container_check(deckops_doctor):
    """--offline answers first-use and location, and claims nothing about liveness."""
    assert _verdict(deckops_doctor, probe=None) == "ok"
    assert (
        _verdict(deckops_doctor, probe=None, container_exists=False) == "setup_required"
    )


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
    deckops_doctor, tmp_path, capsys, on_darwin
):
    """A verdict IS success — the caller reads `status`, not the exit code."""
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


# --- review regressions (PR #412) --------------------------------------------


def _mirrors_only_install(tmp_path) -> Path:
    """A scripts dir shaped like a fresh `tessl install`: mirrors, no sources."""
    import shutil

    scripts = tmp_path / "installed"
    scripts.mkdir()
    for f in _scripts_dir().glob("*.txt"):
        shutil.copyfile(f, scripts / f.name)
    for f in _scripts_dir().glob("*.py"):
        shutil.copyfile(f, scripts / f.name)
    return scripts


def test_a_fresh_install_is_not_reported_as_driver_drift(deckops_doctor, tmp_path):
    """tessl install lands mirrors and no sources; check() reads those as orphans.

    Materializing is the supported recovery, so it runs before the drift check —
    otherwise a valid installation is told to reinstall itself.
    """
    scripts = _mirrors_only_install(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    report = deckops_doctor.diagnose(vault, scripts, True, "darwin")
    assert report["drivers"]["problems"] == []
    assert report["status"] == "setup_required"
    assert "RunDeckOps.bas" in report["drivers"]["materialized"]


@pytest.mark.parametrize(
    ("stamp_text", "problem"),
    [
        ("Option Explicit\n' no stamp line\n", "has no"),
        ('Public Const DECKOPS_STAMP As String = "unfinished\n', "unterminated"),
        ('Public Const DECKOPS_STAMP As String = "abc"\n' * 2, "more than one"),
    ],
)
def test_a_malformed_stamp_reports_drift_instead_of_crashing(
    deckops_doctor, tmp_path, stamp_text, problem
):
    """A damaged real driver gets one actionable stamp diagnostic, not two."""
    scripts = _mirrors_only_install(tmp_path)
    for name in ("RunDeckOps.bas", "RunDeckOps.bas.txt"):
        (scripts / name).write_text(stamp_text, encoding="utf-8")
    report = deckops_doctor.diagnose(tmp_path, scripts, True, "darwin")
    assert report["status"] == "driver_drift"
    assert report["expected_stamp"] == ""
    problems = report["drivers"]["problems"]
    assert sum(problem in p for p in problems) == 1
    assert len(problems) == len(set(problems))


def test_a_mirror_only_stamp_problem_is_not_lost(deckops_doctor, tmp_path, monkeypatch):
    """The fallback mirror needs its own stamp check when no real is available."""
    scripts = _mirrors_only_install(tmp_path)
    (scripts / "RunDeckOps.bas.txt").write_text(
        "Option Explicit\n' no stamp line\n", encoding="utf-8"
    )
    # Keep this test on the fallback-reader branch rather than restoring the real.
    monkeypatch.setattr(deckops_doctor.sync_deck_drivers, "materialize", lambda _: [])
    report = deckops_doctor.diagnose(tmp_path, scripts, True, "darwin")
    assert report["status"] == "driver_drift"
    assert report["expected_stamp"] == ""
    problems = report["drivers"]["problems"]
    assert (
        sum(p.startswith("RunDeckOps.bas has no Public Const") for p in problems) == 1
    )
    assert any("orphan mirror" in p and "RunDeckOps.bas.txt" in p for p in problems)


def test_a_container_open_elsewhere_still_counts_as_set_up(deckops_doctor):
    """A DeckOps.pptm predating the canonical path is set up, not unconfigured."""
    assert (
        _verdict(
            deckops_doctor,
            container_exists=False,
            probe={
                "state": "ok",
                "stamp": "abc123",
                "container": "/elsewhere/DeckOps.pptm",
            },
        )
        == "ok"
    )


def test_an_unreachable_macro_with_a_container_open_is_not_setup_required(
    deckops_doctor,
):
    """The ask is "import the module", not "create a second container"."""
    assert (
        _verdict(
            deckops_doctor,
            container_exists=False,
            probe={
                "state": "macro_unreachable",
                "container": "/elsewhere/DeckOps.pptm",
            },
        )
        == "macro_unreachable"
    )


def test_powerpoint_closed_with_no_container_anywhere_is_setup_required(deckops_doctor):
    assert (
        _verdict(deckops_doctor, container_exists=False, probe={"state": "not_running"})
        == "setup_required"
    )


def test_report_flags_a_container_open_off_the_canonical_path(deckops_doctor, tmp_path):
    scripts = _scripts_dir()
    report = deckops_doctor.diagnose(tmp_path, scripts, True, "darwin")
    assert report["container"]["canonical_mismatch"] is False  # nothing open offline


def test_next_step_names_the_open_container_not_the_canonical_one(
    deckops_doctor, tmp_path, monkeypatch
):
    """Sending the user to the canonical path spawns a second container."""
    monkeypatch.setattr(
        deckops_doctor,
        "run_probe",
        lambda _d: {
            "state": "macro_unreachable",
            "container": "/open/here/DeckOps.pptm",
        },
    )
    report = deckops_doctor.diagnose(tmp_path, _scripts_dir(), False, "darwin")
    assert "/open/here/DeckOps.pptm" in report["next_step"]


# --- probe failures are not verdicts (PR #412 round 3) -----------------------


@pytest.mark.parametrize("failed_state", ["probe_failed", "probe_missing"])
def test_a_probe_that_could_not_run_is_not_a_setup_verdict(
    deckops_doctor, failed_state
):
    """Denied Automation consent must not read as "create a container".

    The driver returns macro_unreachable (exit 0) for the one EXPECTED failure.
    Anything else means the question was never asked, so no fix is prescribed.
    """
    assert (
        _verdict(
            deckops_doctor,
            container_exists=False,
            probe={"state": failed_state, "detail": "not authorised"},
        )
        == failed_state
    )


def test_a_probe_failure_outranks_a_present_container(deckops_doctor):
    assert _verdict(deckops_doctor, probe={"state": "probe_failed"}) == "probe_failed"


def test_an_unparseable_probe_reads_as_failure_not_unreachable(deckops_doctor):
    """An empty probe payload means the driver said nothing, not "no macro"."""
    assert _verdict(deckops_doctor, probe={}) == "probe_failed"


def test_run_probe_maps_a_nonzero_osascript_exit_to_probe_failed(
    deckops_doctor, tmp_path, monkeypatch
):
    import subprocess as sp

    def fake_run(*_a, **_k):
        return sp.CompletedProcess(_a[0], 1, "", "Not authorised to send Apple events")

    monkeypatch.setattr(deckops_doctor.subprocess, "run", fake_run)
    probe = deckops_doctor.run_probe(_scripts_dir())
    assert probe["state"] == "probe_failed"
    assert "Not authorised" in probe["detail"]


def test_run_probe_maps_a_timeout_to_probe_failed(deckops_doctor, monkeypatch):
    import subprocess as sp

    def fake_run(*_a, **_k):
        raise sp.TimeoutExpired(cmd="osascript", timeout=1)

    monkeypatch.setattr(deckops_doctor.subprocess, "run", fake_run)
    probe = deckops_doctor.run_probe(_scripts_dir())
    assert probe["state"] == "probe_failed"
    assert "modal dialog" in probe["detail"]


def test_main_exits_nonzero_when_the_probe_could_not_run(
    deckops_doctor, tmp_path, monkeypatch, capsys, on_darwin
):
    """No verdict was reached, so this is a script failure, not a finding."""
    monkeypatch.setattr(
        deckops_doctor,
        "run_probe",
        lambda _d: {"state": "probe_failed", "detail": "not authorised"},
    )
    rc = deckops_doctor.main(["--vault-root", str(tmp_path)])
    out = capsys.readouterr()
    assert rc == 1
    assert json.loads(out.out)["status"] == "probe_failed"
    assert "UNKNOWN" in out.err


def test_docstring_does_not_claim_to_be_read_only(deckops_doctor):
    """diagnose() writes missing drivers; a blanket read-only claim is false."""
    doc = deckops_doctor.__doc__
    assert "Read-only." not in doc
    assert "materialize" in doc


def test_main_on_a_foreign_platform_says_so_and_still_returns_a_verdict(
    deckops_doctor, tmp_path, monkeypatch, capsys
):
    """The Ubuntu-CI path: a verdict, exit 0, and no PowerPoint probe attempted."""
    monkeypatch.setattr(deckops_doctor.sys, "platform", "linux")
    monkeypatch.setattr(
        deckops_doctor,
        "run_probe",
        lambda _d: pytest.fail("the probe must not run off macOS"),
    )
    rc = deckops_doctor.main(["--vault-root", str(tmp_path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unsupported_platform"


def test_a_corrupt_sibling_script_raises_an_actionable_import_error(
    deckops_doctor, tmp_path, monkeypatch
):
    """A raw traceback would replace the diagnostic this script exists to give."""
    broken = tmp_path / "sync-deck-drivers.py"
    broken.write_text("def (((\n", encoding="utf-8")
    monkeypatch.setattr(deckops_doctor, "__file__", str(tmp_path / "deckops-doctor.py"))
    with pytest.raises(ImportError, match="reinstall the plugin"):
        deckops_doctor._load_sibling("sync_deck_drivers", "sync-deck-drivers.py")


def test_a_missing_sibling_script_raises_an_actionable_import_error(
    deckops_doctor, tmp_path, monkeypatch
):
    monkeypatch.setattr(deckops_doctor, "__file__", str(tmp_path / "deckops-doctor.py"))
    with pytest.raises(ImportError, match="reinstall the plugin"):
        deckops_doctor._load_sibling("nope", "not-here.py")

"""Tests for deckops-smoke-test.sh — the setup smoke-test wrapper.

The wrapper's PowerPoint half cannot run in CI (rules/deck-editing-rules.md), so
build-deck.sh is stubbed and everything around it is exercised for real: template
validation, unique-name copying, build-failure propagation, missing output, and
report serialization. Actual PowerPoint automation stays manual validation.
"""

import json
import os
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

SCRIPTS_PC = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "presentation-creator"
    / "scripts"
)
WRAPPER = "deckops-smoke-test.sh"


def _stage(tmp_path: Path, build_stub: str) -> Path:
    """A scripts dir holding the wrapper, the ops fixture, and a stubbed builder."""
    d = tmp_path / "scripts"
    d.mkdir()
    shutil.copyfile(SCRIPTS_PC / WRAPPER, d / WRAPPER)
    shutil.copyfile(SCRIPTS_PC / "smoke-test-ops.txt", d / "smoke-test-ops.txt")
    shutil.copyfile(SCRIPTS_PC / "verify-deck-text.py", d / "verify-deck-text.py")
    stub = d / "build-deck.sh"
    stub.write_text(build_stub, encoding="utf-8")
    for f in (d / WRAPPER, stub):
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
    return d


# A stub standing in for the real macro run: writes the output file it is handed.
BUILD_OK = '#!/bin/bash\nset -euo pipefail\necho "stub build" >&2\ncp "$1" "$2"\n'
BUILD_SILENT = '#!/bin/bash\nset -euo pipefail\necho "stub wrote nothing" >&2\n'
BUILD_FAILS = '#!/bin/bash\nset -euo pipefail\necho "macro exploded" >&2\nexit 1\n'


def _run(scripts: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(scripts / WRAPPER), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _deck_holding_the_smoke_text(path: Path, *, lose_arrow: bool = False) -> Path:
    """A deck showing each smoke-test op's text, as a clean build leaves it.

    The stub builder copies its base, so the template fixture carries this text.
    """
    drawing = "http://schemas.openxmlformats.org/drawingml/2006/main"
    slides: list[list[str]] = []
    ops = (SCRIPTS_PC / "smoke-test-ops.txt").read_text(encoding="utf-8")
    for line in ops.splitlines():
        fields = line.split("\x1f")
        if fields[0] == "SLIDE":
            slides.append([])
        elif fields[0] in {"TITLE", "TEXT"}:
            slides[-1].append(
                fields[-1].replace("→", "?") if lose_arrow else fields[-1]
            )
    with zipfile.ZipFile(path, "w") as archive:
        for number, runs in enumerate(slides, start=1):
            body = "".join(f"<a:t>{escape(run)}</a:t>" for run in runs)
            archive.writestr(
                f"ppt/slides/slide{number}.xml",
                f'<root xmlns:a="{drawing}">{body}</root>',
            )
    return path


@pytest.fixture
def template(tmp_path) -> Path:
    return _deck_holding_the_smoke_text(tmp_path / "template.pptx")


def test_no_arguments_is_a_usage_error(tmp_path):
    r = _run(_stage(tmp_path, BUILD_OK))
    assert r.returncode == 2
    assert "usage:" in r.stderr


def test_too_many_arguments_is_a_usage_error(tmp_path, template):
    r = _run(_stage(tmp_path, BUILD_OK), str(template), "a", "b")
    assert r.returncode == 2


def test_a_missing_template_names_where_the_path_comes_from(tmp_path):
    r = _run(_stage(tmp_path, BUILD_OK), str(tmp_path / "nope.pptx"))
    assert r.returncode == 1
    assert "template not found" in r.stderr
    assert "template_pptx_path" in r.stderr


def test_a_missing_ops_fixture_says_to_reinstall(tmp_path, template):
    scripts = _stage(tmp_path, BUILD_OK)
    (scripts / "smoke-test-ops.txt").unlink()
    r = _run(scripts, str(template))
    assert r.returncode == 1
    assert "op sequence not found" in r.stderr


def test_a_successful_build_reports_the_output_as_json(tmp_path, template):
    out_dir = tmp_path / "out"
    r = _run(_stage(tmp_path, BUILD_OK), str(template), str(out_dir))
    assert r.returncode == 0
    report = json.loads(r.stdout)
    assert report["ok"] is True
    assert report["slides"] == 3
    assert Path(report["output"]).is_file()
    assert Path(report["base"]).is_file()


def test_a_character_lost_on_the_way_in_fails_the_smoke_test(tmp_path):
    """The silent failure this exists to catch: a valid deck showing `?`."""
    lossy = _deck_holding_the_smoke_text(tmp_path / "lossy.pptx", lose_arrow=True)

    r = _run(_stage(tmp_path, BUILD_OK), str(lossy), str(tmp_path / "out"))

    assert r.returncode == 1
    assert "slide 2 is missing" in r.stderr
    assert '"ok"' not in r.stdout


def test_the_template_is_copied_never_touched(tmp_path, template):
    before = template.read_bytes()
    r = _run(_stage(tmp_path, BUILD_OK), str(template), str(tmp_path / "out"))
    report = json.loads(r.stdout)
    assert template.read_bytes() == before
    assert Path(report["base"]) != template
    assert Path(report["base"]).read_bytes() == before


def test_the_base_copy_is_uniquely_named(tmp_path, template):
    """PowerPoint keys open decks by filename and hands back an open same-named one."""
    scripts = _stage(tmp_path, BUILD_OK)
    out_dir = tmp_path / "out"
    first = json.loads(_run(scripts, str(template), str(out_dir)).stdout)
    second = json.loads(_run(scripts, str(template), str(out_dir)).stdout)
    assert first["base"] != second["base"]
    assert first["output"] != second["output"]


def test_a_build_that_writes_nothing_fails_loudly(tmp_path, template):
    r = _run(_stage(tmp_path, BUILD_SILENT), str(template), str(tmp_path / "out"))
    assert r.returncode == 1
    assert "produced no deck" in r.stderr
    assert r.stdout == ""


def test_a_failing_build_propagates_instead_of_reporting_success(tmp_path, template):
    """set -e must carry the builder's non-zero exit, never swallow it."""
    r = _run(_stage(tmp_path, BUILD_FAILS), str(template), str(tmp_path / "out"))
    assert r.returncode != 0
    assert r.stdout == ""
    assert "macro exploded" in r.stderr


@pytest.mark.parametrize("hostile", ['quo"te', "back\\slash", "sp ace"])
def test_report_stays_valid_json_for_hostile_paths(tmp_path, template, hostile):
    """printf interpolation produced invalid JSON behind exit 0 for these."""
    out_dir = tmp_path / hostile
    r = _run(_stage(tmp_path, BUILD_OK), str(template), str(out_dir))
    assert r.returncode == 0
    report = json.loads(r.stdout)  # raises if the encoder was bypassed
    assert hostile in report["output"]
    assert Path(report["output"]).is_file()


def test_an_absent_out_dir_is_created(tmp_path, template):
    out_dir = tmp_path / "deep" / "nested" / "out"
    r = _run(_stage(tmp_path, BUILD_OK), str(template), str(out_dir))
    assert r.returncode == 0
    assert out_dir.is_dir()


def test_the_shipped_wrapper_has_strict_mode_and_valid_syntax():
    text = (SCRIPTS_PC / WRAPPER).read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert (
        subprocess.run(
            ["bash", "-n", str(SCRIPTS_PC / WRAPPER)], capture_output=True
        ).returncode
        == 0
    )
    assert os.access(SCRIPTS_PC / WRAPPER, os.X_OK)

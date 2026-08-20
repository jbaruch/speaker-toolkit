"""Contract tests for the markdown-deck renderer.

Every test here puts a stand-in renderer on PATH: a script that asserts the
calling conditions the real tool needs (a sized terminal for presenterm) and
writes a PDF built by pypdf in the test. What is under test is the wrapper —
flavor routing, lane refusal, failure containment, and the receipt — and a
stand-in is what makes a corrupt render or a hung process reproducible.

The real tools are exercised in `tests/test_markdown_deck_renderers.py`, which
CI installs them for.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
from pypdf import PdfWriter


SCRIPTS = Path(__file__).parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "render-markdown-deck.py"
SPEC = importlib.util.spec_from_file_location("render_markdown_deck", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
render_markdown_deck = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = render_markdown_deck
SPEC.loader.exec_module(render_markdown_deck)


PRESENTERM_DECK = """\
# One

<!-- pause -->

more

<!-- end_slide -->

# Two
"""

MARP_DECK = """\
---
marp: true
---

# One

---

# Two
"""


def _write_pdf(path: Path, pages: int) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=720, height=405)
    with path.open("wb") as stream:
        writer.write(stream)
    return path


def _install(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / name
    script.write_text(f"#!/bin/bash\nset -euo pipefail\n{body}", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _copy_last_argument_body(source: Path) -> str:
    return f'for last; do :; done\ncp "{source}" "$last"\n'


@pytest.fixture
def fake_path(tmp_path, monkeypatch):
    """Return a directory that leads a PATH holding only what a test installs.

    `/usr/bin` and `/bin` follow it because the stand-in renderers need `cp`
    and `stty`. Nothing else does: a real markdown tool installed under
    `/opt/homebrew` or `~/.local` would otherwise turn a lane-is-missing
    assertion into a live render on a developer's machine.
    """
    directory = tmp_path / "bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", os.pathsep.join([str(directory), "/usr/bin", "/bin"]))
    return directory


def _deck(tmp_path: Path, text: str = PRESENTERM_DECK) -> Path:
    deck = tmp_path / "slides.md"
    deck.write_text(text, encoding="utf-8")
    return deck


def test_a_missing_renderer_names_the_lane_and_the_commands(tmp_path, fake_path):
    deck = _deck(tmp_path)

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            deck,
            output=tmp_path / "slides" / "talk.pdf",
            flavor=None,
            timeout_seconds=30,
        )

    message = str(excinfo.value)
    assert "markdown-deck-presenterm" in message
    assert "presenterm" in message
    assert "weasyprint" in message
    assert not (tmp_path / "slides" / "talk.pdf").exists()


def test_a_half_installed_lane_names_only_what_is_missing(tmp_path, fake_path):
    _install(fake_path, "presenterm", "exit 0\n")
    deck = _deck(tmp_path)

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            deck,
            output=tmp_path / "talk.pdf",
            flavor=None,
            timeout_seconds=30,
        )

    assert "weasyprint not on PATH" in str(excinfo.value)


def test_presenterm_is_handed_a_sized_terminal(tmp_path, fake_path):
    rendered = _write_pdf(tmp_path / "source.pdf", pages=2)
    size_file = tmp_path / "winsize.txt"
    _install(
        fake_path,
        "presenterm",
        f"if [ ! -t 0 ]; then\n"
        f'  echo "Inappropriate ioctl for device (os error 25)" >&2\n'
        f"  exit 1\n"
        f"fi\n"
        f'stty size > "{size_file}"\n' + _copy_last_argument_body(rendered),
    )
    _install(fake_path, "weasyprint", "exit 0\n")

    receipt = render_markdown_deck.execute(
        _deck(tmp_path),
        output=tmp_path / "slides" / "talk.pdf",
        flavor=None,
        timeout_seconds=60,
    )

    assert size_file.read_text(encoding="utf-8").split() == [
        str(render_markdown_deck.PRESENTERM_PTY_ROWS),
        str(render_markdown_deck.PRESENTERM_PTY_COLUMNS),
    ]
    assert receipt["rendered"] is True
    assert receipt["page_count"] == 2


def test_the_rendered_page_count_is_the_slide_count(tmp_path, fake_path):
    rendered = _write_pdf(tmp_path / "source.pdf", pages=2)
    _install(fake_path, "marp", _copy_last_argument_body(rendered))
    deck = _deck(tmp_path, MARP_DECK)
    output = tmp_path / "slides" / "talk.pdf"

    receipt = render_markdown_deck.execute(
        deck,
        output=output,
        flavor=None,
        timeout_seconds=60,
    )

    assert receipt["flavor"] == "marp"
    assert receipt["slide_count"] == 2
    assert receipt["slide_count_basis"] == "rendered_pages"
    assert receipt["source_slide_count"] == 2
    assert receipt["slide_count_agrees_with_source"] is True
    assert receipt["output_path"] == str(output)
    assert output.exists()


def test_a_page_count_the_source_disagrees_with_is_reported_not_reconciled(
    tmp_path,
    fake_path,
):
    rendered = _write_pdf(tmp_path / "source.pdf", pages=7)
    _install(fake_path, "marp", _copy_last_argument_body(rendered))

    receipt = render_markdown_deck.execute(
        _deck(tmp_path, MARP_DECK),
        output=tmp_path / "talk.pdf",
        flavor=None,
        timeout_seconds=60,
    )

    assert receipt["page_count"] == 7
    assert receipt["source_slide_count"] == 2
    assert receipt["slide_count"] == 7
    assert receipt["slide_count_agrees_with_source"] is False


def test_a_failing_renderer_leaves_no_pdf_behind(tmp_path, fake_path):
    _install(fake_path, "marp", 'echo "chromium not found" >&2\nexit 3\n')
    output = tmp_path / "slides" / "talk.pdf"

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path, MARP_DECK),
            output=output,
            flavor=None,
            timeout_seconds=30,
        )

    assert "exited 3" in str(excinfo.value)
    assert "chromium not found" in str(excinfo.value)
    assert not output.exists()


def test_a_renderer_that_writes_nothing_is_a_failure(tmp_path, fake_path):
    _install(fake_path, "marp", 'echo "wrote 0 pages"\nexit 0\n')
    output = tmp_path / "talk.pdf"

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path, MARP_DECK),
            output=output,
            flavor=None,
            timeout_seconds=30,
        )

    assert "without writing" in str(excinfo.value)
    assert not output.exists()


def test_a_renderer_output_the_pdf_probe_rejects_is_not_slide_evidence(
    tmp_path,
    fake_path,
):
    _install(
        fake_path,
        "marp",
        'for last; do :; done\nprintf "not a pdf" > "$last"\n',
    )
    output = tmp_path / "talk.pdf"

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path, MARP_DECK),
            output=output,
            flavor=None,
            timeout_seconds=30,
        )

    assert "not usable as slide evidence" in str(excinfo.value)
    assert not output.exists()


def test_a_rejected_render_leaves_the_previous_one_intact(tmp_path, fake_path):
    """An unreadable PDF must not replace a valid earlier render."""
    good = _write_pdf(tmp_path / "good.pdf", pages=3)
    _install(fake_path, "marp", _copy_last_argument_body(good))
    output = tmp_path / "talk.pdf"
    deck = _deck(tmp_path, MARP_DECK)
    render_markdown_deck.execute(deck, output=output, flavor=None, timeout_seconds=60)
    survivor = output.read_bytes()

    _install(
        fake_path,
        "marp",
        'for last; do :; done\nprintf "not a pdf" > "$last"\n',
    )
    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            deck, output=output, flavor=None, timeout_seconds=60
        )

    assert "was left as it was" in str(excinfo.value)
    assert output.read_bytes() == survivor


def test_an_existing_render_is_replaced_rather_than_appended(tmp_path, fake_path):
    first = _write_pdf(tmp_path / "first.pdf", pages=2)
    _install(fake_path, "marp", _copy_last_argument_body(first))
    output = tmp_path / "talk.pdf"
    deck = _deck(tmp_path, MARP_DECK)
    render_markdown_deck.execute(deck, output=output, flavor=None, timeout_seconds=60)

    second = _write_pdf(tmp_path / "second.pdf", pages=5)
    _install(fake_path, "marp", _copy_last_argument_body(second))
    receipt = render_markdown_deck.execute(
        deck, output=output, flavor=None, timeout_seconds=60
    )

    assert receipt["page_count"] == 5


def test_probe_reports_the_lane_without_running_it(tmp_path, fake_path):
    receipt = render_markdown_deck.execute(
        _deck(tmp_path),
        output=None,
        flavor=None,
        timeout_seconds=30,
    )

    assert receipt["rendered"] is False
    assert receipt["lane"] == "markdown-deck-presenterm"
    assert receipt["lane_available"] is False
    assert receipt["missing_commands"] == ["presenterm", "weasyprint"]
    assert receipt["slide_count_basis"] == "source_separators"
    assert receipt["page_count"] is None


def test_an_operator_named_flavor_overrides_detection(tmp_path, fake_path):
    receipt = render_markdown_deck.execute(
        _deck(tmp_path),
        output=None,
        flavor="slidev",
        timeout_seconds=30,
    )

    assert receipt["flavor"] == "slidev"
    assert receipt["flavor_decided_by"] == "operator"


def test_an_undetectable_deck_asks_for_a_flavor(tmp_path, fake_path):
    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path, "# Just a heading\n"),
            output=None,
            flavor=None,
            timeout_seconds=30,
        )

    assert "--flavor" in str(excinfo.value)


def test_an_oversized_source_is_refused_before_it_is_read(tmp_path, fake_path):
    deck = tmp_path / "slides.md"
    deck.write_bytes(b"#" * (render_markdown_deck.MAX_DECK_BYTES + 1))

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            deck, output=None, flavor="marp", timeout_seconds=30
        )

    assert "over the" in str(excinfo.value)


def test_a_missing_deck_names_the_path(tmp_path, fake_path):
    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            tmp_path / "absent.md", output=None, flavor="marp", timeout_seconds=30
        )

    assert "absent.md" in str(excinfo.value)


def test_a_renderer_that_never_finishes_is_killed(tmp_path, fake_path):
    _install(fake_path, "marp", "sleep 30\n")

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path, MARP_DECK),
            output=tmp_path / "talk.pdf",
            flavor=None,
            timeout_seconds=1,
        )

    assert "--timeout-seconds" in str(excinfo.value)


def test_the_cli_refuses_both_probe_and_output(tmp_path):
    deck = _deck(tmp_path, MARP_DECK)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(deck),
            "--probe",
            "--output",
            str(tmp_path / "talk.pdf"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "exactly one of" in result.stderr


def test_the_cli_refuses_neither_probe_nor_output(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(_deck(tmp_path, MARP_DECK))],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "exactly one of" in result.stderr


def test_the_cli_prints_one_receipt_on_stdout(tmp_path):
    deck = _deck(tmp_path, MARP_DECK)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(deck), "--probe"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["schema_version"] == render_markdown_deck.RECEIPT_SCHEMA_VERSION
    assert receipt["flavor"] == "marp"


def test_a_deck_the_cli_cannot_read_exits_one_with_a_diagnostic(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "absent.md"), "--probe"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "absent.md" in result.stderr


def test_the_lane_and_the_renderer_agree_on_what_each_flavor_needs():
    """Two files name the same commands; a test keeps them from drifting.

    `check-runtime.py` is deliberately stdlib-only with no local imports — it
    is the probe that runs before anything else is known to work — so it cannot
    read the renderer specs, and the renderer cannot import a hyphenated
    script. The duplication is pinned rather than removed.
    """
    check_runtime_script = SCRIPTS / "check-runtime.py"
    spec = importlib.util.spec_from_file_location(
        "check_runtime_lane_contract", check_runtime_script
    )
    assert spec is not None and spec.loader is not None
    check_runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_runtime)

    for renderer in render_markdown_deck.RENDERERS.values():
        lane = check_runtime.LANE_REQUIREMENTS[renderer.lane]
        assert lane["commands"] == {command: command for command in renderer.commands}
        assert lane["modules"] == {}


def test_every_flavor_has_a_renderer_spec_and_a_distinct_lane():
    from markdown_deck import FLAVORS

    lanes = {flavor: render_markdown_deck.RENDERERS[flavor].lane for flavor in FLAVORS}

    assert set(lanes) == set(FLAVORS)
    assert len(set(lanes.values())) == len(FLAVORS)


# --- #203: the CLI has a closed failure boundary ---


def test_outer_boundary_reports_an_unexpected_failure_without_a_traceback(
    tmp_path,
    capsys,
    monkeypatch,
):
    def explode(*_args, **_kwargs):
        raise RuntimeError("injected failure at /private/vault/slides.md")

    monkeypatch.setattr(render_markdown_deck, "execute", explode)
    deck = _deck(tmp_path, MARP_DECK)

    assert render_markdown_deck.main([str(deck), "--probe"]) == 3

    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err.splitlines()[0])
    assert payload["error"] == "render_markdown_deck_unexpected_failure"
    assert payload["error_type"] == "RuntimeError"
    assert payload["origin"]
    assert payload["output_written"] is False
    assert "injected failure" not in captured.err
    assert "/private/vault/slides.md" not in captured.err
    assert "Traceback" not in captured.err


def test_the_boundary_reports_a_render_this_run_committed(
    tmp_path,
    capsys,
    monkeypatch,
    fake_path,
):
    rendered = _write_pdf(tmp_path / "source.pdf", pages=2)
    _install(fake_path, "marp", _copy_last_argument_body(rendered))
    output = tmp_path / "talk.pdf"
    real_render = render_markdown_deck.render

    def render_then_explode(*args, **kwargs):
        real_render(*args, **kwargs)
        raise RuntimeError("boom after the replace")

    monkeypatch.setattr(render_markdown_deck, "render", render_then_explode)

    assert (
        render_markdown_deck.main(
            [str(_deck(tmp_path, MARP_DECK)), "--output", str(output)]
        )
        == 3
    )

    payload = json.loads(capsys.readouterr().err.splitlines()[0])
    assert payload["output_written"] is True
    assert output.exists()


def test_a_pdf_left_by_an_earlier_run_is_not_reported_as_this_run_s(
    tmp_path,
    capsys,
    monkeypatch,
):
    output = _write_pdf(tmp_path / "talk.pdf", pages=2)

    def explode(*_args, **_kwargs):
        raise RuntimeError("boom before anything was written")

    monkeypatch.setattr(render_markdown_deck, "execute", explode)

    assert (
        render_markdown_deck.main(
            [str(_deck(tmp_path, MARP_DECK)), "--output", str(output)]
        )
        == 3
    )

    payload = json.loads(capsys.readouterr().err.splitlines()[0])
    assert payload["output_written"] is False


def test_the_unexpected_failure_exit_is_distinct_from_the_argparse_exit(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2


def test_a_chatty_pty_renderer_that_never_finishes_is_killed(tmp_path, fake_path):
    """A wall limit, not an idle one: progress output must not defer the kill."""
    _install(
        fake_path,
        "presenterm",
        'while true; do echo "processing slide 1..."; sleep 0.1; done\n',
    )
    _install(fake_path, "weasyprint", "exit 0\n")

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path),
            output=tmp_path / "talk.pdf",
            flavor=None,
            timeout_seconds=1,
        )

    assert "did not finish within 1s" in str(excinfo.value)
    assert not (tmp_path / "talk.pdf").exists()


def test_an_unwritable_output_directory_is_a_verdict_not_a_crash(
    tmp_path,
    fake_path,
):
    rendered = _write_pdf(tmp_path / "source.pdf", pages=1)
    _install(fake_path, "marp", _copy_last_argument_body(rendered))
    blocked = tmp_path / "readonly"
    blocked.mkdir()
    blocked.chmod(0o500)
    try:
        with pytest.raises(render_markdown_deck.RenderError) as excinfo:
            render_markdown_deck.execute(
                _deck(tmp_path, MARP_DECK),
                output=blocked / "talk.pdf",
                flavor=None,
                timeout_seconds=30,
            )
    finally:
        blocked.chmod(0o700)

    assert "writable directory" in str(excinfo.value)


def test_a_flavor_the_caller_invented_is_a_verdict_not_a_crash(tmp_path):
    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path, MARP_DECK),
            output=None,
            flavor="powerpoint",
            timeout_seconds=30,
        )

    assert "unknown flavor 'powerpoint'" in str(excinfo.value)


def test_a_renderer_that_closes_its_terminal_and_hangs_is_still_killed(
    tmp_path,
    fake_path,
):
    """Closing the pty ends the read loop; the wall limit must still apply."""
    _install(
        fake_path,
        "presenterm",
        'echo "processing slide 1..."\nexec 0<&- 1>&- 2>&-\nsleep 30\n',
    )
    _install(fake_path, "weasyprint", "exit 0\n")
    started = time.monotonic()

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path),
            output=tmp_path / "talk.pdf",
            flavor=None,
            timeout_seconds=1,
        )

    assert "did not finish within 1s" in str(excinfo.value)
    assert time.monotonic() - started < 20
    assert not (tmp_path / "talk.pdf").exists()


def test_a_renderer_gets_the_environment_its_spec_declares(tmp_path, fake_path):
    """reveal-md says nothing useful about a failure without its debug channel."""
    _install(
        fake_path,
        "reveal-md",
        'echo "DEBUG=${DEBUG:-unset}" >&2\nexit 1\n',
    )
    deck = tmp_path / "slides.md"
    deck.write_text('# One\n\n<!-- .element: class="fragment" -->\n', encoding="utf-8")

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            deck,
            output=tmp_path / "talk.pdf",
            flavor=None,
            timeout_seconds=30,
        )

    assert "DEBUG=reveal-md*" in str(excinfo.value)


def test_a_renderer_without_declared_environment_inherits_the_callers(
    tmp_path,
    fake_path,
    monkeypatch,
):
    monkeypatch.setenv("SPEAKER_TOOLKIT_MARKER", "inherited")
    _install(
        fake_path,
        "marp",
        'echo "marker=${SPEAKER_TOOLKIT_MARKER:-unset}" >&2\nexit 1\n',
    )

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path, MARP_DECK),
            output=tmp_path / "talk.pdf",
            flavor=None,
            timeout_seconds=30,
        )

    assert "marker=inherited" in str(excinfo.value)


def test_a_renderer_reads_the_staging_files_its_spec_declares(tmp_path, fake_path):
    """reveal.js splits fragments onto separate pages unless its config says not to."""
    _install(
        fake_path,
        "reveal-md",
        'echo "cwd=$PWD" >&2\ncat reveal-md.json >&2\nexit 1\n',
    )
    deck = tmp_path / "slides.md"
    deck.write_text('# One\n\n<!-- .element: class="fragment" -->\n', encoding="utf-8")

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            deck,
            output=tmp_path / "talk.pdf",
            flavor=None,
            timeout_seconds=30,
        )

    message = str(excinfo.value)
    assert '"pdfSeparateFragments": false' in message
    # Read from the staging directory, which is where the file was written.
    assert "cwd=" in message


def test_a_renderer_without_staging_files_keeps_the_callers_directory(
    tmp_path,
    fake_path,
):
    _install(
        fake_path, "marp", 'ls reveal-md.json >&2 || echo "no config" >&2\nexit 1\n'
    )

    with pytest.raises(render_markdown_deck.RenderError) as excinfo:
        render_markdown_deck.execute(
            _deck(tmp_path, MARP_DECK),
            output=tmp_path / "talk.pdf",
            flavor=None,
            timeout_seconds=30,
        )

    assert "no config" in str(excinfo.value)

"""Tests for insert-qr.sh — the shell wrapper's deterministic behavior (arg
validation, staging/move, JSON-only stdout, macro-failure path), with `osascript`
(the real PowerPoint/VBA call) faked on PATH. Only the VBA macro itself is the
manual-validation gap; the wrapper scaffolding around it is testable.
"""
import json
import os
import subprocess
from pathlib import Path

WRAPPER = (
    Path(__file__).resolve().parents[1]
    / "skills/presentation-creator/scripts/insert-qr.sh"
)


def _fake_osascript(dirpath, *, succeed):
    """Write a fake `osascript` into dirpath. The wrapper calls
    `osascript <driver> <base> <STAGE> <png> <slides>`, so the staged output path
    is $3. On success the fake touches it (simulating the macro writing the COPY)
    and echoes the macro return line; on failure it exits non-zero like the driver.
    """
    p = dirpath / "osascript"
    if succeed:
        p.write_text('#!/bin/bash\ntouch "$3"\necho "InsertQR returned: 1"\n')
    else:
        p.write_text('#!/bin/bash\necho "boom" >&2\nexit 1\n')
    p.chmod(0o755)


def _run(args, tmp_path):
    env = dict(os.environ)
    env["PATH"] = f"{tmp_path}:{env['PATH']}"   # shadow the real osascript
    env["HOME"] = str(tmp_path)                  # isolate ~/.deckops-staging
    return subprocess.run(
        ["bash", str(WRAPPER), *args], capture_output=True, text=True, env=env
    )


def test_success_emits_json_only_stdout(tmp_path):
    base = tmp_path / "deck.pptx"; base.write_text("x")
    png = tmp_path / "qr.png"; png.write_text("x")
    out = tmp_path / "out.pptx"
    _fake_osascript(tmp_path, succeed=True)

    r = _run([str(base), str(out), str(png), "1,3"], tmp_path)
    assert r.returncode == 0, r.stderr
    # stdout is the documented JSON only (the macro return line went to stderr)
    assert json.loads(r.stdout) == {"output": str(out)}
    assert out.exists()


def test_missing_base_fails_with_actionable_error(tmp_path):
    png = tmp_path / "qr.png"; png.write_text("x")
    _fake_osascript(tmp_path, succeed=True)

    r = _run([str(tmp_path / "nope.pptx"), str(tmp_path / "o.pptx"), str(png), "1"], tmp_path)
    assert r.returncode != 0
    assert "base deck not found" in r.stderr


def test_missing_png_fails(tmp_path):
    base = tmp_path / "deck.pptx"; base.write_text("x")
    _fake_osascript(tmp_path, succeed=True)

    r = _run([str(base), str(tmp_path / "o.pptx"), str(tmp_path / "nope.png"), "1"], tmp_path)
    assert r.returncode != 0
    assert "QR PNG not found" in r.stderr


def test_macro_failure_path(tmp_path):
    base = tmp_path / "deck.pptx"; base.write_text("x")
    png = tmp_path / "qr.png"; png.write_text("x")
    out = tmp_path / "out.pptx"
    _fake_osascript(tmp_path, succeed=False)

    r = _run([str(base), str(out), str(png), "1"], tmp_path)
    assert r.returncode != 0
    assert not out.exists()


def test_too_few_args(tmp_path):
    r = _run([str(tmp_path / "deck.pptx")], tmp_path)
    assert r.returncode == 2
    assert "usage:" in r.stderr

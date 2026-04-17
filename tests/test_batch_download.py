"""Tests for batch-download-videos.sh — directory structure and argument handling."""

import os
import subprocess
import stat

import pytest

SCRIPT = os.path.join(
    os.path.dirname(__file__), os.pardir,
    "skills", "vault-ingress", "scripts", "batch-download-videos.sh",
)
SCRIPT = os.path.abspath(SCRIPT)


def _make_fake_ytdlp(tmp_path):
    """Create a fake yt-dlp that just touches the output file."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "yt-dlp"
    # Parse the -o flag to find output path, then create a small file
    fake.write_text("""\
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        -o) shift; touch "$1" ;;
        *) ;;
    esac
    shift
done
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return str(bin_dir)


def test_creates_directory_structure(tmp_path):
    """Script creates <vault>/slides-rebuild/<id>/ directories."""
    vault = tmp_path / "vault"
    vault.mkdir()
    bin_dir = _make_fake_ytdlp(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        ["bash", SCRIPT, str(vault), "abc123", "def456"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert result.returncode == 0
    assert (vault / "slides-rebuild" / "abc123").is_dir()
    assert (vault / "slides-rebuild" / "def456").is_dir()


def test_downloads_to_correct_path(tmp_path):
    """Output file lands at <vault>/slides-rebuild/<id>/<id>.mp4."""
    vault = tmp_path / "vault"
    vault.mkdir()
    bin_dir = _make_fake_ytdlp(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    subprocess.run(
        ["bash", SCRIPT, str(vault), "xyz789"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    expected = vault / "slides-rebuild" / "xyz789" / "xyz789.mp4"
    assert expected.exists()

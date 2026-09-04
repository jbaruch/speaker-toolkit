"""Tests for shared yt-dlp executable resolution."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import sys

import pytest


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "vault-ingress"
    / "scripts"
    / "ytdlp_runtime.py"
)
SPEC = importlib.util.spec_from_file_location("ytdlp_runtime", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
ytdlp_runtime = importlib.util.module_from_spec(SPEC)
sys.modules.setdefault("ytdlp_runtime", ytdlp_runtime)
SPEC.loader.exec_module(ytdlp_runtime)


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_interpreter_console_script_wins_over_path(monkeypatch, tmp_path: Path) -> None:
    pinned = _executable(tmp_path / "runtime" / "yt-dlp")
    stale = _executable(tmp_path / "path" / "yt-dlp")
    monkeypatch.delenv("YT_DLP", raising=False)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("PATH", f"{stale.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(ytdlp_runtime.sys, "executable", str(pinned.parent / "python"))

    assert ytdlp_runtime.resolve_ytdlp() == pinned


def test_explicit_override_wins_over_interpreter(monkeypatch, tmp_path: Path) -> None:
    override = _executable(tmp_path / "override" / "yt-dlp")
    pinned = _executable(tmp_path / "runtime" / "yt-dlp")
    monkeypatch.setenv("YT_DLP", str(override))
    monkeypatch.setattr(ytdlp_runtime.sys, "executable", str(pinned.parent / "python"))

    assert ytdlp_runtime.resolve_ytdlp() == override


def test_invalid_override_fails_instead_of_falling_back(
    monkeypatch, tmp_path: Path
) -> None:
    pinned = _executable(tmp_path / "runtime" / "yt-dlp")
    monkeypatch.setenv("YT_DLP", str(tmp_path / "missing"))
    monkeypatch.setattr(ytdlp_runtime.sys, "executable", str(pinned.parent / "python"))

    try:
        ytdlp_runtime.resolve_ytdlp()
    except ytdlp_runtime.YtDlpResolutionError as exc:
        assert exc.code == "ytdlp_override_invalid"
    else:  # pragma: no cover - assertion branch
        raise AssertionError("invalid YT_DLP override unexpectedly fell back")


def test_path_is_only_a_compatibility_fallback(monkeypatch, tmp_path: Path) -> None:
    fallback = _executable(tmp_path / "path" / "yt-dlp")
    monkeypatch.delenv("YT_DLP", raising=False)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("PATH", str(fallback.parent))
    monkeypatch.setattr(ytdlp_runtime.sys, "executable", "/missing/bin/python")
    monkeypatch.setattr(
        ytdlp_runtime,
        "__file__",
        str(tmp_path / "isolated" / "a" / "b" / "c" / "ytdlp_runtime.py"),
    )

    assert ytdlp_runtime.resolve_ytdlp() == fallback


def test_missing_binary_has_a_typed_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("YT_DLP", raising=False)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(ytdlp_runtime.sys, "executable", "/missing/bin/python")
    monkeypatch.setattr(
        ytdlp_runtime,
        "__file__",
        str(tmp_path / "isolated" / "a" / "b" / "c" / "ytdlp_runtime.py"),
    )

    with pytest.raises(ytdlp_runtime.YtDlpResolutionError) as excinfo:
        ytdlp_runtime.resolve_ytdlp()

    assert excinfo.value.code == "ytdlp_not_found"


def test_calendar_versions_ignore_zero_padding_only() -> None:
    assert ytdlp_runtime.normalized_ytdlp_version("2026.08.19") == (2026, 8, 19)
    assert ytdlp_runtime.normalized_ytdlp_version("2026.8.19") == (2026, 8, 19)
    assert ytdlp_runtime.normalized_ytdlp_version("latest") is None
    assert ytdlp_runtime.normalized_ytdlp_version("2026.8.19.1") is None

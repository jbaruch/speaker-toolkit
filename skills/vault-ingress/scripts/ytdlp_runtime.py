"""Resolve the yt-dlp console script declared by the toolkit runtime.

The project pins yt-dlp as a Python dependency. A bare ``yt-dlp`` subprocess
still resolves through ``PATH``, where an older system installation can shadow
that pin. Keep every caller on one resolution order: explicit override, the
running interpreter, its active virtual environment, the toolkit virtual
environment, then ``PATH`` as a compatibility fallback.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


# Dependabot renews the pyproject.toml pin weekly. Every such manifest update
# must renew this runtime mirror in the same PR;
# tests/test_check_runtime.py::test_ytdlp_version_authority_is_synchronized
# enforces that the two pins stay identical.
YTDLP_REQUIRED_VERSION = "2026.8.19"
YTDLP_RESOLUTION_FAILURE_CODES = frozenset(
    {
        "ytdlp_override_invalid",
        "ytdlp_not_found",
        "ytdlp_version_unavailable",
    }
)


class YtDlpResolutionError(RuntimeError):
    """No usable yt-dlp executable, with a typed recovery code."""

    def __init__(self, code: str, message: str) -> None:
        if code not in YTDLP_RESOLUTION_FAILURE_CODES:
            raise ValueError("invalid yt-dlp resolution failure code")
        super().__init__(message)
        self.code = code


def resolve_ytdlp() -> Path:
    """Return the pinned yt-dlp console script before consulting ``PATH``."""
    override = os.environ.get("YT_DLP")
    if override:
        candidate = Path(override)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise YtDlpResolutionError(
            "ytdlp_override_invalid",
            f"YT_DLP is set to {override!r}, which is not an executable file — "
            "point it at a yt-dlp binary or unset it",
        )

    candidates = [Path(sys.executable).parent / "yt-dlp"]
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        candidates.append(Path(virtual_env) / "bin" / "yt-dlp")
    toolkit_root = Path(__file__).resolve().parents[3]
    candidates.append(toolkit_root / ".venv" / "bin" / "yt-dlp")

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    found = shutil.which("yt-dlp")
    if found:
        return Path(found)
    raise YtDlpResolutionError(
        "ytdlp_not_found",
        "cannot find yt-dlp — install the pinned version with `pip install .` "
        "into the toolkit environment, or set YT_DLP to its path",
    )


def normalized_ytdlp_version(value: str) -> tuple[int, int, int] | None:
    """Normalize yt-dlp's calendar version without an external parser."""
    parts = value.strip().split(".")
    if len(parts) != 3 or any(not part.isdecimal() for part in parts):
        return None
    year, month, day = (int(part) for part in parts)
    return year, month, day

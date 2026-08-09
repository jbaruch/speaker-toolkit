"""Every CLI's `--help` survives `python -OO`, which strips docstrings (#162).

Each entrypoint derives its argparse description from its module docstring.
Under `-OO` that docstring is `None`, and the obvious guard is a trap:

    (__doc__ or "").splitlines()[0]     # IndexError — "".splitlines() == []
    (__doc__ or "").split("\\n")[0]      # ""         — "".split("\\n") == [""]

`--help` is the one command an operator reaches for when nothing else works,
and the first form killed it before argparse could run.

The assertion is exit 0, not the absence of a traceback. Several of these
scripts carry an outer failure boundary (#203) that converts an unexpected
exception into a clean stderr diagnostic and exit 2 — so a traceback check
passes while `--help` is broken. That is exactly how this bug survived its
first fix attempt.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]

# The marker is the argparse description itself, so discovery tracks the thing
# under test rather than a hand-maintained list. A new CLI is covered the day
# it lands.
DOCSTRING_DESCRIPTION_MARKER = "description=(__doc__"

DOCSTRING_CLIS = sorted(
    path
    for path in REPO_ROOT.glob("skills/*/scripts/*.py")
    if DOCSTRING_DESCRIPTION_MARKER in path.read_text(encoding="utf-8")
)


def test_the_discovery_found_the_clis():
    """An empty list would make every parametrized case vacuously pass."""
    assert len(DOCSTRING_CLIS) >= 10, [p.name for p in DOCSTRING_CLIS]


@pytest.mark.parametrize("script", DOCSTRING_CLIS, ids=lambda p: p.name)
def test_help_survives_stripped_docstrings(script):
    result = subprocess.run(
        [sys.executable, "-OO", str(script), "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"`python -OO {script.name} --help` exited {result.returncode}\n"
        f"stderr: {result.stderr[:500]}"
    )
    assert "usage:" in result.stdout

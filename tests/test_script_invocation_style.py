"""Guard: skill scripts must never be invoked in a way that needs the exec bit.

`tessl install` strips the executable bit from every script it packages — all 41
installed `.sh` / `.py` files arrive mode 644 in a consumer install, including
the 33 that are `100755` in git. So `./scripts/foo.sh` works in this checkout
and fails only for consumers, which is the same shape as the 0.18.43-0.18.61
packaging regression: correct in the repo, broken in the package, silent until
someone else trips on it.

Every invocation must therefore name an interpreter (`bash x.sh`, `python3
x.py`) or use `source` / `.`, none of which consult the exec bit.

See issue #134.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# A bare "./..." path ending in .sh/.py — an execution that needs the exec bit.
# Anchored on a non-path character so "../foo.sh" and "x/./y.sh" don't match.
DOT_SLASH_INVOCATION = re.compile(
    r"(?:^|[^A-Za-z0-9_/.-])\./[A-Za-z0-9_./-]*\.(?:sh|py)\b"
)

# A sibling script addressed through a variable, e.g. "$HERE/ensure-drivers.sh".
VAR_PATH_INVOCATION = re.compile(
    r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/[A-Za-z0-9_.-]+\.(?:sh|py)\b"
)

# Prefixes that make a reference safe: an explicit interpreter, or sourcing.
SAFE_PREFIX = re.compile(r"^\s*(?:source\s|\.\s|bash\s|sh\s|python3?\s|exec\s+(?:bash|sh|python3?)\s)")


def _tracked(*globs: str) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", *globs],
        check=True, capture_output=True, text=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def _lines(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return list(enumerate(text.splitlines(), start=1))


@pytest.fixture(scope="module")
def skill_files() -> list[Path]:
    """Every skill doc and skill script — the surfaces a consumer executes."""
    files = _tracked("skills/**/*.md", "skills/*/scripts/*")
    # .txt files are inert mirrors of the drivers tessl install strips; they are
    # read and rewritten by ensure-drivers.sh, never executed.
    return [f for f in files if f.suffix != ".txt"]


def test_skill_files_exist(skill_files: list[Path]) -> None:
    """Guard the guard: an empty file list would make every check below vacuous."""
    assert len(skill_files) > 50


def test_no_dot_slash_script_invocations(skill_files: list[Path]) -> None:
    """No `./foo.sh` — it needs an exec bit the consumer's install does not have."""
    offenders = []
    for path in skill_files:
        for lineno, line in _lines(path):
            if DOT_SLASH_INVOCATION.search(line):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Scripts invoked via a bare './' path. tessl install strips the "
        "executable bit, so these work in this checkout and fail for "
        "consumers. Prefix with an interpreter (`bash x.sh`, `python3 x.py`).\n"
        + "\n".join(offenders)
    )


def test_sibling_scripts_are_sourced_or_interpreted(skill_files: list[Path]) -> None:
    """A `$HERE/foo.sh` reference must be sourced or given an interpreter."""
    offenders = []
    for path in skill_files:
        for lineno, line in _lines(path):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if not VAR_PATH_INVOCATION.search(line):
                continue
            if SAFE_PREFIX.match(line):
                continue
            # An assignment or a non-executing mention (test -f, cp, rm, cat…)
            # never consults the exec bit.
            if re.match(r"^\s*(?:local\s+|declare\s+|export\s+)?[A-Za-z_][A-Za-z0-9_]*=", line):
                continue
            if re.match(r"^\s*(?:if|test|\[|cp|mv|rm|cat|chmod|mkdir|touch|echo|printf|ls)\b", stripped):
                continue
            rel = path.relative_to(REPO_ROOT)
            offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Sibling scripts executed directly through a variable path. tessl "
        "install strips the executable bit; use `source \"$HERE/x.sh\"` or "
        "`bash \"$HERE/x.sh\"`.\n" + "\n".join(offenders)
    )


def test_detector_catches_a_dot_slash_invocation() -> None:
    """The regex must actually fire — a guard that never matches guards nothing."""
    assert DOT_SLASH_INVOCATION.search("./scripts/build-deck.sh --deck x")
    assert DOT_SLASH_INVOCATION.search("run ./generate-qr.py")
    assert not DOT_SLASH_INVOCATION.search("bash scripts/build-deck.sh")
    assert not DOT_SLASH_INVOCATION.search("python3 scripts/generate-qr.py")


def test_detector_distinguishes_sourced_from_executed() -> None:
    executed = '"$HERE/ensure-drivers.sh"'
    sourced = 'source "$HERE/ensure-drivers.sh"'
    interpreted = 'bash "$HERE/ensure-drivers.sh"'

    assert VAR_PATH_INVOCATION.search(executed)
    assert not SAFE_PREFIX.match(executed)
    assert SAFE_PREFIX.match(sourced)
    assert SAFE_PREFIX.match(interpreted)

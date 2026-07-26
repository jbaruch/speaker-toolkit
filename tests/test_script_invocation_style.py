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

# Shell keywords that precede a command WITHOUT changing whether that command
# runs. `if "$HERE/x.sh"; then` executes the script exactly like a bare call, so
# these must be peeled off and the remainder classified — never treated as
# making the line non-executing.
CONTROL_PREFIX = re.compile(r"^\s*(?:if|elif|while|until|then|else|do|!|time)\s+")

# Commands that name a path without executing it. `test`/`[` inspect it, the
# rest copy or print it — none consult the exec bit.
# `[` / `[[` sit outside the \b group: no word boundary exists between a
# bracket and the space that follows it, so `\b` would never match there.
NON_EXECUTING = re.compile(
    r"^\s*(?:\[\[?(?=\s)|(?:test|cp|mv|rm|cat|chmod|chown|mkdir|touch|echo|"
    r"printf|ls|grep|sed|awk|head|tail|wc|diff|install|ln|return|shift)\b)"
)

# `X=...`, `local X=...`, `export X=...` — a path stored, not run.
ASSIGNMENT = re.compile(
    r"^\s*(?:local\s+|declare\s+|export\s+|readonly\s+)?[A-Za-z_][A-Za-z0-9_]*="
)

# Shell separators between commands. A line can chain several, and only the
# segment holding the script path decides whether that script is executed.
SEGMENT_SEPARATOR = re.compile(r"&&|\|\||;|\|")


def _reference_is_safe(segment: str) -> bool:
    """True when this command segment names a script without needing exec.

    Peels leading control keywords first, so `if bash "$HERE/x.sh"; then` is
    judged on `bash "$HERE/x.sh"` while `if "$HERE/x.sh"; then` is judged on the
    bare invocation and correctly flagged.
    """
    candidate = segment
    while True:
        peeled = CONTROL_PREFIX.sub("", candidate, count=1)
        if peeled == candidate:
            break
        candidate = peeled
    return bool(
        SAFE_PREFIX.match(candidate)
        or NON_EXECUTING.match(candidate)
        or ASSIGNMENT.match(candidate)
    )


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


def test_both_categories_are_scanned(skill_files: list[Path]) -> None:
    """Guard the guard, per category.

    A bare total-count assertion is not enough: there are 149 skill docs and 50
    scripts, so the scripts glob could stop matching entirely and the docs alone
    would still clear any total the scripts could have contributed to. Assert
    each category is populated, so neither check can go half-vacuous.
    """
    docs = [f for f in skill_files if f.suffix == ".md"]
    scripts = [f for f in skill_files if "/scripts/" in f.as_posix()]

    assert len(docs) >= 100, f"skill docs missing from the scan (found {len(docs)})"
    assert len(scripts) >= 40, f"skill scripts missing from the scan (found {len(scripts)})"


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
            if line.lstrip().startswith("#"):
                continue
            if not VAR_PATH_INVOCATION.search(line):
                continue
            # Judge each command segment on its own; only the one holding the
            # script path determines whether that script gets executed.
            unsafe = [
                seg for seg in SEGMENT_SEPARATOR.split(line)
                if VAR_PATH_INVOCATION.search(seg) and not _reference_is_safe(seg)
            ]
            if not unsafe:
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


@pytest.mark.parametrize("line", [
    '"$HERE/ensure-drivers.sh"',
    'if "$HERE/ensure-drivers.sh"; then',
    'elif "$HERE/ensure-drivers.sh"; then',
    'while "$HERE/poll.sh"; do',
    'if ! "$HERE/ensure-drivers.sh"; then',
    'mkdir -p "$OUT" && "$HERE/ensure-drivers.sh"',
])
def test_detector_flags_executed_sibling_scripts(line: str) -> None:
    """A shell conditional still EXECUTES its command — `if` is not a pass."""
    unsafe = [
        seg for seg in SEGMENT_SEPARATOR.split(line)
        if VAR_PATH_INVOCATION.search(seg) and not _reference_is_safe(seg)
    ]
    assert unsafe, f"should have been flagged: {line}"


@pytest.mark.parametrize("line", [
    'source "$HERE/ensure-drivers.sh"',
    '. "$HERE/ensure-drivers.sh"',
    'bash "$HERE/ensure-drivers.sh"',
    'python3 "$HERE/persist-results.py"',
    'if bash "$HERE/ensure-drivers.sh"; then',
    'if [ -f "$HERE/ensure-drivers.sh" ]; then',
    'if ! source "$HERE/ensure-drivers.sh"; then',
    'DRIVER="$HERE/ensure-drivers.sh"',
    'cp "$HERE/RunDeckOps.bas.py" "$DEST"',
    'bash "$HERE/a.sh" && bash "$HERE/b.sh"',
])
def test_detector_accepts_safe_references(line: str) -> None:
    unsafe = [
        seg for seg in SEGMENT_SEPARATOR.split(line)
        if VAR_PATH_INVOCATION.search(seg) and not _reference_is_safe(seg)
    ]
    assert not unsafe, f"should have been accepted: {line}"

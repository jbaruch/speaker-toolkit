"""Guard: skill scripts must never be invoked in a way that needs the exec bit.

`tessl install` strips the executable bit from every script it packages — all 41
installed `.sh` / `.py` files arrive mode 644 in a consumer install, including
the 33 that are `100755` in git. So `./scripts/foo.sh` works in this checkout
and fails only for consumers, which is the same shape as the 0.18.43-0.18.61
packaging regression: correct in the repo, broken in the package, silent until
someone else trips on it.

The outcome under test is "no invocation consults the exec bit" — NOT "the
string `./` never appears". `bash ./scripts/foo.sh` names an interpreter and is
fine; `FOO=1 "$HERE/x.sh"` is an environment-prefixed execution and is not. So
classification looks at what immediately precedes each script reference rather
than at how the line happens to start.

See issue #134.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# A "./..." path ending in .sh/.py. Anchored on a non-path character so
# "../foo.sh" and "x/./y.sh" don't match.
DOT_SLASH_REFERENCE = re.compile(
    r"(?:^|[^A-Za-z0-9_/.-])(\./[A-Za-z0-9_./-]*\.(?:sh|py))\b"
)

# A script addressed through a variable, e.g. "$HERE/ensure-drivers.sh".
VAR_PATH_REFERENCE = re.compile(
    r"(\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/[A-Za-z0-9_.-]+\.(?:sh|py))\b"
)

# Text immediately before a reference that hands it to an interpreter or sources
# it — neither consults the exec bit. The optional quote covers `bash "$HERE/x"`,
# and this matches inside markdown prose too (``Run `bash ./x.sh` `` ends with
# "bash " at the reference).
INTERPRETER_BEFORE = re.compile(
    r"(?:^|[^A-Za-z0-9_.-])(?:source|\.|bash|sh|zsh|python3?|uv\s+run|exec\s+(?:bash|sh|zsh|python3?))\s+[\"']?$"
)

# Text immediately before a reference that stores it rather than running it:
# `DRIVER="$HERE/x.sh"`. An environment-assignment PREFIX (`FOO=1 "$HERE/x.sh"`)
# does not match, because a space separates the assignment from the command.
ASSIGNMENT_BEFORE = re.compile(r"=[\"']?$")

# Shell keywords that precede a command without changing whether it runs.
# `if "$HERE/x.sh"; then` executes the script exactly like a bare call.
CONTROL_PREFIX = re.compile(r"^\s*(?:if|elif|while|until|then|else|do|!|time)\s+")

# Commands that name a path without executing it. `[` / `[[` sit outside the \b
# group: no word boundary exists between a bracket and the space after it.
NON_EXECUTING = re.compile(
    r"^\s*(?:\[\[?(?=\s)|(?:test|cp|mv|rm|cat|chmod|chown|mkdir|touch|echo|"
    r"printf|ls|grep|sed|awk|head|tail|wc|diff|install|ln|return|shift)\b)"
)

# Shell separators. Only the segment holding the reference decides its fate.
SEGMENT_SEPARATOR = re.compile(r"&&|\|\||;|\|")


def _reference_is_safe(segment: str, match: re.Match) -> bool:
    """True when this specific reference is named without needing the exec bit."""
    before = segment[:match.start(1)]

    if INTERPRETER_BEFORE.search(before):
        return True
    if ASSIGNMENT_BEFORE.search(before):
        return True

    # Fall back to the command word opening the segment: `[ -f "$HERE/x.sh" ]`
    # and `cp "$HERE/a.sh" "$DEST"` inspect or copy, never execute.
    candidate = segment
    while True:
        peeled = CONTROL_PREFIX.sub("", candidate, count=1)
        if peeled == candidate:
            break
        candidate = peeled
    return bool(NON_EXECUTING.match(candidate))


def _unsafe_references(line: str, reference: re.Pattern) -> list[str]:
    """Every reference on this line that would need the stripped exec bit."""
    if line.lstrip().startswith("#"):
        return []
    if not reference.search(line):
        return []
    unsafe = []
    for segment in SEGMENT_SEPARATOR.split(line):
        for match in reference.finditer(segment):
            if not _reference_is_safe(segment, match):
                unsafe.append(match.group(1))
    return unsafe


def _tracked(*globs: str) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", *globs],
        check=True, capture_output=True, text=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def _lines(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return list(enumerate(text.splitlines(), start=1))


def _scan(skill_files: list[Path], reference: re.Pattern) -> list[str]:
    offenders = []
    for path in skill_files:
        for lineno, line in _lines(path):
            if _unsafe_references(line, reference):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    return offenders


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


def test_no_exec_bit_dependent_dot_slash_invocations(skill_files: list[Path]) -> None:
    """`./foo.sh` needs an exec bit the consumer's install does not have."""
    offenders = _scan(skill_files, DOT_SLASH_REFERENCE)
    assert not offenders, (
        "Scripts executed via a './' path with no interpreter. tessl install "
        "strips the executable bit, so these work in this checkout and fail "
        "for consumers. Prefix with `bash` / `python3`.\n" + "\n".join(offenders)
    )


def test_no_exec_bit_dependent_sibling_invocations(skill_files: list[Path]) -> None:
    """A `$HERE/foo.sh` execution must be sourced or given an interpreter."""
    offenders = _scan(skill_files, VAR_PATH_REFERENCE)
    assert not offenders, (
        "Sibling scripts executed directly through a variable path. tessl "
        "install strips the executable bit; use `source \"$HERE/x.sh\"` or "
        "`bash \"$HERE/x.sh\"`.\n" + "\n".join(offenders)
    )


UNSAFE_LINES = [
    './scripts/build-deck.sh --deck x',
    'run ./generate-qr.py',
    '"$HERE/ensure-drivers.sh"',
    'if "$HERE/ensure-drivers.sh"; then',
    'elif "$HERE/ensure-drivers.sh"; then',
    'while "$HERE/poll.sh"; do',
    'if ! "$HERE/ensure-drivers.sh"; then',
    'mkdir -p "$OUT" && "$HERE/ensure-drivers.sh"',
    # Environment-assignment PREFIX: the script still executes.
    'FOO=1 "$HERE/ensure-drivers.sh"',
    'DEBUG=1 ./scripts/build-deck.sh',
]

SAFE_LINES = [
    'source "$HERE/ensure-drivers.sh"',
    '. "$HERE/ensure-drivers.sh"',
    'bash "$HERE/ensure-drivers.sh"',
    'python3 "$HERE/persist-results.py"',
    # An interpreter makes a './' path fine — the outcome, not the spelling.
    'bash ./scripts/build-deck.sh',
    'python3 ./scripts/generate-qr.py',
    'Run `bash ./scripts/build-deck.sh` to build the deck.',
    'if bash "$HERE/ensure-drivers.sh"; then',
    'if [ -f "$HERE/ensure-drivers.sh" ]; then',
    'if ! source "$HERE/ensure-drivers.sh"; then',
    'DRIVER="$HERE/ensure-drivers.sh"',
    'cp "$HERE/RunDeckOps.bas" "$DEST"',
    'bash "$HERE/a.sh" && bash "$HERE/b.sh"',
    'FOO=1 bash "$HERE/ensure-drivers.sh"',
]


@pytest.mark.parametrize("line", UNSAFE_LINES)
def test_detector_flags_exec_bit_dependent_lines(line: str) -> None:
    """A detector that never fires guards nothing."""
    flagged = (_unsafe_references(line, DOT_SLASH_REFERENCE)
               + _unsafe_references(line, VAR_PATH_REFERENCE))
    assert flagged, f"should have been flagged: {line}"


@pytest.mark.parametrize("line", SAFE_LINES)
def test_detector_accepts_safe_references(line: str) -> None:
    """A detector that fires on everything is noise, not a guard."""
    flagged = (_unsafe_references(line, DOT_SLASH_REFERENCE)
               + _unsafe_references(line, VAR_PATH_REFERENCE))
    assert not flagged, f"should have been accepted: {line}"

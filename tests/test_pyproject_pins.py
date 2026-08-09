"""Every requirement in `pyproject.toml` pins an exact version (#161).

`dependency-management` requires a pin plus a stated renewal mechanism for each
dependency. A remembered intention is not a gate, so this test is the gate: a
newly added unpinned requirement fails CI on the commit that introduces it,
rather than surfacing months later as an unreproducible build.

Both halves parse rather than pattern-match. A substring search for `==` calls
`pkg===1.0`, `pkg==1.*`, and `pkg @ https://host/a==b.whl` pinned; a text search
for the Dependabot ecosystem passes on a commented-out entry. Either would let
the gate report green while the thing it guards is broken.

The `tessl.json` floating carve-out is a separate runtime-managed manifest
contract and is deliberately out of scope here.
"""

import sys
from pathlib import Path

import pytest
import yaml
from packaging.requirements import InvalidRequirement, Requirement

if sys.version_info >= (3, 11):
    import tomllib
else:  # requires-python admits 3.10, where tomllib is not in the stdlib
    import tomli as tomllib

REPO_ROOT = Path(__file__).parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"

# The manifest's directory as Dependabot addresses it.
MANIFEST_DIRECTORY = "/"


def _manifest() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _requirement_groups() -> list[tuple[str, list[str]]]:
    """Every requirement list in the manifest, labeled by where it lives."""
    manifest = _manifest()
    groups = [
        ("build-system.requires", manifest["build-system"]["requires"]),
        ("project.dependencies", manifest["project"]["dependencies"]),
    ]
    optional = manifest["project"].get("optional-dependencies", {})
    groups.extend(
        (f"project.optional-dependencies.{extra}", requirements)
        for extra, requirements in sorted(optional.items())
    )
    return groups


def pin_violation(raw: str) -> str | None:
    """Why `raw` is not an exact pin, or None when it is one.

    An exact pin is a PEP 508 requirement with no direct URL and exactly one
    specifier, whose operator is `==` and whose version carries no wildcard.
    Environment markers are permitted — they select WHETHER a requirement
    applies, never which version.
    """
    try:
        requirement = Requirement(raw)
    except InvalidRequirement as exc:
        return f"not a valid PEP 508 requirement ({exc})"
    if requirement.url:
        return "pins a direct URL, which no version resolver can reproduce"
    specifiers = list(requirement.specifier)
    if len(specifiers) != 1:
        return f"has {len(specifiers)} specifiers; an exact pin has exactly one"
    specifier = specifiers[0]
    if specifier.operator != "==":
        return f"uses operator {specifier.operator!r}, not '=='"
    if "*" in specifier.version:
        return f"pins the wildcard {specifier.version!r}, not one version"
    return None


def test_the_manifest_declares_every_group_this_test_checks():
    """A new group added to the manifest must not slip past unchecked."""
    manifest = _manifest()
    assert "build-system" in manifest
    assert manifest["project"]["optional-dependencies"], (
        "optional groups exist; the collector must be reading them"
    )
    labels = [label for label, _ in _requirement_groups()]
    assert "project.optional-dependencies.test" in labels
    assert "project.optional-dependencies.whisper" in labels


@pytest.mark.parametrize("label,requirements", _requirement_groups())
def test_every_requirement_pins_an_exact_version(label, requirements):
    violations = {
        raw: reason
        for raw in requirements
        if (reason := pin_violation(raw)) is not None
    }
    assert not violations, (
        f"{label} has requirement(s) that are not exact pins: {violations}. "
        f"Pin each with `==<version>` and confirm .github/dependabot.yml's pip "
        f"ecosystem covers it, per rules/dependency-management.md Pinning."
    )


@pytest.mark.parametrize("raw", [
    "pytest",                              # bare name
    "setuptools>=68",                      # range
    "numpy>=2.0,<3.0",                     # two-sided range
    "numpy==2.2.6,>=2.0",                  # pin plus a range that reopens it
    "numpy===2.2.6",                       # arbitrary-equality, not exact
    "numpy==2.2.*",                        # wildcard
    "numpy~=2.2.6",                        # compatible-release
    "lxml @ https://example.invalid/a==b.whl",   # URL containing '=='
])
def test_the_pin_check_rejects_specifiers_that_are_not_exact(raw):
    """The last four beat a naive `'==' in raw` check; the first four do not.

    Both halves matter: dropping the parser would reopen the first four, and
    keeping only the obvious cases would have hidden the rest.
    """
    assert pin_violation(raw) is not None, raw


@pytest.mark.parametrize("raw", [
    "numpy==2.2.6",
    "Pillow==12.3.0",
    "python-pptx==1.0.2",
    "tomli==2.4.1; python_version < '3.11'",     # a marker is not a version
    "qrcode[pil]==8.2",                          # an extra is not a version
])
def test_the_pin_check_accepts_real_pins(raw):
    assert pin_violation(raw) is None, pin_violation(raw)


def test_dependabot_actively_covers_the_pip_ecosystem():
    """A pin with no renewal mechanism rots silently.

    Parsed, not grepped: a commented-out or misplaced entry leaves the text
    present while Dependabot no longer opens a single bump PR.
    """
    config = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    pip_updates = [
        entry for entry in config["updates"]
        if entry.get("package-ecosystem") == "pip"
    ]
    assert len(pip_updates) == 1, (
        f"expected exactly one active pip update entry, got {len(pip_updates)}"
    )
    entry = pip_updates[0]
    assert entry.get("directory") == MANIFEST_DIRECTORY, (
        f"pip entry watches {entry.get('directory')!r}, not the directory "
        f"holding pyproject.toml ({MANIFEST_DIRECTORY!r})"
    )
    assert entry.get("schedule", {}).get("interval") == "weekly", (
        "the pip entry must keep its recurring weekly schedule"
    )


def test_the_package_version_stays_the_non_published_sentinel():
    """The shipped version lives in .tessl-plugin/plugin.json, not here.

    Two version fields with no mechanism keeping them in step is how a
    published artifact starts disagreeing with its own manifest.
    """
    assert _manifest()["project"]["version"] == "0.0.0"
    source = PYPROJECT.read_text(encoding="utf-8")
    assert ".tessl-plugin/plugin.json" in source, (
        "the sentinel must name where the real version lives"
    )

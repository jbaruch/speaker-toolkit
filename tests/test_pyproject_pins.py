"""Every requirement in `pyproject.toml` pins an exact version (#161).

`dependency-management` requires a pin plus a stated renewal mechanism for each
dependency. A remembered intention is not a gate, so this test is the gate: a
newly added unpinned requirement fails CI on the commit that introduces it,
rather than surfacing months later as an unreproducible build.

The `tessl.json` floating carve-out is a separate runtime-managed manifest
contract and is deliberately out of scope here.
"""

import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).parents[1] / "pyproject.toml"

# `~=`, `>=`, and a bare name all let the resolver pick a version the repo never
# tested. Only `==` names one.
EXACT_PIN = "=="


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
    unpinned = [item for item in requirements if EXACT_PIN not in item]
    assert not unpinned, (
        f"{label} has unpinned requirement(s): {unpinned}. "
        f"Pin each with `==<version>` and confirm .github/dependabot.yml's pip "
        f"ecosystem covers it, per rules/dependency-management.md Pinning."
    )


@pytest.mark.parametrize("label,requirements", _requirement_groups())
def test_no_requirement_carries_a_range_alongside_its_pin(label, requirements):
    """`foo==1.0,>=0.9` pins nothing — the range still admits other versions."""
    for item in requirements:
        specifier = item.split(EXACT_PIN, 1)[1] if EXACT_PIN in item else ""
        assert "," not in specifier, (
            f"{label} requirement {item!r} pairs its pin with another "
            f"specifier; a pin must stand alone"
        )


def test_dependabot_covers_the_pip_ecosystem():
    """A pin with no renewal mechanism rots silently."""
    config = (
        Path(__file__).parents[1] / ".github" / "dependabot.yml"
    ).read_text(encoding="utf-8")
    assert 'package-ecosystem: "pip"' in config, (
        "every pinned requirement needs an automated renewal mechanism"
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

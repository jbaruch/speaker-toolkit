"""Toolkit paths resolve when ACR realizes each skill as a sibling directory.

`acr realize --agent claude-code` installs skill `<name>` at
`<project>/.claude/skills/acr__jbaruch__speaker-toolkit__<name>/`, so no
`skills/<name>/` tree exists. These tests copy the shipped skills into that
layout and run the `rules/toolkit-root-lookup.md` ACR reading and every script
that reaches a sibling skill from the copy.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_installed_plugin_paths import _rooted_targets


REPO_ROOT = Path(__file__).resolve().parents[1]
ACR_PREFIX = "acr__jbaruch__speaker-toolkit__"
SKILL_NAMES = tuple(
    Path(skill).name
    for skill in json.loads(
        (REPO_ROOT / ".tessl-plugin" / "plugin.json").read_text(encoding="utf-8")
    )["skills"]
)
# A fixed skill name joined to the parent of a script's own skill directory
# resolves only under `skills/<name>/`.
_SKILL_ALTERNATION = "|".join(re.escape(name) for name in SKILL_NAMES)
FIXED_SIBLING_RE = re.compile(
    r"(?:parents\[[2-9]\]|\.parent\.parent\.parent|os\.pardir)"
    rf".{{0,160}}?[\"'](?:skills/)?(?:{_SKILL_ALTERNATION})[\"'/]"
    rf"|/\s*[\"']skills/(?:{_SKILL_ALTERNATION})/",
    re.DOTALL,
)
# Each script that reaches a sibling skill, that sibling, and any sibling path
# the script computes lazily, beyond the modules it imports.
CROSS_SKILL_SCRIPTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "illustrations/scripts/apply-illustrations-to-deck.py": (
        "presentation-creator",
        (),
    ),
    "illustrations/scripts/build-expansion-manifest.py": ("presentation-creator", ()),
    "illustrations/scripts/generate-illustrations.py": ("presentation-creator", ()),
    "illustrations/scripts/image_cli_process.py": ("vault-ingress", ()),
    "presentation-creator/scripts/generate-qr.py": ("vault-ingress", ()),
    "presentation-creator/scripts/outline_schema.py": ("vault-profile", ()),
    "presentation-creator/scripts/pattern-menu.py": ("vault-ingress", ()),
    "presentation-creator/scripts/pattern_history_status.py": ("vault-profile", ()),
    "screencast-editor/scripts/compose-thumbnail.py": (
        "illustrations",
        ("GENERATOR",),
    ),
    "shorts-producer/scripts/prepare-clip.py": ("vault-ingress", ()),
    "shownotes-publisher/scripts/find-talk-analysis.py": ("vault-ingress", ()),
    "shownotes-publisher/scripts/resolve-runtime.py": (
        "vault-ingress",
        ("OWNER_READER", "RUNTIME_CHECK"),
    ),
    "vault-clarification/scripts/goal_generation_provenance.py": (
        "vault-ingress",
        (),
    ),
    "vault-ingress/scripts/aggregate-catalog-feedback.py": (
        "presentation-creator",
        ("default_catalog_path",),
    ),
    "vault-ingress/scripts/audit-pattern-catalog.py": (
        "presentation-creator",
        ("default_catalog_dir",),
    ),
    "vault-ingress/scripts/return_validation.py": (
        "presentation-creator",
        ("default_catalog_dir",),
    ),
    "vault-profile/scripts/calibrate-speech.py": ("vault-ingress", ()),
    "vault-profile/scripts/classify-pattern-profile.py": ("vault-ingress", ()),
    "vault-profile/scripts/load-vault.py": ("vault-ingress", ()),
    "vault-profile/scripts/pattern_cohort_snapshot.py": ("vault-ingress", ()),
    "vault-profile/scripts/pattern_opportunities.py": ("vault-ingress", ()),
    "vault-profile/scripts/profile_pattern_provenance.py": ("vault-ingress", ()),
    "vault-profile/scripts/section15_pattern_history.py": ("vault-ingress", ()),
    "vault-profile/scripts/speech_calibration.py": ("vault-ingress", ()),
    "vault-profile/scripts/validate-profile.py": ("vault-ingress", ()),
}
PROBE = """
import json, runpy, sys
from pathlib import Path

script, *attributes = sys.argv[1:]
sys.path.insert(0, str(Path(script).parent))
namespace = runpy.run_path(script, run_name="acr_probe")
paths = {}
for name in attributes:
    value = namespace[name]
    paths[name] = str(value() if callable(value) else value)
modules = sorted(
    str(Path(module.__file__).resolve())
    for module in list(sys.modules.values())
    if getattr(module, "__file__", None)
)
print(json.dumps({"paths": paths, "modules": modules}))
"""


@pytest.fixture(scope="module")
def acr_skills(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The shipped skills, realized the way `acr realize` lays them out."""
    skills = tmp_path_factory.mktemp("acr-project") / ".claude" / "skills"
    for name in SKILL_NAMES:
        shutil.copytree(
            REPO_ROOT / "skills" / name,
            skills / f"{ACR_PREFIX}{name}",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    return skills


def _acr_path(acr_skills: Path, relative: str) -> Path:
    skill, rest = relative.split("/", 1)
    return acr_skills / f"{ACR_PREFIX}{skill}" / rest


def _environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def test_the_acr_reading_finds_every_rooted_target(acr_skills: Path) -> None:
    targets = _rooted_targets()
    assert targets
    assert all(target.startswith("skills/") for target in targets), targets

    for skill_md in sorted(acr_skills.glob("*/SKILL.md")):
        own = skill_md.parent
        assert own.name.startswith(ACR_PREFIX), own
        missing = []
        for target in targets:
            _, name, rest = target.split("/", 2)
            # `{speaker_toolkit_root}/skills/<name>/` read as the sibling directory.
            if not (own.with_name(f"{ACR_PREFIX}{name}") / rest).exists():
                missing.append(target)
        assert not missing, (skill_md, sorted(missing))


@pytest.mark.parametrize("relative", sorted(CROSS_SKILL_SCRIPTS))
def test_cross_skill_script_resolves_its_sibling_from_acr_layout(
    acr_skills: Path, relative: str
) -> None:
    script = _acr_path(acr_skills, relative)
    sibling_name, attributes = CROSS_SKILL_SCRIPTS[relative]
    result = subprocess.run(
        [sys.executable, "-c", PROBE, str(script), *attributes],
        cwd=acr_skills,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    modules = [Path(module) for module in report["modules"]]
    repo_skills = (REPO_ROOT / "skills").resolve()
    assert not [m for m in modules if m.is_relative_to(repo_skills)], modules

    sibling = acr_skills.resolve() / f"{ACR_PREFIX}{sibling_name}"
    for name, value in report["paths"].items():
        path = Path(value).resolve()
        assert path.exists(), (name, path)
        assert path.is_relative_to(sibling), (name, path)
    if not attributes:
        assert [m for m in modules if m.is_relative_to(sibling)], (
            f"{relative} loaded nothing from {sibling}; name its lazily computed "
            "sibling path in CROSS_SKILL_SCRIPTS"
        )


@pytest.mark.parametrize(
    "relative",
    sorted(
        relative
        for relative in CROSS_SKILL_SCRIPTS
        if "argparse.ArgumentParser("
        in (REPO_ROOT / "skills" / relative).read_text(encoding="utf-8")
    ),
)
def test_cross_skill_cli_runs_from_acr_layout(acr_skills: Path, relative: str) -> None:
    result = subprocess.run(
        [sys.executable, str(_acr_path(acr_skills, relative)), "--help"],
        cwd=acr_skills,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_no_script_joins_a_fixed_sibling_name(acr_skills: Path) -> None:
    offenders = [
        f"{path.relative_to(acr_skills)}: {match.group(0)!r}"
        for path in sorted(acr_skills.rglob("*.py"))
        for match in FIXED_SIBLING_RE.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    "source",
    [
        'X = Path(__file__).resolve().parents[2] / "vault-ingress" / "scripts"',
        'X = (\n    Path(__file__).resolve().parent.parent.parent\n    / "presentation-creator"\n)',
        'os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "illustrations")',
        'sys.path.insert(0, str(ROOT / "skills/vault-ingress/scripts"))',
    ],
)
def test_fixed_sibling_guard_flags_skills_tree_joins(source: str) -> None:
    assert FIXED_SIBLING_RE.search(source), source


MARKDOWN_LINK_RE = re.compile(r"\]\((?P<target>[^)\s#]+)(?:#[^)]*)?\)")


def _cross_skill_links() -> list[tuple[str, str, str]]:
    """(source file, sibling skill, path inside it) for links into another skill."""
    skills_root = (REPO_ROOT / "skills").resolve()
    found = []
    for name in SKILL_NAMES:
        for source in sorted((skills_root / name).rglob("*.md")):
            for match in MARKDOWN_LINK_RE.finditer(source.read_text(encoding="utf-8")):
                target = match.group("target")
                if "://" in target or target.startswith(("/", "mailto:")):
                    continue
                resolved = (source.parent / target).resolve()
                if not resolved.is_relative_to(skills_root):
                    continue
                sibling, *rest = resolved.relative_to(skills_root).parts
                if sibling != name and sibling in SKILL_NAMES:
                    found.append(
                        (str(source.relative_to(skills_root)), sibling, "/".join(rest))
                    )
    return found


def test_relative_links_into_other_skills_resolve_under_the_acr_reading(
    acr_skills: Path,
) -> None:
    links = _cross_skill_links()
    assert links, "expected cross-skill links to exist; the guard would be vacuous"
    missing = [
        (source, sibling, rest)
        for source, sibling, rest in links
        if not (acr_skills / f"{ACR_PREFIX}{sibling}" / rest).exists()
    ]
    assert missing == []

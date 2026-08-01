"""Guards for commands that must work from an installed plugin mount."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / "skills"
EXPECTED_SKILLS = {
    "illustrations",
    "presentation-creator",
    "shownotes-publisher",
    "vault-clarification",
    "vault-ingress",
    "vault-profile",
}
ROOT_TOKEN = "{speaker_toolkit_root}"
SHELL_LANGUAGES = {"bash", "sh", "shell", "zsh"}
FENCE_RE = re.compile(r"^\s*```(?P<language>[A-Za-z0-9_-]*)\s*$")
INLINE_CODE_RE = re.compile(r"`(?P<code>[^`\n]+)`")
UNROOTED_TOOLKIT_PATH_RE = re.compile(
    r"(?<!\{speaker_toolkit_root\}/)"
    r"(?<![A-Za-z0-9_.-])"
    r"(?P<path>(?:skills|rules)/[A-Za-z0-9_.@/{}/-]+)"
)
ROOTED_TOOLKIT_PATH_RE = re.compile(
    r"\{speaker_toolkit_root\}/"
    r"(?P<path>(?:skills|rules)/[A-Za-z0-9_.@/-]+)"
)
COMMAND_LAUNCHER_RE = re.compile(r'^\s*(?:python(?:3)?|bash|sh|"?\{python_path\}"?)\s+')
DIRECT_SCRIPT_COMMAND_RE = re.compile(
    r'^\s*"?(?:\{speaker_toolkit_root\}/)?(?:skills|rules)/\S+\.(?:py|sh)"?\s+\S'
)
COMMAND_CONTEXT_RE = re.compile(
    r"\b(?:run|running|execute|executing|invoke|invoking|via|with|use|using)\b"
    r"[^`]{0,60}$",
    re.IGNORECASE,
)
BARE_PYTHON_TOOLKIT_COMMAND_RE = re.compile(
    r"(?:^|[|;&]\s*)python(?:3)?\s+"
    r'"?\{speaker_toolkit_root\}/skills/'
)


def _shipped_skill_paths() -> tuple[Path, ...]:
    return tuple(sorted(SKILLS_ROOT.glob("*/SKILL.md")))


def _command_doc_paths() -> tuple[Path, ...]:
    references = SKILLS_ROOT.glob("*/references/**/*.md")
    return tuple(sorted({*_shipped_skill_paths(), *references}))


def _rule_paths() -> tuple[Path, ...]:
    return tuple(sorted((REPO_ROOT / "rules").glob("*.md")))


def _vault_workflow_doc_paths() -> tuple[Path, ...]:
    paths: set[Path] = set()
    for skill_name in ("vault-clarification", "vault-ingress", "vault-profile"):
        skill_root = SKILLS_ROOT / skill_name
        paths.add(skill_root / "SKILL.md")
        paths.update((skill_root / "references").rglob("*.md"))
    return tuple(sorted(paths))


def _shell_command_lines(text: str) -> Iterator[tuple[int, str]]:
    language: str | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        fence = FENCE_RE.match(line)
        if fence:
            if language is None:
                language = fence.group("language").lower()
            else:
                language = None
            continue
        if language in SHELL_LANGUAGES:
            yield line_number, line


def _inline_command_spans(text: str) -> Iterator[tuple[int, str]]:
    previous_line = ""
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("|"):
            previous_line = line
            continue
        for match in INLINE_CODE_RE.finditer(line):
            if (
                match.start() > 0
                and line[match.start() - 1] == "["
                and line[match.end() :].startswith("](")
            ):
                continue
            code = match.group("code")
            context = f"{previous_line.strip()} {line[: match.start()]}"
            if (
                COMMAND_LAUNCHER_RE.match(code)
                or DIRECT_SCRIPT_COMMAND_RE.match(code)
                or COMMAND_CONTEXT_RE.search(context)
            ):
                yield line_number, code
        previous_line = line


def test_every_shipped_skill_defines_an_installed_plugin_root() -> None:
    skill_paths = _shipped_skill_paths()
    assert {path.parent.name for path in skill_paths} == EXPECTED_SKILLS

    for path in skill_paths:
        text = path.read_text(encoding="utf-8")
        assert "absolute path of this loaded `SKILL.md`" in text, path
        assert "two directories above the directory\ncontaining this file" in text, path
        assert "Never derive it from the consumer working directory" in text, path
        assert "Treat `{speaker_toolkit_root}` as absolute" in text, path


def test_operational_toolkit_paths_are_rooted() -> None:
    failures: list[str] = []
    for path in _command_doc_paths():
        text = path.read_text(encoding="utf-8")
        command_surfaces = [
            *_shell_command_lines(text),
            *_inline_command_spans(text),
        ]
        for line_number, command in command_surfaces:
            for match in UNROOTED_TOOLKIT_PATH_RE.finditer(command):
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number}: "
                    f"unrooted {match.group('path')!r} in {command!r}"
                )

    assert not failures, "\n" + "\n".join(failures)


def test_rooted_toolkit_paths_exist_in_the_package_source() -> None:
    missing: list[str] = []
    seen = 0
    for path in _command_doc_paths():
        text = path.read_text(encoding="utf-8")
        for match in ROOTED_TOOLKIT_PATH_RE.finditer(text):
            seen += 1
            target = REPO_ROOT / match.group("path")
            if not target.exists():
                missing.append(f"{path.relative_to(REPO_ROOT)}: {match.group('path')}")

    assert seen > 0
    assert not missing, "\n" + "\n".join(missing)


def test_rule_prose_and_skill_cross_references_use_repo_relative_paths() -> None:
    failures: list[str] = []
    for path in _rule_paths():
        text = path.read_text(encoding="utf-8")
        for match in ROOTED_TOOLKIT_PATH_RE.finditer(text):
            failures.append(
                f"{path.relative_to(REPO_ROOT)}: rooted rule path "
                f"{match.group('path')!r}"
            )

    for path in _shipped_skill_paths():
        text = path.read_text(encoding="utf-8")
        for match in ROOTED_TOOLKIT_PATH_RE.finditer(text):
            if match.group("path").endswith(".md"):
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}: rooted cross-reference "
                    f"{match.group('path')!r}"
                )

    assert not failures, "\n" + "\n".join(failures)


def test_vault_workflows_use_the_configured_interpreter() -> None:
    failures: list[str] = []
    for path in _vault_workflow_doc_paths():
        text = path.read_text(encoding="utf-8")
        command_surfaces = [
            *_shell_command_lines(text),
            *_inline_command_spans(text),
        ]
        for line_number, command in command_surfaces:
            if BARE_PYTHON_TOOLKIT_COMMAND_RE.search(command):
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number}: {command!r}"
                )

    assert not failures, (
        "vault-owned commands must use the tracking database's `{python_path}`; "
        "bare Python can select a different environment:\n" + "\n".join(failures)
    )


def test_profile_interpreter_authority_survives_the_ingress_handoff() -> None:
    profile = (SKILLS_ROOT / "vault-profile" / "SKILL.md").read_text(encoding="utf-8")
    ingress = (SKILLS_ROOT / "vault-ingress" / "SKILL.md").read_text(encoding="utf-8")

    assert "read `config.python_path` from that tracking\ndatabase" in profile
    assert "interpreter\nauthority for every operational command" in profile
    assert "re-read the database and require the stored value to match" in profile
    assert "Never fall back to whichever `python3` happens to be on `PATH`" in profile
    assert (
        '"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/check-runtime.py"'
        in profile
    )
    assert "exact\ndatabase-configured `{python_path}` as handoff context" in ingress
    assert "rejects a missing or mismatched interpreter" in ingress
    assert (
        '"{python_path}" "{speaker_toolkit_root}/skills/vault-ingress/scripts/'
        'scan-shownotes.py"' in ingress
    )

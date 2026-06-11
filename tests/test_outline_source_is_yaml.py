"""Contract: outline.yaml is the single source of truth for every script.

`outline.yaml` is the one hand/agent-edited artifact per talk (see
`skills/presentation-creator/scripts/outline_schema.py`). The `.md` files
(`narrative.md`, `script.md`, `slides.md`, `rhetorical-review.md`) are
human-readable artifacts GENERATED from it — never an input. No script may
ingest a markdown file as its outline; every outline consumer reads
`outline.yaml` through the shared `outline_schema` loader.

This test discovers outline-consuming scripts structurally (argparse declares
an `outline` argument) so a newly-added consumer is covered automatically.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
RULES_DIR = REPO_ROOT / "rules"

# The phantom artifact the illustration scripts used to regex-parse. Nothing in
# the toolkit generates it — the source of truth is outline.yaml.
PHANTOM_MARKDOWN_OUTLINE = "presentation-outline.md"

# Markdown bold-field syntax the legacy markdown outline used for deck-level
# fields; outline.yaml carries these as style_anchor.composition / .embedded_footer.
# The bold-field form must never appear in loaded context (it would teach the
# agent the outline is markdown). `**Model:**` is deliberately NOT forbidden:
# extract-slides.py legitimately renders it into the generated slides.md.
FORBIDDEN_MD_OUTLINE_FIELDS = ("**Composition:**", "**Embedded footer:**")


def _script_files() -> list[Path]:
    return sorted(
        p
        for p in SKILLS_DIR.glob("*/scripts/*.py")
        if "__pycache__" not in p.parts
    )


def _outline_arg_help(tree: ast.AST) -> str | None:
    """Return the help text of an argparse `outline` argument, or None.

    Matches both positional `add_argument("outline", ...)` and optional
    `add_argument("--outline", ...)`.
    """
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant)):
            continue
        name = node.args[0].value
        if name not in ("outline", "--outline"):
            continue
        for kw in node.keywords:
            if kw.arg == "help" and isinstance(kw.value, ast.Constant):
                val = kw.value.value
                return val if isinstance(val, str) else ""
        return ""  # outline arg with no help text
    return None


def _outline_consumers() -> list[tuple[Path, str]]:
    """(script_path, outline-arg help text) for every outline-consuming script."""
    consumers = []
    for path in _script_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        help_text = _outline_arg_help(tree)
        if help_text is not None:
            consumers.append((path, help_text))
    return consumers


def _imports_shared_loader(path: Path) -> bool:
    """True if the script imports the shared outline_schema loader."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "outline_schema" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "outline_schema":
                return True
    return False


CONSUMERS = _outline_consumers()
CONSUMER_IDS = [str(p.relative_to(SKILLS_DIR)) for p, _ in CONSUMERS]
CONSUMER_PATHS = [p for p, _ in CONSUMERS]


def test_outline_consumers_discovered():
    """The three known illustration consumers must be discovered.

    Guards the discovery itself: if the AST walk silently found nothing, the
    parametrized tests below would vacuously pass.
    """
    found = {p.name for p, _ in CONSUMERS}
    expected = {
        "generate-illustrations.py",
        "apply-illustrations-to-deck.py",
        "build-expansion-manifest.py",
    }
    missing = expected - found
    assert not missing, (
        f"outline-consuming scripts not discovered: {sorted(missing)}. "
        f"Discovered: {sorted(found)}"
    )


@pytest.mark.parametrize(("path", "help_text"), CONSUMERS, ids=CONSUMER_IDS)
def test_outline_arg_declares_yaml_not_markdown(path, help_text):
    """Every outline argument's help text points at outline.yaml, not markdown."""
    assert "outline.yaml" in help_text, (
        f"{path.name}: outline argument help must name 'outline.yaml' "
        f"(the single source of truth); got: {help_text!r}"
    )
    assert ".md" not in help_text, (
        f"{path.name}: outline argument help references a markdown file "
        f"({help_text!r}); .md files are generated artifacts, not inputs"
    )


@pytest.mark.parametrize("path", CONSUMER_PATHS, ids=CONSUMER_IDS)
def test_outline_consumers_use_shared_schema_loader(path):
    """Outline consumers parse via outline_schema, not bespoke markdown regex."""
    assert _imports_shared_loader(path), (
        f"{path.name}: must import the shared `outline_schema` loader so every "
        f"script parses the one source-of-truth schema identically"
    )


def _context_artifact_files() -> list[Path]:
    """Repo-owned scripts, skill prose, and rules — the context agents load.

    CHANGELOG.md is excluded by construction (it lives at the repo root, not
    under skills/ or rules/): it is the archive and legitimately names the old
    `presentation-outline.md` in historical entries.
    """
    files = list(_script_files())
    files += [p for p in SKILLS_DIR.glob("**/*.md")]
    files += [p for p in RULES_DIR.glob("*.md")]
    return sorted(set(files))


def test_no_context_artifact_references_phantom_markdown_outline():
    """No script, skill doc, or rule references the phantom presentation-outline.md.

    Scripts, skill prose, and rules are all loaded as agent context, so a stale
    reference there misleads the agent into hand-authoring a file nothing
    generates. The source of truth is outline.yaml.
    """
    offenders = []
    for path in _context_artifact_files():
        src = path.read_text(encoding="utf-8")
        if PHANTOM_MARKDOWN_OUTLINE in src:
            line_nos = [
                i + 1
                for i, line in enumerate(src.splitlines())
                if PHANTOM_MARKDOWN_OUTLINE in line
            ]
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_nos}")
    assert not offenders, (
        f"context artifacts reference the phantom '{PHANTOM_MARKDOWN_OUTLINE}' "
        f"(nothing generates it — use outline.yaml): {offenders}"
    )


def test_no_context_artifact_uses_markdown_outline_field_syntax():
    """No loaded context uses the legacy markdown bold-field outline syntax.

    Catches stale guidance that survives a filename swap — e.g. telling the agent
    the deck declares `**Composition:** poster-theatrical` rather than setting
    `style_anchor.composition` in outline.yaml.
    """
    offenders = []
    for path in _context_artifact_files():
        src = path.read_text(encoding="utf-8")
        hits = [tok for tok in FORBIDDEN_MD_OUTLINE_FIELDS if tok in src]
        if hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {hits}")
    assert not offenders, (
        "context artifacts use legacy markdown outline field syntax — set the "
        f"corresponding style_anchor.* field in outline.yaml instead: {offenders}"
    )

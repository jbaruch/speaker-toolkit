"""The dimension registry and the canonical remap it authorizes (#156).

Fixtures come from the live catalog rather than hardcoded numbers, so an entry
edit that reintroduces drift fails these tests instead of quietly passing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "skills" / "vault-ingress" / "scripts"
CATALOG = REPO_ROOT / "skills" / "presentation-creator" / "references" / "patterns"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

if "catalog_dimension_registry" in sys.modules:
    registry_module = sys.modules["catalog_dimension_registry"]
else:
    _SPEC = importlib.util.spec_from_file_location(
        "catalog_dimension_registry", SCRIPTS / "catalog_dimension_registry.py"
    )
    assert _SPEC is not None and _SPEC.loader is not None
    registry_module = importlib.util.module_from_spec(_SPEC)
    sys.modules["catalog_dimension_registry"] = registry_module
    _SPEC.loader.exec_module(registry_module)


@pytest.fixture(scope="module")
def registry():
    return registry_module.load_dimension_registry(CATALOG)


def _entries():
    for path in sorted(CATALOG.rglob("*.md")):
        if path.name.startswith("_index"):
            continue
        yield path


class TestRegistryShape:
    def test_covers_every_canonical_ordinal_once(self, registry) -> None:
        assert [d.ordinal for d in registry.dimensions] == list(range(1, 15))

    def test_names_match_the_canonical_authority(self, registry) -> None:
        """`rhetoric-dimensions.md` sections 1-14 are the source of truth."""
        authority = (
            REPO_ROOT
            / "skills"
            / "vault-ingress"
            / "references"
            / "rhetoric-dimensions.md"
        ).read_text()
        for dimension in registry.dimensions:
            assert f"## {dimension.ordinal}. {dimension.name}" in authority

    def test_the_canonical_name_resolves_without_an_alias(self, registry) -> None:
        for dimension in registry.dimensions:
            assert registry.ordinal_for_label(dimension.name) == dimension.ordinal

    def test_every_alias_resolves_to_its_own_dimension(self, registry) -> None:
        for dimension in registry.dimensions:
            for alias in dimension.aliases:
                assert registry.ordinal_for_label(alias) == dimension.ordinal


class TestResolution:
    def test_an_unapproved_label_does_not_resolve(self, registry) -> None:
        """The migration stays reviewed: an unknown label is reported, never
        guessed, and never falls back to the number written beside it."""
        assert registry.ordinal_for_label("Vibes And General Excellence") is None

    def test_resolution_ignores_case_and_punctuation(self, registry) -> None:
        assert registry.ordinal_for_label("slide design") == 13
        assert registry.ordinal_for_label("SLIDE  DESIGN") == 13
        assert registry.ordinal_for_label("time/pacing") == 12

    def test_an_ampersand_name_does_not_resolve_from_its_spelled_form(
        self, registry
    ) -> None:
        """`normalize_catalog_alias` drops `&` rather than expanding it, so
        `Humor & Wit` and `Humor and Wit` are different labels. The catalog
        writes the former; an entry using the latter needs an explicit alias."""
        assert registry.ordinal_for_label("Humor & Wit") == 3
        assert registry.ordinal_for_label("Humor and Wit") is None


class TestCatalogAgreement:
    def test_every_resolvable_claim_agrees_with_its_number(self, registry) -> None:
        """The remap's whole point: where a label resolves, the number matches."""
        disagreements = []
        for path in _entries():
            for claim in registry_module.dimension_claims(path.read_text(), registry):
                if not claim.unresolved and not claim.agrees:
                    disagreements.append(
                        f"{path.name}: D{claim.stated_ordinal} ({claim.label}) "
                        f"resolves to D{claim.resolved_ordinal}"
                    )
        assert disagreements == []

    def test_frontmatter_matches_what_the_prose_supports(self, registry) -> None:
        import re

        mismatches = []
        for path in _entries():
            text = path.read_text()
            match = re.search(r"^vault_dimensions: \[([^\]]*)\]$", text, re.M)
            claims = registry_module.dimension_claims(text, registry)
            if match is None or not claims:
                continue
            stored = [int(value) for value in re.findall(r"\d+", match.group(1))]
            wanted = registry_module.resolved_vault_dimensions(claims)
            if stored != wanted:
                mismatches.append(f"{path.name}: {stored} != {wanted}")
        assert mismatches == []

    def test_the_two_worked_examples_from_the_issue(self, registry) -> None:
        """#156 states the expected outcome for these two entries exactly."""
        import re

        for name, expected in (
            ("progressive-reveal.md", [3, 13]),
            ("three-part-close.md", [2, 6]),
        ):
            path = next(p for p in _entries() if p.name == name)
            match = re.search(
                r"^vault_dimensions: \[([^\]]*)\]$", path.read_text(), re.M
            )
            assert match is not None
            assert [int(v) for v in re.findall(r"\d+", match.group(1))] == expected


class TestUnresolvedLabelsArePreserved:
    def test_an_unresolved_claim_keeps_its_number(self, registry) -> None:
        """Dropping a membership on the strength of a missing alias would be a
        bigger change than the drift being fixed."""
        claim = registry_module.DimensionClaim(
            stated_ordinal=9, label="Not An Approved Label", resolved_ordinal=None
        )
        assert registry_module.resolved_vault_dimensions([claim]) == [9]

    def test_a_resolved_claim_uses_the_resolved_number(self, registry) -> None:
        claim = registry_module.DimensionClaim(
            stated_ordinal=7, label="Slide Design", resolved_ordinal=13
        )
        assert registry_module.resolved_vault_dimensions([claim]) == [13]


class TestRegistryValidation:
    def _write(self, tmp_path: Path, body: str) -> Path:
        (tmp_path / "_dimensions.yaml").write_text(body, encoding="utf-8")
        return tmp_path

    def test_a_missing_registry_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(registry_module.CatalogDimensionRegistryError):
            registry_module.load_dimension_registry(tmp_path)

    def test_an_unsupported_schema_version_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(registry_module.CatalogDimensionRegistryError):
            registry_module.load_dimension_registry(
                self._write(tmp_path, "schema_version: 99\ndimensions: []\n")
            )

    def test_a_short_registry_is_an_error(self, tmp_path: Path) -> None:
        body = (
            "schema_version: 1\ndimensions:\n"
            "  - id: only\n    ordinal: 1\n    name: Only\n    aliases: []\n"
        )
        with pytest.raises(registry_module.CatalogDimensionRegistryError):
            registry_module.load_dimension_registry(self._write(tmp_path, body))

    def test_one_label_naming_two_dimensions_is_an_error(self, tmp_path: Path) -> None:
        """An ambiguous alias makes every claim using it unresolvable, which is
        worse than having no alias at all."""
        lines = ["schema_version: 1", "dimensions:"]
        for ordinal in range(1, 15):
            lines += [
                f"  - id: d{ordinal}",
                f"    ordinal: {ordinal}",
                f"    name: Dimension {ordinal}",
                "    aliases:",
                "      - Shared Label",
            ]
        with pytest.raises(
            registry_module.CatalogDimensionRegistryError, match="resolves to both"
        ):
            registry_module.load_dimension_registry(
                self._write(tmp_path, "\n".join(lines) + "\n")
            )

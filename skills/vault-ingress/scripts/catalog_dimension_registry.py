"""One authority for the 14 vault dimensions and the labels that name them.

`vault_dimensions` is a list of bare integers, so a range check is the only
validation a number can carry on its own — and a range check cannot tell that
`4` means Audience Interaction while the prose beside it says humor. That gap is
how entries came to file evidence under dimensions they are not about.

This registry closes it by making the prose label resolvable. Every label the
catalog actually uses is an owner-approved alias of exactly one dimension, so a
`Dimension N (Label)` claim can be checked: does N match where the label
resolves? A label with no alias does not resolve, and the auditor reports it for
owner review rather than guessing — the migration stays reviewed rather than
becoming an automatic renumbering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from catalog_normalization import normalize_catalog_alias


DIMENSION_REGISTRY_SCHEMA_VERSION = 1
DIMENSION_COUNT = 14
REGISTRY_FILENAME = "_dimensions.yaml"

# `tessl install` materializes only .md/.py/.sh/.txt/.json and silently drops
# everything else, so the registry never reached an installed plugin and the
# auditor exited 1 on every consumer machine. A byte-identical `.txt` mirror
# rides along and is read when the real file is absent. Same device as the
# deck-ops drivers (skills/presentation-creator/scripts/sync-deck-drivers.py);
# scripts/check_shipped_extensions.py keeps every such mirror in sync.
MIRROR_SUFFIX = ".txt"

# `Dimension 4 (Audience Engagement)` and `Vault Dimension 13 (Slide Design)`
# are the two shapes the catalog uses.
DIMENSION_CLAIM_RE = re.compile(r"(?:Vault )?Dimension (\d+) \(([^)]+)\)")


class CatalogDimensionRegistryError(ValueError):
    """The dimension registry is missing, malformed, or self-contradictory."""


@dataclass(frozen=True)
class Dimension:
    """One canonical dimension and every label approved to name it."""

    id: str
    ordinal: int
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class DimensionRegistry:
    """The loaded registry, indexed for resolution."""

    dimensions: tuple[Dimension, ...]
    _by_normalized_label: Mapping[str, int]

    def ordinal_for_label(self, label: str) -> int | None:
        """Resolve a prose label to its canonical ordinal, or None.

        None means the label is not owner-approved for any dimension. It is
        never a reason to fall back to the number already written beside it —
        that number is exactly what is under review.
        """
        return self._by_normalized_label.get(normalize_catalog_alias(label))

    def by_ordinal(self, ordinal: int) -> Dimension | None:
        for dimension in self.dimensions:
            if dimension.ordinal == ordinal:
                return dimension
        return None


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CatalogDimensionRegistryError(f"{label} must be a mapping")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogDimensionRegistryError(f"{label} must be a non-empty string")
    return value


def registry_path(catalog_dir: Path | str) -> Path:
    """The registry to read: the real `.yaml`, else its install-surviving mirror.

    The real file wins whenever it exists, so a dev-tree edit is never shadowed
    by a stale mirror. When neither exists the real path is returned, keeping
    the error message pointed at the file an author is expected to create.
    """
    real = Path(catalog_dir) / REGISTRY_FILENAME
    if real.exists():
        return real
    mirror = real.with_name(real.name + MIRROR_SUFFIX)
    return mirror if mirror.exists() else real


def load_dimension_registry(catalog_dir: Path | str) -> DimensionRegistry:
    """Load and validate the registry beside the catalog entries."""
    path = registry_path(catalog_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatalogDimensionRegistryError(
            f"cannot read dimension registry {path}: {exc}"
        ) from exc
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        # The auditor promises a `dimension_registry_invalid` finding for a
        # registry it cannot use. A YAMLError escaping this call would crash it
        # instead, turning the one reportable failure into no report at all.
        raise CatalogDimensionRegistryError(
            f"cannot parse dimension registry {path}: {exc}"
        ) from exc
    document = _require_mapping(parsed, str(path))
    version = document.get("schema_version")
    if version != DIMENSION_REGISTRY_SCHEMA_VERSION:
        raise CatalogDimensionRegistryError(
            f"{path} schema_version must be {DIMENSION_REGISTRY_SCHEMA_VERSION}, "
            f"got {version!r}"
        )
    entries = document.get("dimensions")
    if not isinstance(entries, list) or len(entries) != DIMENSION_COUNT:
        raise CatalogDimensionRegistryError(
            f"{path} must declare exactly {DIMENSION_COUNT} dimensions"
        )

    dimensions: list[Dimension] = []
    by_label: dict[str, int] = {}
    seen_ordinals: set[int] = set()
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        mapping = _require_mapping(entry, f"{path} dimensions[{index}]")
        unknown = set(mapping) - {"id", "ordinal", "name", "aliases"}
        if unknown:
            raise CatalogDimensionRegistryError(
                f"{path} dimensions[{index}] has unknown keys {sorted(unknown)}"
            )
        identifier = _require_text(mapping.get("id"), f"{path} dimensions[{index}].id")
        name = _require_text(mapping.get("name"), f"{path} dimensions[{index}].name")
        ordinal = mapping.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise CatalogDimensionRegistryError(
                f"{path} dimensions[{index}].ordinal must be an integer"
            )
        if not 1 <= ordinal <= DIMENSION_COUNT:
            raise CatalogDimensionRegistryError(
                f"{path} dimensions[{index}].ordinal {ordinal} is out of range"
            )
        if ordinal in seen_ordinals:
            raise CatalogDimensionRegistryError(f"{path} repeats ordinal {ordinal}")
        if identifier in seen_ids:
            raise CatalogDimensionRegistryError(f"{path} repeats id {identifier!r}")
        seen_ordinals.add(ordinal)
        seen_ids.add(identifier)

        raw_aliases = mapping.get("aliases", [])
        if not isinstance(raw_aliases, list):
            raise CatalogDimensionRegistryError(
                f"{path} dimensions[{index}].aliases must be an array"
            )
        aliases = tuple(
            _require_text(alias, f"{path} dimensions[{index}].aliases[{position}]")
            for position, alias in enumerate(raw_aliases)
        )
        # The canonical name resolves too, so an entry already using it needs no
        # alias entry to duplicate it.
        for label in (name, *aliases):
            normalized = normalize_catalog_alias(label)
            if not normalized:
                raise CatalogDimensionRegistryError(
                    f"{path} dimensions[{index}] label {label!r} normalizes empty"
                )
            previous = by_label.get(normalized)
            if previous is not None and previous != ordinal:
                # One label naming two dimensions makes every claim using it
                # unresolvable, which is worse than having no alias at all.
                raise CatalogDimensionRegistryError(
                    f"{path} label {label!r} resolves to both dimension "
                    f"{previous} and {ordinal}"
                )
            by_label[normalized] = ordinal
        dimensions.append(
            Dimension(id=identifier, ordinal=ordinal, name=name, aliases=aliases)
        )

    if seen_ordinals != set(range(1, DIMENSION_COUNT + 1)):
        raise CatalogDimensionRegistryError(
            f"{path} must cover ordinals 1-{DIMENSION_COUNT} exactly once"
        )
    return DimensionRegistry(
        dimensions=tuple(sorted(dimensions, key=lambda item: item.ordinal)),
        _by_normalized_label=by_label,
    )


@dataclass(frozen=True)
class DimensionClaim:
    """One `Dimension N (Label)` claim found in entry prose."""

    stated_ordinal: int
    label: str
    resolved_ordinal: int | None

    @property
    def agrees(self) -> bool:
        return self.resolved_ordinal == self.stated_ordinal

    @property
    def unresolved(self) -> bool:
        return self.resolved_ordinal is None


def dimension_claims(text: str, registry: DimensionRegistry) -> list[DimensionClaim]:
    """Read every dimension claim in one entry's prose."""
    return [
        DimensionClaim(
            stated_ordinal=int(match.group(1)),
            label=match.group(2).strip(),
            resolved_ordinal=registry.ordinal_for_label(match.group(2).strip()),
        )
        for match in DIMENSION_CLAIM_RE.finditer(text)
    ]


def resolved_vault_dimensions(claims: Iterable[DimensionClaim]) -> list[int]:
    """The `vault_dimensions` the prose supports, sorted.

    A resolved claim contributes where its label resolves. An UNRESOLVED claim
    contributes the number already written beside it — preserved, not endorsed.
    Dropping it would silently delete a membership on the strength of a missing
    alias, which is a bigger change than the drift being fixed; the auditor
    reports the unresolved label separately so an owner decides it explicitly.
    """
    ordinals: set[int] = set()
    for claim in claims:
        resolved = claim.resolved_ordinal
        ordinals.add(claim.stated_ordinal if resolved is None else resolved)
    return sorted(ordinals)

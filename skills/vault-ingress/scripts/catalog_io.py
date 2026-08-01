"""Shared YAML and fingerprint primitives for Presentation Pattern catalogs."""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


EvidenceSourceGroups = tuple[frozenset[str], ...]
SOURCE_COMPARISON = "source_comparison"


class DuplicateYAMLKeyError(ConstructorError):
    """A YAML mapping repeats a key that would otherwise be overwritten."""


class _DuplicateKeySafeLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate keys at every nesting level."""

    def construct_mapping(
        self,
        node: MappingNode,
        deep: bool = False,
    ) -> dict[Any, Any]:
        self.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as exc:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found an unhashable mapping key {key!r}",
                    key_node.start_mark,
                ) from exc
            if duplicate:
                raise DuplicateYAMLKeyError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate mapping key {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def load_catalog_yaml(document: str) -> Any:
    """Safely load one YAML document without accepting duplicate mapping keys."""
    loader = _DuplicateKeySafeLoader(document)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def catalog_entry_paths(root: Path) -> list[Path]:
    """Return every recursive Markdown entry except the catalog-root index."""
    root_index = root / "_index.md"
    return sorted(
        (
            path
            for path in root.rglob("*.md")
            if path.is_file() and path != root_index
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def parse_evidence_source_groups(
    value: object,
    allowed_sources: Collection[str],
    *,
    field_name: str = "evaluable_from",
) -> EvidenceSourceGroups:
    """Parse OR alternatives whose nested lists express conjunctive sources."""
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")

    allowed = frozenset(allowed_sources)
    groups: list[frozenset[str]] = []
    for index, option in enumerate(value):
        if isinstance(option, str):
            raw_group = [option]
        elif isinstance(option, list) and len(option) >= 2:
            raw_group = option
        else:
            raise ValueError(
                f"{field_name}[{index}] must be a source string or an "
                "all-of list containing at least two sources")
        if any(not isinstance(source, str) for source in raw_group):
            raise ValueError(
                f"{field_name}[{index}] sources must all be strings")
        if len(raw_group) != len(set(raw_group)):
            raise ValueError(
                f"{field_name}[{index}] contains duplicate sources")
        unknown = sorted(set(raw_group) - allowed)
        if unknown:
            raise ValueError(
                f"{field_name}[{index}] contains unknown sources: {unknown}")
        group = frozenset(raw_group)
        if group == frozenset({SOURCE_COMPARISON}):
            raise ValueError(
                f"{field_name}[{index}] cannot use source_comparison as a "
                "singleton; name the exact underlying source pair")
        if len(group) > 1 and SOURCE_COMPARISON in group:
            raise ValueError(
                "source_comparison labels a completed comparison and cannot be "
                "an underlying source in an all-of alternative")
        if group in groups:
            raise ValueError(
                f"{field_name} contains duplicate alternative {sorted(group)}")
        groups.append(group)
    return tuple(groups)


def qualifying_evidence_groups(
    groups: EvidenceSourceGroups,
    available_sources: Collection[str],
) -> tuple[frozenset[str], ...]:
    """Return alternatives satisfied by inspected sources and comparison proof."""
    available = frozenset(available_sources)
    return tuple(
        group
        for group in groups
        if group <= available and (
            len(group) == 1 or SOURCE_COMPARISON in available)
    )


def evidence_source_satisfies_gate(
    groups: EvidenceSourceGroups,
    evidence_source: str,
    available_sources: Collection[str],
) -> bool:
    """Return whether one detection label cites a satisfied gate alternative."""
    qualifying = qualifying_evidence_groups(groups, available_sources)
    if evidence_source == SOURCE_COMPARISON:
        return any(
            len(group) > 1 or group == frozenset({SOURCE_COMPARISON})
            for group in qualifying
        )
    return frozenset({evidence_source}) in qualifying


def catalog_fingerprint(
    index_content: bytes,
    entry_contents: Iterable[tuple[str, bytes]],
) -> str:
    """Hash the root index and recursively discovered entries deterministically."""
    digest = hashlib.sha256()

    def update(relative_path: str, content: bytes) -> None:
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")

    update("_index.md", index_content)
    for relative_path, content in sorted(entry_contents):
        if relative_path == "_index.md":
            raise ValueError("root _index.md must be supplied as index_content")
        update(relative_path, content)
    return digest.hexdigest()

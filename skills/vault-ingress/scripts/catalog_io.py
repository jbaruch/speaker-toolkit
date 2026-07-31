"""Shared YAML and fingerprint primitives for Presentation Pattern catalogs."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


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

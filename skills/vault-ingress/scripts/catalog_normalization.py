"""Shared, deterministic normalization for Presentation Pattern claims."""

from __future__ import annotations

import re
import unicodedata


def normalize_catalog_alias(value: str) -> str:
    """Map a catalog ID, name, or alias into the collision namespace."""
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    folded = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return "-".join(re.findall(r"[a-z0-9]+", folded))

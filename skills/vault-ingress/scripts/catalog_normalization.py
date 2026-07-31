"""Shared, deterministic normalization for Presentation Pattern claims."""

from __future__ import annotations

import re
import unicodedata


def normalize_catalog_alias(value: str) -> str:
    """Map a catalog ID, name, or alias into the collision namespace."""
    folded = unicodedata.normalize("NFKC", value).casefold()
    return "-".join(re.findall(r"[a-z0-9]+", folded))

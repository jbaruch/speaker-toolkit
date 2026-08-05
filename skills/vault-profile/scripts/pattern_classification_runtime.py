"""Import bridge for the public hyphenated classification CLI.

The arithmetic owner intentionally keeps the issue-specified executable name
``classify-pattern-profile.py``. Python cannot import that filename normally,
so sibling owner/validator scripts use this zero-arithmetic bridge.
"""

from __future__ import annotations

import pathlib
import runpy
from collections.abc import Callable
from functools import lru_cache
from typing import Any, cast


_CLASSIFIER = pathlib.Path(__file__).resolve().with_name("classify-pattern-profile.py")


@lru_cache(maxsize=1)
def _exports() -> dict[str, Any]:
    try:
        return runpy.run_path(str(_CLASSIFIER), run_name="_vault_profile_classifier")
    except (OSError, SyntaxError, ImportError) as exc:
        raise RuntimeError("classification runtime owner could not be loaded") from exc


def _callable(name: str) -> Callable[..., Any]:
    value = _exports().get(name)
    if not callable(value):
        raise RuntimeError(f"classification runtime export {name!r} is unavailable")
    return cast(Callable[..., Any], value)


def resolve_classification_policy(
    vault_root: pathlib.Path,
    *,
    bundled_policy_path: pathlib.Path | None = None,
) -> dict[str, object]:
    kwargs = (
        {}
        if bundled_policy_path is None
        else {"bundled_policy_path": bundled_policy_path}
    )
    return cast(
        dict[str, object],
        _callable("resolve_classification_policy")(vault_root, **kwargs),
    )


def classify_pattern_profile(
    talks: object,
    policy_stamp: object,
    *,
    catalog: Any | None = None,
) -> dict[str, object]:
    return cast(
        dict[str, object],
        _callable("classify_pattern_profile")(talks, policy_stamp, catalog=catalog),
    )


def validate_policy_stamp(value: object) -> dict[str, object]:
    return cast(dict[str, object], _callable("validate_policy_stamp")(value))


def validate_policy(value: object) -> dict[str, object]:
    return cast(dict[str, object], _callable("validate_policy")(value))

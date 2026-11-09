"""Assess decks against a vault's talks, for the owner scripts that do it.

Shared by `sweep-pptx-talk-identity.py`, which assesses rows already in the catalog,
and `catalog-pptx-deck.py`, which assesses decks about to join it. Both have to read
the database, the source root and the candidate set the same way, or a deck could be
proven by one and contradicted by the other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pptx_talk_identity import SIGNAL_UNKNOWN

DATABASE_BASENAME = "tracking-database.json"


def resolve_input(value: str | Path) -> tuple[Path, Path]:
    """Bind a vault root to its canonical database, as preflight does."""
    path = Path(value).expanduser().absolute()
    if path.name.lower() == DATABASE_BASENAME:
        return path.parent, path
    return path, path / DATABASE_BASENAME


def resolve_pptx_source_dir(
    database: Mapping[str, Any],
    *,
    vault_root: Path,
) -> object:
    """Resolve where catalog decks live, falling back to the vault root.

    `config.pptx_source_dir` is optional, and `schemas-db.md` documents that a
    null or absent value falls back to the vault root. Passing the absent value
    straight through would report every deck in such a vault unreadable —
    a configuration default read as universal damage, and one that would put
    every binding into `binding_unproven` on evidence nobody looked for.
    """
    config = database.get("config")
    configured = config.get("pptx_source_dir") if isinstance(config, Mapping) else None
    if isinstance(configured, str) and configured.strip():
        return configured
    return vault_root


def candidate_talks(database: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every talk carrying a filename, in stored order.

    The whole vault is the candidate set on purpose. Narrowing it first — to
    the same year, or the same conference — would decide the question the
    assessment exists to answer, and would hide exactly the cross-talk
    assignment this sweep looks for.
    """
    talks = database.get("talks")
    if not isinstance(talks, list):
        return []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for talk in talks:
        if not isinstance(talk, Mapping):
            continue
        filename = talk.get("filename")
        if not isinstance(filename, str) or not filename or filename in seen:
            continue
        seen.add(filename)
        candidates.append(dict(talk))
    return candidates


def configured_speaker_name(database: Mapping[str, Any]) -> object:
    """The name as it appears on slides, or None when the vault records none."""
    config = database.get("config")
    return config.get("speaker_name") if isinstance(config, Mapping) else None


def material_assessment(assessment: Any) -> dict[str, Any]:
    """Serialize the assessment with only its material candidates.

    The candidate set is every talk in the vault — 215 of them against 82 rows
    — and a talk sharing no signal with the deck reads as six `unknown`
    verdicts. Emitting those is not evidence, it is 215 rows of noise per deck
    hiding the handful that decided the verdict.

    A candidate is material when any signal reads something. That keeps
    everything a reader needs to re-derive the verdict: the selected candidate
    is material because it agrees, and so is every rival that could have
    contested it, since contesting requires agreement.
    """
    serialized = assessment.as_json()
    candidates = serialized.get("candidates")
    if not isinstance(candidates, list):
        return serialized
    material = [
        candidate
        for candidate in candidates
        if isinstance(candidate, Mapping)
        and any(
            verdict != SIGNAL_UNKNOWN
            for verdict in (candidate.get("signals") or {}).values()
        )
    ]
    serialized["candidates"] = material
    serialized["candidates_assessed"] = len(candidates)
    return serialized


def stored_proof(assessment: Mapping[str, Any]) -> dict[str, Any]:
    """The assessment as `record_pptx` stores it.

    `candidates_assessed` is the report's own reading aid. The owner gate validates a
    closed key set, so carrying it would fail the write.
    """
    return {
        key: value for key, value in assessment.items() if key != "candidates_assessed"
    }

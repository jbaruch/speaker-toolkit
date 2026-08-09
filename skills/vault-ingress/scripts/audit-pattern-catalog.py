#!/usr/bin/env python3
"""Audit the Presentation Patterns catalog as a deterministic graph contract.

The command is deliberately read-only. It parses the catalog index and entry
frontmatter, validates mechanically decidable structure, and emits stable JSON
to stdout. It never edits entries or invents semantic relationships.

Structural errors make the process exit 1. Differences that require a human to
choose which prose or metadata is authoritative are emitted separately as
``semantic_debts`` and do not make the process fail. Argument errors use exit 2.
An unexpected failure uses exit 3 and writes one ``catalog_audit_unexpected_failure``
JSON document to stderr, leaving stdout empty — argparse already owns 2, so the
caller can still tell a malformed invocation from a broken auditor.

The machine-owned contract is expressed by the named constants below:

* ``ENTRY_TYPES`` and ``PARTS`` define catalog polarity and lifecycle kinds.
* ``CREATOR_PHASES`` defines the frontmatter phase namespace.
* ``EVIDENCE_SOURCES``, ``BASE_EVIDENCE_GATE_FIELDS``,
  ``OUTCOME_EVIDENCE_GATE_FIELDS``, and ``APPLICABILITY_GATE_FIELDS`` define
  source and applicability gates.
* ``SCORING_*_RE`` define the direct scoring-label contract.
* ``normalize_alias`` defines the collision namespace for IDs, names, and
  optional explicit aliases.

Usage::

    python3 skills/vault-ingress/scripts/audit-pattern-catalog.py
    python3 skills/vault-ingress/scripts/audit-pattern-catalog.py \
        --catalog path/to/patterns
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from failure_diagnostics import emit_unexpected_failure

from yaml import YAMLError

from catalog_io import (
    DuplicateYAMLKeyError,
    catalog_entry_paths,
    catalog_fingerprint,
    load_catalog_yaml,
    parse_evidence_source_groups,
)
from catalog_normalization import normalize_catalog_alias


SCHEMA_VERSION = 1
ENTRY_TYPES = frozenset({"pattern", "antipattern"})
PARTS = frozenset({"prepare", "build", "deliver"})
CREATOR_PHASES = frozenset(
    {
        "intake",
        "intent",
        "architecture",
        "content",
        "guardrails",
        "slides",
        "publishing",
    }
)
EVIDENCE_SOURCES = frozenset(
    {
        "static_slides",
        "native_deck",
        "delivery_video",
        "transcript",
        "source_comparison",
    }
)
# Current-generation absence claims require a single, rendered/static artifact
# or a complete transcript. Other source roles remain valid positive-evidence
# grammar for external and historical catalogs, but cannot authorize absence in
# the bundled catalog until a modality-specific completeness receipt exists.
CURRENT_ABSENCE_CAPABILITY_SOURCES = frozenset(
    {
        "static_slides",
        "transcript",
    }
)
BASE_EVIDENCE_GATE_FIELDS = frozenset(
    {
        "evaluable_from",
        "evidence_requirements",
        "not_evaluable_when",
    }
)
OUTCOME_EVIDENCE_GATE_FIELDS = frozenset(
    {
        "strong_evaluable_from",
        "absence_evaluable_from",
    }
)
APPLICABILITY_GATE_FIELDS = frozenset(
    {
        "not_applicable_when",
        "applicability_evaluable_from",
    }
)
EVIDENCE_GATE_FIELDS = (
    BASE_EVIDENCE_GATE_FIELDS | OUTCOME_EVIDENCE_GATE_FIELDS | APPLICABILITY_GATE_FIELDS
)

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
INDEX_PHASE_RE = re.compile(r"^### (Prepare|Build|Deliver) Phase\b")
SCORING_STRONG_RE = re.compile(
    r"^- Strong signal(?: \((?P<qualifier>[^)]*)\))?:[ \t]*(?P<body>.*)$",
    re.MULTILINE,
)
SCORING_MODERATE_RE = re.compile(
    r"^- Moderate signal:[ \t]*(?P<body>.*)$",
    re.MULTILINE,
)
SCORING_ABSENT_RE = re.compile(
    r"^- Absent(?: \((?P<qualifier>[^)]*)\))?:[ \t]*(?P<body>.*)$",
    re.MULTILINE,
)
SCORING_ARITHMETIC_LABEL_RE = re.compile(
    r"^- (?:Strong signal|Moderate signal|Absent) "
    r"\([^)]*\b(?:pt|pts|point|points)\b[^)]*\):",
    re.IGNORECASE | re.MULTILINE,
)
SCORING_MEDIUM_LABEL_RE = re.compile(
    r"^- Medium signal(?: \([^)]*\))?:",
    re.IGNORECASE | re.MULTILINE,
)
FENCE_RE = re.compile(r"^[ ]{0,3}(?P<marker>`{3,}|~{3,})(?P<rest>.*)$")


@dataclass(frozen=True)
class Issue:
    """One stable, sortable audit finding."""

    code: str
    message: str
    path: str = ""
    entry_id: str = ""
    field: str = ""
    related_id: str = ""

    def as_dict(self) -> dict[str, str]:
        """Return the fixed-shape JSON representation."""
        return {
            "code": self.code,
            "entry_id": self.entry_id,
            "field": self.field,
            "message": self.message,
            "path": self.path,
            "related_id": self.related_id,
        }


@dataclass
class CatalogEntry:
    """Parsed catalog entry plus its source text."""

    path: Path
    relative_path: str
    content: bytes
    text: str
    metadata: dict[str, Any]
    pattern_id: str | None
    name: str | None
    entry_type: str | None
    part: str | None
    observable: bool | None


@dataclass(frozen=True)
class IndexEntry:
    """One row from the master index's catalog tables."""

    pattern_id: str
    name: str
    entry_type: str
    part: str
    dimensions: tuple[int, ...]
    creator_phases: tuple[str, ...]
    related_patterns: tuple[str, ...]
    line: int


def default_catalog_dir() -> Path:
    """Return the bundled Presentation Patterns catalog."""
    return (
        Path(__file__).resolve().parents[2]
        / "presentation-creator"
        / "references"
        / "patterns"
    )


def normalize_alias(value: str) -> str:
    """Map an ID, name, or explicit alias into the collision namespace."""
    return normalize_catalog_alias(value)


def _visible_markdown_lines(text: str) -> list[tuple[int, str]]:
    """Return source lines outside fenced code blocks, with line numbers."""
    visible: list[tuple[int, str]] = []
    fence_character: str | None = None
    fence_length = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        fence = FENCE_RE.match(line)
        if fence_character is not None:
            if fence is not None:
                marker = fence.group("marker")
                if (
                    marker[0] == fence_character
                    and len(marker) >= fence_length
                    and not fence.group("rest").strip()
                ):
                    fence_character = None
                    fence_length = 0
            continue
        if fence is not None:
            marker = fence.group("marker")
            fence_character = marker[0]
            fence_length = len(marker)
            continue
        visible.append((line_number, line))
    return visible


def _markdown_h2_section(text: str, heading: str) -> str | None:
    """Return one visible H2 section, excluding fenced examples."""
    lines = _visible_markdown_lines(text)
    start: int | None = None
    for offset, (_, line) in enumerate(lines):
        if line.rstrip(" \t") == f"## {heading}":
            start = offset + 1
            break
    if start is None:
        return None
    section: list[str] = []
    for _, line in lines[start:]:
        if line.startswith("## "):
            break
        section.append(line)
    return "\n".join(section)


def _issue_sort_key(issue: Issue) -> tuple[str, str, str, str, str, str]:
    return (
        issue.code,
        issue.path,
        issue.entry_id,
        issue.field,
        issue.related_id,
        issue.message,
    )


def _code_counts(issues: list[Issue]) -> dict[str, int]:
    return dict(sorted(Counter(issue.code for issue in issues).items()))


def _parse_frontmatter(
    path: Path,
    relative_path: str,
    text: str,
    errors: list[Issue],
) -> dict[str, Any]:
    if not text.startswith("---\n"):
        errors.append(
            Issue(
                "frontmatter_missing",
                "catalog entry must start with YAML frontmatter",
                relative_path,
            )
        )
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        errors.append(
            Issue(
                "frontmatter_unterminated",
                "catalog entry frontmatter has no closing delimiter",
                relative_path,
            )
        )
        return {}
    try:
        value = load_catalog_yaml(text[4:end]) or {}
    except DuplicateYAMLKeyError as exc:
        errors.append(
            Issue(
                "frontmatter_duplicate_key",
                f"catalog entry frontmatter repeats a YAML mapping key: {exc}",
                relative_path,
            )
        )
        return {}
    except YAMLError as exc:
        errors.append(
            Issue(
                "frontmatter_invalid_yaml",
                f"catalog entry frontmatter is invalid YAML: {exc}",
                relative_path,
            )
        )
        return {}
    if not isinstance(value, dict):
        errors.append(
            Issue(
                "frontmatter_not_mapping",
                "catalog entry frontmatter must be a mapping",
                relative_path,
            )
        )
        return {}
    return value


def _read_entry(path: Path, root: Path, errors: list[Issue]) -> CatalogEntry:
    relative_path = path.relative_to(root).as_posix()
    try:
        content = path.read_bytes()
    except OSError as exc:
        errors.append(
            Issue(
                "entry_unreadable",
                f"catalog entry cannot be read as UTF-8: {exc}",
                relative_path,
            )
        )
        return CatalogEntry(
            path, relative_path, b"", "", {}, None, None, None, None, None
        )
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        errors.append(
            Issue(
                "entry_unreadable",
                f"catalog entry cannot be read as UTF-8: {exc}",
                relative_path,
            )
        )
        return CatalogEntry(
            path, relative_path, content, "", {}, None, None, None, None, None
        )

    metadata = _parse_frontmatter(path, relative_path, text, errors)
    raw_id = metadata.get("id")
    pattern_id = raw_id if isinstance(raw_id, str) and raw_id else None
    raw_name = metadata.get("name")
    name = raw_name if isinstance(raw_name, str) and raw_name else None
    raw_type = metadata.get("type")
    entry_type = raw_type if isinstance(raw_type, str) else None
    raw_part = metadata.get("part")
    part = raw_part if isinstance(raw_part, str) else None
    raw_observable = metadata.get("observable", True)
    observable = raw_observable if isinstance(raw_observable, bool) else None
    return CatalogEntry(
        path,
        relative_path,
        content,
        text,
        metadata,
        pattern_id,
        name,
        entry_type,
        part,
        observable,
    )


def _required_string(
    entry: CatalogEntry,
    field: str,
    errors: list[Issue],
) -> str | None:
    value = entry.metadata.get(field)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        errors.append(
            Issue(
                "field_invalid_string",
                f"{field} must be a trimmed non-empty string",
                entry.relative_path,
                entry.pattern_id or "",
                field,
            )
        )
        return None
    return value


def _string_list(
    entry: CatalogEntry,
    field: str,
    errors: list[Issue],
    *,
    required: bool = True,
    nonempty: bool = False,
) -> list[str] | None:
    value = entry.metadata.get(field)
    if value is None and not required:
        return []
    if (
        not isinstance(value, list)
        or (nonempty and not value)
        or any(
            not isinstance(item, str) or not item.strip() or item != item.strip()
            for item in value
        )
    ):
        requirement = "non-empty " if nonempty else ""
        errors.append(
            Issue(
                "field_invalid_list",
                f"{field} must be a {requirement}list of trimmed non-empty strings",
                entry.relative_path,
                entry.pattern_id or "",
                field,
            )
        )
        return None
    if len(value) != len(set(value)):
        errors.append(
            Issue(
                "field_duplicate_values",
                f"{field} contains duplicate values",
                entry.relative_path,
                entry.pattern_id or "",
                field,
            )
        )
    return value


def _validate_entry_identity(entry: CatalogEntry, errors: list[Issue]) -> None:
    pattern_id = _required_string(entry, "id", errors)
    _required_string(entry, "name", errors)
    entry_type = _required_string(entry, "type", errors)
    part = _required_string(entry, "part", errors)

    if pattern_id is not None and not ID_RE.fullmatch(pattern_id):
        errors.append(
            Issue(
                "id_invalid",
                "id must be a lowercase kebab-case token",
                entry.relative_path,
                pattern_id,
                "id",
            )
        )

    stem = entry.path.stem
    expected_id = stem.removeprefix("_anti_")
    if pattern_id is not None and pattern_id != expected_id:
        errors.append(
            Issue(
                "filename_id_mismatch",
                f"filename encodes id {expected_id!r}, frontmatter declares {pattern_id!r}",
                entry.relative_path,
                pattern_id,
                "id",
            )
        )

    expected_type = "antipattern" if stem.startswith("_anti_") else "pattern"
    if entry_type is not None and entry_type not in ENTRY_TYPES:
        errors.append(
            Issue(
                "type_invalid",
                f"type must be one of {sorted(ENTRY_TYPES)}, got {entry_type!r}",
                entry.relative_path,
                pattern_id or "",
                "type",
            )
        )
    elif entry_type is not None and entry_type != expected_type:
        errors.append(
            Issue(
                "filename_type_mismatch",
                f"filename requires type {expected_type!r}, frontmatter declares {entry_type!r}",
                entry.relative_path,
                pattern_id or "",
                "type",
            )
        )

    parent_part = entry.path.parent.name
    if part is not None and part not in PARTS:
        errors.append(
            Issue(
                "part_invalid",
                f"part must be one of {sorted(PARTS)}, got {part!r}",
                entry.relative_path,
                pattern_id or "",
                "part",
            )
        )
    elif part is not None and part != parent_part:
        errors.append(
            Issue(
                "directory_part_mismatch",
                f"directory requires part {parent_part!r}, frontmatter declares {part!r}",
                entry.relative_path,
                pattern_id or "",
                "part",
            )
        )

    relative_parts = Path(entry.relative_path).parts
    if len(relative_parts) != 2 or parent_part not in PARTS:
        errors.append(
            Issue(
                "entry_path_invalid",
                "entry must live directly under prepare/, build/, or deliver/",
                entry.relative_path,
                pattern_id or "",
            )
        )


def _validate_dimensions_and_phases(
    entry: CatalogEntry,
    errors: list[Issue],
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    raw_dimensions = entry.metadata.get("vault_dimensions")
    dimensions: tuple[int, ...] = ()
    if (
        not isinstance(raw_dimensions, list)
        or not raw_dimensions
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 1
            or value > 14
            for value in raw_dimensions
        )
    ):
        errors.append(
            Issue(
                "vault_dimensions_invalid",
                "vault_dimensions must be a non-empty list of integers from 1 through 14",
                entry.relative_path,
                entry.pattern_id or "",
                "vault_dimensions",
            )
        )
    else:
        dimensions = tuple(raw_dimensions)
        if len(dimensions) != len(set(dimensions)):
            errors.append(
                Issue(
                    "vault_dimensions_duplicate",
                    "vault_dimensions contains duplicate values",
                    entry.relative_path,
                    entry.pattern_id or "",
                    "vault_dimensions",
                )
            )

    phases = _string_list(
        entry,
        "phase_relevance",
        errors,
        nonempty=True,
    )
    phase_values = tuple(phases or ())
    unknown = sorted(set(phase_values) - CREATOR_PHASES)
    if unknown:
        errors.append(
            Issue(
                "creator_phase_invalid",
                f"phase_relevance contains values outside the creator phase namespace: {unknown}",
                entry.relative_path,
                entry.pattern_id or "",
                "phase_relevance",
            )
        )
    return dimensions, phase_values


def _validate_observability(entry: CatalogEntry, errors: list[Issue]) -> None:
    raw_observable = entry.metadata.get("observable", True)
    if not isinstance(raw_observable, bool):
        errors.append(
            Issue(
                "observable_invalid",
                "observable must be a boolean when declared",
                entry.relative_path,
                entry.pattern_id or "",
                "observable",
            )
        )

    present_base = BASE_EVIDENCE_GATE_FIELDS.intersection(entry.metadata)
    present_outcomes = OUTCOME_EVIDENCE_GATE_FIELDS.intersection(entry.metadata)
    present_applicability = APPLICABILITY_GATE_FIELDS.intersection(entry.metadata)
    present = present_base | present_outcomes | present_applicability
    has_evidence_section = (
        _markdown_h2_section(
            entry.text,
            "Evidence Gate",
        )
        is not None
    )
    if present and present_base != BASE_EVIDENCE_GATE_FIELDS:
        errors.append(
            Issue(
                "source_gate_partial",
                f"source gate is partial; present fields are {sorted(present)}",
                entry.relative_path,
                entry.pattern_id or "",
                "evaluable_from",
            )
        )
        return

    if not present:
        if has_evidence_section:
            errors.append(
                Issue(
                    "source_gate_metadata_missing",
                    "Evidence Gate prose requires the complete source-gate frontmatter",
                    entry.relative_path,
                    entry.pattern_id or "",
                    "evaluable_from",
                )
            )
        return

    if raw_observable is False:
        errors.append(
            Issue(
                "unobservable_source_gate_conflict",
                "observable:false entries are skipped and cannot also declare a scoring source gate",
                entry.relative_path,
                entry.pattern_id or "",
                "observable",
            )
        )

    for field in ("evaluable_from", "strong_evaluable_from", "absence_evaluable_from"):
        if field not in entry.metadata:
            continue
        if field == "absence_evaluable_from" and entry.metadata[field] is None:
            continue
        try:
            parse_evidence_source_groups(
                entry.metadata.get(field), EVIDENCE_SOURCES, field_name=field
            )
        except ValueError as exc:
            errors.append(
                Issue(
                    "evidence_source_invalid",
                    str(exc),
                    entry.relative_path,
                    entry.pattern_id or "",
                    field,
                )
            )

    if present_applicability and present_applicability != APPLICABILITY_GATE_FIELDS:
        errors.append(
            Issue(
                "applicability_contract_partial",
                "not_applicable_when and applicability_evaluable_from must be declared together",
                entry.relative_path,
                entry.pattern_id or "",
                "not_applicable_when",
            )
        )
    elif present_applicability == APPLICABILITY_GATE_FIELDS:
        try:
            parse_evidence_source_groups(
                entry.metadata.get("applicability_evaluable_from"),
                EVIDENCE_SOURCES,
                field_name="applicability_evaluable_from",
            )
        except ValueError as exc:
            errors.append(
                Issue(
                    "applicability_evidence_source_invalid",
                    str(exc),
                    entry.relative_path,
                    entry.pattern_id or "",
                    "applicability_evaluable_from",
                )
            )

        conditions = entry.metadata.get("not_applicable_when")
        if not isinstance(conditions, list) or not conditions:
            errors.append(
                Issue(
                    "not_applicable_conditions_invalid",
                    "not_applicable_when must be a non-empty list of condition objects",
                    entry.relative_path,
                    entry.pattern_id or "",
                    "not_applicable_when",
                )
            )
        else:
            seen_condition_ids: set[str] = set()
            for position, condition in enumerate(conditions):
                if not isinstance(condition, dict) or set(condition) != {
                    "condition_id",
                    "description",
                }:
                    errors.append(
                        Issue(
                            "not_applicable_condition_invalid",
                            "each applicability condition must contain exactly condition_id and description",
                            entry.relative_path,
                            entry.pattern_id or "",
                            f"not_applicable_when[{position}]",
                        )
                    )
                    continue
                condition_id = condition.get("condition_id")
                description = condition.get("description")
                if not isinstance(condition_id, str) or not ID_RE.fullmatch(
                    condition_id
                ):
                    errors.append(
                        Issue(
                            "not_applicable_condition_id_invalid",
                            "condition_id must use the catalog's stable lowercase-hyphen identifier form",
                            entry.relative_path,
                            entry.pattern_id or "",
                            f"not_applicable_when[{position}].condition_id",
                        )
                    )
                elif condition_id in seen_condition_ids:
                    errors.append(
                        Issue(
                            "not_applicable_condition_duplicate",
                            "condition_id is duplicated within the entry",
                            entry.relative_path,
                            entry.pattern_id or "",
                            f"not_applicable_when[{position}].condition_id",
                        )
                    )
                else:
                    seen_condition_ids.add(condition_id)
                if not isinstance(description, str) or not description.strip():
                    errors.append(
                        Issue(
                            "not_applicable_description_invalid",
                            "applicability condition description must be a non-empty string",
                            entry.relative_path,
                            entry.pattern_id or "",
                            f"not_applicable_when[{position}].description",
                        )
                    )
    _string_list(entry, "evidence_requirements", errors, nonempty=True)
    _string_list(entry, "not_evaluable_when", errors, nonempty=True)
    if not has_evidence_section:
        errors.append(
            Issue(
                "source_gate_prose_missing",
                "source-gated entry must include an Evidence Gate section",
                entry.relative_path,
                entry.pattern_id or "",
                "evaluable_from",
            )
        )


def _validate_current_absence_capability(
    entry: CatalogEntry,
    errors: list[Issue],
) -> None:
    """Reject absence gates that current receipts cannot prove exhaustive."""
    if not BASE_EVIDENCE_GATE_FIELDS <= set(entry.metadata):
        return
    raw_gate = entry.metadata.get(
        "absence_evaluable_from",
        entry.metadata.get("evaluable_from"),
    )
    if raw_gate is None or not isinstance(raw_gate, list):
        return

    unsupported: list[str] = []
    for position, alternative in enumerate(raw_gate):
        if isinstance(alternative, str):
            sources = [alternative]
            nested = False
        elif isinstance(alternative, list):
            sources = alternative
            nested = True
        else:
            continue
        unsafe_sources = sorted(
            source
            for source in sources
            if isinstance(source, str)
            and source not in CURRENT_ABSENCE_CAPABILITY_SOURCES
        )
        if nested or unsafe_sources:
            details = []
            if nested:
                details.append("nested all-of alternative")
            if unsafe_sources:
                details.append(f"unsupported sources {unsafe_sources}")
            unsupported.append(f"alternative {position}: {', '.join(details)}")

    if unsupported:
        errors.append(
            Issue(
                "absence_source_capability_unsupported",
                "current-generation absence gates require singleton static_slides "
                "or transcript alternatives; " + "; ".join(unsupported),
                entry.relative_path,
                entry.pattern_id or "",
                "absence_evaluable_from",
            )
        )


def _scoring_section(text: str) -> str | None:
    return _markdown_h2_section(text, "Scoring Criteria")


def _validate_scoring(entry: CatalogEntry, errors: list[Issue]) -> None:
    section = _scoring_section(entry.text)
    if section is None:
        errors.append(
            Issue(
                "scoring_section_missing",
                "entry must include a Scoring Criteria section",
                entry.relative_path,
                entry.pattern_id or "",
                "scoring_criteria",
            )
        )
        return

    if SCORING_ARITHMETIC_LABEL_RE.search(section):
        errors.append(
            Issue(
                "scoring_arithmetic_label_forbidden",
                "scoring decision labels are non-arithmetic and must not declare point values",
                entry.relative_path,
                entry.pattern_id or "",
                "scoring_criteria",
            )
        )
    if SCORING_MEDIUM_LABEL_RE.search(section):
        errors.append(
            Issue(
                "scoring_medium_label_invalid",
                "Medium signal is not canonical; use Moderate signal without "
                "treating medium as an alias",
                entry.relative_path,
                entry.pattern_id or "",
                "scoring_criteria",
            )
        )

    strong = list(SCORING_STRONG_RE.finditer(section))
    moderate = list(SCORING_MODERATE_RE.finditer(section))
    absent = list(SCORING_ABSENT_RE.finditer(section))
    for label, matches in (
        ("strong", strong),
        ("moderate", moderate),
        ("absent", absent),
    ):
        if len(matches) != 1:
            errors.append(
                Issue(
                    "scoring_label_count_invalid",
                    f"scoring section must contain exactly one {label} label; found {len(matches)}",
                    entry.relative_path,
                    entry.pattern_id or "",
                    "scoring_criteria",
                )
            )
    if len(strong) != 1 or len(moderate) != 1 or len(absent) != 1:
        return

    if not all(
        match.group("body").strip() for match in (strong[0], moderate[0], absent[0])
    ):
        errors.append(
            Issue(
                "scoring_description_empty",
                "every scoring label must have a non-empty same-line description",
                entry.relative_path,
                entry.pattern_id or "",
                "scoring_criteria",
            )
        )

    strong_qualifier = (strong[0].group("qualifier") or "").strip().casefold()
    absent_qualifier = (absent[0].group("qualifier") or "").strip().casefold()
    if entry.entry_type == "antipattern":
        if strong_qualifier != "antipattern present":
            errors.append(
                Issue(
                    "antipattern_scoring_polarity_inverted",
                    "Strong signal must be labelled as antipattern present",
                    entry.relative_path,
                    entry.pattern_id or "",
                    "scoring_criteria",
                )
            )
        if absent_qualifier != "antipattern not present":
            errors.append(
                Issue(
                    "antipattern_scoring_polarity_inverted",
                    "Absent must be labelled as antipattern not present",
                    entry.relative_path,
                    entry.pattern_id or "",
                    "scoring_criteria",
                )
            )
    elif entry.entry_type == "pattern" and (strong_qualifier or absent_qualifier):
        errors.append(
            Issue(
                "pattern_scoring_qualifier_invalid",
                "pattern scoring labels must use the unqualified direct scale",
                entry.relative_path,
                entry.pattern_id or "",
                "scoring_criteria",
            )
        )


def _parse_csv(value: str) -> tuple[str, ...]:
    if not value or value in {"—", "-"}:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_index(
    root: Path,
    errors: list[Issue],
) -> tuple[str, bytes, dict[str, IndexEntry], set[str]]:
    path = root / "_index.md"
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        errors.append(
            Issue(
                "index_missing",
                "catalog root must contain _index.md",
                "_index.md",
            )
        )
        return "", b"", {}, set()
    except OSError as exc:
        errors.append(
            Issue(
                "index_unreadable",
                f"catalog index cannot be read as UTF-8: {exc}",
                "_index.md",
            )
        )
        return "", b"", {}, set()
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        errors.append(
            Issue(
                "index_unreadable",
                f"catalog index cannot be read as UTF-8: {exc}",
                "_index.md",
            )
        )
        return "", content, {}, set()

    rows: dict[str, IndexEntry] = {}
    in_catalog = False
    part: str | None = None
    visible_lines = _visible_markdown_lines(text)
    for line_number, line in visible_lines:
        if line == "## Pattern Catalog":
            in_catalog = True
            continue
        if in_catalog and line.startswith("## "):
            break
        if not in_catalog:
            continue
        heading = INDEX_PHASE_RE.match(line)
        if heading:
            part = heading.group(1).casefold()
            continue
        if not line.startswith("|"):
            continue
        cells = tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        if not cells or cells[0] == "ID" or set(cells[0]) <= {"-", ":"}:
            continue
        if len(cells) != 6:
            errors.append(
                Issue(
                    "index_row_malformed",
                    f"catalog table row must have six cells; found {len(cells)} on line {line_number}",
                    "_index.md",
                )
            )
            continue
        pattern_id, name, entry_type, raw_dimensions, raw_phases, raw_related = cells
        if part is None:
            errors.append(
                Issue(
                    "index_row_without_part",
                    f"catalog row {pattern_id!r} has no phase heading",
                    "_index.md",
                    pattern_id,
                )
            )
            continue
        if not ID_RE.fullmatch(pattern_id):
            errors.append(
                Issue(
                    "index_id_invalid",
                    f"index id {pattern_id!r} is not lowercase kebab-case",
                    "_index.md",
                    pattern_id,
                    "id",
                )
            )
        if not name:
            errors.append(
                Issue(
                    "index_name_invalid",
                    "index name must be non-empty",
                    "_index.md",
                    pattern_id,
                    "name",
                )
            )
        try:
            dimensions = tuple(int(value) for value in _parse_csv(raw_dimensions))
        except ValueError:
            dimensions = ()
            errors.append(
                Issue(
                    "index_dimensions_invalid",
                    f"index dimensions are not integers on line {line_number}",
                    "_index.md",
                    pattern_id,
                    "vault_dimensions",
                )
            )
        else:
            if not dimensions or any(value < 1 or value > 14 for value in dimensions):
                errors.append(
                    Issue(
                        "index_dimensions_invalid",
                        "index dimensions must be a non-empty list of integers from 1 through 14",
                        "_index.md",
                        pattern_id,
                        "vault_dimensions",
                    )
                )
            if len(dimensions) != len(set(dimensions)):
                errors.append(
                    Issue(
                        "index_dimensions_duplicate",
                        "index dimensions contain duplicate values",
                        "_index.md",
                        pattern_id,
                        "vault_dimensions",
                    )
                )

        creator_phases = _parse_csv(raw_phases)
        if not creator_phases or set(creator_phases) - CREATOR_PHASES:
            errors.append(
                Issue(
                    "index_creator_phases_invalid",
                    "index creator phases must be a non-empty list from the creator phase namespace",
                    "_index.md",
                    pattern_id,
                    "phase_relevance",
                )
            )
        if len(creator_phases) != len(set(creator_phases)):
            errors.append(
                Issue(
                    "index_creator_phases_duplicate",
                    "index creator phases contain duplicate values",
                    "_index.md",
                    pattern_id,
                    "phase_relevance",
                )
            )

        related_patterns = _parse_csv(raw_related)
        if len(related_patterns) != len(set(related_patterns)):
            errors.append(
                Issue(
                    "index_related_duplicate",
                    "index related IDs contain duplicate values",
                    "_index.md",
                    pattern_id,
                    "related_patterns",
                )
            )
        row = IndexEntry(
            pattern_id,
            name,
            entry_type,
            part,
            dimensions,
            creator_phases,
            related_patterns,
            line_number,
        )
        if pattern_id in rows:
            errors.append(
                Issue(
                    "index_id_duplicate",
                    f"index id appears more than once; duplicate is on line {line_number}",
                    "_index.md",
                    pattern_id,
                    "id",
                )
            )
        else:
            rows[pattern_id] = row

    unobservable: set[str] = set()
    unobservable_start = next(
        (
            offset + 1
            for offset, (_, line) in enumerate(visible_lines)
            if line.startswith("## Unobservable Patterns")
        ),
        None,
    )
    if unobservable_start is not None:
        for _, line in visible_lines[unobservable_start:]:
            if line.startswith("## "):
                break
            if not line.startswith("|"):
                continue
            cells = tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
            if len(cells) == 3 and ID_RE.fullmatch(cells[0]):
                if cells[0] in unobservable:
                    errors.append(
                        Issue(
                            "index_unobservable_duplicate",
                            "unobservable checklist ID appears more than once",
                            "_index.md",
                            cells[0],
                            "observable",
                        )
                    )
                unobservable.add(cells[0])
    else:
        errors.append(
            Issue(
                "index_unobservable_section_missing",
                "catalog index must contain the Unobservable Patterns section",
                "_index.md",
            )
        )
    return text, content, rows, unobservable


def _entry_references(
    entry: CatalogEntry,
    errors: list[Issue],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    related = _string_list(entry, "related_patterns", errors)
    inverse = _string_list(entry, "inverse_of", errors)
    aliases = _string_list(entry, "aliases", errors, required=False)
    return tuple(related or ()), tuple(inverse or ()), tuple(aliases or ())


def _compare_index(
    entries: dict[str, CatalogEntry],
    dimensions: dict[str, tuple[int, ...]],
    phases: dict[str, tuple[str, ...]],
    related: dict[str, tuple[str, ...]],
    index_rows: dict[str, IndexEntry],
    errors: list[Issue],
    debts: list[Issue],
) -> None:
    file_ids = set(entries)
    index_ids = set(index_rows)
    for pattern_id in sorted(file_ids - index_ids):
        entry = entries[pattern_id]
        errors.append(
            Issue(
                "index_entry_missing",
                "catalog file has no master-index row",
                entry.relative_path,
                pattern_id,
            )
        )
    for pattern_id in sorted(index_ids - file_ids):
        row = index_rows[pattern_id]
        errors.append(
            Issue(
                "index_entry_orphaned",
                f"master-index row on line {row.line} has no catalog file",
                "_index.md",
                pattern_id,
            )
        )

    for pattern_id in sorted(file_ids & index_ids):
        entry = entries[pattern_id]
        row = index_rows[pattern_id]
        if row.entry_type != entry.entry_type:
            errors.append(
                Issue(
                    "index_type_mismatch",
                    f"index declares {row.entry_type!r}, file declares {entry.entry_type!r}",
                    entry.relative_path,
                    pattern_id,
                    "type",
                )
            )
        if row.part != entry.part:
            errors.append(
                Issue(
                    "index_part_mismatch",
                    f"index places entry in {row.part!r}, file declares {entry.part!r}",
                    entry.relative_path,
                    pattern_id,
                    "part",
                )
            )
        if entry.name is not None and row.name != entry.name:
            debts.append(
                Issue(
                    "index_name_drift",
                    f"index name {row.name!r} differs from file name {entry.name!r}",
                    entry.relative_path,
                    pattern_id,
                    "name",
                )
            )
        if set(row.dimensions) != set(dimensions.get(pattern_id, ())):
            debts.append(
                Issue(
                    "index_dimensions_drift",
                    f"index dimensions {list(row.dimensions)} differ from file dimensions "
                    f"{list(dimensions.get(pattern_id, ()))}",
                    entry.relative_path,
                    pattern_id,
                    "vault_dimensions",
                )
            )
        if set(row.creator_phases) != set(phases.get(pattern_id, ())):
            debts.append(
                Issue(
                    "index_phases_drift",
                    f"index phases {list(row.creator_phases)} differ from file phases "
                    f"{list(phases.get(pattern_id, ()))}",
                    entry.relative_path,
                    pattern_id,
                    "phase_relevance",
                )
            )
        if set(row.related_patterns) != set(related.get(pattern_id, ())):
            debts.append(
                Issue(
                    "index_related_drift",
                    f"index related IDs {list(row.related_patterns)} differ from file IDs "
                    f"{list(related.get(pattern_id, ()))}",
                    entry.relative_path,
                    pattern_id,
                    "related_patterns",
                )
            )


def _validate_graph(
    entries: dict[str, CatalogEntry],
    related: dict[str, tuple[str, ...]],
    inverse: dict[str, tuple[str, ...]],
    errors: list[Issue],
    debts: list[Issue],
) -> None:
    ids = set(entries)
    same_polarity_pairs: set[tuple[str, str]] = set()
    for pattern_id in sorted(entries):
        entry = entries[pattern_id]
        for field, targets in (
            ("related_patterns", related.get(pattern_id, ())),
            ("inverse_of", inverse.get(pattern_id, ())),
        ):
            for target in targets:
                if target == pattern_id:
                    errors.append(
                        Issue(
                            "reference_self",
                            f"{field} cannot reference the entry itself",
                            entry.relative_path,
                            pattern_id,
                            field,
                            target,
                        )
                    )
                elif target not in ids:
                    errors.append(
                        Issue(
                            "reference_dangling",
                            f"{field} references unknown catalog id {target!r}",
                            entry.relative_path,
                            pattern_id,
                            field,
                            target,
                        )
                    )

        for target in inverse.get(pattern_id, ()):
            if target not in ids or target == pattern_id:
                continue
            if pattern_id not in inverse.get(target, ()):
                errors.append(
                    Issue(
                        "inverse_not_reciprocal",
                        f"{target!r} does not declare {pattern_id!r} in inverse_of",
                        entry.relative_path,
                        pattern_id,
                        "inverse_of",
                        target,
                    )
                )
            target_entry = entries[target]
            pair = (
                (pattern_id, target) if pattern_id <= target else (target, pattern_id)
            )
            if (
                entry.entry_type == target_entry.entry_type
                and pair not in same_polarity_pairs
            ):
                same_polarity_pairs.add(pair)
                debts.append(
                    Issue(
                        "inverse_same_polarity",
                        "inverse relationship joins entries with the same catalog polarity",
                        entry.relative_path,
                        pattern_id,
                        "inverse_of",
                        target,
                    )
                )


def _validate_aliases(
    entries: dict[str, CatalogEntry],
    aliases: dict[str, tuple[str, ...]],
    errors: list[Issue],
) -> list[dict[str, Any]]:
    claims: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for pattern_id in sorted(entries):
        entry = entries[pattern_id]
        raw_claims = [("id", pattern_id)]
        if entry.name is not None:
            raw_claims.append(("name", entry.name))
        raw_claims.extend(("aliases", value) for value in aliases.get(pattern_id, ()))

        explicit_seen: dict[str, str] = {}
        for field, value in raw_claims:
            normalized = normalize_alias(value)
            if not normalized:
                errors.append(
                    Issue(
                        "alias_normalizes_empty",
                        f"{field} value {value!r} has no alphanumeric alias form",
                        entry.relative_path,
                        pattern_id,
                        field,
                    )
                )
                continue
            if field == "aliases":
                previous = explicit_seen.get(normalized)
                if previous is not None:
                    errors.append(
                        Issue(
                            "alias_duplicate",
                            f"explicit aliases {previous!r} and {value!r} normalize identically",
                            entry.relative_path,
                            pattern_id,
                            "aliases",
                        )
                    )
                else:
                    explicit_seen[normalized] = value
            claims[normalized].append((pattern_id, field, value, entry.relative_path))

    namespace: list[dict[str, Any]] = []
    for normalized in sorted(claims):
        by_entry: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for pattern_id, field, value, path in claims[normalized]:
            by_entry[pattern_id].append((field, value, path))
        namespace.append(
            {
                "entries": sorted(by_entry),
                "normalized": normalized,
            }
        )
        entry_ids = sorted(by_entry)
        for offset, pattern_id in enumerate(entry_ids):
            for target in entry_ids[offset + 1 :]:
                path = sorted(item[2] for item in by_entry[pattern_id])[0]
                errors.append(
                    Issue(
                        "alias_collision",
                        f"catalog entries claim the same normalized alias {normalized!r}",
                        path,
                        pattern_id,
                        "aliases",
                        target,
                    )
                )
    return namespace


def _validate_unobservable_index(
    entries: dict[str, CatalogEntry],
    listed: set[str],
    errors: list[Issue],
) -> None:
    flagged = {
        pattern_id for pattern_id, entry in entries.items() if entry.observable is False
    }
    for pattern_id in sorted(flagged - listed):
        errors.append(
            Issue(
                "index_unobservable_missing",
                "observable:false entry is absent from the index go-live checklist",
                entries[pattern_id].relative_path,
                pattern_id,
                "observable",
            )
        )
    for pattern_id in sorted(listed - flagged):
        path = (
            entries[pattern_id].relative_path if pattern_id in entries else "_index.md"
        )
        errors.append(
            Issue(
                "index_unobservable_mismatch",
                "index go-live checklist entry is not declared observable:false",
                path,
                pattern_id,
                "observable",
            )
        )


def audit_catalog(
    catalog_dir: str | Path | None = None,
    *,
    enforce_current_source_capabilities: bool | None = None,
) -> dict[str, Any]:
    """Return a stable read-only catalog audit report."""
    if enforce_current_source_capabilities is None:
        enforce_current_source_capabilities = catalog_dir is None
    root = Path(catalog_dir) if catalog_dir is not None else default_catalog_dir()
    errors: list[Issue] = []
    debts: list[Issue] = []
    if not root.is_dir():
        errors.append(
            Issue(
                "catalog_directory_missing",
                f"catalog directory does not exist: {root}",
            )
        )
        return _build_report(root, b"", [], {}, {}, {}, {}, {}, [], errors, debts)

    _, index_content, index_rows, unobservable_listed = _parse_index(root, errors)
    entry_paths = catalog_entry_paths(root)
    if not entry_paths:
        errors.append(
            Issue(
                "catalog_empty",
                "catalog contains no entry Markdown files",
            )
        )

    parsed_entries = [_read_entry(path, root, errors) for path in entry_paths]
    entries: dict[str, CatalogEntry] = {}
    dimensions: dict[str, tuple[int, ...]] = {}
    phases: dict[str, tuple[str, ...]] = {}
    related: dict[str, tuple[str, ...]] = {}
    inverse: dict[str, tuple[str, ...]] = {}
    aliases: dict[str, tuple[str, ...]] = {}

    for entry in parsed_entries:
        _validate_entry_identity(entry, errors)
        _validate_observability(entry, errors)
        if enforce_current_source_capabilities:
            _validate_current_absence_capability(entry, errors)
        _validate_scoring(entry, errors)
        entry_dimensions, entry_phases = _validate_dimensions_and_phases(entry, errors)
        entry_related, entry_inverse, entry_aliases = _entry_references(entry, errors)
        if entry.pattern_id is None:
            continue
        if entry.pattern_id in entries:
            errors.append(
                Issue(
                    "id_duplicate",
                    f"id is already declared by {entries[entry.pattern_id].relative_path}",
                    entry.relative_path,
                    entry.pattern_id,
                    "id",
                )
            )
            continue
        entries[entry.pattern_id] = entry
        dimensions[entry.pattern_id] = entry_dimensions
        phases[entry.pattern_id] = entry_phases
        related[entry.pattern_id] = entry_related
        inverse[entry.pattern_id] = entry_inverse
        aliases[entry.pattern_id] = entry_aliases

    _compare_index(
        entries,
        dimensions,
        phases,
        related,
        index_rows,
        errors,
        debts,
    )
    _validate_graph(entries, related, inverse, errors, debts)
    alias_namespace = _validate_aliases(entries, aliases, errors)
    _validate_unobservable_index(entries, unobservable_listed, errors)

    for row in index_rows.values():
        for target in row.related_patterns:
            if target == row.pattern_id:
                errors.append(
                    Issue(
                        "index_reference_self",
                        "index Related cell cannot reference its own catalog id",
                        "_index.md",
                        row.pattern_id,
                        "related_patterns",
                        target,
                    )
                )
            elif target not in entries:
                errors.append(
                    Issue(
                        "index_reference_dangling",
                        f"index Related cell references unknown catalog id {target!r}",
                        "_index.md",
                        row.pattern_id,
                        "related_patterns",
                        target,
                    )
                )

    return _build_report(
        root,
        index_content,
        parsed_entries,
        entries,
        index_rows,
        related,
        inverse,
        aliases,
        alias_namespace,
        errors,
        debts,
    )


def _build_report(
    root: Path,
    index_content: bytes,
    parsed_entries: list[CatalogEntry],
    entries: dict[str, CatalogEntry],
    index_rows: dict[str, IndexEntry],
    related: dict[str, tuple[str, ...]],
    inverse: dict[str, tuple[str, ...]],
    aliases: dict[str, tuple[str, ...]],
    alias_namespace: list[dict[str, Any]],
    errors: list[Issue],
    debts: list[Issue],
) -> dict[str, Any]:
    ordered_errors = sorted(errors, key=_issue_sort_key)
    ordered_debts = sorted(debts, key=_issue_sort_key)
    entry_values = list(entries.values())
    patterns = sum(entry.entry_type == "pattern" for entry in entry_values)
    antipatterns = sum(entry.entry_type == "antipattern" for entry in entry_values)
    observable = sum(entry.observable is True for entry in entry_values)
    unobservable = sum(entry.observable is False for entry in entry_values)
    source_gated = sum(
        BASE_EVIDENCE_GATE_FIELDS <= set(entry.metadata) for entry in entry_values
    )
    absence_gated = sum(
        BASE_EVIDENCE_GATE_FIELDS <= set(entry.metadata)
        and entry.metadata.get(
            "absence_evaluable_from",
            entry.metadata.get("evaluable_from"),
        )
        is not None
        for entry in entry_values
    )
    applicability_gated = sum(
        APPLICABILITY_GATE_FIELDS <= set(entry.metadata) for entry in entry_values
    )
    positive_only = source_gated - absence_gated
    related_edges = sorted(
        [source, target] for source, targets in related.items() for target in targets
    )
    inverse_declarations = sorted(
        [source, target] for source, targets in inverse.items() for target in targets
    )
    explicit_alias_count = sum(len(values) for values in aliases.values())
    return {
        "catalog": {
            "fingerprint": catalog_fingerprint(
                index_content,
                ((entry.relative_path, entry.content) for entry in parsed_entries),
            ),
            "index": "_index.md",
            "path": root.as_posix(),
        },
        "errors": [issue.as_dict() for issue in ordered_errors],
        "graph": {
            "alias_namespace": alias_namespace,
            "inverse_declarations": inverse_declarations,
            "related_edges": related_edges,
        },
        "schema_version": SCHEMA_VERSION,
        "semantic_debts": [issue.as_dict() for issue in ordered_debts],
        "summary": {
            "alias_keys": len(alias_namespace),
            "antipatterns": antipatterns,
            "applicability_gated": applicability_gated,
            "absence_gated": absence_gated,
            "entries_loaded": len(entries),
            "entry_files": len(parsed_entries),
            "error_codes": _code_counts(ordered_errors),
            "errors": len(ordered_errors),
            "explicit_aliases": explicit_alias_count,
            "index_entries": len(index_rows),
            "inverse_declarations": len(inverse_declarations),
            "observable": observable,
            "patterns": patterns,
            "positive_gated": source_gated,
            "positive_only": positive_only,
            "related_edges": len(related_edges),
            "semantic_debt_codes": _code_counts(ordered_debts),
            "semantic_debts": len(ordered_debts),
            "source_gated": source_gated,
            "unobservable": unobservable,
        },
        "valid": not ordered_errors,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the Presentation Patterns catalog without modifying it.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="pattern catalog directory containing _index.md and phase subdirectories",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return its process status."""
    args = _parser().parse_args(argv)
    report = audit_catalog(args.catalog)
    # Serialize before writing: a `json.dump` straight to stdout that fails
    # partway leaves a truncated document the caller would try to parse.
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write(rendered + "\n")
    if not report["valid"]:
        print(
            f"catalog audit found {report['summary']['errors']} structural error(s); "
            "inspect JSON stdout before ingress or catalog edits",
            file=sys.stderr,
        )
        return 1
    return 0


def run_cli(argv: list[str] | None = None) -> int:
    """Run the CLI behind its failure boundary. Returns the process exit code.

    Importable so the boundary's contract is testable without executing the
    module as a script.
    """
    try:
        return main(argv)
    # Ingress gates on this audit, so a non-zero exit without the stdout report
    # must still say what happened; a traceback would leak catalog entry paths
    # and read a malformed catalog file as a broken auditor.
    except Exception as exc:  # noqa: BLE001 - outer-boundary-process-contract
        emit_unexpected_failure(
            exc,
            "catalog_audit_unexpected_failure",
            "The Presentation Patterns catalog audit failed unexpectedly. This "
            "command is read-only, so the catalog is unchanged — but it is "
            "UNAUDITED. Do not begin ingress or catalog edits until a clean run "
            "reports on stdout.",
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(run_cli())

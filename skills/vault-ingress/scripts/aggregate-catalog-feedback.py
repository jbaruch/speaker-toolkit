#!/usr/bin/env python3
"""Aggregate catalog feedback from return JSON without editing the catalog.

Inputs may be individual return files, batch arrays, an earlier feedback-harvest
wrapper, or directories (searched recursively for ``*.json``).  Every accepted
feedback entry keeps its source file, return index, talk identity, lane, and
entry index.  Exact catalog references and normalized new-name suggestions are
grouped separately with occurrence, talk, and source-return counts.

The five-lane schema, polarity rules, classifications, and report shape are
documented in ``references/catalog-feedback-intake.md``.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any
import unicodedata

import yaml


REPORT_SCHEMA_VERSION = 1
POLARITIES = frozenset({"pattern", "antipattern"})
LANES = (
    "unmatched_observations",
    "tensions",
    "definition_problems",
    "scoring_problems",
    "confusable_pairs",
)
LANE_SET = frozenset(LANES)
RETURN_MARKERS = frozenset({
    "status", "rhetoric_notes", "pattern_observations", "structured_data",
    "areas_for_improvement", "summary_updates", "verbatim_examples",
})


def _nonempty_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def normalize_suggestion(value: str) -> str:
    """Normalize formatting, not meaning, for free-text recurrence grouping."""
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = normalized.replace("’", "'")
    normalized = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE)
    normalized = re.sub(r"_+", "-", normalized)
    return normalized.strip("-")


def default_catalog_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "presentation-creator" / "references" / "patterns"
    )


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _frontmatter(raw: str) -> dict[str, Any] | None:
    if not raw.startswith("---\n"):
        return None
    end = raw.find("\n---", 4)
    if end < 0:
        return None
    loaded = yaml.safe_load(raw[4:end])
    return loaded if isinstance(loaded, dict) else None


def load_catalog(catalog_path: str | Path) -> dict[str, Any]:
    """Load exact IDs and their polarity from catalog-file frontmatter."""
    root = Path(catalog_path).expanduser().resolve(strict=False)
    registry: dict[str, dict[str, str]] = {}
    errors: list[dict[str, Any]] = []
    if not root.is_dir():
        errors.append(_issue(
            "catalog_directory_unreadable",
            "catalog path is not a readable directory",
            path=str(root),
        ))
        return {"path": str(root), "registry": registry, "errors": errors}

    for path in sorted(root.rglob("*.md"), key=lambda item: str(item)):
        if path.name == "_index.md":
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(_issue(
                "catalog_file_unreadable", f"cannot read catalog file: {exc}",
                path=str(path.resolve(strict=False)),
            ))
            continue
        try:
            metadata = _frontmatter(raw)
        except yaml.YAMLError as exc:
            errors.append(_issue(
                "catalog_frontmatter_invalid", f"invalid YAML frontmatter: {exc}",
                path=str(path.resolve(strict=False)),
            ))
            continue
        if metadata is None:
            errors.append(_issue(
                "catalog_frontmatter_missing",
                "catalog file has no parseable YAML frontmatter",
                path=str(path.resolve(strict=False)),
            ))
            continue

        catalog_id = _nonempty_string(metadata.get("id"))
        polarity = metadata.get("type")
        relative_path = str(path.relative_to(root))
        if catalog_id is None:
            errors.append(_issue(
                "catalog_id_missing", "catalog file has no nonempty id",
                path=relative_path,
            ))
            continue
        if polarity not in POLARITIES:
            errors.append(_issue(
                "catalog_polarity_invalid",
                "catalog type must be pattern or antipattern",
                path=relative_path, catalog_id=catalog_id, actual=polarity,
            ))
            continue

        filename_is_anti = path.stem.startswith("_anti_")
        filename_polarity = "antipattern" if filename_is_anti else "pattern"
        if polarity != filename_polarity:
            errors.append(_issue(
                "catalog_filename_polarity_mismatch",
                "catalog filename convention disagrees with frontmatter type",
                path=relative_path, catalog_id=catalog_id,
                expected=filename_polarity, actual=polarity,
            ))
        if catalog_id in registry:
            errors.append(_issue(
                "catalog_id_duplicate", "catalog id appears in multiple files",
                catalog_id=catalog_id,
                paths=[registry[catalog_id]["path"], relative_path],
            ))
            continue
        registry[catalog_id] = {"polarity": polarity, "path": relative_path}

    if not registry:
        errors.append(_issue(
            "catalog_empty", "catalog directory contains no valid pattern entries",
            path=str(root),
        ))
    return {"path": str(root), "registry": registry, "errors": errors}


def _provenance(
    source_path: Path,
    return_index: int,
    talk_filename: str | None,
    talk_id: str | None,
    *,
    lane: str | None = None,
    entry_index: int | None = None,
) -> dict[str, Any]:
    return {
        "source_path": str(source_path.resolve(strict=False)),
        "source_return_index": return_index,
        "talk_filename": talk_filename,
        "talk_id": talk_id,
        "feedback_lane": lane,
        "feedback_entry_index": entry_index,
    }


def _talk_key(provenance: dict[str, Any]) -> str:
    return provenance["talk_filename"] or provenance["talk_id"] or ""


def _source_return_key(provenance: dict[str, Any]) -> tuple[str, int]:
    return provenance["source_path"], provenance["source_return_index"]


def _require_text(
    entry: dict[str, Any], field: str, errors: list[dict[str, Any]],
) -> str | None:
    text = _nonempty_string(entry.get(field))
    if text is None:
        errors.append(_issue(
            "feedback_text_missing", f"{field} must be a nonempty string",
            field=field, actual=entry.get(field),
        ))
    return text


def _validate_catalog_ids(
    value: Any,
    *,
    registry: dict[str, dict[str, str]],
    errors: list[dict[str, Any]],
    exact_count: int | None = None,
    minimum_count: int | None = None,
) -> list[str]:
    if not isinstance(value, list):
        errors.append(_issue(
            "catalog_ids_not_array", "pattern_ids must be an array",
            field="pattern_ids", actual=value,
        ))
        return []
    if exact_count is not None and len(value) != exact_count:
        errors.append(_issue(
            "catalog_id_count_invalid",
            f"pattern_ids must contain exactly {exact_count} IDs",
            field="pattern_ids", expected=exact_count, actual=len(value),
        ))
    if minimum_count is not None and len(value) < minimum_count:
        errors.append(_issue(
            "catalog_id_count_invalid",
            f"pattern_ids must contain at least {minimum_count} IDs",
            field="pattern_ids", expected=f">={minimum_count}", actual=len(value),
        ))

    ids: list[str] = []
    for position, value_id in enumerate(value):
        catalog_id = _nonempty_string(value_id)
        if catalog_id is None or catalog_id != value_id:
            errors.append(_issue(
                "catalog_id_not_exact",
                "catalog IDs must be nonempty exact strings without normalization",
                field=f"pattern_ids[{position}]", actual=value_id,
            ))
            continue
        ids.append(catalog_id)
        if catalog_id not in registry:
            errors.append(_issue(
                "catalog_id_unknown", "catalog ID does not exist",
                field=f"pattern_ids[{position}]", actual=catalog_id,
            ))
    duplicates = sorted(
        catalog_id for catalog_id, count in Counter(ids).items() if count > 1
    )
    if duplicates:
        errors.append(_issue(
            "catalog_ids_duplicate", "pattern_ids must be distinct",
            field="pattern_ids", actual=duplicates,
        ))
    return ids


def _validate_polarity_assertions(
    entry: dict[str, Any],
    ids: list[str],
    registry: dict[str, dict[str, str]],
    errors: list[dict[str, Any]],
) -> None:
    """Validate optional producer assertions; catalog metadata stays authoritative."""
    if len(ids) == 1 and "catalog_polarity" in entry:
        actual = entry.get("catalog_polarity")
        expected = registry.get(ids[0], {}).get("polarity")
        if actual not in POLARITIES:
            errors.append(_issue(
                "catalog_polarity_invalid",
                "catalog_polarity must be pattern or antipattern",
                field="catalog_polarity", actual=actual,
            ))
        elif expected is not None and actual != expected:
            errors.append(_issue(
                "catalog_polarity_mismatch",
                "asserted polarity disagrees with the exact catalog ID",
                field="catalog_polarity", catalog_id=ids[0],
                expected=expected, actual=actual,
            ))

    if "catalog_polarities" not in entry:
        return
    assertions = entry.get("catalog_polarities")
    if not isinstance(assertions, dict):
        errors.append(_issue(
            "catalog_polarities_not_object",
            "catalog_polarities must map every referenced ID to its polarity",
            field="catalog_polarities", actual=assertions,
        ))
        return
    if set(assertions) != set(ids):
        errors.append(_issue(
            "catalog_polarity_keys_mismatch",
            "catalog_polarities keys must exactly match pattern_ids",
            field="catalog_polarities", expected=sorted(set(ids)),
            actual=sorted(str(key) for key in assertions),
        ))
    for catalog_id in sorted(set(ids) & set(assertions)):
        actual = assertions[catalog_id]
        expected = registry.get(catalog_id, {}).get("polarity")
        if actual not in POLARITIES:
            errors.append(_issue(
                "catalog_polarity_invalid",
                "asserted polarity must be pattern or antipattern",
                field=f"catalog_polarities.{catalog_id}", actual=actual,
            ))
        elif expected is not None and actual != expected:
            errors.append(_issue(
                "catalog_polarity_mismatch",
                "asserted polarity disagrees with the exact catalog ID",
                field=f"catalog_polarities.{catalog_id}", catalog_id=catalog_id,
                expected=expected, actual=actual,
            ))


def validate_entry(
    lane: str,
    entry: Any,
    registry: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Validate one canonical-lane entry and return derived grouping data."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    catalog_ids: list[str] = []
    suggestion: dict[str, Any] | None = None
    if not isinstance(entry, dict):
        errors.append(_issue(
            "feedback_entry_not_object", "feedback entry must be an object",
            actual=entry,
        ))
        return {
            "errors": errors, "warnings": warnings,
            "catalog_ids": catalog_ids, "suggestion": suggestion,
        }

    if lane == "unmatched_observations":
        _require_text(entry, "observation", errors)
        _require_text(entry, "why_no_pattern_fits", errors)
        proposed = entry.get("proposed_name")
        proposed_name = _nonempty_string(proposed)
        if proposed is not None and proposed_name is None:
            errors.append(_issue(
                "suggestion_name_invalid",
                "proposed_name must be null or a nonempty string",
                field="proposed_name", actual=proposed,
            ))
        proposed_polarity = entry.get("proposed_polarity")
        if proposed_name is None:
            if proposed_polarity is not None:
                errors.append(_issue(
                    "suggestion_polarity_without_name",
                    "proposed_polarity requires proposed_name",
                    field="proposed_polarity", actual=proposed_polarity,
                ))
        else:
            normalized = normalize_suggestion(proposed_name)
            if not normalized:
                errors.append(_issue(
                    "suggestion_name_invalid",
                    "proposed_name normalizes to an empty value",
                    field="proposed_name", actual=proposed_name,
                ))
            elif normalized in registry:
                errors.append(_issue(
                    "suggestion_matches_catalog_id",
                    "unmatched suggestion normalizes to an existing exact catalog ID",
                    field="proposed_name", actual=proposed_name,
                    catalog_id=normalized,
                ))
            if proposed_polarity is None:
                warnings.append(_issue(
                    "suggestion_polarity_missing",
                    "legacy suggestion needs human pattern/antipattern classification",
                    field="proposed_polarity", suggestion=normalized,
                ))
            elif proposed_polarity not in POLARITIES:
                errors.append(_issue(
                    "suggestion_polarity_invalid",
                    "proposed_polarity must be pattern or antipattern",
                    field="proposed_polarity", actual=proposed_polarity,
                ))
            suggestion = {
                "normalized_suggestion": normalized,
                "proposed_name": proposed_name,
                "proposed_polarity": proposed_polarity or "unspecified",
            }

    elif lane == "tensions":
        catalog_ids = _validate_catalog_ids(
            entry.get("pattern_ids"), registry=registry, errors=errors,
            minimum_count=2,
        )
        _require_text(entry, "nature", errors)
        _require_text(entry, "evidence", errors)
        _validate_polarity_assertions(entry, catalog_ids, registry, errors)

    elif lane == "definition_problems":
        pattern_id = entry.get("pattern_id")
        catalog_ids = _validate_catalog_ids(
            [pattern_id], registry=registry, errors=errors, exact_count=1,
        )
        _require_text(entry, "problem", errors)
        _require_text(entry, "detail", errors)
        _validate_polarity_assertions(entry, catalog_ids, registry, errors)

    elif lane == "scoring_problems":
        _require_text(entry, "issue", errors)
        _require_text(entry, "detail", errors)
        if "polarity" in entry and entry.get("polarity") != "neutral":
            errors.append(_issue(
                "lane_polarity_invalid",
                "scoring_problems is a neutral diagnostic lane",
                field="polarity", expected="neutral", actual=entry.get("polarity"),
            ))

    elif lane == "confusable_pairs":
        catalog_ids = _validate_catalog_ids(
            entry.get("pattern_ids"), registry=registry, errors=errors,
            exact_count=2,
        )
        _require_text(entry, "detail", errors)
        _validate_polarity_assertions(entry, catalog_ids, registry, errors)

    return {
        "errors": errors,
        "warnings": warnings,
        "catalog_ids": catalog_ids,
        "suggestion": suggestion,
    }


def discover_inputs(values: list[str | Path]) -> dict[str, Any]:
    """Resolve arguments to a de-duplicated, sorted concrete-file list."""
    discovered: defaultdict[Path, set[str]] = defaultdict(set)
    immediate: list[dict[str, Any]] = []
    discovery_warnings: list[dict[str, Any]] = []
    for value in values:
        argument = Path(value).expanduser().resolve(strict=False)
        if argument.is_dir():
            files = sorted(argument.rglob("*.json"), key=lambda item: str(item))
            if not files:
                immediate.append({
                    "path": str(argument), "kind": "directory", "status": "rejected",
                    "shape": None, "reason": "directory contains no JSON files",
                })
            for path in files:
                discovered[path.resolve(strict=False)].add(str(argument))
        else:
            discovered[argument].add(str(argument))

    for path, origins in discovered.items():
        if len(origins) > 1:
            discovery_warnings.append(_issue(
                "duplicate_input_suppressed",
                "the same concrete file was discovered through multiple inputs",
                path=str(path), discovered_from=sorted(origins),
            ))
    files = [
        {"path": path, "discovered_from": sorted(origins)}
        for path, origins in sorted(discovered.items(), key=lambda item: str(item[0]))
    ]
    return {
        "files": files,
        "immediate": immediate,
        "warnings": discovery_warnings,
    }


def _read_json(path: Path) -> tuple[Any | None, dict[str, Any] | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        return None, _issue(
            "input_encoding_invalid", f"input is not valid UTF-8: {exc}",
        )
    except OSError as exc:
        return None, _issue("input_unreadable", f"cannot read input: {exc}")
    try:
        return json.loads(raw, parse_constant=_reject_json_constant), None
    except json.JSONDecodeError as exc:
        return None, _issue(
            "input_json_invalid",
            f"input is not valid JSON at line {exc.lineno}, column {exc.colno}",
        )
    except ValueError as exc:
        return None, _issue("input_json_invalid", f"input is not valid JSON: {exc}")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard numeric constant {value}")


def _return_container(document: Any) -> tuple[list[Any] | None, str | None, str | None]:
    if isinstance(document, list):
        return document, "return_array", None
    if not isinstance(document, dict):
        return None, None, "top-level JSON must be a return object or return array"
    if "returns" in document:
        returns = document.get("returns")
        if not isinstance(returns, list):
            return None, None, "top-level returns must be an array"
        shape = "feedback_harvest" if any(
            isinstance(item, dict) and "feedback" in item for item in returns
        ) else "returns_wrapper"
        return returns, shape, None
    return_like = (
        "catalog_feedback" in document
        or "feedback" in document
        or (
            any(key in document for key in ("filename", "talk_id"))
            and bool(RETURN_MARKERS & set(document))
        )
    )
    if return_like:
        return [document], "single_return", None
    return None, None, "JSON object is not a recognized return document"


class FeedbackAggregator:
    """Collect validated feedback with deterministic provenance and grouping."""

    def __init__(self, catalog: dict[str, Any]):
        self.catalog = catalog
        self.registry: dict[str, dict[str, str]] = catalog["registry"]
        self.inputs: dict[str, list[dict[str, Any]]] = {
            "accepted": [], "rejected": [], "invalid": [],
        }
        self.returns: dict[str, list[dict[str, Any]]] = {
            "accepted": [], "rejected": [], "invalid": [],
        }
        self.entries: dict[str, list[dict[str, Any]]] = {
            "accepted": [], "invalid": [],
        }
        self.warnings: list[dict[str, Any]] = []
        self.validation_errors: list[dict[str, Any]] = []

    def consume_file(self, path: Path, discovered_from: list[str]) -> None:
        document, read_error = _read_json(path)
        base = {
            "path": str(path.resolve(strict=False)),
            "kind": "file",
            "discovered_from": discovered_from,
        }
        if read_error:
            self.inputs["invalid"].append({
                **base, "status": "invalid", "shape": None,
                "reason": read_error["message"], "issues": [read_error],
            })
            return

        return_items, shape, rejection = _return_container(document)
        if return_items is None:
            status = "invalid" if rejection == "top-level returns must be an array" else "rejected"
            self.inputs[status].append({
                **base, "status": status, "shape": None,
                "reason": rejection, "issues": [],
            })
            return

        before = self._counts()
        for return_index, return_item in enumerate(return_items):
            self._consume_return(path, return_index, return_item)
        after = self._counts()
        deltas = {key: after[key] - before[key] for key in after}
        invalid_count = deltas["invalid_returns"] + deltas["invalid_entries"]
        if invalid_count:
            status = "invalid"
            reason = "recognized return document contains invalid feedback data"
        elif deltas["accepted_returns"]:
            status = "accepted"
            reason = None
        else:
            status = "rejected"
            reason = "recognized returns contain no catalog_feedback"
        self.inputs[status].append({
            **base,
            "status": status,
            "shape": shape,
            "return_count": len(return_items),
            "accepted_return_count": deltas["accepted_returns"],
            "rejected_return_count": deltas["rejected_returns"],
            "invalid_return_count": deltas["invalid_returns"],
            "accepted_entry_count": deltas["accepted_entries"],
            "invalid_entry_count": deltas["invalid_entries"],
            "reason": reason,
        })

    def _counts(self) -> dict[str, int]:
        return {
            "accepted_returns": len(self.returns["accepted"]),
            "rejected_returns": len(self.returns["rejected"]),
            "invalid_returns": len(self.returns["invalid"]),
            "accepted_entries": len(self.entries["accepted"]),
            "invalid_entries": len(self.entries["invalid"]),
        }

    def _consume_return(self, path: Path, return_index: int, item: Any) -> None:
        if not isinstance(item, dict):
            provenance = _provenance(path, return_index, None, None)
            self.returns["invalid"].append({
                "provenance": provenance,
                "issues": [_issue(
                    "return_not_object", "return must be a JSON object", actual=item,
                )],
            })
            return

        talk_filename = _nonempty_string(item.get("filename"))
        talk_id = _nonempty_string(item.get("talk_id"))
        provenance = _provenance(path, return_index, talk_filename, talk_id)
        feedback_key = (
            "catalog_feedback" if "catalog_feedback" in item
            else "feedback" if "feedback" in item else None
        )
        if feedback_key is None:
            self.returns["rejected"].append({
                "provenance": provenance,
                "reason": "return has no catalog_feedback",
            })
            return
        issues = []
        if talk_filename is None and talk_id is None:
            issues.append(_issue(
                "talk_identity_missing",
                "feedback return needs a nonempty filename or talk_id",
            ))
        feedback = item.get(feedback_key)
        if not isinstance(feedback, dict):
            issues.append(_issue(
                "catalog_feedback_not_object",
                "catalog_feedback must be an object of the five feedback lanes",
                actual=feedback,
            ))
        if issues:
            self.returns["invalid"].append({
                "provenance": provenance, "issues": issues,
            })
            return

        assert isinstance(feedback, dict)  # narrowed by the validation above
        invalid_before = len(self.entries["invalid"])
        for lane, value in feedback.items():
            if lane not in LANE_SET:
                lane_provenance = _provenance(
                    path, return_index, talk_filename, talk_id, lane=lane,
                )
                self.entries["invalid"].append({
                    "provenance": lane_provenance,
                    "feedback": value,
                    "issues": [_issue(
                        "feedback_lane_unsupported",
                        "catalog_feedback contains a lane outside the five-lane contract",
                        expected=list(LANES), actual=lane,
                    )],
                })
                continue
            if not isinstance(value, list):
                lane_provenance = _provenance(
                    path, return_index, talk_filename, talk_id, lane=lane,
                )
                self.entries["invalid"].append({
                    "provenance": lane_provenance,
                    "feedback": value,
                    "issues": [_issue(
                        "feedback_lane_not_array",
                        "each feedback lane must be an array",
                        actual=type(value).__name__,
                    )],
                })
                continue
            for entry_index, entry in enumerate(value):
                self._consume_entry(
                    path, return_index, talk_filename, talk_id,
                    lane, entry_index, entry,
                )

        status = (
            "invalid" if len(self.entries["invalid"]) > invalid_before
            else "accepted"
        )
        target = self.returns[status]
        if status == "accepted":
            target.append({"provenance": provenance})
        else:
            target.append({
                "provenance": provenance,
                "issues": [_issue(
                    "feedback_entries_invalid",
                    "one or more feedback lanes/entries are invalid",
                )],
            })

    def _consume_entry(
        self,
        path: Path,
        return_index: int,
        talk_filename: str | None,
        talk_id: str | None,
        lane: str,
        entry_index: int,
        entry: Any,
    ) -> None:
        provenance = _provenance(
            path, return_index, talk_filename, talk_id,
            lane=lane, entry_index=entry_index,
        )
        validation = validate_entry(lane, entry, self.registry)
        if validation["errors"]:
            self.entries["invalid"].append({
                "provenance": provenance,
                "feedback": entry,
                "issues": validation["errors"],
            })
            return
        for warning in validation["warnings"]:
            self.warnings.append({"provenance": provenance, **warning})
        references = [
            {
                "catalog_id": catalog_id,
                "polarity": self.registry[catalog_id]["polarity"],
            }
            for catalog_id in validation["catalog_ids"]
            if catalog_id in self.registry
        ]
        self.entries["accepted"].append({
            "provenance": provenance,
            "feedback": entry,
            "catalog_references": references,
            "suggestion": validation["suggestion"],
        })

    def _exact_catalog_groups(self) -> list[dict[str, Any]]:
        groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for accepted in self.entries["accepted"]:
            provenance = accepted["provenance"]
            for reference in accepted["catalog_references"]:
                groups[reference["catalog_id"]].append(provenance)
        result = []
        for catalog_id, occurrences in groups.items():
            lane_counts = Counter(item["feedback_lane"] for item in occurrences)
            result.append({
                "catalog_id": catalog_id,
                "polarity": self.registry[catalog_id]["polarity"],
                "catalog_path": self.registry[catalog_id]["path"],
                "occurrence_count": len(occurrences),
                "talk_count": len({_talk_key(item) for item in occurrences}),
                "source_return_count": len({
                    _source_return_key(item) for item in occurrences
                }),
                "lane_counts": dict(sorted(lane_counts.items())),
                "occurrences": sorted(occurrences, key=provenance_sort_key),
            })
        return sorted(
            result,
            key=lambda item: (-item["talk_count"], -item["occurrence_count"], item["catalog_id"]),
        )

    def _suggestion_groups(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        conflicts: list[dict[str, Any]] = []
        for accepted in self.entries["accepted"]:
            suggestion = accepted["suggestion"]
            if suggestion is None:
                continue
            groups[suggestion["normalized_suggestion"]].append({
                "provenance": accepted["provenance"],
                "proposed_name": suggestion["proposed_name"],
                "proposed_polarity": suggestion["proposed_polarity"],
            })

        result = []
        for normalized, occurrences in groups.items():
            explicit = sorted({
                item["proposed_polarity"] for item in occurrences
                if item["proposed_polarity"] != "unspecified"
            })
            unspecified = sum(
                item["proposed_polarity"] == "unspecified" for item in occurrences
            )
            if len(explicit) > 1:
                polarity_status = "conflict"
                conflicts.append(_issue(
                    "suggestion_polarity_conflict",
                    "normalized suggestion is asserted as both pattern and antipattern",
                    normalized_suggestion=normalized,
                    asserted_polarities=explicit,
                ))
            elif explicit and unspecified:
                polarity_status = "partial"
            elif explicit:
                polarity_status = "consistent"
            else:
                polarity_status = "unspecified"
            talks = {_talk_key(item["provenance"]) for item in occurrences}
            source_returns = {
                _source_return_key(item["provenance"]) for item in occurrences
            }
            variants = Counter(item["proposed_name"] for item in occurrences)
            result.append({
                "normalized_suggestion": normalized,
                "occurrence_count": len(occurrences),
                "talk_count": len(talks),
                "source_return_count": len(source_returns),
                "variants": [
                    {"value": value, "count": count}
                    for value, count in sorted(variants.items())
                ],
                "asserted_polarities": explicit,
                "unspecified_polarity_count": unspecified,
                "polarity_status": polarity_status,
                "occurrences": sorted(
                    occurrences,
                    key=lambda item: provenance_sort_key(item["provenance"]),
                ),
            })
        return (
            sorted(
                result,
                key=lambda item: (
                    -item["talk_count"], -item["occurrence_count"],
                    item["normalized_suggestion"],
                ),
            ),
            conflicts,
        )

    def report(self, requested_inputs: list[str], discovery: dict[str, Any]) -> dict[str, Any]:
        suggestions, suggestion_conflicts = self._suggestion_groups()
        catalog_groups = self._exact_catalog_groups()
        lane_summary = {}
        for lane in LANES:
            lane_entries = [
                item for item in self.entries["accepted"]
                if item["provenance"]["feedback_lane"] == lane
            ]
            invalid_lane_entries = [
                item for item in self.entries["invalid"]
                if item["provenance"]["feedback_lane"] == lane
            ]
            lane_summary[lane] = {
                "accepted_entry_count": len(lane_entries),
                "invalid_entry_count": len(invalid_lane_entries),
                "talk_count": len({
                    _talk_key(item["provenance"]) for item in lane_entries
                }),
                "source_return_count": len({
                    _source_return_key(item["provenance"]) for item in lane_entries
                }),
            }

        for classification in self.inputs:
            self.inputs[classification].sort(key=lambda item: item["path"])
        for classification in self.returns:
            self.returns[classification].sort(
                key=lambda item: provenance_sort_key(item["provenance"])
            )
        for classification in self.entries:
            self.entries[classification].sort(
                key=lambda item: provenance_sort_key(item["provenance"])
            )
        warnings = sorted(
            [*self.warnings, *discovery["warnings"]], key=issue_sort_key
        )
        validation_errors = sorted(
            [*self.validation_errors, *suggestion_conflicts], key=issue_sort_key
        )
        catalog_errors = sorted(self.catalog["errors"], key=issue_sort_key)
        invalid_count = (
            len(self.inputs["invalid"])
            + len(self.entries["invalid"])
            + len(catalog_errors)
            + len(validation_errors)
        )
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "ok": invalid_count == 0,
            "read_only": True,
            "requested_inputs": sorted(str(Path(value).expanduser().resolve(strict=False)) for value in requested_inputs),
            "catalog": {
                "path": self.catalog["path"],
                "id_count": len(self.registry),
                "pattern_count": sum(
                    item["polarity"] == "pattern" for item in self.registry.values()
                ),
                "antipattern_count": sum(
                    item["polarity"] == "antipattern" for item in self.registry.values()
                ),
                "errors": catalog_errors,
            },
            "input_summary": {
                key: len(self.inputs[key]) for key in ("accepted", "rejected", "invalid")
            },
            "inputs": self.inputs,
            "return_summary": {
                key: len(self.returns[key]) for key in ("accepted", "rejected", "invalid")
            },
            "returns": self.returns,
            "entry_summary": {
                "accepted": len(self.entries["accepted"]),
                "invalid": len(self.entries["invalid"]),
                "warnings": len(warnings),
            },
            "lane_summary": lane_summary,
            "exact_catalog_ids": catalog_groups,
            "normalized_suggestions": suggestions,
            "entries": self.entries,
            "validation": {
                "errors": validation_errors,
                "warnings": warnings,
            },
        }


def provenance_sort_key(provenance: dict[str, Any]) -> tuple[Any, ...]:
    return (
        provenance.get("source_path") or "",
        provenance.get("source_return_index", -1),
        provenance.get("talk_filename") or "",
        provenance.get("talk_id") or "",
        provenance.get("feedback_lane") or "",
        provenance.get("feedback_entry_index")
        if provenance.get("feedback_entry_index") is not None else -1,
    )


def issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str]:
    provenance = issue.get("provenance") or {}
    return (
        issue.get("code") or "",
        str(provenance_sort_key(provenance)),
        issue.get("message") or "",
    )


def aggregate_feedback(
    inputs: list[str | Path],
    *,
    catalog_path: str | Path | None = None,
) -> dict[str, Any]:
    """Aggregate concrete inputs and return the stable, read-only report."""
    requested = [str(value) for value in inputs]
    catalog = load_catalog(catalog_path or default_catalog_path())
    discovery = discover_inputs(inputs)
    aggregator = FeedbackAggregator(catalog)
    if not inputs:
        aggregator.validation_errors.append(_issue(
            "inputs_missing", "at least one return file or directory is required",
        ))
    for immediate in discovery["immediate"]:
        aggregator.inputs[immediate["status"]].append(immediate)
    for discovered in discovery["files"]:
        aggregator.consume_file(discovered["path"], discovered["discovered_from"])
    return aggregator.report(requested, discovery)


def _argument_error_report() -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": False,
        "read_only": True,
        "error": {
            "code": "invalid_arguments",
            "message": "expected one or more return files/directories",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "inputs", nargs="+", help="return JSON files or directories",
    )
    parser.add_argument(
        "--catalog", default=None,
        help="pattern catalog directory (defaults to the bundled catalog)",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code:
            print(json.dumps(_argument_error_report(), indent=2, sort_keys=True))
        raise

    report = aggregate_feedback(args.inputs, catalog_path=args.catalog)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

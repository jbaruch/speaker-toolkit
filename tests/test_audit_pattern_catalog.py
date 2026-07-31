"""Outcome tests for the read-only Presentation Patterns catalog auditor."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _base_entries() -> list[dict]:
    return [
        {
            "id": "clear-path",
            "name": "Clear Path",
            "type": "pattern",
            "part": "build",
            "phase_relevance": ["content"],
            "vault_dimensions": [2],
            "related_patterns": ["blocked-path"],
            "inverse_of": ["blocked-path"],
        },
        {
            "id": "blocked-path",
            "name": "Blocked Path",
            "type": "antipattern",
            "part": "build",
            "phase_relevance": ["guardrails"],
            "vault_dimensions": [14],
            "related_patterns": ["clear-path"],
            "inverse_of": ["clear-path"],
        },
    ]


def _scoring(entry_type: str) -> str:
    if entry_type == "antipattern":
        return """## Scoring Criteria
- Strong signal (2 pts — antipattern present): repeated harmful behavior
- Moderate signal (1 pt): one limited harmful instance
- Absent (0 pts — antipattern not present): no harmful behavior
"""
    return """## Scoring Criteria
- Strong signal (2 pts): repeated effective behavior
- Moderate signal (1 pt): one limited effective instance
- Absent (0 pts): no effective behavior
"""


def _metadata(entry: dict) -> dict:
    return {
        key: copy.deepcopy(value)
        for key, value in entry.items()
        if not key.startswith("_")
    }


def _write_catalog(
    tmp_path: Path,
    entries: list[dict] | None = None,
    *,
    unobservable_ids: set[str] | None = None,
    extra_index_rows: list[dict] | None = None,
) -> Path:
    root = tmp_path / "patterns"
    root.mkdir()
    values = copy.deepcopy(entries or _base_entries())
    for entry in values:
        directory = entry.get("_directory", entry["part"])
        target_dir = root / directory
        target_dir.mkdir(exist_ok=True)
        default_name = (
            f"_anti_{entry['id']}.md"
            if entry["type"] == "antipattern"
            else f"{entry['id']}.md"
        )
        filename = entry.get("_filename", default_name)
        if entry.get("_raw_text") is not None:
            text = entry["_raw_text"]
        else:
            frontmatter = yaml.safe_dump(
                _metadata(entry),
                sort_keys=False,
                allow_unicode=True,
            )
            scoring = entry.get("_scoring", _scoring(entry["type"]))
            evidence = ""
            gate_fields = {
                "evaluable_from", "evidence_requirements", "not_evaluable_when"}
            has_gate = gate_fields <= set(entry)
            if entry.get("_evidence_section", has_gate):
                evidence = "\n## Evidence Gate\nNamed sources must satisfy the gate.\n"
            text = f"---\n{frontmatter}---\n\n# {entry['name']}\n\n{scoring}{evidence}"
        (target_dir / filename).write_text(text, encoding="utf-8")

    rows = [entry for entry in values if entry.get("_in_index", True)]
    rows.extend(copy.deepcopy(extra_index_rows or []))
    lines = ["# Test Catalog", "", "## Pattern Catalog", ""]
    for part, label in (("prepare", "Prepare"), ("build", "Build"), ("deliver", "Deliver")):
        part_rows = [
            entry for entry in rows
            if entry.get("_index_part", entry["part"]) == part
        ]
        lines.extend([
            f"### {label} Phase",
            "",
            "| ID | Name | Type | Vault Dims | Creator Phases | Related |",
            "|----|------|------|------------|----------------|---------|",
        ])
        for entry in part_rows:
            dimensions = entry.get("_index_dimensions", entry["vault_dimensions"])
            phases = entry.get("_index_phases", entry["phase_relevance"])
            related = entry.get("_index_related", entry["related_patterns"])
            lines.append(
                "| "
                + " | ".join([
                    entry["id"],
                    entry.get("_index_name", entry["name"]),
                    entry.get("_index_type", entry["type"]),
                    ", ".join(str(value) for value in dimensions) or "—",
                    ", ".join(phases) or "—",
                    ", ".join(related) or "—",
                ])
                + " |"
            )
        lines.append("")

    if unobservable_ids is None:
        listed = {
            entry["id"] for entry in values
            if entry.get("observable") is False
        }
    else:
        listed = unobservable_ids
    lines.extend([
        "## Phase-Grouped Lookup Table",
        "",
        "## Unobservable Patterns — Go-Live Checklist",
        "",
        "| ID | Name | Action |",
        "|----|------|--------|",
    ])
    names = {entry["id"]: entry["name"] for entry in values}
    for pattern_id in sorted(listed):
        lines.append(f"| {pattern_id} | {names.get(pattern_id, pattern_id)} | Review |")
    lines.extend(["", "## Summary Statistics", ""])
    (root / "_index.md").write_text("\n".join(lines), encoding="utf-8")
    return root


def _codes(report: dict, lane: str = "errors") -> set[str]:
    return {issue["code"] for issue in report[lane]}


def test_valid_catalog_emits_graph_and_stable_report(tmp_path, audit_pattern_catalog):
    root = _write_catalog(tmp_path)
    first = audit_pattern_catalog.audit_catalog(root)
    second = audit_pattern_catalog.audit_catalog(root)

    assert first == second
    assert first["valid"] is True
    assert first["errors"] == []
    assert first["semantic_debts"] == []
    assert first["summary"]["entries_loaded"] == 2
    assert first["graph"]["inverse_declarations"] == [
        ["blocked-path", "clear-path"],
        ["clear-path", "blocked-path"],
    ]
    assert len(first["catalog"]["fingerprint"]) == 64


def test_bundled_catalog_passes_structural_contract(audit_pattern_catalog):
    report = audit_pattern_catalog.audit_catalog()

    assert report["valid"] is True
    assert report["summary"]["entries_loaded"] == 111
    assert report["summary"]["patterns"] == 83
    assert report["summary"]["antipatterns"] == 28
    assert report["summary"]["observable"] == 99
    assert report["summary"]["unobservable"] == 12


def test_bundled_catalog_has_no_phase_or_inverse_polarity_debt(
    audit_pattern_catalog,
):
    report = audit_pattern_catalog.audit_catalog()

    assert {
        "index_phases_drift",
        "inverse_same_polarity",
    }.isdisjoint(_codes(report, "semantic_debts"))


def test_audit_does_not_modify_catalog(tmp_path, audit_pattern_catalog):
    root = _write_catalog(tmp_path)
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }

    audit_pattern_catalog.audit_catalog(root)

    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_nested_reserved_index_file_cannot_evade_audit_or_fingerprint(
    tmp_path,
    audit_pattern_catalog,
):
    root = _write_catalog(tmp_path)
    before = audit_pattern_catalog.audit_catalog(root)
    (root / "build" / "_index.md").write_text(
        "# A nested file that is not the catalog index\n",
        encoding="utf-8",
    )

    after = audit_pattern_catalog.audit_catalog(root)

    assert after["valid"] is False
    assert "frontmatter_missing" in _codes(after)
    assert after["summary"]["entry_files"] == 3
    assert after["catalog"]["fingerprint"] != before["catalog"]["fingerprint"]


def test_missing_catalog_directory_is_json_report(audit_pattern_catalog, tmp_path):
    report = audit_pattern_catalog.audit_catalog(tmp_path / "missing")

    assert report["valid"] is False
    assert _codes(report) == {"catalog_directory_missing"}


def test_empty_catalog_is_invalid(tmp_path, audit_pattern_catalog):
    root = tmp_path / "patterns"
    root.mkdir()
    (root / "_index.md").write_text(
        "# Empty\n\n## Pattern Catalog\n\n## Unobservable Patterns\n",
        encoding="utf-8",
    )

    report = audit_pattern_catalog.audit_catalog(root)

    assert "catalog_empty" in _codes(report)


def test_index_and_file_inventories_must_match(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["_in_index"] = False
    root = _write_catalog(
        tmp_path,
        entries,
        extra_index_rows=[{
            "id": "ghost-path",
            "name": "Ghost Path",
            "type": "pattern",
            "part": "build",
            "phase_relevance": ["content"],
            "vault_dimensions": [2],
            "related_patterns": [],
            "inverse_of": [],
        }],
    )

    report = audit_pattern_catalog.audit_catalog(root)

    assert {"index_entry_missing", "index_entry_orphaned"} <= _codes(report)


def test_duplicate_ids_are_rejected(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    duplicate = copy.deepcopy(entries[0])
    duplicate["_filename"] = "duplicate-clear.md"
    duplicate["_in_index"] = False
    entries.append(duplicate)

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "id_duplicate" in _codes(report)


def test_filename_must_encode_frontmatter_id(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["_filename"] = "different-path.md"

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "filename_id_mismatch" in _codes(report)


def test_reserved_anti_prefix_must_match_type(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["_filename"] = "_anti_clear-path.md"

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "filename_type_mismatch" in _codes(report)


def test_anti_word_without_reserved_prefix_remains_pattern(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries.append({
        "id": "anti-sell",
        "name": "Anti-Sell",
        "type": "pattern",
        "part": "deliver",
        "phase_relevance": ["content"],
        "vault_dimensions": [6],
        "related_patterns": [],
        "inverse_of": [],
    })

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert report["valid"] is True


def test_directory_and_part_must_agree(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["part"] = "prepare"
    entries[0]["_directory"] = "build"

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "directory_part_mismatch" in _codes(report)


def test_creator_phase_namespace_is_closed(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["phase_relevance"] = ["rehearsal"]
    entries[0]["_index_phases"] = ["content"]

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "creator_phase_invalid" in _codes(report)


def test_source_gate_requires_all_fields(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["evaluable_from"] = ["delivery_video"]

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "source_gate_partial" in _codes(report)


def test_source_gate_rejects_unknown_source(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0].update({
        "evaluable_from": ["speaker_memory"],
        "evidence_requirements": ["The event is visible."],
        "not_evaluable_when": ["The event is hidden."],
    })

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "evidence_source_invalid" in _codes(report)


def test_source_gate_accepts_conjunctive_alternatives(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0].update({
        "evaluable_from": [
            "delivery_video",
            ["static_slides", "transcript"],
            ["native_deck", "transcript"],
        ],
        "evidence_requirements": ["The compared facts are visible."],
        "not_evaluable_when": ["The required pair is unavailable."],
    })

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert report["valid"] is True


@pytest.mark.parametrize("alternatives", [
    [["delivery_video"]],
    [["transcript", "transcript"]],
    [["source_comparison", "transcript"]],
    [["static_slides", "speaker_memory"]],
    ["delivery_video", "delivery_video"],
])
def test_source_gate_rejects_invalid_alternatives(
    tmp_path,
    audit_pattern_catalog,
    alternatives,
):
    entries = _base_entries()
    entries[0].update({
        "evaluable_from": alternatives,
        "evidence_requirements": ["The compared facts are visible."],
        "not_evaluable_when": ["The required pair is unavailable."],
    })

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "evidence_source_invalid" in _codes(report)


def test_unobservable_entry_cannot_have_source_gate(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0].update({
        "observable": False,
        "evaluable_from": ["delivery_video"],
        "evidence_requirements": ["The event is visible."],
        "not_evaluable_when": ["The event is hidden."],
    })

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "unobservable_source_gate_conflict" in _codes(report)


def test_source_gate_metadata_requires_matching_prose(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0].update({
        "evaluable_from": ["delivery_video"],
        "evidence_requirements": ["The event is visible."],
        "not_evaluable_when": ["The event is hidden."],
        "_evidence_section": False,
    })

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "source_gate_prose_missing" in _codes(report)


def test_source_gate_prose_requires_matching_metadata(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["_evidence_section"] = True

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "source_gate_metadata_missing" in _codes(report)


def test_inline_evidence_gate_phrase_is_not_a_section(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0].update({
        "evaluable_from": ["delivery_video"],
        "evidence_requirements": ["The event is visible."],
        "not_evaluable_when": ["The event is hidden."],
        "_evidence_section": False,
        "_scoring": _scoring("pattern")
        + "\nProse may mention ## Evidence Gate without creating one.\n",
    })

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "source_gate_prose_missing" in _codes(report)


def test_fenced_evidence_gate_is_not_a_section(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0].update({
        "evaluable_from": ["delivery_video"],
        "evidence_requirements": ["The event is visible."],
        "not_evaluable_when": ["The event is hidden."],
        "_evidence_section": False,
        "_scoring": _scoring("pattern")
        + "\n```markdown\n## Evidence Gate\nOnly a code example.\n```\n",
    })

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "source_gate_prose_missing" in _codes(report)


def test_unobservable_index_and_frontmatter_must_match(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["observable"] = False

    report = audit_pattern_catalog.audit_catalog(
        _write_catalog(tmp_path, entries, unobservable_ids=set())
    )

    assert "index_unobservable_missing" in _codes(report)


def test_related_and_inverse_references_must_resolve(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["related_patterns"] = ["missing-related"]
    entries[0]["inverse_of"] = ["missing-inverse"]
    entries[0]["_index_related"] = []

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    dangling = [
        issue for issue in report["errors"]
        if issue["code"] == "reference_dangling"
    ]
    assert {issue["related_id"] for issue in dangling} == {
        "missing-related", "missing-inverse"}


def test_index_related_references_must_resolve(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["_index_related"] = ["ghost-path"]

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "index_reference_dangling" in _codes(report)


def test_inverse_declarations_are_reciprocal(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[1]["inverse_of"] = []

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    issue = next(
        issue for issue in report["errors"]
        if issue["code"] == "inverse_not_reciprocal"
    )
    assert issue["entry_id"] == "clear-path"
    assert issue["related_id"] == "blocked-path"


def test_same_polarity_inverse_is_semantic_debt(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[1]["type"] = "pattern"
    entries[1]["phase_relevance"] = ["content"]

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert report["valid"] is True
    assert _codes(report, "semantic_debts") == {"inverse_same_polarity"}
    debts = [
        issue for issue in report["semantic_debts"]
        if issue["code"] == "inverse_same_polarity"
    ]
    assert len(debts) == 1
    assert {
        debts[0]["entry_id"], debts[0]["related_id"]
    } == {"blocked-path", "clear-path"}


def test_antipattern_scoring_uses_direct_polarity(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[1]["_scoring"] = """## Scoring Criteria
- Strong signal (2 pts): antipattern absent
- Moderate signal (1 pt): mixed
- Absent (0 pts): antipattern present
"""

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "antipattern_scoring_polarity_inverted" in _codes(report)


def test_scoring_scale_must_have_all_three_labels(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["_scoring"] = """## Scoring Criteria
- Strong signal (2 pts): effective
- Absent (0 pts): absent
"""

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "scoring_label_count_invalid" in _codes(report)


def test_inline_scoring_phrase_is_not_a_section(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["_scoring"] = """This names ## Scoring Criteria without a heading.
- Strong signal (2 pts): effective
- Moderate signal (1 pt): mixed
- Absent (0 pts): absent
"""

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "scoring_section_missing" in _codes(report)


def test_fenced_scoring_criteria_are_not_a_section(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0]["_scoring"] = (
        "```markdown\n"
        + _scoring("pattern")
        + "```\n"
    )

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "scoring_section_missing" in _codes(report)


def test_fenced_scoring_labels_do_not_duplicate_visible_scale(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0]["_scoring"] = (
        _scoring("pattern")
        + "\n~~~markdown\n"
        + _scoring("pattern")
        + "~~~\n"
    )

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "scoring_label_count_invalid" not in _codes(report)
    assert report["valid"] is True


def test_normalized_alias_collision_is_rejected(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["aliases"] = ["BLOCKED_path!"]

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    collision = next(
        issue for issue in report["errors"]
        if issue["code"] == "alias_collision"
    )
    assert collision["entry_id"] == "blocked-path"
    assert collision["related_id"] == "clear-path"


def test_duplicate_explicit_aliases_are_rejected(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["aliases"] = ["Side Door", "side-door!"]

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "alias_duplicate" in _codes(report)


def test_index_metadata_drift_is_separate_semantic_debt(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0].update({
        "_index_name": "Clear Route",
        "_index_dimensions": [3],
        "_index_phases": ["slides"],
        "_index_related": [],
    })

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert report["valid"] is True
    assert _codes(report, "semantic_debts") == {
        "index_name_drift",
        "index_dimensions_drift",
        "index_phases_drift",
        "index_related_drift",
    }


def test_index_type_and_part_disagreement_are_structural(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0]["_index_type"] = "antipattern"
    entries[0]["_index_part"] = "prepare"

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert {"index_type_mismatch", "index_part_mismatch"} <= _codes(report)


def test_index_name_must_be_nonempty(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["_index_name"] = ""

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "index_name_invalid" in _codes(report)
    assert report["valid"] is False


def test_index_related_cell_cannot_reference_its_own_id(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0]["_index_related"] = ["clear-path"]

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "index_reference_self" in _codes(report)
    assert report["valid"] is False


def test_fenced_catalog_table_does_not_supply_index_inventory(
    tmp_path,
    audit_pattern_catalog,
):
    root = _write_catalog(tmp_path)
    index = root / "_index.md"
    text = index.read_text(encoding="utf-8")
    text = text.replace(
        "## Pattern Catalog",
        "```markdown\n## Pattern Catalog",
        1,
    ).replace(
        "## Phase-Grouped Lookup Table",
        "```\n\n## Phase-Grouped Lookup Table",
        1,
    )
    index.write_text(text, encoding="utf-8")

    report = audit_pattern_catalog.audit_catalog(root)

    assert "index_entry_missing" in _codes(report)
    assert report["valid"] is False


def test_fenced_catalog_row_does_not_create_an_orphaned_index_entry(
    tmp_path,
    audit_pattern_catalog,
):
    root = _write_catalog(tmp_path)
    index = root / "_index.md"
    text = index.read_text(encoding="utf-8")
    fenced_row = (
        "~~~markdown\n"
        "| ghost-path | Ghost Path | pattern | 2 | content | — |\n"
        "~~~\n\n"
    )
    text = text.replace("### Build Phase", fenced_row + "### Build Phase", 1)
    index.write_text(text, encoding="utf-8")

    report = audit_pattern_catalog.audit_catalog(root)

    assert "index_entry_orphaned" not in _codes(report)
    assert report["valid"] is True


def test_fenced_unobservable_table_does_not_supply_checklist(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0]["observable"] = False
    root = _write_catalog(tmp_path, entries)
    index = root / "_index.md"
    text = index.read_text(encoding="utf-8")
    text = text.replace(
        "## Unobservable Patterns — Go-Live Checklist",
        "```markdown\n## Unobservable Patterns — Go-Live Checklist",
        1,
    ).replace(
        "## Summary Statistics",
        "```\n\n## Summary Statistics",
        1,
    )
    index.write_text(text, encoding="utf-8")

    report = audit_pattern_catalog.audit_catalog(root)

    assert {
        "index_unobservable_missing",
        "index_unobservable_section_missing",
    } <= _codes(report)
    assert report["valid"] is False


def test_fenced_unobservable_row_does_not_create_a_checklist_entry(
    tmp_path,
    audit_pattern_catalog,
):
    root = _write_catalog(tmp_path)
    index = root / "_index.md"
    text = index.read_text(encoding="utf-8")
    fenced_row = (
        "~~~markdown\n"
        "| clear-path | Clear Path | Review |\n"
        "~~~\n"
    )
    text = text.replace("## Summary Statistics", fenced_row + "\n## Summary Statistics", 1)
    index.write_text(text, encoding="utf-8")

    report = audit_pattern_catalog.audit_catalog(root)

    assert "index_unobservable_mismatch" not in _codes(report)
    assert report["valid"] is True


@pytest.mark.parametrize(("field", "value", "code"), [
    ("_index_dimensions", [2, 2], "index_dimensions_duplicate"),
    ("_index_dimensions", [0], "index_dimensions_invalid"),
    ("_index_phases", ["content", "content"], "index_creator_phases_duplicate"),
    ("_index_phases", ["rehearsal"], "index_creator_phases_invalid"),
    ("_index_related", ["blocked-path", "blocked-path"], "index_related_duplicate"),
])
def test_index_list_shape_is_validated_independently_of_set_drift(
    tmp_path,
    audit_pattern_catalog,
    field,
    value,
    code,
):
    entries = _base_entries()
    entries[0][field] = value

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert code in _codes(report)
    assert report["valid"] is False


def test_unobservable_checklist_rejects_duplicate_ids(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[0]["observable"] = False
    root = _write_catalog(tmp_path, entries)
    index = root / "_index.md"
    text = index.read_text(encoding="utf-8")
    row = "| clear-path | Clear Path | Review |"
    index.write_text(text.replace(row, f"{row}\n{row}"), encoding="utf-8")

    report = audit_pattern_catalog.audit_catalog(root)

    assert "index_unobservable_duplicate" in _codes(report)


def test_invalid_yaml_is_reported_without_crashing(tmp_path, audit_pattern_catalog):
    entries = _base_entries()
    entries[0]["_raw_text"] = "---\nid: [unterminated\n---\n"

    report = audit_pattern_catalog.audit_catalog(_write_catalog(tmp_path, entries))

    assert "frontmatter_invalid_yaml" in _codes(report)


def test_cli_emits_json_and_nonzero_for_invalid_catalog(
    tmp_path,
    audit_pattern_catalog,
):
    entries = _base_entries()
    entries[1]["inverse_of"] = []
    root = _write_catalog(tmp_path, entries)

    completed = subprocess.run(
        [sys.executable, audit_pattern_catalog.__file__, "--catalog", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert report["valid"] is False
    assert "structural error" in completed.stderr


def test_cli_emits_stable_json_for_valid_catalog(tmp_path, audit_pattern_catalog):
    root = _write_catalog(tmp_path)
    command = [
        sys.executable,
        audit_pattern_catalog.__file__,
        "--catalog",
        str(root),
    ]

    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stdout == second.stdout
    assert first.stderr == ""
    assert json.loads(first.stdout)["valid"] is True

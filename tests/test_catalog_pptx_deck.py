"""Tests for catalog-pptx-deck.py, the owner path for a deck new to the catalog and
for a cataloged row's fresh receipt."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from conftest import CURRENT_ROOT_SCHEMA_VERSION as CURRENT_ROOT
from test_pptx_deck_facts import full_deck_members, write_deck

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "vault-ingress" / "scripts"
SCRIPT = SCRIPTS / "catalog-pptx-deck.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


catalog_deck = _load("catalog_pptx_deck", "catalog-pptx-deck.py")
mutate = _load("mutate_tracking_database_for_catalog", "mutate-tracking-database.py")

TALK = {
    "filename": "2025-01-17-voxxed-ticino-devops-developers.md",
    "title": "DevOps for Developers",
    "conference": "Voxxed Days Ticino",
    "date": "2025-01-17",
}
OTHER_TALK = {
    "filename": "2025-03-02-kubecon-europe-supply-chain.md",
    "title": "Securing the Software Supply Chain",
    "conference": "KubeCon Europe",
    "date": "2025-03-02",
}
DECK = "Voxxed Days Ticino/2025/DevOps for Developers.pptx"
UNRELATED_DECK = "Misc/Holiday Party Quiz.pptx"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    return root


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "Presentations"
    root.mkdir()
    return root


def _deck(
    source_root: Path, relative: str = DECK, *, title: str = TALK["title"]
) -> str:
    write_deck(
        source_root,
        relative,
        full_deck_members(slide_titles=[title], runs=[title], slides=42),
    )
    return relative


def _result(source_root: Path, relative: str, **overrides: Any) -> dict[str, Any]:
    """One deck's extraction result, as pptx-extraction.py reports it."""
    content = (source_root / relative).read_bytes()
    return {
        "schema_version": 4,
        "pipeline_version": "1.5.0",
        "input_fingerprint": {
            "algorithm": "sha256",
            "digest": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        },
        "pptx_path": relative,
        "slide_count": 42,
        **overrides,
    }


def _write_extraction(
    tmp_path: Path, *results: dict[str, Any], **envelope: Any
) -> Path:
    path = tmp_path / "extraction.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "pptx_directory_batch",
                "complete": True,
                "incomplete_reason_codes": [],
                "results": list(results),
                "skipped": [],
                **envelope,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_database(
    vault: Path,
    source_root: Path,
    *,
    talks: list[dict[str, Any]] | None = None,
    catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    database = {
        "schema_version": CURRENT_ROOT,
        "config": {
            "schema_version": 3,
            "pptx_directory_exclusions": [],
            "pptx_source_dir": str(source_root),
        },
        "talks": [
            {**talk, "schema_version": 5, "status": "pending"}
            for talk in (talks if talks is not None else [TALK, OTHER_TALK])
        ],
        "pptx_catalog": catalog or [],
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }
    (vault / "tracking-database.json").write_text(
        json.dumps(database), encoding="utf-8"
    )
    return database


def _deck_entry(report: dict[str, Any], relative: str = DECK) -> dict[str, Any]:
    return {deck["pptx_path"]: deck for deck in report["decks"]}[relative]


def test_a_proven_deck_gets_a_plan_the_owner_writer_accepts(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    database = _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    report = catalog_deck.execute(vault, extraction=extraction)

    assert _deck_entry(report)["disposition"] == "bind"
    assert _deck_entry(report)["selected_talk_filename"] == TALK["filename"]
    mutations = report["mutation_plan"]["mutations"]
    assert len(mutations) == 1
    assert mutations[0]["expect"] == {"$missing": True}
    assert mutations[0]["expect_talk_pptx_path"] == {"$missing": True}

    candidate, _changes = mutate.build_candidate(database, mutations)

    record = candidate["pptx_catalog"][0]
    assert record["talk_filename"] == TALK["filename"]
    assert record["matched"] is True
    assert record["slide_count"] == 42
    assert record["visual_extracted"] is True
    assert record["visual_evidence"]["outcome"] == "succeeded"
    assert record["identity_assessment"]["verdict"] == "matched"
    assert "candidates_assessed" not in record["identity_assessment"]
    bound = {talk["filename"]: talk for talk in candidate["talks"]}[TALK["filename"]]
    assert bound["pptx_path"] == relative


def test_the_configured_speaker_name_keeps_a_rival_out_of_the_way(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    """The Universe deck's shape, through the command: a footer naming the speaker."""
    relative = "GitHub Universe/2026/Prototype/prototype-policy.pptx"
    title = "When a prototype becomes critical, does your GitHub policy know?"
    write_deck(
        source_root,
        relative,
        full_deck_members(
            slide_titles=[title], runs=[title, "Baruch Sadogursky"], slides=12
        ),
    )
    talks = [
        {
            "filename": "github-universe-2026-prototype-policy.md",
            "title": title,
            "conference": "GitHub Universe 2026",
            "date": "2026-10-29",
        },
        {
            "filename": "playlist-rival.md",
            "title": "Baruch Sadogursky on JFrog Xray",
            "conference": "",
            "date": "",
        },
    ]
    database = _write_database(vault, source_root, talks=talks)
    database["config"]["speaker_name"] = "Baruch Sadogursky"
    (vault / "tracking-database.json").write_text(
        json.dumps(database), encoding="utf-8"
    )
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    report = catalog_deck.execute(vault, extraction=extraction)

    entry = _deck_entry(report, relative)
    assert entry["disposition"] == "bind"
    assert entry["selected_talk_filename"] == talks[0]["filename"]


def test_a_talk_holding_a_null_deck_path_gets_an_expectation_the_writer_accepts(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    database = _write_database(
        vault, source_root, talks=[{**TALK, "pptx_path": None}, OTHER_TALK]
    )
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    mutations = catalog_deck.execute(vault, extraction=extraction)["mutation_plan"][
        "mutations"
    ]

    assert mutations[0]["expect_talk_pptx_path"] is None
    candidate, _changes = mutate.build_candidate(database, mutations)
    bound = {talk["filename"]: talk for talk in candidate["talks"]}[TALK["filename"]]
    assert bound["pptx_path"] == relative


def test_the_plan_is_exactly_the_envelope_the_writer_loads(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    plan = catalog_deck.execute(vault, extraction=extraction)["mutation_plan"]

    assert set(plan) == {"schema_version", "mutations"}
    assert plan["schema_version"] == 1


def test_the_receipt_names_an_artifact_that_verifies_on_disk(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    result = _result(source_root, relative)
    extraction = _write_extraction(tmp_path, result)

    report = catalog_deck.execute(vault, extraction=extraction)

    evidence = report["mutation_plan"]["mutations"][0]["record"]["visual_evidence"]
    assert evidence["extractor_schema_version"] == 4
    assert evidence["pipeline_version"] == "1.5.0"
    assert evidence["source_fingerprint"] == result["input_fingerprint"]
    artifact = vault / evidence["artifact"]["path"]
    assert (
        hashlib.sha256(artifact.read_bytes()).hexdigest()
        == evidence["artifact"]["sha256"]
    )
    assert json.loads(artifact.read_text(encoding="utf-8")) == result
    assert report["artifacts_written"] == [evidence["artifact"]["path"]]


def test_a_rerun_writes_nothing_new_and_plans_the_same(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    first = catalog_deck.execute(vault, extraction=extraction)
    second = catalog_deck.execute(vault, extraction=extraction)

    assert second["artifacts_written"] == []
    assert second["mutation_plan"] == first["mutation_plan"]


def test_a_dry_run_writes_no_artifact_and_never_the_database(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))
    before = (vault / "tracking-database.json").read_bytes()

    report = catalog_deck.execute(vault, extraction=extraction, dry_run=True)

    assert report["artifacts_written"] == []
    assert len(report["artifacts_planned"]) == 1
    assert not (vault / report["artifacts_planned"][0]).exists()
    assert (vault / "tracking-database.json").read_bytes() == before


def test_writing_the_artifact_still_leaves_the_database_alone(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))
    before = (vault / "tracking-database.json").read_bytes()

    catalog_deck.execute(vault, extraction=extraction)

    assert (vault / "tracking-database.json").read_bytes() == before


def test_a_deck_matching_no_talk_joins_the_catalog_unbound(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root, UNRELATED_DECK, title="Holiday Party Quiz")
    database = _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    report = catalog_deck.execute(vault, extraction=extraction)

    assert _deck_entry(report, relative)["disposition"] == "catalog_unbound"
    mutation = report["mutation_plan"]["mutations"][0]
    assert mutation["record"]["talk_filename"] is None
    assert mutation["record"]["matched"] is False
    assert mutation["record"]["identity_assessment"] is None
    assert "expect_talk_pptx_path" not in mutation
    candidate, _changes = mutate.build_candidate(database, [mutation])
    assert candidate["pptx_catalog"][0]["pptx_path"] == relative


def test_a_contested_identity_is_review_work_and_never_planned(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    """Two talks with one title and no venue or year to separate them."""
    relative = _deck(source_root, "Decks/DevOps for Developers.pptx")
    _write_database(
        vault,
        source_root,
        talks=[
            TALK,
            {
                **TALK,
                "filename": "2024-11-05-devoxx-belgium-devops-developers.md",
                "conference": "Devoxx Belgium",
                "date": "2024-11-05",
            },
        ],
    )
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    report = catalog_deck.execute(vault, extraction=extraction)

    entry = _deck_entry(report, relative)
    assert entry["disposition"] == "review_required"
    assert entry["reason_codes"]
    assert report["mutation_plan"]["mutations"] == []
    assert report["artifacts_planned"] == []


def test_a_refused_binding_is_held_for_review(
    tmp_path: Path, vault: Path, source_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever `binding_refusal` refuses, this refuses, with its reason."""
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))
    monkeypatch.setattr(
        catalog_deck,
        "binding_refusal",
        lambda *_a, **_k: "identity_non_delivery_artifact",
    )

    report = catalog_deck.execute(vault, extraction=extraction)

    entry = _deck_entry(report)
    assert entry["disposition"] == "review_required"
    assert entry["reason_codes"] == ["identity_non_delivery_artifact"]
    assert report["mutation_plan"]["mutations"] == []


def test_two_revisions_proving_one_talk_are_both_held(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    """The Universe folder's shape: every revision proves the same talk."""
    first = _deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers v2.pptx")
    second = _deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers v3.pptx")
    _write_database(vault, source_root)
    extraction = _write_extraction(
        tmp_path, _result(source_root, first), _result(source_root, second)
    )

    report = catalog_deck.execute(vault, extraction=extraction)

    for relative in (first, second):
        entry = _deck_entry(report, relative)
        assert entry["disposition"] == "review_required"
        assert entry["reason_codes"] == ["talk_contested_in_this_batch"]
    assert report["mutation_plan"]["mutations"] == []


def test_naming_the_delivered_revision_with_deck_binds_only_it(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    first = _deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers v2.pptx")
    second = _deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers v3.pptx")
    _write_database(vault, source_root)
    extraction = _write_extraction(
        tmp_path, _result(source_root, first), _result(source_root, second)
    )

    report = catalog_deck.execute(vault, extraction=extraction, selected_decks=[second])

    assert [deck["pptx_path"] for deck in report["decks"]] == [second]
    assert report["decks"][0]["disposition"] == "bind"


@pytest.mark.parametrize("bound_by", ["talk-record", "catalog-row"])
def test_a_talk_that_already_has_a_deck_isnt_silently_rebound(
    tmp_path: Path, vault: Path, source_root: Path, bound_by: str
) -> None:
    relative = _deck(source_root)
    talks = [TALK, OTHER_TALK]
    catalog: list[dict[str, Any]] = []
    if bound_by == "talk-record":
        talks = [{**TALK, "pptx_path": "Elsewhere/older.pptx"}, OTHER_TALK]
    else:
        catalog = [
            {
                "schema_version": 1,
                "pptx_path": "Elsewhere/older.pptx",
                "talk_filename": TALK["filename"],
                "matched": True,
                "slide_count": 10,
                "visual_extracted": False,
            }
        ]
    _write_database(vault, source_root, talks=talks, catalog=catalog)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    report = catalog_deck.execute(vault, extraction=extraction)

    assert _deck_entry(report)["disposition"] == "review_required"
    assert _deck_entry(report)["reason_codes"] == ["talk_already_bound_to_another_deck"]
    assert report["mutation_plan"]["mutations"] == []


def _store(vault: Path, database: dict[str, Any]) -> None:
    (vault / "tracking-database.json").write_text(
        json.dumps(database), encoding="utf-8"
    )


def _cataloged_current(
    tmp_path: Path, vault: Path, source_root: Path, relative: str
) -> dict[str, Any]:
    """Catalog a deck through this command and the owner writer: a current row."""
    database = _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))
    plan = catalog_deck.execute(vault, extraction=extraction)["mutation_plan"]
    candidate, _changes = mutate.build_candidate(database, plan["mutations"])
    _store(vault, candidate)
    return candidate


def _legacy_row(
    relative: str = DECK,
    *,
    talk: dict[str, Any] | None = TALK,
    visual_extracted: bool,
) -> dict[str, Any]:
    """A v1 catalog row, as rows bound before any receipt or assessment look."""
    return {
        "schema_version": 1,
        "pptx_path": relative,
        "talk_filename": talk["filename"] if talk is not None else None,
        "matched": talk is not None,
        "slide_count": 10,
        "visual_extracted": visual_extracted,
    }


def _needs_extraction_fixture(
    tmp_path: Path, vault: Path, source_root: Path, evidence: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A bound row whose evidence the classifier reports `needs_extraction`.

    Returns the stored database and the extraction result of the deck as it is now.
    """
    relative = _deck(source_root)
    if evidence == "stale":
        _cataloged_current(tmp_path, vault, source_root, relative)
        write_deck(
            source_root,
            relative,
            full_deck_members(
                slide_titles=[TALK["title"]], runs=[TALK["title"]], slides=43
            ),
        )
        database = json.loads(
            (vault / "tracking-database.json").read_text(encoding="utf-8")
        )
        return database, _result(source_root, relative, slide_count=43)
    database = _write_database(
        vault,
        source_root,
        talks=[{**TALK, "pptx_path": relative}, OTHER_TALK],
        catalog=[_legacy_row(relative, visual_extracted=evidence == "unknown_legacy")],
    )
    return database, _result(source_root, relative)


@pytest.mark.parametrize("evidence", ["stale", "unknown_legacy", "pending"])
def test_a_cataloged_row_needing_extraction_gets_a_fresh_receipt(
    tmp_path: Path, vault: Path, source_root: Path, evidence: str
) -> None:
    database, result = _needs_extraction_fixture(tmp_path, vault, source_root, evidence)
    extraction = _write_extraction(tmp_path, result)

    report = catalog_deck.execute(vault, extraction=extraction)

    assert _deck_entry(report)["disposition"] == "refresh"
    mutations = report["mutation_plan"]["mutations"]
    assert len(mutations) == 1
    evidence_receipt = mutations[0]["record"]["visual_evidence"]
    artifact = vault / evidence_receipt["artifact"]["path"]
    assert json.loads(artifact.read_text(encoding="utf-8")) == result

    candidate, _changes = mutate.build_candidate(database, mutations)

    record = candidate["pptx_catalog"][0]
    assert len(candidate["pptx_catalog"]) == 1
    assert record["talk_filename"] == TALK["filename"]
    assert record["slide_count"] == result["slide_count"]
    assert record["visual_evidence"] == evidence_receipt
    assert (
        record["visual_evidence"]["source_fingerprint"] == result["input_fingerprint"]
    )
    assert record["identity_assessment"]["verdict"] == "matched"
    assert (
        record["identity_assessment"]["source_identity"] == result["input_fingerprint"]
    )
    bound = {talk["filename"]: talk for talk in candidate["talks"]}[TALK["filename"]]
    assert bound["pptx_path"] == DECK

    _store(vault, candidate)
    rerun = catalog_deck.execute(vault, extraction=extraction, selected_decks=[DECK])
    assert rerun["decks"][0]["disposition"] == "already_cataloged"
    assert rerun["mutation_plan"]["mutations"] == []


def test_a_current_cataloged_row_is_left_alone(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _cataloged_current(tmp_path, vault, source_root, relative)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    unselected = catalog_deck.execute(vault, extraction=extraction)
    selected = catalog_deck.execute(
        vault, extraction=extraction, selected_decks=[relative]
    )

    assert unselected["decks"] == []
    assert unselected["mutation_plan"]["mutations"] == []
    assert selected["decks"][0]["disposition"] == "already_cataloged"
    assert selected["mutation_plan"]["mutations"] == []
    assert selected["artifacts_planned"] == []


@pytest.mark.parametrize(
    "change",
    ["slide_count", "binding_severed"],
)
def test_a_refresh_is_refused_when_the_row_changed_underneath_it(
    tmp_path: Path, vault: Path, source_root: Path, change: str
) -> None:
    database, result = _needs_extraction_fixture(
        tmp_path, vault, source_root, "unknown_legacy"
    )
    extraction = _write_extraction(tmp_path, result)
    mutations = catalog_deck.execute(vault, extraction=extraction)["mutation_plan"][
        "mutations"
    ]
    row = database["pptx_catalog"][0]
    if change == "slide_count":
        row["slide_count"] = 11
    else:
        row.update(talk_filename=None, matched=False)

    with pytest.raises(mutate.TrackingDatabaseMutationError, match="precondition"):
        mutate.build_candidate(database, mutations)


def test_refreshing_an_unbound_row_never_binds_it(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    """The deck proves TALK, but binding a cataloged deck is not a receipt refresh."""
    relative = _deck(source_root)
    database = _write_database(
        vault,
        source_root,
        catalog=[_legacy_row(relative, talk=None, visual_extracted=True)],
    )
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    report = catalog_deck.execute(vault, extraction=extraction)

    assert _deck_entry(report)["disposition"] == "refresh"
    mutation = report["mutation_plan"]["mutations"][0]
    assert "expect_talk_pptx_path" not in mutation
    candidate, _changes = mutate.build_candidate(database, [mutation])
    record = candidate["pptx_catalog"][0]
    assert record["talk_filename"] is None
    assert record["identity_assessment"] is None
    assert record["visual_extracted"] is True
    assert all("pptx_path" not in talk for talk in candidate["talks"])


def test_a_refresh_the_fresh_assessment_contradicts_is_held(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    """The row binds OTHER_TALK, but the deck proves TALK: the sweep's call."""
    relative = _deck(source_root)
    _write_database(
        vault,
        source_root,
        catalog=[_legacy_row(relative, talk=OTHER_TALK, visual_extracted=True)],
    )
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    report = catalog_deck.execute(vault, extraction=extraction)

    entry = _deck_entry(report)
    assert entry["disposition"] == "review_required"
    assert entry["reason_codes"] == ["stored_binding_not_proven"]
    assert report["mutation_plan"]["mutations"] == []
    assert report["artifacts_planned"] == []


@pytest.mark.parametrize("claimed_by", ["talk-record", "catalog-row"])
def test_a_refresh_wont_move_a_talk_another_deck_holds(
    tmp_path: Path, vault: Path, source_root: Path, claimed_by: str
) -> None:
    relative = _deck(source_root)
    talks = [{**TALK, "pptx_path": relative}, OTHER_TALK]
    catalog = [_legacy_row(relative, visual_extracted=True)]
    if claimed_by == "talk-record":
        talks[0] = {**TALK, "pptx_path": "Elsewhere/older.pptx"}
    else:
        catalog.append(_legacy_row("Elsewhere/older.pptx", visual_extracted=False))
    _write_database(vault, source_root, talks=talks, catalog=catalog)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    report = catalog_deck.execute(vault, extraction=extraction)

    entry = _deck_entry(report)
    assert entry["disposition"] == "review_required"
    assert entry["reason_codes"] == ["talk_already_bound_to_another_deck"]
    assert report["mutation_plan"]["mutations"] == []


def test_a_new_revision_beside_a_refreshed_row_is_held_and_the_refresh_isnt(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    """The Universe folder's shape: the bound deck's receipt is stale, and an
    uncataloged revision in the same batch proves the same talk."""
    database, result = _needs_extraction_fixture(
        tmp_path, vault, source_root, "unknown_legacy"
    )
    revision = _deck(
        source_root, "Voxxed Days Ticino/2025/DevOps for Developers v2.pptx"
    )
    extraction = _write_extraction(tmp_path, result, _result(source_root, revision))

    report = catalog_deck.execute(vault, extraction=extraction)

    assert _deck_entry(report)["disposition"] == "refresh"
    assert _deck_entry(report, revision)["reason_codes"] == [
        "talk_already_bound_to_another_deck"
    ]
    mutations = report["mutation_plan"]["mutations"]
    assert [mutation["record"]["pptx_path"] for mutation in mutations] == [DECK]
    mutate.build_candidate(database, mutations)


def test_a_named_deck_the_extraction_doesnt_hold_is_reported(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    report = catalog_deck.execute(
        vault, extraction=extraction, selected_decks=["Not/Extracted.pptx"]
    )

    assert report["decks"][0]["disposition"] == "not_in_extraction"
    assert report["mutation_plan"]["mutations"] == []


def test_a_deck_replaced_after_extraction_is_stale_not_planned(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))
    _deck(source_root, relative, title="A Completely Different Talk")

    report = catalog_deck.execute(vault, extraction=extraction)

    entry = _deck_entry(report, relative)
    assert entry["disposition"] == "extraction_stale"
    assert report["mutation_plan"]["mutations"] == []


def test_a_deck_gone_from_disk_is_reported_unreadable(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))
    (source_root / relative).unlink()

    report = catalog_deck.execute(vault, extraction=extraction)

    assert _deck_entry(report, relative)["disposition"] == "deck_unreadable"
    assert report["mutation_plan"]["mutations"] == []


def test_a_single_deck_result_with_an_absolute_path_is_accepted(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    result = _result(source_root, relative, pptx_path=str(source_root / relative))
    extraction = tmp_path / "single.json"
    extraction.write_text(json.dumps(result), encoding="utf-8")

    report = catalog_deck.execute(vault, extraction=extraction)

    assert _deck_entry(report, relative)["disposition"] == "bind"
    record = report["mutation_plan"]["mutations"][0]["record"]
    assert record["pptx_path"] == relative


def test_an_incomplete_scan_stays_visible(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(
        tmp_path,
        _result(source_root, relative),
        complete=False,
        incomplete_reason_codes=["pptx_artifact_unavailable"],
        skipped=[{"path": "talks/other.pptx", "reason": "pptx_artifact_unavailable"}],
    )

    report = catalog_deck.execute(vault, extraction=extraction)

    assert report["incomplete_reason_codes"] == ["pptx_artifact_unavailable"]


@pytest.mark.parametrize(
    "artifact_dir",
    [
        "",
        "/abs",
        "../outside",
        "a/../../b",
        "C:/extractions",
        r"C:\extractions",
        r"\\server\share\extractions",
        "//server/share/extractions",
    ],
)
def test_an_artifact_dir_outside_the_vault_is_refused(
    tmp_path: Path, vault: Path, source_root: Path, artifact_dir: str
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    with pytest.raises(catalog_deck.CatalogInputError, match="artifact-dir"):
        catalog_deck.execute(vault, extraction=extraction, artifact_dir=artifact_dir)


def _run_cli(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, arguments)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_emits_a_report_a_writer_can_lift_the_plan_from(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    result = _run_cli(vault, "--extraction", extraction)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(report["mutation_plan"]), encoding="utf-8")
    applied = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "mutate-tracking-database.py"),
            str(vault / "tracking-database.json"),
            str(plan_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert applied.returncode == 0, applied.stderr


@pytest.mark.parametrize(
    ("content", "needle"),
    [
        ("not json", "cannot read the extraction result"),
        ("[]", "not a JSON object"),
        ("{}", "neither a pptx-extraction.py"),
        ('{"kind": "pptx_directory_batch"}', "schema-v1 pptx-extraction.py"),
    ],
)
def test_cli_refuses_an_unusable_extraction_result(
    tmp_path: Path, vault: Path, source_root: Path, content: str, needle: str
) -> None:
    _write_database(vault, source_root)
    extraction = tmp_path / "bad.json"
    extraction.write_text(content, encoding="utf-8")

    result = _run_cli(vault, "--extraction", extraction)

    assert result.returncode == 2
    assert needle in result.stderr
    assert json.loads(result.stdout)["ok"] is False


def test_cli_refuses_an_unusable_database_without_echoing_it(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    (vault / "tracking-database.json").write_text("{not json", encoding="utf-8")
    extraction = _write_extraction(tmp_path, _result(source_root, relative))

    result = _run_cli(vault, "--extraction", extraction)

    assert result.returncode == 2
    assert json.loads(result.stdout)["ok"] is False
    assert "{not json" not in result.stderr


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": 3},
        {"schema_version": 5},
        {"schema_version": "4"},
        {"pipeline_version": "1.4.0"},
        {"pipeline_version": "1.6.0"},
    ],
    ids=[
        "old-schema",
        "future-schema",
        "string-schema",
        "old-pipeline",
        "future-pipeline",
    ],
)
def test_a_result_from_another_extraction_generation_is_refused(
    tmp_path: Path, vault: Path, source_root: Path, overrides: dict[str, Any]
) -> None:
    """A receipt binds the generation it was made with; an old or future one can't
    become a current catalog record."""
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(
        tmp_path, _result(source_root, relative, **overrides)
    )

    with pytest.raises(
        catalog_deck.CatalogInputError, match="this command reads schema 4"
    ):
        catalog_deck.execute(vault, extraction=extraction)

    assert not (vault / catalog_deck.DEFAULT_ARTIFACT_DIR).exists()


@pytest.mark.parametrize(
    "fingerprint",
    [None, {"algorithm": "md5", "digest": "0" * 32, "size_bytes": 1}, {"digest": "x"}],
    ids=["missing", "other-algorithm", "malformed"],
)
def test_a_result_without_a_valid_fingerprint_is_refused(
    tmp_path: Path, vault: Path, source_root: Path, fingerprint: object
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(
        tmp_path, _result(source_root, relative, input_fingerprint=fingerprint)
    )

    with pytest.raises(catalog_deck.CatalogInputError, match="input_fingerprint"):
        catalog_deck.execute(vault, extraction=extraction)


@pytest.mark.parametrize(
    "envelope",
    [
        {"schema_version": None},
        {"complete": False},
        {"incomplete_reason_codes": ["pptx_artifact_unavailable"]},
        {"unexpected": True},
    ],
    ids=[
        "unversioned",
        "completeness-without-receipts",
        "reasons-without-receipts",
        "extra-field",
    ],
)
def test_an_envelope_the_strict_decoder_rejects_is_refused(
    tmp_path: Path, vault: Path, source_root: Path, envelope: dict[str, Any]
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative), **envelope)

    with pytest.raises(catalog_deck.CatalogInputError, match="schema-v1"):
        catalog_deck.execute(vault, extraction=extraction)


def test_a_legacy_unversioned_batch_is_refused(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = tmp_path / "legacy.json"
    extraction.write_text(
        json.dumps({"results": [_result(source_root, relative)], "skipped": []}),
        encoding="utf-8",
    )

    with pytest.raises(catalog_deck.CatalogInputError, match="schema-v1"):
        catalog_deck.execute(vault, extraction=extraction)


def test_a_symlinked_artifact_directory_refuses_the_write(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault / catalog_deck.DEFAULT_ARTIFACT_DIR).symlink_to(
        outside, target_is_directory=True
    )

    with pytest.raises(catalog_deck.ArtifactWriteRefused, match="symbolic link"):
        catalog_deck.execute(vault, extraction=extraction)

    assert list(outside.iterdir()) == []


def test_a_symlinked_artifact_file_refuses_the_write(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))
    planned = catalog_deck.execute(vault, extraction=extraction, dry_run=True)[
        "artifacts_planned"
    ][0]
    outside = tmp_path / "outside.json"
    outside.write_text("untouched", encoding="utf-8")
    (vault / planned).parent.mkdir(parents=True)
    (vault / planned).symlink_to(outside)

    with pytest.raises(catalog_deck.ArtifactWriteRefused, match="symbolic link"):
        catalog_deck.execute(vault, extraction=extraction)

    assert outside.read_text(encoding="utf-8") == "untouched"


def test_a_vault_root_reached_through_a_symlink_still_takes_the_artifact(
    tmp_path: Path, vault: Path, source_root: Path
) -> None:
    """The root is trusted configuration; only components below it must be real."""
    relative = _deck(source_root)
    _write_database(vault, source_root)
    extraction = _write_extraction(tmp_path, _result(source_root, relative))
    linked_vault = tmp_path / "linked-vault"
    linked_vault.symlink_to(vault, target_is_directory=True)

    report = catalog_deck.execute(linked_vault, extraction=extraction)

    written = report["artifacts_written"]
    assert len(written) == 1
    assert (vault / written[0]).is_file()

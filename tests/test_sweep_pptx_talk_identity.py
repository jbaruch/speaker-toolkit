"""Tests for the catalog-wide PPTX-to-talk binding sweep (#176).

Carries this issue's synthetic regressions: same-title decks across venues and
years, unrelated decks in nearby directories, master/static pairs with
different slide counts, and a published PDF that disambiguates two candidates.

Every database and every deck is built in-test from fixed literals. Nothing
reads the clock or a live vault, so a run today and a run next year agree.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from test_pptx_deck_facts import full_deck_members, write_deck


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load_script(module_name: str, filename: str):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


sweep = _load_script("sweep_pptx_talk_identity", "sweep-pptx-talk-identity.py")


VOXXED_TALK = {
    "filename": "2025-01-17-voxxed-ticino-devops-developers.md",
    "title": "DevOps for Developers",
    "conference": "Voxxed Days Ticino",
    "date": "2025-01-17",
}
DEVOXX_TALK = {
    "filename": "2024-11-05-devoxx-belgium-devops-developers.md",
    "title": "DevOps for Developers",
    "conference": "Devoxx Belgium",
    "date": "2024-11-05",
}
KUBECON_TALK = {
    "filename": "2025-03-02-kubecon-europe-supply-chain.md",
    "title": "Securing the Software Supply Chain",
    "conference": "KubeCon Europe",
    "date": "2025-03-02",
}


def catalog_row(pptx_path: str, talk_filename: str | None, **overrides: Any) -> dict:
    row: dict[str, Any] = {
        "pptx_path": pptx_path,
        "talk_filename": talk_filename,
        "matched": talk_filename is not None,
        "slide_count": 42,
        "visual_extracted": False,
        "schema_version": 1,
    }
    row.update(overrides)
    return row


def database(rows: list[dict], talks: list[dict], source_root: Path) -> dict:
    """One owner-current database whose only interesting part is the catalog."""
    return {
        "schema_version": 1,
        "config": {
            "schema_version": 2,
            "pptx_directory_exclusions": [],
            "pptx_source_dir": str(source_root),
        },
        "talks": [{**talk, "schema_version": 5, "status": "pending"} for talk in talks],
        "pptx_catalog": rows,
        "qr_codes": [],
        "resources": [],
        "thumbnails": [],
        "confirmed_intents": [],
        "improvement_goals": [],
    }


def sweep_rows(rows: list[dict], talks: list[dict], source_root: Path) -> list[dict]:
    payload = database(rows, talks, source_root)
    return sweep.sweep_catalog(payload, pptx_source_dir=str(source_root))


@pytest.fixture()
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "Presentations"
    root.mkdir()
    return root


def deck(
    source_root: Path,
    relative: str,
    *,
    title: str = "DevOps for Developers",
    slides: int = 42,
) -> str:
    write_deck(
        source_root,
        relative,
        full_deck_members(slide_titles=[title], runs=[title], slides=slides),
    )
    return relative


class TestDispositions:
    def test_a_binding_the_assessment_selects_is_confirmed(
        self, source_root: Path
    ) -> None:
        path = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        rows = sweep_rows(
            [catalog_row(path, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK, KUBECON_TALK],
            source_root,
        )
        assert rows[0]["disposition"] == sweep.DISPOSITION_CONFIRMED
        assert rows[0]["selected_talk_filename"] == VOXXED_TALK["filename"]

    def test_a_deck_bound_to_another_talk_is_contradicted(
        self, source_root: Path
    ) -> None:
        """The live vault's defect: a deck feeding evidence to someone else's talk."""
        path = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        rows = sweep_rows(
            [catalog_row(path, KUBECON_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK, KUBECON_TALK],
            source_root,
        )
        assert rows[0]["disposition"] == sweep.DISPOSITION_CONTRADICTED
        assert rows[0]["stored_talk_filename"] == KUBECON_TALK["filename"]
        assert rows[0]["selected_talk_filename"] == VOXXED_TALK["filename"]

    def test_an_unbound_row_is_never_a_proposal_to_bind_it(
        self, source_root: Path
    ) -> None:
        path = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        rows = sweep_rows(
            [catalog_row(path, None)],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        assert rows[0]["disposition"] == sweep.DISPOSITION_UNBOUND
        assert rows[0]["stored_talk_filename"] is None

    def test_a_row_that_is_not_an_object_is_reported_not_dropped(
        self, source_root: Path
    ) -> None:
        """A dropped row would read as a binding with nothing wrong."""
        rows = sweep_rows(["not a record"], [VOXXED_TALK], source_root)  # type: ignore[list-item]
        assert rows[0]["disposition"] == sweep.DISPOSITION_UNASSESSABLE
        assert rows[0]["reason_codes"] == ["catalog_row_not_an_object"]


class TestSameTitleAcrossVenuesAndYears:
    def test_two_deliveries_of_one_talk_stay_distinguishable(
        self, source_root: Path
    ) -> None:
        ticino = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        belgium = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        rows = sweep_rows(
            [
                catalog_row(ticino, VOXXED_TALK["filename"]),
                catalog_row(belgium, DEVOXX_TALK["filename"]),
            ],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        assert [row["disposition"] for row in rows] == [
            sweep.DISPOSITION_CONFIRMED,
            sweep.DISPOSITION_CONFIRMED,
        ]

    def test_swapping_the_two_deliveries_contradicts_both(
        self, source_root: Path
    ) -> None:
        """Identical titles must not let one delivery's deck pass as the other's."""
        ticino = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        belgium = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        rows = sweep_rows(
            [
                catalog_row(ticino, DEVOXX_TALK["filename"]),
                catalog_row(belgium, VOXXED_TALK["filename"]),
            ],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        assert [row["disposition"] for row in rows] == [
            sweep.DISPOSITION_CONTRADICTED,
            sweep.DISPOSITION_CONTRADICTED,
        ]

    def test_the_same_venue_a_year_apart_is_not_one_delivery(
        self, source_root: Path
    ) -> None:
        later = {
            "filename": "2026-01-20-voxxed-ticino-devops-developers.md",
            "title": "DevOps for Developers",
            "conference": "Voxxed Days Ticino",
            "date": "2026-01-20",
        }
        path = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        rows = sweep_rows(
            [catalog_row(path, later["filename"])],
            [VOXXED_TALK, later],
            source_root,
        )
        assert rows[0]["disposition"] == sweep.DISPOSITION_CONTRADICTED
        assert rows[0]["selected_talk_filename"] == VOXXED_TALK["filename"]


class TestUnrelatedDecksInNearbyDirectories:
    def test_a_second_talk_at_the_same_venue_makes_the_binding_ambiguous(
        self, source_root: Path
    ) -> None:
        """Two talks fit the directory; the deck's title says which, and both
        readings are corroborated, so nothing is proven."""
        ticino_supply_chain = {
            "filename": "2025-01-18-voxxed-ticino-supply-chain.md",
            "title": "Securing the Software Supply Chain",
            "conference": "Voxxed Days Ticino",
            "date": "2025-01-18",
        }
        path = deck(
            source_root,
            "Voxxed Days Ticino/2025/Securing the Software Supply Chain.pptx",
            title="Securing the Software Supply Chain",
        )
        rows = sweep_rows(
            [catalog_row(path, VOXXED_TALK["filename"])],
            [VOXXED_TALK, ticino_supply_chain, KUBECON_TALK],
            source_root,
        )
        assert rows[0]["disposition"] == sweep.DISPOSITION_REVIEW_REQUIRED
        assert "identity_ambiguous_candidates" in rows[0]["reason_codes"]

    def test_a_rival_the_directory_contradicts_does_not_unseat_the_binding(
        self, source_root: Path
    ) -> None:
        """The reused-talk-family case, and why a title mismatch cannot veto.

        The deck renders KubeCon's title but sits in Ticino's 2025 directory,
        and KubeCon's venue contradicts that directory. `pptx_talk_identity`
        treats a non-agreeing title as missing corroboration rather than as
        contradiction — a deck legitimately carries a punchier title than its
        catalog entry — so the venue and year decide. Asserted here because
        the opposite rule would make every reused talk's deck unprovable.
        """
        path = deck(
            source_root,
            "Voxxed Days Ticino/2025/Securing the Software Supply Chain.pptx",
            title="Securing the Software Supply Chain",
        )
        rows = sweep_rows(
            [catalog_row(path, VOXXED_TALK["filename"])],
            [VOXXED_TALK, KUBECON_TALK],
            source_root,
        )
        assert rows[0]["disposition"] == sweep.DISPOSITION_CONFIRMED
        kubecon = next(
            entry
            for entry in rows[0]["assessment"]["candidates"]
            if entry["talk_filename"] == KUBECON_TALK["filename"]
        )
        # The rival's own standing is still reported, so the owner sees the
        # title evidence the verdict did not act on.
        assert kubecon["agreeing"] == ["title"]
        assert kubecon["conflicting"] == ["venue"]


class TestMasterAndStaticPairs:
    def test_a_master_never_confirms_a_binding(self, source_root: Path) -> None:
        path = deck(
            source_root,
            "Voxxed Days Ticino/2025/master/DevOps for Developers.pptx",
            slides=95,
        )
        rows = sweep_rows(
            [catalog_row(path, VOXXED_TALK["filename"], slide_count=95)],
            [VOXXED_TALK],
            source_root,
        )
        assert rows[0]["disposition"] == sweep.DISPOSITION_REVIEW_REQUIRED
        assert rows[0]["artifact_role"] == "master"
        assert "identity_non_delivery_artifact" in rows[0]["reason_codes"]

    def test_the_pair_is_told_apart_by_role_and_slide_count(
        self, source_root: Path
    ) -> None:
        """One delivery, two artifacts: only the delivery deck may be confirmed."""
        delivery = deck(
            source_root,
            "Voxxed Days Ticino/2025/DevOps for Developers.pptx",
            slides=95,
        )
        export = deck(
            source_root,
            "Voxxed Days Ticino/2025/static/DevOps for Developers.pptx",
            slides=40,
        )
        rows = sweep_rows(
            [
                catalog_row(delivery, VOXXED_TALK["filename"], slide_count=95),
                catalog_row(export, VOXXED_TALK["filename"], slide_count=40),
            ],
            [VOXXED_TALK],
            source_root,
        )
        assert rows[0]["disposition"] == sweep.DISPOSITION_CONFIRMED
        assert rows[0]["artifact_role"] == "delivery"
        assert rows[1]["disposition"] == sweep.DISPOSITION_REVIEW_REQUIRED
        assert rows[1]["artifact_role"] == "static_export"
        # The counts are what tells the owner which artifact is which, so the
        # sweep reports both the deck's own count and the row's stored claim.
        assert [row["deck_slide_count"] for row in rows] == [95, 40]
        assert [row["stored_slide_count"] for row in rows] == [95, 40]

    def test_a_deck_whose_stored_count_no_longer_matches_is_visible(
        self, source_root: Path
    ) -> None:
        path = deck(
            source_root,
            "Voxxed Days Ticino/2025/DevOps for Developers.pptx",
            slides=95,
        )
        rows = sweep_rows(
            [catalog_row(path, VOXXED_TALK["filename"], slide_count=40)],
            [VOXXED_TALK],
            source_root,
        )
        assert rows[0]["deck_slide_count"] == 95
        assert rows[0]["stored_slide_count"] == 40


class TestPublishedPdfDisambiguates:
    def test_the_pdf_identity_decides_between_two_equal_candidates(self) -> None:
        """Without the PDF both deliveries agree on title; with it, one wins.

        Asserted against the identity module rather than through the sweep,
        because the sweep has no producer for this fact: the live vault's
        talk-referenced PDFs live in the vault's own `slides/` directory and
        never beside a deck, so no deterministic deck-to-PDF binding exists to
        read. Inventing one would manufacture the evidence the module refuses
        to assume. The contract is covered so a future producer inherits it.
        """
        identity = _load_script("pptx_talk_identity", "pptx_talk_identity.py")
        ambiguous = identity.assess_pptx_talk_identity(
            {
                "pptx_path": "Decks/DevOps for Developers.pptx",
                "rendered_title": "DevOps for Developers",
            },
            [VOXXED_TALK, DEVOXX_TALK],
        )
        assert ambiguous.verdict == "review_required"
        decided = identity.assess_pptx_talk_identity(
            {
                "pptx_path": "Decks/DevOps for Developers.pptx",
                "rendered_title": "DevOps for Developers",
                "published_pdf_talk_filename": VOXXED_TALK["filename"],
            },
            [VOXXED_TALK, DEVOXX_TALK],
        )
        assert decided.verdict == "matched"
        assert decided.selected_talk_filename == VOXXED_TALK["filename"]


class TestDamagedDecks:
    def test_damage_weakens_evidence_never_the_requirement(
        self, source_root: Path
    ) -> None:
        (source_root / "Voxxed Days Ticino" / "2025").mkdir(parents=True)
        broken = "Voxxed Days Ticino/2025/DevOps for Developers.pptx"
        (source_root / broken).write_text("not a package", encoding="utf-8")
        rows = sweep_rows(
            [catalog_row(broken, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        # Venue and year still come from the path, so the binding is still
        # assessed — with the deck's own title absent, not waived.
        assert rows[0]["deck_facts_reason_code"] == "deck_facts_not_a_package"
        assert rows[0]["disposition"] == sweep.DISPOSITION_CONFIRMED
        assert rows[0]["observed_facts"] == []

    def test_a_damaged_deck_cannot_confirm_the_wrong_talk(
        self, source_root: Path
    ) -> None:
        (source_root / "Voxxed Days Ticino" / "2025").mkdir(parents=True)
        broken = "Voxxed Days Ticino/2025/DevOps for Developers.pptx"
        (source_root / broken).write_text("not a package", encoding="utf-8")
        rows = sweep_rows(
            [catalog_row(broken, DEVOXX_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        assert rows[0]["disposition"] == sweep.DISPOSITION_CONTRADICTED


class TestCandidateTable:
    def test_only_material_candidates_are_serialized(self, source_root: Path) -> None:
        """215 rows of six `unknown` verdicts is not evidence, it is noise."""
        path = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        rows = sweep_rows(
            [catalog_row(path, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK, KUBECON_TALK],
            source_root,
        )
        table = rows[0]["assessment"]["candidates"]
        assert rows[0]["assessment"]["candidates_assessed"] == 3
        assert all(
            any(verdict != "unknown" for verdict in entry["signals"].values())
            for entry in table
        )

    def test_the_selected_candidate_survives_the_trim(self, source_root: Path) -> None:
        """The trim must never remove the evidence behind the verdict."""
        path = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        rows = sweep_rows(
            [catalog_row(path, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK, KUBECON_TALK],
            source_root,
        )
        names = {
            entry["talk_filename"] for entry in rows[0]["assessment"]["candidates"]
        }
        assert VOXXED_TALK["filename"] in names

    def test_the_trimmed_assessment_still_authorizes_its_binding(
        self, source_root: Path
    ) -> None:
        """What the sweep reports must be what the owner gate would accept."""
        identity = _load_script("pptx_talk_identity", "pptx_talk_identity.py")
        path = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        rows = sweep_rows(
            [catalog_row(path, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK, KUBECON_TALK],
            source_root,
        )
        assessment = dict(rows[0]["assessment"])
        assessment.pop("candidates_assessed")
        assert (
            identity.binding_refusal(
                assessment,
                pptx_path=path,
                talk_filename=VOXXED_TALK["filename"],
            )
            is None
        )


class TestReport:
    def test_counts_cover_the_whole_catalog_even_when_rows_are_filtered(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        good = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        payload = database(
            [
                catalog_row(good, VOXXED_TALK["filename"]),
                catalog_row(bad, VOXXED_TALK["filename"]),
            ],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        report = sweep.execute(path, dispositions=[sweep.DISPOSITION_CONTRADICTED])
        assert report["catalog_row_count"] == 2
        assert report["disposition_counts"][sweep.DISPOSITION_CONFIRMED] == 1
        assert report["disposition_counts"][sweep.DISPOSITION_CONTRADICTED] == 1
        assert len(report["rows"]) == 1

    def test_unresolved_counts_every_binding_a_reparse_would_carry_forward(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        good = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        unbound = deck(source_root, "Decks/Loose.pptx", title="Loose")
        payload = database(
            [
                catalog_row(good, VOXXED_TALK["filename"]),
                catalog_row(bad, VOXXED_TALK["filename"]),
                catalog_row(unbound, None),
            ],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        report = sweep.execute(path)
        # Confirmed and unbound rows are resolved; only the contradiction is not.
        assert report["unresolved_binding_count"] == 1

    def test_the_report_is_stable_across_runs(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        path_a = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        payload = database(
            [catalog_row(path_a, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        first = sweep.execute(path)
        second = sweep.execute(path)
        assert first == second


class TestVaultResolution:
    def test_a_vault_root_resolves_to_its_canonical_database(
        self, tmp_path: Path
    ) -> None:
        root, database_path = sweep.resolve_input(tmp_path)
        assert root == tmp_path
        assert database_path == tmp_path / "tracking-database.json"

    def test_a_database_path_resolves_to_its_parent_root(self, tmp_path: Path) -> None:
        given = tmp_path / "tracking-database.json"
        root, database_path = sweep.resolve_input(given)
        assert root == tmp_path
        assert database_path == given


class TestCli:
    def test_an_unreadable_database_reports_a_neutral_code(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = sweep.main([str(tmp_path)])
        assert exit_code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert "error" in payload

    def test_a_swept_catalog_exits_zero_with_contradictions_present(
        self, tmp_path: Path, source_root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A reporting tool, not a gate: preflight is what blocks."""
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        payload = database(
            [catalog_row(bad, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        exit_code = sweep.main([str(path)])
        assert exit_code == 0
        report = json.loads(capsys.readouterr().out)
        assert report["disposition_counts"][sweep.DISPOSITION_CONTRADICTED] == 1

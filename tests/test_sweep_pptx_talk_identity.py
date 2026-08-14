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


class TestSourceDirectoryFallback:
    def test_an_absent_source_dir_falls_back_to_the_vault_root(
        self, tmp_path: Path
    ) -> None:
        """`schemas-db.md`: a null or absent `pptx_source_dir` means the vault root.

        Passing the absent value through would report every deck unreadable —
        a configuration default read as universal damage.
        """
        deck(tmp_path, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        payload = database(
            [
                catalog_row(
                    "Voxxed Days Ticino/2025/DevOps for Developers.pptx",
                    VOXXED_TALK["filename"],
                )
            ],
            [VOXXED_TALK, DEVOXX_TALK],
            tmp_path,
        )
        del payload["config"]["pptx_source_dir"]
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        report = sweep.execute(path)
        assert report["rows"][0]["deck_facts_reason_code"] == "deck_facts_read"
        assert report["rows"][0]["disposition"] == sweep.DISPOSITION_CONFIRMED

    @pytest.mark.parametrize("configured", [None, "", "   "])
    def test_a_blank_source_dir_falls_back_too(
        self, tmp_path: Path, configured: object
    ) -> None:
        deck(tmp_path, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        payload = database([], [VOXXED_TALK], tmp_path)
        payload["config"]["pptx_source_dir"] = configured
        assert sweep.resolve_pptx_source_dir(payload, vault_root=tmp_path) == tmp_path

    def test_a_configured_source_dir_wins(self, tmp_path: Path) -> None:
        payload = database([], [VOXXED_TALK], tmp_path / "Presentations")
        assert sweep.resolve_pptx_source_dir(payload, vault_root=tmp_path) == str(
            tmp_path / "Presentations"
        )


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


class TestSeverPlan:
    def _plan(self, tmp_path: Path, source_root: Path, rows, talks):
        payload = database(rows, talks, source_root)
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return sweep.execute(path, emit_mutations=True)["mutation_plan"]

    def test_a_contradicted_binding_is_severed(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        plan = self._plan(
            tmp_path,
            source_root,
            [catalog_row(bad, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
        )

        assert [m["kind"] for m in plan["mutations"]] == ["sever_pptx_talk_binding"]
        assert plan["mutations"][0]["pptx_path"] == bad

    def test_a_confirmed_binding_is_absent_from_the_plan(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """Proving a binding is `record_pptx`'s job; a sever plan that also
        carried proofs would be two decisions in one file."""
        good = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        plan = self._plan(
            tmp_path,
            source_root,
            [catalog_row(good, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
        )

        assert plan["mutations"] == []

    def test_an_unbound_row_is_never_severed(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        loose = deck(source_root, "Decks/Loose.pptx", title="Loose")
        plan = self._plan(
            tmp_path, source_root, [catalog_row(loose, None)], [VOXXED_TALK]
        )

        assert plan["mutations"] == []

    def test_the_plan_carries_both_exact_preconditions(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """Assessed at one moment, applied at another: anything that moved in
        between must fail the apply rather than sever silently."""
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        row = catalog_row(bad, VOXXED_TALK["filename"])
        bound_talk = {**VOXXED_TALK, "pptx_path": bad}
        plan = self._plan(tmp_path, source_root, [row], [bound_talk, DEVOXX_TALK])

        mutation = plan["mutations"][0]
        assert mutation["expect"] == row
        assert mutation["expect_talk_pptx_path"] == bad

    def test_a_talk_that_never_named_a_deck_expects_the_missing_marker(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """Expecting null and expecting absent are different preconditions."""
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        plan = self._plan(
            tmp_path,
            source_root,
            [catalog_row(bad, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
        )

        assert plan["mutations"][0]["expect_talk_pptx_path"] == {"$missing": True}

    def test_the_plan_ignores_the_disposition_filter(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """A plan that inherited `--dispositions` would sever only what the
        operator happened to be reading."""
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        payload = database(
            [catalog_row(bad, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = sweep.execute(
            path,
            dispositions=[sweep.DISPOSITION_CONFIRMED],
            emit_mutations=True,
        )

        assert report["rows"] == []
        assert len(report["mutation_plan"]["mutations"]) == 1

    def test_no_plan_without_the_flag(self, tmp_path: Path, source_root: Path) -> None:
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        payload = database(
            [catalog_row(bad, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        assert "mutation_plan" not in sweep.execute(path)

    def test_two_severs_naming_one_talk_clear_its_path_once(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """The live catalog has exactly this: two UberConf 2024 decks bound to
        one delivery. Snapshotting the stored value for both makes the second
        mutation fail a precondition the first one made false."""
        first = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        second = deck(source_root, "Devoxx Belgium/2024/Another Deck.pptx")
        bound = {**VOXXED_TALK, "pptx_path": first}
        plan = self._plan(
            tmp_path,
            source_root,
            [
                catalog_row(first, VOXXED_TALK["filename"]),
                catalog_row(second, VOXXED_TALK["filename"]),
            ],
            [bound, DEVOXX_TALK],
        )

        assert len(plan["mutations"]) == 2
        assert plan["mutations"][0]["expect_talk_pptx_path"] == first
        assert plan["mutations"][1]["expect_talk_pptx_path"] == {"$missing": True}


class TestProofPlan:
    def _plans(self, tmp_path: Path, source_root: Path, rows, talks):
        payload = database(rows, talks, source_root)
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        report = sweep.execute(path, emit_mutations=True)
        return report["mutation_plan"], report["proof_plan"]

    def test_a_confirmed_binding_gets_its_proof_written(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """A confirmed binding is not yet a proven one — preflight blocks a row
        that names a talk without an assessment."""
        good = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        _sever, proof = self._plans(
            tmp_path,
            source_root,
            [catalog_row(good, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
        )

        assert [m["kind"] for m in proof["mutations"]] == ["record_pptx"]
        record = proof["mutations"][0]["record"]
        assert record["talk_filename"] == VOXXED_TALK["filename"]
        assert record["identity_assessment"]["verdict"] == "matched"

    def test_the_written_proof_satisfies_the_owner_gate(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """What the plan writes must be what `record_pptx` would accept."""
        identity = _load_script("pptx_talk_identity", "pptx_talk_identity.py")
        good = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        _sever, proof = self._plans(
            tmp_path,
            source_root,
            [catalog_row(good, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
        )
        record = proof["mutations"][0]["record"]

        assert (
            identity.binding_refusal(
                record["identity_assessment"],
                pptx_path=record["pptx_path"],
                talk_filename=record["talk_filename"],
            )
            is None
        )

    def test_two_decks_confirming_one_talk_prove_neither(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """Two decks cannot both be one talk's delivery deck. Each is assessed
        alone and each agrees, so the contradiction is only visible across rows
        — and proving either would assert what the other disproves."""
        first = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        second = deck(
            source_root, "Voxxed Days Ticino/2025/DevOps for Developers 2.pptx"
        )
        _sever, proof = self._plans(
            tmp_path,
            source_root,
            [
                catalog_row(first, VOXXED_TALK["filename"]),
                catalog_row(second, VOXXED_TALK["filename"]),
            ],
            [VOXXED_TALK, DEVOXX_TALK],
        )

        assert proof["mutations"] == []

    def test_the_proof_record_drops_the_reports_own_reading_aid(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """`candidates_assessed` is this report's field; the owner gate
        validates a closed key set and would refuse the write."""
        good = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        _sever, proof = self._plans(
            tmp_path,
            source_root,
            [catalog_row(good, VOXXED_TALK["filename"])],
            [VOXXED_TALK],
        )

        assert (
            "candidates_assessed"
            not in (proof["mutations"][0]["record"]["identity_assessment"])
        )


class TestNothingIsSilentlyLeftBound:
    def test_an_unassessable_row_is_severed_like_any_unproven_one(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """ "The assessment could not run" is the strongest form of "not
        proven", and the plan claims to sever every binding it could not."""
        assert sweep.DISPOSITION_UNASSESSABLE in sweep.SEVERABLE_DISPOSITIONS

    def test_a_row_the_plan_cannot_address_is_named_not_dropped(
        self, source_root: Path
    ) -> None:
        """A plan that quietly drops what it cannot handle reads as complete
        while leaving a binding in place.

        Exercised at the builder, because a catalog the owner reader would
        reject never reaches `execute` — which is the right upstream behaviour
        and the reason this safety net needs its own test.
        """
        payload = database([], [VOXXED_TALK], source_root)
        orphan = {
            "index": 7,
            "pptx_path": "Gone.pptx",
            "stored_talk_filename": VOXXED_TALK["filename"],
            "disposition": sweep.DISPOSITION_UNASSESSABLE,
        }

        mutations, unseverable = sweep.sever_mutations(payload, [orphan])

        assert mutations == []
        assert len(unseverable) == 1
        assert unseverable[0]["index"] == 7

    def test_a_row_resolves_by_index_not_by_its_normalized_path(
        self, source_root: Path
    ) -> None:
        """A row's `pptx_path` is the deck-facts reading's normalized text, so
        a stored path with internal double spaces would not match a
        path-keyed lookup and would drop out of the plan silently."""
        stored = "Voxxed  Days/2025/Two  Spaces.pptx"
        payload = database(
            [catalog_row(stored, VOXXED_TALK["filename"])],
            [VOXXED_TALK],
            source_root,
        )
        row = {
            "index": 0,
            # Collapsed exactly as `_text` would produce it.
            "pptx_path": "Voxxed Days/2025/Two Spaces.pptx",
            "stored_talk_filename": VOXXED_TALK["filename"],
            "disposition": sweep.DISPOSITION_CONTRADICTED,
        }

        mutations, unseverable = sweep.sever_mutations(payload, [row])

        assert unseverable == []
        assert mutations[0]["pptx_path"] == stored

    def test_a_healthy_plan_reports_nothing_unseverable(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        payload = database(
            [catalog_row(bad, VOXXED_TALK["filename"])],
            [VOXXED_TALK, DEVOXX_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = sweep.execute(path, emit_mutations=True)

        assert len(report["mutation_plan"]["mutations"]) == 1
        assert report["unseverable"] == []


class TestThePlanOnlyEmitsWhatTheWriterAccepts:
    """A plan is a file a human reviews and then runs. One that looks
    actionable and dies partway through on a precondition the builder could
    have seen is worse than one that says up front what it cannot address.
    """

    def _row(self, **overrides: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "index": 0,
            "pptx_path": "Deck.pptx",
            "stored_talk_filename": VOXXED_TALK["filename"],
            "disposition": sweep.DISPOSITION_CONTRADICTED,
        }
        row.update(overrides)
        return row

    @pytest.mark.parametrize("bad_path", [None, "", "   ", " Deck.pptx", 17])
    def test_a_row_with_no_usable_path_is_named_not_emitted(
        self, source_root: Path, bad_path: object
    ) -> None:
        payload = database(
            [catalog_row("Deck.pptx", VOXXED_TALK["filename"])],
            [VOXXED_TALK],
            source_root,
        )
        payload["pptx_catalog"][0]["pptx_path"] = bad_path

        mutations, unseverable = sweep.sever_mutations(payload, [self._row()])

        assert mutations == []
        assert unseverable[0]["reason"] == "catalog row has no usable pptx_path"

    def test_a_dangling_talk_filename_is_named_not_emitted(
        self, source_root: Path
    ) -> None:
        """`_talk_by_filename` raises on a talk no record carries, so a plan
        naming one dies at apply with nothing said about it beforehand."""
        payload = database(
            [catalog_row("Deck.pptx", "ghost.md")],
            [VOXXED_TALK],
            source_root,
        )

        mutations, unseverable = sweep.sever_mutations(
            payload, [self._row(stored_talk_filename="ghost.md")]
        )

        assert mutations == []
        assert "binds a talk no record carries" in unseverable[0]["reason"]

    def test_a_row_pointing_past_the_catalog_is_named(self, source_root: Path) -> None:
        payload = database([], [VOXXED_TALK], source_root)

        mutations, unseverable = sweep.sever_mutations(payload, [self._row(index=9)])

        assert mutations == []
        assert unseverable[0]["reason"] == "no catalog row at this index"

    def test_the_proof_plan_applies_the_same_preconditions(
        self, source_root: Path
    ) -> None:
        payload = database(
            [catalog_row("Deck.pptx", "ghost.md")],
            [VOXXED_TALK],
            source_root,
        )
        row = self._row(
            stored_talk_filename="ghost.md",
            disposition=sweep.DISPOSITION_CONFIRMED,
            assessment={"verdict": "matched"},
        )

        assert sweep.proof_mutations(payload, [row]) == []


class TestThePlanEnvelopesAreApplyableAsIs:
    def test_each_plan_carries_only_what_load_plan_accepts(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """`load_plan` validates a CLOSED envelope, so an extra reporting key
        makes an otherwise healthy plan un-applyable."""
        bad = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        good = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        payload = database(
            [
                catalog_row(bad, DEVOXX_TALK["filename"]),
                catalog_row(good, VOXXED_TALK["filename"]),
            ],
            [VOXXED_TALK, DEVOXX_TALK, KUBECON_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = sweep.execute(path, emit_mutations=True)

        for name in ("mutation_plan", "proof_plan"):
            assert set(report[name]) == {"schema_version", "mutations"}, name
        assert "unseverable" in report


class TestOneTalkClaimedByAWrongAndARightDeck:
    def test_severing_the_wrong_deck_spares_the_right_binding(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        """One contradicted row and one confirmed row on the same talk: the
        sever must not clear a talk-side binding that names the confirmed deck.
        """
        wrong = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        right = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        bound = {**VOXXED_TALK, "pptx_path": right}
        payload = database(
            [
                catalog_row(wrong, VOXXED_TALK["filename"]),
                catalog_row(right, VOXXED_TALK["filename"]),
            ],
            [bound, DEVOXX_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = sweep.execute(path, emit_mutations=True)
        severs = report["mutation_plan"]["mutations"]

        assert [m["pptx_path"] for m in severs] == [wrong]
        # The precondition pins what is there; the writer then leaves it,
        # because it names a different deck.
        assert severs[0]["expect_talk_pptx_path"] == right

    def test_the_writer_leaves_that_binding_in_place(
        self, tmp_path: Path, source_root: Path
    ) -> None:
        mutate = _load_script("mutate_tracking_database", "mutate-tracking-database.py")
        wrong = deck(source_root, "Devoxx Belgium/2024/DevOps for Developers.pptx")
        right = deck(source_root, "Voxxed Days Ticino/2025/DevOps for Developers.pptx")
        bound = {**VOXXED_TALK, "pptx_path": right}
        payload = database(
            [
                catalog_row(wrong, VOXXED_TALK["filename"]),
                catalog_row(right, VOXXED_TALK["filename"]),
            ],
            [bound, DEVOXX_TALK],
            source_root,
        )
        path = tmp_path / "tracking-database.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        severs = sweep.execute(path, emit_mutations=True)["mutation_plan"]["mutations"]

        candidate, _changes = mutate.build_candidate(payload, severs)

        talk = next(
            t for t in candidate["talks"] if t["filename"] == VOXXED_TALK["filename"]
        )
        assert talk["pptx_path"] == right
        assert candidate["pptx_catalog"][0]["talk_filename"] is None
        assert candidate["pptx_catalog"][1]["talk_filename"] == VOXXED_TALK["filename"]

"""Tests for deterministic PPTX talk-identity assessment (#176).

Every fixture is built in-test from fixed literals. No test reads the clock,
the filesystem, or a live vault, so a run today and a run next year agree.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "vault-ingress" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

if "pptx_talk_identity" in sys.modules:
    pptx_talk_identity = sys.modules["pptx_talk_identity"]
else:
    _SPEC = importlib.util.spec_from_file_location(
        "pptx_talk_identity", SCRIPTS / "pptx_talk_identity.py"
    )
    assert _SPEC is not None and _SPEC.loader is not None
    pptx_talk_identity = importlib.util.module_from_spec(_SPEC)
    # Registered before exec so the module's dataclasses can resolve their own
    # module during class construction.
    sys.modules["pptx_talk_identity"] = pptx_talk_identity
    _SPEC.loader.exec_module(pptx_talk_identity)


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
UNRELATED_TALK = {
    "filename": "2025-03-02-kubecon-europe-supply-chain.md",
    "title": "Securing the Software Supply Chain",
    "conference": "KubeCon Europe",
    "date": "2025-03-02",
}


def _deck(**overrides: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "pptx_path": "Conferences/Voxxed Days Ticino/2025/DevOps for Developers.pptx"
    }
    facts.update(overrides)
    return facts


def _assess(deck: dict[str, Any], candidates: list[dict[str, Any]]):
    return pptx_talk_identity.assess_pptx_talk_identity(deck, candidates)


class TestVerdicts:
    def test_venue_and_year_agreement_selects_one_talk(self) -> None:
        result = _assess(_deck(), [VOXXED_TALK, DEVOXX_TALK])
        assert result.verdict == pptx_talk_identity.VERDICT_MATCHED
        assert result.selected_talk_filename == VOXXED_TALK["filename"]
        assert pptx_talk_identity.REASON_MATCHED in result.reason_codes

    def test_same_title_across_venues_stays_distinguishable(self) -> None:
        """The reused-talk-family case that mis-assigned the live vault."""
        result = _assess(
            _deck(
                pptx_path="Conferences/Devoxx Belgium/2024/DevOps for Developers.pptx"
            ),
            [VOXXED_TALK, DEVOXX_TALK],
        )
        assert result.selected_talk_filename == DEVOXX_TALK["filename"]

    def test_no_candidates_is_unmatched(self) -> None:
        result = _assess(_deck(), [])
        assert result.verdict == pptx_talk_identity.VERDICT_UNMATCHED
        assert result.reason_codes == (pptx_talk_identity.REASON_NO_CANDIDATE_TALKS,)

    def test_unrelated_deck_in_a_nearby_directory_is_not_matched(self) -> None:
        result = _assess(
            _deck(pptx_path="Conferences/KubeCon Europe/2025/Something Else.pptx"),
            [VOXXED_TALK],
        )
        assert result.verdict != pptx_talk_identity.VERDICT_MATCHED
        assert result.selected_talk_filename is None


class TestFilenameSimilarityIsNeverSufficient:
    def test_filename_agreement_alone_routes_to_review(self) -> None:
        """The explicit acceptance criterion: fuzzy filename similarity alone
        must not produce a match."""
        result = _assess(
            _deck(pptx_path="Decks/devops-developers.pptx"),
            [VOXXED_TALK],
        )
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_FILENAME_SIMILARITY]
            == pptx_talk_identity.SIGNAL_AGREE
        )
        assert candidate.agreeing == ()
        assert result.verdict == pptx_talk_identity.VERDICT_REVIEW_REQUIRED
        assert pptx_talk_identity.REASON_FILENAME_SIMILARITY_ONLY in result.reason_codes

    def test_filename_similarity_is_excluded_from_selecting_signals(self) -> None:
        assert (
            pptx_talk_identity.SIGNAL_FILENAME_SIMILARITY
            not in pptx_talk_identity.SELECTING_SIGNALS
        )


class TestDeliveryYearVetoesButNeverElects:
    """Every talk delivered in a year satisfies its year signal equally."""

    def test_year_is_excluded_from_selecting_signals(self) -> None:
        assert (
            pptx_talk_identity.SIGNAL_DELIVERY_YEAR
            not in pptx_talk_identity.SELECTING_SIGNALS
        )

    def test_a_matching_year_alone_does_not_select(self) -> None:
        result = _assess(
            _deck(pptx_path="Conferences/KubeCon Europe/2025/Something Else.pptx"),
            [VOXXED_TALK],
        )
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_DELIVERY_YEAR]
            == pptx_talk_identity.SIGNAL_AGREE
        )
        assert candidate.agreeing == ()
        assert result.verdict == pptx_talk_identity.VERDICT_UNMATCHED

    def test_a_mismatched_year_still_vetoes(self) -> None:
        result = _assess(
            _deck(
                pptx_path=(
                    "Conferences/Voxxed Days Ticino/2019/DevOps for Developers.pptx"
                )
            ),
            [VOXXED_TALK],
        )
        candidate = result.candidates[0]
        assert pptx_talk_identity.SIGNAL_DELIVERY_YEAR in candidate.conflicting
        assert not candidate.selectable


class TestVenueVocabulary:
    """A directory is a venue claim only when it names an event some talk uses."""

    def test_a_generic_directory_is_not_an_unrecognized_venue(self) -> None:
        result = _assess(
            {
                "pptx_path": "Decks/Downloads/deck.pptx",
                "rendered_title": "DevOps for Developers",
            },
            [VOXXED_TALK],
        )
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_VENUE]
            == pptx_talk_identity.SIGNAL_UNKNOWN
        )
        assert result.verdict == pptx_talk_identity.VERDICT_MATCHED

    def test_a_known_event_directory_that_is_not_this_talks_conflicts(self) -> None:
        result = _assess(
            _deck(pptx_path="Conferences/KubeCon Europe/2025/Supply Chain.pptx"),
            [VOXXED_TALK, UNRELATED_TALK],
        )
        voxxed = next(
            item
            for item in result.candidates
            if item.talk_filename == VOXXED_TALK["filename"]
        )
        assert (
            voxxed.signals[pptx_talk_identity.SIGNAL_VENUE]
            == pptx_talk_identity.SIGNAL_CONFLICT
        )
        assert result.selected_talk_filename == UNRELATED_TALK["filename"]


class TestConflictAndAmbiguity:
    def test_wrong_year_under_right_venue_conflicts(self) -> None:
        result = _assess(
            _deck(
                pptx_path="Conferences/Voxxed Days Ticino/2019/DevOps for Developers.pptx"
            ),
            [VOXXED_TALK],
        )
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_DELIVERY_YEAR]
            == pptx_talk_identity.SIGNAL_CONFLICT
        )
        assert result.verdict == pptx_talk_identity.VERDICT_REVIEW_REQUIRED
        assert pptx_talk_identity.REASON_CONFLICTING_SIGNALS in result.reason_codes

    def test_two_selectable_candidates_are_ambiguous(self) -> None:
        twin = dict(VOXXED_TALK)
        twin["filename"] = "2025-01-17-voxxed-ticino-devops-developers-part-two.md"
        result = _assess(_deck(), [VOXXED_TALK, twin])
        assert result.verdict == pptx_talk_identity.VERDICT_REVIEW_REQUIRED
        assert pptx_talk_identity.REASON_AMBIGUOUS_CANDIDATES in result.reason_codes
        assert result.selected_talk_filename is None

    def test_published_pdf_disambiguates_two_candidates(self) -> None:
        twin = dict(VOXXED_TALK)
        twin["filename"] = "2025-01-17-voxxed-ticino-devops-developers-part-two.md"
        result = _assess(
            _deck(published_pdf_talk_filename=VOXXED_TALK["filename"]),
            [VOXXED_TALK, twin],
        )
        assert result.verdict == pptx_talk_identity.VERDICT_MATCHED
        assert result.selected_talk_filename == VOXXED_TALK["filename"]

    def test_a_conflicting_signal_outranks_agreement(self) -> None:
        result = _assess(
            _deck(published_pdf_talk_filename=UNRELATED_TALK["filename"]),
            [VOXXED_TALK],
        )
        assert result.verdict == pptx_talk_identity.VERDICT_REVIEW_REQUIRED
        assert result.selected_talk_filename is None


class TestArtifactRoles:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            (
                "Conferences/Voxxed Days Ticino/2025/DevOps for Developers.pptx",
                pptx_talk_identity.ROLE_DELIVERY,
            ),
            (
                "Masters/Voxxed Days Ticino/2025/DevOps for Developers.pptx",
                pptx_talk_identity.ROLE_MASTER,
            ),
            (
                "Conferences/Voxxed Days Ticino/2025/DevOps static export.pptx",
                pptx_talk_identity.ROLE_STATIC_EXPORT,
            ),
            (
                "Backup/Voxxed Days Ticino/2025/DevOps for Developers.pptx",
                pptx_talk_identity.ROLE_BACKUP,
            ),
        ],
    )
    def test_role_classification(self, path: str, expected: str) -> None:
        facts = pptx_talk_identity.deck_identity_facts({"pptx_path": path})
        assert pptx_talk_identity.classify_artifact_role(facts) == expected

    def test_masterclass_is_a_topic_not_a_role(self) -> None:
        """Role tokens match whole path words, never substrings."""
        facts = pptx_talk_identity.deck_identity_facts(
            {"pptx_path": "Conferences/Devoxx Belgium/2024/Kafka Masterclass.pptx"}
        )
        assert (
            pptx_talk_identity.classify_artifact_role(facts)
            == pptx_talk_identity.ROLE_DELIVERY
        )

    def test_a_master_never_carries_a_bare_matched_verdict(self) -> None:
        result = _assess(
            _deck(
                pptx_path="Masters/Voxxed Days Ticino/2025/DevOps for Developers.pptx"
            ),
            [VOXXED_TALK],
        )
        assert result.artifact_role == pptx_talk_identity.ROLE_MASTER
        assert result.verdict == pptx_talk_identity.VERDICT_REVIEW_REQUIRED
        assert pptx_talk_identity.REASON_NON_DELIVERY_ARTIFACT in result.reason_codes
        assert result.selected_talk_filename is None


class TestSignalSemantics:
    def test_a_deck_title_that_differs_is_not_a_conflict(self) -> None:
        """Decks routinely carry a punchier title than the catalog entry."""
        result = _assess(
            _deck(rendered_title="Ship It Like You Mean It"), [VOXXED_TALK]
        )
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_TITLE]
            == pptx_talk_identity.SIGNAL_UNKNOWN
        )

    def test_rendered_title_agreement_corroborates(self) -> None:
        result = _assess(
            {
                "pptx_path": "Decks/deck.pptx",
                "rendered_title": "DevOps for Developers",
            },
            [VOXXED_TALK],
        )
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_TITLE]
            == pptx_talk_identity.SIGNAL_AGREE
        )
        assert result.verdict == pptx_talk_identity.VERDICT_MATCHED

    def test_hashtag_agreement_corroborates(self) -> None:
        result = _assess(
            {"pptx_path": "Decks/deck.pptx", "hashtags": ["#VoxxedTicino"]},
            [VOXXED_TALK],
        )
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_HASHTAG]
            == pptx_talk_identity.SIGNAL_AGREE
        )

    def test_an_ambiguous_directory_token_is_not_a_venue(self) -> None:
        """`devops/` names a topic folder at least as often as an event."""
        result = _assess(
            _deck(pptx_path="devops/DevOps for Developers.pptx"), [VOXXED_TALK]
        )
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_VENUE]
            != pptx_talk_identity.SIGNAL_CONFLICT
        )

    def test_document_timestamp_corroborates_but_never_contradicts(self) -> None:
        """A master re-saved years later is normal, not evidence of the wrong
        talk."""
        result = _assess(
            {"pptx_path": "Decks/deck.pptx", "document_created_year": "2019"},
            [VOXXED_TALK],
        )
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_DELIVERY_YEAR]
            == pptx_talk_identity.SIGNAL_UNKNOWN
        )

    def test_deck_filename_is_not_read_as_a_venue(self) -> None:
        """Reading a venue from the filename would manufacture agreement from
        the one signal the module refuses to trust alone."""
        result = _assess({"pptx_path": "Decks/Voxxed Days Ticino.pptx"}, [VOXXED_TALK])
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_VENUE]
            == pptx_talk_identity.SIGNAL_UNKNOWN
        )

    def test_a_talk_year_falls_back_to_the_filename_prefix(self) -> None:
        undated = {
            "filename": "2025-01-17-voxxed-ticino-devops-developers.md",
            "title": "DevOps for Developers",
            "conference": "Voxxed Days Ticino",
        }
        result = _assess(_deck(), [undated])
        candidate = result.candidates[0]
        assert (
            candidate.signals[pptx_talk_identity.SIGNAL_DELIVERY_YEAR]
            == pptx_talk_identity.SIGNAL_AGREE
        )


class TestInputValidation:
    def test_unknown_deck_keys_are_rejected(self) -> None:
        with pytest.raises(pptx_talk_identity.PptxTalkIdentityError):
            pptx_talk_identity.deck_identity_facts(
                {"pptx_path": "a.pptx", "confidence": 0.9}
            )

    def test_missing_path_is_rejected(self) -> None:
        with pytest.raises(pptx_talk_identity.PptxTalkIdentityError):
            pptx_talk_identity.deck_identity_facts({"pptx_path": "  "})

    def test_a_non_mapping_is_rejected(self) -> None:
        with pytest.raises(pptx_talk_identity.PptxTalkIdentityError):
            pptx_talk_identity.deck_identity_facts(["a.pptx"])

    def test_a_malformed_created_year_is_rejected(self) -> None:
        with pytest.raises(pptx_talk_identity.PptxTalkIdentityError):
            pptx_talk_identity.deck_identity_facts(
                {"pptx_path": "a.pptx", "document_created_year": "25"}
            )

    def test_a_duplicate_candidate_is_rejected(self) -> None:
        with pytest.raises(pptx_talk_identity.PptxTalkIdentityError):
            _assess(_deck(), [VOXXED_TALK, dict(VOXXED_TALK)])

    def test_a_candidate_without_a_filename_is_rejected(self) -> None:
        with pytest.raises(pptx_talk_identity.PptxTalkIdentityError):
            _assess(_deck(), [{"title": "No Filename"}])


class TestSerialization:
    def test_assessment_json_is_closed_and_stable(self) -> None:
        payload = _assess(_deck(), [VOXXED_TALK]).as_json()
        assert set(payload) == {
            "schema_version",
            "pptx_path",
            "verdict",
            "artifact_role",
            "selected_talk_filename",
            "reason_codes",
            "candidates",
        }
        assert payload["schema_version"] == (
            pptx_talk_identity.PPTX_TALK_IDENTITY_SCHEMA_VERSION
        )
        assert set(payload["candidates"][0]["signals"]) == set(
            pptx_talk_identity.SIGNAL_NAMES
        )

    def test_every_emitted_reason_code_is_in_the_closed_taxonomy(self) -> None:
        cases = [
            (_deck(), [VOXXED_TALK, DEVOXX_TALK]),
            (_deck(), []),
            (_deck(pptx_path="Decks/devops-developers.pptx"), [VOXXED_TALK]),
            (
                _deck(
                    pptx_path="Masters/Voxxed Days Ticino/2025/DevOps for Developers.pptx"
                ),
                [VOXXED_TALK],
            ),
            (
                _deck(
                    pptx_path="Conferences/Voxxed Days Ticino/2019/DevOps for Developers.pptx"
                ),
                [VOXXED_TALK],
            ),
            (_deck(pptx_path="Decks/unrelated-thing.pptx"), [UNRELATED_TALK]),
        ]
        for deck, candidates in cases:
            result = _assess(deck, candidates)
            assert result.verdict in pptx_talk_identity.VERDICTS
            assert set(result.reason_codes) <= pptx_talk_identity.REASON_CODES
            assert result.artifact_role in pptx_talk_identity.ARTIFACT_ROLES

    def test_a_non_matched_verdict_never_carries_a_selection(self) -> None:
        for deck, candidates in [
            (_deck(), []),
            (_deck(pptx_path="Decks/devops-developers.pptx"), [VOXXED_TALK]),
            (
                _deck(
                    pptx_path="Conferences/Voxxed Days Ticino/2019/DevOps for Developers.pptx"
                ),
                [VOXXED_TALK],
            ),
        ]:
            result = _assess(deck, candidates)
            assert result.selected_talk_filename is None

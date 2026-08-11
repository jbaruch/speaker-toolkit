"""Deterministic talk-identity assessment for candidate PPTX decks.

A deck becomes evidence for whichever talk the catalog says it belongs to. That
binding is made once, before persistence, and every later safeguard runs after
it — so a deck bound to the wrong talk supplies slide counts, design evidence,
OCR, and pattern observations to that wrong talk with nothing downstream able to
notice.

This module proves the binding instead of assuming it. It reads deterministic
identity facts already present on both sides — the catalog's title, conference,
and delivery date; the deck's path, document properties, and rendered title,
footer, and hashtag text — and reports which talk the deck belongs to, or
refuses to choose.

Two rules shape the taxonomy:

* Filename similarity alone never selects a talk. Reused talk families and
  nearby years produce near-identical filenames, which is precisely the signal
  that mis-assigned the live vault's decks in the first place.
* An unproven binding is a review finding, never a silent match. Refusing to
  choose costs one owner decision; choosing wrongly corrupts every derived
  analysis for that talk until someone notices.

Title and event comparison delegate to `source_identity_matching`, the same
authority the video source-identity audit uses. A deck must not be matched by a
weaker parallel rule than a recording.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from source_identity_matching import (
    AMBIGUOUS_EVENT_ALIASES,
    EventAlias,
    YEAR_RE,
    event_alias,
    event_aliases_compatible,
    known_event_aliases,
    normalized_words,
    titles_agree,
)


PPTX_TALK_IDENTITY_SCHEMA_VERSION = 1

# Signal verdicts. `unknown` is the honest default: a fact the deck does not
# carry is not evidence for or against any candidate.
SIGNAL_AGREE = "agree"
SIGNAL_CONFLICT = "conflict"
SIGNAL_UNKNOWN = "unknown"
SIGNAL_VERDICTS = frozenset({SIGNAL_AGREE, SIGNAL_CONFLICT, SIGNAL_UNKNOWN})

# Signal names, in report order.
SIGNAL_TITLE = "title"
SIGNAL_VENUE = "venue"
SIGNAL_DELIVERY_YEAR = "delivery_year"
SIGNAL_HASHTAG = "hashtag"
SIGNAL_PUBLISHED_PDF = "published_pdf"
SIGNAL_FILENAME_SIMILARITY = "filename_similarity"

SIGNAL_NAMES = (
    SIGNAL_TITLE,
    SIGNAL_VENUE,
    SIGNAL_DELIVERY_YEAR,
    SIGNAL_HASHTAG,
    SIGNAL_PUBLISHED_PDF,
    SIGNAL_FILENAME_SIMILARITY,
)

# A selecting signal must be one a same-family deck from another delivery could
# not also satisfy. Two signals are deliberately excluded:
#
# * filename similarity — reused talk families produce near-identical filenames,
#   which is what mis-assigned the live vault's decks in the first place;
# * delivery year — every talk delivered that year satisfies it equally, so it
#   narrows a candidate set without identifying anything in it.
#
# Both still report, and a year MISmatch still contradicts. Vetoing and electing
# are separate powers: a wrong year is proof of the wrong delivery, while a
# right year is proof of nothing.
SELECTING_SIGNALS = frozenset(
    {
        SIGNAL_TITLE,
        SIGNAL_VENUE,
        SIGNAL_HASHTAG,
        SIGNAL_PUBLISHED_PDF,
    }
)

VERDICT_MATCHED = "matched"
VERDICT_REVIEW_REQUIRED = "review_required"
VERDICT_UNMATCHED = "unmatched"
VERDICTS = frozenset({VERDICT_MATCHED, VERDICT_REVIEW_REQUIRED, VERDICT_UNMATCHED})

REASON_NO_CANDIDATE_TALKS = "identity_no_candidate_talks"
REASON_NO_AGREEING_SIGNAL = "identity_no_agreeing_signal"
REASON_FILENAME_SIMILARITY_ONLY = "identity_filename_similarity_only"
REASON_AMBIGUOUS_CANDIDATES = "identity_ambiguous_candidates"
REASON_CONFLICTING_SIGNALS = "identity_conflicting_signals"
REASON_MATCHED = "identity_matched"
REASON_NON_DELIVERY_ARTIFACT = "identity_non_delivery_artifact"

REASON_CODES = frozenset(
    {
        REASON_NO_CANDIDATE_TALKS,
        REASON_NO_AGREEING_SIGNAL,
        REASON_FILENAME_SIMILARITY_ONLY,
        REASON_AMBIGUOUS_CANDIDATES,
        REASON_CONFLICTING_SIGNALS,
        REASON_MATCHED,
        REASON_NON_DELIVERY_ARTIFACT,
    }
)

# An editable master and a published static export are legitimate artifacts for
# a delivery, but they are not the delivery deck and must not silently become
# its evidence. Roles are reported so the owner records which artifact is the
# published source and which is a later or editable variant.
ROLE_DELIVERY = "delivery"
ROLE_MASTER = "master"
ROLE_STATIC_EXPORT = "static_export"
ROLE_BACKUP = "backup"
ARTIFACT_ROLES = frozenset(
    {ROLE_DELIVERY, ROLE_MASTER, ROLE_STATIC_EXPORT, ROLE_BACKUP}
)

# Matched against whole path tokens, never substrings: `masterclass` is a talk
# topic, `master` is an artifact role.
_ROLE_TOKENS: tuple[tuple[str, frozenset[str]], ...] = (
    (ROLE_BACKUP, frozenset({"backup", "backups", "bak", "archive", "archived", "old"})),
    (ROLE_MASTER, frozenset({"master", "masters", "template", "templates", "source"})),
    (ROLE_STATIC_EXPORT, frozenset({"static", "export", "exports", "exported"})),
)

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)
_TALK_FILENAME_DATE_RE = re.compile(r"\A(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})-")

# A deck whose filename shares this many significant words with a talk's slug is
# similar enough to report — and never, on its own, similar enough to select.
_FILENAME_OVERLAP_MINIMUM = 2


class PptxTalkIdentityError(ValueError):
    """A talk-identity assessment input violates the module's contract."""


@dataclass(frozen=True)
class DeckIdentityFacts:
    """Deterministic identity facts observed on one candidate deck.

    Every field beyond `pptx_path` is optional because a damaged or minimal
    deck still deserves an assessment from whatever it does carry. Absence
    weakens the evidence; it never invents agreement.
    """

    pptx_path: str
    document_title: str | None = None
    document_created_year: str | None = None
    rendered_title: str | None = None
    rendered_footers: tuple[str, ...] = ()
    hashtags: tuple[str, ...] = ()
    published_pdf_talk_filename: str | None = None

    @property
    def path_tokens(self) -> tuple[str, ...]:
        return tuple(_TOKEN_RE.findall(self.pptx_path.casefold()))

    @property
    def basename(self) -> str:
        return posixpath.basename(self.pptx_path.replace("\\", "/"))


@dataclass(frozen=True)
class CandidateAssessment:
    """One talk's per-signal standing against the deck under assessment."""

    talk_filename: str
    signals: Mapping[str, str]
    agreeing: tuple[str, ...]
    conflicting: tuple[str, ...]

    @property
    def selectable(self) -> bool:
        """A candidate is selectable on corroboration with no contradiction."""
        return bool(self.agreeing) and not self.conflicting

    def as_json(self) -> dict[str, Any]:
        return {
            "talk_filename": self.talk_filename,
            "signals": {name: self.signals[name] for name in SIGNAL_NAMES},
            "agreeing": list(self.agreeing),
            "conflicting": list(self.conflicting),
        }


@dataclass(frozen=True)
class TalkIdentityAssessment:
    """The full, schema-versioned identity verdict for one deck."""

    pptx_path: str
    verdict: str
    artifact_role: str
    selected_talk_filename: str | None
    reason_codes: tuple[str, ...]
    candidates: tuple[CandidateAssessment, ...] = field(default=())

    @property
    def matched(self) -> bool:
        return self.verdict == VERDICT_MATCHED

    @property
    def review_required(self) -> bool:
        return self.verdict == VERDICT_REVIEW_REQUIRED

    def as_json(self) -> dict[str, Any]:
        return {
            "schema_version": PPTX_TALK_IDENTITY_SCHEMA_VERSION,
            "pptx_path": self.pptx_path,
            "verdict": self.verdict,
            "artifact_role": self.artifact_role,
            "selected_talk_filename": self.selected_talk_filename,
            "reason_codes": list(self.reason_codes),
            "candidates": [candidate.as_json() for candidate in self.candidates],
        }


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PptxTalkIdentityError(f"{label} must be a non-empty string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PptxTalkIdentityError(f"{label} must be a string or null")
    stripped = value.strip()
    return stripped or None


def _text_tuple(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise PptxTalkIdentityError(f"{label} must be an array of strings")
    items: list[str] = []
    for index, item in enumerate(value):
        text = _optional_text(item, f"{label}[{index}]")
        if text is not None:
            items.append(text)
    return tuple(items)


def deck_identity_facts(value: object) -> DeckIdentityFacts:
    """Validate a caller-supplied deck fact mapping into the closed shape.

    Typed `object` deliberately: this is the boundary where unvalidated caller
    input becomes a closed shape, so the isinstance guard is the contract, not
    a redundant assertion behind a narrower annotation.
    """
    if not isinstance(value, Mapping):
        raise PptxTalkIdentityError("deck facts must be a mapping")
    unknown = set(value) - {
        "pptx_path",
        "document_title",
        "document_created_year",
        "rendered_title",
        "rendered_footers",
        "hashtags",
        "published_pdf_talk_filename",
    }
    if unknown:
        raise PptxTalkIdentityError(
            f"deck facts carry unknown keys: {sorted(unknown)}"
        )
    created_year = _optional_text(
        value.get("document_created_year"), "deck facts document_created_year"
    )
    if created_year is not None and not re.fullmatch(r"(?:19|20)\d{2}", created_year):
        raise PptxTalkIdentityError(
            "deck facts document_created_year must be a four-digit year"
        )
    return DeckIdentityFacts(
        pptx_path=_require_text(value.get("pptx_path"), "deck facts pptx_path"),
        document_title=_optional_text(
            value.get("document_title"), "deck facts document_title"
        ),
        document_created_year=created_year,
        rendered_title=_optional_text(
            value.get("rendered_title"), "deck facts rendered_title"
        ),
        rendered_footers=_text_tuple(
            value.get("rendered_footers"), "deck facts rendered_footers"
        ),
        hashtags=_text_tuple(value.get("hashtags"), "deck facts hashtags"),
        published_pdf_talk_filename=_optional_text(
            value.get("published_pdf_talk_filename"),
            "deck facts published_pdf_talk_filename",
        ),
    )


def classify_artifact_role(facts: DeckIdentityFacts) -> str:
    """Report whether the deck is a delivery artifact or a variant of one."""
    tokens = set(facts.path_tokens)
    for role, markers in _ROLE_TOKENS:
        if tokens & markers:
            return role
    return ROLE_DELIVERY


def _talk_year(talk: Mapping[str, Any]) -> str | None:
    """Resolve a talk's delivery year from its date, else its filename prefix.

    Both are recorded values. Neither consults the clock, so an assessment made
    today and the same assessment made next year agree.
    """
    date_value = talk.get("date")
    if isinstance(date_value, str):
        match = YEAR_RE.search(date_value)
        if match is not None:
            return match.group(0)
    filename = talk.get("filename")
    if isinstance(filename, str):
        match = _TALK_FILENAME_DATE_RE.match(filename)
        if match is not None:
            return match.group("year")
    return None


def _deck_path_years(facts: DeckIdentityFacts) -> tuple[str, ...]:
    return tuple(
        token
        for token in facts.path_tokens
        if re.fullmatch(r"(?:19|20)\d{2}", token) is not None
    )


def _deck_venue_aliases(
    facts: DeckIdentityFacts, known_aliases: frozenset[EventAlias]
) -> list[EventAlias]:
    """Read venue aliases from the deck's directory components.

    Only directories are consulted. A deck's own filename is the talk's name far
    more often than the venue's, and reading a venue out of it would manufacture
    agreement from the one signal this module refuses to trust alone.

    A component counts as a venue claim only when it names an event some talk in
    the vault actually uses. Without that gate every generic folder — `Decks/`,
    `Downloads/` — would parse as an unrecognized venue and contradict every
    candidate, turning the discriminator into a blanket refusal.
    """
    normalized = facts.pptx_path.replace("\\", "/")
    components = [part for part in posixpath.dirname(normalized).split("/") if part]
    aliases: list[EventAlias] = []
    for component in components:
        alias = event_alias(component)
        if alias is None:
            continue
        if len(alias) == 1 and alias[0] in AMBIGUOUS_EVENT_ALIASES:
            # `devops/` names a topic folder at least as often as an event.
            continue
        if not any(
            event_aliases_compatible(alias, known) for known in known_aliases
        ):
            continue
        aliases.append(alias)
    return aliases


def _title_signal(
    facts: DeckIdentityFacts,
    talk: Mapping[str, Any],
    _known_aliases: frozenset[EventAlias],
) -> str:
    talk_title = talk.get("title")
    if not isinstance(talk_title, str) or not talk_title.strip():
        return SIGNAL_UNKNOWN
    observed = [
        text
        for text in (facts.document_title, facts.rendered_title, *facts.rendered_footers)
        if text
    ]
    if not observed:
        return SIGNAL_UNKNOWN
    if any(titles_agree(talk_title, text) for text in observed):
        return SIGNAL_AGREE
    # A deck legitimately carries a punchier title than its catalog entry, so a
    # non-agreeing title is missing corroboration rather than contradiction.
    return SIGNAL_UNKNOWN


def _venue_signal(
    facts: DeckIdentityFacts,
    talk: Mapping[str, Any],
    known_aliases: frozenset[EventAlias],
) -> str:
    talk_alias = event_alias(talk.get("conference"))
    if talk_alias is None:
        return SIGNAL_UNKNOWN
    deck_aliases = _deck_venue_aliases(facts, known_aliases)
    if not deck_aliases:
        return SIGNAL_UNKNOWN
    if any(event_aliases_compatible(talk_alias, alias) for alias in deck_aliases):
        return SIGNAL_AGREE
    # The deck sits under a named event that is not this talk's event. That is
    # the discriminator between two deliveries of one reused talk.
    return SIGNAL_CONFLICT


def _delivery_year_signal(
    facts: DeckIdentityFacts,
    talk: Mapping[str, Any],
    _known_aliases: frozenset[EventAlias],
) -> str:
    talk_year = _talk_year(talk)
    if talk_year is None:
        return SIGNAL_UNKNOWN
    path_years = _deck_path_years(facts)
    if path_years:
        if talk_year in path_years:
            return SIGNAL_AGREE
        return SIGNAL_CONFLICT
    if facts.document_created_year is not None:
        if facts.document_created_year == talk_year:
            return SIGNAL_AGREE
        # A master edited or re-saved years later is normal, so a document
        # timestamp corroborates but never contradicts.
        return SIGNAL_UNKNOWN
    return SIGNAL_UNKNOWN


def _hashtag_signal(
    facts: DeckIdentityFacts,
    talk: Mapping[str, Any],
    known_aliases: frozenset[EventAlias],
) -> str:
    talk_alias = event_alias(talk.get("conference"))
    if talk_alias is None or not facts.hashtags:
        return SIGNAL_UNKNOWN
    # `#VoxxedTicino` carries no word boundary, so a compact comparison against
    # the joined alias recovers what alias-wise compatibility cannot see.
    compact_talk = "".join(talk_alias)
    for raw in facts.hashtags:
        for token in _HASHTAG_RE.findall(raw) or [raw.lstrip("#")]:
            alias = event_alias(token)
            if alias is None:
                continue
            if event_aliases_compatible(talk_alias, alias):
                return SIGNAL_AGREE
            if "".join(alias) == compact_talk:
                return SIGNAL_AGREE
    # Conference hashtags are inconsistently present and frequently abbreviated
    # beyond alias recovery, so absence of agreement proves nothing.
    return SIGNAL_UNKNOWN


def _published_pdf_signal(
    facts: DeckIdentityFacts,
    talk: Mapping[str, Any],
    _known_aliases: frozenset[EventAlias],
) -> str:
    if facts.published_pdf_talk_filename is None:
        return SIGNAL_UNKNOWN
    filename = talk.get("filename")
    if not isinstance(filename, str) or not filename:
        return SIGNAL_UNKNOWN
    if facts.published_pdf_talk_filename == filename:
        return SIGNAL_AGREE
    return SIGNAL_CONFLICT


def _filename_similarity_signal(
    facts: DeckIdentityFacts,
    talk: Mapping[str, Any],
    _known_aliases: frozenset[EventAlias],
) -> str:
    filename = talk.get("filename")
    if not isinstance(filename, str) or not filename:
        return SIGNAL_UNKNOWN
    slug = _TALK_FILENAME_DATE_RE.sub("", filename)
    slug = re.sub(r"\.md\Z", "", slug)
    talk_words = normalized_words(slug.replace("-", " "))
    deck_words = normalized_words(posixpath.splitext(facts.basename)[0])
    if not talk_words or not deck_words:
        return SIGNAL_UNKNOWN
    if len(talk_words & deck_words) >= _FILENAME_OVERLAP_MINIMUM:
        return SIGNAL_AGREE
    return SIGNAL_UNKNOWN


_SIGNAL_EVALUATORS = {
    SIGNAL_TITLE: _title_signal,
    SIGNAL_VENUE: _venue_signal,
    SIGNAL_DELIVERY_YEAR: _delivery_year_signal,
    SIGNAL_HASHTAG: _hashtag_signal,
    SIGNAL_PUBLISHED_PDF: _published_pdf_signal,
    SIGNAL_FILENAME_SIMILARITY: _filename_similarity_signal,
}


def assess_candidate(
    facts: DeckIdentityFacts,
    talk: Mapping[str, Any],
    known_aliases: frozenset[EventAlias] = frozenset(),
) -> CandidateAssessment:
    """Evaluate every signal for one candidate talk.

    `known_aliases` is the vault's vocabulary of real event names. It defaults
    to empty so a single-candidate caller still gets an assessment; the effect
    of an empty vocabulary is that no directory reads as a venue, which loses
    the signal rather than inventing one.
    """
    filename = talk.get("filename")
    if not isinstance(filename, str) or not filename:
        raise PptxTalkIdentityError("candidate talk requires a filename")
    signals = {
        name: evaluator(facts, talk, known_aliases)
        for name, evaluator in _SIGNAL_EVALUATORS.items()
    }
    agreeing = tuple(
        name
        for name in SIGNAL_NAMES
        if name in SELECTING_SIGNALS and signals[name] == SIGNAL_AGREE
    )
    conflicting = tuple(
        name for name in SIGNAL_NAMES if signals[name] == SIGNAL_CONFLICT
    )
    return CandidateAssessment(
        talk_filename=filename,
        signals=signals,
        agreeing=agreeing,
        conflicting=conflicting,
    )


def assess_pptx_talk_identity(
    deck: Mapping[str, Any] | DeckIdentityFacts,
    candidates: Iterable[Mapping[str, Any]],
) -> TalkIdentityAssessment:
    """Decide which talk a deck belongs to, or refuse to decide.

    The verdict is `matched` only when exactly one candidate is corroborated by
    a signal filename similarity cannot fake and contradicted by none. Every
    other outcome is `review_required` or `unmatched`; neither authorizes
    catalog persistence or extraction.
    """
    facts = deck if isinstance(deck, DeckIdentityFacts) else deck_identity_facts(deck)
    artifact_role = classify_artifact_role(facts)
    talks = list(candidates)
    # The candidate set is the vault's event vocabulary. A directory naming an
    # event no talk uses is a folder, not a contradicting venue.
    known_aliases = frozenset(known_event_aliases(talks))
    assessments = tuple(
        assess_candidate(facts, talk, known_aliases) for talk in talks
    )

    seen: set[str] = set()
    for assessment in assessments:
        if assessment.talk_filename in seen:
            raise PptxTalkIdentityError(
                f"candidate talk {assessment.talk_filename!r} appears twice"
            )
        seen.add(assessment.talk_filename)

    def result(
        verdict: str, selected: str | None, *reasons: str
    ) -> TalkIdentityAssessment:
        codes = list(reasons)
        # A master, backup, or static export never carries a bare `matched`
        # verdict into persistence: the owner records which artifact is the
        # published source before its contents become a talk's evidence.
        if artifact_role != ROLE_DELIVERY and verdict == VERDICT_MATCHED:
            verdict = VERDICT_REVIEW_REQUIRED
            codes.append(REASON_NON_DELIVERY_ARTIFACT)
        elif artifact_role != ROLE_DELIVERY:
            codes.append(REASON_NON_DELIVERY_ARTIFACT)
        return TalkIdentityAssessment(
            pptx_path=facts.pptx_path,
            verdict=verdict,
            artifact_role=artifact_role,
            selected_talk_filename=selected if verdict == VERDICT_MATCHED else None,
            reason_codes=tuple(dict.fromkeys(codes)),
            candidates=assessments,
        )

    if not assessments:
        return result(VERDICT_UNMATCHED, None, REASON_NO_CANDIDATE_TALKS)

    selectable = [item for item in assessments if item.selectable]
    if len(selectable) == 1:
        return result(VERDICT_MATCHED, selectable[0].talk_filename, REASON_MATCHED)
    if len(selectable) > 1:
        return result(
            VERDICT_REVIEW_REQUIRED, None, REASON_AMBIGUOUS_CANDIDATES
        )

    contradicted = [
        item for item in assessments if item.agreeing and item.conflicting
    ]
    if contradicted:
        return result(VERDICT_REVIEW_REQUIRED, None, REASON_CONFLICTING_SIGNALS)

    filename_only = [
        item
        for item in assessments
        if item.signals[SIGNAL_FILENAME_SIMILARITY] == SIGNAL_AGREE
        and not item.conflicting
    ]
    if filename_only:
        return result(
            VERDICT_REVIEW_REQUIRED, None, REASON_FILENAME_SIMILARITY_ONLY
        )

    return result(VERDICT_UNMATCHED, None, REASON_NO_AGREEING_SIGNAL)

"""Deterministic title and event matching for source-identity checks.

Provider titles often retain a talk's explicit base title while dropping its
catalog subtitle and appending an event. Base-title agreement is evaluated
separately from event agreement so a familiar talk family cannot hide a video
from the wrong delivery.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
import math
import re
from typing import Any
import unicodedata


WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
TITLE_SUBTITLE_RE = re.compile(r":|\s[-\u2013\u2014]\s|\s\(")
EVENT_CONTEXT_SEPARATOR_RE = re.compile(r"\s[-\u2013\u2014|]\s")
AT_RE = re.compile(r"\bat\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
EXPLICIT_YEAR_RE = re.compile(r"(?<!\d)\d{4}(?!\d)")
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
CATALOG_YEAR_RE = re.compile(r"\d{4}")
SHOWNOTES_EVENT_QUALIFIER_RE = re.compile(
    r"\s+at\s+(?P<event>\S(?:.*\S)?)\Z",
    re.IGNORECASE,
)

TITLE_QUOTE_EQUIVALENTS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)

TITLE_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "by",
        "conference",
        "for",
        "from",
        "in",
        "keynote",
        "of",
        "on",
        "or",
        "session",
        "talk",
        "the",
        "to",
        "with",
    }
)
EVENT_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "annual",
        "at",
        "conference",
        "conf",
        "convention",
        "day",
        "days",
        "edition",
        "event",
        "events",
        "meetup",
        "meetups",
        "of",
        "open",
        "summit",
        "the",
        "webinar",
        "webinars",
    }
)
SHOWNOTES_EVENT_STOP_WORDS = frozenset({"a", "an", "at", "of", "the"})
SHOWNOTES_OPTIONAL_EVENT_BIGRAMS = frozenset({("voxxed", "days")})
AMBIGUOUS_EVENT_ALIASES = frozenset({"ai", "devops", "java", "spring"})
EVENT_WORD_REPLACEMENTS = {
    "belgium": ("be",),
    "devoxxbe": ("devoxx", "be"),
    "devoxxfr": ("devoxx", "fr"),
    "devoxxuk": ("devoxx", "uk"),
    "devopsdays": ("devops",),
    "france": ("fr",),
}

EventAlias = tuple[str, ...]


def _ordered_words(value: str, stop_words: frozenset[str]) -> list[str]:
    return [
        word
        for word in WORD_RE.findall(value.casefold())
        if word not in stop_words and len(word) > 1
    ]


def normalized_words(value: str) -> set[str]:
    """Return significant title words for overlap and clip-marker checks."""
    return set(_ordered_words(value, TITLE_STOP_WORDS))


def _normalized_title_presentation(value: str) -> str:
    return unicodedata.normalize("NFC", value).translate(TITLE_QUOTE_EQUIVALENTS)


def _contains_sequence(haystack: list[str] | EventAlias, needle: EventAlias) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(
        tuple(haystack[index : index + width]) == needle
        for index in range(len(haystack) - width + 1)
    )


def _contains_ordered_subsequence(
    haystack: list[str] | EventAlias,
    needle: EventAlias,
) -> bool:
    position = 0
    for word in haystack:
        if position < len(needle) and word == needle[position]:
            position += 1
    return position == len(needle)


def _explicit_base_title_agrees(expected: str, observed: str) -> bool:
    separator = TITLE_SUBTITLE_RE.search(expected)
    if separator is None:
        return False
    lead = tuple(_ordered_words(expected[: separator.start()], TITLE_STOP_WORDS))
    if len(lead) < 2:
        return False
    if len(lead) == 2 and not any(len(word) >= 8 for word in lead):
        return False
    observed_words = _ordered_words(observed, TITLE_STOP_WORDS)
    return _contains_sequence(observed_words, lead)


def titles_agree(expected: str, observed: str) -> bool:
    """Conservatively compare a catalog title with a provider title.

    Full normalized containment and significant-word overlap retain the v1
    behavior. An explicitly delimited, distinctive base title is also accepted
    when it appears contiguously in the provider title. Event identity is a
    separate check; callers must not use this result as delivery proof.
    """
    expected_flat = " ".join(WORD_RE.findall(expected.casefold()))
    observed_flat = " ".join(WORD_RE.findall(observed.casefold()))
    if expected_flat and f" {expected_flat} " in f" {observed_flat} ":
        return True
    expected_compact = "".join(WORD_RE.findall(expected.casefold()))
    observed_compact = "".join(WORD_RE.findall(observed.casefold()))
    if len(expected_compact) >= 8 and expected_compact in observed_compact:
        return True
    expected_words = normalized_words(expected)
    observed_words = normalized_words(observed)
    if expected_words and observed_words:
        overlap = len(expected_words & observed_words)
        minimum = (
            1 if len(expected_words) == 1 else max(2, (len(expected_words) + 1) // 2)
        )
        if overlap >= minimum:
            return True
    return _explicit_base_title_agrees(expected, observed)


def event_alias(value: Any) -> EventAlias | None:
    """Normalize a catalog conference into a comparable event alias."""
    if not isinstance(value, str) or not value.strip():
        return None
    words_list: list[str] = []
    for word in _ordered_words(value, EVENT_STOP_WORDS):
        if word.isdigit():
            continue
        words_list.extend(EVENT_WORD_REPLACEMENTS.get(word, (word,)))
    words = tuple(words_list)
    if not words or (len(words) == 1 and len(words[0]) < 3):
        return None
    return words


def _shownotes_event_alias(value: Any, *, expected_year: str) -> EventAlias | None:
    """Return a conservative NFC alias for shownotes title comparison."""
    if not isinstance(value, str) or not value.strip():
        return None
    words_list: list[str] = []
    normalized = unicodedata.normalize("NFC", value).casefold()
    raw_words = WORD_RE.findall(normalized)
    for index, word in enumerate(raw_words):
        if word in SHOWNOTES_EVENT_STOP_WORDS:
            continue
        if word.isdigit():
            if word == expected_year:
                continue
            return None
        if len(word) <= 1:
            continue
        if (
            index > 0
            and (raw_words[index - 1], word) in SHOWNOTES_OPTIONAL_EVENT_BIGRAMS
        ):
            continue
        words_list.extend(EVENT_WORD_REPLACEMENTS.get(word, (word,)))
    words = tuple(words_list)
    if not words or (len(words) == 1 and len(words[0]) < 3):
        return None
    return words


def shownotes_titles_agree(
    authored_title: Any,
    shownotes_title: Any,
    *,
    conference: Any,
    talk_date: Any,
) -> bool:
    """Compare an authored title with a shownotes publication title.

    Agreement is intentionally asymmetric. Shownotes may retain the complete
    authored title and append ``at <event>`` only when that event alias equals
    the talk conference and every explicit year agrees with the talk date.
    Generic event-type words remain significant. Only the shownotes comparator's
    closed branded presentation variants may be omitted.
    The authored title itself receives only the scanner's historical NFC and
    Unicode-quote normalization; case, punctuation, wording, and whitespace
    remain meaningful.
    """
    if not isinstance(authored_title, str) or not isinstance(shownotes_title, str):
        return False

    authored = _normalized_title_presentation(authored_title)
    shownotes = _normalized_title_presentation(shownotes_title)
    if authored == shownotes:
        return True
    if not authored or not shownotes.startswith(authored):
        return False

    qualifier_match = SHOWNOTES_EVENT_QUALIFIER_RE.fullmatch(shownotes[len(authored) :])
    if qualifier_match is None:
        return False
    qualifier = qualifier_match.group("event")

    if not isinstance(talk_date, str) or ISO_DATE_RE.fullmatch(talk_date) is None:
        return False
    try:
        expected_year = f"{date.fromisoformat(talk_date).year:04d}"
    except ValueError:
        return False

    for value in (conference, qualifier):
        if not isinstance(value, str):
            return False
        explicit_years = set(EXPLICIT_YEAR_RE.findall(value))
        if explicit_years and explicit_years != {expected_year}:
            return False

    conference_alias = _shownotes_event_alias(
        conference,
        expected_year=expected_year,
    )
    qualifier_alias = _shownotes_event_alias(
        qualifier,
        expected_year=expected_year,
    )
    if conference_alias is None or qualifier_alias != conference_alias:
        return False
    return True


def known_event_aliases(talks: Iterable[Any]) -> set[EventAlias]:
    """Collect deterministic event aliases from all valid catalog records."""
    aliases: set[EventAlias] = set()
    for talk in talks:
        if not isinstance(talk, dict):
            continue
        alias = event_alias(talk.get("conference"))
        if alias is not None:
            aliases.add(alias)
    return aliases


def _provider_event_contexts(title: str) -> list[list[str]]:
    contexts: list[str] = []
    at_matches = list(AT_RE.finditer(title))
    if at_matches:
        contexts.append(title[at_matches[-1].end() :])
    chunks = EVENT_CONTEXT_SEPARATOR_RE.split(title)
    if len(chunks) > 1:
        contexts.extend(
            chunk for chunk in (chunks[0], chunks[-1]) if YEAR_RE.search(chunk)
        )

    normalized: set[EventAlias] = set()
    for context in contexts:
        words = event_alias(context)
        if words is not None:
            normalized.add(words)
    return [list(words) for words in sorted(normalized)]


def provider_event_aliases(
    provider_title: str,
    known_aliases: set[EventAlias],
) -> list[EventAlias]:
    """Find maximal known event aliases in explicit provider-title contexts."""
    found: set[EventAlias] = set()
    ordered_aliases = sorted(
        known_aliases,
        key=lambda alias: (-len(alias), -sum(map(len, alias)), alias),
    )
    for context in _provider_event_contexts(provider_title):
        context_matches: list[EventAlias] = []
        for alias in ordered_aliases:
            if len(alias) == 1 and alias[0] in AMBIGUOUS_EVENT_ALIASES:
                continue
            contiguous = _contains_sequence(context, alias)
            ordered = len(alias) > 1 and _contains_ordered_subsequence(context, alias)
            if not contiguous and not ordered:
                continue
            if any(_contains_sequence(existing, alias) for existing in context_matches):
                continue
            context_matches.append(alias)
        found.update(context_matches)
    return sorted(found)


def event_aliases_compatible(left: EventAlias, right: EventAlias) -> bool:
    """Report whether two event aliases can name the same event.

    One alias containing every word of the other is compatibility, not equality:
    a catalog conference is often the fuller form of what an artifact records.
    Public because PPTX talk-identity assessment compares a deck-path venue with
    a catalog conference and must not maintain a second, weaker rule.
    """
    left_words = set(left)
    right_words = set(right)
    return left_words <= right_words or right_words <= left_words


def _aliases_compatible(left: EventAlias, right: EventAlias) -> bool:
    return event_aliases_compatible(left, right)


def event_agreement(
    catalog_conference: Any,
    provider_title: str,
    known_aliases: set[EventAlias],
) -> tuple[bool | None, EventAlias | None, list[EventAlias]]:
    """Compare an explicitly named provider event with the catalog conference."""
    catalog_alias = event_alias(catalog_conference)
    mentions = provider_event_aliases(provider_title, known_aliases)
    if catalog_alias is None or not mentions:
        return None, catalog_alias, mentions
    agrees = any(_aliases_compatible(catalog_alias, mention) for mention in mentions)
    return agrees, catalog_alias, mentions


def parse_catalog_date(value: Any) -> tuple[date | None, int] | None:
    """Return a catalog date as its exact day (when known) and its year.

    A catalog record carries either a full ISO-8601 day or a bare `YYYY`, and a
    bare year is a real delivery whose day was never recorded — not an absent
    date. Returning the day and the year separately lets a caller compare at
    whichever precision the record actually supports, so a coarse record stays
    comparable instead of dropping out of the comparison entirely.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    if CATALOG_YEAR_RE.fullmatch(value):
        return None, int(value)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed, parsed.year


# A provider upload date is UTC; a cataloged delivery date is the local day at
# the venue. A talk delivered in Auckland (UTC+13) and uploaded straight after
# carries a UTC upload date of the previous day, which is not evidence of a
# recording that predates its own delivery. One day absorbs every real offset —
# the extremes are UTC-12 and UTC+14 — while a recording genuinely from an
# earlier delivery is off by far more than a day. The same offset applies at a
# bare-year record's boundary, where 31 December can be a 1 January delivery.
UPLOAD_TIMEZONE_GRACE = timedelta(days=1)


def upload_predates_catalog(
    upload: date | None,
    catalog: tuple[date | None, int] | None,
) -> bool | None:
    """Return whether provider upload evidence precedes the cataloged delivery.

    Compares at the catalog record's own precision: against the exact day when
    the record carries one, and against the year otherwise. `None` means the
    comparison could not be made, which is distinct from `False`.

    Both precisions allow `UPLOAD_TIMEZONE_GRACE`, because the two dates are not
    measured in the same timezone. A bare-year record is compared against the
    first day of that year, so the grace covers its boundary too: a talk
    delivered on 1 January in a UTC+13 venue and uploaded immediately carries a
    UTC upload date of 31 December, which is a clock offset rather than evidence
    of an earlier delivery.
    """
    if upload is None or catalog is None:
        return None
    catalog_day, catalog_year = catalog
    boundary = catalog_day if catalog_day is not None else date(catalog_year, 1, 1)
    return upload < boundary - UPLOAD_TIMEZONE_GRACE


def expected_duration_seconds(talk: dict[str, Any]) -> float | None:
    """Return the catalog's own duration for a talk, in seconds.

    Reads the first positive, finite duration among the record's own fields and
    its `structured_data` block. Booleans are rejected before the numeric test
    because `bool` is an `int` in Python, and a `True` would otherwise read as a
    one-second duration.
    """
    candidates = [
        talk.get("duration_seconds"),
        talk.get("video_duration_seconds"),
        talk.get("talk_duration_seconds"),
    ]
    structured = talk.get("structured_data")
    if isinstance(structured, dict):
        candidates.extend(
            [
                structured.get("video_duration_seconds"),
                structured.get("recording_duration_seconds"),
                structured.get("duration_seconds"),
            ]
        )
    for value in candidates:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            return float(value)
    return None


SOURCE_TITLE_EQUIVALENCE_RECORD_SCHEMA_VERSION = 1


def pinned_provider_title(value: str) -> str:
    """Canonicalize a provider title for pinned comparison.

    Whitespace runs and Unicode composition vary without changing what an owner
    read, so both are normalized. Every comparison of a pinned title — the
    reader's match and the writer's duplicate check — goes through this, or the
    two disagree about which records are the same approval.
    """
    return " ".join(unicodedata.normalize("NFC", value).split())


def title_equivalence_recorded(
    equivalences: Any,
    *,
    talk_filename: Any,
    video_id: Any,
    catalog_title: Any,
    provider_title: Any,
) -> bool:
    """Report whether an owner reviewed this exact title pair for this talk.

    Comparison is on the pinned strings, not the fuzzy title contract: the ledger
    records a judgment about one observed pair, so either side changing retires
    it. A provider that retitles the video re-gates, and so does a catalog title
    edited after the review — the approval was that THESE two name the same
    talk, and it says nothing about a name the owner never read. Whitespace and
    Unicode composition are normalized because those vary without changing what
    an owner read.
    """
    if not isinstance(equivalences, list):
        return False
    if (
        not isinstance(talk_filename, str)
        or not isinstance(video_id, str)
        or not isinstance(catalog_title, str)
        or not isinstance(provider_title, str)
    ):
        return False
    pinned = pinned_provider_title(provider_title)
    pinned_catalog = pinned_provider_title(catalog_title)
    if not pinned or not pinned_catalog:
        return False
    for equivalence in equivalences:
        if not isinstance(equivalence, dict):
            continue
        # An unrecognized generation is unusable state, never an approval: a
        # future record may mean something this reader cannot see, and the
        # failure it would suppress is the wrong-delivery gate.
        recorded_version = equivalence.get("schema_version")
        if (
            isinstance(recorded_version, bool)
            or not isinstance(recorded_version, int)
            or recorded_version != SOURCE_TITLE_EQUIVALENCE_RECORD_SCHEMA_VERSION
        ):
            continue
        recorded_filename = equivalence.get("talk_filename")
        recorded_id = equivalence.get("video_id")
        recorded_title = equivalence.get("provider_title")
        recorded_catalog = equivalence.get("catalog_title")
        if (
            not isinstance(recorded_filename, str)
            or not isinstance(recorded_id, str)
            or not isinstance(recorded_title, str)
            or not isinstance(recorded_catalog, str)
        ):
            continue
        if (
            recorded_filename == talk_filename
            and recorded_id == video_id
            and pinned_provider_title(recorded_title) == pinned
            and pinned_provider_title(recorded_catalog) == pinned_catalog
        ):
            return True
    return False

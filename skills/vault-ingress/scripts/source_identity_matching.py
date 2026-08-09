"""Deterministic title and event matching for source-identity checks.

Provider titles often retain a talk's explicit base title while dropping its
catalog subtitle and appending an event. Base-title agreement is evaluated
separately from event agreement so a familiar talk family cannot hide a video
from the wrong delivery.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
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


def _aliases_compatible(left: EventAlias, right: EventAlias) -> bool:
    left_words = set(left)
    right_words = set(right)
    return left_words <= right_words or right_words <= left_words


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

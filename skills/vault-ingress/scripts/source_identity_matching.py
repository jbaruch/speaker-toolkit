"""Deterministic title and event matching for source-identity checks.

Provider titles often retain a talk's explicit base title while dropping its
catalog subtitle and appending an event. Base-title agreement is evaluated
separately from event agreement so a familiar talk family cannot hide a video
from the wrong delivery.
"""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any


WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
TITLE_SUBTITLE_RE = re.compile(r":|\s[-\u2013\u2014]\s|\s\(")
EVENT_CONTEXT_SEPARATOR_RE = re.compile(r"\s[-\u2013\u2014|]\s")
AT_RE = re.compile(r"\bat\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

TITLE_STOP_WORDS = frozenset({
    "a", "an", "and", "at", "by", "conference", "for", "from", "in",
    "keynote", "of", "on", "or", "session", "talk", "the", "to", "with",
})
EVENT_STOP_WORDS = frozenset({
    "a", "an", "annual", "at", "conference", "conf", "convention", "day",
    "days", "edition", "event", "events", "meetup", "meetups", "of", "open",
    "summit", "the", "webinar", "webinars",
})
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
        word for word in WORD_RE.findall(value.casefold())
        if word not in stop_words and len(word) > 1
    ]


def normalized_words(value: str) -> set[str]:
    """Return significant title words for overlap and clip-marker checks."""
    return set(_ordered_words(value, TITLE_STOP_WORDS))


def _contains_sequence(haystack: list[str] | EventAlias, needle: EventAlias) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(tuple(haystack[index:index + width]) == needle
               for index in range(len(haystack) - width + 1))


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
    lead = tuple(_ordered_words(expected[:separator.start()], TITLE_STOP_WORDS))
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
        minimum = 1 if len(expected_words) == 1 else max(
            2, (len(expected_words) + 1) // 2)
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
        contexts.append(title[at_matches[-1].end():])
    chunks = EVENT_CONTEXT_SEPARATOR_RE.split(title)
    if len(chunks) > 1:
        contexts.extend(
            chunk for chunk in (chunks[0], chunks[-1])
            if YEAR_RE.search(chunk)
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
            if (
                len(alias) == 1
                and alias[0] in AMBIGUOUS_EVENT_ALIASES
            ):
                continue
            contiguous = _contains_sequence(context, alias)
            ordered = (
                len(alias) > 1
                and _contains_ordered_subsequence(context, alias)
            )
            if not contiguous and not ordered:
                continue
            if any(_contains_sequence(existing, alias)
                   for existing in context_matches):
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
    agrees = any(
        _aliases_compatible(catalog_alias, mention) for mention in mentions
    )
    return agrees, catalog_alias, mentions

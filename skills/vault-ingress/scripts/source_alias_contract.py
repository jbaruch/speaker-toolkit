"""Owner-reviewed, inactive same-delivery YouTube identities.

An alias is an identity judgment, never an acquisition capability or analysis
receipt. Edges retain the identity actually compared by the reviewer; a later
official-source promotion may extend that chain, but every edge must end at the
talk's one current source. No title heuristic creates an edge.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
import math
import re
from typing import Any, NoReturn
from urllib.parse import parse_qs, urlparse


SOURCE_ALIAS_SCHEMA_VERSION = 1
PROMOTED_SOURCE_ALIAS_SCHEMA_VERSION = 2
MAX_RETIRED_ALIAS_DEPTH = 32
PRIOR_SOURCE_FIELDS = frozenset(
    {"video_url", "youtube_id", "source_identity", "status", "reprocess_reason"}
)
RELATIONSHIPS = frozenset(
    {"valid_duplicate", "mirror", "superseded_by_official_upload"}
)
COMPARISON_METHODS = frozenset({"recording_review", "transcript", "artifact"})
MAX_ALIASES = 10000
MAX_TEXT_LENGTH = 16384
RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "talk_filename",
        "catalog_title",
        "source_type",
        "alias",
        "canonical",
        "relationship",
        "event",
        "comparison",
        "reviewer",
        "verified_at",
        "canonical_choice_reason",
    }
)
PROVIDER_FIELDS = frozenset(
    {
        "provider",
        "video_id",
        "url",
        "title",
        "uploader",
        "upload_date",
        "duration_seconds",
        "captured_at",
    }
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


class SourceAliasError(ValueError):
    """A closed alias record or its owner binding is invalid."""


def _refuse(label: str, detail: str) -> NoReturn:
    raise SourceAliasError(
        f"{label}: {detail}; review and repair through the alias owner"
    )


def _shape(value: Any, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        _refuse(label, "unsupported record shape")
    return value


def _text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > MAX_TEXT_LENGTH
    ):
        _refuse(label, "expected bounded nonempty trimmed text")
    return value


def _missing(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"$missing"}
        and value["$missing"] is True
    )


def _timestamp(value: Any, label: str) -> None:
    text = _text(value, label)
    _date(text[:10], label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceAliasError(
            f"{label}: supply a timezone-aware ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _refuse(label, "timestamp has no timezone")


def _date(value: Any, label: str) -> None:
    # Pin the portable calendar-date spelling instead of inheriting additional
    # basic/week-date forms from newer Python fromisoformat implementations.
    text = _text(value, label)
    if DATE_RE.fullmatch(text) is None:
        _refuse(label, "expected YYYY-MM-DD calendar date")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise SourceAliasError(f"{label}: supply a valid calendar date") from exc


def _url(value: Any, label: str) -> str:
    text = _text(value, label)
    try:
        parsed = urlparse(text)
        port = parsed.port
    except ValueError as exc:
        raise SourceAliasError(f"{label}: supply a valid HTTP(S) evidence URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 80, 443}
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in text)
    ):
        _refuse(label, "invalid HTTP(S) evidence URL")
    return text


def youtube_identity(value: Any) -> str | None:
    # Resolve lazily: tracking_database owns this contract and ingress_contract
    # re-exports the talk schema from tracking_database. No parsing runs during
    # import, so both import orders use the existing provider parser safely.
    from ingress_contract import parse_youtube_id

    try:
        return parse_youtube_id(value)
    except ValueError:
        return None


def _provider(value: Any, label: str) -> Mapping[str, Any]:
    record = _shape(value, PROVIDER_FIELDS, label)
    url = _url(record["url"], f"{label}.url")
    identity = youtube_identity(url)
    parsed = urlparse(url)
    if (
        record["provider"] != "youtube"
        or identity is None
        or record["video_id"] != identity
        or (parsed.path == "/watch" and len(parse_qs(parsed.query).get("v", [])) != 1)
    ):
        _refuse(label, "unsupported provider or URL/ID disagreement")
    for field in ("title", "uploader"):
        _text(record[field], f"{label}.{field}")
    _date(record["upload_date"], f"{label}.upload_date")
    duration = record["duration_seconds"]
    if (
        type(duration) not in {int, float}
        or not 0 < duration <= 100000000
        or not math.isfinite(duration)
    ):
        _refuse(label, "provider duration must be positive and finite")
    _timestamp(record["captured_at"], f"{label}.captured_at")
    return record


def _validate_alias_record(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _refuse(label, "unsupported record shape")
    version = value.get("schema_version")
    if type(version) is not int or version not in {
        SOURCE_ALIAS_SCHEMA_VERSION,
        PROMOTED_SOURCE_ALIAS_SCHEMA_VERSION,
    }:
        _refuse(label, "unsupported source-alias schema version")
    fields = RECORD_FIELDS
    if version == PROMOTED_SOURCE_ALIAS_SCHEMA_VERSION:
        fields = fields | {"prior_state", "retired_alias"}
    record = _shape(value, fields, label)
    for field in ("talk_filename", "catalog_title", "reviewer"):
        _text(record[field], f"{label}.{field}")
    if (
        record["source_type"] != "video"
        or not isinstance(record["relationship"], str)
        or record["relationship"] not in RELATIONSHIPS
    ):
        _refuse(label, "unsupported source lane or relationship")
    if record["canonical_choice_reason"] is not None:
        _text(record["canonical_choice_reason"], f"{label}.canonical_choice_reason")
    _timestamp(record["verified_at"], f"{label}.verified_at")
    alias = _provider(record["alias"], f"{label}.alias")
    canonical = _provider(record["canonical"], f"{label}.canonical")
    if alias["video_id"] == canonical["video_id"]:
        _refuse(label, "an alias cannot name its own canonical identity")
    event = _shape(
        record["event"],
        frozenset({"url", "conference", "date", "speakers"}),
        f"{label}.event",
    )
    event_url = _url(event["url"], f"{label}.event.url")
    if youtube_identity(event_url) in {alias["video_id"], canonical["video_id"]}:
        _refuse(label, "event evidence must be independent of the two provider pages")
    _text(event["conference"], f"{label}.event.conference")
    _date(event["date"], f"{label}.event.date")
    speakers = event["speakers"]
    if not isinstance(speakers, list) or not speakers:
        _refuse(label, "independent event evidence must identify the speakers")
    for speaker in speakers:
        _text(speaker, f"{label}.event.speakers")
    if len(speakers) != len(set(speakers)):
        _refuse(label, "event speakers must be unique")
    comparison = _shape(
        record["comparison"],
        frozenset(
            {
                "method",
                "summary",
                "canonical_sha256",
                "alias_sha256",
                "agreement_basis_points",
            }
        ),
        f"{label}.comparison",
    )
    if (
        not isinstance(comparison["method"], str)
        or comparison["method"] not in COMPARISON_METHODS
    ):
        _refuse(label, "equivalence requires recording, transcript, or artifact review")
    _text(comparison["summary"], f"{label}.comparison.summary")
    for field in ("canonical_sha256", "alias_sha256"):
        digest = comparison[field]
        if digest is None and comparison["method"] == "recording_review":
            continue
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            _refuse(
                label, "comparison artifact hashes must identify the reviewed bytes"
            )
    agreement = comparison["agreement_basis_points"]
    if agreement is not None and (
        type(agreement) is not int or not 0 <= agreement <= 10000
    ):
        _refuse(label, "agreement must be null or integer basis points")
    if version == PROMOTED_SOURCE_ALIAS_SCHEMA_VERSION:
        if (
            record["relationship"] != "superseded_by_official_upload"
            or record["canonical_choice_reason"] is None
        ):
            _refuse(
                label, "promotion requires the official-upload relationship and reason"
            )
        prior = _shape(
            record["prior_state"],
            PRIOR_SOURCE_FIELDS | {"schema_version"},
            f"{label}.prior_state",
        )
        if type(prior["schema_version"]) is not int or prior["schema_version"] != 1:
            _refuse(label, "unsupported prior-source-state schema version")
        old_url = _url(prior["video_url"], f"{label}.prior_state.video_url")
        old_id = prior["youtube_id"]
        if youtube_identity(old_url) != alias["video_id"] or (
            not _missing(old_id) and old_id not in (None, "", alias["video_id"])
        ):
            _refuse(
                label, "superseded state disagrees with the prior canonical identity"
            )
        for field in ("status", "reprocess_reason"):
            old = prior[field]
            if old is not None and not _missing(old):
                _text(old, f"{label}.prior_state.{field}")
        identity = prior["source_identity"]
        if identity is not None and not isinstance(identity, Mapping):
            _refuse(label, "historical source identity must be an object or null")
    return record


def validate_alias_record(value: Any, *, label: str = "source_alias") -> None:
    """Read both generations and bounded, inactive retired-decision history."""
    record = _validate_alias_record(value, label=label)
    depth = 0
    while record["schema_version"] == PROMOTED_SOURCE_ALIAS_SCHEMA_VERSION:
        retired = record["retired_alias"]
        if retired is None:
            return
        depth += 1
        if depth > MAX_RETIRED_ALIAS_DEPTH:
            _refuse(label, "retired alias history exceeds the supported depth")
        parent = _validate_alias_record(retired, label=f"{label}.retired_alias")
        if (
            parent["talk_filename"] != record["talk_filename"]
            or parent["alias"]["video_id"] != record["canonical"]["video_id"]
        ):
            _refuse(label, "retired decision does not belong to the promoted identity")
        record = parent


def active_identity(talk: Mapping[str, Any]) -> str | None:
    identity = youtube_identity(talk.get("video_url"))
    stored = talk.get("youtube_id")
    if stored is not None and (
        not isinstance(stored, str) or stored not in {"", identity}
    ):
        return None
    return identity


def validate_alias_database(database: Mapping[str, Any]) -> None:
    """Validate shape, ownership, rejected overlap, and bounded acyclic lineage."""
    records = database.get("source_aliases", [])
    if not isinstance(records, list) or len(records) > MAX_ALIASES:
        _refuse("source_aliases", "expected a bounded array")
    if not records:
        return
    talks = {talk["filename"]: talk for talk in database["talks"]}
    active_ids = {
        identity
        for talk in talks.values()
        for identity in (
            youtube_identity(talk.get("video_url")),
            talk.get("youtube_id"),
        )
        if isinstance(identity, str) and identity
    }
    edges: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records):
        label = f"source_aliases[{index}]"
        validate_alias_record(record, label=label)
        filename = record["talk_filename"]
        if filename not in talks:
            _refuse(label, "alias names no canonical talk")
        identity = _text(record["alias"]["video_id"], f"{label}.alias.video_id")
        if identity in active_ids:
            _refuse(label, "accepted alias overlaps an active canonical source")
        if identity in edges:
            _refuse(label, "duplicate alias ownership")
        rejected = {
            youtube_identity(rejection["url"])
            for rejection in talks[filename].get("source_rejections", [])
            if rejection["source_type"] == "video"
        }
        if identity in rejected or record["canonical"]["video_id"] in rejected:
            _refuse(label, "accepted source overlaps the talk's rejection ledger")
        edges[identity] = record
    resolved: dict[str, str] = {}
    for identity, record in edges.items():
        filename = record["talk_filename"]
        terminal = active_identity(talks[filename])
        if terminal is None:
            _refuse("source_aliases", "talk has no agreeing canonical URL/ID")
        visited = {identity}
        target = record["canonical"]["video_id"]
        while target != terminal:
            if resolved.get(target) == filename:
                break
            if target in visited:
                _refuse("source_aliases", "alias lineage contains a cycle")
            visited.add(target)
            parent = edges.get(target)
            if parent is None or parent["talk_filename"] != filename:
                _refuse(
                    "source_aliases",
                    "alias lineage does not end at its talk's canonical source",
                )
            target = parent["canonical"]["video_id"]
        for visited_identity in visited:
            resolved[visited_identity] = filename


def matched_alias(
    database: Mapping[str, Any], talk: Mapping[str, Any], url: Any
) -> Mapping[str, Any] | None:
    """Look up only a reviewed identity; callers first validate the database."""
    identity = youtube_identity(url)
    if identity is None:
        return None
    return next(
        (
            record
            for record in database.get("source_aliases", [])
            if record["talk_filename"] == talk.get("filename")
            and record["alias"]["video_id"] == identity
        ),
        None,
    )

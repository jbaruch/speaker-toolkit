"""Provider-qualified talk source identity (#427).

A talk published anywhere other than YouTube could not carry transcript or
video evidence, because every binding lane resolved a bare ``youtube_id``.
These tests pin the shared ingress_contract those lanes now resolve instead: the
provider parsers, the binding token, and the guarantee that a YouTube talk's
token is still the bare ID every stored artifact was named for.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", ("youtube", "dQw4w9WgXcQ")),
        ("https://youtu.be/dQw4w9WgXcQ", ("youtube", "dQw4w9WgXcQ")),
        ("https://vimeo.com/1223667266", ("vimeo", "1223667266")),
        ("https://vimeo.com/1223667266/9f3c1a2b4d", ("vimeo", "1223667266")),
        ("https://player.vimeo.com/video/1223667266", ("vimeo", "1223667266")),
        ("https://vimeo.com/channels/staffpicks/1223667266", ("vimeo", "1223667266")),
        (
            "https://vimeo.com/groups/javazone/videos/1223667266",
            ("vimeo", "1223667266"),
        ),
        ("https://vimeo.com/event/55555/videos/1223667266", ("vimeo", "1223667266")),
        ("vimeo.com/1223667266", ("vimeo", "1223667266")),
        ("https://www.infoq.com/presentations/java-puzzle/", ("infoq", "java-puzzle")),
        ("https://www.infoq.com/presentations/java-puzzle", ("infoq", "java-puzzle")),
        ("https://infoq.com/presentations/Java-Puzzle/", ("infoq", "java-puzzle")),
    ],
)
def test_supported_provider_urls_resolve_to_an_identity(
    ingress_contract, url, expected
):
    identity = ingress_contract.parse_source_identity(url)
    assert identity is not None
    assert (identity.provider, identity.video_id) == expected


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "   ",
        42,
        "https://example.com/videos/1223667266",
        "https://vimeo.com/abcdefgh",
        "https://vimeo.com/12345",
        "https://vimeo.com/channels/staffpicks",
        "https://www.infoq.com/podcasts/java-puzzle/",
        "https://www.infoq.com/presentations/",
        "ftp://vimeo.com/1223667266",
    ],
)
def test_unsupported_or_malformed_sources_resolve_to_nothing(ingress_contract, url):
    assert ingress_contract.parse_source_identity(url) is None


def test_youtube_binding_token_is_the_bare_id(ingress_contract):
    """Every artifact named before this change keeps binding to its own name."""
    identity = ingress_contract.parse_source_identity("https://youtu.be/dQw4w9WgXcQ")
    assert identity is not None
    assert identity.binding_token == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    ("provider", "video_id", "token"),
    [
        ("vimeo", "1223667266", "vimeo-1223667266"),
        ("infoq", "java-puzzle", "infoq-java-puzzle"),
    ],
)
def test_other_providers_carry_their_prefix(
    ingress_contract, provider, video_id, token
):
    assert ingress_contract.SourceIdentity(provider, video_id).binding_token == token


def test_two_providers_sharing_an_id_get_different_tokens(ingress_contract):
    vimeo = ingress_contract.SourceIdentity("vimeo", "123456789012")
    infoq = ingress_contract.SourceIdentity("infoq", "123456789012")
    assert vimeo.binding_token != infoq.binding_token


def test_stored_youtube_id_outranks_the_active_url(ingress_contract):
    """A YouTube talk resolves exactly as it did before providers existed."""
    talk = {
        "youtube_id": "dQw4w9WgXcQ",
        "video_url": "https://vimeo.com/1223667266",
    }
    identity = ingress_contract.talk_source_identity(talk)
    assert identity == ingress_contract.SourceIdentity("youtube", "dQw4w9WgXcQ")
    assert ingress_contract.talk_binding_token(talk) == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    ("talk", "token"),
    [
        ({"video_url": "https://vimeo.com/1223667266"}, "vimeo-1223667266"),
        (
            {"video_url": "https://www.infoq.com/presentations/java-puzzle/"},
            "infoq-java-puzzle",
        ),
        ({"video_url": "https://youtu.be/dQw4w9WgXcQ"}, "dQw4w9WgXcQ"),
        ({"video_url": "https://example.com/talk"}, None),
        ({"youtube_id": "not-an-id"}, None),
        ({}, None),
    ],
)
def test_talk_binding_token_resolves_from_the_active_source(
    ingress_contract, talk, token
):
    assert ingress_contract.talk_binding_token(talk) == token


@pytest.mark.parametrize(
    ("provider", "video_id", "valid"),
    [
        ("youtube", "dQw4w9WgXcQ", True),
        ("vimeo", "1223667266", True),
        ("infoq", "java-puzzle", True),
        ("youtube", "short", False),
        ("vimeo", "not-numeric", False),
        ("infoq", "Upper-Case", False),
        ("twitch", "1223667266", False),
        ("vimeo", 1223667266, False),
        (None, "1223667266", False),
    ],
)
def test_declared_pairs_validate_against_their_provider(
    ingress_contract, provider, video_id, valid
):
    identity = ingress_contract.source_identity_for(provider, video_id)
    assert (identity is not None) is valid


def test_supported_providers_are_the_ones_with_parsers(ingress_contract):
    assert set(ingress_contract.SUPPORTED_SOURCE_PROVIDERS) == set(
        ingress_contract._PROVIDER_ID_PATTERNS
    )

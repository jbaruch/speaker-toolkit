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
        ("vimeo", "1223667266", "vimeo+1223667266"),
        ("infoq", "java-puzzle", "infoq+java-puzzle"),
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
        ({"video_url": "https://vimeo.com/1223667266"}, "vimeo+1223667266"),
        (
            {"video_url": "https://www.infoq.com/presentations/java-puzzle/"},
            "infoq+java-puzzle",
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


# One representative published URL per supported provider. The test below is
# what keeps a provider from being declared supported without a working parser.
PROVIDER_SAMPLE_URLS = {
    "youtube": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "vimeo": "https://vimeo.com/1223667266",
    "infoq": "https://www.infoq.com/presentations/java-puzzle/",
}


def test_every_supported_provider_has_a_sample_url(ingress_contract):
    """A missing sample would make the parser test below vacuous."""
    assert set(ingress_contract.SUPPORTED_SOURCE_PROVIDERS) == set(PROVIDER_SAMPLE_URLS)


@pytest.mark.parametrize("provider", sorted(PROVIDER_SAMPLE_URLS))
def test_every_supported_provider_parses_a_real_url(ingress_contract, provider):
    identity = ingress_contract.parse_source_identity(PROVIDER_SAMPLE_URLS[provider])
    assert identity is not None
    assert identity.provider == provider
    assert ingress_contract.source_identity_for(provider, identity.video_id) == identity


@pytest.mark.parametrize(
    "token",
    ["dQw4w9WgXcQ", "vimeo+1223667266", "infoq+java-puzzle"],
)
def test_every_identity_produces_a_recognized_binding_token(ingress_contract, token):
    assert ingress_contract.is_source_binding_token(token) is True


@pytest.mark.parametrize(
    "token",
    ["vimeo+1234", "infoq+Upper-Case", "vimeo+", "twitch+1223667266", "", None, 11],
)
def test_malformed_tokens_bind_nothing(ingress_contract, token):
    assert ingress_contract.is_source_binding_token(token) is False


@pytest.mark.parametrize(
    ("provider", "video_id", "colliding_youtube_id"),
    # A Vimeo ID is at least six digits, so `vimeo-<id>` was never 11
    # characters and never collided. InfoQ slugs are the real surface.
    [
        ("infoq", "kafka", "infoq-kafka"),
        ("infoq", "abc", "infoq-abc12"),
    ],
)
def test_no_token_can_be_mistaken_for_a_youtube_id(
    ingress_contract, provider, video_id, colliding_youtube_id
):
    """The separator is outside the YouTube alphabet, so overlap is unrepresentable.

    With an in-alphabet separator the InfoQ slug `kafka` and the YouTube ID
    `infoq-kafka` produced one token, and every ownership, alias, and duplicate
    check keyed on it conflated two different recordings.
    """
    token = ingress_contract.SourceIdentity(provider, video_id).binding_token
    assert token != colliding_youtube_id
    assert ingress_contract.token_source_identity(token) == (
        ingress_contract.SourceIdentity(provider, video_id)
    )
    assert ingress_contract.token_source_identity(colliding_youtube_id) == (
        ingress_contract.SourceIdentity("youtube", colliding_youtube_id)
    )


@pytest.mark.parametrize(
    ("provider", "video_id"),
    [
        ("youtube", "dQw4w9WgXcQ"),
        ("vimeo", "1223667266"),
        ("infoq", "java-puzzle"),
    ],
)
def test_the_token_round_trips_back_to_its_identity(
    ingress_contract, provider, video_id
):
    identity = ingress_contract.SourceIdentity(provider, video_id)
    assert ingress_contract.token_source_identity(identity.binding_token) == identity


def test_the_separator_is_outside_the_youtube_alphabet(ingress_contract):
    """The property every collision guarantee above rests on."""
    assert (
        ingress_contract.YOUTUBE_ID_RE.fullmatch(
            ingress_contract.SOURCE_PROVIDER_SEPARATOR * 11
        )
        is None
    )


# A URL `urlparse` itself rejects. Every parser here is documented total, so a
# malformed URL is an absent identity rather than an escaping ValueError that
# would take a caller's actionable message with it (#427 review).
MALFORMED_URLS = ["https://[broken", "https://[", "http://[::1", "//[bad]"]


@pytest.mark.parametrize("url", MALFORMED_URLS)
def test_a_malformed_url_is_an_absent_identity_not_an_exception(ingress_contract, url):
    assert ingress_contract.parse_source_identity(url) is None
    assert ingress_contract.parse_youtube_id(url) is None
    assert ingress_contract.parse_vimeo_id(url) is None
    assert ingress_contract.parse_infoq_id(url) is None
    assert ingress_contract.parse_google_drive_id(url) is None
    assert ingress_contract.is_youtube_url(url) is False


@pytest.mark.parametrize("url", MALFORMED_URLS)
def test_a_malformed_url_reads_as_no_acquisition_source(ingress_contract, url):
    assert ingress_contract.has_remote_video_acquisition({"video_url": url}) is False
    assert ingress_contract.has_remote_slide_acquisition({"slides_url": url}) is False
    assert ingress_contract.talk_source_identity({"video_url": url}) is None

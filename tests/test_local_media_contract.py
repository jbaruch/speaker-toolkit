"""Deterministic resource/fact checks for the generic media owner."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import stat

import pytest

from conftest import SCRIPTS_VI, _import_script


@pytest.fixture
def contract():
    return _import_script(
        Path(SCRIPTS_VI) / "local_media_contract.py", "local_media_contract"
    )


def _document(format_name="mp3", **updates):
    result = {
        "format": {"format_name": format_name, "duration": "60.25"},
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "mp3",
                "channels": 1,
                "sample_rate": "16000",
                "duration": "60.25",
            }
        ],
    }
    result.update(updates)
    return result


def _generation():
    from artifact_supervisor import FileGeneration

    return FileGeneration(256, 10, 11, 1, 2, stat.S_IFREG | 0o600)


def _payload(contract):
    from artifact_supervisor import DiagnosticReceipt

    return {
        "schema_version": 1,
        "source_sha256": "a" * 64,
        "source_size_bytes": 256,
        "parser_diagnostics": DiagnosticReceipt.empty().to_dict(),
        **contract.parse_media_facts(_document(), "mp3"),
    }


@pytest.mark.parametrize(
    "suffix,format_name",
    [
        (".mp3", "mp3"),
        (".wav", "wav"),
        (".m4a", "mov,mp4,m4a,3gp,3g2,mj2"),
        (".mp4", "mov,mp4,m4a,3gp,3g2,mj2"),
        (".mov", "mov"),
        (".webm", "matroska,webm"),
        (".mkv", "matroska,webm"),
    ],
)
def test_closed_container_policy_accepts_audio_with_optional_video(
    contract, suffix, format_name
):
    document = _document(format_name)
    document["streams"].extend(
        [
            {"codec_type": "video", "duration": "60.25"},
            {"codec_type": "video", "disposition": {"attached_pic": 1}},
            {"codec_type": "subtitle"},
        ]
    )
    facts = contract.parse_media_facts(document, contract.CONTAINER_BY_SUFFIX[suffix])
    assert facts["stream_count"] == 4
    assert facts["audio_stream_count"] == 1
    assert facts["video_stream_count"] == 1
    assert facts["attached_picture_count"] == 1
    assert facts["other_stream_count"] == 1
    assert facts["duration_seconds"] == 60.25


def test_audio_only_mp4_and_cover_art_are_not_delivery_video(contract):
    document = _document("mp4")
    document["streams"].append(
        {"codec_type": "video", "disposition": {"attached_pic": "1"}}
    )
    facts = contract.parse_media_facts(document, "iso_bmff")
    assert facts["video_stream_count"] == 0
    assert facts["audio_stream_count"] == 1
    assert facts["attached_picture_count"] == 1


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"streams": [{"codec_type": "video"}]}, "media_no_audio_stream"),
        ({"streams": []}, "media_no_audio_stream"),
        ({"streams": [None]}, "media_parser_rejected"),
        (
            {"format": {"format_name": "wav", "duration": "1"}},
            "media_invalid_container",
        ),
        (
            {"format": {"format_name": "mp3,unknown", "duration": "1"}},
            "media_invalid_container",
        ),
        ({"streams": [{"codec_type": "audio"}] * 65}, "media_stream_limit"),
        (
            {"format": {"format_name": "mp3", "duration": "28801"}},
            "media_duration_limit",
        ),
        ({"programs": [{}]}, "media_parser_rejected"),
        ({"extra": True}, "media_parser_rejected"),
    ],
)
def test_invalid_container_or_stream_facts_fail_closed(contract, change, reason):
    with pytest.raises(contract.LocalMediaError, match=reason):
        contract.parse_media_facts(_document(**change), "mp3")


def test_duration_falls_back_to_real_stream_not_attached_picture(contract):
    document = _document()
    document["format"].pop("duration")
    document["streams"].append(
        {"codec_type": "video", "disposition": {"attached_pic": 1}, "duration": "28000"}
    )
    facts = contract.parse_media_facts(document, "mp3")
    assert facts["duration_source"] == "stream"
    assert facts["duration_seconds"] == 60.25


@pytest.mark.parametrize(
    "field,value",
    [
        ("codec_name", "unknown"),
        ("channels", 0),
        ("channels", True),
        ("sample_rate", "0"),
        ("sample_rate", "NaN"),
    ],
)
def test_at_least_one_audio_stream_must_be_usable(contract, field, value):
    document = _document()
    document["streams"][0][field] = value
    with pytest.raises(contract.LocalMediaError, match="media_no_usable_audio_stream"):
        contract.parse_media_facts(document, "mp3")
    document["streams"].append(_document()["streams"][0])
    assert contract.parse_media_facts(document, "mp3")["audio_stream_count"] == 2


def test_boolean_cover_art_flag_is_not_an_integer_fact(contract):
    document = _document()
    document["streams"].append(
        {"codec_type": "video", "disposition": {"attached_pic": True}}
    )
    with pytest.raises(contract.LocalMediaError, match="media_parser_rejected"):
        contract.parse_media_facts(document, "mp3")


@pytest.mark.parametrize("duration", ["NaN", "Infinity", "garbage", True, 0, -1])
def test_malformed_format_duration_cannot_fall_back_to_a_short_stream(
    contract, duration
):
    document = _document()
    document["format"]["duration"] = duration
    with pytest.raises(contract.LocalMediaError, match="media_parser_rejected"):
        contract.parse_media_facts(document, "mp3")


def test_overlong_stream_cannot_hide_behind_a_short_format_duration(contract):
    document = _document()
    document["streams"][0]["duration"] = "28801"
    with pytest.raises(contract.LocalMediaError, match="media_duration_limit"):
        contract.parse_media_facts(document, "mp3")


@pytest.mark.parametrize(
    "value", [True, 0, -1, float("nan"), float("inf"), 10**400, "60"]
)
def test_untrusted_duration_cannot_become_evidence(contract, value):
    assert contract.positive_duration(value) is None


@pytest.mark.parametrize("value", [True, 0, -1, 8 * 1024**3 + 1, 1.0, "256"])
def test_media_input_limit_is_exact_and_positive(contract, value):
    with pytest.raises(contract.LocalMediaError, match="media_size_limit"):
        contract.validate_media_size(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("source_sha256", "private/path"),
        ("source_size_bytes", 257),
        ("audio_stream_count", 0),
        ("stream_count", 2),
        ("duration_seconds", True),
        ("duration_source", []),
        ("container_family", []),
        (
            "parser_diagnostics",
            {"byte_count": 1, "sha256": "a" * 64, "truncated": False},
        ),
    ],
)
def test_worker_probe_payload_is_closed_and_generation_bound(contract, field, value):
    payload = _payload(contract)
    payload[field] = value
    with pytest.raises(contract.LocalMediaError):
        contract.decode_media_probe(payload, _generation(), None)


@pytest.mark.parametrize("attributes", [0x1000, 0x40000, 0x400000, 0x400])
def test_offline_recall_and_reparse_facts_do_not_authorize_reads(contract, attributes):
    generation = replace(_generation(), file_attributes=attributes)
    with pytest.raises(contract.LocalMediaError):
        contract.decode_media_probe(_payload(contract), generation, None)


def test_video_fact_reuse_is_zero_io(contract, monkeypatch):
    from artifact_metadata import ArtifactAvailability
    from artifact_supervisor import DiagnosticReceipt
    import video_evidence

    probe = video_evidence.VideoArtifactProbe(
        generation=_generation(),
        root_generation=None,
        availability=ArtifactAvailability.from_generation(_generation()),
        source_sha256="a" * 64,
        source_size_bytes=256,
        duration_seconds=60.25,
        duration_source="format",
        container_family="iso_bmff",
        stream_count=2,
        video_stream_count=1,
        audio_stream_count=1,
        attached_picture_count=0,
        other_stream_count=0,
        parser_diagnostics=DiagnosticReceipt.empty(),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("video receipt reuse performed artifact I/O")

    for name in (
        "probe_video_artifact",
        "_run_bounded_metadata_worker",
        "_run_bounded_video_probe",
        "_copy_source_snapshot",
        "_digest_exact_generation",
    ):
        monkeypatch.setattr(video_evidence, name, forbidden)
    result = contract.reuse_video_probe(probe)
    assert result.generation == probe.generation
    assert result.source_sha256 == probe.source_sha256
    assert result.duration_seconds == probe.duration_seconds
    with pytest.raises(contract.LocalMediaError, match="media_no_audio_stream"):
        contract.reuse_video_probe(replace(probe, audio_stream_count=0, stream_count=1))


def test_whisper_payload_discards_provider_only_objects(contract):
    value = {
        "text": "Synthetic speech",
        "language": "en",
        "segments": [
            {
                "text": "Synthetic speech",
                "start": 0.0,
                "end": 2.0,
                "tokens": object(),
                "provider_extra": "private/path",
            }
        ],
        "model": object(),
    }
    assert contract.bounded_whisper_result(value) == {
        "text": "Synthetic speech",
        "language": "en",
        "segments": [{"text": "Synthetic speech", "start": 0.0, "end": 2.0}],
    }


@pytest.mark.parametrize(
    "update,reason",
    [
        ({"text": ""}, "whisper_result_invalid"),
        ({"text": "x" * (2 * 1024 * 1024 + 1)}, "whisper_text_limit"),
        ({"text": "\ud800"}, "whisper_result_invalid"),
        ({"language": "private/path"}, "whisper_language_invalid"),
        ({"language": "x" * 33}, "whisper_language_invalid"),
        ({"segments": iter(())}, "whisper_segments_invalid"),
        ({"segments": [None] * 20001}, "whisper_segment_limit"),
        ({"segments": [None]}, "whisper_segments_invalid"),
        ({"segments": [{"text": "x" * 16385}]}, "whisper_segment_text_limit"),
    ],
)
def test_whisper_resource_failures_are_path_neutral(contract, update, reason):
    with pytest.raises(contract.LocalMediaError, match=reason) as caught:
        contract.bounded_whisper_result(
            {"text": "Synthetic speech", "language": "en", **update}
        )
    assert "private/path" not in str(caught.value)


def test_optional_timing_downgrade_still_checks_every_segment_ceiling(contract):
    value = {
        "text": "Synthetic speech",
        "segments": [{"text": "Synthetic speech", "start": None, "end": 2}],
    }
    assert contract.bounded_whisper_result(value)["segments"] is None
    value["segments"].append({"text": "x" * 16385, "start": 2, "end": 3})
    with pytest.raises(contract.LocalMediaError, match="whisper_segment_text_limit"):
        contract.bounded_whisper_result(value)

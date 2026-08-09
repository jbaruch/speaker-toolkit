"""The shared outer-boundary diagnostic contract (#203).

Six vault-ingress entrypoints publish failures through this module. The
path-neutrality guarantee is asserted once here rather than re-derived in each
entrypoint's suite; each entrypoint's own tests assert its error code, its
state fields, and that stdout stays clean.
"""

import io
import json

import pytest


def _raised(exc):
    """Raise `exc` so it carries a real traceback for the frame extractor.

    `pytest.raises` gives the caught instance without a broad handler, which
    `rules/error-handling.md` reserves for outer process boundaries.
    """
    with pytest.raises(type(exc)) as excinfo:
        raise exc
    return excinfo.value


def test_sanitized_frames_report_location_without_paths_or_text(
        failure_diagnostics):
    """`no-secrets` forbids exception text; the frames replace it."""
    caught = _raised(RuntimeError("token=SECRET at /private/vault/creds.json"))

    frames = failure_diagnostics.sanitized_frames(caught)

    assert frames, "the failing code location must be reported"
    for frame in frames:
        assert ":" in frame and " in " in frame
        assert "/" not in frame          # basename only, never a host path
        assert "SECRET" not in frame


def test_failure_document_carries_the_type_but_never_the_message(
        failure_diagnostics):
    """The type says which failure it was; the message would say where."""
    caught = _raised(FileNotFoundError(2, "No such file", "/private/vault/db.json"))

    document = failure_diagnostics.unexpected_failure_document(
        caught, "example_unexpected_failure"
    )

    assert document["error"] == "example_unexpected_failure"
    assert document["error_type"] == "FileNotFoundError"
    serialized = json.dumps(document)
    assert "/private/vault/db.json" not in serialized
    assert "No such file" not in serialized


def test_state_fields_merge_into_the_document(failure_diagnostics):
    """A mutating entrypoint reports commit position beside the failure."""
    caught = _raised(RuntimeError("boom"))

    document = failure_diagnostics.unexpected_failure_document(
        caught, "example_unexpected_failure", state={"database_written": True}
    )

    assert document["database_written"] is True


def test_state_adds_fields_beside_the_identity(failure_diagnostics):
    """State extends the document; it does not reshape it."""
    caught = _raised(RuntimeError("boom"))

    document = failure_diagnostics.unexpected_failure_document(
        caught,
        "example_unexpected_failure",
        state={"analyses_written": False},
    )

    assert set(document) == {
        "error", "error_type", "origin", "analyses_written"
    }


def test_state_cannot_overwrite_the_error_identity(failure_diagnostics):
    """An entrypoint must not be able to rename its own failure.

    A caller that shadowed `error` would make every downstream consumer
    misclassify the failure — including the tests that gate each entrypoint on
    its own code.
    """
    caught = _raised(RuntimeError("boom"))

    document = failure_diagnostics.unexpected_failure_document(
        caught,
        "example_unexpected_failure",
        state={
            "error": "something_else",
            "error_type": "NotThisOne",
            "origin": ["forged.py:1 in nowhere"],
            "database_written": True,
        },
    )

    assert document["error"] == "example_unexpected_failure"
    assert document["error_type"] == "RuntimeError"
    assert document["origin"] != ["forged.py:1 in nowhere"]
    assert document["database_written"] is True, "non-identity state survives"
    assert failure_diagnostics.IDENTITY_FIELDS == {
        "error", "error_type", "origin"
    }


def test_emitted_failure_is_one_json_document_then_a_recovery_note(
        failure_diagnostics):
    """Callers parse line one; a human reads the rest."""
    caught = _raised(RuntimeError("boom at /private/vault/db.json"))
    stream = io.StringIO()

    failure_diagnostics.emit_unexpected_failure(
        caught,
        "example_unexpected_failure",
        "Nothing was written; retry the batch.",
        stream=stream,
    )

    lines = stream.getvalue().splitlines()
    payload = json.loads(lines[0])
    assert payload["error"] == "example_unexpected_failure"
    assert "Nothing was written; retry the batch." in stream.getvalue()
    assert "innermost last" in stream.getvalue()
    assert "Traceback" not in stream.getvalue()
    assert "/private/vault/db.json" not in stream.getvalue()


def test_emitted_document_is_key_ordered_for_stable_diffs(failure_diagnostics):
    """Operators diff these across runs; key order must not float."""
    caught = _raised(RuntimeError("boom"))
    stream = io.StringIO()

    failure_diagnostics.emit_unexpected_failure(
        caught, "example_unexpected_failure", "retry", state={"z": 1, "a": 2},
        stream=stream,
    )

    first_line = stream.getvalue().splitlines()[0]
    assert first_line == json.dumps(json.loads(first_line), sort_keys=True)

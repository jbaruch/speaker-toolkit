"""The shownotes analysis is the one bound to the exact delivery (#460)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import (
    CURRENT_ROOT_SCHEMA_VERSION,
    SCRIPTS_VI,
    _import_script,
    current_tracking_config,
)

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills/shownotes-publisher/scripts/find-talk-analysis.py"
)
PROCESSED = "2026-09-20"


def _talk(
    filename, title, conference, date, *, status="processed", processed=PROCESSED
):
    return {
        "filename": filename,
        "schema_version": 8,
        "status": status,
        "title": title,
        "conference": conference,
        "date": date,
        "processed_date": processed,
    }


ROBOCODERS = _talk(
    "2026-09-12-wearedevs-robocoders.md",
    "RoboCoders: Who Reviews the Reviewer?",
    "WeAreDevelopers NA",
    "2026-09-12",
)
ROBOCODERS_REPEAT = _talk(
    "2026-10-02-devoxx-robocoders.md",
    "RoboCoders: Who Reviews the Reviewer?",
    "Devoxx Belgium",
    "2026-10-02",
)


def _vault(tmp_path: Path, talks, *, root_version=None, config=None) -> Path:
    vault = tmp_path / "vault"
    (vault / "analyses").mkdir(parents=True)
    database = vault / "tracking-database.json"
    database.write_text(
        json.dumps(
            {
                "schema_version": root_version or CURRENT_ROOT_SCHEMA_VERSION,
                "config": config or current_tracking_config(),
                "talks": talks,
                "pptx_catalog": [],
                "qr_codes": [],
                "resources": [],
                "thumbnails": [],
                "confirmed_intents": [],
                "improvement_goals": [],
            }
        ),
        encoding="utf-8",
    )
    return database


def _analysis(database: Path, talk, *, processed=PROCESSED, title=None) -> Path:
    path = database.parent / "analyses" / talk["filename"]
    path.write_text(
        f"# Rhetoric Analysis: {title or talk['title']}\n\n"
        f"**Filename:** {talk['filename']}\n"
        f"**Processed:** {processed}\n"
        f"**Status:** {talk['status']}\n\n---\n\n## Rhetoric Notes\n\nBody.\n",
        encoding="utf-8",
    )
    return path


def _find(database: Path, *arguments: str):
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--database", str(database), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, json.loads(completed.stdout), completed.stderr


def _by_identity(talk):
    return (
        "--title",
        talk["title"],
        "--event",
        talk["conference"],
        "--date",
        talk["date"],
    )


def test_the_exact_delivery_binds_its_analysis(tmp_path):
    database = _vault(tmp_path, [ROBOCODERS, ROBOCODERS_REPEAT])
    analysis = _analysis(database, ROBOCODERS)
    _analysis(database, ROBOCODERS_REPEAT)

    code, payload, stderr = _find(
        database,
        "--title",
        "  robocoders:  who reviews the REVIEWER? ",
        "--event",
        "wearedevelopers na",
        "--date",
        "2026-09-12",
    )

    assert code == 0, stderr
    assert payload["binding"] == "bound"
    assert payload["talk"]["filename"] == ROBOCODERS["filename"]
    assert payload["analysis_path"] == str(analysis)
    assert len(payload["analysis_sha256"]) == 64
    # The verdict carries the checked bytes, so nothing reopens the path.
    assert payload["analysis_text"] == analysis.read_text(encoding="utf-8")


def test_a_filename_names_the_record_directly(tmp_path):
    database = _vault(tmp_path, [ROBOCODERS])
    _analysis(database, ROBOCODERS)
    code, payload, stderr = _find(database, "--filename", ROBOCODERS["filename"])
    assert code == 0, stderr
    assert payload["binding"] == "bound"


def test_a_similar_title_at_another_event_is_not_the_delivery(tmp_path):
    database = _vault(tmp_path, [ROBOCODERS_REPEAT])
    _analysis(database, ROBOCODERS_REPEAT)

    code, payload, _stderr = _find(database, *_by_identity(ROBOCODERS))

    assert code == 0
    assert payload["binding"] == "not_found"
    assert payload["talk"] is None
    # The same title elsewhere is named so the caller sees why it missed.
    assert [c["filename"] for c in payload["candidates"]] == [
        ROBOCODERS_REPEAT["filename"]
    ]
    # No record matched, so there is nothing vault-ingress could select.
    assert payload["handoff"] is None


def test_two_records_for_one_delivery_are_ambiguous(tmp_path):
    twin = {**ROBOCODERS, "filename": "2026-09-12-wearedevs-robocoders-2.md"}
    database = _vault(tmp_path, [ROBOCODERS, twin])
    code, payload, _stderr = _find(database, *_by_identity(ROBOCODERS))
    assert code == 0
    assert payload["binding"] == "ambiguous"
    assert len(payload["candidates"]) == 2


@pytest.mark.parametrize(
    "talk,write,binding,claimable",
    [
        ({**ROBOCODERS, "status": "pending"}, False, "not_processed", True),
        ({**ROBOCODERS, "status": "skipped_no_sources"}, False, "not_processed", False),
        (ROBOCODERS, False, "analysis_missing", False),
        (ROBOCODERS, "older", "analysis_stale", False),
        (ROBOCODERS, "other-title", "analysis_stale", False),
    ],
    ids=["pending", "sourceless", "no-file", "older-render", "other-talk-file"],
)
def test_an_unbound_analysis_hands_off_only_what_ingress_can_claim(
    tmp_path, talk, write, binding, claimable
):
    """A processed record with a bad render is not one the queue can claim."""
    database = _vault(tmp_path, [talk])
    if write == "older":
        _analysis(database, talk, processed="2026-01-01")
    elif write == "other-title":
        _analysis(database, talk, title="A Different Talk")

    code, payload, stderr = _find(database, "--filename", talk["filename"])

    assert code == 0, stderr
    assert payload["binding"] == binding
    assert payload["talk"]["filename"] == talk["filename"]
    if claimable:
        assert payload["handoff"] == {
            "skill": "vault-ingress",
            "scope": "one_talk",
            "filename": talk["filename"],
            "title": talk["title"],
            "event": talk["conference"],
            "date": talk["date"],
        }
    else:
        assert payload["handoff"] is None


def test_a_symlinked_analysis_is_not_bound(tmp_path):
    database = _vault(tmp_path, [ROBOCODERS])
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("# Rhetoric Analysis: x\n", encoding="utf-8")
    (database.parent / "analyses" / ROBOCODERS["filename"]).symlink_to(elsewhere)
    code, payload, _stderr = _find(database, "--filename", ROBOCODERS["filename"])
    assert code == 0
    assert payload["binding"] == "analysis_missing"


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        ("--title", "T", "--event", "E"),
        ("--filename", "a.md", "--title", "T", "--event", "E", "--date", "D"),
        ("--filename", ""),
        ("--filename", "   "),
        ("--title", " ", "--event", " ", "--date", " "),
    ],
    ids=[
        "nothing",
        "partial-identity",
        "both",
        "empty-filename",
        "blank-filename",
        "blank-identity",
    ],
)
def test_the_delivery_must_be_named_one_way(tmp_path, arguments):
    database = _vault(tmp_path, [ROBOCODERS])
    code, payload, stderr = _find(database, *arguments)
    assert code == 2
    assert payload["reason_code"] == "invalid_arguments"
    assert payload["error"] in stderr


def test_a_legacy_database_is_handed_to_the_owner_migration(tmp_path):
    database = _vault(
        tmp_path, [ROBOCODERS], root_version=CURRENT_ROOT_SCHEMA_VERSION - 1
    )
    code, payload, _stderr = _find(database, "--filename", ROBOCODERS["filename"])
    assert code == 2
    assert payload["reason_code"] == "database_not_current"


def test_a_future_database_is_not_handed_to_the_migration(tmp_path):
    database = _vault(
        tmp_path, [ROBOCODERS], root_version=CURRENT_ROOT_SCHEMA_VERSION + 1
    )
    code, payload, _stderr = _find(database, "--filename", ROBOCODERS["filename"])
    assert code == 2
    assert payload["reason_code"] == "database_unsupported"
    assert "update speaker-toolkit" in payload["error"]


def test_an_unreadable_database_is_refused(tmp_path):
    code, payload, _stderr = _find(tmp_path / "nowhere.json", "--filename", "a.md")
    assert code == 2
    assert payload["reason_code"] == "database_unreadable"


def test_an_analysis_that_cannot_be_read_is_a_stable_answer(tmp_path):
    database = _vault(tmp_path, [ROBOCODERS])
    analysis = _analysis(database, ROBOCODERS)
    analysis.chmod(0)
    try:
        code, payload, stderr = _find(database, "--filename", ROBOCODERS["filename"])
    finally:
        analysis.chmod(0o644)
    assert code == 0, stderr
    assert payload["binding"] == "analysis_unreadable"
    assert "PermissionError" in payload["error"]
    assert payload["handoff"] is None


def test_a_directory_at_the_analysis_path_is_missing_not_a_crash(tmp_path):
    database = _vault(tmp_path, [ROBOCODERS])
    (database.parent / "analyses" / ROBOCODERS["filename"]).mkdir()
    code, payload, stderr = _find(database, "--filename", ROBOCODERS["filename"])
    assert code == 0, stderr
    assert payload["binding"] == "analysis_missing"


def test_an_analysis_that_is_not_utf8_is_unreadable_not_bound(tmp_path):
    """Replacing bad bytes would bind text the digest never covered."""
    database = _vault(tmp_path, [ROBOCODERS])
    analysis = _analysis(database, ROBOCODERS)
    analysis.write_bytes(analysis.read_bytes() + b"\nbroken \xff\xfe bytes\n")
    code, payload, stderr = _find(database, "--filename", ROBOCODERS["filename"])
    assert code == 0, stderr
    assert payload["binding"] == "analysis_unreadable"
    assert "not UTF-8" in payload["error"]
    assert "analysis_text" not in payload


def test_a_stored_root_that_matches_the_locator_binds(tmp_path):
    vault = tmp_path / "vault"
    database = _vault(
        tmp_path,
        [ROBOCODERS],
        config=current_tracking_config(vault_storage_path=str(vault)),
    )
    _analysis(database, ROBOCODERS)
    code, payload, stderr = _find(database, "--filename", ROBOCODERS["filename"])
    assert code == 0, stderr
    assert payload["binding"] == "bound"


@pytest.mark.parametrize(
    "stored",
    ["/somewhere/else", "relative/vault", ""],
    ids=["other", "relative", "empty"],
)
def test_a_stored_root_that_disagrees_with_the_locator_refuses(tmp_path, stored):
    """An asserted root elsewhere must never let the locator's directory bind."""
    database = _vault(
        tmp_path,
        [ROBOCODERS],
        config=current_tracking_config(vault_storage_path=stored),
    )
    _analysis(database, ROBOCODERS)
    code, payload, stderr = _find(database, "--filename", ROBOCODERS["filename"])
    assert code == 2
    assert payload["reason_code"] == "vault_root_invalid"
    assert "vault_storage_path" in stderr


def test_a_concurrent_write_mid_read_asks_for_a_rerun(tmp_path, monkeypatch, capsys):
    """A generation conflict is fixed by rerunning, never by a repair."""
    module = _import_script(str(SCRIPT), "find_talk_analysis_under_test")
    io = _import_script(
        str(Path(SCRIPTS_VI) / "tracking_database_io.py"), "tracking_database_io"
    )
    database = _vault(tmp_path, [ROBOCODERS])

    def conflict(_path):
        raise io.TrackingDatabaseConflictError("changed mid-read")

    monkeypatch.setattr(module, "snapshot_tracking_database", conflict)

    code = module.main(["--database", str(database), "--filename", "x.md"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["reason_code"] == "database_generation_conflict"
    assert "rerun" in payload["error"]

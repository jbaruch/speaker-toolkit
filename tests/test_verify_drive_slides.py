"""Exercise the Drive slide link verifier with fixed provider metadata."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

VERIFY = (
    Path(__file__).resolve().parents[1]
    / "skills/shownotes-publisher/scripts/verify-drive-slides.py"
)
FILE_ID = "slides_abc-123"
PDF_BYTES = b"%PDF-1.7\nslides content\n"
PDF_METADATA = {
    "id": FILE_ID,
    "mimeType": "application/pdf",
    "trashed": False,
    "sha256Checksum": hashlib.sha256(PDF_BYTES).hexdigest(),
}


def run_verifier(tmp_path, metadata, content=PDF_BYTES):
    pdf = tmp_path / "export.pdf"
    pdf.write_bytes(content)
    return subprocess.run(
        [sys.executable, str(VERIFY), str(pdf), FILE_ID],
        input=json.dumps(metadata),
        capture_output=True,
        check=False,
        text=True,
    )


def test_preview_url_requires_matching_drive_content(tmp_path):
    result = run_verifier(tmp_path, PDF_METADATA)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "file_id": FILE_ID,
        "preview_url": "https://drive.google.com/file/d/slides_abc-123/preview",
        "checksum_algorithm": "sha256",
    }


def test_older_drive_pdf_with_only_md5_is_supported(tmp_path):
    metadata = {
        **PDF_METADATA,
        "sha256Checksum": None,
        "md5Checksum": hashlib.md5(PDF_BYTES, usedforsecurity=False).hexdigest(),
    }
    result = run_verifier(tmp_path, metadata)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["checksum_algorithm"] == "md5"


def test_reused_drive_id_with_stale_bytes_refuses_to_publish(tmp_path):
    result = run_verifier(tmp_path, PDF_METADATA, b"%PDF-1.7\nupdated content\n")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "differs from the export" in result.stderr


@pytest.mark.parametrize(
    ("fields", "diagnostic"),
    [
        ({"id": "different-file"}, "selected file ID"),
        ({"mimeType": "text/plain"}, "active PDF"),
        ({"trashed": True}, "active PDF"),
        ({"sha256Checksum": None}, "no PDF checksum"),
        (
            {
                "sha256Checksum": "invalid",
                "md5Checksum": hashlib.md5(
                    PDF_BYTES, usedforsecurity=False
                ).hexdigest(),
            },
            "invalid sha256Checksum",
        ),
    ],
)
def test_unverifiable_drive_metadata_returns_no_url(tmp_path, fields, diagnostic):
    result = run_verifier(tmp_path, {**PDF_METADATA, **fields})
    assert result.returncode == 1
    assert result.stdout == ""
    assert diagnostic in result.stderr

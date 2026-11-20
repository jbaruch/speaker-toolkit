#!/usr/bin/env python3
"""Verify that the Drive slide PDF matches the toolkit export.

Inputs are the exported local PDF, the selected Drive file ID, and the raw
Drive v3 files.get JSON on stdin. Read metadata after the export and upload.
The caller owns the Drive read and the anonymous preview access check.

Exit 0 prints JSON with the verified file_id, preview_url and checksum_algorithm.
Verification failures exit 1 with a diagnostic on stderr and no preview URL.
Usage errors exit 2. This command makes no network calls or writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DRIVE_ID = re.compile(r"[A-Za-z0-9_-]+")


def drive_checksum(metadata: dict[str, object]) -> tuple[str, str]:
    for field, algorithm, length in (
        ("sha256Checksum", "sha256", 64),
        ("md5Checksum", "md5", 32),
    ):
        value = metadata.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not re.fullmatch(
            rf"[0-9a-fA-F]{{{length}}}", value
        ):
            raise ValueError(
                f"Drive returned an invalid {field}. Read fresh file metadata."
            )
        return algorithm, value.lower()
    raise ValueError(
        "Drive returned no PDF checksum. Wait for the upload and read metadata again."
    )


def verify(pdf: Path, file_id: str, metadata: object) -> dict[str, str]:
    if not DRIVE_ID.fullmatch(file_id):
        raise ValueError("Pass the selected Drive file ID.")
    if not isinstance(metadata, dict) or metadata.get("id") != file_id:
        raise ValueError("Read Drive files.get metadata for the selected file ID.")
    if (
        metadata.get("mimeType") != "application/pdf"
        or metadata.get("trashed") is not False
    ):
        raise ValueError(
            "Select an active PDF in Drive and request its mimeType and trashed fields."
        )

    algorithm, expected = drive_checksum(metadata)
    # Drive may return only MD5 for an older binary. This compares revisions
    # using authenticated provider metadata and makes no security decision.
    digest = hashlib.new(algorithm, usedforsecurity=False)
    with pdf.open("rb") as stream:
        header = stream.read(5)
        if header != b"%PDF-":
            raise ValueError("Pass the PDF produced by the slide export.")
        digest.update(header)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(
            "The Drive PDF differs from the export. Sync or update the existing "
            "Drive file, then read fresh metadata and verify again."
        )
    return {
        "file_id": file_id,
        "preview_url": f"https://drive.google.com/file/d/{file_id}/preview",
        "checksum_algorithm": algorithm,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("file_id")
    args = parser.parse_args()
    try:
        metadata = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        print("ERROR: Supply fresh Drive files.get JSON on stdin.", file=sys.stderr)
        return 1
    try:
        result = verify(args.pdf, args.file_id, metadata)
    except OSError as exc:
        print(
            f"ERROR: Cannot read the PDF at {args.pdf}: {exc.strerror}. "
            "Pass a readable slide-export path.",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

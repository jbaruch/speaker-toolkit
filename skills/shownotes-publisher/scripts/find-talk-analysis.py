#!/usr/bin/env python3
"""Find the rhetoric analysis that belongs to one exact delivery (#460).

The shownotes brief synthesizes from the analysis of the delivery it describes,
so a similar title is never enough. This script binds the analysis through the
tracking database owner, not through whatever the rendered file's header says:

1. Read ``tracking-database.json`` through the owner snapshot and require the
   current generation (``tracking_database.assess_tracking_database``); an older
   one is the owner's to migrate.
2. Select the talk record by ``--filename``, or by ``--title``, ``--event`` and
   ``--date`` together. Title and event match after whitespace collapsing and
   case folding (``_identity_text``); the date matches the record's ``date``
   exactly. Event is the record's ``conference``.
3. The record must be processed (``ANALYZED_STATUSES``), and
   ``{vault_root}/analyses/{filename}.md`` must be a regular file whose header,
   as ``write-analysis.py`` renders it, names the record's title, filename and
   ``processed_date``. The vault root is the database locator's directory,
   resolved through ``vault_root_authority.resolve_vault_root_authority`` so a
   ``config.vault_storage_path`` that names any other root refuses.

Stdout: one JSON object, exit 0 for every answered lookup. ``binding`` is
``bound`` with ``talk``, ``analysis_path``, ``analysis_sha256`` and
``analysis_text``, the checked bytes decoded as UTF-8 for synthesis; or one of
``not_found``, ``ambiguous``, ``not_processed``, ``analysis_missing`` (also a
link or non-regular file at the path), ``analysis_unreadable`` (with the
read ``error``), ``analysis_stale``, each with ``talk`` (null unless one record
matched), ``candidates`` (the records that share the event and date, or the
title, for a miss; every match for ``ambiguous``) and ``handoff``. The handoff
is non-null only when exactly one record matched and its status is one
vault-ingress's queue can claim (``CLAIMABLE_STATUSES``): ``skill``,
``scope: one_talk`` and that record's ``filename``, ``title``, ``event`` and
``date``, the explicit one-talk selection vault-ingress Step 2 takes. It is null
for ``bound``, ``not_found``, ``ambiguous`` and every unclaimable record.

Exit 2 writes ``{"ok": false, "reason_code", "error"}`` and the message to
stderr when the database cannot be read (the owner's
``tracking_database_io.DATABASE_READ_DIAGNOSTICS`` code and remedy, such as
``database_generation_conflict`` for a concurrent write, which a rerun fixes),
is an older generation (``database_not_current``), a supported one in a
malformed shape (``database_invalid``, the owner's to repair) or a newer one
this toolkit does not read (``database_unsupported``, which only a newer
toolkit fixes), its ``config.vault_storage_path`` does not
agree with its location (``vault_root_invalid``), or the arguments name no
delivery (``invalid_arguments``).
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

TOOLKIT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(TOOLKIT_ROOT / "skills/vault-ingress/scripts"))
# E402: these resolve only after the insert above puts the co-shipped
# vault-ingress scripts directory on sys.path.
from tracking_database import (  # noqa: E402
    TrackingDatabaseError,
    assess_tracking_database,
)
from queue_claim_contract import CLAIMABLE_STATUSES  # noqa: E402
from tracking_database_io import (  # noqa: E402
    DATABASE_READ_DIAGNOSTICS,
    DATABASE_READ_FALLBACK,
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)
from vault_root_authority import (  # noqa: E402
    VaultRootAuthorityError,
    resolve_vault_root_authority,
)

DEFAULT_DATABASE = "~/.claude/rhetoric-knowledge-vault/tracking-database.json"
ANALYSES_DIRECTORY = "analyses"
ANALYZED_STATUSES = frozenset({"processed", "processed_partial"})
# How many header lines write-analysis.py's provenance block can occupy.
HEADER_LINES = 12
IDENTITY_FIELDS = (
    "filename",
    "title",
    "conference",
    "date",
    "status",
    "processed_date",
)
_WHITESPACE = re.compile(r"\s+")
# No separator, leading dot, or control character (NUL included): the path is
# built from it and handed to os.open.
_PLAIN_MARKDOWN_NAME = re.compile(r"[^./\\\x00-\x1f\x7f][^/\\\x00-\x1f\x7f]*\.md")


class AnalysisLookupError(RuntimeError):
    """A refusal with a stable reason code and an actionable message."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _identity_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _WHITESPACE.sub(" ", value).strip().casefold()


def _identity(talk: dict[str, Any]) -> dict[str, Any]:
    return {field: talk.get(field) for field in IDENTITY_FIELDS}


def read_current_database(path: Path) -> tuple[dict[str, Any], Path]:
    """The owner-current database and the vault root its locator names."""
    try:
        snapshot = snapshot_tracking_database(path)
        database = decode_json_object(snapshot)
    except TrackingDatabaseIOError as exc:
        # The owner's closed vocabulary carries the remedy: a concurrent write
        # is rerun, a damaged file is repaired.
        code, remedy = DATABASE_READ_DIAGNOSTICS.get(
            exc.reason_code, DATABASE_READ_FALLBACK
        )
        raise AnalysisLookupError(code, f"{path}: {remedy}") from exc
    try:
        assessment = assess_tracking_database(database)
    except TrackingDatabaseError as exc:
        # A supported generation in a malformed shape is the owner's to repair.
        raise AnalysisLookupError(
            "database_invalid",
            f"the tracking database at {path} is malformed ({exc}); repair it "
            "through vault-ingress Step 1",
        ) from exc
    if not assessment.usable or not isinstance(database, dict):
        # A generation newer than this reader: the reader is lagging, so the
        # only remedy is a newer toolkit, never a repair of the database.
        raise AnalysisLookupError(
            "database_unsupported",
            f"the tracking database at {path} is a newer generation than this "
            "speaker-toolkit reads ("
            + ", ".join(assessment.reason_codes)
            + "); update speaker-toolkit, then rerun the lookup",
        )
    if assessment.state != "current":
        raise AnalysisLookupError(
            "database_not_current",
            f"the tracking database at {path} is an older owner generation; run "
            "the owner migration through vault-ingress Step 1",
        )
    try:
        vault_root = resolve_vault_root_authority(
            database_path=path, config=database.get("config")
        )
    except VaultRootAuthorityError as exc:
        raise AnalysisLookupError(
            "vault_root_invalid",
            f"the tracking database at {path} does not agree with its "
            f"config.vault_storage_path ({exc.reason_code}); pass the database "
            "at the vault root it names, or repair config.vault_storage_path "
            "through vault-ingress Step 1",
        ) from exc
    return database, vault_root


def select_talks(
    talks: list[Any],
    *,
    filename: str | None,
    title: str | None,
    event: str | None,
    date: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exact matches, and near records to name when nothing matched."""
    records = [talk for talk in talks if isinstance(talk, dict)]
    if filename is not None:
        return [talk for talk in records if talk.get("filename") == filename], []
    wanted = (_identity_text(title), _identity_text(event), date)
    matches = [
        talk
        for talk in records
        if (
            _identity_text(talk.get("title")),
            _identity_text(talk.get("conference")),
            talk.get("date"),
        )
        == wanted
    ]
    near = [
        talk
        for talk in records
        if talk not in matches
        and (
            (_identity_text(talk.get("conference")), talk.get("date")) == wanted[1:]
            or _identity_text(talk.get("title")) == wanted[0]
        )
    ]
    return matches, near


def _header_binds(text: str, talk: dict[str, Any]) -> bool:
    head = text.splitlines()[:HEADER_LINES]
    # write-analysis.py's own heading fallback for a record with no title.
    heading = talk.get("title") or str(talk.get("filename", "")).removesuffix(".md")
    expected = {
        f"# Rhetoric Analysis: {heading}",
        f"**Filename:** {talk.get('filename')}",
        f"**Processed:** {talk.get('processed_date')}",
    }
    return expected.issubset(head)


def _read_regular_file(path: Path) -> bytes | OSError | None:
    """The file's bytes; None when no regular file is there; the read error.

    One descriptor opened without following a final symlink is checked and
    read, so a file swapped for a link after a check can never be followed.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None
        return exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            return handle.read()
    except OSError as exc:
        return exc
    finally:
        os.close(descriptor)


def bind_analysis(talk: dict[str, Any], vault_root: Path) -> dict[str, Any]:
    filename = talk.get("filename")
    # A plain markdown name only: the analysis path is built from it.
    if not isinstance(filename, str) or not _PLAIN_MARKDOWN_NAME.fullmatch(filename):
        return {"binding": "analysis_missing", "analysis_path": None}
    if talk.get("status") not in ANALYZED_STATUSES:
        return {"binding": "not_processed", "analysis_path": None}
    path = vault_root / ANALYSES_DIRECTORY / filename
    raw = _read_regular_file(path)
    if raw is None:
        return {"binding": "analysis_missing", "analysis_path": str(path)}
    if isinstance(raw, OSError):
        return {
            "binding": "analysis_unreadable",
            "analysis_path": str(path),
            "error": (
                f"{type(raw).__name__}: {raw.strerror or 'no detail'}; make the "
                "analysis file readable (its permissions or its volume), then "
                "rerun the lookup"
            ),
        }
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {
            "binding": "analysis_unreadable",
            "analysis_path": str(path),
            "error": (
                f"not UTF-8 at byte {exc.start}; restore the analysis from a "
                "good copy or re-render it, then rerun the lookup"
            ),
        }
    if not _header_binds(text, talk):
        return {"binding": "analysis_stale", "analysis_path": str(path)}
    return {
        "binding": "bound",
        "analysis_path": str(path),
        "analysis_sha256": hashlib.sha256(raw).hexdigest(),
        "analysis_text": text,
    }


def lookup(args: argparse.Namespace) -> dict[str, Any]:
    selectors = (args.filename, args.title, args.event, args.date)
    if any(value is not None and not value.strip() for value in selectors):
        raise AnalysisLookupError(
            "invalid_arguments",
            "a delivery selector is blank; pass the exact filename, or the "
            "title, event and date",
        )
    by_filename = args.filename is not None
    by_identity = None not in (args.title, args.event, args.date)
    if by_filename == by_identity or (
        by_filename and any(v is not None for v in (args.title, args.event, args.date))
    ):
        raise AnalysisLookupError(
            "invalid_arguments",
            "name the delivery by --filename, or by --title, --event and --date "
            "together",
        )
    database, vault_root = read_current_database(
        Path(args.database).expanduser().absolute()
    )
    matches, near = select_talks(
        database.get("talks", []),
        filename=args.filename,
        title=args.title,
        event=args.event,
        date=args.date,
    )
    if len(matches) != 1:
        # No single record: vault-ingress has nothing it could select.
        return {
            "ok": True,
            "binding": "ambiguous" if matches else "not_found",
            "talk": None,
            "candidates": [_identity(talk) for talk in (matches or near)],
            "handoff": None,
        }
    talk = matches[0]
    bound = bind_analysis(talk, vault_root)
    result: dict[str, Any] = {"ok": True, "talk": _identity(talk), **bound}
    if bound["binding"] != "bound":
        result["candidates"] = []
        # vault-ingress can process only a record its queue can claim; a
        # processed record with a missing or stale render is not one.
        result["handoff"] = (
            {
                "skill": "vault-ingress",
                "scope": "one_talk",
                "filename": talk.get("filename"),
                "title": talk.get("title"),
                "event": talk.get("conference"),
                "date": talk.get("date"),
            }
            if talk.get("status") in CLAIMABLE_STATUSES
            else None
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--filename", help="the talk record's exact filename")
    parser.add_argument("--title")
    parser.add_argument("--event", help="the record's conference")
    parser.add_argument("--date", help="YYYY-MM-DD delivery date")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(lookup(args)))
        return 0
    except AnalysisLookupError as exc:
        print(
            json.dumps({"ok": False, "reason_code": exc.reason_code, "error": str(exc)})
        )
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

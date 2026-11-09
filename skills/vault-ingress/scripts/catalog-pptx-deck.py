#!/usr/bin/env python3
"""Plan the catalog entry for a deck that isn't in `pptx_catalog` yet.

`vault-ingress` Step 1 persists each reviewed extraction with a `record_pptx`
mutation, and a matched record must carry an assessment made before the binding was
decided. `sweep-pptx-talk-identity.py` only reaches rows already in the catalog, so a
newly delivered deck had no owner path in. This is that path. It takes an extraction
result, assesses the deck against every talk, and emits the `record_pptx` plan with
the catalog record, the visual-evidence receipt and the identity assessment, ready
for `mutate-tracking-database.py`'s usual dry-run and apply.

The assessment decides the binding. One disposition per deck:

* `bind`: the assessment proves one talk, and `binding_refusal` agrees.
* `catalog_unbound`: no talk matched, so the deck joins the catalog bound to nothing.
* `review_required`: nothing is planned, and `reason_codes` says why. Either the
  assessment was contested or refused, or binding it would displace another deck:
  the talk already has one, or two selected decks both prove it. Replacing a binding
  is an owner decision, so select one deck with `--deck` or resolve the other first.
* `already_cataloged`: nothing is planned. `sweep-pptx-talk-identity.py` owns these.
* `not_in_extraction`: `--deck` named a deck the extraction result doesn't hold.
* `deck_unreadable`: the deck can't be read under the source root.
* `extraction_stale`: the deck's bytes changed after the extraction read them.

Usage:
    catalog-pptx-deck.py <vault-root-or-database> --extraction <result.json>
                         [--deck <pptx_path>]... [--artifact-dir <vault-relative>]
                         [--dry-run]

    --extraction    pptx-extraction.py output: a schema-v1 `--directory` envelope or
                    one deck's result, each result at the current extraction schema
                    and pipeline. Without --deck, every deck in it that isn't
                    cataloged yet is selected.
    --deck          a root-relative `pptx_path` to select; repeatable.
    --artifact-dir  where the extraction artifacts go, relative to the vault root.
    --dry-run       write no artifact; the plan still names what would be written.

Side effect, stated plainly: each `bind` or `catalog_unbound` deck's extraction result
is written to `<artifact-dir>/<sha256>.json` under the vault, since a receipt has to
name an artifact that exists. The name is the content's digest, so a rerun writes
nothing new. Every directory below the vault root is opened without following links,
so a symlinked component refuses the write instead of escaping the vault. The database
is never written; the plan is for the owner writer to apply.

Stdout: one JSON object. `mutation_plan` is exactly the `{schema_version, mutations}`
envelope `mutate-tracking-database.py` accepts, and `decks[]` sits beside it.
Stderr: one actionable line when the inputs can't be used.
Exit 0 when the decks were assessed, a `review_required` included, since that's a
finding to act on. Exit 2 when the database, the extraction result, `--artifact-dir`
or an artifact write is unusable; stdout is then `{ok: false, code, error}`, and no
plan exists to apply.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import re
import secrets
import stat
from typing import Any, Mapping, Sequence

from artifact_locator import ArtifactLocatorError, classify_artifact_locator
from pptx_catalog_assessment import (
    candidate_talks,
    configured_speaker_name,
    material_assessment,
    resolve_input,
    resolve_pptx_source_dir,
    stored_proof,
)
from pptx_deck_facts import read_deck_identity_facts
from pptx_discovery_contract import (
    PPTX_DIRECTORY_BATCH_KIND,
    PptxDiscoveryContractError,
    decode_pptx_directory_batch,
)
from pptx_evidence import (
    PPTX_EXTRACTION_PIPELINE_VERSION,
    PPTX_EXTRACTION_SCHEMA_VERSION,
)
from pptx_talk_identity import (
    VERDICT_MATCHED,
    VERDICT_UNMATCHED,
    PptxTalkIdentityError,
    assess_pptx_talk_identity,
    binding_refusal,
)
from tracking_database import (
    PPTX_CATALOG_RECORD_SCHEMA_VERSION,
    TrackingDatabaseError,
    assess_tracking_database,
)
from tracking_database_io import (
    DATABASE_READ_DIAGNOSTICS,
    DATABASE_READ_FALLBACK,
    TrackingDatabaseIOError,
    decode_json_object,
    snapshot_tracking_database,
)

REPORT_SCHEMA_VERSION = 1
MUTATION_PLAN_SCHEMA_VERSION = 1
DEFAULT_ARTIFACT_DIR = "pptx-extractions"
# The owner writer's missing-value sentinel, restated here because the plan is JSON
# handed to that writer rather than a Python call into it.
MISSING_MARKER = {"$missing": True}

DISPOSITION_BIND = "bind"
DISPOSITION_UNBOUND = "catalog_unbound"
DISPOSITION_REVIEW = "review_required"
DISPOSITION_CATALOGED = "already_cataloged"
DISPOSITION_NOT_EXTRACTED = "not_in_extraction"
DISPOSITION_UNREADABLE = "deck_unreadable"
DISPOSITION_STALE = "extraction_stale"

REASON_CONTESTED_IN_BATCH = "talk_contested_in_this_batch"
REASON_TALK_ALREADY_BOUND = "talk_already_bound_to_another_deck"


class CatalogInputError(Exception):
    """The extraction result or an argument can't be used; the message says why."""


class ArtifactWriteRefused(Exception):
    """An artifact can't be written inside the vault; the message says why."""


_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def _require_current_result(result: object, *, label: str) -> dict[str, Any]:
    """One extraction result at the current generation, or a refusal naming why.

    A receipt binds the extractor schema and pipeline version it was made with, so
    an older or a future result can't become a current catalog record.
    """
    if not isinstance(result, dict):
        raise CatalogInputError(f"{label} is not an object")
    schema_version = result.get("schema_version")
    if (
        type(schema_version) is not int
        or schema_version != PPTX_EXTRACTION_SCHEMA_VERSION
        or result.get("pipeline_version") != PPTX_EXTRACTION_PIPELINE_VERSION
    ):
        raise CatalogInputError(
            f"{label} is extraction schema {schema_version!r}, pipeline "
            f"{result.get('pipeline_version')!r}; this command reads schema "
            f"{PPTX_EXTRACTION_SCHEMA_VERSION}, pipeline "
            f"{PPTX_EXTRACTION_PIPELINE_VERSION}. Re-run pptx-extraction.py and pass "
            "its output"
        )
    fingerprint = result.get("input_fingerprint")
    if not (
        isinstance(fingerprint, dict)
        and set(fingerprint) == {"algorithm", "digest", "size_bytes"}
        and fingerprint["algorithm"] == "sha256"
        and isinstance(fingerprint["digest"], str)
        and _SHA256_HEX.fullmatch(fingerprint["digest"])
        and type(fingerprint["size_bytes"]) is int
        and fingerprint["size_bytes"] >= 0
    ):
        raise CatalogInputError(
            f"{label} has no valid input_fingerprint; re-run pptx-extraction.py"
        )
    pptx_path = result.get("pptx_path")
    slide_count = result.get("slide_count")
    if not isinstance(pptx_path, str) or not pptx_path:
        raise CatalogInputError(f"{label} has no pptx_path; re-run pptx-extraction.py")
    if type(slide_count) is not int or slide_count < 0:
        raise CatalogInputError(
            f"{label} has no valid slide_count; re-run pptx-extraction.py"
        )
    return result


def _load_extraction_results(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Return the extraction's per-deck results and any incomplete-scan reasons."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogInputError(
            f"cannot read the extraction result {path}: {exc}; re-run pptx-extraction.py "
            "and pass its JSON output"
        ) from exc
    if not isinstance(payload, dict):
        raise CatalogInputError(f"the extraction result {path} is not a JSON object")
    if payload.get("kind") == PPTX_DIRECTORY_BATCH_KIND or set(payload) == {
        "results",
        "skipped",
    }:
        try:
            batch = decode_pptx_directory_batch(payload)
        except PptxDiscoveryContractError as exc:
            raise CatalogInputError(
                f"{path} is not a schema-v1 pptx-extraction.py --directory envelope "
                f"({exc}); re-run pptx-extraction.py --directory and pass its output"
            ) from exc
        raw_results = batch["results"]
        incomplete = batch["incomplete_reason_codes"]
        assert isinstance(raw_results, list) and isinstance(incomplete, list)
        results = [
            _require_current_result(result, label=f"{path} results[{index}]")
            for index, result in enumerate(raw_results)
        ]
        reasons = [str(code) for code in incomplete]
    elif "pptx_path" in payload:
        results, reasons = [_require_current_result(payload, label=str(path))], []
    else:
        raise CatalogInputError(
            f"{path} is neither a pptx-extraction.py --directory envelope nor one deck's "
            "result"
        )
    return results, reasons


def _root_relative(pptx_path: object, source_root: object) -> str | None:
    """A result's deck path as the catalog names it: relative to the source root.

    A `--directory` result is already relative. A single-deck run reports the path it
    was handed, which is usually absolute.
    """
    if not isinstance(pptx_path, str) or not pptx_path:
        return None
    path = Path(pptx_path)
    if not path.is_absolute():
        return pptx_path
    try:
        return path.resolve().relative_to(Path(str(source_root)).resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _safe_artifact_dir(value: str) -> PurePosixPath:
    """The artifact directory as a canonical vault-relative locator.

    Classified lexically by the shared locator owner, so a Windows drive or UNC path
    is refused on every host, not only on Windows.
    """
    try:
        kind = classify_artifact_locator(value)
    except ArtifactLocatorError as exc:
        raise CatalogInputError(
            f"--artifact-dir {value!r} must be a canonical path relative to the vault "
            f"root ({exc}), such as {DEFAULT_ARTIFACT_DIR}"
        ) from exc
    if kind != "relative":
        raise CatalogInputError(
            f"--artifact-dir {value!r} is a {kind.replace('_', ' ')} path; give a "
            f"path relative to the vault root, such as {DEFAULT_ARTIFACT_DIR}"
        )
    return PurePosixPath(value)


# Contained writes depend on these, so a platform without them refuses rather than
# falling back to path-based writes that a symlink could redirect.
_REQUIRED_OPEN_FLAGS = ("O_NOFOLLOW", "O_DIRECTORY")


def _open_contained_directory(vault_root: Path, parts: tuple[str, ...]) -> int:
    """A descriptor for the directory `parts` names under the vault root.

    The root is opened by name and may itself be a symlink: it's trusted
    configuration. Each component below it is opened relative to its parent with
    O_NOFOLLOW and created when missing, so a symlinked component refuses the walk.
    """
    if (
        os.open not in os.supports_dir_fd
        or os.mkdir not in os.supports_dir_fd
        or os.rename not in os.supports_dir_fd
        or os.unlink not in os.supports_dir_fd
        or any(not hasattr(os, name) for name in _REQUIRED_OPEN_FLAGS)
    ):
        raise ArtifactWriteRefused(
            "this platform can't open paths relative to a directory without following "
            "links, so the artifact can't be written safely"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_DIRECTORY
    current = os.open(os.fspath(vault_root), flags)
    try:
        for part in parts:
            try:
                nested = os.open(part, flags | os.O_NOFOLLOW, dir_fd=current)
            except FileNotFoundError:
                os.mkdir(part, 0o755, dir_fd=current)
                nested = os.open(part, flags | os.O_NOFOLLOW, dir_fd=current)
            except OSError as exc:
                raise ArtifactWriteRefused(
                    f"{part!r} under the artifact directory is a symbolic link or not "
                    f"a directory ({exc.strerror}); replace it with a real directory "
                    "and re-run"
                ) from exc
            os.close(current)
            current = nested
    except BaseException:
        os.close(current)
        raise
    return current


def _write_artifact(vault_root: Path, relative: str, content: bytes) -> bool:
    """Write one content-addressed artifact inside the vault; False when already there.

    Every component below the vault root is opened without following links, the
    content is staged under a unique exclusive name, and the rename stays anchored
    to the same directory descriptor.
    """
    locator = PurePosixPath(relative)
    directory = _open_contained_directory(vault_root, locator.parts[:-1])
    name = locator.name
    try:
        try:
            existing = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
                dir_fd=directory,
            )
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise ArtifactWriteRefused(
                f"the artifact {relative} is a symbolic link or unreadable "
                f"({exc.strerror}); remove it and re-run"
            ) from exc
        if existing is not None:
            with os.fdopen(existing, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ArtifactWriteRefused(
                        f"the artifact {relative} isn't a regular file; remove it and "
                        "re-run"
                    )
                if stream.read() == content:
                    return False
        staged = f".{name}.{secrets.token_hex(8)}"
        descriptor = os.open(
            staged,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o644,
            dir_fd=directory,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # POSIX rename replaces the destination atomically; platforms without
            # dir_fd support were refused when the directory was opened.
            os.rename(staged, name, src_dir_fd=directory, dst_dir_fd=directory)
        except BaseException:
            # Created exclusively above and not yet renamed, so the name is ours.
            os.unlink(staged, dir_fd=directory)
            raise
    finally:
        os.close(directory)
    return True


def _visual_evidence(
    result: Mapping[str, Any],
    artifact_dir: PurePosixPath,
) -> tuple[dict[str, Any], bytes]:
    """The receipt for one extraction result, and the artifact bytes it names."""
    content = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode(
        "utf-8"
    )
    digest = hashlib.sha256(content).hexdigest()
    return (
        {
            "outcome": "succeeded",
            "extractor_schema_version": result.get("schema_version"),
            "pipeline_version": result.get("pipeline_version"),
            "source_fingerprint": result.get("input_fingerprint"),
            "artifact": {
                "path": (artifact_dir / f"{digest}.json").as_posix(),
                "sha256": digest,
            },
        },
        content,
    )


def _assess_deck(
    pptx_path: str,
    result: Mapping[str, Any],
    *,
    source_root: object,
    candidates: list[dict[str, Any]],
    speaker_name: object,
) -> dict[str, Any]:
    """Assess one uncataloged deck. The caller still applies the cross-deck rules."""
    reading = read_deck_identity_facts(pptx_path, source_root)
    entry: dict[str, Any] = {
        "pptx_path": pptx_path,
        "deck_facts_reason_code": reading.reason_code,
    }
    observed = reading.source_identity
    if observed is None:
        return {
            **entry,
            "disposition": DISPOSITION_UNREADABLE,
            "reason_codes": [reading.reason_code],
        }
    if result.get("input_fingerprint") != observed:
        return {
            **entry,
            "disposition": DISPOSITION_STALE,
            "reason_codes": ["extraction_source_fingerprint_differs"],
        }
    try:
        assessment = assess_pptx_talk_identity(
            reading.facts,
            candidates,
            source_identity=observed,
            speaker_name=speaker_name,
        )
    except PptxTalkIdentityError as exc:
        return {
            **entry,
            "disposition": DISPOSITION_REVIEW,
            "reason_codes": ["identity_assessment_refused"],
            "error": type(exc).__name__,
        }
    selected = assessment.selected_talk_filename
    material = material_assessment(assessment)
    entry.update(
        {
            "verdict": assessment.verdict,
            "artifact_role": assessment.artifact_role,
            "selected_talk_filename": selected,
            "reason_codes": list(assessment.reason_codes),
            "assessment": material,
        }
    )
    if assessment.verdict == VERDICT_MATCHED and isinstance(selected, str):
        refusal = binding_refusal(
            stored_proof(material),
            pptx_path=pptx_path,
            talk_filename=selected,
            observed_source_identity=observed,
        )
        if refusal is not None:
            return {
                **entry,
                "disposition": DISPOSITION_REVIEW,
                "reason_codes": [refusal],
            }
        return {**entry, "disposition": DISPOSITION_BIND}
    if assessment.verdict == VERDICT_UNMATCHED:
        return {**entry, "disposition": DISPOSITION_UNBOUND}
    return {**entry, "disposition": DISPOSITION_REVIEW}


def _hold_displacing_bindings(
    decks: list[dict[str, Any]],
    *,
    talks: Mapping[str, Mapping[str, Any]],
    catalog: Sequence[Any],
) -> None:
    """Turn a `bind` that would displace another deck into `review_required`.

    Each deck is assessed alone, so this is only visible across decks. Two decks can't
    both be one talk's delivery deck, and a talk that already has a deck loses it to
    whatever this plan binds, which nobody decided here.
    """
    claims = Counter(
        deck["selected_talk_filename"]
        for deck in decks
        if deck["disposition"] == DISPOSITION_BIND
    )
    bound_in_catalog = {
        record.get("talk_filename") for record in catalog if isinstance(record, Mapping)
    }
    for deck in decks:
        if deck["disposition"] != DISPOSITION_BIND:
            continue
        talk_filename = deck["selected_talk_filename"]
        talk = talks.get(talk_filename, {})
        if claims[talk_filename] > 1:
            deck.update(
                disposition=DISPOSITION_REVIEW,
                reason_codes=[REASON_CONTESTED_IN_BATCH],
            )
        elif talk.get("pptx_path") or talk_filename in bound_in_catalog:
            deck.update(
                disposition=DISPOSITION_REVIEW,
                reason_codes=[REASON_TALK_ALREADY_BOUND],
            )


def plan_decks(
    database: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    *,
    source_root: object,
    selected_decks: Sequence[str],
    artifact_dir: PurePosixPath,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, bytes]]:
    """Return (decks report, record_pptx mutations, artifact path -> bytes)."""
    catalog = database.get("pptx_catalog")
    catalog = catalog if isinstance(catalog, list) else []
    cataloged = {
        record.get("pptx_path") for record in catalog if isinstance(record, Mapping)
    }
    by_path: dict[str, Mapping[str, Any]] = {}
    for result in results:
        relative = _root_relative(result.get("pptx_path"), source_root)
        if relative is not None:
            by_path[relative] = result
    wanted = list(selected_decks) or [path for path in by_path if path not in cataloged]

    candidates = candidate_talks(database)
    talks = {talk["filename"]: talk for talk in candidates}
    decks: list[dict[str, Any]] = []
    for pptx_path in wanted:
        if pptx_path in cataloged:
            decks.append(
                {
                    "pptx_path": pptx_path,
                    "disposition": DISPOSITION_CATALOGED,
                    "reason_codes": [],
                }
            )
        elif pptx_path not in by_path:
            decks.append(
                {
                    "pptx_path": pptx_path,
                    "disposition": DISPOSITION_NOT_EXTRACTED,
                    "reason_codes": [],
                }
            )
        else:
            decks.append(
                _assess_deck(
                    pptx_path,
                    by_path[pptx_path],
                    source_root=source_root,
                    candidates=candidates,
                    speaker_name=configured_speaker_name(database),
                )
            )
    _hold_displacing_bindings(decks, talks=talks, catalog=catalog)

    mutations: list[dict[str, Any]] = []
    artifacts: dict[str, bytes] = {}
    for deck in decks:
        disposition = deck["disposition"]
        if disposition not in {DISPOSITION_BIND, DISPOSITION_UNBOUND}:
            continue
        result = by_path[deck["pptx_path"]]
        evidence, content = _visual_evidence(result, artifact_dir)
        artifacts[evidence["artifact"]["path"]] = content
        bound = disposition == DISPOSITION_BIND
        talk_filename = deck["selected_talk_filename"] if bound else None
        mutation: dict[str, Any] = {
            "kind": "record_pptx",
            "expect": MISSING_MARKER,
            "record": {
                "schema_version": PPTX_CATALOG_RECORD_SCHEMA_VERSION,
                "pptx_path": deck["pptx_path"],
                "talk_filename": talk_filename,
                "matched": bound,
                "slide_count": result.get("slide_count"),
                "visual_extracted": True,
                "visual_evidence": evidence,
                "identity_assessment": (
                    stored_proof(deck["assessment"]) if bound else None
                ),
            },
        }
        if bound:
            # The writer tells null from absent, so expect whichever this talk holds.
            talk = talks.get(talk_filename, {})
            mutation["expect_talk_pptx_path"] = (
                talk["pptx_path"] if "pptx_path" in talk else MISSING_MARKER
            )
        mutations.append(mutation)
    return decks, mutations, artifacts


def execute(
    value: str | Path,
    *,
    extraction: Path,
    selected_decks: Sequence[str] = (),
    artifact_dir: str = DEFAULT_ARTIFACT_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    relative_artifact_dir = _safe_artifact_dir(artifact_dir)
    results, incomplete = _load_extraction_results(extraction)
    vault_root, database_path = resolve_input(value)
    snapshot = snapshot_tracking_database(database_path)
    database = decode_json_object(snapshot)
    try:
        assessment = assess_tracking_database(database)
    except TrackingDatabaseError as exc:
        raise TrackingDatabaseIOError(
            "tracking database owner assessment failed",
            reason_code="owner_assessment_failed",
        ) from exc
    if not assessment.usable:
        raise TrackingDatabaseIOError(
            "tracking database has no usable legacy/current owner state",
            reason_code="owner_state_unusable",
        )
    decks, mutations, artifacts = plan_decks(
        database,
        results,
        source_root=resolve_pptx_source_dir(database, vault_root=vault_root),
        selected_decks=selected_decks,
        artifact_dir=relative_artifact_dir,
    )
    written = (
        []
        if dry_run
        else [
            path
            for path, content in artifacts.items()
            if _write_artifact(vault_root, path, content)
        ]
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "ok": True,
        "database_path": str(snapshot.path),
        "sha256": snapshot.sha256,
        "dry_run": dry_run,
        "incomplete_reason_codes": incomplete,
        "artifacts_planned": sorted(artifacts),
        "artifacts_written": sorted(written),
        "decks": decks,
        "mutation_plan": {
            "schema_version": MUTATION_PLAN_SCHEMA_VERSION,
            "mutations": mutations,
        },
    }


def _error(code: str, message: str) -> int:
    print(
        json.dumps(
            {
                "schema_version": REPORT_SCHEMA_VERSION,
                "ok": False,
                "code": code,
                "error": message,
            }
        )
    )
    print(f"catalog-pptx-deck failed: {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan the catalog entry for a deck that isn't in pptx_catalog yet."
    )
    parser.add_argument("vault", type=Path)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--deck", action="append", default=[])
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = execute(
            args.vault,
            extraction=args.extraction,
            selected_decks=args.deck,
            artifact_dir=args.artifact_dir,
            dry_run=args.dry_run,
        )
    except CatalogInputError as exc:
        return _error("extraction_input_invalid", str(exc))
    except ArtifactWriteRefused as exc:
        return _error("artifact_write_refused", str(exc))
    except TrackingDatabaseIOError as exc:
        # Never echo the exception: decoder messages carry the host database path and
        # the rejected value. Route the typed reason through the closed vocabulary.
        code, message = DATABASE_READ_DIAGNOSTICS.get(
            exc.reason_code, DATABASE_READ_FALLBACK
        )
        return _error(code, message)
    except OSError as exc:
        return _error(
            "artifact_write_failed",
            f"cannot write the extraction artifact: {exc}; fix the vault folder's "
            "permissions or free up the disk, then re-run",
        )
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

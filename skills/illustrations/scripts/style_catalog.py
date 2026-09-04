#!/usr/bin/env python3
"""Own the versioned public/personal style catalog and exploration projection.

CLI: style_catalog.py list [--vault VAULT]
     style_catalog.py candidates --selection JSON --output JSON [--vault VAULT]
     style_catalog.py put --vault VAULT --entry JSON --expected-sha256 SHA|missing
                         [--apply]

All commands emit one JSON object; failures also emit a closed diagnostic on
stderr. Exit 0 success, 1 expected operational/validation failure, 2 usage or
unexpected process-boundary failure. Reads never migrate or write. Put defaults
to a digest-bound preview, preserves other entries, and backs up replaced bytes.
Selection and artifact schemas: skills/illustrations/references/style-catalog.md.
No image generation, network access, tracking-DB access, or public submission.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, NoReturn
from urllib.parse import urlsplit


VERSION = 1
CANDIDATES_VERSION = 2
MAX_BYTES = 2 * 1024 * 1024
MAX_ENTRIES = 200
PERSONAL_NAME = "style-catalog.json"
PUBLIC_PATH = Path(__file__).resolve().parent.parent / "catalog" / "styles.json"
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FORMATS = {"FULL", "IMG+TXT"}


class CatalogError(ValueError):
    """Closed error code and safe, actionable diagnostic."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> NoReturn:
    raise CatalogError(code, message)


def _shape(value: Any, fields: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        _fail("catalog_shape_invalid", "Use the documented closed catalog schema.")
    return value


def _version(value: Any, expected: int = VERSION) -> None:
    if type(value) is not int or value != expected:
        _fail(
            "catalog_version_unsupported",
            "Update the owner tool; do not restamp records.",
        )


def _text(value: Any, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 16000
        or (not empty and not value.strip())
        or any(ord(c) < 32 and c not in "\n\t" for c in value)
    ):
        _fail("catalog_text_invalid", "Supply bounded plain-text catalog fields.")
    return value


def _slug(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 100 or not SLUG.fullmatch(value):
        _fail("catalog_slug_invalid", "Use a lowercase, hyphen-separated style slug.")
    return value


def _https(value: str) -> None:
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme == "https"
            and bool(parts.hostname)
            and parts.username is None
            and parts.password is None
        )
    except ValueError:
        valid = False
    if not valid or any(c.isspace() for c in value):
        _fail(
            "catalog_reference_invalid",
            "Use a public HTTPS reference without credentials.",
        )


def validate_entry(value: Any, *, public: bool = False) -> dict:
    entry = _shape(
        value,
        {
            "schema_version",
            "slug",
            "name",
            "anchors",
            "text_treatment",
            "conventions",
            "composition",
            "tags",
            "sample",
            "provenance",
        },
    )
    _version(entry["schema_version"])
    _slug(entry["slug"])
    name = _text(entry["name"])
    if len(name) > 160 or "\n" in name or "\t" in name:
        _fail("catalog_name_invalid", "Use a single-line style display name.")
    anchors = _shape(entry["anchors"], FORMATS)
    for anchor in anchors.values():
        _text(anchor)
    _text(entry["conventions"], empty=True)
    if entry["composition"] not in ("overlay", "poster-theatrical"):
        _fail("catalog_composition_invalid", "Choose overlay or poster-theatrical.")
    _text(entry["text_treatment"], empty=entry["composition"] == "overlay")
    tags = entry["tags"]
    if not isinstance(tags, list) or not 1 <= len(tags) <= 20:
        _fail("catalog_tags_invalid", "Supply one to twenty distinct tag slugs.")
    for tag in tags:
        _slug(tag)
    if len(set(tags)) != len(tags):
        _fail("catalog_tags_invalid", "Remove duplicate tag slugs.")
    sample = _shape(
        entry["sample"], {"schema_version", "kind", "location", "description"}
    )
    _version(sample["schema_version"])
    if sample["kind"] not in ("local-image", "remote-image", "reference"):
        _fail(
            "catalog_sample_invalid",
            "Declare an image or an explicitly unbundled reference.",
        )
    _text(sample["location"])
    _text(sample["description"])
    if public or sample["kind"] != "local-image":
        if sample["kind"] == "local-image":
            _fail(
                "catalog_sample_private",
                "Publish a consented public sample, not a local path.",
            )
        _https(sample["location"])
    provenance = _shape(
        entry["provenance"], {"schema_version", "kind", "reference", "note"}
    )
    _version(provenance["schema_version"])
    if provenance["kind"] not in (
        "exploration",
        "delivered-talk",
        "contribution",
        "personal",
    ):
        _fail("catalog_provenance_invalid", "Use a documented provenance kind.")
    _text(provenance["reference"])
    _text(provenance["note"])
    if public:
        _https(provenance["reference"])
    return entry


def validate_catalog(value: Any, *, public: bool = False) -> dict:
    catalog = _shape(value, {"schema_version", "styles"})
    _version(catalog["schema_version"])
    entries = catalog["styles"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        _fail("catalog_entries_invalid", "Use at most 200 style entries per layer.")
    slugs = set()
    for entry in entries:
        validate_entry(entry, public=public)
        if entry["slug"] in slugs:
            _fail(
                "catalog_slug_duplicate",
                "Keep each slug unique within its catalog layer.",
            )
        slugs.add(entry["slug"])
    return catalog


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("catalog_json_duplicate", "Remove duplicate JSON object keys.")
        result[key] = value
    return result


def _constant(_: str) -> None:
    _fail("catalog_json_invalid", "Use finite, standard JSON values.")


def decode(raw: bytes | None) -> Any:
    if raw is None:
        _fail("catalog_file_missing", "Locate the required input file and retry.")
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("catalog_json_invalid", "Supply valid JSON encoded as UTF-8.")


def encode(value: Any) -> bytes:
    raw = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode()
    if len(raw) > MAX_BYTES:
        _fail(
            "catalog_too_large", "Keep each catalog or selection document within 2 MiB."
        )
    return raw


def digest(raw: bytes | None) -> str:
    return "missing" if raw is None else hashlib.sha256(raw).hexdigest()


def _file_ok(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
        _fail("catalog_file_invalid", "Use a regular local JSON file within 2 MiB.")
    if getattr(info, "st_flags", 0) & getattr(stat, "UF_DATALESS", 0x40000000):
        _fail(
            "catalog_file_unavailable",
            "Make the catalog available locally, then retry.",
        )


def read_bytes(path: Path, *, missing: bool = False) -> bytes | None:
    try:
        _file_ok(path.lstat())
        fd = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0),
        )
    except FileNotFoundError:
        if missing:
            return None
        _fail("catalog_file_missing", "Locate the required input file and retry.")
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        _file_ok(before)
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    current = path.lstat()

    def identity(info):
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    if (
        len(raw) > MAX_BYTES
        or identity(before) != identity(after)
        or identity(after) != identity(current)
    ):
        _fail(
            "catalog_input_changed",
            "Input changed during the read; retry from a fresh preview.",
        )
    return raw


def personal_path(vault: Path) -> Path:
    try:
        resolved = vault.resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError):
        _fail("catalog_vault_invalid", "Select an existing vault directory.")
    if not resolved.is_dir():
        _fail("catalog_vault_invalid", "Select an existing vault directory.")
    return resolved / PERSONAL_NAME


def load_merged(vault: Path | None = None, *, public_path: Path = PUBLIC_PATH) -> dict:
    public_raw = read_bytes(public_path)
    public = validate_catalog(decode(public_raw), public=True)
    personal_raw = read_bytes(personal_path(vault), missing=True) if vault else None
    personal = (
        validate_catalog(decode(personal_raw))
        if personal_raw is not None
        else {"schema_version": 1, "styles": []}
    )
    merged = {}
    for layer, catalog, raw in (
        ("public", public, public_raw),
        ("personal", personal, personal_raw),
    ):
        for entry in catalog["styles"]:
            merged[entry["slug"]] = {
                **copy.deepcopy(entry),
                "catalog_source": {
                    "schema_version": 1,
                    "layer": layer,
                    "sha256": digest(raw),
                },
            }
    return {
        "schema_version": 1,
        "public_sha256": digest(public_raw),
        "personal_sha256": digest(personal_raw),
        "styles": [merged[slug] for slug in sorted(merged)],
    }


def validate_candidate_style(style: Any) -> dict:
    if not isinstance(style, dict) or "catalog_source" not in style:
        _fail(
            "catalog_candidate_invalid",
            "Rebuild catalog candidates with the owner tool.",
        )
    validate_entry(
        {key: value for key, value in style.items() if key != "catalog_source"}
    )
    source = _shape(style["catalog_source"], {"schema_version", "layer", "sha256"})
    _version(source["schema_version"])
    if (
        source["layer"] not in ("public", "personal")
        or not isinstance(source["sha256"], str)
        or not SHA256.fullmatch(source["sha256"])
    ):
        _fail(
            "catalog_candidate_invalid",
            "Rebuild candidates from the current catalog layers.",
        )
    return style


def seed_candidates(merged: dict, selection: Any) -> dict:
    selection = _shape(selection, {"schema_version", "slugs", "slides", "models"})
    _version(selection["schema_version"])
    slugs = selection["slugs"]
    if not isinstance(slugs, list) or not 1 <= len(slugs) <= 20:
        _fail("catalog_selection_invalid", "Select one to twenty style slugs.")
    for slug in slugs:
        _slug(slug)
    if len(set(slugs)) != len(slugs):
        _fail("catalog_selection_invalid", "Select each style slug only once.")
    entries = {entry["slug"]: entry for entry in merged["styles"]}
    if any(slug not in entries for slug in slugs):
        _fail(
            "catalog_selection_missing",
            "List the current merged catalog and select known slugs.",
        )
    styles = [copy.deepcopy(entries[slug]) for slug in slugs]
    compositions = {entry["composition"] for entry in styles}
    slides = selection["slides"]
    if (
        not isinstance(slides, dict)
        or not slides
        or set(slides) - FORMATS
        or any(type(n) is not int or n < 1 for n in slides.values())
    ):
        _fail(
            "catalog_selection_slides_invalid",
            "Map FULL and/or IMG+TXT to positive slide numbers.",
        )
    if len(compositions) != 1 or (
        "poster-theatrical" in compositions and set(slides) != {"FULL"}
    ):
        _fail(
            "catalog_selection_composition",
            "Explore one composition at a time; posters require FULL only.",
        )
    names = [
        re.sub(r"[^a-z0-9]+", "-", entry["name"].lower()).strip("-") or "style"
        for entry in styles
    ]
    if len(set(names)) != len(names):
        _fail(
            "catalog_selection_name_collision",
            "Choose distinct display names for exploration output directories.",
        )
    models = selection["models"]
    if not isinstance(models, list) or not 1 <= len(models) <= 20:
        _fail(
            "catalog_selection_models_invalid",
            "Supply one to twenty shortlisted model IDs.",
        )
    for model in models:
        _text(model)
        if any(c.isspace() for c in model):
            _fail(
                "catalog_selection_models_invalid", "Use model IDs without whitespace."
            )
    if len(set(models)) != len(models):
        _fail("catalog_selection_models_invalid", "Select each model ID only once.")
    return {
        "schema_version": CANDIDATES_VERSION,
        "slides": copy.deepcopy(slides),
        "models": list(models),
        "styles": styles,
    }


def validate_candidates(value: Any) -> dict:
    candidate = _shape(value, {"schema_version", "slides", "models", "styles"})
    _version(candidate["schema_version"], CANDIDATES_VERSION)
    if not isinstance(candidate["styles"], list):
        _fail(
            "catalog_candidate_invalid",
            "Rebuild candidates with the catalog owner tool.",
        )
    for style in candidate["styles"]:
        validate_candidate_style(style)
    seed_candidates(
        {"styles": candidate["styles"]},
        {
            "schema_version": 1,
            "slugs": [style["slug"] for style in candidate["styles"]],
            "slides": candidate["slides"],
            "models": candidate["models"],
        },
    )
    return candidate


def _publish_new(path: Path, raw: bytes) -> bool:
    existing = read_bytes(path, missing=True)
    if existing is not None:
        if existing == raw:
            return False
        _fail(
            "catalog_output_exists",
            "Preserve the existing output; choose a fresh filename.",
        )
    with tempfile.TemporaryDirectory(
        prefix=".style-catalog-", dir=path.parent
    ) as temporary:
        stage = Path(temporary) / "candidate.json"
        with stage.open("xb") as stream:
            os.chmod(stage, 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(stage, path)
        except FileExistsError:
            if read_bytes(path) != raw:
                _fail(
                    "catalog_output_changed",
                    "Output appeared during publication; choose a fresh filename.",
                )
            return False
    return True


def put_entry(vault: Path, entry: Any, expected: str, *, apply: bool = False) -> dict:
    validate_entry(entry)
    if expected != "missing" and (
        not isinstance(expected, str) or not SHA256.fullmatch(expected)
    ):
        _fail(
            "catalog_expected_invalid",
            "Pass the preview's SHA-256, or missing for a new catalog.",
        )
    target = personal_path(vault)
    # All owner writes use one canonical-path lock; no tracking-database lease is involved.
    from filelock import FileLock, Timeout

    lock_path = Path(tempfile.gettempdir()) / (
        "speaker-style-" + hashlib.sha256(str(target).encode()).hexdigest() + ".lock"
    )
    try:
        with FileLock(str(lock_path), timeout=10):
            raw = read_bytes(target, missing=True)
            if digest(raw) != expected:
                _fail(
                    "catalog_expected_mismatch",
                    "Catalog changed; preview again before applying.",
                )
            prior = (
                validate_catalog(decode(raw))
                if raw is not None
                else {"schema_version": 1, "styles": []}
            )
            entries = {item["slug"]: item for item in prior["styles"]}
            changed = entries.get(entry["slug"]) != entry
            entries[entry["slug"]] = copy.deepcopy(entry)
            candidate = {
                "schema_version": 1,
                "styles": [entries[slug] for slug in sorted(entries)],
            }
            validate_catalog(candidate)
            output = raw if not changed and raw is not None else encode(candidate)
            result = {
                "schema_version": 1,
                "ok": True,
                "changed": changed,
                "applied": False,
                "input_sha256": digest(raw),
                "output_sha256": digest(output),
                "backup": None,
            }
            if not apply or not changed:
                return result
            if raw is not None:
                backup = target.with_name(PERSONAL_NAME + ".backup-" + digest(raw))
                _publish_new(backup, raw)
                result["backup"] = str(backup)
            with tempfile.TemporaryDirectory(
                prefix=".style-catalog-", dir=target.parent
            ) as temporary:
                stage = Path(temporary) / "catalog.json"
                _publish_new(stage, output)
                if read_bytes(target, missing=True) != raw:
                    _fail(
                        "catalog_expected_mismatch",
                        "Catalog changed; preview again before applying.",
                    )
                os.replace(stage, target)
            result["applied"] = True
            return result
    except Timeout:
        _fail(
            "catalog_writer_busy",
            "Wait for the current catalog writer, then preview again.",
        )


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        _fail("catalog_usage_invalid", "Use --help for the catalog command contract.")


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(description=__doc__, allow_abbrev=False, add_help=False)
        parser.add_argument("action", nargs="?", choices=("list", "candidates", "put"))
        parser.add_argument("--help", action="store_true")
        parser.add_argument("--vault", type=Path)
        parser.add_argument("--selection", type=Path)
        parser.add_argument("--output", type=Path)
        parser.add_argument("--entry", type=Path)
        parser.add_argument("--expected-sha256")
        parser.add_argument("--apply", action="store_true")
        args = parser.parse_args(argv)
        if args.help:
            result = {"schema_version": 1, "ok": True, "help": __doc__}
        elif args.action == "list" and not any(
            (args.selection, args.output, args.entry, args.expected_sha256, args.apply)
        ):
            result = {"ok": True, **load_merged(args.vault)}
        elif (
            args.action == "candidates"
            and args.selection
            and args.output
            and not any((args.entry, args.expected_sha256, args.apply))
        ):
            candidate = seed_candidates(
                load_merged(args.vault), decode(read_bytes(args.selection))
            )
            created = _publish_new(args.output, encode(candidate))
            result = {
                "schema_version": 1,
                "ok": True,
                "created": created,
                "output": str(args.output),
                "styles": len(candidate["styles"]),
            }
        elif (
            args.action == "put"
            and args.vault
            and args.entry
            and args.expected_sha256
            and not any((args.selection, args.output))
        ):
            result = put_entry(
                args.vault,
                decode(read_bytes(args.entry)),
                args.expected_sha256,
                apply=args.apply,
            )
        else:
            _fail(
                "catalog_usage_invalid", "Use --help for the catalog command contract."
            )
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except CatalogError as exc:
        code, message = exc.code, str(exc)
        status = 2 if code == "catalog_usage_invalid" else 1
    except (OSError, ImportError):
        code, message, status = (
            "catalog_io_failed",
            "Check local file access and the configured Python dependencies, then retry.",
            1,
        )
    # Callers treat missing/invalid stdout as a silent contract failure. Emit one
    # closed JSON failure; a traceback would replace the promised JSON envelope.
    except Exception:  # noqa: BLE001 — outer-boundary-process-contract
        code, message, status = (
            "catalog_unexpected_failure",
            "Unexpected owner failure; preserve inputs and report this code.",
            2,
        )
    result = {
        "schema_version": 1,
        "ok": False,
        "error": {"code": code, "message": message},
    }
    print(json.dumps(result))
    print(message, file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())

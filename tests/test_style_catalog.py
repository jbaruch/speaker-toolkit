"""Catalog ownership, overlay, publication, and real exploration adapter contracts."""

import copy
import json
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conftest import SCRIPTS_ILL, _import_script
from test_generate_illustrations import _write_outline


@pytest.fixture
def catalog():
    return _import_script(str(Path(SCRIPTS_ILL) / "style_catalog.py"), "style_catalog")


def personal_entry(catalog, slug="personal-ink"):
    entry = copy.deepcopy(catalog.load_merged()["styles"][0])
    entry.pop("catalog_source")
    entry["slug"] = slug
    entry["name"] = "Personal Ink"
    return entry


def selection(slugs=None, **updates):
    return {
        "schema_version": 1,
        "slugs": slugs or ["comic-book-hero"],
        "slides": {"FULL": 3},
        "models": ["gemini-3-pro-image"],
        **updates,
    }


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_packaged_seeds_are_closed_versioned_references(catalog):
    merged = catalog.load_merged()
    assert {style["slug"] for style in merged["styles"]} == {
        "comic-book-hero",
        "isometric-systems-3d",
        "illuminated-manuscript",
    }
    for style in merged["styles"]:
        catalog.validate_candidate_style(style)
        assert style["catalog_source"]["layer"] == "public"
        assert style["sample"]["kind"] == "reference"
        assert "not bundled" in style["sample"]["description"]
        assert "EMBEDDED TITLE" not in style["anchors"]["FULL"]
    assert merged["personal_sha256"] == "missing"


def test_personal_shadow_and_union_leave_public_untouched(catalog, tmp_path):
    original = catalog.PUBLIC_PATH.read_bytes()
    entry = personal_entry(catalog, "comic-book-hero")
    custom = personal_entry(catalog)
    write_json(
        tmp_path / catalog.PERSONAL_NAME,
        {"schema_version": 1, "styles": [entry, custom]},
    )
    merged = catalog.load_merged(tmp_path)
    assert len(merged["styles"]) == 4
    shadow = next(
        style for style in merged["styles"] if style["slug"] == "comic-book-hero"
    )
    assert shadow["name"] == "Personal Ink"
    assert shadow["catalog_source"]["layer"] == "personal"
    assert catalog.PUBLIC_PATH.read_bytes() == original


@pytest.mark.parametrize("version", [None, True, 0, 2, "1"])
def test_unknown_personal_generations_never_fall_back_or_rewrite(
    catalog, tmp_path, version
):
    path = write_json(
        tmp_path / catalog.PERSONAL_NAME, {"schema_version": version, "styles": []}
    )
    original = path.read_bytes()
    with pytest.raises(catalog.CatalogError, match="Update the owner"):
        catalog.load_merged(tmp_path)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("slug", "../../bad"),
        ("name", "two\nlines"),
        ("name", ""),
        ("anchors", {"FULL": "x"}),
        ("anchors", {"FULL": "", "IMG+TXT": "x"}),
        ("composition", "anything"),
        ("composition", []),
        ("text_treatment", ""),
        ("tags", ["same", "same"]),
        ("tags", ["bad tag"]),
        ("tags", []),
        ("conventions", 2),
        ("sample", {"schema_version": 2}),
        ("provenance", {"schema_version": 1}),
    ],
)
def test_invalid_records_refused_before_publication(catalog, tmp_path, field, value):
    entry = personal_entry(catalog)
    entry[field] = value
    with pytest.raises(catalog.CatalogError):
        catalog.put_entry(tmp_path, entry, "missing", apply=True)
    assert not (tmp_path / catalog.PERSONAL_NAME).exists()


def test_duplicate_slug_and_unknown_field_refused(catalog):
    entry = personal_entry(catalog)
    with pytest.raises(catalog.CatalogError, match="unique"):
        catalog.validate_catalog({"schema_version": 1, "styles": [entry, entry]})
    with pytest.raises(catalog.CatalogError, match="closed"):
        catalog.validate_entry({**entry, "future": True})


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":1,"schema_version":1}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b"\xff",
        b"{bad",
    ],
)
def test_strict_json(catalog, raw):
    with pytest.raises(catalog.CatalogError):
        catalog.decode(raw)


def test_private_sample_not_accepted_as_public(catalog):
    entry = personal_entry(catalog)
    entry["sample"].update(kind="local-image", location="private.png")
    catalog.validate_entry(entry)
    with pytest.raises(catalog.CatalogError, match="consented public"):
        catalog.validate_entry(entry, public=True)
    entry["sample"].update(
        kind="remote-image", location="https://user:password@example.test/image.png"
    )
    with pytest.raises(catalog.CatalogError, match="without credentials"):
        catalog.validate_entry(entry)


@pytest.mark.parametrize(
    "userinfo",
    ["user:synthetic-password", ":synthetic-password", "user:", ":", "user", ""],
)
@pytest.mark.parametrize("field", ["sample", "provenance"])
def test_public_url_userinfo_is_always_refused(catalog, userinfo, field):
    entry = personal_entry(catalog)
    location = "location" if field == "sample" else "reference"
    entry[field][location] = f"https://{userinfo}@example.test/image.png"
    with pytest.raises(catalog.CatalogError, match="without credentials"):
        catalog.validate_entry(entry, public=True)


def test_cli_does_not_echo_password_with_empty_username(catalog, tmp_path):
    entry = personal_entry(catalog)
    entry["sample"]["location"] = "https://:synthetic-password@example.test/image.png"
    path = write_json(
        tmp_path / catalog.PERSONAL_NAME, {"schema_version": 1, "styles": [entry]}
    )
    original = path.read_bytes()
    result = subprocess.run(
        [sys.executable, catalog.__file__, "list", "--vault", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "catalog_reference_invalid"
    assert "synthetic-password" not in result.stdout + result.stderr
    assert path.read_bytes() == original


def test_preview_apply_backup_and_exact_idempotence(catalog, tmp_path):
    entry = personal_entry(catalog)
    preview = catalog.put_entry(tmp_path, entry, "missing")
    target = tmp_path / catalog.PERSONAL_NAME
    assert preview["changed"] and not preview["applied"]
    assert not target.exists()
    applied = catalog.put_entry(tmp_path, entry, "missing", apply=True)
    assert applied["output_sha256"] == preview["output_sha256"]
    assert applied["applied"] and applied["backup"] is None
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    # Keep unusual input whitespace byte-for-byte on a semantic no-op.
    original = b"  " + target.read_bytes() + b"\n"
    target.write_bytes(original)
    unchanged = catalog.put_entry(tmp_path, entry, catalog.digest(original), apply=True)
    assert not unchanged["changed"] and not unchanged["applied"]
    assert target.read_bytes() == original
    second = personal_entry(catalog, "second-style")
    changed = catalog.put_entry(tmp_path, second, catalog.digest(original), apply=True)
    assert Path(changed["backup"]).read_bytes() == original
    assert len(catalog.load_merged(tmp_path)["styles"]) == 5
    assert (
        next(
            item
            for item in json.loads(target.read_bytes())["styles"]
            if item["slug"] == entry["slug"]
        )
        == entry
    )


def test_stale_digest_and_commit_failure_preserve_catalog(
    catalog, tmp_path, monkeypatch
):
    entry = personal_entry(catalog)
    catalog.put_entry(tmp_path, entry, "missing", apply=True)
    target = tmp_path / catalog.PERSONAL_NAME
    original = target.read_bytes()
    entry["name"] = "Changed"
    with pytest.raises(catalog.CatalogError, match="preview again"):
        catalog.put_entry(tmp_path, entry, "missing", apply=True)

    def fail_replace(*args):
        raise OSError("synthetic commit failure")

    monkeypatch.setattr(catalog.os, "replace", fail_replace)
    with pytest.raises(OSError):
        catalog.put_entry(tmp_path, entry, catalog.digest(original), apply=True)
    assert target.read_bytes() == original
    assert next(tmp_path.glob("*.backup-*")).read_bytes() == original
    assert not list(tmp_path.glob(".style-catalog-*"))


def test_symlink_and_large_catalog_never_opened(catalog, tmp_path, monkeypatch):
    real = tmp_path / "real.json"
    real.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(catalog.CatalogError, match="regular local"):
        catalog.read_bytes(link)
    monkeypatch.setattr(catalog, "MAX_BYTES", 1)
    with pytest.raises(catalog.CatalogError, match="regular local"):
        catalog.read_bytes(real)


def test_cloud_placeholder_is_metadata_only(catalog, tmp_path, monkeypatch):
    path = tmp_path / "placeholder.json"
    info = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o600, st_size=10, st_flags=0x40000000
    )
    monkeypatch.setattr(Path, "lstat", lambda self: info)

    def forbidden(*args):
        pytest.fail("placeholder was opened")

    monkeypatch.setattr(catalog.os, "open", forbidden)
    with pytest.raises(catalog.CatalogError, match="available locally"):
        catalog.read_bytes(path)


def test_input_change_detected(catalog, tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    path.write_text("{}")
    original = Path.lstat
    calls = []

    def changed(self):
        calls.append(self)
        if len(calls) == 2:
            self.write_text('{"changed":true}')
        return original(self)

    monkeypatch.setattr(Path, "lstat", changed)
    with pytest.raises(catalog.CatalogError, match="changed during"):
        catalog.read_bytes(path)


def test_regular_catalog_read_without_posix_open_flags(catalog, tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    raw = b'{\r\n  "schema_version": 1, "styles": []\r\n}\r\n'
    path.write_bytes(raw)
    monkeypatch.delattr(catalog.os, "O_NONBLOCK", raising=False)
    monkeypatch.delattr(catalog.os, "O_NOFOLLOW", raising=False)
    assert catalog.read_bytes(path) == raw


def test_binary_flag_is_used_where_available(catalog, tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    path.write_bytes(b"{}\r\n")
    original_open = catalog.os.open
    binary_flag = getattr(catalog.os, "O_BINARY", 1 << 27)
    monkeypatch.setattr(catalog.os, "O_BINARY", binary_flag, raising=False)
    seen = []

    def open_binary(candidate, flags):
        seen.append(flags)
        # Simulate a platform with O_BINARY while executing the byte read locally.
        return original_open(candidate, catalog.os.O_RDONLY)

    monkeypatch.setattr(catalog.os, "open", open_binary)
    assert catalog.read_bytes(path) == b"{}\r\n"
    assert seen[0] & binary_flag


@pytest.mark.parametrize("kind", ["missing", "file", "below-file"])
def test_invalid_vault_has_specific_closed_cli_diagnostic(catalog, tmp_path, kind):
    path = tmp_path / "vault"
    if kind in ("file", "below-file"):
        path.write_text("not a vault")
    if kind == "below-file":
        path = path / "nested"
    result = subprocess.run(
        [sys.executable, catalog.__file__, "list", "--vault", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "catalog_vault_invalid"
    assert "Select an existing vault directory" in result.stderr


@pytest.mark.parametrize(
    "updates",
    [
        {"schema_version": 2},
        {"slugs": ["missing"]},
        {"slugs": ["comic-book-hero", "comic-book-hero"]},
        {"slides": {"FULL": True}},
        {"slides": {"FULL": 0}},
        {"slides": {"IMG+TXT": 3}},
        {"slides": {"other": 3}},
        {"models": []},
        {"models": ["has space"]},
        {"models": ["same", "same"]},
    ],
)
def test_bad_selection_refused(catalog, updates):
    with pytest.raises(catalog.CatalogError):
        catalog.seed_candidates(catalog.load_merged(), selection(**updates))


def test_candidate_projection_preserves_style_and_source(
    catalog, generate_illustrations, tmp_path
):
    merged = catalog.load_merged()
    projected = catalog.seed_candidates(merged, selection())
    path = write_json(tmp_path / "candidates.json", projected)
    parsed = generate_illustrations.parse_candidates(str(path))
    assert parsed == projected
    assert parsed["schema_version"] == 2
    assert parsed["styles"][0] == merged["styles"][0]
    assert "text_treatment" in parsed["styles"][0]


def test_mixed_composition_and_output_name_collision_refused(catalog):
    merged = catalog.load_merged()
    styles = merged["styles"]
    styles[1]["composition"] = "overlay"
    selected = selection([style["slug"] for style in styles[:2]])
    with pytest.raises(catalog.CatalogError, match="one composition"):
        catalog.seed_candidates(merged, selected)
    styles[1]["composition"] = styles[0]["composition"]
    styles[1]["name"] = styles[0]["name"].upper()
    with pytest.raises(catalog.CatalogError, match="distinct display"):
        catalog.seed_candidates(merged, selected)


@pytest.mark.parametrize("poster", [True, False])
def test_real_exploration_adapter_uses_catalog_prompt(
    catalog, generate_illustrations, tmp_path, monkeypatch, poster
):
    gi = generate_illustrations
    merged = catalog.load_merged()
    style = merged["styles"][0]
    if not poster:
        style["composition"] = "overlay"
        style["text_treatment"] = ""
    projected = catalog.seed_candidates(merged, selection())
    cpath = write_json(tmp_path / "candidates.json", projected)
    outline = _write_outline(
        tmp_path,
        model="gemini-3-pro-image",
        slides=[
            {
                "n": 3,
                "chapter": "c",
                "title": "A choice",
                "format": "FULL",
                "text_overlay": "ACTUAL SLIDE TITLE",
                "image_prompt": "[STYLE ANCHOR] A single ladder.",
            }
        ],
    )
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    prompts = []

    def generate(prompt, model, keys, fmt):
        prompts.append((prompt, fmt))
        return b"synthetic image transport", "image/png"

    monkeypatch.setattr(gi, "generate_image", generate)
    gi.run_style_explore(str(outline), str(cpath))
    assert len(prompts) == 1
    prompt, fmt = prompts[0]
    assert fmt == "FULL"
    assert style["anchors"]["FULL"] in prompt and style["conventions"] in prompt
    assert "A single ladder." in prompt and gi.COMPOSE_ONLY_DIRECTIVE in prompt
    assert ("ACTUAL SLIDE TITLE" in prompt) is poster
    assert ("EMBEDDED TEXT" in prompt) is poster
    assert (style["text_treatment"] in prompt) if poster else True
    manifest = json.loads((tmp_path / "style-explore" / "rendered.json").read_text())
    assert manifest["cells"][0]["status"] == "OK"


def test_poster_missing_title_refuses_before_render(
    catalog, generate_illustrations, tmp_path, monkeypatch, capsys
):
    candidate = write_json(
        tmp_path / "candidates.json",
        catalog.seed_candidates(catalog.load_merged(), selection()),
    )
    outline = _write_outline(
        tmp_path,
        model="gemini-3-pro-image",
        slides=[
            {
                "n": 3,
                "chapter": "c",
                "title": "No text",
                "format": "FULL",
                "image_prompt": "[STYLE ANCHOR] Ladder.",
            }
        ],
    )
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")

    def forbidden(*args):
        pytest.fail("invalid poster was rendered")

    monkeypatch.setattr(generate_illustrations, "generate_image", forbidden)
    with pytest.raises(SystemExit) as error:
        generate_illustrations.run_style_explore(str(outline), str(candidate))
    assert error.value.code == 1
    assert "text_overlay" in capsys.readouterr().err


def test_cli_candidates_round_trip_and_preserves_changed_output(catalog, tmp_path):
    source = write_json(tmp_path / "selection.json", selection())
    output = tmp_path / "candidates.json"
    command = [
        sys.executable,
        catalog.__file__,
        "candidates",
        "--selection",
        str(source),
        "--output",
        str(output),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0 and json.loads(first.stdout)["created"]
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode == 0 and not json.loads(second.stdout)["created"]
    output.write_text("keep me")
    refused = subprocess.run(command, capture_output=True, text=True, check=False)
    assert (
        refused.returncode == 1
        and json.loads(refused.stdout)["error"]["code"] == "catalog_output_exists"
    )
    assert output.read_text() == "keep me"


@pytest.mark.parametrize(
    "args,status",
    [(["--help"], 0), (["list"], 0), (["put"], 2), (["list", "--app"], 2)],
)
def test_cli_json_contract(catalog, args, status):
    result = subprocess.run(
        [sys.executable, catalog.__file__, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == status
    assert json.loads(result.stdout)["ok"] is (status == 0)
    assert bool(result.stderr) is (status != 0)


def test_outer_boundary_redacts_unexpected_and_preserves_interrupts(
    catalog, monkeypatch, capsys
):
    def unexpected(*args):
        raise RuntimeError("private secret input")

    monkeypatch.setattr(catalog, "load_merged", unexpected)
    assert catalog.main(["list"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "catalog_unexpected_failure"
    assert "private secret" not in captured.out + captured.err

    def interrupted(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(catalog, "load_merged", interrupted)
    with pytest.raises(KeyboardInterrupt):
        catalog.main(["list"])


@pytest.mark.parametrize(
    "damage",
    ["root-bool", "style-future", "missing-source", "extra-field", "duplicate-key"],
)
def test_malformed_v2_candidates_are_not_legacy_fallback(
    catalog, generate_illustrations, tmp_path, damage
):
    candidate = catalog.seed_candidates(catalog.load_merged(), selection())
    if damage == "root-bool":
        candidate["schema_version"] = True
    elif damage == "style-future":
        candidate["styles"][0]["schema_version"] = 2
    elif damage == "missing-source":
        candidate["styles"][0].pop("catalog_source")
    elif damage == "extra-field":
        candidate["styles"][0]["future"] = "refuse"
    path = write_json(tmp_path / "candidates.json", candidate)
    if damage == "duplicate-key":
        path.write_text(
            path.read_text().replace(
                '"schema_version": 2', '"schema_version": 1, "schema_version": 2', 1
            )
        )
    original = path.read_bytes()
    with pytest.raises(ValueError):
        generate_illustrations.parse_candidates(str(path))
    assert path.read_bytes() == original


def test_cli_put_requires_explicit_apply(catalog, tmp_path):
    entry_path = write_json(tmp_path / "entry.json", personal_entry(catalog))
    command = [
        sys.executable,
        catalog.__file__,
        "put",
        "--vault",
        str(tmp_path),
        "--entry",
        str(entry_path),
        "--expected-sha256",
        "missing",
    ]
    preview = subprocess.run(command, capture_output=True, text=True, check=False)
    assert preview.returncode == 0 and not json.loads(preview.stdout)["applied"]
    assert not (tmp_path / catalog.PERSONAL_NAME).exists()
    applied = subprocess.run(
        [*command, "--apply"], capture_output=True, text=True, check=False
    )
    assert applied.returncode == 0 and json.loads(applied.stdout)["applied"]
    assert (
        json.loads(preview.stdout)["output_sha256"]
        == json.loads(applied.stdout)["output_sha256"]
    )


def test_owner_lock_failure_preserves_absent_catalog(catalog, tmp_path, monkeypatch):
    import filelock

    def busy(*args, **kwargs):
        raise filelock.Timeout("synthetic-lock")

    monkeypatch.setattr(filelock, "FileLock", busy)
    with pytest.raises(catalog.CatalogError, match="current catalog writer"):
        catalog.put_entry(tmp_path, personal_entry(catalog), "missing", apply=True)
    assert not (tmp_path / catalog.PERSONAL_NAME).exists()


def test_contribution_form_requires_complete_payload_and_consent():
    import yaml

    path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "ISSUE_TEMPLATE"
        / "style-contribution.yml"
    )
    form = yaml.safe_load(path.read_text())
    assert form["labels"] == ["style-contribution"]
    inputs = {item["id"]: item for item in form["body"] if "id" in item}
    assert set(inputs) == {"entry", "sample", "provenance", "consent"}
    assert all(
        inputs[key]["validations"]["required"]
        for key in ("entry", "sample", "provenance")
    )
    assert all(
        option["required"] for option in inputs["consent"]["attributes"]["options"]
    )

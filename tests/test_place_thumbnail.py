"""Shownotes gets PNG bytes without changing the generated source image."""

import builtins
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills/shownotes-publisher/scripts/place-thumbnail.py"
)
spec = importlib.util.spec_from_file_location("place_thumbnail", SCRIPT)
assert spec is not None and spec.loader is not None
placement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(placement)


def image_file(path, *, format="JPEG", size=(1280, 720), mode="RGB"):
    Image.new(mode, size, (24, 64, 96, 128) if mode == "RGBA" else (24, 64, 96)).save(
        path, format=format
    )
    return path


@pytest.mark.parametrize("size", [(400, 300), (1280, 720)])
def test_jpeg_with_png_filename_becomes_png_and_keeps_original(tmp_path, size):
    source = image_file(tmp_path / "generated.png", size=size)
    original = source.read_bytes()
    destination = tmp_path / "site" / "talk-thumbnail.png"

    receipt = placement.place_thumbnail(source, destination)

    assert receipt["ok"] is True
    assert receipt["mime_type"] == "image/png"
    assert source.read_bytes() == original
    with Image.open(source) as before, Image.open(destination) as after:
        assert after.format == "PNG"
        assert after.size == before.size == size
        assert after.tobytes() == before.tobytes()
    placed = destination.read_bytes()
    assert placement.place_thumbnail(source, destination) == receipt
    assert destination.read_bytes() == placed
    assert list(destination.parent.iterdir()) == [destination]


def test_png_copy_preserves_transparency_and_exact_bytes(tmp_path):
    source = image_file(tmp_path / "generated.png", format="PNG", mode="RGBA")
    destination = tmp_path / "talk-thumbnail.png"

    placement.place_thumbnail(source, destination)

    assert destination.read_bytes() == source.read_bytes()
    with Image.open(destination) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0)) == (24, 64, 96, 128)


@pytest.mark.parametrize("size", [(400, 300), (640, 480), (1280, 720)])
def test_existing_valid_png_is_verified_without_rewriting(tmp_path, size):
    destination = image_file(tmp_path / "talk-thumbnail.png", format="PNG", size=size)
    original = destination.read_bytes()

    receipt = placement.place_thumbnail(destination, destination)
    assert receipt["ok"] is True
    assert receipt["dimensions"] == list(size)

    assert destination.read_bytes() == original


@pytest.mark.parametrize("bad_image", ["unsupported", "invalid", "truncated"])
def test_invalid_source_preserves_an_existing_destination(tmp_path, bad_image):
    source = tmp_path / "source.png"
    if bad_image == "unsupported":
        image_file(source, format="GIF")
    elif bad_image == "truncated":
        image_file(source)
        source.write_bytes(source.read_bytes()[:100])
    else:
        source.write_bytes(b"not an image")
    original = source.read_bytes()
    destination = tmp_path / "talk-thumbnail.png"
    destination.write_bytes(b"existing content")

    with pytest.raises((OSError, ValueError)):
        placement.place_thumbnail(source, destination)

    assert source.read_bytes() == original
    assert destination.read_bytes() == b"existing content"


def test_jpeg_cannot_overwrite_itself_with_a_different_format(tmp_path):
    source = image_file(tmp_path / "talk-thumbnail.png")
    original = source.read_bytes()

    with pytest.raises(ValueError):
        placement.place_thumbnail(source, source)

    assert source.read_bytes() == original


def test_failed_replacement_preserves_existing_destination(tmp_path, monkeypatch):
    source = image_file(tmp_path / "source.jpg")
    destination = tmp_path / "site" / "talk-thumbnail.png"
    destination.parent.mkdir()
    destination.write_bytes(b"existing content")

    def denied_replace(*_args):
        raise PermissionError("destination is read-only")

    monkeypatch.setattr(placement.os, "replace", denied_replace)

    with pytest.raises(placement.ThumbnailPlacementError):
        placement.place_thumbnail(source, destination)

    assert destination.read_bytes() == b"existing content"
    assert list(destination.parent.iterdir()) == [destination]


def test_cli_runs_from_unrelated_directory_with_spaces(tmp_path):
    source = image_file(tmp_path / "generated image.jpg")
    destination = tmp_path / "site with spaces" / "talk-thumbnail.png"
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--destination",
            str(destination),
        ],
        cwd=unrelated,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "ok": True,
        "path": str(destination),
        "mime_type": "image/png",
        "dimensions": [1280, 720],
    }
    assert result.stderr == ""
    with Image.open(destination) as image:
        assert image.format == "PNG"


def test_cli_reports_bad_input_without_creating_destination(tmp_path):
    destination = tmp_path / "site" / "talk-thumbnail.png"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(tmp_path / "missing.jpg"),
            "--destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False
    assert result.stderr
    assert "read thumbnail source" in result.stderr
    assert "select a readable source" in result.stderr
    assert "Traceback" not in result.stderr
    assert not destination.parent.exists()


@pytest.mark.parametrize("failure", ["truncated_source", "destination_parent_file"])
def test_cli_failure_names_the_repair_for_its_operation(tmp_path, failure):
    source = image_file(tmp_path / "source.jpg")
    destination = tmp_path / "site" / "talk-thumbnail.png"
    if failure == "truncated_source":
        source.write_bytes(source.read_bytes()[:100])
        expected = ("decode thumbnail source", "regenerate it with illustrations")
    else:
        destination.parent.write_text("a file blocks this directory")
        expected = ("destination", "write permissions and free space")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False
    assert all(instruction in result.stderr for instruction in expected)
    assert "Traceback" not in result.stderr
    assert not destination.exists()


def test_destination_extension_must_match_png_bytes(tmp_path):
    source = image_file(tmp_path / "source.jpg")
    destination = tmp_path / "talk-thumbnail.jpg"

    with pytest.raises(ValueError):
        placement.place_thumbnail(source, destination)

    assert not destination.exists()


def test_decode_limit_failure_leaves_destination_untouched(tmp_path, monkeypatch):
    source = image_file(tmp_path / "source.jpg")
    destination = tmp_path / "talk-thumbnail.png"
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)

    with pytest.raises(ValueError):
        placement.place_thumbnail(source, destination)

    assert not destination.exists()


def test_cli_missing_decoder_reports_runtime_repair(tmp_path, monkeypatch, capsys):
    original_import = builtins.__import__

    def without_pillow(name, *args, **kwargs):
        if name == "PIL":
            raise ImportError("Pillow unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_pillow)

    assert (
        placement.main(
            [
                "--source",
                str(tmp_path / "source.jpg"),
                "--destination",
                str(tmp_path / "out.png"),
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert json.loads(output.out)["ok"] is False
    assert "runtime" in output.err

"""A stamped poster footer is pixel-identical across slides (#474)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageChops

from conftest import SCRIPTS_ILL, _import_script

FOOTER = "@jbaruch    @gamussa    #wearedevs    #RoboCoders    speaking.jbaru.ch"
STYLE = {
    "font_path": None,
    "font_index": 0,
    "target_width_pct": 82.0,
    "baseline_from_bottom_pct": 3.8,
    "color": "#F2EFE6",
}


@pytest.fixture
def stamp():
    return _import_script(str(Path(SCRIPTS_ILL) / "footer_stamp.py"), "footer_stamp")


def _scene(color, size=(1536, 864)):
    return Image.new("RGB", size, color)


def _glyphs(stamp, image):
    inked = stamp.footer_mask(image.size, FOOTER, STYLE).point(
        lambda value: 255 if value == 255 else 0
    )
    return ImageChops.multiply(image.convert("L"), inked)


def test_the_footer_is_pixel_identical_over_any_scene(stamp):
    """A regenerated slide is a new scene; its footer must not change."""
    first = stamp.stamp_footer(_scene((20, 30, 40)), FOOTER, STYLE)
    regenerated = stamp.stamp_footer(_scene((150, 60, 10)), FOOTER, STYLE)
    assert (
        ImageChops.difference(
            _glyphs(stamp, first), _glyphs(stamp, regenerated)
        ).getbbox()
        is None
    )


def test_the_footer_spans_the_target_width_at_the_target_baseline(stamp):
    width, height = 1536, 864
    box = stamp.footer_mask((width, height), FOOTER, STYLE).getbbox()
    assert box is not None
    left, top, right, bottom = box
    assert abs((right - left) / width * 100 - STYLE["target_width_pct"]) < 2
    assert abs((left + right) / 2 - width / 2) <= 2
    baseline = height * (1 - STYLE["baseline_from_bottom_pct"] / 100)
    assert top < baseline <= bottom


def test_verification_accepts_the_stamp_and_refuses_anything_else(stamp, tmp_path):
    stamped = stamp.stamp_footer(_scene((20, 30, 40)), FOOTER, STYLE)
    assert stamp.verify_footer(stamped, FOOTER, STYLE)[0] is True
    assert stamp.verify_footer(_scene((20, 30, 40)), FOOTER, STYLE)[0] is False
    assert stamp.verify_footer(stamped, FOOTER + " extra", STYLE)[0] is False
    written = stamp.stamp_footer_file(
        _save(_scene((20, 30, 40)), tmp_path / "slide-03.jpg"),
        tmp_path / "footer-stamped",
        FOOTER,
        STYLE,
    )
    assert written == tmp_path / "footer-stamped" / "slide-03.png"
    with Image.open(written) as reread:
        assert reread.format == "PNG"
        assert stamp.verify_footer(reread, FOOTER, STYLE) == (True, 1.0)


def _save(image, path):
    image.save(path, quality=95)
    return path


def _busy_scene(seed_color, size=(1536, 864)):
    """A scene with detail under the footer, the case JPEG re-encoding smears."""
    image = _scene(seed_color, size)
    pixels = image.load()
    assert pixels is not None
    for x in range(size[0]):
        for y in range(size[1] - 120, size[1]):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 5) % 256)
    return image


def test_written_footers_are_pixel_identical_across_scenes(stamp, tmp_path):
    """Write, reopen, compare: the footer never depends on the scene behind it."""
    out = tmp_path / "footer-stamped"
    first = stamp.stamp_footer_file(
        _save(_busy_scene((20, 30, 40)), tmp_path / "slide-03.jpg"), out, FOOTER, STYLE
    )
    second = stamp.stamp_footer_file(
        _save(_busy_scene((200, 90, 10)), tmp_path / "slide-04.jpg"),
        out,
        FOOTER,
        STYLE,
    )
    inked = stamp.footer_mask((1536, 864), FOOTER, STYLE).point(
        lambda value: 255 if value == 255 else 0
    )
    black = Image.new("RGB", (1536, 864), (0, 0, 0))
    with Image.open(first) as a, Image.open(second) as b:
        glyphs_a = Image.composite(a.convert("RGB"), black, inked)
        glyphs_b = Image.composite(b.convert("RGB"), black, inked)
    assert ImageChops.difference(glyphs_a, glyphs_b).getbbox() is None
    assert glyphs_a.getbbox() is not None


@pytest.mark.parametrize(
    "text,style,detail",
    [
        ("   ", STYLE, "footer text is empty"),
        (FOOTER, {**STYLE, "extra": 1}, "must carry exactly"),
        (FOOTER, {**STYLE, "color": "white"}, "#RRGGBB"),
        (
            FOOTER,
            {**STYLE, "font_path": "/nowhere/font.ttf"},
            "cannot load footer font",
        ),
        ("x" * 4000, STYLE, "too long to fit"),
    ],
    ids=["empty", "closed-style", "color", "font", "too-long"],
)
def test_an_unusable_footer_is_refused_with_a_fix(stamp, text, style, detail):
    with pytest.raises(stamp.FooterStampError, match=detail):
        stamp.stamp_footer(_scene((0, 0, 0)), text, style)


def test_the_reserved_strip_covers_the_footer(stamp):
    strip = stamp.reserved_strip_pct(FOOTER, STYLE)
    box = stamp.footer_mask(stamp.REFERENCE_FRAME, FOOTER, STYLE).getbbox()
    height = stamp.REFERENCE_FRAME[1]
    assert strip > (height - box[1]) / height * 100
    assert strip < 25

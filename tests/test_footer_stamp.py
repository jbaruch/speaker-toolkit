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
        tmp_path / "footer-stamped" / "slide-03.jpg",
        FOOTER,
        STYLE,
    )
    with Image.open(written) as reread:
        assert stamp.verify_footer(reread, FOOTER, STYLE)[0] is True


def _save(image, path):
    image.save(path, quality=95)
    return path


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

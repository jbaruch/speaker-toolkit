"""Stamp a poster deck's footer deterministically onto each slide image (#474).

An image model rendering the same literal footer on every slide still changes
its font, size, weight, spacing and baseline from slide to slide. With
`style_anchor.footer_style` set, generation leaves the footer out and this
module draws it: one real font, sized to span `target_width_pct` of the slide,
centred, its baseline `baseline_from_bottom_pct` above the bottom edge, in
`color`. The same text and style on a frame of the same size produce identical
footer pixels, so the footer is pixel-consistent across the deck and a
regenerated slide cannot change it.

`stamp_footer` returns a new flattened RGB image; `verify_footer` checks a
stamped image against the footer the style prescribes. `style` is a mapping
with exactly the `FooterStyle` fields in
`skills/presentation-creator/scripts/outline_schema.py`, which owns their
defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont

STYLE_FIELDS = frozenset(
    {
        "font_path",
        "font_index",
        "target_width_pct",
        "baseline_from_bottom_pct",
        "color",
    }
)
MIN_FONT_SIZE = 4
# Strip reservation is measured on a 16:9 frame; the margin keeps scene detail
# a little clear of the footer's tallest glyph.
REFERENCE_FRAME = (1600, 900)
STRIP_MARGIN_PCT = 2.0
# A stamped pixel inside a glyph counts as the footer colour within this many
# levels per channel, which absorbs JPEG re-encoding. VERIFY_MIN_MATCH is the
# share of fully-inked glyph pixels that must match.
VERIFY_CHANNEL_TOLERANCE = 48
VERIFY_MIN_MATCH = 0.9
# Lookup tables for `Image.point`: glyph pixels at full coverage, and channel
# differences within the tolerance.
_FULLY_INKED = [255 if level == 255 else 0 for level in range(256)]
_WITHIN_TOLERANCE = [
    255 if level <= VERIFY_CHANNEL_TOLERANCE else 0 for level in range(256)
]


class FooterStampError(ValueError):
    """The footer style or text cannot produce a stamp."""


def _require_style(style: Mapping[str, Any]) -> None:
    if set(style) != STYLE_FIELDS:
        raise FooterStampError(
            f"footer style must carry exactly {sorted(STYLE_FIELDS)}; got "
            f"{sorted(style)} — pass outline_schema.FooterStyle.model_dump()"
        )


def _rgb(color: str) -> tuple[int, int, int]:
    if len(color) != 7 or not color.startswith("#"):
        raise FooterStampError(f"footer color must be #RRGGBB, not {color!r}")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _font(style: Mapping[str, Any], size: int) -> ImageFont.FreeTypeFont:
    path = style["font_path"]
    try:
        font = (
            ImageFont.truetype(
                str(Path(path).expanduser()), size, index=style["font_index"]
            )
            if path
            else ImageFont.load_default(size=size)
        )
    except OSError as exc:
        raise FooterStampError(
            f"cannot load footer font {path!r} ({exc}); point "
            "style_anchor.footer_style.font_path at a TrueType/OpenType file"
        ) from exc
    if not isinstance(font, ImageFont.FreeTypeFont):
        raise FooterStampError(
            "the bundled footer font needs Pillow's FreeType support; install a "
            "FreeType-enabled Pillow or set footer_style.font_path"
        )
    return font


def fitted_font(
    text: str, style: Mapping[str, Any], frame_width: int
) -> ImageFont.FreeTypeFont:
    """The largest size whose rendered text fits the style's target width."""
    target = frame_width * float(style["target_width_pct"]) / 100.0
    low, high = MIN_FONT_SIZE, max(MIN_FONT_SIZE, frame_width)
    if _font(style, low).getlength(text) > target:
        raise FooterStampError(
            f"footer text is too long to fit {style['target_width_pct']}% of a "
            f"{frame_width}px frame at {MIN_FONT_SIZE}px; shorten it or widen "
            "target_width_pct"
        )
    while low < high:
        middle = (low + high + 1) // 2
        if _font(style, middle).getlength(text) <= target:
            low = middle
        else:
            high = middle - 1
    return _font(style, low)


def _draw(canvas: Image.Image, text: str, style: Mapping[str, Any], fill: Any) -> None:
    width, height = canvas.size
    font = fitted_font(text, style, width)
    baseline = height * (1.0 - float(style["baseline_from_bottom_pct"]) / 100.0)
    ImageDraw.Draw(canvas).text(
        (width / 2.0, baseline), text, font=font, fill=fill, anchor="ms"
    )


def reserved_strip_pct(
    text: str, style: Mapping[str, Any], frame: tuple[int, int] = REFERENCE_FRAME
) -> float:
    """The bottom share of the frame the footer occupies, plus a margin.

    Generation reserves this strip so the stamped footer lands on quiet ground;
    it is measured from the same glyph rendering the stamp uses.
    """
    box = footer_mask(frame, text, style).getbbox()
    if box is None:
        raise FooterStampError("footer text renders no glyphs; check embedded_footer")
    return (frame[1] - box[1]) / frame[1] * 100.0 + STRIP_MARGIN_PCT


def stamp_footer(
    image: Image.Image, text: str, style: Mapping[str, Any]
) -> Image.Image:
    """Return a flattened RGB copy of ``image`` carrying the footer."""
    _require_style(style)
    if not text.strip():
        raise FooterStampError("footer text is empty; set style_anchor.embedded_footer")
    stamped = image.convert("RGB")
    _draw(stamped, text, style, _rgb(style["color"]))
    return stamped


def footer_mask(
    size: tuple[int, int], text: str, style: Mapping[str, Any]
) -> Image.Image:
    """The footer's glyph coverage on a frame of ``size`` (255 = fully inked)."""
    _require_style(style)
    mask = Image.new("L", size, 0)
    _draw(mask, text, style, 255)
    return mask


def verify_footer(
    image: Image.Image, text: str, style: Mapping[str, Any]
) -> tuple[bool, float]:
    """Whether ``image`` carries this exact footer, and the matching share."""
    rgb = image.convert("RGB")
    inked = footer_mask(rgb.size, text, style).point(_FULLY_INKED)
    red, green, blue = ImageChops.difference(
        rgb, Image.new("RGB", rgb.size, _rgb(style["color"]))
    ).split()
    worst = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    close = worst.point(_WITHIN_TOLERANCE)
    inked_count = inked.histogram()[255]
    if inked_count == 0:
        return False, 0.0
    matched = ImageChops.multiply(close, inked).histogram()[255]
    share = matched / inked_count
    return share >= VERIFY_MIN_MATCH, share


def stamp_footer_file(
    source: Path, destination: Path, text: str, style: Mapping[str, Any]
) -> Path:
    """Stamp ``source`` into ``destination`` and verify the written file."""
    with Image.open(source) as image:
        stamped = stamp_footer(image, text, style)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stamped.save(destination, quality=95)
    with Image.open(destination) as written:
        ok, share = verify_footer(written, text, style)
    if not ok:
        raise FooterStampError(
            f"stamped footer on {destination.name} matched only {share:.0%} of "
            "its glyph pixels; check footer_style.color against the image"
        )
    return destination

"""Stamp a poster deck's footer deterministically onto each slide image (#474).

An image model rendering the same literal footer on every slide still changes
its font, size, weight, spacing and baseline from slide to slide. With
`style_anchor.footer_style` set, generation leaves the footer out and this
module draws it: one real font, sized to span `target_width_pct` of the slide,
centred, its baseline `baseline_from_bottom_pct` above the bottom edge, in
`color`. Glyphs are rasterized without antialiasing, so every glyph pixel is
the footer colour and none blends with the scene: the same text and style on a
frame of the same size produce identical footer pixels over any scene, and a
regenerated slide cannot change them. Geometry whose glyphs would leave the
frame is refused.

`stamp_footer` returns a new flattened RGB image. `verify_footer` checks that
every glyph pixel carries exactly the footer colour and that the footer stands
out from the ground around it (`MIN_CONTRAST_RATIO`), so neither an image of
the footer colour nor a footer stamped onto a matching strip passes.
`stamp_footer_file` refuses a slide whose footer strip would hide the footer,
and writes PNG whatever the source format, so re-encoding never makes the
footer's pixels depend on the scene behind them. `style` is a mapping
with exactly the `FooterStyle` fields in
`skills/presentation-creator/scripts/outline_schema.py`, which owns their
defaults. `stamp_spec` and `stamped_slide` are the one answer to which deck
images get a footer: apply stamps those slides and the build-expansion manifest
stamps those slides' build frames.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

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
STAMPED_SUFFIX = ".png"
# WCAG 2 contrast ratio between the footer colour and the mean colour of the
# non-glyph pixels in the footer's bounding box; 3:1 is the large-text minimum.
MIN_CONTRAST_RATIO = 3.0
# Lookup table for `Image.point`: channel differences of zero.
_EXACT = [255 if level == 0 else 0 for level in range(256)]


class FooterStampError(ValueError):
    """The footer style or text cannot produce a stamp."""


def stamp_spec(anchor: Any) -> tuple[str, dict[str, Any]] | None:
    """The footer text and style a deck stamps, or None when the model renders it.

    ``anchor`` is an outline ``StyleAnchor`` (or None); its validator already
    limits ``footer_style`` to poster decks with an embedded footer.
    """
    if anchor is None or anchor.footer_style is None or not anchor.embedded_footer:
        return None
    return anchor.embedded_footer, anchor.footer_style.model_dump()


def stamped_slide(slide: Any) -> bool:
    """Whether a poster deck's slide is an illustrated full-bleed background.

    Only an illustrated slide (one with an ``image_prompt``) that is FULL with
    no safe zone carries its footer in the image. A screenshot or other
    non-illustrated slide keeps its own treatment and is never stamped.
    """
    return (
        slide.format.value == "FULL"
        and not slide.safe_zone
        and bool(slide.image_prompt)
    )


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


def _glyph_mask(
    size: tuple[int, int], text: str, style: Mapping[str, Any]
) -> Image.Image:
    width, height = size
    font = fitted_font(text, style, width)
    baseline = height * (1.0 - float(style["baseline_from_bottom_pct"]) / 100.0)
    origin = (width / 2.0, baseline)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    # Mono rasterization: a glyph pixel is fully inked or untouched, never a
    # partial-coverage blend with whatever scene lies underneath.
    draw.fontmode = "1"
    left, top, right, bottom = draw.textbbox(origin, text, font=font, anchor="ms")
    if left < 0 or top < 0 or right > width or bottom > height:
        raise FooterStampError(
            f"footer glyphs span ({left:.0f}, {top:.0f})-({right:.0f}, {bottom:.0f}), "
            f"outside the {width}x{height} frame; raise baseline_from_bottom_pct "
            "or lower target_width_pct"
        )
    draw.text(origin, text, font=font, fill=255, anchor="ms")
    return mask


def _luminance(color: tuple[float, ...]) -> float:
    def linear(channel: float) -> float:
        value = channel / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in color[:3])
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def footer_contrast(image: Image.Image, text: str, style: Mapping[str, Any]) -> float:
    """Contrast ratio of the footer colour against the ground around its glyphs.

    The ground is the mean colour of the pixels inside the footer's bounding box
    that no glyph covers, read from ``image`` as it stands.
    """
    rgb = image.convert("RGB")
    mask = footer_mask(rgb.size, text, style)
    box = mask.getbbox()
    if box is None:
        raise FooterStampError("footer text renders no glyphs; check embedded_footer")
    ground = ImageChops.invert(mask.crop(box))
    if ground.getbbox() is None:
        raise FooterStampError(
            "the footer's glyphs cover their whole bounding box; nothing is left "
            "to contrast with"
        )
    mean = ImageStat.Stat(rgb.crop(box), mask=ground).mean
    lighter, darker = sorted(
        (_luminance(_rgb(style["color"])), _luminance(tuple(mean))), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


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
    stamped.paste(_rgb(style["color"]), mask=footer_mask(stamped.size, text, style))
    return stamped


def footer_mask(
    size: tuple[int, int], text: str, style: Mapping[str, Any]
) -> Image.Image:
    """The footer's glyph pixels on a frame of ``size``: 255 inked, 0 untouched."""
    _require_style(style)
    return _glyph_mask(size, text, style)


def verify_footer(
    image: Image.Image, text: str, style: Mapping[str, Any]
) -> tuple[bool, float]:
    """Whether ``image`` carries this footer, visibly, and the matching share.

    Every glyph pixel must be exactly the footer colour, and the colour must
    reach `MIN_CONTRAST_RATIO` against the ground around the glyphs.
    """
    rgb = image.convert("RGB")
    inked = footer_mask(rgb.size, text, style)
    red, green, blue = ImageChops.difference(
        rgb, Image.new("RGB", rgb.size, _rgb(style["color"]))
    ).split()
    worst = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    exact = worst.point(_EXACT)
    inked_count = inked.histogram()[255]
    if inked_count == 0:
        return False, 0.0
    matched = ImageChops.multiply(exact, inked).histogram()[255]
    share = matched / inked_count
    if matched != inked_count:
        return False, share
    return footer_contrast(rgb, text, style) >= MIN_CONTRAST_RATIO, share


def stamp_footer_file(
    source: Path, directory: Path, text: str, style: Mapping[str, Any]
) -> Path:
    """Stamp ``source`` into ``directory/<stem>.png`` and verify the written file."""
    destination = directory / f"{source.stem}{STAMPED_SUFFIX}"
    with Image.open(source) as image:
        contrast = footer_contrast(image, text, style)
        if contrast < MIN_CONTRAST_RATIO:
            raise FooterStampError(
                f"the footer colour {style['color']} reaches only {contrast:.1f}:1 "
                f"against {source.name}'s footer strip (minimum "
                f"{MIN_CONTRAST_RATIO:.0f}:1), so the stamp would be invisible; "
                "pick a contrasting footer_style.color or regenerate the slide "
                "with a quieter strip"
            )
        stamped = stamp_footer(image, text, style)
    directory.mkdir(parents=True, exist_ok=True)
    stamped.save(destination, format="PNG")
    with Image.open(destination) as written:
        ok, share = verify_footer(written, text, style)
    if not ok:
        raise FooterStampError(
            f"stamped footer on {destination.name} matched only {share:.0%} of "
            "its glyph pixels after writing; re-run apply, and check the disk "
            "if it recurs"
        )
    return destination

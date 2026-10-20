#!/usr/bin/env python3
"""Apply generated illustrations to a deck.

Reads outline.yaml (the single source of truth — schema + loader in
skills/presentation-creator/scripts/outline_schema.py). Two slide formats are
supported, distinguished by the per-slide fields:

FULL — slide has a `safe_zone:` field (zone of upper_third / middle_third /
  lower_third / left_half / right_half):
  1. Record the slide + illustration in the backgrounds manifest (--backgrounds-out).
     The illustration becomes the slide BACKGROUND FILL via a later ApplyBackgrounds
     VBA pass (apply-backgrounds.sh) — NOT a python-pptx picture shape, which would
     sit above the layout's halftone-dot overlay and which a python-pptx round-trip
     would drop. See rules/deck-editing-rules.md.
  2. Add a zone-sized semi-transparent scrim above the (later) background and below
     the text (if not already present).
  3. Reposition title text boxes into the designed safe zone:
     upper_third/middle_third/lower_third -> full-width band at the matching Y;
     left_half/right_half -> narrower column on that side.

IMG+TXT — slide has `format: IMG+TXT` and no `safe_zone`:
  1. Replace the background picture with the matching illustration.
  2. Resize and position the picture as a left-column image (~60% of slide).
  3. Reposition title and body placeholders into the right column.

FULL-POSTER — style_anchor sets `composition: poster-theatrical`; every FULL
  slide is background-only. The title is baked into the image by
  `generate-illustrations.py`, so there is no scrim and no overlaid title — just
  the background manifest entry. QR (inserted later) is the only added shape.
  With `style_anchor.footer_style` set, the footer is stamped here instead of
  rendered by the model: each slide image is stamped by `footer_stamp.py` into
  a PNG under `ILLUSTRATIONS_DIR/footer-stamped/`, and that copy becomes the
  background, so the generated image stays footer-free for edits and builds.
  `build-expansion-manifest.py` stamps the same slides' build frames.

The outline is the single source of truth for slide format and zone
assignments — the same fields that `generate-illustrations.py` reads.
See `rules/title-overlay-rules.md` for the title-overlay policy and
`skills/illustrations/references/generation.md` for the format vocabulary.

Usage:
    apply-illustrations-to-deck.py DECK ILLUSTRATIONS_DIR OUTLINE_YAML \\
        [--out OUT_DECK] [--image-ext jpg|jpeg|png] \\
        [--scrim-color RRGGBB] [--scrim-alpha 0-100000]

Stdout is one JSON object: ``ok``, the written ``deck`` (null when the outline
has nothing to apply), ``updated`` and ``eligible`` slide counts, the per-slide
``results``, and the ``backgrounds_manifest`` path (null when no FULL slide
needs a background). Progress lines go to stderr. A refusal exits non-zero
with its message on stderr and names the fix: an eligible slide whose image is
missing or that lies past the deck's end (nothing is written), an unreadable
source deck, an unwritable output deck or backgrounds manifest, or a slide image
that cannot be read or stamped.
"""

import argparse
import json
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.exc import PackageNotFoundError
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.oxml.ns import qn
from pptx.util import Inches

# outline.yaml is the single source of truth; its schema + loader live with the
# presentation-creator scripts.
sys.path.insert(
    0,
    str(
        (
            Path(__file__).resolve().parent.parent.parent
            / "presentation-creator"
            / "scripts"
        )
    ),
)
import outline_schema  # noqa: E402  (path appended above)
from footer_stamp import (  # noqa: E402  (sibling module)
    FooterStampError,
    require_one_geometry,
    stamp_footer_file,
    stamp_spec,
    stamped_slide,
)

# 16:9 slide geometry (inches)
SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5

# Layout per zone: top/left of the title column, and column width.
# Horizontal bands use the full content width centered horizontally.
# Half-frame zones use a narrower column on the chosen side, with the
# title vertically centered.
TEXT_W_FULL_IN = 10.0
TEXT_W_HALF_IN = 5.5
HALF_MARGIN_IN = 0.4
_BAND_H_IN = 1.9  # horizontal-band title height (title + subtitle)
_HALF_H_IN = 4.5  # half-frame title column height
_HALF_TOP_IN = (SLIDE_H_IN - _HALF_H_IN) / 2

ZONE_LAYOUT = {
    "upper_third": {
        "top_in": 0.4,
        "left_in": (SLIDE_W_IN - TEXT_W_FULL_IN) / 2,
        "width_in": TEXT_W_FULL_IN,
        "height_in": _BAND_H_IN,
    },
    "middle_third": {
        "top_in": (SLIDE_H_IN - _BAND_H_IN) / 2,
        "left_in": (SLIDE_W_IN - TEXT_W_FULL_IN) / 2,
        "width_in": TEXT_W_FULL_IN,
        "height_in": _BAND_H_IN,
    },
    "lower_third": {
        "top_in": SLIDE_H_IN - _BAND_H_IN - 0.4,
        "left_in": (SLIDE_W_IN - TEXT_W_FULL_IN) / 2,
        "width_in": TEXT_W_FULL_IN,
        "height_in": _BAND_H_IN,
    },
    "left_half": {
        "top_in": _HALF_TOP_IN,
        "left_in": HALF_MARGIN_IN,
        "width_in": TEXT_W_HALF_IN,
        "height_in": _HALF_H_IN,
    },
    "right_half": {
        "top_in": _HALF_TOP_IN,
        "left_in": SLIDE_W_IN - HALF_MARGIN_IN - TEXT_W_HALF_IN,
        "width_in": TEXT_W_HALF_IN,
        "height_in": _HALF_H_IN,
    },
}

SUBTITLE_OFFSET_IN = 1.2

# IMG+TXT layout — image ~60% of slide on the left, text column on the right.
# Numbers chosen to leave a 0.3" outer margin, 0.2" gutter, and 0.6" footer band.
IMGTXT_IMG_LEFT_IN = 0.3
IMGTXT_IMG_TOP_IN = 0.8
IMGTXT_IMG_WIDTH_IN = 8.0  # ~60% of 13.333" slide width
IMGTXT_IMG_HEIGHT_IN = 5.9  # leaves a 0.8" footer band below
IMGTXT_TEXT_LEFT_IN = IMGTXT_IMG_LEFT_IN + IMGTXT_IMG_WIDTH_IN + 0.2  # 8.5
IMGTXT_TEXT_WIDTH_IN = SLIDE_W_IN - IMGTXT_TEXT_LEFT_IN - 0.3  # 4.533
IMGTXT_TITLE_TOP_IN = IMGTXT_IMG_TOP_IN
IMGTXT_TITLE_HEIGHT_IN = 1.9
IMGTXT_BODY_TOP_IN = IMGTXT_TITLE_TOP_IN + IMGTXT_TITLE_HEIGHT_IN + 0.1  # 2.8
IMGTXT_BODY_HEIGHT_IN = (
    IMGTXT_IMG_TOP_IN + IMGTXT_IMG_HEIGHT_IN - IMGTXT_BODY_TOP_IN
)  # aligns body bottom with image bottom — 3.9

# Default scrim: 45% black. Decks with a strong tonal style (warm sepia,
# cool night, etc.) should pass a sampled color via --scrim-color.
# See suggest-scrim-color.py (same directory) and rules/title-overlay-rules.md §5.
DEFAULT_SCRIM_HEX = "000000"
DEFAULT_SCRIM_ALPHA = 45000

SCRIM_SHAPE_NAME = "_title_scrim"


# Poster-theatrical composition (rules/title-overlay-rules.md): title + footer
# are baked into the image, so FULL slides get a background only — no scrim, no
# overlaid title. QR is the only thing inserted afterward.
POSTER_COMPOSITION = "poster-theatrical"


def parse_composition(outline_path: Path) -> str | None:
    """Deck-level composition from style_anchor; None means standard overlay."""
    anchor = outline_schema.load_outline_partial(outline_path).style_anchor
    if anchor and anchor.composition is not None:
        return anchor.composition.value
    return None


def _progress(message: str) -> None:
    """Human progress goes to stderr; stdout carries only the JSON summary."""
    print(message, file=sys.stderr)


def parse_footer_stamp(outline_path: Path) -> tuple[str, dict] | None:
    """The footer text and style to stamp, or None when the model renders it."""
    return stamp_spec(outline_schema.load_outline_partial(outline_path).style_anchor)


def parse_zones(outline_path: Path) -> dict:
    """Read `safe_zone` from the outline.

    Returns {slide_num: zone_name} where zone_name is a key of ZONE_LAYOUT.
    Slides without a safe_zone are absent from the dict.
    """
    return {
        s.n: s.safe_zone.zone.value
        for s in outline_schema.load_outline_partial(outline_path).slides
        if s.safe_zone
    }


def parse_img_txt_slides(outline_path: Path) -> set:
    """Slide numbers whose format is IMG+TXT and which have no safe_zone.

    Safe zone takes precedence (it implies FULL), so a slide carrying both is
    handled by the zones path instead.
    """
    return {
        s.n
        for s in outline_schema.load_outline_partial(outline_path).slides
        if s.format.value == "IMG+TXT" and not s.safe_zone
    }


def parse_full_slides(outline_path: Path) -> set:
    """Slide numbers whose format is FULL with no safe_zone.

    In poster-theatrical mode these are full-bleed backgrounds with the title +
    footer baked into the image — no scrim, no overlaid title. Safe-zone FULL
    slides are handled by the zones path instead (safe zone takes precedence).
    """
    return {
        s.n
        for s in outline_schema.load_outline_partial(outline_path).slides
        if stamped_slide(s)
    }


def replace_picture_blob(picture_shape, new_image_path: Path) -> None:
    """Swap the picture's embedded image to the one at new_image_path.

    Uses rel re-pointing rather than mutating ``image_part._blob`` in
    place. A template may seed every slide's picture from a single
    placeholder file; python-pptx dedupes identical source paths into
    one image part shared across slides. Mutating that shared blob
    would clobber every other slide referencing it — last swap wins
    and every slide ends up with the same final image.
    """
    slide_part = picture_shape.part
    _, new_rId = slide_part.get_or_add_image_part(str(new_image_path))
    picture_shape._element.blipFill.blip.set(qn("r:embed"), new_rId)


def swap_or_insert_picture(slide, illust_path: Path):
    """Return the slide's largest picture shape, swapping its image to illust_path.

    If the slide has no picture shape (presentation-creator's slide walk leaves
    illustrated slides without an image — the illustrations skill applies them
    post-walk), insert a full-bleed picture and return it. The caller may then
    reposition/resize as needed for the format.
    """
    pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    if pictures:
        bg = max(pictures, key=lambda s: (s.width or 0) * (s.height or 0))
        replace_picture_blob(bg, illust_path)
        return bg
    return slide.shapes.add_picture(
        str(illust_path),
        left=Inches(0),
        top=Inches(0),
        width=Inches(SLIDE_W_IN),
        height=Inches(SLIDE_H_IN),
    )


def ensure_scrim(slide, zone: str, scrim_hex: str, scrim_alpha: int) -> int:
    """Add a zone-sized semi-transparent rectangle between picture and text.

    Zone-scoped (not full-slide) — a full-slide scrim flattens the whole
    illustration; scoping to the title box keeps the rest at full brightness.
    OOXML spPr child order must be xfrm -> prstGeom -> solidFill -> ln.
    """
    # Skip if a scrim was already added (identified by name)
    if any(s.name == SCRIM_SHAPE_NAME for s in slide.shapes):
        return 0
    layout = ZONE_LAYOUT[zone]
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        left=Inches(layout["left_in"]),
        top=Inches(layout["top_in"]),
        width=Inches(layout["width_in"]),
        height=Inches(layout["height_in"]),
    )
    shape.name = SCRIM_SHAPE_NAME
    sp = shape._element
    style = sp.find(qn("p:style"))
    if style is not None:
        sp.remove(style)

    spPr = sp.find(qn("p:spPr"))
    keep = {qn("a:xfrm"), qn("a:prstGeom"), qn("a:custGeom")}
    for child in list(spPr):
        if child.tag not in keep:
            spPr.remove(child)
    solid = etree.SubElement(spPr, qn("a:solidFill"))
    clr = etree.SubElement(solid, qn("a:srgbClr"))
    clr.set("val", scrim_hex.upper())
    alpha = etree.SubElement(clr, qn("a:alpha"))
    alpha.set("val", str(scrim_alpha))
    ln = etree.SubElement(spPr, qn("a:ln"))
    etree.SubElement(ln, qn("a:noFill"))

    # Insert scrim just before the first shape with a text frame
    spTree = slide.shapes._spTree
    spTree.remove(sp)
    first_text_idx = None
    last_pic_idx = None
    for i, child in enumerate(spTree):
        # Track last picture for fallback insertion point
        if child.tag == qn("p:pic"):
            last_pic_idx = i
        # Detect any shape with text: textboxes (txBox="1") and placeholders with txBody
        nvSpPr = child.find(qn("p:nvSpPr"))
        if nvSpPr is not None:
            cNvSpPr = nvSpPr.find(qn("p:cNvSpPr"))
            has_txbox = cNvSpPr is not None and cNvSpPr.get("txBox") == "1"
            has_placeholder = (
                nvSpPr.find(qn("p:nvPr")) is not None
                and nvSpPr.find(qn("p:nvPr")).find(qn("p:ph")) is not None
            )
            has_txbody = child.find(qn("p:txBody")) is not None
            if has_txbox or (has_placeholder and has_txbody):
                first_text_idx = i
                break
    if first_text_idx is not None:
        spTree.insert(first_text_idx, sp)
    elif last_pic_idx is not None:
        spTree.insert(last_pic_idx + 1, sp)
    else:
        spTree.append(sp)
    return 1


def reposition_title(slide, zone: str) -> int:
    """Reposition title and subtitle shapes into the designed zone.

    Only moves title/subtitle placeholders and text boxes — leaves body
    text, callouts, and other content shapes in their original positions.
    """
    # Prefer the slide's explicit title/subtitle placeholders
    title_shapes = []
    if slide.shapes.title is not None:
        title_shapes.append(slide.shapes.title)
    for s in slide.placeholders:
        if s.placeholder_format.idx == 1 and s not in title_shapes:  # subtitle
            title_shapes.append(s)
    # Fall back to text boxes if no placeholders found
    if not title_shapes:
        title_shapes = [
            s
            for s in slide.shapes
            if s.has_text_frame
            and s.name != SCRIM_SHAPE_NAME
            and s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX
        ]
    title_shapes.sort(key=lambda s: s.top)
    if not title_shapes:
        return 0

    layout = ZONE_LAYOUT[zone]
    title_top = Inches(layout["top_in"])
    text_left = Inches(layout["left_in"])
    text_width = Inches(layout["width_in"])

    for j, shape in enumerate(title_shapes):
        shape.left = int(text_left)
        shape.width = int(text_width)
        shape.top = int(title_top + Inches(SUBTITLE_OFFSET_IN * j))
    return len(title_shapes)


def apply_img_txt_layout(slide) -> tuple[int, int]:
    """Position picture, title, and body for an IMG+TXT slide.

    Image goes in the left column (~60% of slide); title and body placeholders
    move to the right column. Returns (picture_repositioned, text_repositioned).
    """
    pic_moved = 0
    pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    if pictures:
        bg = max(pictures, key=lambda s: (s.width or 0) * (s.height or 0))
        bg.left = Inches(IMGTXT_IMG_LEFT_IN)
        bg.top = Inches(IMGTXT_IMG_TOP_IN)
        bg.width = Inches(IMGTXT_IMG_WIDTH_IN)
        bg.height = Inches(IMGTXT_IMG_HEIGHT_IN)
        pic_moved = 1

    text_moved = 0
    title = slide.shapes.title
    if title is not None:
        title.left = Inches(IMGTXT_TEXT_LEFT_IN)
        title.top = Inches(IMGTXT_TITLE_TOP_IN)
        title.width = Inches(IMGTXT_TEXT_WIDTH_IN)
        title.height = Inches(IMGTXT_TITLE_HEIGHT_IN)
        text_moved += 1

    # Reposition any non-title placeholder (body/content) into the right column.
    # Subtitle (idx 1) shares the body's column-and-stack treatment.
    body_shapes = [
        s
        for s in slide.placeholders
        if s.has_text_frame
        and s is not title
        and s.placeholder_format.idx != 0  # idx 0 is the title; already handled
    ]
    body_shapes.sort(key=lambda s: s.top or 0)
    for j, shape in enumerate(body_shapes):
        shape.left = Inches(IMGTXT_TEXT_LEFT_IN)
        shape.top = Inches(IMGTXT_BODY_TOP_IN + j * 0.1)  # tiny stagger if multiple
        shape.width = Inches(IMGTXT_TEXT_WIDTH_IN)
        # Single body fills the column; multiple bodies share the height.
        per_shape_height = IMGTXT_BODY_HEIGHT_IN / max(len(body_shapes), 1)
        shape.height = Inches(per_shape_height)
        text_moved += 1

    return pic_moved, text_moved


class ApplyError(RuntimeError):
    """A refusal whose message names the operation that failed and its fix."""


def _why(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {getattr(exc, 'strerror', None) or exc}"


def _unapplied(
    illust_dir: Path, ext: str, slides: set[int], slide_count: int
) -> list[str]:
    """Each eligible slide that cannot be applied, and why."""
    problems = []
    for n in sorted(slides):
        illust = illust_dir / f"slide-{n:02d}.{ext}"
        if n > slide_count:
            problems.append(f"slide {n} is past the deck's {slide_count} slides")
        elif not illust.exists():
            problems.append(f"slide {n} has no {illust.name}")
    return problems


def apply(
    deck: Path,
    illust_dir: Path,
    zones: dict,
    img_txt_slides: set,
    out_deck: Path,
    ext: str,
    scrim_hex: str,
    scrim_alpha: int,
    poster_full_slides: set | None = None,
    footer_stamp: tuple[str, dict] | None = None,
) -> tuple[list[dict], dict]:
    """Apply scrim + title for FULL slides and the IMG+TXT layout.

    FULL-slide illustrations are NOT inserted as picture shapes here; they are
    recorded in the returned ``backgrounds`` map ({slide_num: abs_image_path})
    for the ApplyBackgrounds VBA pass, which sets them as slide background fills
    as the final write. Returns ``(results, backgrounds)``.
    """
    poster_full_slides = poster_full_slides or set()
    try:
        prs = Presentation(str(deck))
    except (OSError, PackageNotFoundError) as exc:
        raise ApplyError(
            f"cannot read the source deck {deck} ({_why(exc)}); pass an existing "
            ".pptx, then re-run"
        ) from exc
    # Every eligible slide, or nothing: a partial deck would ship with the
    # skipped slides unillustrated.
    problems = _unapplied(
        illust_dir,
        ext,
        set(zones) | set(img_txt_slides) | poster_full_slides,
        len(prs.slides),
    )
    if problems:
        raise ApplyError(
            "not every eligible slide can be applied, so no deck was written: "
            f"{'; '.join(problems)} — generate the missing slide images, or fix "
            "the outline's slide numbers against the deck, then re-run"
        )
    results = []
    backgrounds: dict[int, str] = {}

    # FULL slides with Safe zone — scrim + title here; background via VBA pass
    for n, zone in sorted(zones.items()):
        illust = illust_dir / f"slide-{n:02d}.{ext}"

        slide = prs.slides[n - 1]
        backgrounds[n] = str(illust.resolve())

        scrim_added = ensure_scrim(slide, zone, scrim_hex, scrim_alpha)
        moved = reposition_title(slide, zone)
        _progress(
            f"  [{n:02d}] zone={zone}  moved={moved} text  scrim+{scrim_added}  bg->VBA"
        )
        results.append(
            {
                "slide": n,
                "format": "FULL",
                "zone": zone,
                "text_moved": moved,
                "scrim_added": scrim_added,
            }
        )

    # IMG+TXT slides — image-left + text-right layout
    for n in sorted(img_txt_slides):
        illust = illust_dir / f"slide-{n:02d}.{ext}"

        slide = prs.slides[n - 1]
        try:
            swap_or_insert_picture(slide, illust)
        except OSError as exc:
            raise ApplyError(
                f"cannot read the slide image {illust} ({_why(exc)}); regenerate "
                "or replace it, then re-run"
            ) from exc

        pic_moved, text_moved = apply_img_txt_layout(slide)
        _progress(f"  [{n:02d}] format=IMG+TXT  pic+{pic_moved}  text+{text_moved}")
        results.append(
            {
                "slide": n,
                "format": "IMG+TXT",
                "picture_repositioned": pic_moved,
                "text_moved": text_moved,
            }
        )

    # Poster-theatrical FULL slides — background only. Title + footer are baked
    # into the image, so no scrim and no overlaid title; QR (added later) is the
    # only inserted shape.
    if footer_stamp is not None:
        # Refuse a mixed set before stamping any of it.
        require_one_geometry(
            illust_dir / f"slide-{n:02d}.{ext}" for n in sorted(poster_full_slides)
        )
    for n in sorted(poster_full_slides):
        illust = illust_dir / f"slide-{n:02d}.{ext}"
        if footer_stamp is None:
            backgrounds[n] = str(illust.resolve())
            _progress(
                f"  [{n:02d}] poster FULL  bg->VBA  (title+footer baked into image)"
            )
        else:
            text, style = footer_stamp
            stamped_dir = illust_dir / "footer-stamped"
            try:
                stamped = stamp_footer_file(illust, stamped_dir, text, style)
            except OSError as exc:
                raise ApplyError(
                    f"cannot stamp {illust.name} into {stamped_dir} ({_why(exc)}); "
                    "regenerate or replace the image if it is unreadable, or make "
                    "the directory writable, then re-run"
                ) from exc
            backgrounds[n] = str(stamped.resolve())
            _progress(
                f"  [{n:02d}] poster FULL  bg->VBA  (title baked, footer stamped)"
            )
        results.append(
            {
                "slide": n,
                "format": "FULL-POSTER",
                "zone": None,
                "footer_stamped": footer_stamp is not None,
            }
        )

    try:
        prs.save(str(out_deck))
    except OSError as exc:
        raise ApplyError(
            f"cannot write the output deck {out_deck} ({_why(exc)}); make its "
            "directory writable or pass --out elsewhere, then re-run"
        ) from exc
    return results, backgrounds


def _summary(
    deck: Path | None,
    results: list[dict],
    eligible: int,
    backgrounds_manifest: Path | None,
) -> dict:
    """The one JSON object main prints on stdout."""
    return {
        "ok": True,
        "deck": str(deck) if deck is not None else None,
        "updated": len(results),
        "eligible": eligible,
        "results": results,
        "backgrounds_manifest": (
            str(backgrounds_manifest) if backgrounds_manifest is not None else None
        ),
    }


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("deck", type=Path, help="Path to source .pptx")
    ap.add_argument(
        "illustrations", type=Path, help="Directory with slide-NN.<ext> files"
    )
    ap.add_argument(
        "outline", type=Path, help="Path to outline.yaml (the single source of truth)"
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output deck (default: <stem>-with-titles.pptx)",
    )
    ap.add_argument("--image-ext", default="jpg", choices=["jpg", "jpeg", "png"])
    ap.add_argument(
        "--scrim-color",
        default=DEFAULT_SCRIM_HEX,
        help="Scrim color as 6-digit hex (default: %(default)s). "
        "Run suggest-scrim-color.py to sample one from the deck's illustrations.",
    )
    ap.add_argument(
        "--scrim-alpha",
        type=int,
        default=DEFAULT_SCRIM_ALPHA,
        help="Scrim opacity in OOXML thousandths (0-100000, default: %(default)s = 45%%).",
    )
    ap.add_argument(
        "--backgrounds-out",
        type=Path,
        default=None,
        help="Where to write the FULL-slide backgrounds manifest JSON "
        "(default: <out_stem>.backgrounds.json). Feed it to "
        "apply-backgrounds.sh to set the backgrounds via PowerPoint.",
    )
    args = ap.parse_args()

    out_deck = args.out or args.deck.with_name(args.deck.stem + "-with-titles.pptx")
    backgrounds_out = args.backgrounds_out or out_deck.with_name(
        out_deck.stem + ".backgrounds.json"
    )
    poster = parse_composition(args.outline) == POSTER_COMPOSITION
    zones = parse_zones(args.outline)
    img_txt_slides = parse_img_txt_slides(args.outline)
    # Poster-theatrical decks are all background-only FULL slides — no Safe zones,
    # no IMG+TXT. Fail fast on a mix rather than apply contradictory layouts.
    if poster and (zones or img_txt_slides):
        offenders = sorted(set(zones) | img_txt_slides)
        raise SystemExit(
            "poster-theatrical composition does not allow `safe_zone` or "
            f"`format: IMG+TXT` slides. Offending slide(s): "
            f"{', '.join(map(str, offenders))}. Fix the outline or drop "
            "`composition: poster-theatrical` from style_anchor."
        )
    # In poster-theatrical mode, FULL slides get a background only (text baked in).
    poster_full_slides = parse_full_slides(args.outline) if poster else set()
    total_slides = len(zones) + len(img_txt_slides) + len(poster_full_slides)
    if total_slides == 0:
        _progress(
            f"No `safe_zone`, `format: IMG+TXT`, or poster-theatrical FULL "
            f"slides found in {args.outline.name}. Nothing to do."
        )
        print(json.dumps(_summary(None, [], 0, None)))
        return

    scrim_hex = args.scrim_color.lstrip("#").upper()
    if len(scrim_hex) != 6 or any(c not in "0123456789ABCDEF" for c in scrim_hex):
        raise SystemExit(
            f"--scrim-color must be a 6-digit hex, got {args.scrim_color!r}"
        )
    if not (0 <= args.scrim_alpha <= 100000):
        raise SystemExit(f"--scrim-alpha must be 0..100000, got {args.scrim_alpha}")

    try:
        results, backgrounds = apply(
            args.deck,
            args.illustrations,
            zones,
            img_txt_slides,
            out_deck,
            args.image_ext,
            scrim_hex,
            args.scrim_alpha,
            poster_full_slides,
            parse_footer_stamp(args.outline) if poster else None,
        )
    except (ApplyError, FooterStampError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    _progress(f"\nSaved {out_deck}")
    _progress(f"Updated {len(results)}/{total_slides} slides")

    if backgrounds:
        manifest = {
            "backgrounds": {str(n): path for n, path in sorted(backgrounds.items())}
        }
        try:
            backgrounds_out.write_text(json.dumps(manifest, indent=2) + "\n")
        except OSError as exc:
            raise SystemExit(
                f"ERROR: wrote {out_deck.name} but cannot write the backgrounds "
                f"manifest {backgrounds_out} ({type(exc).__name__}: "
                f"{exc.strerror or exc}); make its directory writable or pass "
                "--backgrounds-out elsewhere, then re-run"
            ) from exc
        _progress(
            f"Wrote {len(backgrounds)} FULL-slide background(s) -> {backgrounds_out}"
        )
        _progress(
            f"Apply them via: apply-backgrounds.sh <uniquely-named copy of {out_deck.name}> "
            f"<final.pptx> {backgrounds_out.name}"
        )
    else:
        _progress(
            "No FULL background slides (Safe zone or poster) — no background manifest written."
        )
    print(
        json.dumps(
            _summary(
                out_deck,
                results,
                total_slides,
                backgrounds_out if backgrounds else None,
            )
        )
    )


if __name__ == "__main__":
    main()

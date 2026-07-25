#!/usr/bin/env python3
"""Extract visual design data from .pptx files using python-pptx.

Produces per-slide visual data and global design statistics as JSON.
Skips static exports, conflict copies, and template files.

On slides where a picture is large enough to hide baked-in text (see
text_extraction_confidence), picture blobs are OCR'd so the analysis has a
word inventory — not just "unreadable by shapes." Design judgment (density,
two-layer legibility) still needs rendered pages; OCR is inventory only.

Usage:
    pptx-extraction.py <path> [--skip template] [--no-ocr]

    <path>       Path to a single .pptx file or a directory to scan recursively
    --skip       Additional skip patterns (case-insensitive substring match on filename)
    --no-ocr     Skip OCR even on low-confidence slides (shape walk only)

Examples:
    pptx-extraction.py /path/to/talk.pptx
    pptx-extraction.py /path/to/Presentations --skip template --skip draft
"""

import argparse
import glob
import io
import json
import os
import re
import sys
from collections import Counter

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Emu, Inches, Pt

# A picture covering at least this fraction of the slide is large enough to be
# carrying rendered text — AI-generated illustration decks bake titles, callout
# labels, and annotations into the image, where python-pptx cannot see them.
# Below this, a picture reads as decorative and the extractable text is the
# whole story. Tuned to catch full-bleed and near-full-bleed layouts; a slide
# at or above it gets text_extraction_confidence "low" whether or not text
# frames are also present, since a text overlay does not prove the picture
# underneath is wordless.
_TEXT_BEARING_IMAGE_AREA_RATIO = 0.5

# Cap so one dense manual page cannot blow out the JSON. Inventory is for
# cites and transcript cross-checks, not a full document dump.
_OCR_TEXT_MAX_CHARS = 8000

# One stderr warning per process when the OCR engine is missing — not once
# per slide on a 100-slide deck.
_ocr_unavailable_warned = False

# Cached tesseract availability for this process: None = not checked yet.
_tesseract_available = None


class OcrUnavailableError(Exception):
    """Tesseract (or its Python binding) is not available on this machine."""


def picture_area_ratio(shape, prs):
    """Return a picture shape's area as a fraction of the slide (0.0–1.0).

    Missing geometry (any of width/height/slide dimensions absent or zero)
    returns 0.0 — unknown size is not evidence of a large picture.
    """
    slide_area = (prs.slide_width or 0) * (prs.slide_height or 0)
    if not slide_area:
        return 0.0
    if not shape.width or not shape.height:
        return 0.0
    return min((shape.width * shape.height) / slide_area, 1.0)


def normalize_ocr_text(text):
    """Collapse whitespace and strip; empty input stays empty."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _require_tesseract():
    """Ensure tesseract + bindings are available; cache the result per process.

    Raises OcrUnavailableError when missing. Subsequent calls in the same
    process do not re-spawn the version check.
    """
    global _tesseract_available
    if _tesseract_available is True:
        return
    if _tesseract_available is False:
        raise OcrUnavailableError(
            "tesseract binary not found; install tesseract-ocr (apt) or "
            "tesseract (brew)"
        )

    try:
        import pytesseract
    except ImportError as e:
        _tesseract_available = False
        raise OcrUnavailableError(
            "OCR requires Pillow and pytesseract; install project dependencies"
        ) from e

    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError as e:
        _tesseract_available = False
        raise OcrUnavailableError(
            "tesseract binary not found; install tesseract-ocr (apt) or "
            "tesseract (brew)"
        ) from e

    _tesseract_available = True


def ocr_image_bytes(blob):
    """OCR a single image blob. Returns normalized text (maybe empty).

    Raises OcrUnavailableError when the engine or its binding is missing.
    Unreadable blobs and per-image OCR failures return "" so one bad picture
    does not abort the deck.
    """
    global _tesseract_available
    _require_tesseract()

    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise OcrUnavailableError(
            "OCR requires Pillow and pytesseract; install project dependencies"
        ) from e

    try:
        img = Image.open(io.BytesIO(blob))
    except OSError as e:
        sys.stderr.write(f"WARN: OCR skipped unreadable image blob: {e}\n")
        return ""

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    try:
        raw = pytesseract.image_to_string(img)
    except pytesseract.TesseractNotFoundError as e:
        _tesseract_available = False
        raise OcrUnavailableError(
            "tesseract binary not found; install tesseract-ocr (apt) or "
            "tesseract (brew)"
        ) from e
    except pytesseract.TesseractError as e:
        sys.stderr.write(f"WARN: OCR failed on image blob: {e}\n")
        return ""

    return normalize_ocr_text(raw)


def ocr_picture_blobs(blobs):
    """OCR picture blobs; join non-empty results with ' | '.

    Raises OcrUnavailableError if the engine is missing. Returns "" when every
    blob is empty or unreadable. Caller is responsible for sort order.
    """
    parts = []
    for blob in blobs:
        text = ocr_image_bytes(blob)
        if text:
            parts.append(text)
    joined = " | ".join(parts)
    if len(joined) > _OCR_TEXT_MAX_CHARS:
        return joined[:_OCR_TEXT_MAX_CHARS]
    return joined


def apply_ocr_to_slide(slide_data, picture_blobs, *, ocr=True, ocr_fn=None):
    """Fill ocr_text + text_extraction_method on a per-slide dict.

    OCR runs only when confidence is low and at least one picture blob is
    available. Image-background slides with no PICTURE shapes have no blob to
    OCR here (rendering the page is out of this script's scope).

    ocr_fn is injectable for tests (signature: list[bytes] -> str). Default
    is ocr_picture_blobs.
    """
    slide_data["ocr_text"] = ""
    slide_data["text_extraction_method"] = "shapes"

    if slide_data.get("text_extraction_confidence") != "low":
        return slide_data
    if not ocr:
        return slide_data
    if not picture_blobs:
        # Low confidence without a picture blob (image background only) —
        # nothing this path can inventory.
        return slide_data

    run_ocr = ocr_fn if ocr_fn is not None else ocr_picture_blobs
    global _ocr_unavailable_warned
    try:
        slide_data["ocr_text"] = run_ocr(picture_blobs)
        slide_data["text_extraction_method"] = "shapes+ocr"
    except OcrUnavailableError as e:
        slide_data["text_extraction_method"] = "shapes+ocr_unavailable"
        if not _ocr_unavailable_warned:
            sys.stderr.write(
                f"WARN: OCR unavailable ({e}); low-confidence slides will "
                f"have empty ocr_text. Install tesseract to enable.\n"
            )
            _ocr_unavailable_warned = True
    return slide_data


def rgb_to_hex(rgb):
    """Convert RGBColor to hex string."""
    if rgb is None:
        return None
    return f"#{rgb.red:02X}{rgb.green:02X}{rgb.blue:02X}"


def get_background_color(slide):
    """Extract background color from a slide."""
    bg = slide.background
    fill = bg.fill
    try:
        if fill.type is not None:
            if fill.type == 1:  # solid
                return rgb_to_hex(fill.fore_color.rgb), "solid"
            elif fill.type == 2:  # pattern
                return rgb_to_hex(fill.fore_color.rgb), "pattern"
            elif fill.type == 3:  # gradient
                return None, "gradient"
            elif fill.type == 6:  # background (image)
                return None, "image"
    except Exception:
        pass
    # Fall back to slide layout background
    try:
        layout_bg = slide.slide_layout.background.fill
        if layout_bg.type is not None and layout_bg.type == 1:
            return rgb_to_hex(layout_bg.fore_color.rgb), "solid_from_layout"
    except Exception:
        pass
    return None, "unknown"


def extract_shape_info(shape):
    """Extract visual properties from a shape."""
    info = {
        "name": shape.name,
        "shape_type": str(shape.shape_type),
        "left": round(shape.left / 914400, 2) if shape.left else None,
        "top": round(shape.top / 914400, 2) if shape.top else None,
        "width": round(shape.width / 914400, 2) if shape.width else None,
        "height": round(shape.height / 914400, 2) if shape.height else None,
    }

    # Text properties
    if shape.has_text_frame:
        tf = shape.text_frame
        info["text_preview"] = tf.text[:100] if tf.text else ""
        for para in tf.paragraphs:
            for run in para.runs:
                if run.font:
                    info["font_name"] = run.font.name
                    info["font_size"] = run.font.size.pt if run.font.size else None
                    try:
                        info["font_color"] = rgb_to_hex(run.font.color.rgb) if run.font.color else None
                    except AttributeError:
                        info["font_color"] = None
                    info["bold"] = run.font.bold
                    info["italic"] = run.font.italic
                    break
            if "font_name" in info:
                break

    # Fill properties
    if hasattr(shape, "fill"):
        try:
            fill = shape.fill
            if fill.type == 1:  # solid
                info["fill_color"] = rgb_to_hex(fill.fore_color.rgb)
        except Exception:
            pass

    # Line/outline properties
    if hasattr(shape, "line"):
        try:
            line = shape.line
            if line.fill.type == 1:
                info["line_color"] = rgb_to_hex(line.color.rgb)
                info["line_width"] = line.width.pt if line.width else None
        except Exception:
            pass

    # Auto-shape type (for speech bubbles, starbursts, etc.)
    if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
        try:
            info["auto_shape_type"] = str(shape.auto_shape_type)
        except Exception:
            pass

    return info


def extract_template_layouts(prs):
    """Enumerate slide layouts defined by the presentation's masters.

    Returns a list of {index, master_index, name, placeholders: [{idx, type}]}
    entries. `master_index` distinguishes layouts that share a name across
    different slide masters (PowerPoint allows reuse of layout names like
    "Title and Content" across masters) — the vault-profile aggregator keys
    on the (master_index, name) pair when preserving curated `use_for`
    values across regenerations.

    The `use_for` field documented in the speaker-profile schema is
    intentionally curated by the speaker and is not emitted here.
    """
    layouts = []
    index = 0
    for master_index, master in enumerate(prs.slide_masters):
        for layout in master.slide_layouts:
            placeholders = []
            for ph in layout.placeholders:
                try:
                    pf = ph.placeholder_format
                    pt = pf.type
                    type_name = getattr(pt, "name", None) or str(pt).split(" ", 1)[0]
                    placeholders.append({
                        "idx": pf.idx,
                        "type": type_name,
                    })
                except AttributeError as e:
                    # Malformed placeholder — record skip with context, continue.
                    sys.stderr.write(
                        f"WARN: skipping placeholder in layout "
                        f"master={master_index} '{layout.name}': {e}\n"
                    )
            layouts.append({
                "index": index,
                "master_index": master_index,
                "name": layout.name,
                "placeholders": placeholders,
            })
            index += 1
    return layouts


def extract_pptx(pptx_path, *, ocr=True, ocr_fn=None):
    """Main extraction function.

    ocr: when True (default), low-confidence slides with PICTURE shapes get
         an OCR inventory in ocr_text.
    ocr_fn: optional callable(list[bytes]) -> str for tests; default uses
            tesseract via ocr_picture_blobs.
    """
    prs = Presentation(pptx_path)
    result = {
        "pptx_path": pptx_path,
        "slide_count": len(prs.slides),
        "slide_width_inches": round(prs.slide_width / 914400, 2),
        "slide_height_inches": round(prs.slide_height / 914400, 2),
        "template_layouts": extract_template_layouts(prs),
        "per_slide_visual": [],
        "global_design": {
            "fonts_used": Counter(),
            "background_colors": Counter(),
            "shape_types_used": Counter(),
            "color_sequence": [],
        }
    }

    for i, slide in enumerate(prs.slides):
        bg_hex, bg_type = get_background_color(slide)

        slide_data = {
            "slide_number": i + 1,
            "background_color_hex": bg_hex,
            "background_type": bg_type,
            "layout_name": slide.slide_layout.name if slide.slide_layout else None,
            "shape_count": len(slide.shapes),
            # True when at least one shape carries a text frame. Names what it
            # measures — shapes the extractor can read text out of. It is NOT
            # a claim about whether the slide shows text; text rendered inside
            # a picture is invisible here (see text_extraction_confidence).
            "has_text_frame_shapes": False,
            "has_image": False,
            # Largest picture's area as a fraction of the slide (0.0–1.0).
            "image_area_ratio": 0.0,
            # "high" — no picture is large enough to be carrying rendered text,
            #          so extractable text is the whole story for this slide.
            # "low"  — a picture covers enough of the slide to carry text the
            #          shape-level extractor cannot see. Absence of shape text
            #          proves nothing; read ocr_text for inventory and still
            #          judge design dimensions from the rendered image.
            "text_extraction_confidence": "high",
            "has_speaker_notes": bool(
                slide.has_notes_slide and
                slide.notes_slide.notes_text_frame.text.strip()
            ),
            # Shape-frame text only. Baked-in picture text lands in ocr_text.
            "text_content_preview": "",
            # OCR inventory when confidence is low and picture blobs exist.
            "ocr_text": "",
            # shapes | shapes+ocr | shapes+ocr_unavailable
            "text_extraction_method": "shapes",
            "footer_text": "",
            "shapes_summary": []
        }

        text_parts = []
        # Unrounded — the threshold compares against true geometry; the
        # reported value is rounded only for readability.
        max_image_ratio = 0.0
        # (ratio, blob) pairs — sorted largest-first before OCR so the primary
        # full-bleed image is inventoried first.
        picture_entries = []
        for shape in slide.shapes:
            shape_info = extract_shape_info(shape)
            slide_data["shapes_summary"].append(shape_info)

            # Track fonts
            if "font_name" in shape_info and shape_info["font_name"]:
                result["global_design"]["fonts_used"][shape_info["font_name"]] += 1

            # Track shape types
            if "auto_shape_type" in shape_info:
                result["global_design"]["shape_types_used"][shape_info["auto_shape_type"]] += 1

            # Check for images
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                slide_data["has_image"] = True
                ratio = picture_area_ratio(shape, prs)
                if ratio > max_image_ratio:
                    max_image_ratio = ratio
                try:
                    picture_entries.append((ratio, shape.image.blob))
                except ValueError as e:
                    # python-pptx raises ValueError when the picture has no
                    # embedded image (missing blip rId) — skip that shape.
                    sys.stderr.write(
                        f"WARN: could not read picture blob on slide "
                        f"{i + 1}: {e}\n"
                    )

            # Check for text-frame shapes
            if shape.has_text_frame:
                slide_data["has_text_frame_shapes"] = True
                text_parts.append(shape.text_frame.text)

                # Detect footer by position (bottom 15% of slide) and small font
                if shape.top and shape.top > prs.slide_height * 0.85:
                    slide_data["footer_text"] = shape.text_frame.text

        slide_data["text_content_preview"] = " | ".join(
            t[:50] for t in text_parts if t.strip()
        )[:200]

        slide_data["image_area_ratio"] = round(max_image_ratio, 3)

        # A picture large enough to carry text, or an image *background* (which
        # covers the whole slide by definition), can both be hiding rendered
        # text the shape walk never sees.
        if (
            max_image_ratio >= _TEXT_BEARING_IMAGE_AREA_RATIO
            or bg_type == "image"
        ):
            slide_data["text_extraction_confidence"] = "low"

        picture_entries.sort(key=lambda item: item[0], reverse=True)
        picture_blobs = [blob for _, blob in picture_entries]
        apply_ocr_to_slide(
            slide_data, picture_blobs, ocr=ocr, ocr_fn=ocr_fn,
        )

        # Track background colors
        if bg_hex:
            result["global_design"]["background_colors"][bg_hex] += 1
        result["global_design"]["color_sequence"].append(bg_hex or "unknown")

        result["per_slide_visual"].append(slide_data)

    # Convert Counters to dicts for JSON serialization
    result["global_design"]["fonts_used"] = dict(result["global_design"]["fonts_used"])
    result["global_design"]["background_colors"] = dict(result["global_design"]["background_colors"])
    result["global_design"]["shape_types_used"] = dict(result["global_design"]["shape_types_used"])

    return result


def should_skip(basename, skip_patterns):
    """Check if a .pptx file should be skipped."""
    lower = basename.lower()
    # Skip static exports
    if "static" in lower:
        return True, "static export"
    # Skip Google Drive conflict copies: (N).pptx
    if re.search(r'\(\d+\)\.pptx$', basename):
        return True, "conflict copy"
    # Skip files matching user-provided skip patterns (case-insensitive)
    for pat in skip_patterns:
        if pat.lower() in lower:
            return True, f"matches skip pattern '{pat}'"
    return False, None


def batch_extract(directory, skip_patterns, *, ocr=True):
    """Extract from all .pptx files in a directory, skipping unwanted files."""
    results = []
    skipped = []

    for pptx_path in sorted(glob.glob(f"{directory}/**/*.pptx", recursive=True)):
        basename = os.path.basename(pptx_path)
        skip, reason = should_skip(basename, skip_patterns)
        if skip:
            skipped.append({"path": pptx_path, "reason": reason})
            print(f"SKIP: {pptx_path} ({reason})", file=sys.stderr)
            continue

        try:
            data = extract_pptx(pptx_path, ocr=ocr)
            results.append(data)
            print(f"OK:   {pptx_path} ({data['slide_count']} slides)", file=sys.stderr)
        except Exception as e:
            skipped.append({"path": pptx_path, "reason": f"error: {e}"})
            print(f"FAIL: {pptx_path}: {e}", file=sys.stderr)

    return results, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Extract visual design data from .pptx files."
    )
    parser.add_argument("path", help="Single .pptx file or directory to scan recursively")
    parser.add_argument("--skip", action="append", default=["template"],
                        help="Skip patterns (case-insensitive, default: template)")
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Skip OCR on low-confidence slides (shape walk only)",
    )
    args = parser.parse_args()
    ocr = not args.no_ocr

    if os.path.isfile(args.path):
        result = extract_pptx(args.path, ocr=ocr)
        print(json.dumps(result, indent=2))
    elif os.path.isdir(args.path):
        results, skipped = batch_extract(args.path, args.skip, ocr=ocr)
        output = {"results": results, "skipped": skipped}
        print(json.dumps(output, indent=2))
    else:
        print(f"Error: {args.path} is not a file or directory", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

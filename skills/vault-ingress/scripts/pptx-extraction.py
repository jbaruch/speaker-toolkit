#!/usr/bin/env python3
"""Extract visual design data from .pptx files using python-pptx.

Produces per-slide visual data and global design statistics as JSON.
Skips static exports, conflict copies, and template files.

Text is collected recursively from shape frames and native table cells, with
source/confidence recorded per channel. Low-confidence picture and background
blobs are OCR'd for a word inventory; groups, tables, SmartArt, charts, and
other unsupported containers explicitly require a rendered pass. OCR remains
inventory only, not a substitute for visual design judgment.

Native slide XML is also inventoried for timing containers, exact animation
behavior elements, visibility set actions, transitions, and audio/video timing.
Those are raw package counts with explicit non-playback provenance, not claims
about observed motion, concurrency, or delivered behavior.

Usage:
    pptx-extraction.py <path> [--skip template] [--no-ocr]
    pptx-extraction.py --version

    <path>       Path to a single .pptx file or a directory to scan recursively
    --skip       Additional skip patterns (case-insensitive substring match on filename)
    --no-ocr     Skip OCR even on low-confidence slides (shape walk only)

Examples:
    pptx-extraction.py /path/to/talk.pptx
    pptx-extraction.py /path/to/Presentations --skip template --skip draft
"""

import argparse
import base64
import glob
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter
from math import gcd
from pathlib import Path
from zlib import error as ZlibError

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

# Field-shape and behavior versions are deliberately separate. A missing
# schema_version/pipeline_version identifies the legacy extractor output.
# v2 adds the fixed-shape native_timing record on every slide plus stable deck
# totals. The additive shape does not change v1 fields, but a v1 record cannot
# answer timing questions and must not turn missing metadata into a zero count.
SCHEMA_VERSION = 2
PIPELINE_VERSION = "1.1.0"

# PresentationML timing elements are counted by exact qualified name and kept
# in separate semantic lanes. In particular, a <p:timing> container or a media
# node is not a generic animation/motion observation.
_ANIMATION_BEHAVIOR_ELEMENTS = {
    "general": "p:anim",
    "color": "p:animClr",
    "effect": "p:animEffect",
    "motion": "p:animMotion",
    "rotation": "p:animRot",
    "scale": "p:animScale",
}
_MEDIA_TIMING_ELEMENTS = {
    "audio": "p:audio",
    "video": "p:video",
}
_TIMING_PROVENANCE = {
    "source": "pptx_package_xml",
    "measurement": "raw_ooxml_element_counts",
    "observed_playback": False,
}

# DrawingML graphic-frame URIs. python-pptx exposes chart/table helpers, but
# returns shape_type=None for SmartArt and other graphic frames, so the URI is
# the only reliable discriminator for those objects.
_GRAPHIC_DATA_URI_TABLE = (
    "http://schemas.openxmlformats.org/drawingml/2006/table"
)
_GRAPHIC_DATA_URI_CHART = (
    "http://schemas.openxmlformats.org/drawingml/2006/chart"
)
_GRAPHIC_DATA_URI_OLE = (
    "http://schemas.openxmlformats.org/presentationml/2006/ole"
)

# A valid, transparent one-pixel PNG. When a ZIP member under ppt/media has a
# bad CRC, the extractor substitutes this blob in an in-memory copy of the
# package. That preserves every healthy slide/shape while making the lost asset
# explicit in corrupt_assets; the source file is never rewritten.
_RECOVERY_IMAGE_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

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


def _count_in_timing(timing_elements, qualified_name):
    """Count exact descendants across presentation timing containers."""
    tag = qn(qualified_name)
    return sum(
        1
        for timing in timing_elements
        for _element in timing.iter(tag)
    )


def _is_visibility_set_action(set_element):
    """Return whether a <p:set> explicitly targets a visibility attribute."""
    for attribute_name in set_element.iter(qn("p:attrName")):
        value = (attribute_name.text or "").strip().lower()
        if value == "visibility" or value.endswith(".visibility"):
            return True
    return False


def extract_native_timing(slide):
    """Inventory raw timing/transition XML without claiming observed motion.

    Counts are structural package evidence only. Markup-compatibility Choice and
    Fallback branches are both retained and therefore both counted; resolving
    which branch a particular presenter executes requires a playback engine.
    """
    root = slide.element
    timing_elements = list(root.iter(qn("p:timing")))
    set_actions = [
        element
        for timing in timing_elements
        for element in timing.iter(qn("p:set"))
    ]
    animation_counts = {
        name: _count_in_timing(timing_elements, qualified_name)
        for name, qualified_name in _ANIMATION_BEHAVIOR_ELEMENTS.items()
    }
    animation_counts["total"] = sum(animation_counts.values())
    media_counts = {
        name: _count_in_timing(timing_elements, qualified_name)
        for name, qualified_name in _MEDIA_TIMING_ELEMENTS.items()
    }
    media_counts["total"] = sum(media_counts.values())
    part_name = str(slide.part.partname).lstrip("/")
    return {
        "timing_element_present": bool(timing_elements),
        "timing_element_count": len(timing_elements),
        "transition_count": sum(1 for _ in root.iter(qn("p:transition"))),
        "set_action_count": len(set_actions),
        "visibility_set_action_count": sum(
            1 for element in set_actions if _is_visibility_set_action(element)
        ),
        "animation_behavior_counts": animation_counts,
        "media_timing_counts": media_counts,
        "has_animation_behaviors": animation_counts["total"] > 0,
        "has_media_timing": media_counts["total"] > 0,
        "provenance": {
            **_TIMING_PROVENANCE,
            "part_name": part_name,
        },
    }


def summarize_native_timing(per_slide_visual):
    """Aggregate fixed-key deck totals from per-slide structural metadata."""
    animation_counts = {
        name: 0 for name in _ANIMATION_BEHAVIOR_ELEMENTS
    }
    media_counts = {name: 0 for name in _MEDIA_TIMING_ELEMENTS}
    summary = {
        "slides_with_timing_elements": 0,
        "slides_with_transitions": 0,
        "slides_with_animation_behaviors": 0,
        "slides_with_media_timing": 0,
        "timing_element_count": 0,
        "transition_count": 0,
        "set_action_count": 0,
        "visibility_set_action_count": 0,
    }
    for slide_data in per_slide_visual:
        timing = slide_data["native_timing"]
        summary["slides_with_timing_elements"] += int(
            timing["timing_element_present"])
        summary["slides_with_transitions"] += int(
            timing["transition_count"] > 0)
        summary["slides_with_animation_behaviors"] += int(
            timing["has_animation_behaviors"])
        summary["slides_with_media_timing"] += int(
            timing["has_media_timing"])
        for field in (
            "timing_element_count",
            "transition_count",
            "set_action_count",
            "visibility_set_action_count",
        ):
            summary[field] += timing[field]
        for name in animation_counts:
            animation_counts[name] += timing["animation_behavior_counts"][name]
        for name in media_counts:
            media_counts[name] += timing["media_timing_counts"][name]
    animation_counts["total"] = sum(animation_counts.values())
    media_counts["total"] = sum(media_counts.values())
    return {
        **summary,
        "animation_behavior_counts": animation_counts,
        "media_timing_counts": media_counts,
        "provenance": dict(_TIMING_PROVENANCE),
    }


def _input_fingerprint(blob):
    """Return a deterministic fingerprint for the exact source bytes."""
    return {
        "algorithm": "sha256",
        "digest": hashlib.sha256(blob).hexdigest(),
        "size_bytes": len(blob),
    }


def _is_embedded_media_member(member_name):
    """Return whether a ZIP member is an independently recoverable asset."""
    normalized = member_name.replace("\\", "/").lstrip("/")
    return normalized.startswith("ppt/media/") and not normalized.endswith("/")


def _validate_zip_members(package_blob):
    """Return corrupt ZIP member names, validating every member's CRC."""
    corrupt = []
    try:
        with zipfile.ZipFile(io.BytesIO(package_blob)) as archive:
            for member in archive.infolist():
                try:
                    with archive.open(member) as stream:
                        while stream.read(1024 * 1024):
                            pass
                except (zipfile.BadZipFile, ZlibError):
                    corrupt.append(member.filename)
    except zipfile.BadZipFile as e:
        raise ValueError("invalid PPTX ZIP container") from e
    return corrupt


def _presentation_with_media_recovery(package_blob):
    """Load a presentation, substituting only corrupt embedded media.

    XML, relationships, and other structural package parts are not safe to
    discard. A corrupt non-media member therefore remains a hard error, while
    corrupt assets under ppt/media are replaced in an in-memory copy so the
    rest of the deck can still be cataloged.
    """
    corrupt_names = _validate_zip_members(package_blob)
    if not corrupt_names:
        return Presentation(io.BytesIO(package_blob)), []

    unsafe = [name for name in corrupt_names if not _is_embedded_media_member(name)]
    if unsafe:
        joined = ", ".join(sorted(unsafe))
        raise ValueError(f"corrupt structural PPTX member(s): {joined}")

    recovered_package = io.BytesIO()
    corrupt_set = set(corrupt_names)
    try:
        with (
            zipfile.ZipFile(io.BytesIO(package_blob)) as source,
            zipfile.ZipFile(recovered_package, "w") as destination,
        ):
            for member in source.infolist():
                if member.filename in corrupt_set:
                    payload = _RECOVERY_IMAGE_BYTES
                else:
                    payload = source.read(member)
                destination.writestr(member, payload)
    except (zipfile.BadZipFile, ZlibError) as e:
        raise ValueError("could not recover corrupt PPTX media") from e

    recovered_package.seek(0)
    assets = [
        {
            "part_name": name,
            "error_type": "crc_mismatch",
            "status": "recovered_with_placeholder",
        }
        for name in sorted(corrupt_names)
    ]
    return Presentation(recovered_package), assets


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


def _append_ocr_text(slide_data, text):
    """Append one OCR channel's text to the backward-compatible aggregate."""
    if not text:
        return
    current = slide_data.get("ocr_text", "")
    combined = f"{current} | {text}" if current else text
    slide_data["ocr_text"] = combined[:_OCR_TEXT_MAX_CHARS]


def _run_ocr_channel(
    slide_data, blobs, *, channel, provenance, ocr=True, ocr_fn=None,
):
    """OCR one image source and emit channel-level provenance/confidence."""
    record = {
        "channel": channel,
        "text": "",
        "confidence": "low",
        "status": "unavailable" if not blobs else "pending",
        "provenance": provenance,
    }
    slide_data["text_channels"].append(record)

    if not blobs:
        return
    if not ocr:
        record["status"] = "skipped"
        return

    run_ocr = ocr_fn if ocr_fn is not None else ocr_picture_blobs
    global _ocr_unavailable_warned
    try:
        text = normalize_ocr_text(run_ocr(blobs))
        record["text"] = text
        record["status"] = "extracted" if text else "empty"
        _append_ocr_text(slide_data, text)
        slide_data["text_extraction_method"] = "shapes+ocr"
    except OcrUnavailableError as e:
        record["status"] = "unavailable"
        slide_data["text_extraction_method"] = "shapes+ocr_unavailable"
        if not _ocr_unavailable_warned:
            sys.stderr.write(
                f"WARN: OCR unavailable ({e}); low-confidence slides will "
                f"have empty OCR channels. Install tesseract to enable.\n"
            )
            _ocr_unavailable_warned = True


def apply_ocr_to_slide(
    slide_data, picture_blobs, *, ocr=True, ocr_fn=None, shape_paths=None,
):
    """Fill picture OCR fields on a per-slide dict.

    OCR runs only when confidence is low and at least one picture blob is
    available. Image-background slides with no PICTURE shapes have no blob to
    OCR here (rendering the page is out of this script's scope).

    ocr_fn is injectable for tests (signature: list[bytes] -> str). Default
    is ocr_picture_blobs.
    """
    if slide_data.get("text_extraction_confidence") != "low":
        return slide_data
    if not picture_blobs:
        return slide_data

    _run_ocr_channel(
        slide_data,
        picture_blobs,
        channel="picture_ocr",
        provenance={
            "source": "embedded_picture_blobs",
            "shape_paths": shape_paths or [],
        },
        ocr=ocr,
        ocr_fn=ocr_fn,
    )
    return slide_data


def apply_background_ocr(slide_data, background_image, *, ocr=True, ocr_fn=None):
    """OCR an actual background fill blob, or record why rendering is needed."""
    if background_image is None:
        background_image = {
            "blob": None,
            "status": "unavailable",
            "provenance": {"source": "pptx_background_image"},
        }
    blob = background_image.get("blob")
    _run_ocr_channel(
        slide_data,
        [blob] if blob else [],
        channel="background_image_ocr",
        provenance=background_image["provenance"],
        ocr=ocr,
        ocr_fn=ocr_fn,
    )
    return slide_data


def rgb_to_hex(rgb):
    """Convert RGBColor to hex string."""
    if rgb is None:
        return None
    return f"#{rgb.red:02X}{rgb.green:02X}{rgb.blue:02X}"


def _local_name(element):
    """Return the namespace-free local name for an lxml element."""
    return element.tag.rsplit("}", 1)[-1]


def _background_candidates(slide):
    """Yield slide/layout/master objects in background inheritance order."""
    yield "slide", slide
    layout = slide.slide_layout
    if layout is not None:
        yield "layout", layout
        master = layout.slide_master
        if master is not None:
            yield "master", master


def _effective_background(slide):
    """Return the first explicit background without mutating PPTX XML.

    Accessing ``slide.background.fill`` creates a no-fill background when the
    slide inherits one. Reading the raw cSld tree avoids that destructive
    behavior and lets us retain the relationship owner for image fills.
    """
    for source, owner in _background_candidates(slide):
        bg = owner.element.cSld.bg
        if bg is None:
            continue
        bg_pr = bg.bgPr
        if bg_pr is None:
            # A theme background reference explicitly wins over inheritance,
            # but it does not expose a concrete color/image blob here.
            return {
                "source": source,
                "owner": owner,
                "fill": None,
                "type": "unknown",
                "color": None,
            }

        fill = bg_pr.eg_fillProperties
        if fill is None:
            fill_type = "unknown"
        else:
            fill_type = {
                "solidFill": "solid",
                "pattFill": "pattern",
                "gradFill": "gradient",
                "blipFill": "image",
                "noFill": "unknown",
                "grpFill": "unknown",
            }.get(_local_name(fill), "unknown")

        color = None
        if fill is not None:
            srgb = next(iter(fill.iter(qn("a:srgbClr"))), None)
            if srgb is not None and srgb.get("val"):
                color = f"#{srgb.get('val').upper()}"
            else:
                system = next(iter(fill.iter(qn("a:sysClr"))), None)
                if system is not None and system.get("lastClr"):
                    color = f"#{system.get('lastClr').upper()}"

        reported_type = fill_type
        if fill_type == "solid" and source != "slide":
            reported_type = f"solid_from_{source}"
        return {
            "source": source,
            "owner": owner,
            "fill": fill,
            "type": reported_type,
            "color": color,
        }

    return {
        "source": "none",
        "owner": None,
        "fill": None,
        "type": "unknown",
        "color": None,
    }


def get_background_color(slide):
    """Extract background color/type without altering inherited backgrounds."""
    background = _effective_background(slide)
    return background["color"], background["type"]


def get_background_image(slide):
    """Return an explicit background-image blob and its provenance.

    The result is ``None`` for non-image backgrounds. For an image background
    whose relationship/blob is missing, the returned record has ``blob=None``
    and ``status=unavailable`` so callers can require a rendered-page pass.
    """
    background = _effective_background(slide)
    background_type = background["type"]
    if background_type != "image":
        return None

    fill = background["fill"]
    owner = background["owner"]
    source = background["source"]
    provenance = {
        "source": "pptx_background_image",
        "background_owner": source,
    }
    if fill is None or owner is None:
        return {"blob": None, "status": "unavailable", "provenance": provenance}

    blip = next(iter(fill.iter(qn("a:blip"))), None)
    r_id = blip.get(qn("r:embed")) if blip is not None else None
    if not r_id:
        return {"blob": None, "status": "unavailable", "provenance": provenance}

    provenance["relationship_id"] = r_id
    try:
        image_part = owner.part.related_part(r_id)
        blob = image_part.blob
    except (KeyError, ValueError, AttributeError):
        return {"blob": None, "status": "unavailable", "provenance": provenance}
    provenance["part_name"] = str(image_part.partname).lstrip("/")
    return {"blob": blob, "status": "available", "provenance": provenance}


def _picture_payload(shape):
    """Return a picture blob plus the package part that supplied it."""
    r_id = shape.element.blip_rId
    if not r_id:
        raise ValueError("picture has no embedded image relationship")
    image_part = shape.part.related_part(r_id)
    return image_part.blob, str(image_part.partname).lstrip("/")


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
        except (AttributeError, TypeError, ValueError, NotImplementedError):
            pass

    # Line/outline properties
    if hasattr(shape, "line"):
        try:
            line = shape.line
            if line.fill.type == 1:
                info["line_color"] = rgb_to_hex(line.color.rgb)
                info["line_width"] = line.width.pt if line.width else None
        except (AttributeError, TypeError, ValueError, NotImplementedError):
            pass

    # Auto-shape type (for speech bubbles, starbursts, etc.)
    if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
        try:
            info["auto_shape_type"] = str(shape.auto_shape_type)
        except (AttributeError, ValueError):
            pass

    return info


def walk_shapes(shapes, parent_path=()):
    """Yield every shape recursively with a stable, human-readable path."""
    for index, shape in enumerate(shapes):
        name = shape.name or f"shape_{index + 1}"
        path = parent_path + (name,)
        yield shape, path
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from walk_shapes(shape.shapes, path)


def _graphic_data_uri(shape):
    """Return a graphic-frame URI, including those unknown to python-pptx."""
    element = shape.element
    if _local_name(element) != "graphicFrame":
        return None
    return element.graphicData_uri or None


def _classify_graphic_frame(shape):
    """Classify a DrawingML graphic frame from its URI."""
    uri = _graphic_data_uri(shape)
    if uri is None:
        return None
    if uri == _GRAPHIC_DATA_URI_TABLE:
        return "table"
    if uri == _GRAPHIC_DATA_URI_CHART:
        return "chart"
    if uri == _GRAPHIC_DATA_URI_OLE:
        if shape.shape_type == MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT:
            return "embedded_ole_object"
        return "linked_ole_object"
    if "diagram" in uri.lower():
        return "smartart"
    return "graphic_frame"


def _extract_table_channel(shape, shape_path):
    """Extract visible native table-cell text, skipping merged spill cells."""
    table = shape.table
    cell_text = []
    fonts = Counter()
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row.cells):
            if cell.is_spanned:
                continue
            text = cell.text.strip()
            if text:
                cell_text.append({
                    "cell": f"R{row_index + 1}C{column_index + 1}",
                    "text": text,
                })
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    if run.font.name:
                        fonts[run.font.name] += 1

    combined = " | ".join(item["text"] for item in cell_text)
    channel = {
        "channel": "table_cell_text",
        "text": combined,
        "confidence": "medium",
        "status": "extracted" if combined else "empty",
        "provenance": {
            "source": "pptx_table_cells",
            "shape_path": list(shape_path),
            "cells": [item["cell"] for item in cell_text],
        },
    }
    details = {
        "table_rows": len(table.rows),
        "table_columns": len(table.columns),
        "table_text_preview": combined[:200],
        "table_fonts": dict(fonts),
    }
    return channel, details


def _shape_text_channel(shape, shape_path, *, in_group):
    """Return a provenance-bearing channel for one shape text frame."""
    text = shape.text_frame.text
    return {
        "channel": "shape_text",
        "text": text,
        "confidence": "medium" if in_group else "high",
        "status": "extracted" if text.strip() else "empty",
        "provenance": {
            "source": "pptx_shape_text_frame",
            "shape_path": list(shape_path),
        },
    }


def _mark_render_required(slide_data, reason):
    """Conservatively lower confidence and record a stable render reason."""
    slide_data["text_extraction_confidence"] = "low"
    slide_data["render_required"] = True
    if reason not in slide_data["render_required_reasons"]:
        slide_data["render_required_reasons"].append(reason)


def _record_unsupported(slide_data, kind, shape, shape_path, *, uri=None):
    """Record content that requires rendering or a specialized extractor."""
    provenance = {
        "source": "pptx_unsupported_visual_container",
        "shape_path": list(shape_path),
    }
    if uri:
        provenance["graphic_data_uri"] = uri
    slide_data["text_channels"].append({
        "channel": f"{kind}_text",
        "text": "",
        "confidence": "low",
        "status": "unsupported",
        "provenance": provenance,
    })
    entry = {
        "content_type": kind,
        "shape_name": shape.name,
        "shape_path": list(shape_path),
        "reason": "visible text or labels may not be represented in PPTX text frames",
        "render_required": True,
    }
    if uri:
        entry["graphic_data_uri"] = uri
    slide_data["unsupported_content"].append(entry)
    _mark_render_required(slide_data, kind)


def _has_speaker_notes(slide):
    """Return whether a slide has non-empty speaker notes."""
    if not slide.has_notes_slide:
        return False
    notes_frame = slide.notes_slide.notes_text_frame
    return bool(notes_frame is not None and notes_frame.text.strip())


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

    ocr: when True (default), low-confidence image channels get an OCR
         inventory in ocr_text and text_channels.
    ocr_fn: optional callable(list[bytes]) -> str for tests; default uses
            tesseract via ocr_picture_blobs.
    """
    package_blob = Path(pptx_path).read_bytes()
    prs, corrupt_assets = _presentation_with_media_recovery(package_blob)
    slide_width = prs.slide_width
    slide_height = prs.slide_height
    if slide_width is None or slide_height is None:
        raise ValueError("PPTX presentation has no slide dimensions")
    slide_width_value = int(slide_width)
    slide_height_value = int(slide_height)
    if slide_width_value <= 0 or slide_height_value <= 0:
        raise ValueError("PPTX presentation has invalid slide dimensions")
    ratio_divisor = gcd(slide_width_value, slide_height_value)
    corrupt_part_names = {asset["part_name"] for asset in corrupt_assets}
    result = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "input_fingerprint": _input_fingerprint(package_blob),
        "pptx_path": os.fspath(pptx_path),
        "slide_count": len(prs.slides),
        "slide_width_inches": round(slide_width_value / 914400, 2),
        "slide_height_inches": round(slide_height_value / 914400, 2),
        "aspect_ratio": (
            f"{slide_width_value // ratio_divisor}:"
            f"{slide_height_value // ratio_divisor}"
        ),
        "corrupt_assets": corrupt_assets,
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
            # Low is also used for groups, tables, unsupported graphic frames,
            # and image backgrounds: extracted text in one channel never proves
            # another visual channel is wordless.
            "text_extraction_confidence": "high",
            "text_channels": [],
            "unsupported_content": [],
            "has_unsupported_content": False,
            "render_required": False,
            "render_required_reasons": [],
            "has_speaker_notes": _has_speaker_notes(slide),
            # Raw package structure only: separate behavior/media/transition
            # lanes deliberately make no claim about playback or delivery.
            "native_timing": extract_native_timing(slide),
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
        # (ratio, blob, path, package-part) entries — sorted largest-first
        # before OCR so the primary full-bleed image is inventoried first.
        picture_entries = []
        recursive_shape_count = 0
        for shape, shape_path in walk_shapes(slide.shapes):
            recursive_shape_count += 1
            shape_info = extract_shape_info(shape)
            shape_info["shape_path"] = list(shape_path)
            shape_info["group_depth"] = len(shape_path) - 1
            slide_data["shapes_summary"].append(shape_info)

            # Track fonts
            if "font_name" in shape_info and shape_info["font_name"]:
                result["global_design"]["fonts_used"][shape_info["font_name"]] += 1

            # Track shape types
            if "auto_shape_type" in shape_info:
                result["global_design"]["shape_types_used"][shape_info["auto_shape_type"]] += 1

            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                _mark_render_required(slide_data, "grouped_shapes")
                slide_data["text_channels"].append({
                    "channel": "group_container_text",
                    "text": "",
                    "confidence": "low",
                    "status": "requires_render",
                    "provenance": {
                        "source": "pptx_group_container",
                        "shape_path": list(shape_path),
                    },
                })

            # Check for images
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                slide_data["has_image"] = True
                ratio = picture_area_ratio(shape, prs)
                if ratio > max_image_ratio:
                    max_image_ratio = ratio
                try:
                    blob, part_name = _picture_payload(shape)
                    if part_name in corrupt_part_names:
                        _record_unsupported(
                            slide_data,
                            "corrupt_embedded_asset",
                            shape,
                            shape_path,
                        )
                    else:
                        picture_entries.append(
                            (ratio, blob, list(shape_path), part_name)
                        )
                except (KeyError, ValueError, AttributeError) as e:
                    _record_unsupported(
                        slide_data, "unreadable_picture", shape, shape_path,
                    )
                    sys.stderr.write(
                        f"WARN: could not read picture blob on slide "
                        f"{i + 1}: {e}\n"
                    )

            # Check for text-frame shapes
            if shape.has_text_frame:
                slide_data["has_text_frame_shapes"] = True
                channel = _shape_text_channel(
                    shape, shape_path, in_group=len(shape_path) > 1,
                )
                slide_data["text_channels"].append(channel)
                text_parts.append(channel["text"])

                # Detect footer by position (bottom 15% of slide) and small font
                if (
                    len(shape_path) == 1
                    and shape.top
                    and shape.top > slide_height_value * 0.85
                ):
                    slide_data["footer_text"] = channel["text"]

            graphic_kind = _classify_graphic_frame(shape)
            if graphic_kind is not None:
                uri = _graphic_data_uri(shape)
                shape_info["graphic_frame_type"] = graphic_kind
                shape_info["graphic_data_uri"] = uri
                if graphic_kind == "table":
                    table_channel, table_details = _extract_table_channel(
                        shape, shape_path,
                    )
                    shape_info.update(table_details)
                    slide_data["text_channels"].append(table_channel)
                    text_parts.append(table_channel["text"])
                    for font_name, count in table_details["table_fonts"].items():
                        result["global_design"]["fonts_used"][font_name] += count
                    _mark_render_required(slide_data, "table")
                else:
                    _record_unsupported(
                        slide_data,
                        graphic_kind,
                        shape,
                        shape_path,
                        uri=uri,
                    )
            elif shape.shape_type in {
                MSO_SHAPE_TYPE.DIAGRAM,
                MSO_SHAPE_TYPE.IGX_GRAPHIC,
                MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT,
                MSO_SHAPE_TYPE.LINKED_OLE_OBJECT,
                MSO_SHAPE_TYPE.MEDIA,
                MSO_SHAPE_TYPE.WEB_VIDEO,
            }:
                _record_unsupported(
                    slide_data,
                    str(shape.shape_type).split(" ", 1)[0].lower(),
                    shape,
                    shape_path,
                )

        slide_data["shape_count_recursive"] = recursive_shape_count

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
            reason = "background_image" if bg_type == "image" else "large_picture"
            _mark_render_required(slide_data, reason)

        picture_entries.sort(key=lambda item: item[0], reverse=True)
        picture_blobs = [entry[1] for entry in picture_entries]
        picture_paths = [entry[2] for entry in picture_entries]
        apply_ocr_to_slide(
            slide_data,
            picture_blobs,
            ocr=ocr,
            ocr_fn=ocr_fn,
            shape_paths=picture_paths,
        )

        if bg_type == "image":
            background_image = get_background_image(slide)
            if (
                background_image is not None
                and background_image["provenance"].get("part_name")
                in corrupt_part_names
            ):
                _mark_render_required(slide_data, "corrupt_embedded_asset")
                background_image["blob"] = None
                background_image["status"] = "recovered_with_placeholder"
                background_image["provenance"]["asset_status"] = (
                    "recovered_with_placeholder"
                )
                slide_data["unsupported_content"].append({
                    "content_type": "corrupt_embedded_asset",
                    "shape_name": None,
                    "shape_path": [],
                    "reason": "background image bytes failed package CRC validation",
                    "render_required": True,
                })
            apply_background_ocr(
                slide_data,
                background_image,
                ocr=ocr,
                ocr_fn=ocr_fn,
            )

        slide_data["has_extracted_text"] = any(
            channel["text"].strip()
            for channel in slide_data["text_channels"]
        )
        slide_data["has_unsupported_content"] = bool(
            slide_data["unsupported_content"]
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
    result["native_timing_summary"] = summarize_native_timing(
        result["per_slide_visual"])

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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Extract visual design data from .pptx files."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Single .pptx file or directory to scan recursively",
    )
    parser.add_argument("--skip", action="append", default=["template"],
                        help="Skip patterns (case-insensitive, default: template)")
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Skip OCR on low-confidence slides (shape walk only)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print extractor schema and pipeline versions as JSON",
    )
    args = parser.parse_args(argv)
    if args.version:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "pipeline_version": PIPELINE_VERSION,
        }))
        return
    if args.path is None:
        parser.error("path is required unless --version is used")
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

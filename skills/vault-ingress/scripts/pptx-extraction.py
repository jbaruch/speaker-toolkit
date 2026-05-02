#!/usr/bin/env python3
"""Extract visual design data from .pptx files using python-pptx.

Produces per-slide visual data and global design statistics as JSON.
Skips static exports, conflict copies, and template files.

Usage:
    pptx-extraction.py <path> [--skip template]

    <path>       Path to a single .pptx file or a directory to scan recursively
    --skip       Additional skip patterns (case-insensitive substring match on filename)

Examples:
    pptx-extraction.py /path/to/talk.pptx
    pptx-extraction.py /path/to/Presentations --skip template --skip draft
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Emu, Inches, Pt


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

    Returns a list of {index, name, placeholders: [{idx, type}]} entries.
    The `use_for` field documented in the speaker-profile schema is
    intentionally curated by the speaker and is not emitted here — the
    vault-profile aggregator preserves any prior `use_for` values across
    regenerations rather than overwriting them with empty strings.
    """
    layouts = []
    index = 0
    for master in prs.slide_masters:
        for layout in master.slide_layouts:
            placeholders = []
            for ph in layout.placeholders:
                try:
                    pt = ph.placeholder_format.type
                    type_name = getattr(pt, "name", None) or str(pt).split(" ", 1)[0]
                    placeholders.append({
                        "idx": ph.placeholder_format.idx,
                        "type": type_name,
                    })
                except Exception:
                    pass
            layouts.append({
                "index": index,
                "name": layout.name,
                "placeholders": placeholders,
            })
            index += 1
    return layouts


def extract_pptx(pptx_path):
    """Main extraction function."""
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
            "has_text_placeholder": False,
            "has_image": False,
            "has_speaker_notes": bool(
                slide.has_notes_slide and
                slide.notes_slide.notes_text_frame.text.strip()
            ),
            "text_content_preview": "",
            "footer_text": "",
            "shapes_summary": []
        }

        text_parts = []
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

            # Check for text placeholders
            if shape.has_text_frame:
                slide_data["has_text_placeholder"] = True
                text_parts.append(shape.text_frame.text)

                # Detect footer by position (bottom 15% of slide) and small font
                if shape.top and shape.top > prs.slide_height * 0.85:
                    slide_data["footer_text"] = shape.text_frame.text

        slide_data["text_content_preview"] = " | ".join(
            t[:50] for t in text_parts if t.strip()
        )[:200]

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


def batch_extract(directory, skip_patterns):
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
            data = extract_pptx(pptx_path)
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
    args = parser.parse_args()

    if os.path.isfile(args.path):
        result = extract_pptx(args.path)
        print(json.dumps(result, indent=2))
    elif os.path.isdir(args.path):
        results, skipped = batch_extract(args.path, args.skip)
        output = {"results": results, "skipped": skipped}
        print(json.dumps(output, indent=2))
    else:
        print(f"Error: {args.path} is not a file or directory", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

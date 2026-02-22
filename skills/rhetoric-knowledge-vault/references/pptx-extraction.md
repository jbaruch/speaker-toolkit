# PPTX Visual Extraction — Technical Reference

Extract exact visual design data from .pptx files using python-pptx.
This produces the data that PDF visual inspection cannot: hex colors, font names,
shape types, exact positions, and formatting specs.

## Prerequisites

python-pptx must be installed in the Python environment at `config.python_path`:
`{python_path} -m pip install python-pptx`

## Extraction Script

Run this for each .pptx file. It returns a JSON structure with per-slide visual data
and global design statistics.

```python
import json
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from collections import Counter

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
                    info["font_color"] = rgb_to_hex(run.font.color.rgb) if run.font.color and run.font.color.rgb else None
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

def extract_pptx(pptx_path):
    """Main extraction function."""
    prs = Presentation(pptx_path)
    result = {
        "pptx_path": pptx_path,
        "slide_count": len(prs.slides),
        "slide_width_inches": round(prs.slide_width / 914400, 2),
        "slide_height_inches": round(prs.slide_height / 914400, 2),
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

# Usage:
# data = extract_pptx("/path/to/talk.pptx")
# print(json.dumps(data, indent=2))
```

## What This Extracts (mapped to slide-design-spec.md sections)

| Spec Section | Extraction Coverage | Field |
|---|---|---|
| 2. Background Colors | Exact hex values + fill type | `background_color_hex`, `background_type` |
| 3. Typography | Font names, sizes, colors, bold/italic | `shapes_summary[].font_*` |
| 4. Footer | Position, font, color, separator | `footer_text`, footer shape properties |
| 5. Image Placement | Whether image is present (composition type needs PDF visual classification) | `has_image` |
| 6. Bubbles/Starbursts | Auto-shape type enum, fill/line colors | `auto_shape_type`, `fill_color`, `line_color` |
| 7. Layout Taxonomy | PowerPoint layout name per slide | `layout_name` |
| 10. Color Sequencing | Full sequence of hex values | `color_sequence` |

## What This Does NOT Extract (still needs PDF visual analysis)

- **Image composition type** (full-bleed vs side-by-side vs inset) — python-pptx can
  tell you an image exists and its position/size, but classifying the COMPOSITION
  PATTERN requires visual judgment
- **Content type** (meme vs data chart vs quote) — requires understanding the content,
  not just the shapes
- **Section divider identification** — requires understanding the rhetorical function
- **Background color NAME** (the semantic register label like "purple_halftone") —
  python-pptx gives hex values; mapping hex to register names requires building the
  lookup table from the first few extractions

## Matching PPTX to Shownotes Talks

The .pptx files are in `Conference/Year/TalkName.pptx` and shownotes entries have
`conference` and `title` fields. Fuzzy matching rules:

1. Normalize conference names (strip year, "Days", "Conference", etc.)
2. Match by date proximity (same year, preferably same month)
3. Match by title substring (e.g., "DevOps Reframed" matches "devops-reframed" in slug)
4. Flag ambiguous matches for user confirmation
5. Some talks have multiple .pptx files (one per delivery) — match to the CLOSEST date

Common patterns in .pptx filenames:
- `DevOps Reframed.pptx` — main deck
- `DevOps Reframed static.pptx` — static export (SKIP)
- `DevOps Reframed (1).pptx` — Google Drive conflict copy (SKIP)
- `Presentation Template DOTCs 2023.pptx` — conference template (SKIP)

## Batch Extraction

To extract from all matched .pptx files:

```python
import glob, json

pptx_dir = "/path/to/Presentations"  # config.pptx_source_dir
template_skip_patterns = ["template"]  # config.template_skip_patterns
results = []

for pptx_path in glob.glob(f"{pptx_dir}/**/*.pptx", recursive=True):
    # Skip static exports, conflict copies, templates
    basename = os.path.basename(pptx_path)
    if "static" in basename.lower():
        continue
    if re.search(r'\(\d+\)\.pptx$', basename):
        continue
    # Skip files matching config.template_skip_patterns (case-insensitive)
    if any(t in basename.lower() for t in template_skip_patterns):
        continue

    try:
        data = extract_pptx(pptx_path)
        results.append(data)
    except Exception as e:
        print(f"FAILED: {pptx_path}: {e}")

# Save all results
with open("{vault_root}/pptx-extraction-results.json", "w") as f:
    json.dump(results, f, indent=2)
```

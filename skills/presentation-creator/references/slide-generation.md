# Slide Generation — Technical Reference

Detailed instructions for Phase 5: turning a finalized outline into a .pptx deck
using the MCP PPT server and the speaker's template.

---

## Template Layout Map

Read the template path from `speaker-profile.json → infrastructure.template_pptx_path`.
Read the layout map from `speaker-profile.json → infrastructure.template_layouts[]`.

Each layout entry has: `index`, `name`, `placeholders[]`, and `use_for`.

### Layout Selection Logic (generic mapping)

| Outline slide type | Layout to use | Notes |
|-------------------|--------------|-------|
| Title slide | Layout with CENTER_TITLE only | Opening, section dividers |
| Title + subtitle | Layout with TITLE + SUBTITLE | Bio, shownotes, section openers |
| Bullet list | Layout with TITLE + BODY | Most content slides |
| Comparison / two lists | Layout with TITLE + 2 BODY columns | Before/after, pros/cons |
| Image/meme with title | Layout with TITLE only (no body) | Title in placeholder, image via `manage_image` |
| Full-bleed image/meme | BLANK layout (no placeholders) | Position everything manually |
| Quote / caption | Caption layout if available | Attributed quotes, epigraphs |

Match these generic types to the speaker's actual layout names/indices from the profile.

Also review the template catalog in `slide-design-spec.md` Section 7 for rich
patterns (SWOT, timelines, funnels, competitor matrices, etc.) that may be available
in the speaker's template.

---

## Creating a Clean Deck from Template

The template may ship with demo slides. Strip them to get a clean deck with layouts
only. Use python-pptx directly:

```python
from pptx import Presentation

# Read template path from speaker profile
tmpl = Presentation('{template_pptx_path}')

# Remove all slides, keep layouts
xml_slides = tmpl.slides._sldIdLst
for sldId in list(xml_slides):
    rId = sldId.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
    tmpl.part.drop_rel(rId)
    xml_slides.remove(sldId)

tmpl.save('{output_path}')
```

Then open the clean deck with the MCP: `open_presentation(file_path=...)`.

---

## Slide Generation Workflow

### For each slide in the outline:

1. **Add slide** with the right layout (index from profile template_layouts):
   ```
   add_slide(layout_index=N, title="Slide Title")
   ```

2. **Populate placeholders** — title first, then body:
   ```
   populate_placeholder(slide_index=N, placeholder_idx=0, text="Title")
   populate_placeholder(slide_index=N, placeholder_idx=1, text="Body text")
   ```

3. **Or use bullet points** for list content:
   ```
   add_bullet_points(slide_index=N, placeholder_idx=1, bullet_points=[...])
   ```

4. **For image/meme slides** — use title-only or blank layout, add image:
   ```
   manage_image(slide_index=N, operation="add", image_source="path/to/image.png",
                left=1, top=1.5, width=8, height=5)
   ```

5. **For non-placeholder text** (captions, annotations):
   ```
   manage_text(slide_index=N, operation="add", text="Caption",
               left=1, top=6, width=8, height=0.5,
               font_size=14, color=[255,255,255])
   ```

6. **For shapes** (dividers, accent boxes):
   ```
   add_shape(slide_index=N, shape_type="RECTANGLE",
             left=0, top=0, width=10, height=0.3,
             fill_color=[0,188,212])
   ```

### Background Colors

Read `design_rules.background_color_strategy` from the speaker profile. Apply the
strategy when adding slides. Common strategies:
- `random_non_repeating` — pick a random saturated color, never repeat on adjacent slides
- `theme_sequence` — follow the template's built-in color rotation

Read `design_rules.white_black_reserved_for` to know when white/black backgrounds
are appropriate (typically full-bleed image/meme slides only).

### Footer

Read `design_rules.footer` from the speaker profile for exact position, font, size,
and color adaptation rules. Add footer to EVERY slide using `manage_text`. The footer
pattern template is in `footer.pattern` — substitute conference-specific values.

### Text Overflow Prevention

Template placeholders have fixed sizes. To avoid overflow:

- **Titles**: Max ~60 characters. If longer, use `manage_text` with `auto_fit=True`.
- **Body bullets**: Max 6-7 items per placeholder. For more, split across two slides.
- **Bullet text**: Keep individual bullets under ~80 characters.
- **Use `optimize_slide_text`** after populating to auto-resize if needed:
  ```
  optimize_slide_text(slide_index=N, min_font_size=12, max_font_size=28)
  ```

---

## Speaker Notes (python-pptx)

The MCP PPT server does not support speaker notes. Use python-pptx directly as a
batch operation after all slides are generated via MCP.

```python
from pptx import Presentation

prs = Presentation('path/to/deck.pptx')

# notes_map: {slide_index: "speaker notes text"}
notes_map = {
    0: "",  # title slide — no notes
    1: "Brief intro — name, role, one sentence.",
    2: "The core argument starts here. Pause after the first bullet.",
    # ... etc
}

for idx, notes_text in notes_map.items():
    if notes_text:
        slide = prs.slides[idx]
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = notes_text

prs.save('path/to/deck.pptx')
```

Run this AFTER MCP slide generation is complete, and BEFORE presenting to the author.

---

## Interactive Iteration Patterns

### Slide-specific changes

Author says: "Slide 12 — make the title shorter"
→ `populate_placeholder(slide_index=11, placeholder_idx=0, text="New shorter title")`

Author says: "Slide 5 — change to two columns"
→ Cannot change layout of existing slide via MCP. Instead:
  1. Note content of slide 5
  2. Generate a replacement slide with the new layout (appended at end)
  3. Use python-pptx to delete the old slide 5 and reorder the new one into position
  4. Re-open the deck with MCP `open_presentation`

### Batch changes

Read `design_rules.slide_numbers` from the speaker profile. If "never", decline
requests to add slide numbers and explain it's a design rule.

### Content delivery

Author provides an image for a placeholder slide:
→ `manage_image(slide_index=N, operation="add", image_source="/path/to/image.png", ...)`

### Structural changes (python-pptx)

The MCP PPT server cannot delete or reorder slides. Use python-pptx:

**Delete slides:**
```python
from pptx import Presentation

prs = Presentation('path/to/deck.pptx')
xml_slides = prs.slides._sldIdLst
slide_to_delete = list(xml_slides)[N]  # 0-based index
rId = slide_to_delete.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
prs.part.drop_rel(rId)
xml_slides.remove(slide_to_delete)
prs.save('path/to/deck.pptx')
```

**Reorder slides:**
```python
from pptx import Presentation

prs = Presentation('path/to/deck.pptx')
xml_slides = prs.slides._sldIdLst
slides_list = list(xml_slides)
slide = slides_list[FROM]
xml_slides.remove(slide)
if TO >= len(list(xml_slides)):
    xml_slides.append(slide)
else:
    xml_slides.insert(TO, slide)
prs.save('path/to/deck.pptx')
```

After any python-pptx structural operation, re-open the deck with MCP
(`open_presentation`) to continue editing.

---

## MCP Tool Quick Reference

| Operation | Tool | Key params |
|-----------|------|-----------|
| Add slide | `add_slide` | layout_index, title, background_colors=[[r,g,b]] |
| Set title/body | `populate_placeholder` | slide_index, placeholder_idx, text |
| Add bullets | `add_bullet_points` | slide_index, placeholder_idx, bullet_points[] |
| Add free text | `manage_text` | slide_index, operation="add", text, position, font |
| Add image | `manage_image` | slide_index, operation="add", image_source, position |
| Add shape | `add_shape` | slide_index, shape_type, position, colors |
| Add table | `add_table` | slide_index, rows, cols, data, position |
| Add chart | `add_chart` | slide_index, chart_type, categories, series |
| Fix text overflow | `optimize_slide_text` | slide_index, min/max_font_size |
| Inspect slide | `get_slide_info` | slide_index |
| Save | `save_presentation` | file_path |

---

## PDF Export (Final Step)

After the author declares done, export the .pptx to PDF using PowerPoint AppleScript:

```python
import subprocess

pptx_path = '/absolute/path/to/deck.pptx'
pdf_path  = '/absolute/path/to/deck.pdf'

script = f'''
tell application "Microsoft PowerPoint"
    open POSIX file "{pptx_path}"
    delay 2
    save active presentation in POSIX file "{pdf_path}" as save as PDF
    close active presentation saving no
end tell
'''
subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=30)
```

Requirements:
- Microsoft PowerPoint must be installed
- Paths must be absolute POSIX paths

---

## File Locations

Read `infrastructure.presentation_file_convention` from the speaker profile for the
directory structure. Typical convention:

```
{presentations-dir}/{conference}/{year}/{talk-slug}/
├── {talk-slug}.pptx              ← the deck (Phase 5 output)
├── {talk-slug}.pdf               ← PDF export (Phase 5 final step)
├── presentation-outline.md        ← the outline (Phase 3/4 output)
└── assets/                        ← images, memes, screenshots (author provides)
```

The speaker's template is read-only — never modify it.

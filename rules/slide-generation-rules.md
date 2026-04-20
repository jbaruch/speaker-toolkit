# Slide Generation Rules

## Speaker Notes — Separate Batch Pass

Speaker notes MUST be injected as a separate step AFTER all slides are created.
Never add notes inline during slide creation.

```python
# ✅ CORRECT: Separate pass after all slides exist
prs = Presentation('deck.pptx')
for idx, notes_text in notes_map.items():
    slide = prs.slides[idx]
    slide.notes_slide.notes_text_frame.text = notes_text
prs.save('deck.pptx')

# ❌ WRONG: Adding notes during slide creation
for slide_data in outline:
    slide = add_slide(...)
    slide.notes_slide.notes_text_frame.text = slide_data['notes']  # NOT HERE
```

Why: MCP PPT server doesn't support notes. Notes are always a python-pptx
batch operation on the saved .pptx file.

## Template Stripping — Before Content

Remove all existing slides from the template BEFORE adding new content slides.
The clean deck should retain only layout definitions, no demo/sample slides.

## Keynote Compatibility

Keynote uses a stricter OOXML parser than PowerPoint. The rules below
prevent generated `.pptx` files from being rejected on import.

### notesMasterIdLst patch

The `inject-speaker-notes.py` script automatically adds the
`<p:notesMasterIdLst>` element to `ppt/presentation.xml` inside the
`.pptx` when it is missing. No manual step is needed — just run the
script as part of the normal speaker-notes injection pass.

### Use rectangles for decorative lines — never connectors

Connectors emit `<p:cxnSp>` elements that Keynote's parser may reject.
Use a thin `RECTANGLE` shape instead of `add_connector(MSO_CONNECTOR.STRAIGHT, ...)`.

```python
# ✅ CORRECT: thin rectangle acts as a decorative line
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches

shapes.add_shape(
    MSO_SHAPE.RECTANGLE,
    left, top, width,
    Inches(0.04),          # very small height = visual line
)
# then set solid fill + no border as needed

# ❌ WRONG: connector shape — Keynote may refuse the file
from pptx.enum.shapes import MSO_CONNECTOR

shapes.add_connector(MSO_CONNECTOR.STRAIGHT, left, top, end_x, end_y)
```

### Never create slide shapes with python-pptx then remove them via raw XML in the same flow

Do not create a slide shape through python-pptx and then delete that
same shape with `element.getparent().remove(element)` during generation.
That pattern causes python-pptx's internal state to diverge from the
serialized XML, and strict parsers (including Keynote) reject the result.
If a shape is not needed, do not create it in the first place.

This rule applies to slide-shape authoring flows. It does not prohibit
narrowly scoped XML cleanup utilities that remove pre-existing elements
(e.g., `_pptx_repair.py` cleaning viewProps, or `generate-qr.py`
replacing an existing QR image) — those operate on elements not managed
by python-pptx's in-memory state.

### Keep shape IDs contiguous per slide

Each slide's `cNvPr id` values should form a contiguous sequence
(1, 2, 3 ...). This happens automatically when shapes are added through
normal python-pptx APIs. It breaks when shapes are inserted or deleted
via raw XML manipulation — another reason to avoid it.

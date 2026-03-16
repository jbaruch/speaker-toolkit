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
Use the `_sldIdLst` + `drop_rel()` pattern, not a public API.

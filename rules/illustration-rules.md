# Illustration Rules

## Edit vs Regenerate — The Asymmetry Rule

- **Content ADDITIONS** (adding a person, changing composition) → always **REGENERATE**
  from the full prompt. Editing strips the style when adding new visual elements.
- **Content MODIFICATIONS** (changing a hat, making text bigger) → **REGENERATE**.
  Same style-stripping problem as additions.
- **Content REMOVAL** (erase a label, remove a border) → **EDIT** works well.
  The model preserves style when only removing content.

Rule of thumb: if the model must draw something new, regenerate. If it only
erases existing content, edit.

## Edit Prompt Safety — Three Mandatory Components

Every image edit prompt MUST include:

1. `"DO NOT add any new elements."` — suppresses Gemini's aggressive decoration
2. `"Let background continue naturally — no parchment patch."` — prevents flat-fill artifacts when erasing
3. Explicit preservation list: `"Keep the [X]. Keep the [Y]."` — prevents unintended removal of nearby elements

The `--edit` and `--fix` commands auto-append #1 and #2, but #3 must always
be added manually.

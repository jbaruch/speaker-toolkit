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

## Style-Anchor Discipline

Never simplify or rewrite the speaker's original style anchor when iterating.
The specificity of the anchor (period vocabulary, document conventions,
material constraints) is what produces a coherent style across slides; pruning
it for "cleanliness" reverts the output to a generic illustrative default.

Append to the anchor for new constraints — don't replace.

## Build Process — Progressive Reveals

Builds (slide-by-slide reveals where elements appear progressively) are the
hardest illustration case because each step must visually match the others.

Chain backwards from the full image:

- Stage `N` (final) = full slide image
- Stage `N-1` = full minus the last element to reveal
- ... → Stage `00` = empty frame (title + borders only, no content)

Each step's input is the PREVIOUS step's output (chained edits work because
the per-step diff is small and the style is preserved on erasure — see the
edit-vs-regenerate asymmetry rule above).

Don't:

- Use PIL or parchment masking to "blank out" regions — the texture mismatch
  is obvious. Always erase via image-edit, not pixel paste.
- Generate each build stage independently from prompts — visual drift
  between stages will be jarring even if each individual stage looks fine.

Naming convention: `builds/slide-NN-build-MM.jpg` where `MM` is the stage
index (`00` is empty, `01` adds the first element, etc.).

For checklists or progressive-state slides (e.g., a form filling in across
multiple slides), use the same approach: take the most-complete version as
the base and image-edit backwards to earlier states. Adding checkmarks via
edit preserves visual consistency far better than regenerating from prompt.

## Targeted Fixes Beat Regeneration

When an image is "almost perfect" — say, one mislabeled callout or a single
extra element — do a targeted image-edit fix pass. Regenerating from scratch
risks losing all the things that already work. The edit-only-removes
asymmetry applies: erase the wrong element, then if needed regenerate just
the corrected element.

## Iteration Hygiene

Save experiment versions (`v2`, `v3`, `v4`) instead of overwriting the
working file. Slide illustrations take many iterations to converge; stomping
on a near-good output to try one more variation loses information that may
have been worth keeping. The disk cost of saving all attempts is trivial
compared to the cost of regenerating a known-good output you accidentally
clobbered.

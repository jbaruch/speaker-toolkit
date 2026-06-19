---
alwaysApply: true
---

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

`--build` reads #3 from each build step's description (the erase instruction
carries its own `Keep ...` list — see the Edit-Prompt Authoring section of
`skills/illustrations/references/builds.md` for the authoring format). It
validates that every erase step contains a `Keep` clause and skips the slide
with an error if any step is missing one — component #3 is never silently
dropped.

Each build step's description is passed verbatim to the image editor as the
edit prompt — phrase it as a removal, never as the resulting state. An additive
or end-state description ("the CI server appears") contradicts component #1
(`DO NOT add any new elements`, auto-appended); the editor obeys the suffix and
the element survives instead of being erased.

## Style-Anchor Discipline

The style anchor is injected into **every** slide's prompt, so anything in it
renders on **every** slide. The anchor therefore defines **STYLE ONLY** —
medium, palette, rendering technique, lettering/text treatment, period
vocabulary, material constraints, and recurring-character conventions. It must
**never** contain per-slide scene content or recurring page-furniture: parts
inventories, step strips, numbered stations, exploded diagrams, callouts.
That furniture is per-slide **content** — it belongs in the individual slide's
`image_prompt`, not the anchor.

This is most acute for **document-style aesthetics** (instruction booklet,
blueprint, newspaper, schematic), where page furniture *reads* like a style
convention but is per-slide content — keep it in each slide's `image_prompt`,
never in the anchor.

Never simplify or rewrite the speaker's original style anchor when iterating.
The specificity of the *style* (period vocabulary, document conventions,
material constraints) is what produces a coherent look across slides; pruning
it for "cleanliness" reverts the output to a generic illustrative default.

Append to the anchor for new **style** constraints — don't replace. Reconcile
the two halves of this rule by separating axes: **prune content** that crept in
(scene elements, page furniture), but **preserve and extend style** specificity.
"Don't prune" protects the style detail, not smuggled-in content.

`generate-illustrations.py` appends a generation-time `COMPOSE ONLY THE SCENE`
guard to every fresh-generation prompt as a backstop, telling the model to
render only what the per-slide scene names. The guard reduces leakage; a
style-only anchor prevents it. Both matter — don't rely on the guard to excuse
a content-laden anchor.

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

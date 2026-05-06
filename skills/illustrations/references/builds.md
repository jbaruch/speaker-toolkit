# Build Generation — Detail

Reference for Step 4 (builds) and the build-insertion portion of Step 5
(apply to deck). The `illustration-rules` Build Process section is auto-loaded
— this file covers the script contract and deck insertion.

## When to Use Builds

- Complex diagrams revealed one element at a time.
- Checklists that accumulate items across the talk.
- Step-by-step processes shown progressively.
- Any visual that benefits from gradual reveal (NOT PowerPoint animations —
  these are separate slides with separate images).

## Backwards-Chaining Workflow

1. Start from the full slide image (`illustrations/slide-NN.ext`).
2. Use image editing to remove the last element → that's build step `N-1`.
3. Use the `N-1` output as input, remove the next element → that's `N-2`.
4. Continue until `build-00` (empty frame with title/borders only).
5. The final build step is a copy of the full slide image.

This backwards approach produces better results than building up from empty,
because the model preserves the existing composition and style at each step.

## Run

```bash
python3 generate-illustrations.py presentation-outline.md --build 5     # one slide
python3 generate-illustrations.py presentation-outline.md --build all   # all builds
```

Output: `illustrations/builds/slide-NN-build-MM.jpg`.

## Edit-Prompt Authoring

- Each step description must explicitly say what to KEEP: "keep the road",
  "keep the soldiers", etc.
- Always include: "no parchment patch", "no new frames", "solid lines not
  dashed".
- The edit safety suffixes (`DO NOT add any new elements`, `let background
  continue naturally`) are auto-appended by the script.

For near-perfect results, use `--fix` for targeted corrections rather than
regenerating the entire chain.

## Deck Insertion

Build slides are inserted as separate slides in the deck (not PowerPoint
animations). Each step is a full-bleed image:

| Step | Source | Layout | Notes |
|------|--------|--------|-------|
| `build-00` | `builds/slide-NN-build-00.jpg` | BLANK | Empty frame — first slide shown |
| `build-01` | `builds/slide-NN-build-01.jpg` | BLANK | First element revealed |
| ... | ... | BLANK | Progressive reveals |
| `build-N` | Copy of `slide-NN.ext` | BLANK | Full image — final reveal |

Insertion rules:

- Insert in order: `build-00`, `build-01`, ..., `build-N`.
- All build slides use the BLANK layout with `manage_image` full-bleed
  positioning (`left=0, top=0, width=10, height=7.5`).
- Speaker notes go ONLY on the final build step. Earlier steps get empty
  notes — the speaker advances through them silently or with ad-lib
  narration.
- Build slides count toward the slide budget — factor them in during
  presentation-creator's Phase 4 guardrails.
- The final build step (`build-N`) is visually identical to the parent
  slide. In the deck, the parent slide is **replaced** by its build sequence
  — not duplicated after it.

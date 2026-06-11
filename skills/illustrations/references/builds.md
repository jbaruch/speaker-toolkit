# Build Generation — Detail

Reference for Step 5 (builds) and the build-insertion portion of Step 6
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
python3 skills/illustrations/scripts/generate-illustrations.py outline.yaml --build 5     # one slide
python3 skills/illustrations/scripts/generate-illustrations.py outline.yaml --build all   # all builds
```

Output: `illustrations/builds/slide-NN-build-MM.jpg`.

## Edit-Prompt Authoring

Each build step in `outline.yaml` carries two fields. `desc` is the additive,
human-facing reveal ("Add the third panel") — it renders in `slides.md` and the
script. `erase` is the **erase instruction** that turns the next stage into this
one (backwards chaining), and it is the prompt `--build` actually sends to the
image model. "Panel 2 revealed — sergeant, STILL? stamp" does not tell the model
to erase anything, so the element survives and the stage comes out identical to
the previous one.

- `erase` names what to ERASE, then lists what to KEEP — one `Keep` clause per
  element that must persist (page chrome, frames, already-revealed panels,
  borders, labels). This is component #3 of the Edit Prompt Safety rule, and it
  is mandatory: `--build` validates that every non-final step's `erase` carries
  a `Keep` clause and skips the slide with an error if one is missing.
- The final (highest-numbered) step is a copy of the full slide image — it needs
  no `erase` prompt.
- Pull the persisting elements from the slide's full `image_prompt` — the chrome
  that never appears in any build step (header bars, FIG labels, rules) is
  exactly what drifts when it isn't named.
- Include the visual-consistency clauses where relevant: "no parchment patch",
  "no new frames", "solid lines not dashed".
- The edit safety suffixes (`DO NOT add any new elements`, `let background
  continue naturally`) are auto-appended by the script — don't repeat them.

Example (slide with three trial panels revealed progressively):

```yaml
builds:
  - step: 0
    desc: "Empty trial panels — three labeled frames, no content"
    erase: 'Erase Panel 1 content and the "PLUGIN USELESS?" stamp. Keep the page chrome. Keep the three empty panel frames and their TRIAL labels.'
  - step: 1
    desc: "Panel 1 content + PLUGIN USELESS? stamp"
    erase: 'Erase Panel 2 and the "STILL?" stamp. Keep the page chrome. Keep the three panel frames and labels. Keep Panel 1 content.'
  - step: 2
    desc: "Panel 2 content + STILL? stamp"
    erase: 'Erase Panel 3 and the "LIFT +81 PTS" stamp. Keep the page chrome (header bar, FIG label, bottom rule). Keep the three panel frames and their TRIAL labels. Keep Panel 1 and Panel 2 content.'
  - step: 3
    desc: "Panel 3 content + LIFT +81 PTS stamp — full slide"
```

For near-perfect results, use `--fix` for targeted corrections rather than
regenerating the entire chain.

## Deck Insertion

Build slides are inserted via the `ExpandBuilds` VBA pass (real PowerPoint —
structural slide insertion never uses python-pptx, per `rules/deck-editing-rules.md`):

```bash
# 1. Emit the build-expansion manifest from the outline + generated frames.
#    Pass --notes <notes.json> so each parent's speaker notes ride onto its
#    FINAL frame (expansion drops the parent slide, so notes must be carried).
python3 skills/illustrations/scripts/build-expansion-manifest.py \
    outline.yaml illustrations/builds/ \
    --notes notes.json --out builds-manifest.json

# 2. Expand: replace each parent slide with its frames as full-bleed bg-fill slides
skills/presentation-creator/scripts/expand-builds.sh \
    <deck-copy.pptx> <deck-expanded.pptx> builds-manifest.json
```

`ExpandBuilds` processes parents descending so inserting one parent's frames
doesn't shift lower-numbered parents. **Ordering**: run it BEFORE the by-index
passes (`inject-notes.sh`, `apply-backgrounds.sh`, `insert-qr.sh`) — expansion
renumbers every slide after a build parent, so those passes must key on the
POST-expansion deck. Build parents' notes are applied to the final frame by
`ExpandBuilds` itself (from `--notes`), so the later `inject-notes.sh` pass must
NOT also target those original parent indices.

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
- All build slides use the BLANK layout, full-bleed image positioning at 16:9
  slide dimensions (`left=0, top=0, width=13.333", height=7.5"`).
- Speaker notes go ONLY on the final build step. Earlier steps get empty
  notes — the speaker advances through them silently or with ad-lib
  narration.
- Build slides count toward the slide budget — factor them in during
  presentation-creator's Phase 4 guardrails.
- The final build step (`build-N`) is visually identical to the parent
  slide. In the deck, the parent slide is **replaced** by its build sequence
  — not duplicated after it.

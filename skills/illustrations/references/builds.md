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

## Model

Run the chain on an edit-stable model from the Step 6 shortlist. The edit
tiers and their order belong to the registry; see
`skills/illustrations/references/strategy.md` Step 6. Pick any other editor for
a build talk only on the speaker's explicit request.

## Run

```bash
python3 "{speaker_toolkit_root}/skills/illustrations/scripts/generate-illustrations.py" outline.yaml --build 5     # one slide
python3 "{speaker_toolkit_root}/skills/illustrations/scripts/generate-illustrations.py" outline.yaml --build all   # all builds
```

Output: `illustrations/builds/slide-NN-build-MM.jpg`.

Lane options are shared with generation; see
[image-provider-lanes.md](image-provider-lanes.md). Unmasked OpenAI edits can
chain through Codex with `--image-lane cli --allow-cli-native`. Each call edits
the previous frame; it does not regenerate from a fresh prompt. Native geometry
may vary. `erase_region` remains API-only: auto reports the API decision;
forcing CLI refuses with `cli_mask_not_supported` before the edit. A failed
edit aborts that slide's remaining chain and exits non-zero.

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

### `erase_region` — pixel-stable static backgrounds

A step may also carry an optional **`erase_region`**: a normalized
`[x0, y0, x1, y1]` bounding box (0..1, origin top-left) around the element being
erased. It is the fix for build drift: a maskless edit redraws the whole
frame, so a static background can shift or lose elements between frames even
with a `Keep` clause. With `erase_region`, `--build` confines the change to the
box — OpenAI receives a real edit mask, and for both vendors the result is
composited back over the prior frame, so every pixel **outside** the box is the
source pixel exactly. The box is still redrawn by the model (the erased area
shows real background, not a flat fill).

Use it whenever a build has a background that must not move (conveyors,
baseplates, panel frames, blueprint chrome). Omit it for free-form scenes where
whole-frame regeneration is fine. The progress line marks masked steps
`build-NN [masked]`. The final (full-image) step is a verbatim copy and never
takes a region.

```yaml
builds:
  - step: 1
    desc: "Panel 1 content + PLUGIN USELESS? stamp"
    erase: 'Erase Panel 2 and the "STILL?" stamp. Keep the page chrome. Keep the three panel frames and labels. Keep Panel 1 content.'
    erase_region: [0.34, 0.18, 0.66, 0.82]   # the middle (Panel 2) column only
```

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
# 1. Emit the build-expansion manifest from the outline + generated frames, and
#    the whole deck's notes keyed on the expanded deck. notes.json is keyed on
#    the deck before expansion; each parent's note is split across its frames.
python3 "{speaker_toolkit_root}/skills/illustrations/scripts/build-expansion-manifest.py" \
    outline.yaml illustrations/builds/ --out builds-manifest.json \
    --notes notes.json --notes-out notes-expanded.json

# 2. Expand: replace each parent slide with its frames as full-bleed bg-fill slides
bash "{speaker_toolkit_root}/skills/presentation-creator/scripts/expand-builds.sh" \
    <deck-copy.pptx> <deck-expanded.pptx> builds-manifest.json

# 3. Notes: every slide's note on the expanded deck, each build frame included
bash "{speaker_toolkit_root}/skills/presentation-creator/scripts/inject-notes.sh" \
    <deck-expanded.pptx> <deck-notes.pptx> notes-expanded.json
```

With `style_anchor.footer_style` set, the manifest lists footer-stamped PNG
copies of each poster parent's frames from `illustrations/builds/footer-stamped/`
(see `skills/illustrations/scripts/build-expansion-manifest.py` docstring); the
raw frames stay footer-free for editing.

`ExpandBuilds` processes parents descending so inserting one parent's frames
doesn't shift lower-numbered parents. **Ordering**: run it BEFORE the by-index
passes (`inject-notes.sh`, `apply-backgrounds.sh`, `insert-qr.sh`) — expansion
renumbers every slide after a build parent, so those passes must key on the
POST-expansion deck. `notes-expanded.json` already is: inject it as written,
never re-keyed by hand. `ExpandBuilds` writes only the manifest's `notes`, the
final frame's segment, and the notes pass rewrites that frame with the same
text.

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
- Each build step carries its own segment of the parent's notes (Notes per
  frame below). A step with no segment is a silent advance.
- Build slides count toward the slide budget — factor them in during
  presentation-creator's Phase 4 guardrails.
- The final build step (`build-N`) is visually identical to the parent
  slide. In the deck, the parent slide is **replaced** by its build sequence
  — not duplicated after it.

### Notes per frame

A build slide's note is split at its cue lines, so each frame carries the words
spoken while it is on screen. The marker is canonical: a `cue: "BUILD 01"`
script item is the notes line `[BUILD 01]`, step zero-padded.

- Text before the first cue goes on frame 00, the first frame shown.
- Text after `[BUILD NN]` goes on frame NN, up to the next cue; the last
  segment goes on the final frame.
- The cue lines themselves are dropped. The frame change is the cue.
- A frame with no text between its cue and the next is a silent advance.

For the infinite-monkeys slide below, frame 00 gets everything up to "What we
have with LLMs are monkeys." and frame 01 gets only the GPU line:

```text
Infinite monkeys, with infinite typewriters, ... Shakespeare.
What we have with LLMs are monkeys.
[BUILD 01]
We just gave them GPUs, and the randomness is skewed towards Shakespeare.
```

`build-expansion-manifest.py` refuses, naming the slide and the fix:

- a cue past the slide's last frame;
- cues out of increasing order, or repeated;
- an unpadded `[BUILD 1]`;
- a note whose cues differ from the outline script's bare `cue: "BUILD NN"` items.

A build slide with no cue in its note or its script keeps the whole note on
frame 00 and prints a `WARN` on stderr. A bracketed line naming a step without
being a bare cue (`[SLIDE 2 UP — BUILD 00]`) stays in the text with a `WARN`.

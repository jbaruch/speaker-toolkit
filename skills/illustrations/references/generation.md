# Deck Illustration Generation — Detail

Reference for Step 4 (deck illustrations) and Step 6 (apply to deck) in
`SKILL.md`. The `illustration-rules` and `title-overlay-rules` steering rules
are auto-loaded — apply them, don't restate them.

## Setup

Before generating, ensure:

1. **API key(s)** — the script dispatches by model-name prefix:
   `gpt-image-*` → OpenAI; `imagen-*` and `gemini-*` / `nano-banana-*` →
   Google. Add whichever keys the run will actually use to
   `{vault}/secrets.json` (preferred):
   ```json
   {
     "gemini": { "api_key": "your-google-key" },
     "openai": { "api_key": "your-openai-key" }
   }
   ```
   For single-model generation (`generate`, `--edit`, `--build`, `--fix`),
   only the key for the outline's baked `**Model:**` vendor is required —
   the other can be omitted. For `--compare`, every vendor represented in
   `COMPARE_MODELS` is hit, so all corresponding keys must be present (the
   current curated list spans both Google and OpenAI, so both are needed).
   Env-var fallbacks: `GEMINI_API_KEY`, `OPENAI_API_KEY`. Get keys from
   https://aistudio.google.com/app/apikey (Google) and
   https://platform.openai.com/api-keys (OpenAI).

2. **Model availability** — verify the model in the outline header is
   accessible with your key. The script reads it from the
   `**Model:** \`model-name\`` line in the Illustration Style Anchor section.
   Imagen models have no edit endpoint — `--edit`, `--build`, and `--fix`
   require a Gemini or OpenAI model.

3. **Python 3** — stdlib only (`urllib`, `json`, `base64`, `uuid`). No pip
   install needed.

## Slide Selection Modes

```bash
python3 skills/illustrations/scripts/generate-illustrations.py presentation-outline.md remaining
```

`remaining` skips slides whose images already exist; `all` regenerates every
slide; specific slides can be passed as `2 5 9` or a range `2-10`.

## Model Comparison (Phase 2 model selection)

```bash
python3 skills/illustrations/scripts/generate-illustrations.py presentation-outline.md --compare 2
```

Generates the same prompt across the curated `COMPARE_MODELS` list — a
cross-vendor mix of Gemini, Imagen, and OpenAI flagships — for visual
comparison. Output lands in `illustrations/model-comparison/`.

## Edit / Fix / Versioned Generation

| Command | When to use | Output |
|---------|-------------|--------|
| `--edit N "<prompt>"` | Removing content from an existing image | `slide-NN-vM.ext` |
| `--fix N "<prompt>"` | Iterating on a near-perfect image (90%+ correct) | `slide-NN-vM.ext` (next version) |
| `-v 2 5 9` | Generate without overwriting the base image | `slide-NN-vM.ext` |

`--edit` and `--fix` auto-append the safety suffixes (`DO NOT add any new
elements`, `Let background continue naturally`). The explicit preservation
list (`Keep the X. Keep the Y.`) must always be added manually — the script
cannot know what to preserve.

## Slide Format Vocabulary

The outline's Illustration Style Anchor block defines format codes per slide.
The `apply-illustrations-to-deck.py` script maps each code to a layout +
positioning:

| Outline Format | Layout | Image Handling |
|----------------|--------|----------------|
| `FULL` | BLANK | Full-bleed image at 16:9 slide dimensions (`left=0, top=0, width=13.333", height=7.5"`); title repositioned into the declared Safe zone |
| `FULL` + text overlay | BLANK | Full-bleed image + `manage_text` overlay |
| `IMG+TXT` | TITLE only (no body) | Image ~60% of slide on the left, title + body on the right. Exact geometry is owned by the `IMGTXT_*` constants in `skills/illustrations/scripts/apply-illustrations-to-deck.py` (image `left=0.3", top=0.8", width=8.0", height=5.9"`; text column `left=8.5", width≈4.5"`) — read the constants when debugging layout, not the table |
| `EXCEPTION` | Per content type | No generated image — real asset from `[IMAGE NN]` placeholder; handled by presentation-creator's slide walk, not by this skill |

## File Layout

```
{talk-dir}/illustrations/
├── slide-01.jpg               ← one file per illustrated slide
├── slide-02.png
├── slide-05-v2.jpg            ← versioned iterations (--fix / --edit / -v)
├── builds/                    ← progressive reveal build steps (see builds.md)
│   ├── slide-05-build-00.jpg
│   ├── slide-05-build-01.jpg
│   └── slide-05-build-02.jpg
└── model-comparison/          ← --compare output
```

## Title Safe Zone

The `Safe zone:` line in each FULL slide block tells the script to append a
`TITLE SAFE ZONE` directive to the prompt before generation. Five zones are
supported: `upper_third`, `middle_third`, `lower_third`, `left_half`,
`right_half`. See [skills/illustrations/references/title-placement.md](title-placement.md)
for the outline schema and [`rules/title-overlay-rules.md`](../../../rules/title-overlay-rules.md)
for the full policy (auto-loaded).

## Apply to Deck

```bash
python3 skills/illustrations/scripts/apply-illustrations-to-deck.py \
  deck.pptx illustrations/ presentation-outline.md \
  --out deck-with-titles.pptx \
  --scrim-color 100903 --scrim-alpha 47553   # omit for plain 45% black
```

The script:

1. For each FULL slide (a `Safe zone:` field), records the illustration in a
   backgrounds manifest (`--backgrounds-out`, default `<out_stem>.backgrounds.json`)
   for the PowerPoint background pass below — it does NOT insert a picture shape.
2. Adds a zone-sized scrim rectangle above the (later) background and below the title.
3. Repositions title text boxes into the declared safe zone.
4. For each slide with `Format: IMG+TXT`, applies the IMG+TXT layout
   (image ~60% on the left as a picture shape, title placeholder + body on the right).
5. Inserts build sequences (see [skills/illustrations/references/builds.md](builds.md)) for any slide with a
   `- Builds:` block.

Then set the FULL-slide backgrounds via the real PowerPoint app, so each
illustration becomes the slide BACKGROUND FILL (covered by the layout's
halftone-dot overlay) and survives — a python-pptx round-trip would drop it.
Run this as the FINAL write of the build, AFTER speaker notes are injected:

```bash
# operate on a uniquely-named copy — PowerPoint keys open decks by filename
cp deck-with-titles.pptx deck-bg-src.pptx
skills/presentation-creator/scripts/apply-backgrounds.sh \
  deck-bg-src.pptx deck-final.pptx deck-with-titles.backgrounds.json
```

macOS + Microsoft PowerPoint only; see [`rules/deck-editing-rules.md`](../../../rules/deck-editing-rules.md).

If no scrim color is supplied, run `python3 skills/illustrations/scripts/suggest-scrim-color.py illustrations/`
first to sample a deck-tuned color. For warm or cool styled decks, the
sampled color reads as "deeper shadow in the same style" instead of a flat
black film.

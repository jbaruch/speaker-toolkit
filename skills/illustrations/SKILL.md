---
name: illustrations
description: >
  Generates the visual layer of a talk: deck illustrations (FULL / IMG+TXT slides
  with a shared style anchor), progressive-reveal build chains, and YouTube
  thumbnails. Owns style-strategy collaboration (informed by the speaker's
  visual_style_history in the vault), prompt safety, edit-vs-regenerate
  asymmetry, build chaining, title-safe-zone composition, and thumbnail
  composition with a real speaker photo. Invoked by presentation-creator
  during illustration strategy (Phase 2), illustration generation and
  application to the deck (Phase 5), and the post-event YouTube thumbnail
  (Phase 7). Triggers: "illustrate the deck", "generate illustrations",
  "create slide visuals", "design the visual style", "make a thumbnail",
  "build a YouTube thumbnail", "add visuals to my talk", "regenerate slide
  image", "fix the thumbnail", "generate progressive reveals", "build
  sequence for a slide".
user-invocable: true
---

# Illustrations

This skill is an action router — pick the step that matches the user's intent and execute only that step. Do not run other steps; do not parallelize.

Step 1 inspects the request and the talk-directory state to decide the mode (Strategy / Generation / Thumbnail) and which subsequent step is the entry point. The "Multi-mode chaining" section at the end of Step 1 is the one explicit exception, and only triggers when a single invocation requests multiple modes.

Owns every AI-generated image the toolkit produces: deck illustrations, build
chains, and thumbnails. Reads the vault for visual history, the
`presentation-outline.md` for slide-level prompts, and the `speaker-profile.json`
for `visual_style_history` and `publishing_process.thumbnail` config.

The auto-loaded steering rules are the constitution: `illustration-rules`
(edit vs regenerate, build chains, iteration hygiene), `title-overlay-rules`
(safe-zone composition), and `thumbnail-generation-rules` (Phase 7 specifics).
Do not restate them here — apply them.

## Key Files & References

| File / Reference | Purpose |
|------------------|---------|
| `presentation-outline.md` | Source of truth — STYLE ANCHOR header + per-slide Format/Illustration/Image prompt |
| `speaker-profile.json` → `visual_style_history` | Default style, departures, mode profiles, confirmed visual intents |
| `speaker-profile.json` → `publishing_process.thumbnail` | Speaker photo path + aesthetic preference |
| `illustrations/` (alongside outline) | Generated images, builds, model-comparison output |
| [skills/illustrations/references/strategy.md](references/strategy.md) | Phase 2 D#11 detail — style proposal, format vocabulary, model choice, continuity devices |
| [skills/illustrations/references/generation.md](references/generation.md) | Deck generation, edit/fix workflow, model comparison |
| [skills/illustrations/references/builds.md](references/builds.md) | Backwards-chained build generation |
| [skills/illustrations/references/thumbnails.md](references/thumbnails.md) | Phase 7 thumbnail composition + slide selection |
| `skills/illustrations/scripts/generate-illustrations.py` | Deck illustrations, edits, fixes, builds, model comparison |
| `skills/illustrations/scripts/apply-illustrations-to-deck.py` | Insert illustrations + builds into a .pptx |
| `skills/illustrations/scripts/generate-thumbnail.py` | YouTube thumbnail composition |

## Step 1 — Route by Mode

Determine which of three modes applies and execute only the matching steps:

- **Strategy** — outline has no STYLE ANCHOR yet, or the author wants to revise
  it. Run Step 2, then stop unless generation was also requested.
- **Generation** — outline has a STYLE ANCHOR and per-slide prompts. Run
  Step 3 (illustrations), Step 4 (builds, if any slides have a `- Builds:`
  block), and Step 5 (apply to deck, if a .pptx exists).
- **Thumbnail** — talk has been delivered and a video URL is available.
  Skip to Step 6.

### Multi-mode chaining

If — and only if — a single invocation requests multiple modes (e.g., "design
the visual style, then generate everything"), run them in order
Strategy → Generation → Thumbnail. Proceed immediately to the first applicable
step; do not pause for confirmation between modes. A single-mode invocation
runs exactly the one matching step's chain and stops.

## Step 2 — Define Style Strategy

Collaborate with the author to produce the Illustration Style Anchor for the
outline. Read the talk's concepts from `presentation-spec.md`, the speaker's
`visual_style_history` from the profile, and `rhetoric-style-summary.md`
Section 13 for cross-talk visual patterns. Propose 3–4 style options grounded
in **concept fit** + **vault context**, recommend one, iterate on the anchor
paragraph, then define format vocabulary (FULL / IMG+TXT / EXCEPTION + any
talk-specific additions), model choice, and visual continuity devices.

Full protocol with the option-presentation template, format vocabulary
defaults, and continuity-device options: [skills/illustrations/references/strategy.md](references/strategy.md).

Write the approved STYLE ANCHOR block into the outline header. Proceed
immediately to Step 3 if generation was also requested; otherwise finish here.

## Step 3 — Generate Deck Illustrations

Batch-generate every missing slide illustration from the outline:

```bash
python3 skills/illustrations/scripts/generate-illustrations.py \
  presentation-outline.md remaining
```

Review with the author. For targeted corrections use `--fix` (preserves the
near-good output); for additions use full regeneration; for removals use
`--edit`. The edit-vs-regenerate asymmetry rule (`illustration-rules` §1)
governs which to pick. Save iteration versions (`v2`, `v3`) instead of
overwriting — see `illustration-rules` Iteration Hygiene.

Operational detail (compare modes, prompt patterns, retry ladder):
[skills/illustrations/references/generation.md](references/generation.md).

Proceed immediately to Step 4.

## Step 4 — Generate Builds

If any slides in the outline have a `- Builds:` block, generate the
backwards-chained build images. Each step's input is the previous step's
output — never regenerate independently from prompts.

```bash
python3 skills/illustrations/scripts/generate-illustrations.py \
  presentation-outline.md --build all
```

Output: `illustrations/builds/slide-NN-build-MM.jpg`. Build-00 is the empty
frame; build-N is the full image. Detail and the per-step contract:
[skills/illustrations/references/builds.md](references/builds.md).

If no slides specify builds, proceed silently to Step 5.

## Step 5 — Apply Illustrations to Deck

Insert generated illustrations and build sequences into the .pptx. Build
slides replace their parent slide rather than duplicating after it; speaker
notes go on the final build step only.

The script contract is `DECK ILLUSTRATIONS_DIR OUTLINE_MD` (positional, in
that order), with optional `--out`, `--image-ext`, `--scrim-color`,
`--scrim-alpha`. It writes a new `<stem>-with-titles.pptx` next to the
input deck unless `--out` is given.

```bash
python3 skills/illustrations/scripts/apply-illustrations-to-deck.py \
  deck.pptx illustrations/ presentation-outline.md
```

If no .pptx exists yet (Phase 5 hasn't run), finish here — presentation-creator
Phase 5 will call back into this skill at Step 5 once the deck is built.

## Step 6 — Generate Thumbnail

Run the thumbnail composition for a delivered talk. Surface 3–5 candidate
slides ranked by visual impact, let the speaker pick, then compose:

```bash
python3 skills/illustrations/scripts/generate-thumbnail.py \
  --slide-image illustrations/slide-NN.png \
  --speaker-photo "$SPEAKER_PHOTO" \
  --title "HOOK TITLE" \
  --aesthetic <photo|comic_book>
```

Aesthetic precedence (`thumbnail-generation-rules` §7): explicit speaker
preference → `default_illustration_style` → confirmed intents → `photo`.
For illustrated decks, also pass `--portrait-style "<anchor>"` so the
portrait is pre-stylized to match the deck.

Iteration is conversational — change one thing at a time (style variant,
expression, colors, title text, slide). Detail:
[skills/illustrations/references/thumbnails.md](references/thumbnails.md).

Finish here.

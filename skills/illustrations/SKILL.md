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
chains, and thumbnails. Reads the vault for visual history, `outline.yaml` for
the style anchor and slide-level prompts, and the `speaker-profile.json`
for `visual_style_history` and `publishing_process.thumbnail` config.

The auto-loaded steering rules are the constitution: `illustration-rules`
(edit vs regenerate, build chains, iteration hygiene), `title-overlay-rules`
(safe-zone composition), and `thumbnail-generation-rules` (Phase 7 specifics).
Do not restate them here — apply them.

## Key Files & References

| File / Reference | Purpose |
|------------------|---------|
| `outline.yaml` | Source of truth — `style_anchor` (model, per-format anchors, composition, embedded_footer, text_treatment) + per-slide `format` / `image_prompt` / `text_overlay` / `safe_zone` / `builds` |
| `speaker-profile.json` → `visual_style_history` | Default style, departures, mode profiles, confirmed visual intents |
| `speaker-profile.json` → `publishing_process.thumbnail` | Speaker photo path + aesthetic preference |
| `illustrations/` (alongside outline) | Generated images, builds, model-comparison output |
| `style-explore/` (alongside outline) | Phase 2 exploration grid (style × model × format) + `index.md` + `rendered.json` manifest |
| [skills/illustrations/references/strategy.md](references/strategy.md) | Phase 2 detail — idea-sourcing wizard, optimization priorities, model shortlist, style proposals, exploration render, the render-before-bake gate, continuity devices |
| [skills/illustrations/references/generation.md](references/generation.md) | Deck generation, edit/fix workflow, model comparison |
| [skills/illustrations/references/builds.md](references/builds.md) | Backwards-chained build generation |
| [skills/illustrations/references/thumbnails.md](references/thumbnails.md) | Phase 7 thumbnail composition + slide selection |
| [skills/illustrations/references/style-explore-candidates-schema.md](references/style-explore-candidates-schema.md) | `--style-explore` contract — `candidates.json` input + `rendered.json` output |
| `skills/illustrations/scripts/model_registry.py` | Model roster, aliases, attributes; `--check-freshness` + `--shortlist` |
| `skills/illustrations/scripts/generate-illustrations.py` | Deck illustrations, edits, fixes, builds, model comparison, style exploration |
| `skills/illustrations/scripts/apply-illustrations-to-deck.py` | Insert illustrations + builds into a .pptx |
| `skills/illustrations/scripts/generate-thumbnail.py` | YouTube thumbnail composition |

## Step 1 — Route by Mode

Determine which of three modes applies and execute only the matching steps:

- **Strategy** — outline has no STYLE ANCHOR yet, or the author wants to revise
  it. Run Step 2 (freshness), then Steps 3-9 (style strategy), then stop unless
  generation was also requested.
- **Generation** — outline has a STYLE ANCHOR and per-slide prompts. Run
  Step 2 (freshness), Step 10 (illustrations), Step 11 (builds, if any slides
  have a `builds:` block), and Step 12 (apply to deck, if a .pptx exists).
- **Thumbnail** — talk has been delivered and a video URL is available.
  Skip to Step 13.

### Multi-mode chaining

If — and only if — a single invocation requests multiple modes (e.g., "design
the visual style, then generate everything"), run them in order
Strategy → Generation → Thumbnail. Proceed immediately to the first applicable
step; do not pause for confirmation between modes. A single-mode invocation
runs exactly the one matching step's chain and stops.

"Proceed immediately" governs handoff between modes — it never overrides the
within-Strategy human gates (Steps 3, 4, 9). Those stop for the speaker even in a
chained invocation.

## Step 2 — Check Image-Model Freshness

Run the deterministic precheck first, then report its verdict in one line —
never skip this step silently:

```bash
python3 skills/illustrations/scripts/model_registry.py --check-freshness
```

The script emits JSON: `last_reviewed`, `age_days`, `stale`, and the full
`models` roster (ids, aliases, attributes). State the verdict before
proceeding (e.g. "Registry reviewed 2026-06-02, 0 days old — fresh").

- **`stale: true`** — use `WebSearch` to identify the current flagship image
  models from Google (Gemini image, Imagen) and OpenAI (`gpt-image-*`), plus
  any other vendor with a public image API. Reconcile the registry in
  `skills/illustrations/scripts/model_registry.py`: add new flagships, drop
  discontinued ones, refresh the attribute tiers, bump `REGISTRY_LAST_REVIEWED`.
  "Nano Banana" is Google's codename for the Gemini image line (Nano Banana
  Pro = Gemini 3 Pro Image) — fold a codename into the matching entry's
  `aliases`, never add it as a separate model. The speaker approves the edits.
- **`stale: false`** — the roster is current; do not web-search.

For Generation mode entering an existing outline, also confirm the outline's
baked model is still in the roster. Check it against the JSON `models` list
(the alias map resolves codenames). If absent or clearly superseded, surface
that to the speaker — they keep the baked model or re-run the exploration
(Step 3). Never silently swap the model.

`generate-illustrations.py` dispatches by family: `gemini-*` / `nano-banana-*`
(Google `generateContent`), `imagen-*` (Google `:predict`), `gpt-image-*`
(OpenAI). A model from a new vendor family needs a `model_family()` +
`_call_<vendor>` adapter before it can render — surface that as a follow-up
script change.

Proceed immediately to Step 3 or Step 10 per Step 1's routing.

## Step 3 — Source Style Ideas

Open the strategy collaboration by asking where the visual ideas come from.
Present an `AskUserQuestion` multi-select of idea sources — your usual, mode /
series match, new to you, wild card, what's trending, "I'll drive (here are my
references)" — plus a Quick-default fast path. The 3-4 proposals in Step 7 span
the checked sources. Never skip this step silently; never bake a model or style
from this menu by reasoning — every candidate reaches the speaker as a rendered
sample in Steps 8-9.

Source vocabulary, the Quick-default path, no-profile degradation:
[skills/illustrations/references/strategy.md](references/strategy.md).

Proceed immediately to Step 4.

## Step 4 — Establish Optimization Priorities

Elicit what the speaker optimizes for with an `AskUserQuestion` multi-select
(checkboxes, not radio): cost, speed, quality, build-editability. Auto-add
build-editability when any slide has a `Builds:` block. Never skip this step
silently — the priorities drive the shortlist in Step 6.

Proceed immediately to Step 5.

## Step 5 — Define Format Vocabulary + Composition

Ask the speaker — `AskUserQuestion`, never infer — how titles and footers are rendered:

- **Bleed** — title + footer baked into every image, stylized to the art (the
  example noir deck). Striking and consistent, but **not editable** after
  generation. Sets `composition: poster-theatrical` and locks every slide to
  **FULL** (no IMG+TXT, no safe zones); the text treatment + footer are recorded
  in the anchor at Step 9.
- **Overlay** — titles + footers added by PowerPoint over a per-slide safe zone.
  Editable, uniform font, less integrated. Standard composition; the format
  vocabulary is FULL / IMG+TXT / EXCEPTION + any talk-specific additions.

Detail: [skills/illustrations/references/strategy.md](references/strategy.md).

Proceed immediately to Step 6.

## Step 6 — Narrow the Model Shortlist

Filter the roster to a shortlist by the Step 4 priorities — no render yet:

```bash
python3 skills/illustrations/scripts/model_registry.py --shortlist <priorities>
```

The roster is a seed cache, not an allowlist. To rank a model not in it (a new
flagship from Step 2, or one the speaker names), WebSearch its attributes and
pass `--add '<json>'`, or list its id directly in `candidates.json` — see
strategy.md.

Proceed immediately to Step 7.

## Step 7 — Propose Styles Across the Checked Sources

Propose 3-4 style options spanning the Step 3 sources, grounded in concept fit +
vault context (the speaker's `visual_style_history`, `rhetoric-style-summary.md`
Section 13). These are candidates for the render, not a commitment — the speaker
picks from rendered pixels, not prose. Option template:
[skills/illustrations/references/strategy.md](references/strategy.md).

Proceed immediately to Step 8.

## Step 8 — Render the Exploration Grid

Write `style-explore/candidates.json` (styles × shortlist × formats per the
schema), then render:

```bash
python3 skills/illustrations/scripts/generate-illustrations.py \
  <outline> --style-explore style-explore/candidates.json
```

This writes the grid under `style-explore/`, an `index.md` contact sheet, and a
`rendered.json` manifest of what actually rendered. The grid is the only place a
model becomes eligible to bake. Never skip this step silently. The speaker picks
a style + model from `style-explore/index.md`.

`candidates.json` input + `rendered.json` output contract:
[skills/illustrations/references/style-explore-candidates-schema.md](references/style-explore-candidates-schema.md).

Proceed immediately to Step 9.

## Step 9 — Bake the Anchor, Then Verify

Write the `style_anchor` block — chosen model + per-format anchors + visual
continuity devices (`conventions`) — into `outline.yaml`. For poster-theatrical
composition, also set `style_anchor.composition: poster-theatrical`,
`style_anchor.embedded_footer: <text>`, and `style_anchor.text_treatment: <how
baked title + footer are rendered>` (e.g. "glowing hand-script neon on an
in-scene surface").

Anchor vs per-slide split — everything that must look identical across slides
lives in the anchor; only the scene and the literal title vary per slide:

- **Anchor**: visual style (per-format anchors), `text_treatment` (the title +
  footer rendering style), and `embedded_footer` (the full footer text). These
  keep every baked title/footer consistent.
- **Per slide**: `image_prompt` carries only the scene; `text_overlay` carries
  only the literal title string for that slide — never the text styling.

Then run the deterministic precheck and report its verdict in one line; never
skip this step silently:

```bash
python3 skills/illustrations/scripts/generate-illustrations.py \
  <outline> --check-style-explore
```

It confirms the baked model was rendered in the grid (exit 0) or refuses with an
actionable message (exit non-zero). On failure the baked model was never shown —
pick a rendered model from `style-explore/index.md` and re-verify, or re-render
(Step 8). Step 10 generation re-runs the same gate, so a baked-but-unrendered
model cannot generate.

Full protocol — the option template, continuity options, the gate contract:
[skills/illustrations/references/strategy.md](references/strategy.md).

Proceed immediately to Step 10 if generation was also requested; otherwise finish
here.

## Step 10 — Generate Deck Illustrations

Batch-generate every missing slide illustration from the outline:

```bash
python3 skills/illustrations/scripts/generate-illustrations.py \
  outline.yaml remaining
```

Review with the author. For targeted corrections use `--fix` (preserves the
near-good output); for additions use full regeneration; for removals use
`--edit`. The edit-vs-regenerate asymmetry rule (`illustration-rules` §1)
governs which to pick. Save iteration versions (`v2`, `v3`) instead of
overwriting — see `illustration-rules` Iteration Hygiene.

Operational detail (compare modes, prompt patterns, retry ladder):
[skills/illustrations/references/generation.md](references/generation.md).

Proceed immediately to Step 11.

## Step 11 — Generate Builds

If any slides in the outline have a `builds:` block, generate the
backwards-chained build images. Each step's input is the previous step's
output — never regenerate independently from prompts. The edit prompt for each
step comes from `builds[].erase` (the additive `builds[].desc` is the
human-facing reveal); `--build` skips any non-final step whose `erase` prompt
lacks a "Keep ..." clause.

```bash
python3 skills/illustrations/scripts/generate-illustrations.py \
  outline.yaml --build all
```

Output: `illustrations/builds/slide-NN-build-MM.<ext>` where `<ext>` is
the MIME-derived extension for each step (`.jpg` / `.png` / `.webp`
depending on the model and source image). Build-00 is the empty frame;
build-N is the full image. Detail and the per-step contract:
[skills/illustrations/references/builds.md](references/builds.md).

If no slides specify builds, proceed silently to Step 12.

## Step 12 — Apply Illustrations to Deck

Insert generated illustrations and build sequences into the .pptx. Build
slides replace their parent slide rather than duplicating after it; speaker
notes go on the final build step only.

The script contract is `DECK ILLUSTRATIONS_DIR OUTLINE_YAML` (positional, in
that order), with optional `--out`, `--image-ext`, `--scrim-color`,
`--scrim-alpha`. It writes a new `<stem>-with-titles.pptx` next to the
input deck unless `--out` is given.

```bash
python3 skills/illustrations/scripts/apply-illustrations-to-deck.py \
  deck.pptx illustrations/ outline.yaml
```

If no .pptx exists yet (Phase 5 hasn't run), finish here — presentation-creator
Phase 5 will call back into this skill at Step 12 once the deck is built.

## Step 13 — Generate Thumbnail

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

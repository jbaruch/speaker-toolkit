# Illustration Strategy — Detail

The Step 3 collaboration in `SKILL.md`. Produces the Illustration Style Anchor
block written into the outline header.

Not every talk needs generated illustrations — demo-heavy, data-heavy, or
screenshot-driven talks may not. When the author wants AI-generated
illustrations, this protocol walks through the visual identity collaboratively,
in the order below: decide what to optimize for, narrow the models by data,
then render styles and models together and pick visually.

## Sub-step 1: Establish Optimization Priorities

Ask what the speaker optimizes for before proposing anything. The priorities
drive which models reach the shortlist (Sub-step 3):

- **cost** — cheaper per-image generation
- **speed** — faster turnaround per image
- **quality** — top-tier fidelity
- **build-editability** — the model must support image editing; required for
  progressive-reveal builds and edit/fix iteration

Present this with `AskUserQuestion` as a **multi-select** (checkboxes, not a
single-choice radio) — the speaker can pick several (e.g. "quality and
editability"). Pass every chosen priority to `--shortlist` (Sub-step 3), which
ranks and filters the roster accordingly.

Auto-flag `build-editability` when any slide carries a `Builds:` block — build
frames are produced by editing the previous frame, so the model must support
editing. A deck with no builds can drop the constraint.

Per-model attributes and how priorities rank them live in
`skills/illustrations/scripts/model_registry.py` (the `MODEL_REGISTRY` entries
and `shortlist_models`). Don't restate the tiers here.

## Sub-step 2: Define Format Vocabulary & Aspect Ratios

Define the slide format types for this talk:

```
SLIDE FORMAT VOCABULARY
========================
FULL     — full-bleed illustration, 1-2 sentences overlaid
           → Landscape 16:9 (1920×1080)
IMG+TXT  — illustration ~60% of slide, text beside/below
           → Portrait 2:3 (1024×1536)
EXCEPTION — real photo, data table, bio, or primary source
           → No generated illustration; uses [IMAGE NN] placeholder
========================
```

Format names and ratios are talk-specific — the author may rename them or add
formats (e.g., DIAGRAM for technical slides, QUOTE for attributed quotations).

## Sub-step 3: Narrow the Model Shortlist

Filter the roster by the Sub-step 1 priorities before rendering anything. This
stages the cost — data-driven narrowing first, pixels later:

```bash
python3 skills/illustrations/scripts/model_registry.py --shortlist <priorities>
```

Pass the priorities comma-separated (e.g. `quality,build-editability`). The
script returns the ranked candidate models as JSON, best first. Carry the top
1–3 into the exploration render. The ranking and filter logic are in
`model_registry.py` — read the JSON, don't reimplement them.

The roster is a seed cache, not an allowlist. When the speaker wants a model
not in it — or Step 2 surfaced a new flagship — WebSearch its cost, speed,
quality, and edit support, then rank it alongside the cached set without
editing the table:

```bash
python3 skills/illustrations/scripts/model_registry.py \
  --shortlist <priorities> --add '[{"id":"...","family":"...","cost":"...","speed":"...","quality":"...","edit":"..."}]'
```

You can also drop the new id straight into `candidates.json` to render it — the
exploration picks visually, so a ranking isn't required. Any id from a
supported vendor family (`gemini-*`, `imagen-*`, `gpt-image-*`) renders with no
code change; only a new vendor family needs a `_call_<vendor>` adapter.
Persistent additions belong in the registry via the Step 2 refresh; per-talk
injections don't touch the table.

## Sub-step 4: Propose Style Ideas with Sample Prompts

Present 3–4 style options informed by **three sources**:

1. **The talk's own concepts, metaphors, and narrative** — the style should
   reinforce the thesis, not be decorative wallpaper.
2. **The vault's visual history** — read `speaker-profile.json` →
   `visual_style_history` for the structured data:
   `default_illustration_style`, `style_departures[]` (what styles the speaker
   has used and what triggered them), `mode_visual_profiles[]` (which modes
   tend toward which aesthetics), and `confirmed_visual_intents[]` (hard
   rules about visual design). Also read `rhetoric-style-summary.md` Section
   13 (cross-talk visual patterns), `slide-design-spec.md`, and `design_rules`.
   Know what the speaker's default looks like so you can propose informed
   departures.
3. **Historical precedent for this mode/context** — read `visual_style_history`
   → `mode_visual_profiles` for the matching mode ID. If the vault shows the
   speaker uses a particular aesthetic for this talk type, surface that as a
   data point (e.g., "your vault shows you use terminal aesthetic for agent
   talks"). If this talk's mode/context has no visual precedent in
   `style_departures`, say so.

Each option includes: a name, **why it fits this talk's concepts**, **how it
relates to the speaker's visual history** (continuation vs. departure), and a
**sample prompt excerpt** showing a specific slide from THIS talk rendered in
the style.

```
ILLUSTRATION STYLE OPTIONS for "{talk title}"
=========================================================

A. [STYLE NAME]
   CONCEPT FIT: [Why this style reinforces the talk's thesis,
   metaphors, and narrative arc — not just what it looks like]

   VAULT CONTEXT: [How this relates to the speaker's visual
   history — continuation of default, intentional departure,
   or precedent from similar talk types]

   Sample prompt (Slide N — [slide title]):
   "[Complete prompt showing this specific slide rendered
   in the proposed style]"

B. [STYLE NAME]
   CONCEPT FIT: [...]
   VAULT CONTEXT: [...]
   Sample prompt (Slide N — [slide title]):
   "[...]"

C. [STYLE NAME]
   ...

RECOMMENDATION: [Which option and why — grounded in concept
fit and vault context, not just aesthetic preference]
=========================================================
```

The key: **each style option explains WHY it fits this specific talk's
concepts**, not just what it looks like. These options become the candidate
styles for the exploration render — the speaker doesn't commit from prose.

## Sub-step 5: Render the Exploration Grid

Models produce meaningfully different aesthetics from the same prompt, and so
do styles. The decision is visual — made from rendered output, not prose
descriptions — and style and model are picked together.

1. **Write `style-explore/candidates.json`** — the shortlisted models, the
   candidate styles with their per-format anchor paragraphs, and one
   representative slide per format (central to the deck's concept, not the
   title slide, not an edge case; each slide must already have a complete
   `[STYLE ANCHOR]. <scene description>` Image prompt). Schema:
   [skills/illustrations/references/style-explore-candidates-schema.md](style-explore-candidates-schema.md).
2. **Render the grid:**
   ```bash
   python3 skills/illustrations/scripts/generate-illustrations.py \
     <outline> --style-explore style-explore/candidates.json
   ```
   Output lands in `style-explore/<style-slug>/<format>/<model>.<ext>` with a
   `style-explore/index.md` contact sheet grouping every render by style.
3. **Present the grid.** Walk the speaker through `index.md`. Lead with a brief
   read of each cell — what each style+model emphasized about the prompt — but
   the visual decision is the speaker's, not the agent's.
4. **Bake the choice.** The chosen model goes into the outline header's
   `**Model:** \`<model-name>\`` line; the chosen style's anchor paragraphs
   become the per-format STYLE ANCHOR blocks. Every subsequent generation in
   Step 4 (deck illustrations) and Step 5 (builds) uses this model.

If the speaker dislikes every cell, iterate — swap a representative slide,
revise an anchor paragraph, or re-run `--shortlist` with different priorities
to widen the model set — then re-render. Bake model-specific prompt
conventions (negative prompts, aspect-ratio tokens, reserved keywords) into the
anchor immediately after the model is chosen, before Step 4 generation runs.

## Sub-step 6: Visual Continuity Devices

Define recurring elements that tie the deck together as a coherent visual
artifact:

- **Sequential numbering** (e.g., "FIG. N" numbering) — ties the deck together
  as one coherent document. The generation model may render numbers
  imperfectly; that's acceptable.
- **Recurring characters/motifs** in consistent style (same uniforms, same
  species, same rendering approach across all appearances).
- **Checklist progression** — a shared base image that gets edited to add
  checkmarks, fill-ins, or stamps across the talk. Use image editing (not
  regeneration) to preserve visual consistency. Track which slide is the base
  image.
- **Progressive visual elements** with explicit base-image tracking: document
  which slide is the "source" image for each progression, so edits chain
  correctly.
- **Annotation style** (callout labels, footnotes, stamps) — keep labels
  funny/deadpan if that's the tone; the gags in labels ARE the point.

## Gate

Author approves the optimization priorities, format vocabulary, style anchor
paragraphs, and model choice. These become the Illustration Style Anchor
section in the outline header. Once written, Step 4 (generation) can run.

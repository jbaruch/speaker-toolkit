# Illustration Strategy — Detail

The Steps 3-9 collaboration in `SKILL.md`. Produces the `style_anchor` block
written into `outline.yaml`, and guarantees the baked model came from a
rendered grid the speaker saw.

Not every talk needs generated illustrations — demo-heavy, data-heavy, or
screenshot-driven talks may not. When the author wants AI-generated
illustrations, this protocol walks the visual identity collaboratively, in step
order: source the ideas, decide what to optimize for, narrow the models by data,
render styles and models together, pick visually, then bake and verify.

## Step 3: Source Style Ideas (the wizard)

Ask where the visual ideas come from before proposing anything — even when the
speaker has visual history. Present an `AskUserQuestion` **multi-select**
(checkboxes, not radio); the checked sources decide which buckets the 3-4
proposals (Step 7) span. This is the visual-layer instance of the shared
idea-sourcing shape: [../../presentation-creator/references/idea-sourcing-wizard.md](../../presentation-creator/references/idea-sourcing-wizard.md).

The talk's own concepts, metaphors, and narrative are always-on grounding — state
them above the menu, not as a checkbox. The six sources, each mapped to its field
under `speaker-profile.json → visual_style_history`:

1. **Your Usual** — `default_illustration_style` (and `default_image_source`).
2. **Mode / Series Match** — `mode_visual_profiles[]` (match `mode_id` →
   `typical_style`) + `style_departures[]` whose `talks[]` overlap this
   series/mode. Surfaces "your vault shows you use X for this talk type."
3. **New To You** — an aesthetic absent from `default_illustration_style` and
   `style_departures[].style`, filtered for concept fit.
4. **Wild Card (дичь)** — a deliberately provocative aesthetic, NOT filtered for
   fit. Provocation, not prescription.
5. **What's Trending** — `WebSearch` for current illustration / AI-art
   aesthetics. No vault field; this is judgment, the only source that reaches the
   network.
6. **I'll Drive** — speaker-supplied direction + reference examples (paths/URLs
   the speaker provides).

Multi-select → the proposals span the checked sources for variety (e.g. one Your
Usual + one Mode Match + one Wild Card).

**Quick-default fast path.** A menu entry that renders `default_illustration_style`
against one sensible shortlisted model immediately, writes `style-explore/` +
`rendered.json` + `index.md`, and shows the result — deferring deeper refinement.
It is the sanctioned way to go fast: it still renders and shows, never silently
bakes. Mechanically it is a one-style, one-model `candidates.json` fed to the same
`--style-explore`, so it flows through the same Step 9 gate — no separate path.

**No-profile / summary-only.** When `visual_style_history` is null or absent,
sources 1-2 have no data — present them as "no history yet" or omit them. Sources
3-6 still work from concept fit + the talk. Quick-default falls back to a
concept-fit default. The grid and gate are unchanged: the wizard degrades, the
enforcement does not.

Never skip this step silently. Never bake a model or style from this menu by
reasoning — every candidate reaches the speaker as a rendered sample.

## Step 4: Establish Optimization Priorities

Ask what the speaker optimizes for. The priorities drive which models reach the
shortlist (Step 6):

- **cost** — cheaper per-image generation
- **speed** — faster turnaround per image
- **quality** — top-tier fidelity
- **build-editability** — the model must support image editing; required for
  progressive-reveal builds and edit/fix iteration

Present with `AskUserQuestion` as a **multi-select** (checkboxes, not radio) — the
speaker can pick several (e.g. `quality,build-editability`). Pass every chosen
priority to `--shortlist` (Step 6).

Auto-flag `build-editability` when any slide carries a `Builds:` block — build
frames are produced by editing the previous frame, so the model must support
editing. A deck with no builds can drop the constraint.

Per-model attributes and how priorities rank them live in
`skills/illustrations/scripts/model_registry.py` (the `MODEL_REGISTRY` entries and
`shortlist_models`). Don't restate the tiers here.

## Step 5: Define Format Vocabulary & Aspect Ratios

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

**Composition choice.** Also decide how text meets the image:

- **Standard overlay** (default) — titles and footers are overlaid at apply time;
  generation reserves a `Safe zone:` per slide (sections 1–7 of
  `rules/title-overlay-rules.md`).
- **Poster-theatrical** — every slide is full-bleed and the title + footer are
  rendered INTO the image, stylized and blended in the deck's own visual
  vocabulary; nothing is overlaid except the QR code. No safe zones. Choose this
  when the speaker wants a unified "all art, no chrome" poster look. Capture the
  deck footer string now (handles/hashtags/URL) — it gets baked into every image,
  so exact small text may be approximated and need a re-roll or `--edit` touch-up.

## Step 6: Narrow the Model Shortlist

Filter the roster by the Step 4 priorities before rendering anything. This stages
the cost — data-driven narrowing first, pixels later:

```bash
python3 skills/illustrations/scripts/model_registry.py --shortlist <priorities>
```

Pass the priorities comma-separated (e.g. `quality,build-editability`). The script
returns the ranked candidate models as JSON, best first. Carry the top 1-3 into
the exploration render. The ranking and filter logic are in `model_registry.py` —
read the JSON, don't reimplement them.

The roster is a seed cache, not an allowlist. When the speaker wants a model not
in it — or Step 2 surfaced a new flagship — WebSearch its cost, speed, quality,
and edit support, then rank it alongside the cached set without editing the table:

```bash
python3 skills/illustrations/scripts/model_registry.py \
  --shortlist <priorities> --add '[{"id":"...","family":"...","cost":"...","speed":"...","quality":"...","edit":"..."}]'
```

You can also drop the new id straight into `candidates.json` to render it — the
exploration picks visually, so a ranking isn't required. Any id from a supported
vendor family (`gemini-*`, `imagen-*`, `gpt-image-*`) renders with no code change;
only a new vendor family needs a `_call_<vendor>` adapter. Persistent additions
belong in the registry via the Step 2 refresh; per-talk injections don't touch the
table.

## Step 7: Propose Styles Across the Checked Sources

Present 3-4 style options spanning the Step 3 sources, each informed by **three
inputs**:

1. **The talk's own concepts, metaphors, and narrative** — the style should
   reinforce the thesis, not be decorative wallpaper.
2. **The vault's visual history** — `speaker-profile.json → visual_style_history`:
   `default_illustration_style`, `style_departures[]`, `mode_visual_profiles[]`,
   `confirmed_visual_intents[]`. Also `rhetoric-style-summary.md` Section 13,
   `slide-design-spec.md`, and `design_rules`.
3. **Historical precedent for this mode/context** — `mode_visual_profiles` for the
   matching mode ID. If the vault shows the speaker uses a particular aesthetic
   for this talk type, surface that. If this talk's mode/context has no precedent
   in `style_departures`, say so.

Each option includes: a name, **why it fits this talk's concepts**, **how it
relates to the speaker's visual history** (continuation vs. departure), and a
**sample prompt excerpt** showing a specific slide from THIS talk in the style.

```
ILLUSTRATION STYLE OPTIONS for "{talk title}"
=========================================================

A. [STYLE NAME]  (source: your usual | mode match | new | wild | trending | yours)
   CONCEPT FIT: [Why this style reinforces the talk's thesis,
   metaphors, and narrative arc — not just what it looks like]

   VAULT CONTEXT: [Continuation of default, intentional departure,
   or precedent from similar talk types]

   Sample prompt (Slide N — [slide title]):
   "[Complete prompt showing this specific slide rendered
   in the proposed style]"

B. [STYLE NAME]
   ...

RECOMMENDATION: [Which option and why — grounded in concept
fit and vault context, not just aesthetic preference]
=========================================================
```

These are candidates for the render, not a commitment — the speaker doesn't
commit from prose.

## Step 8: Render the Exploration Grid

Models produce meaningfully different aesthetics from the same prompt, and so do
styles. The decision is visual — made from rendered output, not prose — and style
and model are picked together.

1. **Write `style-explore/candidates.json`** — the shortlisted models, the
   candidate styles with their per-format anchor paragraphs, and one
   representative slide per format (central to the deck's concept, not the title
   slide, not an edge case; each slide must already have a complete `[STYLE
   ANCHOR]. <scene description>` Image prompt). Schema:
   [style-explore-candidates-schema.md](style-explore-candidates-schema.md).
2. **Render the grid:**
   ```bash
   python3 skills/illustrations/scripts/generate-illustrations.py \
     <outline> --style-explore style-explore/candidates.json
   ```
   Output lands in `style-explore/<style-slug>/<format>/<model>.<ext>` with a
   `style-explore/index.md` contact sheet and a `style-explore/rendered.json`
   manifest recording which models actually rendered OK (the gate's source of
   truth).
3. **Present the grid.** Walk the speaker through `index.md`. Lead with a brief
   read of each cell — what each style+model emphasized — but the visual decision
   is the speaker's, not the agent's.

If the speaker dislikes every cell, iterate — swap a representative slide, revise
an anchor paragraph, or re-run `--shortlist` with different priorities to widen
the model set — then re-render.

## Step 9: Bake the Anchor, Then Verify

Bake the choice into `outline.yaml`'s `style_anchor`: the chosen model goes in
`style_anchor.model`; the chosen style's anchor paragraphs become `style_anchor.full`
and `style_anchor.imgtxt`; the visual continuity devices go in
`style_anchor.conventions`. Bake model-specific prompt conventions (negative
prompts, aspect-ratio tokens, reserved keywords) into the anchor at the same time.

When the composition is poster-theatrical, also set
`style_anchor.composition: poster-theatrical` and
`style_anchor.embedded_footer: <footer text>`. Generation reads these to embed the
title + footer into each image and skip safe zones; apply and deck-build read them
to leave titles/footers off the slide (QR only). Standard-overlay decks omit both.

Then run the render-before-bake gate and report its one-line verdict:

```bash
python3 skills/illustrations/scripts/generate-illustrations.py \
  <outline> --check-style-explore
```

It reads the baked `style_anchor.model`, resolves codenames to canonical ids, and confirms
the model appears among `rendered.json`'s OK renders. Exit 0 = the speaker saw
this model; exit non-zero = the baked model was never rendered. On failure, pick a
rendered model from `index.md` and re-verify, or re-render (Step 8). Step 10
generation re-runs the same gate, so a baked-but-unrendered model can't generate.

**Visual continuity devices** — recurring elements that tie the deck together:

- **Sequential numbering** (e.g., "FIG. N") — ties the deck together as one
  document. Imperfect rendering of the numbers is acceptable.
- **Recurring characters/motifs** in consistent style (same uniforms, same
  species, same rendering across all appearances).
- **Checklist / progressive elements** with explicit base-image tracking — a
  shared base image edited to add checkmarks, fill-ins, or stamps. Use image
  editing (not regeneration) to preserve consistency; document which slide is the
  base.
- **Annotation style** (callout labels, footnotes, stamps) — keep labels
  funny/deadpan if that's the tone; the gags in labels ARE the point.

## Gate

The author approves the optimization priorities, format vocabulary, style anchor
paragraphs, and model choice; these become the `style_anchor` block in
`outline.yaml`. The `--check-style-explore` verdict is the machine-checked
precondition — once it passes, Step 10 generation can run.

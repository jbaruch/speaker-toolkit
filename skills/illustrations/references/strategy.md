# Illustration Strategy — Detail

The Step 2 collaboration in `SKILL.md`. Produces the Illustration Style Anchor
block that gets written into the outline header.

Not every talk needs generated illustrations — demo-heavy, data-heavy, or
screenshot-driven talks may not. When the author wants AI-generated
illustrations, this protocol walks through the visual identity collaboratively.

## Sub-step 1: Propose Style Ideas with Sample Prompts

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
concepts**, not just what it looks like. The author picks one (or mixes
elements), then iterates on the anchor paragraph together.

## Sub-step 2: Define Format Vocabulary & Aspect Ratios

Once the style is chosen, define the slide format types for this talk:

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

Format names and ratios are talk-specific — the author may use different names
or add formats (e.g., DIAGRAM for technical slides, QUOTE for attributed
quotations).

## Sub-step 3: Choose Image Generation Model

Agree on the target model (affects prompt style and capabilities):

- Model name and API (e.g., `gemini-3-pro-image-preview`, `dall-e-3`, `flux`).
- Any model-specific prompt conventions to bake into the style anchor.
- Use `generate-illustrations.py --compare N` to generate the same prompt
  across multiple models for visual comparison — see [generation.md](generation.md).

## Sub-step 4: Visual Continuity Devices

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

Author approves the style anchor paragraphs, format vocabulary, and model
choice. These become the Illustration Style Anchor section in the outline
header. Once written, Step 3 (generation) can run.

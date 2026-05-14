# Illustrated Conference Talk Outline

## Problem/Feature Description

A speaker has been accepted to give a 45-minute keynote about "The Arc of AI" at DevOpsDays Amsterdam 2026. The talk traces the history of developer tool adoption panics — from IDEs to Stack Overflow to AI agents — and argues that each wave follows the same pattern: panic, adoption, normalization. The central metaphor is a "personnel evaluation form" that humanity fills out for each new tool, deciding whether to trust it as a teammate.

The speaker wants AI-generated illustrations for this talk — not stock photos or screenshots, but a cohesive visual identity where every slide feels like a page from the same artifact. They've already chosen a **retro technical manual** style during the architecture phase: every slide looks like a page from a declassified government field manual, with deadpan clinical labeling and vintage technical illustration.

Using the vault data and illustration decisions provided below, create a complete illustrated presentation outline as `outline.yaml`. The outline should have a cohesive visual style applied across all slides via the top-level `style_anchor:` block, with AI-generated illustration prompts (per-slide `image_prompt:` fields) that maintain visual consistency throughout the deck. Follow the schema defined in `skills/presentation-creator/scripts/outline_schema.py` — `style_anchor.full`, `style_anchor.imgtxt`, `style_anchor.conventions`; per-slide `format:` (FULL | IMG+TXT | EXCEPTION | TITLE), `visual:`, `text_overlay:`, `image_prompt:` (must reference the `[STYLE ANCHOR]` token).

## Output Specification

Produce the following file:

1. **`outline.yaml`** — A complete illustrated presentation outline validating against `outline_schema.py`. Run `python3 skills/presentation-creator/scripts/outline_schema.py outline.yaml` to confirm.

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/vault/rhetoric-style-summary.md ===============
# Rhetoric & Style Summary — Alex Chen

Last updated: 2026-03-15

## Section 1: Presentation Modes
**Mode A: "The Provocateur"** — Problem-diagnosis-solution. Heavy memes, audience interaction, humor as persuasion. ~1.4 slides/min. Humor: heavy.
**Mode C: "The Co-Narrator"** — Co-presented talks. Alternating deep dives. ~1.2 slides/min. Humor: moderate.

## Section 2: Opening Patterns
Opens with provocative claims or audience polls. Delayed self-intro (brief bio slide 3, fuller bio mid-talk).

## Section 4: Humor & Wit
Self-deprecating, meme cascades, callback humor, pop-culture references (sci-fi heavy). Running gags across talks.

## Section 6: Closing Patterns
Three-part close: 3 numbered summary points, CTA, social handles. Callbacks to opening.

## Section 7: Verbal Signatures
"is not a thing", "right?", "okay so", "full stop", "with love", "raise your hand if"

## Section 13: Slide Design & Visual Style
Default template: comic-book halftone backgrounds (purple, red, yellow, green, salmon, blue, orange). Multiplication sign bullets. Footer always present.

Cross-talk visual evolution: Default is comic-book halftone for Mode A talks. Terminal/hacker aesthetic used for agent-focused talks (3 instances). BTTF retro-futurism used for co-presented talks with co-presenter Simon (2 instances). Each departure was content-driven — the visual style reinforced the talk's framing device.

## Section 15: Areas for Improvement
- Rushes closing section (6/18 talks)
- Meme accretion in Act 1 (4/18 talks)

## Section 16: Speaker-Confirmed Intent
- Comic-book halftone is the default, departures are deliberate and content-driven
- On-slide profanity: never
- Three-point close: non-negotiable
- Visual style should reinforce the talk's central metaphor, not be decorative
=============== END OF FILE ===============

=============== FILE: inputs/vault/speaker-profile.json ===============
{
  "schema_version": 1,
  "generated_date": "2026-03-15",
  "talks_analyzed": 18,
  "speaker": {
    "name": "Alex Chen",
    "handle": "@alexchen",
    "website": "alexchen.dev",
    "shownotes_url_pattern": "alexchen.dev/{slug}"
  },
  "infrastructure": {
    "template_pptx_path": "/templates/alex-template.pptx",
    "presentation_file_convention": "{pptx_source_dir}/{conference}/{year}/{talk-slug}/"
  },
  "presentation_modes": [
    {"id": "a", "name": "The Provocateur", "description": "Problem-diagnosis-solution with heavy memes", "when_to_use": "Culture/process talks, myth-busting", "slide_density_per_min": 1.4, "humor_register": "heavy"},
    {"id": "c", "name": "The Co-Narrator", "description": "Co-presented alternating deep dives", "when_to_use": "Co-presented talks, broad scope topics", "slide_density_per_min": 1.2, "humor_register": "moderate"}
  ],
  "design_rules": {
    "background_color_strategy": "random_non_repeating",
    "footer": {"always_present": true, "pattern": "@alexchen | #{conference} | #{topic} | alexchen.dev"},
    "slide_numbers": "never",
    "default_bullet_symbol": "multiplication_sign"
  },
  "rhetoric_defaults": {
    "default_duration_minutes": 45,
    "modular_design": true,
    "three_part_close": true,
    "on_slide_profanity": "never_default"
  },
  "confirmed_intents": [
    {"pattern": "comic_book_default", "intent": "deliberate", "rule": "Departures from comic-book halftone must be content-driven"},
    {"pattern": "three_point_close", "intent": "deliberate", "rule": "Always exactly three summary points"},
    {"pattern": "on_slide_profanity", "intent": "deliberate", "rule": "Never on slides"}
  ],
  "guardrail_sources": {
    "slide_budgets": [{"duration_min": 45, "max_slides": 70, "slides_per_min": 1.5}],
    "act1_ratio_limits": [{"duration_range": "45 min", "max_percent": 45}]
  },
  "visual_style_history": {
    "default_illustration_style": "comic_book_halftone",
    "default_image_source": "meme",
    "style_departures": [
      {
        "style": "terminal_hacker",
        "trigger": "agent-focused talks (topic-driven)",
        "talks": ["2025-agent-workflows.md", "2025-ai-agents-production.md", "2026-agent-evals.md"],
        "description": "Green-on-black terminal aesthetic with monospace fonts and command-line screenshots."
      },
      {
        "style": "bttf_retro_futurism",
        "trigger": "co-presented talks with Simon (co-presenter-driven)",
        "talks": ["2025-ai-native-dev-part1.md", "2026-ai-native-dev-part2.md"],
        "description": "Back to the Future retro-futurism: neon outlines, DeLorean motifs, 1980s sci-fi aesthetic."
      }
    ],
    "mode_visual_profiles": [
      {"mode_id": "a", "typical_style": "comic_book_halftone", "image_source_mix": "meme-heavy with occasional screenshots"},
      {"mode_id": "c", "typical_style": "varies by co-presenter", "image_source_mix": "mixed"}
    ],
    "evolution_notes": "Style departures started in 2025. Each departure was a deliberate visual reinforcement of the talk's framing device.",
    "confirmed_visual_intents": [
      {"pattern": "style_departure", "intent": "deliberate", "rule": "Visual departures must be justified by the talk's central metaphor or framing device"}
    ]
  }
}
=============== END OF FILE ===============

=============== FILE: inputs/vault/slide-design-spec.md ===============
# Slide Design Spec — Alex Chen
Background pool: purple (#5B2C6F), red (#C0392B), yellow (#F1C40F), green (#27AE60), salmon (#E8A0BF), blue (#2980B9), orange (#E67E22).
Strategy: random non-repeating. White/black for full-bleed image slides only.
Footer: @alexchen | #{conference} | #{topic} | alexchen.dev. Always present. 16pt Arial.
Bullet: multiplication sign. Slide numbers: never.
=============== END OF FILE ===============

=============== FILE: inputs/illustration-decisions.md ===============
# Phase 2 Illustration Decisions (already approved)

## Style Choice
**Retro Technical Manual** — every slide looks like a page from a vintage U.S. Military
technical manual or declassified government field guide. Detailed technical pen-and-ink
line-art diagrams. Aged parchment background with foxing and tea-staining. Blue-ink
leader lines and deadpan callout labels. The "personnel evaluation form" thread becomes
a literal bureaucratic form filling in across the talk.

## Model
`gemini-2.0-flash-preview-image-generation`

## Visual Continuity
- Sequential figure numbering: "FIG. 1", "FIG. 2", etc.
- The "Personnel Evaluation Form" appears first in slide 3 (partially filled),
  returns mid-talk (more fields filled), and appears complete in the closing
- Deadpan military callout labels on every illustration
- Footer stamp style: "CLASSIFIED — FOR CONFERENCE USE ONLY"
=============== END OF FILE ===============

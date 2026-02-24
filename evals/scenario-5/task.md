# Conference Talk Outline

## Problem/Feature Description

A speaker has been accepted to give a 45-minute talk about software supply chain security at KubeCon EU 2026. The talk should argue that most organizations are approaching supply chain security wrong — they focus on tools rather than processes. The speaker wants to use their signature "myth-busting" style: expose the problems with data, use humor and memes to make the pain relatable, and close with a practical framework.

The talk has a strong central metaphor: "supply chain security theater" — the idea that most orgs perform security rituals without actual security. This metaphor should thread through the entire talk, evolving from a surface observation in the opening to a deeper diagnosis by the end. The speaker also wants to use a recurring "security checklist" visual that starts as a joke (checking off meaningless items) but transforms into a real framework by the closing.

The speaker has an existing rhetoric vault with their speaking patterns documented. Using the vault data provided below, create a complete presentation outline that captures the full structure of the talk — detailed enough that a slide designer who has never seen the speaker present could build the deck and a stand-in could deliver it. Every visual element should be specified precisely enough to source or create.

The talk has no co-presenter. Commercial intent is "subtle" (the speaker works at a security company but doesn't want to hard-sell). Profanity register is "moderate" (verbal only). The audience is experienced DevOps/security practitioners.

## Output Specification

Produce the following file:

1. **`presentation-outline.md`** — A complete presentation outline for the talk

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/vault/rhetoric-style-summary.md ===============
# Rhetoric & Style Summary — Jordan Securo

Last updated: 2026-02-20

## Section 1: Presentation Modes
**Mode A: "The Myth Buster"** — Problem-diagnosis-solution. Heavy memes, audience interaction, humor as persuasion. ~1.4 slides/min. Humor: heavy. Commercial: none/subtle.
**Mode B: "The Deep Dive"** — Technical demo-driven. Minimal slides. Moderate humor. ~0.8 slides/min.

## Section 2: Opening Patterns
Typically opens with a provocative claim or bold statement combined with audience interaction. Shownotes URL at slide 4-5. Brief bio at slide 3, fuller bio mid-talk.

## Section 3: Narrative Structures
Primary: problem-diagnosis-solution (70%). Acts split ~35/45/20.

## Section 4: Humor & Wit
Self-deprecating, meme cascades (3-5 in sequence), callback humor, pop-culture references.

## Section 5: Transition Techniques
"next thing you know...", "jokes aside", "okay so here's the thing". Punchline-to-setup bridging.

## Section 6: Closing Patterns
Three-part close: numbered summary (always 3 points), CTA with shownotes URL, social handles with humor sign-off. Often calls back to opening.

## Section 7: Verbal Signatures
"is not a thing", "right?", "okay so", "raise your hand if", "full stop", "with love".

## Section 13: Slide Design
Comic-book aesthetic. Background colors: purple halftone, red halftone, yellow halftone, green halftone, white clean. No adjacent repeats. Footer always: @handle | #conference | #topic | website. Multiplication sign (x) for bullets.

## Section 15: Areas for Improvement
- Rushes closing section (8/12 talks)
- Opening theoretical framing sometimes exceeds 15% of talk time
- Meme accretion in Act 1

## Section 16: Speaker-Confirmed Intent
- Delayed self-introduction: deliberate
- Anti-sell pattern: deliberate
- Three-point close: non-negotiable
- On-slide profanity: never
=============== END OF FILE ===============

=============== FILE: inputs/vault/speaker-profile.json ===============
{
  "schema_version": 1,
  "generated_date": "2026-02-20",
  "talks_analyzed": 15,
  "speaker": {
    "name": "Jordan Securo",
    "handle": "@jordansec",
    "website": "jordan.sec",
    "shownotes_url_pattern": "jordan.sec/{slug}"
  },
  "infrastructure": {
    "template_pptx_path": "/templates/jordan-template.pptx",
    "presentation_file_convention": "{pptx_source_dir}/{conference}/{year}/{talk-slug}/",
    "font_pair": {"title": {"name": "Bangers"}, "body": {"name": "Arial"}}
  },
  "presentation_modes": [
    {"id": "a", "name": "The Myth Buster", "description": "Problem-diagnosis-solution with heavy memes", "when_to_use": "Culture/process talks, myth-busting", "slide_density_per_min": 1.4, "humor_register": "heavy", "commercial_intent": "none", "profanity_default": "moderate"},
    {"id": "b", "name": "The Deep Dive", "description": "Technical demo-driven", "when_to_use": "Tooling/hands-on talks", "slide_density_per_min": 0.8, "humor_register": "moderate", "commercial_intent": "subtle", "profanity_default": "zero"}
  ],
  "design_rules": {
    "background_color_strategy": "random_non_repeating",
    "footer": {"always_present": true, "pattern": "@jordansec | #{conference} | #{topic} | jordan.sec", "font": "Arial", "font_size_pt": 16},
    "slide_numbers": "never",
    "default_bullet_symbol": "multiplication_sign"
  },
  "rhetoric_defaults": {
    "default_duration_minutes": 45,
    "modular_design": true,
    "delayed_self_intro": {"enabled": true, "brief_bio_slide": 3},
    "anti_sell_pattern": true,
    "three_part_close": true,
    "on_slide_profanity": "never_default"
  },
  "confirmed_intents": [
    {"pattern": "delayed_self_introduction", "intent": "deliberate", "rule": "Brief bio slide 3, full re-intro mid-talk"},
    {"pattern": "anti_sell", "intent": "deliberate", "rule": "Argue against own position before pitch"},
    {"pattern": "three_point_close", "intent": "deliberate", "rule": "Always exactly three summary points"},
    {"pattern": "on_slide_profanity", "intent": "deliberate", "rule": "Never on slides, verbal only"}
  ],
  "pacing": {
    "slides_per_minute": {"comfortable": 1.4, "max": 1.5}
  },
  "guardrail_sources": {
    "slide_budgets": [
      {"duration_min": 20, "max_slides": 30},
      {"duration_min": 30, "max_slides": 45},
      {"duration_min": 45, "max_slides": 70},
      {"duration_min": 60, "max_slides": 90}
    ],
    "act1_ratio_limits": [
      {"duration_range": "20-30 min", "max_percent": 40},
      {"duration_range": "45 min", "max_percent": 45},
      {"duration_range": "60+ min", "max_percent": 50}
    ],
    "recurring_issues": [
      {"id": "rushed_closing", "description": "Rushes final section", "guardrail": "Closing must have at least 3 slides and 3 min allocated"},
      {"id": "act1_meme_accretion", "description": "Too many memes in Act 1", "guardrail": "Act 1 meme-only slides should not exceed 60% of Act 1"}
    ]
  },
  "instrument_catalog": {
    "opening_patterns": [
      {"code": "a", "name": "Bold Claim", "best_for": "myth-busting, culture talks"},
      {"code": "b", "name": "Audience Poll", "best_for": "engagement-first, large audiences"},
      {"code": "c", "name": "Failure Framing", "best_for": "war stories, security incidents"}
    ],
    "narrative_structures": [
      {"name": "Problem-Diagnosis-Solution", "best_for": "myth busting", "acts": "35/45/20 split"},
      {"name": "Discovery-Demo", "best_for": "tooling talks", "acts": "20/60/20 split"}
    ],
    "humor_techniques": [
      {"name": "Self-deprecating", "register": "safe"},
      {"name": "Meme cascade", "register": "moderate"},
      {"name": "Callback humor", "register": "safe"}
    ],
    "closing_patterns": [
      {"name": "Three-part summary + CTA", "best_for": "all modes", "structure": "3 numbered points -> CTA -> social"},
      {"name": "Callback close", "best_for": "narrative talks", "structure": "reference opening -> summary -> CTA"}
    ],
    "verbal_signatures": [
      {"phrase": "is not a thing", "usage": "dismissing misconceptions", "frequency": "high"},
      {"phrase": "right?", "usage": "confirmation tag", "frequency": "high"},
      {"phrase": "raise your hand if", "usage": "audience polls", "frequency": "medium"},
      {"phrase": "full stop", "usage": "emphasis", "frequency": "medium"}
    ]
  }
}
=============== END OF FILE ===============

=============== FILE: inputs/vault/slide-design-spec.md ===============
# Slide Design Spec — Jordan Securo
Background pool: purple (#5B2C6F), red (#C0392B), yellow (#F1C40F), green (#27AE60), white (#FFFFFF).
Strategy: random non-repeating. White/black for meme slides only.
Footer: @jordansec | #{conference} | #{topic} | jordan.sec. Always present. 16pt Arial.
Bullet: multiplication sign. Slide numbers: never.
=============== END OF FILE ===============

# Build a Conference Talk Outline

## Background

Sam Rivera is a senior platform engineer who has built a strong reputation as a conference speaker over the past four years. She has analyzed 18 of her past talks into a rhetoric knowledge vault that tracks her presentation patterns, humor style, and verbal signatures. A complete vault is provided below.

Sam has just been accepted to speak at **PlatformCon 2025** (London, June 18) — a 45-minute slot in the main track aimed at senior engineers and engineering managers. Her topic is how platform teams fail by building too much too soon: the "golden path" that turns into a golden cage.

She has shared a brief outline of what she wants to cover:
- The seductive appeal of full internal developer platforms built in-house
- Three real failure modes she has witnessed (with anonymized war stories)
- The counterintuitive argument: a good platform is mostly NOT built
- What "just enough platform" looks like in practice
- A practical decision framework for platform teams

She wants this to be a talk that challenges the audience's assumptions rather than validates them. She is happy for humor but wants the tone to stay practical and credible — this is not a keynote entertainment slot.

## Output Specification

Produce a complete presentation outline saved to:

```
presentations/platformcon/2025/golden-cage/presentation-outline.md
```

The outline should be ready to hand to Sam for review — section by section, slide by slide, with visual descriptions and speaker notes. Include all the structural elements needed to give her flexibility for time adjustments. Include any relevant content from her vault that naturally fits the talk.

**Important:** Sam has specific war stories, data points, and meme preferences she wants to insert herself. Where her input is needed, use typed placeholders (e.g., `[AUTHOR 01: ...]` for her stories, `[DATA 01: ...]` for statistics she'll provide, `[MEME 01]` with a brief describing what meme is needed). She also wants callback opportunities flagged explicitly so she can track the throughline during rehearsal.

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/rhetoric-style-summary.md ===============
# Rhetoric & Style Summary — Sam Rivera
Last updated: 2025-03-01 | 18 talks analyzed

## Status
Processed: 18 | Skipped: 0 | Languages: en (18)

## Section 1: Opening Pattern
Sam consistently opens with a provocative claim or failure story (14/18 talks). She delays her bio to slide 3-4, opening cold with content. The "failure framing" open is her signature — she describes a real (anonymized) situation where something went badly wrong, then asks "how many of you have been here?"

## Section 2: Narrative Structure
Primary arc: problem diagnosis → solution → practical framework (15/18). Uses a three-act structure with an explicit mid-talk pivot ("but here's the thing nobody tells you..."). Bookends are frequent (12/18): opens with a character or scenario, closes with the resolution.

## Section 3: Humor & Wit
Self-deprecating and observational. Avoids pop-culture unless universal (no gaming refs, no niche internet). Favorite technique: mock-outrage at bad practices, delivered deadpan. Running gags escalate: she introduces a ridiculous-but-real practice in Act 1 and calls it back with escalation in Acts 2 and 3.

## Section 4: Audience Interaction
Show-of-hands in the opening (every talk). One rhetorical question per major section transition. Prefers "raise your hand if you've been here" over polling tools.

## Section 5: Transition Techniques
Explicit verbal bridges ("Now here's where it gets interesting", "But wait — it gets worse"). Occasional foreshadowing ("I'll come back to this in a moment").

## Section 6: Closing Pattern
Three-part close: summary bullets → specific CTA (always actionable, never vague) → shownotes URL with QR code. Closing callback to opening scenario resolves the story.

## Section 7: Verbal Signatures
- "Here's the thing nobody tells you..."
- "And I think that's actually fine." (dismissal of false dichotomies)
- "Let's be honest." (before a spicy take)
- "Raise your hand if..." (audience address)
- Occasional dry: "Which is great. That's fine. Everything is fine."

## Section 8: Slide-to-Speech Relationship
Minimal text per slide. Speaker notes are detailed — Sam writes as if she'll forget everything. Heavy use of images and memes as rhetorical punctuation (not filler). Data slides have big numbers, small labels.

## Section 9: Persuasion Techniques
Personal war story → audience identification → data → principle → actionable framework. Builds credibility through acknowledged failure first. Anti-sell present in commercial talks.

## Section 10: Cultural & Pop-Culture References
Avoids niche; uses: aviation safety culture, Formula 1 strategy, cooking analogies.

## Section 11: Technical Content Delivery
Avoids code-heavy slides in talks aimed at mixed audiences. Uses before/after comparisons. Decision trees on slides.

## Section 12: Pacing Clues
Spends ~30% on problem framing (Act 1), 50% on solution/examples (Act 2-3), 20% on framework + close. Default duration: 45 min. Modular: always includes cut lines.

## Section 13: Slide Design Patterns
Dark background, white text. Occasional full-bleed photography. Meme slides are full-bleed with minimal overlay text. Footer: "@srivera | #platformcon | speaking.srivera.dev/{slug}".

## Section 16: Speaker-Confirmed Intent
- "I delay my bio deliberately — I want the audience hooked before I tell them who I am."
- "The mock-outrage delivery is intentional — I want people laughing before I make them uncomfortable."

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "generated_date": "2025-03-01",
  "speaker": {
    "name": "Sam Rivera",
    "handle": "@srivera",
    "website": "srivera.dev",
    "shownotes_url_pattern": "speaking.srivera.dev/{slug}",
    "bio_short": "Platform engineer, chaos practitioner, recovering over-builder. 4 years of conference talks about the infrastructure things nobody wants to admit."
  },
  "infrastructure": {
    "template_pptx_path": "~/Presentations/template/srivera-template.pptx",
    "presentation_file_convention": "~/Presentations/{conference}/{year}/{talk-slug}/",
    "template_layouts": [
      {"index": 0, "name": "TITLE_ONLY", "use_for": "title slide, section dividers"},
      {"index": 1, "name": "TITLE_AND_BODY", "use_for": "content slides with bullets"},
      {"index": 2, "name": "BLANK", "use_for": "full-bleed images, memes"},
      {"index": 3, "name": "TITLE_AND_TWO_COLUMN", "use_for": "before/after, comparisons"}
    ]
  },
  "presentation_modes": [
    {
      "name": "provocateur",
      "description": "Challenge the audience's assumptions head-on. Use failure stories. End with an uncomfortable truth.",
      "when_to_use": "Technical audiences, main track slots, audiences that build things"
    },
    {
      "name": "practitioner",
      "description": "Show the work. Decision frameworks, before/after, real numbers.",
      "when_to_use": "Workshop slots, mixed seniority, audiences that want to take something home"
    }
  ],
  "rhetoric_defaults": {
    "default_duration_minutes": 45,
    "profanity_calibration": "mild_allowed_verbal_only",
    "on_slide_profanity": false,
    "three_part_close": true,
    "modular_design": true,
    "default_bullet_symbol": "→"
  },
  "instrument_catalog": {
    "opening_patterns": [
      {"name": "failure_framing", "description": "Open with a real failure scenario, ask 'who's been here?'", "best_for": "technical audiences, main track"},
      {"name": "bold_claim", "description": "Make the most controversial claim first, defend it backwards", "best_for": "keynote, large rooms"}
    ],
    "narrative_structures": [
      {"name": "problem_diagnosis_solution", "acts": ["problem framing", "root cause", "solution + framework"], "time_allocation": "30/40/30"},
      {"name": "three_war_stories", "acts": ["story 1", "story 2", "story 3 + synthesis"], "time_allocation": "25/25/50"}
    ],
    "verbal_signatures": [
      "Here's the thing nobody tells you...",
      "And I think that's actually fine.",
      "Let's be honest.",
      "Which is great. That's fine. Everything is fine."
    ]
  },
  "guardrail_sources": {
    "slide_budgets": [
      {"duration_minutes": 20, "max_slides": 30, "slides_per_min": 1.5},
      {"duration_minutes": 30, "max_slides": 45, "slides_per_min": 1.5},
      {"duration_minutes": 45, "max_slides": 68, "slides_per_min": 1.5},
      {"duration_minutes": 60, "max_slides": 90, "slides_per_min": 1.5}
    ],
    "act1_ratio_limits": [
      {"duration_minutes": 45, "max_percentage": 45}
    ],
    "recurring_issues": [
      {"issue": "Act 1 overrun", "description": "Problem framing section regularly exceeds 45% of slides", "severity": "warn"},
      {"issue": "Missing cut lines", "description": "Occasionally forgets to add CUT LINE markers", "severity": "warn"}
    ]
  },
  "pacing": {
    "wpm_range": "140-160",
    "slides_per_minute": 1.4
  },
  "pattern_profile": {
    "signature_patterns": [
      {"pattern_id": "narrative-arc", "usage_count": 17, "total_talks": 18, "mastery_level": "signature"},
      {"pattern_id": "bookends", "usage_count": 12, "total_talks": 18, "mastery_level": "signature"},
      {"pattern_id": "brain-breaks", "usage_count": 15, "total_talks": 18, "mastery_level": "signature"}
    ],
    "antipattern_frequency": [
      {"pattern_id": "shortchanged", "occurrences": 4, "total_talks": 18, "severity": "occasional"},
      {"pattern_id": "bullet-riddled-corpse", "occurrences": 2, "total_talks": 18, "severity": "rare"}
    ],
    "never_used_patterns": ["takahashi", "cave-painting", "lipsync", "preroll", "greek-chorus", "talklet"]
  },
  "design_rules": {
    "background_color_strategy": "dark_with_accent_colors",
    "white_black_reserved_for": "full-bleed image/meme slides only",
    "footer": {
      "pattern": "@srivera | #{conference_hashtag} | speaking.srivera.dev/{slug}",
      "position": "bottom-left",
      "font": "Arial",
      "font_size": 9,
      "color_adaptation": "always_white"
    },
    "slide_numbers": "never",
    "default_bullet_symbol": "→"
  },
  "publishing_process": {
    "export_format": "pdf_and_pptx",
    "export_method": "LibreOffice CLI headless",
    "shownotes_publishing": {
      "enabled": true,
      "method": "git push to srivera.dev/speaking repo"
    },
    "qr_code": {
      "enabled": true,
      "target": "shownotes_url",
      "insert_into_deck": true,
      "slide_position": "shownotes_slide"
    }
  }
}

# Review a Draft Conference Talk

## Background

Morgan Lee is a frequent conference speaker who has just finished a first draft of a 45-minute talk for DevRelCon 2025. Morgan uses a structured speaker toolkit that tracks their past patterns and known weak spots, and they want a complete rhetorical review of the draft before presenting it to their co-author.

The review should help Morgan understand: whether the structure is balanced and fits the time slot, what presentation patterns to intentionally deploy (given their speaking history), and whether there are any technique risks they should address before rehearsal.

## Output Specification

Produce a review report saved to `review-report.md` covering:

1. A complete guardrail check for the draft outline — covering slide budget, structure balance, branding, content quality, and all other standard checks. Include a pattern score projection (an estimated numeric score for the talk's rhetorical pattern quality).
2. A pattern strategy recommendation for this talk, organized into tiers based on the speaker's history: what patterns they should definitely use, what's worth considering given the context, what they've never tried but could explore, and one or two wild-card provocations from patterns they've never used (not filtered for relevance — just inspiration).
3. Any specific concerns or flags worth discussing before the next revision

Use the speaker profile and draft outline provided below. The review should be specific and actionable — not generic advice.

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "generated_date": "2025-02-15",
  "speaker": {
    "name": "Morgan Lee",
    "handle": "@mlee_devrel",
    "shownotes_url_pattern": "speaking.morganlee.io/{slug}"
  },
  "rhetoric_defaults": {
    "default_duration_minutes": 45,
    "profanity_calibration": "none",
    "on_slide_profanity": false,
    "three_part_close": true,
    "modular_design": true
  },
  "design_rules": {
    "footer": {
      "pattern": "@mlee_devrel | #{conference_hashtag} | speaking.morganlee.io/{slug}"
    },
    "slide_numbers": "never"
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
      {
        "issue": "meme_accretion",
        "description": "Act 1 accumulates too many meme/image-only slides before the core argument begins",
        "guardrail": "If Act 1 has more than 60% meme/image-only slides, flag it",
        "severity": "warn"
      },
      {
        "issue": "theoretical_framing_delay",
        "description": "Opens with a long theoretical context section before getting to the practical point",
        "guardrail": "If the opening framework section exceeds 10% of total slides before any concrete example, flag it",
        "severity": "warn"
      }
    ]
  },
  "pattern_profile": {
    "signature_patterns": [
      {"pattern_id": "narrative-arc", "usage_count": 20, "total_talks": 22, "mastery_level": "signature"},
      {"pattern_id": "foreshadowing", "usage_count": 18, "total_talks": 22, "mastery_level": "signature"},
      {"pattern_id": "brain-breaks", "usage_count": 19, "total_talks": 22, "mastery_level": "signature"},
      {"pattern_id": "bookends", "usage_count": 17, "total_talks": 22, "mastery_level": "signature"}
    ],
    "contextual_patterns": [
      {"pattern_id": "expansion-joints", "usage_count": 8, "total_talks": 22},
      {"pattern_id": "a-la-carte-content", "usage_count": 5, "total_talks": 22},
      {"pattern_id": "talklet", "usage_count": 4, "total_talks": 22}
    ],
    "antipattern_frequency": [
      {"pattern_id": "shortchanged", "occurrences": 6, "total_talks": 22, "severity": "recurring"},
      {"pattern_id": "bullet-riddled-corpse", "occurrences": 3, "total_talks": 22, "severity": "occasional"}
    ],
    "never_used_patterns": ["takahashi", "cave-painting", "preroll", "greek-chorus", "lipsync", "live-on-tape", "seeding-the-first-question", "crawling-credits"]
  }
}

=============== FILE: inputs/draft-outline.md ===============
# Developer Relations in the Age of AI Assistants

**Spec:** practitioner | 45 min | DevRelCon 2025 | DevRel professionals and community managers
**Slide budget:** 68 slides (TBD)

## Opening Sequence [5 min, slides 1-7]

### Slide 1: Title Slide
### Slide 2: Bio
### Slide 3: Opening Meme — "AI is eating the world"
### Slide 4: Opening Meme — Developer confusion about AI tools
### Slide 5: Opening Meme — "Documentation? We don't do that here"
### Slide 6: Opening Meme — The "just ask ChatGPT" meme
### Slide 7: Shownotes URL

## Act 1: The Challenge [18 min, slides 8-33]

### Slide 8: What is DevRel anyway?
- Body: Three bullet points defining DevRel
- Speaker: "Before we get into AI, let's align on definitions."
### Slide 9: History of DevRel (2000-2010)
### Slide 10: History of DevRel (2010-2015)
### Slide 11: History of DevRel (2015-2020)
### Slide 12: History of DevRel (2020-2024)
### Slide 13: The Tooling Landscape
### Slide 14: Traditional Documentation Workflows
### Slide 15: The Documentation Gap
### Slide 16: Survey Result — "84% of developers say docs are outdated"
  - No source listed
### Slide 17: Survey Result — "71% have given up on a product due to bad docs"
  - No source listed
### Slide 18: "So what do developers do instead?"
### Slide 19: The AI Assistant Adoption Curve
### Slide 20: Meme — "Stack Overflow vs. ChatGPT"
### Slide 21: Data: AI tool adoption stats (2024)
  - Source: "Various reports"
### Slide 22: "The DevRel Fear Response"
  - Body: 6 bullet points: • Fear #1... • Fear #2... • Fear #3... • Fear #4... • Fear #5... • Fear #6...
### Slide 23: Fear #1 in detail
### Slide 24: Fear #2 in detail
### Slide 25: Fear #3 in detail
### Slide 26: Fear #4 in detail
### Slide 27: Fear #5 in detail
### Slide 28: Fear #6 in detail
### Slide 29: "But are these fears justified?"
### Slide 30-33: Supporting data slides (various)

## Act 2: The Opportunity [17 min, slides 34-56]

### Slide 34: "Here's the reframe"
### Slide 35-56: Solutions and case studies

## Closing Sequence [3 min, slides 57-60]

### Slide 57: Summary — 3 key takeaways
### Slide 58: Call to Action
### Slide 59: Shownotes + QR
### Slide 60: Thanks

Total slides: 60

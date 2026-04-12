# Guardrail Audit for a Draft Conference Talk

## Background

Morgan Lee is a frequent conference speaker who has just finished a first draft of a 45-minute talk for DevRelCon 2025. Morgan wants a structured quality audit of the draft before presenting it to their co-author. The audit should check every standard guardrail category and flag any violations.

## Output Specification

Produce a guardrail report saved to `guardrail-report.md` covering all standard check categories: slide budget, structure balance, branding, profanity, data attribution, time-sensitive content, closing completeness, cut lines, and anti-patterns. Each check should be labeled with a clear pass/warn/fail verdict. Include a pattern score projection (an estimated numeric score).

Use the speaker profile and draft outline provided below.

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
  }
}
=============== END OF FILE ===============

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
=============== END OF FILE ===============

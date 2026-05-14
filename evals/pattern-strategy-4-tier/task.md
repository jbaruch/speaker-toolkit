# Pattern Strategy for a Conference Talk

## Background

Morgan Lee is preparing a 45-minute talk for DevRelCon 2025 about "Developer Relations in the Age of AI Assistants." Morgan has a documented history of 22 talks with tracked presentation patterns — some they use consistently, some occasionally, and some they've never tried. There are also known antipatterns from their history.

Given Morgan's pattern profile and the draft outline below, produce a pattern strategy recommendation that organizes techniques into tiers based on Morgan's history and this talk's context.

## Output Specification

Produce a pattern strategy report saved to `pattern-strategy.md` containing:

1. A tiered pattern recommendation organized into tiers based on the speaker's usage history
2. Antipattern flags for any risks detected in the draft, each tagged so the speaker can tell at a glance which risks come from their habitual patterns versus risks specific to this outline
3. Any specific recommendations for this talk

Use the speaker profile and draft outline provided below.

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "generated_date": "2025-02-15",
  "speaker": {
    "name": "Morgan Lee",
    "handle": "@mlee_devrel"
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
=============== END OF FILE ===============

=============== FILE: inputs/outline-draft.yaml ===============
# Phase 2 output — talk metadata + chapter skeleton.
# Slides will be filled in during Phase 3, after pattern-strategy selection.
talk:
  title: "Developer Relations in the Age of AI Assistants"
  slug: "devrelcon-2025-devrel-age-of-ai"
  speakers: ["Morgan Lee"]
  duration_min: 45
  audience: "DevRel professionals and community managers"
  mode: "practitioner"
  venue: "DevRelCon 2025"
  slide_budget: 68
  pacing_wpm: [135, 145]
  architecture: "narrative-arc"      # to be confirmed by the pattern-strategy recommendation
  applied_patterns: []               # Phase 2 fills this in; the eval expects the agent to populate it

chapters:
  - id: ch-opening
    title: "Opening Sequence"
    target_min: 5
    argument_beats:
      - text: "Slides 1-7: title, bio, four opening memes, shownotes."
        slide_refs: [1, 2, 3, 4, 5, 6, 7]
        tags: [meme-heavy-act1]

  - id: ch-challenge
    title: "Act 1: The Challenge"
    target_min: 18
    argument_beats:
      - text: "Slides 8-12: history of DevRel (5 slides of background before any concrete example)."
        slide_refs: [8, 9, 10, 11, 12]
        tags: [background-heavy]
      - text: "Slides 13-15: tooling landscape."
        slide_refs: [13, 14, 15]
      - text: "Slides 16-17: survey stats (no sources cited yet)."
        slide_refs: [16, 17]
        tags: [missing-attribution]
      - text: "Slides 18-20: AI adoption data."
        slide_refs: [18, 19, 20]
      - text: "Slides 22-28: 'The DevRel Fear Response' — 6 fears enumerated one per slide."
        slide_refs: [22, 23, 24, 25, 26, 27, 28]
      - text: "Slides 29-33: supporting data."
        slide_refs: [29, 30, 31, 32, 33]

  - id: ch-opportunity
    title: "Act 2: The Opportunity"
    target_min: 17
    argument_beats:
      - text: "Slide 34: reframe."
        slide_refs: [34]
      - text: "Slides 35-56: solutions and case studies."
        slide_refs: [35, 56]

  - id: ch-closing
    title: "Closing Sequence"
    target_min: 3
    argument_beats:
      - text: "Slide 57: summary — 3 key takeaways. Slide 58: CTA. Slide 59: shownotes + QR. Slide 60: thanks."
        slide_refs: [57, 58, 59, 60]
=============== END OF FILE ===============

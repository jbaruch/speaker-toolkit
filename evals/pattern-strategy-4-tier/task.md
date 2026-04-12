# Pattern Strategy for a Conference Talk

## Background

Morgan Lee is preparing a 45-minute talk for DevRelCon 2025 about "Developer Relations in the Age of AI Assistants." Morgan has a documented history of 22 talks with tracked presentation patterns — some they use consistently, some occasionally, and some they've never tried. There are also known antipatterns from their history.

Given Morgan's pattern profile and the draft outline below, produce a pattern strategy recommendation that organizes techniques into tiers based on Morgan's history and this talk's context.

## Output Specification

Produce a pattern strategy report saved to `pattern-strategy.md` containing:

1. A tiered pattern recommendation organized into exactly four tiers based on the speaker's usage history
2. Antipattern flags for any risks detected in the draft, each tagged with whether it's a known recurring issue or a new contextual concern
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

=============== FILE: inputs/draft-outline.md ===============
# Developer Relations in the Age of AI Assistants

**Spec:** practitioner | 45 min | DevRelCon 2025 | DevRel professionals and community managers
**Slide budget:** 68 slides

## Opening Sequence [5 min, slides 1-7]
### Slide 1: Title Slide
### Slide 2: Bio
### Slide 3-6: Opening Memes (4 consecutive)
### Slide 7: Shownotes URL

## Act 1: The Challenge [18 min, slides 8-33]
### Slide 8-12: History of DevRel (5 slides of background before any concrete example)
### Slide 13-15: Tooling landscape
### Slide 16-17: Survey stats (no sources cited)
### Slide 18-20: AI adoption data
### Slide 22-28: "The DevRel Fear Response" (6 fears enumerated one per slide)
### Slide 29-33: Supporting data

## Act 2: The Opportunity [17 min, slides 34-56]
### Slide 34: Reframe
### Slide 35-56: Solutions and case studies

## Closing Sequence [3 min, slides 57-60]
### Slide 57: Summary — 3 key takeaways
### Slide 58: Call to Action
### Slide 59: Shownotes + QR
### Slide 60: Thanks

Total slides: 60
=============== END OF FILE ===============

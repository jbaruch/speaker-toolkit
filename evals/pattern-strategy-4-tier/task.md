# Pattern Strategy for a Conference Talk

## Background

Morgan Lee is preparing a 45-minute talk for DevRelCon 2025 about "Developer
Relations in the Age of AI Assistants." Morgan has a legacy profile containing
historical pattern classifications, but it predates the current opportunity-aware
contract and cannot authorize those claims.

For this fixed synthetic case, the installed creator requires speaker-profile schema
`5` and pattern-scoring schema `5` for policy-derived history. Schema v5 uses
classification-availability v2 and the bundled `speaker-toolkit-default@1` policy when
there is no strict vault override; schema v4 remains occurrence-only. The supplied
profile uses the occurrence-compatible speaker-profile schema `4`, but its
pattern-scoring schema is the stale schema `4`. It has neither a self-contained policy
stamp nor independently authorized domains, so its old mastery, novelty, frequency,
severity, and trend fields must fail closed even though they are internally
consistent. Its explicitly non-pattern guardrail lane remains independently readable.

Given Morgan's stale pattern profile and the draft outline below, produce a taxonomy-grounded pattern strategy for this talk without treating the legacy fields as speaker history.

## Output Specification

Produce a pattern strategy report saved to `pattern-strategy.md` containing:

1. Surface the pattern-history-disabled warning and recommend reprocessing the stale
   scoring generation as needed, then regenerating schema v5. The bundled policy applies
   automatically; Morgan does not need to invent thresholds.
2. Present one flat relevant-pattern list from the current taxonomy. Do not emit the
   four historical tiers, usage/mastery/trend claims, or `[NEW]` labels. New-to-You is
   authorized only by an available `mastery_and_novelty` domain and an exact
   `never_tried` classification—never by `not_yet_observed`, a raw zero, or the stale
   `never_used_patterns` array supplied here.
3. Flag risks detected in the draft as `[CONTEXTUAL]`. A catalog `[RECURRING]` label
   requires an available `antipattern_recurrence` domain and a derived
   `antipattern_classifications` row classified `high_frequency` or
   `moderate_frequency`; never derive it from the stale raw `antipattern_frequency`
   rows.
4. Preserve the explicitly independent `long_context_ramp` guardrail because it carries
   `source_lane: "non_pattern"`. Report it at its declared severity, but do not present
   it as catalog-derived recurrence.
5. Include specific recommendations for this talk.

Use the speaker profile and draft outline provided below.

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 4,
  "generated_date": "2025-02-15",
  "speaker": {
    "name": "Morgan Lee",
    "handle": "@mlee_devrel"
  },
  "guardrail_sources": {
    "recurring_issues": [
      {
        "id": "long_context_ramp",
        "source_lane": "non_pattern",
        "description": "Delays the first concrete example with historical framing",
        "guardrail": "Reach a concrete audience example within the first 10% of the talk",
        "severity": "warning"
      }
    ]
  },
  "pattern_profile": {
    "pattern_baseline": {
      "schema_version": 1,
      "as_of": "2025-02-15T12:00:00+00:00",
      "scope": "global",
      "active_batch_excluded": false,
      "excluded_filenames": [],
      "eligible_statuses": ["processed", "processed_partial"],
      "pattern_scoring_generation_status": "current",
      "pattern_scoring_generation_reasons": [],
      "pattern_catalog_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "pattern_scoring_schema_version": 4,
      "scored_talk_count": 22,
      "pattern_score_sum": 154,
      "average_pattern_score": 7.0
    },
    "baseline_talk_filenames": [
      "talk-01.md", "talk-02.md", "talk-03.md", "talk-04.md", "talk-05.md",
      "talk-06.md", "talk-07.md", "talk-08.md", "talk-09.md", "talk-10.md",
      "talk-11.md", "talk-12.md", "talk-13.md", "talk-14.md", "talk-15.md",
      "talk-16.md", "talk-17.md", "talk-18.md", "talk-19.md", "talk-20.md",
      "talk-21.md", "talk-22.md"
    ],
    "talks_scored": 22,
    "average_pattern_score": 7.0,
    "score_trend": "stable",
    "pattern_breadth": {
      "avg_distinct_patterns_per_talk": 6.4,
      "trend": "stable",
      "note": "Computed from the exact current pattern cohort."
    },
    "underused_patterns": [
      {"pattern_id": "takahashi", "mastery_level": "never_tried", "fits_modes": ["practitioner"], "note": "A high-fit experiment."}
    ],
    "score_drivers": {
      "direction": "stable",
      "antipattern_drivers": [],
      "pattern_drivers": [],
      "note": "No directional movement in the exact current cohort."
    },
    "by_mode": [
      {"mode_id": "practitioner", "talks_in_mode": 22, "stable": true, "average_pattern_score": 7.0, "top_antipatterns": ["shortchanged"]}
    ],
    "strengths": [
      {"pattern_id": "narrative-arc", "kind": "signature_pattern", "mastery_level": "signature", "evidence": "20 of 22 current-cohort talks", "lean_in": "Use it as the structural backbone."}
    ],
    "strengths_note": "Current-generation strengths only.",
    "note": "Only observable patterns from the current catalog are included.",
    "pattern_usage": [
      {"pattern_id": "narrative-arc", "times_used": 20, "out_of": 22, "usage_rate": 0.91, "trend": "consistent", "mastery_level": "signature"},
      {"pattern_id": "foreshadowing", "times_used": 18, "out_of": 22, "usage_rate": 0.82, "trend": "consistent", "mastery_level": "signature"},
      {"pattern_id": "brain-breaks", "times_used": 19, "out_of": 22, "usage_rate": 0.86, "trend": "consistent", "mastery_level": "signature"},
      {"pattern_id": "bookends", "times_used": 17, "out_of": 22, "usage_rate": 0.77, "trend": "consistent", "mastery_level": "signature"},
      {"pattern_id": "expansion-joints", "times_used": 8, "out_of": 22, "usage_rate": 0.36, "trend": "stable", "mastery_level": "occasional"},
      {"pattern_id": "a-la-carte-content", "times_used": 5, "out_of": 22, "usage_rate": 0.23, "trend": "stable", "mastery_level": "occasional"},
      {"pattern_id": "talklet", "times_used": 4, "out_of": 22, "usage_rate": 0.18, "trend": "stable", "mastery_level": "occasional"}
    ],
    "antipattern_frequency": [
      {"pattern_id": "shortchanged", "times_detected": 6, "out_of": 22, "frequency_rate": 0.27, "trend": "stable", "severity": "recurring"},
      {"pattern_id": "bullet-riddled-corpse", "times_detected": 3, "out_of": 22, "frequency_rate": 0.14, "trend": "stable", "severity": "occasional"}
    ],
    "never_used_patterns": ["takahashi", "cave-painting", "preroll", "greek-chorus", "lipsync", "live-on-tape", "seeding-the-first-question", "crawling-credits"],
    "signature_combinations": [],
    "mastery_levels": {
      "signature": ["narrative-arc", "foreshadowing", "brain-breaks", "bookends"],
      "regular": [],
      "occasional": ["expansion-joints", "a-la-carte-content", "talklet"],
      "rare": [],
      "never_tried": ["takahashi", "cave-painting", "preroll", "greek-chorus", "lipsync", "live-on-tape", "seeding-the-first-question", "crawling-credits"]
    }
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

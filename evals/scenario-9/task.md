# Conference CFP Submission

## Problem/Feature Description

A speaker wants to submit a proposal to speak at a developer conference. The conference's call-for-papers (CFP) requires a title, an abstract (200-300 words), 3-5 key takeaways, and a speaker bio. The speaker has a topic idea but needs help shaping it into a compelling submission that matches their established speaking style.

The speaker wants to propose a talk about "Why Most AI Code Assistants Make Your Code Worse" for DevRelCon 2026. The angle: AI code assistants optimize for speed of generation, not for maintainability, readability, or team conventions — and the industry is sleepwalking into a technical debt crisis. The speaker wants their signature myth-busting style but adapted for a DevRel audience who may feel defensive about AI tooling they promote.

Using the provided vault data, write the CFP submission. The speaker's vault captures their presentation patterns — use it to ensure the submission reflects how they actually speak and present.

## Output Specification

Produce the following files:

1. **`cfp-submission.md`** — The complete CFP submission document containing:
   - Talk title
   - Abstract (200-300 words)
   - Key takeaways (3-5 bullet points)
   - Speaker bio

2. **`presentation-spec.md`** — The intent capture document that informed the submission (working title, thesis, audience, venue, format, constraints)

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/vault/speaker-profile.json ===============
{
  "schema_version": 1,
  "speaker": {
    "name": "Sam Coder",
    "handle": "@samcodes",
    "website": "sam.codes",
    "shownotes_url_pattern": "sam.codes/{slug}",
    "bio_short": "Developer advocate and conference speaker who's been arguing with computers for 15 years.",
    "bio_context": "Former principal engineer at three startups, now helping developers build better tools at DevToolCo."
  },
  "presentation_modes": [
    {"id": "a", "name": "The Myth Buster", "description": "Problem-diagnosis-solution with heavy memes and audience interaction", "when_to_use": "Culture/process talks, myth-busting, challenging conventional wisdom", "humor_register": "heavy", "commercial_intent": "none"},
    {"id": "b", "name": "The Deep Dive", "description": "Technical demo-driven exploration", "when_to_use": "Tooling talks, hands-on sessions", "humor_register": "moderate", "commercial_intent": "subtle"}
  ],
  "rhetoric_defaults": {
    "default_duration_minutes": 45,
    "profanity_calibration": "per_audience",
    "on_slide_profanity": "never_default",
    "anti_sell_pattern": true,
    "three_part_close": true
  },
  "instrument_catalog": {
    "opening_patterns": [
      {"code": "a", "name": "Bold Claim", "best_for": "myth-busting talks"},
      {"code": "b", "name": "Audience Poll", "best_for": "large audiences"},
      {"code": "c", "name": "Failure Framing", "best_for": "war stories"}
    ],
    "verbal_signatures": [
      {"phrase": "is not a thing", "usage": "dismissing misconceptions"},
      {"phrase": "right?", "usage": "confirmation tag"},
      {"phrase": "full stop", "usage": "emphasis after strong claims"}
    ]
  }
}
=============== END OF FILE ===============

=============== FILE: inputs/vault/rhetoric-style-summary.md ===============
# Rhetoric & Style Summary — Sam Coder

Last updated: 2026-02-15

## Section 1: Presentation Modes
Mode A: "The Myth Buster" — Problem-diagnosis-solution. Heavy memes, audience interaction.
Mode B: "The Deep Dive" — Demo-driven. Minimal slides.

## Section 2: Opening Patterns
Opens with bold claims or audience polls. Gets audience engaged immediately.

## Section 4: Humor
Self-deprecating, meme cascades, callback humor. Heavy register in myth-buster mode.

## Section 6: Closing Patterns
Three-part close: 3 numbered summary points, CTA, social handles.

## Section 7: Verbal Signatures
"is not a thing", "right?", "okay so", "full stop"
=============== END OF FILE ===============

=============== FILE: inputs/conference-info.md ===============
**Conference:** DevRelCon 2026
**Location:** London
**Date:** September 2026
**Audience:** Developer advocates, DevRel professionals, community managers
**Talk slots:** 30 minutes or 45 minutes
**CFP Requirements:**
- Title
- Abstract (200-300 words)
- 3-5 key takeaways for attendees
- Speaker bio (100-150 words)
**Theme:** "The Evolving Developer Experience"
=============== END OF FILE ===============

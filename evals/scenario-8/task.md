# Co-Presented Talk Adaptation

## Problem/Feature Description

Two speakers are co-presenting a talk at a developer conference. Speaker A (the vault speaker) has an existing solo talk outline about "Testing in Production" that needs to be adapted for dual delivery. Speaker B is a reliability engineer who will bring SRE expertise. They need the outline restructured so both speakers have clear ownership of sections, smooth handoffs, and consistent branding.

Given the existing single-speaker outline below, adapt it for two co-presenters. Speaker A ("Morgan") owns the testing philosophy and cultural arguments. Speaker B ("Riley") owns the SRE tooling and incident response sections. They'll alternate sections with verbal handoffs.

The vault data for Speaker A is provided. Use it to maintain A's voice and style patterns while accommodating the co-presenter.

## Output Specification

Produce the following files:

1. **`co-presented-outline.md`** — The adapted presentation outline with dual-speaker annotations
2. **`adaptation-checklist.md`** — A checklist of all the adaptations made for co-presentation

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/original-outline.md ===============
# Testing in Production: Why You're Already Doing It

**Spec:** Myth Buster | 45 min | SREcon | SRE practitioners
**Slide budget:** 65 slides

---

## Opening Sequence [3 min, slides 1-5]

### Slide 1: Title Slide
- Visual: "Testing in Production: Why You're Already Doing It"
- Footer: @morgandev | #SREcon | #testinprod | morgan.dev

### Slide 2: Provocative Hook
- Visual: Meme — "You guys are testing in production?" shocked face
- Speaker: "Raise your hand if your company has a strict no-testing-in-production policy. Now keep your hand up if you've ever run a feature flag. Congratulations, you're testing in production."

### Slide 3: Brief Bio
- Visual: Morgan Dev, Senior Engineer at TestCo

### Slide 4: Shownotes
- Visual: morgan.dev/testinprod + QR code
- Speaker: "Slides, links, the whole thing — grab this URL now"

### Slide 5: The Thesis
- Visual: "Production testing isn't reckless — pretending you don't do it is."
- Speaker: "And I'm going to prove it to you in the next 40 minutes."

## Act 1: The Myth [15 min, slides 6-25]

### Slide 6: The Sacred Rule
- Visual: "Never test in production" carved in stone tablet
- Speaker: "We've all heard this right? It's like the eleventh commandment of software engineering."

### Slide 7-12: Evidence of Production Testing
- Visual: Feature flags, canary deploys, A/B tests, chaos engineering, dark launches, progressive rollouts
- Speaker: "Every single one of these is production testing. Full stop."

### Slide 13-18: Meme Cascade — Denial
- Visual: 6 memes about organizations in denial about production testing

### Slide 19-25: The Data
- Visual: Survey data and case studies
- Speaker: "91% of companies with advanced testing practices test in production regularly"

## Act 2: The Reality [18 min, slides 26-50]

### Slide 26-35: Tooling Deep Dive
- Visual: OpenTelemetry, feature flags, chaos tools
- Speaker: "Let me show you what good production testing actually looks like"

### Slide 36-42: Incident Response Integration
- Visual: How production tests catch issues before users report them
- Speaker: "This is where it gets really interesting from an SRE perspective"

### Slide 43-50: The Framework
- Visual: Morgan's testing maturity model
- Speaker: "Here's how to assess where your org is and where to go"

## Closing Sequence [3 min, slides 51-55]

### Slide 51: Summary
- Visual: "1. You're already testing in prod 2. Make it intentional 3. Build the safety nets"

### Slide 52: CTA
- Visual: "Start with one canary deploy this sprint"

### Slide 53: Thanks + Social
- Visual: @morgandev | morgan.dev/testinprod
=============== END OF FILE ===============

=============== FILE: inputs/speaker-profile-excerpt.json ===============
{
  "speaker": {"name": "Morgan Dev", "handle": "@morgandev", "website": "morgan.dev"},
  "design_rules": {
    "footer": {
      "always_present": true,
      "pattern": "@morgandev | #{conference} | #{topic} | morgan.dev",
      "co_presented_extra": "co-presenter handle added after @morgandev, separated by ' & '"
    }
  },
  "rhetoric_defaults": {
    "three_part_close": true,
    "on_slide_profanity": "never_default"
  },
  "instrument_catalog": {
    "verbal_signatures": [
      {"phrase": "right?", "usage": "confirmation tag", "frequency": "high"},
      {"phrase": "full stop", "usage": "emphasis", "frequency": "medium"},
      {"phrase": "raise your hand if", "usage": "audience polls", "frequency": "medium"}
    ]
  }
}
=============== END OF FILE ===============

=============== FILE: inputs/co-presenter-info.md ===============
**Co-presenter:** Riley Ops
**Handle:** @rileyops
**Role:** SRE Lead at ReliabilityCo
**Expertise:** Incident response, observability, chaos engineering
**Sections to own:** Tooling deep dive (slides 26-35), Incident response (slides 36-42)
**Handoff style:** Verbal cue + slide type change
=============== END OF FILE ===============

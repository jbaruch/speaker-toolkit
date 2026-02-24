# Presentation Quality Audit

## Problem/Feature Description

A speaking coach reviews presentation outlines before speakers finalize their decks. They need a systematic quality audit that checks the outline against the speaker's established patterns and constraints. The audit should catch common issues: going over slide budget, spending too long on the problem section before getting to solutions, missing branding elements, inappropriate on-slide language, missing source citations on data slides, stale content, incomplete closings, and known anti-patterns specific to this speaker.

Given a draft presentation outline and the speaker's profile data, produce a comprehensive quality audit report. The report should flag every issue found, reference the specific constraint that was violated, and recommend fixes.

## Output Specification

Produce the following files:

1. **`guardrail-report.txt`** — A structured quality audit report covering all check categories
2. **`recommendations.md`** — Specific recommendations for fixing each issue found

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "speaker": {"name": "Casey Devrel", "handle": "@caseydev"},
  "rhetoric_defaults": {
    "default_duration_minutes": 45,
    "modular_design": true,
    "three_part_close": true,
    "on_slide_profanity": "never_default",
    "profanity_calibration": "per_audience"
  },
  "design_rules": {
    "footer": {"always_present": true, "pattern": "@caseydev | #{conference} | #{topic} | casey.dev", "co_presented_extra": "co-presenter handle after @caseydev"},
    "slide_numbers": "never"
  },
  "guardrail_sources": {
    "slide_budgets": [
      {"duration_min": 20, "max_slides": 30, "slides_per_min": 1.5},
      {"duration_min": 30, "max_slides": 45, "slides_per_min": 1.5},
      {"duration_min": 45, "max_slides": 70, "slides_per_min": 1.5},
      {"duration_min": 60, "max_slides": 90, "slides_per_min": 1.5}
    ],
    "act1_ratio_limits": [
      {"duration_range": "20-30 min", "max_percent": 40},
      {"duration_range": "45 min", "max_percent": 45},
      {"duration_range": "60+ min", "max_percent": 50}
    ],
    "recurring_issues": [
      {"id": "rushed_closing", "description": "Rushes final section due to time", "guardrail": "Closing must have at least 3 slides and 3 min", "severity": "warning"},
      {"id": "act1_meme_accretion", "description": "Too many memes dilute Act 1 argument", "guardrail": "Act 1 meme-only slides should not exceed 60%", "severity": "warning"},
      {"id": "missing_anti_sell", "description": "Forgets to include anti-sell beat in commercial talks", "guardrail": "If commercial_intent != none, include anti-sell section", "severity": "info"}
    ]
  }
}
=============== END OF FILE ===============

=============== FILE: inputs/presentation-outline.md ===============
# Platform Engineering: The Missing Manual

**Spec:** Myth Buster | 45 min | DevOpsCon Berlin | DevOps practitioners
**Slide budget:** 70 slides
**Commercial intent:** subtle

---

## Opening Sequence [3 min, slides 1-5]

### Slide 1: Title Slide
- Visual: "Platform Engineering: The Missing Manual" in bold comic font

### Slide 2: Provocative Hook
- Visual: Meme — "We need a platform team" starter pack
- Speaker: "Raise your hand if your company decided they need a platform team last year. Keep it up if they actually know what that team should build."

### Slide 3: Brief Bio
- Visual: Casey Devrel, Developer Advocate at PlatformCo

### Slide 4: Shownotes URL
- Visual: casey.dev/platform-manual with QR code

### Slide 5: Bold Claim
- Visual: "Platform Engineering is not a thing"
- Speaker: "Yeah I said it. Platform Engineering, as most people practice it, is not a thing."

## Act 1: The Problem [20 min, slides 6-40]

### Slide 6: Why Everyone's Confused
- Visual: meme — confused math lady
- Speaker: "okay so let me paint the picture for you"

### Slide 7: The Gartner Hype
- Visual: Gartner hype cycle graph
- Speaker: "Gartner says 80% of orgs will have platform teams by 2026"

### Slide 8: But Wait
- Visual: meme — "but that's none of my business" Kermit

### Slide 9: The Real Data
- Visual: Chart showing 73% of platform initiatives fail in year one

### Slide 10-15: Meme Cascade — Platform Fails
- Visual: 6 consecutive memes showing platform engineering gone wrong

### Slide 16: The Tool Trap
- Visual: "You don't need a platform, you need a damn conversation"
- Speaker: "And I know what you're thinking — but we already bought the tools!"

### Slide 17-22: More Evidence
- Visual: Case studies and data points

### Slide 23: Survey Data
- Visual: "68% of developers say their internal platform makes things slower"

### Slide 24-28: The Culture Gap
- Visual: Examples of platform teams that became bottlenecks

### Slide 29-35: More Memes and Examples
- Visual: Mixed memes and case study slides

### Slide 36-40: The Vendor Problem
- Visual: How vendors have co-opted the platform engineering narrative
- Speaker: "and look I work at PlatformCo so I'm part of the problem right?"

## Act 2: The Diagnosis [15 min, slides 41-58]

### Slide 41: The Three Root Causes
- Visual: numbered list

### Slide 42-50: Deep Dive on Each Cause
- Visual: Data, examples, and analysis

### Slide 51-55: The Framework
- Visual: Casey's 4-pillar framework for platform engineering

### Slide 56-58: Validation Stories
- Visual: Teams that got it right

## Closing Sequence [2 min, slides 59-60]

### Slide 59: Summary
- Visual: "Remember: 1. Platforms are products 2. Start with developer interviews"
- Speaker: "so to wrap up quickly..."

### Slide 60: Thanks
- Visual: "Thanks! Questions?"

=============== END OF FILE ===============

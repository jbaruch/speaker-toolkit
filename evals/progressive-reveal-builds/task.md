# Adding Progressive Reveals to an Illustrated Talk

## Problem/Feature Description

A speaker is building a 60-minute keynote about "Zero Trust Architecture" that uses AI-generated illustrations in a retro military technical manual style. The talk has a section that introduces five security principles one at a time — each principle is a pillar in an architectural diagram. The speaker wants the audience to see the pillars appear one by one as they're discussed, not all at once.

Similarly, there's a "Security Maturity Checklist" that appears four times across the talk, each time with more items checked off as the audience has learned new concepts.

The speaker has already drafted the base outline with style anchors and image prompts. They now need the two affected slides to be elaborated so the audience sees each element appear one at a time, plus a plan for producing those intermediate images and getting them into the deck.

## Output Specification

Produce the following files:

1. **`updated-outline-excerpt.yaml`** — the updated outline entries for the two slides.

2. **`build-generation-plan.md`** — a step-by-step plan for producing the intermediate images and getting them into the PowerPoint deck. Cover image generation, file organization, and how the intermediate sequence interacts with the slide budget and deck layout.

## Input Files

The following file is provided as input.

=============== FILE: inputs/outline-excerpt.yaml ===============
talk:
  title: "Zero Trust Architecture — From Perimeter to Principles"
  slug: "rsa-2026-zero-trust-architecture"
  speakers: ["Speaker"]
  duration_min: 60
  audience: "Security engineers"
  mode: "provocateur"
  venue: "RSA Conference 2026"
  slide_budget: 90
  pacing_wpm: [135, 145]
  architecture: "narrative-arc"

style_anchor:
  model: "gemini-3-pro-image-preview"
  full: |
    Retro U.S. Military WWII technical manual style. Pen-and-ink line art on
    aged parchment background with foxing. Blue-ink leader lines, decorative
    military document border ornaments, classification stamps, and technical
    manual header formatting. All people/robots/animals wear WWII uniforms
    with garrison caps and rank insignia. Render all callout labels in large
    bold font. FIG. numbering on each illustration.
  imgtxt: |
    Same WWII technical manual style, portrait orientation. Illustration in
    upper 60%, technical annotations below.
  conventions: |
    Sequential FIG. numbering. Classification stamp rotates: RESTRICTED,
    CONFIDENTIAL, TOP SECRET. Recurring character: a sergeant with a
    clipboard evaluating each principle.

chapters:
  - id: ch-principles
    title: "Act 2: The Five Principles"
    target_min: 20
    argument_beats:
      - text: "Walk the five pillars one at a time, then circle back via the maturity checklist."
        slide_refs: [30, 38, 45, 52, 58]

slides:
  - n: 30
    chapter: ch-principles
    title: "The Five Pillars of Zero Trust"
    format: FULL
    visual: "Five classical pillars supporting a ZERO TRUST architrave."
    text_overlay: "The Five Pillars"
    image_prompt: |
      [STYLE ANCHOR]. FIG. 15. Five classical stone pillars in architectural
      elevation view. Each pillar labeled: "VERIFY EXPLICITLY", "LEAST PRIVILEGE",
      "ASSUME BREACH", "MICRO-SEGMENTATION", "CONTINUOUS VALIDATION." Architrave
      reads "ZERO TRUST ARCHITECTURE." The sergeant stands beside with clipboard,
      checking off each pillar. Classification: TOP SECRET.
    big_idea: true
    applied_patterns:
      - id: call-to-adventure
        big_idea_text: "Zero Trust is five principles, not a product."

  - n: 38
    chapter: ch-principles
    title: "Security Maturity Checklist (First Appearance)"
    format: FULL
    visual: "Military personnel evaluation form with first two items checked."
    text_overlay: "Where are you on the maturity curve?"
    image_prompt: |
      [STYLE ANCHOR]. FIG. 20. PERSONNEL EVALUATION FORM: SECURITY MATURITY
      ASSESSMENT. Checklist with 6 items: "IDENTITY VERIFICATION" [checked],
      "ACCESS CONTROLS" [checked], "NETWORK SEGMENTATION" [unchecked],
      "CONTINUOUS MONITORING" [unchecked], "INCIDENT RESPONSE" [unchecked],
      "ZERO TRUST COMPLIANCE" [unchecked]. Stamp: EVALUATION IN PROGRESS.

  - n: 45
    chapter: ch-principles
    title: "Security Maturity Checklist (Second Appearance)"
    format: FULL
    visual: "Same form, now with four items checked."
    text_overlay: "Making progress"
    image_prompt: |
      [STYLE ANCHOR]. FIG. 25. Same PERSONNEL EVALUATION FORM. Now "IDENTITY
      VERIFICATION" [checked], "ACCESS CONTROLS" [checked], "NETWORK
      SEGMENTATION" [checked], "CONTINUOUS MONITORING" [checked], "INCIDENT
      RESPONSE" [unchecked], "ZERO TRUST COMPLIANCE" [unchecked]. Stamp:
      MAKING PROGRESS.

  - n: 52
    chapter: ch-principles
    title: "Security Maturity Checklist (Third Appearance)"
    format: FULL
    visual: "Same form, now with five items checked."
    text_overlay: "Nearly there"
    image_prompt: |
      [STYLE ANCHOR]. FIG. 30. Same form. Five of six checked. Only "ZERO
      TRUST COMPLIANCE" unchecked. Stamp: NEARLY THERE.

  - n: 58
    chapter: ch-principles
    title: "Security Maturity Checklist (Final — All Checked)"
    format: FULL
    visual: "Complete form, all items checked, approval stamp."
    text_overlay: "Approved"
    image_prompt: |
      [STYLE ANCHOR]. FIG. 35. Same form, all six items checked. Large
      "APPROVED" stamp. Radiating approval lines. The sergeant salutes.
=============== END OF FILE ===============

## Key Notes

- The fixture excerpt is intentionally small — it omits other chapters/slides that would be present in a full outline. Treat the slides shown as the only ones requiring elaboration.
- The Five Pillars slide (n=30) walks one pillar at a time.
- The Maturity Checklist slides (n=38, 45, 52, 58) are already a sequence across slides — decide whether each *individual* slide also needs intermediate states and discuss the tradeoff in the plan.

# Illustrated Outline Quality Audit

## Problem/Feature Description

A speaker drafted an illustrated talk and wants a Phase 4 quality audit before they finalize the deck. They hand the agent the talk's `outline.yaml` and the speaker profile and ask for a thorough review.

## Output Specification

Produce the following file:

1. **`guardrail-report.md`** — a Phase 4 audit report covering the outline and the speaker profile together. The report should be structured so the speaker can act on its findings.

## Input Files

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "speaker": {"name": "Pat Illustra", "handle": "@patillustra"},
  "rhetoric_defaults": {
    "default_duration_minutes": 45,
    "modular_design": true,
    "three_part_close": true,
    "profanity_calibration": "verbal-only — never on slides"
  },
  "design_rules": {
    "footer": {
      "elements": ["@patillustra", "#KubeCon"]
    },
    "slide_numbers": "never"
  },
  "guardrail_sources": {
    "slide_budgets": [
      {"duration_min": 45, "max_slides": 70, "slides_per_min": 1.5}
    ],
    "act1_ratio_limits": [
      {"duration_range": "45 min", "max_percent": 45}
    ],
    "recurring_issues": [
      {"id": "rushed_closing", "description": "Rushes final section", "guardrail": "Closing must have at least 3 slides and 3 min", "severity": "warning"}
    ]
  }
}
=============== END OF FILE ===============

=============== FILE: inputs/outline.yaml ===============
talk:
  title: "Observability Beyond Dashboards"
  slug: "kubecon-eu-2026-observability-beyond-dashboards"
  speakers: ["Pat Illustra"]
  duration_min: 45
  audience: "SRE practitioners"
  mode: "provocateur"
  venue: "KubeCon EU 2026"
  slide_budget: 70
  pacing_wpm: [135, 145]
  architecture: "narrative-arc"
  thesis: "Dashboards are not observability. Stop fetishizing them."
  shownotes_url_base: "https://pat.dev/"
  profanity_register: "verbal-only — never on slides"
  applied_patterns:
    - { id: bookends }

style_anchor:
  model: "gemini-2.0-flash-preview-image-generation"
  full: |
    Detailed architectural blueprint on dark blue background. White and cyan
    line drawings with precise technical annotations. Grid overlay. Engineering
    stamp in corner: "APPROVED FOR PRODUCTION." Monospace labels.
  imgtxt: |
    Blueprint schematic panel on dark blue background. White line drawing in
    upper 60% of frame. Technical annotations in cyan monospace.
  conventions: "Sequential drawing numbers DWG-001 onward; recurring system health gauge."

chapters:
  - id: ch-opening
    title: "Opening"
    target_min: 3
    argument_beats:
      - text: "Hook with the dashboard graveyard image."
        slide_refs: [1, 2]

  - id: ch-problem
    title: "Act 1: The Problem"
    target_min: 18
    argument_beats:
      - text: "Tool sprawl and alert fatigue."
        slide_refs: [4, 5]
      - text: "87% of SREs report alert fatigue — needs source."
        slide_refs: [4]
        tags: [data-claim]

  - id: ch-solution
    title: "Act 2: The Solution"
    target_min: 20
    argument_beats:
      - text: "Observability-first architecture, the framework."
        slide_refs: [7]

  - id: ch-close
    title: "Closing"
    target_min: 2
    argument_beats:
      - text: "Wrap up fast — three takeaways and CTA."
        slide_refs: [9, 10]

slides:
  - n: 0
    chapter: ch-opening
    title: "Title Card"
    format: TITLE
    text_overlay: "Observability Beyond Dashboards · Pat Illustra · KubeCon EU 2026"

  - n: 1
    chapter: ch-opening
    title: "The Dashboard Graveyard"
    format: FULL
    visual: "Server room full of flatlined monitoring screens with cobwebs."
    text_overlay: "How many dashboards did you look at this week?"
    image_prompt: |
      [STYLE ANCHOR]. DWG-002. Blueprint elevation view of a server room.
      Rows of monitoring screens, each showing flatlined graphs labeled
      "LAST VIEWED: 18 MONTHS AGO." Cobwebs in precise technical pen style.
      Callout: "FIG. A — THE DASHBOARD GRAVEYARD."
    applied_patterns:
      - { id: opening-punch, flavors: [challenging, unexpected] }

  - n: 2
    chapter: ch-opening
    title: "Bold Claim"
    format: FULL
    visual: "Dashboard with a red REJECTED stamp."
    text_overlay: "Dashboards are not observability."
    image_prompt: |
      [STYLE ANCHOR]. DWG-003. Technical cross-section of a monitoring dashboard
      with large "REJECTED" stamp overlay in red ink. Callout labels:
      "VANITY METRICS", "UNUSED ALERTS", "COPY-PASTED QUERIES."
    big_idea: true
    thesis: preview
    applied_patterns:
      - id: call-to-adventure
        big_idea_text: "Dashboards are not observability."

  - n: 4
    chapter: ch-problem
    title: "Dashboard Fatigue Survey"
    format: IMG+TXT
    visual: "System health gauge in the red zone."
    text_overlay: "87% of SREs report alert fatigue"
    image_prompt: |
      [STYLE ANCHOR]. DWG-005. System health gauge labeled "DASHBOARD FATIGUE
      INDEX." Needle in the red zone. Scale from "MANAGEABLE" to "CRITICAL
      OVERLOAD." Monospace annotation: "87% OF SRES REPORT ALERT FATIGUE."

  - n: 5
    chapter: ch-problem
    title: "Tool Sprawl"
    format: FULL
    visual: "Exploded view of an observability stack."
    text_overlay: "The observability tool stack (simplified)"
    image_prompt: |
      Components flying apart.

  - n: 7
    chapter: ch-solution
    title: "The Reframe"
    format: FULL
    visual: "Revision overlay drawing — old monitoring crossed out, new architecture overlaid."
    text_overlay: "REVISION B — observability-first"
    image_prompt: |
      [STYLE ANCHOR]. DWG-015. Revision overlay drawing. Old monitoring
      architecture ghosted/faded. New observability architecture overlaid in
      bright cyan. Label: "REVISION B — OBSERVABILITY-FIRST ARCHITECTURE."
      Stamp: "UNDER REVIEW."

  - n: 9
    chapter: ch-close
    title: "Summary"
    format: FULL
    visual: "System health gauge now at OPTIMAL."
    text_overlay: "Three takeaways"
    image_prompt: |
      [STYLE ANCHOR]. DWG-026. System health gauge — needle now at "OPTIMAL."
      Stamp: "APPROVED FOR PRODUCTION." Three summary items as engineering specifications.
    thesis: payoff

  - n: 10
    chapter: ch-close
    title: "Thanks + Social"
    format: EXCEPTION
    format_justification: "Real social handles + shownotes URL — no generated asset needed."
    visual: "Social handles and shownotes URL."
    text_overlay: "@patillustra · pat.dev/observability-beyond"
=============== END OF FILE ===============

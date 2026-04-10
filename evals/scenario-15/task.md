# Illustrated Presentation Quality Audit

## Problem/Feature Description

A speaker has drafted an illustrated presentation outline and wants a quality audit before finalizing. The outline uses AI-generated illustrations with a defined style anchor, but several issues were introduced during the drafting process. The audit should catch both standard guardrail issues AND illustration-specific problems: missing format tags, EXCEPTION slides without justification, prompts that don't reference the style anchor, and prompts that are just copy-pasted from the illustration description.

Given the draft illustrated outline and the speaker's profile, produce a comprehensive quality audit report. The illustration coverage check (guardrail #10) should run because the outline has an Illustration Style Anchor section.

## Output Specification

Produce the following file:

1. **`guardrail-report.txt`** — A structured quality audit report covering all check categories including illustration coverage

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/speaker-profile.json ===============
{
  "schema_version": 1,
  "speaker": {"name": "Pat Illustra", "handle": "@patillustra"},
  "rhetoric_defaults": {
    "default_duration_minutes": 45,
    "modular_design": true,
    "three_part_close": true,
    "on_slide_profanity": "never_default"
  },
  "design_rules": {
    "footer": {"always_present": true, "pattern": "@patillustra | #{conference} | #{topic} | pat.dev"},
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

=============== FILE: inputs/draft-outline.md ===============
# Observability Beyond Dashboards

**Spec:** Provocateur | 45 min | KubeCon EU | SRE practitioners
**Slide budget:** 70 slides

---

## Illustration Style Anchor

All generated illustrations use the **blueprint schematic** style. Prefix every image prompt with the appropriate anchor below.

**Model:** `gemini-2.0-flash-preview-image-generation`

### STYLE ANCHOR (FULL — Landscape 1920x1080)
> Detailed architectural blueprint on dark blue background. White and cyan line drawings with precise technical annotations. Grid overlay. Engineering stamp in corner: "APPROVED FOR PRODUCTION." Monospace labels. ISO standard drawing conventions.

### STYLE ANCHOR (IMG+TXT — Portrait 1024x1536)
> Blueprint schematic panel on dark blue background. White line drawing occupying upper 60% of frame. Technical annotations in cyan monospace. Grid overlay. Clean separation between illustration and text area below.

### Conventions
- Sequential drawing numbering: "DWG-001", "DWG-002", etc.
- Recurring "system health meter" gauge fills from empty to full across the talk
- All annotations use monospace UPPERCASE labels
- Engineering approval stamp rotates: "DRAFT", "UNDER REVIEW", "APPROVED"

---

## Opening Sequence [3 min, slides 1-5]

### Slide 1: Title Slide
- Format: **FULL**
- Illustration: Blueprint title card with the talk title
- Image prompt: `[STYLE ANCHOR]. Architectural title block. "OBSERVABILITY BEYOND DASHBOARDS" in large monospace. Drawing number DWG-001. Date field, revision field, engineer field. Stamp: DRAFT.`
- Speaker: (no notes)

### Slide 2: Opening Hook — The Dashboard Graveyard
- Format: **FULL**
- Illustration: Rows of abandoned monitoring dashboards
- Image prompt: `[STYLE ANCHOR]. Blueprint elevation view of a server room. DWG-002. Rows of monitoring screens, each showing flatlined graphs labeled "LAST VIEWED: 18 MONTHS AGO." Cobwebs drawn in precise technical pen style. Callout: "FIG. A — THE DASHBOARD GRAVEYARD."`
- Speaker: "Raise your hand if you have more than 50 dashboards in your Grafana instance. Now keep it up if you looked at more than 5 of them this week."

### Slide 3: Brief Bio
- Format: **EXCEPTION** — bio slide with real headshot
- Visual: Pat Illustra, SRE Lead at ObservaCo
- Speaker: "Quick intro — I break things for a living and then blame the dashboards."

### Slide 4: Shownotes URL
- Format: **EXCEPTION**
- Visual: pat.dev/observability-beyond + QR code
- Speaker: "Everything's here — grab it now."

### Slide 5: Bold Claim
- Format: **FULL**
- Illustration: A dashboard being crossed out with a red X
- Image prompt: `[STYLE ANCHOR]. DWG-003. Technical cross-section of a monitoring dashboard with large "REJECTED" stamp overlay in red ink. Callout labels: "VANITY METRICS", "UNUSED ALERTS", "COPY-PASTED QUERIES." Engineering note: "SEE REPLACEMENT SPEC DWG-015."`
- Speaker: "Dashboards are not observability. Full stop."

## Act 1: The Problem [18 min, slides 6-28]

### Slide 6: The Monitoring Trap
- Format: **FULL**
- Illustration: Engineers trapped inside a cage of dashboard screens
- Image prompt: `Rows of engineers surrounded by screens showing graphs. Some screens cracked. Labels pointing to issues.`
- Speaker: "okay so let me paint the picture"

### Slide 7: Survey Data — Dashboard Fatigue
- Format: **IMG+TXT**
- Illustration: Gauge showing "dashboard fatigue" at critical levels
- Image prompt: `[STYLE ANCHOR]. DWG-005. System health gauge labeled "DASHBOARD FATIGUE INDEX." Needle in the red zone. Scale from "MANAGEABLE" to "CRITICAL OVERLOAD." Monospace annotation: "87% OF SRES REPORT ALERT FATIGUE."`
- Speaker: "87% of SREs report alert fatigue — but nobody cites a source for that number apparently"

### Slide 8: The Tool Sprawl
- Illustration: Explosion diagram of observability tools
- Image prompt: `[STYLE ANCHOR]. DWG-006. Exploded view of an observability stack. Components: Prometheus, Grafana, Datadog, PagerDuty, Jaeger flying apart. Leader lines to each. Label: "TYPICAL ENTERPRISE OBSERVABILITY STACK (SIMPLIFIED)."`
- Speaker: "And the tools keep multiplying"

### Slide 9: Real Incident Screenshot
- Format: **EXCEPTION**
- Visual: Actual PagerDuty screenshot showing 47 alerts in 10 minutes
- Speaker: "This is from last Tuesday. 47 alerts. 10 minutes. One actual problem."

### Slide 10-15: The Alert Storm
- Format: **FULL**
- Illustration: Progressive views of alerts multiplying across systems
- Image prompt: `[STYLE ANCHOR]. DWG-007 through DWG-012. Progressive blueprint sequence showing alert propagation across a distributed system. Each drawing adds more alert indicators.`

### Slide 16: The Cost
- Format: **FULL**
- Illustration: Cost diagram of observability tool spend
- Image prompt: `[STYLE ANCHOR]. DWG-013. Financial schematic: "ANNUAL OBSERVABILITY EXPENDITURE." Stacked bar chart in blueprint style. Sections: TOOLING LICENSE ($450K), STORAGE ($280K), ENGINEER TIME WASTED ($1.2M — largest). Callout: "THE HIDDEN COST IS ALWAYS PEOPLE."`

### Slide 17-22: Case Studies — What Went Wrong
- Format: **IMG+TXT**
- Illustration: Failure mode diagrams for each case study
- Image prompt: `[STYLE ANCHOR]. Failure mode analysis diagrams. Each shows a different anti-pattern.`

### Slide 23-28: The Cultural Problem
- Format: **FULL**
- Illustration: Organizational chart showing observability silos
- Image prompt: `Organizational chart with departments in boxes. Walls between them. Each department has its own monitoring stack.`

## Act 2: The Solution [18 min, slides 29-52]

### Slide 29: The Reframe
- Format: **FULL**
- Illustration: Blueprint revision — old dashboard crossed out, new observability model overlaid
- Image prompt: `[STYLE ANCHOR]. DWG-015. Revision overlay drawing. Old monitoring architecture ghosted/faded. New observability architecture overlaid in bright cyan. Label: "REVISION B — OBSERVABILITY-FIRST ARCHITECTURE." Stamp: "UNDER REVIEW."`

### Slide 30-40: The Framework
- Format: **IMG+TXT**
- Illustration: Each pillar of the observability framework as a structural element
- Image prompt: `[STYLE ANCHOR]. Structural engineering diagrams. Each pillar labeled and load-bearing.`

### Slide 41-46: Live Demo Screenshots
- Format: **EXCEPTION** — real tool screenshots
- Visual: Live demo of the observability platform

### Slide 47-52: Migration Stories
- Format: **FULL**
- Illustration: Before/after blueprints of teams that migrated
- Image prompt: `[STYLE ANCHOR]. Split-view blueprints. Left: "BEFORE" with chaotic monitoring. Right: "AFTER" with clean observability architecture. DWG-020 through DWG-025.`

## Closing Sequence [2 min, slides 53-55]

### Slide 53: Summary
- Format: **FULL**
- Illustration: The system health meter gauge now at "OPTIMAL"
- Image prompt: `[STYLE ANCHOR]. DWG-026. System health gauge from slide 7 callback — needle now at "OPTIMAL." Stamp: "APPROVED FOR PRODUCTION." Three summary items as engineering specifications.`
- Speaker: "so to wrap up fast..."

### Slide 54: CTA
- Format: **FULL**
- Illustration: Action items as engineering work orders
- Image prompt: `[STYLE ANCHOR]. DWG-027. Engineering work order form. Three action items as line items.`

### Slide 55: Thanks + Social
- Format: **EXCEPTION** — social handles and shownotes URL
- Visual: @patillustra | pat.dev/observability-beyond
=============== END OF FILE ===============

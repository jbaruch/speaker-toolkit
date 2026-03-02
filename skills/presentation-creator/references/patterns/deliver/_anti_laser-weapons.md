---
id: laser-weapons
name: Laser Weapons
type: antipattern
part: deliver
phase_relevance:
  - guardrails
  - slides
vault_dimensions: [13, 14]
detection_signals:
  - "bouncing laser dot"
  - "reliance on pointer for navigation"
  - "slides requiring external highlighting"
related_patterns: [traveling-highlights, lightsaber]
inverse_of: [traveling-highlights]
difficulty: foundational
observable: false
---

# Laser Weapons

## Summary
Laser pointers are a crutch for identifying content that should instead be emphasized with Traveling Highlights or built-in animations. The bouncing dot distracts, and the dependence on external tools signals poor slide design.

## The Pattern in Detail
The laser pointer seems like a reasonable tool: you point at something on the screen, the audience looks where you point. In practice, laser pointers in presentations are almost universally problematic. The red (or green) dot bounces and jitters as your hand trembles from adrenaline, caffeine, or simple human motor imprecision. The audience tracks the bouncing dot rather than absorbing the content it is supposed to highlight. When the speaker moves the pointer rapidly from one element to another, the audience's eyes chase the dot like a cat chasing a laser toy — engaging but not enlightening.

The deeper problem is what laser pointer dependence reveals about slide design. If you need a laser pointer to direct audience attention to the right part of a slide, your slide is too complex. A well-designed slide directs attention through visual hierarchy, contrast, color, and animation. The Traveling Highlights pattern provides the correct approach: build your slides so that the currently relevant element is visually prominent while other elements are dimmed or hidden. This is more work during slide creation but dramatically more effective during delivery because the highlighting is pixel-perfect, consistent, and independent of your hand steadiness.

The laser pointer also tethers you to a specific physical relationship with the screen. You need line of sight to the screen, and the audience needs to track between you (the voice) and the screen (the dot), which splits their attention. Traveling Highlights eliminate this split because the slide itself provides the emphasis — the audience looks at the screen and sees what is important without any external assistance.

Some speakers use laser pointers as a presentation crutch in a more general sense: the pointer gives their hands something to do, provides a sense of control, and serves as a physical security blanket similar to the Bunker antipattern's podium. If this resonates, address the underlying anxiety (Shoeless pattern) rather than the surface symptom.

The only acceptable use of a laser pointer is the controlled Lightsaber variant — rare, deliberate, purposeful highlighting of a specific element that genuinely cannot be handled through slide design. But even this exception should trigger the question: "Could I redesign this slide to not need a pointer?" The answer is almost always yes.

## When to Use / When to Avoid
This is an antipattern to avoid entirely in the vast majority of presentations. Replace laser pointer dependence with Traveling Highlights, animations, and good visual design. If you find yourself reaching for the laser pointer regularly, treat it as a symptom that your slides need redesign, not as a tool that solves the problem. The Lightsaber pattern describes the narrow exception where brief, controlled pointer use is justified.

## Detection Heuristics
- Laser dot visible on screen frequently or continuously during the presentation
- Dot bounces or jitters, distracting from content
- Speaker uses the pointer to navigate between slide elements rather than using built-in highlighting
- Slides are complex enough to require external attention-direction tools

## Scoring Criteria
- Strong signal (2 pts): No laser pointer used — slides are designed with built-in visual emphasis (Traveling Highlights), attention flows naturally without external tools
- Moderate signal (1 pt): Laser pointer used occasionally but slides mostly self-direct attention
- Absent (0 pts): Heavy laser pointer reliance throughout the talk, bouncing dot is a constant visual element, slides clearly need external highlighting to be understood

## Relationship to Vault Dimensions
This antipattern maps to Vault Dimension 13 (Visual Design Quality) because laser pointer dependence reveals poor visual hierarchy in slide design, and to Vault Dimension 14 (Speaker Craft / Professionalism) because the bouncing dot and pointer dependence signal amateur delivery technique.

## Combinatorics
Laser Weapons is the direct inverse of Traveling Highlights, which provides the correct alternative. The Lightsaber pattern describes the narrow acceptable use case. The Weatherman pattern reduces pointer dependence by providing presenter-view-based navigation. Carnegie Hall rehearsal should specifically include testing whether any slides require a pointer and redesigning those that do.

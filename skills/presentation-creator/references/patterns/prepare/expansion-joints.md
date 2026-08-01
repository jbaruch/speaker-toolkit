---
id: expansion-joints
name: Expansion Joints
type: pattern
part: prepare
phase_relevance:
  - architecture
  - content
vault_dimensions: [2, 12]
evidence_channels: [slides, slide_sequence, video]
detection_signals:
  - "modular content sections"
  - "cut lines present"
  - "expandable digressions marked"
  - "graceful skip points"
evaluable_from:
  - static_slides
  - native_deck
  - delivery_video
strong_evaluable_from:
  - delivery_video
absence_evaluable_from: null
not_applicable_when:
  - condition_id: short-talk-at-most-20-minutes
    description: "Complete delivery video establishes that the presentation lasts no more than 20 minutes, where the catalog says Expansion Joints should be avoided."
applicability_evaluable_from:
  - delivery_video
evidence_requirements:
  - "A visual positive finding must locate a genuine modular boundary or cut line whose removal preserves the surrounding narrative; a titled section or optional-looking appendix alone does not prove flexibility."
  - "A strong finding requires delivery video showing an actual expansion or contraction under an observable timing change and a complete narrative after that adaptation."
not_evaluable_when:
  - "Only a modular-looking deck is available without evidence that a section can be skipped or expanded without breaking dependencies."
  - "For a talk longer than 20 minutes, the recording does not expose a timing perturbation or the relevant transition and therefore cannot establish strong adaptation or a negative outcome."
related_patterns: [talklet, narrative-arc]
inverse_of: [shortchanged]
difficulty: intermediate
---

# Expansion Joints

## Summary
Include material that can expand or contract depending on time constraints and audience interaction levels.

## The Pattern in Detail
Live presentations are inherently unpredictable. Questions from the audience, technical difficulties, a preceding speaker running long, or an unexpectedly engaged audience that wants to explore a topic deeper — all of these can throw your carefully planned timeline into disarray. Expansion Joints are sections of your presentation deliberately designed to accommodate these fluctuations, expanding when you have extra time and contracting when you are running short.

There are two types of Expansion Joints: Implicit and Explicit. An Implicit Expansion Joint is a slide or short sequence that you can either discuss in depth or skip entirely without disrupting the narrative flow. For example, a case study slide that reinforces a point already made — if time permits, you walk through it; if not, you move on and the audience never knows it existed. The key is that skipping the material does not create a visible gap or leave the audience confused about what they missed.

An Explicit Expansion Joint is a more substantial digression — a set of slides with their own mini Narrative Arc that branches off from the main flow and returns to it. These are clearly optional explorations that enrich the presentation when time allows but can be cleanly omitted when it does not. An explicit joint might be a deep dive into a specific implementation detail, a historical context section, or an advanced variant of the technique being presented. The important thing is that each explicit joint is self-contained: it has its own beginning, middle, and end, so it feels complete if included and invisible if excluded.

Practicing with Expansion Joints is essential. You must rehearse both the "expanded" and "contracted" versions of your talk so that skipping material feels natural rather than panicked. A speaker who suddenly jumps from slide 23 to slide 31 while muttering "we'll skip this part" undermines audience confidence. A speaker who seamlessly flows from slide 23 to slide 31 because the transition was designed to work both ways demonstrates mastery.

Martin Fowler famously uses Expansion Joints as a safety net against a different problem: having too little material. Rather than worrying about running short, he builds in enough expandable sections to guarantee he can fill any time slot. This inverts the usual anxiety — instead of "will I have enough material?" the question becomes "which of my extra material will I choose to include?" This is a far more comfortable position to present from.

## When to Use / When to Avoid
Use Expansion Joints in any presentation over 20 minutes, especially when the time slot is uncertain or when audience interaction is expected. They are essential for talks that may be adapted to different time slots. Avoid over-relying on Expansion Joints to the point where your "core" presentation is too thin — the contracted version must still be complete and satisfying.

## Detection Heuristics
The vault should look for evidence of modular content design: sections that can be included or excluded without disrupting flow, clear cut lines between segments, and the kind of flexible time management that suggests the speaker prepared more material than strictly necessary.

## Scoring Criteria
- Strong signal: Presentation handles time fluctuations gracefully; speaker can expand or contract sections without visible disruption; content feels complete at any length
- Moderate signal: Some flexibility evident but transitions are occasionally rough when material is skipped; time management is adequate but not elegant
- Absent: Presentation is rigidly sequential with no apparent flexibility; speaker is visibly rushed or has obvious filler when time estimates miss

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`.

## Relationship to Vault Dimensions
Relates to Dimension 2 (Structure/Organization). Relates to Dimension 12 (Time/Pacing).

## Combinatorics
Pairs with Talklet (modular 20-minute units are natural expansion joints), Narrative Arc (joints must work within the arc, not break it). The inverse is Shortchanged — a talk that runs short because it lacks expandable material to fill the time appropriately.

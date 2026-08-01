---
id: talklet
name: Talklet
type: pattern
part: prepare
phase_relevance:
  - architecture
  - content
vault_dimensions: [2, 12]
evidence_channels: [timed_transcript, slides, video]
detection_signals:
  - "self-contained 20-minute modules"
  - "modular structure"
  - "sections can stand alone"
  - "flexible time management"
evaluable_from:
  - transcript
  - static_slides
  - native_deck
  - delivery_video
strong_evaluable_from:
  - transcript
  - delivery_video
absence_evaluable_from: null
not_applicable_when:
  - condition_id: short-talk-at-most-30-minutes
    description: "Complete delivery video establishes that the presentation lasts no more than 30 minutes, where the catalog says Talklet module overhead exceeds the benefit."
  - condition_id: cumulative-prerequisite-chain
    description: "Complete delivery video establishes that the subject matter is a cumulative procedure or prerequisite chain in which each section consumes concepts or results introduced immediately before it, so sections cannot be independently removed or reordered."
applicability_evaluable_from:
  - delivery_video
evidence_requirements:
  - "A positive finding must locate module boundaries and show that each cited section has its own contextual opening, body, and close; three titled sections alone do not establish Talklets."
  - "A strong finding requires a complete timed spoken record showing approximately 20-minute modules with limited cross-module dependencies, so structural reorderability follows from observable self-containment rather than an imagined alternate delivery."
not_evaluable_when:
  - "The source is untimed, incomplete, or does not preserve section order and dependencies."
  - "Only slide titles or visual dividers are available without the spoken arcs needed to establish that modules stand alone."
  - "The complete delivery is unavailable, so duration and cumulative-prerequisite applicability conditions cannot both be assessed."
related_patterns: [narrative-arc, foreshadowing, backtracking, a-la-carte-content, expansion-joints]
inverse_of: []
difficulty: intermediate
---

# Talklet

## Summary
Build a larger presentation from small, self-contained 20-minute units, allowing flexible time management.

## The Pattern in Detail
Psychological research consistently shows that the average adult attention span for sustained focus on a single topic is approximately 20 minutes. After that, engagement drops sharply unless something changes — the topic, the format, the energy level. The Talklet pattern works with this biological reality rather than against it by structuring presentations as a series of self-contained 20-minute modules, each of which stands on its own as a complete mini-presentation.

The practical power of the Talklet becomes apparent when you face the dreaded request: "Can you do your 90-minute talk in 45 minutes?" The naive response is to speed up the entire presentation, compressing every section equally. This fails. Presentations are NOT fractal and do not scale uniformly. Some sections require a minimum amount of time to be comprehensible, while others can be shortened without loss. A Talklet-structured presentation handles this gracefully: you deliver two talklets instead of four, or three instead of five, and each delivered talklet is complete and satisfying at full depth.

For Talklets to work, the modules must be mostly orthogonal — each one covers a distinct topic that does not depend heavily on material from other talklets. A talklet about "Why Microservices" and a talklet about "Microservice Deployment Patterns" can stand alone; a talklet about "Advanced Query Optimization" cannot stand alone if it assumes the audience sat through "Query Optimization Basics." When topics have dependencies, the dependent talklets must be delivered in order, but independent ones can be rearranged or dropped.

The Talklet pattern works especially well with A la Carte Content, where you offer the audience a choice of which talklets to hear. "I have four modules prepared — let's vote on which three we cover." This transforms the audience from passive recipients into active participants in shaping their experience. It also provides a natural safety valve for time management and a powerful engagement technique.

Building Talklets requires discipline during the design phase. Each module needs its own opening (to establish context), body (to deliver content), and closing (to consolidate learning). Transitions between talklets should acknowledge the shift: "That completes our exploration of X. Now let's turn to a different but related question: Y." The Foreshadowing and Backtracking patterns help connect talklets into a larger whole — foreshadowing upcoming modules from earlier ones, and referencing earlier modules from later ones.

## When to Use / When to Avoid
Use the Talklet pattern for any presentation over 30 minutes, especially if you expect to deliver variants of the talk at different time slots. It is ideal for topics with multiple semi-independent subtopics. Avoid for short talks where the overhead of self-contained modules exceeds the benefit, and for topics that are inherently sequential with deep dependencies between sections — some material simply cannot be modularized.

## Detection Heuristics
The vault should look for evidence of modular construction: self-contained sections of approximately 20 minutes each, clear module boundaries with explicit transitions, and sections that appear to function independently rather than depending on sequential consumption.

## Scoring Criteria
- Strong signal: Clearly modular structure with ~20-minute self-contained units; each module has its own arc; modules could be reordered or dropped without breaking the presentation
- Moderate signal: Some modularity evident but modules are not fully self-contained; dependencies between sections limit flexibility
- Absent: No modular structure; content is monolithic and cannot be shortened without uniform compression

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`.

## Relationship to Vault Dimensions
Relates to Dimension 2 (Structure/Organization). Relates to Dimension 12 (Time/Pacing).

## Combinatorics
Pairs with Narrative Arc (each talklet has its own mini-arc, and the collection has an overall arc), Foreshadowing and Backtracking (connecting modules into a larger whole), A la Carte Content (audience choice among talklets), and Expansion Joints (talklets can serve as large-scale expansion joints).

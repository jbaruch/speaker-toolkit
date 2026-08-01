---
id: narrative-arc
name: Narrative Arc
type: pattern
part: prepare
phase_relevance:
  - intent
  - architecture
  - content
vault_dimensions: [2, 5]
evidence_channels: [transcript, timed_transcript, slides, slide_sequence, video]
detection_signals:
  - "clear three-act structure"
  - "problem-solution arc"
  - "throughline maintained"
  - "rising tension toward resolution"
evaluable_from:
  - transcript
  - static_slides
  - native_deck
  - delivery_video
strong_evaluable_from:
  - transcript
  - delivery_video
absence_evaluable_from: null
evidence_requirements:
  - "A positive finding must use complete ordered talk structure and locate the throughline, tension, and resolution across sections rather than mistaking one local anecdote for the presentation's arc."
  - "A strong finding requires the complete spoken delivery; current artifacts do not authorize absence."
not_evaluable_when:
  - "Only an excerpt, outline fragment, or selected slide sequence is available without the opening-to-close order."
  - "The transcript or recording is incomplete, or a transcript/deck pair cannot be aligned well enough to determine whether the talk resolves its central tension."
related_patterns: [triad, bookends, intermezzi, unifying-visual-theme, context-keeper]
inverse_of: [lipstick-on-a-pig, celery]
difficulty: foundational
---

# Narrative Arc

## Summary
Structure your presentation as a story with beginning, middle, and end — leveraging humanity's innate feel for how stories work.

## The Pattern in Detail
A narrative arc describes rising and falling tension through conflict and resolution. Humans are hardwired for stories — we have been telling them around campfires for millennia, and our brains are optimized to follow, remember, and retell narrative structures. A presentation that harnesses this innate wiring has a profound advantage over one that merely lists facts or demonstrates features.

The structure is deceptively simple: beginning, middle, and end. The beginning establishes context, introduces the problem or question, and gives the audience a reason to care. The middle escalates tension through complications, explores alternatives, and builds toward a climax. The end resolves the tension, delivers the payoff, and leaves the audience with a clear takeaway. This structure applies to every kind of presentation — not just storytelling talks. Even a product demo can follow a narrative arc: set up the differentiators that matter, show how competitors fall short (conflict), and finish with your product's strengths (resolution).

Discovering the narrative arc is often the hardest part of building a presentation. The raw material — your knowledge, your data, your experience — does not arrive pre-organized into a story. You must find the story within the material. One effective technique is to think in threes (the Triad pattern): three problems, three solutions, three insights. Another is to create flowchart-like views of your problem/solution structure, where each solution creates the conditions for the next problem. This chain of problem-solution-new-problem creates natural rising tension.

The narrative arc also provides a crucial coherence function. Every slide, every demo, every aside should serve the arc. If a piece of content does not advance the story, it either needs to be reframed so it does, or it needs to be cut. This is painful — speakers often love their tangential material — but ruthless adherence to the arc is what separates a memorable presentation from a forgettable one. The story creates shared context between speaker and audience, giving everyone a mental framework to organize new information as it arrives.

A common mistake is to have a strong beginning, a rich middle, and then run out of time for the ending. The resolution is not optional — it is the payoff for everything that came before. Plan your time so that the ending receives the attention it deserves. An unresolved narrative arc leaves the audience unsatisfied even if every individual slide was excellent.

## When to Use / When to Avoid
Use this pattern for virtually every presentation. Even talks that seem purely informational benefit from narrative structure. Avoid forcing a dramatic arc onto material that genuinely does not have one — not every status update needs a villain — but even straightforward material benefits from a clear beginning-middle-end structure.

## Detection Heuristics
The vault should look for evidence of intentional narrative structure. A clear throughline from problem to resolution, rising tension through the middle sections, and a satisfying conclusion are strong indicators. Random-seeming topic jumps and abrupt endings suggest the absence of a narrative arc.

## Scoring Criteria
- Strong signal: Clear three-act structure; throughline maintained from opening to close; rising tension with satisfying resolution; every section serves the arc
- Moderate signal: Some narrative structure present but inconsistent; beginning and end exist but middle meanders; throughline partially maintained
- Absent: No discernible narrative structure; slides feel like a random collection; no resolution or payoff

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`.

## Relationship to Vault Dimensions
Relates to Dimension 2 (Structure/Organization) as the primary structural pattern for presentations. Relates to Dimension 5 (Storytelling/Narrative) directly — this pattern IS the narrative dimension.

## Combinatorics
Pairs powerfully with Triad (three-act structure maps to three main themes), Bookends (opening and closing that frame the arc), Intermezzi (transitions between arc sections), Unifying Visual Theme (visual coherence reinforces narrative coherence), and Context Keeper (maintaining audience orientation within the arc). The Narrative Arc is arguably the most foundational pattern — nearly every other pattern either supports it or depends on it.

## Related Reading
- Reynolds, G. (2012). *Presentation Zen: Simple Ideas on Presentation Design and Delivery* (2nd ed.). Ch. 4 — "Crafting the Story" applies Robert McKee's conflict-driven story structure to presentations, and cites the Heath brothers' SUCCESs framework. New Riders.
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Ch. 2, 4, 6 — derives presentations' two-turning-point shape from Aristotle's three-act, Syd Field's Paradigm, and Vogler's Hero's Journey; the *sparkline* form is a persuasion-specific narrative arc with named turning points (Call to Adventure, Call to Action) and a "new bliss" close. Wiley.

---
id: coda
name: Coda
type: pattern
part: build
phase_relevance:
  - content
  - slides
vault_dimensions: [8, 13]
evidence_channels: [transcript, slides, slide_sequence, video]
detection_signals:
  - "reference slides at end"
  - "bibliography or resource list"
  - "further reading section"
evaluable_from:
  - [static_slides, transcript]
  - [native_deck, transcript]
strong_evaluable_from:
  - [static_slides, transcript]
  - [native_deck, transcript]
absence_evaluable_from: null
not_applicable_when:
  - condition_id: no-external-resources-cited
    description: "A complete transcript paired with the complete rendered or native deck establishes that the spoken and body material independently uses or cites no external resources, research, tools, or further reading that a Coda could collect."
applicability_evaluable_from:
  - [static_slides, transcript]
  - [native_deck, transcript]
evidence_requirements:
  - "Evidence must show supplementary deck material after, and separate from, the spoken conclusion."
  - "Evidence must expose the existing scoring cues: reference material appears after, and remains separate from, the spoken conclusion."
not_evaluable_when:
  - "Only a deck is available without a transcript that locates the spoken conclusion."
  - "Only delivery video or transcript is available without an inspectable authored deck showing the post-spoken material."
  - "The complete speech-and-deck inventory is unavailable, so the no-external-resources applicability condition cannot be assessed."
related_patterns: [infodeck, vacation-photos]
inverse_of: []
difficulty: foundational
---

# Coda

## Summary
Place further reading, references, and supplementary materials at the end of your slide deck, after your spoken content, providing a concluding piece that supplies reference material not delivered in the spoken portion.

## The Pattern in Detail
The Coda is the concluding section of your presentation that exists after your last spoken slide. It is a collection of reference slides, further reading lists, bibliographies, resource links, and supplementary materials that your audience can consume at their leisure after the talk. The term is borrowed from music, where a coda is a concluding passage that brings a piece to a satisfying close. In the context of presentations, the Coda serves a similar purpose: it wraps up the experience by giving the audience a structured place to go deeper.

One of the most common mistakes presenters make is trying to embed references, URLs, and citations inline within their spoken slides. This creates a disruptive experience because the audience tries to write down URLs or read citation details instead of listening to what you are saying. By contrast, when you promise "all references are at the end," the audience relaxes and focuses on your narrative. You have given them permission to pay attention now and look things up later.

The Coda is also one of the few places in a presentation where bullet points are genuinely acceptable. This section is designed for solo consumption after the fact, whether the audience is reviewing a shared PDF of your deck or flipping through slides they photographed. The rules about avoiding dense text and bullet points are relaxed. In fact, bullet points are preferable here. They make reference material scannable.

A well-constructed Coda typically includes: a "Further Reading" slide with book titles and authors, a "Resources" slide with links to tools, libraries, or frameworks mentioned, a "Bibliography" or "References" slide for academic or research citations, and optionally a "Contact" slide with your social handles and website. Some speakers also include bonus content or appendix slides that expand on topics they only touched on briefly during the talk.

The key discipline is keeping the Coda firmly separated from the spoken portion of the talk. Your last spoken slide should be your conclusion or call to action, and everything after that is clearly marked as reference material. This separation preserves the Narrative Arc of your spoken presentation while still providing the depth that serious audience members crave.

## When to Use / When to Avoid
Use the Coda pattern in virtually every presentation that references external resources, research, tools, or further reading. It is especially valuable in technical talks, conference presentations, and academic lectures where the audience expects to be able to follow up on the material.

Avoid relying on the Coda as a dumping ground for slides you cut from the main talk. The Coda is for reference material, not for content you could not fit in. If you have substantive content that did not make the cut, either restructure your talk to include it or save it for a different presentation.

## Detection Heuristics
When scoring talks, look for a clear demarcation point between the spoken conclusion and supplementary material. Reference slides should appear after the final narrative slide. The presence of a "Further Reading," "Resources," or "References" section at the end of a deck is a strong positive signal. Conversely, URLs and citations scattered throughout the body of the talk indicate the absence of this pattern.

## Scoring Criteria
- Strong signal: Clear reference/bibliography section at end of deck, separated from spoken content, with organized further reading materials
- Moderate signal: Some references collected at end but mixed with spoken content, or references present but unorganized
- Absent: No reference section, or references scattered inline throughout the presentation

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`.

## Relationship to Vault Dimensions
Dimension 8 (Information Density): manages information density across the spoken portion and the reference section. Dimension 13 (Slide Design): a deck-structure decision about what belongs in the spoken flow versus reference material.

## Combinatorics
The Coda pairs naturally with the Infodeck pattern, as both deal with content designed for solo consumption. It works well alongside Vacation Photos. Image-heavy spoken slides benefit from having a text-rich reference section at the end. The Coda also supports Narrative Arc by keeping disruptive reference material out of the story flow.

## Related Reading
- Reynolds, G. (2012). *Presentation Zen: Simple Ideas on Presentation Design and Delivery* (2nd ed.). Ch. 10 — "Save the best for last," exemplified by Steve Jobs's "one more thing" closing slide. New Riders.

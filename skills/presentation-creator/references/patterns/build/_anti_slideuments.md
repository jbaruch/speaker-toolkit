---
id: slideuments
name: Slideuments
type: antipattern
part: build
phase_relevance:
  - guardrails
vault_dimensions: [8, 14]
detection_signals:
  - "dense slides meant to be read"
  - "dual-purpose document/presentation"
  - "no clear presentation vs document separation"
related_patterns: [infodeck, charred-trail, gradual-consistency]
inverse_of: [infodeck]
difficulty: foundational
---

# Slideuments

## Summary
Trying to make one artifact work as both a presentation and a readable document produces something bad at both — a term coined by Garr Reynolds to describe the worst of both worlds.

## The Pattern in Detail
Slideuments is the antipattern of attempting to create a single slide deck that serves dual duty as both a live presentation and a standalone readable document. The term was coined by Garr Reynolds, author of "Presentation Zen," to describe the hybrid monster that results: slides that are too text-heavy to work as visual aids during a live talk, yet too fragmented and context-dependent to work as a self-contained document. The Slideument fails at both of its intended purposes, satisfying neither the audience in the room nor the reader at their desk.

The root cause of Slideuments is an understandable efficiency impulse. Creating a presentation takes time. Creating a document takes time. Creating both takes twice as much time. The Slideument promises a shortcut: create one artifact that serves both needs. But this shortcut is an illusion, because the design requirements of presentations and documents are fundamentally opposed. A good presentation slide uses large images, minimal text, and relies on the speaker to provide context and detail. A good document page uses dense text, complete sentences, and must be self-explanatory without a speaker. There is no sweet spot that satisfies both requirements — any compromise tilts toward one format at the expense of the other.

The typical Slideument manifests as slides packed with complete sentences and detailed paragraphs — more text than a presentation slide should have, but less context than a standalone document needs. The presenter reads from these dense slides during the talk (creating a Bullet-Riddled Corpse experience for the live audience), and the document reader struggles through slides that assume knowledge of what the presenter said between and around the bullet points (creating a frustrating reading experience). Both audiences are underserved, and the creator has actually spent MORE effort managing the impossible compromise than they would have spent creating two purpose-built artifacts.

The professional solution to the Slideuments problem is to embrace the separation of concerns. Create two artifacts: a presentation deck optimized for live delivery (visual, sparse, speaker-dependent) and a document optimized for solo reading (textual, comprehensive, self-contained). If creating two artifacts from scratch is not feasible, there is a practical workaround: create your presentation deck in the visual, sparse style appropriate for live delivery, but add comprehensive speaker notes to each slide. When distributing the deck afterward, export it as a PDF with speaker notes visible. The audience gets a readable document (the speaker notes) alongside visual reference points (the slides), which approximates the experience of attending the talk in person.

Another approach is to create the presentation first, deliver it, and then write a blog post or article that covers the same material in document form. This "presentation-first, document-second" workflow ensures that neither artifact is compromised by trying to serve the other's purpose. Some speakers go further and create an Infodeck — a separate, self-contained slide deck designed specifically for reading — that covers the same content as the live presentation but with document-appropriate information density. The key insight is that the two formats serve different audiences with different needs, and any attempt to merge them produces an artifact that serves no audience well.

## When to Use / When to Avoid
This is an antipattern and should always be avoided. Never attempt to make a single slide deck serve as both a live presentation and a standalone document. Instead, create separate artifacts for each purpose, or use the speaker notes workaround to provide document-like content alongside presentation-style slides.

If organizational pressure demands a single artifact (a common corporate scenario), use the speaker notes approach: visual slides for the live presentation with comprehensive speaker notes that make the PDF export self-contained. This is the closest you can get to serving both audiences without compromising either one.

## Detection Heuristics
When scoring talks, look for slides that contain complete sentences or full paragraphs — indicators that the slides were designed to be read without a presenter. Also look for the inverse: moments where a distributed slide deck is incomprehensible without the speaker's verbal context, suggesting it was designed for live delivery but distributed as a document. The clearest signal is a deck that feels too dense for presenting but too sparse for reading.

## Scoring Criteria
- Strong signal (2 pts): Clear separation between presentation and document artifacts, or slides with comprehensive speaker notes that serve as the document layer while keeping slides visual and sparse
- Moderate signal (1 pt): Some Slideument tendencies — slides that are slightly too text-heavy for presentation but have enough context to be somewhat readable standalone
- Absent (0 pts): Classic Slideument behavior — dense text slides used for both presenting and distributing, no speaker notes, no separate document, both audiences poorly served

## Relationship to Vault Dimensions
Dimension 8 (Slide Design): Slideuments represent a fundamental design failure born from trying to satisfy incompatible design requirements in a single artifact, resulting in compromised design for both purposes. Dimension 14 (Overall Quality Indicators): The presence of Slideument behavior is a strong negative quality signal, indicating that the presenter has not thought carefully about audience needs and artifact purposes.

## Combinatorics
Slideuments is the inverse of the Infodeck pattern — where an Infodeck is deliberately designed for reading (embracing document characteristics), a Slideument accidentally tries to be both and fails at both. It relates to the Charred Trail pattern (leaving a trail of content for after-the-fact consumption) and Gradual Consistency (building coherent artifacts over time). The Bullet-Riddled Corpse antipattern often appears within Slideuments, as the dual-purpose compromise tends to produce bullet-heavy slides.

## Related Reading
- Reynolds, G. (2012). *Presentation Zen: Simple Ideas on Presentation Design and Delivery* (2nd ed.). Ch. 3 — Reynolds coined the term "slideument" and dedicates the "Create a Document, Not a Slideument" section to this antipattern. New Riders.
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Ch. 2 — uses the term "slideument" explicitly: "Documents masquerade as presentations, and these *slideuments* have become the lingua franca of many organizations." Reports should be distributed; presentations should be presented. Wiley.

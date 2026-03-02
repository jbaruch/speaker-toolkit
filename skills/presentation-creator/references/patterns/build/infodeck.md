---
id: infodeck
name: Infodeck
type: pattern
part: build
phase_relevance:
  - architecture
vault_dimensions: [8]
detection_signals:
  - "self-contained document format"
  - "dense information without animations"
  - "designed for reading not presenting"
related_patterns: [coda]
inverse_of: [slideuments]
difficulty: intermediate
---

# Infodeck

## Summary
A document created with presentation tools intended for distribution and solo consumption — never projected before an audience — serving as a standalone reference artifact.

## The Pattern in Detail
The Infodeck is a presentation-tool artifact that is emphatically NOT a presentation. It is a document created in Keynote, PowerPoint, or Google Slides that is designed to be read by an individual, never projected before an audience. The distinction is critical because it liberates the creator from the constraints of live presentation — no need for animations, transitions, large fonts, or sparse text — while preserving the unique advantages that presentation tools offer over traditional word processors and page-layout applications.

Those advantages are substantial. First, presentation tools enforce a spatial layout discipline that word processors do not. Each "slide" is a fixed-size canvas, which encourages visual thinking about information placement, hierarchy, and grouping. Second, the canvas constraint discourages the long, meandering prose that word processors enable. When you have a finite spatial budget, you are forced to distill ideas to their essence. Third, presentation tools make it trivially easy to include diagrams, charts, images, and other visual elements inline with text — far easier than the typical word processor workflow of inserting and wrapping figures.

The Infodeck is the natural format for technical design documents, architectural overviews, project proposals, and onboarding materials where visual diagrams and spatial layouts are integral to the content. Amazon's famous "six-page memo" culture could arguably be served by Infodecks in contexts where diagrams and data visualizations complement the written narrative. The format is also ideal for creating reference materials that will be shared via email, Slack, or internal wikis — the fixed-canvas format ensures consistent rendering across devices and platforms.

The critical discipline of the Infodeck pattern is to never attempt to present one live. Because Infodecks have no animations, no transitions, and dense text, projecting them before an audience produces a painfully boring experience. The audience reads ahead while the presenter talks, the dense text competes with the speaker's voice, and the lack of animations means there is no temporal dimension to guide attention. If you need to present the same content live, you must create a separate presentation artifact that follows live-presentation patterns like Vacation Photos, Gradual Consistency, and Charred Trail.

The Infodeck is the positive counterpart to the Slideuments antipattern. Where Slideuments try to serve both live presentation and solo reading and fail at both, the Infodeck succeeds at its one purpose by embracing that purpose fully. An Infodeck does not apologize for being dense, text-heavy, or animation-free, because those are features in the context of solo consumption. The key is intentionality: know what you are building and for whom.

## When to Use / When to Avoid
Use the Infodeck format when you need to create a document for distribution and solo reading that benefits from spatial layout, visual elements, and the canvas-based constraint of presentation tools. Technical design documents, project proposals, quarterly reviews distributed before meetings, and reference guides are all strong candidates.

Avoid the Infodeck format when the document will be presented live. Also avoid it when the content is purely textual with no diagrams or visual elements — in that case, a word processor or markdown document is a better tool. Do not create an Infodeck and then give it to someone else to present, as the lack of animations and temporal structure makes live delivery painful.

## Detection Heuristics
When scoring artifacts (not live presentations), look for dense, self-contained slide decks with substantial text, integrated diagrams, and no animations or transitions. The deck should be comprehensible without any verbal accompaniment. In the context of scoring live presentations, identifying an Infodeck being presented live is a negative signal — it suggests the presenter confused the format.

## Scoring Criteria
- Strong signal (2 pts): Clear separation between presentation artifacts (designed for live delivery) and Infodeck artifacts (designed for solo reading), with appropriate design choices for each
- Moderate signal (1 pt): Some awareness of the distinction, with reference materials separated from live content but not fully optimized for solo consumption
- Absent (0 pts): No distinction between live and distributed formats, or an Infodeck presented live without adaptation

## Relationship to Vault Dimensions
Dimension 8 (Slide Design): The Infodeck pattern directly addresses slide design by establishing that different consumption contexts demand different design approaches. Understanding when to create an Infodeck versus a presentation is a foundational slide design skill.

## Combinatorics
The Infodeck pairs with Coda, as the Coda section of a live presentation can function as a mini-Infodeck — dense reference material appended after the spoken content. Understanding the Infodeck pattern also helps apply the Gradual Consistency pattern correctly: Gradual Consistency is the technique for making an Infodeck's content presentable live by adding temporal build animations.

---
id: breadcrumbs
name: Breadcrumbs
type: pattern
part: build
phase_relevance:
  - content
  - slides
vault_dimensions: [2, 13]
evidence_channels: [slides, slide_sequence, video]
detection_signals:
  - "agenda slides with highlighting"
  - "progress indicators"
  - "topic map showing current position"
evaluable_from:
  - static_slides
  - native_deck
  - delivery_video
strong_evaluable_from:
  - static_slides
  - native_deck
  - delivery_video
absence_evaluable_from: null
not_applicable_when:
  - condition_id: fewer-than-three-major-sections
    description: "A complete delivery video establishes that the delivery itself has fewer than three major sections, where the catalog says Breadcrumb overhead exceeds its value. The deck's own page or section count does not establish this: a talk can be sectioned by demo environment while its deck is one continuous run."
applicability_evaluable_from:
  - delivery_video
evidence_requirements:
  - "Evidence must expose the recurring orientation device across enough of the talk to apply a positive criterion; current artifacts do not authorize an absent outcome."
  - "Evidence must expose the existing scoring cues: strong: recurring three-state progress display; moderate: initial agenda or inconsistent highlighting; absent: no agenda or progress indicator."
not_evaluable_when:
  - "No rendered slides, native deck, or delivery video covers the span in which the orientation device would be visible."
  - "Only a transcript or spoken account is available, or the visual source is too partial for the asserted positive tier; non-detection remains not_evaluable."
  - "No complete delivery video establishes the delivery's section inventory, so the fewer-than-three-sections applicability condition cannot be assessed."
related_patterns: [context-keeper, bookends]
inverse_of: []
difficulty: foundational
---

# Breadcrumbs

## Summary
Create an agenda trail throughout your presentation showing progress, giving the audience a familiar grounding element through a persistent or recurring display that highlights the current section within the overall structure. Whatever the audience is actually looking at can carry it; the deck is the usual carrier, not the required one.

## The Pattern in Detail
Breadcrumbs borrow their name from the fairy tale of Hansel and Gretel, who dropped breadcrumbs to mark their path through the forest. In presentations, Breadcrumbs serve the same navigational purpose: they show the audience where they have been, where they are now, and where they are going. The most common implementation is a visual agenda or topic map that recurs throughout the presentation, with the current section highlighted and completed sections visually marked as finished.

The classic Breadcrumbs implementation uses a horizontal or vertical list of section titles that appears on a dedicated slide before each new section. The current section is highlighted with a distinctive color, bold text, or a visual indicator like an arrow or box. Previous sections are either dimmed, checked off, or marked with a completion indicator. Upcoming sections remain in their default state. This simple three-state visual — completed, current, upcoming — gives the audience an instant snapshot of their position in the talk.

More sophisticated implementations integrate Breadcrumbs into the slide template itself as a persistent element. A thin progress bar at the bottom of every slide, a small topic list in a sidebar, or section-colored accents that change with each new topic can all serve as continuous Breadcrumbs. These persistent implementations have the advantage of providing constant orientation without requiring dedicated agenda slides, but they must be subtle enough not to compete with the slide's primary content.

The carrier does not have to be the deck. A talk that spends most of its runtime in a terminal, an IDE, or a browser can put the trail in whatever is projected instead: a terminal status bar listing the session's windows with the current one highlighted, an IDE tab strip named by section, a whiteboard column ticked off as each topic closes, or a physical prop the speaker advances. A demo-heavy talk whose deck is off-screen for most of its length is precisely the case where a deck-resident trail fails and a carrier on the working surface succeeds. The three-state read — completed, current, upcoming — is what makes it Breadcrumbs; the surface rendering it is an implementation choice.

The mind map variant is a particularly effective Breadcrumbs implementation for presentations with hierarchical or interconnected content. Instead of a linear list, the Breadcrumbs display a visual mind map or concept map showing all topics and their relationships. As the presenter moves through the content, the current node in the map is highlighted, showing not just sequential progress but also how the current topic relates to other topics in the presentation. This approach is more complex to design but provides richer context for audiences trying to build a mental model of the material.

Breadcrumbs serve a dual purpose beyond navigation. They also function as a preview and review mechanism. When a Breadcrumbs slide appears at the start of a new section, the audience briefly reviews everything covered so far (reinforcing retention) and previews everything still to come (building anticipation). This periodic review-and-preview cycle helps the audience consolidate their understanding and maintain engagement throughout long presentations.

## When to Use / When to Avoid
Use Breadcrumbs in any structured presentation with three or more distinct sections. They are especially valuable in educational content, technical tutorials, and business presentations where the audience needs to understand the relationship between sections. Workshops and training sessions benefit enormously from Breadcrumbs. Participants often need to know what has been covered and what is coming.

Avoid Breadcrumbs in narrative-driven presentations where the structure should feel organic rather than outlined. If your talk is a story with a beginning, middle, and end, an explicit agenda overlay can feel clinical and break the narrative immersion. Also avoid them in very short presentations with only one or two sections, where the overhead of Breadcrumbs exceeds their navigational value.

## Detection Heuristics
When scoring talks, look for recurring agenda or progress indicators that show the audience their position within the presentation structure. This can be dedicated agenda slides that reappear between sections, persistent visual elements on every slide, or any recurring mechanism that highlights the current section relative to the whole. Score what the audience could see, not which artifact rendered it: a persistent rail in a projected terminal or editor qualifies on the same terms as a slide-resident one, and a delivery video is the source that shows it.

## Scoring Criteria
- Strong signal: Clear, recurring Breadcrumbs mechanism with three-state visualization (completed, current, upcoming), used consistently throughout the presentation at section transitions
- Moderate signal: An agenda slide shown at the beginning but not revisited, or inconsistent highlighting of current position
- Absent: No agenda, progress indicator, or structural navigation cues visible to the audience

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`. A rendered deck cannot prove the audience had no orientation cue, because the deck is not always what the audience was looking at.

## Relationship to Vault Dimensions
Dimension 2 (Structure and Flow): Breadcrumbs are a direct, explicit revelation of the presentation's structure, making the flow visible and navigable for the audience. Dimension 13 (Visual Polish and Craft): Well-designed Breadcrumbs require thoughtful visual design — color coding, spatial arrangement, and consistent styling — that reflects overall visual craft.

## Combinatorics
Breadcrumbs are a specific implementation of the Context Keeper parent pattern and pair naturally with Bookends, which mark section boundaries that Breadcrumbs track. The two patterns reinforce each other: Bookends provide the structural rhythm and Breadcrumbs provide the navigational awareness. Breadcrumbs also support A La Carte Content by showing which menu items have been covered in an audience-directed flow.

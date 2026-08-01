---
id: a-la-carte-content
name: Á la Carte Content
type: pattern
part: build
phase_relevance:
  - architecture
  - content
vault_dimensions: [2, 4]
evidence_channels: [slides, slide_sequence, video]
detection_signals:
  - "audience choice mechanism"
  - "hyperlinked menu slide"
  - "non-linear navigation"
  - "flexible agenda"
evaluable_from:
  - delivery_video
strong_evaluable_from:
  - delivery_video
absence_evaluable_from: null
not_applicable_when:
  - condition_id: short-talk-under-30-minutes
    description: "Complete delivery video establishes that the talk is shorter than 30 minutes, where the catalog says there are not enough sections for a meaningful audience menu."
  - condition_id: fixed-prerequisite-order
    description: "Complete delivery video establishes that the subject matter forms a fixed prerequisite chain in which later topics require the immediately preceding material, so audience-directed reordering would impair comprehension."
applicability_evaluable_from:
  - delivery_video
evidence_requirements:
  - "Delivery video must cover the event or interval needed to apply the existing delivery, timing, interaction, or audience-response criteria."
  - "Evidence must expose the existing scoring cues: functional navigation, genuine audience selection, and smooth non-linear delivery."
not_evaluable_when:
  - "No delivery video covers the relevant event or interval."
  - "Only a deck, transcript, or short excerpt is available, so actual timing, interaction, room behavior, or absence cannot be established."
  - "The complete delivery is unavailable, so duration and prerequisite-order applicability conditions cannot both be assessed."
related_patterns: [talklet, coda, live-demo]
inverse_of: []
difficulty: advanced
---

# Á la Carte Content

## Summary
Let the audience choose what comes next by creating a menu-driven presentation with hyperlinked topics, turning a linear talk into an interactive, audience-directed experience.

## The Pattern in Detail
Á la Carte Content — also known as "Choose Your Own Adventure" — transforms the traditional one-directional presentation into an interactive experience where the audience has agency over the order and selection of topics. Instead of marching through a predetermined sequence of slides, the presenter offers a menu of topics and lets the audience vote, shout out, or otherwise indicate what they want to hear about next. This approach fundamentally changes the power dynamic in the room and dramatically increases engagement.

The most common implementation involves creating a "home" or "menu" slide that serves as a visual table of contents. Each topic on this slide is represented by an icon, text box, or image that is hyperlinked to the corresponding section of the deck. When the audience selects a topic, the presenter clicks the appropriate element and jumps directly to that section. At the end of each section, a hyperlink returns the presenter to the menu slide, where the audience can make their next selection. Most presentation tools support this through internal hyperlinks — Keynote uses "Link to Slide," PowerPoint uses "Hyperlink to Slide."

This pattern works exceptionally well when combined with the Talklet pattern, where the presentation is already organized into coarse, self-contained chunks. Each Talklet becomes a menu item, and the order in which they are presented does not matter. Venkat Subramaniam uses a brilliant variant of this approach in his conference talks, presenting topics in a Jeopardy-style game board where audience members select categories and point values, turning the entire talk into a competitive puzzle.

The audience selection mechanism can take several forms. The simplest is a show of hands: "Who wants to hear about Topic A? Topic B?" More sophisticated approaches use live polling tools, physical props (colored cards), or even audience shout-outs. The key is that the selection must be genuine — if the audience senses that you are going to cover everything regardless of their input, the interactive element feels performative rather than participatory.

Á la Carte Content demands significant preparation from the presenter. You must be comfortable with every possible ordering of your sections, including the possibility that some sections will not be covered at all. You need smooth transitions between any two sections, not just sequential ones. And you must manage time carefully: if the audience selects the longest topics first, you may need to gracefully communicate that time constraints prevent covering every remaining option. This level of flexibility is why the pattern is rated as advanced difficulty.

## When to Use / When to Avoid
Use Á la Carte Content when your audience is diverse and likely to have varying interests, such as at conferences, meetups, or training sessions with mixed experience levels. It is also effective for repeat presentations where you want to offer fresh experiences to returning audience members. The pattern shines when you have more material than time allows and want the audience to prioritize.

Avoid this pattern when your content has strong sequential dependencies — when Topic B only makes sense after Topic A. Also avoid it in very large audiences (500+) where polling becomes logistically difficult, or in formal settings where the interactive element might feel out of place. Short talks (under 30 minutes) generally do not have enough sections to make the menu meaningful.

## Detection Heuristics
When scoring talks, look for a visible menu or selection mechanism, hyperlinked navigation between sections, and evidence that the audience influenced the order of content. A presenter who returns to a "home base" slide between sections and solicits audience input is demonstrating this pattern clearly.

## Scoring Criteria
- Strong signal: Clear menu slide with functional hyperlinks, genuine audience selection mechanism, smooth navigation between non-sequential sections
- Moderate signal: Some audience choice offered but limited (e.g., choosing between two options), or menu exists but navigation is clunky
- Absent: Entirely linear presentation with no audience agency over content order

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`.

## Relationship to Vault Dimensions
Dimension 2 (Structure and Flow): Á la Carte Content represents a fundamentally different structural paradigm — non-linear, audience-directed flow rather than presenter-dictated sequence. Dimension 4 (Audience Engagement): This pattern is one of the strongest expressions of audience engagement, giving the audience literal control over the presentation's direction.

## Combinatorics
Á la Carte Content pairs naturally with Talklet, as self-contained sections are essential for non-sequential navigation. The Coda pattern provides a home for reference materials that might otherwise clutter the menu options. Live Demo sections work well as menu items. Context Keeper implementations like Breadcrumbs can be adapted to show which menu items have been covered and which remain.

---
id: a-la-carte-content
name: A La Carte Content
type: pattern
part: build
phase_relevance:
  - architecture
  - content
vault_dimensions: [2, 4]
detection_signals:
  - "audience choice mechanism"
  - "hyperlinked menu slide"
  - "non-linear navigation"
  - "flexible agenda"
related_patterns: [talklet, coda, live-demo]
inverse_of: []
difficulty: advanced
---

# A La Carte Content

## Summary
Let the audience choose what comes next by creating a menu-driven presentation with hyperlinked topics, turning a linear talk into an interactive, audience-directed experience.

## The Pattern in Detail
A La Carte Content — also known as "Choose Your Own Adventure" — transforms the traditional one-directional presentation into an interactive experience where the audience has agency over the order and selection of topics. Instead of marching through a predetermined sequence of slides, the presenter offers a menu of topics and lets the audience vote, shout out, or otherwise indicate what they want to hear about next. This approach fundamentally changes the power dynamic in the room and dramatically increases engagement because the audience feels ownership over the experience.

The most common implementation involves creating a "home" or "menu" slide that serves as a visual table of contents. Each topic on this slide is represented by an icon, text box, or image that is hyperlinked to the corresponding section of the deck. When the audience selects a topic, the presenter clicks the appropriate element and jumps directly to that section. At the end of each section, a hyperlink returns the presenter to the menu slide, where the audience can make their next selection. Most presentation tools support this through internal hyperlinks — Keynote uses "Link to Slide," PowerPoint uses "Hyperlink to Slide."

This pattern works exceptionally well when combined with the Talklet pattern, where the presentation is already organized into coarse, self-contained chunks. Each Talklet becomes a menu item, and because Talklets are designed to be independent, the order in which they are presented does not matter. Venkat Subramaniam uses a brilliant variant of this approach in his conference talks, presenting topics in a Jeopardy-style game board where audience members select categories and point values, turning the entire talk into a competitive puzzle.

The audience selection mechanism can take several forms. The simplest is a show of hands: "Who wants to hear about Topic A? Topic B?" More sophisticated approaches use live polling tools, physical props (colored cards), or even audience shout-outs. The key is that the selection must be genuine — if the audience senses that you are going to cover everything regardless of their input, the interactive element feels performative rather than participatory.

A La Carte Content demands significant preparation from the presenter. You must be comfortable with every possible ordering of your sections, including the possibility that some sections will not be covered at all. You need smooth transitions between any two sections, not just sequential ones. And you must manage time carefully: if the audience selects the longest topics first, you may need to gracefully communicate that time constraints prevent covering every remaining option. This level of flexibility is why the pattern is rated as advanced difficulty.

## When to Use / When to Avoid
Use A La Carte Content when your audience is diverse and likely to have varying interests, such as at conferences, meetups, or training sessions with mixed experience levels. It is also effective for repeat presentations where you want to offer fresh experiences to returning audience members. The pattern shines when you have more material than time allows and want the audience to prioritize.

Avoid this pattern when your content has strong sequential dependencies — when Topic B only makes sense after Topic A. Also avoid it in very large audiences (500+) where polling becomes logistically difficult, or in formal settings where the interactive element might feel out of place. Short talks (under 30 minutes) generally do not have enough sections to make the menu meaningful.

## Detection Heuristics
When scoring talks, look for a visible menu or selection mechanism, hyperlinked navigation between sections, and evidence that the audience influenced the order of content. A presenter who returns to a "home base" slide between sections and solicits audience input is demonstrating this pattern clearly.

## Scoring Criteria
- Strong signal (2 pts): Clear menu slide with functional hyperlinks, genuine audience selection mechanism, smooth navigation between non-sequential sections
- Moderate signal (1 pt): Some audience choice offered but limited (e.g., choosing between two options), or menu exists but navigation is clunky
- Absent (0 pts): Entirely linear presentation with no audience agency over content order

## Relationship to Vault Dimensions
Dimension 2 (Structure and Flow): A La Carte Content represents a fundamentally different structural paradigm — non-linear, audience-directed flow rather than presenter-dictated sequence. Dimension 4 (Audience Engagement): This pattern is one of the strongest expressions of audience engagement, giving the audience literal control over the presentation's direction.

## Combinatorics
A La Carte Content pairs naturally with Talklet, as self-contained sections are essential for non-sequential navigation. The Coda pattern provides a home for reference materials that might otherwise clutter the menu options. Live Demo sections work well as menu items because they are inherently self-contained. Context Keeper implementations like Breadcrumbs can be adapted to show which menu items have been covered and which remain.

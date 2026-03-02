---
id: crawling-code
name: Crawling Code
type: pattern
part: build
phase_relevance:
  - slides
vault_dimensions: [11, 13]
detection_signals:
  - "scrolling code display"
  - "highlighted active lines"
  - "shaded context lines"
related_patterns: [traveling-highlights, emergence]
inverse_of: []
difficulty: advanced
---

# Crawling Code

## Summary
Show code by scrolling through it with only a portion visible at a time, shading out-of-attention lines to maintain focus while highlighted lines indicate the currently discussed section.

## The Pattern in Detail
Crawling Code is an advanced slide animation technique for presenting source code that acknowledges a fundamental tension: code is inherently linear and sequential, but audiences can only absorb a few lines at a time. Rather than showing an entire code listing on a single slide (which overwhelms the audience) or breaking the code across many disconnected slides (which destroys context), Crawling Code presents the code as a scrolling window. Only a portion of the full listing is visible at any moment. The lines currently being discussed are highlighted with full color and opacity, while surrounding lines are visible but dimmed or shaded, providing context without competing for attention.

The implementation of Crawling Code requires layered construction within your presentation tool. One approach is to create the full code listing as a single tall text element, then use motion animations to scroll it upward as you progress through the explanation. Overlaid on this scrolling text are semi-transparent rectangles that shade the lines above and below the current focus area. Another approach — more labor-intensive but more controllable — is to create separate text elements for each logical block of code and use entrance, emphasis, and exit animations to highlight and dim them in sequence. Some presenters use a hybrid approach: the code is a single element that scrolls, while the highlight zone is a separate element that remains stationary in the center of the visible area.

The visual design of the shading is critical. The out-of-focus lines should be visible enough that the audience can see the surrounding context — the function signature above, the closing brace below, the import statements at the top — but dim enough that they do not compete with the highlighted lines for visual attention. A common technique is to overlay a semi-transparent white or black rectangle (depending on your slide background) over the non-focus areas, reducing their opacity to approximately thirty to forty percent. The highlighted lines, by contrast, should be at full brightness with syntax coloring intact.

Crawling Code is particularly effective for code walkthroughs in technical presentations, where the presenter needs to explain a function line by line, show how data flows through a pipeline, or trace the execution of an algorithm. Without this technique, presenters face an impossible choice: show all the code at once (and lose the audience to information overload), show one line at a time (and lose all context), or show the code on multiple slides (and force the audience to mentally reconstruct the relationships between fragments). Crawling Code threads this needle by maintaining visible context while directing focused attention.

The pacing of the crawl is essential. Each highlighted section should remain visible long enough for the audience to read and comprehend the code before the crawl advances. For most audiences, this means five to ten seconds per highlighted block of three to five lines. The transition between highlighted sections should be smooth rather than abrupt — a gentle scroll or fade rather than a jump cut. This smooth motion helps the audience track where they are in the overall code listing and reinforces the linear, sequential nature of the code being explained.

## When to Use / When to Avoid
Use Crawling Code whenever you need to present a code listing longer than approximately ten lines where the audience needs to understand the code in detail. It is essential for algorithm explanations, API walkthroughs, debugging demonstrations, and any situation where code comprehension is the primary objective.

Avoid Crawling Code for very short code snippets (under ten lines) where a single static slide is sufficient. Also avoid it when the code is being shown for illustrative purposes only — if the audience does not need to read and understand the actual code, a simpler approach like a screenshot or a pseudocode summary is more appropriate and far less work to produce.

## Detection Heuristics
When scoring talks, look for code that scrolls or transitions through visible regions, with clear visual differentiation between highlighted (active) lines and shaded (contextual) lines. Note whether the presenter maintains visible context around the highlighted code or shows lines in complete isolation. Smooth scrolling with consistent pacing is a strong positive signal.

## Scoring Criteria
- Strong signal (2 pts): Code displayed with smooth scrolling, clear highlighting of active lines, visible but dimmed context lines, appropriate pacing, and syntax coloring on the focus area
- Moderate signal (1 pt): Some attempt at progressive code display — sequential reveal or partial highlighting — but without the full context-preserving, scrolling implementation
- Absent (0 pts): Full code listings displayed statically with no visual guidance, or code split across disconnected slides with no visual continuity

## Relationship to Vault Dimensions
Dimension 11 (Demonstrations and Tools): Crawling Code is a primary technique for presenting code — the most common tool artifact in technical presentations — in a way that prioritizes comprehension over completeness. Dimension 13 (Slide Aesthetics): The layered construction of Crawling Code, with its careful use of opacity, highlight colors, and smooth animation, represents sophisticated slide design that elevates the visual quality of technical content.

## Combinatorics
Crawling Code works closely with Traveling Highlights — while Crawling Code handles vertical navigation through a code listing, Traveling Highlights can be applied within the visible window to draw attention to specific tokens, variables, or expressions on the currently highlighted lines. It also pairs with Emergence, as the gradual revelation of code through scrolling mirrors the piece-by-piece assembly philosophy of Emergence applied to textual content.

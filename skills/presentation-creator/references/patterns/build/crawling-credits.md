---
id: crawling-credits
name: Crawling Credits
type: pattern
part: build
phase_relevance:
  - slides
vault_dimensions: [6, 13]
detection_signals:
  - "scrolling credits animation"
  - "multi-contributor acknowledgment"
  - "Star Wars style credits"
related_patterns: [coda]
inverse_of: []
difficulty: intermediate
---

# Crawling Credits

## Summary
Show credits in a Star Wars-style bottom-to-top scroll, giving each entry equal but limited screen time, for use when you need to credit many contributors without consuming multiple slides.

## The Pattern in Detail
Crawling Credits is an animation technique borrowed directly from cinema — most famously the opening crawl of Star Wars — applied to the problem of crediting many contributors in a presentation. Rather than dedicating multiple static slides to listing names (which is tedious for the audience) or cramming dozens of names onto a single slide in tiny font (which is unreadable), the Crawling Credits pattern uses a smooth bottom-to-top scrolling animation that gives each contributor equal but limited screen time as their name rises through the visible area.

The mechanics of implementation vary by presentation tool. In Keynote, you can create a tall text box that extends well below the visible slide area and apply a Move animation that scrolls it upward over a defined duration. In PowerPoint, the equivalent is a motion path animation on a text box. The key technical consideration is timing: the scroll speed must be slow enough for the audience to read each name but fast enough that the entire credits sequence does not overstay its welcome. A good rule of thumb is approximately two to three seconds of visibility per name, which means a list of thirty contributors would take about sixty to ninety seconds — the length of a brief verbal acknowledgment.

The Crawling Credits pattern solves a genuine social problem in presentations. Many talks are the product of collaborative effort — team members, open-source contributors, research assistants, mentors — and failing to acknowledge them is both ungracious and politically unwise. But listing contributors in a traditional slide format forces a choice between comprehensiveness (listing everyone, which takes too long) and selectivity (listing a few, which offends the omitted). Crawling Credits threads this needle by making the acknowledgment feel celebratory and cinematic rather than bureaucratic.

The visual design of Crawling Credits matters. Use a clean, readable font at a size large enough to be legible from the back of the room as each name scrolls through the center of the visible area. Consider grouping contributors by role or contribution type, with section headers that scroll along with the names. A subtle musical accompaniment — if the venue allows audio — reinforces the cinematic feel and signals to the audience that this is a deliberate stylistic choice, not a technical accident.

One important constraint: Crawling Credits should not be used to replace verbal acknowledgment of key collaborators. Your most important contributors deserve a spoken "thank you" by name. Crawling Credits is best used for the extended list — the full team, all the beta testers, every open-source contributor — that you cannot reasonably name individually during your talk. It is a complement to personal acknowledgment, not a substitute for it.

## When to Use / When to Avoid
Use Crawling Credits when you have more than eight to ten contributors to acknowledge and dedicating multiple slides to static name lists would disrupt the flow of your talk. It is especially effective at the end of a talk, during the Coda section, where it serves as both acknowledgment and a graceful transition to the end.

Avoid Crawling Credits when you have only a handful of people to thank — a simple spoken acknowledgment or a single slide is more appropriate. Also avoid it if your presentation tool does not support smooth scrolling animations, as a jerky or stuttering scroll undermines the cinematic effect and looks amateurish.

## Detection Heuristics
When scoring talks, look for animated credit sequences that scroll vertically. The presence of a scrolling list of names, contributors, or acknowledgments is a clear signal. Also look for evidence that the presenter chose this format deliberately — grouping by role, consistent formatting, appropriate pacing — rather than simply animating a text box as an afterthought.

## Scoring Criteria
- Strong signal (2 pts): Smooth, well-paced scrolling credits with organized groupings, readable font size, and deliberate cinematic presentation of contributor acknowledgments
- Moderate signal (1 pt): Scrolling credits present but with pacing issues (too fast or too slow), inconsistent formatting, or lacking clear organization
- Absent (0 pts): No scrolling credits used, or contributors listed on static slides with cramped text or omitted entirely

## Relationship to Vault Dimensions
Dimension 6 (Information Density): Crawling Credits manages high-density acknowledgment information by distributing it over time rather than space, keeping the screen uncluttered at any given moment while still conveying comprehensive credit. Dimension 13 (Slide Aesthetics): The cinematic quality of well-executed Crawling Credits elevates the overall aesthetic of the presentation, turning a potentially mundane obligation into a visually engaging moment.

## Combinatorics
Crawling Credits pairs naturally with the Coda pattern, as the end-of-deck reference section is the ideal location for extended contributor acknowledgments. It can also complement any pattern that involves collaborative work, providing a graceful way to transition from the substance of the talk to the social obligations of acknowledgment without breaking the flow.

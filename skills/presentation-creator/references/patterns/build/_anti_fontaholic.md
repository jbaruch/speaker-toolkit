---
id: fontaholic
name: Fontaholic
type: antipattern
part: build
phase_relevance:
  - guardrails
  - slides
vault_dimensions: [13, 14]
detection_signals:
  - "excessive font variety"
  - "inconsistent typography"
  - "more than 2-3 fonts used"
related_patterns: [floodmarks]
inverse_of: []
difficulty: foundational
---

# Fontaholic

## Summary
Using too many font faces in a presentation, creating a "ransom note" effect that is jarring, inconsistent, and difficult to read — stick with clean sans-serif fonts and limit your palette.

## The Pattern in Detail
The Fontaholic antipattern occurs when a presenter uses an excessive number of typefaces throughout their slides, creating a visual cacophony that undermines readability and professionalism. The colloquial name for this effect is the "ransom note" — just as a ransom note constructed from cut-out magazine letters features a chaotic mix of fonts, sizes, and styles that is deliberately disorienting, a Fontaholic presentation creates unintentional visual chaos through typographic inconsistency. Each slide (or even each text element within a slide) appears to have been designed by a different person, and the audience's eye is constantly adjusting to new letterforms instead of absorbing the content.

The temptation of font variety is understandable. Presentation software comes with hundreds of installed fonts, and designers and non-designers alike are drawn to variety. A serif font for the title adds gravitas. A handwritten font for a quote adds personality. A monospace font for code adds technical authenticity. A decorative font for the section header adds flair. Each individual choice may seem reasonable in isolation, but the cumulative effect of four or five or six different typefaces is visual incoherence. The audience processes typography subconsciously — they may not be able to articulate what feels wrong, but they experience the inconsistency as a general sense of disorder and amateurism.

The professional standard for presentations is to use no more than two, and ideally three, typefaces throughout the entire deck. A common approach is: one sans-serif font for titles and headings (such as Helvetica, Arial, or Calibri), the same or a complementary sans-serif for body text and bullets, and a monospace font for code (such as Menlo, Consolas, or Source Code Pro). This three-font palette covers virtually every typographic need a presenter encounters. Within this palette, variety is achieved through size, weight (bold, regular, light), and style (italic, uppercase) rather than through font face changes.

Mixing fonts within the same visual group is acceptable and even desirable for emphasis. Using bold weight of your heading font for key terms, or italic for quotes, creates visual hierarchy without introducing new typefaces. The problem arises when the presenter reaches for a new font face instead of using weight and style variations of their existing fonts. This distinction — between typographic variation within a font family and the introduction of entirely new font families — is the line between professional design and Fontaholic chaos.

The fix for Fontaholic is straightforward: establish a font palette at the beginning of your slide design process and enforce it rigorously. Define your heading font, your body font, and your code font (if applicable) before creating any slides. Save these choices as part of your slide master or template. Then, when you feel the urge to use a different font for a specific element, pause and ask: can I achieve the desired effect using size, weight, or style changes to my existing fonts? The answer is almost always yes.

## When to Use / When to Avoid
This is an antipattern and should always be avoided. Typographic consistency is a fundamental principle of visual design, and violating it always degrades the quality of the presentation, even when the individual font choices are themselves attractive.

The only context where deliberate font variety might be acceptable is when the variety itself is the point — for example, a presentation about typography that showcases different typefaces as part of its content. In all other contexts, limit your font palette to two or three families.

## Detection Heuristics
When scoring talks, count the number of distinct font families used across the slide deck. Two or three fonts is normal. Four is suspicious. Five or more is a clear Fontaholic signal. Also look for inconsistency within slides — a title in one font, a subtitle in another, body text in a third, and a callout in a fourth is a classic pattern. Pay special attention to decorative or display fonts used for single elements, which are often the first sign of Fontaholic behavior.

## Scoring Criteria
- Strong signal (2 pts): Consistent typographic palette of two to three font families throughout the entire deck, with variety achieved through size, weight, and style rather than new typefaces
- Moderate signal (1 pt): Generally consistent typography with one or two additional fonts used for specific purposes (code, quotes), total of four or fewer font families
- Absent (0 pts): Five or more font families used across the deck, inconsistent typography within individual slides, ransom-note visual effect

## Relationship to Vault Dimensions
Dimension 13 (Slide Aesthetics): Typography is one of the most fundamental elements of visual design, and Fontaholic behavior directly degrades the aesthetic quality of slides by introducing visual chaos where consistency is needed. Dimension 14 (Overall Quality Indicators): Typographic inconsistency is a reliable signal of inexperience or inattention to design details, impacting the perceived professionalism of the entire presentation.

## Combinatorics
Fontaholic often co-occurs with the Floodmarks antipattern, as both represent failures of visual restraint — too many fonts and too much background imagery are driven by the same impulse to add visual complexity rather than simplify. The cure for both is discipline: establish constraints early and enforce them throughout. Fontaholic is less likely to occur when the presenter starts from a well-designed template that locks in the typographic palette.

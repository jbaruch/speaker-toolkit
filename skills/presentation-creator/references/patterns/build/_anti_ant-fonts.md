---
id: ant-fonts
name: Ant Fonts
type: antipattern
part: build
phase_relevance:
  - guardrails
  - slides
vault_dimensions: [13, 14]
detection_signals:
  - "small font sizes"
  - "cramped text"
  - "readability issues from back of room"
  - "auto-shrunk content"
related_patterns: [bullet-riddled-corpse, infodeck]
inverse_of: []
difficulty: foundational
---

# Ant Fonts

## Summary
Using tiny fonts to cram more information onto a slide, making content unreadable from the back of the room — if you think "you probably can't read this," you have already failed.

## The Pattern in Detail
Ant Fonts is the antipattern of using excessively small text on presentation slides, named for the fact that only an ant — with its face pressed against the screen — could comfortably read the content. The most damning signal of this antipattern is the presenter's own admission: "You probably can't read this in the back, but..." This phrase, uttered with depressing frequency at conferences and corporate meetings around the world, is a confession that the presenter knows the content is inaccessible but has chosen to display it anyway. The audience in the back rows is effectively told that the information is not for them.

The primary driver of Ant Fonts is the desire to include more information than a slide can comfortably display at a readable size. Rather than cutting content, spreading it across multiple slides, or rethinking the approach entirely, the presenter simply makes the text smaller. This is almost always an unconscious process — the presenter is working at their desk, twelve inches from a laptop screen, where 10-point font is perfectly legible. They do not mentally project the slide onto a screen fifteen feet away and imagine reading it from fifty feet. The cognitive gap between the authoring environment and the display environment is the root cause of nearly every Ant Fonts violation.

PowerPoint exacerbates this problem with its automatic font shrinking behavior. When a text box in PowerPoint overflows, the software's default behavior is to reduce the font size until the text fits. This happens smoothly and incrementally, so the presenter may not notice that their 24-point text has been silently reduced to 12-point or even 9-point text. The slide looks fine on the laptop, the text fits in the box, and the presenter moves on — unaware that they have created a slide that will be illegible to half the room. This auto-shrinking should be the first default setting any serious presenter disables.

Martin Fowler, the software development thought leader, offers a practical heuristic for combating Ant Fonts: design your slides at fifty percent zoom. If you can read your slide at half size on your laptop screen, the audience will be able to read it at full size from the back of the room. This simple technique forces you to use large enough text and eliminates the cognitive gap between authoring and display. For code specifically, the minimum font size should be eighteen points — anything smaller becomes a blur of characters from even moderate viewing distances.

The deeper issue that Ant Fonts reveals is a problem with Narrative Arc. When a presenter feels compelled to cram text onto a slide, it usually means they have not made the hard choices about what to include and what to cut. Every presentation has finite time and finite visual real estate, and the discipline of a strong Narrative Arc forces the presenter to prioritize ruthlessly. Ant Fonts is what happens when that discipline breaks down — when the presenter says "I'll just include everything" instead of "I'll include only what serves the story." The text shrinks because the story has not been properly shaped.

## When to Use / When to Avoid
This is an antipattern and should always be avoided. There is no legitimate reason to use text so small that audience members cannot read it. If you cannot fit the content at a readable size, you have too much content for one slide.

The solution is never to make the text smaller. The solution is one of: reduce the content, spread it across multiple slides, convert text to a visual representation (diagram, chart, image), or move detailed text to the Coda or a handout. For code, use the Crawling Code pattern to show a portion at a time rather than cramming an entire listing onto one slide.

## Detection Heuristics
When scoring talks, evaluate text readability from the audience perspective. Any text below 18-point font for code or 24-point font for regular text is a warning sign. The presenter saying "you probably can't read this" is an automatic detection trigger. Inconsistent text sizes across slides (indicating auto-shrinking) is another strong signal. Also watch for audience members squinting, leaning forward, or pulling out their phones to photograph a slide — all behavioral indicators of Ant Fonts.

## Scoring Criteria
- Strong signal (2 pts): All text is clearly readable from the back of the room, consistent font sizes across slides, no auto-shrunk content, code at 18pt or larger
- Moderate signal (1 pt): Most text is readable, with one or two slides that push the readability boundary, no verbal acknowledgment of illegibility
- Absent (0 pts): Multiple slides with small text, presenter acknowledges readability issues ("you probably can't read this"), auto-shrunk fonts visible, code in small font sizes

## Relationship to Vault Dimensions
Dimension 13 (Slide Aesthetics): Ant Fonts directly degrade the visual quality of slides, producing cramped, cluttered layouts that are aesthetically unpleasant and functionally illegible. Dimension 14 (Overall Quality Indicators): The presence of unreadable text is one of the most immediately visible negative quality signals in any presentation, suggesting insufficient preparation and poor audience awareness.

## Combinatorics
Ant Fonts frequently co-occurs with Bullet-Riddled Corpse, as the desire to include many bullet points on a single slide drives the font size down. It also co-occurs with Cookie Cutter, where the constraint of one-idea-per-slide forces text reduction to fit the container. The Infodeck pattern (slides designed for reading, not presenting) is the one context where smaller text might be acceptable, since the reader controls their viewing distance. In live presentation contexts, Ant Fonts has no acceptable application.

## Related Reading
- Reynolds, G. (2012). *Presentation Zen: Simple Ideas on Presentation Design and Delivery* (2nd ed.). Ch. 9 — quotes Guy Kawasaki: "If you need to put eight-point or ten-point fonts up there, it's because you do not know your material." New Riders.

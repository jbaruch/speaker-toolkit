---
id: analog-noise
name: Analog Noise
type: pattern
part: build
phase_relevance:
  - slides
vault_dimensions: [13]
detection_signals:
  - "hand-drawn elements"
  - "rough/sketch aesthetic"
  - "intentionally imperfect visuals"
related_patterns: [defy-defaults, leet-grammars]
inverse_of: []
difficulty: intermediate
---

# Analog Noise

## Summary
Add hand-drawn, rough, or imperfect visual elements to create visual interest and draw attention to key points. The aesthetic earns its keep through distinctiveness and human warmth — not, despite a claim this file used to make, by making text harder to read.

## The Pattern in Detail
In a world of pixel-perfect digital presentations, imperfection stands out. The Analog Noise pattern deliberately introduces hand-drawn, rough, sketchy, or otherwise "imperfect" visual elements into your slides. This might take the form of hand-drawn diagrams, sketch-style fonts, rough lines and arrows, watercolor textures, or illustrations that look like they were created with markers on a whiteboard. The visual imperfection is the point — it creates a distinctive aesthetic that feels human, personal, and authentic in a sea of sterile digital uniformity.

The selective-emphasis form of this pattern rests on solid ground: the **isolation effect** (the von Restorff effect), one of the older and better-replicated findings in memory research, holds that an item which differs conspicuously from the items around it is better remembered than the ones it sits among. A single hand-drawn diagram in a deck of clean corporate graphics *is* that isolated item. The mechanism is not that the sketch is harder to process — it is that the sketch is **different**, and difference is what attention and memory latch onto. This also explains the pattern's most important constraint, which follows directly from the mechanism rather than from taste: isolation requires a uniform field to be isolated against. Make every slide sketchy and nothing is distinctive anymore. The novelty is a budget, and spending it everywhere spends it nowhere.

Note what this does and does not claim. Distinctiveness reliably buys **attention and memorability for the marked item** — which is the whole job of the selective-emphasis approach, and it does that job well. It does not make your audience understand the content better, and the theme-wide application below is an aesthetic and tonal choice, justified on those grounds, with no retention argument behind it at all.

There are two strategic approaches to using Analog Noise. The first is to adopt it as a consistent visual theme for the entire presentation. In this approach, every slide uses sketch-style fonts, hand-drawn borders, rough-textured backgrounds, and illustration-style imagery. This creates a cohesive aesthetic that signals informality, creativity, and approachability. It works particularly well for talks about design thinking, creative processes, agile methodologies, or any topic where the content itself values iteration and imperfection. When using Analog Noise as a theme, consistency is critical — mixing sketch-style elements with polished corporate graphics creates a jarring incongruity rather than a deliberate aesthetic.

The second approach is to use Analog Noise sparingly for emphasis. In an otherwise polished presentation, a single hand-drawn diagram, a slide with a whiteboard-marker font, or a rough sketch inserted among clean graphics creates a powerful contrast that draws the eye and signals "pay attention, this is important." This selective approach leverages the novelty of the imperfect element against the clean backdrop of the rest of the deck. It is analogous to using a highlighter on a printed page — the marked text stands out precisely because the surrounding text is uniform.

Practical implementation varies by tool and skill level. At the simplest level, you can use "handwriting" or "sketch" fonts (many are available free online) for selected text elements. A step up is to use a drawing tablet or even a phone app to create hand-drawn diagrams, arrows, and annotations that you then import as images. Some presenters photograph actual whiteboard drawings or paper sketches. Keynote and PowerPoint both support freeform drawing tools, though the results depend heavily on the presenter's drawing skill and the input device used. For those who prefer not to draw, services like Excalidraw generate sketch-style diagrams programmatically.

### Do Not Make It Hard to Read
Earlier versions of this pattern justified Analog Noise with a much stronger and more exciting claim: that hard-to-read text is *better remembered* than clean text, because the extra effort of decoding it forces deeper processing. The claim was sourced to a real and widely-cited 2011 study (Diemand-Yauman, Oppenheimer & Vaughan, "Fortune favors the bold (and the italicized)"), it was repeated in a great many talks about talks, and it is the reason a font called Sans Forgetica exists.

It has not held up. The disfluency effect has replicated poorly and inconsistently; a meta-analysis across studies including the large original effect found essentially nothing for problem solving, and multiple attempts to reproduce Sans Forgetica's memory benefit found it performed no better than an ordinary font. Some later work finds recall is *worse* for disfluent text, which is the unsurprising direction. Treat the hard-to-read-font claim as retired.

The broader *desirable difficulties* framework it borrowed its authority from (Bjork & Bjork) is not retired and remains well-supported — but it is about **effortful retrieval**, not effortful reading. Making someone reconstruct an idea from memory is a desirable difficulty; making them squint is just a cost. Those two things were never the same claim, and the font study's popularity blurred them. The catalog's honest applications of desirable difficulty are `retrieval-beat` and `guess-first`, both of which put the effort in the audience's *recall* rather than in their optic nerve.

The practical rule this leaves is short and unglamorous: **legibility is never the thing you trade away.** Sketchiness in a border, an arrow, a diagram, a texture, a heading — fine, and often good. Body text set in a font that fights the reader, or a hand-drawn label the back row cannot resolve, buys nothing and costs comprehension, and it lands you in `_anti_ant-fonts.md` with a better story about why. If a slide's roughness makes anyone in the room work to read it, that is not desirable difficulty. That is just a hard-to-read slide.

## When to Use / When to Avoid
Use Analog Noise when you want to signal authenticity, creativity, or informality. It is especially effective in design-oriented talks, creative workshops, and presentations where the "work in progress" aesthetic aligns with the message. The selective emphasis approach works in almost any context where you need to draw attention to a key slide.

Avoid Analog Noise in formal corporate settings where polished graphics are expected, such as board presentations, investor pitches, or regulatory briefings. Also avoid it when the "rough" aesthetic might be misinterpreted as lack of preparation — know your audience's expectations.

## Detection Heuristics
When scoring talks, look for visual elements that are deliberately imperfect: hand-drawn diagrams, sketch-style fonts, rough lines, watercolor or marker textures, or whiteboard-style illustrations. The key distinction is between intentional imperfection (a deliberate aesthetic choice) and unintentional sloppiness (misaligned elements, pixelated images, inconsistent formatting).

## Scoring Criteria
- Strong signal (2 pts): Deliberate, consistent use of hand-drawn or sketch-style visual elements that create a cohesive aesthetic, or strategic use of imperfect elements for emphasis at key moments
- Moderate signal (1 pt): Some hand-drawn or rough elements present but inconsistently applied, or the aesthetic feels accidental rather than intentional
- Absent (0 pts): All visual elements are digitally clean and standard, with no hand-drawn or rough aesthetic choices

## Relationship to Vault Dimensions
Dimension 13 (Visual Polish and Craft): Analog Noise is a sophisticated expression of visual craft.

## Combinatorics
Analog Noise pairs naturally with Defy Defaults, as both involve making unconventional visual choices. It shares philosophical DNA with Leet Grammars — both patterns involve intentional deviation from "correct" norms to create impact. The pattern can enhance Bookends and Intermezzi by giving section dividers a distinctive hand-crafted feel. It also works well as the visual layer for Emergence, where hand-drawn diagrams build incrementally to reveal complexity.

Its relationship to `retrieval-beat` and `guess-first` is corrective rather than cooperative: those two patterns are what the desirable-difficulty argument actually licenses, and this pattern should no longer be understood as a member of that family (see "Do Not Make It Hard to Read"). The constraint boundary is `_anti_ant-fonts.md` — the moment roughness costs legibility, Analog Noise has become that antipattern.

## Related Reading
- Diemand-Yauman, C., Oppenheimer, D. M., & Vaughan, E. B. (2011). "Fortune favors the bold (and the italicized): Effects of disfluency on educational outcomes." *Cognition*, 118(1) — the origin of the hard-to-read-font claim, recorded here because the claim is widely repeated in presentation advice and this file previously carried it. Subsequent replication attempts, including a meta-analysis and multiple Sans Forgetica studies, have not supported it.
- Bjork, R. A., & Bjork, E. L. — the "desirable difficulties" framework, which remains well-supported and is about effortful retrieval rather than effortful perception. Applied honestly in `retrieval-beat.md` and `guess-first.md`.
- Brown, P. C., Roediger, H. L., III, & McDaniel, M. A. (2014). *Make It Stick: The Science of Successful Learning.* Ch. 4 — "Embrace Difficulties" presents the desirable-difficulties framework in its retrieval-based form. Belknap Press / Harvard University Press.

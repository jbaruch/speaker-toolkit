---
id: cookie-cutter
name: Cookie Cutter
type: antipattern
part: build
phase_relevance:
  - guardrails
  - slides
vault_dimensions: [8, 13]
detection_signals:
  - "ideas forced into single slides"
  - "information cramming"
  - "unnatural content breaks at slide boundaries"
related_patterns: [soft-transitions, fourthought]
inverse_of: [soft-transitions]
difficulty: foundational
---

# Cookie Cutter

## Summary
Letting slide boundaries dictate information density by forcing each idea into exactly one slide, rather than using as many slides as the idea requires.

## The Pattern in Detail
The Cookie Cutter antipattern occurs when a presenter treats each slide as a fixed-size container that every idea must fit inside, regardless of the idea's actual size. Rather than letting the content dictate how many slides it needs, the presenter lets the slide count dictate how much content each idea gets. Ideas are cut, compressed, and crammed to fit the arbitrary boundaries of a single slide, producing overcrowded visuals and intellectually incomplete explanations. The metaphor is apt: a cookie cutter imposes a uniform shape on dough regardless of the dough's natural form, and the result is identical, soulless shapes with wasted material trimmed away.

This antipattern is deeply embedded in presentation culture because most presentation software actively encourages it. PowerPoint's default behavior when text exceeds a text box is to shrink the font size — an automated accommodation that enables and conceals the cramming. Presenters see their text fit neatly on the slide and assume everything is fine, not realizing that the software has silently reduced their 24-point text to 11-point text to make it fit. The result is slides that technically contain all the information but are unreadable from any distance greater than three feet. Keynote is slightly better in this regard, as it does not auto-shrink by default, but the underlying mindset — one idea, one slide — persists regardless of tool.

The root cause of Cookie Cutter thinking is a misconception about what slides cost. Presenters mentally treat each slide as if it has a price: the more slides you use, the more you are "spending." This creates artificial pressure to minimize slide count, which leads directly to information cramming. In reality, slides are free. There is no per-slide charge from Keynote or PowerPoint. There is no conference rule that limits you to thirty slides. The audience does not count your slides and penalize you for using more. What the audience does notice — and penalize you for — is cramped, unreadable, overwhelming slides that try to communicate too much at once.

The solution to Cookie Cutter is a fundamental mindset shift: let the idea determine its slide footprint. A simple idea that can be expressed in three words gets one slide with three large words. A complex idea that requires a diagram, an explanation, an example, and a summary might need four or five slides. A narrative transition might use a series of slides with a single word or image each, creating a rhythmic buildup. The Soft Transitions pattern is the direct antidote, using sequences of slides that blur the boundaries between ideas so the audience never notices where one slide ends and the next begins.

The Cookie Cutter mindset is especially damaging when combined with other antipatterns. When a presenter is also committing Bullet-Riddled Corpse (filling slides with bullet points), Ant Fonts (using tiny text), and Cookie Cutter simultaneously, the result is dense, unreadable slides packed with information that the audience cannot absorb. Each antipattern reinforces the others, creating a downward spiral of presentation quality. Breaking the Cookie Cutter habit — simply giving yourself permission to use more slides — often triggers improvements in all three dimensions simultaneously.

## When to Use / When to Avoid
This is an antipattern and should always be avoided. There is no scenario where forcing ideas into arbitrarily uniform slide containers produces a better presentation than letting ideas determine their own footprint.

The instinct toward Cookie Cutter thinking may be strongest when a presenter is given a fixed time slot and unconsciously maps "thirty minutes" to "thirty slides." Fight this instinct. Some thirty-minute talks use twenty slides; others use one hundred and fifty. The slide count is irrelevant; what matters is whether each slide serves the narrative and whether the audience can absorb the content.

## Detection Heuristics
When scoring talks, look for slides that feel overstuffed — text that is clearly compressed to fit, diagrams with overlapping labels, bullet lists that extend to the bottom of the slide. Also look for ideas that feel artificially truncated at slide boundaries, as if the explanation was cut short because the slide ran out of space. Auto-shrunk fonts (inconsistent text sizes across slides) are a telltale indicator of the software accommodating Cookie Cutter behavior.

## Scoring Criteria
- Strong signal (2 pts): No evidence of cookie-cutter thinking — ideas span as many slides as they need, content is appropriately sized, and slide boundaries are invisible to the audience
- Moderate signal (1 pt): Occasional cramming on some slides, but most ideas are given appropriate space; some variation in text size suggesting occasional forced fitting
- Absent (0 pts): Consistent pattern of one-idea-per-slide regardless of idea complexity, with visible cramming, auto-shrunk fonts, and ideas that feel truncated at slide boundaries

## Relationship to Vault Dimensions
Dimension 8 (Slide Design): Cookie Cutter fundamentally compromises slide design by subordinating design decisions to arbitrary size constraints rather than content requirements. Dimension 13 (Slide Aesthetics): The visual cramming that results from Cookie Cutter thinking produces aesthetically poor slides with inconsistent text sizes, cluttered layouts, and no visual breathing room.

## Combinatorics
Cookie Cutter is the inverse of Soft Transitions, which explicitly encourages multi-slide sequences that blur the boundaries between ideas. It often co-occurs with Bullet-Riddled Corpse (bullets used to fit more content per slide) and Ant Fonts (small text used to fit more content per slide). The Fourthought pattern, when applied properly during the ideation phase, helps prevent Cookie Cutter by encouraging ideas to find their natural size before slides are designed.

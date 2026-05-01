---
id: takahashi
name: Takahashi
type: pattern
part: prepare
phase_relevance:
  - architecture
  - slides
vault_dimensions: [8, 12, 13]
detection_signals:
  - "one element per slide"
  - "very high slide count"
  - "rapid transitions"
  - "minimal text per slide"
related_patterns: [brain-breaks]
inverse_of: [bullet-riddled-corpse]
difficulty: advanced
---

# Takahashi

## Summary
A stylized format using one word, phrase, or image per slide, transitioning through hundreds of slides very quickly for machine-gun delivery.

## The Pattern in Detail
The Takahashi method, originated by Masayoshi Takahashi who presented at a Ruby conference without access to image-editing software, is a radical approach to slide design. Each slide contains exactly one element: a single word, a short phrase, or a single image. The speaker transitions through slides rapidly — sometimes every few seconds — creating a machine-gun rhythm that keeps the audience's visual attention constantly refreshed while the speaker's voice provides the connective tissue between visual fragments.

The visual effect is striking and immediately distinctive. Where a conventional presentation might have 30-50 slides for a 90-minute talk, a Takahashi presentation might have 350 or more. Each slide acts as a visual punctuation mark for the speaker's words — emphasizing a key term, illustrating a concept with a single image, or creating dramatic pauses through blank or minimal slides. The audience experiences the presentation as a rapid-fire multimedia stream where visual and auditory channels work in tight synchronization.

The Takahashi method works with virtually any presentation type because it shifts the information density from the slides to the speaker. In a conventional presentation, slides carry a significant portion of the content — bullet points, diagrams, code samples. In Takahashi, the slides carry almost none. They serve as visual anchors, emotional cues, and rhythm markers while the speaker carries the full content load verbally. This makes Takahashi presentations uniquely dependent on the speaker's delivery skills and deep knowledge of the material.

Building a Takahashi presentation requires a fundamentally different workflow. You write your talk first — every word, every transition, every pause — and then create slides that punctuate and emphasize key moments. Each slide takes seconds to create (it is just a word or an image) but choosing which moments deserve visual emphasis requires deep understanding of your own material and your audience's needs. The creation process is fast per-slide but thoughtful in aggregate.

One significant limitation: Takahashi presentations make poor printed handouts. A stack of 350 slides, each containing a single word, is meaningless without the speaker's voice to provide context. If handout material is required, you need to create a separate document — an outline, a blog post, or a companion guide. This is additional work but also an opportunity: the companion document can go deeper than any slide deck, and the presentation itself is optimized purely for live delivery rather than compromising to serve dual purposes.

## When to Use / When to Avoid
Use Takahashi when you want to create a highly engaging, visually distinctive presentation and you are confident in your delivery skills. It works best when you are deeply familiar with your material and can carry the content verbally without relying on slide text as a crutch. Avoid when the audience needs reference material (code samples, detailed diagrams), when printed handouts are essential, or when you are not comfortable with rapid slide transitions and the delivery demands they create.

## Detection Heuristics
The vault should look for the characteristic Takahashi signature: very high slide count, minimal content per slide (one word, phrase, or image), rapid transitions, and a speaker who carries the full informational load verbally.

## Scoring Criteria
- Strong signal (2 pts): One element per slide consistently; very high slide count relative to talk length; rapid, well-timed transitions; speaker and slides in tight sync; the format enhances rather than distracts
- Moderate signal (1 pt): Mostly minimal slides but with occasional text-heavy exceptions; transitions generally smooth but inconsistent rhythm
- Absent (0 pts): Standard slide density; no evidence of Takahashi method; slides carry content rather than punctuating it

## Relationship to Vault Dimensions
Relates to Dimension 8 (Slide Design/Visual Quality) because Takahashi is a deliberate and bold design choice. Relates to Dimension 12 (Time/Pacing) because the rapid slide transitions create a distinctive pacing pattern. Relates to Dimension 13 (Visual Aids Effectiveness) because the single-element-per-slide approach maximizes visual impact per slide.

## Combinatorics
Pairs with Brain Breaks (the rapid visual changes function as continuous micro-breaks for attention). The inverse is Bullet-Riddled Corpse — where Takahashi puts one element per slide, the antipattern crams as many bullet points as possible onto each slide.

## Related Reading
- Reynolds, G. (2012). *Presentation Zen: Simple Ideas on Presentation Design and Delivery* (2nd ed.). Ch. 7 — documents the Takahashi Method directly with sample slides and the origin story (Masayoshi Takahashi, Tokyo developer). New Riders.

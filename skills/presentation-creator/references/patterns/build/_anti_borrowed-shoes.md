---
id: borrowed-shoes
name: Borrowed Shoes
type: antipattern
part: build
phase_relevance:
  - guardrails
vault_dimensions: [7, 8, 14]
detection_signals:
  - "mismatch between speaker style and slides"
  - "uncomfortable delivery rhythm"
  - "borrowed material without adaptation"
related_patterns: [crucible, narrative-arc, carnegie-hall]
inverse_of: []
difficulty: foundational
---

# Borrowed Shoes

## Summary
Presenting someone else's slides is like wearing someone else's shoes — uncomfortable and produces terrible results because individual presentation style is deeply imprinted onto materials.

## The Pattern in Detail
Borrowed Shoes is the antipattern of delivering a presentation using slides created by someone else without substantially reworking them to fit your own style, voice, and delivery rhythm. The metaphor is visceral and accurate: wearing someone else's shoes may technically get you from point A to point B, but the fit is wrong, the wear patterns do not match your gait, and every step feels slightly off. Similarly, presenting someone else's slides may technically convey the information, but the timing is wrong, the emphasis does not match your instincts, the humor falls flat, and the entire experience feels forced and uncomfortable — for both the presenter and the audience.

The reason Borrowed Shoes produces such poor results is that a presentation is not merely its slides. A presentation is a deeply personal fusion of content, visual design, timing, verbal emphasis, gestural habits, humor, storytelling style, and personality. When an experienced presenter creates a deck, every element reflects their individual approach: the pace at which they reveal information, the moments where they pause for effect, the visual density that matches their speaking rhythm, the jokes that land because of their particular delivery. This personal imprint is invisible in the slide file — it lives in the presenter's muscle memory and intuition — but its absence is immediately felt when someone else tries to use those slides.

The most common scenario for Borrowed Shoes is the corporate cascade: a senior leader creates a presentation, and then team leads are expected to deliver it to their teams. The slide deck is emailed around with a note that says "please present this to your group by Friday." The recipients dutifully open the deck, click through it once or twice, and then stand in front of their teams and read slides they did not write, in an order they did not choose, with timing they have not practiced. The result is universally terrible. The presenter stumbles over unfamiliar transitions, misses the intended emphasis of key slides, and cannot answer questions about design choices they did not make. The audience, sensing the presenter's discomfort, disengages.

The solution to Borrowed Shoes is not to refuse to present material created by others — sometimes the situation demands it. The solution is to rework the material until it fits you. This means: study the original deck to understand the intended message and narrative arc. Then close the original file and rebuild the presentation from scratch in your own style, using the original as a content reference rather than a visual template. If rebuilding from scratch is not feasible due to time constraints, at minimum restructure the deck to match your speaking rhythm, replace visuals that do not resonate with you, and add speaker notes that reflect your own language and emphasis.

An alternative approach when you must deliver someone else's content is to radically simplify the delivery. Consider presenting with minimal slides — perhaps just a whiteboard or a few key diagrams — and using the original deck as background material that you reference but do not project. This leverages your natural communication style rather than forcing you into someone else's template. A confident speaker with a whiteboard and genuine understanding will always outperform a uncomfortable speaker clicking through borrowed slides.

## When to Use / When to Avoid
This is an antipattern and should always be avoided. If you must present material originally created by someone else, always rework it to fit your style before presenting. The degree of rework depends on available time: at minimum, rewrite speaker notes in your own voice and resequence slides to match your rhythm. At best, rebuild the deck entirely using the original as a content guide.

The one exception is a deliberate, rehearsed co-presentation where the original creator coaches the second presenter through the material, transfers the contextual knowledge, and helps the second presenter internalize the timing and emphasis. This transforms Borrowed Shoes into a genuine collaboration.

## Detection Heuristics
When scoring talks, watch for signs of disconnect between the presenter and the slides: hesitation at transitions (suggesting unfamiliarity with slide order), mismatched verbal emphasis (the presenter stresses different points than the slide design emphasizes), visual style inconsistent with the presenter's other materials, and inability to answer detailed questions about design or content choices. A presenter who says "I believe this slide is about..." or "I think the original author intended..." is exhibiting classic Borrowed Shoes signals.

## Scoring Criteria
- Strong signal (2 pts): Slides clearly reflect the presenter's own style, voice, and rhythm, with seamless integration between spoken delivery and visual design
- Moderate signal (1 pt): Some adaptation of borrowed material visible — speaker notes in the presenter's voice, some slides modified — but occasional friction between presenter style and slide design
- Absent (0 pts): Presenter clearly working from someone else's slides with no adaptation — visible discomfort at transitions, mismatched emphasis, inability to explain design choices

## Relationship to Vault Dimensions
Dimension 7 (Language and Communication): Borrowed Shoes creates a mismatch between the presenter's natural communication style and the language embedded in the slides, producing awkward phrasing and forced delivery. Dimension 8 (Slide Design): The design choices in borrowed slides reflect someone else's visual thinking, creating a disconnect that the audience perceives even if they cannot articulate it. Dimension 14 (Overall Quality Indicators): A presenter working from borrowed material almost always delivers at a lower quality level than their natural capability, depressing overall presentation quality.

## Combinatorics
Borrowed Shoes is mitigated by the Crucible pattern (intensive rehearsal transforms unfamiliar material into internalized content), the Narrative Arc pattern (understanding the story structure helps the presenter navigate borrowed material), and the Carnegie Hall pattern (deliberate practice reduces the friction of presenting someone else's slides). When these patterns are applied rigorously, the worst effects of Borrowed Shoes can be reduced — though the ideal solution remains reworking the material to fit the presenter's own style.

## Related Reading
- Reynolds, G. (2012). *Presentation Zen: Simple Ideas on Presentation Design and Delivery* (2nd ed.). Ch. 6 — argues against using corporate or stock templates that don't fit your message. New Riders.
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Ch. 8 — first-impression chaos when a presenter is unprepared with someone else's material: "Garr Reynolds…entered the room upbeat and engaged, shook hands, asked attendees questions" while the unprepared presenter "kept trying to squeeze an entire workday in before the workshop." Wiley.

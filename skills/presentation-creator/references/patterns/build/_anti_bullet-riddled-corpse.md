---
id: bullet-riddled-corpse
name: Bullet-Riddled Corpse
type: antipattern
part: build
phase_relevance:
  - guardrails
  - slides
vault_dimensions: [8, 13, 14]
detection_signals:
  - "text-heavy bullet slides"
  - "audience reading ahead"
  - "slides as speaker notes"
  - "auto-shrunk fonts"
related_patterns: [charred-trail, infodeck]
inverse_of: [vacation-photos, takahashi]
difficulty: foundational
---

# Bullet-Riddled Corpse

## Summary
Slides consisting primarily of bullet points that serve as speaker notes, causing audiences to read ahead while the presenter drones on — a default slide style that kills audience engagement.

## The Pattern in Detail
The Bullet-Riddled Corpse is perhaps the most widespread antipattern in presentation design, so pervasive that many presenters do not even recognize it as a problem. It occurs when slides are filled with bullet points that essentially reproduce the presenter's speaking notes, creating dense walls of text that the audience reads silently at their own pace while the presenter reads aloud at a different pace. The result is a cognitive fork: the audience is simultaneously trying to read the text and listen to the speaker, and both activities suffer. The audience reads faster than the speaker speaks, reaches the last bullet point, and then waits impatiently for the speaker to catch up. Engagement dies, attention wanders, and the presentation becomes an exercise in endurance rather than communication.

The antipattern is named for its lethal effect on audience engagement. When a bullet-filled slide appears on screen, EVERY person in the audience reads EVERY word on the slide instantly. This is not a choice — it is a neurological reflex. Humans are compelled to read text when it appears in their visual field. Once the audience has read all the bullets, there is nothing left for the speaker to reveal, explain, or dramatize. The bullets have preempted the narrative. The speaker becomes redundant — a human audio player reciting text that the audience has already consumed visually. This is why bullet-heavy presentations feel so lifeless despite containing perfectly good information.

The root cause is a conflation of two distinct artifacts: presentations (designed for live performance) and documents (designed for solo reading). Bullet points are an excellent tool for documents — they are scannable, hierarchical, and information-dense. But these same qualities make them terrible for presentations, where the goal is not efficient information transfer but guided narrative experience. When a presenter uses bullet points as their organizational framework, they are unconsciously building a document and then reading it aloud, which is the worst possible format for live communication.

Presentation software bears significant blame for this antipattern. The default templates in PowerPoint, Google Slides, and even Keynote feature "Title and Content" layouts with pre-formatted bullet point placeholders. These defaults implicitly teach millions of presenters that a slide consists of a title followed by bullets. PowerPoint goes further by automatically shrinking font size as you add more bullets, removing the natural resistance that would otherwise limit information density. The software actively enables and conceals the cramming that makes Bullet-Riddled Corpse slides possible.

It is important to note that bullet points are not inherently evil — they are simply inappropriate for presentation slides. The same content that creates a Bullet-Riddled Corpse on a projected slide works perfectly well in an Infodeck designed for solo consumption. The distinction is context: if the artifact is meant to be read without a presenter, bullets are appropriate. If the artifact accompanies a live speaker, bullets compete with the speaker and should be eliminated in favor of images, diagrams, single phrases, or other visual treatments that complement rather than duplicate the spoken word.

## When to Use / When to Avoid
This is an antipattern and should always be avoided in presentation slides. Replace bullet points with images, diagrams, single keywords, or short phrases that complement your spoken narrative rather than duplicating it. If you need bullets for reference material, place them in the Coda section or in a separate Infodeck.

The one exception is when you are deliberately creating an Infodeck — a slide deck designed for solo consumption without a presenter. In that context, bullet points are appropriate and useful. But if you are presenting live, every bullet on your slide is a competitor for your audience's attention.

## Detection Heuristics
When scoring talks, count the proportion of slides that consist primarily of bullet points (three or more text bullets occupying the majority of the slide). Note whether the audience appears to be reading ahead of the speaker. Look for auto-shrunk fonts (inconsistent text sizes that indicate PowerPoint has compressed the text to fit). Also note if the presenter is reading bullet points verbatim from the slide.

## Scoring Criteria
- Strong signal (2 pts): Slides use visual communication — images, diagrams, single phrases, key words — rather than bullet points, with spoken narration providing the detail that would otherwise be in bullets
- Moderate signal (1 pt): Mix of bullet-heavy slides and visual slides, or bullets present but kept to three or fewer short items per slide
- Absent (0 pts): Majority of slides are bullet-point lists of four or more items, presenter reads bullets from slides, fonts are auto-shrunk to accommodate text volume

## Relationship to Vault Dimensions
Dimension 8 (Slide Design): Bullet-Riddled Corpse is a fundamental failure of slide design that misunderstands the purpose of projected visuals in a live presentation. Dimension 13 (Slide Aesthetics): Text-heavy bullet slides are among the least aesthetically pleasing slide formats, producing dense, uniform visual patterns that numb the audience. Dimension 14 (Overall Quality Indicators): The prevalence of bullet-point slides is one of the most reliable negative indicators of overall presentation quality.

## Combinatorics
Bullet-Riddled Corpse is the inverse of both Vacation Photos (image-centric slides with minimal text) and Takahashi (slides with single large words or phrases). It often co-occurs with Cookie Cutter (cramming ideas into slide-sized containers) and Ant Fonts (shrinking text to fit more bullets). The Charred Trail pattern (leaving breadcrumbs of previous content) and the Infodeck pattern (document-style decks) both represent contexts where text density is more appropriate. Breaking free from Bullet-Riddled Corpse often requires fundamental rethinking of how slides function in a live presentation.

## Related Reading
- Reynolds, G. (2012). *Presentation Zen: Simple Ideas on Presentation Design and Delivery* (2nd ed.). Ch. 6 — "How Many Bullet Points Per Slide?" and the "1-7-7 Rule" critique. New Riders.
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Ch. 8 — "Wean Yourself from the Slides": audiences can read OR listen, not both, so a default-template bulleted slide costs ~25 seconds of read-time per slide that the audience is NOT spending listening to the speaker. Wiley.

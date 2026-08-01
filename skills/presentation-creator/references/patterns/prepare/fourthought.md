---
id: fourthought
name: Fourthought
type: pattern
part: prepare
phase_relevance:
  - intent
  - architecture
vault_dimensions: [2, 8]
detection_signals:
  - "ideation, capture, and organization artifacts predate slide authoring"
  - "speaker confirms the four-phase preparation workflow"
related_patterns: [unifying-visual-theme, backtracking, narrative-arc]
inverse_of: [cookie-cutter, injured-outlines]
difficulty: foundational
observable: false
---

# Fourthought

## Summary
Stay away from the presentation tool as long as possible. Use four phases: ideate, capture, organize, and design.

## The Pattern in Detail
Fourthought is a disciplined approach to presentation creation that insists on separating thinking from tooling. The name encodes both "forethought" (thinking ahead) and "four thought" (four phases of thinking). The core principle is simple: stay away from PowerPoint, Keynote, Google Slides, or whatever presentation tool you use for as long as humanly possible. The tool should be the last thing you touch, not the first.

The four phases are: ideate, capture, organize, and design. In the ideate phase, you think freely about your topic without any constraints. What are the key ideas? What stories do you want to tell? What does the audience need to understand? In the capture phase, you record these ideas in whatever medium works for you — sticky notes, mind maps, outlines, voice memos, napkin sketches. In the organize phase, you arrange the captured ideas into a coherent structure, finding the Narrative Arc and identifying the logical flow. Only in the design phase do you open the presentation tool and begin creating slides.

The reason for this discipline is that presentation tools impose a particular way of thinking. The moment you open a slide editor, you start chopping concepts into slide-sized bites. This is the Cookie Cutter antipattern — letting the tool's constraints shape your ideas rather than letting your ideas shape the tool's output. Stuart Halloway offers a memorable analogy: it takes three morning runs to compose a blog entry and 15 minutes to write it. The thinking is the work; the typing is merely transcription. If building slides is the most time-consuming part of your preparation, you are doing it wrong.

The practical benefits are significant. When you think before you design, your ideas have room to breathe and connect in unexpected ways. You discover relationships between concepts that would have been invisible if each concept were trapped in its own slide from the start. You find the natural groupings and sequences that form the backbone of a strong presentation. You avoid the common trap of having 47 slides that each make sense individually but collectively tell no coherent story.

Fourthought also makes revision dramatically easier. When your ideas live in a mind map or an outline, reorganizing them is trivial — move a sticky note, reorder a list. When those same ideas are embedded in formatted slides with animations and images, reorganizing requires painful slide-by-slide reconstruction. Front-loading the thinking means the expensive design work happens only once, on a structure that has already been validated.

## When to Use / When to Avoid
Use this pattern for every presentation of any significance. The only exception might be a quick internal update where you are essentially filling in a pre-existing template with new data. Even then, spending five minutes thinking before opening the tool will improve the result. The pattern scales — a five-minute lightning talk benefits from Fourthought just as much as a 90-minute keynote.

## Detection Heuristics
Do not infer preparation order from a well-organized result. Verify Fourthought
only from ideation, capture, and organization artifacts that predate the deck, or
from speaker confirmation of the four-phase workflow. A coherent talk without
those sources is unevaluable, not evidence that the process occurred.

## Scoring Criteria
- Strong signal: Dated ideation, capture, and organization artifacts all predate slide authoring and show the four-phase workflow
- Moderate signal: Some pre-slide ideation/organization artifacts exist, but one phase is undocumented
- Absent: Creation history shows slide authoring began before any captured ideation or organization
- Unevaluable: Preparation artifacts or speaker confirmation are unavailable

## Relationship to Vault Dimensions
Relates to Dimension 2 (Structure/Organization). Relates to Dimension 8 (Slide Design/Visual Quality).

## Combinatorics
Pairs naturally with Narrative Arc (Fourthought's organize phase is where you discover your arc), Unifying Visual Theme (the design phase is where visual themes are applied to already-organized ideas), and Backtracking (having a clear structure makes it easy to reference earlier material). Fourthought is the inverse of Cookie Cutter — where Cookie Cutter lets the tool drive the thinking, Fourthought insists that thinking drives the tool.

---
id: injured-outlines
name: Injured Outlines
type: antipattern
part: build
phase_relevance:
  - guardrails
vault_dimensions: [8, 14]
detection_signals:
  - "single sub-bullet under headers"
  - "orphaned outline items"
  - "incomplete list hierarchies"
related_patterns: [fourthought]
inverse_of: [fourthought]
difficulty: foundational
---

# Injured Outlines

## Summary
Outlines and bulleted lists with only one item at a given hierarchical level, indicating incomplete thinking — if a heading has only one subheading, the subheading IS the heading.

## The Pattern in Detail
Injured Outlines is the antipattern of creating hierarchical outlines or bulleted lists where one or more levels contain only a single item. The term captures the idea that the outline is damaged — structurally broken in a way that reveals incomplete thinking beneath the surface. The rule is simple and comes from centuries of rhetorical tradition: if you subdivide, you must subdivide into at least two parts. A heading with only one subheading is not subdividing at all; the single subheading is the heading, and the apparent parent heading is a superfluous label that adds a level of indirection without adding meaning.

Consider a slide that reads: "Performance Concerns" followed by a single sub-bullet: "Database queries are slow." This is an Injured Outline. The sub-bullet is not a subdivision of "Performance Concerns" — it IS the performance concern. The slide should simply read "Database queries are slow" and eliminate the false hierarchy. Now consider a properly formed outline: "Performance Concerns" followed by two sub-bullets: "Database queries are slow" and "API response times exceed SLA." This is a genuine subdivision because the heading ("Performance Concerns") meaningfully groups two distinct items.

The reason Injured Outlines indicate incomplete thinking is that they reveal moments where the presenter started to organize ideas but stopped before the organization was complete. The single sub-bullet is often the first thought that came to mind, and the presenter moved on without asking "what are the OTHER items at this level?" This question — "what else belongs here?" — is the fundamental act of analytical thinking, and skipping it produces content that is shallow by definition. The Fourthought pattern, with its emphasis on brainstorming and categorization, is the direct antidote: thorough ideation naturally produces multiple items at each level.

Injured Outlines are especially prevalent in presentations that were created by starting in the presentation tool rather than starting with a separate ideation process. When a presenter opens PowerPoint or Keynote and begins typing bullets directly onto slides, the tool's linear workflow encourages a "write it down and move on" mentality that does not pause for completeness checks. By contrast, when a presenter uses Fourthought to brainstorm on index cards, a whiteboard, or a mind-mapping tool before touching the presentation software, the spatial arrangement of ideas makes single-child hierarchies visually obvious and easy to correct.

The fix for Injured Outlines is not always to add more sub-bullets. Sometimes the correct fix is to promote the orphaned sub-bullet to its parent's level, eliminating the unnecessary hierarchy. Other times, the correct fix is to think more deeply about the topic and discover the additional items that belong at that level. Occasionally, the correct fix is to realize that the hierarchy is wrong entirely and restructure the outline. The important thing is to never leave a single-child hierarchy in place, because it always signals either incomplete thinking or unnecessary structural complexity — and both are problems worth fixing.

## When to Use / When to Avoid
This is an antipattern and should always be avoided. Every level of every outline or bulleted list in your presentation should contain at least two items. If you find yourself with a single sub-bullet, stop and ask: is this the only item at this level (in which case, promote it), or have I not thought hard enough about what else belongs here (in which case, brainstorm more)?

## Detection Heuristics
When scoring talks, examine every bulleted list and hierarchical outline for single-child levels. A heading with exactly one sub-bullet is the canonical signal. Also look for outlines that have inconsistent depth — one section with three levels of nesting while another has only one level — which may indicate Injured Outlines that were partially addressed but not fully resolved.

## Scoring Criteria
- Strong signal (2 pts): All outlines and bulleted lists have at least two items at every level, indicating thorough and complete hierarchical thinking
- Moderate signal (1 pt): Most outlines are well-formed, with one or two instances of single-child hierarchies that do not significantly impact comprehension
- Absent (0 pts): Multiple instances of single sub-bullets under headings, orphaned outline items, or hierarchies that add structural complexity without adding meaning

## Relationship to Vault Dimensions
Dimension 8 (Slide Design): Injured Outlines represent a structural flaw in slide content organization that undermines the clarity of information architecture. Dimension 14 (Overall Quality Indicators): The presence of Injured Outlines is a reliable signal of insufficient preparation and incomplete analytical thinking, directly impacting the perceived quality of the presentation.

## Combinatorics
Injured Outlines is the inverse of the Fourthought pattern, which emphasizes thorough brainstorming and categorization that naturally produces complete hierarchies. When Fourthought is applied rigorously, Injured Outlines do not occur. The antipattern often co-occurs with other preparation-related issues, as the incomplete thinking that produces Injured Outlines tends to manifest in other areas of the presentation as well.

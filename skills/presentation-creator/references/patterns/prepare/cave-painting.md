---
id: cave-painting
name: Cave Painting
type: pattern
part: prepare
phase_relevance:
  - architecture
  - slides
vault_dimensions: [5, 13]
detection_signals:
  - "canvas-based layout"
  - "zoom transitions"
  - "spatial organization"
  - "visible overall structure"
related_patterns: [context-keeper, soft-transitions, brain-breaks, takahashi, lipsync]
inverse_of: []
difficulty: advanced
---

# Cave Painting

## Summary
Use a huge canvas with your presentation laid out linearly, zooming in and out on sections as you proceed.

## The Pattern in Detail
The Cave Painting pattern takes its name from the idea of a massive wall — like the walls of prehistoric caves — where an entire story is laid out visually in one continuous space. In presentation terms, this means placing all your content on a single enormous canvas and using zoom transitions to navigate between sections. Instead of discrete slides that replace each other, the audience sees the camera moving across a landscape of content, zooming into a section for detail and pulling back out to show how that section fits into the whole.

This approach works exceptionally well for fractal subjects — topics where both the overall structure and the individual subtopics make visual sense when seen as parts of a larger whole. A software architecture diagram, for example, can serve as the canvas: zoom into the authentication module to discuss security, pull back to see how it connects to the API gateway, then zoom into the data layer. The audience always knows where they are in relation to the whole because the whole remains visible during transitions. This makes Cave Painting a specialized form of Context Keeper.

The spatial organization of a Cave Painting presentation adds a dimension of meaning that linear slides cannot provide. Proximity communicates relationship — topics placed near each other on the canvas are implicitly related. Direction communicates progression — moving left to right or top to bottom suggests temporal or logical sequence. The canvas itself becomes a mental map that the audience constructs and navigates alongside the speaker. Research on spatial memory suggests that people recall spatially organized information more readily than linearly organized information.

Tools like Prezi, which popularized this approach, make Cave Painting technically accessible. However, the tool's capability comes with a significant hazard: motion sickness. Rapid zooming, especially combined with rotation, can cause genuine physical discomfort in audience members. The solution is restraint — zoom smoothly and at moderate speed, minimize rotational transitions, and avoid the temptation to show off the tool's full range of motion effects. The zoom should serve comprehension, not spectacle. If an audience member closes their eyes during a transition, you have overdone it.

Creating a Cave Painting presentation requires thinking about spatial relationships during the Fourthought phase. Where you place content on the canvas is a design decision with semantic meaning, unlike linear slides where the only relationship is sequence. This additional dimension of planning is both the pattern's power and its challenge — it demands that you understand your material well enough to map it spatially, which not all topics lend themselves to.

## When to Use / When to Avoid
Use Cave Painting for topics with inherent spatial or hierarchical structure: system architectures, process flows, geographic data, organizational structures, or any subject where seeing the whole while examining parts adds value. Avoid for strictly linear narratives that do not benefit from spatial context, for audiences known to be sensitive to motion, or when the presentation will be viewed primarily as exported slides (the spatial relationship is lost in a PDF export).

## Detection Heuristics
The vault should look for evidence of canvas-based spatial organization: zoom transitions between sections, a visible overall structure that contextualizes individual sections, and the characteristic "pull back to see the whole, zoom in for detail" rhythm.

## Scoring Criteria
- Strong signal (2 pts): Canvas-based layout with meaningful spatial organization; smooth zoom transitions; overall structure visible and contextualized; spatial relationships reinforce content relationships
- Moderate signal (1 pt): Some spatial organization but not fully exploited; transitions present but occasionally disorienting; overall structure partially visible
- Absent (0 pts): Standard linear slides with no spatial dimension; no zoom or canvas-based transitions

## Relationship to Vault Dimensions
Relates to Dimension 5 (Storytelling/Narrative) because the spatial canvas creates a visual narrative that parallels the verbal one. Relates to Dimension 13 (Visual Aids Effectiveness) because the canvas-based approach maximizes the information-carrying capacity of visual presentation.

## Combinatorics
Pairs with Context Keeper (Cave Painting is inherently a context-keeping device), Soft Transitions (zooming between sections creates smooth visual transitions), Brain Breaks (the zoom-out moments serve as visual palate cleansers), Takahashi (individual zoomed-in sections can use Takahashi-style single elements), and Lipsync (spatial layout helps synchronize verbal and visual content).

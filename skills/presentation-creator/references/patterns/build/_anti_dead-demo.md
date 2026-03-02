---
id: dead-demo
name: Dead Demo
type: antipattern
part: build
phase_relevance:
  - guardrails
vault_dimensions: [11, 14]
detection_signals:
  - "purposeless demo"
  - "demo as time filler"
  - "no narrative connection to demonstration"
related_patterns: [live-demo, a-la-carte-content]
inverse_of: [live-demo]
difficulty: foundational
---

# Dead Demo

## Summary
Using a live demonstration as a time filler when the presenter is short on expositional content, resulting in a purposeless demo with no narrative connection — just clicking through menus without story or context.

## The Pattern in Detail
The Dead Demo antipattern occurs when a presenter fills time with a live demonstration that serves no narrative purpose. Unlike the Live Demo pattern — where the demonstration proves a point, advances the story, and gives the audience concrete evidence to support abstract claims — a Dead Demo exists solely because the presenter did not have enough prepared content to fill their time slot. The demonstration meanders through features, clicks through menus, and shows capabilities without any framing of why the audience should care. It is a demonstration of nothing in particular, for no particular reason, that happens to consume minutes the presenter could not otherwise account for.

The telltale sign of a Dead Demo is the absence of narrative scaffolding. A legitimate Live Demo is preceded by a problem statement ("Here's the challenge we face"), accompanied by commentary ("Watch what happens when I click this — notice how the system responds"), and followed by synthesis ("What you just saw demonstrates the principle we discussed"). A Dead Demo, by contrast, begins with "Let me show you the tool" and proceeds with "And here you can see this feature... and over here is this other feature... and if I click here you can see this..." The presenter is narrating their screen activity without connecting it to any larger point. The audience watches politely but retains nothing because there is nothing to retain — no story, no problem, no resolution.

The root cause of Dead Demo is almost always insufficient preparation. The presenter was allocated a forty-five-minute slot, prepared thirty minutes of expositional content, and decided to "fill the rest with a demo." This backward construction — demo as padding rather than demo as proof — guarantees a Dead Demo because the demonstration was not designed to support the narrative; it was tacked on to fill a gap. Proper demo integration requires the demonstration to be planned alongside the expositional content, with each demo moment corresponding to a narrative beat that the demo proves or illustrates.

Dead Demos are particularly damaging because they often occupy the final portion of a talk — the time slot where the audience expects a climax, a synthesis, or a call to action. Instead, they get a meandering tour of a tool's interface that gradually drains the energy and engagement the presenter built during the expositional portion. The audience's attention declines, early departures begin, and the presenter finishes to polite but lukewarm applause. The strong opening and middle of the talk are overshadowed by the weak, purposeless ending.

The fix for Dead Demo is structural, not cosmetic. If you do not have enough prepared content for your time slot, the answer is to prepare more content or request a shorter slot — not to pad with a demonstration. If you want to include a demonstration, plan it as part of your content from the beginning. Define what the demo will prove, script the sequence, rehearse the narration, and position it at the point in your narrative where concrete evidence will be most impactful. A well-integrated five-minute demo is infinitely more valuable than a purposeless twenty-minute tour of features. Consider the A-la-Carte Content pattern as an alternative: prepare optional content modules that can expand or contract to fill available time without resorting to unstructured demos.

## When to Use / When to Avoid
This is an antipattern and should always be avoided. Never use a demonstration as a time filler. Every demonstration in a presentation should serve a clear narrative purpose, prove a specific point, or provide concrete evidence for an abstract claim.

If you find yourself reaching for a demo because you have time to fill, stop and prepare more expositional content instead. If you genuinely want to include a demo, integrate it into your narrative from the beginning rather than appending it as an afterthought.

## Detection Heuristics
When scoring talks, evaluate whether each demonstration is preceded by a problem statement and followed by a synthesis. Demos that begin with "let me show you the tool" without narrative framing are strong Dead Demo signals. Also note the demo's position in the talk — demos placed at the end as apparent time fillers are suspicious. Watch the audience during the demo: if engagement drops visibly, the demo is likely serving as padding rather than content.

## Scoring Criteria
- Strong signal (2 pts): All demonstrations are narratively motivated — preceded by a problem or question, accompanied by purposeful commentary, and followed by synthesis that connects the demo to the larger message
- Moderate signal (1 pt): Demonstrations are partially integrated with the narrative — some framing present but incomplete, or demo content occasionally drifts into feature touring without clear purpose
- Absent (0 pts): Demonstrations used as time fillers with no narrative connection, feature touring without context, audience engagement visibly declining during demo sections

## Relationship to Vault Dimensions
Dimension 11 (Demonstrations and Tools): Dead Demo is the anti-form of demonstration — tool interaction that fails to serve any communicative purpose, degrading rather than enhancing the presentation's engagement with tools and technology. Dimension 14 (Overall Quality Indicators): A purposeless demonstration is one of the most visible quality failures in a technical presentation, signaling insufficient preparation and weak narrative design.

## Combinatorics
Dead Demo is the inverse of the Live Demo pattern. Where Live Demo integrates demonstration into narrative with clear purpose and preparation, Dead Demo uses demonstration as a substitute for narrative. The A-la-Carte Content pattern offers a structural alternative: instead of padding with an unstructured demo, prepare modular content segments that can expand or contract to fill available time. The relationship between Dead Demo and Live Demo is not one of degree but of intent — the same technical actions can constitute either pattern depending on narrative purpose.

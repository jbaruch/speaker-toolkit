---
id: live-demo
name: Live Demo
type: pattern
part: build
phase_relevance:
  - architecture
  - content
vault_dimensions: [11]
detection_signals:
  - "live software demonstration"
  - "real-time tool interaction"
  - "unscripted product showcase"
related_patterns: [lipsync, traveling-highlights]
inverse_of: [dead-demo]
difficulty: advanced
---

# Live Demo

## Summary
Running a product live in front of the audience carries significant credibility but equally significant risk of failure — a demonstration OF something rather than a presentation ABOUT something.

## The Pattern in Detail
The Live Demo is one of the most powerful and most dangerous patterns in a presenter's arsenal. When you demonstrate software, a tool, a framework, or a system live in front of an audience, you are making an implicit promise: "This is real, and I am confident enough to show you it working right now." The credibility boost of a successful live demo is enormous. The audience sees the thing in action, not as a curated screenshot or a carefully edited recording, but as a living, breathing system responding to real input in real time. This transforms abstract claims into concrete proof.

However, the risks are equally substantial. Networks fail. Servers go down. API keys expire. Databases lose connectivity. Dependencies update overnight and break backward compatibility. Screen resolutions change between your practice environment and the projector. Font rendering differs across operating systems. A live demo that fails catastrophically can destroy not just the demo segment but the entire presentation, because the audience loses confidence in everything else you have said. They begin to wonder: if the product does not work, how reliable is anything else this person has told me?

The key to successful Live Demo execution is relentless preparation and layered backup plans. First, practice the exact demo sequence at least ten times, ideally on the same hardware and network you will use during the presentation. Second, prepare a recorded backup (the Lipsync pattern) that you can switch to seamlessly if the live version fails. Third, have a set of screenshots that capture each major step of the demo, so you can walk through the flow even if neither the live version nor the recording works. Fourth, script your recovery — know exactly what you will say if something breaks, and frame it as a learning moment rather than a disaster.

The distinction between Live Demo and the Dead Demo antipattern is crucial. A Live Demo is a demonstration that serves the narrative — it is embedded in a story, it proves a point, it builds toward a conclusion. The audience understands why they are watching the demo and what they should take away from it. A Dead Demo, by contrast, is a demonstration used as a time filler, with no narrative purpose, no context, and no insight. The same technical action can be either a Live Demo or a Dead Demo depending entirely on how it is framed and why it exists in the presentation.

Live Demos are most effective when they are short, focused, and integrated into the flow of the talk. The ideal live demo lasts three to five minutes, demonstrates one or two key capabilities, and then returns to slides that contextualize what the audience just saw. Extended demos of fifteen or twenty minutes test even the most engaged audience's patience and multiply the probability of something going wrong. If you need to demonstrate a lengthy workflow, consider breaking it into multiple short demos interspersed with expositional slides, or use the Lipsync pattern for the longer segments and reserve live interaction for the most impactful moments.

## When to Use / When to Avoid
Use Live Demo when the credibility of showing something working in real time is essential to your message. Product launches, developer tools, and technical architecture talks all benefit from the proof that a live demo provides. Use it when the audience would be skeptical of claims made with only slides and screenshots.

Avoid Live Demo when the risk outweighs the benefit — for example, when your network connectivity is uncertain, when the system is unstable, or when you have not had sufficient time to practice. Also avoid it when the demo does not serve the narrative; if you are demonstrating for the sake of demonstrating, you have crossed into Dead Demo territory.

## Detection Heuristics
When scoring talks, watch for moments where the presenter leaves the slide deck and interacts with a live system. Note whether the demo is framed with context (why are we watching this?) and whether the presenter returns to slides afterward to synthesize what was shown. Also observe whether the presenter appears confident and rehearsed or anxious and improvising during the demo.

## Scoring Criteria
- Strong signal (2 pts): Well-rehearsed live demonstration that serves the narrative, is appropriately scoped, and includes visible backup preparedness (e.g., seamless recovery from a glitch, or mention of recorded fallback)
- Moderate signal (1 pt): Live demonstration present but either too long, not well-integrated with the narrative, or showing signs of insufficient rehearsal
- Absent (0 pts): No live demonstration when one would have strengthened the talk, or a demonstration that fails without recovery, or a Dead Demo used as time filler

## Relationship to Vault Dimensions
Dimension 11 (Demonstrations and Tools): Live Demo is the primary pattern for this dimension, representing the highest-risk, highest-reward approach to showing tools and systems in action during a presentation.

## Combinatorics
Live Demo pairs critically with the Lipsync pattern, which serves as its safety net — a pre-recorded version of the demo that can be substituted if the live version fails. It also works well with Traveling Highlights, which can be used on slides before and after the demo to focus attention on specific parts of what was just demonstrated. The Dead Demo antipattern is its inverse, representing purposeless demonstration that wastes audience time.

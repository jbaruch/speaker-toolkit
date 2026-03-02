---
id: lipsync
name: Lipsync
type: pattern
part: build
phase_relevance:
  - content
  - slides
vault_dimensions: [11, 13]
detection_signals:
  - "recorded demo playback"
  - "embedded video of tool interaction"
  - "narrated screen recording"
related_patterns: [live-demo, cave-painting, live-on-tape]
inverse_of: []
difficulty: intermediate
---

# Lipsync

## Summary
Record your tool interaction and play it back as part of the presentation, reducing stress, preventing errors, and enabling voiceover narration instead of risking a live demonstration.

## The Pattern in Detail
Lipsync is the practice of pre-recording a demonstration of a tool, system, or workflow and embedding the recording directly into your presentation, narrating over it live as it plays. The name evokes the idea of lip-syncing to a pre-recorded track — your voice is live, but the visuals are pre-recorded, giving you the best of both worlds: the appearance of a live demonstration with none of the risk. The audience rarely notices or cares that the demo is recorded, and even if they do, the quality of a well-produced recording typically exceeds what a live demo would deliver under the pressure of a stage.

The primary motivation for Lipsync is risk reduction. Live demos are notoriously fragile. Network connectivity, server availability, API rate limits, software updates, screen resolution differences, and sheer bad luck can all conspire to make a live demo fail at the worst possible moment. A Lipsync recording, by contrast, is deterministic — it plays the same way every time, regardless of the venue's network or the alignment of the stars. This frees the presenter to focus entirely on narration and audience engagement rather than anxiously watching a cursor and praying that the next click produces the expected result.

Creating an effective Lipsync recording requires careful planning. Record at the highest resolution your presentation tool supports, and ensure the recording dimensions match your slide deck's aspect ratio. Perform the demonstration at a deliberate, slightly slower pace than you would naturally — what feels slow to you will feel comfortable to an audience seeing the workflow for the first time. Remove or mask any sensitive information (API keys, passwords, personal data) before recording. Edit out pauses, typos, and dead time to produce a clean, focused recording that shows only the essential steps.

The embedding technique matters. In Keynote, you can embed a video directly on a slide and set it to play automatically when the slide advances. In PowerPoint, the process is similar. Some presenters prefer to use a full-screen video that replaces the slide entirely during the demo segment, while others embed the video in a window on a slide that also contains annotations, callouts, or key points. The choice depends on the complexity of what you are showing and whether the audience needs contextual information alongside the demo.

One subtle advantage of Lipsync over Live Demo is the ability to control pacing and emphasis. In a live demo, you are at the mercy of loading times, network latency, and your own typing speed. In a Lipsync recording, you can speed up tedious portions (file downloads, compilation, deployment) and slow down or pause on critical moments. You can add visual emphasis — zoom effects, highlight boxes, cursor enlargement — that would be impossible to produce in real time. The result is a polished, professional demonstration that communicates more effectively than even a flawless live demo could.

## When to Use / When to Avoid
Use Lipsync whenever you need to show a tool or system in action and the risk of a live demo outweighs the credibility benefit. It is especially valuable when network connectivity is uncertain, when the demo involves external services you cannot control, or when the demonstration includes steps that take significant time to complete (compilation, deployment, data processing).

Avoid Lipsync when the live, real-time nature of the demonstration is the point — for example, when you are explicitly showing that a system responds in real time, or when audience participation is part of the demo. Also avoid it if the recording quality would be poor (low resolution, bad audio, visible UI artifacts) — a bad recording is worse than a competent live demo.

## Detection Heuristics
When scoring talks, look for embedded video playback during demonstration segments. Indicators include perfectly smooth mouse movements, absence of typing errors, consistent pacing, and the presenter speaking naturally without looking at the projected screen. A presenter who narrates confidently without monitoring the demo is likely using Lipsync.

## Scoring Criteria
- Strong signal (2 pts): High-quality embedded recording with live narration, smooth pacing, appropriate editing, and seamless integration with the surrounding slides
- Moderate signal (1 pt): Recorded demo present but with quality issues (low resolution, unedited dead time, poor integration with slides) or overly long
- Absent (0 pts): No recorded demo when one would have been appropriate, or a risky live demo used where Lipsync would have been safer and more effective

## Relationship to Vault Dimensions
Dimension 11 (Demonstrations and Tools): Lipsync is the risk-managed alternative to Live Demo for showing tools and systems in action, prioritizing reliability and polish over the credibility of real-time execution. Dimension 13 (Slide Aesthetics): A well-produced Lipsync recording integrated into the slide deck elevates the overall visual quality of the presentation, particularly when enhanced with zoom effects, highlights, and clean editing.

## Combinatorics
Lipsync is the natural complement and safety net for the Live Demo pattern. Many experienced presenters prepare both: they attempt the live demo but have the Lipsync recording ready as an instant fallback. It also pairs well with Cave Painting (static diagrams that can contextualize what the recording shows) and Live-on-Tape (the recording itself becomes part of the distributable artifact). The relationship with Live Demo is symbiotic rather than adversarial — the two patterns work together to maximize both credibility and reliability.

---
id: preroll
name: Preroll
type: pattern
part: build
phase_relevance:
  - slides
  - publishing
vault_dimensions: [1, 13]
evidence_channels: [video]
detection_signals:
  - "pre-talk info slide"
  - "looping intro display"
  - "housekeeping before start"
evaluable_from:
  - delivery_video
strong_evaluable_from:
  - delivery_video
absence_evaluable_from: null
not_applicable_when:
  - condition_id: no-prestart-display-opportunity
    description: "Complete pre-start delivery video establishes an immediate handoff or venue-controlled display with no presenter-controlled screen period before the talk."
applicability_evaluable_from:
  - delivery_video
evidence_requirements:
  - "Delivery video must begin before the official talk start and show what the audience saw while assembling."
  - "A strong score must expose a polished looping sequence with identification, abstract, and housekeeping; a static title slide supports only moderate."
not_evaluable_when:
  - "The recording starts at or after the first spoken line and contains no pre-start display period."
  - "The pre-start screen is cropped, replaced, or otherwise not visible long enough to distinguish a loop from one static frame."
  - "The source does not show the full pre-start interval needed to assess whether a presenter-controlled display opportunity existed."
related_patterns: [seeding-the-first-question]
inverse_of: [abstract-attorney]
difficulty: foundational
---

# Preroll

## Summary
Display topic, presenter info, and housekeeping details on a looping slide before your talk officially begins, showing your name, title, abstract, and reminders such as silencing cell phones.

## The Pattern in Detail
The Preroll is the set of slides or looping visual content that plays on screen before your presentation officially starts. While the audience is filing in, finding seats, and settling down, the Preroll provides useful context: who you are, what the talk is about, any logistical reminders, and other housekeeping details. It transforms dead time into productive time, priming the audience for what they are about to experience and establishing your presence even before you speak your first word.

A well-designed Preroll typically includes your name and title, the title of the presentation, a brief abstract or description of the talk, and practical reminders like "please silence your cell phones." If this information does not fit comfortably on a single slide, the Preroll can be constructed as a series of slides exported as a looping video. This ensures the information cycles continuously for latecomers without requiring any interaction from the presenter, who may be busy with last-minute preparations, microphone checks, or conversations with early arrivals.

One of the Preroll's most valuable secondary functions is defusing the Abstract Attorney antipattern. Abstract Attorneys are audience members who fixate on the published abstract and spend the entire talk evaluating whether the presenter is delivering exactly what was promised. By displaying the abstract prominently in the Preroll, you give these audience members a chance to read and process it before the talk begins. By the time you start speaking, the abstract has been consumed and mentally filed away, reducing the likelihood that someone will derail a Q&A session with "but your abstract said..."

The Preroll also serves as a professional touch that signals preparation and respect for the audience's time. When attendees walk into a room and see a blank screen or a desktop wallpaper, the implicit message is that the presenter has not yet arrived or is not ready. When they see a polished Preroll with clear information, the implicit message is that this presenter is organized, professional, and has thought about the audience experience from the first moment they enter the room. This small detail sets expectations and builds credibility before the talk even begins.

For conferences and events where multiple speakers share a stage, the Preroll is especially important. It helps the audience confirm they are in the right room for the talk they want to see. In large conference venues with multiple tracks, attendees are constantly making decisions about which session to attend, and a clear Preroll that displays the topic and abstract helps them commit to staying rather than wandering to another room.

## When to Use / When to Avoid
Use the Preroll for any in-person presentation where you have control over the display before your talk begins. It is especially valuable at conferences, meetups, and corporate events where the audience is assembling over a period of several minutes. It is also useful for virtual presentations where attendees join a video call early and see your shared screen.

Avoid investing significant effort in a Preroll when you have no control over the display before your talk (for example, when a conference runs a centralized slide loop between sessions) or when the format leaves no gap between the previous speaker and your start.

## Detection Heuristics
When scoring talks, look for evidence of pre-talk content: a title slide displayed before the official start, looping information visible as the audience settles, or the presenter referencing information that was shown beforehand. Ask whether the presenter used the pre-talk period productively or let it go to waste.

## Scoring Criteria
- Strong signal: Polished looping Preroll with name, title, abstract, and housekeeping information displayed before the talk begins, clearly designed for the pre-audience period
- Moderate signal: A static title slide displayed before the talk, providing basic identification but lacking housekeeping or abstract information
- Absent: Blank screen, desktop wallpaper, or no pre-talk visual content visible as the audience assembles

## Evidence Gate
Use `strong_evaluable_from`, `evidence_requirements`, and `not_evaluable_when` above to evaluate positive evidence.
Current catalog artifacts may support positive detection only. Because `absence_evaluable_from` is `null`, no delivery video, transcript, rendered or native deck, comparison artifact, or claim of full coverage authorizes an absence finding; when no positive signal is established, record `not_evaluable`, not `absent`.

## Relationship to Vault Dimensions
Dimension 1 (Topic and Thesis): The Preroll establishes the topic and framing before the talk begins, giving the audience a head start on understanding what they are about to learn. Dimension 13 (Slide Aesthetics): The visual quality of the Preroll sets aesthetic expectations for the entire presentation, making it a first impression of the presenter's design sensibility.

## Combinatorics
The Preroll pairs naturally with Seeding the First Question, as the pre-talk period is an ideal time to plant a provocative question or prompt that primes the audience for engagement. It also works as a counterweight to the Abstract Attorney antipattern by addressing abstract concerns before the talk begins. In the publishing phase, the Preroll can be included as part of a Live-on-Tape recording to provide context for viewers who were not present at the original event.

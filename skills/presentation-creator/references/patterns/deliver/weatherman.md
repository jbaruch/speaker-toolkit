---
id: weatherman
name: Weatherman
type: pattern
part: deliver
phase_relevance:
  - publishing
vault_dimensions: [12]
detection_signals:
  - "speaker faces audience"
  - "uses presenter display"
  - "interacts with slides without turning around"
related_patterns: [make-it-rain, lipsync]
inverse_of: []
difficulty: foundational
---

# Weatherman

## Summary
Face your audience at all times by using the heads-up display on your laptop, like a TV weather reporter uses a green screen. Never turn your back to present.

## The Pattern in Detail
Television weather reporters stand in front of a green screen, gesturing at maps and graphics they cannot see directly. They maintain eye contact with the camera (their audience) by using a monitor positioned just below the camera lens. The Weatherman pattern applies this same principle to presentations: use your laptop's presenter display as a heads-up display so you always face the audience, even when referencing slide content.

The first step is to unmirror your displays. Most operating systems default to mirrored mode, which shows the same content on your laptop and the projector. Switch to extended desktop mode instead, and use your presentation software's presenter view. This gives you the current slide, upcoming slide, speaker notes, and a timer on your laptop screen while the audience sees only the clean slide. Position your laptop where you can glance at it with a slight downward look — far less disruptive than turning 180 degrees to face the projection screen.

The benefits of this approach extend beyond simple audience eye contact. When you face the audience, you can read their reactions. You notice confused expressions that signal you need to slow down or clarify. You see nods of understanding that tell you the message is landing. You catch the raised hand in the back row that you would miss if you were staring at the screen behind you. Turning your back to the audience is not just poor form — it is flying blind.

An advanced technique is to "break the fourth wall" by tapping or gesturing at the projected screen behind you. When you know exactly where an element is positioned (because you can see it on your laptop), you can point at the screen without looking at it, creating an impression of seamless mastery. This is especially effective with diagrams or code samples where you want to direct the audience's attention to a specific area. The audience experiences it as magical — you seem to know exactly where everything is without looking.

The Weatherman pattern also frees you from dependence on laser pointers (see the Laser Weapons antipattern). When you face the audience and use Traveling Highlights or built-in animations to direct attention, you eliminate the need for an external pointing device entirely.

## When to Use / When to Avoid
Use this pattern in every presentation that involves projected slides. It requires a small investment in learning your operating system's display settings and your presentation software's presenter view, but that investment pays dividends immediately. Avoid the Weatherman pattern only in rare scenarios where the venue setup makes it impossible to see your laptop (some stages position the confidence monitor too far away). In those cases, request a confidence monitor or adjust your position.

## Detection Heuristics
- Speaker maintains eye contact with audience throughout
- Speaker references slide content without turning around
- Presenter view or confidence monitor is clearly in use
- Speaker interacts with projected content from a front-facing position

## Scoring Criteria
- Strong signal (2 pts): Speaker faces audience at all times, uses presenter display effectively, interacts with slides without turning around, maintains strong eye contact
- Moderate signal (1 pt): Speaker mostly faces audience but occasionally turns to check the screen
- Absent (0 pts): Speaker frequently turns their back to the audience to read or reference slides

## Relationship to Vault Dimensions
This pattern maps to Vault Dimension 12 (Delivery Mechanics). Facing the audience is a fundamental delivery skill that affects eye contact, audience reading, vocal projection (speaking toward the audience rather than away from them), and overall stage presence.

## Combinatorics
Weatherman pairs naturally with Make It Rain (physical interaction with the projected screen), Lipsync (coordinating live demonstrations with slide content), and the Lightsaber pattern (reducing dependence on laser pointers). It also supports Display of High Value — a speaker who faces the audience with confidence projects more authority than one who repeatedly turns to check the screen. Carnegie Hall rehearsals should incorporate the presenter display setup to build comfort with the technique.

## Related Reading
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Ch. 6 — "Contrast the Delivery" lists alternation between traditional and nontraditional methods (stage stance, style, visuals, interaction, content, involvement) as the third required contrast type alongside content and emotional contrast. Wiley.

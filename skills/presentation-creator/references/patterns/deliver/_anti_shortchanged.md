---
id: shortchanged
name: Shortchanged
type: antipattern
part: deliver
phase_relevance:
  - guardrails
vault_dimensions: [12, 14]
detection_signals:
  - "rushing through material"
  - "visible time pressure"
  - "skipped content"
  - "compressed delivery"
related_patterns: [preparation, expansion-joints, weatherman]
inverse_of: [expansion-joints]
difficulty: foundational
---

# Shortchanged

## Summary
Dealing with a last-minute reduction in presentation time due to previous speakers running long or schedule changes. The key is preparation: know in advance which material is essential and which can be cut without damage.

## The Pattern in Detail
You prepared a fifty-minute talk. You rehearsed it to fit perfectly. You arrive at the venue and discover that the previous speaker ran fifteen minutes over, the organizer apologetically asks if you can fit your talk into thirty-five minutes, and you have approximately ninety seconds to mentally restructure your entire presentation. This is the Shortchanged antipattern — not something you do wrong, but something that happens to you. The quality of your response determines whether the audience notices.

The most common failure mode is the panicked speedup. The speaker tries to deliver fifty minutes of content in thirty-five minutes by talking faster, skipping pauses, and blowing through slides at double speed. The audience experiences a fire hose of information delivered at an incomprehensible pace. The speaker is visibly stressed, which makes the audience uncomfortable. Key points are buried in the torrent, and nothing lands with impact. The speaker finishes on time but has communicated almost nothing effectively.

The correct response requires advance preparation. Before you ever arrive at the venue, you should know which sections of your talk are load-bearing and which are expandable. Label your content mentally (or in your speaker notes) as "must deliver," "nice to have," and "expendable." When you are shortchanged, you cut the expendable material entirely and abbreviate the nice-to-have material, preserving the core message and its supporting evidence at full quality. The audience gets a tighter, more focused talk rather than a compressed mess.

Learn your presentation software's keyboard shortcuts for jumping to specific slides. In Keynote, you can type a slide number and press Enter to jump directly. In PowerPoint, similar shortcuts exist. This lets you skip sections cleanly — the audience never sees the slides you skipped, so they do not know they are getting an abbreviated version. Showing skipped slides (by visibly clicking through them) is the worst possible approach because it telegraphs to the audience that they are getting a diminished experience.

The deeper lesson of Shortchanged is that every talk should be designed with modularity in mind. If your talk falls apart when you remove ten minutes, it was too tightly coupled. The Expansion Joints pattern is the proactive counterpart to this antipattern — build your talk with sections that can be cleanly added or removed based on available time.

## When to Use / When to Avoid
This is an antipattern to be prepared for, not a pattern to apply. You cannot prevent schedule disruptions, but you can prepare for them. Build contingency plans into every talk: know your shortcuts, label your sections, and rehearse the abbreviated version at least once. The preparation phase is when you defend against Shortchanged — by the time it happens, your options are limited to the contingencies you have already built.

## Detection Heuristics
- Speaker visibly accelerates pace partway through the talk
- Slides are skipped or flashed through rapidly
- Speaker mentions time constraints explicitly ("I am running short on time")
- Content feels compressed or incomplete in the final third of the talk

## Scoring Criteria
- Strong signal (2 pts): Speaker handles time reduction gracefully — sections are cleanly omitted, core message is preserved at full quality, audience may not even notice the abbreviation
- Moderate signal (1 pt): Speaker adapts to time pressure but with visible strain — some rushing evident, minor content awkwardness
- Absent (0 pts): Speaker panics under time pressure — visible rushing, compressed delivery, audience clearly receives a degraded experience

## Relationship to Vault Dimensions
This antipattern maps to Vault Dimension 12 (Delivery Mechanics) because the visible symptoms of being shortchanged are pacing and flow disruptions, and to Vault Dimension 14 (Speaker Craft / Professionalism) because handling schedule disruptions gracefully is a hallmark of professional speaker craft.

## Combinatorics
The primary defense against Shortchanged is the Expansion Joints pattern (modular talk design). Preparation supports it by ensuring you know your keyboard shortcuts and have labeled your sections. Carnegie Hall rehearsal should include at least one run of the abbreviated version. The Weatherman pattern helps because a speaker using presenter view can see upcoming slides and make real-time decisions about what to skip.

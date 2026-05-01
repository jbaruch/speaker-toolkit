# Presentation Patterns — Master Index

Structured reference taxonomy primarily based on *Presentation Patterns: Techniques for
Crafting Better Presentations* (Neal Ford, Matthew McCullough, Nathaniel Schutta, 2013),
with supplementary patterns and reinforcements from *Presentation Zen* (Garr Reynolds,
2nd ed., 2012) and *Resonate: Present Visual Stories that Transform Audiences* (Nancy
Duarte, 2010). Contains 72 named patterns and 25 antipatterns organized by presentation
lifecycle phase. See the Sources section at the end of this file for full citations.

**This is the primary entry point.** The agent reads this file first, then drills into
individual pattern files only when detailed descriptions, scoring criteria, or
combinatorics are needed.

## How to Use This Index

1. **During creator Phase 2 (Architecture):** Read the phase-grouped lookup table below
   to find which patterns are relevant at the current phase, then read the pattern files
   for the ones you want to present as options.
2. **During vault Step 3 (Analysis):** Scan against observable patterns only — skip
   patterns marked `observable: false` (pre-event logistics, physical stage behaviors,
   and external systems that leave no trace in transcripts or slides).
3. **During creator Phase 4 (Guardrails):** Read all antipatterns and compare against
   the outline. Flag matches as `[RECURRING]` (from speaker profile) or `[CONTEXTUAL]`
   (new detection). Skip unobservable antipatterns.
4. **During creator Phase 6 (Publishing / Go-Live):** Surface unobservable patterns as
   a go-live preparation checklist — these are actions to take before and during delivery
   that the vault cannot score retroactively.

---

## Pattern Catalog

### Prepare Phase (19 patterns + 3 antipatterns)

| ID | Name | Type | Vault Dims | Creator Phases | Related |
|----|------|------|------------|----------------|---------|
| know-your-audience | Know Your Audience | pattern | 4, 9 | intake | emotional-state, seeding-satisfaction |
| opening-punch | Opening PUNCH | pattern | 1, 4 | intent, content | bookends, narrative-arc, foreshadowing, preroll, know-your-audience |
| social-media-advertising | Social Media Advertising | pattern | 4 | publishing | seeding-satisfaction |
| required | Required | pattern | 9 | intake, intent | proposed, posse, concurrent-creation, crucible |
| the-big-why | The Big Why | pattern | 9 | intake | carnegie-hall, crucible |
| proposed | Proposed | pattern | 9 | intake, intent | required, peer-review, know-your-audience |
| narrative-arc | Narrative Arc | pattern | 2, 5 | intent, architecture, content | triad, bookends, intermezzi, unifying-visual-theme, context-keeper |
| fourthought | Fourthought | pattern | 2, 8 | intent, architecture | unifying-visual-theme, backtracking, narrative-arc |
| crucible | Crucible | pattern | 12, 14 | content | brain-breaks, fourthought, carnegie-hall, traveling-highlights |
| concurrent-creation | Concurrent Creation | pattern | 2, 8 | content | talklet, unifying-visual-theme |
| triad | Triad | pattern | 2 | intent, architecture | narrative-arc, fourthought, talklet |
| expansion-joints | Expansion Joints | pattern | 2, 12 | architecture, content | talklet, narrative-arc |
| talklet | Talklet | pattern | 2, 12 | architecture, content | narrative-arc, foreshadowing, backtracking, a-la-carte-content, expansion-joints |
| unifying-visual-theme | Unifying Visual Theme | pattern | 10, 13 | architecture, slides | brain-breaks, defy-defaults, narrative-arc |
| brain-breaks | Brain Breaks | pattern | 3, 12 | architecture, content | leet-grammars, narrative-arc, entertainment, crucible |
| leet-grammars | Leet Grammars | pattern | 7, 10 | content | analog-noise, brain-breaks |
| lightning-talk | Lightning Talk | pattern | 2, 12 | architecture | talklet, carnegie-hall, fourthought, defy-defaults, narrative-arc |
| takahashi | Takahashi | pattern | 8, 12, 13 | architecture, slides | brain-breaks |
| cave-painting | Cave Painting | pattern | 5, 13 | architecture, slides | context-keeper, soft-transitions, brain-breaks, takahashi, lipsync |
| abstract-attorney | Abstract Attorney | antipattern | 2, 14 | intent, guardrails | preroll, narrative-arc, fourthought, triad, crucible, carnegie-hall |
| alienating-artifact | Alienating Artifact | antipattern | 3, 10, 14 | guardrails | know-your-audience, brain-breaks |
| celery | Celery | antipattern | 2, 14 | guardrails | required, know-your-audience, narrative-arc, brain-breaks |

### Build Phase (34 patterns + 10 antipatterns)

| ID | Name | Type | Vault Dims | Creator Phases | Related |
|----|------|------|------------|----------------|---------|
| sparkline | Sparkline | pattern | 2, 5, 9 | architecture, content | narrative-arc, bookends, big-idea, call-to-adventure, call-to-action, new-bliss |
| call-to-adventure | Call to Adventure | pattern | 1, 2, 9 | architecture, content | sparkline, big-idea, opening-punch, narrative-arc |
| call-to-action | Call to Action | pattern | 4, 6, 9 | content, publishing | sparkline, coda, mentor, big-idea |
| new-bliss | New Bliss | pattern | 5, 6, 9 | content | sparkline, call-to-action, coda, bookends |
| star-moment | S.T.A.R. Moment | pattern | 3, 5, 13 | content, slides | big-idea, sparkline, narrative-arc, vacation-photos, foreshadowing |
| inoculation | Inoculation | pattern | 4, 9 | content, guardrails | know-your-audience, mentor, peer-review, sparkline |
| master-story | Master Story | pattern | 2, 5, 7 | content | narrative-arc, foreshadowing, sparkline, big-idea, star-moment |
| coda | Coda | pattern | 6, 8 | content, slides | infodeck, vacation-photos |
| peer-review | Peer Review | pattern | 7, 8 | content, guardrails | leet-grammars |
| foreshadowing | Foreshadowing | pattern | 2, 5 | content | narrative-arc, talklet, backtracking, intermezzi |
| composite-animation | Composite Animation | pattern | 13 | slides | emergence, gradual-consistency |
| a-la-carte-content | A la Carte Content | pattern | 2, 4 | architecture, content | talklet, coda, live-demo |
| vacation-photos | Vacation Photos | pattern | 8, 13 | architecture, slides | unifying-visual-theme |
| defy-defaults | Defy Defaults | pattern | 13 | slides | analog-noise, bookends, intermezzi |
| analog-noise | Analog Noise | pattern | 13 | slides | defy-defaults, leet-grammars |
| infodeck | Infodeck | pattern | 8 | architecture | coda |
| gradual-consistency | Gradual Consistency | pattern | 8, 13 | slides | exuberant-title-top, composite-animation, analog-noise |
| charred-trail | Charred Trail | pattern | 8, 13 | slides | context-keeper, exuberant-title-top, bookends |
| exuberant-title-top | Exuberant Title Top | pattern | 13 | slides | charred-trail, gradual-consistency |
| invisibility | Invisibility | pattern | 13 | slides | gradual-consistency |
| context-keeper | Context Keeper | pattern | 2, 5, 13 | architecture, content, slides | breadcrumbs, bookends, narrative-arc, charred-trail, cave-painting |
| breadcrumbs | Breadcrumbs | pattern | 2, 13 | content, slides | context-keeper, bookends |
| bookends | Bookends | pattern | 2, 5, 13 | content, slides | context-keeper, narrative-arc, intermezzi, defy-defaults |
| soft-transitions | Soft Transitions | pattern | 5, 13 | slides | intermezzi, cave-painting |
| intermezzi | Intermezzi | pattern | 2, 5, 13 | content, slides | context-keeper, bookends, narrative-arc, unifying-visual-theme, brain-breaks |
| backtracking | Backtracking | pattern | 2, 5 | content | fourthought, foreshadowing, talklet |
| preroll | Preroll | pattern | 1, 13 | slides, publishing | seeding-the-first-question |
| crawling-credits | Crawling Credits | pattern | 6, 13 | slides | coda |
| live-demo | Live Demo | pattern | 11 | architecture, content | lipsync, traveling-highlights |
| lipsync | Lipsync | pattern | 11, 13 | content, slides | live-demo, cave-painting, live-on-tape |
| traveling-highlights | Traveling Highlights | pattern | 11, 13 | slides | crawling-code, emergence |
| crawling-code | Crawling Code | pattern | 11, 13 | slides | traveling-highlights, emergence |
| emergence | Emergence | pattern | 11, 13 | content, slides | composite-animation, traveling-highlights, crawling-code |
| live-on-tape | Live on Tape | pattern | 8 | publishing | lipsync, entertainment |
| cookie-cutter | Cookie Cutter | antipattern | 8, 13 | guardrails, slides | soft-transitions, fourthought |
| injured-outlines | Injured Outlines | antipattern | 8, 14 | guardrails | fourthought |
| bullet-riddled-corpse | Bullet-Riddled Corpse | antipattern | 8, 13, 14 | guardrails, slides | charred-trail, infodeck |
| ant-fonts | Ant Fonts | antipattern | 13, 14 | guardrails, slides | bullet-riddled-corpse, infodeck |
| fontaholic | Fontaholic | antipattern | 13, 14 | guardrails, slides | floodmarks |
| floodmarks | Floodmarks | antipattern | 13, 14 | guardrails, slides | bookends, defy-defaults, unifying-visual-theme |
| photomaniac | Photomaniac | antipattern | 10, 13, 14 | guardrails, slides | unifying-visual-theme, vacation-photos |
| borrowed-shoes | Borrowed Shoes | antipattern | 7, 8, 14 | guardrails | crucible, narrative-arc, carnegie-hall |
| slideuments | Slideuments | antipattern | 8, 14 | guardrails | infodeck, charred-trail, gradual-consistency |
| dead-demo | Dead Demo | antipattern | 11, 14 | guardrails | live-demo, a-la-carte-content |

### Deliver Phase (19 patterns + 12 antipatterns)

| ID | Name | Type | Vault Dims | Creator Phases | Related |
|----|------|------|------------|----------------|---------|
| preparation | Preparation | pattern | 14 | publishing | know-your-audience, carnegie-hall |
| screen-blackout | Screen Blackout | pattern | 12, 13 | content, slides | breathing-room, intermezzi, brain-breaks, mentor |
| carnegie-hall | Carnegie Hall | pattern | 12, 14 | publishing | crucible |
| posse | Posse | pattern | 4 | publishing | greek-chorus, seeding-satisfaction |
| seeding-satisfaction | Seeding Satisfaction | pattern | 4 | publishing | know-your-audience, social-media-advertising |
| seeding-the-first-question | Seeding the First Question | pattern | 4 | content, publishing | preroll, know-your-audience, display-of-high-value, greek-chorus |
| display-of-high-value | Display of High Value | pattern | 9 | content | know-your-audience, mentor |
| shoeless | Shoeless | pattern | 14 | publishing | breathing-room, carnegie-hall, crucible |
| emotional-state | Emotional State | pattern | 4, 9 | intake, content | social-media-advertising, know-your-audience |
| breathing-room | Breathing Room | pattern | 7, 12 | content | narrative-arc, brain-breaks, know-your-audience |
| mentor | Mentor | pattern | 9, 11 | intent, content | narrative-arc, display-of-high-value |
| weatherman | Weatherman | pattern | 12 | publishing | make-it-rain, lipsync |
| entertainment | Entertainment | pattern | 3, 10 | content | know-your-audience, brain-breaks, make-it-rain |
| make-it-rain | Make It Rain | pattern | 4 | content | entertainment, weatherman |
| echo-chamber | Echo Chamber | pattern | 4, 7 | publishing | seeding-the-first-question |
| red-yellow-green | Red, Yellow, Green | pattern | 4 | publishing | crucible, know-your-audience |
| lightsaber | Lightsaber | pattern | 11 | content | traveling-highlights |
| stakeout | The Stakeout | pattern | 14 | publishing | preparation, carnegie-hall |
| greek-chorus | Greek Chorus | pattern | 4, 9 | architecture, content | posse, mentor |
| shortchanged | Shortchanged | antipattern | 12, 14 | guardrails | preparation, expansion-joints, weatherman |
| hiccup-words | Hiccup Words | antipattern | 7, 14 | guardrails | breathing-room, carnegie-hall |
| disowning-your-topic | Disowning Your Topic | antipattern | 9, 12, 14 | guardrails | know-your-audience, crucible |
| going-meta | Going Meta | antipattern | 9, 14 | guardrails | breathing-room, carnegie-hall, crucible |
| bunker | Bunker | antipattern | 4, 14 | guardrails | carnegie-hall, know-your-audience |
| hecklers | Hecklers | antipattern | 4, 14 | guardrails | know-your-audience, display-of-high-value |
| backchannel | Backchannel | antipattern | 4, 14 | guardrails | social-media-advertising, know-your-audience |
| laser-weapons | Laser Weapons | antipattern | 13, 14 | guardrails, slides | traveling-highlights, lightsaber |
| negative-ignorance | Negative Ignorance | antipattern | 4, 14 | guardrails | know-your-audience, seeding-satisfaction |
| dual-headed-monster | Dual-Headed Monster | antipattern | 4, 14 | guardrails | live-on-tape, weatherman |
| tower-of-babble | Tower of Babble | antipattern | 7, 9, 14 | guardrails | know-your-audience, leet-grammars |
| lipstick-on-a-pig | Lipstick on a Pig | antipattern | 8, 9, 14 | guardrails | narrative-arc |

---

## Phase-Grouped Lookup Table

Which patterns to surface at each creator phase:

### Phase 0: Intake
Audience/context patterns — shown as context-setting reminders.

- know-your-audience
- required
- the-big-why
- proposed
- emotional-state

### Phase 1: Intent
Planning patterns — inform spec construction.

- narrative-arc
- fourthought
- triad
- required
- proposed
- mentor
- opening-punch
- abstract-attorney *(antipattern — warn about abstract drift)*

### Phase 2: Architecture
All structural patterns — the main Pattern Strategy selection moment.

**Full 4-tier recommendation using `pattern_profile`:**
- **Signature tier:** Speaker's high-usage patterns from profile
- **Contextual tier:** Patterns matching spec context with occasional speaker usage
- **New to You tier:** From `never_used_patterns`, filtered by spec relevance
- **Shake It Up tier:** Random picks from `never_used_patterns`

Structural patterns relevant here:
- narrative-arc, triad, talklet, expansion-joints, lightning-talk, takahashi, cave-painting
- a-la-carte-content, context-keeper, bookends, intermezzi
- unifying-visual-theme, vacation-photos, infodeck
- brain-breaks, greek-chorus
- live-demo *(if demo-driven mode)*
- sparkline *(if persuasive mode — alternative to narrative-arc)*
- call-to-adventure *(architectural placement of sparkline turning point 1)*

### Phase 3: Content
Build patterns — applied during outline writing.

- foreshadowing, backtracking, brain-breaks, bookends, intermezzi, coda
- breadcrumbs, context-keeper, a-la-carte-content
- live-demo, lipsync, emergence
- leet-grammars, entertainment, breathing-room
- display-of-high-value, mentor, seeding-the-first-question
- make-it-rain, lightsaber, echo-chamber
- opening-punch, screen-blackout
- call-to-adventure, call-to-action, new-bliss, star-moment, inoculation, master-story

### Phase 4: Guardrails
Antipatterns as warnings — scanned against the outline.

**All 25 antipatterns**, with two flag types:
- `[RECURRING]` — from `pattern_profile.antipattern_frequency` (speaker-specific)
- `[CONTEXTUAL]` — detected in the current outline (new detection)

### Phase 5: Slides
Visual/construction patterns — applied during slide generation.

- defy-defaults, composite-animation, vacation-photos, analog-noise
- takahashi, cave-painting, charred-trail, gradual-consistency
- exuberant-title-top, invisibility, soft-transitions
- traveling-highlights, crawling-code, emergence
- preroll, crawling-credits, bookends, intermezzi, breadcrumbs
- screen-blackout
- cookie-cutter, ant-fonts, fontaholic, floodmarks, photomaniac, laser-weapons *(antipatterns)*

### Phase 6: Publishing
Delivery prep patterns — final checklist before the talk.

- preparation, carnegie-hall, seeding-satisfaction, seeding-the-first-question
- posse, shoeless, emotional-state, weatherman, stakeout
- echo-chamber, red-yellow-green
- social-media-advertising, preroll, live-on-tape
- call-to-action *(go-live preparation — confirm asks are concrete and immediately executable)*

---

## Vault Dimension → Pattern Mapping

Reverse lookup: which patterns relate to each of the 14 rhetoric analysis dimensions.

| Dim | Name | Patterns | Antipatterns |
|-----|------|----------|--------------|
| 1 | Opening Pattern | preroll, opening-punch, call-to-adventure | — |
| 2 | Narrative Structure | narrative-arc, fourthought, triad, expansion-joints, talklet, context-keeper, breadcrumbs, bookends, intermezzi, foreshadowing, backtracking, a-la-carte-content, concurrent-creation, lightning-talk, sparkline, call-to-adventure, master-story | abstract-attorney, celery |
| 3 | Humor & Wit | brain-breaks, entertainment, star-moment | alienating-artifact |
| 4 | Audience Interaction | know-your-audience, social-media-advertising, a-la-carte-content, posse, seeding-satisfaction, seeding-the-first-question, emotional-state, make-it-rain, echo-chamber, red-yellow-green, greek-chorus, opening-punch, call-to-action, inoculation | bunker, hecklers, backchannel, negative-ignorance, dual-headed-monster |
| 5 | Transition Techniques | narrative-arc, foreshadowing, backtracking, context-keeper, bookends, intermezzi, soft-transitions, cave-painting, sparkline, new-bliss, star-moment, master-story | — |
| 6 | Closing Pattern | coda, crawling-credits, call-to-action, new-bliss | — |
| 7 | Verbal Signatures | leet-grammars, peer-review, breathing-room, echo-chamber, master-story | hiccup-words, borrowed-shoes, tower-of-babble |
| 8 | Slide-to-Speech Relationship | fourthought, concurrent-creation, coda, vacation-photos, infodeck, gradual-consistency, charred-trail, takahashi, live-on-tape, peer-review | cookie-cutter, injured-outlines, bullet-riddled-corpse, borrowed-shoes, slideuments, lipstick-on-a-pig |
| 9 | Persuasion Techniques | know-your-audience, required, the-big-why, proposed, display-of-high-value, emotional-state, mentor, greek-chorus, sparkline, call-to-adventure, call-to-action, new-bliss, inoculation | disowning-your-topic, going-meta, tower-of-babble, lipstick-on-a-pig |
| 10 | Cultural & Pop-Culture References | leet-grammars, unifying-visual-theme, entertainment | alienating-artifact, photomaniac |
| 11 | Technical Content Delivery | live-demo, lipsync, traveling-highlights, crawling-code, emergence, mentor, lightsaber | dead-demo |
| 12 | Pacing Clues | crucible, expansion-joints, talklet, brain-breaks, lightning-talk, takahashi, carnegie-hall, breathing-room, weatherman, screen-blackout | shortchanged, disowning-your-topic |
| 13 | Slide Design Patterns | unifying-visual-theme, takahashi, cave-painting, composite-animation, vacation-photos, defy-defaults, analog-noise, gradual-consistency, charred-trail, exuberant-title-top, invisibility, context-keeper, breadcrumbs, bookends, soft-transitions, intermezzi, preroll, crawling-credits, lipsync, traveling-highlights, crawling-code, emergence, screen-blackout, star-moment | cookie-cutter, bullet-riddled-corpse, ant-fonts, fontaholic, floodmarks, photomaniac, laser-weapons |
| 14 | Areas for Improvement | crucible, preparation, carnegie-hall, shoeless, stakeout | abstract-attorney, alienating-artifact, celery, injured-outlines, bullet-riddled-corpse, ant-fonts, fontaholic, floodmarks, photomaniac, borrowed-shoes, slideuments, dead-demo, shortchanged, hiccup-words, disowning-your-topic, going-meta, bunker, hecklers, backchannel, laser-weapons, negative-ignorance, dual-headed-monster, tower-of-babble, lipstick-on-a-pig |

---

---

## Unobservable Patterns — Go-Live Checklist

These patterns involve pre-event logistics, physical stage behaviors, or external systems
that leave **no trace in transcripts or slides**. The vault cannot score them. Instead,
they surface during **creator Phase 6 (Publishing / Go-Live)** as a preparation checklist.

**Do not include these in vault scoring or the speaker profile's `pattern_profile`.**

### Pre-Event Preparation
| ID | Name | Checklist Action |
|----|------|-----------------|
| preparation | Preparation | Pack duplicate cables, backup deck to USB/cloud, hydrate, check room layout and schedule |
| carnegie-hall | Carnegie Hall | Complete 4 structured rehearsals: (1) pace/timing, (2) delivery, (3) fix notes from 1-2, (4) find the groove |
| stakeout | The Stakeout | Locate a productive staging area near the venue, arrive with ample buffer time |
| posse | Posse | Bring a friend/colleague for front-row support, positive energy, and equipment backup |
| seeding-satisfaction | Seeding Satisfaction | Arrive early, mingle with attendees, make personal connections, verify audience assumptions |
| shoeless | Shoeless | Activate your personal comfort ritual (favorite undershirt, sneakers, beverage placement) |

### During Delivery
| ID | Name | Checklist Action |
|----|------|-----------------|
| lightsaber | Lightsaber | If using a laser pointer, use sparingly and steadily — max 2-3 moments per talk |
| red-yellow-green | Red, Yellow, Green | If venue supports it, set up colored feedback cards near the exit |

### Antipatterns to Avoid (unobservable)
| ID | Name | What to Watch For |
|----|------|------------------|
| laser-weapons | Laser Weapons | Don't wave the pointer constantly — build highlights into slides instead |
| bunker | Bunker | Step out from behind the podium, walk the stage, make eye contact |
| backchannel | Backchannel | Don't monitor social media during your talk — use it as feedback after |

---

## Summary Statistics

- **Total entries:** 97 (72 patterns + 25 antipatterns)
- **Observable (vault-scorable):** 86 (64 patterns + 22 antipatterns)
- **Unobservable (go-live checklist):** 11 (8 patterns + 3 antipatterns)
- **Prepare phase:** 22 (19 patterns + 3 antipatterns)
- **Build phase:** 44 (34 patterns + 10 antipatterns)
- **Deliver phase:** 31 (19 patterns + 12 antipatterns)

## Sources

- Ford, N., McCullough, M., & Schutta, N. (2013). *Presentation Patterns: Techniques for Crafting Better Presentations.* Addison-Wesley. — primary taxonomy source.
- Reynolds, G. (2012). *Presentation Zen: Simple Ideas on Presentation Design and Delivery* (2nd ed.). New Riders. — supplementary source; reinforces ~17 existing patterns and contributes the `opening-punch` and `screen-blackout` patterns plus three refinement subsections folded into existing patterns: "Hara Hachi Bu — The 90–95% Finish Line" (in `breathing-room.md`), "Plan Analog Before Going Digital" (in `concurrent-creation.md`), and "The Elevator Test" (in `the-big-why.md`).
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Wiley. — supplementary source; reinforces ~20 existing patterns and contributes seven new build-phase patterns (`sparkline`, `call-to-adventure`, `call-to-action`, `new-bliss`, `star-moment`, `inoculation`, `master-story`) plus six refinement subsections folded into existing patterns: "Adopting the Stance — Planning Implications" (in `mentor.md`), "The Big Idea — Statement Format" (in `the-big-why.md`), "Numerical Narrative — Making Numbers Land" (in `vacation-photos.md`), "Screening with Critics — Beyond Copyediting" (in `peer-review.md`), "Murder Your Darlings — The Pre-Delivery Cut Pass" (in `crucible.md`), and "The Three Contrast Types — Engine of the Middle" (in `sparkline.md`).

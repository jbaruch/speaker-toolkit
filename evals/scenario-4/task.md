# Speaker Profile Document Generation

## Problem/Feature Description

A speaking platform has been analyzing a speaker's talks for months and has accumulated a rich set of rhetoric observations stored in narrative documents and a tracking database. Now they need to generate a structured, machine-readable speaker profile document that can drive automated tooling — presentation generators, style checkers, and audience recommendation engines.

The profile must synthesize data from the narrative summary (which describes patterns in prose), the tracking database (which contains per-talk structured data and confirmed speaker intents), and the slide design spec (which describes visual rules). The result should be a comprehensive JSON document that any downstream tool can parse without needing to read prose.

## Output Specification

Produce the following file:

1. **`speaker-profile.json`** — A comprehensive speaker profile JSON document synthesized from the provided vault data

## Input Files

The following files are provided as inputs. Extract them before beginning.

=============== FILE: inputs/rhetoric-style-summary.md ===============
# Rhetoric & Style Summary — Alex Devson

Last updated: 2026-02-20

## Section 1: Presentation Modes

Alex operates in three distinct presentation modes:

**Mode A: "The Myth Buster"** — Problem-diagnosis-solution arc. Heavy meme usage, audience interaction, humor as persuasion tool. Used for DevOps and culture talks. Commercial intent: none or subtle. ~1.4 slides/min.

**Mode B: "The Deep Dive"** — Technical deep-dive with live demos. Minimal slides, demo-scaffolding style. Moderate humor. Used for tooling talks. ~0.8 slides/min.

**Mode C: "The Keynote"** — Inspirational narrative, story-driven. Image-heavy slides. Light humor. Used for opening/closing keynotes. ~1.2 slides/min.

## Section 2: Opening Patterns

Alex typically opens with a provocative statement or bold claim, often combined with immediate audience interaction ("raise your hand if..."). The shownotes URL appears early (slide 4-5). Bio is brief and delayed — appears at slide 3, with fuller credentials revealed mid-talk.

## Section 3: Narrative Structures

Primary arc: problem-diagnosis-solution (70% of talks). Acts typically split 35/45/20. The "diagnosis" section includes both evidence (data slides) and emotional appeal (memes showing the pain).

## Section 4: Humor & Wit

Heavy humor register in Myth Buster mode. Techniques: self-deprecating ("and I say that with love"), meme cascades (3-5 memes in sequence), callback humor (referencing earlier joke with twist), pop-culture references (mostly internet/developer memes).

## Section 5: Transition Techniques

Characteristic transitions: "next thing you know...", "jokes aside", "okay so here's the thing". Uses topic-bridging where the punchline of a joke becomes the setup for the next serious point.

## Section 6: Closing Patterns

Three-part close: numbered summary (always 3 points), call-to-action with shownotes URL, and social handles with humor sign-off. Closing often calls back to the opening provocation.

## Section 7: Verbal Signatures

Recurring phrases: "is not a thing" (dismissal), "right?" (confirmation tag), "okay so" (transition filler), "raise your hand if" (audience poll), "full stop" (emphasis), "with love" (softener before criticism).

## Section 8: Slide-to-Speech Relationship

Slides are minimal text, heavy images/memes. Speaker uses slides as visual punchlines — the spoken word carries the argument, slides carry the emotion. Speaker notes used sparingly for key transitions only.

## Section 9: Persuasion Techniques

Pattern: establish credibility through shared pain → present data → propose framework → validate with story. Anti-sell pattern: deliberately argues against own position before revealing the pitch.

## Section 10: Cultural References

Heavy internet meme culture. Favorites: "this is fine" dog, skeleton waiting, Drake approving/disapproving, "I am once again asking". Memes always serve a rhetorical function, never decoration.

## Section 11: Technical Content Delivery

Progressive complexity: start with familiar concepts, layer in specifics. Analogies drawn from everyday life. Live demos are scripted but appear spontaneous.

## Section 12: Pacing Clues

Opening sequence moves fast (30s/slide). Data sections slow down (60-90s/slide). Meme sequences are rapid-fire. Consistently runs into time pressure in final third.

## Section 13: Slide Design Patterns

Comic-book aesthetic: bold colors, hand-lettered fonts, speech bubbles, starburst shapes. Background colors from a fixed pool: purple halftone, red halftone, yellow halftone, green halftone, white clean. No adjacent color repeats. Footer always present with: @handle | #conference | #topic | website.

## Section 15: Areas for Improvement

- Consistently rushes the closing section due to time management (observed in 8/12 talks)
- Opening theoretical framing sometimes exceeds 15% of talk time
- Meme accretion in Act 1 — too many memes dilute the argument
- Transitions between humor and serious points could be smoother

## Section 16: Speaker-Confirmed Intent

- Delayed self-introduction is deliberate (confirmed): "I want them curious before they know who I am"
- Anti-sell pattern is deliberate (confirmed): "If I argue against myself first, they trust me more"
- Three-point closing is non-negotiable: "Always three. Never two, never four."
- On-slide profanity never (confirmed): "Keep it verbal so I can adapt per venue"
=============== END OF FILE ===============

=============== FILE: inputs/tracking-database.json ===============
{
  "config": {
    "vault_root": "/vault",
    "speaker_name": "Alex Devson",
    "speaker_handle": "@alexdev",
    "speaker_website": "alex.dev",
    "shownotes_url_pattern": "alex.dev/{slug}",
    "template_pptx_path": "/templates/alex-template.pptx",
    "presentation_file_convention": "{pptx_source_dir}/{conference}/{year}/{talk-slug}/"
  },
  "talks": [
    {"filename": "2024-03-15-devops-reframed.md", "title": "DevOps Reframed", "conference": "DevOps Days Chicago", "status": "processed", "structured_data": {"slide_count": 62, "meme_count": 15, "audience_interaction_count": 4, "opening_type": "bold_claim", "closing_type": "summary_cta", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "45 min"}},
    {"filename": "2024-06-20-supply-chain.md", "title": "Supply Chain Security", "conference": "KubeCon EU", "status": "processed", "structured_data": {"slide_count": 55, "meme_count": 12, "audience_interaction_count": 3, "opening_type": "failure_framing", "closing_type": "summary_cta", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "40 min"}},
    {"filename": "2024-09-05-ai-testing.md", "title": "AI Testing Revolution", "conference": "StarEast", "status": "processed", "structured_data": {"slide_count": 48, "meme_count": 8, "audience_interaction_count": 2, "opening_type": "audience_poll", "closing_type": "summary_cta", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "35 min"}},
    {"filename": "2024-01-20-ci-deep-dive.md", "title": "CI Pipeline Deep Dive", "conference": "FOSDEM", "status": "processed", "structured_data": {"slide_count": 30, "meme_count": 3, "audience_interaction_count": 1, "opening_type": "demo_cold_open", "closing_type": "demo_finale", "narrative_arc_type": "discovery_demo", "talk_duration_estimate": "50 min"}},
    {"filename": "2023-11-05-container-myths.md", "title": "Container Myths Busted", "conference": "DockerCon", "status": "processed", "structured_data": {"slide_count": 70, "meme_count": 18, "audience_interaction_count": 5, "opening_type": "provocative_image", "closing_type": "callback", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "45 min"}},
    {"filename": "2023-09-12-gitops-keynote.md", "title": "GitOps: The Journey", "conference": "GitOpsCon", "status": "processed", "structured_data": {"slide_count": 45, "meme_count": 6, "audience_interaction_count": 2, "opening_type": "story", "closing_type": "summary_cta", "narrative_arc_type": "chronological", "talk_duration_estimate": "30 min"}},
    {"filename": "2023-06-15-security-left.md", "title": "Shift Left or Shift Shame?", "conference": "BSides", "status": "processed", "structured_data": {"slide_count": 58, "meme_count": 14, "audience_interaction_count": 3, "opening_type": "bold_claim", "closing_type": "summary_cta", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "40 min"}},
    {"filename": "2023-04-20-platform-eng.md", "title": "Platform Engineering 101", "conference": "PlatformCon", "status": "processed", "structured_data": {"slide_count": 52, "meme_count": 10, "audience_interaction_count": 4, "opening_type": "audience_poll", "closing_type": "summary_cta", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "45 min"}},
    {"filename": "2023-02-10-iac-myths.md", "title": "IaC Myths", "conference": "Config Mgmt Camp", "status": "processed", "structured_data": {"slide_count": 65, "meme_count": 16, "audience_interaction_count": 3, "opening_type": "failure_framing", "closing_type": "summary_cta", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "45 min"}},
    {"filename": "2022-11-08-testing-culture.md", "title": "Testing Culture", "conference": "SeleniumConf", "status": "processed", "structured_data": {"slide_count": 50, "meme_count": 11, "audience_interaction_count": 3, "opening_type": "bold_claim", "closing_type": "summary_cta", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "40 min"}},
    {"filename": "2022-08-15-devsecops.md", "title": "DevSecOps Done Right", "conference": "Black Hat", "status": "processed", "structured_data": {"slide_count": 42, "meme_count": 5, "audience_interaction_count": 2, "opening_type": "story", "closing_type": "summary_cta", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "30 min"}},
    {"filename": "2022-05-20-monolith-micro.md", "title": "Monolith to Microservices", "conference": "QCon London", "status": "processed", "structured_data": {"slide_count": 68, "meme_count": 14, "audience_interaction_count": 4, "opening_type": "provocative_image", "closing_type": "callback", "narrative_arc_type": "problem_diagnosis_solution", "talk_duration_estimate": "45 min"}}
  ],
  "confirmed_intents": [
    {"pattern": "delayed_self_introduction", "intent": "deliberate", "rule": "Two-phase intro: brief bio slide 3, full re-intro mid-talk", "note": "Speaker confirmed: wants audience curious first"},
    {"pattern": "anti_sell", "intent": "deliberate", "rule": "Argue against own position before pitch", "note": "Builds trust through apparent objectivity"},
    {"pattern": "three_point_close", "intent": "deliberate", "rule": "Always exactly three summary points in closing", "note": "Non-negotiable speaker preference"},
    {"pattern": "on_slide_profanity", "intent": "deliberate", "rule": "Never on slides, verbal only", "note": "Enables deck reuse across venue types"}
  ]
}
=============== END OF FILE ===============

=============== FILE: inputs/slide-design-spec.md ===============
# Slide Design Specification — Alex Devson

## Background Colors
Pool: purple halftone (#5B2C6F), red halftone (#C0392B), yellow halftone (#F1C40F), green halftone (#27AE60), white clean (#FFFFFF), grey neutral (#BDC3C7).
Strategy: random non-repeating. No adjacent slides share the same background color. White/black reserved for full-bleed image/meme slides.

## Typography
- Title font: Bangers (Google Fonts, hand-lettered comic style)
- Body font: Arial
- Footer font: Arial, 16pt
- Bullet character: multiplication sign (x)
- Title color adapts to background for contrast

## Footer
Always present. Pattern: @alexdev | #{conference} | #{topic} | alex.dev
Position: bottom-left, spanning full width. 16pt Arial.
Co-presented extra: co-presenter handle added after @alexdev.
Color adapts to background. Outline for legibility on dark backgrounds.

## Shapes
- Speech bubbles (CLOUD_CALLOUT): white fill, black outline, used for audience quotes
- Starbursts (EXPLOSION1): red fill, white text, used for bold declarations
- Slide numbers: never
=============== END OF FILE ===============

# Rhetoric & Style Analysis Dimensions

Analyze each talk across these 14 dimensions plus structured data extraction. Focus on STYLE and RHETORIC, not the technical content itself. The goal is to collect material for building a prescriptive presentation-creator skill — understand HOW the speaker presents so we can replicate it.

**IMPORTANT:** In addition to qualitative observations, extract concrete quantitative data and verbatim examples from the transcript. Every observation should be grounded in specific evidence.

## 1. Opening Pattern
How does the talk begin? What hook is used? (e.g., story, provocative question, joke, bold claim, audience interaction, cold open into demo)

**Related Patterns:** Preroll | **Antipatterns:** —

## 2. Narrative Structure
What's the arc? How are sections organized? Is there a throughline? Does the talk follow a problem-solution arc, a chronological journey, a listicle, or something else?

**Related Patterns:** Narrative Arc, Triad, Talklet, Expansion Joints, Fourthought, Context Keeper, Bookends, Intermezzi, Foreshadowing, Backtracking, A la Carte Content, Breadcrumbs, Lightning Talk, Concurrent Creation | **Antipatterns:** Abstract Attorney, Celery

## 3. Humor & Wit
What jokes/references are made? What type of humor — self-deprecating, absurdist, observational, callback, running gag? How frequent? Where is humor placed relative to serious points?

**Related Patterns:** Brain Breaks, Entertainment | **Antipatterns:** Alienating Artifact

## 4. Audience Interaction
Any engagement techniques visible in transcript? Show of hands, rhetorical questions, direct address, polling, "raise your hand if...", pauses for laughter/response?

**Related Patterns:** Know Your Audience, Social Media Advertising, A la Carte Content, Posse, Seeding Satisfaction, Seeding the First Question, Emotional State, Make It Rain, Echo Chamber, Red Yellow Green, Greek Chorus | **Antipatterns:** Bunker, Hecklers, Backchannel, Negative Ignorance, Dual-Headed Monster

## 5. Transition Techniques
How does the speaker move between topics? Verbal bridges, visual transitions, story callbacks, "now let's talk about...", seamless vs. explicit breaks?

**Related Patterns:** Narrative Arc, Foreshadowing, Backtracking, Context Keeper, Bookends, Intermezzi, Soft Transitions, Cave Painting | **Antipatterns:** —

## 6. Closing Pattern
How does the talk end? Callback to opening, call to action, summary, emotional note, joke, open question, resource list?

**Related Patterns:** Coda, Crawling Credits | **Antipatterns:** —

## 7. Verbal Signatures
Recurring phrases, characteristic expressions, filler patterns, catchphrases, favorite sentence structures, how the speaker addresses the audience.

**Related Patterns:** Leet Grammars, Peer Review, Breathing Room, Echo Chamber | **Antipatterns:** Hiccup Words, Borrowed Shoes, Tower of Babble

## 8. Slide-to-Speech Relationship
How do slides complement the spoken word? Are slides dense or minimal? Does the speaker read slides or use them as springboards? Image-heavy vs. text-heavy? Speaker notes vs. improvisation clues?

**Related Patterns:** Fourthought, Concurrent Creation, Coda, Vacation Photos, Infodeck, Gradual Consistency, Charred Trail, Takahashi, Live on Tape, Peer Review | **Antipatterns:** Cookie Cutter, Injured Outlines, Bullet-Riddled Corpse, Borrowed Shoes, Slideuments, Lipstick on a Pig

## 9. Persuasion Techniques
How are arguments structured? Appeal to authority, personal experience, data/evidence, analogy, social proof, counterargument handling, building credibility?

**Related Patterns:** Know Your Audience, Required, The Big Why, Proposed, Display of High Value, Emotional State, Mentor, Greek Chorus | **Antipatterns:** Disowning Your Topic, Going Meta, Tower of Babble, Lipstick on a Pig

## 10. Cultural & Pop-Culture References
What's referenced and how? Movies, TV shows, books, memes, historical events, internet culture. How are these woven in — as analogies, humor, slide imagery?

**Related Patterns:** Leet Grammars, Unifying Visual Theme, Entertainment | **Antipatterns:** Alienating Artifact, Photomaniac

## 11. Technical Content Delivery
How is complexity handled? Simplification strategies, analogy patterns, progressive revelation, live demo integration, code examples, before/after comparisons?

**Related Patterns:** Live Demo, Lipsync, Traveling Highlights, Crawling Code, Emergence, Mentor, Lightsaber | **Antipatterns:** Dead Demo

## 12. Pacing Clues
Section lengths, density of content per slide, speed of topic transitions, where the speaker lingers vs. rushes, balance of depth vs. breadth.

**Related Patterns:** Crucible, Expansion Joints, Talklet, Brain Breaks, Lightning Talk, Takahashi, Carnegie Hall, Breathing Room, Weatherman | **Antipatterns:** Shortchanged, Disowning Your Topic

## 13. Slide Design Patterns

**Related Patterns:** Unifying Visual Theme, Takahashi, Cave Painting, Composite Animation, Vacation Photos, Defy Defaults, Analog Noise, Gradual Consistency, Charred Trail, Exuberant Title Top, Invisibility, Context Keeper, Breadcrumbs, Bookends, Soft Transitions, Intermezzi, Preroll, Crawling Credits, Lipsync, Traveling Highlights, Crawling Code, Emergence | **Antipatterns:** Cookie Cutter, Bullet-Riddled Corpse, Ant Fonts, Fontaholic, Floodmarks, Photomaniac, Laser Weapons

Analyze the visual design of EVERY slide in the PDF. This feeds the `slide-design-spec.md`
in the vault root. Refer to that document for the full taxonomy of categories.

### 13a. Per-Slide Visual Classification

For EACH slide, determine:

- **Background color name**: Which of the established categories? (purple_halftone,
  red_halftone, yellow_halftone, green_halftone, blue_halftone, orange_halftone,
  salmon_pink_halftone, white_clean, grey_neutral, vintage_parchment, sepia_red_propaganda,
  or NEW if not in the list — describe it)
- **Content type**: title, bio, shownotes, content_bullets, data_chart, quote, meme_only,
  meme_with_text, section_divider, progressive_reveal, comparison_table, hot_take,
  cta, thanks
- **Image composition** (if image present): full_bleed, full_bleed_with_text,
  image_left_text_right, image_right_text_left, centered_image_with_title, inset_image,
  progressive_reveal, screenshot, meme_with_caption, or none
- **Speech bubble present?** (the callout shape containing text)
- **Starburst/explosion shape present?** (the irregular star shape for declarations)
- **Footer visible?**

Record the background color of every slide in order as `background_color_sequence`.

### 13b. Typography Observations

From visual inspection of the PDF:
- What font appears to be used for titles? For body text? For footer?
  (Name the font family if identifiable; otherwise describe: "hand-lettered comic",
  "sans-serif clean", "monospace")
- Approximate font size ranges (small/medium/large/extra-large for titles vs body vs footer)
- Does text color change with background color, or stay constant (e.g., always white)?
- What bullet character is used? (multiplication sign ×, dash -, circle, other)
- Text alignment patterns (centered titles? left-aligned body?)

### 13c. Footer & Branding Observations

- How many footer elements? What separator between them?
- Does footer text color adapt to the background or stay fixed?
- Are there corporate/sponsor branding elements (logos, watermarks)? Where? How prominent?
- Any other recurring branding elements?

### 13d. Shape Observations

- Which slides have speech bubbles? Describe: fill color, outline, tail direction
- Which slides have starburst/explosion shapes? Describe: fill color, text inside
- Any other recurring shapes (arrows, rounded rectangles, etc.)?
- Approximate size and position of recurring shapes

### 13e. Section Divider Identification

- Do section divider slides exist as a DISTINCT visual type?
- If yes: what layout, font size, background color, any shapes?
- If no: how are section boundaries signaled visually? (color change? text cue?
  starburst marker?)

### 13f. Illustration & Image Style

Analyze the visual aesthetic of images and illustrations across the deck. This feeds
the `visual_style_history` in the speaker profile, which informs illustration style
proposals when creating new talks.

For each talk, determine:

- **Image source types**: What kinds of images appear? Categorize each image slide as:
  `ai_generated`, `stock_photo`, `screenshot`, `meme`, `custom_artwork`, `diagram`,
  `photo_real` (speaker's own photos), `none` (text-only). Report the distribution.
- **Illustration aesthetic** (when AI-generated or custom artwork is present):
  Name the style — e.g., comic-book halftone, retro-futurism, technical manual,
  patent drawing, propaganda poster, watercolor, pixel art, flat vector, photorealistic
  render, collage, or a novel style (describe it). Be specific enough that someone
  could reproduce it in a prompt.
- **Visual coherence**: Do all illustrations share a unified style (suggesting a
  deliberate style anchor), or are they mixed/ad-hoc?
- **Style anchor evidence**: Is there a recurring visual formula — same color palette,
  same rendering technique, same fictional framing device (e.g., "every slide is a
  page from a field manual")? Describe it.
- **Visual continuity devices**: Numbering schemes (e.g., "FIG. N"), recurring
  characters or mascots, progressive visual elements (e.g., a form that fills in),
  annotation conventions (callout labels, stamps, footnotes).
- **Image-to-slide ratio**: What fraction of slides are image-primary (FULL or
  IMG+TXT equivalent) vs text-primary vs screenshot/demo?
- **Mode correlation**: Does the visual style appear to be driven by the talk's
  mode or context? (e.g., terminal aesthetic for agent talks, retro style for
  co-presented talks). Note the correlation if visible.

**Cross-talk patterns** (updated in the summary after multiple talks):
- Default illustration aesthetic (the style the speaker gravitates toward)
- Intentional departures and what triggered them (mode, co-presenter, topic)
- Evolution over time (has the style changed?)
- Confirmed intents about visual design (from clarification sessions)

## 14. Reflection: Areas for Improvement

**Related Patterns:** Crucible, Preparation, Carnegie Hall, Shoeless, The Stakeout | **Antipatterns:** Abstract Attorney, Alienating Artifact, Celery, Injured Outlines, Bullet-Riddled Corpse, Ant Fonts, Fontaholic, Floodmarks, Photomaniac, Borrowed Shoes, Slideuments, Dead Demo, Shortchanged, Hiccup Words, Disowning Your Topic, Going Meta, Bunker, Hecklers, Backchannel, Laser Weapons, Negative Ignorance, Dual-Headed Monster, Tower of Babble, Lipstick on a Pig

Critically assess what could be improved in this talk's delivery and rhetoric. Look for: uneven pacing (rushing through the last third because of time pressure), weak transitions, jokes that don't land, audience engagement that falls flat, slides that are too dense or too sparse, arguments that lack support, sections that drag, abrupt endings, time management issues (visible "5 minutes left" panic), filler words overuse, unclear structure, missed callback opportunities, underused audience interaction. Be honest and constructive — the goal is to identify patterns to avoid, not just patterns to replicate.

## 15. Structured Data Extraction

Count and categorize these for the `structured_data` output:
- **slide_count**: Total slides in the PDF
- **talk_duration_estimate**: From transcript length or explicit time references
- **meme_count**: Slides that are primarily memes/reaction images
- **image_only_slide_count**: Slides with no extractable text
- **audience_interaction_count**: Show-of-hands, polls, rhetorical questions expecting response
- **opening_type**: Categorize as one of: provocative_image, failure_framing, audience_poll, story, bold_claim, demo_cold_open
- **closing_type**: Categorize as one of: summary_cta, callback, open_question, demo_finale, resource_list
- **narrative_arc_type**: problem_diagnosis_solution, discovery_demo, chronological, listicle
- **slide_design_style**: comic_book, minimal_dark, demo_scaffolding, mixed
- **illustration_style**: Name the dominant illustration aesthetic if present (e.g., "retro_tech_manual", "comic_book_halftone", "patent_drawing", "none"). Use "none" if the talk has no deliberate illustration style.
- **illustration_coherence**: unified, mixed, none — whether illustrations share a single style anchor
- **image_source_distribution**: Object mapping source types to counts, e.g., {"ai_generated": 20, "meme": 5, "screenshot": 8, "none": 12}
- **visual_continuity_devices**: List any recurring visual motifs (e.g., ["FIG_numbering", "progressive_form", "recurring_mascot"]) or empty list
- **opening_sequence**: List the type of each of the first ~5 slides (e.g., ["title", "provocative_hook", "bio", "shownotes_url", "first_argument"])
- **closing_sequence**: List the type of each of the last ~5 slides

## 16. Verbatim Examples Extraction

Extract ACTUAL QUOTES from the transcript for the `verbatim_examples` output:
- **signature_phrases**: Recurring expressions the speaker uses (e.g., "is not a thing", "right?", "okay so")
- **jokes**: The best 3-5 humor lines, verbatim
- **transitions**: Actual phrases used to move between topics (e.g., "Next thing you know...", "Jokes Aside")
- **audience_addresses**: How the speaker talks to the audience (e.g., "raise your hand if...", "how many of you...")
- **opening_lines**: First 2-3 sentences of the talk, verbatim from transcript
- **closing_lines**: Last 2-3 sentences of the talk, verbatim from transcript

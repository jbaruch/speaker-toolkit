# Rhetoric & Style Analysis Dimensions

Analyze each talk across these 14 dimensions plus structured data extraction. Focus on STYLE and RHETORIC, not the technical content itself. The goal is to collect material for building a prescriptive presentation-creator skill — understand HOW the speaker presents so we can replicate it.

**IMPORTANT:** In addition to qualitative observations, extract concrete quantitative data and verbatim examples from the transcript. Every observation should be grounded in specific evidence.

## 1. Opening Pattern
How does the talk begin? What hook is used? (e.g., story, provocative question, joke, bold claim, audience interaction, cold open into demo)

## 2. Narrative Structure
What's the arc? How are sections organized? Is there a throughline? Does the talk follow a problem-solution arc, a chronological journey, a listicle, or something else?

## 3. Humor & Wit
What jokes/references are made? What type of humor — self-deprecating, absurdist, observational, callback, running gag? How frequent? Where is humor placed relative to serious points?

## 4. Audience Interaction
Any engagement techniques visible in transcript? Show of hands, rhetorical questions, direct address, polling, "raise your hand if...", pauses for laughter/response?

## 5. Transition Techniques
How does the speaker move between topics? Verbal bridges, visual transitions, story callbacks, "now let's talk about...", seamless vs. explicit breaks?

## 6. Closing Pattern
How does the talk end? Callback to opening, call to action, summary, emotional note, joke, open question, resource list?

## 7. Verbal Signatures
Recurring phrases, characteristic expressions, filler patterns, catchphrases, favorite sentence structures, how the speaker addresses the audience.

## 8. Slide-to-Speech Relationship
How do slides complement the spoken word? Are slides dense or minimal? Does the speaker read slides or use them as springboards? Image-heavy vs. text-heavy? Speaker notes vs. improvisation clues?

## 9. Persuasion Techniques
How are arguments structured? Appeal to authority, personal experience, data/evidence, analogy, social proof, counterargument handling, building credibility?

## 10. Cultural & Pop-Culture References
What's referenced and how? Movies, TV shows, books, memes, historical events, internet culture. How are these woven in — as analogies, humor, slide imagery?

## 11. Technical Content Delivery
How is complexity handled? Simplification strategies, analogy patterns, progressive revelation, live demo integration, code examples, before/after comparisons?

## 12. Pacing Clues
Section lengths, density of content per slide, speed of topic transitions, where the speaker lingers vs. rushes, balance of depth vs. breadth.

## 13. Slide Design Patterns

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

## 14. Reflection: Areas for Improvement
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

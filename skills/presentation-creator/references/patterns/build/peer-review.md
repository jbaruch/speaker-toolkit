---
id: peer-review
name: Peer Review
type: pattern
part: build
phase_relevance:
  - content
  - guardrails
vault_dimensions: [7, 8]
detection_signals:
  - "clean grammar"
  - "consistent style"
  - "polished text"
  - "no typos on slides"
related_patterns: [leet-grammars]
inverse_of: [tower-of-babble]
difficulty: foundational
---

# Peer Review

## Summary
Have a literate colleague or professional editor review your text for grammar, clarity, and style before presenting, following five progressively expensive steps from automated tools to professional copyediting.

## The Pattern in Detail
Behind almost every stirring presentation is great copyediting. The Peer Review pattern establishes a deliberate quality assurance process for all textual content in your presentation, from slide titles and bullet points to speaker notes and handout materials. This is not merely about catching typos — though that alone justifies the effort — but about ensuring clarity, consistency, and polish across every word your audience will see or hear.

The pattern defines five progressively expensive steps that any presenter can follow. Step one is the most basic: run spell check and grammar check using your presentation tool's built-in capabilities or a dedicated writing tool. This catches the low-hanging fruit but misses contextual errors, awkward phrasing, and domain-specific mistakes. Step two is to read your content aloud. The ear catches problems the eye misses — sentences that are too long, words that sound similar but mean different things, and rhythms that feel off. This step costs nothing but time and is remarkably effective.

Step three escalates to having a friend or colleague review your slides and notes. A fresh pair of eyes catches ambiguities and assumptions that you, as the author, are blind to. Step four is to involve a documentation team or technical writing group, if your organization has one. Technical writers are trained to spot inconsistencies, unclear antecedents, and jargon that excludes rather than clarifies. Step five, the most expensive but most impactful, is to hire a professional copyeditor. For high-stakes presentations — keynotes, sales pitches, executive briefings — the investment pays for itself many times over.

It is important to note that Peer Review applies to all text in your presentation, not just the words on slides. Your speaker notes, handout materials, and even the abstract or description of your talk all benefit from review. However, the standard for slides is different from the standard for prose: you should not put complete sentences on slides unless they are direct quotes. Slides use fragments, keywords, and short phrases. The review process should enforce this distinction.

The inverse of Peer Review is the Tower of Babble antipattern, where unreviewed, unclear text confuses and alienates the audience. The difference between a polished presentation and an amateur one is often not the ideas but the execution of language. Audiences notice errors even when they cannot articulate what feels wrong, and those errors erode credibility and trust.

## When to Use / When to Avoid
Use Peer Review for any presentation you care about. At minimum, always complete steps one and two (automated tools and reading aloud). For conference talks, client presentations, and any high-visibility event, aim for at least step three. Reserve steps four and five for keynotes, product launches, and career-defining moments.

Avoid skipping Peer Review because you "know the material." Expertise in a subject does not guarantee clear communication of that subject. In fact, domain experts are often the worst at spotting their own unclear writing because they fill in gaps unconsciously.

## Detection Heuristics
When scoring talks, look for the absence of errors rather than the presence of editing marks. Clean grammar, consistent capitalization, uniform punctuation style, and the absence of typos on slides are all strong indicators that Peer Review was applied. Inconsistent formatting — some slides with periods at the end of bullets, others without — suggests the pattern was not followed.

## Scoring Criteria
- Strong signal (2 pts): Zero visible typos or grammatical errors on slides, consistent style throughout, polished and professional text quality
- Moderate signal (1 pt): Mostly clean text with one or two minor errors, generally consistent style with occasional lapses
- Absent (0 pts): Multiple typos, grammatical errors, inconsistent capitalization or punctuation, or unclear phrasing on slides

## Relationship to Vault Dimensions
Dimension 7 (Language and Communication): Peer Review directly impacts the quality of language used throughout the presentation, ensuring clarity and precision. Dimension 8 (Slide Design): Clean, error-free text is a fundamental component of professional slide design, and the review process often catches design inconsistencies as well.

## Combinatorics
Peer Review pairs naturally with the Leet Grammars pattern, which deals with intentional deviations from standard language conventions. When you deliberately break grammar rules for effect (Leet Grammars), the rest of your text must be impeccable so the audience recognizes the deviation as intentional. Peer Review also supports every other content pattern by ensuring the textual foundation is solid.

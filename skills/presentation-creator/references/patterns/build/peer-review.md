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

### Screening with Critics — Beyond Copyediting
Peer Review's five-step ladder addresses *language quality*. There is a separate, complementary review activity that addresses *content quality and structural integrity*: hosting a formal screening with honest critics. Nancy Duarte names this in *Resonate* Ch. 8 and treats it as non-negotiable for high-stakes talks.

The screening is a deliberate, time-boxed review session with three properties that distinguish it from casual feedback or copyediting:

- **3× the duration of the presentation.** A 20-minute talk gets a 60-minute screening; an hour-long talk gets a three-hour screening. The screening runs the entire presentation once at full speed, then revisits each section in detail with the screeners commenting as they go. The 3× ratio is what makes it a screening rather than a polite courtesy review — there is enough time to actually engage with structural decisions, not just react to surface impressions.

- **Naysayers from outside the speaker's organization.** The screeners must be willing and able to disagree. Internal reviewers are subject to political pressure, hierarchical deference, and shared blind spots. The right screening panel is composed of people who match the *target audience profile* (industry, role, knowledge level) but are *not* part of the speaker's reporting chain or social tribe. Trusted customers, industry peers, focus-group participants, and outside-organization friends all work; subordinates, direct reports, and people who depend on the speaker's approval do not.

- **Each screener gets a printed slide+notes packet** so they can mark up specific moments rather than offering only impressionistic feedback. The packet collects line-level critiques alongside structural ones.

Beyond the structural rules, the screener-selection process matters more than most speakers realize because organizations breed dysfunctional review environments that *guarantee* a useless screening. Duarte names six dysfunctional review patterns to recognize and route around:

- **Conceited Captain.** A leader who engages late and forces the team into a time-crunched, low-quality review pass.
- **Political Paranoia.** No one makes progressive decisions out of fear for their own destruction; feedback is calibrated to internal politics rather than message quality.
- **Message Magic.** In the absence of a real strategy, imagined or fictitious messages become the norm, and screeners feel the message is too sacred to challenge.
- **Vacuum Visionary.** No room for alternative perspectives; subject-matter experts have no seat at the table; the visionary's word is law.
- **Lackey Leader.** Indecisive leadership and flattery-driven consensus stall any real critique; everyone agrees with the leader on every point.
- **Customer Cold-Shoulder.** Self-focused communication is valued more than customer insight; screeners aren't selected to represent the actual audience.

If any of these patterns are present in the speaker's home organization, the right move is to do the screening *outside* the organization entirely. The cost of an unrepresentative screening (false confidence) is higher than the cost of seeking external screeners.

The screening produces three actionable outputs: structural critiques (where the talk's flow breaks down), language critiques (which feed back into the Peer Review ladder), and resistance discoveries (objections the screeners raised that the speaker hadn't anticipated — these become candidate inoculation moves). The work after the screening is to triage and address each critique, not to defend the existing draft.

The Markus Covert case study (Stanford bioengineer who won the $2.5M NIH Pioneer Award): he rehearsed his 15-minute presentation **20 times** with scientists across various disciplines, collecting feedback and modifying after each run. Rehearsal 19 and 20 produced "don't change a thing" — but only after 18 rounds of structured external critique. That's the screening discipline at work.

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

## Related Reading
- Duarte, N. (2010). *Resonate: Present Visual Stories that Transform Audiences.* Ch. 8 — "Host a Screening with Honest Critics": a formal review session 3× the duration of the presentation, with naysayers from outside the speaker's organization. Lists six dysfunctional review patterns to avoid: Conceited Captain, Political Paranoia, Message Magic, Vacuum Visionary, Lackey Leader, Customer Cold-Shoulder. Wiley.

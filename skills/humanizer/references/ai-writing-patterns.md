# AI Writing Pattern Catalog

Each pattern has an ID, description, detection heuristic, examples, and rewrite guidance.
Patterns are grouped by category.

---

## Category 1: Vocabulary & Word Choice

### AI-VOCAB — AI-Favorite Vocabulary

**Confidence:** High (when word is central to the sentence, not incidental)

**Detection:** Flag these words/phrases when used as load-bearing vocabulary rather than
in passing quotation or technical terminology:

- delve, delve into
- tapestry (metaphorical use)
- landscape (non-geographic: "the testing landscape")
- leverage (as verb outside finance)
- utilize (instead of "use")
- facilitate
- encompass
- multifaceted
- nuanced (as filler adjective)
- paradigm (outside philosophy/science)
- robust (outside engineering specs)
- streamline
- synergy, synergize
- holistic
- ecosystem (non-biological)
- empower
- foster (outside childcare)
- navigate (non-physical: "navigate challenges")
- realm
- pivotal
- comprehensive
- cutting-edge, groundbreaking, game-changing
- harness (non-physical: "harness the power of")
- spearhead
- underscores (as verb: "this underscores the importance")
- it's worth noting that, it's important to note
- in today's [fast-paced/ever-changing/rapidly-evolving] world

**Examples:**
- "Let's delve into the tapestry of microservice architectures" → "Let's look at how microservices fit together"
- "Navigate the landscape of modern testing" → "Figure out modern testing"
- "It's worth noting that this approach leverages..." → "This approach uses..."

---

### INFLATED-SYMBOLISM — Inflated Symbolic Language

**Confidence:** High

**Detection:** Flag metaphors that inflate mundane technical concepts into grand symbolic
narratives. Look for:

- "beacon of" (anything non-literal)
- "testament to"
- "cornerstone of"
- "pillar of"
- "bridge between X and Y" (for abstract concepts)
- "journey" (for technical processes: "the CI/CD journey")
- "unlock the potential/power of"
- "at the heart of"
- "the very fabric of"
- "stands as a"

**Examples:**
- "Kubernetes stands as a beacon of container orchestration" → "Kubernetes is the main container orchestrator"
- "Testing is the cornerstone of software quality" → "Testing catches bugs before users do"
- "This unlocks the true potential of reactive programming" → "This is where reactive programming pays off"

---

## Category 2: Sentence & Phrase Structure

### PROMOTIONAL — Promotional / Hype Language

**Confidence:** High

**Detection:** Flag sentences that read like marketing copy rather than technical
explanation. Signals:

- Superlatives without evidence ("best", "most powerful", "ultimate")
- Transformation claims ("revolutionizes", "transforms", "redefines")
- Promise language ("ensures", "guarantees" for non-guaranteed outcomes)
- Excitement markers ("exciting", "remarkable", "extraordinary")
- "Take X to the next level"
- "Seamlessly integrate"

**Examples:**
- "This revolutionary framework transforms how we think about state management" → "This framework handles state differently — here's how"
- "Seamlessly integrate your CI pipeline" → "Hook it into your CI pipeline"

---

### SUPERFICIAL-ING — Superficial -ing Analyses

**Confidence:** Medium

**Detection:** Flag noun phrases where an -ing gerund is used as a superficial modifier
that adds no real information. The pattern: "[topic] is about [verb]-ing [vague noun]".

Common forms:
- "achieving scalability" (instead of explaining what scales and how)
- "enhancing performance" (instead of naming the specific optimization)
- "enabling collaboration" (instead of describing what people actually do)
- "driving innovation" (instead of naming the innovation)
- "ensuring reliability" (instead of explaining the reliability mechanism)
- "fostering growth" (instead of describing what grows)
- "leveraging capabilities"
- "optimizing workflows"

**Detection heuristic:** Flag when an -ing phrase is the main predicate or summary of a
point, AND the object is abstract/vague. Ignore -ing phrases with concrete objects
("parsing JSON", "rendering the sidebar").

**Examples:**
- "This is about enabling teams to achieve better outcomes" → "This lets teams ship faster because..."
- "Focused on driving innovation in the deployment space" → "We changed how deploys work — specifically..."

---

### VAGUE-ATTRIBUTION — Vague Attributions

**Confidence:** Medium

**Detection:** Flag attribution phrases that gesture at authority without naming sources:

- "Studies show..."
- "Research indicates..."
- "Experts agree..."
- "It's widely known that..."
- "According to industry best practices..."
- "Many developers believe..."
- "It has been shown that..."
- "The data suggests..." (without citing specific data)

These are fine in casual speech IF followed by specifics. Flag when the attribution
stands alone as the entire evidence.

**Examples:**
- "Studies show that TDD improves code quality" → "A 2014 Microsoft study found TDD reduced defect density by 40-90%"
- "Experts agree that microservices are the future" → Just state your argument directly

---

### NEGATIVE-PARALLELISM — "No X, No Y" Negative Parallelism

**Confidence:** Medium

**Detection:** Flag parallel negative constructions that create artificial rhetorical
weight. Patterns:

- "No X, no Y" / "No X — no Y"
- "Without X, there is no Y"
- "Not just X, but Y" (when overused — once is fine, three times is a pattern)
- "Neither X nor Y" (when the paired items are artificially balanced)
- Chains of negatives: "no latency, no downtime, no compromises"

**Context:** Single use is often fine and can be effective rhetoric. Flag when:
- Used more than once in the same piece
- The paired items feel artificially balanced
- The construction adds gravitas to mundane concepts

**Examples:**
- "No tests, no deployment. No monitoring, no confidence." → "We block deploys without tests and require monitoring before we trust anything in prod."
- "Without observability, there is no reliability" → "You can't fix what you can't see"

---

### DID-NOTHING — Unnatural "Did Nothing" Phrasing

**Confidence:** Medium

**Detection:** Flag phrases where LLMs describe inaction or absence using oddly formal
or literary phrasing instead of natural alternatives:

- "did nothing to address"
- "did little to alleviate"
- "fell short of addressing"
- "failed to materialize"
- "remained conspicuously absent"
- "was notable for its absence"
- "left much to be desired"
- "proved insufficient"

**Examples:**
- "The refactoring did nothing to address the underlying issue" → "The refactoring didn't fix it"
- "Performance improvements failed to materialize" → "It wasn't actually faster"
- "Documentation remained conspicuously absent" → "There were no docs"

---

## Category 3: Structural Patterns

### EM-DASH-CHAIN — Em Dash Overuse

**Confidence:** Medium (density-dependent)

**Detection:** Count em dashes (—) per paragraph or per N sentences. Flag when:

- 3+ em dashes in a single paragraph
- 2+ em dashes in a single sentence
- Em dashes in more than 40% of paragraphs in a piece

**Context:** Some writers naturally use em dashes. If the speaker's vault shows heavy
em dash usage, raise the threshold by 50%.

**Examples:**
- "Kubernetes — the industry-standard orchestrator — handles this elegantly — if you configure it right — which most teams don't." → "Kubernetes handles this well if you configure it right. Most teams don't."

---

### RULE-OF-THREE — Rule of Three Overuse

**Confidence:** Medium (frequency-dependent)

**Detection:** Flag triadic structures (lists of exactly 3, three-part sentences, three
parallel clauses). The rule of three is a legitimate rhetorical device — the problem is
when EVERY paragraph uses it.

Flag when:
- 3+ triads in a 500-word passage
- Consecutive paragraphs each contain a triad
- Triads feel formulaic rather than intentional (items are generic, not specific)

**Examples:**
- "It's fast, reliable, and scalable. It's easy to learn, easy to deploy, and easy to maintain. It handles errors, manages state, and scales horizontally." → Vary the list lengths. Use pairs, fours, or irregular groupings.

---

### CONJUNCTIVE-EXCESS — Excessive Conjunctive Phrases

**Confidence:** Medium

**Detection:** Flag overuse of transitional/conjunctive phrases that create artificial
flow between sentences. LLMs use these to simulate coherent reasoning:

- "Furthermore," / "Moreover,"
- "Additionally,"
- "In addition to this,"
- "That being said,"
- "With that in mind,"
- "On the flip side,"
- "Interestingly,"
- "It's also worth mentioning that"
- "Building on this,"
- "To put it another way,"
- "In essence,"
- "Ultimately,"

Flag when: 3+ conjunctive openers in a 300-word passage, or consecutive sentences
start with conjunctive phrases.

**Examples:**
- "Furthermore, this approach improves testing. Moreover, it simplifies deployment. Additionally, it reduces costs." → "It also simplifies deployment and cuts costs." (Combine and drop the conjunctives.)

---

### UNIFORM-RHYTHM — Overly Perfect Sentence Rhythm

**Confidence:** Low (promoted to Medium with co-occurring patterns)

**Detection:** Measure sentence length variation within paragraphs. Flag when:

- 5+ consecutive sentences within ±4 words of the same length
- A paragraph where all sentences follow the same Subject-Verb-Object structure
- Alternating long-short-long-short pattern that feels mechanical
- Every sentence starts with the same part of speech (especially articles: "The X...",
  "The Y...", "The Z...")

**Heuristic:** Calculate the standard deviation of sentence lengths in a paragraph.
Natural writing typically has SD > 6 words. Flag paragraphs with SD < 4.

**Examples:**
- "The system processes requests. The handler validates input. The service transforms data. The database stores results." → "Requests come in, get validated, and transform through the service layer before landing in the database."

---

### PERFECT-NARRATIVE — Too-Perfect Narrative Structure

**Confidence:** Low (promoted to Medium with co-occurring patterns)

**Detection:** Flag prose that follows an unnaturally clean narrative arc with no
digressions, asides, qualifications, or natural tangents. Signals:

- Every paragraph has exactly one topic, perfectly scoped
- Transitions between paragraphs are suspiciously smooth
- No hedging, uncertainty, or "actually, let me back up"
- No parenthetical asides or personal anecdotes
- Problem→Solution→Benefit structure repeated identically across sections
- Absence of self-correction or revised thinking

**Context:** Presentation outlines are supposed to be structured — this check is most
relevant for speaker notes, abstracts, and prose sections where natural voice matters.

**Examples:**
- Robotic: "First, we identify the problem. Then, we explore solutions. Finally, we evaluate results." → Natural: "So the problem was — and this took us a while to figure out — that the cache was lying to us."

---

### PERFORMED-CREDENTIALISM — Unnecessary Technical Precision

**Confidence:** Medium

**Detection:** Flag when text adds technical specificity that serves no communicative
purpose — it exists to sound authoritative rather than to inform. Signals:

- Version numbers when version doesn't matter ("Python 3.11.4" when any Python 3 applies)
- Full formal names when abbreviations are standard ("Representational State Transfer" in
  a talk where everyone says REST)
- Unnecessary qualifier chains ("highly distributed event-driven microservice architecture"
  when "microservices" suffices)
- Academic-style hedging in non-academic context ("it could be argued that", "one might
  posit that")
- Citing RFCs or specs by number when the audience doesn't need the reference

**Examples:**
- "Leveraging HTTP/1.1 persistent connections as defined in RFC 7230..." → "Using keep-alive connections..."
- "Python 3.11.4's implementation of PEP 657" → "Python's better error messages" (if the specific PEP isn't the point)
- "One might argue that this represents a paradigm shift" → "This changes things"

---

## Pattern Stacking Rules

When multiple patterns co-occur in the same paragraph, escalate confidence:

| Individual findings | Stacked confidence |
|--------------------|-------------------|
| 2 low in same paragraph | → 1 medium |
| 1 medium + 1 low in same paragraph | → 1 high |
| 2 medium in same paragraph | → 1 high |
| 3+ any in same paragraph | → 1 high (flag as "AI pattern cluster") |

Report pattern stacking explicitly in the output:

```
[PATTERN-STACK] Lines 14-18: AI-VOCAB + PROMOTIONAL + CONJUNCTIVE-EXCESS
  "Furthermore, this groundbreaking approach seamlessly leverages the power of..."
  → This paragraph has 3 AI tells. Consider rewriting from scratch in your own voice.
```

---

## False Positive Guidance

These are NOT AI patterns — do not flag:

- **Technical jargon in technical talks.** "Kubernetes", "event-driven", "idempotent" are
  domain terms, not AI vocabulary.
- **Deliberate rhetorical devices.** A single well-placed rule of three, an intentional
  em dash for dramatic pause, or a parallel structure used for emphasis.
- **Speaker's documented voice.** If the vault shows the speaker naturally uses certain
  phrases or structures, suppress those patterns or lower their confidence.
- **Quoted material.** Don't flag patterns inside quotation marks or code blocks.
- **Casual/spoken language.** Contractions, sentence fragments, slang, and informal
  phrasing are human markers. Their presence should reduce overall AI confidence.

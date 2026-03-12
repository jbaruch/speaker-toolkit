---
name: humanizer
description: >
  Detect and flag AI-generated writing patterns in presentation content — speaker notes,
  outlines, abstracts, and any prose produced during the presentation workflow. Scans text
  for telltale LLM markers: inflated symbolism, promotional language, superficial -ing
  constructions, vague attributions, em dash overuse, rule of three abuse, AI vocabulary,
  excessive conjunctive phrases, negative parallelism, performed credentialism, overly
  perfect rhythm, too-structured narratives, and unnatural phrasing. Use this skill when
  reviewing any written content for AI tells, or as a post-generation quality gate in the
  presentation-creator workflow.
  Triggers: "humanize this", "check for AI patterns", "scan for AI writing",
  "does this sound AI-generated", "make it sound human", "check AI tells",
  "run humanizer", "flag AI patterns".
user_invocable: true
---

# Humanizer — AI Writing Pattern Detector

Scan text for patterns that signal AI-generated writing. Flag each detection with the
pattern name, location, and a concrete suggestion for how to rewrite it naturally.

**This skill detects problems. It does NOT auto-rewrite.** The author decides what to
change — some "AI patterns" may be intentional stylistic choices.

## When to Use

- After Phase 3 (Content Development) of the presentation-creator workflow
- When reviewing CFP abstracts or speaker notes
- When editing any prose that may have been AI-assisted
- On explicit user request

## How to Run

1. Accept text input — either a file path, pasted text, or the current presentation outline.
2. Scan against all pattern detectors listed in `references/ai-writing-patterns.md`.
3. Report findings grouped by severity (high / medium / low confidence).
4. For each finding, show: pattern name, matched text (quoted), and rewrite suggestion.

## Input

The skill accepts:
- A file path to scan (markdown, text)
- Pasted text in the conversation
- `$ARGUMENTS` pointing to a specific file or "outline" to scan the current presentation outline

If no input is specified, ask: "What text should I scan for AI writing patterns?"

## Detection Process

For each paragraph or sentence in the input:

1. Run all pattern checks from `references/ai-writing-patterns.md`
2. Record matches with the exact text span and pattern ID
3. Assign confidence: **high** (strong signal, almost always AI), **medium** (likely AI
   but occasionally natural), **low** (weak signal, context-dependent)
4. Generate a rewrite suggestion that preserves the meaning but sounds human

### Confidence Calibration

- **High**: Pattern is rare in natural human writing and strongly associated with LLMs.
  Examples: "delve into", "it's worth noting that", "tapestry of".
- **Medium**: Pattern occurs in human writing but at much lower frequency than in LLM output.
  Examples: em dash chains, rule of three in every paragraph, negative parallelism.
- **Low**: Pattern is common in both human and AI writing but becomes suspicious in
  combination with other signals. Examples: slightly uniform rhythm, occasional -ing
  construction.

Promote low→medium or medium→high when **multiple patterns co-occur** in the same
paragraph (pattern stacking).

## Output Format

```
HUMANIZER SCAN — {source description}
================================================
Patterns scanned: {count}
Findings: {high} high / {medium} medium / {low} low

HIGH CONFIDENCE
───────────────
[AI-VOCAB] Line 14: "delve into the intricacies of microservices"
  → Try: "dig into how microservices work" or "look at microservices up close"

[PROMOTIONAL] Line 22: "This groundbreaking approach revolutionizes..."
  → Try: "This approach changes how we..." or just state what it does

MEDIUM CONFIDENCE
─────────────────
[EM-DASH-CHAIN] Lines 8-12: 4 em dashes in 5 sentences
  → Try: Replace 2-3 with commas, periods, or parentheses

[RULE-OF-THREE] Lines 15, 23, 31: Three consecutive paragraphs each end with a triad
  → Try: Vary the rhythm — use pairs, singles, or lists of 4-5

LOW CONFIDENCE
──────────────
[UNIFORM-RHYTHM] Lines 40-48: 6 sentences with near-identical length (18-22 words)
  → Try: Mix short punchy sentences with longer ones. Break the pattern.

================================================
Overall: {CLEAN / NEEDS REVIEW / HEAVY AI SIGNAL}
  CLEAN = 0 high, ≤2 medium
  NEEDS REVIEW = 1-3 high or 3+ medium
  HEAVY AI SIGNAL = 4+ high or pattern stacking detected
================================================
```

## Integration with Presentation Creator

When used as a guardrail in the presentation-creator workflow, add a 10th guardrail
check to the standard guardrail output:

```
[PASS/WARN/FAIL] AI writing patterns: {high} high, {medium} medium findings
```

- **PASS**: CLEAN (0 high, ≤2 medium)
- **WARN**: NEEDS REVIEW (1-3 high or 3+ medium)
- **FAIL**: HEAVY AI SIGNAL (4+ high or pattern stacking)

## Important Notes

- **Speaker notes are conversational.** Calibrate for spoken language, not formal prose.
  Contractions, fragments, and casual phrasing are fine — those are human tells, not
  problems.
- **Some patterns are intentional.** The rule of three is a legitimate rhetorical device.
  Em dashes have valid uses. Flag but don't assume everything is a problem.
- **Context matters.** A single AI vocabulary word in an otherwise natural paragraph is
  low confidence. Five AI patterns in one paragraph is high confidence regardless of
  individual severity.
- **The vault voice is the gold standard.** If the speaker's vault shows they naturally
  use em dashes heavily or favor triadic structures, lower the sensitivity for those
  specific patterns.

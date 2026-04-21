# Interaction Rules

## One Question Per Turn

- **Never present multiple questions in one message.** Ask one question, wait for
  the answer, then ask the next. This applies to every skill, every phase.
- If you have five things to clarify, that's five turns — not one wall of text
  with numbered questions.
- The user should never see "1. ... 2. ... 3. ..." in a clarification message.

## Use AskUserQuestion for Finite Choices

- When the vault or spec provides a finite set of options (mode selection, opening
  pattern, profanity register, yes/no confirmations), use `AskUserQuestion` with
  structured options.
- Put the recommended option first with "(Recommended)" appended to the label.
- Use conversational text (plain message) only for open-ended questions where the
  answer is free-form — but still ONE question at a time.

## Bad Pattern vs Good Pattern

Recognize and avoid the wall-of-text anti-pattern:

```
BAD — multiple questions in one message:
  "Great, a few things to clarify:
   1. Which mode — slide-driven polemic or panel?
   2. Any commercial intent?
   3. What profanity register for this venue?
   4. Here's the slug I generated — look right?
   5. Anything else I should know?"

GOOD — one AskUserQuestion per turn, sequentially:
  AskUserQuestion("Which presentation mode fits this talk?",
    options=[{label:"Slide-driven polemic (Recommended)", ...}, ...])
  → wait for answer →
  AskUserQuestion("What profanity register for JCON Europe?",
    options=[{label:"Moderate — damn/hell (Recommended)", ...}, ...])
  → wait for answer →
  "Any venue-specific context I should know about JCON Europe?"
  → wait for answer →
  AskUserQuestion("Generated slug: 2026-06-23-jcon-robocoders — confirm?",
    options=[{label:"Looks good (Recommended)", ...}, {label:"I want to adjust", ...}])
```

## Phase 2 Decisions

- Each rhetorical instrument decision (mode, opening, narrative arc, humor, etc.)
  is its own turn. Present options from the vault, recommend one, wait for the
  author's choice before moving to the next decision.
- Never combine instrument selections into a single message.

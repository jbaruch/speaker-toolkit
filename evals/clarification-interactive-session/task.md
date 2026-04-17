# Vault Clarification Interactive Session

## Problem/Feature Description

One talk ("Robocoders: Judgment Day") has been processed through vault-ingress. The automated analysis identified rhetoric patterns, humor beats, and blind spots. Now a clarification session is needed to:

1. Clarify surprising patterns (the delayed self-introduction — was it intentional?)
2. Conduct a humor post-mortem (grade each joke, capture spontaneous moments)
3. Probe blind spots (demo engagement, theatrical opening, Q&A room dynamics)
4. Capture speaker infrastructure config (first session — all config fields are empty)
5. Store confirmed intents and mark the session complete

This is the speaker's first clarification session (`clarification_sessions_completed: 0`), so infrastructure config capture (Step 5B) is required.

## Setup

Download the vault state:

```bash
curl -sLO https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-clarification-session/tracking-database.json
curl -sLO https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-clarification-session/rhetoric-style-summary.md
```

## Task

Run a clarification session on the processed talk. The session must cover all five steps from the vault-clarification skill:

### Step 1: Rhetoric Clarification
- The analysis flagged `delayed_self_introduction` as surprising. Ask the speaker whether this is deliberate, accidental, or context-dependent.
- Ask ONE question at a time, not a batch.

### Step 2: Blind Spot Probing
- For the demo section (slides 14-16): ask about audience engagement during live coding
- For the theatrical opening (slides 1-2): ask about any stage effects tied to "Judgment Day"
- For the Q&A section (slides 30-31): ask about room dynamics when speaker moved from mic

### Step 3: Humor Post-Mortem
- Walk through each of the 4 identified humor beats and ask if they landed
- Grade each with: `hit`, `nod`, `flat`, or `spontaneous_hit`
- Specifically probe the transcript gap after slide 15 — was there an off-script moment?
- Ask about spontaneous humor not captured in the transcript
- For any spontaneous humor that landed well, recommend whether to promote it to a planned beat

### Step 4: Infrastructure Config Capture
Since `clarification_sessions_completed` is 0, ask for all empty config fields:
- speaker_name, speaker_handle, speaker_website
- shownotes_url_pattern, shownotes_slug_convention
- template_pptx_path, presentation_file_convention
- publishing_process details (export format, QR code settings, shortener)

### Step 5: Mark Complete
- Increment `clarification_sessions_completed` to 1
- Store all confirmed intents in `confirmed_intents` array

## Output Specification

Produce an updated `tracking-database.json` with:
- `config.clarification_sessions_completed` incremented to 1
- All infrastructure config fields populated from speaker responses
- `confirmed_intents` array with at least 1 entry (the delayed intro pattern)
- Each talk entry updated with `humor_postmortem` (grades per beat) and `blind_spot_observations`

Also produce an updated `rhetoric-style-summary.md` incorporating the new findings from the clarification session.

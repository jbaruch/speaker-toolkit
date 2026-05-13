# Vault Clarification Interactive Session

## Problem/Feature Description

One talk ("Robocoders: Judgment Day") has been processed through vault-ingress. The automated analysis identified rhetoric patterns, humor beats, and blind spots that the transcript and slides alone cannot fully resolve. The vault is in its initial state — all infrastructure config fields are empty and no prior clarification session has been recorded.

## Setup

Download the vault state:

```bash
curl -sLO https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-clarification-session/tracking-database.json
curl -sLO https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-clarification-session/rhetoric-style-summary.md
```

## Task

The speaker has just delivered "Robocoders: Judgment Day". The vault has automated observations that need human input before they can be used downstream:

- The `delayed_self_introduction` pattern was flagged as surprising — the analysis can't tell whether it was deliberate or accidental.
- Four humor beats were detected, plus an 8-second transcript gap after slide 15 that may indicate an off-script moment.
- The demo section (slides 14-16), theatrical opening (slides 1-2), and Q&A section (slides 30-31) have content the transcript can't capture: audience reactions, stage effects, room dynamics.
- This is the speaker's first clarification session, and infrastructure config fields are empty.

Run the clarification needed to resolve those gaps and bring the vault to a state where downstream skills (vault-profile, presentation-creator) can rely on it.

## Output Specification

Produce an updated `tracking-database.json` with:
- All infrastructure config fields populated from speaker responses
- The speaker's confirmed interpretation of the delayed-intro pattern stored alongside the talk
- Each talk's humor performance and blind-spot observations captured in the database

Also produce an updated `rhetoric-style-summary.md` incorporating the new findings from the clarification session.

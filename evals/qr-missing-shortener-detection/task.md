# QR Generation for a Closing Slide

## Problem/Feature Description

A speaker asks the agent to generate a QR code for their talk's closing slide. The agent has the speaker profile and the talk's outline; it should produce the QR per the speaker's documented publishing process.

## Output Specification

Produce the following files:

1. **`agent-response.md`** — the agent's response to the speaker.
2. **`qr-generation-plan.md`** — the plan documenting what the agent will run and what URL the QR will encode.

## Input Files

Download fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/qr-missing-shortener-detection"
mkdir -p inputs/vault inputs/talk
curl -L -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
curl -L -o inputs/vault/tracking-database.json "$BASE/tracking-database.json"
curl -L -o inputs/talk/outline.yaml "$BASE/outline.yaml"
```

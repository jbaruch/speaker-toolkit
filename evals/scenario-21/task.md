# QR Generation with Bitly Custom Back-Half and Slug from Spec

## Problem/Feature Description

A speaker wants a QR code for the closing slide of their talk. The talk has been published and shownotes exist. The fixture provides the presentation spec and the speaker profile.

Using the presentation-creator skill, plan the QR generation workflow and document the commands that would be run.

## Output Specification

Produce the following files:

1. **`qr-generation-plan.md`** — The complete plan including:
   - The exact command that would be run to generate the QR
   - The shownotes URL (constructed from the profile pattern and the talk slug)
   - What URL the QR will encode
2. **`verification-report.md`** — Document:
   - Which script was referenced
   - Where the talk slug came from
   - The expected shortened URL format
   - The reasoning behind which URL the QR encodes

## Input Files

Download vault fixtures from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-21"
mkdir -p inputs/vault inputs/talk
curl -L -o inputs/vault/speaker-profile.json "$BASE/speaker-profile.json"
curl -L -o inputs/vault/secrets.json "$BASE/secrets.json"
curl -L -o inputs/vault/tracking-database.json "$BASE/tracking-database.json"
curl -L -o inputs/talk/presentation-spec.md "$BASE/presentation-spec.md"
```

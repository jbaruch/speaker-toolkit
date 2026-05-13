# Humor Post-Mortem and Blind Spot Debrief

## Problem/Feature Description

Two talks have been processed through vault-ingress and their analysis is complete. Now the speaker needs a post-analysis debrief covering:

1. **Humor post-mortem** — walk through each identified humor beat and grade its effectiveness
2. **Blind spot capture** — probe for information transcripts cannot reveal (audience reactions, stage moments, room context)
3. **Recency adaptation** — the recent talk gets detailed per-joke questioning; the old talk gets compressed broad-strokes questions

## Setup

Download the two fixed analysis files:

```bash
curl -sLO https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-12/test_analysis_recent.json
curl -sLO https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-12/test_analysis_old.json
```

## Task

Process both talk analyses and produce structured debrief outputs:

1. **For the recent talk** (`test_analysis_recent.json` — "Robocoders: Judgment Day", 7 days ago):
   - Generate a debrief questionnaire that walks the speaker through the recent talk's humor performance
   - Include questions about each meme slide's audience reaction
   - Cover the demo sections (d1, d2) and the theatrical opening (bs3)

2. **For the old talk** (`test_analysis_old.json` — "Groovy Puzzlers", 3 years ago):
   - Generate a debrief appropriate to a talk delivered 3 years ago
   - Still capture notable audience moments

3. **Produce structured output** as JSON files:
   - `debrief_questionnaire_recent.json` — the questionnaire for the recent talk
   - `debrief_questionnaire_old.json` — the questionnaire for the old talk
   - Each question should reference specific analysis observations (humor beat IDs, slide numbers, quotes)
   - Blind spot observations stored as structured fields, not free text

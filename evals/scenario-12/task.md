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
   - Generate a debrief questionnaire with per-joke questions grounded in the specific humor beats from the analysis (reference actual quotes, slide numbers, meme descriptions)
   - Include questions about each meme slide's audience reaction
   - Include a dedicated question about spontaneous humor not captured in the transcript (h5 has a suspicious gap)
   - Include blind spot questions for the demo sections (d1, d2) and the theatrical opening (bs3)
   - For any spontaneous humor that landed well, include a "promote to planned beat?" recommendation

2. **For the old talk** (`test_analysis_old.json` — "Groovy Puzzlers", 3 years ago):
   - Generate a COMPRESSED debrief — broad questions only, not per-joke grading
   - Ask "any jokes you remember landing particularly well or badly?" rather than walking through each beat
   - Still capture notable audience moments but in summary form

3. **Produce structured output** as JSON files:
   - `debrief_questionnaire_recent.json` — the per-beat questionnaire for the recent talk
   - `debrief_questionnaire_old.json` — the compressed questionnaire for the old talk
   - Each question should reference specific analysis observations (humor beat IDs, slide numbers, quotes)
   - Each humor beat should have a `humor_grade` field from: `hit`, `nod`, `flat`, `spontaneous_hit`
   - Blind spot observations stored as structured fields, not free text

The old talk debrief must be demonstrably shorter than the recent talk debrief.

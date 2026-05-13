# Extract Resources for Shownotes Publishing

## Problem/Feature Description

A speaker is preparing to publish shownotes for their talk "Robocoders: Judgment Day" at DevNexus 2026. The presentation outline contains URLs, GitHub repos, book references, RFC citations, and tool mentions scattered across speaker notes and visual descriptions. Before publishing, they need a consolidated, categorized list of all resources mentioned in the talk.

Using the presentation-creator skill, extract resources from the outline and produce the resource list for the speaker to review.

## Output Specification

Produce the following files:

1. **`resources.json`** — The extracted resources in JSON format, as produced by the extraction workflow
2. **`workflow-log.md`** — Document the exact commands run, including:
   - Which script was used for extraction
   - The command-line arguments passed
   - Any observations about the extracted resources (categories found, duplicates removed, items that should NOT appear)

## Input Files

Download the outline and spec from the project repository:

```bash
BASE="https://github.com/jbaruch/speaker-toolkit/raw/main/eval-resources/scenario-22"
mkdir -p inputs
curl -L -o inputs/presentation-outline.md "$BASE/presentation-outline.md"
curl -L -o inputs/presentation-spec.md "$BASE/presentation-spec.md"
```

## Key Parameters

- Use the talk slug from the spec.
- The outline contains URLs in code blocks and image prompts as well as in body text. It mentions GitHub repo references, two book citations, three RFC mentions, and several tool names in backticks.
- The URL `https://dora.dev` appears twice.
- The Coda slide (slide 58) has resources that should be prioritized.

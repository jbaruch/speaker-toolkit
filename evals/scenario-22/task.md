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

- **Talk slug:** `2026-04-16-devnexus-robocoders-judgment-day`
- The outline contains URLs in speaker notes, GitHub repo references, two book citations, three RFC mentions, and several tool names in backticks
- Some URLs appear inside code blocks (should NOT be extracted)
- One URL appears inside an Image prompt field (should NOT be extracted)
- The URL `https://dora.dev` appears twice — should be deduplicated
- The Coda slide (slide 58) has resources that should be prioritized

## Notes on Verification

The critical tests:
1. A script was used for extraction, not manual scanning
2. The output is valid JSON with the expected structure (talk_slug, extracted_at, resources array)
3. URLs from code blocks are NOT in the output
4. URLs from Image prompt lines are NOT in the output
5. Duplicate URLs are deduplicated
6. Resources are categorized by type (url, repo, book, rfc, tool)
7. The talk slug comes from the spec, not invented

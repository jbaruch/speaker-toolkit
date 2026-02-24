---
name: creating-eval-scenarios
description: Generate evaluation scenarios for Tessl tiles to measure skill effectiveness. Creates inventory of instructions from the skill, test cases with success criteria, and validates skill coverage. Use when asked to "generate evals", "create evaluation scenarios", "test this skill", "measure skill value", or "prepare for tessl publish".
---

# Creating Eval Scenarios

Generate evaluation scenarios that measure whether agents follow instructions from skills.

## Prerequisites

Skills must be packaged in a Tessl tile (directory with `tile.json` + skill folders). If not, use the `converting-skill-to-tessl-tile` skill first. Ask the user where to put the tile if its not specified.

Its possible for a tile to contain multiple skills.  In this case, split the tile into multiple tiles, one for each skill first.

## Quick Start

Read  [references/scenario-generation.md](references/scenario-generation.md) before starting.
It will guide you through the workflow of researching the tile and creating all the expected files in the correct formats.


## Output Structure

```
<tile>/evals/
├── instructions.json          # Json containing list of all instructions in the skill
├── summary.json               # Feasible scenarios
├── summary_infeasible.json    # Infeasible capabilities (no folders)
└── scenario-N/
    ├── task.md                # Goal description (may include inlined inputs)
    ├── criteria.json          # Scoring rubric (must sum to 100)
    └── capability.txt         # Single line: capability being tested
```

## Eval Constraints

The eval is one-shot and file-based:
- No proprietary software is preinstalled, or any API_keys, or any additional files
- Agent receives task → produces output files in its working directory
- Scorer reviews just the files the agent created (source code, outputs, etc.)
- **NO** observation of agent process during execution
- **NO** interactive back-and-forth
The eval will time out if the scenario takes too long to complete or leaves any large files on disk at the end.

Mark capabilities as **infeasible** if they won't work in this sandbox.


## Running Evals

Once ready, you can trigger the eval run on the tessl platform.
```bash
tessl eval run <path/to/tile>
tessl eval view-status <status_id> --json
tessl eval list
```

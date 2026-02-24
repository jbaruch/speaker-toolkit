---
name: converting-skill-to-tessl-tile
description: Package a standalone skill into a Tessl tile for versioning, distribution, and evaluation. Creates tile manifest, validates directory structure, and ensures skill format compliance. Use when asked to "convert to tile", "package this skill", "create a tessl tile", "wrap skill in tile", or before running evals on a skill not yet in a tile.
---

# Converting Skills to Tessl Tiles

Wrap standalone skills into Tessl tiles to enable versioning, publishing, and evaluation.

## Prerequisites

Tessl CLI must be installed. Verify with:
```bash
tessl --version
```

If not installed, visit https://docs.tessl.io/

## Quick Start

```bash
# 1. Create new tile
tessl tile new <tile-name>

# 2. Copy skill into tile directory
cp -r <skill-folder> <tile-name>/

# 3. Update tile.json to reference the skill (see schema below)

# 4. Validate
tessl tile lint <tile-name>
```

If lint fails, see [Common Lint Errors](#common-lint-errors) below, fix issues, then re-run lint.

## Tile Structure

```
<tile-name>/
├── tile.json
└── <skill-name>/
    ├── SKILL.md
    ├── references/   (optional)
    └── scripts/      (optional)
```

## tile.json Schema

```json
{
  "name": "<workspace>/<tile-name>",
  "version": "0.0.1",
  "summary": "Brief description of what this tile provides.",
  "private": true,
  "skills": {
    "<skill-name>": {
      "path": "<skill-name>/SKILL.md"
    }
  }
}
```

**Fields:**
- `name`: Format `workspace/tile-name` (workspace is your tessl username or org)
- `version`: Semantic version
- `summary`: One-line description
- `private`: Set `false` to make publicly discoverable.  Tiles cannot be made private after they are published, so this should be set to `false` until the user is ready to publish.
- `skills`: Map of skill names to their SKILL.md paths

## Multiple Skills

A tile can contain multiple skills:

```json
{
  "name": "myorg/data-tools",
  "version": "1.0.0",
  "summary": "Data processing and visualization skills.",
  "private": false,
  "skills": {
    "csv-processor": {
      "path": "csv-processor/SKILL.md"
    },
    "chart-builder": {
      "path": "chart-builder/SKILL.md"
    }
  }
}
```

## Common Lint Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `missing SKILL.md` | Path in tile.json doesn't match actual file location | Update `path` to match actual SKILL.md location |
| `invalid name format` | Name missing workspace prefix | Use format `workspace/tile-name` |
| `missing frontmatter` | SKILL.md lacks YAML frontmatter | Add `---` delimited frontmatter with `name` and `description` |
| `missing description` | SKILL.md frontmatter missing description field | Add `description:` to SKILL.md frontmatter |
| `invalid version` | Version not semver format | Use format like `1.0.0` or `0.0.1` |

After fixing errors, re-run: `tessl tile lint <tile-name>`

## Using Tiles

```bash
# Install locally for testing
tessl tile install <tile-name>

# Optionally publish to registry
tessl tile publish <tile-name>
```

## Next Steps

After creating a tile, use the `creating-eval-scenarios` skill to generate evaluation scenarios.

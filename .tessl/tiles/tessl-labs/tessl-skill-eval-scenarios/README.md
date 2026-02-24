# Tessl Tile Eval

Skills for packaging and evaluating Tessl tiles.

## Skills

| Skill | Description |
|-------|-------------|
| `converting-skill-to-tessl-tile` | Wrap standalone skills into Tessl tiles |
| `creating-eval-scenarios` | Generate eval scenarios to measure skill effectiveness |

## Workflow

1. **Package**: Use `converting-skill-to-tessl-tile` to wrap skills in a tile
2. **Evaluate**: Use `creating-eval-scenarios` to generate test scenarios
3. **Run**: Execute `tessl eval run <tile-name>` to kick off the evaluation

Check on the status of evals by using `tessl eval list` and `tessl eval view-results <eval-id>`.

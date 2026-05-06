# Title Placement — Outline Schema + Scripts

Implements the policy in
[`rules/title-overlay-rules.md`](rules/title-overlay-rules.md).

## Outline schema addition

Each slide block in `presentation-outline.md` gains one optional line:

```markdown
### Slide 3: The Question
- Format: **FULL**
- Image prompt: `[STYLE ANCHOR]. <scene description> ...`
- Safe zone: upper_third (uniform backdrop drawn from the style anchor)
- Text: **how many hours last week...**
```

Grammar: `- Safe zone: <zone> (<surface>)`

- `<zone>` — one of `upper_third`, `middle_third`, `lower_third`,
  `left_half`, `right_half`. Horizontal bands reserve a full-width
  strip; half-frame zones reserve one side of the frame for the title
  column and push the subject to the opposite side. `left_third` /
  `right_third` are intentionally excluded — too narrow to hold
  horizontal title text. `middle_third` is for styles whose subject
  naturally frames a clean center opening (TV sets, monitors, windows,
  portrait frames, vignettes).
- `<surface>` — optional short phrase describing what fills the zone in
  the deck's own visual vocabulary (e.g. "unbroken painted sky", "flat
  studio backdrop", "parchment grain", "gradient wash"). If omitted, a
  generic default is used, but results are noticeably better with an
  explicit style-anchored surface.

Slides without a `Safe zone:` line generate and apply exactly as today.

## Scripts

| Script | Role |
|--------|------|
| `generate-illustrations.py` | Parses `Safe zone:` and appends the SAFE ZONE directive to each prompt before calling Gemini. |
| `apply-illustrations-to-deck.py` | Swaps generated images into a .pptx, adds a zone-sized scrim rectangle behind the title, and positions title text. Reads the same outline for zone data. Accepts `--scrim-color` / `--scrim-alpha`. |
| `suggest-scrim-color.py` | Samples the darkest 5% of pixels across a deck's illustrations and prints a scrim color + alpha tuned to the deck's natural shadow tone. |

All three live in `skills/illustrations/scripts/`.

## End-to-end workflow

```bash
# 1. Author presentation-outline.md with `Safe zone:` lines

# 2. Generate illustrations — directive appended automatically
python3 skills/illustrations/scripts/generate-illustrations.py presentation-outline.md all

# 3. (Optional) Sample a scrim color tuned to the deck's style
python3 skills/illustrations/scripts/suggest-scrim-color.py illustrations/
# -> prints: scrim base #RRGGBB, recommended alpha NNNNN

# 4. Apply to deck
python3 skills/illustrations/scripts/apply-illustrations-to-deck.py \
    deck.pptx illustrations/ presentation-outline.md \
    --out deck-with-titles.pptx \
    --scrim-color 100903 --scrim-alpha 47553   # omit for plain 45% black
```

## Notes

- **Scrim always applied, zone-scoped.** A rectangle matching the
  title zone sits between the picture and the text. Full-slide scrims
  flatten the illustration; zone-sized ones lift the title locally.
- **Scrim color sampled from the deck.** Default is 45% black. For
  styled decks (warm sepia, cool night, etc.) `suggest-scrim-color.py`
  samples the natural shadow tone — the scrim then reads as "deeper
  shadow of the same style" instead of a black film.
- **Idempotence.** `generate-illustrations.py` strips any existing
  `TITLE SAFE ZONE` block before re-appending, so re-running after a
  zone edit produces the right result.
- **Recovery path.** If a specific slide's illustration ignores the
  directive, use the Loop B pattern (vision-LLM diagnose → revised
  prompt → regenerate). Documented in the rule file; not mechanized
  as a default.

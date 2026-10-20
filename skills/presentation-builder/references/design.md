# Deck Design

## General Design Principles

This phase generates concrete slides from the outline. **Every slide should respect the design principles in `slide-design-spec.md` Section 11**, including:

- **Signal-to-Noise Ratio** — remove anything that does not encode information
- **The Big Four** — Contrast, Repetition, Alignment, Proximity
- **Picture Superiority Effect** — pictures beat words for retention; replace decorative text with concrete imagery when possible
- **Empty space is active** — default to asymmetric layouts; don't fill margins with logos or templated decoration
- **Rule of thirds** — anchor primary subjects on the 3×3 grid intersections, not dead-center
- **Faces and eye-gaze** — orient face-direction toward the focal text/chart, never away from it
- **Full-bleed images** — default to images that bleed off all four edges
- **2D for 2D data** — never apply 3D effects to flat data
- **Logo discipline** — first and last slide only (this aligns with the speaker's existing footer convention; the footer is not a logo)
- **Minimum font size** — body text ~24pt or larger at 16:9 conference resolution
- **Visual relationships** — when an outline slide contains bulleted content, identify which of five relationships the bullets express (flow / structure / cluster / radiate / influence) and convert the bullets into a diagram form rather than a list. Bullets are the fallback only when none of the five relationships fit. See `slide-design-spec.md` §11.13.
- **Image juxtaposition** — when content is comparison-shaped (any of the contrast types from `sparkline`'s middle), prefer paired-image slides over single-image slides. Place two images side-by-side at equal weight, or use before/after with a transition arrow. See `slide-design-spec.md` §11.14.
- **Numerical narrative** — for data slides, choose one of three framing techniques: Scale (anchor against familiar magnitude), Compare (cross-domain comparison), or Context (annotate why the chart's bumps and trends look the way they do). Raw numbers without one of these framings are forgettable. See the "Numerical Narrative — Making Numbers Land" subsection in [vacation-photos.md](../../presentation-creator/references/patterns/build/vacation-photos.md).

Speaker-style data in `slide-design-spec.md` Sections 1–10 (extracted from the speaker's actual deck corpus) takes precedence where it exists. The principles in Sections 11.1–11.14 are the default for layout decisions where the corpus is silent.

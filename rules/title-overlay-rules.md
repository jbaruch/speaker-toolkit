# Title Overlay Rules

Steering rules for placing overlaid slide titles on illustrated slides.
Covers the generation-time directive pattern, the zones in use, and the
safety net that applies regardless of placement.

## 1. Engineer Negative Space at Generation Time

When a slide will have a title overlaid on an illustration, bake a
`TITLE SAFE ZONE` directive into the image prompt **before** generation.
Do not rely on post-hoc placement heuristics to find a safe zone — if
the generator doesn't know about it, the subject will occupy the best
area by default.

Directive to append to every Image prompt:

```
TITLE SAFE ZONE -- CRITICAL COMPOSITION RULE: Reserve the {zone} of
the 16:9 frame as clean uninterrupted negative space filled only with
{surface}. No subjects, objects, text, props, or focal points may
appear in this region. The scene's subjects must be composed entirely
in the remaining portion of the frame. This negative space will carry
an overlaid title.
```

Where `{zone}` is `upper third`, `middle third`, `lower third`, `left half`,
or `right half` (see §2 for the full list), and
`{surface}` is a short style-specific description of what should fill
the zone (a uniform area drawn from the style anchor — for example,
"an unbroken area of the painted sky", "a clean stretch of the studio
backdrop", "a flat region of the base texture used elsewhere in the
frame"). Always phrase the surface in the style's own vocabulary so
the generator reaches for materials it already knows how to render.

## 2. Five Zones Cover Practical Compositions

Three horizontal-band zones and two half-frame zones are supported:

- **`upper_third`** — uniform backdrop above the subject (sky, ceiling,
  wall, gradient, etc. depending on style). Use for landscapes,
  portraits, hero shots, and most open compositions.
- **`middle_third`** — reserved center band, with the subject framing
  around it. Use for styles that produce TV sets, portrait frames,
  vignettes, windows, or any composition where the focal subject
  surrounds a clean central opening intended to hold the title.
- **`lower_third`** — uniform region below the subject. Use when the
  subject is centered and top-heavy (e.g. a poster, hero object, or
  sign that naturally leaves surface below it).
- **`left_half`** — left side of the frame reserved as clean surface,
  subject composed on the right. Use for split-panel, side-by-side,
  or "subject pushed to one side" compositions.
- **`right_half`** — mirror of `left_half`: subject on the left, clean
  surface on the right. Useful when the subject naturally faces or
  moves leftward.

Do **not** use `left_third` or `right_third` — a third of a 16:9 frame
is too narrow a vertical column for readable horizontal title text.
`left_half` / `right_half` give the title enough column width to wrap
across a few lines.

## 3. Pick the Zone Per Slide Based on Subject Geometry

A global default fails. Assign the zone per slide based on where the
subject naturally sits, in the vocabulary of the chosen style:

| Composition | Zone |
|-------------|------|
| Open landscape or scene with a uniform backdrop above the subject | `upper_third` |
| Portrait / hero object with clean space above | `upper_third` |
| Overhead shot with a clean surface at the top of frame | `upper_third` |
| Framed composition (TV, monitor, window, portrait frame, vignette) | `middle_third` |
| Full-frame artifact (poster, sign, document) with surface below it | `lower_third` |
| Silhouette or element rising from the bottom against open backdrop | `lower_third` |
| Subject pushed right, facing right, or split-panel with clean left side | `left_half` |
| Subject pushed left, facing left, or split-panel with clean right side | `right_half` |

The concrete surface (sky, fabric, paper, parchment, gradient, etc.)
is chosen from the deck's style anchor. The zone assignment is what
this rule governs.

Persist assignments in the design brief as a per-slide table so the
brief stays the single source of truth.

## 4. Brightness Is Not the Same as Cleanness

A brightness-based band picker conflates *darkness* with *safe*. A
bright uniform backdrop is a valid title region; a dark cluttered
scene is not. If you need a programmatic signal, use *variance* (low
variance = uniform) rather than mean luminance. Better: specify the
zone in the brief and skip the picker entirely.

## 5. Always Apply a Scrim Behind the Title

Regardless of zone choice, add a semi-transparent rectangle **sized to
the title zone** (not the whole slide) between the background picture
and the text. Scope matters: a full-slide scrim flattens the whole
illustration, while a zone-sized scrim lifts the title locally and
leaves the rest of the scene at full brightness.

Default: 45% black.

```xml
<p:sp>
  <p:spPr>
    <a:xfrm>.. zone box ..</a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
    <a:solidFill>
      <a:srgbClr val="000000"><a:alpha val="45000"/></a:srgbClr>
    </a:solidFill>
    <a:ln><a:noFill/></a:ln>
  </p:spPr>
</p:sp>
```

OOXML child order inside `<p:spPr>` must be `xfrm → prstGeom → solidFill
→ ln`. Keynote (and some strict OOXML readers) silently drop the fill
when `<a:ln>` precedes `<a:solidFill>`, which is the exact failure mode
that makes "scrim isn't rendering" bugs look like "scrim has no visible
effect."

### Tinted scrims for styled decks

Pure black is the right default for neutral styles. Warm-toned decks
(sepia, painted Western, golden hour) and cool-toned decks (cyanotype,
night, deep space) read better with a scrim color sampled from the
deck's own natural shadows — the title still sits on a darker field,
but the darkening looks like "deeper shadow of the same style" rather
than a black film dropped on top.

Suggested sampler (`skills/illustrations/scripts/suggest-scrim-color.py`):

1. Resize each illustration to ~200px longest edge.
2. Take the darkest 5% of pixels across the whole deck by Rec. 709
   luminance.
3. Average their sRGB.
4. Clamp the result to a target luminance (~0.10) so mid-shadow averages
   don't produce a washed-out scrim.
5. Bump alpha above 45% slightly when the sample is chromatic (a tinted
   scrim loses some darkening power to the tint).

Persist the chosen color and alpha in the deck's design brief once, not
per slide.

## 6. Callbacks and Bookends Break Under Independent Regen

When two slides are meant to be the same scene with one detail
changed (bookend pattern — first and last slide of a deck), independent
Gemini calls produce two different scenes. Generate the base slide
first, then **edit** the callback slide from the base output instead
of regenerating. This is consistent with the edit-vs-regenerate rule
in `illustration-rules.md`: the callback is a content *modification*
of an existing image, not a fresh concept.

## 7. Loop B Is the Recovery Pattern, Not the Primary Pipeline

When the up-front SAFE ZONE directive fails on a slide (the generator
put the subject in the declared safe zone anyway):

1. Send the generated image + the original prompt + the title to a
   vision LLM, asking for a diagnosis and a revised prompt.
2. Regenerate with the revised prompt.

This costs an extra round-trip per slide. Use it only for the 10–25%
of slides that resist the initial directive, not as the default path.

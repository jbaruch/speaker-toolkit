#!/usr/bin/env python3
"""Outline schema — the source-of-truth document for a talk.

`outline.yaml` is the single hand-edited (well, agent-edited) artifact per talk.
`narrative.md`, `rhetorical-review.md`, `script.md`, and `slides.md` are
generated from it by separate extractor scripts.

Pattern IDs are validated against the closed enum discovered from
`references/patterns/{prepare,build,deliver}/*.md` at import time. Antipatterns
(`_anti_*.md`) are deliberately excluded — antipatterns surface as detections
in `rhetorical-review.md`, never as authored declarations. The observable
vs unobservable distinction within the patterns taxonomy is a Phase 6
checklist concern, not a schema concern; the schema accepts any non-antipattern.
"""

from __future__ import annotations

import json
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


class _StrictModel(BaseModel):
    """Base for every outline model — rejects unknown fields.

    `extra='forbid'` catches misspelled or unsupported YAML keys at load
    time instead of silently dropping them, which is the right call for
    a source-of-truth schema downstream extractors depend on.
    """

    model_config = ConfigDict(extra="forbid")

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# ── Pattern enum: discovered from the patterns directory ──────────────

_PATTERNS_DIR = (
    Path(__file__).resolve().parent.parent / "references" / "patterns"
)


def _discover_pattern_ids() -> tuple[frozenset[str], frozenset[str]]:
    """Return (allowed_in_outline, antipattern_ids).

    Walks all three phase directories. Any non-antipattern, non-index file
    is allowed; antipatterns (file prefix `_anti_`) are rejected.
    """
    allowed: set[str] = set()
    antipatterns: set[str] = set()

    for phase in ("prepare", "build", "deliver"):
        for md in (_PATTERNS_DIR / phase).glob("*.md"):
            stem = md.stem
            if stem.startswith("_anti_"):
                antipatterns.add(stem.removeprefix("_anti_"))
            elif stem.startswith("_"):
                continue
            else:
                allowed.add(stem)

    return frozenset(allowed), frozenset(antipatterns)


PATTERN_IDS, ANTIPATTERN_IDS = _discover_pattern_ids()

ARCHITECTURE_IDS: frozenset[str] = frozenset({
    "narrative-arc", "sparkline", "fourthought", "triad", "talklet",
    "expansion-joints", "lightning-talk", "takahashi", "cave-painting",
})


# ── Closed enums for instance metadata ───────────────────────────────


class AudienceSpread(str, Enum):
    """Whether the room is mixed in what it accepts as proof.

    Drives `walk-around`'s cover-or-match decision. Homogeneity is a claim
    about what persuades the room, never about job titles.
    """

    heterogeneous = "heterogeneous"
    homogeneous = "homogeneous"


class Register(str, Enum):
    """The four question archetypes a `walk-around` answers.

    Herrmann's quadrant letters, kept as a recognizable handle. These name
    kinds of question, never kinds of person — see
    `references/patterns/prepare/walk-around.md`.
    """

    a_precision = "A"  # what exactly, and how do you know?
    b_process = "B"  # how does it work, in what order?
    c_impact = "C"  # who does this affect, and how will it land?
    d_implication = "D"  # where does this lead, what does it connect to?


class PunchFlavor(str, Enum):
    personal = "personal"
    unexpected = "unexpected"
    novel = "novel"
    challenging = "challenging"
    humorous = "humorous"


class StarSubtype(str, Enum):
    memorable_dramatization = "memorable-dramatization"
    repeatable_sound_bite = "repeatable-sound-bite"
    evocative_visual = "evocative-visual"
    emotive_storytelling = "emotive-storytelling"
    shocking_statistic = "shocking-statistic"


class ResistanceVector(str, Enum):
    comfort_zone = "comfort-zone"
    fear = "fear"
    vulnerabilities = "vulnerabilities"
    misunderstanding = "misunderstanding"
    obstacles = "obstacles"
    politics = "politics"


class MasterStoryBeat(str, Enum):
    introduce = "introduce"
    recall_1 = "recall-1"
    recall_2 = "recall-2"
    recall_3 = "recall-3"


class SlideFormat(str, Enum):
    full = "FULL"
    img_txt = "IMG+TXT"
    exception = "EXCEPTION"
    demo = "DEMO"
    # Enum members shadow inherited str methods by design — `SlideFormat.title`
    # resolves to the member, never to `str.title`. The assignment-type finding
    # is a false positive on every str-Enum member named after a str method.
    title = "TITLE"  # pyright: ignore[reportAssignmentType]


class Composition(str, Enum):
    """Deck-wide illustration composition (see rules/title-overlay-rules.md).

    `standard` overlays titles/footers at apply time over a reserved safe zone;
    `poster-theatrical` bakes title + footer into the image as part of the scene.
    Absence of the field means `standard`.
    """

    standard = "standard"
    poster_theatrical = "poster-theatrical"


class SafeZoneName(str, Enum):
    upper_third = "upper_third"
    middle_third = "middle_third"
    lower_third = "lower_third"
    left_half = "left_half"
    right_half = "right_half"


class Renderer(str, Enum):
    pptx = "pptx"
    presenterm = "presenterm"


class AudienceTemperament(str, Enum):
    doer = "doer"
    supplier = "supplier"
    influencer = "influencer"
    innovator = "innovator"


# ── Pattern application: pattern id + per-pattern instance metadata ──

# Maps pattern id → set of instance-metadata fields it accepts.
# Empty set means the pattern carries no instance metadata.
_PATTERN_INSTANCE_FIELDS: dict[str, frozenset[str]] = {
    "opening-punch": frozenset({"flavors"}),
    "star-moment": frozenset({"subtype"}),
    "inoculation": frozenset({"resistance_vector"}),
    "master-story": frozenset({"story_id", "beat"}),
    "foreshadowing": frozenset({"plant_id"}),
    "call-to-adventure": frozenset({"big_idea_text"}),
    "call-to-action": frozenset({"asks"}),
    "walk-around": frozenset({"registers"}),
}

_ALL_INSTANCE_FIELDS: frozenset[str] = frozenset({
    "flavors", "subtype", "resistance_vector",
    "story_id", "beat", "plant_id", "big_idea_text", "asks",
    "registers",
})


class AppliedPattern(_StrictModel):
    """One pattern application — either at talk level or slide level."""

    id: str
    flavors: list[PunchFlavor] | None = None
    subtype: StarSubtype | None = None
    resistance_vector: ResistanceVector | None = None
    story_id: str | None = None
    beat: MasterStoryBeat | None = None
    plant_id: str | None = None
    big_idea_text: str | None = None
    asks: dict[AudienceTemperament, str] | None = None
    # Which of the four question archetypes this walk-around application
    # answers. The agent judges which registers a claim actually lands;
    # check-rhetorical.py checks the union across the talk.
    registers: list[Register] | None = Field(default=None, min_length=1)

    @field_validator("id")
    @classmethod
    def _id_in_closed_set(cls, v: str) -> str:
        if v in PATTERN_IDS:
            return v
        if v in ANTIPATTERN_IDS:
            raise ValueError(
                f"pattern id '{v}' is an antipattern — antipatterns are not "
                f"declared in outline.yaml; they surface in rhetorical-review",
            )
        raise ValueError(
            f"pattern id '{v}' not found in references/patterns/",
        )

    @model_validator(mode="after")
    def _instance_data_matches_pattern(self) -> "AppliedPattern":
        allowed = _PATTERN_INSTANCE_FIELDS.get(self.id, frozenset())
        for field_name in _ALL_INSTANCE_FIELDS:
            if getattr(self, field_name) is not None and field_name not in allowed:
                raise ValueError(
                    f"pattern '{self.id}' does not accept '{field_name}' "
                    f"(accepted: {sorted(allowed) or 'none'})",
                )
        return self


# ── Slide-level structural ledger entries ────────────────────────────


class Callback(_StrictModel):
    kind: Literal["plant", "pay"]
    id: str
    variation: str | None = None


class ProgressiveListEntry(_StrictModel):
    id: str
    item_index: int = Field(ge=1)


class RunningGagEntry(_StrictModel):
    id: str
    appearance_index: int = Field(ge=1)


class SafeZone(_StrictModel):
    """Per-slide title safe zone for standard-composition illustrations.

    Reserves negative space in the generated image for an overlaid title;
    `surface` optionally overrides the default backdrop description for the
    zone. See rules/title-overlay-rules.md.
    """

    zone: SafeZoneName
    surface: str | None = None


class Build(_StrictModel):
    step: int = Field(ge=0)
    desc: str
    # Backwards-erase prompt for `generate-illustrations.py --build`. `desc` is
    # the additive, human-facing reveal ("Add the second pillar"); `erase` is the
    # instruction that turns step N+1 into this step by removing what N+1 added,
    # with explicit "Keep ..." clauses for everything that must persist. The
    # final (full-image) step needs no erase prompt — it is copied from the base
    # slide image. Optional so slides whose builds are only deck-budget
    # placeholders validate; --build refuses any non-final step missing it.
    erase: str | None = None
    # Optional erase region as a normalized bounding box [x0, y0, x1, y1] in
    # 0..1 image coords (origin top-left). When set, --build confines the edit to
    # this box: the static background outside it is preserved pixel-for-pixel
    # (OpenAI gets a real edit mask; Gemini's full regeneration is composited back
    # over the prior frame outside the box). Without it, the whole frame is
    # regenerated and a static background can drift (#90). Belongs only on
    # non-final steps — the final step is a verbatim copy, never edited.
    erase_region: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def _check_erase_region(self) -> "Build":
        if self.erase_region is None:
            return self
        x0, y0, x1, y1 = self.erase_region
        if not all(0.0 <= v <= 1.0 for v in self.erase_region):
            raise ValueError(
                f"erase_region values must be in 0..1 (normalized), got {self.erase_region}"
            )
        if x0 >= x1 or y0 >= y1:
            raise ValueError(
                "erase_region must be [x0, y0, x1, y1] with x0 < x1 and y0 < y1, "
                f"got {self.erase_region}"
            )
        return self


# ── Screenplay-form script ───────────────────────────────────────────


class ScriptItem(_StrictModel):
    """One unit in a slide's screenplay block.

    Exactly one of {cue, parenthetical, line} is set. `speaker` is required
    iff the talk has more than one speaker (enforced at the Outline level).
    """

    cue: str | None = None
    parenthetical: str | None = None
    line: str | None = None
    speaker: str | None = None

    @model_validator(mode="after")
    def _exactly_one_content(self) -> "ScriptItem":
        present = [
            x for x in (self.cue, self.parenthetical, self.line) if x is not None
        ]
        if len(present) != 1:
            raise ValueError(
                "script item must have exactly one of {cue, parenthetical, line}",
            )
        if self.speaker is not None and self.cue is not None:
            raise ValueError(
                "speaker attribution does not apply to cue items "
                "(cues are scene-level, not speaker-attributed)",
            )
        return self


# ── Narrative-side: chapters + argument beats ────────────────────────


class ArgumentBeat(_StrictModel):
    text: str
    slide_refs: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Chapter(_StrictModel):
    id: str
    title: str
    target_min: float = Field(gt=0)
    accent: str | None = None
    cuttable: bool = False
    argument_beats: list[ArgumentBeat] = Field(default_factory=list)


# ── Illustration style anchor (optional, per talk) ───────────────────


class StyleAnchor(_StrictModel):
    model: str
    full: str
    imgtxt: str
    conventions: str
    # Deck-wide composition; null == standard overlay. poster-theatrical bakes
    # the title (+ embedded_footer) into every image. See rules/title-overlay-rules.md.
    composition: Composition | None = None
    embedded_footer: str | None = None
    # How baked title + footer text is rendered in poster-theatrical mode (e.g.
    # "glowing hand-script neon on an in-scene surface"). Lives on the anchor so
    # every slide's text is styled identically; the per-slide image_prompt carries
    # only the scene and text_overlay carries only the literal title string. Only
    # consumed in poster-theatrical mode; null falls back to a generic treatment.
    text_treatment: str | None = None


# ── Talk metadata ────────────────────────────────────────────────────


class TalkMetadata(_StrictModel):
    title: str
    slug: str
    speakers: list[str] = Field(min_length=1)
    duration_min: float = Field(gt=0)
    audience: str
    # Whether the room is mixed in what it accepts as proof, or uniform.
    # Drives the `walk-around` cover-or-match decision: a heterogeneous room
    # gets all four registers, a homogeneous one gets its own. Declared at
    # intake so the choice is made deliberately rather than defaulted into.
    audience_spread: AudienceSpread
    # Which register a homogeneous room speaks. Required iff the room is
    # homogeneous; forbidden otherwise (there is no single register to name
    # for a mixed room).
    dominant_register: Register | None = None
    mode: str
    venue: str
    slide_budget: int = Field(gt=0)
    pacing_wpm: tuple[int, int]
    architecture: str
    applied_patterns: list[AppliedPattern] = Field(default_factory=list)

    @model_validator(mode="after")
    def _walk_around_is_per_claim(self) -> "TalkMetadata":
        """`walk-around` audits a claim, and a claim has a location.

        Slides and interludes both carry claims and are individually
        checkable — a live demo answering "how does it work in what order"
        is a B answer no slide can match. Talk level carries no claim: it
        asserts that the talk answers a register somewhere, with nothing to
        check it against, which is the unfalsifiable shape the audit exists
        to prevent.
        """
        if any(p.id == "walk-around" for p in self.applied_patterns):
            raise ValueError(
                "`walk-around` is a per-claim audit and cannot be declared at "
                "talk level — attach it to the slides or interludes carrying "
                "the load-bearing claims, with `registers:` naming what each "
                "one answers",
            )
        return self

    @model_validator(mode="after")
    def _register_matches_spread(self) -> "TalkMetadata":
        if self.audience_spread == AudienceSpread.homogeneous:
            if self.dominant_register is None:
                raise ValueError(
                    "audience_spread 'homogeneous' requires 'dominant_register' "
                    "(A=precision/evidence, B=process/sequence, C=human impact, "
                    "D=implication) — name the register the room speaks, or set "
                    "audience_spread to 'heterogeneous' and cover all four",
                )
        elif self.dominant_register is not None:
            raise ValueError(
                "audience_spread 'heterogeneous' does not accept "
                "'dominant_register' — a mixed room has no single register; "
                "cover all four via walk-around instead",
            )
        return self

    # Spec metadata (collapsed from the legacy presentation-spec.md).
    # All optional — older outlines without these fields still validate.
    thesis: str | None = None
    # A reader-facing summary of `thesis` — a couple of paragraphs or a short
    # bulleted list. Authored as a distillation of the elaborated thesis;
    # narrative.md renders it verbatim as the TL;DR (it never reprints `thesis`).
    tldr: str | None = None
    shownotes_url_base: str | None = None
    commercial_intent: str | None = None
    profanity_register: str | None = None
    must_include: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    catalog_reference: str | None = None
    delivery_count: int | None = Field(default=None, ge=1)
    delivery_date: str | None = None  # ISO YYYY-MM-DD

    # Deck tooling + theme, sourced in Phase 2 Decision #2. All optional —
    # older outlines without these fields still validate.
    engine: Renderer | None = None  # pptx | presenterm; null = legacy/inferred
    deck_theme: str | None = None  # free-string theme/template pointer (provenance)
    engine_source: str | None = None  # how the engine was sourced (provenance)

    @field_validator("architecture")
    @classmethod
    def _architecture_in_closed_set(cls, v: str) -> str:
        if v not in ARCHITECTURE_IDS:
            raise ValueError(
                f"architecture '{v}' not in closed set: {sorted(ARCHITECTURE_IDS)}",
            )
        return v

    @field_validator("slug")
    @classmethod
    def _slug_is_kebab(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                f"slug '{v}' must be kebab-case (lowercase alphanumeric + "
                f"single hyphens, no leading/trailing/double dashes)",
            )
        return v

    @field_validator("delivery_date")
    @classmethod
    def _delivery_date_iso(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(
                f"delivery_date '{v}' must be ISO YYYY-MM-DD",
            )
        return v


# ── Slide ────────────────────────────────────────────────────────────


class Interlude(_StrictModel):
    """A production interlude between slides — typically a live demo.

    The speaker switches off the deck for the duration. The interlude is
    anchored by `after_slide`: it plays between slide N and slide N+1.
    Audience never sees a numbered slide for it; the script extractor
    inlines it in sequence.
    """

    id: str
    after_slide: int = Field(ge=0)
    title: str
    chapter: str
    cuttable: bool = False
    script: list[ScriptItem] = Field(default_factory=list)
    callbacks: list[Callback] = Field(default_factory=list)
    applied_patterns: list[AppliedPattern] = Field(default_factory=list)


class Slide(_StrictModel):
    n: int = Field(ge=0)
    cuttable: bool = False
    chapter: str
    title: str
    format: SlideFormat
    format_justification: str | None = None
    visual: str | None = None
    text_overlay: str | None = None
    image_prompt: str | None = None
    safe_zone: SafeZone | None = None
    builds: list[Build] = Field(default_factory=list)
    script: list[ScriptItem] = Field(default_factory=list)
    applied_patterns: list[AppliedPattern] = Field(default_factory=list)
    callbacks: list[Callback] = Field(default_factory=list)
    progressive_lists: list[ProgressiveListEntry] = Field(default_factory=list)
    running_gags: list[RunningGagEntry] = Field(default_factory=list)
    placeholders: list[str] = Field(default_factory=list)
    big_idea: bool = False
    thesis: Literal["preview", "payoff"] | None = None

    @model_validator(mode="after")
    def _exception_needs_justification(self) -> "Slide":
        if self.format == SlideFormat.exception and not self.format_justification:
            raise ValueError(
                f"slide {self.n}: format=EXCEPTION requires format_justification",
            )
        return self

    @model_validator(mode="after")
    def _build_steps_contiguous_from_zero(self) -> "Slide":
        """Builds start at 0 and are contiguous (0, 1, 2, …, N-1).

        Per phase3-content.md: `step: 0` is the empty frame and each
        subsequent step adds one element. Holes or wrong starting steps
        produce mislabeled build-NN images and break slide-budget
        arithmetic.
        """
        if not self.builds:
            return self
        steps = [b.step for b in self.builds]
        expected = list(range(len(steps)))
        if sorted(steps) != expected:
            raise ValueError(
                f"slide {self.n}: build steps must be contiguous starting "
                f"at 0; got {steps}, expected {expected}",
            )
        if steps != expected:
            raise ValueError(
                f"slide {self.n}: build steps not in ascending order: {steps}",
            )
        return self


# ── Shared cross-field checks ────────────────────────────────────────


def _check_beat_slide_refs(
    chapters: list["Chapter"], slides: list["Slide"],
) -> None:
    """Reject argument_beat slide_refs that point at a non-existent slide.

    Shared by `Outline` (full) and `PartialOutline` (narrative phase). When no
    slide is authored yet, the slide set is empty, so any ref is invalid — beats
    must leave slide_refs empty until Phase 3 wires them to real slides.
    """
    slide_ns = {s.n for s in slides}
    for c in chapters:
        for beat in c.argument_beats:
            for ref in beat.slide_refs:
                if ref not in slide_ns:
                    hint = (
                        " — no slides are authored yet; leave slide_refs "
                        "empty until Phase 3"
                        if not slide_ns
                        else ""
                    )
                    raise ValueError(
                        f"chapter '{c.id}' argument_beat slide_ref {ref} "
                        f"does not match any slide in slides[]{hint}",
                    )


# ── Top-level outline ────────────────────────────────────────────────


class Outline(_StrictModel):
    talk: TalkMetadata
    style_anchor: StyleAnchor | None = None
    chapters: list[Chapter] = Field(min_length=1)
    slides: list[Slide] = Field(min_length=1)
    interludes: list[Interlude] = Field(default_factory=list)

    @model_validator(mode="after")
    def _chapter_ids_unique(self) -> "Outline":
        ids = [c.id for c in self.chapters]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate chapter ids: {ids}")
        return self

    @model_validator(mode="after")
    def _chapter_refs_valid(self) -> "Outline":
        chapter_ids = {c.id for c in self.chapters}
        for s in self.slides:
            if s.chapter not in chapter_ids:
                raise ValueError(
                    f"slide {s.n} references unknown chapter '{s.chapter}' "
                    f"(known: {sorted(chapter_ids)})",
                )
        for il in self.interludes:
            if il.chapter not in chapter_ids:
                raise ValueError(
                    f"interlude '{il.id}' references unknown chapter "
                    f"'{il.chapter}' (known: {sorted(chapter_ids)})",
                )
        return self

    @model_validator(mode="after")
    def _argument_beat_slide_refs_valid(self) -> "Outline":
        _check_beat_slide_refs(self.chapters, self.slides)
        return self

    @model_validator(mode="after")
    def _interlude_anchors_valid(self) -> "Outline":
        slide_ns = {s.n for s in self.slides}
        for il in self.interludes:
            if il.after_slide not in slide_ns:
                raise ValueError(
                    f"interlude '{il.id}' anchored after_slide={il.after_slide} "
                    f"but no slide has that number",
                )
        ids = [il.id for il in self.interludes]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate interlude ids: {ids}")
        return self

    @model_validator(mode="after")
    def _slide_numbers_unique_and_ordered(self) -> "Outline":
        nums = [s.n for s in self.slides]
        if len(set(nums)) != len(nums):
            raise ValueError(f"duplicate slide numbers: {nums}")
        if nums != sorted(nums):
            raise ValueError(f"slide numbers not in ascending order: {nums}")
        return self

    @model_validator(mode="after")
    def _exactly_one_big_idea(self) -> "Outline":
        marked = [s.n for s in self.slides if s.big_idea]
        if len(marked) != 1:
            raise ValueError(
                f"expected exactly 1 slide with big_idea=true, found {len(marked)} "
                f"(slides: {marked})",
            )
        return self

    @model_validator(mode="after")
    def _speaker_attribution_matches_talk_speakers(self) -> "Outline":
        speakers = set(self.talk.speakers)
        multi = len(speakers) > 1

        def _check(label: str, script: list[ScriptItem]) -> None:
            for i, item in enumerate(script):
                # `line:` items have stricter rules than `parenthetical:` items.
                # Cues never carry `speaker:` (already enforced at ScriptItem level).
                if item.line is not None:
                    if multi and item.speaker is None:
                        raise ValueError(
                            f"{label} script[{i}]: multi-speaker talk requires "
                            f"`speaker:` on every line item",
                        )
                    if not multi and item.speaker is not None:
                        raise ValueError(
                            f"{label} script[{i}]: single-speaker talk must not "
                            f"attribute lines",
                        )
                elif item.parenthetical is not None:
                    # speaker on parenthetical is OPTIONAL in multi-speaker
                    # mode (floating stage directions describe the scene) and
                    # FORBIDDEN in single-speaker mode (redundant).
                    if not multi and item.speaker is not None:
                        raise ValueError(
                            f"{label} script[{i}]: single-speaker talk must not "
                            f"attribute parentheticals",
                        )
                if item.speaker is not None and item.speaker not in speakers:
                    raise ValueError(
                        f"{label} script[{i}]: speaker '{item.speaker}' "
                        f"not in talk.speakers={sorted(speakers)}",
                    )

        for s in self.slides:
            _check(f"slide {s.n}", s.script)
        for il in self.interludes:
            _check(f"interlude '{il.id}'", il.script)
        return self

    @model_validator(mode="after")
    def _slide_budget_respected(self) -> "Outline":
        total = sum(max(len(s.builds), 1) for s in self.slides)
        if total > self.talk.slide_budget:
            raise ValueError(
                f"slide budget exceeded: {total} slides (builds expanded) > "
                f"{self.talk.slide_budget} budget",
            )
        return self

    @model_validator(mode="after")
    def _callback_plants_paid(self) -> "Outline":
        plants: dict[str, int] = {}
        pays: dict[str, int] = {}
        for s in self.slides:
            for cb in s.callbacks:
                bucket = plants if cb.kind == "plant" else pays
                bucket[cb.id] = bucket.get(cb.id, 0) + 1
        for il in self.interludes:
            for cb in il.callbacks:
                bucket = plants if cb.kind == "plant" else pays
                bucket[cb.id] = bucket.get(cb.id, 0) + 1
        unpaid = sorted(set(plants) - set(pays))
        orphan_pays = sorted(set(pays) - set(plants))
        problems: list[str] = []
        if unpaid:
            problems.append(f"unpaid plants: {unpaid}")
        if orphan_pays:
            problems.append(f"pays without plants: {orphan_pays}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


# ── Narrative-phase partial view ─────────────────────────────────────


class PartialOutline(_StrictModel):
    """Talk metadata plus an optional, slide-less narrative scaffold.

    Before any slide exists, `narrative.md` renders `talk.tldr` as the TL;DR
    plus the `chapters[].argument_beats` arc (fully authored by the end of
    Phase 2); once `slides[]` are authored, the full view switches to a
    per-slide walk. `extract-narrative.py` renders from this view so the human
    can review and approve the narrative during Phases 1–2.

    Every present section is still validated by its own field- and model-level
    validators (a `slides[]` entry, if present, still runs its build-step and
    EXCEPTION checks), and slide_refs are still checked for integrity. What this
    view *skips* are the `Outline`-level cross-field validators that presuppose a
    complete deck: `chapters`/`slides` `min_length`, the `big_idea` singleton,
    slide-budget arithmetic, callback pairing, slide ordering/uniqueness,
    chapter/interlude anchoring, and speaker attribution. The full `Outline`
    stays the Phase 3+ source-of-truth contract.
    """

    talk: TalkMetadata
    style_anchor: StyleAnchor | None = None
    chapters: list[Chapter] = Field(default_factory=list)
    slides: list[Slide] = Field(default_factory=list)
    interludes: list[Interlude] = Field(default_factory=list)

    @model_validator(mode="after")
    def _argument_beat_slide_refs_valid(self) -> "PartialOutline":
        _check_beat_slide_refs(self.chapters, self.slides)
        return self


# ── Loader + CLI guard ───────────────────────────────────────────────


def load_outline(path: Path | str) -> Outline:
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return Outline.model_validate(data)


def load_outline_partial(path: Path | str) -> PartialOutline:
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return PartialOutline.model_validate(data)


def main(argv: list[str]) -> int:
    args = argv[1:]
    emit_json = "--emit-json" in args
    args = [a for a in args if a != "--emit-json"]
    if len(args) != 1:
        print(
            "usage: outline_schema.py [--emit-json] <outline.yaml>",
            file=sys.stderr,
        )
        return 2
    try:
        outline = load_outline(args[0])
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if emit_json:
        json.dump(outline.model_dump(mode="json"), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(
            f"OK: {len(outline.slides)} slides across "
            f"{len(outline.chapters)} chapters",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

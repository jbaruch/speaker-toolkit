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

import re
import sys
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

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
    title = "TITLE"


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
}

_ALL_INSTANCE_FIELDS: frozenset[str] = frozenset({
    "flavors", "subtype", "resistance_vector",
    "story_id", "beat", "plant_id", "big_idea_text", "asks",
})


class AppliedPattern(BaseModel):
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


class Callback(BaseModel):
    kind: Literal["plant", "pay"]
    id: str
    variation: str | None = None


class ProgressiveListEntry(BaseModel):
    id: str
    item_index: int = Field(ge=1)


class RunningGagEntry(BaseModel):
    id: str
    appearance_index: int = Field(ge=1)


class Build(BaseModel):
    step: int = Field(ge=0)
    desc: str


# ── Screenplay-form script ───────────────────────────────────────────


class ScriptItem(BaseModel):
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


class ArgumentBeat(BaseModel):
    text: str
    slide_refs: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Chapter(BaseModel):
    id: str
    title: str
    target_min: float = Field(gt=0)
    accent: str | None = None
    cuttable: bool = False
    argument_beats: list[ArgumentBeat] = Field(default_factory=list)


# ── Illustration style anchor (optional, per talk) ───────────────────


class StyleAnchor(BaseModel):
    model: str
    full: str
    imgtxt: str
    conventions: str


# ── Talk metadata ────────────────────────────────────────────────────


class TalkMetadata(BaseModel):
    title: str
    slug: str
    speakers: list[str] = Field(min_length=1)
    duration_min: float = Field(gt=0)
    audience: str
    mode: str
    venue: str
    slide_budget: int = Field(gt=0)
    pacing_wpm: tuple[int, int]
    architecture: str
    applied_patterns: list[AppliedPattern] = Field(default_factory=list)

    # Spec metadata (collapsed from the legacy presentation-spec.md).
    # All optional — older outlines without these fields still validate.
    thesis: str | None = None
    shownotes_url_base: str | None = None
    commercial_intent: str | None = None
    profanity_register: str | None = None
    must_include: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    catalog_reference: str | None = None
    delivery_count: int | None = Field(default=None, ge=1)
    delivery_date: str | None = None  # ISO YYYY-MM-DD

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


class Interlude(BaseModel):
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


class Slide(BaseModel):
    n: int = Field(ge=0)
    cuttable: bool = False
    chapter: str
    title: str
    format: SlideFormat | None = None
    format_justification: str | None = None
    visual: str | None = None
    text_overlay: str | None = None
    image_prompt: str | None = None
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


# ── Top-level outline ────────────────────────────────────────────────


class Outline(BaseModel):
    talk: TalkMetadata
    style_anchor: StyleAnchor | None = None
    chapters: list[Chapter] = Field(min_length=1)
    slides: list[Slide] = Field(min_length=1)
    interludes: list[Interlude] = Field(default_factory=list)

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


# ── Loader + CLI guard ───────────────────────────────────────────────


def load_outline(path: Path | str) -> Outline:
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return Outline.model_validate(data)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: outline_schema.py <outline.yaml>", file=sys.stderr)
        return 2
    try:
        outline = load_outline(argv[1])
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        f"OK: {len(outline.slides)} slides across "
        f"{len(outline.chapters)} chapters",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

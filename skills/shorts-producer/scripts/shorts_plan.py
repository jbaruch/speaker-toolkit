"""The shorts plan: one talk's clips, written by the agent, read by the scripts.

``plan.json`` lives in the talk's shorts output folder. Relative paths in it
resolve against the plan's own directory. Schema version 1:

    {
      "schema_version": 1,
      "talk": "<tracking-database filename>",
      "source": "<local recording, video+audio>",
      "deck_pdf": "<the deck as PDF>",
      "work_dir": "<local scratch folder for intermediates>",
      "out_dir": "<folder for the finished shorts>",
      "handle": "@speaker", "event": "EVENT NAME", "website": "example.com",
      "qr_url": "<shownotes link>" | null,
      "clips": [{
        "id": "01-slug", "title": "...", "hook": ["LINE ONE", "LINE TWO"],
        "start": 1038.94, "end": 1069.45, "rationale": "...",
        "speaker_region": [x, y, w, h],
        "slides": [[0, 14], [4.9, 15]],
        "captions": "the corrected caption text"
      }]
    }

``start``/``end`` are seconds in the source. ``speaker_region`` is the
normalized box the speaker stays inside, ``slides`` pairs a clip offset in
seconds with a deck page number, and ``captions`` is the corrected text. Those
three are needed to render, not to prepare.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

SCHEMA_VERSION = 1
CLIP_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
PLAN_FIELDS = (
    "talk",
    "source",
    "deck_pdf",
    "work_dir",
    "out_dir",
    "handle",
    "event",
    "website",
)
RENDER_FIELDS = ("speaker_region", "slides", "captions", "title", "hook")
# Seconds of recording prepared on each side of a clip, so the agent can move a
# boundary to a sentence edge without preparing again.
CONTEXT_SECONDS = 8.0


class PlanError(ValueError):
    """The plan cannot drive this step; the message says what to fix."""


def _path(plan_dir: Path, value: object, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise PlanError(f"plan field {field!r} must be a path string")
    path = Path(value).expanduser()
    return path if path.is_absolute() else (plan_dir / path).resolve()


def load(plan_path: Path) -> dict[str, Any]:
    """Read and check the plan's top level; paths come back absolute."""
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanError(f"cannot read the plan {plan_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"the plan {plan_path} is not JSON: {exc}") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != SCHEMA_VERSION:
        raise PlanError(
            f"the plan must be an object with schema_version {SCHEMA_VERSION}"
        )
    missing = [field for field in PLAN_FIELDS if field not in plan]
    if missing:
        raise PlanError(f"the plan is missing {missing}")
    for field in ("source", "deck_pdf", "work_dir", "out_dir"):
        plan[field] = _path(plan_path.parent, plan[field], field)
    qr_url = plan.get("qr_url")
    if qr_url is not None and not (
        isinstance(qr_url, str) and qr_url.startswith("https://")
    ):
        raise PlanError("qr_url must be an https:// link or null")
    clips = plan.get("clips")
    if not isinstance(clips, list) or not clips:
        raise PlanError("the plan needs a non-empty clips list")
    seen: set[str] = set()
    for clip in clips:
        _check_clip(clip, seen)
    return plan


def _check_clip(clip: object, seen: set[str]) -> None:
    if not isinstance(clip, dict):
        raise PlanError("every clip must be an object")
    clip_id = clip.get("id")
    if not isinstance(clip_id, str) or not CLIP_ID.match(clip_id):
        raise PlanError(
            f"clip id {clip_id!r} must be lowercase letters, digits and dashes"
        )
    if clip_id in seen:
        raise PlanError(f"clip id {clip_id!r} appears twice")
    seen.add(clip_id)
    start, end = clip.get("start"), clip.get("end")
    if not (
        isinstance(start, (int, float))
        and isinstance(end, (int, float))
        and 0 <= start < end
    ):
        raise PlanError(
            f"clip {clip_id}: start and end must be seconds with start < end"
        )


def clip(plan: dict[str, Any], clip_id: str) -> dict[str, Any]:
    for candidate in plan["clips"]:
        if candidate["id"] == clip_id:
            return candidate
    raise PlanError(
        f"no clip {clip_id!r} in the plan; ids: {[c['id'] for c in plan['clips']]}"
    )


def require_render_fields(selected: dict[str, Any]) -> None:
    """A clip is renderable once the agent filled in what preparation showed."""
    clip_id = selected["id"]
    missing = [field for field in RENDER_FIELDS if field not in selected]
    if missing:
        raise PlanError(
            f"clip {clip_id} is missing {missing} — prepare it and fill them in"
        )
    region = selected["speaker_region"]
    if not (
        isinstance(region, list)
        and len(region) == 4
        and all(isinstance(v, (int, float)) for v in region)
        and 0 <= region[0] < 1
        and 0 <= region[1] < 1
        and 0 < region[2] <= 1 - region[0] + 1e-9
        and 0 < region[3] <= 1 - region[1] + 1e-9
    ):
        raise PlanError(
            f"clip {clip_id}: speaker_region must be [x, y, w, h] inside 0..1"
        )
    slides = selected["slides"]
    duration = selected["end"] - selected["start"]
    if not isinstance(slides, list) or not slides:
        raise PlanError(
            f"clip {clip_id}: slides needs at least one [offset, page] pair"
        )
    offsets = []
    for pair in slides:
        if not (
            isinstance(pair, list)
            and len(pair) == 2
            and isinstance(pair[0], (int, float))
            and isinstance(pair[1], int)
            and pair[1] >= 1
        ):
            raise PlanError(
                f"clip {clip_id}: slide entry {pair!r} must be [offset, page]"
            )
        offsets.append(pair[0])
    if offsets[0] != 0 or offsets != sorted(offsets) or offsets[-1] >= duration:
        raise PlanError(
            f"clip {clip_id}: slide offsets must start at 0, rise, and stay inside the clip"
        )
    hook = selected["hook"]
    if not (
        isinstance(hook, list)
        and 1 <= len(hook) <= 2
        and all(isinstance(h, str) and h for h in hook)
    ):
        raise PlanError(f"clip {clip_id}: hook must be one or two lines of text")
    if not isinstance(selected["captions"], str) or not selected["captions"].split():
        raise PlanError(f"clip {clip_id}: captions must be the corrected text")


def clip_dir(plan: dict[str, Any], clip_id: str) -> Path:
    return plan["work_dir"] / clip_id


def deck_dir(plan: dict[str, Any]) -> Path:
    return plan["work_dir"] / "deck"


def vision_script(plan: dict[str, Any]) -> Path:
    """The Apple Vision helper, copied to a runnable name in the work folder.

    An installed plugin has only the ``vision.swift.txt`` mirror, because
    ``tessl install`` drops ``.swift`` files, and ``swift`` runs only a
    ``.swift`` path. A clone has both; the real file wins.
    """
    target = plan["work_dir"] / "vision.swift"
    here = Path(__file__).resolve().parent
    source = here / "vision.swift"
    if not source.exists():
        source = here / "vision.swift.txt"
    text = source.read_text(encoding="utf-8")
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return target


def deck_page(plan: dict[str, Any], page: int) -> Path:
    """The rendered page, as ``prepare-clip.py`` names it."""
    return deck_dir(plan) / f"page-{page:03d}.png"

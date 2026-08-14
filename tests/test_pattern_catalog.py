"""Structural guards on the Presentation Patterns catalog.

The catalog is prose, so nothing mechanically enforced its own conventions and
one of them drifted. The 2026-07-27 full-vault reparse surfaced the cost: 26 of
28 antipattern files used an INVERTED scale where "Strong signal" described the
antipattern being ABSENT, while the two newest files used the direct scale.
Subagents record `confidence` in `antipatterns_detected` meaning "how strongly
present", so the same value meant opposite things depending on which file a
scorer happened to open — across 3,228 corpus observations. Five independent
reparse agents reported it before it was believed.

These are deliberately structural: they check the contract a scorer reads, not
prose quality. Every assertion below was verified against the catalog as it
stands, so a failure means real drift rather than an invented convention.
"""

import glob
import json
import os
import re

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = os.path.join(
    REPO_ROOT, "skills", "presentation-creator", "references", "patterns"
)
INDEX = os.path.join(PATTERNS, "_index.md")

STRONG_RE = re.compile(r"^- Strong signal(?: \((?P<qualifier>[^)]*)\))?:", re.M)
MODERATE_RE = re.compile(r"^- Moderate signal:", re.M)
ABSENT_RE = re.compile(r"^- Absent(?: \((?P<qualifier>[^)]*)\))?:", re.M)
ARITHMETIC_LABEL_RE = re.compile(
    r"^- (?:Strong signal|Moderate signal|Absent) "
    r"\([^)]*\b(?:pt|pts|point|points)\b[^)]*\):",
    re.I | re.M,
)
MEDIUM_LABEL_RE = re.compile(r"^- Medium signal(?: \([^)]*\))?:", re.I | re.M)

ENTRY_FILES = sorted(f for f in glob.glob(os.path.join(PATTERNS, "*", "*.md")))
ANTI_FILES = [f for f in ENTRY_FILES if os.path.basename(f).startswith("_anti_")]
ENTRY_BY_ID = {
    os.path.basename(path)[:-3].removeprefix("_anti_"): path for path in ENTRY_FILES
}

NAME_TRAP_GUARDS = {
    "make-it-rain": (
        "physical object in the room",
        "screen-based demonstration does not qualify",
    ),
    "dead-demo": (
        '"dead" means narratively lifeless, not technically failed',
        "Judge the demo's narrative purpose",
    ),
    "cave-painting": (
        "not a synonym for pictorial or wordless slides",
        "one spatial canvas",
    ),
    "exuberant-title-top": (
        "not a static title layout",
        "flattened final-state slide alone is not evidence",
    ),
    "flyover": (
        "not a high-level or abbreviated treatment of a topic",
        "status or belonging comparison",
    ),
    "bookends": (
        "repeated section-boundary slides",
        "not for symmetry between the opening and closing",
    ),
}

EVIDENCE_SOURCE_VALUES = frozenset(
    {
        "static_slides",
        "native_deck",
        "delivery_video",
        "transcript",
        "source_comparison",
    }
)
EVIDENCE_SOURCE_CHANNELS = {
    "static_slides": frozenset({"slides", "slide_sequence", "talk_metadata"}),
    "native_deck": frozenset({"slides", "slide_sequence", "talk_metadata"}),
    "delivery_video": frozenset({"video", "talk_metadata"}),
    "transcript": frozenset({"transcript", "timed_transcript", "talk_metadata"}),
}
EVIDENCE_GATE_FIELDS = frozenset(
    {
        "evaluable_from",
        "evidence_requirements",
        "not_evaluable_when",
    }
)
OUTCOME_EVIDENCE_GATE_FIELDS = frozenset(
    {
        "strong_evaluable_from",
        "absence_evaluable_from",
    }
)
ABSENCE_STATIC_IDS = frozenset(
    {
        "analog-noise",
        "ant-fonts",
        "bookends",
        "breadcrumbs",
        "cookie-cutter",
        "defy-defaults",
        "floodmarks",
        "fontaholic",
        "injured-outlines",
        "takahashi",
        "unifying-visual-theme",
    }
)
ABSENCE_TRANSCRIPT_IDS = frozenset(
    {
        "concrete-before-abstract",
        "flyover",
        "going-meta",
        "mentor",
        "negative-ignorance",
    }
)
EXPECTED_ABSENCE_GATES = {
    **{pattern_id: ["static_slides"] for pattern_id in ABSENCE_STATIC_IDS},
    **{pattern_id: ["transcript"] for pattern_id in ABSENCE_TRANSCRIPT_IDS},
}
assert len(EXPECTED_ABSENCE_GATES) == 16
APPLICABILITY_GATE_FIELDS = frozenset(
    {
        "not_applicable_when",
        "applicability_evaluable_from",
    }
)
ALL_EVIDENCE_GATE_FIELDS = (
    EVIDENCE_GATE_FIELDS | OUTCOME_EVIDENCE_GATE_FIELDS | APPLICABILITY_GATE_FIELDS
)
EXISTING_REQUIRED_EVIDENCE_GATES = {
    "progressive-reveal": frozenset(
        {
            frozenset({"static_slides"}),
            frozenset({"native_deck"}),
            frozenset({"delivery_video"}),
        }
    ),
    "composite-animation": frozenset(
        {
            frozenset({"native_deck"}),
            frozenset({"delivery_video"}),
        }
    ),
    "invisibility": frozenset(
        {
            frozenset({"native_deck"}),
            frozenset({"native_deck", "static_slides"}),
            frozenset({"delivery_video", "static_slides"}),
        }
    ),
    "exuberant-title-top": frozenset(
        {
            frozenset({"native_deck"}),
            frozenset({"delivery_video"}),
        }
    ),
    "gradual-consistency": frozenset(
        {
            frozenset({"native_deck"}),
            frozenset({"native_deck", "static_slides"}),
            frozenset({"delivery_video", "static_slides"}),
        }
    ),
    "traveling-highlights": frozenset(
        {
            frozenset({"static_slides"}),
            frozenset({"native_deck"}),
            frozenset({"delivery_video"}),
        }
    ),
    "second-look": frozenset(
        {
            frozenset({"delivery_video"}),
            frozenset({"static_slides", "transcript"}),
            frozenset({"native_deck", "transcript"}),
        }
    ),
    "vacation-photos": frozenset(
        {
            frozenset({"delivery_video"}),
            frozenset({"static_slides", "transcript"}),
            frozenset({"native_deck", "transcript"}),
        }
    ),
}

SAFE_VISUAL_GATE_IDS = frozenset(
    {
        "analog-noise",
        "bookends",
        "breadcrumbs",
        "context-keeper",
        "cookie-cutter",
        "defy-defaults",
        "floodmarks",
        "fontaholic",
        "injured-outlines",
        "intermezzi",
        "three-part-close",
        "unifying-visual-theme",
    }
)
SAFE_MOTION_GATE_IDS = frozenset(
    {
        "cave-painting",
        "crawling-credits",
        "soft-transitions",
    }
)
SAFE_DELIVERY_GATE_IDS = frozenset(
    {
        "a-la-carte-content",
        "brain-breaks",
        "breathing-room",
        "celery",
        "dead-demo",
        "dual-headed-monster",
        "hecklers",
        "lightning-talk",
        "live-demo",
        "make-it-rain",
        "weatherman",
    }
)
SAFE_SPOKEN_GATE_IDS = frozenset({"echo-chamber"})
SAFE_COMBINED_GATE_IDS = frozenset({"lipstick-on-a-pig"})
SAFE_CODA_GATE_IDS = frozenset({"coda"})

VISUAL_GATE = frozenset(
    {
        frozenset({"static_slides"}),
        frozenset({"native_deck"}),
        frozenset({"delivery_video"}),
    }
)
MOTION_GATE = frozenset(
    {
        frozenset({"native_deck"}),
        frozenset({"delivery_video"}),
    }
)
DELIVERY_GATE = frozenset({frozenset({"delivery_video"})})
SPOKEN_GATE = frozenset(
    {
        frozenset({"transcript"}),
        frozenset({"delivery_video"}),
    }
)
COMBINED_GATE = frozenset(
    {
        frozenset({"delivery_video"}),
        frozenset({"static_slides", "transcript"}),
        frozenset({"native_deck", "transcript"}),
    }
)
CODA_GATE = frozenset(
    {
        frozenset({"static_slides", "transcript"}),
        frozenset({"native_deck", "transcript"}),
    }
)

SAFE_SOURCE_GATE_GROUPS = (
    (SAFE_VISUAL_GATE_IDS, VISUAL_GATE),
    (SAFE_MOTION_GATE_IDS, MOTION_GATE),
    (SAFE_DELIVERY_GATE_IDS, DELIVERY_GATE),
    (SAFE_SPOKEN_GATE_IDS, SPOKEN_GATE),
    (SAFE_COMBINED_GATE_IDS, COMBINED_GATE),
    (SAFE_CODA_GATE_IDS, CODA_GATE),
)
SAFE_SOURCE_GATES = {
    pattern_id: alternatives
    for pattern_ids, alternatives in SAFE_SOURCE_GATE_GROUPS
    for pattern_id in pattern_ids
}
assert len(SAFE_SOURCE_GATES) == 29

APPROVED_MECHANICAL_OUTCOME_GATES = {
    "ant-fonts": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "absence_evaluable_from": ["static_slides", "native_deck", "delivery_video"],
    },
    "bullet-riddled-corpse": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "call-to-action": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "call-to-adventure": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "charred-trail": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "absence_evaluable_from": ["native_deck", "delivery_video"],
    },
    "concrete-before-abstract": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "crawling-code": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["native_deck", "delivery_video"],
        "absence_evaluable_from": ["native_deck", "delivery_video"],
    },
    "emergence": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["native_deck", "delivery_video"],
    },
    "flyover": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "going-meta": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "master-story": {
        "evaluable_from": [
            "transcript",
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "meme-as-argument": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "absence_evaluable_from": ["static_slides", "native_deck", "delivery_video"],
    },
    "negative-ignorance": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "new-bliss": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "seeding-the-first-question": {
        "evaluable_from": ["delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "triad": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "absence_evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
    },
    "delayed-self-introduction": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
        "absence_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
    },
    "display-of-high-value": {
        "evaluable_from": ["delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "emotional-state": {
        "evaluable_from": ["delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": None,
    },
    "guess-first": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "inoculation": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": None,
    },
    "preroll": {
        "evaluable_from": ["delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "retrieval-beat": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "screen-blackout": {
        "evaluable_from": ["delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "takahashi": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["static_slides", "native_deck", "delivery_video"],
    },
}
assert len(APPROVED_MECHANICAL_OUTCOME_GATES) == 25

APPROVED_MECHANICAL_SOURCE_GATES = {
    pattern_id: frozenset(
        frozenset([option]) if isinstance(option, str) else frozenset(option)
        for option in gates["evaluable_from"]
    )
    for pattern_id, gates in APPROVED_MECHANICAL_OUTCOME_GATES.items()
}

SEMANTIC_OUTCOME_GATES = {
    "alienating-artifact": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "absence_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
    },
    "anti-sell": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": None,
    },
    "backtracking": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
    },
    "entertainment": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
    },
    "expansion-joints": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": None,
    },
    "foreshadowing": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
    },
    "greek-chorus": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "hiccup-words": {
        "evaluable_from": ["delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "lipsync": {
        "evaluable_from": ["delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "mentor": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["transcript", "delivery_video"],
    },
    "narrative-arc": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
    },
    "nodding-room": {
        "evaluable_from": ["delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "opening-punch": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
        "absence_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
    },
    "photomaniac": {
        "evaluable_from": ["static_slides", "native_deck", "delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "shortchanged": {
        "evaluable_from": ["transcript", "delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": None,
    },
    "sparkline": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
        "absence_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
    },
    "star-moment": {
        "evaluable_from": ["delivery_video"],
        "strong_evaluable_from": ["delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "talklet": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": ["transcript", "delivery_video"],
        "absence_evaluable_from": ["delivery_video"],
    },
    "walk-around": {
        "evaluable_from": [
            "transcript",
            "static_slides",
            "native_deck",
            "delivery_video",
        ],
        "strong_evaluable_from": [
            "delivery_video",
            ["transcript", "static_slides"],
            ["transcript", "native_deck"],
        ],
        "absence_evaluable_from": None,
    },
}
assert len(SEMANTIC_OUTCOME_GATES) == 19

SEMANTIC_SOURCE_GATES = {
    pattern_id: frozenset(
        frozenset([option]) if isinstance(option, str) else frozenset(option)
        for option in gates["evaluable_from"]
    )
    for pattern_id, gates in SEMANTIC_OUTCOME_GATES.items()
}

# Base and strong gates remain the owner-reviewed positive-detection contract.
# Absence is deliberately narrower: the current capability generation trusts
# only a complete, separately declared rendered PDF or a complete transcript.
# Keep the historical maps readable while overriding their absence lane with
# the single canonical release decision.
for _outcome_map in (APPROVED_MECHANICAL_OUTCOME_GATES, SEMANTIC_OUTCOME_GATES):
    for _pattern_id, _expected_gates in _outcome_map.items():
        _expected_gates["absence_evaluable_from"] = EXPECTED_ABSENCE_GATES.get(
            _pattern_id
        )

EXPECTED_APPLICABILITY_CONDITION_IDS = {
    "a-la-carte-content": ("short-talk-under-30-minutes", "fixed-prerequisite-order"),
    "backtracking": ("lightning-format",),
    "bookends": ("fewer-than-three-major-sections",),
    "brain-breaks": ("short-talk-at-most-15-minutes",),
    "breadcrumbs": ("fewer-than-three-major-sections",),
    "call-to-action": ("purely-ceremonial-talk",),
    "call-to-adventure": ("non-persuasive-talk",),
    "cave-painting": ("no-spatial-or-hierarchical-content",),
    "charred-trail": ("no-sequential-multi-item-slide",),
    "coda": ("no-external-resources-cited",),
    "context-keeper": ("short-talk-at-most-15-minutes",),
    "crawling-code": ("no-long-code-listing",),
    "dead-demo": ("no-demonstration-occurs",),
    "dual-headed-monster": ("no-simultaneous-hybrid-audience",),
    "echo-chamber": ("no-q-and-a-segment",),
    "emergence": ("no-complex-visual",),
    "expansion-joints": ("short-talk-at-most-20-minutes",),
    "foreshadowing": (
        "short-talk-at-most-15-minutes",
        "strictly-sequential-instructional-contract",
    ),
    "hecklers": ("no-audience-disruption",),
    "intermezzi": ("short-talk-at-most-15-minutes", "continuous-single-theme-flow"),
    "lightning-talk": ("not-lightning-format",),
    "lipsync": ("no-executable-subject",),
    "live-demo": ("no-executable-subject",),
    "master-story": ("short-talk-under-20-minutes", "purely-informational-big-idea"),
    "new-bliss": ("non-persuasive-talk",),
    "nodding-room": ("performance-shaped-talk",),
    "opening-punch": ("tightly-formatted-ceremonial-slot",),
    "preroll": ("no-prestart-display-opportunity",),
    "progressive-reveal": ("no-complex-reveal-opportunity",),
    "retrieval-beat": ("performance-shaped-talk",),
    "screen-blackout": ("screen-only-remote-presentation", "no-projected-screen"),
    "seeding-the-first-question": ("no-q-and-a-segment",),
    "sparkline": ("non-persuasive-talk",),
    "talklet": ("short-talk-at-most-30-minutes", "cumulative-prerequisite-chain"),
    "three-part-close": ("short-talk-under-25-minutes", "non-action-oriented-talk"),
    "traveling-highlights": ("no-dense-visual",),
    "weatherman": ("no-projected-slides",),
}
assert len(EXPECTED_APPLICABILITY_CONDITION_IDS) == 37

APP_VIDEO_GATE_IDS = frozenset(
    {
        "a-la-carte-content",
        "backtracking",
        "brain-breaks",
        "context-keeper",
        "dead-demo",
        "dual-headed-monster",
        "expansion-joints",
        "foreshadowing",
        "hecklers",
        "intermezzi",
        "lightning-talk",
        "lipsync",
        "live-demo",
        "master-story",
        "nodding-room",
        "preroll",
        "screen-blackout",
        "seeding-the-first-question",
        "talklet",
        "three-part-close",
        "weatherman",
    }
)
APP_VISUAL_GATE_IDS = frozenset(
    {
        "bookends",
        "breadcrumbs",
        "charred-trail",
        "crawling-code",
        "emergence",
        "progressive-reveal",
        "traveling-highlights",
    }
)
APP_SPOKEN_GATE_IDS = frozenset(
    {
        "call-to-action",
        "call-to-adventure",
        "echo-chamber",
        "new-bliss",
        "opening-punch",
        "retrieval-beat",
        "sparkline",
    }
)
EXPECTED_APPLICABILITY_GATES = {
    **{pattern_id: ["delivery_video"] for pattern_id in APP_VIDEO_GATE_IDS},
    **{
        pattern_id: ["static_slides", "native_deck", "delivery_video"]
        for pattern_id in APP_VISUAL_GATE_IDS
    },
    **{
        pattern_id: ["transcript", "delivery_video"]
        for pattern_id in APP_SPOKEN_GATE_IDS
    },
    "cave-painting": ["native_deck", "delivery_video"],
    "coda": [
        ["static_slides", "transcript"],
        ["native_deck", "transcript"],
    ],
}
assert set(EXPECTED_APPLICABILITY_GATES) == set(EXPECTED_APPLICABILITY_CONDITION_IDS)

OBSERVABLE_GATE_IDS = frozenset(
    set(EXISTING_REQUIRED_EVIDENCE_GATES)
    | set(SAFE_SOURCE_GATES)
    | set(APPROVED_MECHANICAL_SOURCE_GATES)
    | set(SEMANTIC_SOURCE_GATES)
)
POSITIVE_ONLY_IDS = OBSERVABLE_GATE_IDS - frozenset(EXPECTED_ABSENCE_GATES)
assert len(OBSERVABLE_GATE_IDS) == 81
assert len(POSITIVE_ONLY_IDS) == 65

RECLASSIFIED_UNOBSERVABLE_IDS = frozenset(
    {
        "disowning-your-topic",
        "golden-rule",
        "infodeck",
        "leet-grammars",
        "live-on-tape",
        "slideuments",
        "the-big-why",
        "tower-of-babble",
    }
)
assert len(RECLASSIFIED_UNOBSERVABLE_IDS) == 8

REQUIRED_EVIDENCE_GATES = {
    **EXISTING_REQUIRED_EVIDENCE_GATES,
    **SAFE_SOURCE_GATES,
    **APPROVED_MECHANICAL_SOURCE_GATES,
    **SEMANTIC_SOURCE_GATES,
}
assert len(REQUIRED_EVIDENCE_GATES) == 81


def _ids(files):
    return [os.path.basename(f)[:-3] for f in files]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _front(path, key):
    m = re.search(rf"^{key}:\s*(\S+)\s*$", _read(path), re.M)
    return m.group(1) if m else None


def _metadata(path):
    parts = _read(path).split("---", 2)
    assert len(parts) == 3, f"{os.path.basename(path)}: malformed frontmatter"
    metadata = yaml.safe_load(parts[1])
    assert isinstance(metadata, dict), (
        f"{os.path.basename(path)}: frontmatter is not a mapping"
    )
    return metadata


def _path_for_id(pattern_id):
    matches = [path for path in ENTRY_FILES if _front(path, "id") == pattern_id]
    assert len(matches) == 1, f"expected one catalog entry for {pattern_id!r}"
    return matches[0]


def _entry(pattern_id):
    return _path_for_id(pattern_id)


def test_catalog_is_present():
    """Guard the guard: a bad glob would make every parametrized test vacuous."""
    assert len(ENTRY_FILES) == 111, f"expected 111 entries, found {len(ENTRY_FILES)}"
    assert len(ANTI_FILES) == 28, f"expected 28 antipatterns, found {len(ANTI_FILES)}"


@pytest.mark.parametrize("path", ANTI_FILES, ids=_ids(ANTI_FILES))
def test_antipattern_scoring_polarity_is_direct(path):
    """`Strong signal` must mean the antipattern is PRESENT.

    An inverted file makes `confidence: strong` in `antipatterns_detected`
    ambiguous — a scorer cannot tell "strongly present" from "strongly clean"
    without opening the individual file.
    """
    strong = STRONG_RE.search(_read(path))
    assert strong, f"{os.path.basename(path)}: no Strong signal bullet"
    assert strong.group("qualifier") == "antipattern present", (
        f"{os.path.basename(path)} scores on the inverted scale: "
        f"Strong signal must read 'Strong signal (antipattern present)'"
    )


@pytest.mark.parametrize("path", ANTI_FILES, ids=_ids(ANTI_FILES))
def test_antipattern_absent_bullet_is_labelled(path):
    absent = ABSENT_RE.search(_read(path))
    assert absent, f"{os.path.basename(path)}: no Absent bullet"
    assert absent.group("qualifier") == "antipattern not present", (
        f"{os.path.basename(path)}: Absent must read "
        f"'Absent (antipattern not present)' so polarity is unambiguous"
    )


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_scoring_block_is_complete(path):
    """A partial scale is worse than none — a scorer fills the gap by guessing."""
    text = _read(path)
    assert "## Scoring Criteria" in text, f"{os.path.basename(path)}: no scoring block"
    assert STRONG_RE.search(text), f"{os.path.basename(path)}: missing Strong bullet"
    assert MODERATE_RE.search(text), (
        f"{os.path.basename(path)}: missing Moderate bullet"
    )
    assert ABSENT_RE.search(text), f"{os.path.basename(path)}: missing Absent bullet"


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_scoring_labels_are_non_arithmetic_and_use_moderate(path):
    """Decision labels are not weights, and ``medium`` is not an alias."""
    text = _read(path)
    assert not ARITHMETIC_LABEL_RE.search(text), (
        f"{os.path.basename(path)}: scoring labels must not declare point values"
    )
    assert not MEDIUM_LABEL_RE.search(text), (
        f"{os.path.basename(path)}: use Moderate signal, never Medium signal"
    )


def test_compact_list_alone_is_not_bullet_riddled_corpse():
    text = _read(_entry("bullet-riddled-corpse"))
    section = text[text.index("## Scoring Criteria") : text.index("## Evidence Gate")]
    normalized = " ".join(section.split())

    assert "Repeated bullet-heavy slides" in normalized
    assert "duplicate the speaker's narration" in normalized
    assert "reading-ahead or cognitive competition" in normalized
    assert (
        "a compact list of three or fewer short items by itself is not a signal"
        in normalized
    )


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_id_matches_filename(path):
    """Prevents the invented-id class: prior passes scored six ids that did not
    exist in the catalog, `terminal-as-deck` fourteen times."""
    expected = os.path.basename(path)[:-3].removeprefix("_anti_")
    assert _front(path, "id") == expected, (
        f"{os.path.basename(path)}: frontmatter id is {_front(path, 'id')!r}"
    )


def test_ids_are_unique():
    seen = {}
    for f in ENTRY_FILES:
        pid = _front(f, "id")
        assert pid not in seen, f"duplicate id {pid!r}: {seen.get(pid)} and {f}"
        seen[pid] = f


@pytest.mark.parametrize(
    "pattern_id,required_phrases",
    NAME_TRAP_GUARDS.items(),
    ids=NAME_TRAP_GUARDS,
)
def test_name_traps_have_explicit_disqualifiers(pattern_id, required_phrases):
    """Known false friends must tell a fast scanner what does not qualify."""
    text = _read(ENTRY_BY_ID[pattern_id])
    assert "**NAME TRAP" in text, f"{pattern_id}: missing explicit name-trap guard"
    missing = [phrase for phrase in required_phrases if phrase not in text]
    assert not missing, f"{pattern_id}: missing disambiguators {missing}"


def test_catalog_references_resolve():
    """Every related/inverse reference must name a real catalog entry."""
    ids = set(ENTRY_BY_ID)
    dangling = []
    for path in ENTRY_FILES:
        metadata = _metadata(path)
        for field in ("related_patterns", "inverse_of"):
            references = metadata.get(field)
            assert isinstance(references, list), (
                f"{metadata.get('id')}: {field} must be a list"
            )
            dangling.extend(
                (metadata.get("id"), field, target)
                for target in references
                if target not in ids
            )
    assert not dangling, f"dangling catalog references: {dangling}"


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_type_matches_anti_prefix(path):
    """`_anti_` prefix and `type:` must agree — a scorer that trusts one and a
    validator that trusts the other would disagree about what may be scored."""
    declared = _front(path, "type")
    is_anti = os.path.basename(path).startswith("_anti_")
    assert declared == ("antipattern" if is_anti else "pattern"), (
        f"{os.path.basename(path)}: type is {declared!r}"
    )


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_evidence_gate_frontmatter_is_well_formed(path):
    """An evidence gate must be complete and use the documented source enum."""
    metadata = _metadata(path)
    present_base = EVIDENCE_GATE_FIELDS.intersection(metadata)
    present_outcomes = OUTCOME_EVIDENCE_GATE_FIELDS.intersection(metadata)
    present_applicability = APPLICABILITY_GATE_FIELDS.intersection(metadata)
    if not present_base and not present_outcomes and not present_applicability:
        return

    assert present_base == EVIDENCE_GATE_FIELDS, (
        f"{os.path.basename(path)}: partial evidence gate; "
        f"present={sorted(present_base | present_outcomes)}"
    )

    requirements = metadata["evidence_requirements"]
    disqualifiers = metadata["not_evaluable_when"]
    for gate_field in (
        "evaluable_from",
        "strong_evaluable_from",
        "absence_evaluable_from",
    ):
        if gate_field not in metadata:
            continue
        sources = metadata[gate_field]
        if gate_field == "absence_evaluable_from" and sources is None:
            continue
        assert isinstance(sources, list) and sources, (
            f"{os.path.basename(path)}: {gate_field} must be a non-empty list"
        )
        groups = []
        for option in sources:
            if isinstance(option, list):
                assert len(option) >= 2, (
                    f"{os.path.basename(path)}: nested alternatives need two sources"
                )
            group = [option] if isinstance(option, str) else option
            assert isinstance(group, list) and group, (
                f"{os.path.basename(path)}: invalid evidence-source alternative"
            )
            assert all(isinstance(source, str) for source in group), (
                f"{os.path.basename(path)}: evidence sources must be strings"
            )
            assert set(group) <= EVIDENCE_SOURCE_VALUES, (
                f"{os.path.basename(path)}: unknown evidence sources "
                f"{sorted(set(group) - EVIDENCE_SOURCE_VALUES)}"
            )
            assert len(group) == len(set(group)), (
                f"{os.path.basename(path)}: duplicate evidence sources"
            )
            assert group != ["source_comparison"], (
                f"{os.path.basename(path)}: comparison label needs an exact pair"
            )
            assert len(group) == 1 or "source_comparison" not in group, (
                f"{os.path.basename(path)}: comparison label cannot be an underlying source"
            )
            groups.append(frozenset(group))
        assert len(groups) == len(set(groups)), (
            f"{os.path.basename(path)}: duplicate evidence-source alternatives"
        )

    assert present_applicability in (frozenset(), APPLICABILITY_GATE_FIELDS), (
        f"{os.path.basename(path)}: applicability fields must be declared together"
    )
    if present_applicability:
        conditions = metadata["not_applicable_when"]
        assert isinstance(conditions, list) and conditions, (
            f"{os.path.basename(path)}: not_applicable_when must be non-empty"
        )
        condition_ids = []
        for condition in conditions:
            assert isinstance(condition, dict)
            assert set(condition) == {"condition_id", "description"}
            assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", condition["condition_id"])
            assert isinstance(condition["description"], str)
            assert condition["description"].strip()
            condition_ids.append(condition["condition_id"])
        assert len(condition_ids) == len(set(condition_ids))

        sources = metadata["applicability_evaluable_from"]
        assert isinstance(sources, list) and sources
        groups = []
        for option in sources:
            group = [option] if isinstance(option, str) else option
            assert isinstance(group, list) and group
            assert all(isinstance(source, str) for source in group)
            assert set(group) <= EVIDENCE_SOURCE_VALUES
            assert len(group) == len(set(group))
            groups.append(frozenset(group))
        assert len(groups) == len(set(groups))
    for field, values in (
        ("evidence_requirements", requirements),
        ("not_evaluable_when", disqualifiers),
    ):
        assert isinstance(values, list) and values, (
            f"{os.path.basename(path)}: {field} must be a non-empty list"
        )
        assert all(isinstance(value, str) and value.strip() for value in values), (
            f"{os.path.basename(path)}: {field} values must be non-empty strings"
        )


@pytest.mark.parametrize(
    ("pattern_id", "expected_sources"),
    sorted(REQUIRED_EVIDENCE_GATES.items()),
)
def test_source_dependent_patterns_have_required_evidence_gates(
    pattern_id, expected_sources
):
    """Known source traps must never fall back to visual guesswork."""
    path = _path_for_id(pattern_id)
    metadata = _metadata(path)
    actual_sources = frozenset(
        frozenset([option]) if isinstance(option, str) else frozenset(option)
        for option in metadata["evaluable_from"]
    )
    assert actual_sources == expected_sources
    assert len(metadata["evidence_requirements"]) >= 2
    assert len(metadata["not_evaluable_when"]) >= 2
    assert "## Evidence Gate" in _read(path)


@pytest.mark.parametrize(
    ("pattern_id", "expected_gates"),
    sorted(APPROVED_MECHANICAL_OUTCOME_GATES.items()),
)
def test_approved_mechanical_gates_preserve_owner_reviewed_outcomes(
    pattern_id, expected_gates
):
    """Owner-reviewed mechanical proposals pin all three outcome contracts."""
    metadata = _metadata(_path_for_id(pattern_id))

    assert {
        field: metadata[field]
        for field in (
            "evaluable_from",
            "strong_evaluable_from",
            "absence_evaluable_from",
        )
    } == expected_gates


@pytest.mark.parametrize(
    ("pattern_id", "expected_gates"),
    sorted(SEMANTIC_OUTCOME_GATES.items()),
)
def test_semantic_owner_review_pins_positive_strong_and_absence_gates(
    pattern_id, expected_gates
):
    metadata = _metadata(_path_for_id(pattern_id))
    assert {
        field: metadata[field]
        for field in (
            "evaluable_from",
            "strong_evaluable_from",
            "absence_evaluable_from",
        )
    } == expected_gates


def test_every_observable_entry_has_a_positive_source_gate():
    observable = {
        _metadata(path)["id"]
        for path in ENTRY_FILES
        if _metadata(path).get("observable") is not False
    }
    gated = {
        _metadata(path)["id"]
        for path in ENTRY_FILES
        if EVIDENCE_GATE_FIELDS <= set(_metadata(path))
    }

    assert observable == gated == set(REQUIRED_EVIDENCE_GATES)


def test_every_observable_entry_explicitly_declares_all_outcome_gates():
    """Bundled entries cannot inherit outcome authority from a broad base gate.

    External and legacy catalogs may still use loader defaults, but every entry
    shipped here records its strong and absence decisions explicitly.
    """
    missing = {}
    for path in ENTRY_FILES:
        metadata = _metadata(path)
        if metadata.get("observable") is False:
            continue
        absent_fields = OUTCOME_EVIDENCE_GATE_FIELDS - set(metadata)
        if absent_fields:
            missing[metadata["id"]] = sorted(absent_fields)

    assert not missing


def test_bundled_absence_gates_use_only_current_fail_closed_capabilities():
    """Absence currently trusts only complete transcript or rendered-PDF roles.

    Native decks, delivery recordings, and comparison groups remain useful for
    positive detections. They cannot re-enter an absence denominator until a
    versioned capability/alignment receipt makes their required modality
    mechanically decidable.
    """
    actual = {}
    for path in ENTRY_FILES:
        metadata = _metadata(path)
        if metadata.get("observable") is False:
            continue
        gate = metadata["absence_evaluable_from"]
        if gate is not None:
            assert all(isinstance(option, str) for option in gate)
            assert set(gate) <= {"static_slides", "transcript"}
            actual[metadata["id"]] = gate

    assert actual == EXPECTED_ABSENCE_GATES


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_evidence_gate_prose_matches_machine_absence_authority(path):
    """Worker-facing prose must not widen the executable absence gate."""
    metadata = _metadata(path)
    if metadata.get("observable") is False:
        return

    match = re.search(
        r"^## Evidence Gate\s*\n(?P<body>.*?)(?=^## |\Z)",
        _read(path),
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"{os.path.basename(path)}: missing Evidence Gate section"
    evidence_gate = match.group("body")
    absence_gate = metadata["absence_evaluable_from"]

    if absence_gate is None:
        assert "positive detection only" in evidence_gate
        assert "`absence_evaluable_from` is `null`" in evidence_gate
        assert "record `not_evaluable`, not `absent`" in evidence_gate
    elif absence_gate == ["static_slides"]:
        assert (
            "only from a complete, separately declared rendered PDF "
            "(`static_slides`)" in evidence_gate
        )
        assert (
            "native deck, delivery video, transcript, or comparison artifact "
            "does not authorize absence" in evidence_gate
        )
    elif absence_gate == ["transcript"]:
        assert "only from a complete transcript (`transcript`)" in evidence_gate
        assert (
            "delivery video, rendered/static slides, native decks, and "
            "comparison artifacts do not authorize absence" in evidence_gate
        )
    else:  # The exact policy test above should fail first with a clearer diff.
        pytest.fail(
            f"{metadata['id']}: unsupported bundled absence gate {absence_gate!r}"
        )


def test_positive_only_absence_null_set_is_exact():
    actual = {
        _metadata(path)["id"]
        for path in ENTRY_FILES
        if _metadata(path).get("absence_evaluable_from", "missing") is None
    }

    assert actual == POSITIVE_ONLY_IDS


@pytest.mark.parametrize(
    "pattern_id",
    sorted(EXPECTED_APPLICABILITY_CONDITION_IDS),
)
def test_applicability_contracts_pin_conditions_and_source_gates(pattern_id):
    metadata = _metadata(_path_for_id(pattern_id))

    assert (
        tuple(
            condition["condition_id"] for condition in metadata["not_applicable_when"]
        )
        == EXPECTED_APPLICABILITY_CONDITION_IDS[pattern_id]
    )
    assert (
        metadata["applicability_evaluable_from"]
        == (EXPECTED_APPLICABILITY_GATES[pattern_id])
    )
    assert all(
        condition["description"].strip()
        for condition in metadata["not_applicable_when"]
    )


def test_applicability_contract_set_is_exact():
    actual = {
        _metadata(path)["id"]
        for path in ENTRY_FILES
        if APPLICABILITY_GATE_FIELDS <= set(_metadata(path))
    }

    assert actual == set(EXPECTED_APPLICABILITY_CONDITION_IDS)


def test_lipsync_executable_subject_condition_is_the_applicability_canary():
    metadata = _metadata(_path_for_id("lipsync"))

    assert metadata["evaluable_from"] == ["delivery_video"]
    assert metadata["absence_evaluable_from"] is None
    assert metadata["applicability_evaluable_from"] == ["delivery_video"]
    assert metadata["not_applicable_when"] == [
        {
            "condition_id": "no-executable-subject",
            "description": (
                "Complete delivery video establishes that the talk explains or "
                "claims no executable tool, system, or workflow that could be "
                "demonstrated."
            ),
        }
    ]


def test_traveling_highlights_is_the_outcome_gate_canary():
    metadata = _metadata(_path_for_id("traveling-highlights"))

    assert metadata["strong_evaluable_from"] == ["native_deck", "delivery_video"]
    assert metadata["absence_evaluable_from"] is None


def test_progressive_reveal_explicitly_disables_absence():
    metadata = _metadata(_path_for_id("progressive-reveal"))

    assert metadata["strong_evaluable_from"] == metadata["evaluable_from"]
    assert metadata["absence_evaluable_from"] is None


def test_index_defines_confidence_and_binary_pattern_score_exactly():
    index = _read(INDEX)
    section = index[
        index.index(
            "## Decision Labels, Confidence, and Binary Pattern Score"
        ) : index.index("## Evidence-Source Contract")
    ]
    normalized = " ".join(section.split())

    assert "three **non-arithmetic** decision labels" in normalized
    assert (
        "`confidence` records evidence certainty and has exactly three valid "
        "values: `weak`, `moderate`, and `strong`" in normalized
    )
    assert "`strong` maps to the entry's Strong signal decision criterion" in normalized
    assert (
        "`moderate` maps to the entry's Moderate signal decision criterion"
        in normalized
    )
    assert (
        "`weak` means direct, source-located but incomplete positive evidence "
        "that satisfies the base gate" in normalized
    )
    assert (
        "It never means speculation, a failed source gate, `not_evaluable`, "
        "or `not_applicable`" in normalized
    )
    assert "`medium` is invalid and is never an alias for `moderate`" in normalized
    assert "Each detected pattern contributes **+1**" in normalized
    assert "each detected antipattern contributes **−1**" in normalized
    assert (
        "`Absent`, undetected, `not_evaluable`, and `not_applicable` outcomes "
        "contribute zero" in normalized
    )
    assert (
        "`pattern_score = count(patterns_detected) - "
        "count(antipatterns_detected)`" in normalized
    )


def test_evidence_source_enum_is_documented_in_index():
    index = _read(INDEX)
    section = index[
        index.index("## Evidence-Source Contract") : index.index("## Pattern Catalog")
    ]
    for source in EVIDENCE_SOURCE_VALUES:
        assert f"`{source}`" in section, f"index does not document {source!r}"


def test_index_scopes_exact_comparison_proof_to_positive_detections():
    index = _read(INDEX)
    section = index[
        index.index("## Evidence-Source Contract") : index.index("## Pattern Catalog")
    ]
    normalized = " ".join(section.split())

    assert "For a positive comparison detection" in normalized
    assert "For an undetected absence outcome" in normalized
    assert "there is no detection object or `evidence_sources_used` field" in normalized


def test_index_documents_null_absence_and_applicability_denominators():
    index = _read(INDEX)
    section = index[
        index.index("## Evidence-Source Contract") : index.index("## Pattern Catalog")
    ]
    normalized = " ".join(section.split())

    assert "`absence_evaluable_from: null`" in normalized
    assert "`not_applicable_when`" in normalized
    assert "`applicability_evaluable_from`" in normalized
    assert (
        "An explicit null absence gate permits source-gated positive detections "
        "but never authorizes an absence" in normalized
    )
    assert (
        "only an applicable assessment plus complete absence-gate coverage "
        "yields undetected" in normalized
    )


def test_unobservable_files_match_the_index():
    """The index's go-live tables are what a reader consults; the per-file
    `observable: false` flag is what a scorer consults. Drift between them means
    an entry gets scored that the index says cannot be, or vice versa.
    """
    flagged = {
        str(_front(f, "id")) for f in ENTRY_FILES if _front(f, "observable") == "false"
    }
    index = _read(INDEX)
    section = index[index.index("## Unobservable Patterns") :]
    listed = set(re.findall(r"^\| ([a-z0-9-]+) \|", section, re.M))
    assert flagged == listed, (
        f"only in files: {sorted(flagged - listed)}; "
        f"only in index: {sorted(listed - flagged)}"
    )


@pytest.mark.parametrize("pattern_id", sorted(RECLASSIFIED_UNOBSERVABLE_IDS))
def test_artifact_unprovable_entries_are_explicitly_unobservable(pattern_id):
    metadata = _metadata(_entry(pattern_id))
    text = _read(_entry(pattern_id))

    assert metadata["observable"] is False
    assert ALL_EVIDENCE_GATE_FIELDS.isdisjoint(metadata)
    assert "## Vault Observability" in text


def test_index_summary_statistics_are_accurate():
    """The counts are quoted into briefs and skill prose; a stale total sends
    scorers looking for entries that do not exist."""
    index = _read(INDEX)
    total = len(ENTRY_FILES)
    anti = len(ANTI_FILES)
    unobs = sum(1 for f in ENTRY_FILES if _front(f, "observable") == "false")
    unobs_anti = sum(1 for f in ANTI_FILES if _front(f, "observable") == "false")
    positive = sum(EVIDENCE_GATE_FIELDS <= set(_metadata(f)) for f in ENTRY_FILES)
    absence = sum(
        EVIDENCE_GATE_FIELDS <= set(_metadata(f))
        and _metadata(f).get("absence_evaluable_from", "default") is not None
        for f in ENTRY_FILES
    )
    applicability = sum(
        APPLICABILITY_GATE_FIELDS <= set(_metadata(f)) for f in ENTRY_FILES
    )
    positive_only = positive - absence
    assert (
        f"**Total entries:** {total} ({total - anti} patterns + {anti} antipatterns)"
        in index
    )
    assert (
        f"**Observable (vault-scorable):** {total - unobs} "
        f"({total - anti - (unobs - unobs_anti)} patterns + "
        f"{anti - unobs_anti} antipatterns)"
    ) in index
    assert (
        f"**Unobservable (go-live checklist):** {unobs} "
        f"({unobs - unobs_anti} patterns + {unobs_anti} antipatterns)"
    ) in index
    assert f"**Positive source-gated:** {positive}" in index
    assert f"**Absence source-gated:** {absence}" in index
    assert f"**Applicability-gated:** {applicability}" in index
    assert f"**Positive-only (absence disabled):** {positive_only}" in index


def test_public_catalog_totals_are_accurate():
    """README and plugin metadata must not advertise a stale scoring denominator."""
    readme = _read(os.path.join(REPO_ROOT, "README.md"))
    with open(
        os.path.join(REPO_ROOT, ".tessl-plugin", "plugin.json"),
        encoding="utf-8",
    ) as handle:
        description = json.load(handle)["description"]

    total = len(ENTRY_FILES)
    anti = len(ANTI_FILES)
    unobservable = sum(
        _metadata(path).get("observable") is False for path in ENTRY_FILES
    )
    unobservable_anti = sum(
        _metadata(path).get("observable") is False for path in ANTI_FILES
    )
    observable = total - unobservable
    observable_anti = anti - unobservable_anti
    observable_patterns = observable - observable_anti
    unobservable_patterns = unobservable - unobservable_anti

    observable_breakdown = (
        f"{observable} observable: {observable_patterns} patterns + "
        f"{observable_anti} antipatterns"
    )
    unobservable_breakdown = (
        f"{unobservable} unobservable: {unobservable_patterns} patterns + "
        f"{unobservable_anti} antipatterns"
    )
    assert observable_breakdown in description
    assert unobservable_breakdown in description
    assert (
        f"taxonomy's {observable} observable entries "
        f"({observable_patterns} patterns + {observable_anti} antipatterns)"
    ) in readme
    assert (
        f"**{observable} are observable** "
        f"({observable_patterns} patterns + {observable_anti} antipatterns)"
    ) in readme
    assert (
        f"**{unobservable} are unobservable**\n"
        f"({unobservable_patterns} patterns + {unobservable_anti} antipatterns)"
    ) in readme


def test_evidence_channels_use_the_closed_source_channel_vocabulary():
    allowed = {
        "transcript",
        "timed_transcript",
        "slides",
        "slide_sequence",
        "video",
        "talk_metadata",
    }
    for path in ENTRY_FILES:
        channels = _metadata(path).get("evidence_channels")
        if _metadata(path).get("observable") is not False:
            assert isinstance(channels, list) and channels, (
                f"{os.path.basename(path)}: every observable entry needs a "
                "non-empty evidence_channels list"
            )
            assert set(channels) <= allowed, (
                f"{os.path.basename(path)}: unknown channels {set(channels) - allowed}"
            )


def test_unobservable_entries_do_not_declare_evidence_gates():
    for path in ENTRY_FILES:
        metadata = _metadata(path)
        if metadata.get("observable") is False:
            assert ALL_EVIDENCE_GATE_FIELDS.isdisjoint(metadata), (
                f"{os.path.basename(path)}: unobservable entries cannot declare "
                "per-talk evidence gates"
            )


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_ids(ENTRY_FILES))
def test_every_gated_source_has_an_allowed_citation_channel(path):
    metadata = _metadata(path)
    channels = set(metadata.get("evidence_channels") or [])
    for gate_field in (
        "evaluable_from",
        "strong_evaluable_from",
        "absence_evaluable_from",
        "applicability_evaluable_from",
    ):
        if metadata.get(gate_field) is None:
            continue
        for option in metadata.get(gate_field, []):
            sources = [option] if isinstance(option, str) else option
            for source in sources:
                assert channels.intersection(EVIDENCE_SOURCE_CHANNELS[source]), (
                    f"{os.path.basename(path)}: {gate_field} source {source!r} "
                    "has no permitted source-located citation channel"
                )


def test_metadata_channel_declares_the_fields_it_can_use():
    for path in ENTRY_FILES:
        metadata = _metadata(path)
        channels = metadata.get("evidence_channels") or []
        fields = metadata.get("evidence_metadata_fields") or []
        assert bool(fields) == ("talk_metadata" in channels), (
            f"{os.path.basename(path)}: talk_metadata and evidence_metadata_fields "
            "must be declared together"
        )
        assert len(fields) == len(set(fields)), (
            f"{os.path.basename(path)}: duplicate evidence metadata fields"
        )


@pytest.mark.parametrize(
    "pattern_id,channels",
    [
        ("opening-punch", {"transcript", "timed_transcript", "slides", "video"}),
        ("call-to-adventure", {"transcript", "timed_transcript", "video"}),
        ("progressive-reveal", {"slide_sequence", "video"}),
        ("composite-animation", {"slides", "video"}),
        ("crawling-credits", {"slides", "video"}),
        ("soft-transitions", {"slide_sequence", "video"}),
        ("echo-chamber", {"transcript", "video"}),
        ("lipstick-on-a-pig", {"transcript", "slides", "video"}),
        ("coda", {"transcript", "slides", "slide_sequence", "video"}),
        ("second-look", {"transcript", "slides", "video"}),
        ("vacation-photos", {"transcript", "slides", "video"}),
        ("preroll", {"video"}),
        ("make-it-rain", {"video"}),
        ("weatherman", {"video"}),
        ("ant-fonts", {"slides", "video"}),
        ("three-part-close", {"slide_sequence", "video"}),
        ("screen-blackout", {"video"}),
        ("takahashi", {"slides", "slide_sequence", "video"}),
    ],
)
def test_channel_sensitive_patterns_require_exact_source_channels(pattern_id, channels):
    assert set(_metadata(_entry(pattern_id))["evidence_channels"]) == channels


def test_lightning_talk_metadata_corroborates_without_widening_the_video_gate():
    metadata = _metadata(_entry("lightning-talk"))

    assert metadata["evidence_metadata_fields"] == [
        "title",
        "conference",
        "slide_count",
    ]
    assert "talk_metadata" in metadata["evidence_channels"]
    assert metadata["evaluable_from"] == ["delivery_video"]


def test_hidden_process_and_provenance_ids_are_not_auto_scorable():
    hidden = {
        "abstract-attorney",
        "borrowed-shoes",
        "concurrent-creation",
        "crucible",
        "fourthought",
        "know-your-audience",
        "peer-review",
        "proposed",
        "required",
        "social-media-advertising",
    }
    assert {
        pattern_id
        for pattern_id in hidden
        if _metadata(_entry(pattern_id)).get("observable") is not False
    } == set()


@pytest.mark.parametrize(
    "pattern_id,anchors",
    [
        ("takahashi", ("one word, phrase, or image per slide", "hundreds of slides")),
        ("cookie-cutter", ("forcing each idea into exactly one slide",)),
        ("progressive-reveal", ("same base image", "adding one annotation per slide")),
        ("meme-as-argument", ("internet memes", "argumentative devices")),
        ("dead-demo", ("time filler", "no narrative connection")),
        (
            "three-part-close",
            ("three distinct slides", "summary, call to action, thanks"),
        ),
        ("anti-sell", ("products, employer, or credentials", "expects a pitch")),
        ("negative-ignorance", ("who here is not familiar with x?",)),
        ("shortchanged", ("last-minute reduction", "previous speakers running long")),
    ],
)
def test_stable_ids_retain_their_distinguishing_source_meaning(pattern_id, anchors):
    text = _read(_entry(pattern_id)).casefold()
    for anchor in anchors:
        assert anchor.casefold() in text, (
            f"{pattern_id}: missing source-meaning anchor {anchor!r}"
        )


def test_every_transcript_evaluable_entry_can_cite_a_transcript():
    """An entry evaluable from a source it cannot cite is unusable via it.

    Eleven observable entries declared `transcript` in `evaluable_from` — ten of
    them in `strong_evaluable_from` too — while omitting `transcript` from
    `evidence_channels`. A worker with a plain transcript then had no legal
    citation, and canonicalization still demanded an assessment because the
    applicability gate read as complete. The contradiction is only visible
    across the two fields, which is why nothing caught it.

    Every gate field counts, not just `evaluable_from`: an entry that admits a
    transcript for its STRONG tier, its absence proof, or its applicability
    determination needs a transcript channel just as much, and checking one
    field would let the same defect return through the other three.
    """
    gate_fields = (
        "evaluable_from",
        "strong_evaluable_from",
        "absence_evaluable_from",
        "applicability_evaluable_from",
    )
    offenders = []
    for path in ENTRY_FILES:
        metadata = _metadata(path)
        if not metadata.get("observable", True):
            continue
        admits_transcript = any(
            "transcript"
            in {
                source
                for group in (metadata.get(field) or [])
                for source in ([group] if isinstance(group, str) else group)
            }
            for field in gate_fields
        )
        if not admits_transcript:
            continue
        if "transcript" not in set(metadata.get("evidence_channels") or ()):
            offenders.append((metadata.get("id"), path))

    assert offenders == [], [entry for entry, _ in offenders]

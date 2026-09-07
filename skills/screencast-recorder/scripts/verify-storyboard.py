#!/usr/bin/env python3
"""Judge a recorded screen sequence against its approved storyboard.

The recording postmortem behind #364 lost a day to a rig that treated "the page
loaded" as proof. #369's answer is that what the viewer can *see* is the
contract, and that a verifier must be able to FAIL each way a take can look
right while being wrong. This is that verifier's manifest lane.

Five verification axes (#369 §5). This script owns the four that read structured
state; the pixel axis needs encoded frames and is reported `unverified`, never
`pass`:

  semantic  route, data fingerprint, required labels, seam state agreement
  geometry  required content in frame, unclipped, labels readable at DELIVERY size
  motion    required pan/scroll performed; pointer on target when the click fires
  time      the proof frame falls inside the ACTUALLY SPOKEN word span
  pixels    NOT CHECKED HERE — reported `unverified`

The distinction between `fail` and `unverified` is the point. A verifier that
reports `pass` for an axis it never examined is worse than no verifier, because
it converts an unknown into a false assurance — which is precisely the failure
#364 paid twenty-four hours for.

Usage:
    verify-storyboard.py <sequence.json>

Stdout: one JSON verdict object. Stderr: actionable diagnostics.
Exit 0 when every checked axis passes, 1 on any failure, 2 on usage error.

Input contract, output shape, and every finding code are documented in
skills/screencast-recorder/references/sequence-contract.md.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import TypeGuard

# Axis names, fixed so a consumer can group findings without string guessing.
SEMANTIC, GEOMETRY, MOTION, TIME, PIXELS = (
    "semantic",
    "geometry",
    "motion",
    "time",
    "pixels",
)

# State a seam must carry across unchanged. "Same page" is not continuity
# (#369 §2): page, data, framing, tabs, cursor and transient state must agree.
SEAM_FIELDS = (
    "route",
    "data_fingerprint",
    "viewport",
    "zoom",
    "scroll",
    "transform",
    "tabs",
    "active_tab",
)

# Only timings derived from a real transcription can satisfy the time axis.
# A WPM estimate predicts feasibility; it never establishes synchronisation.
ACTUAL_TIMING_SOURCE = "actual_word_timestamps"


def _finding(code, axis, subject, message, **extra):
    """Build a finding. `axis` is the VERIFICATION axis, never a pan/scroll axis.

    A caller describing a spatial axis passes `pan_axis`; `axis` here is one of
    the five verification axes. Because all four fields are named parameters,
    Python rejects a payload that would shadow one with "got multiple values",
    so no explicit guard is needed — an earlier draft added one and it was dead
    code. The first version of this function did collide (`axis="x"` for a pan),
    which is why the distinction is spelled out.
    """
    out = {"code": code, "axis": axis, "subject": subject, "message": message}
    out.update(extra)
    return out


def _rect_contains(outer, inner, margin=0):
    """Is `inner` inside `outer` inset by `margin`? Rects are [x, y, w, h]."""
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (
        ix >= ox + margin
        and iy >= oy + margin
        and ix + iw <= ox + ow - margin
        and iy + ih <= oy + oh - margin
    )


def _point_in_rect(point, rect):
    px, py = point
    rx, ry, rw, rh = rect
    return rx <= px <= rx + rw and ry <= py <= ry + rh


def _phrase_spans(words, phrase):
    """Every [start, end] where `phrase` is spoken, in order. Empty if never.

    All occurrences, not the first: a narration that says "ship it" twice has two
    valid moments to prove against, and matching only the first would fail a take
    whose proof frame is correctly placed during the second.

    Matches on a normalised token sequence so punctuation and spacing from the
    transcriber do not decide whether a phrase was spoken.
    """

    def norm(s):
        return "".join(c for c in s.lower() if c.isalnum())

    target = [norm(w) for w in phrase.split() if norm(w)]
    if not target:
        return []
    toks = [(norm(w.get("word", "")), w) for w in words]
    toks = [(tok, w) for tok, w in toks if tok]
    spans = []
    for i in range(len(toks) - len(target) + 1):
        if [tok for tok, _ in toks[i : i + len(target)]] == target:
            window = [w for _, w in toks[i : i + len(target)]]
            spans.append((float(window[0]["start"]), float(window[-1]["end"])))
    return spans


# What each row requirement needs before it can be judged at all. Without this,
# a requirement whose evidence is missing silently passes — the same "unexamined
# reported as passing" failure the pixel axis is careful to avoid, which this
# script committed everywhere else in its first draft.
EVIDENCE_FOR_REQUIREMENT = {
    # requirement -> (needed field, the axis that requirement is judged on)
    "route": (("entry", "route"), SEMANTIC),
    "data_fingerprint": (("entry", "data_fingerprint"), SEMANTIC),
    "visible_labels": (("entry", "labels"), SEMANTIC),
    # Missing viewport blocks GEOMETRY, not semantic. Filing it under the wrong
    # axis let `axes.geometry` read `pass` while its evidence was absent.
    "content_bounds": (("entry", "viewport"), GEOMETRY),
}


def check_evidence(row, clip, narration, delivery, findings):
    """Refuse to judge a requirement whose evidence the take does not carry.

    Returns the set of requirement names that cannot be judged. Every check
    below skips those: running a predicate whose evidence was just refused
    produces a verdict about nothing, and reports two codes for one defect.
    """
    blocked = set()
    req = row.get("require") or {}
    subject = row["id"]
    labels = (clip.get("entry") or {}).get("labels") or []

    for name, ((section, field), axis) in EVIDENCE_FOR_REQUIREMENT.items():
        if name not in req:
            continue
        if (clip.get(section) or {}).get(field) is None:
            blocked.add(name)
            findings.append(
                _finding(
                    "evidence_missing",
                    axis,
                    subject,
                    f"row requires {name} but the clip carries no {section}.{field}",
                    requirement=name,
                    missing_field=f"{section}.{field}",
                )
            )

    if delivery.get("min_label_px") and req.get("visible_labels"):
        if "scale" not in delivery:
            blocked.add("label_readability")
            findings.append(
                _finding(
                    "evidence_missing",
                    GEOMETRY,
                    subject,
                    "readability is required but delivery.scale is absent, so a "
                    "recorded height cannot be converted to its delivered size",
                    requirement="visible_labels",
                    missing_field="delivery.scale",
                )
            )
        if "visible_labels" in blocked:
            # The labels field is absent entirely, so nothing can be measured.
            # Without this, readability silently reported geometry: pass.
            blocked.add("label_readability")
        present = {label.get("text") for label in labels}
        measured = {label.get("text") for label in labels if "height_px" in label}
        # A label absent from the frame is reported by the semantic axis; asking
        # for its measurement too would be a second code for one root cause.
        unmeasured = [
            x for x in req["visible_labels"] if x in present and x not in measured
        ]
        if unmeasured:
            blocked.add("label_readability")
            findings.append(
                _finding(
                    "evidence_missing",
                    GEOMETRY,
                    subject,
                    "a required label carries no height_px, so readability cannot be judged",
                    requirement="visible_labels",
                    labels=unmeasured,
                )
            )

    if req.get("click_on_target"):
        for click in (e for e in clip.get("events") or [] if e.get("type") == "click"):
            absent = [f for f in ("pointer", "target_rect") if click.get(f) is None]
            if absent:
                blocked.add("click_on_target")
                findings.append(
                    _finding(
                        "evidence_missing",
                        MOTION,
                        subject,
                        "a click event carries no "
                        + " or ".join(absent)
                        + ", so it cannot be judged",
                        requirement="click_on_target",
                        missing_field=", ".join(f"events[].{f}" for f in absent),
                        at_seconds=click.get("t"),
                    )
                )

    if row.get("proof_frame_t") is not None and not (narration.get("words") or []):
        blocked.add("proof_frame_t")
        findings.append(
            _finding(
                "evidence_missing",
                TIME,
                subject,
                "row declares a proof frame but the sequence carries no narration words",
                requirement="proof_frame_t",
                missing_field="narration.words",
            )
        )

    return blocked


def check_semantic(row, clip, findings, exercised, blocked):
    req = row.get("require") or {}
    entry = clip.get("entry") or {}
    subject = row["id"]

    if any(k in req for k in ("route", "data_fingerprint", "visible_labels")):
        exercised.add(SEMANTIC)

    if "route" in req and "route" not in blocked and entry.get("route") != req["route"]:
        findings.append(
            _finding(
                "route_mismatch",
                SEMANTIC,
                subject,
                "clip is not on the route the row requires",
                expected=req["route"],
                actual=entry.get("route"),
            )
        )
    # Negative test 1: correct route, stale data. The route passing is exactly
    # what makes this failure invisible without a data fingerprint.
    if (
        "data_fingerprint" in req
        and "data_fingerprint" not in blocked
        and entry.get("data_fingerprint") != req["data_fingerprint"]
    ):
        findings.append(
            _finding(
                "stale_data",
                SEMANTIC,
                subject,
                "route is correct but the rendered data is not the required revision",
                expected=req["data_fingerprint"],
                actual=entry.get("data_fingerprint"),
            )
        )
    required_labels = (
        [] if "visible_labels" in blocked else req.get("visible_labels") or []
    )
    present = {label.get("text") for label in entry.get("labels") or []}
    missing = [label for label in required_labels if label not in present]
    if missing:
        findings.append(
            _finding(
                "required_label_absent",
                SEMANTIC,
                subject,
                "a label the phrase names is not present in the frame",
                missing=missing,
            )
        )


def check_geometry(row, clip, delivery, findings, exercised, blocked):
    req = row.get("require") or {}
    entry = clip.get("entry") or {}
    subject = row["id"]
    viewport = entry.get("viewport")

    bounds_runs = bool(req.get("content_bounds")) and "content_bounds" not in blocked
    readability_runs = (
        bool(delivery.get("min_label_px"))
        and bool(req.get("visible_labels"))
        and "label_readability" not in blocked
    )
    if bounds_runs or readability_runs:
        exercised.add(GEOMETRY)

    # Negative test 2: the content is present but partly outside the viewport.
    bounds = None if "content_bounds" in blocked else req.get("content_bounds")
    if bounds and viewport:
        margin = req.get("margin_px", 0)
        vp_rect = [0, 0, viewport["width"], viewport["height"]]
        if not _rect_contains(vp_rect, bounds, margin):
            findings.append(
                _finding(
                    "content_clipped",
                    GEOMETRY,
                    subject,
                    "required content is not fully inside the viewport at the declared margin",
                    content_bounds=bounds,
                    viewport=vp_rect,
                    margin_px=margin,
                )
            )

    # Negative test 4: readable in the browser is not readable at delivery size.
    min_px = None if "label_readability" in blocked else delivery.get("min_label_px")
    if min_px:
        scale = delivery.get("scale", 1.0)
        too_small = [
            {
                "text": label.get("text"),
                "delivery_px": round(label["height_px"] * scale, 2),
            }
            for label in entry.get("labels") or []
            if label.get("text") in (req.get("visible_labels") or [])
            and "height_px" in label
            and label["height_px"] * scale < min_px
        ]
        if too_small:
            findings.append(
                _finding(
                    "label_below_readable_size",
                    GEOMETRY,
                    subject,
                    "a required label falls below the readable threshold at delivery resolution",
                    min_label_px=min_px,
                    labels=too_small,
                )
            )


def check_motion(row, clip, findings, exercised, blocked):
    req = row.get("require") or {}
    events = clip.get("events") or []
    subject = row["id"]

    if req.get("pan") or req.get("click_on_target"):
        exercised.add(MOTION)

    # Negative test 3: content wider than the viewport with no pan performed.
    pan_req = req.get("pan")
    if pan_req:
        axis = pan_req.get("axis", "x")
        need = abs(pan_req.get("min_abs_delta", 0))
        moved = max(
            (
                abs(e.get("delta", 0))
                for e in events
                if e.get("type") == "pan" and e.get("axis") == axis
            ),
            default=0,
        )
        if moved < need:
            findings.append(
                _finding(
                    "pan_not_performed",
                    MOTION,
                    subject,
                    "the row requires a deliberate pan that the take does not contain",
                    pan_axis=axis,
                    required_abs_delta=need,
                    observed_abs_delta=moved,
                )
            )

    # Negative test 5: the click fires while the pointer is not on the target.
    if req.get("click_on_target") and "click_on_target" not in blocked:
        clicks = [e for e in events if e.get("type") == "click"]
        if not clicks:
            findings.append(
                _finding(
                    "click_absent",
                    MOTION,
                    subject,
                    "the row requires a visible click and the take contains none",
                )
            )
        for click in clicks:
            pointer, target = click.get("pointer"), click.get("target_rect")
            if pointer and target and not _point_in_rect(pointer, target):
                findings.append(
                    _finding(
                        "cursor_off_target",
                        MOTION,
                        subject,
                        "the pointer was not on the target when the click fired",
                        pointer=pointer,
                        target_rect=target,
                        at_seconds=click.get("t"),
                    )
                )


def check_time(row, narration, findings, exercised, blocked):
    subject = row["id"]
    proof_t = row.get("proof_frame_t")
    phrase = row.get("phrase")
    if proof_t is None or not phrase or "proof_frame_t" in blocked:
        return
    exercised.add(TIME)

    # Negative test 10: timing asserted from predicted WPM. WPM establishes
    # whether a script is deliverable; it never establishes synchronisation.
    if narration.get("source") != ACTUAL_TIMING_SOURCE:
        findings.append(
            _finding(
                "timing_not_from_actual_words",
                TIME,
                subject,
                "synchronisation was asserted without actual transcribed word timestamps",
                source=narration.get("source"),
                required_source=ACTUAL_TIMING_SOURCE,
            )
        )
        return

    spans = _phrase_spans(narration.get("words") or [], phrase)
    if not spans:
        findings.append(
            _finding(
                "phrase_not_spoken",
                TIME,
                subject,
                "the row's phrase does not appear in the transcribed narration",
                phrase=phrase,
            )
        )
        return
    if not any(start <= proof_t <= end for start, end in spans):
        findings.append(
            _finding(
                "proof_outside_phrase",
                TIME,
                subject,
                "the visual proof does not occur while the phrase is being spoken",
                phrase=phrase,
                spoken=[list(s) for s in spans],
                proof_frame_t=proof_t,
            )
        )


def check_seam(previous, following, tolerances, findings, exercised):
    """A seam passes only when the outgoing and incoming state agree (#369 §2)."""
    subject = f"{previous['id']}→{following['id']}"
    exit_state, entry_state = previous.get("exit") or {}, following.get("entry") or {}
    if exit_state and entry_state:
        exercised.add(SEMANTIC)

    for field in SEAM_FIELDS:
        before, after = exit_state.get(field), entry_state.get(field)
        # Absent on both sides compares equal and would pass silently. Two
        # manifests carrying only a route are not a verified continuity join.
        if before is None or after is None:
            findings.append(
                _finding(
                    "evidence_missing",
                    SEMANTIC,
                    subject,
                    f"seam cannot be judged: {field} is missing",
                    field=field,
                    present_on_exit=before is not None,
                    present_on_entry=after is not None,
                )
            )
            continue
        if before == after:
            continue
        # Negative test 7: a numeric transform drifted across the seam.
        tol = tolerances.get(field)
        if tol is not None and isinstance(before, dict) and isinstance(after, dict):
            keys = set(before) | set(after)
            # A key absent from one side is missing evidence; defaulting it to 0
            # would read the gap as "within tolerance".
            if all(k in before and k in after for k in keys) and all(
                abs(before[k] - after[k]) <= tol for k in keys
            ):
                continue
        # Negative test 8: the tab set or active tab changed across the seam.
        code = (
            "seam_tab_mismatch"
            if field in ("tabs", "active_tab")
            else "seam_state_mismatch"
        )
        findings.append(
            _finding(
                code,
                SEMANTIC,
                subject,
                f"seam does not carry {field} across unchanged",
                field=field,
                before=before,
                after=after,
            )
        )


def _is_number(value) -> TypeGuard[float]:
    """A real, finite number. `bool` is an `int` in Python and is not one.

    Finiteness matters: JSON admits NaN, and every comparison against NaN is
    false, so a NaN measurement silently satisfies any threshold it is tested
    against — passing readability while carrying no usable evidence.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _numbers(value, count):
    """True when `value` is a list of exactly `count` real finite numbers."""
    return (
        isinstance(value, list) and len(value) == count and all(map(_is_number, value))
    )


def _rect_problem(where, value):
    """A rect is four finite numbers describing a REGION, or a problem string.

    Zero width or height passes a coordinate-count check and describes nothing:
    a target_rect of [1,1,0,0] contains no point, so no click can land on it,
    yet the containment test reported motion: pass.
    """
    if not _numbers(value, 4):
        return f"{where} must be 4 finite numbers"
    if value[2] <= 0 or value[3] <= 0:
        return f"{where} must have positive width and height"
    return None


def _manifest_problem(where, manifest):
    """Shape problems in one manifest, or None.

    Presence is not enough: `viewport: {}` is present and useless, and accepting
    it let a required `content_bounds` report `geometry: pass` having compared
    nothing. Evidence must be the right SHAPE before it can be judged.
    """
    if manifest is None:
        return None  # absence is handled by the evidence gate, with its axis
    if not isinstance(manifest, dict):
        return f"{where} must be an object"
    if "viewport" in manifest:
        viewport = manifest["viewport"]
        if not isinstance(viewport, dict):
            return f"{where}.viewport must be an object"
        for side in ("width", "height"):
            size = viewport.get(side)
            # _is_number first: `NaN <= 0` is False, so a bare comparison admits NaN.
            if not _is_number(size) or size <= 0:
                return f"{where}.viewport.{side} must be a positive number"
    if "labels" in manifest:
        labels = manifest["labels"]
        if not isinstance(labels, list):
            return f"{where}.labels must be a list"
        for index, label in enumerate(labels):
            if not isinstance(label, dict):
                return f"{where}.labels[{index}] must be an object"
            if not isinstance(label.get("text"), str):
                return f"{where}.labels[{index}].text must be a string"
            if "height_px" in label and not _is_number(label["height_px"]):
                return f"{where}.labels[{index}].height_px must be a finite number"
    if "tabs" in manifest and not isinstance(manifest["tabs"], list):
        return f"{where}.tabs must be a list"
    for name, keys in (
        ("scroll", ("x", "y")),
        ("transform", ("pan_x", "pan_y", "zoom")),
    ):
        block = manifest.get(name)
        if block is None:
            continue
        if not isinstance(block, dict):
            return f"{where}.{name} must be an object"
        # An empty scroll/transform is present but carries no continuity evidence,
        # and two empty ones compare equal — agreement between two absences.
        for key in keys:
            if key not in block:
                return f"{where}.{name} must carry {key}"
            if not _is_number(block[key]):
                return f"{where}.{name}.{key} must be a finite number"
    if "zoom" in manifest and not _is_number(manifest["zoom"]):
        return f"{where}.zoom must be a finite number"
    return None


def structural_problem(sequence):
    """Describe the first contract violation, or None. Runs before verify().

    Covers both shapes verify() would otherwise trip over: a missing key it
    indexes (`clip["id"]`), and evidence present but malformed, which would be
    read as checkable and silently pass.
    """
    for name in ("clips", "rows"):
        items = sequence.get(name, [])
        if not isinstance(items, list):
            return f"{name} must be a list"
        seen = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                return f"{name}[{index}] must be an object"
            if not isinstance(item.get("id"), str) or not item["id"]:
                return f"{name}[{index}] needs a non-empty string id"
            # verify() looks clips up by id; a duplicate silently replaced the
            # earlier one, so a conforming clip could stand in for a failing one.
            if item["id"] in seen:
                return f"{name}[{index}] repeats the id {item['id']!r}"
            seen.add(item["id"])

    for index, clip in enumerate(sequence.get("clips", [])):
        for section in ("entry", "exit"):
            problem = _manifest_problem(f"clips[{index}].{section}", clip.get(section))
            if problem:
                return problem
        if "events" in clip and not isinstance(clip["events"], list):
            return f"clips[{index}].events must be a list"
        events = clip.get("events") or []
        for position, event in enumerate(events or []):
            at = f"clips[{index}].events[{position}]"
            if not isinstance(event, dict):
                return f"{at} must be an object"
            for field in ("t", "delta"):
                if field in event and not _is_number(event[field]):
                    return f"{at}.{field} must be a finite number"
            if event.get("type") == "click":
                if "pointer" in event and not _numbers(event["pointer"], 2):
                    return f"{at}.pointer must be 2 numbers"
                if "target_rect" in event:
                    problem = _rect_problem(f"{at}.target_rect", event["target_rect"])
                    if problem:
                        return problem

    for index, row in enumerate(sequence.get("rows", [])):
        if "require" in row and not isinstance(row["require"], dict):
            return f"rows[{index}].require must be an object"
        require = row.get("require") or {}
        for field in ("route", "data_fingerprint"):
            if field in require and not isinstance(require[field], str):
                return f"rows[{index}].require.{field} must be a string"
        if "visible_labels" in require:
            labels_req = require["visible_labels"]
            if not isinstance(labels_req, list) or not all(
                isinstance(x, str) for x in labels_req
            ):
                return f"rows[{index}].require.visible_labels must be a list of strings"
        if "click_on_target" in require and not isinstance(
            require["click_on_target"], bool
        ):
            return f"rows[{index}].require.click_on_target must be a boolean"
        if "content_bounds" in require:
            # `null` passed validation and then made the geometry check skip
            # itself — a declared requirement that verified nothing.
            problem = _rect_problem(
                f"rows[{index}].require.content_bounds", require["content_bounds"]
            )
            if problem:
                return problem
        if "margin_px" in require:
            margin = require["margin_px"]
            if not _is_number(margin) or margin < 0:
                return f"rows[{index}].require.margin_px must be a non-negative finite number"
        if "pan" in require:
            pan = require["pan"]
            if not isinstance(pan, dict):
                return f"rows[{index}].require.pan must be an object"
            # A pan requirement with no threshold defaulted to 0, which any
            # take satisfies — including one that performed no pan at all.
            if "min_abs_delta" not in pan:
                return f"rows[{index}].require.pan must carry min_abs_delta"
            if not _is_number(pan["min_abs_delta"]) or pan["min_abs_delta"] <= 0:
                return (
                    f"rows[{index}].require.pan.min_abs_delta must be a "
                    "positive finite number"
                )
        if "proof_frame_t" in row:
            proof = row["proof_frame_t"]
            if not _is_number(proof):
                return f"rows[{index}].proof_frame_t must be a finite number"
            # A proof frame with no phrase names no moment to prove against.
            # Skipping it silently let the time axis report pass for the sequence.
            phrase = row.get("phrase")
            if not isinstance(phrase, str) or not phrase.strip():
                return f"rows[{index}] declares proof_frame_t but no phrase to prove it against"

    delivery = sequence.get("delivery") or {}
    if not isinstance(delivery, dict):
        return "delivery must be an object"
    for field in ("width", "height", "min_label_px", "scale"):
        if field not in delivery:
            continue
        value = delivery[field]
        # Non-positive is not merely odd here: min_label_px <= 0 makes the
        # readability predicate vacuously true, and a zero scale erases the
        # measurement it converts.
        if not _is_number(value) or value <= 0:
            return f"delivery.{field} must be a positive finite number"

    tolerances = sequence.get("seam_tolerances") or {}
    if not isinstance(tolerances, dict):
        return "seam_tolerances must be an object"
    for field, value in tolerances.items():
        if not _is_number(value):
            return f"seam_tolerances.{field} must be a finite number"

    narration = sequence.get("narration") or {}
    if not isinstance(narration, dict):
        return "narration must be an object"
    words = narration.get("words", [])
    if not isinstance(words, list):
        return "narration.words must be a list"
    for index, word in enumerate(words):
        if not isinstance(word, dict):
            return f"narration.words[{index}] must be an object"
        for field in ("start", "end"):
            if not _is_number(word.get(field)):
                return f"narration.words[{index}].{field} must be a finite number"
    return None


def verify(sequence):
    findings = []
    exercised = set()
    delivery = sequence.get("delivery") or {}
    narration = sequence.get("narration") or {}
    clips = {c["id"]: c for c in sequence.get("clips", [])}

    if not sequence.get("rows"):
        findings.append(
            _finding(
                "sequence_empty",
                SEMANTIC,
                "sequence",
                "the sequence declares no storyboard rows, so it verifies nothing",
            )
        )

    for row in sequence.get("rows", []):
        clip = clips.get(row.get("clip"))
        if clip is None:
            findings.append(
                _finding(
                    "clip_missing",
                    SEMANTIC,
                    row.get("id", "?"),
                    "the row names a clip the sequence does not contain",
                    clip=row.get("clip"),
                )
            )
            continue
        blocked = check_evidence(row, clip, narration, delivery, findings)
        check_semantic(row, clip, findings, exercised, blocked)
        check_geometry(row, clip, delivery, findings, exercised, blocked)
        check_motion(row, clip, findings, exercised, blocked)
        check_time(row, narration, findings, exercised, blocked)

    ordered = sequence.get("clips", [])
    tolerances = sequence.get("seam_tolerances", {})
    for previous, following in zip(ordered, ordered[1:]):
        check_seam(previous, following, tolerances, findings, exercised)

    failed = {f["axis"] for f in findings}
    axes, unverified = {}, {}
    for axis in (SEMANTIC, GEOMETRY, MOTION, TIME):
        if axis in failed:
            axes[axis] = "fail"
        elif axis in exercised:
            axes[axis] = "pass"
        else:
            # No requirement in this sequence exercised the axis. Reporting pass
            # would claim an assurance nothing was checked to earn.
            axes[axis] = "unverified"
            unverified[axis] = (
                "no row in this sequence declared a requirement on this axis"
            )
    # Never report pass for the axis this script structurally cannot examine.
    axes[PIXELS] = "unverified"
    unverified[PIXELS] = "requires encoded frames; not checked by the manifest lane"

    return {
        "ok": not findings,
        "axes": axes,
        "unverified_axes": unverified,
        "finding_count": len(findings),
        "findings": findings,
        "counts": {
            "rows": len(sequence.get("rows", [])),
            "clips": len(ordered),
            "seams": max(len(ordered) - 1, 0),
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Verify a recorded screen sequence against its approved storyboard."
    )
    ap.add_argument("sequence", type=Path)
    args = ap.parse_args(argv)

    try:
        sequence = json.loads(args.sequence.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"ERROR: sequence file not found: {args.sequence} — emit it from the "
            "recording rig per references/sequence-contract.md.",
            file=sys.stderr,
        )
        return 2
    except json.JSONDecodeError as e:
        print(f"ERROR: {args.sequence} is not valid JSON ({e}).", file=sys.stderr)
        return 2
    except UnicodeDecodeError as e:
        print(
            f"ERROR: {args.sequence} is not UTF-8 text ({e}) — the sequence is a "
            "JSON document, not media.",
            file=sys.stderr,
        )
        return 2
    except OSError as e:
        print(
            f"ERROR: cannot read {args.sequence}: {e.strerror or e} — check the "
            "path and permissions.",
            file=sys.stderr,
        )
        return 2

    if not isinstance(sequence, dict):
        print("ERROR: sequence must be a JSON object.", file=sys.stderr)
        return 2

    problem = structural_problem(sequence)
    if problem:
        print(
            f"ERROR: {args.sequence} does not satisfy the sequence contract: "
            f"{problem} — see references/sequence-contract.md.",
            file=sys.stderr,
        )
        return 2

    try:
        verdict = verify(sequence)
    except (KeyError, TypeError, AttributeError, ValueError, IndexError) as e:
        # structural_problem() should have caught this; if a shape still reaches
        # verify(), the contract promises exit 2 and a diagnostic, not a traceback.
        print(
            f"ERROR: {args.sequence} could not be verified ({type(e).__name__}: {e}) "
            "— see references/sequence-contract.md.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(verdict, indent=2))
    if not verdict["ok"]:
        print(
            f"{verdict['finding_count']} finding(s); the take does not match its storyboard.",
            file=sys.stderr,
        )
        return 1
    print(
        "manifest lane passed; the pixel axis is UNVERIFIED and still needs frame checks.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

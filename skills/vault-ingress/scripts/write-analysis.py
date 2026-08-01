#!/usr/bin/env python3
"""Render per-talk analysis markdown from subagent return JSONs.

Step 4 (Persist Subagent Results) has two halves: merge the returns into the
tracking DB, and write `analyses/{talk_filename}.md` for each processed talk.
`persist-results.py` owns the first half. The second half was assigned to the
orchestrator in prose with no executable form, so it depended on an agent
remembering to hand-write a 160-line document per talk — and across the
2026-07-26 full reparse it was skipped for all 82 talks. The DB held the
corrected analysis while every `analyses/*.md` still asserted what the reparse
had just refuted.

This script is that second half. It reads the same `batch-returns.json` array
`persist-results.py` consumes, so the two halves cannot drift apart.

Sections rendered, in order:
  1. Title + provenance (filename, processed date, transcript/slide source)
  2. Rhetoric Notes (Dimensions 1-13) — verbatim from the return
  3. Areas for Improvement (Dimension 14)
  4. Adherence Assessment
  5. Structured Data — scalars as a list, `per_slide_visual` as a table,
     remaining nested blocks as fenced JSON
  6. Verbatim Examples
  7. Presentation Patterns Scoring — score line plus pattern/antipattern tables
  8. Catalog Feedback — only when the return carried findings

Returns vary in shape across batches (32 distinct top-level keys were observed
across 82 returns). Every section is skipped when its source field is absent
rather than emitting an empty heading, so a thin return produces a short file
instead of a scaffold of blanks.

Usage:
    write-analysis.py <batch-returns.json> <analyses-dir> [--run-date YYYY-MM-DD]
                      [--talks <tracking-database.json>]

    --talks supplies talk titles for the H1 and the source-validated pattern
    citations written by persist-results.py. Without it the H1 falls back to the
    return's own `title`, then to the filename stem, and citation locations are
    rendered explicitly as unverified.
    --run-date sets the "Processed" line when a return omits `processed_date`,
    matching persist-results.py's stamping so the DB and the file agree.

    Writes one file per PROCESSED return; a return whose status is present and
    not in PROCESSED_STATUSES is skipped rather than allowed to overwrite an
    earlier run's good file with a stub. Prints a JSON summary to stdout:
        {"written": <int>, "dir": "<path>",
         "files": [{"filename": "...", "path": "...", "bytes": <int>}],
         "skipped": [{"filename": "...", "status": "..."}]}
    Diagnostics and errors go to stderr; exit code is non-zero on failure.

Example:
    write-analysis.py batch-returns.json ~/.claude/rhetoric-knowledge-vault/analyses
"""

import json
import os
import sys
from datetime import date

# structured_data keys rendered as their own table rather than inline, because
# they are per-slide row collections and read as noise in a bullet list.
TABLE_BLOCKS = ("per_slide_visual",)

# Scalar types that render inline in the Structured Data bullet list.
SCALARS = (str, int, float, bool)

# Statuses whose returns carry an analysis worth writing. A return that reports
# a skipped status has no analysis to render, and writing one anyway would
# replace a good file from an earlier run with a near-empty stub — the file is
# keyed on the talk, so a later skip silently destroys an earlier success.
# A return with NO status is written: status is optional in the return schema
# and its absence is not evidence of a skip.
PROCESSED_STATUSES = frozenset({"processed", "processed_partial"})


def as_prose(value):
    """Coerce a prose field to a markdown string.

    The schema declares these as strings, but subagents sometimes return a list
    of finding objects instead (observed on `areas_for_improvement` and
    `new_patterns` in the 2026-07-26 reparse). Joining rather than rejecting
    keeps one non-conforming return from failing the whole batch, and a dict
    entry renders as a bullet per key so nothing is silently dropped.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                parts = "; ".join(f"**{k}:** {v}" for k, v in item.items())
                lines.append(f"- {parts}")
            else:
                lines.append(f"- {item}")
        return "\n".join(lines)
    if isinstance(value, dict):
        return "\n".join(f"- **{k}:** {v}" for k, v in value.items())
    return str(value)


def md_escape_cell(value):
    """Make a value safe inside a markdown table cell.

    Pipes would split the cell and newlines would end the row, so both are
    neutralized rather than dropped — a truncated evidence string is harder to
    audit than one with a visible separator.
    """
    text = "" if value is None else str(value)
    # Both newline forms end a row; a bare \r breaks rendering in some viewers
    # even though it is invisible in the source.
    return (text.replace("|", "\\|")
                .replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
                .strip())


def render_table(rows):
    """Render a list of flat dicts as a markdown table with a union of keys.

    Rows from different talks carry different columns; a union keeps a sparse
    row readable instead of silently dropping its extra fields.
    """
    if not rows:
        return []
    columns = []
    for row in rows:
        if not isinstance(row, dict):
            return ["```json", json.dumps(rows, indent=2, ensure_ascii=False), "```"]
        for key in row:
            if key not in columns:
                columns.append(key)
    out = ["| " + " | ".join(columns) + " |",
           "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        out.append("| " + " | ".join(md_escape_cell(row.get(c)) for c in columns) + " |")
    return out


def render_pattern_table(entries, *, evidence_verified=False):
    """Render patterns_detected / antipatterns_detected as an evidence table."""
    if not entries:
        return ["_None recorded._"]
    out = [
        "| Pattern ID | Confidence | Evidence | Source citations |",
        "|---|---|---|---|",
    ]
    for e in entries:
        if not isinstance(e, dict):
            out.append(f"| {md_escape_cell(e)} | | | |")
            continue
        pid = e.get("pattern_id", "")
        citations = e.get("evidence_citations")
        if not isinstance(citations, list) or not citations:
            rendered_citations = "legacy/unverified"
        else:
            rendered_citations = "; ".join(
                render_evidence_citation(
                    citation,
                    evidence_verified=evidence_verified,
                )
                for citation in citations
            )
        out.append(
            "| `{}` | {} | {} | {} |".format(
                md_escape_cell(pid),
                md_escape_cell(e.get("confidence", "")),
                md_escape_cell(e.get("evidence", "")),
                md_escape_cell(rendered_citations),
            )
        )
    return out


def render_evidence_citation(citation, *, evidence_verified=False):
    """Render one citation compactly; label locations not sourced from the DB."""
    if not isinstance(citation, dict):
        rendered = str(citation)
        return rendered if evidence_verified else f"unverified: {rendered}"
    channel = citation.get("channel")
    if channel in {"transcript", "timed_transcript"}:
        line_start = citation.get("line_start")
        line_end = citation.get("line_end")
        location = "transcript"
        if line_start is not None:
            location += f" lines {line_start}–{line_end or line_start}"
        if citation.get("start_seconds") is not None:
            location += (
                f" ({citation['start_seconds']}s–{citation.get('end_seconds')}s)"
            )
        quote = citation.get("quote")
        translation = citation.get("translation")
        if quote and translation:
            rendered = f'{location}: “{translation}” (original: “{quote}”)'
        else:
            rendered = f'{location}: “{quote}”' if quote else location
    elif channel in {"slides", "slide_sequence"}:
        label = "slide sequence" if channel == "slide_sequence" else "slides"
        numbers = citation.get("slide_numbers") or []
        rendered = f"{label} {', '.join(str(number) for number in numbers)}"
    elif channel == "video":
        rendered = (
            f"video {citation.get('start_seconds')}s–{citation.get('end_seconds')}s"
        )
    elif channel == "talk_metadata":
        rendered = f"metadata {citation.get('field')}={citation.get('value')!r}"
    else:
        rendered = json.dumps(citation, ensure_ascii=False)
    return rendered if evidence_verified else f"unverified: {rendered}"


def render_structured_data(sd):
    """Split structured_data into scalars, per-slide tables, and nested blocks."""
    if not isinstance(sd, dict) or not sd:
        return []
    out = ["## Structured Data", ""]
    # A None value means the subagent could not determine the field. Rendering it
    # as the literal "None" reads as a finding rather than an absence, and the
    # nested-block branch below already drops None — so drop it here too.
    scalars = [(k, v) for k, v in sd.items() if isinstance(v, SCALARS)]
    if scalars:
        for key, val in scalars:
            out.append(f"- **{key}:** {val}")
        out.append("")
    for key in TABLE_BLOCKS:
        rows = sd.get(key)
        if isinstance(rows, list) and rows:
            out += [f"### {key}", "", *render_table(rows), ""]
    nested = {k: v for k, v in sd.items()
              if k not in TABLE_BLOCKS and not isinstance(v, SCALARS) and v is not None}
    if nested:
        out += ["### Additional structured fields", "", "```json",
                json.dumps(nested, indent=2, ensure_ascii=False), "```", ""]
    return out


def render_verbatim(examples):
    if not isinstance(examples, dict) or not examples:
        return []
    out = ["## Verbatim Examples", ""]
    for category, items in examples.items():
        out.append(f"### {category}")
        out.append("")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    out.append(f"- {json.dumps(item, ensure_ascii=False)}")
                else:
                    out.append(f"- {item}")
        else:
            out.append(str(items))
        out.append("")
    return out


def render_catalog_feedback(feedback):
    """Render the reparse's catalog audit block when the return carried one."""
    if not isinstance(feedback, dict):
        return []
    populated = {k: v for k, v in feedback.items() if v}
    if not populated:
        return []
    out = ["## Catalog Feedback", ""]
    for section, entries in populated.items():
        out += [f"### {section}", "", "```json",
                json.dumps(entries, indent=2, ensure_ascii=False), "```", ""]
    return out


def render_analysis(ret, title=None, run_date=None, *, evidence_verified=False):
    """Build the full markdown document for one subagent return."""
    filename = ret.get("filename", "")
    heading = title or ret.get("title") or filename.removesuffix(".md")
    processed = ret.get("processed_date") or run_date or ""

    out = [f"# Rhetoric Analysis: {heading}", ""]
    out.append(f"**Filename:** {filename}")
    if processed:
        out.append(f"**Processed:** {processed}")
    if ret.get("status"):
        out.append(f"**Status:** {ret['status']}")
    if ret.get("transcript_source"):
        out.append(f"**Transcript source:** {ret['transcript_source']}")
    if ret.get("slide_source"):
        out.append(f"**Slide source:** {ret['slide_source']}")
    out += ["", "---", ""]

    if ret.get("rhetoric_notes"):
        out += ["## Rhetoric Notes (Dimensions 1-13)", "",
                as_prose(ret["rhetoric_notes"]), ""]
    if ret.get("areas_for_improvement"):
        out += ["## Areas for Improvement (Dimension 14)", "",
                as_prose(ret["areas_for_improvement"]), ""]
    if ret.get("adherence_assessment"):
        out += ["## Adherence Assessment", "",
                as_prose(ret["adherence_assessment"]), ""]

    out += render_structured_data(ret.get("structured_data"))
    out += render_verbatim(ret.get("verbatim_examples"))

    obs = ret.get("pattern_observations")
    if isinstance(obs, dict) and obs:
        out += ["## Presentation Patterns Scoring", ""]
        score = obs.get("pattern_score")
        if isinstance(score, dict):
            out.append("**Pattern score:** {} ({} patterns − {} antipatterns)".format(
                score.get("score", "?"),
                score.get("patterns_used", len(obs.get("patterns_detected") or [])),
                score.get("antipatterns_detected",
                          len(obs.get("antipatterns_detected") or [])),
            ))
        elif score is not None:
            out.append(f"**Pattern score:** {score}")
        out += ["", "### Patterns Detected", "",
                *render_pattern_table(
                    obs.get("patterns_detected"),
                    evidence_verified=evidence_verified,
                ), "",
                "### Antipatterns Detected", "",
                *render_pattern_table(
                    obs.get("antipatterns_detected"),
                    evidence_verified=evidence_verified,
                ), ""]
        unevaluable = obs.get("unevaluable_from_pdf")
        if unevaluable:
            out += ["### Unevaluable From Available Artifacts", "", "```json",
                    json.dumps(unevaluable, indent=2, ensure_ascii=False), "```", ""]

    out += render_catalog_feedback(ret.get("catalog_feedback"))
    return "\n".join(out).rstrip() + "\n"


def safe_output_name(filename):
    """Map a return's `filename` to a basename inside the output directory.

    `filename` arrives from a subagent return, which is model-generated text, so
    it is untrusted for path purposes. An absolute path or a `../` segment would
    otherwise let `os.path.join` escape the analyses directory and overwrite
    something else — `tracking-database.json` sits one level up. Only the
    basename is kept, and a name that is nothing but separators or dots is
    rejected rather than silently coerced into a plausible file.
    """
    base = os.path.basename(filename.replace("\\", "/").strip().rstrip("/")).strip()
    # `...` survives basename and is not caught by an equality check, so test for
    # "contains nothing but dots or whitespace" rather than enumerating cases.
    if not base.strip(". \t\r\n"):
        print(f"ERROR: return `filename` {filename!r} does not name a file; "
              f"cannot place its analysis file", file=sys.stderr)
        sys.exit(1)
    # Match the extension case-insensitively so `TALK.MD` does not become
    # `TALK.MD.md`.
    return base if base.lower().endswith(".md") else base + ".md"


def citation_claim(citation):
    """Return the model-owned portion used to bind raw and persisted evidence."""
    if not isinstance(citation, dict):
        return citation
    channel = citation.get("channel")
    engine_owned = {
        "transcript": {"line_start", "line_end", "start_seconds", "end_seconds"},
        "timed_transcript": {"line_start", "line_end", "start_seconds", "end_seconds"},
        "talk_metadata": {"value"},
    }.get(channel, set())
    return {key: value for key, value in citation.items() if key not in engine_owned}


def detection_claim(detection):
    """Return a detection without persistence-owned citation locations."""
    if not isinstance(detection, dict):
        return detection
    claim = {
        key: value
        for key, value in detection.items()
        if key != "evidence_citations"
    }
    citations = detection.get("evidence_citations")
    claim["evidence_citations"] = (
        [citation_claim(citation) for citation in citations]
        if isinstance(citations, list)
        else citations
    )
    return claim


def detection_arrays_match(raw, persisted):
    """True when persisted detections validate this batch, not an older one."""
    return (
        isinstance(raw, list)
        and isinstance(persisted, list)
        and [detection_claim(item) for item in raw]
        == [detection_claim(item) for item in persisted]
    )


def overlay_persisted_evidence(ret, talk):
    """Overlay source-validated detections from the just-persisted talk record.

    The batch file intentionally remains the immutable handoff between scripts,
    so deterministic line/time/value stamps exist only in the tracking DB. Keep
    the return's rich score object, but source both detailed detection arrays from
    the DB before rendering. Returns ``(effective_return, evidence_verified)``.
    """
    raw = ret.get("pattern_observations")
    persisted = talk.get("pattern_observations") if isinstance(talk, dict) else None
    if not isinstance(raw, dict) or not isinstance(persisted, dict):
        return ret, False
    fields = [
        field
        for field in ("patterns_detected", "antipatterns_detected")
        if field in raw
    ]
    if not fields or any(
        field not in persisted
        or not detection_arrays_match(raw[field], persisted[field])
        for field in fields
    ):
        return ret, False
    observations = dict(raw)
    for field in fields:
        observations[field] = persisted[field]
    if "evidence_schema_version" in persisted:
        observations["evidence_schema_version"] = persisted["evidence_schema_version"]
    effective = dict(ret)
    effective["pattern_observations"] = observations
    return effective, True


def load_json(path, label):
    """Read and parse a JSON file, failing visibly with operator guidance."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {label} file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERROR: cannot read {label} file {path}: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: {label} file {path} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def parse_args(argv):
    args, run_date, talks_path = [], None, None
    i = 0
    while i < len(argv):
        if argv[i] in ("--run-date", "--talks"):
            if i + 1 >= len(argv):
                print(f"ERROR: {argv[i]} requires a value", file=sys.stderr)
                sys.exit(1)
            if argv[i] == "--run-date":
                run_date = argv[i + 1]
            else:
                talks_path = argv[i + 1]
            i += 2
            continue
        args.append(argv[i])
        i += 1
    if len(args) != 2:
        print(f"Usage: {sys.argv[0]} <batch-returns.json> <analyses-dir> "
              f"[--run-date YYYY-MM-DD] [--talks <tracking-database.json>]",
              file=sys.stderr)
        sys.exit(1)
    if run_date is None:
        run_date = date.today().isoformat()
    else:
        try:
            date.fromisoformat(run_date)
        except ValueError:
            print(f"ERROR: --run-date must be YYYY-MM-DD, got {run_date!r}", file=sys.stderr)
            sys.exit(1)
    return args[0], args[1], run_date, talks_path


def main():
    batch_path, out_dir, run_date, talks_path = parse_args(sys.argv[1:])

    returns = load_json(batch_path, "batch-returns")
    if not isinstance(returns, list):
        print(f"ERROR: {batch_path} must be a JSON array of subagent returns, "
              f"got {type(returns).__name__}", file=sys.stderr)
        sys.exit(1)

    talks = {}
    if talks_path:
        db = load_json(talks_path, "tracking database")
        if not isinstance(db, dict) or not isinstance(db.get("talks"), list):
            print(f"ERROR: {talks_path} is not a tracking database — expected a JSON "
                  f"object with a `talks` array; pass the vault's "
                  f"tracking-database.json or drop --talks", file=sys.stderr)
            sys.exit(1)
        talks = {
            talk.get("filename"): talk
            for talk in db["talks"]
            if isinstance(talk, dict)
        }

    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        print(f"ERROR: cannot create output directory {out_dir}: {e} — check the "
              f"path exists as a directory and is writable", file=sys.stderr)
        sys.exit(1)

    written, skipped = [], []
    for i, ret in enumerate(returns):
        if not isinstance(ret, dict):
            print(f"ERROR: batch-returns entry {i} is a {type(ret).__name__}, not a "
                  f"subagent return object; check that {batch_path} is an array of "
                  f"returns and not an array of filenames or paths", file=sys.stderr)
            sys.exit(1)
        name = ret.get("filename")
        if not name:
            print("ERROR: a return has no `filename` field; cannot place its "
                  "analysis file", file=sys.stderr)
            sys.exit(1)
        status = ret.get("status")
        if status and status not in PROCESSED_STATUSES:
            skipped.append({"filename": name, "status": status})
            continue
        safe_name = safe_output_name(name)
        path = os.path.join(out_dir, safe_name)
        talk = talks.get(name)
        effective, evidence_verified = overlay_persisted_evidence(ret, talk)
        body = render_analysis(
            effective,
            title=talk.get("title") if isinstance(talk, dict) else None,
            run_date=run_date,
            evidence_verified=evidence_verified,
        )
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
        except OSError as e:
            print(f"ERROR: cannot write analysis file {path}: {e} — check the "
                  f"output directory is writable and has free space", file=sys.stderr)
            sys.exit(1)
        written.append({"filename": name, "path": path, "bytes": len(body.encode())})

    json.dump({"written": len(written), "dir": out_dir, "files": written,
               "skipped": skipped}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

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

    --talks supplies talk titles for the H1; without it the H1 falls back to the
    return's own `title`, then to the filename stem.
    --run-date sets the "Processed" line when a return omits `processed_date`,
    matching persist-results.py's stamping so the DB and the file agree.

    Writes one file per return; prints a JSON summary to stdout:
        {"written": <int>, "dir": "<path>",
         "files": [{"filename": "...", "path": "...", "bytes": <int>}]}
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
    return text.replace("|", "\\|").replace("\n", " ").strip()


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


def render_pattern_table(entries):
    """Render patterns_detected / antipatterns_detected as an evidence table."""
    if not entries:
        return ["_None recorded._"]
    out = ["| Pattern ID | Confidence | Evidence |", "|---|---|---|"]
    for e in entries:
        if not isinstance(e, dict):
            out.append(f"| {md_escape_cell(e)} | | |")
            continue
        pid = e.get("pattern_id", "")
        out.append("| `{}` | {} | {} |".format(
            md_escape_cell(pid),
            md_escape_cell(e.get("confidence", "")),
            md_escape_cell(e.get("evidence", "")),
        ))
    return out


def render_structured_data(sd):
    """Split structured_data into scalars, per-slide tables, and nested blocks."""
    if not isinstance(sd, dict) or not sd:
        return []
    out = ["## Structured Data", ""]
    scalars = [(k, v) for k, v in sd.items() if isinstance(v, SCALARS) or v is None]
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


def render_analysis(ret, title=None, run_date=None):
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
                *render_pattern_table(obs.get("patterns_detected")), "",
                "### Antipatterns Detected", "",
                *render_pattern_table(obs.get("antipatterns_detected")), ""]
        unevaluable = obs.get("unevaluable_from_pdf")
        if unevaluable:
            out += ["### Unevaluable From Available Artifacts", "", "```json",
                    json.dumps(unevaluable, indent=2, ensure_ascii=False), "```", ""]

    out += render_catalog_feedback(ret.get("catalog_feedback"))
    return "\n".join(out).rstrip() + "\n"


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

    titles = {}
    if talks_path:
        db = load_json(talks_path, "tracking database")
        titles = {t.get("filename"): t.get("title") for t in db.get("talks", [])}

    os.makedirs(out_dir, exist_ok=True)
    written = []
    for ret in returns:
        name = ret.get("filename")
        if not name:
            print("ERROR: a return has no `filename` field; cannot place its "
                  "analysis file", file=sys.stderr)
            sys.exit(1)
        path = os.path.join(out_dir, name if name.endswith(".md") else name + ".md")
        body = render_analysis(ret, title=titles.get(name), run_date=run_date)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        written.append({"filename": name, "path": path, "bytes": len(body.encode())})

    json.dump({"written": len(written), "dir": out_dir, "files": written},
              sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

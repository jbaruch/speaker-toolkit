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
`persist-results.py` consumes, verifies each exact return against its completed
claim receipt, then renders analysis-owned fields from the persisted effective
talk. Version-2/v3 omissions therefore preserve the same values in both the DB and
Markdown instead of disappearing from the file. Receipt-bound catalog feedback,
which is intentionally not stored on the talk, still comes from the exact return.

Sections rendered, in order:
  1. Title + provenance (filename, processed date, transcript/slide source)
  2. Rhetoric Notes (Dimensions 1-13) — from persisted effective state
  3. Areas for Improvement (Dimension 14)
  4. Adherence Assessment
  5. Structured Data — scalars as a list, `per_slide_visual` as a table,
     remaining nested blocks as fenced JSON
  6. Verbatim Examples
  7. Presentation Patterns Scoring — score line plus pattern/antipattern tables
  8. Catalog Feedback — only when the return carried findings

Persisted analyses vary in shape across generations. Every section is skipped
when its effective source field is absent rather than emitting an empty heading.

Usage:
    write-analysis.py <batch-returns.json> <analyses-dir>
                      --talks <tracking-database.json> [--run-date YYYY-MM-DD]

    --talks supplies the canonical effective analysis, talk titles for the H1,
    and the completed queue generation that authorizes each replacement. An
    active, unpersisted claim is rejected.
    The persisted talk's `processed_date` is the authority for the "Processed"
    line. `--run-date` is an optional consistency assertion against that
    writer-owned stamp for every return; it accepts the same date/timestamp
    forms as persist-results.py. A legacy date-only return value is ignored; an
    explicit full timestamp must agree.

    Writes one file per PROCESSED return as one transaction: every existing
    target is preflighted, every body is staged, and replacements roll back if a
    later target fails. A return whose required terminal status is not in
    PROCESSED_STATUSES is skipped rather than allowed to overwrite an earlier
    run's good file with a stub. Prints a JSON summary to stdout:
        {"written": <int>, "dir": "<path>",
         "files": [{"filename": "...", "path": "...", "bytes": <int>}],
         "skipped": [{"filename": "...", "status": "..."}]}
    Diagnostics and errors go to stderr; exit code is non-zero on failure.

Example:
    write-analysis.py batch-returns.json ~/.claude/rhetoric-knowledge-vault/analyses
"""

import copy
import json
import os
import stat
import sys
import tempfile
import unicodedata

from ingress_contract import IngressContractError, reject_tracking_database_symlink
from return_validation import (
    ANALYSIS_STATUSES,
    LEGACY_UNBASELINEABLE_SCORING_STATUS,
    SNAPSHOT_RETURN_SCHEMA_VERSIONS,
    ReturnValidationError,
    normalize_processing_stamp,
    resolve_return_schema_version,
    validate_batch_claims_against_talks,
    validate_batch,
    validate_persisted_v2_analysis_state,
    validate_persisted_catalog_generation,
)

# structured_data keys rendered as their own table rather than inline, because
# they are per-slide row collections and read as noise in a bullet list.
TABLE_BLOCKS = ("per_slide_visual",)

# Scalar types that render inline in the Structured Data bullet list.
SCALARS = (str, int, float, bool)

# Statuses whose returns carry an analysis worth writing. A return that reports
# a skipped status has no analysis to render, and writing one anyway would
# replace a good file from an earlier run with a near-empty stub — the file is
# keyed on the talk, so a later skip silently destroys an earlier success.
PROCESSED_STATUSES = ANALYSIS_STATUSES

# Every field render_analysis reads from the canonical talk. Catalog feedback is
# deliberately absent: it is a receipt-bound review side channel, not DB state.
PERSISTED_RENDER_FIELDS = (
    "status",
    "transcript_source",
    "slide_source",
    "slides_local_path",
    "rhetoric_notes",
    "areas_for_improvement",
    "adherence_assessment",
    "structured_data",
    "verbatim_examples",
    "pattern_observations",
    "pattern_scoring_generation_status",
    "pattern_scoring_generation_reasons",
)


class AnalysisBatchWriteError(OSError):
    """A staged analysis batch could not commit or recover atomically."""


def effective_render_payload(ret, talk):
    """Build the single canonical payload rendered after persistence.

    The completed claim binds `ret` byte-for-byte, while the talk contains the
    result of applying that return's versioned omission/replacement semantics.
    Only the non-persisted catalog-feedback side channel comes from the return.
    """
    if resolve_return_schema_version(ret) in SNAPSHOT_RETURN_SCHEMA_VERSIONS:
        validate_persisted_v2_analysis_state(talk)
    payload = {"filename": ret["filename"]}
    for field in PERSISTED_RENDER_FIELDS:
        if field in talk:
            payload[field] = copy.deepcopy(talk[field])
    if "catalog_feedback" in ret:
        payload["catalog_feedback"] = copy.deepcopy(ret["catalog_feedback"])
    return payload


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


def render_pattern_table(entries):
    """Render patterns_detected / antipatterns_detected as an evidence table."""
    if not entries:
        return ["_None recorded._"]
    out = [
        "| Pattern ID | Confidence | Evidence Source | Sources Used | Evidence |",
        "|---|---|---|---|---|",
    ]
    for e in entries:
        if not isinstance(e, dict):
            out.append(f"| {md_escape_cell(e)} | | | | |")
            continue
        pid = e.get("pattern_id", "")
        sources_used = e.get("evidence_sources_used")
        sources_used_text = (
            ", ".join(str(source) for source in sources_used)
            if isinstance(sources_used, list) else ""
        )
        out.append("| `{}` | {} | {} | {} | {} |".format(
            md_escape_cell(pid),
            md_escape_cell(e.get("confidence", "")),
            md_escape_cell(e.get("evidence_source", "")),
            md_escape_cell(sources_used_text),
            md_escape_cell(e.get("evidence", "")),
        ))
    return out


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


def render_analysis(ret, title=None, run_date=None, *, persisted_date=None):
    """Build the full markdown document for one canonical analysis payload."""
    filename = ret.get("filename", "")
    heading = title or ret.get("title") or filename.removesuffix(".md")
    processed = persisted_date or run_date or ret.get("processed_date") or ""

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
    if ret.get("slides_local_path"):
        out.append(f"**Slides local path:** {ret['slides_local_path']}")
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
        if (ret.get("pattern_scoring_generation_status") ==
                LEGACY_UNBASELINEABLE_SCORING_STATUS):
            out.append(
                "**Baseline eligibility:** Excluded from current pattern "
                "baselines; this replayed legacy return cannot establish the "
                "current evidence contract.")
            reasons = ret.get("pattern_scoring_generation_reasons")
            if isinstance(reasons, list) and reasons:
                out.append(
                    "**Generation reasons:** " + ", ".join(str(reason)
                                                            for reason in reasons))
            out.append("")
        score = obs.get("pattern_score")
        if isinstance(score, dict):
            out.append("**Pattern score:** {} ({} patterns − {} antipatterns)".format(
                score.get("score", "?"),
                score.get("patterns_used", len(obs.get("patterns_detected") or [])),
                score.get("antipatterns_detected",
                          len(obs.get("antipatterns_detected") or [])),
            ))
        elif score is not None:
            out.append("**Pattern score:** {} ({} patterns − {} antipatterns)".format(
                score,
                len(obs.get("patterns_detected") or []),
                len(obs.get("antipatterns_detected") or []),
            ))
        out += ["", "### Patterns Detected", "",
                *render_pattern_table(obs.get("patterns_detected")), "",
                "### Antipatterns Detected", "",
                *render_pattern_table(obs.get("antipatterns_detected")), ""]
        evidence_sources = obs.get("evidence_sources")
        if evidence_sources:
            out += ["### Evidence Sources Inspected", "",
                    ", ".join(f"`{source}`" for source in evidence_sources), ""]
        unevaluable = obs.get("not_evaluable") or obs.get("unevaluable_from_pdf")
        if unevaluable:
            out += ["### Not Evaluable From Available Evidence", "",
                    *render_table(unevaluable), ""]

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


def output_target_key(filename):
    """Return a filesystem-conservative identity for one sanitized target."""
    return unicodedata.normalize("NFC", safe_output_name(filename).casefold())


def persisted_processed_stamp(ret, talk, requested_stamp=None):
    """Resolve the exact writer-owned stamp, rejecting batch-argument drift."""
    stored = talk.get("processed_date")
    if not isinstance(stored, str) or not stored.strip():
        raise ReturnValidationError(
            f"{ret.get('filename', '<unknown>')} persisted talk has no processed_date; "
            "run persist-results.py successfully before writing its analysis")
    try:
        normalized_stored = normalize_processing_stamp(stored)
    except ValueError as exc:
        raise ReturnValidationError(
            f"{ret.get('filename', '<unknown>')} persisted processed_date is invalid: "
            f"{exc}") from exc
    if normalized_stored != stored:
        raise ReturnValidationError(
            f"{ret.get('filename', '<unknown>')} persisted processed_date {stored!r} "
            f"is not the canonical stored stamp {normalized_stored!r}; rerun "
            "persist-results.py before writing its analysis")

    if requested_stamp is not None and requested_stamp != stored:
        raise ReturnValidationError(
            f"{ret.get('filename', '<unknown>')} --run-date {requested_stamp!r} "
            f"does not match persisted value {stored!r}")
    returned_stamp = ret.get("processed_date")
    if returned_stamp is not None:
        try:
            normalized_returned_stamp = normalize_processing_stamp(returned_stamp)
        except ValueError as exc:
            raise ReturnValidationError(
                f"{ret.get('filename', '<unknown>')} return processed_date is invalid: "
                f"{exc}") from exc
        if (len(normalized_returned_stamp) > 10
                and normalized_returned_stamp != stored):
            raise ReturnValidationError(
                f"{ret.get('filename', '<unknown>')} explicit return processed_date "
                f"{normalized_returned_stamp!r} conflicts with persisted batch "
                f"stamp {stored!r}")
    return stored


def _target_key_from_basename(filename):
    return unicodedata.normalize("NFC", filename.casefold())


def preflight_output_targets(out_dir, rendered):
    """Reject existing normalized collisions and unsafe target entry types."""
    try:
        entries = list(os.scandir(out_dir))
    except OSError as exc:
        raise AnalysisBatchWriteError(
            f"cannot inspect output directory {out_dir}: {exc}") from exc
    existing_by_key = {}
    for entry in entries:
        key = _target_key_from_basename(entry.name)
        existing_by_key.setdefault(key, []).append(entry)

    for name, path, _body in rendered:
        basename = os.path.basename(path)
        matches = existing_by_key.get(_target_key_from_basename(basename), [])
        collisions = sorted(entry.name for entry in matches if entry.name != basename)
        if collisions:
            raise AnalysisBatchWriteError(
                f"analysis target {basename!r} for {name!r} collides with existing "
                f"output entry or entries {collisions} under normalized/case-folded "
                "filesystem identity")
        exact = [entry for entry in matches if entry.name == basename]
        if not exact:
            continue
        try:
            mode = os.lstat(exact[0].path).st_mode
        except OSError as exc:
            raise AnalysisBatchWriteError(
                f"cannot inspect existing analysis target {exact[0].path}: {exc}") from exc
        if stat.S_ISDIR(mode):
            raise AnalysisBatchWriteError(
                f"analysis target {exact[0].path} is an existing directory")
        if not (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
            raise AnalysisBatchWriteError(
                f"analysis target {exact[0].path} is neither a regular file nor "
                "a symbolic link and cannot be replaced safely")


def _stage_text(path, body):
    """Flush one complete body beside its target without changing the target."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    basename = os.path.basename(path)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{basename}.", suffix=".stage", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        return temp_path
    except BaseException:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def _safe_unlink(path):
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _rollback_analysis_batch(items):
    """Restore originals in reverse order, retaining backups if recovery fails."""
    errors = []
    for item in reversed(items):
        target = item["path"]
        if item["installed"]:
            try:
                os.unlink(target)
            except FileNotFoundError:
                pass
            except OSError as exc:
                errors.append(f"cannot remove partial target {target}: {exc}")
                continue
        backup = item["backup"]
        if backup:
            try:
                os.replace(backup, target)
                item["backup"] = None
            except OSError as exc:
                errors.append(
                    f"cannot restore {target} from recovery backup {backup}: {exc}")
    return errors


def atomic_write_batch(rendered):
    """Stage every analysis, then commit all targets with reverse rollback."""
    if not rendered:
        return
    out_dir = os.path.dirname(os.path.abspath(rendered[0][1])) or "."
    preflight_output_targets(out_dir, rendered)

    items = []
    try:
        for name, path, body in rendered:
            items.append({
                "name": name,
                "path": path,
                "stage": _stage_text(path, body),
                "backup": None,
                "installed": False,
            })
    except OSError as exc:
        for item in items:
            _safe_unlink(item["stage"])
        raise AnalysisBatchWriteError(
            f"cannot stage complete analysis batch: {exc}") from exc

    try:
        # Recheck after staging so an external entry created during the staging
        # window cannot bypass the normalized collision/type preflight.
        preflight_output_targets(out_dir, rendered)
        for item in items:
            target = item["path"]
            if os.path.lexists(target):
                mode = os.lstat(target).st_mode
                if stat.S_ISDIR(mode):
                    raise AnalysisBatchWriteError(
                        f"analysis target {target} became a directory before commit")
                directory = os.path.dirname(os.path.abspath(target)) or "."
                basename = os.path.basename(target)
                fd, backup = tempfile.mkstemp(
                    prefix=f".{basename}.", suffix=".backup", dir=directory)
                os.close(fd)
                try:
                    os.replace(target, backup)
                except BaseException:
                    _safe_unlink(backup)
                    raise
                item["backup"] = backup
            os.replace(item["stage"], target)
            item["installed"] = True
    except BaseException as exc:
        rollback_errors = _rollback_analysis_batch(items)
        for item in items:
            _safe_unlink(item["stage"])
        if rollback_errors:
            backups = [item["backup"] for item in items if item["backup"]]
            raise AnalysisBatchWriteError(
                f"analysis batch commit failed ({exc}); rollback also failed: "
                f"{'; '.join(rollback_errors)}; recovery backups retained: {backups}"
            ) from exc
        raise AnalysisBatchWriteError(
            f"analysis batch commit failed ({exc}); every prior target was restored"
        ) from exc
    for item in items:
        try:
            _safe_unlink(item["backup"])
            item["backup"] = None
        except OSError:
            # Every target is already committed. A retained hidden backup is a
            # recoverable cleanup artifact, not grounds to roll back a complete
            # batch after other backups may already have been discarded.
            pass
    for item in items:
        _safe_unlink(item["stage"])


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
              f"--talks <tracking-database.json> [--run-date YYYY-MM-DD]",
              file=sys.stderr)
        sys.exit(1)
    if run_date is not None:
        try:
            run_date = normalize_processing_stamp(run_date)
        except ValueError as exc:
            print("ERROR: --run-date must be YYYY-MM-DD or a timezone-aware "
                  f"ISO-8601 timestamp: {exc}", file=sys.stderr)
            sys.exit(1)
    return args[0], args[1], run_date, talks_path


def main():
    batch_path, out_dir, run_date, talks_path = parse_args(sys.argv[1:])

    returns = load_json(batch_path, "batch-returns")
    try:
        catalog = validate_batch(returns)
    except ReturnValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not talks_path:
        print("ERROR: --talks <tracking-database.json> is required so queue "
              "generation can be verified before an analysis file is replaced",
              file=sys.stderr)
        sys.exit(1)
    try:
        reject_tracking_database_symlink(talks_path)
    except IngressContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    db = load_json(talks_path, "tracking database")
    if not isinstance(db, dict) or not isinstance(db.get("talks"), list):
        print(f"ERROR: {talks_path} is not a tracking database — expected a JSON "
              f"object with a `talks` array; pass the vault's "
              "tracking-database.json", file=sys.stderr)
        sys.exit(1)
    try:
        talks_by_name = validate_batch_claims_against_talks(
            db["talks"], returns, required_state="completed")
        for ret in returns:
            validate_persisted_catalog_generation(
                talks_by_name[ret["filename"]], ret, catalog)
    except ReturnValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    titles = {name: talk.get("title") for name, talk in talks_by_name.items()}

    # Render the entire batch before touching the output directory. A malformed
    # late entry cannot leave earlier analysis files replaced.
    rendered, skipped = [], []
    target_owners = {}
    for ret in returns:
        name = ret.get("filename")
        status = ret.get("status")
        if status not in PROCESSED_STATUSES:
            skipped.append({"filename": name, "status": status})
            continue
        safe_name = safe_output_name(name)
        target_key = output_target_key(name)
        prior = target_owners.get(target_key)
        if prior is not None:
            print(
                f"ERROR: return filenames {prior!r} and {name!r} resolve to the "
                f"same analysis target {safe_name!r}; refusing to overwrite one talk "
                "with another",
                file=sys.stderr,
            )
            sys.exit(1)
        target_owners[target_key] = name
        path = os.path.join(out_dir, safe_name)
        try:
            processed_stamp = persisted_processed_stamp(
                ret, talks_by_name[name], requested_stamp=run_date)
        except ReturnValidationError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            render_payload = effective_render_payload(ret, talks_by_name[name])
        except ReturnValidationError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        body = render_analysis(
            render_payload,
            title=titles.get(name),
            persisted_date=processed_stamp,
        )
        rendered.append((name, path, body))

    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        print(f"ERROR: cannot create output directory {out_dir}: {e} — check the "
              f"path exists as a directory and is writable", file=sys.stderr)
        sys.exit(1)

    try:
        atomic_write_batch(rendered)
    except OSError as e:
        print(f"ERROR: cannot commit analysis batch: {e} — check the output "
              "directory is writable and has free space", file=sys.stderr)
        sys.exit(1)

    written = []
    for name, path, body in rendered:
        written.append({"filename": name, "path": path, "bytes": len(body.encode())})

    json.dump({"written": len(written), "dir": out_dir, "files": written,
               "skipped": skipped, "pattern_catalog_fingerprint": catalog.fingerprint},
              sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

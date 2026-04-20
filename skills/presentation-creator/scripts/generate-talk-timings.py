#!/usr/bin/env python3
"""
Generate timemytalk.app timing files from a presentation outline.

Parses the ## Pacing Summary table and ## Section headers from a
presentation-outline.md to produce a plain-text timing file with
cumulative MM:SS timestamps for each chapter.

Usage:
    python3 generate-talk-timings.py <outline.md>
    python3 generate-talk-timings.py <outline.md> --qa 5
    python3 generate-talk-timings.py <outline.md> --output timings.txt

Requires:
    - Python 3.10+ (stdlib only -- no pip install needed)
"""

import argparse
import re
import sys


# --- Pacing Summary Parsing ---

def parse_pacing_table(text):
    """Parse the ## Pacing Summary markdown table.

    Expects rows like:
        | Act 1: The Challenge | 5 min |
        | Act 2: The Journey   | 12 min |

    Also handles sub-minute durations like "1:30 min" or "0:30 min".

    Returns a list of (section_name, duration_seconds) tuples.
    """
    sections = []
    in_pacing = False
    header_seen = False

    for line in text.split("\n"):
        stripped = line.strip()

        # Detect the Pacing Summary heading
        if re.match(r"^##\s+Pacing\s+Summary", stripped, re.IGNORECASE):
            in_pacing = True
            header_seen = False
            continue

        # Stop at the next ## heading
        if in_pacing and re.match(r"^##\s+", stripped) and not re.match(
            r"^##\s+Pacing\s+Summary", stripped, re.IGNORECASE
        ):
            break

        if not in_pacing:
            continue

        # Skip non-table lines
        if not stripped.startswith("|"):
            continue

        # Skip separator rows (|---|---|)
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            header_seen = True
            continue

        # Skip the header row (first row before separator)
        if not header_seen:
            continue

        # Parse table row: | Section Name | Duration |
        cells = [c.strip() for c in stripped.split("|")]
        # Split on | gives empty strings at start/end
        cells = [c for c in cells if c]

        if len(cells) < 2:
            continue

        name = cells[0].strip()
        duration_str = cells[1].strip()

        # Skip totals row
        if name.lower().startswith("total") or name.startswith("**"):
            continue

        seconds = _parse_duration(duration_str)
        if seconds is not None and seconds > 0:
            sections.append((name, seconds))

    return sections


def _parse_duration(duration_str):
    """Parse a duration string into seconds.

    Supports:
        "5 min"       -> 300
        "12 min"      -> 720
        "1:30 min"    -> 90
        "0:30 min"    -> 30
        ":30 min"     -> 30
        "5"           -> 300  (bare number = minutes)
        "1:30"        -> 90
        ":30"         -> 30
    """
    s = duration_str.strip().lower()
    # Remove trailing "min", "mins", "minutes"
    s = re.sub(r"\s*min(ute)?s?\s*$", "", s).strip()

    if not s:
        return None

    # MM:SS or :SS format
    m = re.match(r"^(\d*):(\d{1,2})$", s)
    if m:
        minutes = int(m.group(1)) if m.group(1) else 0
        secs = int(m.group(2))
        return minutes * 60 + secs

    # Plain number (minutes)
    m = re.match(r"^(\d+)$", s)
    if m:
        return int(m.group(1)) * 60

    return None


# --- Section Header Parsing ---

def parse_section_headers(text):
    """Parse ## Section headers for finer-grained timing info.

    Looks for patterns like:
        ## Act 1: The Challenge [5 min, slides 4-8]
        ## Opening [3 min, slides 1-3]

    Returns a list of (section_name, duration_seconds) tuples.
    """
    sections = []
    # Match ## headers with [N min, ...] bracketed info
    pattern = re.compile(
        r"^##\s+(.+?)\s*\[(\d+(?::\d{1,2})?)\s*min"
    , re.MULTILINE)

    for match in pattern.finditer(text):
        name = match.group(1).strip()
        duration_str = match.group(2).strip()
        seconds = _parse_duration(duration_str + " min")
        if seconds is not None and seconds > 0:
            sections.append((name, seconds))

    return sections


# --- Subdivision ---

def subdivide_long_acts(pacing_sections, section_headers, threshold_seconds=300):
    """Subdivide pacing sections that exceed the threshold using section headers.

    When a pacing section exceeds threshold_seconds (~5 min), look for
    section headers whose names match and split accordingly. Matching uses
    substring containment (pacing name in header or vice versa) plus
    meaningful word overlap.

    Durations are scaled proportionally with remainder assigned to the last
    segment to prevent rounding drift.

    Returns a new list of (name, duration_seconds) tuples.
    """
    if not section_headers:
        return list(pacing_sections)

    result = []

    for pace_name, pace_dur in pacing_sections:
        if pace_dur <= threshold_seconds:
            result.append((pace_name, pace_dur))
            continue

        # Find section headers that match this pacing entry
        matching_headers = []
        pace_lower = pace_name.lower()
        for hdr_name, hdr_dur in section_headers:
            hdr_lower = hdr_name.lower()
            if (pace_lower in hdr_lower or hdr_lower in pace_lower
                    or _name_overlap(pace_lower, hdr_lower)):
                matching_headers.append((hdr_name, hdr_dur))

        if len(matching_headers) >= 2:
            # Scale durations proportionally, assign remainder to last segment
            header_total = sum(d for _, d in matching_headers)
            if header_total > 0:
                allocated = 0
                for i, (hdr_name, hdr_dur) in enumerate(matching_headers):
                    if i == len(matching_headers) - 1:
                        scaled = pace_dur - allocated
                    else:
                        scaled = pace_dur * hdr_dur // header_total
                        allocated += scaled
                    result.append((hdr_name, scaled))
            else:
                result.append((pace_name, pace_dur))
        else:
            result.append((pace_name, pace_dur))

    return result


def _name_overlap(a, b):
    """Check if two section names share meaningful words."""
    stop_words = {"the", "a", "an", "of", "and", "in", "to", "for", "act", "section", "part"}
    words_a = set(re.findall(r"[a-z]+", a)) - stop_words
    words_b = set(re.findall(r"[a-z]+", b)) - stop_words
    if not words_a or not words_b:
        return False
    overlap = words_a & words_b
    return len(overlap) >= 1


# --- Output ---

def format_seconds(total_seconds):
    """Format seconds as MM:SS."""
    minutes = total_seconds // 60
    secs = total_seconds % 60
    return f"{minutes}:{secs:02d}"


def generate_timings(sections, qa_minutes=0):
    """Generate timing lines from sections list.

    Args:
        sections: list of (name, duration_seconds) tuples
        qa_minutes: optional Q&A duration in minutes (added before FINISH)

    Returns:
        list of "MM:SS Label" strings
    """
    lines = []
    cumulative = 0

    for name, duration in sections:
        lines.append(f"{format_seconds(cumulative)} {name}")
        cumulative += duration

    if qa_minutes > 0:
        lines.append(f"{format_seconds(cumulative)} Q&A")
        cumulative += qa_minutes * 60

    lines.append(f"{format_seconds(cumulative)} FINISH")
    return lines


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Generate timemytalk.app timing file from a presentation outline.",
        epilog="Produces MM:SS chapter lines for timemytalk.app timer.",
    )
    parser.add_argument("outline", help="Path to presentation-outline.md")
    parser.add_argument("--qa", type=int, default=0,
                        help="Q&A duration in minutes to add before FINISH")
    parser.add_argument("--output", "-o",
                        help="Output path (default: stdout)")

    args = parser.parse_args()

    with open(args.outline, "r", encoding="utf-8") as f:
        text = f.read()

    # Parse pacing summary table
    pacing = parse_pacing_table(text)

    if not pacing:
        print("WARNING: No usable pacing rows found in outline (table missing or all rows empty).", file=sys.stderr)
        # Emit a minimal FINISH-only output
        output = "0:00 FINISH\n"
    else:
        # Parse section headers for subdivision
        headers = parse_section_headers(text)

        # Subdivide long acts
        sections = subdivide_long_acts(pacing, headers)

        # Generate timing lines
        lines = generate_timings(sections, qa_minutes=args.qa)
        output = "\n".join(lines) + "\n"

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Timings written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()

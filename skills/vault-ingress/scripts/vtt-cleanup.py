#!/usr/bin/env python3
"""Clean a WebVTT subtitle file into plain transcript text.

Strips timestamps, cue position markers, blank lines, and deduplicates
consecutive identical lines. VTT is a rigid format — this handles it reliably.

Usage:
    vtt-cleanup.py <input.vtt> [<output.txt>]

    If output is omitted, writes to the same path with .txt extension.

Examples:
    vtt-cleanup.py transcripts/aBcDeFg.en.vtt
    vtt-cleanup.py transcripts/aBcDeFg.ru.vtt transcripts/aBcDeFg.txt
"""

import re
import sys


def clean_vtt(vtt_text):
    """Clean VTT content into plain text."""
    lines = vtt_text.split('\n')
    cleaned = []
    prev_line = None

    for line in lines:
        line = line.strip()

        # Skip WebVTT header
        if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
            continue

        # Skip timestamp lines: 00:00:01.234 --> 00:00:04.567
        if re.match(r'\d{2}:\d{2}.*-->', line):
            continue

        # Skip cue position markers: align:start position:0%
        if re.match(r'(align|position|size|line|vertical):', line):
            continue

        # Skip numeric cue identifiers (standalone numbers)
        if re.match(r'^\d+$', line):
            continue

        # Skip blank lines
        if not line:
            continue

        # Strip HTML tags (<c>, </c>, <b>, etc.) that appear in some VTTs
        line = re.sub(r'<[^>]+>', '', line)

        # Deduplicate consecutive identical lines
        if line != prev_line:
            cleaned.append(line)
            prev_line = line

    return '\n'.join(cleaned)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <input.vtt> [<output.txt>]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        output_path = re.sub(r'\.[^.]+\.vtt$', '.txt', input_path)
        if output_path == input_path:
            output_path = input_path.rsplit('.', 1)[0] + '.txt'

    with open(input_path, encoding='utf-8') as f:
        vtt_text = f.read()

    cleaned = clean_vtt(vtt_text)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(cleaned)

    input_lines = len(vtt_text.split('\n'))
    output_lines = len(cleaned.split('\n'))
    print(f"Cleaned {input_path}: {input_lines} lines → {output_lines} lines → {output_path}")


if __name__ == "__main__":
    main()

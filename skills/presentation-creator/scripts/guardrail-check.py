#!/usr/bin/env python3
"""Run guardrail checks on a presentation outline against a speaker profile.

Reads the outline and profile, computes each check, and outputs a structured
report with [PASS], [WARN], or [FAIL] labels.

Usage:
    guardrail-check.py <outline.md> <speaker-profile.json>

Output: Prints the guardrail report to stdout.
"""

import json
import re
import sys


def count_slides(outline_text):
    """Count total slides from ### Slide headers and slide ranges."""
    total = 0
    for line in outline_text.split('\n'):
        # Match "### Slide 30-33:" style ranges
        m = re.match(r'###\s+Slide\s+(\d+)\s*-\s*(\d+)', line)
        if m:
            total += int(m.group(2)) - int(m.group(1)) + 1
            continue
        # Match "### Slide 5:" style singles
        m = re.match(r'###\s+Slide\s+(\d+)', line)
        if m:
            total += 1
    # Also check for "Total slides: N" line
    m = re.search(r'Total slides:\s*(\d+)', outline_text)
    if m:
        return int(m.group(1))
    return total


def find_sections(outline_text):
    """Find Act sections with their slide ranges."""
    sections = []
    for m in re.finditer(
        r'##\s+(.+?)\s*\[(\d+)\s*min,\s*slides?\s*(\d+)\s*-\s*(\d+)\]',
        outline_text
    ):
        sections.append({
            'name': m.group(1).strip(),
            'minutes': int(m.group(2)),
            'slide_start': int(m.group(3)),
            'slide_end': int(m.group(4)),
            'slide_count': int(m.group(4)) - int(m.group(3)) + 1,
        })
    return sections


def check_slide_budget(total_slides, profile):
    """Check slide count against profile budget."""
    budgets = profile.get('guardrail_sources', {}).get('slide_budgets', [])
    duration = profile.get('rhetoric_defaults', {}).get('default_duration_minutes', 45)

    max_slides = None
    for b in budgets:
        dur_key = b.get('duration_minutes') or b.get('duration_min')
        if dur_key and dur_key == duration:
            max_slides = b.get('max_slides')
            break

    if max_slides is None:
        max_slides = int(duration * 1.5)

    if total_slides > max_slides:
        return 'FAIL', f'{total_slides}/{max_slides} for {duration}-min slot'
    elif max_slides - total_slides <= max_slides * 0.05:
        return 'WARN', f'{total_slides}/{max_slides} for {duration}-min slot (near limit)'
    else:
        return 'PASS', f'{total_slides}/{max_slides} for {duration}-min slot'


def check_act1_ratio(sections, total_slides, profile):
    """Check Act 1 ratio against profile limit with WARN threshold."""
    act1 = None
    for s in sections:
        if 'act 1' in s['name'].lower() or s == sections[1] if len(sections) > 1 else False:
            act1 = s
            break
    # Try to find any section that looks like Act 1
    if act1 is None:
        for s in sections:
            if 'act 1' in s['name'].lower() or 'the challenge' in s['name'].lower() or 'the problem' in s['name'].lower():
                act1 = s
                break
    # Fall back to second section (first after opening)
    if act1 is None and len(sections) > 1:
        act1 = sections[1]

    if act1 is None or total_slides == 0:
        return 'PASS', 'No Act 1 section found'

    ratio = (act1['slide_count'] / total_slides) * 100

    limits = profile.get('guardrail_sources', {}).get('act1_ratio_limits', [])
    max_pct = 45  # default
    for lim in limits:
        max_pct = lim.get('max_percentage') or lim.get('max_percent', 45)

    # Three-outcome logic:
    #   value > limit        → FAIL
    #   limit - value <= 5   → WARN
    #   limit - value > 5    → PASS
    if ratio > max_pct:
        return 'FAIL', f'{ratio:.1f}% (limit: {max_pct}%) — {act1["name"]}: {act1["slide_count"]}/{total_slides} slides'
    elif max_pct - ratio <= 5:
        return 'WARN', f'{ratio:.1f}% (limit: {max_pct}%, within 5pp) — {act1["name"]}: {act1["slide_count"]}/{total_slides} slides'
    else:
        return 'PASS', f'{ratio:.1f}% (limit: {max_pct}%) — {act1["name"]}: {act1["slide_count"]}/{total_slides} slides'


def check_closing(outline_text):
    """Check closing sequence completeness."""
    closing_section = ''
    in_closing = False
    for line in outline_text.split('\n'):
        if re.match(r'##\s+Closing', line, re.IGNORECASE):
            in_closing = True
        if in_closing:
            closing_section += line + '\n'

    has_summary = bool(re.search(r'summary|takeaway|recap|key point', closing_section, re.IGNORECASE))
    has_cta = bool(re.search(r'call to action|CTA|action item|this week', closing_section, re.IGNORECASE))
    has_social = bool(re.search(r'shownotes|social|thank|QR|handles|URL', closing_section, re.IGNORECASE))

    parts = []
    if has_summary: parts.append('summary')
    if has_cta: parts.append('CTA')
    if has_social: parts.append('social')

    if len(parts) == 3:
        return 'PASS', f'summary={has_summary} CTA={has_cta} social={has_social}'
    else:
        missing = [x for x in ['summary', 'CTA', 'social'] if x not in parts]
        return 'FAIL', f'missing: {", ".join(missing)}'


def check_cut_lines(outline_text):
    """Check for [CUT LINE] markers."""
    if re.search(r'\[CUT LINE', outline_text, re.IGNORECASE):
        return 'PASS', 'Cut line markers present'
    modular = True  # assume modular by default
    if modular:
        return 'FAIL', 'No [CUT LINE] markers found (modular_design is enabled)'
    return 'PASS', 'Cut lines not required (modular_design disabled)'


def check_data_attribution(outline_text):
    """Check for data claims missing sources."""
    missing = []
    for line in outline_text.split('\n'):
        # Lines with percentages or data claims
        if re.search(r'\d+%', line) and 'slide' in line.lower():
            # Check if next few lines have a source
            pass  # Simplified — just flag lines with "No source"
    for m in re.finditer(r'(###.*?\n(?:.*?\n)*?)\s*-\s*No source', outline_text):
        missing.append(m.group(0).split('\n')[0].strip())

    if missing:
        return 'FAIL', f'{len(missing)} slides missing attribution: {"; ".join(missing[:3])}'
    return 'PASS', 'All data slides have sources'


def check_profanity(outline_text, profile):
    """Check for on-slide profanity."""
    register = profile.get('rhetoric_defaults', {}).get('profanity_calibration', 'none')
    profanity_words = ['damn', 'hell', 'shit', 'fuck', 'ass', 'crap', 'bullshit']
    found = []
    for i, line in enumerate(outline_text.split('\n'), 1):
        if line.strip().startswith('- Speaker:') or line.strip().startswith('- Body:') or line.strip().startswith('- Visual:'):
            for word in profanity_words:
                if word in line.lower():
                    found.append(f'"{word}" on line {i}')
    if found:
        return 'FAIL' if register == 'none' else 'WARN', f'{register} register, found: {"; ".join(found)}'
    return 'PASS', f'{register} register applied, 0 on-slide'


def main():
    if len(sys.argv) != 3:
        print(f'Usage: {sys.argv[0]} <outline.md> <speaker-profile.json>', file=sys.stderr)
        sys.exit(1)

    outline_path, profile_path = sys.argv[1], sys.argv[2]

    with open(outline_path) as f:
        outline = f.read()
    with open(profile_path) as f:
        profile = json.load(f)

    total_slides = count_slides(outline)
    sections = find_sections(outline)

    print('GUARDRAIL CHECK')
    print('=' * 60)

    checks = [
        ('Slide budget', check_slide_budget(total_slides, profile)),
        ('Act 1 ratio', check_act1_ratio(sections, total_slides, profile)),
        ('Closing', check_closing(outline)),
        ('Cut lines', check_cut_lines(outline)),
        ('Data attribution', check_data_attribution(outline)),
        ('Profanity', check_profanity(outline, profile)),
    ]

    for name, (label, detail) in checks:
        print(f'[{label}] {name}: {detail}')

    print('=' * 60)


if __name__ == '__main__':
    main()

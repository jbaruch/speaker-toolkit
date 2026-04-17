#!/usr/bin/env python3
"""Insert bright-yellow placeholder slides into a PowerPoint deck at specified positions.

Placeholders are visually loud (yellow background, bold [PLACEHOLDER] title) so they
stand out in thumbnail view when editing large decks. Each placeholder includes a
subtitle with context about what the slide needs to become.

Usage:
    insert-placeholder-slides.py <deck.pptx> <positions.json>
    insert-placeholder-slides.py <deck.pptx> --at 5 --title "New Slide" --subtitle "Description"
    insert-placeholder-slides.py <deck.pptx> <positions.json> --output adapted-deck.pptx

The JSON file format (multiple slides):
    [
        {"position": 5,  "title": "The Great Siloing", "subtitle": "Yegge 20/60/20 adoption data"},
        {"position": 16, "title": "Cost Curves",       "subtitle": "MIT SSRN paper visualization"}
    ]

Positions are 1-indexed (final slide number after all insertions). Slides are inserted
from highest position to lowest so earlier inserts don't shift later targets.

Requires:
    - python-pptx  (pip install python-pptx)
"""

import argparse
import json
import sys
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

YELLOW = RGBColor(0xFF, 0xF2, 0x9E)
TITLE_COLOR = RGBColor(0x20, 0x20, 0x20)
SUBTITLE_COLOR = RGBColor(0x40, 0x40, 0x40)


def add_placeholder_slide(prs, title, subtitle=""):
    """Append a yellow placeholder slide with title and optional subtitle."""
    blank_layout = None
    for layout in prs.slide_layouts:
        if layout.name == "Blank":
            blank_layout = layout
            break
    if blank_layout is None:
        print("  WARNING: No 'Blank' layout found, using last layout", file=sys.stderr)
        blank_layout = prs.slide_layouts[-1]

    slide = prs.slides.add_slide(blank_layout)
    sw, sh = prs.slide_width, prs.slide_height

    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, sw, sh)
    bg.fill.solid()
    bg.fill.fore_color.rgb = YELLOW
    bg.line.fill.background()

    margin = Emu(457200)
    title_h = Emu(1600000)
    box = slide.shapes.add_textbox(margin, Emu(sh // 3), sw - 2 * margin, title_h)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = f"[PLACEHOLDER] {title}"
    run.font.size = Pt(44)
    run.font.bold = True
    run.font.color.rgb = TITLE_COLOR

    if subtitle:
        sub_box = slide.shapes.add_textbox(
            margin, Emu(sh // 3) + title_h + Emu(200000),
            sw - 2 * margin, Emu(2500000)
        )
        stf = sub_box.text_frame
        stf.word_wrap = True
        sp = stf.paragraphs[0]
        sp.alignment = PP_ALIGN.CENTER
        srun = sp.add_run()
        srun.text = subtitle
        srun.font.size = Pt(20)
        srun.font.color.rgb = SUBTITLE_COLOR

    return slide


def move_slide(prs, old_index, new_index):
    """Reorder slide by manipulating sldIdLst XML."""
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    xml_slides.remove(slides[old_index])
    xml_slides.insert(new_index, slides[old_index])


def main():
    parser = argparse.ArgumentParser(
        description="Insert yellow placeholder slides into a PowerPoint deck."
    )
    parser.add_argument("deck", help="Path to .pptx file")
    parser.add_argument("json_file", nargs="?", help="JSON file with placeholder definitions")
    parser.add_argument("--at", type=int, action="append", help="Position (1-indexed, repeatable)")
    parser.add_argument("--title", nargs="*", help="Title(s) for --at mode")
    parser.add_argument("--subtitle", nargs="*", help="Subtitle(s) for --at mode")
    parser.add_argument("--output", "-o", help="Output path (default: overwrite input)")
    args = parser.parse_args()

    if args.json_file:
        with open(args.json_file) as f:
            placeholders = json.load(f)
    elif args.at:
        titles = args.title or ["New Slide"] * len(args.at)
        subtitles = args.subtitle or [""] * len(args.at)
        if args.title and len(args.title) != len(args.at):
            print(f"ERROR: {len(args.at)} positions but {len(args.title)} titles",
                  file=sys.stderr)
            sys.exit(1)
        if args.subtitle and len(args.subtitle) != len(args.at):
            print(f"ERROR: {len(args.at)} positions but {len(args.subtitle)} subtitles",
                  file=sys.stderr)
            sys.exit(1)
        placeholders = [
            {"position": pos, "title": t, "subtitle": s}
            for pos, t, s in zip(args.at, titles, subtitles)
        ]
    else:
        print("ERROR: provide a JSON file or use --at/--title", file=sys.stderr)
        sys.exit(1)

    prs = Presentation(args.deck)
    original_count = len(prs.slides)
    total_after = original_count + len(placeholders)
    print(f"Opened {args.deck}: {original_count} slides")

    # Validate positions
    for ph in placeholders:
        pos = ph["position"]
        if pos < 1 or pos > total_after:
            print(f"ERROR: position {pos} out of range (1..{total_after})", file=sys.stderr)
            sys.exit(1)

    # Insert from highest position to lowest so earlier inserts don't shift later targets.
    # Each placeholder is appended to the end, then immediately moved to its target position.
    for ph in sorted(placeholders, key=lambda x: x["position"], reverse=True):
        title = ph["title"]
        subtitle = ph.get("subtitle", "")
        position = ph["position"]

        add_placeholder_slide(prs, title, subtitle)
        last_idx = len(prs.slides) - 1
        move_slide(prs, last_idx, position - 1)
        print(f"  Inserted [PLACEHOLDER] {title} at position {position}")

    output_path = args.output or args.deck
    prs.save(output_path)
    print(f"Saved {output_path}: {len(prs.slides)} slides")


if __name__ == "__main__":
    main()

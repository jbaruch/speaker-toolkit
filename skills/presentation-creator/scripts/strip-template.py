#!/usr/bin/env python3
"""Strip demo slides from a PowerPoint template, keeping only layouts.

Usage:
    strip-template.py <template.pptx> <output.pptx>

Examples:
    strip-template.py ~/Templates/speaker-template.pptx clean-deck.pptx
"""

import sys
from pptx import Presentation

from _pptx_repair import NS_R, clean_viewprops


def strip_slides(prs):
    """Remove all slides from a presentation, keeping layouts intact.

    Returns the number of slides removed.
    """
    xml_slides = prs.slides._sldIdLst
    removed = 0
    for sldId in list(xml_slides):
        rId = sldId.get(f'{{{NS_R}}}id')
        prs.part.drop_rel(rId)
        xml_slides.remove(sldId)
        removed += 1
    clean_viewprops(prs)
    return removed


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <template.pptx> <output.pptx>", file=sys.stderr)
        sys.exit(1)

    template_path, output_path = sys.argv[1], sys.argv[2]

    tmpl = Presentation(template_path)
    removed = strip_slides(tmpl)
    tmpl.save(output_path)
    print(f"Stripped {removed} slides from template. Saved to {output_path}")


if __name__ == "__main__":
    main()

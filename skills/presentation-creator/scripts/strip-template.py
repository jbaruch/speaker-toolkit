#!/usr/bin/env python3
"""Strip demo slides from a PowerPoint template, keeping only layouts.

Usage:
    strip-template.py <template.pptx> <output.pptx>

Examples:
    strip-template.py ~/Templates/speaker-template.pptx clean-deck.pptx
"""

import sys
from pptx import Presentation

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <template.pptx> <output.pptx>", file=sys.stderr)
    sys.exit(1)

template_path, output_path = sys.argv[1], sys.argv[2]

tmpl = Presentation(template_path)
xml_slides = tmpl.slides._sldIdLst
removed = 0
for sldId in list(xml_slides):
    rId = sldId.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
    tmpl.part.drop_rel(rId)
    xml_slides.remove(sldId)
    removed += 1

tmpl.save(output_path)
print(f"Stripped {removed} slides from template. Saved to {output_path}")

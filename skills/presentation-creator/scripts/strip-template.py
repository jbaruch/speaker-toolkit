#!/usr/bin/env python3
"""Strip demo slides from a PowerPoint template, keeping only layouts.

Usage:
    strip-template.py <template.pptx> <output.pptx>

Examples:
    strip-template.py ~/Templates/speaker-template.pptx clean-deck.pptx
"""

import sys
from lxml import etree
from pptx import Presentation

NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'


def clean_viewprops(prs):
    """Remove stale slide references from viewProps.xml after deleting slides.

    PowerPoint stores last-viewed slide lists in viewProps.xml with their own
    relationship entries. If these aren't cleaned up after slide deletion,
    PowerPoint reports the file as corrupted on open.
    """
    for rel in prs.part.rels.values():
        if "viewProps" in rel.reltype:
            vp_part = rel.target_part
            vp_xml = etree.fromstring(vp_part.blob)
            for sld_lst in vp_xml.findall(f'.//{{{NS_P}}}sldLst'):
                sld_lst.getparent().remove(sld_lst)
            vp_part._blob = etree.tostring(vp_xml, xml_declaration=True,
                                           encoding='UTF-8', standalone=True)
            to_drop = [rId for rId, vp_rel in vp_part.rels.items()
                       if "slide" in vp_rel.reltype.lower()]
            for rId in to_drop:
                vp_part.rels.pop(rId)
            break


if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <template.pptx> <output.pptx>", file=sys.stderr)
    sys.exit(1)

template_path, output_path = sys.argv[1], sys.argv[2]

tmpl = Presentation(template_path)
xml_slides = tmpl.slides._sldIdLst
removed = 0
for sldId in list(xml_slides):
    rId = sldId.get(f'{{{NS_R}}}id')
    tmpl.part.drop_rel(rId)
    xml_slides.remove(sldId)
    removed += 1

clean_viewprops(tmpl)

tmpl.save(output_path)
print(f"Stripped {removed} slides from template. Saved to {output_path}")

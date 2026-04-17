"""Shared PPTX repair utilities used by multiple scripts."""

from lxml import etree

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
            # Remove all <p:sldLst> elements (inside outlineViewPr, slideViewPr, etc.)
            for sld_lst in vp_xml.findall(f'.//{{{NS_P}}}sldLst'):
                sld_lst.getparent().remove(sld_lst)
            vp_part._blob = etree.tostring(vp_xml, xml_declaration=True,
                                           encoding='UTF-8', standalone=True)
            # Remove slide relationships from viewProps rels
            to_drop = [rId for rId, vp_rel in vp_part.rels.items()
                       if "slide" in vp_rel.reltype.lower()]
            for rId in to_drop:
                vp_part.rels.pop(rId)
            break

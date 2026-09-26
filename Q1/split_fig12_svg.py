"""Split the supplied Figure 12 SVG into independent vector panels; no refit."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from lxml import etree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'figures/fig_12_marginal_effects_forest.svg'
SVG = 'http://www.w3.org/2000/svg'
NS = {'s': SVG}
# Bounds include every panel label, axis title and legend, plus whitespace.
PANELS = [('left', 'axes_1', (0, 0, 569, 496.281818)),
          ('right', 'axes_2', (565, 0, 507.444169, 496.281818))]


def without_defs(element):
    result = deepcopy(element)
    for node in result.findall('.//s:defs', NS):
        node.getparent().remove(node)
    return result


def main():
    original_bytes = SOURCE.read_bytes()
    source = ET.fromstring(original_bytes)
    audit = {'source': str(SOURCE.relative_to(ROOT)),
             'source_sha256': sha256(original_bytes).hexdigest(),
             'method': 'Extract original axes groups and shared vector definitions; crop page only.',
             'model_and_data_changed': False, 'panels': []}
    for side, axes_id, bounds in PANELS:
        x, y, width, height = bounds
        out = ET.Element(source.tag, dict(source.attrib), nsmap=source.nsmap)
        out.set('width', f'{width}pt')
        out.set('height', f'{height}pt')
        out.set('viewBox', f'{x} {y} {width} {height}')
        defs = ET.SubElement(out, f'{{{SVG}}}defs')
        for group in source.findall('.//s:defs', NS):
            for child in group:
                defs.append(deepcopy(child))
        ET.SubElement(out, f'{{{SVG}}}rect', x=str(x), y=str(y),
                      width=str(width), height=str(height), fill='white')
        original_axes = source.xpath('//*[@id=$value]', value=axes_id)[0]
        axes = without_defs(original_axes)
        out.append(axes)
        filename = ROOT / f'figures/fig_12_marginal_effects_forest_{side}.svg'
        ET.ElementTree(out).write(str(filename), encoding='utf-8', xml_declaration=True)
        loaded = ET.parse(str(filename)).getroot()
        saved_axes = loaded.xpath('//*[@id=$value]', value=axes_id)[0]
        assert ET.tostring(saved_axes, method='c14n') == ET.tostring(axes, method='c14n')
        assert not loaded.findall('.//s:image', NS), 'Raster content is forbidden'
        ids = loaded.xpath('//@id')
        assert len(ids) == len(set(ids)), 'Duplicate SVG IDs'
        import re
        refs = re.findall(r'(?:url\(#|href="#)([^)" ]+)', ET.tostring(loaded).decode())
        assert set(refs) <= set(ids), 'Unresolved SVG reference'
        audit['panels'].append({'file': str(filename.relative_to(ROOT)), 'viewBox': bounds,
                                'original_panel_preserved': True,
                                'editable_text_nodes': len(axes.findall('.//s:text', NS)),
                                'raster_images': 0, 'references_resolved': True})
    assert SOURCE.read_bytes() == original_bytes
    (ROOT / 'figure_audit/fig12_split.json').write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

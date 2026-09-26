"""Check delivered packages against the original and Word-updated QA copies."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import pypdfium2 as pdfium
import hashlib, json, re, posixpath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
QA = Path('/private/tmp/fpaper-v0925')
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W = '{' + NS['w'] + '}'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def document(path):
    with ZipFile(path) as z:
        return E.fromstring(z.read('word/document.xml'))

def fields(root):
    found, stack = [], []
    for i, e in enumerate(root.iter()):
        if e.tag == W + 'fldSimple':
            found.append((i, e.get(W + 'instr', ''), ''.join(e.xpath('.//w:t/text()', namespaces=NS))))
        elif e.tag == W + 'fldChar':
            kind = e.get(W + 'fldCharType')
            if kind == 'begin':
                stack.append({'i': i, 'code': '', 'value': '', 'sep': False})
            elif kind == 'separate' and stack:
                stack[-1]['sep'] = True
            elif kind == 'end' and stack:
                f = stack.pop()
                found.append((f['i'], f['code'], f['value']))
        elif stack and e.tag == W + 'instrText' and not stack[-1]['sep']:
            stack[-1]['code'] += e.text or ''
        elif stack and e.tag == W + 't' and stack[-1]['sep']:
            stack[-1]['value'] += e.text or ''
    return [(re.sub(r'\s+', ' ', c).strip(), v) for _, c, v in sorted(found)
            if re.match(r'\s*(SEQ|REF)\s', c)]

def package_check(path):
    with ZipFile(path) as z:
        names = set(z.namelist())
        assert len(names) == len(z.namelist())
        external = []
        for name in names:
            if not name.endswith('.rels'):
                continue
            rels = E.fromstring(z.read(name))
            assert len({x.get('Id') for x in rels}) == len(rels), name
            base = posixpath.dirname(posixpath.dirname(name))
            for rel in rels:
                if rel.get('TargetMode') == 'External':
                    external.append(rel.get('Target'))
                else:
                    target = rel.get('Target').split('#')[0]
                    target = target[1:] if target.startswith('/') else posixpath.normpath(posixpath.join(base, target))
                    assert target in names, (name, target)
        assert not external, external
    root = document(path)
    bookmarks = set(root.xpath('//w:bookmarkStart/@w:name', namespaces=NS))
    for code, value in fields(root):
        if code.startswith('REF '):
            assert code.split()[1] in bookmarks, code
        assert '错误' not in value and 'Error!' not in value, value
    return {'unique_relationship_ids': True, 'internal_targets_resolve': True,
            'external_relationships': 0, 'reference_bookmarks_resolve': True}

structure = json.loads((HERE/'结构核验.json').read_text())
for p, digest in structure['sources'].items():
    assert sha(Path(p)) == digest
for name, digest in structure['outputs'].items():
    assert sha(ROOT/name) == digest
source_body = next(Path(p) for p in structure['sources'] if '第五至八章' in p)
source_front = next(Path(p) for p in structure['sources'] if '_前文_raw' in p)
full = ROOT/'F题论文_前文与四问合并_v0.9.25.docx'
front = ROOT/'F题论文_前文重构_v0.9.25.docx'
original = document(source_body)
combined = document(full)
post = list(combined.find('w:body', NS))[structure['body_start_index']:-1]
canon = lambda x: E.tostring(x, method='c14n', exclusive=True)
old_math = [canon(x) for x in original.xpath('//m:oMath', namespaces=NS)]
new_math = [canon(x) for n in post for x in n.xpath('.//m:oMath', namespaces=NS)]
assert old_math == new_math
with ZipFile(source_body) as a, ZipFile(full) as b:
    media = [p for p in a.namelist() if p.startswith('word/media/')]
    assert all(a.read(p) == b.read(p) for p in media)

results = {}
for key, path, word_path, pdf_path, pages in [
    ('front', front, QA/'front_release.docx', QA/'front_release.pdf', 12),
    ('combined', full, QA/'full_ready.docx', QA/'full_ready.pdf', 63),
]:
    actual, updated = fields(document(path)), fields(document(word_path))
    assert actual == updated, [(i, x, y) for i, (x, y) in enumerate(zip(actual, updated)) if x != y]
    assert len(pdfium.PdfDocument(pdf_path)) == pages
    results[key] = {**package_check(path), 'sha256': sha(path),
                    'seq_ref_fields': len(actual), 'word_updated_fields_identical': True,
                    'native_word_pdf_pages': pages, 'native_word_pdf_sha256': sha(pdf_path),
                    'visual_review': ('all 12 pages checked' if key == 'front' else
                                      'all pages checked; final Q4 number-cell revision checked on pages 47–52')}

paragraphs = document(source_front).xpath('./w:body/w:p', namespaces=NS)
report = (HERE/'修订说明.md').read_text()
md = (HERE/'前文源稿.md').read_text()
quoted = []
for row in report.splitlines():
    if not row.startswith('| 原第'):
        continue
    cells = [x.strip() for x in row.strip('|').split('|')]
    idx = int(re.search(r'原第(\d+)段', cells[0])[1])
    raw = ''.join(paragraphs[idx].xpath('.//w:t/text()|.//m:t/text()', namespaces=NS))
    assert cells[1] in raw, (idx, cells[1], raw)
    assert cells[2] in md, cells[2]
    quoted.append(idx)

out = {'version': 'v0.9.25', 'source_files_unchanged': True,
       'posterior_math_objects_unchanged': len(old_math), 'original_media_unchanged': len(media),
       'original_quote_paragraphs_verified': quoted, 'files': results,
       'native_word': 'Microsoft Word 16.89.1',
       'opening_prompts': 'Final QA editions opened without repair or link-update prompts.',
       'field_cache_method': 'Final SEQ/REF instructions and cached values exactly match Word-updated QA copies; original OMML is retained.',
       'rendering_note': 'Word-native pagination is authoritative (12/63 pages); LibreOffice auxiliary pagination differs.',
       'inherited_image_issues': ['图7-1原图缺少节点文字', '图8-1原图内部问次误标为第二问'],
       'numerical_models_not_recomputed': True}
(HERE/'最终核验.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(json.dumps(out, ensure_ascii=False, indent=2))

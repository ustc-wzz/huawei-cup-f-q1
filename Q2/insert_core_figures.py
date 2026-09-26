"""Insert three result figures into the simplified Q2 paper, preserving other XML."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from copy import deepcopy
import hashlib
import json
from io import BytesIO
from lxml import etree as E
from docx import Document
from docx.shared import Cm

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'F题论文初稿_问题二精简_20260926.docx'
OUT=ROOT/'F题论文初稿_问题二图文优化_20260926.docx'
FIG=ROOT/'output_q2_paper'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'm':'http://schemas.openxmlformats.org/officeDocument/2006/math',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
def tag(s):
    prefix,name=s.split(':'); return '{'+NS[prefix]+'}'+name
def text(n):return ''.join(n.xpath('.//w:t/text() | .//m:t/text()',namespaces=NS))
def canonical(n):return E.tostring(n,method='c14n',exclusive=True)
def el(s,**attrs):
    n=E.Element(tag(s))
    for k,v in attrs.items():n.set(tag('w:'+k),str(v))
    return n
with ZipFile(SRC) as z:
    infos=z.infolist(); parts={i.filename:z.read(i.filename) for i in infos}
source_hash=hashlib.sha256(SRC.read_bytes()).hexdigest()
root=E.fromstring(parts['word/document.xml']); body=root.find('w:body',NS)
before=list(body)
q2=next(i for i,n in enumerate(before) if text(n)=='问题二模型建立与求解')
q3=next(i for i,n in enumerate(before) if text(n)=='问题三模型建立与求解')
app=next(i for i,n in enumerate(before) if text(n).startswith('附录二'))
math_before=[canonical(n) for n in root.xpath('.//m:oMath',namespaces=NS)]
rels=E.fromstring(parts['word/_rels/document.xml.rels'])
rel_ns='http://schemas.openxmlformats.org/package/2006/relationships'
ids={n.get('Id') for n in rels}
doc_ids=[int(n.get('id')) for n in root.xpath('.//wp:docPr',namespaces=NS)]
next_id=max(doc_ids+[0])+1
template=before[q2+1]
captions=[]

def para(value, caption=False, heading=False):
    p=el('w:p'); prop=deepcopy(template.find('w:pPr',NS))
    if prop is None:prop=el('w:pPr')
    for n in list(prop):
        if E.QName(n).localname in ['keepNext','pageBreakBefore','ind','spacing','jc','numPr']:
            prop.remove(n)
    prop.append(el('w:ind',firstLine=0,firstLineChars=0,left=0,right=0))
    prop.append(el('w:spacing',before=60,after=80,line=260,lineRule='auto'))
    prop.append(el('w:widowControl'))
    if caption:prop.append(el('w:keepLines'))
    if heading:prop.append(el('w:keepNext'))
    p.append(prop)
    r=el('w:r'); rp=el('w:rPr')
    rp.append(el('w:rFonts',ascii='Times New Roman',hAnsi='Times New Roman',eastAsia='宋体'))
    rp.append(el('w:sz',val=20 if caption else 24))
    if heading:rp.append(el('w:b'))
    r.append(rp); t=el('w:t'); t.text=value; r.append(t); p.append(r)
    return p

def picture(file, title):
    global next_id
    temp=Document(); p=temp.add_paragraph()
    p.add_run().add_picture(str(file),width=Cm(15.9))
    imagep=E.fromstring(E.tostring(p._p))
    prop=el('w:pPr'); prop.append(el('w:jc',val='center'))
    prop.append(el('w:ind',firstLine=0,firstLineChars=0,left=0,right=0)); prop.append(el('w:spacing',before=100,after=0))
    prop.append(el('w:keepNext')); imagep.insert(0,prop)
    rid=f'rIdQ2PaperFigure{next_id}'
    assert rid not in ids; ids.add(rid)
    part=f'word/media/q2_core_{next_id}.png'
    rel=E.SubElement(rels,'{'+rel_ns+'}Relationship')
    rel.set('Id',rid); rel.set('Type',NS['r']+'/image'); rel.set('Target',part[5:])
    parts[part]=file.read_bytes()
    for blip in imagep.xpath('.//a:blip',namespaces=NS):blip.set(tag('r:embed'),rid)
    for pr in imagep.xpath('.//wp:docPr',namespaces=NS):
        pr.set('id',str(next_id)); pr.set('name',title); pr.set('descr',title)
    next_id+=1
    return imagep

def figure(file,title,legend):
    captions.append(title+'。'+legend)
    return [picture(file,title),para(title+'。'+legend,caption=True)]

def insert_after(anchor,nodes):
    idx=body.index(anchor)+1
    for off,n in enumerate(nodes):body.insert(idx+off,n)

cap=next(n for n in body if text(n).startswith('表6-2'))
table=body[body.index(cap)+1]
assert table.tag==tag('w:tbl')
body.remove(table); body.remove(cap)
for n in list(body)[q2:]:
    for t in n.xpath('.//w:t',namespaces=NS):
        if t.text:t.text=t.text.replace('表6-3','表6-2')
anchor=next(n for n in body if text(n).startswith('估计得到') and '576条配方记录' in text(n))
insert_after(anchor,figure(FIG/'01_correction_effectiveness.png',
    '图6-1  质量与配比修正的预测改善及跨尺度边界',
    'a：质量以B7的450条半合成记录按45个参数量—数据量组合分组五折验证；配比以576条记录按完整配方分组五折验证。各自对照为无质量项与无配比项，后者重新估计来源幅度。柱高为汇总留出RMSE，无误差带；降低幅度分别为70.0%和60.1%。b：同一配比修正模型的配方分组与完整尺度留出对照，纵轴为对数轴；配方结果属于事后迁移诊断。'))
anchor=next(n for n in body if text(n).startswith('例如在7B参数'))
insert_after(anchor,figure(FIG/'02_quality_parameter_substitution.png',
    '图6-2  不同质量刻度下的等损失参数替代',
    '固定B1来源、7B参数、140B Token及参考配比，比较质量提高Δu与单独扩大参数量的等损失方案。三条曲线对应s_Q=0.5、1、2，是刻度情景而非置信区间；Δu=0.1时分别为1.972、1.386、1.174倍。固定数据量而不固定算力；正质量增量属于参照点之外的条件外推，图示范围均满足有限替代条件。'))
anchor=next(n for n in body if text(n).startswith('在7B参数、140B Token、u=0'))
insert_after(anchor,figure(FIG/'03_mixture_loss_response.png',
    '图6-3  配比调整对统一模型最终损失的影响',
    '固定B1来源、7B参数、140B Token和额外质量u=0。a：以pile_cc为共同转出域，按转移1个百分点时的损失差排序，从全部16个转入域中选最小、下中位、最大三个方向；负值表示改善。b：训练平均、均匀和第一问候选配比的最终损失及相对平均配比的变化，横轴截取为局部范围。所有值均为两来源模型连接后的条件预测，候选配比尚未经过新训练实验验证。'))
appendix=[para('五 规模验证与完整领域转移结果',heading=True)]
appendix+=figure(ROOT/'output_q2_shared/figures/01_scale_and_sources.png',
    '图附2-1  规模基线拟合与跨来源校准验证',
    '左图为B1训练轨迹及规模项拟合；右图为B4、B5来源内部留一预测。该图解释基线估计与来源校准，正文图6-1另行检验质量与配比修正的增量价值。')
appendix+=figure(ROOT/'output_q2_shared/figures/04_domain_transfer.png',
    '图附2-2  完整领域份额转移矩阵',
    '以训练平均配比为参照，每次转移1个百分点。颜色沿用第一问对数线性模型的预测损失变化；灰色表示不可行方向或对角线。该量与正文图6-3的统一模型最终损失不同，保留此图供检查所有领域方向。')
for n in appendix:body.insert(len(body)-1,n)
parts['word/document.xml']=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
parts['word/_rels/document.xml.rels']=E.tostring(rels,xml_declaration=True,encoding='UTF-8',standalone=True)
types=E.fromstring(parts['[Content_Types].xml'])
if not any(n.get('Extension')=='png' for n in types):
    n=E.SubElement(types,'{http://schemas.openxmlformats.org/package/2006/content-types}Default')
    n.set('Extension','png'); n.set('ContentType','image/png')
    parts['[Content_Types].xml']=E.tostring(types,xml_declaration=True,encoding='UTF-8',standalone=True)
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
    for name,data in parts.items():z.writestr(name,data)
assert math_before==[canonical(n) for n in root.xpath('.//m:oMath',namespaces=NS)]
after=list(body)
new_q3=next(i for i,n in enumerate(after) if text(n)=='问题三模型建立与求解')
new_app=next(i for i,n in enumerate(after) if text(n).startswith('附录二'))
assert [canonical(n) for n in before[:q2]]==[canonical(n) for n in after[:q2]]
assert [canonical(n) for n in before[q3:app]]==[canonical(n) for n in after[new_q3:new_app]]
assert canonical(before[-1])==canonical(after[-1])
with ZipFile(SRC) as z:
    changed=[n for n in z.namelist() if z.read(n)!=parts[n]]
assert set(changed)<={'word/document.xml','word/_rels/document.xml.rels','[Content_Types].xml'}
assert hashlib.sha256(SRC.read_bytes()).hexdigest()==source_hash
report={'version':'v0.9.11','source':SRC.name,'source_sha256':source_hash,
        'output':OUT.name,'output_sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),
        'changed_original_parts':changed,'new_images':5,'main_figures':3,
        'appendix_figures':2,'all_math_preserved':True,'other_chapters_preserved':True,
        'source_unchanged':True,'render_qa':'pending'}
(FIG/'document_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(FIG/'figure_captions.md').write_text('\n\n'.join(captions))
(ROOT/'Q2/论文第二问图文正文.md').write_text('\n\n'.join(text(n) for n in after[q2:new_q3] if text(n)))
print(json.dumps(report,ensure_ascii=False,indent=2))

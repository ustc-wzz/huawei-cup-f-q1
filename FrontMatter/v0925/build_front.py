"""Rebuild the five front chapters; retain the supplied four-question body.

Run with bundled Python. The original attachments are never changed. Pandoc is
used solely to convert the authored Markdown/LaTeX into native Office Math.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from copy import deepcopy
from lxml import etree as E
import hashlib, json, re, subprocess, shutil, posixpath

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
TMP = Path('/private/tmp/fpaper-v0925')
SOURCE_DIR = Path('/Users/luochen/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_qw2nxx7u18d822_43f4/temp/drag')
FRONT = SOURCE_DIR/'F题论文初稿_前文_raw(1).docx'
BODY = SOURCE_DIR/'F题论文_问题一至四_第五至八章_模板统一合并版_免弹窗版.docx'
OUT = ROOT/'F题论文_前文重构_v0.9.25.docx'
FULL = ROOT/'F题论文_前文与四问合并_v0.9.25.docx'
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm':'http://schemas.openxmlformats.org/officeDocument/2006/math',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
REL='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
def q(s):
    a,b=s.split(':');return '{'+NS[a]+'}'+b
def el(s,**attrs):
    n=E.Element(q(s))
    for k,v in attrs.items():n.set(q('w:'+k),str(v))
    return n
def xml(n):return E.tostring(n,encoding='UTF-8',xml_declaration=True,standalone=True)
def canon(n):return E.tostring(n,method='c14n',exclusive=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def text(n):return ''.join(n.xpath('.//w:t/text()|.//m:t/text()',namespaces=NS))
def parts(p):
    with ZipFile(p) as z:return {n:z.read(n) for n in z.namelist()}
def save(p,items):
    with ZipFile(p,'w',ZIP_DEFLATED) as z:
        for n,b in items.items():z.writestr(n,b)
def prop(p):
    pr=p.find('w:pPr',NS)
    if pr is None:pr=el('w:pPr');p.insert(0,pr)
    return pr
def setprop(pr,s,**attrs):
    for n in pr.findall(s,NS):pr.remove(n)
    n=el(s,**attrs);pr.append(n);return n
def run(s):
    r=el('w:r');t=el('w:t');t.text=s;t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');r.append(t);return r
def field(code,value,hidden=False):
    f=el('w:fldSimple',instr=' '+code+' ');r=run(str(value))
    if hidden:
        rp=el('w:rPr');rp.append(el('w:vanish'));r.insert(0,rp)
    f.append(r);return f
def hidden_chapter(p,n):p.append(field(f'SEQ PaperChapter \\r {n} \\h','',True))
def stats(root):
    return {k:len(root.xpath(v,namespaces=NS)) for k,v in {
        'body_paragraphs':'./w:body/w:p','tables':'.//w:tbl','math':'.//m:oMath',
        'drawings':'.//w:drawing','paragraphs':'.//w:p'}.items()}

TMP.mkdir(exist_ok=True)
source_hash={str(p):sha(p) for p in [FRONT,BODY,Path('/Users/luochen/Downloads/完整版第二版_B/main.pdf')]}
bp=parts(BODY);fp=parts(FRONT)
br=E.fromstring(bp['word/document.xml']);bb=br.find('w:body',NS)
fr=E.fromstring(fp['word/document.xml']);fb=fr.find('w:body',NS)
original=[deepcopy(n) for n in list(bb)[:-1]]
assert len(original)==545 and stats(br)['math']==459
for name in ['AGENTS.md','PROJECT_MEMORY.md','CHANGELOG.md']:
    p=TMP/'baseline'/name
    if not p.exists():shutil.copyfile(ROOT/name,p)

# Template contract: exact page geometry/style authority, new slots and allowed edits.
(WORK/'artifact.md').write_text('''# 文稿生成约定

版面以用户上传的四问合并DOCX为准，前文原稿提供封面及摘要空位。
页面为A4（11906×16838 twip），正文四边距1417 twip，页眉850、页脚992 twip。
原模板正文12 pt宋体、两端对齐、首行2字；一级标题14 pt黑体居中，二级标题12 pt加粗。
前文使用同一字族及标题层级；三线表10.5 pt、自然行高、重复表头，数学为原生OMML。
独立稿从第一章开始；完整稿保留原稿封面和摘要空位（前22个body对象）。
五章前文替换原前文全部研究内容；四问后文只允许编号域、编号缓存、交叉引用及编号格排版变化。
后文459个OMML对象及全部47份媒体原字节保留，正文数值与字符仅豁免编号/引用。
章列表连续1—9；每章首个公式、图、表显式重置序列，避免渲染器跨章串号。
关系和书签保持有效；不添加外部资源关系、自动更新弹窗或未完成的编辑说明。
参考初次渲染中文缺字，最终以本机Word原生PDF为版式依据；fontconfig别名仅用于辅助渲染。
''',encoding='utf-8')

# Markdown is the human-editable source. Its sole display equation gets a Word field number below.
md=(WORK/'前文源稿.md').read_text()
tmpmd=TMP/'front.md';tmpmd.write_text(re.sub(r'\\tag\{1-1\}','',md).replace('assets/总体技术路线.png',str(WORK/'assets/总体技术路线.png')))
subprocess.run(['/Users/luochen/miniconda3/bin/pandoc',str(tmpmd),'-f','markdown+tex_math_dollars-implicit_figures','--reference-doc',str(BODY),'-o',str(TMP/'front_native.docx')],check=True)
pp=parts(TMP/'front_native.docx');pr=E.fromstring(pp['word/document.xml'])
front_nodes=[deepcopy(n) for n in list(pr.find('w:body',NS))[:-1]]
styles=E.fromstring(bp['word/styles.xml'])

# Local paragraph roles inherit the uploaded template; existing body styles do not change.
for id,base,name,size in [('FrontBody','a4','前文正文',24),('FrontTable','a9','前文表格',21),('FrontCaption','a8','前文题注',21)]:
    st=el('w:style',type='paragraph',customStyle=1,styleId=id)
    st.append(el('w:name',val=name));st.append(el('w:basedOn',val=base))
    sp=el('w:pPr');st.append(sp)
    if id=='FrontBody':
        sp.append(el('w:spacing',before=0,after=0,line=360,lineRule='exact'))
        sp.append(el('w:ind',firstLine=480,firstLineChars=200));sp.append(el('w:jc',val='both'))
    else:
        sp.append(el('w:ind',left=0,right=0,firstLine=0,firstLineChars=0))
        sp.append(el('w:spacing',before=40,after=40,line=260,lineRule='auto'))
    sp.append(el('w:widowControl'));sp.append(el('w:snapToGrid',val=0))
    rp=el('w:rPr');rp.append(el('w:rFonts',ascii='Times New Roman',hAnsi='Times New Roman',eastAsia='宋体'))
    rp.append(el('w:sz',val=size));rp.append(el('w:szCs',val=size));rp.append(el('w:color',val='000000'));st.append(rp);styles.append(st)

front_rels=E.fromstring(pp['word/_rels/document.xml.rels'])
rels=E.fromstring(bp['word/_rels/document.xml.rels'])
relmap={}
used_front_rids={v for n in front_nodes for e in n.iter() for k,v in e.attrib.items() if k.startswith('{'+NS['r']+'}')}
for rr in front_rels:
    if rr.get('Type','').endswith('/image') and rr.get('Id') in used_front_rids:
        old=rr.get('Id');new='rIdFrontRoute';target='media/front_route.png';relmap[old]=new
        E.SubElement(rels,'{'+REL+'}Relationship',Id=new,Type=rr.get('Type'),Target=target)
        bp['word/'+target]=(WORK/'assets/总体技术路线.png').read_bytes()

chapter=0;tables=0
for n in front_nodes:
    # Namespace-safe relationship and drawing identifiers.
    for ch in n.iter():
        for k,v in list(ch.attrib.items()):
            if k.startswith('{'+NS['r']+'}') and v in relmap:ch.set(k,relmap[v])
    for dp in n.xpath('.//wp:docPr',namespaces=NS):dp.set('id','10001');dp.set('name','总体技术路线')
    if n.tag==q('w:p'):
        ppr=prop(n);sty=ppr.find('w:pStyle',NS);sid=sty.get(q('w:val')) if sty is not None else ''
        if sid in ['Heading1','Heading2','Heading3','1','2','3']:
            lv=int(sid[-1]);setprop(ppr,'w:pStyle',val=str(lv));num=setprop(ppr,'w:numPr');num.append(el('w:ilvl',val=lv-1));num.append(el('w:numId',val=21))
            setprop(ppr,'w:keepNext');setprop(ppr,'w:keepLines')
            if lv==1:
                chapter+=1;hidden_chapter(n,chapter)
                if chapter in [2,3,4,5]:setprop(ppr,'w:pageBreakBefore')
            continue
        setprop(ppr,'w:pStyle',val='FrontBody')
        t=text(n)
        if n.xpath('.//w:drawing',namespaces=NS):
            setprop(ppr,'w:pStyle',val='FrontCaption');setprop(ppr,'w:jc',val='center');setprop(ppr,'w:keepNext')
            setprop(ppr,'w:spacing',before=0,after=0,line=240,lineRule='auto')
            ext=n.xpath('.//wp:extent',namespaces=NS)[0];ratio=5760000/int(ext.get('cx'))
            for ee in n.xpath('.//wp:extent|.//a:xfrm/a:ext',namespaces=NS):
                ee.set('cx',str(round(int(ee.get('cx'))*ratio)));ee.set('cy',str(round(int(ee.get('cy'))*ratio)))
        elif re.match(r'^[图表]\d-\d',t):
            setprop(ppr,'w:pStyle',val='FrontCaption');setprop(ppr,'w:jc',val='center')
            if t.startswith('表'):setprop(ppr,'w:keepNext')
            for child in list(n):
                if child.tag!=q('w:pPr'):n.remove(child)
            m=re.match(r'^([图表])(\d)-(\d+)\s*(.*)',t);kind,ch,num,rest=m.groups()
            n.append(run(kind));n.append(field('SEQ PaperChapter \\c',ch));n.append(run('-'))
            code='SEQ Paper'+kind+' \\* ARABIC'+(' \\r 1' if num=='1' else '')
            n.append(field(code,num));n.append(run(' '+rest))
        elif n.find('m:oMathPara',NS) is not None:
            setprop(ppr,'w:pStyle',val='FrontCaption');setprop(ppr,'w:jc',val='left')
            tabs=setprop(ppr,'w:tabs');tabs.append(el('w:tab',val='center',pos=4536));tabs.append(el('w:tab',val='right',pos=9072))
            om=n.find('m:oMathPara',NS);math=om.find('m:oMath',NS);om.remove(math);n.remove(om);n.append(run('\t'));n.append(math)
            n.append(run('\t('));n.append(field('SEQ PaperChapter \\c',chapter));n.append(run('-'))
            n.append(field('SEQ PaperEquation \\* ARABIC \\r 1',1));n.append(run(')'))
        else:
            # Force all normal prose onto the template's first-line and font system.
            for rp in n.findall('w:r/w:rPr',NS):
                for x in rp.findall('w:rFonts',NS):rp.remove(x)
    elif n.tag==q('w:tbl'):
        tables+=1
        tp=n.find('w:tblPr',NS)
        if tp is None:tp=el('w:tblPr');n.insert(0,tp)
        for x in list(tp):
            if x.tag in [q('w:tblStyle'),q('w:tblBorders'),q('w:tblW'),q('w:tblLayout')]:tp.remove(x)
        tp.append(el('w:tblW',w=9072,type='dxa'));tp.append(el('w:tblLayout',type='fixed'))
        bd=el('w:tblBorders')
        for edge in ['top','bottom','left','right','insideH','insideV']:
            bd.append(el('w:'+edge,val='single' if edge in ['top','bottom'] else 'nil',sz=8,color='000000'))
        tp.append(bd)
        widths=([2250,3750,1900,1172] if tables<=3 else [1300,2400,5372] if tables==4 else [2300,900,5872])
        grid=n.find('w:tblGrid',NS)
        for c in list(grid):grid.remove(c)
        for width in widths:grid.append(el('w:gridCol',w=width))
        rows=n.findall('w:tr',NS)
        for ri,row in enumerate(rows):
            trp=row.find('w:trPr',NS)
            if trp is None:trp=el('w:trPr');row.insert(0,trp)
            setprop(trp,'w:cantSplit')
            if ri==0:setprop(trp,'w:tblHeader')
            for ci,cell in enumerate(row.findall('w:tc',NS)):
                cp=cell.find('w:tcPr',NS)
                if cp is None:cp=el('w:tcPr');cell.insert(0,cp)
                setprop(cp,'w:tcW',w=widths[ci],type='dxa');setprop(cp,'w:vAlign',val='center')
                mar=setprop(cp,'w:tcMar')
                for edge,val in [('top',60),('bottom',60),('left',65),('right',65)]:mar.append(el('w:'+edge,w=val,type='dxa'))
                if ri==0:
                    cb=setprop(cp,'w:tcBorders');cb.append(el('w:bottom',val='single',sz=5,color='000000'))
                for p in cell.findall('w:p',NS):
                    pp0=prop(p)
                    for x in list(pp0):
                        if x.tag!=q('w:pStyle'):pp0.remove(x)
                    setprop(pp0,'w:pStyle',val='FrontTable');setprop(pp0,'w:jc',val='left' if ci in [0,1,2] else 'center')
                    for rr in p.findall('w:r',NS):
                        rpr=rr.find('w:rPr',NS)
                        if rpr is not None:rr.remove(rpr)
                        if ri==0:rp0=el('w:rPr');rp0.append(el('w:b'));rr.insert(0,rp0)

# Keep figure alone with its caption if it cannot fit; don't bind surrounding prose.
assert chapter==5 and tables==5

# Word validates property order more strictly than the PDF fallback renderer.
# Normalize only the newly authored nodes and styles; keep source body XML intact.
property_orders = {
    'pPr': 'pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange',
    'rPr': 'rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange',
    'tblPr': 'tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing tblInd tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription tblPrChange',
    'trPr': 'cnfStyle divId gridBefore gridAfter wBefore wAfter cantSplit trHeight tblHeader tblCellSpacing jc hidden ins del trPrChange',
    'tcPr': 'cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark headers cellIns cellDel cellMerge tcPrChange',
}
def order_properties(root):
    for node in root.iter():
        if E.QName(node).namespace != NS['w']:continue
        order=property_orders.get(E.QName(node).localname)
        if order:
            ranks={name:i for i,name in enumerate(order.split())}
            node[:]=sorted(node,key=lambda e:ranks.get(E.QName(e).localname,999))
for node in front_nodes:order_properties(node)
for st in styles:
    if st.get(q('w:styleId'),'').startswith('Front'):order_properties(st)

# Update only reference tokens in prose/captions, never OMML values.
changes=[]
def rewrite_nodes(p,pattern,fn):
    nodes=p.xpath('.//w:t',namespaces=NS);s=''.join(t.text or '' for t in nodes)
    spans=[];pos=0
    for n in nodes:spans.append((pos,pos+len(n.text or ''),n));pos+=len(n.text or '')
    for m in reversed(list(re.finditer(pattern,s))):
        repl=fn(m)
        if repl==m.group():continue
        changes.append({'before':m.group(),'after':repl,'context':s[:160]})
        a,b=m.span()
        assert len(repl)==len(m.group())
        for offset,(oldchar,newchar) in enumerate(zip(m.group(),repl)):
            if oldchar==newchar:continue
            at=a+offset
            for st,en,node in spans:
                if st<=at<en:
                    v=node.text or '';ix=at-st;node.text=v[:ix]+newchar+v[ix+1:];break

post=[deepcopy(n) for n in original]
ch=5;seen={};reset_counts={}
for n in post:
    if n.tag==q('w:p'):
        sid=n.xpath('./w:pPr/w:pStyle/@w:val',namespaces=NS)
        if sid==['1']:ch+=1;seen={};reset_counts[ch]={}
    for p in ([n] if n.tag==q('w:p') else n.xpath('.//w:p',namespaces=NS)):
        rewrite_nodes(p,r'(?:(?:图|表)\s*[5-8][-－]\d+|式[（(][5-8][-－]\d+[）)])',lambda m:re.sub(r'[5-8](?=[-－])',lambda a:str(int(a.group())+1),m.group()))
        rewrite_nodes(p,r'式[（(]1-(?:6|8|10)[）)]',lambda m:m.group().replace('1-','8-'))
        # Formula/field result paragraphs may have only a bare number.
        s=''.join(p.xpath('.//w:t/text()',namespaces=NS)).strip()
        if re.fullmatch(r'[（(]?[5-8]-\d+[）)]?',s):
            rewrite_nodes(p,r'^[（(]?[5-8]-\d+[）)]?$',lambda m:re.sub(r'[5-8](?=-)',lambda a:str(int(a.group())+1),m.group()))
    # Explicitly reset each sequence at each chapter's first occurrence. Both field forms are supported.
    for node in n.iter():
        is_simple=node.tag==q('w:fldSimple')
        if not is_simple and node.tag!=q('w:instrText'):continue
        code=node.get(q('w:instr')) if is_simple else (node.text or '')
        if 'SEQ PaperChapter' in code and '\\r ' in code:
            new=re.sub(r'\\r\s+[5-8]',r'\\r '+str(ch),code)
        elif 'SEQ PaperChapter' in code:
            new=code
        else:
            mt=re.search(r'SEQ\s+(PaperEquation|Paper图|Paper表)\b',code)
            if not mt:continue
            name=mt.group(1);new=re.sub(r'\s+\\s\s+1','',code)
            new=re.sub(r'\s+\\r\s+\d+','',new)
            if name not in seen:new=new.rstrip()+' \\r 1 ';seen[name]=True;reset_counts[ch][name]=1
        if is_simple:
            node.set(q('w:instr'),new)
            if 'SEQ PaperChapter' in new:
                for t in node.xpath('.//w:t',namespaces=NS):
                    if t.text and t.text.strip().isdigit():t.text=str(ch)
        else:node.text=new

# Caption SEQ names were split over multiple instrText nodes in the original.
# Normalize complete complex-field instructions and their cached chapter values.
def complex_fields(root):
    stack=[]
    for e in root.iter():
        if e.tag==q('w:fldChar'):
            typ=e.get(q('w:fldCharType'))
            if typ=='begin':stack.append({'codes':[],'results':[],'sep':False})
            elif typ=='separate' and stack:stack[-1]['sep']=True
            elif typ=='end' and stack:yield stack.pop()
        elif stack and e.tag==q('w:instrText') and not stack[-1]['sep']:stack[-1]['codes'].append(e)
        elif stack and e.tag==q('w:t') and stack[-1]['sep']:stack[-1]['results'].append(e)

ch=5;seq={};complex_reset={}
for n in post:
    if n.tag==q('w:p') and n.xpath('./w:pPr/w:pStyle/@w:val',namespaces=NS)==['1']:ch+=1;seq={}
    # All fields ordered by XML document position, including simple ones.
    fs=list(complex_fields(n))
    fmap={f['codes'][0]:f for f in fs if f['codes']}
    for e in n.iter():
        if e.tag==q('w:fldSimple'):
            code=e.get(q('w:instr'));res=e.xpath('.//w:t',namespaces=NS);codes=None
        elif e in fmap:
            f=fmap[e];code=''.join(x.text or '' for x in f['codes']);res=f['results'];codes=f['codes']
        else:continue
        mt=re.search(r'SEQ\s+(PaperChapter|PaperEquation|Paper图|Paper表)',code)
        if mt:
            name=mt.group(1)
            if name=='PaperChapter':
                value='' if '\\h' in code else ch
                if '\\r' in code:code=re.sub(r'\\r\s+\d+',r'\\r '+str(ch),code)
            else:
                seq[name]=seq.get(name,0)+1;value=seq[name]
                code=re.sub(r'\s+\\[rs]\s+\d+','',code).strip()
                if value==1:code+=' \\r 1'
                code=' '+code+' '
            if res:
                res[0].text=str(value)
                for x in res[1:]:x.text=''
        elif 'REF ' in code:
            ref=re.search(r'REF\s+(\S+)',code)
            name=ref.group(1) if ref else ''
            match=re.search(r'PaperEq_([5-8])_(\d+)',name)
            q4=re.search(r'Q4Eq_(\d+)',name)
            value=f'{int(match[1])+1}-{match[2]}' if match else f'9-{q4[1]}' if q4 else None
            if value and res:
                res[0].text=value
                for x in res[1:]:x.text=''
        if codes:
            codes[0].text=code
            for x in codes[1:]:x.text=''
        elif e.tag==q('w:fldSimple'):e.set(q('w:instr'),code)

# Retain source math objects verbatim (inclusive ancestor namespaces can differ).
# Double-digit Q4 equation numbers need the full narrow number cell. This changes
# only number-cell padding/wrapping, not the equation or the table's column widths.
number_cell_layout=[]
for n in post:
    for mark in n.xpath('.//w:bookmarkStart[starts-with(@w:name,"Q4Eq_")]',namespaces=NS):
        tc=mark.getparent()
        while tc is not None and tc.tag!=q('w:tc'):tc=tc.getparent()
        if tc is not None:
            cp=tc.find('w:tcPr',NS)
            setprop(cp,'w:noWrap')
            mar=setprop(cp,'w:tcMar')
            for side in ['left','right']:mar.append(el('w:'+side,w=0,type='dxa'))
            order_properties(cp)
            for t in tc.xpath('.//w:t',namespaces=NS):
                if t.text in ['（','）']:t.text={'（':'(', '）':')'}[t.text]
            for rr in tc.xpath('.//w:r',namespaces=NS):
                rp=rr.find('w:rPr',NS)
                if rp is None:rp=el('w:rPr');rr.insert(0,rp)
                setprop(rp,'w:rFonts',ascii='Times New Roman',hAnsi='Times New Roman',eastAsia='宋体')
                setprop(rp,'w:sz',val=21);setprop(rp,'w:szCs',val=21)
                order_properties(rp)
            number_cell_layout.append(mark.get(q('w:name')))
math_old=[canon(x) for n in original for x in n.xpath('.//m:oMath',namespaces=NS)]
math_new=[canon(x) for n in post for x in n.xpath('.//m:oMath',namespaces=NS)]
assert math_old==math_new,'Mathematical structure changed'
for i,(a,b) in enumerate(zip(original,post)):
    # All differences must be contained in field definitions/results or recognized number tokens.
    aa=deepcopy(a);zz=deepcopy(b)
    def clean(n):
        for f in list(n.xpath('.//w:fldSimple',namespaces=NS)):f.getparent().remove(f)
        for f in list(complex_fields(n)):
            for t in f['codes']+f['results']:t.text=''
        for p in ([n] if n.tag==q('w:p') else n.xpath('.//w:p',namespaces=NS)):
            for t in p.xpath('.//w:t',namespaces=NS):
                if t.text:t.text=re.sub(r'(?<=[图表])[5-9](?=-)','§',t.text)
        # Combine visible text to permit source run-split numbering updates.
        s=''.join(n.xpath('.//w:t/text()',namespaces=NS))
        s=re.sub(r'(?<!\d)[1-9]-(\d+)',r'§-\1',s)
        if n.xpath('.//w:bookmarkStart[starts-with(@w:name,"Q4Eq_")]',namespaces=NS):
            s=s.replace('（-）','(-)')
        return s
    assert clean(aa)==clean(zz),(i,clean(aa),clean(zz))

num=E.fromstring(bp['word/numbering.xml'])
num21=num.xpath('//w:num[@w:numId="21"]',namespaces=NS)[0]
for so in num21.xpath('./w:lvlOverride[@w:ilvl="0"]/w:startOverride',namespaces=NS):so.set(q('w:val'),'1')
bp['word/styles.xml']=xml(styles);bp['word/numbering.xml']=xml(num);bp['word/_rels/document.xml.rels']=xml(rels)

# Cover parts already exist in the body template with the same identifiers.
cover=[deepcopy(n) for n in list(fb)[:22]]
fr_rels={r.get('Id'):r for r in E.fromstring(fp['word/_rels/document.xml.rels'])}
cts=E.fromstring(bp['[Content_Types].xml']);fcts=E.fromstring(fp['[Content_Types].xml'])
ctmap={x.get('PartName'):x.get('ContentType') for x in fcts if x.get('PartName')}
imported={};coverrids={}
def import_cover_part(path):
    if path in imported:return imported[path]
    dest=posixpath.join(posixpath.dirname(path),'frontcover_'+posixpath.basename(path));imported[path]=dest
    bp[dest]=fp[path]
    if '/'+path in ctmap:E.SubElement(cts,'{'+CT+'}Override',PartName='/'+dest,ContentType=ctmap['/'+path])
    relpath=posixpath.join(posixpath.dirname(path),'_rels',posixpath.basename(path)+'.rels')
    if relpath in fp:
        xr=E.fromstring(fp[relpath])
        for rr in xr:
            if rr.get('TargetMode')=='External':continue
            child=posixpath.normpath(posixpath.join(posixpath.dirname(path),rr.get('Target')))
            new=import_cover_part(child);rr.set('Target',posixpath.relpath(new,posixpath.dirname(dest)))
        newrel=posixpath.join(posixpath.dirname(dest),'_rels',posixpath.basename(dest)+'.rels');bp[newrel]=xml(xr)
    return dest
for n in cover:
    for e in n.iter():
        for key,rid in e.attrib.items():
            if key.startswith('{'+NS['r']+'}'):
                if rid not in coverrids:
                    rr=fr_rels[rid];newrid='rIdFrontCover'+rid;coverrids[rid]=newrid
                    target=import_cover_part('word/'+rr.get('Target'))
                    E.SubElement(rels,'{'+REL+'}Relationship',Id=newrid,Type=rr.get('Type'),Target=target[5:])
                e.set(key,coverrids[rid])
bp['[Content_Types].xml']=xml(cts);bp['word/_rels/document.xml.rels']=xml(rels)
assert len({r.get('Id') for r in rels}) == len(rels), 'Duplicate package relationship identifiers'
finalsect=deepcopy(bb[-1])
# The retained covers form two sections; body page numbering starts at one afterward.
for header in finalsect.findall('w:headerReference',NS):finalsect.remove(header)

def document(nodes):
    r=deepcopy(br);body=r.find('w:body',NS)
    for n in list(body):body.remove(n)
    for n in nodes:body.append(deepcopy(n))
    body.append(deepcopy(finalsect));return r

independent=document(front_nodes)
separator=el('w:p');spr=el('w:pPr');spr.append(el('w:spacing',before=0,after=0,line=20,lineRule='exact'));separator.append(spr)
sr=el('w:r');sr.append(el('w:br',type='page'));separator.append(sr)
combined=document(cover+front_nodes+[separator]+post)
for doc,path in [(independent,OUT),(combined,FULL)]:
    items=dict(bp);items['word/document.xml']=xml(doc)
    # Keep the existing no-external-link/update-prompt settings.
    save(path,items)

audit={'sources':source_hash,'source_body':stats(br),'front':stats(independent),'combined':stats(combined),
       'original_body_elements':len(original),'front_elements':len(front_nodes),'cover_elements':len(cover),
       'body_start_index':len(cover)+len(front_nodes)+1,'body_math_xml_unchanged':True,
       'body_media_unchanged':all(parts(FULL)[n]==b for n,b in parts(BODY).items() if n.startswith('word/media/')),
       'chapter_mapping':{'5':6,'6':7,'7':8,'8':9},'reference_changes':changes,
       'number_cell_padding_and_wrapping':number_cell_layout,
       'outputs':{OUT.name:sha(OUT),FULL.name:sha(FULL)}}
(WORK/'结构核验.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
assert all(sha(Path(p))==h for p,h in source_hash.items())
print(json.dumps({k:v for k,v in audit.items() if k not in ['sources','reference_changes']},ensure_ascii=False,indent=2))

"""Reorganize Q3 only, preserve native Office Math and derive prose tables from frozen outputs.
Usage: bundled-python rewrite_q3_paper.py SOURCE.docx [OUTPUT.docx]
No numerical model, notebook, or upstream output is changed.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from copy import deepcopy
import csv, hashlib, json, re, sys
from lxml import etree as E

ROOT=Path(__file__).resolve().parent
SRC=Path(sys.argv[1])
OUT=Path(sys.argv[2]) if len(sys.argv)>2 else ROOT/'F题论文初稿_问题三精简_20260926.docx'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
def tag(s):
 a,b=s.split(':');return '{'+NS[a]+'}'+b
def el(s,**attrs):
 n=E.Element(tag(s))
 for k,v in attrs.items():n.set(tag('w:'+k),str(v))
 return n
def text(n):return ''.join(n.xpath('.//w:t/text()|.//m:t/text()',namespaces=NS))
def canon(n):return E.tostring(n,method='c14n',exclusive=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
with ZipFile(SRC) as z:
 infos=z.infolist();parts={i.filename:z.read(i.filename) for i in infos}
source_sha=sha(SRC)
r=E.fromstring(parts['word/document.xml']);body=r.find('w:body',NS);old=list(body)
start=next(i for i,n in enumerate(old) if text(n)=='问题三模型建立与求解')
end=next(i for i,n in enumerate(old) if text(n)=='问题四模型建立与求解')
assert not any('PaperEq_7_' in s for n in old[:start]+old[end:] for s in n.xpath('.//w:instrText/text()',namespaces=NS))
eqs={}
for n in old[start:end]:
 m=re.search(r'\(7-(\d+)\)$',text(n))
 if m and n.tag==tag('w:tbl'):eqs[int(m[1])]=n
assert len(eqs)==55
used={}
def data(name):
 p=ROOT/'output_q3_resource'/name;used[str(p.relative_to(ROOT))]=sha(p)
 if p.suffix=='.json':return json.loads(p.read_text())
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def pick(rows,**kw):
 a=[r for r in rows if all(r[k]==str(v) for k,v in kw.items())];assert len(a)==1,kw;return a[0]
interface=data('q3_interface.json');verification=data('verification.json');decision=data('decision_verification.json')
main=data('tables/main_results.csv');caps=data('tables/cap_scenario_results.csv');thresholds=data('tables/quality_benefit_thresholds.csv')
scan=data('tables/budget_scan.csv');trans=data('tables/transitions.csv');values=data('tables/resource_value_analysis.csv');recipes=data('tables/paired_recipe_comparison.csv')
assert len(main)==45 and len(caps)==225 and {n['state'] for n in scan}=={'R2'}
active_trans=[n for n in trans if n['C_critical']]
assert len(active_trans)==6 and {n['scenario'] for n in active_trans}=={'sQ_2'}
# Fixed prose examples must match frozen outputs at the displayed precision.
assert f'{interface["theta_Q"]:.6f}'=='0.396659'
assert f'{interface["theta_Q"]/2:.6f}'=='0.198330'
assert all(float(n['lambda_full'])<interface['theta_Q'] for n in thresholds)
assert {n['state'] for n in caps}=={'R2'}
for C,checks in [
 ('1e+19',{'equivalent_compute_multiplier':('1.2106',4),'loss_drop_per_log_budget':('0.203078',6)}),
 ('1e+24',{'equivalent_compute_multiplier':('1.3332',4),'loss_drop_per_log_budget':('0.032847',6)})]:
 row=pick(values,C=C,L_ctx='2048',cost='exponential')
 for key,(expected,digits) in checks.items():assert f'{float(row[key]):.{digits}f}'==expected
row=pick(main,C='1e+19',L_ctx='2048',cost='exponential')
assert f'{float(row["baseline_N_B"]):.4f}'=='0.2213'
assert f'{float(row["baseline_D_B"]):.4f}'=='7.0496'
row=pick(recipes,C='1e+19',L_ctx='2048',cost='exponential')
assert f'{float(row["loss_pstar"]):.6f}'=='2.927891'
audit_path=ROOT/'Q3/quality_audit/within_domain_selection.csv'
used[str(audit_path.relative_to(ROOT))]=sha(audit_path)
with audit_path.open(encoding='utf-8-sig') as f:audit=list(csv.DictReader(f))
assert pick(audit,domain='book',requested_keep='0.05')['n_keep']=='9'
new=[];appendix=[];target=new;section='7';counts={'7':0,'附3':0};tables={'7':0,'附3':0};mapping={};plain=[]
def scrub(n):
 for ch in n.iter():
  for k in list(ch.attrib):
   if E.QName(k).localname in ('paraId','textId','rsidR','rsidRDefault','rsidP','rsidTr','rsidRPr'):del ch.attrib[k]
 for ch in list(n.xpath('.//w:bookmarkStart|.//w:bookmarkEnd|.//w:lastRenderedPageBreak',namespaces=NS)):ch.getparent().remove(ch)
 return n
def mathrun(s):
 n=E.Element(tag('m:r'));E.SubElement(n,tag('m:t')).text=s;return n
def sub(s,i):
 n=E.Element(tag('m:sSub'));E.SubElement(n,tag('m:e')).append(mathrun(s));E.SubElement(n,tag('m:sub')).append(mathrun(i));return n
terms={s:sub(*s.split('_',1)) for s in ['N_B','D_B','Q_0','q_low','q_high','s_Q','θ_Q','λ_Q','η_p','η_att','L_ctx','p_0','p_i','q_i','s_L','q_B','t_N','t_D','λ_on','λ_full','C_eq','R_0','R_1','R_2','d_i','κ_i','μ_d','u_b','c_b','u_m','l_s','S_d','n_d','a_i','ε_p','F_C','H_C','M_C','z_0','ϵ_C','K_0','c′_b','N_B,b']}
def power(base,exponent):
 n=E.Element(tag('m:sSup'));E.SubElement(n,tag('m:e')).append(deepcopy(base));E.SubElement(n,tag('m:sup')).append(mathrun(exponent));return n
terms.update({'N_B^(−α)':power(sub('N','B'),'−α'),'D_B^(−ν)':power(sub('D','B'),'−ν')})
pat=re.compile('|'.join(map(re.escape,sorted(terms,key=len,reverse=True))))
def addtext(p,s,rp=None):
 def run(t):
  if not t:return
  n=el('w:r')
  if rp is not None:n.append(deepcopy(rp))
  for j,line in enumerate(t.split('\n')):
   if j:n.append(el('w:br'))
   tnode=el('w:t');tnode.set('{http://www.w3.org/XML/1998/namespace}space','preserve');tnode.text=line;n.append(tnode)
  p.append(n)
 a=0
 for m in pat.finditer(s):
  run(s[a:m.start()]);n=E.Element(tag('m:oMath'));n.append(deepcopy(terms[m[0]]));p.append(n);a=m.end()
 run(s[a:])
tmpl={k:next(n for n in old[start:end] if text(n)==v) for k,v in {'h1':'问题三模型建立与求解','h2':'任务分解与总体解题思路','h3':'从性能辨识到条件资源决策','caption':'表 7-2 本章新增或需区分的主要符号'}.items()}
tmpl['body']=old[start+1]
def para(s,role='body',page_break=False):
 s=re.sub(r'(\d+\.\d+)e-16',r'\1×10⁻¹⁶',s)
 n=el('w:p');pr=deepcopy(tmpl[role].find('w:pPr',NS))
 if pr is None:pr=el('w:pPr')
 for ch in list(pr):
  if E.QName(ch).localname in ['keepNext','pageBreakBefore']:pr.remove(ch)
 if role.startswith('h') or role=='caption':pr.append(el('w:keepNext'))
 pr.append(el('w:widowControl'))
 if section=='附3' and role.startswith('h'):
  for ch in pr.findall('w:numPr',NS):pr.remove(ch)
  num=el('w:numPr');num.append(el('w:numId',val=0));pr.append(num)
 if page_break:pr.append(el('w:pageBreakBefore'))
 n.append(pr);addtext(n,s,tmpl[role].find('w:r/w:rPr',NS));target.append(n);plain.append(('## ' if role.startswith('h') else '')+s);return n
def eq(num):
 assert num not in mapping,num
 counts[section]+=1;label=f'{section}-{counts[section]}';mapping[num]=label
 n=scrub(deepcopy(eqs[num]))
 if num==13:
  for t in n.xpath('.//m:t',namespaces=NS):
   if t.text:t.text=t.text.replace('&','')
 cells=n.findall('w:tr/w:tc',NS)
 assert len(cells)==3
 if section=='附3':
  for col,cell,width in zip(n.findall('w:tblGrid/w:gridCol',NS),cells,[1100,6872,1100]):
   col.set(tag('w:w'),str(width));cell.find('w:tcPr/w:tcW',NS).set(tag('w:w'),str(width))
 cell=cells[-1]
 for ch in list(cell):
  if ch.tag!=tag('w:tcPr'):cell.remove(ch)
 p=el('w:p');pr=el('w:pPr');pr.append(el('w:pStyle',val='-'));pr.append(el('w:jc',val='right'));p.append(pr);addtext(p,'('+label+')');cell.append(p)
 if target and target[-1].tag==tag('w:p'):
  pr=target[-1].find('w:pPr',NS)
  if pr.find('w:keepNext',NS) is None:pr.append(el('w:keepNext'))
 target.append(n);plain.append('[公式'+label+'] '+''.join(n.xpath('.//m:t/text()',namespaces=NS)));return label

def table(title,headers,rows,widths,flow=False):
 assert sum(widths)==9072
 if not flow:
  tables[section]+=1;para(f'表{section}-{tables[section]}  {title}','caption')
 n=el('w:tbl');pr=el('w:tblPr');pr.append(el('w:tblW',w=9072,type='dxa'));pr.append(el('w:tblLayout',type='fixed'))
 borders=el('w:tblBorders')
 for edge in ['top','left','bottom','right','insideH','insideV']:borders.append(el('w:'+edge,val='nil' if flow else 'single',sz=4,color='D9D9D9'))
 pr.append(borders);n.append(pr);grid=el('w:tblGrid')
 for width in widths:grid.append(el('w:gridCol',w=width))
 n.append(grid);allrows=rows if flow else [headers]+rows
 for ri,vals in enumerate(allrows):
  row=el('w:tr');rp=el('w:trPr');rp.append(el('w:cantSplit'))
  if ri==0 and not flow:rp.append(el('w:tblHeader'))
  row.append(rp)
  for ci,(v,width) in enumerate(zip(vals,widths)):
   cell=el('w:tc');cp=el('w:tcPr');cp.append(el('w:tcW',w=width,type='dxa'));cp.append(el('w:vAlign',val='center'))
   mar=el('w:tcMar')
   for edge,val in [('top',95),('bottom',95),('left',80),('right',80)]:mar.append(el('w:'+edge,w=val,type='dxa'))
   cp.append(mar)
   if (flow and ci%2==0) or (not flow and ri==0):cp.append(el('w:shd',val='clear',fill='EAF1F5' if flow else 'F2F2F2'))
   if flow and ci%2==0:
    borders=el('w:tcBorders')
    for edge in ['top','left','bottom','right']:borders.append(el('w:'+edge,val='single',sz=5,color='AEBECA'))
    cp.append(borders)
   cell.append(cp);p=el('w:p');pp=el('w:pPr');pp.append(el('w:pStyle',val='-'));pp.append(el('w:jc',val='center'));pp.append(el('w:spacing',before=0,after=0,line=260,lineRule='auto'))
   if ri<len(allrows)-1:pp.append(el('w:keepNext'))
   p.append(pp);rp=el('w:rPr');rp.append(el('w:rFonts',ascii='Times New Roman',hAnsi='Times New Roman',eastAsia='宋体'));rp.append(el('w:sz',val=21));rp.append(el('w:szCs',val=21))
   if ri==0 and not flow:rp.append(el('w:b'))
   addtext(p,str(v),rp);cell.append(p);row.append(cell)
  n.append(row)
 target.append(n);plain.append('| '+' | '.join(headers)+' |');plain.extend('| '+' | '.join(map(str,a))+' |' for a in rows)

# Keep the original chapter counter hidden; all other chapters retain their original XML.
heading=deepcopy(old[start]);infield=False
for run in heading.findall('w:r',NS):
 f=run.find('w:fldChar',NS)
 if f is not None and f.get(tag('w:fldCharType'))=='begin':infield=True
 if infield:
  rp=run.find('w:rPr',NS)
  if rp is None:rp=el('w:rPr');run.insert(0,rp)
  rp.append(el('w:vanish'))
 if f is not None and f.get(tag('w:fldCharType'))=='end':infield=False
new.append(heading)
para('本问沿用第二问的损失模型，在总算力预算内联合选择参数量、训练量和额外质量投入。提质能够降低预测损失，也会挤占规模预算；本文通过内外两层优化求解这一权衡，再用全局收益阈值解释最优质量状态。配比固定为参考配比p_0，第一问候选配比p⋆仅作对照，因此所得配置为给定配比与情景条件下的最优解。')
table('',[],[['预算取等号','→','固定质量\n优化规模','→','全区间比较\n质量投入','→','配置结果与\n全局阈值']], [1920,464,1920,464,1920,464,1920],flow=True)
para('图7-1  条件资源优化的求解主线','caption')
para('预算约束下的资源优化模型','h2')
para('参数量N_B与训练量D_B均以十亿为单位。质量侧使用三个变量：u为同配比下额外质量增量；z为成本函数使用的质量刻度；U为样本构造的质量增量上限。给定配比p、上下文L_ctx、质量效果尺度s_Q和上限参照比例r，建立：')
eq(15)
para('E、A、B、α、ν继承第二问B1估计，η_p与h(p)分别为配比修正强度及标准化配比响应；主配比满足h(p_0)=0。λ_Q=θ_Q/s_Q为当前质量刻度下的条件收益系数，θ_Q=0.396659，s_Q=1为主情景，0.5与2用于敏感性分析。s_Q尚未由独立质量标定识别。')
para('质量刻度与样本上限','h3')
para('基线质量Q_0=Σp_i q_i沿用第一问，其中q_i为映射后的配方域质量，总质量为Q=Q_0+u。成本刻度由A1七个质量域等权分布的1%和99%分位锚点定义：')
eq(5)
lo=interface['T']['q_low'];hi=interface['T']['q_high']
para(f'其中q_low={lo:.6f}、q_high={hi:.6f}、Δq=q_high−q_low，z_0=T(Q_0)。成本刻度转换只作用于成本端，与决定质量收益的s_Q分别设定。锚点构造与领域样本支持见附录三。')
para('在每个质量域内按评分排序，以最高r比例文档的均值增量构造上限：')
eq(7)
para('M为有质量映射的配方域集合，d_i为对应质量域，κ_i为第一问映射收缩系数，μ_d(r)为该域最高r比例文档的平均质量。缺少质量样本的11个配方域冻结基准质量，新增收益取零。取r=80%、50%、20%、10%、5%形成五个独立上限情景；50%仅用于详细展示。允许u在[0,U]连续变化是建模假设，样本上限不保证相应训练Token供给。')
para('训练 注意力与质量处理成本','h3')
para('基础训练与注意力成本都正比于N_B D_B，质量处理成本按同一训练量D_B计。将三项成本合并：')
eq(14)
para('其中k=10¹⁸(6+η_att L_ctx)，η_att=2×10⁻⁴，c(u)是每十亿训练Token的增量提质算力。g表示每Token质量处理开销，采用题设三类函数：')
eq(12)
para('各情景核对z的定义域及成本单调区间，使c(0)=0、c(u)≥0。三类函数既改变曲率也改变绝对成本量级，比较时保留题设参数。上下文取2048、4096、8192、32768、131072，仅改变开销；本目标未估计长上下文本身的任务收益。')

para('通过降维求解规模与质量配置','h2')
para('固定质量下的唯一规模最优解','h3')
para('固定质量与配比后，增加训练量会严格降低损失；在未设置训练量上限的模型中，最优解用尽预算。因此：')
eq(18)
para('将D_B代回目标，令x=lnN_B，把固定质量下的规模问题写为：')
eq(19)
para('当A、B、α、ν、k为正且c(u)≥0时，该函数关于x严格凸，并在两端发散，因而存在唯一全局最小点。记t_N=A N_B^(−α)、t_D=B D_B^(−ν)，一阶最优条件为：')
eq(23)
para('该等式平衡参数增加的收益与预算挤占训练量造成的损失。共同质量乘子在固定u时不影响极值位置，但提质成本c(u)会改变规模配置。无提质时c(0)=0，关系退化为αt_N=νt_D；无提质解析解作为同预算比较基线，推导见附录三。')
para('全区间比较质量投入','h3')
para('令F_C(u)表示固定质量u、重新优化参数量与训练量后的最小规模可约损失：')
eq(25)
para('外层再加入质量与配比乘子，得到：')
eq(26)
para('外层不预设为凸或单峰函数。求解时比较两个端点、检测到的驻点与局部精化候选，并用加密网格和独立二维优化核查结果。质量状态记为R_0：u⋆=0，R_1：0<u⋆<U，R_2：u⋆=U，分别对应不提质、部分提质与达到参照上限。')

para('主情景的最优配置与质量决策','h2')
para('主情景持续达到样本参照上限','h3')
cap=interface['scenarios']['main']['cap']
para(f'固定p_0、s_Q=1及50%文档参照，质量上限U={cap:.6f}。三档预算、三类成本和五种上下文共45个配置均达到上限；在10¹⁹—10²⁴ FLOPs的3015个预算扫描点中，状态也全部为R_2，未检测到质量状态转移。表7-1展示2048上下文下的三档配置。')
costnames={'exponential':'指数型','power':'幂函数型','logarithmic':'对数型'}
rows=[]
for C,label in [('1e+19','10¹⁹'),('1e+22','10²²'),('1e+24','10²⁴')]:
 for cost in costnames:
  a=pick(main,C=C,L_ctx='2048',cost=cost)
  rows.append([label,costnames[cost],f'{float(a["N_B"]):.4f}',f'{float(a["D_B"]):.4f}',f'{float(a["loss"]):.6f}',f'{float(a["loss_gain"]):.6f}'])
table('2048上下文的主情景配置与无提质基线比较',['预算/FLOPs','成本','N_B','D_B','预测损失','损失下降量'],rows,[1300,1250,1350,1550,1780,1842])
para('表中各行u⋆相同，损失下降量以同预算、同配比、同上下文下重新优化的无提质方案为基线。在10¹⁹ FLOPs指数成本情景，参数量由0.2213B增至0.2458B、训练量由7.0496B降至5.7980B，质量收益补偿了训练量缩减；预算增长后，参数量与训练量继续扩大。持续R_2表示设定上限一直活跃，不表示真实质量已自然饱和。')
para('达到质量上限的全局收益条件','h3')
para('令H_C(u)=lnF_C(u)。固定预算与配比时，质量决策等价于最小化H_C(u)−λ_Q u。全局收益阈值＝在整个允许质量区间比较目标后，开始提质与达到上限所需的质量收益系数。开始提质门槛为：')
eq(36)
para('达到上限的门槛为：')
eq(38)
para('λ_Q<λ_on时不提质；λ_Q>λ_full时达到上限；两阈值严格分离且λ_on<λ_Q<λ_full时最优解位于内部。等号处相应端点是最优解之一，可能存在并列解。阈值相等时可直接由不提质切换到上限。这些判据不要求外层凸性，局部端点导数不能替代全区间比较。')
rows=[]
for cost in costnames:
 a=pick(thresholds,C='1e+19',L_ctx='2048',cost=cost,keep='0.5')
 rows.append([costnames[cost],f'{float(a["lambda_on"]):.6f}',f'{float(a["lambda_full"]):.6f}',f'{interface["theta_Q"]:.6f}','达到上限'])
table('10¹⁹ FLOPs与2048上下文下的全局质量收益门槛',['成本','开始提质λ_on','达到上限λ_full','主情景λ_Q','选择'],rows,[1450,2200,2200,1900,1322])
para('表中主情景λ_Q均高于达到上限门槛，解释了该配置下的R_2。对数成本两阈值相等，此时不存在严格的中间收益区间。五档上限扩展得到的225个离散配置也均为R_2；该结果支持三档预算下的上限情景稳健性；连续预算证据来自50%参照切片。')
para('质量收益减弱后的状态转移','h3')
para('将s_Q改为2后，λ_Q减半为0.198330。在50%上限参照、幂函数成本与2048、4096、8192上下文下，预算扫描检测到不提质→部分提质→达到上限的转移；转移依赖质量收益尺度、成本函数与上下文条件。')
rows=[]
for ctx in ['2048','4096','8192']:
 a=pick(active_trans,L_ctx=ctx,from_state='R0');b=pick(active_trans,L_ctx=ctx,from_state='R1')
 rows.append([ctx,f'{float(a["C_critical"])/1e19:.6f}',f'{float(b["C_critical"])/1e19:.6f}'])
table('弱质量收益情景的预算转移位置',['上下文','不提质→部分提质','部分提质→达到上限'],rows,[2072,3500,3500])
para('表中预算单位为10¹⁹ FLOPs。例如2048上下文在约1.486566×10¹⁹ FLOPs开始提质，在约2.011623×10¹⁹ FLOPs达到上限。转移位置经原目标比较及两侧重算核验。上下文增加会改变预算分配和边界位置，但本模型仅计其额外成本，不将较低的转移预算解释为长上下文更便宜。')

para('资源收益与结果的适用范围','h2')
para('在指数成本、2048上下文主情景中，预算从10¹⁹增至10²⁴ FLOPs时，提质占比由8.6448%降至0.0580%，但绝对提质算力由8.6448×10¹⁷增至5.8003×10²⁰ FLOPs，且质量增量始终为U。因此占比下降不等于停止提质。')
para('等效算力C_eq定义为同配比、同上下文的无提质方案达到当前最优损失所需预算。由无提质标度指数ϵ_C=αν/(α+ν)得到：')
eq(52)
para('上述两个预算点的等效算力倍率分别为1.2106与1.3332。预算影子价格＝增加单位预算所带来的局部最优损失下降；按对数预算计量，−dL⋆/dlnC分别为0.203078与0.032847，显示边际收益减小。两项均为同模型内的收益换算，不是实测训练加速。')
para('固定配比对照中，10¹⁹ FLOPs、2048上下文与指数成本下，候选配比p⋆的条件预测损失为2.927891，低于p_0的2.961071，尽管其质量上限更低。该比较同时改变质量基线、配比响应和上限，不能只按上限大小评价配比；它也不等同于本问对17维配比重新联合寻优。')
para(f'数值核验包含{verification["independent_cases"]}组独立二维优化对照，可约损失最大相对差为{verification["max_independent_objective_relative_error"]:.3e}，最大预算相对残差为{verification["max_budget_relative_error"]:.3e}；另完成{decision["decision_checks"]}个全局阈值两侧、内部及等号决策核验。核验支持求解一致性，有限网格与随机搜索不构成连续域的形式化全局证明。')
para('结果条件于固定配比、成本映射、样本质量上限与尚未识别的s_Q。质量收益承接半合成实验，正质量增量属于基准以上外推；高预算规模可能超出观测范围，且同一D_B成本代理没有提供筛选前原料和训练Token供给约束。候选配比对照还依赖跨来源修正迁移。第四问可继承这些配置与损失路径，并保留相同条件边界。')
main_end=len(plain)

# Supplementary methods retain derivation, numerical settings and evidence boundaries.
target=appendix;section='附3'
para('附录三 问题三的补充推导与数值核验','h1',page_break=True)
para('本附录给出正文采用的质量参照构造、内外层导数、局部候选条件与复现设置。公式与正文共同属于同一个条件资源模型；各阶段使用相同的前问参数与成本刻度。')
para('一 质量参照与成本口径','h2')
para('参数量和Token量以十亿为计算单位，与原始计数的关系为：');eq(1)
para('第一问继承的基线质量与配比响应为：');eq(2)
para('其中c₀、a_i、ε_p为第一问对数线性配比模型参数，s_L为训练综合损失标准差。质量增量定义为：');eq(3)
para('A1七域等权参考分布及固定锚点定义为：');eq(4)
para('S_d为域d的文档集合，n_d为其文档数，各域权重均为1/7。按域内评分降序保留约r比例文档，定义：');eq(6)
para('保留数量按现有排序规则确定，尾部均值与样本数共同解释。五档参照在p_0下的质量上限依次为0.052165、0.111512、0.186546、0.230093、0.268296；其中book域5%参照仅9篇文档，尾部支持较弱。')
para('以l_s表示文档词数，筛选后的词数保留率为：');eq(9)
para('词数保留率一般不等于文档比例r，也不是特定分词器下的Token保留率。没有原料库存与重复训练约束时，该指标仅检查样本支持。质量效果系数及共同乘子为：');eq(10)
para('s_Q改变收益尺度而不改变成本映射T。主情景h(p_0)=0，候选配比对照才引入非零配比乘子；两者均沿用B1性能基线。三项算力逐项表达为：');eq(11)
para('三类成本导数为：');eq(13)
para('在z≥0时，指数型和幂函数型递增且凸，对数型递增且凹；对数型要求1+10z>0。各情景核对基准及上限所在成本区间，使增量成本非负，此时与题设正部截断一致。注意力成本与基础训练成本之比为：');eq(16)
para('临界窗口30000表示题设代理中两项开销相等。上下文取C7的max_position_embeddings去重值，不对长上下文的性能收益另作估计。')
para('二 内层唯一性与外层局部条件','h2')
para('固定u与p，损失对D_B的偏导为：');eq(17)
para('因此有剩余预算时可增加训练量改进目标。该论证使用无额外训练量上限的前提；若加入Token库存限制，需重新判断预算是否紧约束。令W=k exp(x)，内层目标的一阶与二阶导数分别为：');eq(20);eq(21)
para('在正参数与c≥0下二阶导数严格为正；x趋于负无穷时参数不足项发散，趋于正无穷时训练量不足项发散。两端发散与严格凸性共同保证唯一内层解，但不保证外层质量问题为凸。无提质解析基线为：');eq(24)
para('质量端的成本导数须包含刻度换算：');eq(27)
para('利用内层一阶条件，外层剖面目标的导数为：');eq(28)
para('M_C(u)第一项是质量直接改善，第二项是处理成本挤占规模预算的机会成本。令H_C(u)=lnF_C(u)，有：');eq(29)
para('端点及内点的局部必要条件为：');eq(30)
para('这些条件只产生候选解，最终须比较全区间目标。状态定义为：');eq(31)
para('判断状态改变时同时记录质量位置与近似并列候选。开销占比改变或同一状态内规模平滑变化，不单独构成质量状态转移。')
para('三 全局阈值与边界预算候选','h2')
para('不提质优于任何正质量投入的条件为：');eq(35)
para('对所有u>0取割线斜率的下确界，即得到正文开始提质门槛。上限方案优于所有较低质量投入的条件为：');eq(37)
para('对所有u<U取对应割线的上确界，即得到达到上限门槛。两个阈值满足：');eq(39)
para('若两阈值严格分离，严格中间区间内两个端点均非最优，连续目标的最优点位于内部；等号处允许并列解。可微时端点的局部门槛为：');eq(41)
para('局部门槛是割线在端点处的极限，只有附加形状条件成立时才与全局门槛一致。在θ_Q>0且门槛为正时，可换算为效果尺度门槛：');eq(42)
para('较大的s_Q对应较弱质量收益，故尺度门槛方向与收益门槛相反；门槛为零时使用极限解释。')
para('为定位连续边界转移的候选，固定u_b∈{0,U}，记c_b=c(u_b)、c′_b=c′(u_b)、W=kN_B,b，将内层与外层驻点条件联立得到：');eq(32)
para('仅当λ_Q>0、W>0且成本有效时，形成正规模预算候选：');eq(33)
para('该候选仍需与其他分支比较，不能直接当作实际全局切换点。固定边界质量与收益尺度时，其上下文缩放关系为：');eq(34)
para('这只是局部驻点候选的条件关系，不是所有全局转移的规律。高上下文仅增加成本，同预算可行域不会因此扩大。')
para('四 收益指标与数值设置','h2')
para('与同预算、同配比及同上下文下的无提质最优配置比较，绝对损失收益与相对可约损失收益为：');eq(46)
para('u=0属于可行集合，因此求得目标不应高于同条件无提质基线。预算紧约束下的开销份额为：');eq(47)
para('同一上下文内注意力与基础训练份额之比固定，三元开销图不代表三个独立决策维度。在光滑最优分支上，单位预算与对数预算的影子价值分别为：');eq(48);eq(49)
para('分支切换且导数不唯一时采用两侧单边导数。无提质预算标度关系与等效预算定义为：');eq(50);eq(51)
para('由此消去常数K₀得到正文等效算力公式；要求两种可约损失为正，且配比、上下文和基线一致。')
table('求解与核验设置',['环节','数值设置','核验对象'],[
 ['内层求根','对数参数自适应括区间；绝对容差10⁻¹²','一阶条件、预算残差及扩大区间复算'],
 ['外层质量搜索','默认65点；257点复核；状态容差10⁻⁷；近似等价目标容差10⁻⁹','端点、驻点及精化候选的目标比较'],
 ['连续预算','10¹⁹—10²⁴；主扫描101点加密到201点；敏感性101点','规模、质量状态与开销变化'],
 ['全局阈值','129点割线极值搜索及局部精化；代表情景513点复核','阈值两侧、内部和等号处重新优化'],
 ['二维独立优化','随机种子925；差分进化种群倍数12、最多300代、容差10⁻¹⁰','另用L-BFGS-B精化；目标与梯度容差10⁻¹⁴、10⁻⁹']
],[1700,3800,3572])
para('内层括区间扩大到一阶条件两端异号，求唯一根；不把搜索端点当成物理规模上限。独立二维对照直接消去D_B，以x=lnN_B、t=u/U为变量，其对数目标为：');eq(54)
para('搜索区间以无提质解析对数规模为中心上下各扩展10，0≤t≤1；从差分进化候选及两个质量端点启动局部优化。该对照不调用内层求根，但共享相同损失、成本与预算模型；解离搜索边缘大于1的检查不能替代全实轴证明。')
para('检测到相邻预算点状态改变后，在对数预算上求边界驻点并用最多36次状态二分定位；没有边界导数根时使用状态二分。候选预算两侧的探测点为：');eq(53)
para('转移区域另用161个几何间隔预算点放大检查。相邻扫描点状态相同仍可能漏过窄区间切换，同为部分提质的分支切换也未必改变状态标签，所以表述为“未检测到”，不声称穷尽所有分支。')
para('剖面导数的中心差分在u_m=0.43U、δu=10⁻⁴U处进行：');eq(55)
para('每次扰动均重新求内层最优，且要求U>0与扰动点可行。33组二维对照覆盖不提质、部分提质与达到上限三种状态。已有核验中外层导数最大相对误差为2.715×10⁻¹⁰，全局阈值网格对照最大相对差为0，影子价值有限差分最大相对差为7.835×10⁻¹¹；这些是实现一致性检查，不是新训练验证。')
para('情景文件保留观测范围标记：参数量与训练量分别位于B1/B7轴对齐范围仅表示坐标覆盖，不证明其联合配置被观测。正质量增量及候选配比迁移分别标记；数值模型允许显式规模外推，未以观测最大规模作为物理限制。')

# Replace Q3 only and append supplemental methods before the final section properties.
for n in old[start:end]:body.remove(n)
for j,n in enumerate(new):body.insert(start+j,scrub(n) if j else n)
for n in appendix:body.insert(len(body)-1,scrub(n))
parts['word/document.xml']=E.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
 for info in infos:z.writestr(info,parts[info.filename])
# Source, scope, math and package checks.
after=list(body);newend=start+len(new)
assert [canon(n) for n in old[:start]]==[canon(n) for n in after[:start]]
assert [canon(n) for n in old[end:-1]]==[canon(n) for n in after[newend:newend+len(old[end:-1])]]
assert canon(old[-1])==canon(after[-1])
for num,label in mapping.items():
 n=next(n for n in new+appendix if n.tag==tag('w:tbl') and text(n).endswith('('+label+')'))
 expected=deepcopy(eqs[num])
 if num==13:
  for t in expected.xpath('.//m:t',namespaces=NS):
   if t.text:t.text=t.text.replace('&','')
 assert [canon(x) for x in expected.xpath('.//m:oMath',namespaces=NS)]==[canon(x) for x in n.xpath('.//m:oMath',namespaces=NS)]
assert sha(SRC)==source_sha
with ZipFile(OUT) as z:
 assert z.testzip() is None
 changed=[name for name,value in parts.items() if value!=ZipFile(SRC).read(name)]
assert changed==['word/document.xml']
assert not re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',''.join(plain))
report={'version':'v0.9.13','source':SRC.name,'source_sha256':source_sha,'output':OUT.name,'output_sha256':sha(OUT),'changed_parts':changed,'other_chapters_preserved':True,'source_unchanged':True,'numerical_model_changed':False,'old_q3_text_characters':sum(len(text(n)) for n in old[start:end]),'new_q3_text_characters':sum(len(text(n)) for n in new),'equation_counts':counts,'table_counts':tables,'equation_map':mapping,'numerical_sources_sha256':used,'formula_presentation_fix':'Removed literal alignment ampersands from original formula 7-13; mathematical derivative unchanged','render_qa':'pending'}
(ROOT/'Q3/论文第三问精简正文.md').write_text('\n\n'.join(plain[:main_end]))
(ROOT/'Q3/论文第三问实现附录.md').write_text('\n\n'.join(plain[main_end:]))
(ROOT/'Q3/论文第三问精简核验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ['equation_map','numerical_sources_sha256']},ensure_ascii=False,indent=2))

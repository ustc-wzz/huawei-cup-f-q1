"""Edit Q1 sections 5.8–5.10 only, retaining native equations and other chapters.

Usage: bundled-python Q1/simplify_paper_sections.py SOURCE.docx [OUTPUT.docx]
Existing results are read without fitting or changing any computational model.
"""
from pathlib import Path
from copy import deepcopy
from zipfile import ZipFile, ZIP_DEFLATED
from collections import Counter
import csv
import hashlib
import json
import sys
from lxml import etree as E

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'F题论文初稿_问题一5.8至5.10精简_20260926.docx'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
def tag(s):
    pre, name = s.split(':')
    return '{' + NS[pre] + '}' + name
def text(n):
    return ''.join(n.xpath('.//w:t/text() | .//m:t/text()', namespaces=NS))
def canonical(n):
    return E.tostring(n, method='c14n')
def sub(n, name, **kw):
    item = E.SubElement(n, tag(name))
    for k, v in kw.items(): item.set(tag('w:' + k), str(v))
    return item
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

source_hash = sha(SRC)
with ZipFile(SRC) as z:
    infos = z.infolist()
    parts = {i.filename: z.read(i.filename) for i in infos}
r = E.fromstring(parts['word/document.xml'])
b = r.find('w:body', NS)
old = list(b)
start = next(i for i,n in enumerate(old) if text(n) == '质量与配比的跨体系关联')
end = next(i for i,n in enumerate(old[start:], start) if text(n) == '求解结果')
segment = old[start:end]
by_text = {text(n): n for n in segment}
display_before = Counter(canonical(n) for n in r.xpath('.//m:oMathPara', namespaces=NS))
used = {}
tab = ROOT / 'output_q1/length_domain_calibrated22/tables'
def rows(name):
    p = tab / (name + '.csv'); used[str(p.relative_to(ROOT))] = sha(p)
    with p.open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))
def data(name):
    p = tab / (name + '.json'); used[str(p.relative_to(ROOT))] = sha(p)
    return json.loads(p.read_text())
inc = rows('quality_increment')
qonly = rows('quality_only_model')
weights = rows('weight_sensitivity')
metrics = rows('mixture_model_metrics_long')
opt = rows('optimal_mixture')
cross = data('main_mixture_crosscheck')
interface = data('q1_outputs_for_q2_q3')
protocol = data('mixture_selection_protocol')
assert 'KKT' in interface['p_star_note']
assert all(abs(interface['p_star'][k] - interface['p_star_loglinear'][k]) < 1e-12 for k in interface['p_star'])
assert all(float(v['对数特征系数 a_i']) < 0 for v in opt)
assert protocol['main_model'] == '对数线性混料'
def metric(model, dataset, key):
    return float(next(x for x in metrics if x['模型'] == model and x['数据集'] == dataset)[key])
def first(prefix):
    return next(n for n in segment if text(n).startswith(prefix))

def para(s, level=None, appendix=False, pagebreak=False):
    n = E.Element(tag('w:p')); pp = sub(n,'w:pPr')
    sub(pp,'w:keepLines')
    if level and not appendix:
        sub(pp,'w:pStyle',val=str(level))
        sub(pp,'w:spacing',before=120,after=120)
        sub(pp,'w:keepNext')
    elif appendix and level:
        sub(pp,'w:spacing',before=180,after=120)
        sub(pp,'w:keepNext')
        sub(pp,'w:outlineLvl',val=0 if level==1 else 1)
        sub(sub(pp,'w:numPr'),'w:numId',val=0)
        sub(pp,'w:ind',firstLine=0)
    else:
        sub(pp,'w:widowControl')
    if pagebreak: sub(pp,'w:pageBreakBefore')
    run = sub(n,'w:r')
    if appendix and level:
        rp = sub(run,'w:rPr');sub(rp,'w:b');sub(rp,'w:sz',val=32 if level==1 else 26)
        sub(rp,'w:rFonts',ascii='Times New Roman',hAnsi='Times New Roman',eastAsia='黑体')
    sub(run,'w:t').text = s
    return n

equation_map = {}
def equation(old_number, new_number):
    n = deepcopy(next(x for x in segment if x.tag==tag('w:tbl') and text(x).endswith(f'(5-{old_number})')))
    p = n.findall('w:tr/w:tc', NS)[-1].find('w:p',NS)
    for child in list(p):
        if child.tag not in {tag('w:pPr'),tag('w:bookmarkStart'),tag('w:bookmarkEnd')}:
            p.remove(child)
    run = E.Element(tag('w:r'));sub(run,'w:t').text='('+new_number+')'
    ends=p.findall('w:bookmarkEnd',NS)
    if ends:p.insert(p.index(ends[0]),run)
    else:p.append(run)
    equation_map[f'5-{old_number}']=new_number
    # Reserve space between the formula and label without changing math content.
    widths=[250,7522,1300]
    for cell,w in zip(n.findall('w:tr/w:tc',NS),widths):
        cell.find('w:tcPr/w:tcW',NS).set(tag('w:w'),str(w))
    for col,w in zip(n.findall('w:tblGrid/w:gridCol',NS),widths):col.set(tag('w:w'),str(w))
    return n

main = []
def p(s, level=None): main.append(para(s,level))
def cp(prefix): main.append(deepcopy(first(prefix)))
def eq(a,c): main.append(equation(a,c))

p('质量与配比的关联检验',2)
p('领域质量映射与配比加权',3)
cp('质量映射采用文档均分：')
eq(27,'5-27')
cp('直接、近似直接与推断映射分别设')
cp('固定领域质量向量')
eq(28,'5-28')
p('该指标将配比与领域文档均分相联系。缺失映射域的均值回填是参考设定，不代表已测得这些领域的质量；映射与聚合口径在所有配比实验中保持固定。')
p('质量附加项的预测增益',3)
p('以仅含配比加权质量的模型作为简短基线：')
eq(31,'5-29')
p('重点比较对数线性主模型与加入质量项后的模型：')
eq(32,'5-30')
p('两模型使用相同的训练数据与检验集合，以Spearman秩相关系数衡量配方损失排序的一致性。1M与60M检验集各含256个配方，1B检验集含64个配方。')
p('仅质量模型在1M检验集上的决定系数为−0.0480。加入质量项后，1M、60M、1B检验集的秩相关系数分别由'
  + '、'.join(f'{float(x["对数线性(p) Spearman"]):.4f}' for x in inc)
  + '变为' + '、'.join(f'{float(x["对数线性(p)+Qbar Spearman"]):.4f}' for x in inc)
  + '，未显示跨尺度一致的预测增益。因此，配比预测与候选求解继续采用原对数线性主模型，质量指数作为关联分析与后续尺度衔接的参考。')
p('领域质量固定时，配比加权质量完全由配比决定，因此本节检验统计关联与预测增益，不能据此识别独立质量效应。两类不可识别性推导及质量与领域系数的补充相关分析见附录一第一部分。')

p('基于主模型的候选配比求解',2)
p('约束优化与候选解',3)
p('固定训练尺度与评分条件，在领域份额非负且总和为1的约束下，最小化对数线性模型的预测损失：')
eq(33,'5-31')
p('当所有领域系数非正且至少一个严格为负时，该目标为凸函数；当前拟合的17个系数均为负，目标严格凸。由约束最优性条件可得：')
eq(36,'5-32')
p('其中λ为份额总和约束的乘子。通过二分法求解λ，并用序列最小二乘约束优化（SLSQP）交叉核查。该解为当前拟合模型在上述约束下的全局最优；若系数不满足凸性条件，须另行求解，不能直接沿用这一结论。推导与数值设置见附录一第二部分。')
p('候选比较与使用边界',3)
p('本文采用上述对数模型候选作为主配方。其份额最高的三个领域为stackexchange（12.15%）、dm_mathematics（11.97%）和pile_cc（10.44%）。梯度提升回归树（GBM）用于辅助评价，并与训练集最佳观测配方、平均配比和均匀配比进行对照。')
p(f'GBM对主候选、训练平均配比及均匀配比的预测损失分别为{cross["GBM_loss_main"]:.4f}、{cross["GBM_loss_train_mean"]:.4f}和{cross["GBM_loss_uniform"]:.4f}；主候选优于训练平均配比，与均匀配比的差异很小。随机搜索及两模型名次融合仅生成辅助对照候选，具体设置见附录一第二部分。')
p('单纯形约束保证份额非负且总和为1，但不保证候选位于训练配方的联合支持范围。报告候选时还需核查超出训练坐标范围的分量；模型预测最优与实际训练最优应予区分，候选的真实效果仍需新增训练实验验证。')

p('模型验证与稳健性分析',2)
p('质量评分稳健性',3)
p('固定A1参照，分别将单项权重乘以0.8或1.2后重新归一化，并比较去冗余强度0.5、1、1.5、2及等权方案；短板参数β取0、0.1、0.25、0.5、0.75、1，长度校准比较10、20、30组。以样本排序、前列样本重合程度和领域均值变化评价结果对设置的依赖，主设置保持β=0.25。')
single=[x for x in weights if '权重×' in x['方案']]
p(f'单项权重上下扰动20%时，样本排序与主方案的Spearman相关系数最低为{min(float(x["样本Spearman"]) for x in single):.4f}，领域均值排序均保持不变；改用等权方案时，样本与领域均值的秩相关系数分别为0.9465和0.7857。这说明评分对局部权重扰动较稳定，但赋权规则的整体改变仍会影响领域排序。')
p('上述检验描述评分规则的稳定性，不直接证明其准确反映训练价值。长度留出检验只评价长度校准组件，机械重复与格式扰动只评价指标响应；评分的数学性质、完整设置及核验流程见附录一第三部分。')
p('配比预测与跨尺度检验',3)
p('在A4/A5的512个训练配方内，采用外层五折交叉验证比较线性混料、对数线性混料、加性样条和GBM；有待选参数的模型在每个外层训练折内再用内层五折选择。每个配方及其13域损失记录作为一个划分单位，全训练集重拟合并冻结参数后，再用于A6—A11检验。')
p('四类模型的外层折外均方根误差依次为'
  + '、'.join(f'{metric(m,"外层5折CV","RMSE"):.4f}' for m in ['线性混料','对数线性混料','加性样条（PDF）','梯度提升树 GBM'])
  + '。GBM的预测误差最低；综合关系解释与约束求解的需要，本文采用对数线性模型作为主模型，GBM作为预测对照。对数主模型在同尺度1M检验集上的均方根误差为0.1071，决定系数为0.8514。')
p('冻结的对数主模型在60M、1B检验集上的Spearman秩相关系数分别为0.9116、0.7548，但绝对损失的均方根误差分别达到1.4894、2.6679。跨尺度结果支持部分配方排序的保持，不支持绝对损失已被准确标定。A12—A15的估算或外推表仅用于一致性分析，不作为新增独立实测验证。')
p('前期分析曾查看固定检验集的平滑参数表现；本轮选参虽限定于A4/A5内，A6—A11仍属于已被查看过的固定检验集，不能表述为全新未接触的外部验证。跨尺度辅助分析、参数来源与复现流程见附录一第三部分。')

app=[]
def ap(s,level=None,pagebreak=False):app.append(para(s,level,appendix=True,pagebreak=pagebreak))
def ac(prefix):app.append(deepcopy(first(prefix)))
def ae(a,c):app.append(equation(a,c))
ap('附录一 问题一补充推导与复现设置',1,True)
ap('一 固定领域质量下的识别限制',2)
ac('当');ae(29,'附1-1')
ac('故不能从此参数化中唯一分离');ae(30,'附1-2')
ap('式（附1-2）在固定总训练量、固定领域质量及正份额条件下，将质量项吸收到截距中。该结论针对未平滑的可分对数有效数据量形式，不直接推广到所有模型或共同平滑常数下的质量乘性参数化。更根本的限制是现有实验没有在相同配比下独立改变质量并观测损失。')
ap('补充分析仅在具有实际参考映射的领域上，比较领域参考质量与对数主模型系数的Pearson相关和Spearman秩相关；均值回填域不作为独立质量测量点。相关分析用于解释给定映射下的领域差异，不承担因果识别。')
ap('二 约束最优性推导与辅助候选',2)
ap('正文式（5-31）的拉格朗日函数为：');ae(34,'附1-3')
ap('KKT条件，即约束最优点的一阶驻点、原始与对偶可行性及互补条件，包括份额非负、份额和为1、非负约束乘子非负、乘子与对应份额乘积为0，以及：');ae(35,'附1-4')
ap('在正文给出的凸性条件下，由上述条件得到式（5-32）。当前实现对λ采用初始区间[10⁻⁶,10³]，以几何中点更新200次；SLSQP的最大迭代次数为500，目标容差为10⁻¹²，并检查优化器成功与两种方法所得配比的最大分量差小于10⁻⁵。应同时核查份额和、非负性及目标值，不能仅凭优化器返回结果判定成功。')
ap('辅助候选由参数向量各分量均为0.7的Dirichlet分布生成50,000个配比，再加入全部训练配方、主模型候选、训练平均配比和均匀配比。当前实现直接使用非负且和为1的候选，不执行逐分量截断后再归一化。分别计算对数模型与GBM的预测名次，并定义折中候选：');ae(37,'附1-5')
ap('名次融合属于辅助启发式比较，不保证训练稳健性。最终采用的主配方为对数主模型约束最优解，而非该折中候选；两者均未经过新增实际训练验证。训练坐标范围只反映逐域观测范围，不能替代对联合配方支持范围的检查。')
ap('三 验证细节与复现流程',2)
ac('评分模块先检查')
ap('外层五折随机种子为0，内层为1。划分以完整配方及其13域损失为单位；所有待选参数仅在相应训练折内选择。主设置及其来源列于表附1-1。')
ap('同口径损失采用均方根误差与决定系数：');ae(38,'附1-6')
ap('配方排序采用Spearman秩相关系数，并列值以中秩处理：');ae(39,'附1-7')
ap('跨尺度模型可能存在整体损失偏移。检验散点上另拟合的直线只作事后描述，只有另设标定样本才能用于独立绝对误差评价；响应或预测近常数时，相关系数可能无定义，应保留缺失标记。')
ac('对 A12');ac('各尺度表可分别拟合')
ap('表附1-1 主设置、参数来源与核验方式')
param_table=deepcopy(next(n for n in segment if n.tag==tag('w:tbl') and text(n).startswith('模块参数或规则')))
def replace_cell(cell,s):
    pp=cell.find('w:p',NS)
    for child in list(pp):
        if child.tag!=tag('w:pPr'):pp.remove(child)
    sub(sub(pp,'w:r'),'w:t').text=s
    for extra in cell.findall('w:p',NS)[1:]:cell.remove(extra)
for row in param_table.findall('w:tr',NS):
    cells=row.findall('w:tc',NS)
    if text(cells[0])=='候选搜索':
        replace_cell(cells[2],'50,000；各分量0.7')
        replace_cell(cells[3],'单纯形可行性及超训练坐标范围检查')
    if text(cells[0])=='对数混料':
        replace_cell(cells[3],'训练内选参；保留固定检验集历史查看说明')
    if text(cells[0])=='冲突识别':replace_cell(cells[2],'r≤−0.30；20%/80%')
    if text(cells[0])=='GBM':replace_cell(cells[3],'外层训练折内选参；同划分折外比较')
app.append(param_table)
ap('表附1-2 问题一计算流程')
flow=deepcopy(next(n for n in segment if n.tag==tag('w:tbl') and text(n).startswith('步骤操作')))
app.append(flow)
ac('对后续质量成本')

# Compact the two appendix tables while keeping the inherited three-line style.
for table in (param_table, flow):
    for paragraph in table.xpath('.//w:tc/w:p', namespaces=NS):
        pp=paragraph.find('w:pPr', NS)
        if pp is None:
            pp=E.Element(tag('w:pPr'));paragraph.insert(0,pp)
        spacing=pp.find('w:spacing', NS)
        if spacing is None: spacing=sub(pp,'w:spacing')
        for k,v in {'before':'0','after':'0','line':'276','lineRule':'auto'}.items():
            spacing.set(tag('w:'+k),v)
        for run in paragraph.findall('w:r', NS):
            rp=run.find('w:rPr', NS)
            if rp is None: rp=E.Element(tag('w:rPr'));run.insert(0,rp)
            size=rp.find('w:sz', NS)
            if size is None:size=sub(rp,'w:sz')
            size.set(tag('w:val'),'22')

# Keep an equation/table with its immediately preceding introduction or caption.
for group in (main, app):
    for previous, current in zip(group, group[1:]):
        if current.tag == tag('w:tbl') and previous.tag == tag('w:p'):
            pp = previous.find('w:pPr', NS)
            if pp is None:
                pp = E.Element(tag('w:pPr')); previous.insert(0, pp)
            if pp.find('w:keepNext', NS) is None: sub(pp,'w:keepNext')
            if pp.find('w:keepLines', NS) is None: sub(pp,'w:keepLines')

for n in segment:b.remove(n)
for i,n in enumerate(main):b.insert(start+i,n)
app_index=len(b)-1
assert b[-1].tag==tag('w:sectPr')
for n in app:b.insert(len(b)-1,n)
after=list(b)
assert [canonical(n) for n in after[:start]]==[canonical(n) for n in old[:start]]
tail_start=start+len(main)
assert [canonical(n) for n in after[tail_start:app_index]]==[canonical(n) for n in old[end:-1]]
assert canonical(b[-1])==canonical(old[-1])
assert display_before==Counter(canonical(n) for n in r.xpath('.//m:oMathPara',namespaces=NS))
bookmarks=r.xpath('.//w:bookmarkStart/@w:id',namespaces=NS)
assert len(bookmarks)==len(set(bookmarks)), 'duplicate bookmark ids'
parts['word/document.xml']=E.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
    for info in infos:z.writestr(info,parts[info.filename])
assert sha(SRC)==source_hash
with ZipFile(SRC) as z:
    changed=[n for n in z.namelist() if z.read(n)!=parts[n]]
assert changed==['word/document.xml']
old_chars=sum(len(text(n)) for n in segment)
new_chars=sum(len(text(n)) for n in main)
report={'version':'v0.9.12','source':SRC.name,'source_sha256':source_hash,
 'output':OUT.name,'output_sha256':sha(OUT),'sources':used,
 'modified_sections':['5.8','5.9','5.10'],'other_body_nodes_unchanged':True,
 'all_original_display_equations_preserved':True,'all_other_zip_parts_unchanged':True,
 'source_unchanged':True,'main_candidate':'loglinear KKT optimum; rank fusion is supplementary',
 'corrected_implementation_notes':['Dirichlet parameter 0.71 → 0.7','No component clipping / renormalizing in current candidate generation'],
 'equation_number_map':equation_map,'old_body_characters':old_chars,
 'new_body_characters':new_chars,'body_reduction_percent':round(100*(1-new_chars/old_chars),1),
 'render_qa':'pending'}
(ROOT/'Q1/论文5.8至5.10精简正文.md').write_text('\n\n'.join(text(n) for n in main),encoding='utf-8')
(ROOT/'Q1/论文问题一补充附录.md').write_text('\n\n'.join(text(n) for n in app),encoding='utf-8')
(ROOT/'Q1/论文5.8至5.10精简核验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

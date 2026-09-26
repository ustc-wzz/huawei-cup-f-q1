"""Simplify only Q2 in the user-supplied paper and append reproducibility notes.

Usage: bundled-python rewrite_q2_paper.py SOURCE.docx [OUTPUT.docx]
Numerical results are read from existing CSV/JSON outputs; no model is refit.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from copy import deepcopy
import csv
import hashlib
import json
import re
import sys
from lxml import etree as E

ROOT = Path(__file__).resolve().parent
SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'F题论文初稿_问题二精简_20260926.docx'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}

def tag(name):
    prefix, local = name.split(':')
    return '{' + NS[prefix] + '}' + local

def el(name, **attrs):
    item = E.Element(tag(name))
    for key, value in attrs.items():
        item.set(tag('w:' + key), str(value))
    return item

def text_of(item):
    return ''.join(item.xpath('.//w:t/text() | .//m:t/text()', namespaces=NS))

with ZipFile(SRC) as archive:
    infos = archive.infolist()
    parts = {info.filename: archive.read(info.filename) for info in infos}
source_hash = hashlib.sha256(SRC.read_bytes()).hexdigest()
root = E.fromstring(parts['word/document.xml'])
body = root.find('w:body', NS)
old = list(body)
assert text_of(old[390]) == '问题二模型建立与求解'
assert text_of(old[635]) == '问题三模型建立与求解'
assert not any('PaperEq_6_' in t for item in old[:390] + old[635:]
               for t in item.xpath('.//w:instrText/text()', namespaces=NS))

data_dir = ROOT / 'output_q2_shared'
used_sources = {}

def read_rows(name):
    file = data_dir / 'tables' / (name + '.csv')
    used_sources[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    with file.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def pick(rows, **matches):
    selected = [row for row in rows if all(row[key] == value for key, value in matches.items())]
    assert len(selected) == 1, matches
    return selected[0]

def fmt(value, digits=4):
    return f'{float(value):.{digits}f}'

interface_file = data_dir / 'q2_interface.json'
interface = json.loads(interface_file.read_text(encoding='utf-8'))
used_sources[str(interface_file.relative_to(ROOT))] = hashlib.sha256(interface_file.read_bytes()).hexdigest()
classic = read_rows('classic_validation')
cross = read_rows('cross_source_validation')
quality = read_rows('quality_validation')
mixture = read_rows('mixture_validation')
uncertainty = read_rows('conditional_uncertainty')
substitution = read_rows('quality_parameter_substitution')
combination = read_rows('domain_combination_effects')
candidates = read_rows('mixture_candidates')
b8 = read_rows('quality_B8_sensitivity')
audit = read_rows('quality_direction_audit')
improvement = read_rows('paired_group_improvement')
estimated = read_rows('estimated_loss_consistency')
q = pick(quality, 检验='ND组合五折留出', 模型='共同指数修正')
q0 = pick(quality, 检验='ND组合五折留出', 模型='无质量项')
m = pick(mixture, 模型='共同配比修正', 检验='配方分组五折-全部')
m0 = pick(mixture, 模型='无配比项', 检验='配方分组五折-全部')

new = []
appendix = []
plain = []
target = new
equation_counts = {'6': 0, '附2': 0}
table_counts = {'6': 0, '附2': 0}
section = '6'
equation_map = []
equation_nodes = []

def scrub(item):
    for child in item.iter():
        for key in list(child.attrib):
            if E.QName(key).localname in ('paraId', 'textId', 'rsidR', 'rsidRDefault', 'rsidP', 'rsidTr', 'rsidRPr'):
                del child.attrib[key]
    for child in list(item.xpath('.//w:bookmarkStart | .//w:bookmarkEnd | .//w:lastRenderedPageBreak', namespaces=NS)):
        child.getparent().remove(child)
    return item

def math_run(text):
    node = E.Element(tag('m:r'))
    t = E.SubElement(node, tag('m:t'))
    t.text = text
    return node

def math_sub(base, index):
    node = E.Element(tag('m:sSub'))
    E.SubElement(node, tag('m:e')).append(math_run(base))
    E.SubElement(node, tag('m:sub')).append(math_run(index))
    return node

def scale_term(coefficient, base, exponent):
    node = E.Element(tag('m:box'))
    content = E.SubElement(node, tag('m:e'))
    content.append(math_sub(coefficient, 'r'))
    power = E.SubElement(content, tag('m:sSup'))
    E.SubElement(power, tag('m:e')).append(math_sub(base, 'B'))
    E.SubElement(power, tag('m:sup')).append(math_run(exponent))
    return node

inline = {word: math_sub(base, index) for word, base, index in [
    ('N_B', 'N', 'B'), ('D_B', 'D', 'B'), ('q_B', 'q', 'B'), ('s_Q', 's', 'Q'),
    ('θ_Q', 'θ', 'Q'), ('η_p', 'η', 'p'), ('Q_0', 'Q', '0'), ('p_0', 'p', '0'),
    ('s_L', 's', 'L'), ('E_r', 'E', 'r'), ('A_r', 'A', 'r'), ('B_r', 'B', 'r'),
    ('R_r', 'R', 'r'), ('T_N', 'T', 'N'), ('T_D', 'T', 'D'), ('E_A', 'E', 'A'),
    ('A_A', 'A', 'A'), ('B_A', 'B', 'A'), ('q_i', 'q', 'i'), ('a_i', 'a', 'i'),
    ('p_i', 'p', 'i'), ('ε_p', 'ε', 'p'), ('I_ik', 'I', 'ik')
]}
inline.update({'A_rN_B^(−α)': scale_term('A', 'N', '−α'),
               'B_rD_B^(−ν)': scale_term('B', 'D', '−ν'),
               'ρ_Q': math_sub('ρ', 'Q'), 'N′_B': math_sub('N′', 'B'),
               'e_k': math_sub('e', 'k'), 'e_i': math_sub('e', 'i'),
               'C_A': math_sub('C', 'A'), 'R_m': math_sub('R', 'm'),
               'c_r': math_sub('c', 'r')})
inline_pattern = re.compile('|'.join(re.escape(key) for key in sorted(inline, key=len, reverse=True)))

def add_text(parent, text, run_properties=None):
    def add_run(value):
        if not value:
            return
        run = el('w:r')
        if run_properties is not None:
            run.append(deepcopy(run_properties))
        t = el('w:t')
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        t.text = value
        run.append(t)
        parent.append(run)
    start = 0
    for match in inline_pattern.finditer(text):
        add_run(text[start:match.start()])
        math = E.Element(tag('m:oMath'))
        math.append(deepcopy(inline[match.group()]))
        parent.append(math)
        start = match.end()
    add_run(text[start:])

def paragraph(text, role='body', page_break=False):
    template = old[{'body': 391, 'h1': 390, 'h2': 392, 'h3': 393, 'caption': 405}[role]]
    node = el('w:p')
    prop = template.find('w:pPr', NS)
    prop = deepcopy(prop) if prop is not None else el('w:pPr')
    node.append(prop)
    if role == 'body':
        prop.append(el('w:widowControl'))
    if role.startswith('h') or role == 'caption':
        for item in prop.findall('w:keepNext', NS):
            prop.remove(item)
        prop.append(el('w:keepNext'))
    if section == '附2' and role.startswith('h'):
        for item in prop.findall('w:numPr', NS):
            prop.remove(item)
        numbering = el('w:numPr')
        numbering.append(el('w:numId', val=0))
        prop.append(numbering)
    if page_break and prop.find('w:pageBreakBefore', NS) is None:
        prop.append(el('w:pageBreakBefore'))
    add_text(node, text, template.find('w:r/w:rPr', NS))
    target.append(node)
    plain.append(('## ' if role.startswith('h') else '') + text)
    return node

def equation(source_index):
    equation_counts[section] += 1
    label = f'{section}-{equation_counts[section]}'
    node = scrub(deepcopy(old[source_index]))
    assert node.tag == tag('w:tbl')
    cells = node.findall('w:tr/w:tc', NS)
    assert len(cells) == 3
    if section == '附2':
        for col, cell, width in zip(node.findall('w:tblGrid/w:gridCol', NS), cells, [1100, 6872, 1100]):
            col.set(tag('w:w'), str(width))
            cell.find('w:tcPr/w:tcW', NS).set(tag('w:w'), str(width))
    # Retain editable mathematics; replace the old SEQ field and its cached label.
    number_cell = cells[-1]
    for child in list(number_cell):
        if child.tag != tag('w:tcPr'):
            number_cell.remove(child)
    p = el('w:p')
    prop = el('w:pPr')
    prop.append(el('w:pStyle', val='-'))
    prop.append(el('w:jc', val='right'))
    p.append(prop)
    add_text(p, '(' + label + ')')
    number_cell.append(p)
    if target and target[-1].tag == tag('w:p'):
        prop = target[-1].find('w:pPr', NS)
        if prop is None:
            prop = el('w:pPr')
            target[-1].insert(0, prop)
        if prop.find('w:keepNext', NS) is None:
            prop.append(el('w:keepNext'))
    target.append(node)
    plain.append(f'[公式{label}] ' + ''.join(node.xpath('.//m:t/text()', namespaces=NS)))
    equation_map.append({'source_body_index': source_index, 'new_label': label})
    equation_nodes.append(node)
    return label

def table(title, headers, rows, widths):
    assert sum(widths) == 9072
    table_counts[section] += 1
    paragraph(f'表{section}-{table_counts[section]}  {title}', 'caption')
    node = el('w:tbl')
    prop = deepcopy(old[406].find('w:tblPr', NS))
    borders = prop.find('w:tblBorders', NS)
    for border in borders:
        border.set(tag('w:val'), 'single')
        border.set(tag('w:sz'), '4')
        border.set(tag('w:color'), 'D9D9D9')
    node.append(prop)
    grid = el('w:tblGrid')
    for width in widths:
        grid.append(el('w:gridCol', w=width))
    node.append(grid)
    for ri, values in enumerate([headers] + rows):
        row = el('w:tr')
        rp = el('w:trPr')
        rp.append(el('w:cantSplit'))
        if ri == 0:
            rp.append(el('w:tblHeader'))
        row.append(rp)
        for ci, (value, width) in enumerate(zip(values, widths)):
            cell = el('w:tc')
            cp = el('w:tcPr')
            cp.append(el('w:tcW', w=width, type='dxa'))
            cp.append(el('w:vAlign', val='center'))
            margins = el('w:tcMar')
            for side, size in [('top', 75), ('bottom', 75), ('left', 90), ('right', 90)]:
                margins.append(el('w:' + side, w=size, type='dxa'))
            cp.append(margins)
            if ri == 0:
                cp.append(el('w:shd', val='clear', fill='F2F2F2'))
            cell.append(cp)
            p = el('w:p')
            pp = el('w:pPr')
            pp.append(el('w:pStyle', val='-'))
            pp.append(el('w:jc', val='left' if ci == 0 else 'center'))
            pp.append(el('w:spacing', before=0, after=0, line=260, lineRule='auto'))
            if ri < len(rows):
                pp.append(el('w:keepNext'))
            p.append(pp)
            rpr = el('w:rPr')
            rpr.append(el('w:sz', val=22))
            rpr.append(el('w:szCs', val=22))
            if ri == 0:
                rpr.append(el('w:b'))
            add_text(p, str(value), rpr)
            cell.append(p)
            row.append(cell)
        node.append(row)
    target.append(node)
    plain.append('| ' + ' | '.join(headers) + ' |')
    plain.extend('| ' + ' | '.join(map(str, row)) + ' |' for row in rows)

# Retain the original chapter heading and its hidden chapter counter.
new.append(deepcopy(old[390]))
# Preserve the chapter counter while preventing its hidden result from printing.
in_field = False
for run in new[0].findall('w:r', NS):
    field = run.find('w:fldChar', NS)
    if field is not None and field.get(tag('w:fldCharType')) == 'begin':
        in_field = True
    if in_field:
        rp = run.find('w:rPr', NS)
        if rp is None:
            rp = el('w:rPr'); run.insert(0, rp)
        rp.append(el('w:vanish'))
    if field is not None and field.get(tag('w:fldCharType')) == 'end':
        in_field = False
plain.append('# 问题二模型建立与求解')
paragraph('本问沿“规模基线→质量与配比修正→验证及资源替代”建立统一损失模型，比较质量提升与规模扩张的效果。跨来源校准用于检验适用性，计算设置与辅助诊断列于附录二。')
paragraph('质量与配比共同修正的统一模型', 'h2')
paragraph('参数量与训练数据量分别记为N_B、D_B，均以十亿为单位；p为17个领域的训练份额向量，各分量非负且总和为1。以r区分验证语料、分词与训练设置不同的实验来源，建立损失预测关系：')
equation(422)
paragraph('E_r为损失下限，括号内为可约损失，即模型中可随资源增加而减小的部分；α、ν为规模指数。共同修正＝质量与配比通过同一乘子M作用于两个规模项，λ、η_p分别表示其响应强度。观测损失等于预测值加未解释偏差。')
paragraph('为承接第一问，冻结对数线性配比模型f(p)=c+Σa_i ln(p_i+ε_p)，其中c、a_i、ε_p分别为已估截距、领域系数和平滑常数。以训练平均配比p_0及13域平均损失的总体标准差s_L为参照，定义：')
equation(429)
paragraph('q_i为第一问映射后的配方域质量，u=Q−Q_0(p)为同配比下额外提高的质量。原配方实验取u=0，避免重复计入配比变化已有的质量差异。h(p)保留第一问配比排序；p=p_0且u=0时，模型恢复经典形式。')
paragraph('模型假设来源间共享规模指数、允许基准与幅度不同；质量与配比共同修正两个规模项；两类响应在指数中相加，不另设联合项。附件分别提供规模、质量和配方实验，因此采用分阶段估计；联合使用与迁移的限制集中在结果讨论中说明。')

paragraph('分阶段参数估计与验证', 'h2')
paragraph('规模基线与跨来源验证', 'h3')
paragraph('首先在B1的1176条Pythia训练记录上估计五个规模参数，记ϑ=(E,A,α,B,ν)。用对数残差衡量预测与观测的相对偏差：')
equation(444)
paragraph('采用Huber损失，即小残差按平方、大残差按绝对值增长的稳健目标，求解：')
equation(446)
paragraph('检查点具有轨迹相关性，故每次完整留出一种参数规模，用其余规模拟合并预测。B2、B4、B5作为跨来源验证：B2按规模划分校准与检验集，B4/B5在来源内部留一，比较直接迁移与来源校准；形式见附录二。')
par = interface['B1']
paragraph(f'估计得到E={par["E"]:.6f}、A={par["A"]:.6f}、B={par["B"]:.6f}、α={par["alpha"]:.6f}、ν={par["nu"]:.6f}。B1的8次留规模检验中，均方根误差RMSE（预测误差平方平均后开方）的最大值为{max(float(row["RMSE"]) for row in classic[1:]):.6f}，表明该形式能够描述给定轨迹内的规模变化。')
cross_rows = []
for dataset, direct, calibrated in [('B2', '直接迁移到留出规模', '共享指数+幅度校准'),
                                  ('B4', '直接迁移：来源内留一', '偏移+幅度：来源内留一'),
                                  ('B5', '直接迁移：来源内留一', '偏移+幅度：来源内留一')]:
    a = pick(cross, 数据=dataset, 方法=direct)
    b = pick(cross, 数据=dataset, 方法=calibrated)
    cross_rows.append([dataset + ('（半合成）' if dataset == 'B2' else ''), a['n'], fmt(a['RMSE']), fmt(b['RMSE'])])
table('跨来源验证的损失预测误差', ['数据', '检验记录数', '直接迁移RMSE', '校准后RMSE'], cross_rows, [2400, 1600, 2536, 2536])
paragraph('校准后三组误差均降低，支持调整损失基准与幅度后使用相同规模形状。B4/B5需要少量同来源记录，不代表未知来源的直接泛化。后续主配置采用B1基线，其他来源的校准参数仅用于验证。')

paragraph('质量修正的估计与预测改善', 'h3')
paragraph('附件B质量变量q_B与第一问评分Q采用不同刻度。以q_B=1为参照，用正斜率s_Q联系质量增量：')
equation(467)
paragraph('在质量实验的基线配比下，固定B1已估参数，质量模型为：')
equation(469)
paragraph('利用B7去重后的450条记录，以原始损失的约束最小二乘估计θ_Q；R_m为第m条记录的B1可约损失：')
equation(474)
paragraph('按(N_B,D_B)组合实施五折分组验证，同一组合的各质量等级始终放在同一折，并与θ_Q=0的无质量项模型比较。另用B6估计系数，预测B7中未出现于B6的90条记录，以检查新增质量组合。')
qi = pick(uncertainty, 参数='theta_Q')
paragraph(f'得到θ_Q={float(qi["估计"]):.6f}，条件95%区间为[{float(qi["2.5%"]):.6f}, {float(qi["97.5%"]):.6f}]。分组验证RMSE由{float(q0["RMSE"]):.6f}降至{float(q["RMSE"]):.6f}，降低{100*(1-float(q["RMSE"])/float(q0["RMSE"])):.1f}%；B6预测B7新增组合的RMSE为{float(pick(quality, 检验="B6→B7新增质量", 模型="共同指数修正")["RMSE"]):.6f}。这一结果支持在B7半合成情景内加入质量响应项。')

paragraph('配比修正的估计与跨尺度检验', 'h3')
paragraph('配比阶段继承第一问的h(p)，固定B1规模指数，并对A6—A11的配方实验取u=0。允许配方来源拥有独立幅度，建立：')
equation(495)
paragraph('令t=(lnE_A,lnA_A,lnB_A,η_p)，最小化配方校准集C_A上的损失残差平方和：')
equation(497)
paragraph('约束集合T保证幅度为正、η_p非负，具体边界见附录二。1M与60M实验按元数据匹配为1B Token，1B实验为25B Token。五折验证按完整17维配方分组，同配方跨尺度记录保持在同一折；另每次完整留出一个模型尺度。无配比项对照固定η_p=0，但重新估计三个幅度参数。')
mi = pick(uncertainty, 参数='eta')
reg = interface['RegMix']
paragraph(f'估计得到E_A={reg["E"]:.6f}、A_A={reg["A"]:.6f}、B_A={reg["B"]:.6f}、η_p={float(mi["估计"]):.6f}，η_p的条件95%区间为[{float(mi["2.5%"]):.6f}, {float(mi["97.5%"]):.6f}]。576条配方记录的分组验证RMSE由{float(m0["RMSE"]):.6f}降至{float(m["RMSE"]):.6f}，降低{100*(1-float(m["RMSE"])/float(m0["RMSE"])):.1f}%。')
mix_rows = []
for name in ['test_1M', 'test_60M', 'test_1B']:
    a = pick(mixture, 模型='共同配比修正', 检验='配方分组五折-' + name)
    b = pick(mixture, 模型='共同配比修正', 检验='留尺度-' + name)
    mix_rows.append([name.removeprefix('test_'), a['n'], fmt(a['RMSE']), fmt(b['RMSE'])])
table('配方泛化与完整尺度留出的区别', ['模型规模', '记录数', '配方分组RMSE', '完整留尺度RMSE'], mix_rows, [1700, 1300, 2936, 3136])
paragraph('配比项改善了已覆盖尺度内的预测，但完整留尺度误差明显增大，1M留出时达到5.8746。模型可用于已覆盖条件下的配方比较，不能据此保证未覆盖尺度的绝对预测。配方数据已参与第一问检查，此处属于事后迁移诊断。')

paragraph('资源替代分析与适用范围', 'h2')
paragraph('参数规模 数据规模与质量的边际作用', 'h3')
paragraph('记T_N=A_rN_B^(−α)、T_D=B_rD_B^(−ν)，R_r=T_N+T_D，M=exp(−λu+η_p h(p))。边际效用＝其他条件固定时，某项资源增加一个单位带来的局部损失下降。对统一模型求导，有：')
equation(509)
equation(511)
paragraph('前两项分别按每十亿参数、每十亿Token计量，质量项按第一问评分的一分计量。为比较局部相对变化，规模变量采用损失弹性：')
equation(515)
paragraph('由于Q可以为负，质量采用半弹性，即质量增加一个评分单位对应的局部损失相对变化：')
equation(518)
paragraph('三种边际量的单位不同，投入优先级还需结合成本；完整预算约束下的资源配置留待第三问求解。')

paragraph('质量提高对应的参数替代', 'h3')
paragraph('固定数据量、配比与来源，比较“原参数量下质量提高Δu”和“原质量下参数量扩大到N′_B”两种方案。令ρ_Q=exp(−λΔu)，由两方案损失相等得到：')
equation(531)
paragraph('z>0时存在有限参数替代；z=0时只有参数量趋于无穷才达到；z<0时参数扩张无法达到同样收益，因为单独扩大参数仍留下固定数据量对应的损失项。表6-3以B1基线、参考配比p_0和Δu=0.1展示三种质量刻度情景。')
sub_rows = []
for n, d in [('1.0', '20.0'), ('7.0', '140.0'), ('70.0', '1400.0')]:
    values = [fmt(pick(substitution, N_B=n, D_B=d, s_Q情景=s)['等价参数倍数'], 3)
              for s in ['0.5', '1.0', '2.0']]
    sub_rows.append([f'{float(n):g} / {float(d):g}'] + values)
table('质量提高0.1对应的等损失参数倍数', ['N_B / D_B', 's_Q=0.5', 's_Q=1', 's_Q=2'], sub_rows, [2472, 2200, 2200, 2200])
paragraph('例如在7B参数、140B Token与s_Q=1情景下，质量提高0.1相当于将参数量扩大到1.386倍；将刻度改为0.5或2时，倍数分别变为1.972和1.174。该比较固定数据量，不固定总算力；正质量增量向q_B=1参照点之外延伸，属于条件情景外推。')

paragraph('领域替代与训练前沿', 'h3')
paragraph('配比调整必须保持份额总和为1。固定额外质量u，从领域i向领域k转移δ份额，即p′=p+δ(e_k−e_i)，其中e_i为第i个坐标单位向量、0≤δ≤p_i。该方向的局部损失变化为：')
equation(551)
paragraph('导数为负表示该转移方向有利。固定N_B、D_B、u和来源且η_p>0时，损失随f(p)严格递增，相同可行集上可继承第一问的候选最优配比。')
base_candidate = pick(candidates, 方案='训练平均配比')
best_candidate = pick(candidates, 方案='对数线性KKT配比')
paragraph(f'在7B参数、140B Token、u=0的B1口径情景中，从训练平均配比改为第一问候选配比，预测损失由{float(base_candidate["广义Loss_情景"]):.6f}降至{float(best_candidate["广义Loss_情景"]):.6f}。此数值来自两个来源模型的连接，不是新完成的训练实验。')
paragraph('为比较两个领域同时增加的效果，以pile_cc为共同补偿域，分别记两个可行转移方向为v和w，定义组合差：')
equation(567)
assert len(combination) == 360 and all(float(row['广义条件交互_情景']) > 0 for row in combination)
paragraph('在参考配比及δ=0.001、0.005、0.01下，360组组合差均为正。当两次单独调整均降低损失时，正组合差表示联合收益小于两次单独收益之和。该结果受共同补偿域及指数链接曲率影响，不支持将其解释为独立识别的领域因果互补。')
paragraph('仅计训练成本C=6×10¹⁸N_B D_B且固定质量、配比时，共同乘子在最优条件中抵消，得到αT_N=νT_D。因此质量改善会降低损失水平，却不改变这一条件下的最优参数—数据分配；解析解与提质成本判据列于附录二。第三问再把质量处理与注意力开销纳入总预算。')

paragraph('结果的适用范围', 'h3')
paragraph('现有证据支持在给定实验条件内，用质量和配比修正改善损失预测，并进行资源替代的条件计算。解释范围由三项限制决定：其一，B6/B7为半合成质量实验，B8呈相反方向，质量效果尚缺统一真实实验验证；其二，数据仅识别θ_Q=λs_Q，两套质量刻度未实测对齐，s_Q=0.5、1、2均为情景设定；其三，质量与配比分别估计，联合修正及配比系数迁移到B1基线仍是假设，完整留尺度结果也显示绝对预测的局限。')
paragraph('第三问继承B1参数、θ_Q、η_p及第一问接口，指定s_Q后由λ=θ_Q/s_Q计算条件收益。附录二给出不确定性计算；所得区间不覆盖未知质量刻度与联合迁移风险。')

main_plain_end = len(plain)
target = appendix
section = '附2'
paragraph('附录二 问题二的估计设置与辅助检验', 'h1', page_break=True)
paragraph('本附录保留第二问的可复现设置、辅助诊断和补充推导。正文中的估计参数及验证结果均来自同一套计算；下述实现设置不构成额外的模型估计结果。')
paragraph('一 数据处理与跨来源校准', 'h2')
paragraph('读取后统一参数量与训练量的十亿单位，核对规模和损失的有限正值、记录数及重复组合。B1按完整模型规模留出，避免同轨迹检查点随机拆行。B11为模型族元数据、B12为检查点索引，用于辅助读取与覆盖记录；当前计算未逐条完成原始实验追溯。')
paragraph('B2将唯一参数规模排序，交替分配到校准集与检验集。共享指数方案固定B1的α、ν，仅以非负最小二乘估计幅度b=(E₂,A₂,B₂)：')
equation(456)
paragraph('自由指数对照在同一校准集重新估计全部五个参数，其检验RMSE为0.010794，共享指数方案为0.010773。前者使用对数Huber目标，后者使用原始损失最小二乘，因此该对照同时改变了参数约束与估计准则，不能把微小误差差异完全归因于指数共享。')
paragraph('B4按family、B5按source分组，对至少含3条记录的来源逐条留一，并仅用该来源其余记录估计校准参数。以R表示B1基线的可约损失，比较：')
equation(460)
paragraph('仅偏移方案取E_r=max{0,mean(L−R)}；偏移与幅度方案以非负最小二乘估计E_r和c_r，相当于A_r=c_r A、B_r=c_r B。少于3条记录的来源仅保留直接迁移诊断；来源内校准与整来源留出具有不同含义。')
paragraph('质量实验按(N_B,D_B,q_B)去重。B6与B7的重叠组合逐项核对损失一致性，B6→B7检验排除所有重叠组合。B7按(N_B,D_B)的45个组实施五折验证。配方分组以完整17维向量四舍五入到小数点后10位为键，同配方跨尺度归入同折。A组的训练Token量来自RegMix元数据匹配，而非CSV逐运行直接记录。')
paragraph('二 数值设置与条件不确定性', 'h2')
table('估计器与搜索设置', ['阶段', '估计准则', '边界与求解设置'], [
    ['B1规模', '对数Huber；δ=0.01', 'lnE∈[−12,4]；lnA、lnB∈[−12,8]；α、ν∈[0.01,1.5]；6起点，最多3000次评价'],
    ['规模对照与留出', '普通对数最小二乘或同一Huber目标', '最小二乘对照3起点；留规模拟合2起点'],
    ['质量θ_Q', '原始损失最小二乘', '初值0.3；[0,8]；最多2000次评价；B8有符号对照取[−8,8]'],
    ['配比', '原始损失最小二乘', '三个幅度对数∈[−12,5]；η_p∈[0,3]；η_p初值在0.02—0.8间取5点；最多3000次评价']
], [1700, 2500, 4872])
paragraph('B1三个正幅度以对数参数化，首起点为(ln1.5, ln0.4, 0.3, ln1.2, 0.3)，其余起点按固定随机数采样；取目标值最小者。配比幅度初值为(1.3,0.15,1.6)，多起点仅改变η_p。NumPy初始随机种子为925，复现时保持调用顺序。')
paragraph('条件参数区间采用整组自助重采样，即按组有放回抽样并保留组内全部记录：质量按(N_B,D_B)组抽样80次并重估θ_Q；配比按完整配方组抽样50次，每次重估四个配比参数。以参数样本的2.5%和97.5%分位形成95%区间。两类抽样分别执行，不把抽样行号配对为联合后验。')
paragraph('预测改善区间固定已有折外预测，先逐组汇总“无修正平方误差减去有修正平方误差”，再对组重采样1000次，按总误差差除以总记录数计算。质量MSE改善为0.039104，95%区间[0.032879,0.046249]；配比为0.047297，区间[0.037046,0.058225]。此处MSE为均方误差，区间未在每次抽样中重训整个建模流程。')
paragraph('所有区间条件于B1规模参数、第一问冻结模型及附件采样机制，不包含完整上游误差传播、未知s_Q和联合迁移不确定性。')
paragraph('三 辅助数据诊断与敏感性', 'h2')
paragraph('B3为插值轨迹，B9为大模型元数据，B10为估算损失。三者分别承担插值一致性、元数据情景预测及估算值一致性检查，不与独立真实训练验证混用。B9仅对参数量与训练量均为有限正数的记录输出B1口径基线预测，其他记录保留缺失。')
table('辅助一致性检查', ['数据', '性质与比较对象', '结果'], [
    ['B3', '插值轨迹与冻结B1模型', '4000条；RMSE=0.003817'],
    ['B9', '大模型元数据上的基线情景', '无实测损失，不计算预测准确率'],
    ['B10', '估算损失与B1基线', f'RMSE={float(estimated[0]["RMSE"]):.6f}；仅一致性对照']
], [1200, 3900, 3972])
paragraph('B8共有150个(N_B,D_B)组，质量与损失的组内Spearman相关中位数为0.992982，与B7的负方向不同。B8在非负约束下θ_Q触及0，RMSE为1.182455；允许有符号系数时θ_Q=−7.650495、RMSE为0.723406。合并B7+B8时，非负系数同样触及0；有符号估计为−4.820256。该冲突保留为数据口径或模型适用性问题，不预设为已证实的数据错误。')
paragraph('质量刻度取s_Q∈{0.5,1,2}，分别令λ=θ_Q/s_Q。规模指数另各乘0.8、1、1.2形成9个情景，固定扰动指数后在B1上以非负最小二乘重估E、A、B，再检查大规模损失与替代量。该情景包络不等同于95%预测区间。')
paragraph('四 资源效应的补充公式与核验', 'h2')
paragraph('参数扩大k倍对应的反向等价质量增量为：')
equation(540)
paragraph('有限参数替代要求λ>0且质量增量低于下列临界值；达到临界值时只存在无限参数极限：')
equation(536)
paragraph('若增加领域i的份额、其余领域按当前相对份额补偿，可定义以下约束弹性；其适用条件为p_i<1：')
equation(557)
paragraph('正文固定额外质量u。若固定绝对评分Q，配比变化还会改变Q_0(p)，从领域i向领域k转移时需增加质量基准项，得到：')
equation(563)
paragraph('在相同可行集、固定u且η_p>0时，第一问配比最小点的传递关系为：')
equation(572)
paragraph('仅计训练成本且固定质量与配比，令K=C/(6×10¹⁸)，由αT_N=νT_D得到条件最优分配：')
equation(583)
paragraph('若另计每Token质量处理成本g(Q)，并暂不计注意力开销，以原始计数N、D表示总成本：')
equation(588)
paragraph('在提质成本已激活且g′(Q)>0时，质量相较参数扩张具有更高局部单位算力收益的条件为：')
equation(590)
paragraph('此式N为原始参数个数，即10⁹N_B；g必须按当前Q刻度定义。第三问若采用变换后的成本自变量，需按链式法则换算导数。')
paragraph('程序以中心有限差分核对参数、数据、质量及一个可行配比方向的解析导数：')
equation(611)
paragraph('规模与质量方向步长取10⁻⁵max(1,x)，相对误差阈值10⁻⁵；配比方向步长10⁻⁶。有限替代值代回原损失函数检查等损失关系，并检查临界边界符号。训练前沿在10²⁰、10²²、10²⁴ FLOPs下以一维数值优化核对解析解。上述检查均通过，验证的是公式与程序实现的一致性。')

# Patch only the requested chapter; append notes before the original terminal section.
for item in old[390:635]:
    body.remove(item)
for offset, item in enumerate(new):
    body.insert(390 + offset, scrub(item) if offset else item)
for item in appendix:
    body.insert(len(body) - 1, scrub(item))
parts['word/document.xml'] = E.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
settings = E.fromstring(parts['word/settings.xml'])
update = settings.find('w:updateFields', NS)
if update is None:
    update = el('w:updateFields')
    settings.append(update)
update.set(tag('w:val'), 'true')
parts['word/settings.xml'] = E.tostring(settings, xml_declaration=True, encoding='UTF-8', standalone=True)
with ZipFile(OUT, 'w', ZIP_DEFLATED) as archive:
    for info in infos:
        archive.writestr(info, parts[info.filename])

with ZipFile(SRC) as source_zip, ZipFile(OUT) as output_zip:
    assert source_zip.namelist() == output_zip.namelist()
    changed_parts = [name for name in source_zip.namelist() if source_zip.read(name) != output_zip.read(name)]
    assert set(changed_parts) <= {'word/document.xml', 'word/settings.xml'}
    final_root = E.fromstring(output_zip.read('word/document.xml'))
    final_body = list(final_root.find('w:body', NS))
    assert all(E.tostring(a) == E.tostring(b) for a, b in zip(old[:390], final_body[:390]))
    start = 390 + len(new)
    retained_suffix = old[635:-1]
    assert all(E.tostring(a) == E.tostring(b) for a, b in zip(retained_suffix, final_body[start:start + len(retained_suffix)]))
    assert E.tostring(old[-1]) == E.tostring(final_body[-1])
    assert len(final_root.xpath('.//w:sectPr', namespaces=NS)) == len(root.xpath('.//w:sectPr', namespaces=NS))
    # All new display formulas preserve the mathematical tree from the source.
    for mapping, node in zip(equation_map, equation_nodes):
        source_math = old[mapping['source_body_index']].xpath('.//m:oMath', namespaces=NS)
        final_math = node.xpath('.//m:oMath', namespaces=NS)
        assert [E.tostring(x, method='c14n', exclusive=True) for x in source_math] == [E.tostring(x, method='c14n', exclusive=True) for x in final_math], mapping
    assert output_zip.testzip() is None
assert hashlib.sha256(SRC.read_bytes()).hexdigest() == source_hash

main_chars = sum(len(text_of(item)) for item in new)
old_chars = sum(len(text_of(item)) for item in old[390:635])
report = {
    'version': 'v0.9.10', 'source_name': SRC.name, 'source_sha256': source_hash,
    'output': OUT.name, 'output_sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
    'changed_package_parts': changed_parts, 'original_unchanged': True,
    'other_chapters_preserved': True, 'model_recomputed': False,
    'old_q2_body_elements': 245, 'new_q2_body_elements': len(new), 'appendix_body_elements': len(appendix),
    'old_q2_text_characters': old_chars, 'new_q2_text_characters': main_chars,
    'main_text_reduction_percent': round(100 * (1 - main_chars / old_chars), 2),
    'editable_display_equations': equation_counts, 'result_tables': table_counts,
    'equation_source_map': equation_map, 'numerical_sources_sha256': used_sources,
    'render_qa': 'pending'
}
(ROOT / 'Q2/论文第二问精简正文.md').write_text('\n\n'.join(plain[:main_plain_end]), encoding='utf-8')
(ROOT / 'Q2/论文第二问实现附录.md').write_text('\n\n'.join(plain[main_plain_end:]), encoding='utf-8')
(ROOT / 'Q2/论文第二问精简核验.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in report.items() if key not in ('equation_source_map', 'numerical_sources_sha256')}, ensure_ascii=False, indent=2))

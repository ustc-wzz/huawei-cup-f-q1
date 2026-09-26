# %% [markdown]
# # 问题一：质量评价、冲突诊断与领域配比
#
# A1–A3 的22项质量信号 → 方向统一与A1参考映射 → 独特词20组长度校正、两项格式指标领域校准 → 平方相关去冗余赋权 → 指数凹聚合（β=0.25）。A2/A3沿用A1参考，评分可为负。
#
# A4–A15 的17域配比用于预测13个验证域平均损失。对数线性模型用于解释与约束优化，GBM用于预测对照；配比主模型不使用Q。A16用于质量域与配方域的映射。
#
# 顺序运行全部单元，结果保存至 `output_q1/length_domain_calibrated22/`。第1–3节建立模型，第4节检验，第5节汇总当前结果。

# %%
# ============ 0. 环境配置（只需运行一次） ============
import os, sys, json, lzma, glob, math, time, warnings, itertools, csv
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Rectangle, Patch
from matplotlib.lines import Line2D
import seaborn as sns
from scipy import stats
from scipy.special import logsumexp
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform
from scipy.optimize import minimize
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import FunctionTransformer, SplineTransformer, StandardScaler
from sklearn.model_selection import KFold

warnings.filterwarnings('ignore')
import logging
logging.getLogger('matplotlib').setLevel(logging.ERROR)          # 屏蔽 "does not have a glyph" 等字体日志
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
pd.set_option('display.width', 180)
pd.set_option('display.max_columns', 40)
pd.set_option('display.float_format', lambda v: '%.4f' % v)

# ---- 随包中文字体，Windows/macOS共用 ----
from repro_runtime import configure_fonts
configure_fonts()
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 110
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['savefig.bbox'] = 'tight'
plt.rcParams['svg.fonttype'] = 'none'
plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['axes.spines.top'] = False
plt.rcParams['axes.spines.right'] = False
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.color'] = '#E4E4E4'
plt.rcParams['grid.linewidth'] = 0.6
plt.rcParams['axes.edgecolor'] = '#555555'
plt.rcParams['axes.titleweight'] = 'bold'
plt.rcParams['font.size'] = 10

# ---- 统一配色（深蓝 / 青绿 / 珊瑚 / 金 / 紫灰） ----
C_NAVY, C_TEAL, C_CORAL, C_GOLD, C_PLUM, C_GREY = '#1F3A5F', '#2A9D8F', '#E76F51', '#E9C46A', '#6D597A', '#9E9E9E'
PALETTE = [C_NAVY, C_TEAL, C_CORAL, C_GOLD, C_PLUM, '#8AB17D', '#264653', '#B56576']
CMAP_DIV = sns.diverging_palette(230, 20, as_cmap=True)          # 蓝 - 白 - 红
CMAP_SEQ = sns.light_palette(C_NAVY, as_cmap=True)
CMAP_TC  = mpl.colors.LinearSegmentedColormap.from_list('tc', [C_TEAL, C_GOLD, C_CORAL])
RNG = np.random.default_rng(2026)

# ---- 路径 ----
BASE_DIR = Path('.').resolve()
def find_data_root():
    for c in [BASE_DIR / 'real_attachments' / 'A_data_value', BASE_DIR / 'A_data_value', BASE_DIR]:
        if (c / 'regmix_tables').is_dir():
            return c
    raise FileNotFoundError('未找到 A_data_value 目录，请把 notebook 放在 real_attachments 的上一级目录（F题/）下')
DATA = find_data_root()
REG = DATA / 'regmix_tables'
CACHE = DATA / 'signals_cache'
OUT = BASE_DIR / 'output_q1' / 'length_domain_calibrated22'; FIG = OUT / 'figures'; TAB = OUT / 'tables'
for d in (FIG, TAB, CACHE):
    d.mkdir(parents=True, exist_ok=True)

def savefig(name):
    FIG.mkdir(parents=True, exist_ok=True)
    stem = Path(name).stem
    number, content = stem[3:5], stem[6:]
    target = BASE_DIR / 'figures' / f'fig_{number}_{content}.png'
    target.parent.mkdir(parents=True, exist_ok=True)
    from figure_typography import format_math_labels
    format_math_labels(plt.gcf())
    plt.tight_layout()
    plt.savefig(target, dpi=300, bbox_inches='tight')
    plt.savefig(target.with_suffix('.svg'), bbox_inches='tight')
    plt.savefig(target.with_suffix('.pdf'), bbox_inches='tight')
    plt.savefig(FIG / name, dpi=300, bbox_inches='tight')

print('数据目录:', DATA)
print('输出目录:', OUT)

# %% [markdown]
# ## 1. 数据质量评价
#
# ### 1.1 流式读取与列表型指标的压缩规则
#
# A1 每行是一个 JSON 对象（27 字段：22 个质量指标 + `id, content, sub_path, _source_domain, _source_path`），A2/A3 为 24 字段（无 `content` 等）。A1 压缩后 ≈100 MB、解压后 ≈430 MB，其中绝大部分是 `content` 全文，因此采用 **`lzma.open` 逐行读取、边读边丢弃全文** 的方式，只保留建模需要的字段，内存占用与记录数成正比而与全文长度无关。
#
# 在真实文件中探查到 22 个指标里有 **14 个标量、8 个列表型**，8 个列表型字段的语义与压缩规则如下（压缩规则的选择原则：**保留原评分器的语义，可解释，且不引入人为阈值**）：
#
# | 字段 | 列表结构 | 语义 | 压缩规则 |
# |---|---|---|---|
# | `fineweb_edu` | `[s]` | FineWeb-Edu 教育价值回归分（0–5） | 取唯一元素 $s$ |
# | `fluency_en` | `[z_0, z_1]` | 英文流畅度二分类 logits | $p_1=\dfrac{e^{z_1}}{e^{z_0}+e^{z_1}}$，类别方向用数据校验（见 1.2） |
# | `ad_en` | `[z_0, z_1]` | 广告二分类 logits | 同上，取 $p_1$ 后用数据判断哪一类是"广告" |
# | `modernbert_cleanliness/readability/reasoning/professionalism` | `[z_0,\dots,z_5]` | ModernBERT 六级序数评分（0–5 级）logits | 期望等级 $E=\sum_{k=0}^{5} k\,\mathrm{softmax}(z)_k$，比 argmax 保留了类间不确定性 |
# | `qurater` | `[q_1,q_2,q_3,q_4]` | QuRating 原始四分量评分（writing style / required expertise / facts & trivia / educational value，同一 logit 尺度） | 四分量均值 $\bar q=\frac14\sum_k q_k$（四个分量另存，供敏感性分析） |
#
# 对 softmax，记二分类 logits 为 $(z_0,z_1)$，则 $p_1 = 1/(1+e^{z_0-z_1})$；对六类序数评分，$\mathrm{softmax}(z)_k = e^{z_k}/\sum_j e^{z_j}$，期望等级 $E\in[0,5]$。
#
# 读取方式：若 `signals_cache/` 中已有压缩缓存（约 25 MB）则直接读取，否则从原始 `.jsonl.xz` 流式生成缓存。**缓存不做任何抽样，记录数与原文件一一对应。**

# %%
# ============ 1.1 流式读取器 ============
from signal_cache import OUT_COLS, NUM_COLS, SCALAR_FIELDS, MB_FIELDS, open_any, raw_signal_paths
from signal_cache import load_signals as _load_signals

def load_signals(prefix, raw_paths, fixed_domain=None):
    return _load_signals(CACHE, prefix, raw_paths, fixed_domain)

RAW_A1, RAW_A2, RAW_A3 = raw_signal_paths(DATA)
print('原始文件: A1', [p.name for p in RAW_A1], '| A2', [p.name for p in RAW_A2], '| A3', [p.name for p in RAW_A3])

# %%
# ============ 1.1 读取 A1 / A2 / A3 全量记录 ============
t0 = time.time()
A1 = load_signals('A1_sample', RAW_A1)
A2 = load_signals('A2_arxiv', RAW_A2, fixed_domain='arxiv')
A3 = load_signals('A3_github', RAW_A3, fixed_domain='github')
A1['set'], A2['set'], A3['set'] = 'A1 抽样集', 'A2 扩展集(arxiv)', 'A3 扩展集(github)'
print('读取耗时 %.1fs' % (time.time() - t0))

print('\nA1 各域记录数:')
print(A1['domain'].value_counts().to_string())

# 缺失率（只看 22 个指标相关列）
miss = pd.DataFrame({'A1': A1[NUM_COLS[:25]].isna().mean(), 'A2': A2[NUM_COLS[:25]].isna().mean(), 'A3': A3[NUM_COLS[:25]].isna().mean()})
miss = miss[(miss > 0).any(axis=1)]
print('\n存在缺失的字段及缺失率（其余字段无缺失）:')
print((miss * 100).round(3).to_string() if len(miss) else '  无缺失')

# %% [markdown]
# ### 1.2 质量指标预处理与统一尺度
#
# 记样本为 $i$，指标为 $j\in\{1,\ldots,22\}$，A1参考样本集合为 $\mathcal A$，$n_A=|\mathcal A|$，领域标签为 $d_i$。A2、A3只应用A1已拟合的规则。以下区分原始指标 $x_{ij}$、方向效用 $v_{ij}$、归一化值 $u_{ij}$ 和最终正态分数 $Z_{ij}$。
#
# 列表信号按其字段含义压缩。令 $\pi_k(\boldsymbol\ell)=e^{\ell_k-\max_r\ell_r}/\sum_r e^{\ell_r-\max_r\ell_r}$，则二分类取 $\pi_1$，六级序数信号取 $\sum_{k=0}^5k\pi_k$，单元素教育评分取该元素，QuRating取四分量均值。三个DSIR信号均使用 $x_{ij}=\mathrm{DSIR}_{ij}/\max(n_{word,i},1)$。广告类别方向由A1网页域与学术域的均值对照确定，流畅度由arxiv与github对照确定，判定后对扩展集冻结；这属于代理方向判定，不能替代评分器标签说明。非有限指标值以对应A1有效值中位数填补，A1整列缺失则报错。
#
# * **正向型**（越大越好）：教育价值、流畅度、干净度、可读性、推理性、专业性、三个 DSIR 相似度、QuRating、一元词熵、独特词占比、行末标点占比，共 13 个；
# * **负向型**（越小越好）：广告概率、非字母词占比、高频 2-gram / 3-gram 字符占比、大写字母占比、数字字符占比，共 6 个；
# * **区间型**（落在合理区间最好）：词数、句子数、平均词长，共 3 个。词数与平均词长的合理区间取自 Gopher 规则（Rae et al., 2021：词数 50–100,000、平均词长 3–10 字符），句子数下限取 3、上限取 A1 的 95% 分位数。
#
# 正向型取 $v_{ij}=x_{ij}$，负向型取 $v_{ij}=-x_{ij}$。区间型先令 $t=\log_{10}(1+\max(x,0))$（词数、句子数），平均词长则令 $t=x$；把合理区间端点及A1的99.9%分位同步转换为 $t_l,t_h,t_m$，定义
#
# $$
# v(t)=\begin{cases}
# \operatorname{clip}(t/t_l,0,1),&t<t_l,\\
# 1,&t_l\le t\le t_h,\\
# \operatorname{clip}\left(1-\dfrac{t-t_h}{\max(t_m-t_h,10^{-9})},0,1\right),&t>t_h.
# \end{cases}
# $$
#
# 词数合理区间为 $[50,100000]$，句子数为 $[3,\operatorname{Quantile}_{0.95}^{A1}(n_{sent})]$，平均词长为 $[3,10]$。令 $a_j=\min_{l\in\mathcal A}v_{lj}$、$b_j=\max_{l\in\mathcal A}v_{lj}$，归一化为
#
# $$
# u_{ij}=\begin{cases}\operatorname{clip}\left(\dfrac{v_{ij}-a_j}{b_j-a_j},0,1\right),&b_j>a_j,\\0.5,&b_j=a_j.\end{cases}
# $$
#
# 三类参照分别为全局、长度条件及领域条件。独特词占比记为 $j_U$，格式指标集合为 $\mathcal J_F=\{\text{行末标点占比},\text{非字母词占比}\}$。A1有效词数的 $\ln(1+n_{word})$ 等频分组请求20组，重复分界删除，不拆分相同词数；不足500条的小组与相邻组合并，最终内部边界记为 $b_1^{len}<\cdots<b_{G-1}^{len}$。分组函数为
#
# $$
# g(i)=\sum_{r=1}^{G-1}\mathbf1\{\ln(1+n_{word,i})>b_r^{len}\},\qquad
# \mathcal A_g=\{l\in\mathcal A:g(l)=g\},\quad
# \mathcal A_d=\{l\in\mathcal A:d_l=d\}.
# $$
#
# 长度无效时用A1正有效词数中位数填补；超出A1长度范围仍落在首/末组并另行标记。样本 $i$、指标 $j$ 的参考集合为
#
# $$
# \mathcal R_{ij}=\begin{cases}
# \mathcal A_{g(i)},&j=j_U,\\
# \mathcal A_{d_i},&j\in\mathcal J_F,\\
# \mathcal A,&j\notin\{j_U\}\cup\mathcal J_F.
# \end{cases}
# $$
#
# 最终正态分数统一写为
#
# $$
# P_{ij}=\frac1{|\mathcal R_{ij}|}\sum_{l\in\mathcal R_{ij}}
# \left[\mathbf1(u_{lj}<u_{ij})+\frac12\mathbf1(u_{lj}=u_{ij})\right],\qquad
# Z_{ij}=\Phi^{-1}\!\left(\operatorname{clip}(P_{ij},\epsilon_A,1-\epsilon_A)\right),\quad
# \epsilon_A=\frac1{2n_A}.
# $$
#
# $\mathbf1$为条件成立取1的指示函数，$\Phi^{-1}$为标准正态分位函数；三类映射的截断量均使用全体A1的 $\epsilon_A$，不改用组样本量。格式指标只按领域分组，独特词只按长度分组，二者不叠加；其余19项含专业性使用全局参照。未知领域报错，不以全局分布偷偷回退。并列值保留中秩，不加噪声；该变换不保证连续或联合正态。图示量 $X_{ij}=(Z_{ij}+B_A)/(2B_A)$、$B_A=\Phi^{-1}(1-\epsilon_A)$ 仅用于展示，不参与质量聚合。

# %%
# ============ 1.2 指标构造 ============
IND_POS = ['fineweb_edu', 'fluency_en', 'modernbert_cleanliness', 'modernbert_readability', 'modernbert_reasoning',
           'modernbert_professionalism', 'dsir_books', 'dsir_wiki', 'dsir_math', 'qurater',
           'rps_doc_unigram_entropy', 'rps_doc_frac_unique_words', 'rps_lines_ending_with_terminal_punctution_mark']
IND_NEG = ['ad_en', 'rps_doc_frac_no_alph_words', 'rps_doc_frac_chars_top_2gram', 'rps_doc_frac_chars_top_3gram',
           'rps_lines_uppercase_letter_fraction', 'rps_lines_numerical_chars_fraction']
IND_INT = ['rps_doc_word_count', 'rps_doc_num_sentences', 'rps_doc_mean_word_length']
INDICATORS = IND_POS + IND_NEG + IND_INT
assert len(INDICATORS) == 22
DIRECTION = {j: '+' for j in IND_POS}; DIRECTION.update({j: '-' for j in IND_NEG}); DIRECTION.update({j: '~' for j in IND_INT})

# 中文短名（用于图表）
SHORT = {'fineweb_edu': '教育价值', 'fluency_en': '流畅度', 'ad_en': '广告概率', 'modernbert_cleanliness': '干净度',
         'modernbert_readability': '可读性', 'modernbert_reasoning': '推理性', 'modernbert_professionalism': '专业性',
         'dsir_books': 'DSIR书籍', 'dsir_wiki': 'DSIR维基', 'dsir_math': 'DSIR数学', 'qurater': 'QuRating',
         'rps_doc_word_count': '词数', 'rps_doc_num_sentences': '句子数', 'rps_doc_unigram_entropy': '一元词熵',
         'rps_doc_frac_unique_words': '独特词占比(长度校正)', 'rps_doc_frac_no_alph_words': '非字母词(域内校准)',
         'rps_doc_frac_chars_top_2gram': '高频2gram占比', 'rps_doc_frac_chars_top_3gram': '高频3gram占比',
         'rps_lines_uppercase_letter_fraction': '大写字母占比',
         'rps_lines_ending_with_terminal_punctution_mark': '行末标点(域内校准)',
         'rps_lines_numerical_chars_fraction': '数字字符占比', 'rps_doc_mean_word_length': '平均词长'}
MODEL_BASED = ['fineweb_edu', 'fluency_en', 'ad_en'] + MB_FIELDS + ['dsir_books', 'dsir_wiki', 'dsir_math', 'qurater']
RULE_BASED = [j for j in INDICATORS if j not in MODEL_BASED]

# ---- 分类器方向的数据判定 ----
web = A1['domain'].isin(['c4', 'commoncrawl']); acad = A1['domain'].isin(['arxiv', 'wikipedia'])
AD_P1_IS_NONAD = A1.loc[web, 'ad_p1'].mean() < A1.loc[acad, 'ad_p1'].mean()
FL_P1_IS_FLUENT = A1.loc[A1['domain'] == 'arxiv', 'fluency_p1'].mean() > A1.loc[A1['domain'] == 'github', 'fluency_p1'].mean()
print('ad_p1 域均值: 网页域 %.3f vs 学术域 %.3f  =>  第1类为%s' % (A1.loc[web, 'ad_p1'].mean(), A1.loc[acad, 'ad_p1'].mean(), '"非广告"，取 P_ad = 1 - p1' if AD_P1_IS_NONAD else '"广告"，取 P_ad = p1'))
print('fluency_p1 域均值: arxiv %.3f vs github %.3f  =>  第1类为%s' % (A1.loc[A1['domain'] == 'arxiv', 'fluency_p1'].mean(), A1.loc[A1['domain'] == 'github', 'fluency_p1'].mean(), '"流畅"，取 p1' if FL_P1_IS_FLUENT else '"不流畅"，取 1 - p1'))

def build_indicators(df):
    R = pd.DataFrame(index=df.index)
    R['fineweb_edu'] = df['fineweb_edu']
    R['fluency_en'] = df['fluency_p1'] if FL_P1_IS_FLUENT else 1.0 - df['fluency_p1']
    R['ad_en'] = (1.0 - df['ad_p1']) if AD_P1_IS_NONAD else df['ad_p1']
    for c in MB_FIELDS:
        R[c] = df[c]
    R['qurater'] = df[['qurater_1', 'qurater_2', 'qurater_3', 'qurater_4']].mean(axis=1)
    wc = df['rps_doc_word_count'].clip(lower=1)
    for c in ('dsir_books', 'dsir_wiki', 'dsir_math'):
        R[c] = df[c] / wc
    for c in ['rps_doc_word_count', 'rps_doc_num_sentences', 'rps_doc_unigram_entropy', 'rps_doc_frac_unique_words',
              'rps_doc_frac_no_alph_words', 'rps_doc_frac_chars_top_2gram', 'rps_doc_frac_chars_top_3gram',
              'rps_lines_uppercase_letter_fraction', 'rps_lines_ending_with_terminal_punctution_mark',
              'rps_lines_numerical_chars_fraction', 'rps_doc_mean_word_length']:
        R[c] = df[c]
    return R[INDICATORS]

R1, R2, R3 = build_indicators(A1), build_indicators(A2), build_indicators(A3)
print('\nDSIR 原始值 / 每词值 与 lg(词数) 的 Spearman 相关（A1）: %.3f / %.3f' % (
    stats.spearmanr(A1['dsir_books'], np.log1p(A1['rps_doc_word_count']))[0],
    stats.spearmanr(R1['dsir_books'], np.log1p(A1['rps_doc_word_count']))[0]))

desc = pd.DataFrame({'类型': [DIRECTION[j] for j in INDICATORS], 
                     '评分器': ['模型' if j in MODEL_BASED else '规则' for j in INDICATORS],
                     'A1均值': R1.mean(), 'A1中位数': R1.median(), 'A1_1%': R1.quantile(0.01), 'A1_99%': R1.quantile(0.99)}, index=INDICATORS)
desc.index = [SHORT[j] + ' (' + j + ')' for j in INDICATORS]
print('\n22 个指标的类型与 A1 分布摘要（+ 正向 / - 负向 / ~ 区间型）:')
display(desc)

# %%
# ============ 1.2 分位数正态映射（仅 A1 拟合，三个集合共用） ============
INTERVAL = {'rps_doc_word_count': (50.0, 1e5, float(np.nanpercentile(R1['rps_doc_word_count'], 99.9)), True),
            'rps_doc_num_sentences': (3.0, float(np.nanpercentile(R1['rps_doc_num_sentences'], 95)), float(np.nanpercentile(R1['rps_doc_num_sentences'], 99.9)), True),
            'rps_doc_mean_word_length': (3.0, 10.0, float(np.nanpercentile(R1['rps_doc_mean_word_length'], 99.9)), False)}
MEDIAN = R1.replace([np.inf, -np.inf], np.nan).median()
if MEDIAN.isna().any(): raise ValueError('A1 存在全缺失指标')

def interval_score(v, lo, hi, vmax, use_log):
    v = np.asarray(v, float)
    if use_log:
        t, tlo, thi, tmax = np.log10(1 + np.maximum(v, 0)), np.log10(1 + lo), np.log10(1 + hi), np.log10(1 + vmax)
    else:
        t, tlo, thi, tmax = v, lo, hi, vmax
    s = np.ones_like(t)
    below = t < tlo; s[below] = np.clip(t[below] / tlo, 0, 1)
    above = t > thi; s[above] = np.clip(1 - (t[above] - thi) / max(tmax - thi, 1e-9), 0, 1)
    return s


def utility(R):
    U = pd.DataFrame(index=R.index)
    for j in INDICATORS:
        v = R[j].replace([np.inf, -np.inf], np.nan).fillna(MEDIAN[j]).astype(float)
        if j in INTERVAL:
            U[j] = interval_score(v, *INTERVAL[j])
        else:
            U[j] = -v if j in IND_NEG else v
    return U

Uraw1 = utility(R1)
NORM_MIN, NORM_MAX = Uraw1.min(), Uraw1.max()
NORM_RANGE = NORM_MAX - NORM_MIN
def normalized_utility(R):
    u = ((utility(R) - NORM_MIN) / NORM_RANGE.replace(0, np.nan)).clip(0, 1)
    return u.fillna(0.5)
U1 = normalized_utility(R1)
REFERENCE = {j: np.sort(U1[j].to_numpy()) for j in INDICATORS}
QUANTILE_EPS = 0.5 / len(R1)
NORMAL_BOUND = float(stats.norm.ppf(1 - QUANTILE_EPS))
# ============ 独特词占比的 A1 长度条件分位校正 ============
LENGTH_COLUMN='rps_doc_word_count'
UNIQUE_COLUMN='rps_doc_frac_unique_words'
LENGTH_BINS=20
MIN_LENGTH_BIN_SIZE=500
LENGTH_MEDIAN=float(R1.loc[np.isfinite(R1[LENGTH_COLUMN]) & (R1[LENGTH_COLUMN]>0),LENGTH_COLUMN].median())
def length_values(R):
    values=R[LENGTH_COLUMN].to_numpy(dtype=float,copy=True)
    valid=np.isfinite(values)&(values>0)
    values[~valid]=LENGTH_MEDIAN
    return values,~valid

def fit_length_reference(R, requested_bins=20, min_size=MIN_LENGTH_BIN_SIZE):
    wc,missing=length_values(R);lw=np.log1p(wc)
    # 等频边界在观测 log(1+词数) 上取分位点；相同长度统一落入同一组。
    edges=np.unique(np.quantile(lw,np.arange(1,requested_bins)/requested_bins))
    edges=edges[(edges>lw.min())&(edges<lw.max())]
    while len(edges):
        labels=np.searchsorted(edges,lw,side='left')
        counts=np.bincount(labels,minlength=len(edges)+1)
        k=int(np.argmin(counts))
        if counts[k]>=min_size:break
        # 小组与相邻样本量更少的一组合并，直到每组达到最低量。
        if k==0:drop=0
        elif k==len(counts)-1:drop=k-1
        else:drop=k-1 if counts[k-1]<=counts[k+1] else k
        edges=np.delete(edges,drop)
    labels=np.searchsorted(edges,lw,side='left')
    normalized=normalized_utility(R)[UNIQUE_COLUMN].to_numpy()
    refs=[np.sort(normalized[labels==k]) for k in range(len(edges)+1)]
    rows=[]
    for k,ref in enumerate(refs):
        mask=labels==k
        rows.append({'组号':k+1,'n':int(mask.sum()),'最短词数':float(wc[mask].min()),
          '词数中位数':float(np.median(wc[mask])),'最长词数':float(wc[mask].max()),
          '独特词占比中位数':float(R.loc[mask,UNIQUE_COLUMN].median()),
          '归一化独特词唯一值数':int(len(np.unique(ref)))})
    assert all(len(x)>=min_size for x in refs) or len(refs)==1
    # 相同词数不因行顺序而被切开。
    same=pd.DataFrame({'wc':wc,'bin':labels}).groupby('wc')['bin'].nunique()
    assert same.max()==1
    return {'requested_bins':requested_bins,'edges':edges,'refs':refs,'table':pd.DataFrame(rows),
      'train_length_min':float(wc.min()),'train_length_max':float(wc.max()),'train_missing':int(missing.sum())}

def length_percentile(R, model):
    wc,missing=length_values(R);groups=np.searchsorted(model['edges'],np.log1p(wc),side='left')
    values=normalized_utility(R)[UNIQUE_COLUMN].to_numpy()
    p=np.zeros(len(R))
    for k,ref in enumerate(model['refs']):
        mask=groups==k;v=values[mask]
        # 并列保留中秩，不人为加噪。延续共同 epsilon，确保同一概率对应同一Z。
        p[mask]=(np.searchsorted(ref,v,'left')+np.searchsorted(ref,v,'right'))/(2*len(ref))
    p=np.clip(p,QUANTILE_EPS,1-QUANTILE_EPS)
    return p,groups,missing,(wc<model['train_length_min'])|(wc>model['train_length_max'])

LENGTH_MODELS={k:fit_length_reference(R1,k) for k in [10,20,30]}
LENGTH_MODEL=LENGTH_MODELS[LENGTH_BINS]
for k,model in LENGTH_MODELS.items():
    model['table'].to_csv(TAB/f'length_bins_{k}.csv',index=False,encoding='utf-8-sig')
    np.savez_compressed(TAB/f'length_reference_{k}.npz',log_edges=model['edges'],**{f'bin_{j}':v for j,v in enumerate(model['refs'])})
display(LENGTH_MODEL['table'])
print('主方案请求20组，实际组数:',len(LENGTH_MODEL['refs']),'；训练长度缺失填补数:',LENGTH_MODEL['train_missing'])


def normal_scores(R, length_model=LENGTH_MODEL):
    U = normalized_utility(R)
    Z = pd.DataFrame(index=R.index)
    for j in INDICATORS:
        ref = REFERENCE[j]; v = U[j].to_numpy()
        left = np.searchsorted(ref, v, side='left')
        right = np.searchsorted(ref, v, side='right')
        prob = (left + right) / (2.0 * len(ref))
        Z[j] = stats.norm.ppf(np.clip(prob, QUANTILE_EPS, 1 - QUANTILE_EPS))
    if length_model is not False:
        p,_,_,_=length_percentile(R,length_model)
        Z[UNIQUE_COLUMN]=stats.norm.ppf(p)
    return Z

# ============ 两项格式规则的 A1 领域条件分位校准 ============
FORMAT_RULES=['rps_lines_ending_with_terminal_punctution_mark','rps_doc_frac_no_alph_words']
FORMAT_REFERENCE={}
fr_ref_rows=[]
for fr_domain in sorted(A1.domain.unique()):
    fr_mask=A1.domain.eq(fr_domain).to_numpy()
    for fr_j in FORMAT_RULES:
        fr_ref=np.sort(U1.loc[fr_mask,fr_j].to_numpy())
        FORMAT_REFERENCE[(fr_domain,fr_j)]=fr_ref
        fr_ref_rows.append({'领域':fr_domain,'指标':fr_j,'A1参考样本数':len(fr_ref),
          '唯一值数':len(np.unique(fr_ref)),'原始指标中位数':float(R1.loc[fr_mask,fr_j].median()),
          '效用最小值':float(fr_ref.min()),'效用最大值':float(fr_ref.max())})
FORMAT_REFERENCE_TABLE=pd.DataFrame(fr_ref_rows)
FORMAT_REFERENCE_TABLE.to_csv(TAB/'format_domain_reference_summary.csv',index=False,encoding='utf-8-sig')
np.savez_compressed(TAB/'format_domain_reference.npz',**{d+'__'+j:v for (d,j),v in FORMAT_REFERENCE.items()})

def format_percentiles(R, domains, indicators=FORMAT_RULES):
    domains=np.asarray(domains,dtype=str)
    if len(domains)!=len(R):raise ValueError('领域标签必须与指标行数一致')
    unknown=set(domains)-{d for d,j in FORMAT_REFERENCE}
    if unknown:raise ValueError('A1无参考领域，不能静默套用其他领域: '+str(sorted(unknown)))
    U=normalized_utility(R)
    P=pd.DataFrame(index=R.index)
    for j in indicators:
        p=np.zeros(len(R));values=U[j].to_numpy()
        for d in np.unique(domains):
            mask=domains==d;ref=FORMAT_REFERENCE[(d,j)];v=values[mask]
            p[mask]=(np.searchsorted(ref,v,'left')+np.searchsorted(ref,v,'right'))/(2*len(ref))
        P[j]=np.clip(p,QUANTILE_EPS,1-QUANTILE_EPS)
    return P

def calibrated_scores(R, domains, base_Z=None, indicators=FORMAT_RULES):
    Z=normal_scores(R) if base_Z is None else base_Z.copy()
    P=format_percentiles(R,domains,indicators)
    for j in indicators:Z[j]=stats.norm.ppf(P[j])
    return Z

display(FORMAT_REFERENCE_TABLE)
print('领域内中秩校准：行末标点正向、非字母词负向；专业性完全保留原映射。')


def normalize(R,domains):
    return ((calibrated_scores(R,domains)+NORMAL_BOUND)/(2*NORMAL_BOUND)).clip(0,1)

Z1_uncorrected, Z2_uncorrected, Z3_uncorrected = [normal_scores(r,False) for r in (R1,R2,R3)]
Z1_length,Z2_length,Z3_length=[normal_scores(r) for r in (R1,R2,R3)]
Z1_normal,Z2_normal,Z3_normal=[calibrated_scores(r,a.domain,base_Z=z) for r,a,z in zip((R1,R2,R3),(A1,A2,A3),(Z1_length,Z2_length,Z3_length))]
X1, X2, X3 = [((z + NORMAL_BOUND) / (2 * NORMAL_BOUND)).clip(0, 1) for z in (Z1_normal, Z2_normal, Z3_normal)]
for X in (X1, X2, X3):
    assert np.isfinite(X.to_numpy()).all() and X.min().min() >= 0 and X.max().max() <= 1
for j in INDICATORS:
    if j==UNIQUE_COLUMN:
        _,bins,_,_=length_percentile(R1,LENGTH_MODEL)
        for b in np.unique(bins):
            idx=np.flatnonzero(bins==b);order=idx[np.argsort(U1[j].to_numpy()[idx],kind='stable')]
            assert (np.diff(Z1_normal[j].to_numpy()[order])>=0).all()
    elif j in FORMAT_RULES:
        for d in A1.domain.unique():
            idx=np.flatnonzero(A1.domain.eq(d).to_numpy());order=idx[np.argsort(U1[j].to_numpy()[idx],kind='stable')]
            assert (np.diff(Z1_normal[j].to_numpy()[order])>=0).all()
    else:
        order=np.argsort(U1[j].to_numpy(),kind='stable')
        assert (np.diff(Z1_normal[j].to_numpy()[order])>=0).all()
        assert np.array_equal(Z1_normal[j],Z1_uncorrected[j])
assert np.allclose(normalize(R1.iloc[:25],A1.domain.iloc[:25]), X1.iloc[:25])
np.savez_compressed(TAB / 'normal_quantile_reference.npz', **REFERENCE)
(TAB / 'preprocessing_parameters.json').write_text(json.dumps({
    'method': 'A1 normal scores; unique-word length-conditional; two format rules domain-conditional; professionalism unchanged; Q directly on Z',
    'format_calibration': {'indicators': FORMAT_RULES,'fit_set': 'A1','reference_file':'format_domain_reference.npz','domain_sizes':A1.domain.value_counts().to_dict(),'unknown_domain_policy':'raise error','clip_epsilon':QUANTILE_EPS},
    'length_correction': {'indicator':UNIQUE_COLUMN,'requested_bins':LENGTH_BINS,'actual_bins':len(LENGTH_MODEL['refs']),'minimum_group_size':MIN_LENGTH_BIN_SIZE,'log_edges':LENGTH_MODEL['edges'].tolist(),'length_median':LENGTH_MEDIAN,'clip_epsilon':QUANTILE_EPS},
    'normalization_min': NORM_MIN.to_dict(), 'normalization_max': NORM_MAX.to_dict(),
    'epsilon': QUANTILE_EPS, 'normal_bound': NORMAL_BOUND,
    'median': MEDIAN.to_dict(), 'interval': INTERVAL,
    'ad_p1_is_nonad': bool(AD_P1_IS_NONAD), 'fl_p1_is_fluent': bool(FL_P1_IS_FLUENT),
    'weight_method': 'squared Pearson redundancy weights for 22 indicators; no grouping; alpha=1',
}, ensure_ascii=False, indent=2), encoding='utf-8')
normal_diagnostic = pd.DataFrame({
    '原归一化值唯一数': U1.nunique(), '原归一化值最大并列比例': U1.apply(lambda v: v.value_counts(normalize=True).max()),
    '最终正态分数唯一数':Z1_normal.nunique(),
    '正态分数均值': Z1_normal.mean(), '正态分数标准差': Z1_normal.std(),
    '偏度': Z1_normal.skew(), '超额峰度': Z1_normal.kurt(),
})
normal_diagnostic.to_csv(TAB / 'normal_quantile_diagnostics.csv', encoding='utf-8-sig')
display(normal_diagnostic)
print('归一化后取值范围检查:', [(float(x.min().min()), float(x.max().max())) for x in (X1, X2, X3)])
print('共同正态边界 b =', NORMAL_BOUND, '；A1/A2/A3 记录数:', len(R1), len(R2), len(R3))
# ---- 图 1：22 个归一化指标在 7 个域上的经验累积分布（A1） ----
DOMAINS = sorted(A1['domain'].unique())
DOM_PALETTE = ['#1F3A5F', '#2A9D8F', '#E76F51', '#E9C46A', '#6D597A', '#8AB17D', '#B56576']
DOM_COLORS = dict(zip(DOMAINS, DOM_PALETTE[:len(DOMAINS)]))
# 用 ECDF 而非核密度：归一化后很多指标在 0 或 1 处有点质量（并列 / 区间型），ECDF 能如实显示这些跳跃且不受带宽影响
fig, axes = plt.subplots(4, 6, figsize=(17, 10.5))
grid = np.linspace(0, 1, 201)
for ax, j in zip(axes.ravel(), INDICATORS):
    for d in DOMAINS:
        v = np.sort(X1.loc[A1['domain'] == d, j].values)
        F = np.searchsorted(v, grid, side='right') / len(v)
        ax.plot(grid, F, color=DOM_COLORS[d], lw=1.4, alpha=0.9)
    ax.set_title('%s (%s)' % (SHORT[j], DIRECTION[j]), fontsize=9.5, color=C_NAVY)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02); ax.set_yticks([0, 0.5, 1]); ax.tick_params(labelsize=8)
for ax in axes.ravel()[len(INDICATORS):]:
    ax.axis('off')
handles = [Line2D([0], [0], color=DOM_COLORS[d], lw=2, label=d) for d in DOMAINS]
axes[3, 4].legend(handles=handles, loc='center left', ncol=1, frameon=False, fontsize=10, borderaxespad=0)
plt.tight_layout()
savefig('fig01_indicator_distributions.png'); plt.show()

# %% [markdown]
# ### 1.3 22 个指标的相关性去冗余赋权
#
# 相关性去冗余赋权 = 按每个指标与其余指标共享信息的程度降低权重，不设四个维度或任何中间评分组。先在 A1 正态分数上计算 Pearson 相关矩阵 R：
# $$
# r_{jk}=\frac{\sum_i(Z_{ij}-\bar Z_j)(Z_{ik}-\bar Z_k)}{\sqrt{\sum_i(Z_{ij}-\bar Z_j)^2\sum_i(Z_{ik}-\bar Z_k)^2}}.
# $$
# 令 $V=\{j:\operatorname{sd}_{A1}(Z_j)>10^{-12}\}$，总体标准差分母为 $n_A$；$V$为空时停止计算，定义
# $$
# d_j=1+\sum_{k\in V,k\ne j}r_{jk}^{2}.
# $$
#
# $$
# w_j(\alpha)=\frac{d_j^{-\alpha}}{\sum_{\ell\in V}d_\ell^{-\alpha}},\quad j\in V.
# $$
# 无变异的指标权重置零并明确标记；本次是否存在这类指标由下面代码输出。基准 α=1，d_j 越大、冗余程度越高、权重越低。公式是本次采用的操作性赋权规则，不声称为唯一最优权重。平方相关衡量线性关联强度；相较绝对相关，它减弱中低相关的冗余惩罚，正负相关都可能代表重复信息；冲突判定仍单独使用带符号的 r≤−0.30，两者含义不同。
#
# 全部权重只用 A1 拟合并固定用于 A2/A3。三个 DSIR 指标分别参与，不合并。低相关不保证指标更可靠或质量含义更重要，必须结合原文辅助核验、逐项权重 ±20% 和 α=0.5/1/1.5/2 的敏感性结果评价；22 项等权只作对照，不作为主模型。
#
# 线性基线为 $Q_i^{lin}=\sum_{j=1}^{22}w_jZ_{ij}$，最终 Q 使用 2.3 的指数凹聚合式。

# %%
# ============ 1.3 22 个指标相关性去冗余赋权 ============

WEIGHT_ALPHA=1.0
VALID_IND=Z1_normal.std(ddof=0)>1e-12
VALID_NAMES=VALID_IND.index[VALID_IND].tolist()
if not VALID_NAMES:raise ValueError('A1 所有指标均无变异，无法进行数据驱动赋权')
def fit_redundancy(z):
    """A1平方Pearson冗余度；常数列权重为零，正负相关等价去冗余。"""
    rho=z.corr(method='pearson')
    valid=z.std(ddof=0)>1e-12
    if not valid.any():raise ValueError('所有指标均无变异')
    block=rho.loc[valid,valid].to_numpy()**2
    np.fill_diagonal(block,1.0)
    assert np.isfinite(block).all()
    redundancy=pd.Series(np.nan,index=z.columns,dtype=float)
    redundancy.loc[valid]=block.sum(axis=1)
    raw=pd.Series(0.,index=z.columns)
    raw.loc[valid]=1/redundancy.loc[valid]
    return rho,redundancy,(raw/raw.sum()).to_numpy()
RHO,REDUNDANCY,wG=fit_redundancy(Z1_normal)
RHO.to_csv(TAB/'pearson_normal_matrix.csv',encoding='utf-8-sig')
def redundancy_weights(alpha=WEIGHT_ALPHA):
    if alpha<0:raise ValueError('alpha 必须非负')
    raw=pd.Series(0.0,index=INDICATORS)
    raw.loc[VALID_NAMES]=REDUNDANCY.loc[VALID_NAMES].pow(-alpha)
    return (raw/raw.sum()).to_numpy()
wG=redundancy_weights()
W=pd.DataFrame({'方向':[DIRECTION[j] for j in INDICATORS],
               '是否有效':VALID_IND,'冗余度':REDUNDANCY,'权重':wG},index=INDICATORS)
assert len(wG)==22 and np.all(wG>=0) and np.isclose(wG.sum(),1)
assert not np.allclose(wG,1/22), '请核查：本数据下去冗余权重不应全部相等'
check=W[W['是否有效']].sort_values('冗余度')
assert np.all(np.diff(check['权重'])<=1e-12)
display(W);W.to_csv(TAB/'indicator_weights.csv',encoding='utf-8-sig')
print('权重范围:',wG.min(),wG.max(),'；无变异指标:',VALID_IND.index[~VALID_IND].tolist())
(TAB/'weighting_parameters.json').write_text(json.dumps({
 'method':'inverse squared Pearson redundancy','alpha':WEIGHT_ALPHA,
 'formula':'d_j=1+sum_{k != j} r_jk**2; w_j=d_j^(-alpha)/sum d^(-alpha)',
 'fit_set':'A1','indicator_order':INDICATORS,'valid_indicators':VALID_NAMES,
 'redundancy':REDUNDANCY.to_dict(),'weights':dict(zip(INDICATORS,wG.tolist()))
},ensure_ascii=False,indent=2), encoding='utf-8')
dist=squareform(np.clip(1-RHO.fillna(0).pow(2).values,0,1),checks=False)
order=hierarchy.leaves_list(hierarchy.linkage(dist,method='average'))
lab=[SHORT[j] for j in RHO.columns]
fig,ax=plt.subplots(figsize=(11.5,9.5))
sns.heatmap(RHO.iloc[order,order],cmap=CMAP_DIV,vmin=-1,vmax=1,square=True,ax=ax,
 xticklabels=[lab[i] for i in order],yticklabels=[lab[i] for i in order],
 cbar_kws={'shrink':.6,'label':'Pearson 相关系数'},linewidths=.4,linecolor='white')
ax.grid(False);plt.setp(ax.get_xticklabels(),rotation=90,fontsize=9)
plt.setp(ax.get_yticklabels(),fontsize=9)

savefig('fig02_corr_cluster_heatmap.png');plt.show()
print('DSIR 三指标的相关性（分别赋权、不合并）:')
display(RHO.loc[['dsir_books','dsir_wiki','dsir_math'],['dsir_books','dsir_wiki','dsir_math']])
fig,ax=plt.subplots(figsize=(10,8))
Wp=W.sort_values('权重');ax.barh([SHORT[j] for j in Wp.index],Wp['权重'],color=C_NAVY)
ax.axvline(1/22,color=C_CORAL,ls='--',label='等权参考线 1/22（非主方案）')
ax.set_xlim(0,wG.max()*1.15);ax.set_xlabel('指标权重');ax.legend()
savefig('fig03_weights_redundancy22.png');plt.show()

# %% [markdown]
# ### 1.4 聚合方式与线性基线
#
# * **样本级**：本节先计算线性基线 $Q_i^{lin}$；最终评分 $Q_i$ 在第 2.3 节计算，二者使用相同的域级聚合方式。
# * **语料级**：一个域的语料是其全部文档的 token 总和，训练时每篇文档对损失的贡献与其 token 数成比例，因此语料级质量应是 **按词数加权的样本均值**（记 $n_i$ 为文档 $i$ 的词数）：
# $$
# Q^{corpus}_D=\frac{\sum_{i\in D} n_i Q_i}{\sum_{i\in D} n_i}.
# $$
# * **领域级**：为了和"文档层面的质量"对照，同时报告 **简单均值** $Q^{doc}_D=\frac{1}{|D|}\sum_{i\in D}Q_i$ 及其 Bootstrap 95% 置信区间（$B=300$ 次有放回重抽样，取 2.5%、97.5% 分位数）。两者的差异反映"长文档是否更优质"。
#
# 题目要求"全量质量信号"：arxiv 与 github 两个域，A1 中只是抽样（1,419 与 10,000 条），A2/A3 给出全量（17,523 与 203,752 条）。下面分别给出 **A1 抽样估计** 与 **扩展集全量估计**，并用两样本 KS 统计量与 Wasserstein 距离刻画二者样本级分布的差异，检验抽样集是否有代表性。

# %%
# ============ 1.4 线性综合分与域级聚合 ============
for A, X in ((A1, X1), (A2, X2), (A3, X3)):
    A['Q_lin'] = (((X.values * 2 * NORMAL_BOUND) - NORMAL_BOUND) * wG).sum(axis=1)

def boot_ci(v, w=None, B=300, seed=0):
    v = np.asarray(v, float); n = len(v); rng = np.random.default_rng(seed)
    w = None if w is None else np.asarray(w, float)
    est = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n, n)
        est[b] = np.average(v[idx]) if w is None else np.average(v[idx], weights=w[idx])
    return np.percentile(est, [2.5, 97.5])

def domain_table(frames, col):
    rows = []
    for name, A in frames:
        for d, g in A.groupby('domain'):
            lo, hi = boot_ci(g[col].values)
            rows.append({'数据集': name, '域': d, 'n': len(g), col + '_doc均值': g[col].mean(), 'CI95低': lo, 'CI95高': hi,
                         col + '_语料(词数加权)': np.average(g[col], weights=g['rps_doc_word_count'].clip(lower=1)),
                         col + '_中位数': g[col].median()})
    return pd.DataFrame(rows)

DT_lin = domain_table([('A1 抽样集', A1), ('A2 扩展集', A2), ('A3 扩展集', A3)], 'Q_lin')
print('域级线性综合分 Q_lin（A1 抽样集 vs 扩展集）:')
display(DT_lin)

# 抽样集 vs 扩展集的分布差异
cmp_rows = []
for d, ext, Xe in (('arxiv', A2, X2), ('github', A3, X3)):
    a = A1.loc[A1['domain'] == d, 'Q_lin'].values; b = ext['Q_lin'].values
    ks = stats.ks_2samp(a, b)
    prof = stats.spearmanr(X1.loc[A1['domain'] == d].mean(), Xe.mean())[0]
    cmp_rows.append({'域': d, 'A1样本数': len(a), '扩展集样本数': len(b), 'KS统计量': ks.statistic, 'KS_p': ks.pvalue,
                     'Wasserstein距离': stats.wasserstein_distance(a, b), '指标均值剖面Spearman': prof})
print('\n抽样集 vs 扩展集的样本级 Q_lin 分布差异:')
display(pd.DataFrame(cmp_rows))

# ---- 图 4：域级 Q 对照 + 抽样/扩展分布叠加 ----
fig = plt.figure(figsize=(14, 8.5))
gs = gridspec.GridSpec(2, 2, height_ratios=[1.15, 1], hspace=0.38, wspace=0.18)
ax = fig.add_subplot(gs[0, :])
a1 = DT_lin[DT_lin['数据集'] == 'A1 抽样集'].set_index('域').loc[DOMAINS]
ext_tab = {'arxiv': DT_lin[DT_lin['数据集'] == 'A2 扩展集'].iloc[0], 'github': DT_lin[DT_lin['数据集'] == 'A3 扩展集'].iloc[0]}
wbar = 0.19; xpos = np.arange(len(DOMAINS)) * 1.0
series = [('A1 抽样集 · 文档均值', C_NAVY, 'Q_lin_doc均值', False), ('A1 抽样集 · 语料级(词数加权)', C_TEAL, 'Q_lin_语料(词数加权)', False),
          ('扩展集全量 · 文档均值', C_CORAL, 'Q_lin_doc均值', True), ('扩展集全量 · 语料级(词数加权)', C_GOLD, 'Q_lin_语料(词数加权)', True)]
for i, d in enumerate(DOMAINS):
    ser = series if d in ext_tab else series[:2]
    offs = (np.arange(len(ser)) - (len(ser) - 1) / 2) * wbar
    for (lab_, c, col, is_ext), off in zip(ser, offs):
        src = ext_tab[d] if is_ext else a1.loc[d]
        err = None if (is_ext or col != 'Q_lin_doc均值') else [[src['Q_lin_doc均值'] - src['CI95低']], [src['CI95高'] - src['Q_lin_doc均值']]]
        ax.bar(xpos[i] + off, src[col], wbar, color=c, label=lab_ if i == 0 or (is_ext and d == 'arxiv') else None, yerr=err, capsize=3, ecolor='#333333', edgecolor='white', linewidth=0.5)
        ax.text(xpos[i] + off, src[col] + 0.012, '%.3f' % src[col], ha='center', va='bottom', fontsize=7.5, rotation=90, color='#222222')
ax.set_xticks(xpos); ax.set_xticklabels(['%s\n(A1 n=%d%s)' % (d, a1.loc[d, 'n'], ('；全量 n=%d' % ext_tab[d]['n']) if d in ext_tab else '') for d in DOMAINS], fontsize=9)
ax.set_ylim(min(0, DT_lin["Q_lin_doc均值"].min() - 0.3), DT_lin["Q_lin_doc均值"].max() + 0.4); ax.set_ylabel('线性综合质量分 Q_lin')
ax.set_title('(a) 域级 Q_lin：A1 抽样集（误差线为 Bootstrap 95% CI）与 arxiv / github 扩展集全量的对照', fontsize=10.5)
ax.legend(loc='upper right', ncol=2, frameon=False, fontsize=9)
for k, (d, ext, c) in enumerate((('arxiv', A2, C_CORAL), ('github', A3, C_GOLD))):
    ax = fig.add_subplot(gs[1, k])
    a = A1.loc[A1['domain'] == d, 'Q_lin'].values; b = ext['Q_lin'].values
    xs = np.linspace(min(a.min(), b.min()), max(a.max(), b.max()), 300)
    ax.fill_between(xs, stats.gaussian_kde(a)(xs), color=C_NAVY, alpha=0.25, label='A1 抽样 (n=%d)' % len(a))
    ax.plot(xs, stats.gaussian_kde(a)(xs), color=C_NAVY, lw=1.6)
    ax.plot(xs, stats.gaussian_kde(b if len(b) <= 30000 else RNG.choice(b, 30000, replace=False))(xs), color=c, lw=2.0, label='扩展集全量 (n=%d)' % len(b))
    r = cmp_rows[k]
    ax.text(0.02, 0.95, 'KS = %.3f (p = %.2g)\nWasserstein = %.4f' % (r['KS统计量'], r['KS_p'], r['Wasserstein距离']), transform=ax.transAxes, va='top', fontsize=9, bbox=dict(boxstyle='round', fc='white', ec='#CCCCCC'))
    ax.set_xlabel('样本级 Q_lin'); ax.set_ylabel('密度'); ax.set_title('(%s) %s 域：抽样集 vs 扩展集的样本级分布' % ('bc'[k], d), fontsize=10.5)
    ax.legend(frameon=False, fontsize=9)
savefig('fig04_domain_Q_compare.png'); plt.show()

# %% [markdown]
# ## 2. 质量冲突消解
#
# ### 2.1 先定义冲突，再计算综合评价
#
# 定义候选指标对、强度及A1高低阈值为
#
# $$
# E=\{(j,k):j<k,\ j,k\in V,\ r_{jk}\le-\tau_r\},\quad\tau_r=0.30,\quad
# c_{jk}=\max(0,-r_{jk}),
# $$
# $$
# q_j^L=\operatorname{Quantile}_{0.20}\{Z_{lj}:l\in\mathcal A\},\qquad
# q_j^H=\operatorname{Quantile}_{0.80}\{Z_{lj}:l\in\mathcal A\},
# $$
# $$
# H_{ij}=\mathbf1(Z_{ij}>q_j^H),\quad L_{ij}=\mathbf1(Z_{ij}<q_j^L),\quad
# B_{ijk}=H_{ij}L_{ik}+L_{ij}H_{ik}.
# $$
#
# $L_{ij}$在本节是低分指示量，与后文损失 $L$ 不同。分位数沿用程序的线性插值定义；严格不等式避免平台并列被同时计为高、低。候选对权重总和 $W_E=\sum_{(j,k)\in E}c_{jk}$，则
#
# $$
# CI_i=\begin{cases}\dfrac{\sum_{(j,k)\in E}c_{jk}B_{ijk}|Z_{ij}-Z_{ik}|}{W_E},&W_E>0,\\0,&W_E=0.\end{cases}
# $$
#
# 因此 $E=\varnothing$ 时取零；无触发对的样本也取零。冲突标记为 $I_i^{conf}=\mathbf1(CI_i>0)$，集合 $\mathcal D$ 的冲突率为 $|\mathcal D|^{-1}\sum_{i\in\mathcal D}I_i^{conf}$。阈值是诊断口径，不是显著性检验。A2/A3沿用A1的 $E,q^L,q^H$；改变诊断阈值不改变 $Q$，不强制固定比例的样本被判冲突。

# %%
# 2.1 Pearson 冲突对与样本冲突强度
Q_LO, Q_HI = 0.20, 0.80
R_THRESHOLD = 0.30
pairs = []
for a, b in itertools.combinations(INDICATORS, 2):
    pairs.append({'指标j': SHORT[a], '指标k': SHORT[b], 'j': a, 'k': b,
                  'Pearson': RHO.loc[a, b],
                  '跨评分器类型': (a in MODEL_BASED) != (b in MODEL_BASED)})
PAIRS = pd.DataFrame(pairs).sort_values('Pearson').reset_index(drop=True)
PAIRS['相关冲突强度'] = (-PAIRS['Pearson']).clip(lower=0)
PAIRS['阈值冲突'] = PAIRS['Pearson'] <= -R_THRESHOLD
PAIRS['判定'] = np.select(
    [PAIRS.Pearson.isna(), PAIRS.Pearson <= -R_THRESHOLD, PAIRS.Pearson >= R_THRESHOLD],
    ['不可判定', '冲突', '同向'], default='弱相关')
print('Pearson 判定统计（操作性阈值，不表示显著性检验）：')
display(PAIRS.groupby('判定').size().rename('指标对数').to_frame())
display(PAIRS.head(15)[['指标j', '指标k', 'Pearson', '相关冲突强度', '判定']])
def sample_conflict(Z, threshold=R_THRESHOLD):
    edges = PAIRS[PAIRS.Pearson <= -threshold]
    lo, hi = Z1_normal.quantile(Q_LO), Z1_normal.quantile(Q_HI)
    result = np.zeros(len(Z)); denom = edges['相关冲突强度'].sum()
    for row in edges.itertuples():
        a,b = row.j,row.k
        mask = ((Z[a]>hi[a]) & (Z[b]<lo[b])) | ((Z[b]>hi[b]) & (Z[a]<lo[a]))
        result += (-row.Pearson) * mask.to_numpy() * np.abs(Z[a].to_numpy()-Z[b].to_numpy())
    return result / denom if denom > 0 else result


PAIRS.to_csv(TAB / 'conflict_pairs_A1.csv', index=False, encoding='utf-8-sig')

fig,ax=plt.subplots(figsize=(9,5.6))
top_corr=PAIRS.sort_values('Pearson').head(15).iloc[::-1]
ax.barh(top_corr['指标j']+' × '+top_corr['指标k'],top_corr.Pearson,color=C_CORAL)
ax.axvline(-R_THRESHOLD,ls='--',color=C_NAVY,label='冲突阈值 −0.30')
ax.set_xlabel('Pearson 相关系数 r（正态映射后）');ax.legend(loc='lower left')
plt.tight_layout();savefig('fig05_pearson_conflict_definition.png');plt.show()

# %% [markdown]
# ### 2.2 从指标对、领域和文本长度检查冲突来源
#
# 直接在 22 个指标上分析，不计算维度得分。图中展示7个领域的冲突信号比例及文本长度与CI的关联；最常见实际触发指标对保留在结果表中。模型评分器和规则指标的区分仅用于描述来源差异，不产生分组权重或分组得分。
#
# 每条文本的代表冲突对取已触发“一高一低”条件的指标对中，对 CI 贡献最大的一对，并记录高低方向。未触发则记“无冲突信号”。这些分析描述关联，不证明因果；CI>0 表示存在冲突信号，不等同于严重冲突。

# %%
# ============ 2.2 22 指标的冲突来源与实际触发对 ============
A1['CI']=sample_conflict(Z1_normal)
TAU=0.0;A1['is_conflict']=A1.CI>TAU
best_contribution=np.zeros(len(A1)); representative=np.full(len(A1),'无冲突信号',dtype=object)
lo,hi=Z1_normal.quantile(Q_LO),Z1_normal.quantile(Q_HI)
for row in PAIRS[PAIRS.Pearson<=-R_THRESHOLD].itertuples():
    a,b=row.j,row.k;va,vb=Z1_normal[a].to_numpy(),Z1_normal[b].to_numpy()
    ab=(va>hi[a])&(vb<lo[b]);ba=(vb>hi[b])&(va<lo[a])
    contribution=(-row.Pearson)*np.abs(va-vb)*(ab|ba)
    update=contribution>best_contribution
    representative[update&ab]=SHORT[a]+'高 / '+SHORT[b]+'低'
    representative[update&ba]=SHORT[b]+'高 / '+SHORT[a]+'低'
    best_contribution=np.maximum(best_contribution,contribution)
A1['代表冲突指标对']=representative
assert np.array_equal(A1.is_conflict.to_numpy(),best_contribution>0)
print('A1 存在冲突信号的比例: %.2f%%' % (100*A1.is_conflict.mean()))
print('评分器类型差异（仅描述，不参与赋权）:')
display(PAIRS.groupby('跨评分器类型')[['相关冲突强度']].agg(['mean','median','count']))
dom_conf=A1.groupby('domain').agg(n=('CI','size'),冲突样本占比=('is_conflict','mean'),平均冲突强度=('CI','mean'),强度中位数=('CI','median'))
patterns=A1[A1.is_conflict].groupby('domain')['代表冲突指标对'].agg(lambda x:x.value_counts().index[0])
dom_conf['最常见冲突指标对']=patterns.reindex(dom_conf.index).fillna('无冲突信号')
display(dom_conf)
A1['wc_decile']=pd.qcut(A1.rps_doc_word_count.rank(method='first'),10,labels=False)+1
len_conf=A1.groupby('wc_decile').agg(词数中位数=('rps_doc_word_count','median'),平均冲突强度=('CI','mean'),冲突样本占比=('is_conflict','mean'))
rho_len=stats.spearmanr(A1.CI,np.log1p(A1.rps_doc_word_count))[0]
print('CI 与 log(词数) 的 Spearman:',rho_len);display(len_conf)
fig,axes=plt.subplots(1,2,figsize=(11,4.8))
dc=dom_conf.sort_values('冲突样本占比');ax=axes[0]
ax.barh(dc.index,100*dc['冲突样本占比'],color=[DOM_COLORS[d] for d in dc.index])
for i,v in enumerate(100*dc['冲突样本占比']):ax.text(v+.5,i,'%.1f%%'%v,va='center',fontsize=9)
ax.set_xlim(0,110);ax.set_xlabel('存在冲突信号的样本比例 (%)');ax.set_title('(a) 7 个领域的冲突信号')
ax=axes[1];ax.plot(len_conf.index,len_conf['平均冲突强度'],marker='o',color=C_NAVY,label='平均 CI')
ax.set_xticks(len_conf.index);ax.set_xlabel('词数十分位：1 最短，10 最长');ax.set_ylabel('平均 CI')
ax2=ax.twinx();ax2.grid(False);ax2.plot(len_conf.index,100*len_conf['冲突样本占比'],marker='s',ls='--',color=C_CORAL,label='信号比例')
ax2.set_ylabel('存在冲突信号的样本比例 (%)');ax2.spines['right'].set_visible(True)
ax.set_title('(b) CI 与文本长度：Spearman=%.3f'%rho_len)
fig.tight_layout();savefig('fig06_conflict_causes.png');plt.show()
A1[['id','domain','代表冲突指标对','CI','is_conflict']].to_csv(TAB/'representative_conflict_pairs_A1.csv',index=False,encoding='utf-8-sig')

# %% [markdown]
# ### 2.3 指数凹聚合与最终评分
#
# $$
# Q_i=-\frac1\beta\ln\left(\sum_{j=1}^{22}w_j e^{-\beta Z_{ij}}\right).
# $$
#
# $$
# w_j\ge0,\quad\sum_j w_j=1,\quad\beta>0.
# $$
# 这里 Z 为正态映射后的 22 个指标，直接作用于实数，权重由 1.3 的相关性去冗余规则确定，不截断负值。β=0.25 为基准建模参数，并检验 0.25/0.5/1/2/4。用 logsumexp 稳定计算，避免指数溢出。
#
# Q 随每个指标单调不减，min(Z)≤Q≤ΣwZ；指标全相等时 Q 等于该值，β→0 时回到线性基线。惩罚 P=Q_lin−Q≥0 表示短板造成的评分下调，不是 Pearson 冲突强度；Q 不保证只惩罚负相关对，也不保证随 CI 严格单调。所有样本使用同一评分函数，避免阈值切换导致评分不连续。

# %%
BETA = 0.25
def softmin_quality(Z, beta=BETA, weights=wG):
    weights = np.asarray(weights, float)
    assert beta > 0 and np.all(weights >= 0) and weights.sum() > 0
    weights = weights / weights.sum()
    return -logsumexp(-beta*np.asarray(Z,float), b=weights, axis=1)/beta
for A,Z in ((A1,Z1_normal),(A2,Z2_normal),(A3,Z3_normal)):
    A['Q_res'] = softmin_quality(Z)
    A['CI'] = sample_conflict(Z)
    A['is_conflict'] = A['CI'] > 0
    A['dQ'] = A['Q_res'] - A['Q_lin']
    assert np.isfinite(A.Q_res).all()
    assert (A.Q_res <= A.Q_lin + 1e-10).all()
    assert (A.Q_res >= Z.min(axis=1) - 1e-10).all()
assert np.allclose(softmin_quality(np.full((3,22), -2.0)), -2.0)
assert np.allclose(softmin_quality(Z1_normal.iloc[:10]+2), softmin_quality(Z1_normal.iloc[:10])+2)
assert np.all(softmin_quality(Z1_normal.iloc[:10]+0.01) >= softmin_quality(Z1_normal.iloc[:10]))
chk=A1.groupby('is_conflict').agg(n=('dQ','size'),Q_lin均值=('Q_lin','mean'),Q_res均值=('Q_res','mean'),平均下调=('dQ','mean'),平均CI=('CI','mean'))
display(chk)
print('CI 与惩罚幅度的 Spearman（描述性，不预设单调）:',stats.spearmanr(A1.CI,-A1.dQ)[0])
sens=[]
k=len(A1)//10; base_top=set(np.argsort(-A1.Q_lin.to_numpy(),kind='stable')[:k])
for beta in [.25,.5,1,2,4]:
    q=softmin_quality(Z1_normal,beta)
    top=set(np.argsort(-q,kind='stable')[:k])
    sens.append({'beta':beta,'与Q_lin的Spearman':stats.spearmanr(A1.Q_lin,q)[0],'均值':q.mean(),
      '冲突样本平均下调':(q-A1.Q_lin)[A1.is_conflict].mean(),'非冲突样本平均下调':(q-A1.Q_lin)[~A1.is_conflict].mean(),
      '前10%集合与Q_lin的Jaccard':len(top&base_top)/len(top|base_top)})
SENS=pd.DataFrame(sens);display(SENS)
tau_sens=pd.DataFrame([{'相关阈值':t,'冲突指标对数':int((PAIRS.Pearson<=-t).sum()),'冲突样本占比':float((sample_conflict(Z1_normal,t)>0).mean()),'平均CI':sample_conflict(Z1_normal,t).mean()} for t in [.2,.3,.4,.5]])
display(tau_sens)
# ---- 图 7 ----
fig = plt.figure(figsize=(11, 5.0))
gs = gridspec.GridSpec(1, 2, width_ratios=[1.1, 1], wspace=0.3)
ax = fig.add_subplot(gs[0])
idx = RNG.choice(len(A1), 15000, replace=False)
sc = ax.scatter(A1['Q_lin'].values[idx], A1['Q_res'].values[idx], c=A1['CI'].values[idx], cmap=CMAP_TC, s=6, alpha=0.6, linewidths=0)
lim = (min(A1['Q_lin'].min(), A1['Q_res'].min()) - 0.1, max(A1['Q_lin'].max(), A1['Q_res'].max()) + 0.1); ax.plot(lim, lim, color='#333333', lw=1, ls='--'); ax.set_xlim(lim); ax.set_ylim(lim)
cb = plt.colorbar(sc, ax=ax, shrink=0.85); cb.set_label('冲突强度 CI')
ax.set_xlabel('线性综合分 Q_lin（可补偿）'); ax.set_ylabel('消解后综合分 Q_res（指数凹聚合）'); ax.set_title('(a) 消解前后的样本级评分（随机 15,000 条）', fontsize=10.5)
ax = fig.add_subplot(gs[1])
xs = np.linspace(A1['dQ'].min(), 0.02, 300)
for mask, c, lab_ in ((~A1['is_conflict'], C_TEAL, '非冲突样本 (CI = %.1f)' % TAU), (A1['is_conflict'], C_CORAL, '冲突样本 (CI > %.1f)' % TAU)):
    v = A1.loc[mask, 'dQ'].values
    if len(v) < 2 or np.std(v) == 0: continue
    ax.fill_between(xs, stats.gaussian_kde(v)(xs), color=c, alpha=0.3); ax.plot(xs, stats.gaussian_kde(v)(xs), color=c, lw=2, label='%s，均值 %.3f' % (lab_, v.mean()))
ax.axvline(0, color='#333333', lw=1); ax.set_xlabel('Q_res - Q_lin'); ax.set_ylabel('密度'); ax.legend(frameon=False, fontsize=9); ax.set_title('(b) 消解带来的评分调整量分布', fontsize=10.5)
savefig('fig07_resolution.png'); plt.show()

# %% [markdown]
# ### 2.4 用原始文本内容检验评分可靠性
#
# 题目要求"最后用原始教材内容检验评分是否可靠"。A1 自带 `content` 全文，读取时保留了每条记录的 **前 200 字符快照** 和三个 **不属于 22 个指标** 的内容侧统计量：URL 密度（每千字符 URL 数）、非 ASCII 字符占比、行数。检验分两步：
# 1. **定性**：打印 $Q^{res}$ 最高、最低以及冲突强度最高的样本各 3 条，人工核对文本；
# 2. **定量**：按 $Q^{res}$ 五分位分组，看 URL 密度、非 ASCII 占比以及营销类关键词命中率是否随质量分单调下降——这些量没有直接参与评分，仅为辅助核验；非 ASCII 比例和 URL 密度不是人工质量标签，也不必然与质量负相关。

# %%
# ============ 2.4 内容检验 ============
def show(df, title, k=3):
    print('=' * 110); print(title); print('=' * 110)
    for _, r in df.head(k).iterrows():
        print('[%s] Q_lin=%.3f Q_res=%.3f CI=%.3f | %s' % (r['domain'],r['Q_lin'],r['Q_res'],r['CI'],r['代表冲突指标对']))
        print('    22 项正态分数: '+'; '.join('%s=%.2f'%(SHORT[j],Z1_normal.loc[r.name,j]) for j in INDICATORS))
        print('    ' + str(r['snippet'])[:180]); print()
show(A1.sort_values('Q_res', ascending=False), 'Q_res 最高的样本')
show(A1.sort_values('Q_res'), 'Q_res 最低的样本')
show(A1.sort_values('CI', ascending=False), '冲突强度最高的样本（可看到"冲突指标一高一低"）')

A1['url_density'] = 1000 * A1['n_url'] / A1['n_chars'].clip(lower=1)
KW = ['click here', 'subscribe', 'buy now', 'free shipping', 'sign up', 'discount', 'cookie', 'log in', 'add to cart', 'best price', 'coupon', 'newsletter']
snip = A1['snippet'].fillna('').str.lower()
A1['kw_hit'] = np.column_stack([snip.str.contains(k, regex=False) for k in KW]).any(axis=1)
A1['Q_quint'] = pd.qcut(A1['Q_res'].rank(method='first'), 5, labels=['Q1(最低)', 'Q2', 'Q3', 'Q4', 'Q5(最高)'])
qc = A1.groupby('Q_quint').agg(URL密度=('url_density', 'mean'), 非ASCII占比=('frac_nonascii', 'mean'), 营销词命中率=('kw_hit', 'mean'), n=('kw_hit', 'size'))
print('\n按 Q_res 五分位的内容侧独立指标（未参与评分）:'); display(qc)
for col in ['url_density', 'frac_nonascii']:
    print('Spearman(Q_res, %s) = %.3f' % (col, stats.spearmanr(A1['Q_res'], A1[col].fillna(0))[0]))

fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
for ax, (col, lab_, c) in zip(axes, (('URL密度', 'URL 密度（个 / 千字符）', C_NAVY), ('非ASCII占比', '非 ASCII 字符占比', C_TEAL), ('营销词命中率', '营销类关键词命中率（前 200 字符）', C_CORAL))):
    ax.bar(qc.index.astype(str), qc[col], color=c, edgecolor='white', width=0.6)
    for i, v in enumerate(qc[col]):
        ax.text(i, v, '%.3g' % v, ha='center', va='bottom', fontsize=8.5)
    ax.set_ylabel(lab_); ax.set_xlabel('Q_res 五分位'); ax.set_title(lab_ + ' vs 质量分', fontsize=10.5)
plt.tight_layout(); savefig('fig08_content_check.png'); plt.show()

# %% [markdown]
# ### 2.5 扩展集验证
#
# A1 的 arxiv/github 子集分别与 A2/A3 比较 Pearson 矩阵、冲突指标对复现和固定 A1 规则下的样本冲突率、惩罚及排序。各附件均全量评分，合并领域汇总按 domain/id 去重，避免重复文档多次加权。原文内容指标只提供辅助证据，不冒充人工标签。

# %%
corr_ext=[]
for d,Ze in [('arxiv',Z2_normal),('github',Z3_normal)]:
    ra=Z1_normal.loc[A1.domain==d].corr(); rb=Ze.corr()
    iu=np.triu_indices(22,1); va=ra.to_numpy()[iu];vb=rb.to_numpy()[iu];ok=np.isfinite(va)&np.isfinite(vb)
    ea=set(np.flatnonzero(va<=-R_THRESHOLD));eb=set(np.flatnonzero(vb<=-R_THRESHOLD))
    corr_ext.append({'域':d,'相关结构Spearman':stats.spearmanr(va[ok],vb[ok])[0],'A1域内冲突对数':len(ea),'扩展冲突对数':len(eb),'冲突对Jaccard':len(ea&eb)/len(ea|eb) if ea|eb else np.nan})
    rb.to_csv(TAB/('Pearson扩展_'+d+'.csv'),encoding='utf-8-sig')
CORR_EXT=pd.DataFrame(corr_ext); display(CORR_EXT)
CORR_EXT.to_csv(TAB/'Pearson扩展复现.csv',index=False,encoding='utf-8-sig')
# 2.5 固定 A1 冲突规则下的扩展集检验
ext_rows = []
for d, Ae in [('arxiv', A2), ('github', A3)]:
    sub = A1.loc[A1.domain.eq(d)]
    ext_rows.append({'域': d, 'A1子集n': len(sub), '扩展集n': len(Ae),
        '冲突样本占比_A1': sub.is_conflict.mean(), '冲突样本占比_扩展': Ae.is_conflict.mean(),
        '平均CI_A1': sub.CI.mean(), '平均CI_扩展': Ae.CI.mean(),
        '冲突样本下调_A1': (sub.Q_res-sub.Q_lin)[sub.is_conflict].mean(),
        '冲突样本下调_扩展': (Ae.Q_res-Ae.Q_lin)[Ae.is_conflict].mean(),
        'Spearman(Qlin,Qres)_A1': stats.spearmanr(sub.Q_lin,sub.Q_res)[0],
        'Spearman(Qlin,Qres)_扩展': stats.spearmanr(Ae.Q_lin,Ae.Q_res)[0]})
EXT = pd.DataFrame(ext_rows)
print('固定 A1 全局规则下的冲突与评分对照：')
display(EXT.T)
EXT.to_csv(TAB/'conflict_extended_check.csv',index=False,encoding='utf-8-sig')

# 图 9：A1 对应域内反向相关最强的 12 对在扩展集上的复现。
fig, axes = plt.subplots(1, 2, figsize=(16, 6.5))
for ax, (d, Ze) in zip(axes, [('arxiv', Z2_normal), ('github', Z3_normal)]):
    ra = Z1_normal.loc[A1.domain.eq(d)].corr()
    rb = Ze.corr()
    ranked = sorted([(ra.loc[a,b],a,b) for a,b in itertools.combinations(INDICATORS,2)
                     if np.isfinite(ra.loc[a,b]) and np.isfinite(rb.loc[a,b])])[:12]
    va = np.array([r for r,a,b in ranked]); vb = np.array([rb.loc[a,b] for r,a,b in ranked])
    yy = np.arange(len(ranked))[::-1]
    ax.hlines(yy,va,vb,color='#BBBBBB',lw=2)
    ax.scatter(va,yy,color=C_NAVY,label='A1 对应域子集',zorder=3)
    ax.scatter(vb,yy,color=C_CORAL,label='扩展集全量',zorder=3)
    ax.axvline(-R_THRESHOLD,color=C_GREY,ls='--',label='相关阈值 −0.30')
    ax.set_yticks(yy)
    ax.set_yticklabels([SHORT[a]+' × '+SHORT[b] for r,a,b in ranked],fontsize=8)
    ax.set_xlabel('正态分数的 Pearson 相关系数')
    ax.set_title(d+'：反向相关最强的 12 对');ax.legend(frameon=False,fontsize=8)
plt.tight_layout();savefig('fig09_extended_conflict_check.png');plt.show()

# ---- 最终域级 Q 表（线性 + 消解后；A1、扩展集、以及 arxiv/github 的合并全量） ----
DT_res = domain_table([('A1 抽样集', A1), ('A2 扩展集', A2), ('A3 扩展集', A3)], 'Q_res')
pool = pd.concat([A1[A1['domain'].isin(['arxiv', 'github'])], A2, A3], ignore_index=True)
pool_before = len(pool)
assert pool[['domain','id']].notna().all().all(), '去重键存在缺失，需先核查'
pool = pool.drop_duplicates(['domain','id'])
print('合并记录数 / 去重后:', pool_before, len(pool))
DT_pool = domain_table([('抽样+扩展 合并全量', pool)], 'Q_res')
DOMAIN_Q = pd.concat([DT_res, DT_pool], ignore_index=True)
DT_lin_all = pd.concat([DT_lin, domain_table([('抽样+扩展 合并全量', pool)], 'Q_lin')], ignore_index=True)
DOMAIN_Q = DOMAIN_Q.merge(DT_lin_all[['数据集', '域', 'Q_lin_doc均值', 'Q_lin_语料(词数加权)']], on=['数据集', '域'], how='left')
DOMAIN_Q.to_csv(TAB / 'domain_Q.csv', index=False, encoding='utf-8-sig')
print('最终域级质量评分表（Q_res 为消解后综合分；已保存 tables/domain_Q.csv）:'); display(DOMAIN_Q)

# 样本级评分导出（供论文附录 / 问题二）
for A, name in ((A1, 'A1'), (A2, 'A2'), (A3, 'A3')):
    A[['id', 'domain', 'Q_lin', 'Q_res', 'CI', 'is_conflict']].to_csv(TAB / ('sample_Q_%s.csv' % name), index=False, encoding='utf-8-sig')

# %% [markdown]
# ## 3. 领域配比建模
#
# 领域配比与损失建模：比较线性混料、对数线性混料、加性样条和GBM。经综合权衡，选择对数线性模型作为主模型，用于关系解释与约束配比求解；GBM作为对照模型，其预测表现整体较强，用于比较和辅助核查。模型选择不等于单项预测指标排名第一。
#
# ### 3.1 四模型与训练集内选择
#
# A4/A5 含 512 组 17 域训练配比及对应的 13 域验证损失。A6–A11 是 1M、60M、1B 的检验数据，样本数分别为 256、256、64；A12–A15 是 63 个训练配比在 10B/70B 的幂律外推数据，不能作为直接观测或独立检验集。
#
# 统一目标为 13 域平均损失，配比满足非负且和为 1：
#
# $$
# \bar L(\mathbf p)=\frac{1}{13}\sum_{v=1}^{13}L_v(\mathbf p).
# $$
#
# 四个无对应验证损失的训练域仍占用配比份额，保留为输入。下表中的样条模型单独采用 PDF 的参考域参数化。
#
# | 候选模型 | 形式与设置 | 训练内待选参数 |
# |---|---|---|
# | 线性混料 | 17 域份额的线性组合，不另设截距 | 无 |
# | 对数线性混料 | 17 域平滑对数份额的线性组合 | ε：0.0001、0.001、0.01、0.03 |
# | 加性样条（PDF） | 省略参考域 uspto_backgrounds；16 域分别使用 4 节点、二次 B 样条，再标准化和岭回归 | α：0.001、0.01、0.1、1、10、100、1000 |
# | 梯度提升树 GBM | 学习率 0.03、子采样率 0.8、随机种子 0 | 树数：300/500；最大深度：2/3 |
#
# 加性样条 = 每个领域份额分别拟合平滑曲线后相加。沿用 PDF 第 6.3 节的节点数、次数、参考域和线性外推设置；PDF 没有明确节点位置，本文固定为均匀节点。样条节点和标准化均只在相应训练折拟合。删去参考域是模型结构选择，不是对非线性模型无影响的代数简化；该模型也没有显式领域交互项。
#
# **评价流程。** 使用训练集内嵌套交叉验证：外层 5 折（随机种子 0）产生每个样本的折外预测；有待选参数的模型只在外层训练部分再做内层 5 折（随机种子 1），按均方误差选参。线性基线没有调参。各模型最终参数另由完整 A4/A5 内部 5 折确定，再对完整训练集拟合。以外层折外 RMSE 比较预测表现；RMSE 相同时参考排序相关。该排名用于性能比较，不直接决定主模型定位。主模型另按研究用途确定：综合预测能力、可解释性和约束配比求解便利性，采用对数线性。此项取舍不代表其预测误差最小，也不通过改变评价指标掩盖 GBM 的优势。参数选择与交叉验证排名均不读取检验集或外推表结果。由于这些检验集在既往分析中已被查看，本次是纠正计算流程后的固定检验评价，不称为全新盲测。
#
# 报告训练、外层折外验证、三个检验尺度的 R²、RMSE、MAE 与 Spearman。RMSE = 均方根误差，MAE = 平均绝对误差，越小越好；Spearman = 配比排序相关，越大越好。跨尺度 R² 与绝对误差衡量未经尺度校准的损失预测，负 R² 表示不如该检验集均值基线，不能略去；配比排序能力单独判断。
#
# **对数线性的解释。**
#
# $$
# \widehat{\bar L}(\mathbf p)=c+\sum_{i=1}^{17}a_i\ln(p_i+\varepsilon).
# $$
#
# 这是收益递减的候选近似，不是由标度律唯一推出的形式；只有拟合得到 a_i<0 的域才具有该形式下的收益递减。线性基线也不能仅因形式简单就事先判为不成立。
#
# $$
# \frac{\partial\widehat{\bar L}}{\partial p_i}=\frac{a_i}{p_i+\varepsilon},
# \qquad
# \frac{\partial\widehat{\bar L}}{\partial\ln p_i}=\frac{a_i p_i}{p_i+\varepsilon}.
# $$
#
# a_i 是对数特征系数，不是损失弹性。损失弹性 = 损失相对变化率除以份额相对变化率，还需将第二式除以预测损失。在份额和为 1 的约束下，实际增加一个域必须减少其他域；沿“从其他域按当前比例转入域 i”的方向，边际效应为
#
# $$
# g_i(\mathbf p)=\frac{a_i}{p_i+\varepsilon}-\sum_k\frac{a_kp_k}{p_k+\varepsilon}.
# $$
#
# 该方向满足配比约束；g_i<0 表示在指定配比附近，该方向预测降低损失。对数线性作为解释和配比求解主模型，GBM 作为对照模型用于比较和辅助核查，交叉验证排名单独报告。

# %%
# ============ 3.1 读取配比实验数据 ============
def load_pair(mix_name, loss_name):
    mix = pd.read_csv(REG / mix_name); loss = pd.read_csv(REG / loss_name)
    mc = [c for c in mix.columns if c.startswith('train_')]; lc = [c for c in loss.columns if c.endswith('_val_loss')]
    df = mix[['index'] + mc].merge(loss[['index'] + lc], on='index')
    P = df[mc].values.astype(float); P = P / P.sum(axis=1, keepdims=True)   # 消除千分位舍入误差，严格落在单纯形上
    return df, P, df[lc].values.astype(float), mc, lc

TR, P_tr, Y_tr, MIX_COLS, LOSS_COLS = load_pair('train_mixture_1m.csv', 'train_pile_loss_1m.csv')
DOM17 = [c.replace('train_the_pile_', '') for c in MIX_COLS]
VAL13 = [c.replace('metric/the_pile_', '').replace('_val_loss', '') for c in LOSS_COLS]
TESTS = {'1M 检验集 (A6/A7)': load_pair('test_mixture_1m.csv', 'test_pile_loss_1m.csv'),
         '60M 检验集 (A8/A9)': load_pair('test_mixture_60m.csv', 'test_pile_loss_60m.csv'),
         '1B 检验集 (A10/A11)': load_pair('test_mixture_1B.csv', 'test_pile_loss_1B.csv')}
ESTS = {'10B 外推表 (A12/A13)': load_pair('est_mixture_10b.csv', 'est_pile_loss_10b.csv'),
        '70B 外推表 (A14/A15)': load_pair('est_mixture_70b.csv', 'est_pile_loss_70b.csv')}
y_tr = Y_tr.mean(axis=1)
print('训练集: %d 组配比 × %d 个域;  验证损失 %d 个域;  无验证损失的域: %s' % (len(TR), len(DOM17), len(VAL13), sorted(set(DOM17) - set(VAL13))))
for k, (df, P, Y, _, _) in list(TESTS.items()) + list(ESTS.items()):
    print('  %-22s n=%3d  平均损失 %.3f ± %.3f' % (k, len(df), Y.mean(), Y.mean(axis=1).std()))
print('训练集平均损失 %.3f ± %.3f，配比行和范围 [%.3f, %.3f]' % (y_tr.mean(), y_tr.std(), TR[MIX_COLS].sum(axis=1).min(), TR[MIX_COLS].sum(axis=1).max()))
print('外推表配比与训练集重合: %d / 63 行 index 相同' % len(set(ESTS['10B 外推表 (A12/A13)'][0]['index']) & set(TR['index'])))

# ---- 图 10：配比实验数据总览 ----
fig = plt.figure(figsize=(16, 5.8))
gs = gridspec.GridSpec(1, 3, width_ratios=[1.1, 0.9, 1], wspace=0.42)
ax = fig.add_subplot(gs[0])
Pdf = pd.DataFrame(P_tr, columns=DOM17); order_p = Pdf.median().sort_values().index
bp = ax.boxplot([Pdf[d] for d in order_p], vert=False, patch_artist=True, widths=0.6, showfliers=True, flierprops=dict(marker='.', markersize=3, alpha=0.4, color=C_GREY))
for patch in bp['boxes']: patch.set(facecolor=C_NAVY, alpha=0.55, edgecolor=C_NAVY)
for med in bp['medians']: med.set(color=C_GOLD, lw=1.6)
ax.set_yticks(np.arange(1, len(order_p) + 1)); ax.set_yticklabels(order_p, fontsize=8.5); ax.set_xlabel('配比 p_i'); ax.set_title('(a) 512 组训练配比中各域份额的分布', fontsize=10.5)
ax = fig.add_subplot(gs[1])
Ldf = pd.DataFrame(Y_tr, columns=VAL13); order_l = Ldf.median().sort_values().index
bp = ax.boxplot([Ldf[d] for d in order_l], vert=False, patch_artist=True, widths=0.6, flierprops=dict(marker='.', markersize=3, alpha=0.4, color=C_GREY))
for patch in bp['boxes']: patch.set(facecolor=C_TEAL, alpha=0.55, edgecolor=C_TEAL)
for med in bp['medians']: med.set(color=C_CORAL, lw=1.6)
ax.set_yticks(np.arange(1, len(order_l) + 1)); ax.set_yticklabels(order_l, fontsize=8.5); ax.set_xlabel('验证集交叉熵损失'); ax.set_title('(b) 13 个验证域损失的分布（1M 训练集）', fontsize=10.5)
ax = fig.add_subplot(gs[2])
# 单域"份额-损失"关系：以 pile_cc 与 dm_mathematics 为例展示边际收益递减（对数横轴）
for d, c in (('pile_cc', C_NAVY), ('dm_mathematics', C_CORAL), ('stackexchange', C_TEAL)):
    i = DOM17.index(d); ax.scatter(P_tr[:, i] + 1e-3, y_tr, s=10, color=c, alpha=0.45, edgecolor='none', label=d)
    bins = np.quantile(P_tr[:, i] + 1e-3, np.linspace(0, 1, 9)); ctr, mean_ = [], []
    for lo_, hi_ in zip(bins[:-1], bins[1:]):
        m_ = (P_tr[:, i] + 1e-3 >= lo_) & (P_tr[:, i] + 1e-3 <= hi_)
        if m_.sum() > 3: ctr.append(np.exp(np.log(P_tr[m_, i] + 1e-3).mean())); mean_.append(y_tr[m_].mean())
    ax.plot(ctr, mean_, color=c, lw=2.2, marker='o', ms=4)
ax.set_xscale('log'); ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: '%g' % v)); ax.xaxis.set_minor_formatter(mpl.ticker.NullFormatter())
ax.set_xlabel('域份额 p_i + 0.001（对数轴）'); ax.set_ylabel('13 域平均损失'); ax.legend(frameon=False, fontsize=9)
ax.set_title('(c) 单域份额与平均损失：先降后升（本域收益递减 + 挤占其他域）', fontsize=10.5)
savefig('fig10_regmix_overview.png'); plt.show()

# %%
# 3.1 四类代理模型：训练集内嵌套交叉验证与独立检验
# 所有模型直接接收完整17域配比；样条管道内部按列名固定删除参考域。
from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, SplineTransformer, StandardScaler
from sklearn.model_selection import GridSearchCV

MODEL_NAMES = ['线性混料', '对数线性混料', '加性样条（PDF）', '梯度提升树 GBM']
EPS_GRID = [1e-4, 1e-3, 1e-2, 3e-2]
ALPHA_GRID = [.001, .01, .1, 1., 10., 100., 1000.]
REFERENCE_DOMAIN = 'uspto_backgrounds'
REFERENCE_IDX = DOM17.index(REFERENCE_DOMAIN)
SPLINE_KEEP = [i for i in range(17) if i != REFERENCE_IDX]
def log_features(P, epsilon=1e-3):
    return np.log(np.asarray(P, float) + epsilon)
def spline_columns(P):
    return np.asarray(P, float)[:, SPLINE_KEEP]
def model_spec(name):
    if name == MODEL_NAMES[0]:
        return LinearRegression(fit_intercept=False), {}
    if name == MODEL_NAMES[1]:
        return Pipeline([('log', FunctionTransformer(log_features, kw_args={'epsilon':1e-3})),
                         ('linear', LinearRegression())]), {'log__kw_args':[{'epsilon':e} for e in EPS_GRID]}
    if name == MODEL_NAMES[2]:
        return Pipeline([('columns', FunctionTransformer(spline_columns)),
            ('spline', SplineTransformer(n_knots=4, degree=2, knots='uniform',
                                         extrapolation='linear', include_bias=True)),
            ('standard', StandardScaler()), ('ridge', Ridge())]), {'ridge__alpha':ALPHA_GRID}
    return GradientBoostingRegressor(learning_rate=.03, subsample=.8, random_state=0), {
        'n_estimators':[300,500], 'max_depth':[2,3]}

def metrics(y, yhat):
    return {'Spearman':stats.spearmanr(y,yhat)[0], 'Pearson':stats.pearsonr(y,yhat)[0],
            'R2':1-np.sum((y-yhat)**2)/np.sum((y-y.mean())**2),
            'RMSE':float(np.sqrt(np.mean((y-yhat)**2))), 'MAE':float(np.mean(np.abs(y-yhat)))}
def fit_train_only(name, P, y):
    model, grid = model_spec(name)
    if not grid:
        return model.fit(P,y), {}, None
    search = GridSearchCV(model, grid, scoring='neg_mean_squared_error',
                         cv=KFold(5,shuffle=True,random_state=1), n_jobs=1, refit=True)
    search.fit(P,y)
    return search.best_estimator_, search.best_params_, search.cv_results_

# 外层留出折从未用于该折的选参、样条节点拟合或标准化。
OUTER_SPLITS = list(KFold(5,shuffle=True,random_state=0).split(P_tr))
FITTED, PRED, OOF, PARAMS = {}, {}, {}, {}
metric_rows, fold_rows, pred_rows, tune_rows = [], [], [], []
cv_fold_id = np.zeros(len(P_tr),dtype=int)
for fold, (tr_i,va_i) in enumerate(OUTER_SPLITS,1): cv_fold_id[va_i]=fold
for name in MODEL_NAMES:
    print('拟合与嵌套验证:', name, flush=True)
    cv_pred = np.full(len(y_tr),np.nan)
    for fold,(tr_i,va_i) in enumerate(OUTER_SPLITS,1):
        assert not np.intersect1d(tr_i,va_i).size
        fitted, params, _ = fit_train_only(name,P_tr[tr_i],y_tr[tr_i])
        cv_pred[va_i] = fitted.predict(P_tr[va_i])
        fold_rows.append({'模型':name,'外层折':fold,'训练数':len(tr_i),'验证数':len(va_i),
                          '所选参数':json.dumps(params,ensure_ascii=False),**metrics(y_tr[va_i],cv_pred[va_i])})
    assert np.isfinite(cv_pred).all()
    OOF[name] = cv_pred
    fitted,params,search_results = fit_train_only(name,P_tr,y_tr)
    FITTED[name]=fitted;PARAMS[name]=params
    if search_results is not None:
        for p_, score, sd in zip(search_results['params'],search_results['mean_test_score'],search_results['std_test_score']):
            tune_rows.append({'模型':name,'参数':json.dumps(p_,ensure_ascii=False),
                              '训练内CV均方误差':-score,'折间均方误差标准差':sd})
    for label,pred in [('训练集',fitted.predict(P_tr)),('外层5折CV',cv_pred)]:
        metric_rows.append({'模型':name,'数据集':label,'n':len(y_tr),**metrics(y_tr,pred)})
    for idx,y,pred,fold in zip(TR['index'],y_tr,cv_pred,cv_fold_id):
        pred_rows.append({'模型':name,'配比编号':idx,'外层折':int(fold),'真实平均损失':y,'折外预测':pred})

# 在读取任何检验预测结果前，按训练集折外RMSE记录性能排名；主模型定位另行综合权衡。
CV_METRICS = pd.DataFrame([r for r in metric_rows if r['数据集']=='外层5折CV']).set_index('模型')
CV_WINNER = CV_METRICS.sort_values(['RMSE','Spearman'],ascending=[True,False]).index[0]
MAIN_MODEL = MODEL_NAMES[1]
SELECTED_MODEL = MAIN_MODEL  # 后续求解与接口使用主模型；不冒充CV冠军
print('交叉验证预测性能优胜模型:',CV_WINNER)
print('解释与配比求解主模型:',MAIN_MODEL)
for name,fitted in FITTED.items():
    for tn,(df,P,Y,_,_) in TESTS.items():
        yh=fitted.predict(P);PRED[(name,tn)]=yh
        metric_rows.append({'模型':name,'数据集':tn,'n':len(df),**metrics(Y.mean(axis=1),yh)})
METRICS_LONG = pd.DataFrame(metric_rows)
METRICS_LONG.to_csv(TAB/'mixture_model_metrics_long.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(fold_rows).to_csv(TAB/'mixture_outer_fold_metrics.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(pred_rows).to_csv(TAB/'mixture_oof_predictions.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(tune_rows).to_csv(TAB/'mixture_train_only_tuning.csv',index=False,encoding='utf-8-sig')
EVAL=METRICS_LONG.pivot(index='模型',columns='数据集',values=['R2','RMSE','MAE','Spearman'])
EVAL=EVAL.reindex(MODEL_NAMES)
EVAL.to_csv(TAB/'mixture_model_eval.csv',encoding='utf-8-sig')
print('全部结果：目标为13域平均损失；跨尺度绝对误差为未校准预测误差。')
display(METRICS_LONG.round(5))
print('仅用全部A4/A5内部CV选定的参数:',PARAMS)
(TAB/'mixture_selection_protocol.json').write_text(json.dumps({
    'selection_rule':'CV benchmark: minimum outer OOF RMSE; main model: loglinear for interpretation and constrained optimization; train-only tuning',
    'outer_seed':0,'inner_seed':1,'folds':5,'target':'mean of 13 validation losses',
    'cv_winner':CV_WINNER,'main_model':MAIN_MODEL,'selected_predictive_model':SELECTED_MODEL,'interpretive_model':MAIN_MODEL,
    'main_model_rationale':'prediction-interpretability-optimization tradeoff; not the lowest CV error',
    'final_parameters':PARAMS,'spline_reference':REFERENCE_DOMAIN,'spline_knots':'uniform',
    'spline_n_knots':4,'spline_degree':2,'spline_extrapolation':'linear',
    'scope':'conditional comparison of stated candidate grids; existing test sets have been inspected in earlier analyses, not a newly untouched holdout'
},ensure_ascii=False,indent=2), encoding='utf-8')
# 对数线性为关系解释与约束配比求解主模型；GBM为对照及辅助核查模型。
EPS_LOG=float(PARAMS[MODEL_NAMES[1]]['log__kw_args']['epsilon'])
def zlog(P):return log_features(P,EPS_LOG)
model_l=FITTED[MODEL_NAMES[1]].named_steps['linear']
model_s=FITTED[MODEL_NAMES[2]]
model_g=FITTED[MODEL_NAMES[3]]
pred_log=lambda P:FITTED[MODEL_NAMES[1]].predict(np.asarray(P,float))
pred_spline=lambda P:model_s.predict(np.asarray(P,float))
pred_gbm=lambda P:model_g.predict(np.asarray(P,float))

# 图11：四模型在三个尺度的原始预测；不在检验集拟合校准线。
fig,axes=plt.subplots(4,3,figsize=(15,15))
for row,name in enumerate(MODEL_NAMES):
    for ax,(tn,(df,P,Y,_,_)) in zip(axes[row],TESTS.items()):
        y=Y.mean(axis=1);yh=PRED[(name,tn)];mt=metrics(y,yh)
        ax.scatter(yh,y,s=15,alpha=.65,color=[C_GREY,C_NAVY,C_TEAL,C_PLUM][row])
        limits=[min(y.min(),yh.min()),max(y.max(),yh.max())]
        ax.plot(limits,limits,'--',color=C_CORAL,lw=1,label='预测 = 实测')
        ax.text(.03,.97,'rho=%.3f\nR2=%.3f\nRMSE=%.3f'%(mt['Spearman'],mt['R2'],mt['RMSE']),
                transform=ax.transAxes,va='top',fontsize=9)
        ax.set_xlabel(name+'：1M尺度预测');ax.set_ylabel('实测平均损失');ax.set_title(tn)
plt.tight_layout();savefig('fig11_test_pred_vs_actual.png');plt.show()

# %% [markdown]
# ### 3.1.1 四模型比较结果
#
# 统一目标：13 个验证域的平均损失。外层 CV 数值由全部 512 条折外预测计算，不是训练拟合值。
#
# | 模型 | 训练 R² | 训练 RMSE | 外层 CV R² | 外层 CV RMSE | 外层 CV Spearman |
# |---|---:|---:|---:|---:|---:|
# | 线性混料 | 0.2961 | 0.2722 | 0.2311 | 0.2845 | 0.4935 |
# | 对数线性混料 | 0.8559 | 0.1232 | 0.8450 | 0.1277 | 0.9413 |
# | 加性样条（PDF） | 0.8067 | 0.1427 | 0.7414 | 0.1650 | 0.8695 |
# | 梯度提升树 GBM | 0.9918 | 0.0294 | 0.9105 | 0.0971 | 0.9611 |
#
# | 模型 | 1M Spearman | 1M RMSE | 60M Spearman | 60M RMSE | 1B Spearman | 1B RMSE |
# |---|---:|---:|---:|---:|---:|---:|
# | 线性混料 | 0.6245 | 0.2278 | 0.5584 | 1.5205 | 0.3685 | 3.1943 |
# | 对数线性混料 | 0.9316 | 0.1071 | 0.9116 | 1.4894 | 0.7548 | 2.6679 |
# | 加性样条（PDF） | 0.8838 | 0.1345 | 0.8727 | 1.4990 | 0.5206 | 2.7587 |
# | 梯度提升树 GBM | 0.9671 | 0.0760 | 0.9301 | 1.4923 | 0.7211 | 2.8133 |
#
# 领域配比与损失建模：比较线性混料、对数线性混料、加性样条和GBM。经综合权衡，选择对数线性模型作为主模型，用于关系解释与约束配比求解；GBM作为对照模型，其预测表现整体较强，用于比较和辅助核查。模型选择不等于单项预测指标排名第一。
#
# 对数线性在 1B 检验排序上有优势，但这不是训练内选参依据。不能据训练集拟合优度或某一个检验尺度宣布跨尺度全面最优。完整 MAE、R²、Pearson 与分折参数见导出表。

# %% [markdown]
# ### 3.2 单域影响与可行配比替代
#
# 对数线性模型报告对数特征系数 a_i 与 Bootstrap 95% 区间（512 组配比重抽样 500 次）。区间固定训练内选定的 ε，未包含选参不确定性。系数符号不等于配比约束下的净收益；实际方向效应使用第 3.1 节的 g_i，并比较训练均值配比与均匀配比。
#
# **组合分析采用可行替代，不把回归系数符号称为互补或因果作用。** 从领域 i 向领域 k 转移 δ 份额，其他域不变：
#
# $$
# \Delta_{i\to k}(\mathbf p;\delta)=
# \widehat{\bar L}\bigl(\mathbf p+\delta(\mathbf e_k-\mathbf e_i)\bigr)
# -\widehat{\bar L}(\mathbf p).
# $$
#
# 在训练平均配比处，全域两两比较 δ=0.001（0.1 个百分点）；另按 PDF 的定义，从 uspto_backgrounds 向其他域转移 0.01（1 个百分点），比较对数线性、样条与 GBM 的局部预测。这些是指定方向和幅度的替代效应，不是交互系数，更不证明领域间的真实互补机制。
#
# 逐验证域拟合对数线性模型，得到 17×13 的系数；展示训练均值配比处可行方向 g_i 的迁移矩阵，负值表示该配比附近向该训练域转移份额预测降低相应验证域损失。同名域是否最有利由结果判断。

# %%
# ============ 3.2 对数特征系数、边际效应、交互与迁移矩阵 ============
A_LOG = pd.Series(model_l.coef_, index=DOM17)
t0 = time.time(); B = 500; rng = np.random.default_rng(1); A_boot = np.zeros((B, 17))
Ztr = zlog(P_tr)
for b in range(B):
    idx = rng.integers(0, len(P_tr), len(P_tr)); A_boot[b] = LinearRegression().fit(Ztr[idx], y_tr[idx]).coef_
print('Bootstrap %d 次耗时 %.1fs' % (B, time.time() - t0))

def simplex_effect(a, p, eps=EPS_LOG):
    grad = a / (p + eps); return grad - (grad * p).sum()
p_mean = P_tr.mean(axis=0); uniform = np.ones(17) / 17
ME = pd.DataFrame({'对数特征系数 a_i': A_LOG, 'CI低': np.percentile(A_boot, 2.5, axis=0), 'CI高': np.percentile(A_boot, 97.5, axis=0),
                   '边际效应@训练均值配比': simplex_effect(A_LOG.values, p_mean), '边际效应@均匀配比': simplex_effect(A_LOG.values, uniform),
                   '有验证损失': [d in VAL13 for d in DOM17], '训练集平均份额': p_mean}, index=DOM17).sort_values('对数特征系数 a_i')
print('对数特征系数与配比约束下的方向效应（解释净收益请看边际效应列）:'); display(ME)
print('检验：p 加权的边际效应之和 = %.2e（理论值 0）' % (p_mean * ME.loc[DOM17, '边际效应@训练均值配比']).sum())
ME.to_csv(TAB / 'domain_marginal_effects.csv', encoding='utf-8-sig')

# 以满足单纯形约束的有限转移代替非约束交互系数解释。
TRANSFER_DELTA=.001
assert p_mean.min()>=TRANSFER_DELTA
transfer_predictors={'对数线性':pred_log,'加性样条':pred_spline,'GBM':pred_gbm}
transfer_rows=[]
for model_name,predict in transfer_predictors.items():
    baseline=float(predict(p_mean.reshape(1,-1))[0])
    for i in range(17):
        for k in range(17):
            if i==k:continue
            pp=p_mean.copy();pp[i]-=TRANSFER_DELTA;pp[k]+=TRANSFER_DELTA
            assert pp.min()>=0 and np.isclose(pp.sum(),1)
            transfer_rows.append({'模型':model_name,'转出域':DOM17[i],'转入域':DOM17[k],
                '转移份额':TRANSFER_DELTA,'预测损失变化':float(predict(pp.reshape(1,-1))[0]-baseline)})
TRANSFER_EFFECTS=pd.DataFrame(transfer_rows)
TRANSFER_EFFECTS.to_csv(TAB/'domain_transfer_effects.csv',index=False,encoding='utf-8-sig')
reference_rows=[]
for model_name,predict in transfer_predictors.items():
    baseline=float(predict(p_mean.reshape(1,-1))[0])
    for k in SPLINE_KEEP:
        pp=p_mean.copy();pp[REFERENCE_IDX]-=.01;pp[k]+=.01
        assert pp.min()>=0 and np.isclose(pp.sum(),1)
        reference_rows.append({'模型':model_name,'转入域':DOM17[k],
                              '预测损失变化':float(predict(pp.reshape(1,-1))[0]-baseline)})
REF_TRANSFER=pd.DataFrame(reference_rows).pivot(index='转入域',columns='模型',values='预测损失变化')
REF_TRANSFER.to_csv(TAB/'reference_domain_transfer_1pp.csv',encoding='utf-8-sig')
print('从专利背景域转出1个百分点的局部预测变化（负值=该替代方向降低损失）：')
display(REF_TRANSFER)

# 跨域迁移矩阵（逐验证域对数线性模型）
T = np.zeros((17, 13)); R2v = {}
for v in range(13):
    m = LinearRegression().fit(Ztr, Y_tr[:, v]); T[:, v] = m.coef_; R2v[VAL13[v]] = m.score(Ztr, Y_tr[:, v])
TRANS = pd.DataFrame(T, index=DOM17, columns=VAL13); TRANS_GRAD=TRANS.div(p_mean+EPS_LOG,axis=0)
TRANS_C=TRANS_GRAD-(TRANS_GRAD.mul(p_mean,axis=0)).sum(axis=0)
TRANS.to_csv(TAB / 'transfer_matrix.csv', encoding='utf-8-sig')
print('逐验证域对数线性模型的训练集 R2:', {k: round(v, 2) for k, v in R2v.items()})
diag_rank = {v: int(TRANS_C[v].rank().loc[v]) for v in VAL13 if v in DOM17}
print('同名域在各验证域列中的名次（1 = 最有帮助）:', diag_rank)

# ---- 图 12：对数特征系数森林图 + 两种配比处的边际效应 ----
fig, axes = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={'width_ratios': [1.15, 1]})
ax = axes[0]; y = np.arange(len(ME))
cols = [C_TEAL if v < 0 else C_CORAL for v in ME['对数特征系数 a_i']]
ax.barh(y, ME['对数特征系数 a_i'], color=cols, alpha=0.35, edgecolor='none')
ax.errorbar(ME['对数特征系数 a_i'], y, xerr=[ME['对数特征系数 a_i'] - ME['CI低'], ME['CI高'] - ME['对数特征系数 a_i']], fmt='o', color='#222222', ecolor='#222222', capsize=3, ms=5)
ax.axvline(0, color='#333333', lw=1)
ax.set_yticks(y); ax.set_yticklabels(['%s%s' % (d, '' if ok else ' *') for d, ok in zip(ME.index, ME['有验证损失'])], fontsize=9.5)
ax.set_xlabel('对数特征系数 a_i（净收益另见右图可行方向）'); ax.set_title('(a) 17 个配方域的对数特征系数（Bootstrap 95% CI；* = 无验证损失的域）', fontsize=10.5)
ax.legend(handles=[Patch(color=C_TEAL, alpha=0.5, label='负对数系数'), Patch(color=C_CORAL, alpha=0.5, label='正对数系数')], frameon=False, loc='lower right')
ax = axes[1]; wbar = 0.38
ax.barh(y + wbar / 2, ME['边际效应@训练均值配比'], wbar, color=C_NAVY, label='在训练集平均配比处')
ax.barh(y - wbar / 2, ME['边际效应@均匀配比'], wbar, color=C_GOLD, label='在均匀配比 (1/17) 处')
ax.axvline(0, color='#333333', lw=1); ax.set_yticks(y); ax.set_yticklabels(ME.index, fontsize=9.5)
ax.set_xlabel('沿单纯形方向的边际效应 g_i(p)（负 = 比当前平均域更值得增加）'); ax.legend(frameon=False, loc='lower left'); ax.set_title('(b) 边际效应随配比位置变化（边际收益递减）', fontsize=10.5)
plt.tight_layout(); savefig('fig12_marginal_effects_forest.png'); plt.show()

# 图13：三模型在相同参考配比与可行转移幅度下对照。
fig,axes=plt.subplots(1,2,figsize=(16,7))
M=TRANSFER_EFFECTS[TRANSFER_EFFECTS['模型']=='加性样条'].pivot(index='转出域',columns='转入域',values='预测损失变化').reindex(index=DOM17,columns=DOM17)
sns.heatmap(M,cmap=CMAP_DIV,center=0,ax=axes[0],cbar_kws={'shrink':.7,'label':'预测损失变化'})
axes[0].set_title('(a) 样条：转移0.1个百分点');axes[0].tick_params(axis='both',labelsize=8)
REF_TRANSFER.sort_values('加性样条').plot.barh(ax=axes[1],color=[C_PLUM,C_TEAL,C_NAVY])
axes[1].axvline(0,color=C_GREY,lw=1);axes[1].set_title('(b) 从专利背景域转出1个百分点')
axes[1].set_xlabel('预测损失变化');axes[1].tick_params(axis='y',labelsize=8)
plt.tight_layout();savefig('fig13_domain_transfer_effects.png');plt.show()

# ---- 图 14：跨域迁移矩阵 ----
fig, ax = plt.subplots(figsize=(11.5, 9))
vm = np.nanpercentile(np.abs(TRANS_C.values), 98)
sns.heatmap(TRANS_C, cmap=CMAP_DIV, center=0, vmin=-vm, vmax=vm, ax=ax, linewidths=0.3, linecolor='white', cbar_kws={'shrink': 0.6, 'label': '训练均值配比处的可行方向效应（负 = 降低损失）'})
ax.grid(False)
for j, v in enumerate(VAL13):
    if v in DOM17:
        i = DOM17.index(v); ax.add_patch(Rectangle((j, i), 1, 1, fill=False, edgecolor=C_GOLD, lw=2.2))
ax.set_xlabel('验证域（13 个）'); ax.set_ylabel('配方域（17 个）'); plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9); plt.setp(ax.get_yticklabels(), fontsize=9)

savefig('fig14_transfer_matrix.png'); plt.show()

# %% [markdown]
# ### 3.3 外推表 A12–A15 上的稳健性讨论
#
# 外推表给出的是训练集中 63 个配比在 10B / 70B 尺度上 **由 1M/60M/1B 三点幂律 $L(N)=E+AN^{-\alpha}$ 逐配比外推** 的损失，不是直接观测。它能回答的问题是："在小尺度上学到的配比排序，经幂律外推后是否保持？"本文从三个层次检验：
#
# 1. **配比排序**：63 个配比在 1M（实测）、10B、70B（外推）三个尺度上平均损失的两两 Spearman 相关，以及 1M 代理模型预测与各尺度损失的相关；
# 2. **逐验证域排序**：对 13 个验证域分别计算 1M 实测与 10B 外推的 Spearman 相关——逐域与平均损失的排序差异用于描述聚合效应；仅凭排序差异不能确定反转的原因；
# 3. **域效应排序**：在每个尺度的数据上分别拟合对数线性模型，比较 17 个域对数特征系数 $a_i$ 的排序在各尺度间的秩相关。
#
# 需要强调：外推表的方差被幂律外推大幅压缩（标准差从 1M 的 0.38 降到 10B 的 0.10），三点拟合误差可能影响排序，但本分析没有独立识别其成因；因此外推表上的结论只能作为 **稳健性警示** 而非事实，这也是问题二需要把配比纳入标度律的直接动机。

# %%
# ============ 3.3 外推稳健性 ============
TRi = TR.set_index('index'); e10 = ESTS['10B 外推表 (A12/A13)'][0].set_index('index'); e70 = ESTS['70B 外推表 (A14/A15)'][0].set_index('index')
idx63 = e10.index
L1 = TRi.loc[idx63, LOSS_COLS].mean(axis=1).values; L10 = e10[LOSS_COLS].mean(axis=1).values; L70 = e70[LOSS_COLS].mean(axis=1).values
print('63 个配比的平均损失在不同尺度间的 Spearman 相关:')
print('  1M实测 vs 10B外推 = %.3f   1M实测 vs 70B外推 = %.3f   10B vs 70B = %.3f' % (stats.spearmanr(L1, L10)[0], stats.spearmanr(L1, L70)[0], stats.spearmanr(L10, L70)[0]))
print('  1M实测 与 (10B外推 - 1M实测) 的 Spearman = %.3f  -> 1M 损失越高的配比被外推压得越低' % stats.spearmanr(L1, L10 - L1)[0])
print('  损失标准差: 1M %.3f -> 10B %.3f -> 70B %.3f' % (L1.std(), L10.std(), L70.std()))

scale_rows = []
for tn, (df, P, Y, _, _) in list(TESTS.items()) + list(ESTS.items()):
    scale_rows.append({'数据集': tn, 'n': len(df), '性质': '实测' if '检验' in tn else '幂律外推',
                       '对数线性 Spearman': stats.spearmanr(pred_log(P), Y.mean(axis=1))[0], 'GBM Spearman': stats.spearmanr(pred_gbm(P), Y.mean(axis=1))[0], '样条 Spearman': stats.spearmanr(pred_spline(P), Y.mean(axis=1))[0]})
SCALE = pd.DataFrame(scale_rows); display(SCALE)
SCALE.to_csv(TAB/'mixture_extrapolation_comparison.csv',index=False,encoding='utf-8-sig')

per_dom = pd.Series({v: stats.spearmanr(TRi.loc[idx63, c], e10[c])[0] for v, c in zip(VAL13, LOSS_COLS)}).sort_values()
print('逐验证域 1M 实测 vs 10B 外推的 Spearman（中位数 %.2f）:' % per_dom.median()); print(per_dom.round(3).to_string())

AV = pd.DataFrame({'1M 训练(512)': A_LOG.values}, index=DOM17)
for tn, (df, P, Y, _, _) in list(TESTS.items()) + list(ESTS.items()):
    AV[tn.split(' ')[0]] = LinearRegression().fit(zlog(P), Y.mean(axis=1)).coef_
AV_rank = AV.rank()
print('\n各尺度上的对数特征系数 a_i 与 1M 训练集的 Spearman:'); print(AV.corr(method='spearman').iloc[0].round(3).to_string())
AV.to_csv(TAB / 'log_elasticity_by_scale.csv', encoding='utf-8-sig')

# ---- 图 15 ----
fig = plt.figure(figsize=(17, 6))
gs = gridspec.GridSpec(1, 3, width_ratios=[1, 1, 1.25], wspace=0.35)
ax = fig.add_subplot(gs[0]); xb = np.arange(len(SCALE)); wbar = 0.38
ax.bar(xb - wbar / 2, SCALE['对数线性 Spearman'], wbar, color=[C_NAVY if s == '实测' else C_CORAL for s in SCALE['性质']], label='对数线性主模型')
ax.bar(xb + wbar / 2, SCALE['GBM Spearman'], wbar, color=[C_NAVY if s == '实测' else C_CORAL for s in SCALE['性质']], alpha=0.45, hatch='//', label='GBM')
for i, (v1, v2) in enumerate(zip(SCALE['对数线性 Spearman'], SCALE['GBM Spearman'])):
    ax.text(i - wbar / 2, v1 + (0.02 if v1 >= 0 else -0.02), '%.2f' % v1, ha='center', va='bottom' if v1 >= 0 else 'top', fontsize=8.5)
    ax.text(i + wbar / 2, v2 + (0.02 if v2 >= 0 else -0.02), '%.2f' % v2, ha='center', va='bottom' if v2 >= 0 else 'top', fontsize=8.5)
ax.axhline(0, color='#333333', lw=1); ax.set_xticks(xb); ax.set_xticklabels([s.split(' ')[0] for s in SCALE['数据集']], fontsize=9)
ax.set_ylabel('Spearman(1M 代理模型预测, 损失)'); ax.set_title('(a) 1M 代理模型的排序能力随尺度的变化', fontsize=10.5)
ax.legend(handles=[Patch(color=C_NAVY, label='实测检验集'), Patch(color=C_CORAL, label='幂律外推表（非实测）'), Patch(facecolor='white', edgecolor='#555555', hatch='//', label='斜线 = GBM，实心 = 对数线性')], frameon=False, loc='lower left', fontsize=8.5)
ax = fig.add_subplot(gs[1])
ax.barh(per_dom.index, per_dom.values, color=[C_TEAL if v > 0.5 else (C_GOLD if v > 0 else C_CORAL) for v in per_dom.values], edgecolor='white')
ax.axvline(stats.spearmanr(L1, L10)[0], color=C_CORAL, ls='--', lw=1.5, label='13 域平均损失: %.2f' % stats.spearmanr(L1, L10)[0])
ax.axvline(0, color='#333333', lw=1); ax.set_xlabel('Spearman(1M 实测, 10B 外推)，63 个配比'); ax.tick_params(axis='y', labelsize=8.5); ax.legend(frameon=False, loc='lower right', fontsize=9)
ax.set_title('(b) 逐验证域的排序保持度：单域保持、平均反转', fontsize=10.5)
ax = fig.add_subplot(gs[2])
sns.heatmap(AV_rank.loc[AV_rank['1M 训练(512)'].sort_values().index], cmap=CMAP_SEQ, annot=True, fmt='.0f', ax=ax, cbar_kws={'shrink': 0.7, 'label': '对数特征系数 a_i 名次（1 = 系数最负）'}, linewidths=0.4, linecolor='white', annot_kws={'size': 8})
ax.grid(False)
ax.set_title('(c) 域对数特征系数名次在各尺度间的变化', fontsize=10.5); ax.set_xlabel(''); plt.setp(ax.get_xticklabels(), rotation=0, fontsize=9); plt.setp(ax.get_yticklabels(), fontsize=8.5)
savefig('fig15_extrapolation_robustness.png'); plt.show()

# %% [markdown]
# ### 3.4 是否以及如何引入质量评分 $Q$ 的论证
#
# **可识别性边界。** 在未平滑的可分对数有效数据量模型中，域固定质量项可吸收进截距，不能单独识别其效应。本文实际使用带 ε 的模型，因此该代数论证不能不加条件地直接套用；若把质量乘到 p 上且仍采用共同 ε，质量会改变曲线形状。更根本的限制是附件没有同一配比、不同质量的受控实验，且 17 域只有 6 域有直接或近似质量映射，不能据此估计质量的因果效应。配比质量指数是 p 的确定函数，其加入后即使改善预测，也只能作为当前参数化下的辅助特征证据。
#
# **质量映射。** 以七个质量域文档均分的等权均值 $\bar\mu=7^{-1}\sum_d\mu_d$为收缩中心，A16映射 $d(j)$给出配方域的质量代理
#
# $$
# Q_j^{mix}=\begin{cases}\kappa_j\mu_{d(j)}+(1-\kappa_j)\bar\mu,&d(j)\text{有质量样本},\\\bar\mu,&d(j)\text{无对应样本},\end{cases}\qquad
# \kappa_j=\begin{cases}1,&direct,\\0.8,&near\_direct,\\0.5,&inferred.\end{cases}
# $$
# $$
# Q_0(p)=\sum_{j=1}^{17}p_jQ_j^{mix},\qquad f_{aug}(p)=c+\sum_ja_j\ln(p_j+\varepsilon_p)+b_QQ_0(p).
# $$
#
# 无对应样本的11域取 $\bar\mu$，不宣称已获得其质量实测。$f_{aug}$是附加特征对照，主配比模型仍为 $f_{log}$；$Q_0$是 $p$的确定函数，预测改善不能单独识别质量因果效应。
#
# **KKT求解。** KKT条件＝约束最优点的一阶驻点、原始/对偶可行性及互补条件。当前拟合全部 $a_j<0$ 时，Hessian为正定对角阵 $\operatorname{diag}[-a_j/(p_j+\varepsilon_p)^2]$，目标严格凸。令等式约束乘子为 $\xi$、非负约束乘子为 $\mu_j$，避免与问题二质量系数 $\lambda$混淆：
#
# $$
# \mathcal L=f_{log}(p)+\xi(\sum_jp_j-1)-\sum_j\mu_jp_j,
# $$
# $$
# \frac{a_j}{p_j+\varepsilon_p}+\xi-\mu_j=0,\quad
# p_j\ge0,\ \mu_j\ge0,\ \mu_jp_j=0,\ \sum_jp_j=1.
# $$
#
# 因而
#
# $$
# p_j^*=\max\left(0,-\frac{a_j}{\xi}-\varepsilon_p\right),\qquad
# \sum_j\max\left(0,-\frac{a_j}{\xi}-\varepsilon_p\right)=1,\quad\xi>0.
# $$
#
# 求解最后的单调标量方程后，以SLSQP数值约束优化核验。若系数条件不成立，程序停止而不继续套用该凸解。候选只对当前拟合曲面最优，不是已实测训练最优。

# %%
# ============ 3.4 引入 Q 的论证 + 最优配比 ============
MAP = pd.read_csv(DATA / 'domain_mapping_guide.csv')
Qd = DOMAIN_Q[DOMAIN_Q['数据集'] == 'A1 抽样集'].set_index('域')['Q_res_doc均值'].to_dict()
Qd.update(DOMAIN_Q[DOMAIN_Q['数据集'] == '抽样+扩展 合并全量'].set_index('域')['Q_res_doc均值'].to_dict())   # arxiv/github 用全量
Q_BAR = float(np.mean(list(Qd.values())))
KAPPA = {'direct': 1.0, 'near_direct': 0.8, 'inferred': 0.5}
Qi = {}
for _, r in MAP.iterrows():
    qd = Qd.get(str(r['quality_domain']).strip()); k_ = KAPPA.get(r['mapping_type'], 0.5)
    Qi[r['mixture_domain']] = k_ * qd + (1 - k_) * Q_BAR if qd is not None else Q_BAR
Q17 = pd.Series([Qi.get(d, Q_BAR) for d in DOM17], index=DOM17)
QMAP = MAP.set_index('mixture_domain').assign(Q_quality_domain=[Qd.get(str(q).strip(), np.nan) for q in MAP['quality_domain']], kappa=[KAPPA.get(t, 0.5) for t in MAP['mapping_type']], Q_i=[Qi[m] for m in MAP['mixture_domain']])
print('7 个质量域的 Q_res（arxiv/github 为合并全量）:', {k: round(v, 4) for k, v in Qd.items()}, ' 均值 %.4f' % Q_BAR)
display(QMAP[['quality_domain', 'mapping_type', 'kappa', 'Q_quality_domain', 'Q_i']])

# (1) 域效应 vs 质量
mapped = [d for d in DOM17 if str(QMAP.loc[d, 'quality_domain']).strip() != '(none)']
a_m = A_LOG[mapped]; q_m = Q17[mapped]
print('\n(1) 有映射的 %d 个域：对数特征系数 a_i vs Q_i 的 Spearman = %.3f (p = %.2f), Pearson = %.3f' % (len(mapped), stats.spearmanr(a_m, q_m)[0], stats.spearmanr(a_m, q_m)[1], stats.pearsonr(a_m, q_m)[0]))
# 对照：域效应能否被"与验证集的分布匹配"解释 —— 同名域自迁移强度
self_tr = pd.Series({d: TRANS_C.loc[d, d] for d in DOM17 if d in VAL13})
print('    对照：a_i 与同名域自迁移强度 TRANS_C[i,i] 的 Spearman = %.3f（%d 个域）' % (stats.spearmanr(A_LOG[self_tr.index], self_tr)[0], len(self_tr)))

# (2) 配比级质量指数
Qbar_tr = P_tr @ Q17.values
lin_q = LinearRegression().fit(Qbar_tr.reshape(-1, 1), y_tr)
r2_rows = [{'数据集': '1M 训练集', 'n': len(y_tr), 'R2(仅Qbar)': lin_q.score(Qbar_tr.reshape(-1, 1), y_tr), 'Spearman(Qbar, 损失)': stats.spearmanr(Qbar_tr, y_tr)[0]}]
for tn, (df, P, Y, _, _) in TESTS.items():
    qb = P @ Q17.values; r2_rows.append({'数据集': tn, 'n': len(df), 'R2(仅Qbar)': lin_q.score(qb.reshape(-1, 1), Y.mean(axis=1)) if '1M' in tn else np.nan, 'Spearman(Qbar, 损失)': stats.spearmanr(qb, Y.mean(axis=1))[0]})
R2Q = pd.DataFrame(r2_rows); print('\n(2) 单变量模型 L = c0 + c1 * Qbar(p) 的解释力（c1 = %.3f；60M/1B 因损失水平不同只看 Spearman）:' % lin_q.coef_[0]); display(R2Q)

# (3) 增量信息：对数线性主模型 + Qbar 特征
aug_rows = []
m_aug = LinearRegression().fit(np.column_stack([Ztr, Qbar_tr]), y_tr)
for tn, (df, P, Y, _, _) in TESTS.items():
    base_rho = stats.spearmanr(pred_log(P), Y.mean(axis=1))[0]
    aug_rho = stats.spearmanr(m_aug.predict(np.column_stack([zlog(P), P @ Q17.values])), Y.mean(axis=1))[0]
    aug_rows.append({'检验集': tn, '对数线性(p) Spearman': base_rho, '对数线性(p)+Qbar Spearman': aug_rho, '提升': aug_rho - base_rho})
AUG = pd.DataFrame(aug_rows); print('\n(3) 把 Qbar(p) 加入对数线性主模型的增量信息（Qbar 系数 = %.3f）:' % m_aug.coef_[-1]); display(AUG)

# ---- 最优配比：KKT 解析解 + SLSQP 验证 + GBM 交叉评估 ----
a = A_LOG.values
assert np.all(a < 0), "当前KKT解析式需要全部系数为负；不满足时须另行求解"
def p_closed(lam):
    return np.maximum(0.0, -a / lam - EPS_LOG)
lo_l, hi_l = 1e-6, 1e3
for _ in range(200):
    mid = np.sqrt(lo_l * hi_l)
    if p_closed(mid).sum() > 1: lo_l = mid
    else: hi_l = mid
p_kkt = p_closed(np.sqrt(lo_l * hi_l)); p_kkt = p_kkt / p_kkt.sum()
obj = lambda p: model_l.predict(zlog(p.reshape(1, -1)))[0]
res = minimize(obj, p_kkt, method='SLSQP', bounds=[(0, 1)] * 17, constraints=[{'type': 'eq', 'fun': lambda p: p.sum() - 1}], options={'maxiter': 500, 'ftol': 1e-12})
assert res.success, res.message
p_num = np.clip(res.x, 0, 1); p_num = p_num / p_num.sum()
assert np.max(np.abs(p_kkt-p_num))<1e-5
print('\nKKT 解析解与 SLSQP 数值解的最大差异 = %.2e，目标值 %.4f / %.4f' % (np.abs(p_kkt - p_num).max(), obj(p_kkt), obj(p_num)))
p_star = p_kkt
# 单纯形候选，不把归一化后的坐标范围误称为训练支持范围。
lo_b,hi_b=P_tr.min(axis=0),P_tr.max(axis=0)
cand=np.vstack([RNG.dirichlet(np.ones(17)*.7,size=50000),P_tr,p_star.reshape(1,-1),p_mean.reshape(1,-1),uniform.reshape(1,-1)])
assert np.all(cand>=0) and np.allclose(cand.sum(axis=1),1)
Lc = pred_gbm(cand); p_gbm = cand[np.argmin(Lc)]
# 两模型平均名次折中候选：仅为启发式，不保证稳健性。
Ll = model_l.predict(zlog(cand)); rk = stats.rankdata(Ll) + stats.rankdata(Lc)
p_rob = cand[np.argmin(rk)]
p_selected=p_star.copy()  # 对数线性KKT主方案；GBM仅辅助核查
CANDS = [('对数线性最优 p*', p_star), ('GBM 候选最优', p_gbm), ('两模型折中候选 p_rob', p_rob), ('训练集最好配比', P_tr[np.argmin(y_tr)]), ('训练集平均配比', p_mean), ('均匀配比 1/17', uniform), ('主模型解析配比',p_selected)]
CMP = pd.DataFrame({'配比': [n for n, _ in CANDS], '对数线性预测损失': [obj(p) for _, p in CANDS],
                    'GBM 预测损失': [pred_gbm(p.reshape(1, -1))[0] for _, p in CANDS], '样条预测损失':[pred_spline(p.reshape(1,-1))[0] for _,p in CANDS], '主模型预测':[FITTED[SELECTED_MODEL].predict(p.reshape(1,-1))[0] for _,p in CANDS], '超训练坐标范围数':[int(((p<lo_b)|(p>hi_b)).sum()) for _,p in CANDS], 'Qbar(p)': [p @ Q17.values for _, p in CANDS]})
print('各配比在多个代理模型下的预测损失（训练集实测最小损失 %.3f）:' % y_tr.min()); display(CMP)
print('对数线性最优 p* 与 GBM 最优配比的 Spearman = %.3f；p_rob 与二者的 Spearman = %.3f / %.3f' % (stats.spearmanr(p_star, p_gbm)[0], stats.spearmanr(p_rob, p_star)[0], stats.spearmanr(p_rob, p_gbm)[0]))
OPT = pd.DataFrame({'最优配比 p* (对数线性)': p_star, 'GBM 搜索最优': p_gbm, '两模型折中候选 p_rob': p_rob, '训练集平均配比': p_mean, '均匀配比': uniform, '对数特征系数 a_i': a, 'Q_i': Q17.values, '主模型解析配比':p_selected}, index=DOM17).sort_values('最优配比 p* (对数线性)' , ascending=False)
display(OPT)

# ---- 图 16 ----
fig = plt.figure(figsize=(17, 5.8))
gs = gridspec.GridSpec(1, 3, width_ratios=[1, 1, 1.3], wspace=0.32)
ax = fig.add_subplot(gs[0])
for d in DOM17:
    is_m = d in mapped
    ax.scatter(Q17[d], A_LOG[d], s=70 if is_m else 35, color=C_NAVY if is_m else C_GREY, edgecolor='white', zorder=3)
    if is_m: ax.annotate(d, (Q17[d], A_LOG[d]), xytext=(5, 4), textcoords='offset points', fontsize=8.5, color=C_NAVY)
ax.text(0.98, 0.97, '灰点 = A16 无对应质量域的 11 个域\n(Q_i 取 7 个质量域均值)', transform=ax.transAxes, fontsize=8, color=C_GREY, ha='right', va='top')
a_, b_ = np.polyfit(q_m, a_m, 1); xs = np.linspace(q_m.min() - 0.01, q_m.max() + 0.01, 20); ax.plot(xs, a_ * xs + b_, color=C_CORAL, lw=1.6, ls='--')
ax.axhline(0, color='#333333', lw=0.8); ax.set_xlabel('配方域质量 Q_i（A16 映射 + 置信度收缩）'); ax.set_ylabel('对数特征系数 a_i（不等于净方向收益）')
ax.set_title('(a) 域效应 vs 质量：Spearman = %.2f（有映射的 %d 个域，深色）' % (stats.spearmanr(a_m, q_m)[0], len(mapped)), fontsize=10)
ax = fig.add_subplot(gs[1])
ax.scatter(Qbar_tr, y_tr, s=14, color=C_NAVY, alpha=0.55, edgecolor='none', label='1M 训练集 (512)')
P1m = TESTS['1M 检验集 (A6/A7)'][1]; Y1m = TESTS['1M 检验集 (A6/A7)'][2].mean(axis=1)
ax.scatter(P1m @ Q17.values, Y1m, s=14, color=C_CORAL, alpha=0.7, edgecolor='none', label='1M 检验集 (256)')
xs = np.linspace(Qbar_tr.min(), Qbar_tr.max(), 20); ax.plot(xs, lin_q.predict(xs.reshape(-1, 1)), color='#333333', lw=1.5, label='L = %.2f %+.2f Qbar' % (lin_q.intercept_, lin_q.coef_[0]))
ax.set_xlabel('配比级质量指数 Qbar(p) = sum p_i Q_i'); ax.set_ylabel('13 域平均损失'); ax.legend(frameon=False, fontsize=8.5)
ax.set_title('(b) 单一质量标量对配比效应的解释力：R2 = %.3f（训练）' % R2Q['R2(仅Qbar)'][0], fontsize=10)
ax = fig.add_subplot(gs[2])
y = np.arange(len(OPT)); wbar = 0.22
ax.barh(y + 1.5 * wbar, OPT['两模型折中候选 p_rob'], wbar, color=C_CORAL, label='两模型折中候选 p_rob（GBM 评估 %.3f）' % CMP['GBM 预测损失'][2])
ax.barh(y + 0.5 * wbar, OPT['最优配比 p* (对数线性)'], wbar, color=C_GOLD, label='对数线性 KKT 最优 p*（GBM 评估 %.3f）' % CMP['GBM 预测损失'][0])
ax.barh(y - 0.5 * wbar, OPT['GBM 搜索最优'], wbar, color=C_PLUM, label='GBM 候选最优（GBM 评估 %.3f）' % CMP['GBM 预测损失'][1])
ax.barh(y - 1.5 * wbar, OPT['训练集平均配比'], wbar, color=C_NAVY, alpha=0.7, label='训练集平均配比（GBM 评估 %.3f）' % CMP['GBM 预测损失'][4])
ax.set_yticks(y); ax.set_yticklabels(OPT.index, fontsize=8.5); ax.invert_yaxis(); ax.set_xlabel('配比份额'); ax.legend(frameon=False, fontsize=8.5, loc='upper center', bbox_to_anchor=(0.5, -0.09), ncol=2)
ax.set_title('(c) 三种候选配比与训练集平均配比（按主模型 p* 排序）', fontsize=10)
savefig('fig16_Q_and_optimal_mixture.png'); plt.show()

# ---- 保存给问题二 / 三的接口文件 ----
OPT.to_csv(TAB / 'optimal_mixture.csv', encoding='utf-8-sig')
Q17.rename('Q_i').to_csv(TAB / 'mixture_domain_Q.csv', encoding='utf-8-sig')
handoff = {'quality_model': 'normal scores + Pearson conflict + redundancy22 weighted exponential softmin', 'beta': BETA, 'Q_scale': 'real-valued normal score, may be negative', 'correlation_threshold': R_THRESHOLD, 'quality_domain_Q_res': {k: float(v) for k, v in Qd.items()}, 'Q_bar_global': Q_BAR, 'mixture_domain_Q': {d: float(Q17[d]) for d in DOM17},
           'kappa': KAPPA, 'weighting': 'inverse_squared_Pearson_redundancy22_no_grouping', 'weight_alpha': WEIGHT_ALPHA, 'length_correction': {'indicator': UNIQUE_COLUMN, 'bins': LENGTH_BINS, 'model_file': 'length_reference_20.npz'}, 'conflict_tail_quantiles': [Q_LO,Q_HI], 'format_calibration': {'indicators': FORMAT_RULES,'reference_file':'format_domain_reference.npz','reference_set':'A1 domain-specific'},'professionalism_mapping':'unchanged global A1 normal mapping', 'indicator_weights': {j: float(W.loc[j, '权重']) for j in INDICATORS},
           'log_linear_model': {'intercept': float(model_l.intercept_), 'epsilon': EPS_LOG, 'a_i': {d: float(A_LOG[d]) for d in DOM17}},
           'p_star_loglinear': {d: float(v) for d, v in zip(DOM17, p_star)}, 'p_star_gbm': {d: float(v) for d, v in zip(DOM17, p_gbm)},
           'p_star': {d: float(v) for d, v in zip(DOM17, p_selected)}, 'p_star_note': '对数线性主模型在非负且和为1约束下的KKT最优；SLSQP核验，GBM辅助评价；无真实训练验证', 'selected_predictive_model':MAIN_MODEL, 'main_model':MAIN_MODEL, 'cv_winner':CV_WINNER, 'selection_parameters':PARAMS, 'p_compromise':dict(zip(DOM17,map(float,p_rob))), 'L_hat_p_star_selected':float(FITTED[SELECTED_MODEL].predict(p_selected.reshape(1,-1))[0]),
           'L_hat_p_star_loglinear': float(obj(p_selected)), 'L_hat_p_star_gbm': float(pred_gbm(p_selected.reshape(1,-1))[0]),
           'Qbar_p_star': float(p_selected @ Q17.values), 'train_mixture_Qbar': [float(v) for v in Qbar_tr],
           # 各尺度配比实验的 13 域平均损失统计（供问题二检验“配比效应随尺度的变化”假设；不需要再读附件 A）
           'regmix_scale_stats': dict([('1M 训练集', {'N_params': 1e6, 'n': int(len(y_tr)), 'mean': float(y_tr.mean()), 'std': float(y_tr.std()), 'min': float(y_tr.min()), 'max': float(y_tr.max())})] +
                                      [(tn.split(' ')[0], {'N_params': {'1M': 1e6, '60M': 6e7, '1B': 1e9}[tn.split(' ')[0]], 'n': int(len(df)), 'mean': float(Y.mean(axis=1).mean()), 'std': float(Y.mean(axis=1).std()), 'min': float(Y.mean(axis=1).min()), 'max': float(Y.mean(axis=1).max())}) for tn, (df, P, Y, _, _) in TESTS.items()]),
           'mixture_loss_loglinear': {'p_rob': float(obj(p_rob)), 'p_selected':float(obj(p_selected)), 'p_star_loglinear': float(obj(p_star)), 'uniform': float(obj(uniform)), 'train_mean_mixture': float(obj(p_mean)), 'train_min_observed': float(y_tr.min()), 'train_max_observed': float(y_tr.max())},
           'train_mixture_loss_hat': [float(v) for v in model_l.predict(Ztr)], 'domain_order': DOM17}
with open(TAB / 'q1_outputs_for_q2_q3.json', 'w', encoding='utf-8') as f:
    json.dump(handoff, f, ensure_ascii=False, indent=2)
print('\n已保存问题二/三接口文件: output_q1/length_domain_calibrated22/tables/q1_outputs_for_q2_q3.json')
# 主方案在GBM下的交叉核查：只衡量模型一致性，不是实测收益。
g_main=float(pred_gbm(p_selected.reshape(1,-1))[0])
g_mean=float(pred_gbm(p_mean.reshape(1,-1))[0])
g_uniform=float(pred_gbm(uniform.reshape(1,-1))[0])
g_best=float(pred_gbm(p_gbm.reshape(1,-1))[0])
crosscheck={'main_model':MAIN_MODEL,'cv_winner':CV_WINNER,
 'GBM_loss_main':g_main,'GBM_loss_train_mean':g_mean,'GBM_loss_uniform':g_uniform,
 'GBM_loss_search_best':g_best,'GBM_main_minus_search_best':g_main-g_best,
 'main_better_than_train_mean_under_GBM':bool(g_main<g_mean),
 'main_better_than_uniform_under_GBM':bool(g_main<g_uniform),
 'real_training_validated':False}
(TAB/'main_mixture_crosscheck.json').write_text(json.dumps(crosscheck,ensure_ascii=False,indent=2), encoding='utf-8')
print('主方案的GBM辅助核查（预测而非实测）:');display(pd.Series(crosscheck))

# %% [markdown]
# ## 4. 模型检验与敏感性分析
#
# ### 4.1 权重敏感性与结果导出
#
# 逐项扰动权重，比较去冗余强度与等权基线，检查样本排序和领域均分的稳定性。统一导出当前 β=0.25 的评分、预处理参数和后续模型接口。
#
# 负 Q 是相对评分的正常取值；后续模型不能直接把 Q 当作概率或有效数据倍率。

# %%
# ============ 4.1 权重敏感性与结果导出 ============
sensitivity_rows = []
base_q = A1['Q_res'].to_numpy()
base_domain = pd.Series(base_q).groupby(A1['domain']).mean()
def record_sensitivity(name, weights):
    weights = np.array(weights, dtype=float, copy=True); weights /= weights.sum()
    q = softmin_quality(Z1_normal, BETA, weights)
    domain = pd.Series(q).groupby(A1['domain']).mean()
    sensitivity_rows.append({'方案': name, '样本Spearman': stats.spearmanr(base_q, q)[0], '域均值Spearman': stats.spearmanr(base_domain, domain)[0], '最大域均值变化': float((domain-base_domain).abs().max())})
for k,j in enumerate(INDICATORS):
    for factor in [.8,1.2]:
        weights=wG.copy();weights[k]*=factor
        record_sensitivity(SHORT[j]+'权重×'+str(factor),weights)
record_sensitivity('相关性去冗余权重（主方案）',wG.copy())
for alpha in [.5,1.5,2.0]:
    record_sensitivity('去冗余强度alpha='+str(alpha),redundancy_weights(alpha))
record_sensitivity('22指标等权（仅对照）',np.ones(22)/22)
WEIGHT_SENS = pd.DataFrame(sensitivity_rows)
WEIGHT_SENS.to_csv(TAB / 'weight_sensitivity.csv', index=False, encoding='utf-8-sig')
display(WEIGHT_SENS)
SENS.to_csv(TAB / 'beta_sensitivity.csv', index=False, encoding='utf-8-sig')
tau_sens.to_csv(TAB / 'conflict_threshold_sensitivity.csv', index=False, encoding='utf-8-sig')
R2Q.to_csv(TAB / 'quality_only_model.csv', index=False, encoding='utf-8-sig')
AUG.to_csv(TAB / 'quality_increment.csv', index=False, encoding='utf-8-sig')
print('结果目录:', OUT)

# 保存全部 22 指标的方向、归一化、正态映射及去冗余权重参数，供逐项核查。
for name,A,R,Z,X in [('A1',A1,R1,Z1_normal,X1),('A2',A2,R2,Z2_normal,X2),('A3',A3,R3,Z3_normal,X3)]:
    pd.concat([A[['id','sub_path','domain']], normalized_utility(R).add_prefix('U_'),Z.add_prefix('Z_')],axis=1).to_csv(TAB/('all_indicators_'+name+'.csv.gz'),index=False,compression='gzip')
DT_lin.to_csv(TAB/'linear_domain_Q.csv',index=False,encoding='utf-8-sig')
chk.to_csv(TAB/'conflict_score_adjustments.csv',encoding='utf-8-sig')
dom_conf.to_csv(TAB/'domain_conflict.csv',encoding='utf-8-sig')
len_conf.to_csv(TAB/'length_conflict.csv',encoding='utf-8-sig')
qc.to_csv(TAB/'content_checks.csv',encoding='utf-8-sig')
pd.DataFrame(cmp_rows).to_csv(TAB/'sample_extended_distributions.csv',index=False,encoding='utf-8-sig')
print('验证通过：权重和为1、Q有限、最小值≤Q≤线性均值、常数保持、平移等变、单调性。')

weight_alpha_table=pd.DataFrame({'指标':INDICATORS,**{'alpha='+str(a):redundancy_weights(a) for a in [.5,1,1.5,2]}})
weight_alpha_table.to_csv(TAB/'redundancy_alpha_weights.csv',index=False,encoding='utf-8-sig')
checks={'22指标独立赋权':len(W)==22,'权重非负':bool((wG>=0).all()),
        '权重和为1':bool(np.isclose(wG.sum(),1)),
        '不是直接等权':bool(not np.allclose(wG,1/22)),
        'A1原始样本数':len(A1),'A2原始样本数':len(A2),'A3原始样本数':len(A3)}
(TAB/'validation_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2), encoding='utf-8')
display(pd.Series(checks))

for name,A,R,Z,oldZ in [('A1',A1,R1,Z1_normal,Z1_uncorrected),('A2',A2,R2,Z2_normal,Z2_uncorrected),('A3',A3,R3,Z3_normal,Z3_uncorrected)]:
    pp,bb,miss,extra=length_percentile(R,LENGTH_MODEL)
    audit=A[['id','domain']].copy()
    audit['词数']=R[LENGTH_COLUMN].to_numpy();audit['原始独特词占比']=R[UNIQUE_COLUMN].to_numpy()
    audit['长度组']=bb+1;audit['校正后分位']=pp
    audit['原正态分数']=oldZ[UNIQUE_COLUMN].to_numpy();audit['校正后正态分数']=Z[UNIQUE_COLUMN].to_numpy()
    audit['长度缺失填补']=miss;audit['超出A1长度范围']=extra
    audit.to_csv(TAB/f'length_calibration_{name}.csv.gz',index=False,compression='gzip')

for name,A,R,Z,Zold in [('A1',A1,R1,Z1_normal,Z1_length),('A2',A2,R2,Z2_normal,Z2_length),('A3',A3,R3,Z3_normal,Z3_length)]:
    pp=format_percentiles(R,A.domain)
    audit=A[['id','domain']].copy()
    for j in FORMAT_RULES:
        audit[j+'__raw']=R[j].to_numpy()
        audit[j+'__normalized_utility']=normalized_utility(R)[j].to_numpy()
        audit[j+'__global_Z']=Zold[j].to_numpy()
        audit[j+'__domain_percentile']=pp[j].to_numpy()
        audit[j+'__domain_Z']=Z[j].to_numpy()
    audit.to_csv(TAB/f'format_calibration_{name}.csv.gz',index=False,compression='gzip')

# %% [markdown]
# ### 4.2 长度校正检验
#
# 固定其余处理，比较未校正及 10 / 20 / 30 组长度校正，检查长度残余关联、留出样本、分组边界与原文案例。本节单独检验长度组件，完整格式校准的对照见第 4.3 节。

# %%
# ============ 4.2 对照实验：所有方案重估相关、去冗余权重、Q和冲突 ============
lc_scenarios={'未校正':(Z1_uncorrected,Z2_uncorrected,Z3_uncorrected)}
for lc_k in [10,20,30]:
    lc_scenarios[f'{lc_k}组校正']=(Z1_length,Z2_length,Z3_length) if lc_k==20 else tuple(normal_scores(r,LENGTH_MODELS[lc_k]) for r in (R1,R2,R3))

def lc_evaluate_reference(z1,zs,tail,prepared):
    rho,weights,quality=prepared
    corr=rho.to_numpy();edges=[(j,k,corr[j,k]) for j in range(22) for k in range(j+1,22) if corr[j,k]<=-.3]
    lo,hi=np.quantile(z1,tail,axis=0),np.quantile(z1,1-tail,axis=0);denom=sum(-r for j,k,r in edges)
    outputs=[]
    for z,q in zip(zs,quality):
        v=z.to_numpy();ci=np.zeros(len(v))
        for j,k,r in edges:
            hit=((v[:,j]>hi[j])&(v[:,k]<lo[k]))|((v[:,k]>hi[k])&(v[:,j]<lo[j]))
            ci+=-r*hit*np.abs(v[:,j]-v[:,k])
        if denom:ci/=denom
        outputs.append({'Q':q,'CI':ci,'flag':ci>0})
    return outputs,weights,corr,edges

lc_metrics=[];lc_domains=[];lc_audit=[];lc_store={};lc_weight_rows=[]
lc_j=INDICATORS.index(UNIQUE_COLUMN)
for lc_name,lc_zs in lc_scenarios.items():
    lc_rho,_,lc_weights=fit_redundancy(lc_zs[0])
    lc_prepared=(lc_rho,lc_weights,[softmin_quality(z,BETA,lc_weights) for z in lc_zs])
    for lc_tail in [.25,.20]:
        lc_os,lc_ws,lc_corr,lc_edges=lc_evaluate_reference(lc_zs[0],lc_zs,lc_tail,lc_prepared)
        lc_store[(lc_name,lc_tail)]=(lc_os,lc_ws,lc_edges)
        if lc_tail==.20:
            lc_weight_rows.extend([{'方案':lc_name,'指标':j,'权重':float(w)} for j,w in zip(INDICATORS,lc_ws)])
        for lc_set,lc_A,lc_R,lc_Z,lc_o in zip(['A1','A2','A3'],[A1,A2,A3],[R1,R2,R3],lc_zs,lc_os):
            lc_wc=np.log1p(length_values(lc_R)[0]);lc_zu=lc_Z[UNIQUE_COLUMN].to_numpy()
            lc_metrics.append({'方案':lc_name,'高低界':f'{int(lc_tail*100)}/{int((1-lc_tail)*100)}','数据集':lc_set,'n':len(lc_A),
              '独特词与长度Spearman':stats.spearmanr(lc_zu,lc_wc)[0],
              '冲突指标对数':len(lc_edges),'涉及独特词的冲突对数':sum(lc_j in (j,k) for j,k,r in lc_edges),
              '冲突样本比例':lc_o['flag'].mean(),'Q均值':lc_o['Q'].mean(),
              'Q与未校正的Spearman':stats.spearmanr(lc_o['Q'],lc_store[('未校正',lc_tail)][0][['A1','A2','A3'].index(lc_set)]['Q'])[0]})
            for lc_d in sorted(lc_A.domain.unique()):
                lc_mask=lc_A.domain.eq(lc_d).to_numpy()
                lc_domains.append({'方案':lc_name,'高低界':f'{int(lc_tail*100)}/{int((1-lc_tail)*100)}','数据集':lc_set,'领域':lc_d,'n':int(lc_mask.sum()),
                  '冲突样本比例':float(lc_o['flag'][lc_mask].mean()),'Q均值':float(lc_o['Q'][lc_mask].mean()),
                  '独特词分位中位数':float(np.median(stats.norm.cdf(lc_zu[lc_mask]))),
                  '独特词与长度Spearman':float(stats.spearmanr(lc_zu[lc_mask],lc_wc[lc_mask])[0])})
# 本节为长度校正组件对照，与第 4.3 节完整方案分开。
for lc_z,lc_o in zip([Z1_length,Z2_length,Z3_length],lc_store[('20组校正',.20)][0]):
    assert np.allclose(softmin_quality(lc_z,BETA,lc_store[('20组校正',.20)][1]),lc_o['Q'])
lc_metrics=pd.DataFrame(lc_metrics);lc_domains=pd.DataFrame(lc_domains)
lc_metrics.to_csv(TAB/'length_correction_comparison.csv',index=False,encoding='utf-8-sig')
lc_domains.to_csv(TAB/'length_correction_domain_comparison.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(lc_weight_rows).to_csv(TAB/'length_correction_weights_comparison.csv',index=False,encoding='utf-8-sig')
display(lc_metrics[lc_metrics['数据集']=='A1'])
display(lc_domains[(lc_domains['数据集']=='A1')&(lc_domains['高低界']=='20/80')].pivot(index='领域',columns='方案',values='冲突样本比例'))

# 同一20/80下，保留原指标但固定未校正权重的桥接对照：区分映射变化与重估权重。
lc_base_w=lc_store[('未校正',.20)][1]
lc_bridge_q=softmin_quality(Z1_length,BETA,lc_base_w)
lc_bridge=pd.DataFrame({'方案':['未校正+未校正权重','20组校正+固定未校正权重','20组校正+重估权重'],
 'Q均值':[lc_store[('未校正',.20)][0][0]['Q'].mean(),lc_bridge_q.mean(),lc_store[('20组校正',.20)][0][0]['Q'].mean()],
 '与新Q排序相关':[stats.spearmanr(lc_store[('未校正',.20)][0][0]['Q'],lc_store[('20组校正',.20)][0][0]['Q'])[0],stats.spearmanr(lc_bridge_q,lc_store[('20组校正',.20)][0][0]['Q'])[0],1.0]})
lc_bridge.to_csv(TAB/'length_correction_weight_bridge.csv',index=False,encoding='utf-8-sig');display(lc_bridge)

# 分组迁移：只在 A1 的80%记录拟合条件分位参考，在其余20%上检验长度关联。
# 基础22指标构造仍来自全量A1，故这只是长度校正组件的留出检验，不是整模型独立验证。
from sklearn.model_selection import train_test_split
lc_fit_idx,lc_test_idx=train_test_split(np.arange(len(R1)),test_size=.2,random_state=2026,stratify=A1.domain)
lc_holdout=[]
for lc_k in [10,20,30]:
    lc_model=fit_length_reference(R1.iloc[lc_fit_idx],lc_k)
    lc_p,_,_,_=length_percentile(R1.iloc[lc_test_idx],lc_model)
    lc_holdout.append({'请求组数':lc_k,'实际组数':len(lc_model['refs']),'拟合记录数':len(lc_fit_idx),'留出记录数':len(lc_test_idx),
      '留出校正前长度Spearman':stats.spearmanr(Z1_uncorrected[UNIQUE_COLUMN].iloc[lc_test_idx],np.log1p(R1[LENGTH_COLUMN].iloc[lc_test_idx]))[0],
      '留出校正后长度Spearman':stats.spearmanr(lc_p,np.log1p(R1[LENGTH_COLUMN].iloc[lc_test_idx]))[0]})
pd.DataFrame(lc_holdout).to_csv(TAB/'length_component_holdout.csv',index=False,encoding='utf-8-sig');display(pd.DataFrame(lc_holdout))

# 压力测试：指标层面模拟全文机械重复2/4次，词数乘m，独特词占比除以m。
# 并非重新调用评分器或生成新人工标签；只检验校正函数对这类异常的敏感性。
lc_rng=np.random.default_rng(2026);_,lc_bb,_,_=length_percentile(R1,LENGTH_MODEL)
lc_pick=np.concatenate([lc_rng.choice(np.flatnonzero(lc_bb==k),size=min(150,int((lc_bb==k).sum())),replace=False) for k in range(len(LENGTH_MODEL['refs']))])
lc_stress=[]
for lc_k in [10,20,30]:
    lc_model=LENGTH_MODELS[lc_k];lc_origin=R1.iloc[lc_pick].copy()
    lc_p0,_,_,_=length_percentile(lc_origin,lc_model)
    for lc_m in [2,4]:
        lc_repeat=lc_origin.copy();lc_repeat[LENGTH_COLUMN]*=lc_m;lc_repeat[UNIQUE_COLUMN]/=lc_m
        lc_p1,_,_,lc_extra=length_percentile(lc_repeat,lc_model)
        lc_stress.append({'组数':lc_k,'重复倍数':lc_m,'n':len(lc_pick),'校正分位降低比例':float((lc_p1<lc_p0-1e-12).mean()),
          '校正分位不降比例':float((lc_p1>=lc_p0-1e-12).mean()),'中位分位下降':float(np.median(lc_p0-lc_p1)),
          '重复后低于20分位比例':float((lc_p1<.2).mean()),'超出A1长度范围比例':float(lc_extra.mean())})
lc_stress=pd.DataFrame(lc_stress);lc_stress.to_csv(TAB/'mechanical_repetition_stress.csv',index=False,encoding='utf-8-sig');display(lc_stress)

# 边界与样本覆盖：组内校正无法保证消除最宽末组中的剩余长度效应。
lc_pp,lc_bb,_,_=length_percentile(R1,LENGTH_MODEL)
lc_bindiag=LENGTH_MODEL['table'].copy()
lc_bindiag['组内校正后长度Spearman']=[stats.spearmanr(lc_pp[lc_bb==k],np.log1p(R1.loc[lc_bb==k,LENGTH_COLUMN]))[0] for k in range(len(LENGTH_MODEL['refs']))]
lc_bindiag.to_csv(TAB/'length_bin_residual_association.csv',index=False,encoding='utf-8-sig')
# 在边界左右给同一独特词占比做反事实检查，仅度量分箱不连续，不是新文本质量标签。
lc_boundary=[]
for lc_b,lc_edge in enumerate(LENGTH_MODEL['edges']):
    lc_wc_edge=float(np.expm1(lc_edge))
    lc_vals=np.quantile(R1[UNIQUE_COLUMN],[.1,.25,.5,.75,.9])
    for lc_v in lc_vals:
        lc_synth=pd.concat([R1.iloc[[0]]]*2,ignore_index=True)
        lc_synth[LENGTH_COLUMN]=[np.expm1(np.nextafter(lc_edge,-np.inf)),np.expm1(np.nextafter(lc_edge,np.inf))]
        lc_synth[UNIQUE_COLUMN]=lc_v
        lc_p,_,_,_=length_percentile(lc_synth,LENGTH_MODEL)
        lc_boundary.append({'边界':lc_b+1,'边界词数':lc_wc_edge,'固定独特词占比':lc_v,'左右分位差':lc_p[1]-lc_p[0]})
pd.DataFrame(lc_boundary).to_csv(TAB/'length_bin_boundary_jumps.csv',index=False,encoding='utf-8-sig')

# 原文候选：改变标签不自动等于纠正误报，保留全文供实质核验。
lc_old_flag=lc_store[('未校正',.20)][0][0]['flag'];lc_new_flag=lc_store[('20组校正',.20)][0][0]['flag']
lc_cases=[];lc_seen=set()
def lc_add_case(indices,reason,limit=1):
    count=0
    for idx in indices:
        if int(idx) not in lc_seen:
            lc_cases.append((int(idx),reason));lc_seen.add(int(idx));count+=1
            if count>=limit:break
for lc_dom in ['arxiv','book']:
    lc_mask=A1.domain.eq(lc_dom).to_numpy()&lc_old_flag&~lc_new_flag
    lc_idx=np.flatnonzero(lc_mask);lc_idx=lc_idx[np.argsort(-(lc_pp[lc_idx]-stats.norm.cdf(Z1_uncorrected[UNIQUE_COLUMN].to_numpy()[lc_idx])))]
    lc_add_case(lc_idx,f'{lc_dom} 校正后不再触发冲突',2)
    lc_idx=np.flatnonzero(A1.domain.eq(lc_dom).to_numpy()&lc_new_flag)
    lc_idx=lc_idx[np.argsort(lc_pp[lc_idx])]
    lc_add_case(lc_idx,f'{lc_dom} 校正后仍触发且独特词分位偏低')
lc_repeat_signal=R1['rps_doc_frac_chars_top_3gram'].to_numpy()
lc_idx=np.flatnonzero((lc_repeat_signal>=np.quantile(lc_repeat_signal,.99))&(lc_pp<.2))
lc_idx=lc_idx[np.argsort(-lc_repeat_signal[lc_idx])]
lc_add_case(lc_idx,'高3gram重复规则信号且校正分位仍低的候选',2)
lc_idmap={str(A1.iloc[idx].id):(idx,reason) for idx,reason in lc_cases};lc_found={}
for lc_path in RAW_A1:
    with open_any(lc_path) as lc_f:
        for lc_line in lc_f:
            try:lc_obj=json.loads(lc_line)
            except (ValueError,TypeError):continue
            lc_id=str(lc_obj.get('id',''))
            if lc_id in lc_idmap:
                lc_text=lc_obj.get('content') or lc_obj.get('text') or ''
                lc_found[lc_id]=lc_text
                if len(lc_found)==len(lc_idmap):break
    if len(lc_found)==len(lc_idmap):break
lc_text_dir=OUT/'text_review';lc_text_dir.mkdir(exist_ok=True)
lc_case_rows=[]
for lc_i,(lc_idx,lc_reason) in enumerate(lc_cases,1):
    lc_id=str(A1.iloc[lc_idx].id);lc_text=lc_found.get(lc_id,'');lc_lines=[x.strip() for x in lc_text.splitlines() if x.strip()]
    lc_file=lc_text_dir/f'case_{lc_i:02d}.txt';lc_file.write_text(lc_text,encoding='utf-8')
    lc_row={'案例':lc_i,'id':lc_id,'领域':A1.iloc[lc_idx].domain,'选择理由':lc_reason,'词数':float(R1.iloc[lc_idx][LENGTH_COLUMN]),
      '原始独特词占比':float(R1.iloc[lc_idx][UNIQUE_COLUMN]),'校正前分位':float(stats.norm.cdf(Z1_uncorrected.iloc[lc_idx][UNIQUE_COLUMN])),
      '校正后分位':float(lc_pp[lc_idx]),'校正前冲突':bool(lc_old_flag[lc_idx]),'校正后冲突':bool(lc_new_flag[lc_idx]),
      '全文字符数':len(lc_text),'重复非空行比例':1-len(set(lc_lines))/len(lc_lines) if lc_lines else np.nan,
      '原3gram重复指标':float(lc_repeat_signal[lc_idx]),'文本路径':str(lc_file.relative_to(OUT))}
    lc_case_rows.append(lc_row)
    print('\n案例',lc_i,lc_reason,'词数',lc_row['词数'],'分位',round(lc_row['校正前分位'],3),'→',round(lc_row['校正后分位'],3))
    print(lc_text[:500].replace('\n',' '))
pd.DataFrame(lc_case_rows).to_csv(TAB/'length_correction_text_cases.csv',index=False,encoding='utf-8-sig')
print('原文找到数/候选数:',len(lc_found),len(lc_cases),'；机器信号不等于人工重复标签。')

# 图17：长度关联与领域冲突的前后对照；所有图均使用新结果。
fig,axes=plt.subplots(1,3,figsize=(17,5.5))
lc_plot_idx=np.random.default_rng(1).choice(len(A1),5000,replace=False)
lc_logwc=np.log10(np.maximum(R1[LENGTH_COLUMN].to_numpy(),1))
axes[0].scatter(lc_logwc[lc_plot_idx],stats.norm.cdf(Z1_uncorrected[UNIQUE_COLUMN].to_numpy()[lc_plot_idx]),s=3,alpha=.25,label='未校正',color=C_CORAL)
axes[0].set_xlabel('log10(词数)');axes[0].set_ylabel('独特词分位');axes[0].set_title('(a) 未校正：分位受长度影响')
axes[1].scatter(lc_logwc[lc_plot_idx],lc_pp[lc_plot_idx],s=3,alpha=.25,color=C_TEAL)
for e in LENGTH_MODEL['edges']:axes[1].axvline(np.log10(np.expm1(e)),color='#999999',lw=.4,alpha=.4)
axes[1].set_xlabel('log10(词数)');axes[1].set_ylabel('长度条件分位');axes[1].set_title('(b) 20组校正（竖线为组界）')
lc_pivot=lc_domains[(lc_domains['数据集']=='A1')&(lc_domains['高低界']=='20/80')].pivot(index='领域',columns='方案',values='冲突样本比例')
(100*lc_pivot[['未校正','20组校正']]).plot.bar(ax=axes[2],color=[C_CORAL,C_TEAL])
axes[2].set_ylim(0,105);axes[2].set_ylabel('冲突信号比例 (%)');axes[2].set_xlabel('A1领域');axes[2].tick_params(axis='x',rotation=40)
axes[2].set_title('(c) 同一20/80规则下比较')
fig.tight_layout();savefig('fig17_length_correction.png');plt.show()
fig,axes=plt.subplots(1,2,figsize=(14,5.2))
(100*lc_pivot[['未校正','10组校正','20组校正','30组校正']]).plot.bar(ax=axes[0],color=[C_GREY,C_NAVY,C_TEAL,C_CORAL])
axes[0].set_ylabel('冲突信号比例 (%)');axes[0].set_ylim(0,105);axes[0].tick_params(axis='x',rotation=35);axes[0].set_title('(a) 分组数敏感性，同一20/80')
for k,c in zip([10,20,30],[C_NAVY,C_TEAL,C_CORAL]):
    ss=lc_stress[lc_stress['组数']==k]
    axes[1].plot(ss['重复倍数'],100*ss['校正分位降低比例'],marker='o',color=c,label=f'{k}组')
axes[1].set_xticks([2,4]);axes[1].set_xlabel('指标层模拟机械重复倍数');axes[1].set_ylabel('校正分位降低的样本比例 (%)');axes[1].set_title('(b) 压力测试（非人工有效性标签）');axes[1].legend()
fig.tight_layout();savefig('fig18_length_sensitivity.png');plt.show()
print('对照完成：先看长度关联，再看留出组件检验、分组敏感性、组界跳变和原文候选，不按最低冲突率选模型。')

# %% [markdown]
# ### 4.3 格式校准检验与局部冲突
#
# 固定独特词20组长度校正，比较不校准格式、仅校准标点、仅校准非字母词、两项同时校准；每组重新计算相关与去冗余权重。A1参考只拟合一次，A2/A3沿用，并单列排除A1重叠记录后的扩展样本。0.4用于敏感性，零冲突对不等于完美模型。

# %%
# ============ 4.3 格式规则的四组消融与0.3/0.4对照 ============
fr_base_zs=(Z1_length,Z2_length,Z3_length)
fr_schemes={'仅长度校正':[], '长度+标点校准':[FORMAT_RULES[0]],'长度+非字母校准':[FORMAT_RULES[1]],'长度+两规则校准':FORMAT_RULES}
fr_variants={name:tuple(calibrated_scores(r,a.domain,z,js) for r,a,z in zip([R1,R2,R3],[A1,A2,A3],fr_base_zs)) for name,js in fr_schemes.items()}

def fr_evaluate(zs,prepared,cutoff=.3,tail=.2):
    rho,ww,quality=prepared
    edges=[(j,k,rho.iloc[j,k]) for j in range(22) for k in range(j+1,22) if rho.iloc[j,k]<=-cutoff]
    lo,hi=zs[0].quantile(tail).to_numpy(),zs[0].quantile(1-tail).to_numpy()
    denom=sum(-v for j,k,v in edges);outs=[]
    for z,q in zip(zs,quality):
        zz=z.to_numpy();ci=np.zeros(len(z))
        for j,k,r in edges:
            hit=((zz[:,j]>hi[j])&(zz[:,k]<lo[k]))|((zz[:,k]>hi[k])&(zz[:,j]<lo[j]))
            ci+=-r*hit*np.abs(zz[:,j]-zz[:,k])
        if denom:ci/=denom
        outs.append({'ci':ci,'flag':ci>0,'q':q})
    return outs,ww,rho,edges

fr_subsets=[('A1','A1全体',0,np.ones(len(A1),bool))]
for d in sorted(A1.domain.unique()):fr_subsets.append(('A1','A1 '+d,0,A1.domain.eq(d).to_numpy()))
fr_A1keys=pd.MultiIndex.from_frame(A1[['domain','id']])
for name,idx,a in [('A2',1,A2),('A3',2,A3)]:
    fr_subsets.append((name,name+' 全量',idx,np.ones(len(a),bool)))
    fr_subsets.append((name,name+' 新增去重',idx,~pd.MultiIndex.from_frame(a[['domain','id']]).isin(fr_A1keys)))
fr_rows=[];fr_cache={};fr_corrows=[];fr_prof='modernbert_professionalism'
for fr_name,zs in fr_variants.items():
    fr_rho,_,fr_weights=fit_redundancy(zs[0])
    fr_prepared=(fr_rho,fr_weights,[softmin_quality(z,BETA,fr_weights) for z in zs])
    for cutoff in [.3,.4]:
        outs,ww,rho,edges=fr_evaluate(zs,fr_prepared,cutoff);fr_cache[(fr_name,cutoff)]=(outs,ww,rho,edges)
        for setname,label,idx,mask in fr_subsets:
            before=fr_cache[('仅长度校正',cutoff)][0][idx];new=outs[idx]
            fr_rows.append({'方案':fr_name,'相关阈值':cutoff,'集合':label,'n':int(mask.sum()),'冲突指标对数':len(edges),
              '专业性相关冲突对数':sum(fr_prof in (INDICATORS[j],INDICATORS[k]) for j,k,r in edges),
              '冲突样本比例':float(new['flag'][mask].mean()),'Q均值':float(new['q'][mask].mean()),
              'Q排序相关_对长度版':float(stats.spearmanr(new['q'][mask],before['q'][mask])[0]),
              '取消标记数':int((before['flag'][mask]&~new['flag'][mask]).sum()),'新增标记数':int((~before['flag'][mask]&new['flag'][mask]).sum())})
        if cutoff==.3:
            for j in [UNIQUE_COLUMN]+FORMAT_RULES:
                fr_corrows.append({'方案':fr_name,'专业性对比指标':j,'全局Pearson':rho.loc[fr_prof,j]})
fr_results=pd.DataFrame(fr_rows);fr_results.to_csv(TAB/'format_ablation_and_thresholds.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(fr_corrows).to_csv(TAB/'format_professionalism_correlations.csv',index=False,encoding='utf-8-sig')
display(fr_results[fr_results['集合']=='A1全体']);display(pd.DataFrame(fr_corrows))
for A,out in zip([A1,A2,A3],fr_cache[('长度+两规则校准',.3)][0]):
    assert np.allclose(A.Q_res,out['q']) and np.allclose(A.CI,out['ci']) and np.array_equal(A.is_conflict,out['flag'])
fr_a1domain=fr_results[(fr_results['相关阈值']==.3)&fr_results['集合'].str.startswith('A1 ')]
display(fr_a1domain.pivot(index='集合',columns='方案',values='冲突样本比例'))
for name,A,idx in [('A1',A1,0),('A2',A2,1),('A3',A3,2)]:
    compare=A[['id','domain']].copy()
    for scheme in fr_schemes:
        result=fr_cache[(scheme,.3)][0][idx]
        compare[scheme+'__Q']=result['q'];compare[scheme+'__flag']=result['flag'];compare[scheme+'__CI']=result['ci']
    compare.to_csv(TAB/f'format_ablation_samples_{name}.csv.gz',index=False,compression='gzip')
fig,axes=plt.subplots(1,2,figsize=(15,5.8))
cp=pd.DataFrame(fr_corrows).pivot(index='专业性对比指标',columns='方案',values='全局Pearson')
cp.index=[SHORT[j] for j in cp.index]
cp[['仅长度校正','长度+两规则校准']].plot.barh(ax=axes[0],color=[C_CORAL,C_TEAL]);axes[0].axvline(-.3,color=C_NAVY,ls='--')
axes[0].set_xlabel('Pearson r');axes[0].set_title('(a) 专业性不变，仅调整比较参照')
vp=fr_a1domain.pivot(index='集合',columns='方案',values='冲突样本比例')
(100*vp[['仅长度校正','长度+两规则校准']]).plot.bar(ax=axes[1],color=[C_CORAL,C_TEAL]);axes[1].set_ylabel('冲突信号比例 (%)')
axes[1].set_ylim(0,105);axes[1].tick_params(axis='x',rotation=35);axes[1].set_title('(b) A1各领域，相同0.3与20/80')
fig.tight_layout();savefig('fig19_format_calibration.png');plt.show()

# 格式校准的全局与局部关系核查
# 主模型仍逐对扫描22项，没有对专业性或格式规则加排除名单。
fr_expected={(INDICATORS[j],INDICATORS[k]) for j in range(22) for k in range(j+1,22) if RHO.iloc[j,k]<=-R_THRESHOLD}
fr_actual=set(zip(PAIRS.loc[PAIRS['阈值冲突'],'j'],PAIRS.loc[PAIRS['阈值冲突'],'k']))
assert fr_expected==fr_actual
for zold,znew in zip(fr_base_zs,[Z1_normal,Z2_normal,Z3_normal]):
    for j in INDICATORS:
        if j not in FORMAT_RULES:assert np.array_equal(zold[j].to_numpy(),znew[j].to_numpy())

# 全局协方差分解：总体协方差=领域内加权协方差+领域均值之间的协方差。
fr_audit_rows=[]
for j in FORMAT_RULES:
    for stage,z in [('校准前',Z1_length),('校准后',Z1_normal)]:
        x=z[fr_prof].to_numpy();y=z[j].to_numpy();mx=x.mean();my=y.mean()
        within=0.;between=0.
        for d in sorted(A1.domain.unique()):
            mask=A1.domain.eq(d).to_numpy();part=mask.mean()
            xd,yd=x[mask],y[mask];within+=part*np.mean((xd-xd.mean())*(yd-yd.mean()))
            between+=part*(xd.mean()-mx)*(yd.mean()-my)
        total=np.mean((x-mx)*(y-my));assert np.isclose(total,within+between)
        fr_audit_rows.append({'指标':j,'阶段':stage,'总协方差':total,'域内协方差项':within,'域间均值协方差项':between,
          '全局Pearson':stats.pearsonr(x,y)[0]})
fr_cov=pd.DataFrame(fr_audit_rows);fr_cov.to_csv(TAB/'audit_covariance_decomposition.csv',index=False,encoding='utf-8-sig');display(fr_cov)

# 强制保留局部反证：每个领域内部重新计算r，使用该领域自身20/80，不能以全局r不足阈值就不展示。
fr_within_rows=[]
for j in FORMAT_RULES:
    for d in sorted(A1.domain.unique()):
        mask=A1.domain.eq(d).to_numpy()
        for stage,z in [('校准前',Z1_length),('校准后',Z1_normal)]:
            sub=z.loc[mask];x,y=sub[fr_prof],sub[j]
            r=stats.pearsonr(x,y)[0] if x.std()>1e-12 and y.std()>1e-12 else np.nan
            xl,xh=x.quantile(.2),x.quantile(.8);yl,yh=y.quantile(.2),y.quantile(.8)
            opposite=((x>xh)&(y<yl))|((x<xl)&(y>yh))
            fr_within_rows.append({'领域':d,'指标':j,'阶段':stage,'n':len(sub),'域内Pearson':r,
              '域内Spearman':stats.spearmanr(x,y)[0],'域内r<=负0.3':bool(r<=-.3),
              '域内高低交叉率':float(opposite.mean()),'局部规则冲突率':float(opposite.mean()) if r<=-.3 else 0.0})
fr_within=pd.DataFrame(fr_within_rows);fr_within.to_csv(TAB/'audit_within_domain_pairs.csv',index=False,encoding='utf-8-sig')
print('全局不再满足阈值，并不代表下表中的局部冲突消失:')
display(fr_within[fr_within['阶段']=='校准后'])
# A2/A3沿用A1对应域内的候选对和高低界，单独展示这些局部关系的扩展重现。
fr_local_ext=[]
for d,ae,ze in [('arxiv',A2,Z2_normal),('github',A3,Z3_normal)]:
    sub=Z1_normal.loc[A1.domain.eq(d)]
    for j in FORMAT_RULES:
        xr,yr=sub[fr_prof],sub[j];r=xr.corr(yr)
        xl,xh=xr.quantile(.2),xr.quantile(.8);yl,yh=yr.quantile(.2),yr.quantile(.8)
        xe,ye=ze[fr_prof],ze[j]
        crosses=((xe>xh)&(ye<yl))|((xe<xl)&(ye>yh))
        fr_local_ext.append({'领域':d,'指标':j,'A1域内r':r,'扩展域内r':xe.corr(ye),'A1是否局部候选':bool(r<=-.3),
          '扩展固定A1域内界交叉率':float(crosses.mean()),'扩展局部冲突信号率':float(crosses.mean()) if r<=-.3 else 0.0})
pd.DataFrame(fr_local_ext).to_csv(TAB/'audit_local_extension.csv',index=False,encoding='utf-8-sig');display(pd.DataFrame(fr_local_ext))

# 指标层反事实：在同一领域，减少句末标点或提高非字母词；固定其他指标及最终权重，不重新拟合。
fr_rng=np.random.default_rng(7);fr_idx=np.concatenate([fr_rng.choice(np.flatnonzero(A1.domain.eq(d)),size=min(300,int(A1.domain.eq(d).sum())),replace=False) for d in sorted(A1.domain.unique())])
fr_stress=[]
for js,label in [([FORMAT_RULES[0]],'仅恶化标点'),([FORMAT_RULES[1]],'仅恶化非字母词'),(FORMAT_RULES,'两项同时恶化')]:
    baseR=R1.iloc[fr_idx].copy();damaged=baseR.copy();dom=A1.domain.iloc[fr_idx]
    for j in js:
        if j in IND_NEG:damaged[j]=baseR[j]+.5*(float(R1[j].max())-baseR[j])
        else:damaged[j]=baseR[j]-.5*(baseR[j]-float(R1[j].min()))
    zz=calibrated_scores(damaged,dom);q0=A1.Q_res.to_numpy()[fr_idx];q1=softmin_quality(zz)
    assert np.all(q1<=q0+1e-10)
    for j in js:assert np.all(zz[j].to_numpy()<=Z1_normal[j].to_numpy()[fr_idx]+1e-10)
    fr_stress.append({'情景':label,'n':len(fr_idx),'Q不增加比例':float((q1<=q0+1e-10).mean()),
      'Q严格下降比例':float((q1<q0-1e-10).mean()),'Q平均下降':float((q0-q1).mean())})
fr_stress=pd.DataFrame(fr_stress);fr_stress.to_csv(TAB/'audit_format_degradation_stress.csv',index=False,encoding='utf-8-sig');display(fr_stress)

# 预先选定的格式冲突原文：保留真实ID，不使用新结果挑选“成功”案例。
fr_case_ids=['BkiUbIA5qWTD6fM1V7xu','BkiUd-k5qX_Bw5o9Imfb','BkiUdtA5qsFAfn88t1jO','BkiUetY5qhLBeMNHlnbx','BkiUct425V5ha7jY8d0t','BkiUdt85qsBDAu0h_wHS']
fr_found={}
for path in RAW_A1:
    with open_any(path) as f:
        for line in f:
            try:obj=json.loads(line)
            except (ValueError,TypeError):continue
            id_=str(obj.get('id',''))
            if id_ in fr_case_ids:fr_found[id_]=obj.get('content') or obj.get('text') or ''
            if len(fr_found)==len(fr_case_ids):break
    if len(fr_found)==len(fr_case_ids):break
fr_case_dir=OUT/'format_text_review';fr_case_dir.mkdir(exist_ok=True)
fr_case_rows=[]
for number,id_ in enumerate(fr_case_ids,1):
    idx=np.flatnonzero(A1.id.astype(str).eq(id_).to_numpy())[0]
    text=fr_found.get(id_,'');filename=fr_case_dir/f'case_{number:02d}.txt';filename.write_text(text,encoding='utf-8')
    before=fr_cache[('仅长度校正',.3)][0][0];after=fr_cache[('长度+两规则校准',.3)][0][0]
    row={'案例':number,'id':id_,'领域':A1.iloc[idx].domain,'校准前标记':bool(before['flag'][idx]),'校准后标记':bool(after['flag'][idx]),
      'Q前':float(before['q'][idx]),'Q后':float(after['q'][idx]),'专业性Z':float(Z1_normal.iloc[idx][fr_prof]),'全文字符数':len(text),'文本路径':str(filename.relative_to(OUT))}
    for j in FORMAT_RULES:
        row[j+'__原始值']=float(R1.iloc[idx][j]);row[j+'__原Z']=float(Z1_length.iloc[idx][j]);row[j+'__域内Z']=float(Z1_normal.iloc[idx][j])
    fr_case_rows.append(row)
    print('\n预选原文案例',number,A1.iloc[idx].domain,'标记',row['校准前标记'],'→',row['校准后标记']);print(text[:320].replace('\n',' '))
pd.DataFrame(fr_case_rows).to_csv(TAB/'audit_format_text_cases.csv',index=False,encoding='utf-8-sig')
fr_checks={'未使用冲突排除名单':fr_expected==fr_actual,'专业性及另外19项相对长度版完全不变':True,
 '参考分布只用A1':True,'阈值固定0.3而非为清零而调整':R_THRESHOLD==.3,
 '反事实格式恶化Q未增加':bool((fr_stress['Q不增加比例']==1).all()),
 '已保留局部反向关系而非宣称无冲突':True,
 '存在校准后的域内候选冲突':bool(fr_within.loc[fr_within['阶段']=='校准后','域内r<=负0.3'].any()),
 '有独立人工标签足以证明误判改善':False}
(TAB/'audit_checks.json').write_text(json.dumps(fr_checks,ensure_ascii=False,indent=2), encoding='utf-8');display(pd.Series(fr_checks))
fig,axes=plt.subplots(1,2,figsize=(15,5.5))
wp=fr_within[fr_within['阶段']=='校准后'].pivot(index='领域',columns='指标',values='域内Pearson')
wp.columns=[SHORT[j] for j in wp.columns];wp.plot.bar(ax=axes[0],color=[C_NAVY,C_TEAL]);axes[0].axhline(-.3,color=C_CORAL,ls='--')
axes[0].tick_params(axis='x',rotation=35);axes[0].set_ylabel('校准后领域内Pearson');axes[0].set_title('(a) 全局关系减弱后，局部反向关系仍需保留')
axes[1].bar(fr_stress['情景'],fr_stress['Q平均下降'],color=[C_NAVY,C_TEAL,C_CORAL]);axes[1].set_ylabel('固定权重下Q平均下降');axes[1].set_title('(b) 格式规则恶化仍受到评分惩罚（指标层测试）')
fig.tight_layout();savefig('fig20_conflict_audit.png');plt.show()
print('审查结论：算法没有硬性屏蔽冲突；领域校准改变了参照尺度，因此不能把全局负相关减弱解释为原冲突已被证明消除。局部冲突、原始值和人工核验需求均保留。')

# %% [markdown]
# ### 4.4 聚合参数 β 的敏感性
#
# 本节固定 A1 参照、长度与格式校准、22 项权重，仅比较 β=0、0.1、0.25、0.5、0.75、1。β=0 单独按线性加权平均计算，表示 β 趋于零的极限，不能直接代入带 1/β 的公式。A1 七个领域按文档均分比较；A2、A3 各自全量评分并单列，避免混淆抽样与扩展口径。当前主模型已采用 β=0.25；β=1 为较强惩罚对照。本节不覆盖主模型评分或问题二/三接口。

# %%
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import logsumexp

# 固定既有A1参照、22项指标和权重；仅改变指数凹聚合的beta。
# 本节不覆盖主模型BETA=0.25及评分/接口文件。
bt_root=Path('output_q1/length_domain_calibrated22/tables')
bt_main_beta=float(__import__('json').loads((bt_root/'q1_outputs_for_q2_q3.json').read_text(encoding='utf-8'))['beta'])
bt_w=pd.read_csv(bt_root/'indicator_weights.csv',index_col=0)['权重']
bt_values=[0.0,0.1,0.25,0.5,0.75,1.0]
bt_rows=[]
for bt_set in ['A1','A2','A3']:
    bt_df=pd.read_csv(bt_root/f'all_indicators_{bt_set}.csv.gz')
    bt_z=bt_df[['Z_'+j for j in bt_w.index]].to_numpy()
    bt_lin=bt_z@bt_w.to_numpy()
    bt_prev=None
    for bt_beta in bt_values:
        bt_q=bt_lin.copy() if bt_beta==0 else -logsumexp(-bt_beta*bt_z+np.log(bt_w.to_numpy()),axis=1)/bt_beta
        assert np.isfinite(bt_q).all()
        assert np.all(bt_q<=bt_lin+1e-12)
        if bt_prev is not None: assert np.all(bt_q<=bt_prev+1e-12)
        bt_prev=bt_q
        if np.isclose(bt_beta,bt_main_beta):
            bt_saved=pd.read_csv(bt_root/f'sample_Q_{bt_set}.csv')
            assert np.array_equal(bt_df['id'].to_numpy(),bt_saved['id'].to_numpy())
            assert np.allclose(bt_q,bt_saved['Q_res'],atol=1e-12)
        bt_frame=bt_df[['domain']].assign(Q=bt_q,drop=bt_lin-bt_q)
        for bt_dom,bt_group in bt_frame.groupby('domain'):
            bt_rows.append({'集合':bt_set,'领域':bt_dom,'样本数':len(bt_group),'beta':bt_beta,'文档均分':bt_group.Q.mean(),'相对线性均分下调':bt_group['drop'].mean()})
bt_result=pd.DataFrame(bt_rows)
bt_result['集合内领域排名']=bt_result.groupby(['集合','beta'])['文档均分'].rank(ascending=False,method='min').astype(int)
bt_result.to_csv(bt_root/'beta_small_trial_domain_scores.csv',index=False,encoding='utf-8-sig')
bt_a1=bt_result[bt_result['集合']=='A1']
bt_table=bt_a1.pivot(index='beta',columns='领域',values='文档均分')
bt_table['github_A3']=bt_result[(bt_result['集合']=='A3')&(bt_result['领域']=='github')].set_index('beta')['文档均分']
bt_table['book_A1排名']=bt_a1[bt_a1['领域']=='book'].set_index('beta')['集合内领域排名']
print('固定预处理和权重，只改变beta；全部为文档均分。beta=0表示线性聚合极限。')
print(bt_table.round(4).to_string())
print('\nbook相对线性均分的下调：')
print(bt_a1[bt_a1['领域']=='book'][['beta','文档均分','相对线性均分下调','集合内领域排名']].round(4).to_string(index=False))
print('\n验证通过：当前主模型beta=0.25复现A1/A2/A3保存评分；beta越小，每条样本的评分不下降。冲突指标CI与beta无关。')

# %% [markdown]
# #### β 敏感性的解释
#
# β越小，短板惩罚越弱，逐样本评分不下降；具体领域均分与排名见上表。β=0.25固定为主参数，不以预期领域排名倒推参数。β不参与冲突判定。排序变化不能证明评分更准确，仍需独立人工标签。

# %% [markdown]
# ### 4.5 独立复算与完整性核查
#
# 本节从导出结果独立复算，不依赖主模型内存变量。局部冲突仅审查两项格式规则与专业性，保留逐样本反证，不替换主模型的CI和Q。

# %%
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.special import logsumexp
from scipy.stats import norm
BASE=Path.cwd()
OUT=BASE/'output_q1/length_domain_calibrated22'
T=OUT/'tables'
rules=['rps_lines_ending_with_terminal_punctution_mark','rps_doc_frac_no_alph_words']
prof='modernbert_professionalism'
audit_beta=float(json.loads((T/'q1_outputs_for_q2_q3.json').read_text(encoding='utf-8'))['beta'])
wtab=pd.read_csv(T/'indicator_weights.csv',index_col=0)
cols=wtab.index.tolist();w=wtab['权重'].to_numpy()
assert len(cols)==22 and np.isclose(w.sum(),1) and np.all(w>=0)
frames={s:pd.read_csv(T/f'all_indicators_{s}.csv.gz') for s in ['A1','A2','A3']}
zs={s:f[['Z_'+j for j in cols]].set_axis(cols,axis=1) for s,f in frames.items()}
rho=zs['A1'].corr()
valid=zs['A1'].std(ddof=0)>1e-12
expected=pd.Series(0.,index=cols)
expected.loc[valid]=1/rho.loc[valid,valid].pow(2).sum(axis=1)
expected/=expected.sum()
assert np.allclose(w,expected,atol=1e-12)
lo=zs['A1'].quantile(.2);hi=zs['A1'].quantile(.8)
edges=[(j,k,rho.loc[j,k]) for i,j in enumerate(cols) for k in cols[i+1:] if rho.loc[j,k]<=-.3]
refs=np.load(T/'format_domain_reference.npz')
for d in frames['A1'].domain.unique():
 for j in rules:
  assert np.allclose(refs[d+'__'+j],np.sort(frames['A1'].loc[frames['A1'].domain.eq(d),'U_'+j]))
local_edges=[]
for d in sorted(frames['A1'].domain.unique()):
 sub=zs['A1'].loc[frames['A1'].domain.eq(d)]
 for j in rules:
  r=sub[prof].corr(sub[j]) if sub[prof].std()>1e-12 and sub[j].std()>1e-12 else np.nan
  if r<=-.3:local_edges.append((d,j,r,sub[[prof,j]].quantile(.2),sub[[prof,j]].quantile(.8)))
summary=[]
for s,f in frames.items():
 z=zs[s];score=pd.read_csv(T/f'sample_Q_{s}.csv')
 assert f.id.equals(score.id) and f.domain.equals(score.domain)
 q=-logsumexp(-audit_beta*z.to_numpy()+np.log(w),axis=1)/audit_beta
 assert np.allclose(q,score.Q_res,atol=1e-12)
 ca=pd.read_csv(T/f'format_calibration_{s}.csv.gz')
 for j in rules:assert np.allclose(norm.ppf(ca[j+'__domain_percentile']),z[j],atol=1e-10)
 ci=np.zeros(len(f));denom=sum(-r for j,k,r in edges)
 for j,k,r in edges:
  flag=((z[j]>hi[j])&(z[k]<lo[k]))|((z[k]>hi[k])&(z[j]<lo[j]))
  ci+=-r*flag*np.abs(z[j]-z[k])
 if denom:ci/=denom
 assert np.allclose(ci,score.CI,atol=1e-12) and np.array_equal(ci>0,score.is_conflict)
 local=np.zeros(len(f),bool);records=f[['id','domain']].copy()
 for d,j,r,ll,hh in local_edges:
  flag=f.domain.eq(d)&(((z[prof]>hh[prof])&(z[j]<ll[j]))|((z[prof]<ll[prof])&(z[j]>hh[j])))
  records[d+'__'+j+'__局部信号']=flag
  local|=flag.to_numpy()
 records['全局冲突信号']=score.is_conflict
 records['两项格式规则的局部冲突信号']=local
 records['全局或上述局部信号']=score.is_conflict.to_numpy()|local
 records.to_csv(T/f'audit_global_local_flags_{s}.csv.gz',index=False,compression='gzip')
 summary.append({'集合':s,'n':len(f),'全局冲突率':score.is_conflict.mean(),'两规则局部冲突率':local.mean(),'全局或两规则局部信号率':records['全局或上述局部信号'].mean()})
summary=pd.DataFrame(summary)
summary.to_csv(T/'audit_global_local_summary.csv',index=False,encoding='utf-8-sig')
assert len(pd.read_csv(T/'format_ablation_and_thresholds.csv'))==96
assert len(pd.read_csv(T/'audit_within_domain_pairs.csv'))==28
assert len(pd.read_csv(T/'audit_format_text_cases.csv'))==6
assert (pd.read_csv(T/'audit_format_text_cases.csv')['全文字符数']>0).all()
print('独立复算通过：22项去冗余权重、所有集合的Q及CI、固定A1参照。')
print('局部信号单独输出，不修改主模型Q或把局部信号混称为原全局冲突率。')
print(summary.to_string(index=False))
print('注意：上述局部审查仅覆盖本次两项格式规则与专业性，不是全部231对的局部扫描；未经过独立人工标签验证。')
(T/'independent_verification.json').write_text(json.dumps({'22项权重及三个集合Q_CI复算通过':True,'局部信号逐样本导出':True},ensure_ascii=False,indent=2), encoding='utf-8');

# %% [markdown]
# ## 5. 结果与适用边界
#
# 以下摘要从本次输出自动生成。质量评分是相对于A1的模型分数；领域校准改变比较参照，冲突率下降不等于误判减少。局部核查仅覆盖两项格式规则与专业性，原文案例不替代独立盲评。
#
# 配比选择综合考虑可解释性与优化便利性；检验集排序能力不等于跨尺度绝对损失校准。推荐配比、质量增量与后续资源配置均需真实训练验证。
#
# 主要输出：`tables/sample_Q_A1.csv`（A2/A3同名规则）、`domain_Q.csv`、`quality_increment.csv`、`q1_outputs_for_q2_q3.json`；完整参数与数值复算见同目录JSON。

# %%
from IPython.display import Markdown
quality_order=pd.Series(Qd).sort_values(ascending=False)
quality_text='、'.join(f'{d}（{v:.4f}）' for d,v in quality_order.items())
increment=pd.read_csv(TAB/'quality_increment.csv')
summary_text=(f"## 问题一计算结果\n\n平方相关赋权，β={BETA}。领域文档均分：{quality_text}。arxiv/github采用合并去重全量。\n\n"
              f"与线性基线的样本排序相关：{stats.spearmanr(A1.Q_res,A1.Q_lin)[0]:.6f}；权重范围：{wG.min():.6f}—{wG.max():.6f}。\n\n"
              "质量附加特征的检验结果：\n\n"+'|'+ '|'.join(increment.columns)+'|\n|'+'|'.join(['---']*len(increment.columns))+'|\n'+ '\n'.join('|'+ '|'.join(map(str,row))+'|' for row in increment.itertuples(index=False,name=None))+"\n\n"
              "领域均分和附加特征检验不证明质量的因果效应；配比主模型仍为对数线性，GBM为对照。\n")
(OUT/'results_summary.md').write_text(summary_text,encoding='utf-8')
display(Markdown(summary_text))

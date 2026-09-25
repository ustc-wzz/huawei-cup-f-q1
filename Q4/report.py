"""Write the solution chapter from final numerical outputs only."""
import hashlib,json,shutil
from pathlib import Path
import numpy as np
import pandas as pd
from data_pipeline import ROOT,OUT,dump

def read(n):return pd.read_csv(OUT/'tables'/f'{n}.csv')
def js(n):return json.loads((OUT/f'{n}.json').read_text())
def md(df):
    def fmt(v):
        if isinstance(v,(float,np.floating)):return '—' if np.isnan(v) else f'{v:.3f}'
        return str(v).replace('|','／')
    return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+\
        '\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in df.itertuples(index=False,name=None))

def run():
    assert js('verification')['status']=='passed'
    a=js('data_audit');c8=js('c8_audit');m=read('mediation_contributions');main=m.iloc[0]
    coef=read('mediation_coefficients');design=js('mediation_design');fore=js('forecast_design')
    pred=read('coupled_frontier_forecast');mainpred=pred[pred.scenario.eq('quarter_historical_growth')&pred.technical_half_life_months.eq(24)&pred.horizon_months.gt(0)]
    broad=read('broad_frontier_forecast');bmain=broad[broad.scenario.eq('quarter_historical_growth')]
    val=read('structural_validation_metrics');bval=read('broad_backtest_metrics');bridge=read('bridge_metrics')
    quant=read('structural_quantile_metrics');conf=read('confounding_sensitivity');quality=read('q3_cost_quality_sensitivity')
    absbridge=read('q3_absolute_bridge_forecast');jb=read('bridge_leave_report_out')
    labels={'pretrained':'基础','chat_finetuned':'对话／微调','merge':'合并'}
    outcome=coef[coef.equation.eq('outcome_logit')].set_index('term').value
    tab=m[['method','scale_points','technology_points','total_points','scale_share','technology_share']].copy()
    tab.columns=['模型','规模贡献/分','技术贡献/分','总变化/分','规模份额','技术份额']
    ptab=mainpred[['target_date','compute_budget','N_B','D_B','loss','forecast','lo','hi']].copy()
    ptab['compute_budget']=ptab.compute_budget.map(lambda x:f'{x:.4e}')
    ptab.columns=['目标日','预算/FLOPs','N/十亿','D/十亿Token','Loss','条件前沿/分','区间下限','区间上限']
    btab=bmain[['type','horizon_months','forecast','lo','hi']].copy();btab.type=btab.type.map(labels)
    btab.columns=['类型','预测月数','描述性前沿/分','区间下限','区间上限']
    files=read('c8_corrupt_files');dirs=read('c8_directory_ledger')
    badnames='、'.join(Path(v).name for v in files.file)
    bmetrics=bval.pivot(index='type',columns='method',values='MAE')
    win=[labels[k] for k,r in bmetrics.iterrows() if r.quantile_N_time<r.last_month_q90]
    fail=[labels[k] for k,r in bmetrics.iterrows() if r.quantile_N_time>=r.last_month_q90]
    qsample=read('c4_compute_sample')
    score_dispersion=read('task_weight_sensitivity').groupby('type').forecast_12m.agg(['min','max'])
    text=f'''# 问题四模型求解与结果（v0.6.0）

## 4.9 数据进入模型后的实际范围

全部观测来自本地附件；未下载外部模型记录。C1原有{a['c1_rows']}行，经许可证、日期、正参数量、六任务完整性筛选并去除{a['c1_duplicate_removed']}条重复仓库记录，保留{a['c1_unique_screened']}个模型。提交时间为{a['dates'][0]}至{a['dates'][1]}，不足一年。模型类型计数为：{a['types']}。合并模型单列，不能当作从头训练的新增资源样本。

C1与C4确定性匹配通过{a['matched']}个模型，其中满足基础模型、非明显MoE、发布日期和训练N/D均可用的主样本为{a['primary_nd']}个、{a['nd_organizations']}个发布机构，发布日期覆盖{a['nd_publication_range'][0]}至{a['nd_publication_range'][1]}。历史贡献是这个可比子样本的条件归因，不能直接推成全部开源大模型产业的总体份额。N/D源于报告元数据，部分本身是估计值。

六任务重建均分与C1官方Average的最大绝对差为{a['score_rebuild_max_error']:.3g}分，主分析等权口径与原榜单一致。C3共{a['c3_rows']}行，其中排行榜来源{a['c3_sources']['same_leaderboard']}行，历史文献来源{a['c3_sources']['historical_noncomparable']}行；历史来源只用于来源分层描述，不与同口径排行榜混合回归。图02展示两个时间轴与C3来源差别。

<span style="color:red">Insert figure here: figures/02_data_and_evolution.png</span>

## 4.10 JSON截断处理与逐任务结果

实际扫描{c8['directories']}个目录、{c8['json_files']}个JSON，发现{c8['corrupt_files']}个解析损坏文件。原件完整保留。{c8['corrupt_directories_with_fallback']}个损坏目录可使用同目录的有效替代评测，{c8['directories_without_valid']}个目录没有可解析评测，仅退出逐任务分析。最终保留{c8['models']}个可解析模型，其中{c8['complete']}个具有MuSR三个叶子任务完整值；这不表示六大任务全部完整。

选中评测中{c8['matched']}个模型与筛选后C1匹配，其中{c8['matching_within_1e_6']}个MuSR重建分与C1在1e-6内一致，中位绝对差为{c8['median_abs_difference']:.6f}分。差异记录保留在`c8_musr_reconstruction.csv`；最新评测与C1快照可能不同，不通过改写C1消除差异。三个叶子任务的分类型均分见`c8_task_type_summary.csv`与图06。

损坏文件名为：{badnames}。完整相对路径、解析错误、替代文件及无有效记录目录分别见`c8_corrupt_files.csv`和`c8_directory_ledger.csv`。处理规则与得分高低无关，未进行截断后拼接或缺项填零。

<span style="color:red">Insert figure here: figures/06_task_level_audit.png</span>

## 4.11 中介估计与贡献占比

主模型在logit能力尺度的估计为
\\[
\\widehat Z={outcome['intercept']:.6f}+{outcome['scale_index']:.6f}x(N,D)+{outcome['time_year']:.6f}T.
\\]
完整系数和噪声协方差分别保存于`mediation_coefficients.csv`、`noise_model.json`。时间T的单位为年，零点为2023-01-01；规模项x使用问题二固定参数。能力残差和成对规模残差均来自实际拟合，没有对原始数据额外添加随机噪声。

选取主样本发布日期四分位对比，即{design['start_date']}至{design['end_date']}。反事实积分得到起点能力{main.start_score:.3f}分、终点{main.end_score:.3f}分，总增量{main.total_points:.3f}分。这些是同一残差分布下的模型反事实均值，不是两个自然年度榜单的直接观测均分。

{md(tab)}

主模型规模份额为{100*main.scale_share:.2f}%，非规模份额为{100*main.technology_share:.2f}%。按发布机构进行400次重抽样，规模贡献95%区间为[{main.scale_points_lo:.3f}, {main.scale_points_hi:.3f}]分，非规模贡献为[{main.technology_points_lo:.3f}, {main.technology_points_hi:.3f}]分。相应份额区间分别为[{100*main.scale_share_lo:.2f}%, {100*main.scale_share_hi:.2f}%]与[{100*main.technology_share_lo:.2f}%, {100*main.technology_share_hi:.2f}%]，没有裁成0—100%。非规模贡献区间包含零，说明样本不足以精确确定它的符号与比例；用户确认的解释假设并不能消除估计不确定性。

自由N/D系数对照给出的规模份额为{100*m.iloc[1].scale_share:.2f}%，表明标度响应形状会影响归因。在ρ从−0.6到0.6的偏差压力测试中，规模份额范围为{100*conf.scale_share.min():.2f}%至{100*conf.scale_share.max():.2f}%；该范围不是真实混杂强度的置信区间。D测量误差压力测试见`data_volume_sensitivity.csv`。图01明确因果假设，图03展示贡献与敏感性。

<span style="color:red">Insert figure here: figures/01_causal_structure.png</span>

<span style="color:red">Insert figure here: figures/03_mediation_and_sensitivity.png</span>

## 4.12 泛化与前沿口径验证

均值能力预测采用相同划分、相同分数尺度评价，结果如下。发布队列留出存在同一模型在不同截点重复出现的情况，表中n是预测记录数，不是独立实验数；机构留出按整组划分。

{md(val)}

条件90%分位的验证另列，不用均值模型RMSE代替：

{md(quant)}

名义90%分位的机构留出覆盖率为{100*quant.set_index('design').loc['leave_organization','coverage']:.2f}%，发布队列留出覆盖率为{100*quant.set_index('design').loc['publication_holdout','coverage']:.2f}%，均低于90%。因此该前沿在样本外存在标定不足，不能把拟合分位数当作具有90%实证保障的未来上界。这里保留原始验证结果，不用留出集反向调高截距。

大样本提交日期回测只覆盖未来1—3个月，对照目标是同类型当月能力90%分位。预测时先将条件响应与规模分布、残差分布组合，再取整体90%分位。

{md(bval)}

按MAE比较，分位模型优于上月延续的类型为：{'、'.join(win) or '无'}；未胜出的类型为：{'、'.join(fail) or '无'}。因此对话／微调趋势可以作为有短期比较依据的描述性前沿；基础和合并类型的趋势预测仅作敏感性对照，不声称优于简单延续。短期回测不能为12/24个月外推提供同等强度的验证。主结构模型的长期情景也没有被这些短期榜单结果“证实”。

<span style="color:red">Insert figure here: figures/07_validation.png</span>

## 4.13 Loss—Benchmark桥接及误差传播

桥接逐层留一结果如下。n为该层总记录，validated_n为测试Loss仍位于训练折支撑区间内的记录；端点出界不参与误差平均，不能只报误差而隐藏覆盖。

{md(bridge)}

中可比层还按报告来源整组留出，共得到{len(jb)}条预测记录，其中{jb.prediction.notna().sum()}条处于训练支撑范围。可换算记录MAE为{jb.error.abs().mean():.3f}分。相同报告的多个模型并不是多次独立标度实验。

Q3未来主配置Loss范围为[{absbridge.loss.min():.6f}, {absbridge.loss.max():.6f}]。高可比层是否支持目标Loss，应逐行看`q3_absolute_bridge_forecast.csv`；当前高可比层支持{int(absbridge[absbridge.tier.eq('high')].supported.sum())}个目标配置。中可比桥接仅作为跨报告情景，并传播报告重抽样的不确定性。该桥接输出没有再加一次时间进步项，避免重复计量。高可比的局部小误差不代表其能外推到低Loss、高能力区域。

{md(absbridge[absbridge.scenario.eq('quarter_historical_growth')&absbridge.horizon_months.gt(0)][['horizon_months','tier','loss','prediction','lo','hi','supported','bootstrap_supported']])}

<span style="color:red">Insert figure here: figures/05_loss_benchmark_bridge.png</span>

## 4.14 未来12/24个月的条件前沿

预测起点固定为{fore['cutoff']}，是附件中最后可比观测日，不是程序运行日。故12个月、24个月的目标分别为2026-03-13和2027-03-13；这些输出不能表述为从2026年9月起的实时预测。C4历史算力样本为{fore['compute_sample']}个模型，最近一年预算90%分位为{fore['C0']:.6e} FLOPs，季度前沿拟合的年对数增速为{fore['historical_log_compute_growth_per_year']:.6f}。

主放缓情景取历史对数增速的四分之一，技术趋势半衰期24个月。在问题三p0、50%参考质量切片、s_Q=1、4096上下文、指数成本下得到：

{md(ptab)}

这些是基础模型在资源最优路径上的条件90%分位前沿。主样本最新发布日期早于预测起点，模型在起点就已有约{mainpred.iloc[0].past_last_matched_release_years:.3f}年的时间外推；未来参数量超出主样本范围时，`N_extrapolated`逐行标识。质量上限是问题三的文档筛选参照，不能解释为已证实的Token供给保证。

区间包含发布机构层面的能力拟合及算力元数据重抽样不确定性，但条件于问题二参数、非规模解释和结构迁移。不同成本／质量场景共{len(quality)}个资源配置，另有冻结、半增速和技术半衰期敏感性，分别见`q3_cost_quality_sensitivity.csv`及`coupled_frontier_forecast.csv`；它们不是已发生的真实实验。

大样本描述性前沿如下，训练数据量D缺失，时间项不能用于非规模贡献归因。表内参考规模分布固定为最近三个月，并按算力情景平移。

{md(btab)}

当前短期验证支持对话／微调类型优于朴素基线；合并类型虽可能给出更高预测值，但短期预测未胜出，不据其较高数值宣称整体最优前沿。删除单个能力任务的12个月预测范围为：{score_dispersion.to_dict('index')}。任务权重影响实质性能力定义，不能通过挑选任务得到预期排名。

<span style="color:red">Insert figure here: figures/04_frontier_forecasts.png</span>

## 4.15 可以成立的结论与尚未识别的部分

本次完整实现了“附件审计→N/D中介分解→Loss桥接→Q3资源耦合→12/24个月前沿与不确定性”的计算链。主样本的点估计支持规模和非规模两条路径均有正贡献，但技术贡献区间包含零，且份额对结构形状和混杂压力测试敏感。扩大模型并非唯一解释，现有数据也不足以确定一个精确、普适的技术贡献百分比。

高可比Loss桥接不能覆盖本次未来资源配置的低Loss区间，中可比映射又存在明显跨报告误差。因此条件结构前沿、描述性聊天前沿及绝对桥接情景并列报告，不合并成一条看似精确的预测线。数据质量刻度、未知训练Token供给、跨族标度迁移、元数据缺失选择与远期技术速率仍是模型边界。

独立数值和证据核验状态：{js('verification')['status']}，通过{len(js('verification')['checks'])}项。验证涵盖公式恒等式、退化情形、有限差分、预算守恒、支撑边界、任务重建及输入哈希；它不构成因果识别证明。结果表是论文数字的唯一来源，原始附件未修改。
'''
    (OUT/'模型求解.md').write_text(text)
    shutil.copyfile(ROOT/'Q4/模型建立.md',OUT/'模型建立.md')
    summary=f'''# 问题四结果入口 — v0.6.0

全部数据来自本地附件，原件未修改；方法、代码和实际输出已统一。

- 主样本：{a['primary_nd']}个基础模型、{a['nd_organizations']}家机构，完整N/D与发布日期；大样本榜单{a['c1_unique_screened']}个模型。
- 归因区间：{design['start_date']}→{design['end_date']}。规模{main.scale_points:.3f}分（{main.scale_share:.2%}），技术{main.technology_points:.3f}分（{main.technology_share:.2%}）；技术贡献95%区间[{main.technology_points_lo:.3f},{main.technology_points_hi:.3f}]分，包含零。
- JSON：{c8['corrupt_files']}个损坏文件，{c8['corrupt_directories_with_fallback']}个目录有替代，{c8['directories_without_valid']}个目录退出逐任务分析；保留原文件与错误台账。
- 未来起点为{fore['cutoff']}。主Q3耦合基础模型前沿：12个月{mainpred.iloc[0].forecast:.2f}分，24个月{mainpred.iloc[1].forecast:.2f}分；均为有明确假设的90%条件分位，区间及规模外推见下表。
- 聊天／微调描述性模型短期MAE={bmetrics.loc['chat_finetuned','quantile_N_time']:.3f}，上月延续={bmetrics.loc['chat_finetuned','last_month_q90']:.3f}；基础、合并类型未胜出，保留失败结果。
- 高可比桥接对未来Loss不支持，返回缺失；中可比只作跨报告情景。完整方法与求解章节中说明误差和不能识别的部分。

{md(ptab)}

入口：`0925_问题四.ipynb`；复现：`Q1/.venv/bin/python Q4/run_notebook.py`。正式章节为`模型建立.md`、`模型求解.md`，源数据索引见`input_manifest.json`及`c8_input_manifest.json`。图件在`figures/`，结果在`tables/`。
'''
    (OUT/'results_summary.md').write_text(summary)
    dump(dict(version='v0.6.0',causal_status='conditional on maintained assumptions',
        complete_ND_population='matched pretrained only',contributions=main.to_dict(),
        origin=fore['cutoff'],forecast_targets=mainpred[['target_date','forecast','lo','hi']].to_dict('records'),
        bridges='high-comparability future losses unsupported; medium cross-report scenario only',
        input_interfaces=['output_q2_shared/q2_interface.json','output_q3_resource/config.json']), 'q4_interface')
    artifacts=[]
    for p in sorted(OUT.rglob('*')):
        if p.is_file() and p.name not in ['artifact_manifest.json','delivery_checks.json']:
            artifacts.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,
                              sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    for p in sorted((ROOT/'Q4').iterdir()):
        if p.suffix in ['.py','.md'] or p.name=='requirements.txt':
            artifacts.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,
                                  sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    dump(artifacts,'artifact_manifest')
    print('Method, solution, summary and interface written from verified outputs.',flush=True)

if __name__=='__main__':run()

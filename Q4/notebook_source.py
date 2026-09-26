# %% [markdown]
# # 问题四：技术演进中介分解与能力前沿预测
#
# 全部计算数据使用本地附件；核心假设为控制可比规模后，剩余时间效应代表非规模技术进步。历史归因以完整N/D基础模型为主；大样本榜单分类型预测单独报告，时间轴不混用。
#
# 从头执行本notebook会重新生成审计、贡献、桥接、前沿、回测、图件和两篇章节。前面三问代码与结果只读。JSON原件不删除或修补，损坏与替代规则有逐文件台账。

# %%
from pathlib import Path
import sys,time,json
import pandas as pd
from IPython.display import display,Markdown,Image
ROOT=Path.cwd()
if not (ROOT/'real_attachments').exists(): ROOT=ROOT.parent
assert (ROOT/'Q4/evolution_model.py').exists()
sys.path.insert(0,str(ROOT/'Q4'))
from data_pipeline import OUT,read_data,aggregate_c8
from evolution_model import mediation_analysis,bridge_analysis,coupled_forecast,broad_analysis
from run_analysis import provenance
started=time.time()
print('Python:',sys.executable)
print('计算数据：仅本地附件；预测起点由最后可比观测日期决定。')

# %% [markdown]
# ## 一、模型建立与推导
#
# 下文给出变量、假设、噪声、有限时期反事实分解、预算耦合和验证方法。结果由后续代码真实运行后产生。

# %%
display(Markdown((ROOT/'Q4/模型建立.md').read_text(encoding='utf-8')))

# %% [markdown]
# ## 二、样本筛选与确定性匹配
#
# 名称匹配保留小数点，限定命名空间与参数数量级，拒绝歧义。不将缺失D补为估计观测，不将对话模型的后训练数据量当成预训练总量。

# %%
clean,nd,epoch,paired=read_data()
display(pd.Series(json.loads((OUT/'data_audit.json').read_text(encoding='utf-8')),name='数据审计'))
display(nd[['Model','N','D','publication_date','S']])

# %% [markdown]
# ## 三、C8截断JSON与逐任务检验
#
# 扫描全部文件，保留原件与哈希；同目录选择最新可解析记录。MuSR必须由三个叶子任务分别扣除随机猜测基线后聚合，缺项不补零。

# %%
c8,c8audit=aggregate_c8(clean)
display(pd.Series(c8audit,name='逐任务审计'))
display(pd.read_csv(OUT/'tables/c8_corrupt_files.csv'))
display(pd.read_csv(OUT/'tables/c8_task_type_summary.csv'))

# %% [markdown]
# ## 四、历史贡献与敏感性
#
# N/D中介保留相关残差，能力噪声按经验分布积分。四个反事实角点的对称分解在能力分尺度严格可加；机构重抽样与混杂压力测试分开解释。

# %%
mediation,validation=mediation_analysis(nd)
display(mediation)
display(validation)
display(pd.read_csv(OUT/'tables/structural_quantile_metrics.csv'))

# %% [markdown]
# ## 五、Loss—Benchmark分层桥接
#
# 高、中可比层分别拟合和验证；Loss出界返回缺失，不能截到边界。跨报告结果仅作情景，不冒充同验证集映射。

# %%
bridge,bridge_models,bridge_metrics=bridge_analysis()
display(bridge_metrics)

# %% [markdown]
# ## 六、承接问题三的资源配置与未来前沿
#
# 固定问题三主情景，考察冻结、历史增速1/4、历史增速1/2三种预算路径；技术趋势的12个月、24个月和不衰减半衰期分别保存。质量与配比基准不在时间项之外重复计量。

# %%
forecast=coupled_forecast(nd,epoch,clean.date.max(),bridge_models)
display(forecast.query('technical_half_life_months == 24')[['scenario','horizon_months','target_date','forecast','lo','hi','N_B','D_B','loss','N_extrapolated','D_extrapolated']])
display(pd.read_csv(OUT/'tables/q3_absolute_bridge_forecast.csv'))

# %% [markdown]
# ## 七、分类型大样本预测与真实短期回测
#
# 这条对照缺少D，剩余时间项只作描述性解释。回测先合成规模分布与能力残差，再取月度90%分位，与上月延续比较。1—3个月回测不能替代12/24个月的长期验证。

# %%
broad,broad_metrics=broad_analysis(clean,epoch)
display(broad_metrics)
display(broad.query('scenario == "quarter_historical_growth"')[['type','horizon_months','target_date','forecast','lo','hi']])

# %% [markdown]
# ## 八、独立核验、图件与论文结果
#
# 数值恒等式和数据边界核验通过后，再从最终结果表生成求解章节。核验通过不表示因果假设已证实。

# %%
provenance(started)
from verify import run as verify_run
verification=verify_run()
display(pd.Series(verification['checks'],name='独立核验'))
# 按项目绘图规范导出：数学排版、连续子图编号、统一配色及PNG/SVG/PDF。
from plots import run as plot_run
plot_run()
from report import run as report_run
report_run()

# %%
for name in ['01_causal_structure','02_data_and_evolution','03_mediation_and_sensitivity','04_frontier_forecasts','05_loss_benchmark_bridge','06_task_level_audit','07_validation']:
    display(Image(filename=str(OUT/'figures'/f'{name}.png'),width=1000))

# %%
display(Markdown((OUT/'模型求解.md').read_text(encoding='utf-8')))
print('完成。结果入口：',OUT/'results_summary.md')

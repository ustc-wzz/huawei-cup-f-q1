from pathlib import Path
import pandas as pd,numpy as np
O=Path('output_q1_redundancy');d=pd.read_csv(O/'duplicate_metrics.csv');b=pd.read_csv(O/'bootstrap_metrics.csv');w=pd.read_csv(O/'bootstrap_weights.csv')
a=d.groupby(['copy','power'])[['rho','top10_overlap','bottom10_overlap','family_weight_inflation','mean_abs_rank_shift']].mean();a.to_csv(O/'duplicate_summary.csv')
c=b.groupby(['set','power'])[['rho','top10_overlap','bottom10_overlap','mean_abs_rank_shift','weight_L1']].mean();c.to_csv(O/'bootstrap_summary.csv')
rows=[]
for s,g in b.groupby('set'):
 for metric in ['rho','top10_overlap','bottom10_overlap','mean_abs_rank_shift','weight_L1']:
  p=g.pivot(index='replicate',columns='power',values=metric);diff=p[2]-p[1]
  rows.append({'set':s,'metric':metric,'square_minus_abs_mean':diff.mean(),'paired_low':diff.quantile(.025),'paired_high':diff.quantile(.975)})
pd.DataFrame(rows).to_csv(O/'paired_bootstrap_differences.csv',index=False)
def table(df):
 df=df.reset_index();return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(f'{x:.6f}' if isinstance(x,float) else str(x) for x in row)+' |' for row in df.itertuples(index=False,name=None))
text='''# 绝对相关与平方相关：固定预处理对照实验

本实验仅检验两种冗余赋权规则，主模型及后续接口未修改。固定22项预处理、A1参考和β=0.25；平方相关不等于多个指标联合可解释方差。

## 1. 重复指标

逐一复制全部22项指标，各加入一个完全副本或一个标准差为原指标0.5倍的高斯噪声副本（再恢复原均值/标准差）；两方法使用同一副本。下表为22项实验均值。rho和头尾10%重合率越高越好，排名变动越小越好。家族权重膨胀比=复制后原指标加副本总权重/复制前原指标权重，越接近1越好；不是该家族绝对权重越低越好。

'''+table(a)+'''

## 2. 分层重抽样

固定A1每域20%留出，另外80%训练相关矩阵；按领域保持样本数有放回重抽样200次。预处理按用户要求固定，因此这是条件于既定预处理的权重稳定性，不是从原始数据起的独立端到端验证。A2/A3剔除与A1重复的ID，全量作为固定外部评分对象；不将它们视作带人工标签的质量检验集。每次与该方法在80%训练部分拟合的基准比较，避免把留出变化误计为抽样波动。

'''+table(c)+'''

paired_bootstrap_differences.csv给出同次抽样“平方−绝对值”的差及其2.5%—97.5%经验分位区间；它描述重抽样扰动分布，不应当作两方法真实准确率差的置信区间。

## 3. 独立质量核验：待人工标注

每个A1领域3对随机样本、3对排序相反的分歧样本，共42对84篇无重复文本；覆盖book/arxiv/github及其余4域。每对左右随机，全文保留。blind_review仅包含随机配对号、文本及空白评审表，不包含分数、指标或方法名。analyst_key.csv只供分析者使用，勿发给评审。两名评审独立判断，随机与分歧两层分开统计。

运行 `python Q1_redundancy/evaluate_reviews.py` 汇总已填的两份表：非平局可判断对上计算各法一致率，并对配对差按领域分层重抽样给出95%区间；同时报告可评数量、平局、无法判断及评审一致率。没有标注时程序只报告缺失，不生成虚构的准确率。

当前不能宣称平方形式的质量判别更准确；数值稳定性和抗重复计分只是方法性质。若人评改善而抗重复/稳定性明显退步，应同时报告权衡，不能只挑有利结果。
'''
text+='''

## 本次结果判断

平方形式在全部44个复制实验中减小平均绝对排名扰动。完全副本：扰动从1.3166%降至0.6686%，家族权重膨胀从1.6759倍降至1.4179倍；噪声副本：扰动从1.6830%降至1.2437%。因此本次数据和指定扰动设置支持平方形式的抗重复计分性质更好，但两者都未完全消除重复加权。

200次重抽样的权重L1变动均值从0.005696降至0.005164，A1/A2/A3平均排名扰动分别从0.1036%/0.1491%/0.1372%降至0.0955%/0.1167%/0.1270%；改善幅度较小。A1头部10%重合率反而从99.7298%降至99.6849%；配对扰动差区间均跨零，不能声称一致或显著优胜。

正式替换尚待人评证据。本实验保留原主模型，未修改问题一Q、配比接口或问题二至四计算。
'''
(O/'实验报告.md').write_text(text)
print(a.to_string());print(c.to_string())

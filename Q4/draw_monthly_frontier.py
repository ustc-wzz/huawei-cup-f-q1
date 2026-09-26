"""Attachment-only monthly descriptive frontier; independent of causal estimation."""
from pathlib import Path
import sys, json, hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'Q4'))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, ticker
from data_pipeline import LICENSES,DIMS,model_type
from repro_runtime import configure_fonts
OUT=ROOT/'output_q4_monthly_frontier'

def run():
    OUT.mkdir(exist_ok=True)
    raw=ROOT/'real_attachments/C_efficiency_evolution/leaderboard_cleaned.csv'
    existing=ROOT/'output_q4_evolution/tables/c1_analysis.csv'
    a=pd.read_csv(raw)
    a['date']=pd.to_datetime(a['Submission Date'],errors='coerce')
    a['N']=pd.to_numeric(a['#Params (B)'],errors='coerce')
    a['license']=a['Hub License'].fillna('').str.lower().str.strip()
    a[DIMS]=a[DIMS].apply(pd.to_numeric,errors='coerce')
    a['S']=a[DIMS].mean(axis=1,skipna=False)
    a['type']=a.Type.map(model_type)
    mask=a.license.isin(LICENSES)&a.date.notna()&a.N.gt(0)&a[DIMS].ge(0).all(axis=1)&a[DIMS].le(100).all(axis=1)
    d=a.loc[mask].sort_values(['date','Model'],kind='stable').drop_duplicates('Model',keep='first').copy()
    d['month']=d.date.dt.to_period('M').astype(str)
    old=pd.read_csv(existing).set_index('Model').sort_index()
    now=d.set_index('Model').sort_index()
    assert old.index.equals(now.index)
    assert np.allclose(old[['N','S']],now[['N','S']],atol=1e-12,rtol=0)
    cutoff=d.date.max()
    rows=[];front_members=[];typerows=[]
    for month,g in d.groupby('month',sort=True):
        q90=g.S.quantile(.9,interpolation='linear');q80=g.S.quantile(.8,interpolation='linear')
        f=g[g.S.ge(q90)];f80=g[g.S.ge(q80)]
        rows.append(dict(month=month,n=len(g),q90=q90,maximum=g.S.max(),frontier_n=len(f),
             frontier_N_median_B=f.N.median(),top20_N_median_B=f80.N.median(),
             partial_month=month==cutoff.strftime('%Y-%m') and cutoff.day<cutoff.days_in_month))
        front_members.append(f[['Model','month','date','N','S','type','license']])
        for typ,t in g.groupby('type'):
            typerows.append(dict(month=month,type=typ,n=len(t),q90=t.S.quantile(.9),
                frontier_n=int(f.type.eq(typ).sum()),frontier_share=float(f.type.eq(typ).mean())))
    m=pd.DataFrame(rows);types=pd.DataFrame(typerows)
    m.to_csv(OUT/'monthly_statistics.csv',index=False)
    types.to_csv(OUT/'monthly_type_composition.csv',index=False)
    pd.concat(front_members).to_csv(OUT/'frontier_members.csv',index=False)
    assert int(m.n.sum())==len(d)
    assert m.q90.le(m.maximum).all() and m.frontier_N_median_B.gt(0).all()
    first=m.head(3);late=m[~m.partial_month].tail(3);last=m.tail(3)
    summary=dict(n=len(d),date_min=str(d.date.min().date()),date_max=str(cutoff.date()),
        first_three_q90_mean=float(first.q90.mean()),last_three_complete_q90_mean=float(late.q90.mean()),
        complete_change=float(late.q90.mean()-first.q90.mean()),
        last_three_including_partial_q90_mean=float(last.q90.mean()),
        including_partial_change=float(last.q90.mean()-first.q90.mean()),
        initial_frontier_N_B=float(m.iloc[0].frontier_N_median_B),
        final_frontier_N_B=float(m.iloc[-1].frontier_N_median_B),
        final_complete_frontier_N_B=float(m[~m.partial_month].iloc[-1].frontier_N_median_B))
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    configure_fonts()
    if 'Arial Unicode MS' in {f.name for f in font_manager.fontManager.ttflist}:
        plt.rcParams['font.family']=['Arial Unicode MS']
    plt.rcParams.update({'font.size':9,'axes.titlesize':10,'axes.labelsize':9,
        'xtick.labelsize':8,'ytick.labelsize':8,'axes.spines.top':False,'axes.spines.right':False,
        'axes.linewidth':.7,'axes.edgecolor':'#64717A','text.color':'#283946',
        'axes.labelcolor':'#283946','xtick.color':'#46525C','ytick.color':'#46525C',
        'mathtext.fontset':'stix','pdf.fonttype':42,'svg.fonttype':'none','legend.frameon':False})
    # Contract: historical sample frontier and its composition, not causal effects.
    # 180 mm wide; hero panel + two aligned contextual panels; white background.
    fig=plt.figure(figsize=(180/25.4,116/25.4),facecolor='white')
    gs=fig.add_gridspec(2,2,width_ratios=[1.32,1],left=.09,right=.98,bottom=.19,top=.91,wspace=.32,hspace=.43)
    ax=fig.add_subplot(gs[:,0]);bc=fig.add_subplot(gs[0,1]);sc=fig.add_subplot(gs[1,1],sharex=bc)
    x=np.arange(len(m));labels=[s[2:] + ('*' if p else '') for s,p in zip(m.month,m.partial_month)]
    blue,orange='#376F91','#BC7844'
    for z in [ax,bc,sc]:
        z.set_axisbelow(True);z.grid(axis='y',color='#E5E9EC',lw=.6)
        z.set_xlim(-.4,len(m)-.6)
        for i,p in enumerate(m.partial_month):
            if p:z.axvspan(i-.4,i+.4,color='#F2F3F4',zorder=0)
    ax.plot(x,m.q90,'o-',color=blue,lw=1.5,ms=4,label='当月第90百分位')
    ax.plot(x,m.maximum,'^--',color=orange,lw=1.2,ms=4,label='当月最高分')
    ax.hlines(first.q90.mean(),-.05,2.05,color='#8A959E',ls=':',lw=1)
    li=m.index[m.month.isin(late.month)]
    ax.hlines(late.q90.mean(),li.min()-.05,li.max()+.05,color='#8A959E',ls=':',lw=1)
    ax.set_title('(a) 月度观测能力前沿',loc='left',pad=10)
    ax.set_ylabel('六任务综合能力 / 分');ax.set_xlabel('榜单提交月份')
    ax.set_xticks(x,labels,rotation=55,ha='right')
    ax.set_ylim(max(0,min(m.q90.min(),m.maximum.min())-7),max(m.maximum)+6)
    ax.legend(loc='lower right',fontsize=8,handlelength=2)
    bc.bar(x,m.n,width=.62,color='#B5D3E4',edgecolor='#81ADC7',lw=.4)
    bc.set_title('(b) 当月入榜样本数',loc='left',pad=10);bc.set_ylabel('模型数')
    bc.set_ylim(0,m.n.max()*1.24)
    for i,n in enumerate(m.n):bc.text(i,n+5,str(n),ha='center',fontsize=7,color='#536B7A')
    bc.tick_params(axis='x',labelbottom=False)
    sc.plot(x,m.frontier_N_median_B,'s-',color=orange,lw=1.3,ms=3.8)
    sc.set_yscale('log',base=2);sc.yaxis.set_major_locator(ticker.FixedLocator([8,16,32,64,128]))
    sc.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:g}'));sc.yaxis.set_minor_locator(ticker.NullLocator())
    sc.set_ylim(m.frontier_N_median_B.min()/1.3,m.frontier_N_median_B.max()*1.35)
    sc.set_title('(c) 前沿模型的参数量中位数',loc='left',pad=10)
    sc.set_ylabel('$N$ / 十亿参数\n（对数轴）');sc.set_xlabel('榜单提交月份')
    sc.set_xticks(x,labels,rotation=55,ha='right')
    fig.text(.09,.028,'* 2025年3月仅截至13日；前沿模型为当月得分达到第90百分位的模型。',fontsize=7.5,color='#586A76')
    for ext in ['png','pdf','svg']:fig.savefig(OUT/f'monthly_frontier.{ext}',dpi=600,facecolor='white')
    fig.savefig('/tmp/q4_monthly_preview.png',dpi=180,facecolor='white')
    plt.close(fig)
    f0=summary['initial_frontier_N_B'];f1=summary['final_frontier_N_B']
    text=f'''# 开放权重模型的月度观测能力前沿

## 图注

图：开放权重榜单样本的月度能力前沿、样本数量与前沿规模。(a) 按榜单提交月份计算六任务综合分的第90百分位及最高分；灰色短虚线分别表示最初三个观测月和最后三个完整观测月的月度第90百分位均值。(b) 当月通过筛选并按模型名称去重的样本数。(c) 当月得分达到第90百分位的模型之参数量中位数，纵轴采用对数刻度、刻度值仍为十亿参数。分位数采用线性插值，阈值相同的模型全部纳入。灰色背景及星号标记不完整的2025年3月，记录截止2025年3月13日。首月的首条记录为2024年6月8日，不据此假定覆盖6月1—7日。图中没有预测区间或置信区间；折线连接月度统计值，并非连续技术轨迹。

## 可用于论文的分析

基于附件C1及第四问既定许可筛选规则，共保留{len(d)}个具有有效参数量、提交时间和六项任务分数的模型，按提交月份构造月度观测前沿。2024年6—8月的月度第90百分位均值为{summary['first_three_q90_mean']:.2f}分，最后三个完整观测月（2024年12月—2025年2月）为{summary['last_three_complete_q90_mean']:.2f}分，两组均值相差{summary['complete_change']:.2f}分。若按示例采用2025年1—3月，则均值为{summary['last_three_including_partial_q90_mean']:.2f}分、相差{summary['including_partial_change']:.2f}分，但3月尚非完整月份，因此仅作为补充描述。上述统计反映该榜单筛选样本较高分位水平的变化，不等同于单个模型随时间持续学习的轨迹。

各月样本数在{m.n.min()}—{m.n.max()}之间变化，且不同月份对应不同模型集合。因此，第90百分位及最高分的月际波动可能同时包含能力进步、模型类型与规模构成变化以及提交选择效应；仅凭曲线不能把下降判定为技术退步，也不能断言全部波动均由样本更替造成。最高分还更易受少量极端模型和当月样本量影响，第90百分位适合作为较稳健的描述性指标，但不是与样本构成无关的真实能力上限。

前沿模型参数量中位数从首月的{f0:.2f}B变为末月的{f1:.2f}B，最后一个完整月为{summary['final_complete_frontier_N_B']:.2f}B。该指标描述当月高分模型的规模构成；其变化不能单独证明参数效率提升，因为训练数据量、模型类型及后训练方式没有保持不变。相应地，月度聚合图也不能用来判定个体模型的规模效应系数应当为正或为负，更不能直接解释我们历史归因中的56.98%与43.02%。

本图在第四问中的作用是展示历史背景，并说明为何需要在后续结构模型中同时考虑规模与时间。图中使用提交月份、包含多种模型类型；历史归因模型则使用35个基础模型的发布日期及完整N/D数据，二者的样本与时间定义不同。图中“观测前沿”与后文“给定最优资源配置的条件90%预测分位”也不是同一估计对象，不能无缝拼接为一条曲线。

## 数据口径与复现

- 使用既定开放权重／研究使用许可证列表，包含部分限制性许可证；不称为“严格开源”，也未新增外部许可核验。
- 以Model名称去重保留最早有效提交；分数为六任务等权均值。相同基础模型的派生版本仍是不同模型，样本数不等于独立研发实验数。
- 前沿成员采用90%阈值。示例正文采用80%阈值，口径不同，不能照搬其参数规模数字；80%阈值的对照结果保存在源数据表中。
- 月度均值为三个“月度第90百分位”的等权均值，不是把三个月样本合并后再求第90百分位。
- 图及分析为独立描述性补充，不重新估计原模型，不修改原Notebook、数值结果或ZIP。
'''
    (OUT/'分析与图注.md').write_text(text,encoding='utf-8')
    audit={'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [raw,existing]},
        'n':len(d),'agrees_with_existing_analysis':True,'monthly_count_conserved':True,
        'frontier_threshold':.9,'sensitivity_threshold':.8,'quantile_method':'linear',
        'backend':'python','figure_width_mm':180,'figure_height_mm':116,'dpi':600,
        'license_scope':'existing operational open-weight/research-use allowlist; not strict open source',
        'causal_claim':False}
    (OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(m.to_string(index=False));print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':run()

"""Figures only from executed Q4 tables; no generated observations."""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from data_pipeline import OUT

COLORS=['#366C91','#CB8548','#708B76','#8B7396']
TYPE={'pretrained':'预训练基础','chat_finetuned':'对话／微调','merge':'合并模型','continued':'继续预训练','other':'其他'}

def table(n):return pd.read_csv(OUT/'tables'/f'{n}.csv')
def setup():
    from repro_runtime import configure_fonts
    configure_fonts()
    plt.rcParams.update({
      'axes.unicode_minus':False,'font.size':10,'axes.titlesize':12,'axes.labelsize':10,
      'mathtext.fontset':'stix','figure.facecolor':'white','axes.facecolor':'white',
      'axes.edgecolor':'#555555','axes.linewidth':.8,'grid.color':'#E5E7EB','grid.linewidth':.55,
      'axes.spines.top':False,'axes.spines.right':False,'legend.frameon':False,
      'pdf.fonttype':42,'svg.fonttype':'none','figure.dpi':130,'savefig.dpi':300,'figure.figsize':(6.5,4.2)})
def export(fig,name):
    dest=OUT/'figures';dest.mkdir(exist_ok=True)
    root=OUT.parent/'figures';root.mkdir(exist_ok=True)
    number=int(name[:2])+36
    stem=f'fig_{number:02d}_q4_{name[3:]}'
    from figure_typography import format_math_labels
    format_math_labels(fig)
    for ax in fig.axes:
        if ax.axison and ax.get_label() != '<colorbar>':
            ax.set_axisbelow(True)
            ax.grid(axis='y',alpha=.7)
    fig.savefig(dest/f'{name}.svg',bbox_inches='tight')
    fig.savefig(root/f'{stem}.pdf',bbox_inches='tight')
    fig.savefig(dest/f'{name}.png',dpi=300,bbox_inches='tight');fig.savefig(dest/f'{name}.pdf',bbox_inches='tight')
    fig.savefig(root/f'{stem}.png',dpi=300,bbox_inches='tight');fig.savefig(root/f'{stem}.svg',bbox_inches='tight');plt.close(fig)

def causal():
    from draw_causal_publication import draw, embed_svg_font
    with matplotlib.rc_context():
        fig=draw(save_outputs=False)
        export(fig,'01_causal_structure')
        embed_svg_font(OUT/'figures/01_causal_structure.svg')
        embed_svg_font(OUT.parent/'figures/fig_37_q4_causal_structure.svg')


def sample_plot():
    nd=table('nd_primary_sample');d=table('c1_analysis');c3=table('c3_source_year_audit')
    fig,axs=plt.subplots(1,3,figsize=(13,3.8),layout='constrained')
    x=pd.to_datetime(nd.publication_date);p=axs[0].scatter(x,nd.S,c=np.log10(nd.D),cmap='viridis',s=35)
    axs[0].set(title=f'(a) 完整 $N$、$D$ 基础模型（$n={len(nd)}$）',ylabel='综合能力 / 分',xlabel='发布日期')
    fig.colorbar(p,ax=axs[0],label=r'$\log_{10}D$（$D$ 以十亿 Token 计）',shrink=.8)
    for i,typ in enumerate(['pretrained','chat_finetuned','merge']):
        z=d[d.type.eq(typ)].copy();z['month']=pd.to_datetime(z.month)
        g=z.groupby('month').S.quantile(.9)
        axs[1].plot(g.index,g.values,marker=['o','s','^'][i],linestyle=['-','--','-.'][i],ms=3,color=COLORS[i],label=TYPE[typ])
    axs[1].set(title='(b) 榜单月度第90百分位',xlabel='提交月份',ylabel='综合能力 / 分');axs[1].legend(fontsize=8)
    for klass,lab,col in [('same_leaderboard','排行榜来源',COLORS[0]),('historical_noncomparable','历史文献（不可直接比较）',COLORS[1])]:
        z=c3[c3.source_class.eq(klass)];axs[2].plot(z.Year,z.mean_score,'o--',label=lab,color=col)
    axs[2].set(title='(c) C3来源审计',xlabel='附件年份',ylabel='来源内平均分（不混合拟合）');axs[2].legend(fontsize=8)
    for a in axs[:2]:a.tick_params(axis='x',rotation=30)
    export(fig,'02_data_and_evolution')

def contributions():
    m=table('mediation_contributions').iloc[0];s=table('confounding_sensitivity')
    fig,ax=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for j,(k,lab) in enumerate([('scale_points','规模扩张'),('technology_points','非规模进步')]):
        ax[0].errorbar(m[k],j,xerr=[[m[k]-m[k+'_lo']],[m[k+'_hi']-m[k]]],fmt='o',
             color=COLORS[j],capsize=5,ms=8,label=lab)
        ax[0].text(m[k],j+.15,f'{m[k]:.2f} 分',ha='center')
    ax[0].set(yticks=[0,1],yticklabels=['规模扩张','非规模进步'],ylim=(-.5,1.6),
              xlabel='贡献 / 能力分；95%机构自助区间',title='(a) 同一时间对比的贡献分解')
    ax[0].axvline(0,color='gray',lw=.8,ls='--')
    for k,lab,c in [('scale_share','规模份额',COLORS[0]),('technology_share','技术份额',COLORS[1])]:
        ax[1].plot(s.rho,100*s[k],marker='o' if k=='scale_share' else 's',linestyle='-' if k=='scale_share' else '--',ms=3,color=c,label=lab)
    ax[1].axvline(0,color='gray',lw=.8,ls='--');ax[1].axhline(0,color='gray',lw=.8)
    ax[1].set(title='(b) 未观测混杂的偏差压力测试',xlabel=r'假定的残差相关 $\rho$',ylabel='贡献份额 / %');ax[1].legend()
    export(fig,'03_mediation_and_sensitivity')

def forecast_plot():
    d=table('coupled_frontier_forecast');b=table('broad_frontier_forecast')
    d=d[d.technical_half_life_months.eq(24)]
    labels={'compute_frozen':'算力冻结','quarter_historical_growth':'历史增速的1/4（主）','half_historical_growth':'历史增速的1/2'}
    fig,ax=plt.subplots(1,2,figsize=(11,4.3),layout='constrained')
    for i,(k,g) in enumerate(d.groupby('scenario',sort=False)):
        ax[0].plot(g.horizon_months,g.forecast,marker=['o','s','^'][i],linestyle=['-','--','-.'][i],label=labels[k],color=COLORS[i])
        if k=='quarter_historical_growth':ax[0].fill_between(g.horizon_months,g.lo,g.hi,color=COLORS[i],alpha=.15,label='主情景条件95%区间')
    ax[0].set(title='(a) Q3耦合：基础模型条件90%分位',xlabel='距2025-03-13 / 月',ylabel='能力前沿 / 分',ylim=(0,100),xticks=[0,12,24]);ax[0].legend(fontsize=8)
    for i,typ in enumerate(['pretrained','chat_finetuned','merge']):
        g=b[b.type.eq(typ)&b.scenario.eq('quarter_historical_growth')]
        ax[1].errorbar(g.horizon_months+i*.4,g.forecast,yerr=[g.forecast-g.lo,g.hi-g.forecast],
                       fmt=['o-','s--','^-.'][i],color=COLORS[i],capsize=4,label=TYPE[typ])
    ax[1].set(title='(b) 仅含规模 $N$ 的预测（描述性对照）',xlabel='距2025-03-13 / 月',ylabel='参考分布90%分位 / 分',ylim=(0,100),xticks=[12,24]);ax[1].legend(fontsize=8)
    export(fig,'04_frontier_forecasts')

def bridge_plot():
    b=table('bridge_evidence');k=table('bridge_knots');r=table('q3_absolute_bridge_forecast')
    fig,ax=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for i,(tier,title) in enumerate([('high','高可比：同一验证集'),('medium','中可比：跨报告情景')]):
        z=b[b.tier.eq(tier)];kk=k[k.tier.eq(tier)];rr=r[r.tier.eq(tier)]
        ax[i].scatter(z.Val_Loss,z.LB_Average,s=23,color=COLORS[i],alpha=.65,label=f'附件观测／整理值（$n={len(z)}$）')
        ax[i].plot(kk.loss,kk.score,color=COLORS[i],lw=2,label='层内单调拟合')
        ax[i].axvspan(rr.loss.min(),rr.loss.max(),color='#8B7396',alpha=.18,label='Q3目标损失范围')
        ax[i].set(title=f'({"ab"[i]}) {title}',xlabel='交叉熵损失',ylabel='综合能力 / 分')
        ax[i].legend(fontsize=8)
    export(fig,'05_loss_benchmark_bridge')

def c8_plot():
    d=table('c8_task_type_summary');comp=table('c8_musr_reconstruction')
    tasks=['leaderboard_musr_murder_mysteries','leaderboard_musr_object_placements','leaderboard_musr_team_allocation']
    fig,ax=plt.subplots(1,2,figsize=(10.5,4),layout='constrained')
    for i,typ in enumerate(['pretrained','chat_finetuned','merge']):
        g=d[d.type.eq(typ)].set_index('task').reindex(tasks)
        ax[0].bar(np.arange(3)+(i-1)*.23,g['mean'],width=.22,color=COLORS[i],label=TYPE[typ])
    ax[0].set(xticks=np.arange(3),xticklabels=['谋杀推理','物体放置','团队分配'],ylabel='扣除随机基线后的得分',title='(a) 三项逐任务聚合');ax[0].legend(fontsize=8)
    diff=comp.difference.dropna();ax[1].hist(diff,bins=35,color=COLORS[0]);ax[1].set_yscale('log')
    ax[1].set(title='(b) 重建MuSR与C1快照差异',xlabel='重建分 − C1分',ylabel='模型数（对数轴）')
    ax[1].text(.97,.94,f'$n={len(diff)}$\n{(diff.abs()<1e-6).sum()}条数值一致',
               transform=ax[1].transAxes,ha='right',va='top',fontsize=9)
    export(fig,'06_task_level_audit')

def validation_plot():
    v=table('structural_validation_metrics');b=table('broad_backtest_metrics')
    methods=['scale_time','scale_only','time_only','free_nd'];labs=['标度＋时间','仅规模','仅时间','自由 $N$、$D$＋时间']
    fig,ax=plt.subplots(1,3,figsize=(12,4),layout='constrained')
    for i,design in enumerate(['leave_organization','publication_holdout']):
        z=v[v.design.eq(design)].set_index('method').reindex(methods)
        ax[i].barh(labs,z.MAE,color=[COLORS[0],'#9DB1BE','#B9BFC4',COLORS[1]])
        ax[i].invert_yaxis();ax[i].set(xlabel='能力分 MAE',title=['(a) 机构留出','(b) 发布队列阻塞留出'][i])
    for i,m in enumerate(['quantile_N_time','last_month_q90']):
        g=b[b.method.eq(m)].set_index('type').reindex(['pretrained','chat_finetuned','merge'])
        ax[2].bar(np.arange(3)+(i-.5)*.34,g.MAE,width=.33,color=COLORS[i],label=['分位模型','上月延续'][i])
    ax[2].set(xticks=np.arange(3),xticklabels=['基础','对话／微调','合并'],ylabel='月度90%分位 MAE',title='(c) 提交时间短期回测');ax[2].legend(fontsize=8)
    export(fig,'07_validation')

def run():
    setup()
    for f in [causal,sample_plot,contributions,forecast_plot,bridge_plot,c8_plot,validation_plot]:f()
    from draw_causal_publication import draw
    draw()
    print('Seven PNG/SVG/PDF sets and the standalone causal diagram saved.',flush=True)

if __name__=='__main__':run()

"""Screening-supported scenarios and global quality-benefit decision thresholds.
All quantities are conditional predictions, not new training observations.
"""
from dataclasses import replace
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
import matplotlib.pyplot as plt
from .resource_model import COSTS, COST_LABELS, ETA_ATT, gp

RATES=(.8,.5,.2,.1,.05)
COLORS=dict(zip(COSTS,['#277DA1','#D17B35','#4D9078']))

def profile(model,C,ctx,cost,sc,u):
    r=model.inner(C,ctx,cost,sc,float(u))
    H=np.log(r['tn']+r['td'])
    slope=model.nu*r['td']/(r['tn']+r['td'])*1e9*gp(r['z'],cost)/(sc.hi-sc.lo)/(1e18*(6+ETA_ATT*ctx)*r['N_B']+r['c'])
    return H,slope

def thresholds(model,C,ctx,cost,sc,grid=129):
    """Global secant extrema; endpoints use analytic derivative limits.

    lambda_on = inf_{u>0} [H(u)-H(0)]/u
    lambda_full = sup_{u<U} [H(U)-H(u)]/(U-u)
    Numerical grid + all detected local extrema refinement, not interval proof.
    """
    U=sc.cap
    h0,d0=profile(model,C,ctx,cost,sc,0.)
    h1,d1=profile(model,C,ctx,cost,sc,U)
    def onset(t):
        if t==0:return d0
        return (profile(model,C,ctx,cost,sc,t*U)[0]-h0)/(t*U)
    def full(t):
        if t==1:return d1
        return (h1-profile(model,C,ctx,cost,sc,t*U)[0])/((1-t)*U)
    ts=np.linspace(0,1,grid)
    def extreme(fun,sign):
        vals=np.array([sign*fun(t) for t in ts]);candidates=[(vals[0],0.),(vals[-1],1.)]
        for i in range(1,grid-1):
            if vals[i]<=vals[i-1] and vals[i]<=vals[i+1]:
                opt=minimize_scalar(lambda t:sign*fun(t),bounds=(ts[i-1],ts[i+1]),method='bounded',options={'xatol':1e-9})
                candidates.append((opt.fun,opt.x))
        value,t=min(candidates)
        return sign*value,t
    on,ton=extreme(onset,1);sat,tsat=extreme(full,-1)
    assert on>0 and sat>=on-1e-9
    return dict(C=C,L_ctx=ctx,cost=cost,keep=sc.keep,u_max=U,lambda_on=on,lambda_full=sat,
                onset_competitor_t=ton,full_competitor_t=tsat,local_lambda_on=d0,local_lambda_full=d1,
                sQ_on=model.theta/on,sQ_full=model.theta/sat,grid=grid)

def run(root,model,make_scenario,scan,main,contexts):
    out=Path(root)/'output_q3_resource';tab=out/'tables';figdir=out/'figures'
    def save(d,name):d.to_csv(tab/f'{name}.csv',index=False,encoding='utf-8-sig');return d
    def figsave(fig,name):
        fig.savefig(figdir/f'{name}.png',dpi=300,bbox_inches='tight')
        fig.savefig(figdir/f'{name}.pdf',bbox_inches='tight')
        root_fig=Path(root)/'figures';root_fig.mkdir(parents=True,exist_ok=True)
        target=root_fig/f'fig_{int(name[:2])+24:02d}_q3_{name[3:]}'
        fig.savefig(target.with_suffix('.png'),dpi=300,bbox_inches='tight')
        fig.savefig(target.with_suffix('.svg'),bbox_inches='tight')
        plt.close(fig)
    plt.rcParams.update({'pdf.fonttype':42,'axes.grid':True,'grid.alpha':.15,'legend.frameon':False})
    sc=make_scenario()
    selection=pd.read_csv(Path(root)/'Q3/quality_audit/within_domain_selection.csv')
    caps=pd.read_csv(Path(root)/'Q3/quality_audit/quality_cap_candidates.csv')
    save(selection,'screening_curve');save(caps,'screening_cap_curve')
    # Equal footing scenarios, not five estimates of a uniquely identified ceiling.
    results=[];tr=[]
    for keep in RATES:
        scenario=make_scenario(keep=keep)
        for C in [1e19,1e22,1e24]:
            for ctx in contexts:
                for cost in COSTS:
                    results.append(model.solve(C,ctx,cost,scenario,grid=129))
                    tr.append(thresholds(model,C,ctx,cost,scenario))
    results=save(pd.DataFrame(results),'cap_scenario_results')
    tr=save(pd.DataFrame(tr),'quality_benefit_thresholds')
    # Threshold curves use formal budget domain, with no extension to force transitions.
    curves=[]
    for cost in COSTS:
        for C in np.geomspace(1e19,1e24,61):
            curves.append(thresholds(model,float(C),2048,cost,sc))
    curves=save(pd.DataFrame(curves),'threshold_budget_curves')
    # Verify global decisions on both sides, in the intermediate region and at ties.
    checks=[]
    for row in tr.itertuples(index=False):
        scenario=make_scenario(keep=row.keep)
        for label,lam in [('below',row.lambda_on*.99),('above',row.lambda_full*1.01),
                          ('middle',(row.lambda_on+row.lambda_full)/2),
                          ('on_tie',row.lambda_on),('full_tie',row.lambda_full)]:
            r=model.solve(row.C,row.L_ctx,row.cost,replace(scenario,s_q=model.theta/lam),grid=257)
            h0,_=profile(model,row.C,row.L_ctx,row.cost,scenario,0)
            h1,_=profile(model,row.C,row.L_ctx,row.cost,scenario,scenario.cap)
            opt=np.log(r['reducible_loss'])-model.eta*scenario.h
            expected='R0' if label=='below' else 'R2' if label=='above' else 'R1' if label=='middle' and row.lambda_full-row.lambda_on>1e-7 else 'tie'
            if expected!='tie':assert r['state']==expected,(row,label,r['state'])
            gap=abs(opt-(h0 if label=='on_tie' else h1-lam*scenario.cap)) if label.endswith('tie') else 0.
            assert gap<2e-8
            checks.append(dict(C=row.C,L_ctx=row.L_ctx,cost=row.cost,keep=row.keep,probe=label,
                               lambda_value=lam,state=r['state'],t=r['t'],tie_log_objective_gap=gap))
    checks=save(pd.DataFrame(checks),'threshold_decision_checks')
    refinements=[]
    for row in tr.loc[tr.L_ctx.eq(2048)].itertuples(index=False):
        b=thresholds(model,row.C,row.L_ctx,row.cost,make_scenario(keep=row.keep),grid=513)
        err=max(abs(b[k]/getattr(row,k)-1) for k in ['lambda_on','lambda_full'])
        assert err<2e-6
        refinements.append(dict(C=row.C,cost=row.cost,keep=row.keep,relative_error=err))
    refinements=save(pd.DataFrame(refinements),'threshold_grid_checks')
    # Resource value: shadow price per proportional budget increment; no-quality equivalent compute.
    eps=model.alpha*model.nu/(model.alpha+model.nu)
    values=[]
    for row in scan.itertuples(index=False):
        factor=np.exp(-model.theta/sc.s_q*row.u+model.eta*sc.h)
        marginal_log_budget=model.nu*row.td*factor  # -dL*/dlog(C), away from branch switches
        equivalent=( (row.baseline_loss-model.E)/row.reducible_loss )**(1/eps)
        values.append(dict(C=row.C,L_ctx=row.L_ctx,cost=row.cost,
            shadow_price=marginal_log_budget/row.C,loss_drop_per_log_budget=marginal_log_budget,
            equivalent_compute_multiplier=equivalent,equivalent_no_quality_C=row.C*equivalent,
            share_quality=row.share_quality,C_quality=row.C_quality,
            N_change_pct=100*(row.N_B/row.baseline_N_B-1),D_change_pct=100*(row.D_B/row.baseline_D_B-1)))
    values=save(pd.DataFrame(values),'resource_value_analysis')
    valuechecks=[]
    for row in main.itertuples(index=False):
        a=model.solve(row.C*np.exp(-1e-4),row.L_ctx,row.cost,sc)
        b=model.solve(row.C*np.exp(1e-4),row.L_ctx,row.cost,sc)
        fd=-(b['loss']-a['loss'])/(2e-4)
        v=values.loc[values.L_ctx.eq(row.L_ctx)&values.cost.eq(row.cost)&np.isclose(values.C,row.C,rtol=1e-12)].iloc[0]
        rel=abs(fd/v.loss_drop_per_log_budget-1)
        eq=model.inner(v.equivalent_no_quality_C,row.L_ctx,row.cost,sc,0)['loss']
        assert rel<1e-6 and abs(eq-row.loss)<1e-10
        valuechecks.append(dict(C=row.C,L_ctx=row.L_ctx,cost=row.cost,shadow_relative_error=rel,equivalent_loss_error=abs(eq-row.loss)))
    valuechecks=save(pd.DataFrame(valuechecks),'resource_value_checks')
    # Screening evidence: no token supply inference from document/word retention.
    fig,axes=plt.subplots(1,3,figsize=(12,3.6),layout='constrained')
    for dom,d in selection.groupby('domain'):
        d=d.sort_values('requested_keep')
        axes[0].plot(100*d.requested_keep,d.gain,'o-',ms=3,label=dom)
        axes[1].plot(100*d.actual_doc_keep,100*d.word_keep,'o-',ms=3)
    axes[0].set(xlabel='域内高分文档保留率（%）',ylabel='原始质量均值增量',title='a  筛选越严，质量均值越高')
    axes[0].legend(fontsize=7,ncol=2)
    axes[1].plot([0,100],[0,100],'--',color='.5',lw=1)
    axes[1].set(xlabel='文档保留率（%）',ylabel='词数保留率（%，非Token）',title='b  质量提高伴随样本供给缩减')
    for recipe,d in caps.groupby('recipe'):
        d=d.sort_values('keep');axes[2].plot(100*d.keep,d.u_cap_candidate,'o-',label=recipe)
    axes[2].set(xlabel='域内高分文档保留率（%）',ylabel='情景上限 U',title='c  经既有域映射得到的上限组')
    axes[2].legend();figsave(fig,'07_screening_evidence')
    # Global boundaries give exact region definitions; phase fills are conditional, not confidence bands.
    fig,axes=plt.subplots(1,3,figsize=(12,4),layout='constrained')
    ymin=curves.lambda_on.min()*.55;ymax=max(model.theta*1.7,curves.lambda_full.max()*1.5)
    for ax,cost in zip(axes,COSTS):
        d=curves.loc[curves.cost.eq(cost)]
        ax.fill_between(d.C,ymin,d.lambda_on,color='#EEEEEE',label='R0 不提质')
        ax.fill_between(d.C,d.lambda_on,d.lambda_full,color='#B4D9E7',label='R1 内点')
        ax.fill_between(d.C,d.lambda_full,ymax,color='#D5E7D4',label='R2 达上限')
        ax.plot(d.C,d.lambda_on,color='#277DA1',lw=1.4,label='开始提质阈值')
        ax.plot(d.C,d.lambda_full,color='#39724C',ls='--',lw=1.4,label='达到上限阈值')
        ax.axhline(model.theta,color='#A64F38',ls=':',lw=1.5,label='s_Q=1 条件值')
        ax.set(xscale='log',yscale='log',ylim=(ymin,ymax),xlabel='预算（FLOPs）',ylabel='质量收益 λ（每单位原始Q）',title=COST_LABELS[cost])
    axes[0].legend(fontsize=7,loc='lower left');fig.suptitle('全局决策相位图｜p0，上下文2048，50%参照上限；边界处允许并列最优')
    figsave(fig,'08_global_decision_phase')
    # Cap sensitivity expressed in absolute quality and objective, not only normalized t=1.
    fig,axes=plt.subplots(1,3,figsize=(12,3.8),layout='constrained')
    for ax,C in zip(axes,[1e19,1e22,1e24]):
        for cost in COSTS:
            d=results.loc[results.C.eq(C)&results.L_ctx.eq(2048)&results.cost.eq(cost)].sort_values('u_max')
            ax.plot(d.u_max,d.loss_gain,'o-',label=COST_LABELS[cost],color=COLORS[cost])
        ax.axvline(sc.cap,color='.5',ls=':',label='50%参照')
        ax.set(xlabel='质量情景上限 U（原始Q单位）',ylabel='相对无提质基线的预测Loss下降',title=f'预算 {C:.0e} FLOPs')
    axes[0].legend(fontsize=8);figsave(fig,'09_cap_sensitivity')
    fig,axes=plt.subplots(2,2,figsize=(10,7),layout='constrained')
    for cost in COSTS:
        d=values.loc[values.L_ctx.eq(2048)&values.cost.eq(cost)]
        for ax,col,label in zip(axes.flat,['N_change_pct','D_change_pct','equivalent_compute_multiplier','loss_drop_per_log_budget'],
                                ['参数量相对无提质配置变化（%）','Token量相对无提质配置变化（%）','无提质等效算力 / 当前预算','影子价值 −dL*/d ln C']):
            ax.plot(d.C,d[col],label=COST_LABELS[cost],color=COLORS[cost]);ax.set(xscale='log',xlabel='预算（FLOPs）',ylabel=label)
    axes[0,0].legend();fig.suptitle('提质的机会成本与收益｜p0，s_Q=1，50%参照，上下文2048')
    figsave(fig,'10_resource_tradeoffs')
    # Ternary trajectories distinguish contexts; same-context train:attention is structurally fixed.
    fig,axes=plt.subplots(1,3,figsize=(12,4),layout='constrained')
    triangle=np.array([[0,0],[1,0],[.5,np.sqrt(3)/2],[0,0]])
    for ax,cost in zip(axes,COSTS):
        ax.plot(triangle[:,0],triangle[:,1],color='.55',lw=1)
        for ctx in contexts:
            d=scan.loc[scan.cost.eq(cost)&scan.L_ctx.eq(ctx)].sort_values('C')
            x=d.share_att+.5*d.share_quality;y=np.sqrt(3)/2*d.share_quality
            line,=ax.plot(x,y,lw=1.5,label=str(ctx))
            ax.scatter(x.iloc[0],y.iloc[0],marker='o',s=22,color=line.get_color())
            ax.scatter(x.iloc[-1],y.iloc[-1],marker='^',s=22,color=line.get_color())
        ax.text(0,-.04,'基础训练',ha='center');ax.text(1,-.04,'注意力',ha='center');ax.text(.5,.91,'提质',ha='center')
        ax.set(title=COST_LABELS[cost],aspect='equal',xlim=(-.1,1.1),ylim=(-.08,.96));ax.axis('off')
    axes[0].legend(title='上下文',fontsize=7,loc='upper left')
    fig.suptitle('预算份额三元图｜圆点 10¹⁹ → 三角 10²⁴ FLOPs；同一窗口轨迹受固定注意力/训练比约束')
    figsave(fig,'11_budget_composition')
    # Targeted critical-region zoom: normalized benefit resolves thin intermediate regions.
    phase=[]
    fig,axes=plt.subplots(1,3,figsize=(12,3.7),layout='constrained')
    for ax,cost in zip(axes,COSTS):
        row=tr.loc[tr.keep.eq(.5)&tr.C.eq(1e19)&tr.L_ctx.eq(2048)&tr.cost.eq(cost)].iloc[0]
        ratios=np.linspace(.85,max(1.2,row.lambda_full/row.lambda_on*1.1),101)
        for ratio in ratios:
            lam=ratio*row.lambda_on
            r=model.solve(1e19,2048,cost,replace(sc,s_q=model.theta/lam),grid=129)
            phase.append(dict(C=1e19,L_ctx=2048,cost=cost,lambda_value=lam,lambda_over_on=ratio,t=r['t'],state=r['state']))
        d=pd.DataFrame(phase);d=d.loc[d.cost.eq(cost)]
        ax.plot(d.lambda_over_on,d.t,color=COLORS[cost],lw=2)
        ax.axvline(1,color='.4',ls=':');ax.axvline(row.lambda_full/row.lambda_on,color='.4',ls='--')
        ax.set(xlabel='质量收益 / 开始提质阈值',ylabel='最优质量投入 u/U',title=COST_LABELS[cost],ylim=(-.04,1.04))
    fig.suptitle('临界收益附近的策略变化｜预算10¹⁹，上下文2048，50%参照')
    figsave(fig,'12_critical_benefit_zoom');save(pd.DataFrame(phase),'critical_benefit_zoom')
    status=dict(status='passed',cap_scenario_rows=len(results),threshold_rows=len(tr),decision_checks=len(checks),
        max_threshold_grid_relative_error=float(refinements.relative_error.max()),max_tie_log_objective_gap=float(checks.tie_log_objective_gap.max()),
        max_shadow_relative_error=float(valuechecks.shadow_relative_error.max()),max_equivalent_loss_error=float(valuechecks.equivalent_loss_error.max()),
        max_budget_relative_error=float(results.budget_relative_error.max()),
        limits='Sample-supported quality scenarios, no token supply guarantee; lambda is conditional, no new training validation.')
    assert status['max_budget_relative_error']<1e-12
    (out/'decision_verification.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    return results,tr,values,status

"""No external observations. Structural mediation, quantile frontiers and Q1-3 coupling.

The maintained causal assumptions are explicit in the accompanying model chapter.
Noise is estimated from residuals; observed scores are never perturbed in place.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.special import expit, logit
from scipy import sparse
from sklearn.isotonic import IsotonicRegression
from data_pipeline import ROOT, OUT, CD, DIMS, save, dump

SEED=20260925
REPS=400
REFERENCE=pd.Timestamp('2023-01-01')
PAR=json.loads((ROOT/'output_q2_shared/q2_interface.json').read_text(encoding='utf-8'))['B1']

def zscore(s): return logit(np.clip(np.asarray(s,dtype=float)/100, .001, .999))
def score(z): return 100*expit(z)
def scale_index(m):
    m=np.asarray(m)
    return -np.logaddexp(np.log(PAR['A'])-PAR['alpha']*m[...,0],
                         np.log(PAR['B'])-PAR['nu']*m[...,1])

def ols(X,y):
    return np.linalg.lstsq(X,y,rcond=None)[0]

def qreg(X,y,q=.9,positive=()):
    n,p=X.shape
    eq=sparse.hstack([sparse.csr_matrix(X),sparse.eye(n),-sparse.eye(n)],format='csr')
    bounds=[(0,None) if i in positive else (None,None) for i in range(p)]+[(0,None)]*(2*n)
    r=linprog(np.r_[np.zeros(p),np.full(n,q),np.full(n,1-q)],
        A_eq=eq,b_eq=y,bounds=bounds,method='highs')
    if not r.success:raise RuntimeError(r.message)
    return r.x[:p]

def cluster_sample(d,rng,col='org'):
    groups=d[col].unique()
    return pd.concat([d[d[col].eq(x)] for x in rng.choice(groups,len(groups),replace=True)],ignore_index=True)

def fit_structural(d,kind='scale_time',quantile=None):
    t=d.t.to_numpy();m=d[['lnN','lnD']].to_numpy();x=scale_index(m)
    names={'scale_time':['intercept','scale_index','time_year'],
           'scale_only':['intercept','scale_index'],'time_only':['intercept','time_year'],
           'free_nd':['intercept','lnN','lnD','time_year']}[kind]
    X={'scale_time':np.c_[np.ones(len(d)),x,t], 'scale_only':np.c_[np.ones(len(d)),x],
       'time_only':np.c_[np.ones(len(d)),t], 'free_nd':np.c_[np.ones(len(d)),m,t]}[kind]
    y=zscore(d.S);b=ols(X,y) if quantile is None else qreg(X,y,quantile,positive=(1,) if kind=='scale_time' else ())
    return dict(b=b,resid=y-X@b,names=names,kind=kind,condition=float(np.linalg.cond(X)),rank=int(np.linalg.matrix_rank(X)))

def predict_structural(f,d):
    x=scale_index(d[['lnN','lnD']].to_numpy());t=d.t.to_numpy();one=np.ones(len(d))
    X={'scale_time':np.c_[one,x,t],'scale_only':np.c_[one,x],
       'time_only':np.c_[one,t],'free_nd':np.c_[one,d[['lnN','lnD']],t]}[f['kind']]
    # Integrate empirical outcome noise on the score scale (Jensen correction).
    return score((X@f['b'])[:,None]+f['resid'][None,:]).mean(axis=1)

def fit_mediators(d):
    X=np.c_[np.ones(len(d)),d.t]
    m=d[['lnN','lnD']].to_numpy();a=ols(X,m)
    return a,m-X@a

def decompose(d,t0,t1,kind='scale_time',coeff=None):
    a,em=fit_mediators(d);f=fit_structural(d,kind)
    if coeff is not None:f['b']=np.asarray(coeff)
    def g(t,tm):
        m=np.array([1,tm])@a+em
        if kind=='scale_time':z=f['b'][0]+f['b'][1]*scale_index(m)+f['b'][2]*t
        else:z=f['b'][0]+m@f['b'][1:3]+f['b'][3]*t
        return float(score(z[:,None]+f['resid'][None,:]).mean())
    g00,g01,g10,g11=g(t0,t0),g(t0,t1),g(t1,t0),g(t1,t1)
    indirect=.5*((g01-g00)+(g11-g10))
    direct=.5*((g10-g00)+(g11-g01));total=g11-g00
    return dict(start_score=g00,end_score=g11,scale_points=indirect,technology_points=direct,
        total_points=total,scale_share=indirect/total if abs(total)>1e-6 else np.nan,
        technology_share=direct/total if abs(total)>1e-6 else np.nan,
        additivity_error=abs(indirect+direct-total))

def mediation_analysis(nd):
    # Fixed within-support interquartile date contrast, unchanged in all bootstrap draws.
    t0,t1=np.quantile(nd.t,[.25,.75]);f=fit_structural(nd);a,em=fit_mediators(nd)
    rows=[];boots=[];rng=np.random.default_rng(SEED)
    for k in ['scale_time','free_nd']:
        r=decompose(nd,t0,t1,k);rows.append(dict(method=k,**r))
    for b in range(REPS):
        d=cluster_sample(nd,rng)
        if d.t.nunique()<2:continue
        r=decompose(d,t0,t1);r['replicate']=b;boots.append(r)
    boot=pd.DataFrame(boots);save(boot,'mediation_bootstrap')
    result=pd.DataFrame(rows)
    for name in ['scale_points','technology_points','total_points','scale_share','technology_share']:
        result.loc[0,name+'_lo'],result.loc[0,name+'_hi']=boot[name].quantile([.025,.975])
    save(result,'mediation_contributions')
    coef=[]
    for j,name in enumerate(f['names']):coef.append(dict(equation='outcome_logit',term=name,value=f['b'][j]))
    for j,target in enumerate(['lnN','lnD']):
        for i,name in enumerate(['intercept','time_year']):coef.append(dict(equation=target,term=name,value=a[i,j]))
    save(pd.DataFrame(coef),'mediation_coefficients')
    dump(dict(outcome_sd=float(np.std(f['resid'],ddof=3)),mediator_covariance=np.cov(em,rowvar=False).tolist(),
        residual_cross_equation_independence='identifying assumption, not an empirical discovery',
        outcome_residuals=f['resid'].tolist(),mediator_residuals=em.tolist()),'noise_model')
    # Sensitivity in the reduced scale-index/outcome equations. rho is assumed residual correlation.
    x=scale_index(nd[['lnN','lnD']]);T=np.c_[np.ones(len(nd)),nd.t]
    ax=ols(T,x);ex=x-T@ax;sx=np.std(ex,ddof=2);sy=np.std(f['resid'],ddof=3)
    sens=[]
    for rho in np.linspace(-.6,.6,13):
        b=f['b'].copy();bias=rho/np.sqrt(1-rho*rho)*sy/sx
        b[1]-=bias;b[0]+=bias*ax[0];b[2]+=bias*ax[1]
        sens.append(dict(rho=rho,scale_coefficient=b[1],time_coefficient=b[2],
                         **decompose(nd,t0,t1,coeff=b)))
    save(pd.DataFrame(sens),'confounding_sensitivity')
    # Common versus time-varying D measurement uncertainty (reported metadata can be estimated).
    ds=[]
    for factor in [.5,1.,2.]:
        for pattern in ['uniform','later_models_only']:
            d=nd.copy();mask=np.ones(len(d),bool) if pattern=='uniform' else (d.t>d.t.median())
            d.loc[mask,'lnD']+=np.log(factor)
            ds.append(dict(D_factor=factor,pattern=pattern,**decompose(d,t0,t1)))
    save(pd.DataFrame(ds),'data_volume_sensitivity')
    # Independent leave-organization-out and blocked release-time validation.
    predictions=[];qchecks=[]
    splits=[]
    for org in nd.org.unique():splits.append(('leave_organization',org,nd.org.ne(org),nd.org.eq(org)))
    for cut in ['2023-07-01','2024-01-01','2024-04-01','2024-07-01']:
        before=nd.publication_date<pd.Timestamp(cut)
        splits.append(('publication_holdout',cut,before,~before))
    for design,label,trmask,temask in splits:
        tr,te=nd[trmask],nd[temask]
        if len(tr)<10 or len(te)<(1 if design=='leave_organization' else 2):continue
        for kind in ['scale_time','scale_only','time_only','free_nd']:
            fit=fit_structural(tr,kind);pr=predict_structural(fit,te)
            for (_,v),s in zip(te.iterrows(),pr):
                predictions.append(dict(design=design,fold=label,method=kind,Model=v.Model,
                    train_n=len(tr),actual=v.S,prediction=s,error=s-v.S,
                    max_train_date=str(tr.publication_date.max().date())))
        fq=fit_structural(tr,quantile=.9)
        xp=scale_index(te[['lnN','lnD']]);zp=np.c_[np.ones(len(te)),xp,te.t]@fq['b']
        for (_,v),z in zip(te.iterrows(),zp):
            err=float(zscore(v.S)-z)
            qchecks.append(dict(design=design,fold=label,Model=v.Model,actual=v.S,
                prediction=float(score(z)),covered=float(v.S<=score(z)),
                pinball_logit=max(.9*err,-.1*err)))
    pred=pd.DataFrame(predictions);save(pred,'structural_validation_predictions')
    metrics=pred.groupby(['design','method']).error.agg(n='size',MAE=lambda x:x.abs().mean(),
                               RMSE=lambda x:np.sqrt(np.mean(x*x)),bias='mean').reset_index()
    save(metrics,'structural_validation_metrics')
    qq=pd.DataFrame(qchecks);save(qq,'structural_quantile_validation')
    save(qq.groupby('design').agg(n=('Model','size'),coverage=('covered','mean'),
          pinball_logit=('pinball_logit','mean')).reset_index(),'structural_quantile_metrics')
    meta=dict(n=len(nd),organizations=int(nd.org.nunique()),t0=float(t0),t1=float(t1),
       start_date=str((REFERENCE+pd.Timedelta(days=t0*365.25).round('s')).date()),
       end_date=str((REFERENCE+pd.Timedelta(days=t1*365.25).round('s')).date()),
       comparison='publication-time interquartile contrast in matched pretrained models',
       bootstrap_replicates=len(boot),bootstrap_unit='publisher organization',
       condition_number=f['condition'],design_rank=f['rank'],
       assumptions=['Residual time effect represents non-scale technical progress, conditional on comparable scale and evaluation.',
       'No remaining time-scale-score confounding; scale and outcome disturbances are independent in the primary model.',
       'The Q2 exponents and scale-shape transfer across model families; coefficients are reestimated on C1-C4.',
       'Metadata availability/leaderboard inclusion do not distort the target contrast after sample restrictions.'])
    dump(meta,'mediation_design');return result,metrics

def bridge_analysis():
    b=pd.read_csv(CD/'loss_benchmark_bridge_expanded.csv');b['tier']=np.where(b.Loss_Comparability.str.startswith('High'),'high','medium')
    rows=[];models={};fitrows=[]
    for tier,d in b.groupby('tier'):
        m=IsotonicRegression(increasing=False,out_of_bounds='nan').fit(d.Val_Loss,d.LB_Average);models[tier]=m
        for x,y in zip(m.X_thresholds_,m.y_thresholds_):fitrows.append(dict(tier=tier,loss=x,score=y))
        for ix,r in d.iterrows():
            tr=d.drop(index=ix);iso=IsotonicRegression(increasing=False,out_of_bounds='nan').fit(tr.Val_Loss,tr.LB_Average)
            p=float(iso.predict([r.Val_Loss])[0]);supported=bool(tr.Val_Loss.min()<=r.Val_Loss<=tr.Val_Loss.max())
            rows.append(dict(tier=tier,Model=r.Model,actual=r.LB_Average,prediction=p,
              error=p-r.LB_Average,supported=supported,Loss_Source=r.Loss_Source))
    loo=pd.DataFrame(rows);save(loo,'bridge_loo');save(pd.DataFrame(fitrows),'bridge_knots')
    metrics=loo.groupby('tier').agg(n=('Model','size'),validated_n=('error','count'),
        MAE=('error',lambda x:x.abs().mean()),RMSE=('error',lambda x:np.sqrt(np.mean(x.dropna()**2)))).reset_index()
    save(metrics,'bridge_metrics');save(b,'bridge_evidence')
    c5=pd.read_csv(CD/'loss_benchmark_bridge.csv')
    c56=c5.merge(b,on='Model',suffixes=('_c5','_c6'))
    save(pd.DataFrame([dict(common_models=len(c56),
          max_loss_difference=float((c56.Val_Loss_c5-c56.Val_Loss_c6).abs().max()),
          max_score_difference=float((c56.LB_Average_c5-c56.LB_Average_c6).abs().max()))]),'c5_c6_consistency')
    # Correlated report-level folds avoid pretending repeated loss assignments are independent.
    groups=[]
    for tier,d in b.groupby('tier'):
        if d.Loss_Source.nunique()<2:continue
        for source in d.Loss_Source.unique():
            tr=d[d.Loss_Source.ne(source)];te=d[d.Loss_Source.eq(source)]
            iso=IsotonicRegression(increasing=False,out_of_bounds='nan').fit(tr.Val_Loss,tr.LB_Average)
            for (_,r),p in zip(te.iterrows(),iso.predict(te.Val_Loss)):
                groups.append(dict(tier=tier,source=source,Model=r.Model,actual=r.LB_Average,
                                   prediction=p,error=p-r.LB_Average))
    save(pd.DataFrame(groups),'bridge_leave_report_out')
    return b,models,metrics

def compute_history(epoch,cutoff):
    # Dense, newly trained language models only; posttraining compute is not pretraining compute.
    d=epoch[epoch.open&epoch.language&epoch.pub.notna()&(epoch.C>0)&epoch.pub.le(cutoff)
            &epoch.pub.ge(pd.Timestamp('2022-01-01'))&epoch['Base model'].isna()].copy()
    d=d[~d['Parameters notes'].fillna('').str.contains('active|moe|expert',case=False)]
    d=d[d.Task.fillna('').str.contains('Language modeling|Code generation|Chat',case=False)]
    d=d[~d.Confidence.fillna('').str.contains('Speculative',case=False)]
    d['compute_cluster']=d.Organization.fillna(d.Model)
    d['quarter']=d.pub.dt.to_period('Q').dt.start_time
    q=d.groupby('quarter').agg(C=('C',lambda x:x.quantile(.9)),n=('C','size')).reset_index()
    q['t']=(q.quarter-pd.Timestamp('2022-01-01')).dt.days/365.25
    bb=ols(np.c_[np.ones(len(q)),q.t],np.log(q.C))
    tail=d[d.pub>=cutoff-pd.DateOffset(years=1)]
    c0=float(tail.C.quantile(.9));growth=float(bb[1])
    return d,q,c0,growth

def coupled_forecast(nd,epoch,cutoff,bridge_models):
    sys.path.insert(0,str(ROOT/'Q3'))
    from resource_model import ResourceModel,Scenario
    cfg=json.loads((ROOT/'output_q3_resource/config.json').read_text(encoding='utf-8'))
    mdl=ResourceModel(dict(B1=cfg['parameters'],theta_Q=cfg['theta_Q'],eta=cfg['eta_p']))
    sc=Scenario(**cfg['scenarios']['main'])
    d,q,c0,growth=compute_history(epoch,cutoff)
    save(d[['Model','pub','C','D','N_epoch','Confidence','Training compute notes']],'c4_compute_sample');save(q,'c4_quarter_compute')
    ff=fit_structural(nd,quantile=.9);tbase=(cutoff-REFERENCE).days/365.25
    base=mdl.solve(c0,4096,'exponential',sc)
    # Fit is in base-scale-index units; quality gain is NOT added again to its calibrated intercept.
    x0=scale_index([np.log(base['N_B']),np.log(base['D_B'])])
    z0=float(ff['b']@[1,x0,tbase])
    rr=[];resources=[];rng=np.random.default_rng(SEED+1);draw=[]
    for rep in range(REPS):
        s=cluster_sample(nd,rng);f=fit_structural(s,quantile=.9)
        es=cluster_sample(d,rng,col='compute_cluster')
        qq=es.groupby('quarter').agg(C=('C',lambda x:x.quantile(.9))).reset_index()
        tt=(qq.quarter-pd.Timestamp('2022-01-01')).dt.days/365.25
        gb=ols(np.c_[np.ones(len(qq)),tt],np.log(qq.C))[1]
        tail=es[es.pub>=cutoff-pd.DateOffset(years=1)]
        cb=float(tail.C.quantile(.9)) if len(tail) else c0
        draw.append((f['b'],cb,max(0.,float(gb))))
    for rate,label in [(0.,'compute_frozen'),(.25,'quarter_historical_growth'),(.5,'half_historical_growth')]:
        for h in [0,12,24]:
            dt=h/12;C=c0*np.exp(max(0.,growth)*rate*dt)
            r=mdl.solve(C,4096,'exponential',sc);resources.append(dict(scenario=label,horizon_months=h,**r))
            scale_gain=-ff['b'][1]*np.log(r['reducible_loss']/base['reducible_loss'])
            for half in [12,24,np.inf]:
                decay=0. if np.isinf(half) else np.log(2)/(half/12)
                effective=dt if decay==0 else -np.expm1(-decay*dt)/decay
                z=z0+scale_gain+ff['b'][2]*effective
                preds=[]
                # Fast fixed-cap inner solve, independently checked below against the full solver.
                # A and exponents are conditional on Q2; structural sensitivity is separate.
                for bb,cb,gb in draw:
                    r0=mdl.inner(cb,4096,'exponential',sc,sc.cap)
                    rh=mdl.inner(cb*np.exp(gb*rate*dt),4096,'exponential',sc,sc.cap)
                    xb=scale_index([np.log(r0['N_B']),np.log(r0['D_B'])])
                    zb=bb@[1,xb,tbase]-bb[1]*np.log(rh['reducible_loss']/r0['reducible_loss'])+bb[2]*effective
                    preds.append(float(score(zb)))
                lower,upper=np.quantile(preds,[.025,.975])
                rr.append(dict(scenario=label,horizon_months=h,target_date=str((cutoff+pd.DateOffset(months=h)).date()),
                    technical_half_life_months=half,forecast=float(score(z)),lo=lower,hi=upper,
                    compute_budget=C,loss=r['loss'],scale_logit_gain=scale_gain,
                    technology_logit_gain=ff['b'][2]*effective,N_B=r['N_B'],D_B=r['D_B'],
                    N_extrapolated=bool(r['N_B']>nd.N.max() or r['N_B']<nd.N.min()),
                    D_extrapolated=bool(r['D_B']>nd.D.max() or r['D_B']<nd.D.min()),
                    past_last_matched_release_years=tbase-float(nd.t.max()),
                    interval='95% organization+metadata bootstrap, conditional on Q2 and extrapolation assumptions'))
    forecasts=pd.DataFrame(rr);save(forecasts,'coupled_frontier_forecast');save(pd.DataFrame(resources),'q3_future_resources')
    # Every bootstrap resource call assumes cap is active; independently verify throughout its range.
    budgets=np.array([v[1]*np.exp(v[2]) for v in draw]+[v[1] for v in draw])
    capcheck=[]
    for C in np.geomspace(budgets.min(),budgets.max(),15):
        exact=mdl.solve(float(C),4096,'exponential',sc);fixed=mdl.inner(float(C),4096,'exponential',sc,sc.cap)
        capcheck.append(dict(C=C,state=exact['state'],relative_loss_error=abs(exact['loss']-fixed['loss'])/exact['loss']))
    save(pd.DataFrame(capcheck),'bootstrap_resource_shortcut_check')
    assert max(v['relative_loss_error'] for v in capcheck)<1e-8,'Bootstrap quality-cap shortcut invalid'
    # Absolute C6 bridges are tier-specific and explicitly refuse out-of-support predictions.
    br=[];b=pd.read_csv(OUT/'tables/bridge_evidence.csv');rng=np.random.default_rng(SEED+3)
    for r in resources:
        for tier,iso in bridge_models.items():
            bb=b[b.tier.eq(tier)];L=r['loss'];pred=float(iso.predict([L])[0]);samples=[]
            for rep in range(REPS):
                sources=bb.Loss_Source.unique()
                if len(sources)>1:
                    tr=pd.concat([bb[bb.Loss_Source.eq(s)] for s in rng.choice(sources,len(sources),replace=True)])
                else:tr=bb.iloc[rng.integers(0,len(bb),len(bb))]
                mm=IsotonicRegression(increasing=False,out_of_bounds='nan').fit(tr.Val_Loss,tr.LB_Average)
                pp=float(mm.predict([L])[0])
                if np.isfinite(pp):samples.append(pp)
            lo,hi=np.quantile(samples,[.025,.975]) if samples else (np.nan,np.nan)
            br.append(dict(scenario=r['scenario'],horizon_months=r['horizon_months'],tier=tier,loss=L,
              prediction=pred,lo=lo,hi=hi,support_low=bb.Val_Loss.min(),support_high=bb.Val_Loss.max(),
              supported=bool(np.isfinite(pred)),bootstrap_supported=len(samples),
              interpretation='absolute cross-report scenario only' if tier=='medium' else 'same-validation-set bridge'))
    save(pd.DataFrame(br),'q3_absolute_bridge_forecast')
    # Explicit Q3 quality/cost scenarios propagate structural uncertainty, without adding time gains twice.
    sens=[]
    for name,ss in cfg['scenarios'].items():
        s=Scenario(**ss)
        for cost in ['exponential','power','logarithmic']:
            for h in [0,12,24]:
                C=c0*np.exp(max(0.,growth)*.25*h/12);r=mdl.solve(C,4096,cost,s)
                sens.append(dict(quality_scenario=name,horizon_months=h,**r))
    save(pd.DataFrame(sens),'q3_cost_quality_sensitivity')
    meta=dict(cutoff=str(cutoff.date()),compute_sample=len(d),C0=c0,historical_log_compute_growth_per_year=growth,
        main_growth_fraction=.25,main_technical_half_life_months=24,quantile=.9,
        target='pretrained conditional q90 capability along Q3 loss-optimal resource frontier',
        coefficient=ff['b'].tolist(),x0=float(x0),anchor_score=float(score(z0)),
        issue='Forecast dates originate at last C1 observation, not the current wall-clock date.',
        no_double_count='Q3 quality/recipe held fixed across time; only relative loss gain enters. Time drift is not added to absolute C6 bridges.',
        conditional_interval='Does not include unidentified Q2 structural bias or model-family transfer error.')
    dump(meta,'forecast_design');return forecasts

def fit_broad(d):
    # Diagnostic model; absent training D means time coefficient is not pure non-scale progress.
    t=(d.date-pd.Timestamp('2024-06-01')).dt.days.to_numpy()/365.25
    n=np.log(d.N.to_numpy());X=np.c_[np.ones(len(d)),n,t]
    return qreg(X,zscore(d.S),.9,positive=(1,))

def broad_distribution_model(d,cut):
    b=fit_broad(d)
    t=(d.date-pd.Timestamp('2024-06-01')).dt.days.to_numpy()/365.25
    residual=zscore(d.S)-np.c_[np.ones(len(d)),np.log(d.N),t]@b
    recent=d[d.date>=cut-pd.DateOffset(months=3)]
    if len(recent)==0:recent=d
    # Deterministic midpoint quadrature for the reference-size and empirical noise distributions.
    nq=np.quantile(np.log(recent.N),(np.arange(101)+.5)/101)
    eq=np.quantile(residual,(np.arange(101)+.5)/101)
    return b,nq,eq

def broad_distribution_predict(f,cut,h,compute_growth,rate=.25,half=24):
    b,nq,eq=f;t=(cut-pd.Timestamp('2024-06-01')).days/365.25
    dt=h/12;decay=np.log(2)/(half/12)
    teff=-np.expm1(-decay*dt)/decay
    growth=max(0.,compute_growth)*rate*dt*PAR['nu']/(PAR['alpha']+PAR['nu'])
    z=b[0]+b[1]*(nq[:,None]+growth)+b[2]*(t+teff)+eq[None,:]
    return float(np.quantile(score(z),.9)),float(np.exp(np.quantile(nq,.9)+growth))

def broad_prediction(train,h,compute_growth,rate=.25,half=24,reference_cutoff=None):
    cut=train.date.max() if reference_cutoff is None else reference_cutoff
    f=broad_distribution_model(train,cut)
    p,n=broad_distribution_predict(f,cut,h,compute_growth,rate,half)
    return p,n,f[0]

def broad_analysis(clean,epoch):
    rows=[];metrics=[];forecasts=[];rng=np.random.default_rng(SEED+4)
    cutoff=clean.date.max();_,_,_,g=compute_history(epoch,cutoff)
    for typ in ['pretrained','chat_finetuned','merge']:
        d=clean[clean.type.eq(typ)].copy()
        if len(d)<30:continue
        for cut in pd.date_range('2024-10-01','2025-01-01',freq='MS'):
            end=cut+pd.offsets.MonthEnd(0);tr=d[d.date<=end]
            if len(tr)<30:continue
            _,_,_,gg=compute_history(epoch,end)
            for h in [1,2,3]:
                start=cut+pd.DateOffset(months=h);te=d[d.month.eq(start)]
                if len(te)<5:continue
                pred,_,_=broad_prediction(tr,h,gg,reference_cutoff=end)
                actual=float(te.S.quantile(.9))
                recent=tr[tr.month.eq(tr.month.max())]
                naive=float(recent.S.quantile(.9))
                for method,p in [('quantile_N_time',pred),('last_month_q90',naive)]:
                    rows.append(dict(type=typ,cutoff=str(end.date()),target_month=str(start.date()),horizon_months=h,
                       method=method,actual=actual,prediction=p,error=p-actual,train_n=len(tr),test_n=len(te)))
        boot_models=[broad_distribution_model(cluster_sample(d,rng),cutoff) for _ in range(REPS)]
        for h in [12,24]:
            for rate,label in [(0,'compute_frozen'),(.25,'quarter_historical_growth'),(.5,'half_historical_growth')]:
                p,n,b=broad_prediction(d,h,g,rate,reference_cutoff=cutoff);pp=[]
                for f in boot_models:
                    pp.append(broad_distribution_predict(f,cutoff,h,g,rate)[0])
                lo,hi=np.quantile(pp,[.025,.975])
                forecasts.append(dict(type=typ,scenario=label,horizon_months=h,
                    target_date=str((cutoff+pd.DateOffset(months=h)).date()),forecast=p,lo=lo,hi=hi,N_B=n,
                    N_extrapolated=bool(n>d.N.max()),n=len(d),coefficient_N=b[1],coefficient_time=b[2],
                    causal_status='descriptive N-only marginal q90; residual time includes omitted D; not the ND contribution estimator'))
    res=pd.DataFrame(rows);save(res,'broad_rolling_backtest')
    agg=res.groupby(['type','method']).error.agg(n='size',MAE=lambda x:x.abs().mean(),RMSE=lambda x:np.sqrt(np.mean(x*x))).reset_index()
    save(agg,'broad_backtest_metrics');save(pd.DataFrame(forecasts),'broad_frontier_forecast')
    # Weight sensitivity uses the same screened rows and fits; no outcome-based sample pruning.
    ww=[]
    for typ,d in clean[clean.type.isin(['pretrained','chat_finetuned'])].groupby('type'):
        for omit in [None]+DIMS:
            s=d.copy();dims=DIMS if omit is None else [v for v in DIMS if v!=omit]
            s['S']=s[dims].mean(axis=1)
            p,n,b=broad_prediction(s,12,g)
            ww.append(dict(type=typ,omitted_task=omit or 'none',forecast_12m=p,time_slope=b[2],N_slope=b[1]))
    save(pd.DataFrame(ww),'task_weight_sensitivity')
    return pd.DataFrame(forecasts),agg

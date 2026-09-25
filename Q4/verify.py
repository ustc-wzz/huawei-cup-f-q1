"""Independent numerical and evidence-boundary checks; not proof of causal identification."""
import hashlib,json
import numpy as np
import pandas as pd
from scipy.special import expit
from data_pipeline import ROOT,OUT,key,dump
from evolution_model import scale_index,decompose,fit_structural,PAR

def run():
    def read(n):return pd.read_csv(OUT/'tables'/f'{n}.csv')
    nd=read('nd_primary_sample');design=json.loads((OUT/'mediation_design.json').read_text(encoding='utf-8'))
    t0,t1=design['t0'],design['t1'];f=fit_structural(nd);checks={}
    checks['decimal_model_names_distinct']=key('facebook/opt-1.3b')!=key('OPT-13B')
    checks['unique_primary_models']=not nd.Model.duplicated().any()
    checks['primary_all_pretrained']=bool(nd.type.eq('pretrained').all())
    checks['primary_no_D_imputation']=bool((nd.D>0).all() and nd.D.notna().all())
    main=decompose(nd,t0,t1);same=decompose(nd,t0,t0);rev=decompose(nd,t1,t0)
    checks['decomposition_additive']=main['additivity_error']<1e-12
    checks['equal_time_zero_effects']=abs(same['total_points'])+abs(same['scale_points'])+abs(same['technology_points'])<1e-12
    checks['reverse_time_negates_effects']=all(abs(main[k]+rev[k])<1e-10 for k in ['scale_points','technology_points','total_points'])
    b=f['b'].copy();b[1]=0;no_scale=decompose(nd,t0,t1,coeff=b)
    b=f['b'].copy();b[2]=0;no_time=decompose(nd,t0,t1,coeff=b)
    checks['zero_scale_coefficient_zero_indirect']=abs(no_scale['scale_points'])<1e-12
    checks['zero_time_coefficient_zero_direct']=abs(no_time['technology_points'])<1e-12
    # Check derived scale elasticities against central differences at every observed ND pair.
    m=nd[['lnN','lnD']].to_numpy();N=np.exp(m[:,0]);D=np.exp(m[:,1]);eps=1e-5
    den=PAR['A']*N**(-PAR['alpha'])+PAR['B']*D**(-PAR['nu'])
    maxerr=0.
    for j in [0,1]:
        p=m.copy();q=m.copy();p[:,j]+=eps;q[:,j]-=eps
        num=(scale_index(p)-scale_index(q))/(2*eps)
        ana=(PAR['alpha']*PAR['A']*N**(-PAR['alpha']) if j==0 else PAR['nu']*PAR['B']*D**(-PAR['nu']))/den
        maxerr=max(maxerr,float(abs(num-ana).max()))
    checks['scale_elasticities_match_finite_difference']=maxerr<1e-8
    r=read('q3_future_resources')
    budget=abs(r.C_train+r.C_att+r.C_quality-r.C)/r.C
    checks['q3_budget_feasible']=bool((budget<1e-8).all())
    checks['q3_quality_cap_shortcut_verified']=bool((read('bootstrap_resource_shortcut_check').relative_loss_error<1e-8).all())
    p=read('coupled_frontier_forecast')
    checks['forecast_score_bounds']=bool(p.forecast.between(0,100).all() and p.lo.between(0,100).all() and p.hi.between(0,100).all())
    checks['forecast_interval_ordered']=bool((p.lo<=p.hi).all())
    checks['frozen_compute_zero_scale_gain']=bool((p.loc[p.scenario.eq('compute_frozen'),'scale_logit_gain'].abs()<1e-12).all())
    cut=pd.Timestamp(json.loads((OUT/'forecast_design.json').read_text(encoding='utf-8'))['cutoff'])
    checks['future_dates_from_last_C1_observation']=all(pd.Timestamp(row.target_date)==cut+pd.DateOffset(months=int(row.horizon_months)) for _,row in p.iterrows())
    comp=read('c4_compute_sample');checks['no_future_C4_publication']=bool((pd.to_datetime(comp.pub)<=cut).all())
    br=read('q3_absolute_bridge_forecast')
    checks['unsupported_bridges_return_missing']=bool(br.loc[~br.supported,'prediction'].isna().all())
    knots=read('bridge_knots');checks['bridges_monotone']=all((g.sort_values('loss').score.diff().dropna()<=1e-12).all() for _,g in knots.groupby('tier'))
    c8=read('c8_musr_subtasks');rebuild=read('c8_musr_reconstruction')
    leaf=c8.pivot_table(index='Model',columns='task',values='normalized_score',aggfunc='last')
    manual=leaf.mean(axis=1,skipna=False).rename('manual')
    merged=rebuild.merge(manual,on='Model')
    checks['c8_three_task_equal_aggregation']=bool(np.allclose(merged.MuSR_rebuilt,merged.manual,equal_nan=True))
    raw=c8.raw_accuracy;lower=c8.chance_baseline
    manual_leaf=np.maximum(0,(raw-lower)/(1-lower))*100
    checks['c8_chance_normalization']=bool(np.allclose(c8.normalized_score,manual_leaf,equal_nan=True))
    audit=json.loads((OUT/'c8_audit.json').read_text(encoding='utf-8'));ledger=read('c8_directory_ledger')
    checks['c8_corruption_accounted']=int(ledger.invalid_files.sum())==audit['corrupt_files']
    checks['all_input_hashes_match']=all(hashlib.sha256((ROOT/v['path']).read_bytes()).hexdigest()==v['sha256'] for v in json.loads((OUT/'input_manifest.json').read_text(encoding='utf-8')))
    checks['all_c8_raw_hashes_match']=all(hashlib.sha256((ROOT/v['path']).read_bytes()).hexdigest()==v['sha256'] for v in json.loads((OUT/'c8_input_manifest.json').read_text(encoding='utf-8')))
    out=dict(status='passed' if all(checks.values()) else 'failed',checks={k:bool(v) for k,v in checks.items()},
             max_scale_derivative_error=maxerr,max_budget_relative_error=float(budget.max()),
             scope='numerical identities, evidence boundaries and reproducibility only; not causal proof')
    dump(out,'verification')
    assert all(checks.values()),[k for k,v in checks.items() if not v]
    print(f'{len(checks)} numerical/evidence checks passed.',flush=True)
    return out

if __name__=='__main__':run()

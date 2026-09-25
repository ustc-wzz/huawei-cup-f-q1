"""Read-only audit of Q1 scores for proposed Q3 quality/cost interfaces.

Run from repository root: Q1/.venv/bin/python Q3/audit_quality_interface.py
Adopted choices are recorded in the execution prompt; other rows are sensitivity candidates.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TAB = ROOT / 'output_q1/length_domain_calibrated22/tables'
OUT = ROOT / 'Q3/quality_audit'
OUT.mkdir(parents=True, exist_ok=True)
inputs = []

def read(path):
    inputs.append(path)
    return pd.read_csv(path)

def save(df, name):
    df.to_csv(OUT / f'{name}.csv', index=False, encoding='utf-8-sig')

parts = []
checks = []
for label in ['A1', 'A2', 'A3']:
    d = read(TAB / f'sample_Q_{label}.csv')
    lens = read(TAB / f'length_calibration_{label}.csv.gz')
    assert d[['id','domain']].equals(lens[['id','domain']])
    assert d[['id','domain','Q_res']].notna().all().all()
    assert np.isfinite(d.Q_res).all()
    d['words'] = lens['词数']
    d['length_imputed'] = lens['长度缺失填补']
    d['source'] = label
    assert np.isfinite(d.words).all() and (d.words > 0).all()
    checks.append({'source':label,'rows':len(d),'duplicate_keys':int(d.duplicated(['domain','id']).sum()),
                   'length_imputed':int(d.length_imputed.sum())})
    parts.append(d)
raw = pd.concat(parts, ignore_index=True)
spread = raw.groupby(['domain','id']).Q_res.agg(['min','max'])
assert np.allclose(spread['min'], spread['max'], atol=1e-12, rtol=0)
pool = raw.drop_duplicates(['domain','id']).copy()
q1path = TAB / 'q1_outputs_for_q2_q3.json'
q2path = ROOT / 'output_q2_shared/q2_interface.json'
inputs.extend([q1path,q2path])
q1 = json.loads(q1path.read_text())
q2 = json.loads(q2path.read_text())
assert hashlib.sha256(q1path.read_bytes()).hexdigest() == q2['q1_interface_sha256']
for dom, group in pool.groupby('domain'):
    assert np.isclose(group.Q_res.mean(), q1['quality_domain_Q_res'][dom], atol=1e-12)

qs = [.01,.05,.1,.25,.5,.75,.9,.95,.99]
def stats(label, d):
    a=d.Q_res.to_numpy()
    return {'population':label,'n':len(a),'min':a.min(),'mean':a.mean(),'max':a.max(),
            'word_weighted_mean':np.average(a,weights=d.words),
            **{f'q{int(q*100):02}':np.quantile(a,q) for q in qs}}

dist = [stats('A1',parts[0]),stats('all_unique',pool)]
dist += [stats('domain_'+str(k),g) for k,g in pool.groupby('domain')]
save(pd.DataFrame(dist),'score_distributions')
save(pd.DataFrame(checks),'source_checks')

# Domain-balanced empirical CDF: each quality domain has weight 1/7.
def balanced_quantile(d, probabilities):
    a=d.sort_values('Q_res').copy()
    counts=a.groupby('domain').Q_res.transform('size')
    w=1/counts.to_numpy()/a.domain.nunique()
    cdf=np.cumsum(w)
    return np.interp(probabilities,cdf,a.Q_res)

balanced = balanced_quantile(pool, qs)
save(pd.DataFrame({'quantile':qs,'domain_balanced_Q':balanced}),'balanced_quantiles')

# Within-domain top-score selection keeps domain mix conceptually fixed.
# Fractions refer to documents. Word shares are diagnostics, not token counts.
rates=[1.,.8,.5,.2,.1,.05]
tails=[]
for dom,g in pool.groupby('domain'):
    ordered=g.sort_values(['Q_res','id'],ascending=[False,True])
    for rate in rates:
        n=max(1,int(np.ceil(rate*len(g))))
        selected=ordered.iloc[:n]
        tails.append({'domain':dom,'requested_keep':rate,'n_total':len(g),'n_keep':n,
                      'actual_doc_keep':n/len(g),'word_keep':selected.words.sum()/g.words.sum(),
                      'threshold':selected.Q_res.min(),'baseline_mean':g.Q_res.mean(),
                      'selected_mean':selected.Q_res.mean(),
                      'gain':0. if rate == 1. else selected.Q_res.mean()-g.Q_res.mean(),
                      'selected_word_mean':np.average(selected.Q_res,weights=selected.words)})
tails=pd.DataFrame(tails)
save(tails,'within_domain_selection')
mapping=read(ROOT / 'real_attachments/A_data_value/domain_mapping_guide.csv')
kappas={'direct':1.,'near_direct':.8,'inferred':.5}
ps={'p0':dict(zip(q2['domain_order'],q2['p0'])),'p_star':q1['p_star']}
coverage=[]
caps=[]
for name,p in ps.items():
    q0=sum(p[d]*q1['mixture_domain_Q'][d] for d in p)
    known=0.
    for row in mapping.itertuples(index=False):
        observed=row.quality_domain in q1['quality_domain_Q_res']
        if observed:known+=p[row.mixture_domain]
        coverage.append({'recipe':name,'mixture_domain':row.mixture_domain,'quality_domain':row.quality_domain,
                         'mapping_type':row.mapping_type,'weight':p[row.mixture_domain],'has_quality_samples':observed})
    for rate in rates:
        gain=0.
        for row in mapping.itertuples(index=False):
            if row.quality_domain not in q1['quality_domain_Q_res']:continue
            delta=tails.loc[(tails.domain==row.quality_domain)&(tails.requested_keep==rate),'gain'].item()
            gain+=p[row.mixture_domain]*kappas[row.mapping_type]*delta
        caps.append({'recipe':name,'keep':rate,'Q0':q0,'u_cap_candidate':gain,'Q_cap_candidate':q0+gain,
                     'known_weight':known,'unknown_weight':1-known})
caps=pd.DataFrame(caps)
save(pd.DataFrame(coverage),'mapping_coverage')
save(caps,'quality_cap_candidates')

anchors=[('A1_extrema',parts[0].Q_res.min(),parts[0].Q_res.max()),
         ('A1_q01_q99',*np.quantile(parts[0].Q_res,[.01,.99])),
         ('A1_balanced_q01_q99',*balanced_quantile(parts[0],[.01,.99])),
         ('balanced_q01_q99',*balanced_quantile(pool,[.01,.99])),
         ('balanced_q05_q95',*balanced_quantile(pool,[.05,.95]))]
rows=[]
for name,lo,hi in anchors:
    for cap in caps.itertuples(index=False):
        z0=(cap.Q0-lo)/(hi-lo); z=(cap.Q_cap_candidate-lo)/(hi-lo)
        assert 0<z0<=z<=1
        row={'mapping':name,'Q_low':lo,'Q_high':hi,'slope':1/(hi-lo),
             'recipe':cap.recipe,'keep':cap.keep,'z0':z0,'z_cap':z}
        for cost,fun in [('exponential',lambda x:1e7*np.exp(6*x)),
                         ('power',lambda x:5e9*x**4),
                         ('logarithmic',lambda x:2e9*np.log1p(10*x))]:
            row[cost+'_delta_FLOPs_per_token']=max(0,fun(z)-fun(z0))
        rows.append(row)
save(pd.DataFrame(rows),'mapping_cost_candidates')

# Sampling-composition sensitivity of equal-domain anchor candidates.
anchor_sensitivity=[]
for name,d in [('A1_only',parts[0]),('deduplicated_full',pool)]:
    lo,hi=balanced_quantile(d,[.01,.99])
    anchor_sensitivity.append({'population':name,'balanced_q01':lo,'balanced_q99':hi,'width':hi-lo})
save(pd.DataFrame(anchor_sensitivity),'anchor_sensitivity')

verification={'status':'passed','raw_rows':len(raw),'unique_rows':len(pool),
              'overlap_rows_removed_for_aggregation':len(raw)-len(pool),
              'max_duplicate_score_spread':float((spread['max']-spread['min']).max()),
              'domain_means_match_current_interface':True,'q1_q2_interface_hash_matches':True,
              'candidate_caps_monotone':bool(all((np.diff(g.u_cap_candidate)>=-1e-12).all() for _,g in caps.groupby('recipe',sort=False))),
              'all_candidate_aggregate_cost_coordinates_in_0_1':True,
              'decisions':'Five quality ceilings with keep=0.5 as display slice; see execution prompt. Audit reads current Q1/Q2 interfaces without modifying them.',
              'limitations':['Q scores are model-based document scores, not measured training gains.',
                             'Document/word retention is not token retention.',
                             '11 missing mixture domains retain baseline with zero proposed gain.',
                             'No raw corpus token supply or measured processing cost is available in this audit.',
                             'Mapping T does not identify the B-to-Q1 conversion s_Q.']}
assert verification['candidate_caps_monotone']
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
manifest=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,
           'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]
(OUT/'input_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(verification,ensure_ascii=False,indent=2))
print(pd.DataFrame(dist).to_string(index=False))
print(caps.to_string(index=False))
print(pd.DataFrame(anchor_sensitivity).to_string(index=False))

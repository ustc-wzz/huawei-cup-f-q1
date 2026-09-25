"""Q4 evidence audit. No fuzzy joins or imputed training-token observations."""
from pathlib import Path
import hashlib, json, re
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CD = ROOT / 'real_attachments/C_efficiency_evolution'
OUT = ROOT / 'output_q4_evolution'
DIMS = ['IFEval', 'BBH', 'MATH Lvl 5', 'GPQA', 'MUSR', 'MMLU-PRO']
# Operational open-weight/research-use list, not a claim of OSI open source.
LICENSES = {'apache-2.0','mit','llama2','llama3','llama3.1','llama3.2','llama3.3',
 'gemma','cc-by-4.0','cc-by-sa-4.0','cc-by-nc-4.0','cc-by-nc-sa-4.0',
 'bigscience-bloom-rail-1.0','bigscience-openrail-m','bigcode-openrail-m',
 'creativeml-openrail-m','openrail','openrail++','gpl-3.0','agpl-3.0',
 'lgpl-3.0','bsd-3-clause','bsd-2-clause','cc0-1.0','artistic-2.0',
 'mpl-2.0','llama-2','wtfpl','unlicense','deepseek','yi-license'}

def save(df, name):
    (OUT/'tables').mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT/'tables'/f'{name}.csv', index=False)

def dump(obj, name):
    OUT.mkdir(exist_ok=True)
    (OUT/f'{name}.json').write_text(json.dumps(obj, ensure_ascii=False, indent=2,
        default=lambda x: x.item() if isinstance(x,np.generic) else str(x))+'\n')

def key(name):
    # Preserve decimal separators: OPT-1.3B must never match OPT-13B.
    s=str(name).split('/')[-1].lower().strip()
    s=s.replace('meta-llama','llama')
    s=re.sub(r'(?<=\d)_(?=\d)', '.', s)
    return re.sub(r'[^a-z0-9.]','',s)

def model_type(s):
    s=str(s)
    if 'continuously' in s: return 'continued'
    if 'pretrained' in s: return 'pretrained'
    if 'chat' in s or 'fine-tuned' in s: return 'chat_finetuned'
    if 'merges' in s: return 'merge'
    return 'other'

def read_data():
    a=pd.read_csv(CD/'leaderboard_cleaned.csv')
    a['date']=pd.to_datetime(a['Submission Date'],errors='coerce')
    a['N']=pd.to_numeric(a['#Params (B)'],errors='coerce')
    a['license']=a['Hub License'].fillna('').str.lower().str.strip()
    a[DIMS]=a[DIMS].apply(pd.to_numeric,errors='coerce')
    a['S']=a[DIMS].mean(axis=1,skipna=False)
    a['type']=a.Type.map(model_type)
    a['org']=a.Model.str.split('/').str[0].str.lower()
    a['key']=a.Model.map(key)
    a['exclusion']=''
    for mask,reason in [(~a.license.isin(LICENSES),'license_unverified'),
      (a.date.isna(),'missing_submission_date'),(~(a.N>0),'invalid_N'),
      (~a[DIMS].ge(0).all(axis=1)|~a[DIMS].le(100).all(axis=1),'invalid_scores')]:
        a.loc[mask,'exclusion']+=reason+';'
    audit=a[['Model','date','type','N','license','exclusion']].copy()
    clean=a[a.exclusion.eq('')].sort_values(['date','Model'],kind='stable').drop_duplicates('Model',keep='first').copy()
    clean['month']=clean.date.dt.to_period('M').dt.to_timestamp()
    save(audit,'c1_screening');save(clean[['Model','date','month','N','S','type','license','org']+DIMS],'c1_analysis')

    e=pd.read_csv(CD/'epoch_all_ai_models.csv');e['row_id']=np.arange(len(e))
    e['key']=e.Model.map(key);e['pub']=pd.to_datetime(e['Publication date'],errors='coerce')
    e['D']=pd.to_numeric(e['Training dataset size (total)'],errors='coerce')/1e9
    e['N_epoch']=pd.to_numeric(e['Parameters'],errors='coerce')/1e9
    e['C']=pd.to_numeric(e['Training compute (FLOP)'],errors='coerce')
    e['open']=e['Open model weights?'].fillna('').str.lower().eq('yes')
    e['language']=e.Domain.fillna('').str.contains('Language',case=False)
    matches=[]
    for _,r in clean.iterrows():
        cand=e[e.key.eq(r.key)&e.language&e.open].copy()
        cand=cand[(cand.N_epoch/r.N).between(.65,1.5)]
        if len(cand)!=1:
            matches.append(dict(Model=r.Model,status='ambiguous' if len(cand)>1 else 'unmatched',candidates=len(cand)))
            continue
        v=cand.iloc[0]
        # A re-upload with the same leaf name is not automatically the original model.
        dev=str(v['Hugging Face developer id']).lower()
        special={'facebook':'meta','huggyllama':'meta','meta-llama':'meta','tiiuae':'technology innovation institute',
          'eleutherai':'eleutherai','bigscience':'bigscience','01-ai':'01.ai','stabilityai':'stability ai',
          'qwen':'alibaba','google':'google','microsoft':'microsoft','bigcode':'bigcode',
          'primeintellect':'prime intellect','apple':'apple','mosaicml':'mosaicml'}
        org=str(v.Organization).lower()
        trusted=r.org==dev or (r.org in special and special[r.org] in org)
        status='accepted' if trusted else 'namespace_unverified'
        matches.append(dict(Model=r.Model,status=status,candidates=1,epoch_model=v.Model,
          epoch_row=int(v.row_id),publication_date=v.pub,D=v.D,C=v.C,N_epoch=v.N_epoch,
          epoch_org=v.Organization,base_model=v['Base model'],dataset_notes=v['Dataset size notes'],
          compute_notes=v['Training compute notes'],confidence=v.Confidence,
          parameter_notes=v['Parameters notes'],source=v.Reference))
    ledger=pd.DataFrame(matches);save(ledger,'c4_match_ledger')
    paired=clean.merge(ledger[ledger.status.eq('accepted')],on='Model',validate='one_to_one')
    paired['publication_date']=pd.to_datetime(paired.publication_date)
    paired['is_moe']=paired.parameter_notes.fillna('').str.contains('active|moe|expert',case=False)
    paired['training_from_scratch']=paired.base_model.isna() & paired.type.eq('pretrained')
    paired['eligible_nd']=(paired.training_from_scratch & ~paired.is_moe & (paired.D>0)
                          & paired.publication_date.notna() & paired.publication_date.le(clean.date.max()))
    paired['lag_days']=(paired.date-paired.publication_date).dt.days
    save(paired,'matched_metadata')
    nd=paired[paired.eligible_nd].copy()
    # Dataset size notes must be exposed; C4 is metadata (sometimes estimates), not training logs.
    nd['N_leaderboard']=nd.N
    nd['N']=nd.N_epoch  # Match the training-metadata parameter definition used with D.
    nd['t']=(nd.publication_date-pd.Timestamp('2023-01-01')).dt.days/365.25
    nd['lnN']=np.log(nd.N);nd['lnD']=np.log(nd.D)
    save(nd,'nd_primary_sample')

    c3=pd.read_csv(CD/'leaderboard_extended_timeseries.csv')
    c3['source_class']=np.where(c3.Source.eq('Open LLM Leaderboard'),'same_leaderboard','historical_noncomparable')
    joined=c3.merge(clean[['Model','S']],on='Model',how='left')
    joined['score_difference']=pd.to_numeric(joined.Average,errors='coerce')-joined.S
    save(joined.groupby(['source_class','Year'],dropna=False).agg(n=('Model','size'),
      mean_score=('Average','mean'),matched=('S','count'),
      max_abs_difference=('score_difference',lambda x:x.abs().max())).reset_index(),'c3_source_year_audit')
    save(joined[joined.source_class.eq('historical_noncomparable')],'c3_historical_context')
    counts=dict(c1_rows=len(a),c1_unique_screened=len(clean),c1_duplicate_removed=int((a.exclusion.eq('')).sum()-len(clean)),
       dates=[str(clean.date.min().date()),str(clean.date.max().date())],types=clean.type.value_counts().to_dict(),
       matched=len(paired),primary_nd=len(nd),nd_organizations=nd.org.nunique(),
       nd_publication_range=[str(nd.publication_date.min().date()),str(nd.publication_date.max().date())],
       c3_rows=len(c3),c3_sources=c3.source_class.value_counts().to_dict(),
       score_rebuild_max_error=float((a.S-pd.to_numeric(a['Average ⬆️'],errors='coerce')).abs().max()))
    dump(counts,'data_audit')
    return clean,nd,e,paired

def aggregate_c8(clean):
    """Rebuild MuSR from three individual tasks, not the provided group mean."""
    specs={'leaderboard_musr_murder_mysteries':.5,
      'leaderboard_musr_object_placements':.2,'leaderboard_musr_team_allocation':1/3}
    rows=[];bad=[];sub=[];manifest=[];directories=[]
    for folder in sorted((CD/'detailed_results').iterdir()):
        if not folder.is_dir():continue
        chosen=None;invalid=0;valid=0
        # Audit every file for corruption; select lexicographically latest timestamped valid JSON.
        for f in sorted(folder.glob('*.json')):
            manifest.append(dict(path=str(f.relative_to(ROOT)),sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
            try:j=json.loads(f.read_text())
            except (ValueError,UnicodeError) as err:
                invalid+=1;bad.append(dict(file=str(f.relative_to(ROOT)),error=str(err)[:160]));continue
            if isinstance(j.get('results'),dict):chosen=(f,j);valid+=1
        directories.append(dict(directory=folder.name,valid_files=valid,invalid_files=invalid,
             chosen_file=str(chosen[0].relative_to(ROOT)) if chosen else '',
             status='usable' if chosen else 'no_parseable_evaluation'))
        if chosen is None:continue
        f,j=chosen;vals=[]
        for task,base in specs.items():
            v=j['results'].get(task,{}).get('acc_norm,none',np.nan)
            try:v=float(v)
            except (ValueError,TypeError):v=np.nan
            n=100*max(0.,(v-base)/(1-base)) if np.isfinite(v) else np.nan
            vals.append(n);sub.append(dict(Model=j.get('model_name'),task=task,raw_accuracy=v,
                          chance_baseline=base,normalized_score=n,file=str(f.relative_to(ROOT))))
        rows.append(dict(Model=j.get('model_name'),MuSR_rebuilt=float(np.mean(vals)),
                   complete=bool(np.isfinite(vals).all()),file=str(f.relative_to(ROOT))))
    detail=pd.DataFrame(rows).drop_duplicates('Model',keep='last')
    comp=detail.merge(clean[['Model','MUSR','type','S','date']],on='Model',how='left')
    comp['difference']=comp.MuSR_rebuilt-comp.MUSR
    save(pd.DataFrame(sub),'c8_musr_subtasks');save(comp,'c8_musr_reconstruction')
    save(pd.DataFrame(directories),'c8_directory_ledger')
    save(pd.DataFrame(bad,columns=['file','error']),'c8_corrupt_files')
    merged=pd.DataFrame(sub).merge(clean[['Model','type']],on='Model',how='inner')
    save(merged.groupby(['type','task']).normalized_score.agg(['count','mean','median']).reset_index(),'c8_task_type_summary')
    dump(manifest,'c8_input_manifest')
    audit=dict(json_files=len(manifest),corrupt_files=len(bad),directories=len(directories),
       directories_without_valid=sum(v['valid_files']==0 for v in directories),
       corrupt_directories_with_fallback=sum(v['invalid_files']>0 and v['valid_files']>0 for v in directories),models=len(detail),
       complete=int(detail.complete.sum()),matched=int(comp.MUSR.notna().sum()),
       matching_within_1e_6=int(comp.difference.abs().lt(1e-6).sum()),
       median_abs_difference=float(comp.difference.abs().median()),
       p95_abs_difference=float(comp.difference.abs().quantile(.95)),
       note='latest valid evaluations may differ from C1 snapshot; scores are not silently replaced')
    dump(audit,'c8_audit');return comp,audit

if __name__=='__main__':
    clean,nd,e,paired=read_data()
    print((OUT/'data_audit.json').read_text())
    print(nd[['Model','N','D','publication_date','S']].to_string(index=False))
    print(aggregate_c8(clean)[1])

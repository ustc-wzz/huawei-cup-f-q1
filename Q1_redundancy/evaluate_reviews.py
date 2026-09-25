"""Evaluate independent human labels only; never infer missing labels."""
from pathlib import Path
import numpy as np,pandas as pd
O=Path('output_q1_redundancy');key=pd.read_csv(O/'analyst_key.csv');rng=np.random.default_rng(20260926);results=[];labels=[]
for reviewer in [1,2]:
 f=pd.read_csv(O/'blind_review'/f'reviewer_{reviewer}.csv').fillna('')
 assert f.pair_id.is_unique and set(f.pair_id)==set(key.pair_id)
 f.choice=f.choice.str.strip().str.upper();assert set(f.choice)<=set(['','L','R','T','U'])
 labels.append(f.set_index('pair_id').choice)
 g=key.merge(f,on='pair_id')
 for layer,sub in g.groupby('sampling'):
  valid=sub[sub.choice.isin(['L','R'])].copy();row={'reviewer':reviewer,'sampling':layer,'total':len(sub),'valid':len(valid),'missing':int((sub.choice=='').sum()),'tie':int((sub.choice=='T').sum()),'unable':int((sub.choice=='U').sum())}
  if len(valid):
   valid['abs_correct']=(valid.choice==valid.abs_preference).astype(int);valid['square_correct']=(valid.choice==valid.square_preference).astype(int)
   vals=[]
   for b in range(2000):
    sample=pd.concat([q.iloc[rng.integers(len(q),size=len(q))] for _,q in valid.groupby('domain')]);vals.append((sample.square_correct-sample.abs_correct).mean())
   row.update(abs_agreement=valid.abs_correct.mean(),square_agreement=valid.square_correct.mean(),difference=np.mean(valid.square_correct-valid.abs_correct),difference_low=np.quantile(vals,.025),difference_high=np.quantile(vals,.975))
  results.append(row)
r=pd.DataFrame(results);r.to_csv(O/'human_review_results.csv',index=False);print(r.to_string(index=False))
x,y=labels;mask=x.isin(['L','R','T'])&y.isin(['L','R','T']);print('Two-reviewer comparable pairs:',int(mask.sum()),'agreement:',float((x[mask]==y[mask]).mean()) if mask.any() else 'pending')

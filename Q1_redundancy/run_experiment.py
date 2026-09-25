"""Fixed preprocessing/beta audit; does not overwrite Q1 outputs. Run from project root."""
from pathlib import Path
import json,lzma,hashlib
import numpy as np
import pandas as pd
from scipy.stats import rankdata,spearmanr
R=Path('output_q1/length_domain_calibrated22/tables');O=Path('output_q1_redundancy');O.mkdir(exist_ok=True)
rng=np.random.default_rng(20260925);B=200
cols=pd.read_csv(R/'indicator_weights.csv',index_col=0).index.tolist()
F={s:pd.read_csv(R/f'all_indicators_{s}.csv.gz') for s in ['A1','A2','A3']}
Z={s:f[['Z_'+c for c in cols]].to_numpy() for s,f in F.items()}
def weights(z,p):
 d=(np.abs(np.corrcoef(z,rowvar=False))**p).sum(axis=1);w=1/d;return w/w.sum()
def score(z,w):return -4*np.log(np.exp(-.25*z)@w)
def compare(a,b):
 k=max(1,int(np.ceil(.1*len(a))));ia=np.argsort(a,kind='stable');ib=np.argsort(b,kind='stable')
 return {'rho':spearmanr(a,b).statistic,'top10_overlap':len(np.intersect1d(ia[-k:],ib[-k:]))/k,'bottom10_overlap':len(np.intersect1d(ia[:k],ib[:k]))/k,'mean_abs_rank_shift':np.mean(np.abs(rankdata(a)-rankdata(b)))/len(a)}
W={p:weights(Z['A1'],p) for p in [1,2]};Q={p:{s:score(z,W[p]) for s,z in Z.items()} for p in [1,2]}
assert np.allclose(W[1],pd.read_csv(R/'indicator_weights.csv',index_col=0)['权重'])
assert np.allclose(Q[1]['A1'],pd.read_csv(R/'sample_Q_A1.csv').Q_res)
pd.DataFrame({'indicator':cols,'abs_weight':W[1],'square_weight':W[2]}).to_csv(O/'weights.csv',index=False)
pd.DataFrame([{'set':s,**compare(Q[1][s],Q[2][s])} for s in Z]).to_csv(O/'method_comparison.csv',index=False)
pd.concat([F[s][['domain']].assign(set=s,abs_score=Q[1][s],square_score=Q[2][s]).groupby(['set','domain']).agg(['mean','count']) for s in Z]).to_csv(O/'domain_scores.csv')
# All 22 indicators; same noise realization for both methods. Noise SD=.5 of indicator SD.
rows=[]
for j,c in enumerate(cols):
 for kind in ['exact','noise']:
  z=Z['A1'];copy=z[:,j].copy()
  if kind=='noise':
   copy=copy+rng.normal(0,.5*z[:,j].std(),len(z));copy=(copy-copy.mean())/copy.std()*z[:,j].std()+z[:,j].mean()
  aug=np.column_stack([z,copy])
  for p in [1,2]:
   w=weights(aug,p);rows.append({'indicator':c,'copy':kind,'power':p,'family_weight_before':W[p][j],'family_weight_after':w[j]+w[-1],'family_weight_inflation':(w[j]+w[-1])/W[p][j],**compare(Q[p]['A1'],score(aug,w))})
 print('duplicate',j+1,flush=True)
pd.DataFrame(rows).to_csv(O/'duplicate_metrics.csv',index=False)
# Hold out 20% per domain, never used to estimate correlations. Preprocessing fixed as requested.
train=[];hold=[]
for d,g in F['A1'].groupby('domain'):
 ix=rng.permutation(g.index);k=max(1,int(np.ceil(.2*len(ix))));hold.extend(ix[:k]);train.extend(ix[k:])
train=np.array(train);hold=np.array(hold)
pd.DataFrame({'id':F['A1'].id,'domain':F['A1'].domain,'split':np.where(np.isin(np.arange(len(F['A1'])),hold),'holdout','train')}).to_csv(O/'split.csv',index=False)
# Exclude shared A1 IDs from extension evaluation to avoid known overlap.
eval_ix={'A1':hold}
for s in ['A2','A3']:
 ix=np.flatnonzero(~F[s].id.isin(F['A1'].id));eval_ix[s]=ix
E={s:np.exp(-.25*Z[s][ix]) for s,ix in eval_ix.items()}
base={p:weights(Z['A1'][train],p) for p in [1,2]}
baseq={p:{s:-4*np.log(e@base[p]) for s,e in E.items()} for p in [1,2]}
strata=[np.intersect1d(g.index,train) for _,g in F['A1'].groupby('domain')]
wr={p:[] for p in [1,2]};rows=[]
for b in range(B):
 ix=np.concatenate([rng.choice(g,len(g),replace=True) for g in strata]);z=Z['A1'][ix]
 for p in [1,2]:
  w=weights(z,p);wr[p].append(w)
  for s,e in E.items():rows.append({'replicate':b,'power':p,'set':s,'n':len(e),'weight_L1':np.abs(w-base[p]).sum(),**compare(baseq[p][s],-4*np.log(e@w))})
 if b%20==0:print('bootstrap',b,flush=True)
pd.DataFrame(rows).to_csv(O/'bootstrap_metrics.csv',index=False)
pd.concat([pd.DataFrame({'indicator':cols,'power':p,'mean':np.mean(wr[p],axis=0),'sd':np.std(wr[p],axis=0,ddof=1),'low':np.percentile(wr[p],2.5,axis=0),'high':np.percentile(wr[p],97.5,axis=0)}) for p in [1,2]]).to_csv(O/'bootstrap_weights.csv',index=False)
# Blind within-domain pairs: 3 random and 3 opposite-ranked pairs in each of seven A1 domains.
key=[];used=set();pairno=0
for d,g in F['A1'].groupby('domain'):
 ix=g.index.to_numpy();delta=rankdata(Q[2]['A1'][ix])-rankdata(Q[1]['A1'][ix]);order=ix[np.argsort(delta)]
 for group in ['disagreement','random']:
  count=0
  for attempt in range(10000):
   if group=='random':a,b=rng.choice(ix,2,replace=False)
   else:
    k=min(len(ix)//2, max(10,int(.2*len(ix))));a=rng.choice(order[:k]);b=rng.choice(order[-k:])
    if (Q[1]['A1'][a]-Q[1]['A1'][b])*(Q[2]['A1'][a]-Q[2]['A1'][b])>=0:continue
   if a in used or b in used:continue
   used.update([a,b]);pairno+=1
   if rng.random()<.5:a,b=b,a
   key.append({'pair_id':f'P{pairno:03d}','domain':d,'sampling':group,'left_id':str(F['A1'].id[a]),'right_id':str(F['A1'].id[b]),'abs_preference':'L' if Q[1]['A1'][a]>Q[1]['A1'][b] else 'R','square_preference':'L' if Q[2]['A1'][a]>Q[2]['A1'][b] else 'R'})
   count+=1
   if count==3:break
  assert count==3,(d,group,count)
key=pd.DataFrame(key).sample(frac=1,random_state=9);key.to_csv(O/'analyst_key.csv',index=False)
need=set(key.left_id)|set(key.right_id);texts={}
raw=Path('real_attachments/A_data_value/slimpajama_quality_signal_sample.jsonl.xz')
if not raw.exists():
 raw=next(Path('real_attachments').rglob('slimpajama_quality_signal_sample.jsonl*'))
with (lzma.open(raw,'rt') if raw.suffix=='.xz' else raw.open()) as f:
 for line in f:
  try:o=json.loads(line)
  except ValueError:continue
  id_=str(o.get('id',''))
  if id_ in need:texts[id_]=o.get('content') or o.get('text') or ''
  if len(texts)==len(need):break
assert all(texts.get(i) for i in need)
blind=O/'blind_review';blind.mkdir(exist_ok=True)
for _,r in key.iterrows():
 (blind/(r.pair_id+'.txt')).write_text(r.pair_id+'\n\nLEFT\n'+texts[r.left_id]+'\n\nRIGHT\n'+texts[r.right_id])
for reviewer in [1,2]:
 target=blind/f'reviewer_{reviewer}.csv'
 if not target.exists():pd.DataFrame({'pair_id':key.pair_id,'choice':'','reason':''}).to_csv(target,index=False)
(blind/'README.md').write_text('''# 独立盲评
请两位评审独立填写各自CSV；不要查看analyst_key.csv、计算结果或对方标注。
评价用于通用语言模型训练的文本质量：可理解性、连贯性、信息价值、重复/损坏程度；专业公式、代码或长文本本身不算低质量。不按个人领域偏好评分；无法判断时标U。
choice填L（左更好）、R（右更好）、T（相当）、U（无法判断），reason写简短理由。每对为同领域完整文本，左右随机，无模型分数。
随机样本与分歧样本的结果须分开报告；该评审包不能估计全语料总体准确率。重复运行不覆盖已有评审表；仍建议保留原始标注备份。
''')
(O/'protocol.json').write_text(json.dumps({'seed':20260925,'beta':.25,'bootstrap':B,'fixed_preprocessing':True,'bootstrap_scope':'conditional on fixed A1 preprocessing; not end-to-end independent validation','extension_excludes_A1_ids':True,'duplicate_noise_sd':.5,'blind_pairs':len(key),'human_review_status':'pending','main_model_changed':False,'input_sha256':{f:hashlib.sha256((R/f).read_bytes()).hexdigest() for f in ['all_indicators_A1.csv.gz','all_indicators_A2.csv.gz','all_indicators_A3.csv.gz','indicator_weights.csv']}},ensure_ascii=False,indent=2))
print('SUCCESS',flush=True)

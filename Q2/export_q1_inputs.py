"""问题一补充导出：只复用当前对数线性模型和配方观测，供问题二读取。"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
QROOT=ROOT/'output_q1/length_domain_calibrated22'
OUT=QROOT/'q2_loglinear_inputs';OUT.mkdir(exist_ok=True)
interface=QROOT/'tables/q1_outputs_for_q2_q3.json'
q=json.loads(interface.read_text(encoding='utf-8')); assert q['selected_predictive_model']=='对数线性混料'
dom=q['domain_order'];coef=np.array([q['log_linear_model']['a_i'][d] for d in dom]);eps=q['log_linear_model']['epsilon']
def pred(p):return q['log_linear_model']['intercept']+np.log(p+eps)@coef
raw=ROOT/'real_attachments/A_data_value/regmix_tables'
meta={'domain_order':dom,'interface_sha256':hashlib.sha256(interface.read_bytes()).hexdigest(),'D_source':'RegMix ICLR 2025 Table 2 caption; matched by attachment scale, not run-level CSV field','D_url':'https://proceedings.iclr.cc/paper_files/paper/2025/file/5f67d864aae6115374fed7beddd119e0-Paper-Conference.pdf','datasets':{},'raw_hashes':{}}
for key,stub,N,D in [('train_1M','train',.001,1.),('test_1M','test',.001,1.),('test_60M','test',.06,1.),('test_1B','test',1.,25.)]:
 suffix={'train_1M':'1m','test_1M':'1m','test_60M':'60m','test_1B':'1B'}[key]
 mp=raw/f'{stub}_mixture_{suffix}.csv';lp=raw/f'{stub}_pile_loss_{suffix}.csv'
 mix=pd.read_csv(mp);loss=pd.read_csv(lp);mc=['train_the_pile_'+d for d in dom];lc=[x for x in loss if x.endswith('_val_loss')]
 assert len(lc)==13
 df=mix[['index']+mc].merge(loss[['index']+lc],on='index',validate='one_to_one');p=df[mc].to_numpy(float);p/=p.sum(axis=1,keepdims=True)
 result=pd.DataFrame(p,columns=dom);result.insert(0,'recipe_id',df['index'].to_numpy());result['loss']=df[lc].mean(axis=1);result['loglinear_hat']=pred(p)
 result.to_csv(OUT/f'{key}.csv',index=False)
 meta['datasets'][key]={'N_B':N,'D_B':D,'n':len(result)}
 for path in [mp,lp]:meta['raw_hashes'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
 if key=='train_1M':meta.update(p0=p.mean(axis=0).tolist(),s_L=float(result.loss.std(ddof=0)),anchor_loss=float(pred(p.mean(axis=0))))
pstar=np.array([q['p_star'][d] for d in dom]);err=abs(float(pred(pstar))-q['L_hat_p_star_selected']);assert err<1e-10
meta['p_star_prediction_error']=err
(OUT/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2), encoding='utf-8')
print('问题一对数线性补充接口完成；主配比预测复现误差:',err)

# %% [markdown]
# # 问题二：跨来源融合与共同修正标度律
#
# **研究主线：用问题一刻画数据质量与领域配比，用附件B识别规模与质量规律，在来源校准后建立共同修正标度律，并检验资源之间的替代关系。**
#
# 主模型为
#
# $$
# L_s=E_s+\left(A_sN^{-\alpha}+B_sD^{-\nu}\right)
# \exp[-\lambda u+\eta h(\mathbf p)]+\epsilon,
# \qquad u=Q-Q_0(\mathbf p).
# $$
#
# $s$是实验来源；$E_s,A_s,B_s$允许来源间验证语料、分词和训练设置不同；$\alpha,\nu$是共享的规模指数。$Q_0(\mathbf p)$是原配比质量指数，$u$是同配比下额外质量变化；$h$承接问题一的对数线性预测。共同修正 = 数据因素以同一比例影响参数项与数据项。该结构是待验证的经验假设，不是由交叉熵定义必然推出。
#
# **复现约定**：在项目根目录运行。本notebook读取附件B及问题一补充输出 `output_q1/length_domain_calibrated22/q2_loglinear_inputs/`；不直接读取附件A。缺少补充输出时，先运行 `python Q2/export_q1_inputs.py`，此步骤属于问题一导出阶段。结果保存到 `output_q2_shared/`。
#
# $N,D$统一以十亿计，实际算力为$6\times10^{18}ND$ FLOPs；$\nu$与问题一评分参数$\beta=0.25$不同。$Q$允许负值，不将其解释为合格数据比例。各阶段先给出假设和检验方法，再展示实际结果。

# %%
from pathlib import Path
import json,hashlib,platform
import numpy as np
import pandas as pd
import scipy,sklearn
from scipy.optimize import least_squares,lsq_linear,minimize_scalar
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold
import matplotlib.pyplot as plt
from matplotlib import font_manager
from IPython.display import display,Markdown
ROOT=Path.cwd(); BROOT=ROOT/'real_attachments/B_scaling_laws'
QROOT=ROOT/'output_q1/length_domain_calibrated22'; HROOT=QROOT/'q2_loglinear_inputs'
OUT=ROOT/'output_q2_shared'; TAB=OUT/'tables'; FIG=OUT/'figures'
for p in [TAB,FIG]:p.mkdir(parents=True,exist_ok=True)
q1=json.loads((QROOT/'tables/q1_outputs_for_q2_q3.json').read_text())
meta=json.loads((HROOT/'metadata.json').read_text())
assert q1['selected_predictive_model']=='对数线性混料'
assert hashlib.sha256((QROOT/'tables/q1_outputs_for_q2_q3.json').read_bytes()).hexdigest()==meta['interface_sha256']
RNG=np.random.default_rng(925)
pd.set_option('display.max_columns',15)
fonts={f.name for f in font_manager.fontManager.ttflist}
for f in ['Arial Unicode MS','PingFang SC','Heiti SC','Noto Sans CJK SC']:
    if f in fonts:plt.rcParams['font.family']=f;break
plt.rcParams.update({'axes.unicode_minus':False,'figure.dpi':110,'savefig.dpi':180,'axes.spines.top':False,'axes.spines.right':False})
def save_table(df,name):
    df.to_csv(TAB/f'{name}.csv',index=False,encoding='utf-8-sig');return df
def show(s):display(Markdown(s))
def finish_fig(name):
    plt.tight_layout();plt.savefig(FIG/f'{name}.png',bbox_inches='tight');plt.show()
def metrics(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float);v=np.sum((y-y.mean())**2)
    return {'n':len(y),'RMSE':float(np.sqrt(np.mean((y-p)**2))),'MAE':float(np.mean(abs(y-p))),
            'R2':float(1-np.sum((y-p)**2)/v) if v>0 else np.nan,
            'Spearman':float(spearmanr(y,p).statistic) if np.std(p)>1e-12 else np.nan}
versions={'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__}
(OUT/'versions.json').write_text(json.dumps(versions,indent=2))
print('当前问题一模型：',q1['selected_predictive_model'],'；主配比复现误差：',meta['p_star_prediction_error'])

# %% [markdown]
# ## 1. 输入、变量与三个可检验假设
#
# 附件A的质量信号和配方实验通过问题一输出引入：质量评分负责定义基线，配比模型负责给出相对配比优劣；附件B提供规模轨迹、文献收敛点与半合成质量实验。两者不是同一批受控实验，不直接拼成完整的四维实验表。
#
# | 假设 | 数学含义 | 检验设计 |
# |---|---|---|
# | H1：规模结构可迁移 | 来源共享$\alpha,\nu$，绝对损失允许来源校准 | B1按模型规模留出；B2共享/自由指数比较；B4/B5来源内留一 |
# | H2：共同的相对修正 | $(L_s-E_s)/(A_sN^{-\alpha}+B_sD^{-\nu})$由质量或配比决定 | 质量按$(N,D)$分组与新质量水平验证；配比按配方分组及留尺度验证 |
# | H3：质量与配比可分离 | 指数内没有$u\times h$交互项，来源间可迁移修正规律 | 现有独立附件只能分别验证边际规律；完整检验需交叉受控实验 |
#
# H3及质量刻度转换是明确保留的工作假设，不会因两个边际模型拟合较好就自动获得证明。B6—B8为半合成数据，B3为插值，B10为估算；后两者不能当作独立外推验证。

# %%
FILES={'B1':'pythia_training_log_existing.csv','B2':'cerebras_training_log.csv','B4':'scaling_baseline.csv','B5':'published_scaling_data.csv','B6':'supplementary_NQ_experiment.csv','B7':'supplementary_NQ_experiment_expanded.csv','B8':'supplementary_NQ_experiment_large.csv','B9':'supplementary_large_models.csv','B10':'supplementary_large_baseline.csv','B11':'open_model_family_metadata.csv','B12':'pythia_checkpoint_index.csv'}
NATURE={'B1':'附件标注真实轨迹，未独立追溯','B2':'半合成','B3':'插值','B4':'真实收敛点','B5':'文献收敛点','B6':'半合成','B7':'半合成','B8':'半合成含外推','B9':'模型元数据','B10':'估算Loss','B11':'辅助元数据','B12':'辅助索引'}
data={k:pd.read_csv(BROOT/v) for k,v in FILES.items()}
data['B3']=pd.concat([pd.read_csv(p) for p in sorted((BROOT/'training_trajectories').glob('*.csv'))],ignore_index=True)
audit=[]
for k,d in data.items():
    r={'编号':k,'性质':NATURE[k],'行数':len(d),'完全重复行':int(d.duplicated().sum())}
    for c in ['N_params_B','D_tokens_B','val_loss']:
        if c in d:r[c+'_无效数']=int((~np.isfinite(d[c])|(d[c]<=0)).sum())
    audit.append(r)
audit=save_table(pd.DataFrame(audit),'data_audit');display(audit)
for k in ['B1','B2','B4','B5','B6','B7','B8','B10']:
    assert np.isfinite(data[k][['N_params_B','D_tokens_B','val_loss']]).all().all()
    assert (data[k][['N_params_B','D_tokens_B','val_loss']]>0).all().all()
unit=[]
for k in ['B1','B2']:
    d=data[k];ratio=d.C_FLOPs_1e21*1e21/(6e18*d.N_params_B*d.D_tokens_B)
    unit.append({'数据':k,'C/(6ND)中位数':ratio.median(),'5%':ratio.quantile(.05),'95%':ratio.quantile(.95)})
display(save_table(pd.DataFrame(unit),'compute_unit_check'))
print('B11覆盖模型族：',data['B11'].family.unique(),'；B12检查点索引行数：',len(data['B12']))

# %% [markdown]
# ## 2. 经典规模项与跨来源校准（H1）
#
# 在B1上拟合$E+AN^{-\alpha}+BD^{-\nu}$。幅度用对数参数化保证正值，对数残差使用Huber损失（阈值0.01），多起点求解；普通对数最小二乘作为拟合敏感性对照。轨迹中的检查点相关，因此按整个模型规模留出，而非随机拆行。
#
# B2先直接迁移，再用交替模型规模作为校准集，其余规模验证共享指数与自由指数。B4/B5样本较少，采用较简约的来源校准$E_s+c_s(AN^{-\alpha}+BD^{-\nu})$，这是$A_s,B_s$同时缩放的受限形式；来源至少3点才进行来源内留一，其余记录仅用于直接迁移诊断。校准后检验不等于预测一个完全未知来源。

# %%
def xy(d):return d.N_params_B.to_numpy(float),d.D_tokens_B.to_numpy(float),d.val_loss.to_numpy(float)
def decode(t):return np.array([np.exp(t[0]),np.exp(t[1]),t[2],np.exp(t[3]),t[4]])
def classic(N,D,p):
    e,a,al,b,v=p;return e+a*np.asarray(N)**(-al)+b*np.asarray(D)**(-v)
def fit_classic(d,starts=6,loss='huber'):
    n,dd,y=xy(d);rng=np.random.default_rng(925);fits=[]
    for j in range(starts):
        t=np.array([np.log(1.5),np.log(.4),.3,np.log(1.2),.3]) if j==0 else np.r_[np.log(rng.uniform(.5,2)),np.log(rng.uniform(.1,2)),rng.uniform(.1,.6),np.log(rng.uniform(.2,3)),rng.uniform(.1,.6)]
        fits.append(least_squares(lambda x:np.log(classic(n,dd,decode(x)))-np.log(y),t,bounds=([-12,-12,.01,-12,.01],[4,8,1.5,8,1.5]),loss=loss,f_scale=.01,max_nfev=3000))
    f=min(fits,key=lambda f:f.cost);return decode(f.x),f
par,basefit=fit_classic(data['B1']);E,A,alpha,B,nu=par
ols,_=fit_classic(data['B1'],loss='linear',starts=3)
display(save_table(pd.DataFrame({'参数':['E','A','alpha','B','nu'],'Huber':par,'对数OLS':ols}),'classic_parameters'))
validation=[];foldpars=[]
n,dd,y=xy(data['B1']);validation.append({'数据':'B1','方法':'全量拟合',**metrics(y,classic(n,dd,par))})
for size in sorted(data['B1'].N_params_B.unique()):
    train=data['B1'][data['B1'].N_params_B!=size];test=data['B1'][data['B1'].N_params_B==size];p,_=fit_classic(train,starts=2)
    n,dd,y=xy(test);validation.append({'数据':'B1','方法':f'留出{size:g}B',**metrics(y,classic(n,dd,p))});foldpars.append(p)
save_table(pd.DataFrame(foldpars,columns=['E','A','alpha','B','nu']).assign(held_N_B=sorted(data['B1'].N_params_B.unique())),'classic_leave_scale_parameters')
b1metrics=save_table(pd.DataFrame(validation),'classic_validation');display(b1metrics)
sizes=sorted(data['B2'].N_params_B.unique());train=data['B2'][data['B2'].N_params_B.isin(sizes[::2])];test=data['B2'][~data['B2'].N_params_B.isin(sizes[::2])]
xn,xd,yl=xy(train);tn,td,ty=xy(test);co=lsq_linear(np.c_[np.ones(len(train)),xn**(-alpha),xd**(-nu)],yl,bounds=(0,np.inf)).x
free,_=fit_classic(train);cross=[{'数据':'B2','方法':'直接迁移到留出规模',**metrics(ty,classic(tn,td,par))},{'数据':'B2','方法':'共享指数+幅度校准',**metrics(ty,np.c_[np.ones(len(test)),tn**(-alpha),td**(-nu)]@co)},{'数据':'B2','方法':'自由指数+幅度校准',**metrics(ty,classic(tn,td,free))}]
tn,td,ty=xy(data['B3']);cross.append({'数据':'B3','方法':'插值一致性，非独立验证',**metrics(ty,classic(tn,td,par))})
coverage=[];source_predictions=[]
for key,groupcol in [('B4','family'),('B5','source')]:
    d=data[key];ys=[];preds={s:[] for s in ['直接迁移','仅偏移','偏移+幅度']}
    for source,g in d.groupby(groupcol):
        coverage.append({'数据':key,'来源':source,'n':len(g),'纳入来源内留一':len(g)>=3})
        if len(g)<3:continue
        for i,row in g.iterrows():
            tr=g.drop(i);n,dd,y=xy(tr);r=classic(n,dd,par)-E;r0=float(classic(row.N_params_B,row.D_tokens_B,par)-E)
            c=lsq_linear(np.c_[np.ones(len(tr)),r],y,bounds=(0,np.inf)).x
            values=[E+r0,max(0,float(np.mean(y-r)))+r0,c[0]+c[1]*r0];ys.append(row.val_loss)
            for name,v in zip(preds,values):
                preds[name].append(v);source_predictions.append({'数据':key,'来源':source,'行':i,'方法':name,'真实':row.val_loss,'预测':v})
    for name,v in preds.items():cross.append({'数据':key,'方法':name+'：来源内留一',**metrics(ys,v)})
    n,dd,y=xy(d);cross.append({'数据':key,'方法':'全部数据直接迁移',**metrics(y,classic(n,dd,par))})
cross=save_table(pd.DataFrame(cross),'cross_source_validation');display(cross)
save_table(pd.DataFrame(source_predictions),'cross_source_predictions');save_table(pd.DataFrame(coverage),'source_coverage')
fig,ax=plt.subplots(1,2,figsize=(11,4))
for size,g in data['B1'].groupby('N_params_B'):
    ax[0].scatter(g.D_tokens_B,g.val_loss,s=4);ax[0].plot(g.D_tokens_B,classic(g.N_params_B,g.D_tokens_B,par),lw=.8,label=f'{size:.2g}B')
ax[0].set(xscale='log',xlabel='D（十亿Token）',ylabel='交叉熵损失',title='B1经典规模项');ax[0].legend(ncol=2,fontsize=7)
sp=pd.DataFrame(source_predictions);sp=sp[sp['方法']=='偏移+幅度']
for k,g in sp.groupby('数据'):ax[1].scatter(g['真实'],g['预测'],s=18,label=k)
lims=[sp['真实'].min(),sp['真实'].max()];ax[1].plot(lims,lims,'k--',lw=1);ax[1].set(xlabel='真实损失',ylabel='留一预测',title='来源校准后的留出验证');ax[1].legend();finish_fig('01_scale_and_sources')
show(f'B1按规模留出的最大RMSE为 **{b1metrics.iloc[1:].RMSE.max():.6f}**。B2共享指数与自由指数在同一留出集比较；B4/B5允许来源校准后再留一，避免把拟合误差当作迁移误差。小残差只说明对所给数据拟合好，不判断其生成性质。')

# %% [markdown]
# ## 3. 质量响应与评分刻度（H2的质量部分）
#
# 附件B质量记为$q_B$，不同于问题一的实数评分$Q$。以$q_{ref}=1$为B实验参考，写作
#
# $$
# u=s_Q(q_B-1),\quad
# L=E+(AN^{-\alpha}+BD^{-\nu})\exp[\theta_Q(1-q_B)],\quad
# \theta_Q=\lambda s_Q.
# $$
#
# $s_Q$是质量刻度转换斜率。没有共同评分样本时，只能估计$\theta_Q$，不能分别识别$\lambda$和$s_Q$；采用$s_Q=0.5,1,2$作为明确的敏感性情景。$q_B=1$与B1基线的关系先用残差检查；这不等于已证明问题一原始配比质量对应$q_B=1$。
#
# B7用于按$(N,D)$组合五折留出；另用B6拟合、预测B7新增质量水平，重合行不作为新增证据。以无质量修正为基线，检验共同修正是否带来预测改善。B8先审计方向，再单独报告纳入敏感性，不因不符合模型就将其异常解释为已知数据错误。

# %%
qkeys=['N_params_B','D_tokens_B','Q_score'];q=data['B7'].drop_duplicates(qkeys).copy();q['z']=1-q.Q_score;q['group']=q.groupby(qkeys[:2]).ngroup()
def quality_predict(d,t):
    n,dd,_=xy(d);return E+(classic(n,dd,par)-E)*np.exp(t*(1-d.Q_score.to_numpy()))
def quality_fit(d,signed=False):
    f=least_squares(lambda t:quality_predict(d,t[0])-d.val_loss.to_numpy(),[.3],bounds=([-8 if signed else 0],[8]),max_nfev=2000);return float(f.x[0])
qa=[]
for key in ['B6','B7','B8']:
    r=[spearmanr(g.Q_score,g.val_loss).statistic for _,g in data[key].groupby(qkeys[:2])]
    qa.append({'数据':key,'ND组数':len(r),'负相关组比例':float(np.mean(np.array(r)<0)),'组内相关中位数':float(np.median(r)),'Loss等于0.5比例':float(np.isclose(data[key].val_loss,.5).mean())})
display(save_table(pd.DataFrame(qa),'quality_direction_audit'))
base_q=q[np.isclose(q.Q_score,1)];n,dd,y=xy(base_q);anchor_residual=float(np.mean(y-classic(n,dd,par)))
print('q_B=1相对B1的平均残差：',anchor_residual)
common=data['B6'].merge(data['B7'],on=qkeys,suffixes=('_6','_7'));assert np.allclose(common.val_loss_6,common.val_loss_7)
new=q.merge(data['B6'][qkeys],on=qkeys,how='left',indicator=True);new=new[new._merge=='left_only']
theta=quality_fit(q);quality_rows=[];qcv=np.zeros(len(q))
for tr,te in GroupKFold(5).split(q,groups=q.group):qcv[te]=quality_predict(q.iloc[te],quality_fit(q.iloc[tr]))
for label,d,p in [('B7全量拟合',q,quality_predict(q,theta)),('ND组合五折留出',q,qcv),('B6→B7新增质量',new,quality_predict(new,quality_fit(data['B6'])))]:
    quality_rows.append({'检验':label,'模型':'共同指数修正',**metrics(d.val_loss,p)})
    quality_rows.append({'检验':label,'模型':'无质量项',**metrics(d.val_loss,quality_predict(d,0))})
qmetrics=save_table(pd.DataFrame(quality_rows),'quality_validation');display(qmetrics)
save_table(q[qkeys+['val_loss']].assign(OOF_prediction=qcv),'quality_oof_predictions')
boots=[]
for _ in range(80):
    chosen=RNG.choice(q.group.unique(),q.group.nunique(),replace=True);sample=pd.concat([q[q.group==g] for g in chosen],ignore_index=True);boots.append(quality_fit(sample))
qci=np.quantile(boots,[.025,.975]);save_table(pd.DataFrame({'theta_Q':boots}),'quality_group_bootstrap')
qmap=save_table(pd.DataFrame([{'s_Q情景':s,'lambda条件值':theta/s,'条件区间下限':qci[0]/s,'条件区间上限':qci[1]/s} for s in [.5,1.,2.]]),'quality_scale_scenarios');display(qmap)
sens=[]
for label,d in [('B8',data['B8']),('B7+B8',pd.concat([q,data['B8']],ignore_index=True))]:
    for signed in [False,True]:
        t=quality_fit(d,signed);sens.append({'数据':label,'允许负系数':signed,'theta_Q':t,'触界':abs(t)<1e-7 or abs(abs(t)-8)<1e-5,**metrics(d.val_loss,quality_predict(d,t))})
display(save_table(pd.DataFrame(sens),'quality_B8_sensitivity'))
fig,ax=plt.subplots(1,2,figsize=(11,4))
n,dd,y=xy(q);normalized=(y-E)/(classic(n,dd,par)-E)
ax[0].scatter(q.Q_score,normalized,s=9,alpha=.3);x=np.linspace(q.Q_score.min(),1,100);ax[0].plot(x,np.exp(theta*(1-x)),color='#E76F51');ax[0].set(xlabel='附件B质量 q_B',ylabel='归一化可约损失',title='共同质量修正：B7半合成数据')
ax[1].scatter(q.val_loss,qcv,s=10,alpha=.6);lims=[q.val_loss.min(),q.val_loss.max()];ax[1].plot(lims,lims,'k--',lw=1);ax[1].set(xlabel='半合成观测Loss',ylabel='ND组合留出预测',title='质量响应留出验证');finish_fig('02_quality')
show(f'共同质量系数 **θ_Q={theta:.4f}**，ND组合留出RMSE为 **{metrics(q.val_loss,qcv)["RMSE"]:.4f}**。区间只描述B7半合成情景内的组重采样变动；刻度转换和真实数据质量效应仍未识别。B8方向不同，不能与B7不加区分地估计一个统一质量响应。')

# %% [markdown]
# ## 4. 对数线性配比与跨尺度迁移（H2的配比部分）
#
# 沿用问题一对数线性配比主模型，以其相对预测损失构造配比修正；模型比较见问题一。
#
# 问题一给出$f(\mathbf p)=c+\sum_i a_i\ln(p_i+0.001)$，定义
#
# $$
# Q_0(\mathbf p)=\sum_i p_iQ_i,\qquad
# h(\mathbf p)=\frac{f(\mathbf p)-f(\mathbf p_0)}{s_L}.
# $$
#
# $\mathbf p_0$取训练平均配比，$s_L$取训练真实13域平均损失的总体标准差。这个变换保留配比排序和最优点，但不自动保留损失差大小。$Q_0$是文档均值与Token份额混合定义的质量指数；17域中11域无直接质量对应，不能解释为全部域均已实测质量。
#
# 原配方实验取$u=0$，在其损失口径下拟合
#
# $$
# L_A=E_A+(A_AN^{-\alpha}+B_AD^{-\nu})e^{\eta h(\mathbf p)}.
# $$
#
# 参数$E_A,A_A,B_A,\eta$仅用校准配方估计。五折按完整配方向量分组，同配方跨尺度始终在同一折；另外完全留出一个模型尺度。问题一已查看过这些检验集，因此本节是事后迁移诊断，不称为全新盲测。按RegMix原论文Table 2匹配，1M/60M训练1B Token，1B训练25B Token；原CSV没有逐运行D字段，结论以这一元数据匹配为条件。

# %%
domains=q1['domain_order'];coef=np.array([q1['log_linear_model']['a_i'][d] for d in domains]);eps=q1['log_linear_model']['epsilon']
Qj=np.array([q1['mixture_domain_Q'][d] for d in domains]);p0=np.array(meta['p0']);sL=meta['s_L'];anchor=meta['anchor_loss']
def mix_score(p):return q1['log_linear_model']['intercept']+np.log(np.asarray(p)+eps)@coef
def h_score(p):return (mix_score(p)-anchor)/sL
assert abs(h_score(p0))<1e-12
parts=[]
for name in ['test_1M','test_60M','test_1B']:
    d=pd.read_csv(HROOT/f'{name}.csv');p=d[domains].to_numpy();assert np.allclose(mix_score(p),d.loglinear_hat)
    d['h']=h_score(p);d['scale']=name;d['N']=meta['datasets'][name]['N_B'];d['D']=meta['datasets'][name]['D_B'];d['group']=[tuple(row) for row in np.round(p,10)];parts.append(d)
mix=pd.concat(parts,ignore_index=True);mix['group']=pd.factorize(mix.group)[0]
def mix_predict(d,t):
    e,a,b=np.exp(t[:3]);return e+(a*d.N.to_numpy()**(-alpha)+b*d.D.to_numpy()**(-nu))*np.exp(t[3]*d.h.to_numpy())
def mix_fit(d,with_h=True,starts=5):
    fits=[]
    for eta0 in np.linspace(.02,.8,starts):
        t=np.r_[np.log([1.3,.15,1.6]),eta0]
        if with_h:
            f=least_squares(lambda x:mix_predict(d,x)-d.loss.to_numpy(),t,bounds=([-12]*3+[0],[5]*3+[3]),max_nfev=3000)
        else:
            f=least_squares(lambda x:mix_predict(d,np.r_[x,0])-d.loss.to_numpy(),t[:3],bounds=([-12]*3,[5]*3),max_nfev=3000);f.x=np.r_[f.x,0]
        fits.append(f)
    return min(fits,key=lambda f:f.cost)
fitmix=mix_fit(mix);mt=fitmix.x;eta=float(mt[3]);mixparams=np.exp(mt[:3])
mr=[];mcv={};splits=list(GroupKFold(5).split(mix,groups=mix.group))
for name,has_h in [('共同配比修正',True),('无配比项',False)]:
    pred=np.zeros(len(mix))
    for tr,te in splits:
        assert not set(mix.iloc[tr].group)&set(mix.iloc[te].group)
        ff=mix_fit(mix.iloc[tr],with_h=has_h,starts=3);pred[te]=mix_predict(mix.iloc[te],ff.x)
    mcv[name]=pred;mr.append({'模型':name,'检验':'配方分组五折-全部',**metrics(mix.loss,pred)})
    for scale,g in mix.groupby('scale'):mr.append({'模型':name,'检验':'配方分组五折-'+scale,**metrics(g.loss,pred[g.index])})
for scale in mix.scale.unique():
    tr=mix[mix.scale!=scale];te=mix[mix.scale==scale];ff=mix_fit(tr,starts=5)
    mr.append({'模型':'共同配比修正','检验':'留尺度-'+scale,**metrics(te.loss,mix_predict(te,ff.x))})
mm=save_table(pd.DataFrame(mr),'mixture_validation');display(mm)
display(save_table(pd.DataFrame({'参数':['E_A','A_A','B_A','eta'],'估计值':[*mixparams,eta]}),'mixture_parameters'))
save_table(mix[['recipe_id','group','scale','N','D','loss','h']].assign(OOF_prediction=mcv['共同配比修正']),'mixture_oof_predictions')
eta_boot=[]
for _ in range(50):
    sample=pd.concat([mix[mix.group==g] for g in RNG.choice(mix.group.unique(),mix.group.nunique(),replace=True)],ignore_index=True)
    eta_boot.append(float(mix_fit(sample,starts=2).x[3]))
etaci=np.quantile(eta_boot,[.025,.975]);save_table(pd.DataFrame({'eta':eta_boot}),'mixture_group_bootstrap')
# 同配方跨尺度排序，仅按配方向量匹配，不按行号或不可靠ID匹配。
rankrows=[]
for a,b in [('test_1M','test_60M'),('test_1M','test_1B'),('test_60M','test_1B')]:
    z=mix[mix.scale==a].merge(mix[mix.scale==b],on='group',suffixes=('_a','_b'))
    rankrows.append({'尺度1':a,'尺度2':b,'匹配配方数':len(z),'Spearman':spearmanr(z.loss_a,z.loss_b).statistic if len(z)>2 else np.nan})
display(save_table(pd.DataFrame(rankrows),'matched_mixture_ranks'))
fig,ax=plt.subplots(1,2,figsize=(11,4))
for scale,g in mix.groupby('scale'):ax[0].scatter(g.loss,mcv['共同配比修正'][g.index],s=13,label=scale)
lims=[mix.loss.min(),mix.loss.max()];ax[0].plot(lims,lims,'k--',lw=1);ax[0].set(xlabel='真实损失',ylabel='配方留出预测',title='共享η，来源A独立校准');ax[0].legend(fontsize=8)
scales=['test_1M','test_60M','test_1B'];inside=[mm.loc[(mm['模型']=='共同配比修正')&(mm['检验']=='配方分组五折-'+s),'RMSE'].iloc[0] for s in scales];outside=[mm.loc[mm['检验']=='留尺度-'+s,'RMSE'].iloc[0] for s in scales]
x=np.arange(3);ax[1].bar(x-.18,inside,.36,label='配方留出');ax[1].bar(x+.18,outside,.36,label='整个尺度留出');ax[1].set_xticks(x,['1M','60M','1B']);ax[1].set(yscale='log',ylabel='RMSE（对数轴）',title='规模外推难于同尺度配方预测');ax[1].legend();finish_fig('03_mixture_transfer')
show(f'配比修正 **η={eta:.4f}**，全体配方分组留出RMSE为 **{metrics(mix.loss,mcv["共同配比修正"])["RMSE"]:.4f}**。较好的配方预测不代表跨尺度绝对损失预测可靠；只用两个尺度校准也可能使基线幅度难以分离，因此留尺度误差同时反映结构假设与覆盖不足。η迁移到B1损失口径仍是未联合验证的假设。')

# %% [markdown]
# ## 5. 边际效用、弹性与质量—规模替代
#
# 记$T_N=A_sN^{-\alpha}$、$T_D=B_sD^{-\nu}$、$R=T_N+T_D$、$\Phi=e^{-\lambda u+\eta h}$。固定配比和来源，损失下降量定义的边际效用为
#
# $$
# -\partial_NL=\frac{\alpha T_N\Phi}{N},\qquad
# -\partial_DL=\frac{\nu T_D\Phi}{D},\qquad
# -\partial_QL=\lambda R\Phi.
# $$
#
# 参数与数据的损失弹性 = 输入相对变化一单位对应的损失相对变化，分别为
#
# $$
# \varepsilon_N=-\frac{\alpha T_N\Phi}{L},\qquad
# \varepsilon_D=-\frac{\nu T_D\Phi}{L}.
# $$
#
# $Q$可为负且其零点是相对参照，不能把$\ln Q$当作普遍有效的坐标。质量半弹性 = 质量增加一分对应的局部损失相对变化，定义为$\partial_Q\ln L=-\lambda R\Phi/L$；同时报告质量增加0.1的有限损失变化。配比的约束弹性在下一节定义。
#
# 固定$D,\mathbf p$，令提高质量$\Delta u$与原质量下增大参数到$N'$具有相同损失，设$r=e^{-\lambda\Delta u}$，则
#
# $$
# \frac{N'}{N}=\left[r+\frac{T_D}{T_N}(r-1)\right]^{-1/\alpha}.
# $$
#
# 方括号$z>0$时存在有限替代；$z=0$时仅$N'\to\infty$达到；$z<0$时无论增加多少参数都无法达到该质量收益。反过来，参数增加$k$倍的等价质量改善为$\Delta u=\lambda^{-1}\ln[R/(k^{-\alpha}T_N+T_D)]$。这些比较不固定算力，仅固定D和配比。
#
# 在只计训练成本$C=6\times10^{18}ND$、固定$u,\mathbf p$的条件下，共同因子抵消，最优条件是$\alpha T_N=\nu T_D$；因此
#
# $$
# N^*=\left(\frac{\alpha A_s}{\nu B_s}\right)^{1/(\alpha+\nu)}
# \left(\frac{C}{6\times10^{18}}\right)^{\nu/(\alpha+\nu)},\quad
# D^*=\frac{C}{6\times10^{18}N^*}.
# $$
#
# 这不是问题三的完整联合最优：质量处理若占用预算，N和D的可用预算仍会变化。若质量处理成本为$D_{raw}[g(Q)-g(Q_0)]_+$，在处理成本激活且仅计训练和处理成本时，质量比增加参数更划算的条件为
#
# $$
# g'(Q)<\frac{6\lambda R N_{raw}}{\alpha T_N}.
# $$
#
# 输出右侧临界边际成本，避免把题设其他质量刻度的成本参数直接作用到本评分；加入注意力成本后需对总成本重新求导。

# %%
def terms(N,D,params=par):
    e,a,al,b,v=params;return a*np.asarray(N)**(-al),b*np.asarray(D)**(-v)
def predict_loss(N,D,u=0.,p=None,s_Q=1.,eta_value=eta,params=par):
    assert s_Q>0
    h=h_score(p0 if p is None else p);tn,td=terms(N,D,params)
    return params[0]+(tn+td)*np.exp(-theta/s_Q*np.asarray(u)+eta_value*h)
def equivalent_ratio(N,D,du,s_Q=1.,params=par):
    tn,td=terms(N,D,params);r=np.exp(-theta/s_Q*du);z=float(r+td/tn*(r-1))
    return (float(z**(-1/params[2])) if z>0 else np.inf),z
marginal=[];sub=[];checks=[]
for n,d in [(1.,20.),(7.,140.),(70.,1400.)]:
    tn,td=terms(n,d);r=tn+td;lam=theta;loss=E+r
    marginal.append({'N_B':n,'D_B':d,'Loss':loss,'参数边际收益_每十亿参数':alpha*tn/n,'数据边际收益_每十亿Token':nu*td/d,'质量边际收益_每分':lam*r,'参数弹性':-alpha*tn/loss,'数据弹性':-nu*td/loss,'质量半弹性':-lam*r/loss,'质量增加0.1损失下降_情景':float(loss-predict_loss(n,d,u=.1)),'g_prime临界_FLOPs每Token每分':6*lam*r*n*1e9/(alpha*tn)})
    expected=[-alpha*tn/n,-nu*td/d,-lam*r]
    for j,x in enumerate([n,d,0.]):
        step=1e-5*max(1,abs(x));plus=[n,d,0.];minus=plus.copy();plus[j]+=step;minus[j]-=step
        num=(predict_loss(*plus)-predict_loss(*minus))/(2*step)
        checks.append({'变量':['N','D','Q'][j],'N_B':n,'D_B':d,'解析':expected[j],'有限差分':float(num),'相对误差':float(abs(num-expected[j])/max(abs(expected[j]),1e-12))})
for s in [.5,1.,2.]:
    for n,d in [(1.,20.),(7.,140.),(70.,1400.),(1000.,20.)]:
        ratio,z=equivalent_ratio(n,d,.1,s_Q=s)
        err=abs(predict_loss(n*ratio,d,s_Q=s)-predict_loss(n,d,u=.1,s_Q=s)) if np.isfinite(ratio) else np.nan
        if np.isfinite(err):assert err<1e-9
        tn,td=terms(n,d);double=np.log((tn+td)/(2**(-alpha)*tn+td))/(theta/s)
        assert np.isclose(predict_loss(n,d,u=double,s_Q=s),predict_loss(2*n,d,s_Q=s))
        sub.append({'s_Q情景':s,'N_B':n,'D_B':d,'质量增加':.1,'等价参数倍数':ratio,'存在条件z':z,'状态':'有限可替代' if z>0 else '参数扩张不可替代','参数翻倍等价质量提升':float(double),'等损失误差':err})
checks=save_table(pd.DataFrame(checks),'derivative_checks');assert checks['相对误差'].max()<1e-5
marginal=save_table(pd.DataFrame(marginal),'marginal_elasticity_cost');display(marginal)
sub=save_table(pd.DataFrame(sub),'quality_parameter_substitution');display(sub)
# 边界与前沿均进行数值核验。
tn,td=terms(7.,140.);critical=np.log((tn+td)/td)/theta
assert abs(equivalent_ratio(7.,140.,critical)[1])<1e-10
assert equivalent_ratio(7.,140.,critical*1.01)[1]<0
front=[]
for c in [1e20,1e22,1e24]:
    ns=(alpha*A/(nu*B))**(1/(alpha+nu))*(c/6e18)**(nu/(alpha+nu));ds=c/6e18/ns
    tn,td=terms(ns,ds);assert np.isclose(alpha*tn,nu*td)
    for u in [0.,.1]:
        opt=minimize_scalar(lambda x:predict_loss(np.exp(x),c/6e18/np.exp(x),u=u),bounds=(np.log(ns)-5,np.log(ns)+5),method='bounded')
        assert abs(opt.x-np.log(ns))<1e-4
        ratio,_=equivalent_ratio(ns,ds,.1)
        front.append({'C_FLOPs':c,'u情景':u,'N_B':ns,'D_B':ds,'Loss':float(predict_loss(ns,ds,u=u)),'质量0.1等价参数倍数':ratio})
front=save_table(pd.DataFrame(front),'conditional_training_frontier');display(front)
show('上表的质量提升采用 **s_Q=1等明确情景**；u>0相对B实验q_ref=1属于向更高质量方向的外推，不能当作已观测收益。解析导数、两向替代等式、不可替代边界和条件前沿均通过数值核验。')

# %% [markdown]
# ## 6. 领域数据之间的替代与组合效应
#
# 领域份额之和为1，增加一个域必须减少其他域。固定额外质量处理水平u，从i向k转移$\delta$，计算$L(p+\delta(e_k-e_i))-L(p)$。在当前可微对数线性模型下，局部方向导数为
#
# $$
# \frac{dL}{d\delta}\bigg|_0
# =(L-E_s)\frac{\eta}{s_L}
# \left(\frac{a_k}{p_k+\varepsilon}-\frac{a_i}{p_i+\varepsilon}\right).
# $$
#
# 为报告每个域的约束弹性，令其他域按原比例减少，域i的份额增加$dp_i$；此时
#
# $$
# \varepsilon_{p_i}^{con}
# =\frac{p_i(L-E_s)\eta}{Ls_L}
# \left[\frac{a_i}{p_i+\varepsilon}
# -\sum_{j\ne i}\frac{p_j}{1-p_i}\frac{a_j}{p_j+\varepsilon}\right].
# $$
#
# 该弹性依赖指定补偿规则，不是无约束偏导的比值。若固定绝对Q而非u，还需加入$Q_0(p)$变化，不能混用两种比较。
#
# 对“互补”，固定补偿域r=pile_cc，取$v=e_i-e_r,w=e_k-e_r$，计算联合变化超过两次单独变化之和的损失差
#
# $$
# I_{ik}=L(p+\delta v+\delta w)-L(p+\delta v)-L(p+\delta w)+L(p).
# $$
#
# $I<0$表示在该基点、补偿域和步长下联合改善更强；$I>0$表示联合改善较弱。对数线性f本身没有自由的跨域交互项，该差值可能来自共享补偿域的曲率及指数链接，不能据其符号证明领域间的因果互补。同时导出f上的对照，并检验步长敏感性。

# %%
n,d=7.,140.;base_loss=float(predict_loss(n,d));grad_h=coef/(p0+eps)/sL
p_elastic=[]
for i,name in enumerate(domains):
    mask=np.arange(len(domains))!=i
    dh=grad_h[i]-np.sum(p0[mask]/(1-p0[i])*grad_h[mask]);effect=(base_loss-E)*eta*dh
    p_elastic.append({'领域':name,'基线份额':p0[i],'每单位份额方向边际损失':effect,'约束弹性':p0[i]*effect/base_loss})
display(save_table(pd.DataFrame(p_elastic).sort_values('约束弹性'),'domain_constrained_elasticity'))
transfer=[];interactions=[];r=domains.index('pile_cc')
for delta in [.001,.005,.01]:
    for i in range(17):
        for k in range(17):
            if i==k or p0[i]<delta:continue
            pp=p0.copy();pp[i]-=delta;pp[k]+=delta
            transfer.append({'转出':domains[i],'转入':domains[k],'delta':delta,'问题一损失差':float(mix_score(pp)-mix_score(p0)),'广义损失差_情景':float(predict_loss(n,d,p=pp)-base_loss),'一阶近似':(base_loss-E)*eta*(grad_h[k]-grad_h[i])*delta})
    assert p0[r]>2*delta
    for i in range(17):
        for k in range(i+1,17):
            if r in [i,k]:continue
            pi=p0.copy();pi[i]+=delta;pi[r]-=delta;pk=p0.copy();pk[k]+=delta;pk[r]-=delta;both=pi+pk-p0
            assert np.all(both>=0) and np.isclose(both.sum(),1)
            points=[both,pi,pk,p0];f=np.array([mix_score(p) for p in points]);ll=np.array([predict_loss(n,d,p=p) for p in points])
            value=float(ll@[1,-1,-1,1]);interactions.append({'域i':domains[i],'域k':domains[k],'补偿域':'pile_cc','delta':delta,'问题一条件交互':float(f@[1,-1,-1,1]),'广义条件交互_情景':value,'解释':'超加性收益' if value<0 else '次加性收益'})
transfer=save_table(pd.DataFrame(transfer),'domain_transfers');interactions=save_table(pd.DataFrame(interactions),'domain_combination_effects')
display(transfer[transfer.delta==.01].sort_values('广义损失差_情景').head(8));display(interactions[interactions.delta==.01].sort_values('广义条件交互_情景').head(8))
# 一个可行方向的导数独立核验，及主模型最优配比的传递。
i=domains.index('arxiv');k=domains.index('stackexchange');v=np.zeros(17);v[k]=1;v[i]=-1;step=1e-6
num=(predict_loss(n,d,p=p0+step*v)-predict_loss(n,d,p=p0-step*v))/(2*step)
assert np.isclose(num,(base_loss-E)*eta*(grad_h[k]-grad_h[i]),rtol=1e-5)
pstar=np.array([q1['p_star'][s] for s in domains]);assert np.all(pstar>=0) and np.isclose(pstar.sum(),1)
assert np.isclose(mix_score(pstar),q1['L_hat_p_star_selected'])
candidates=pd.DataFrame([{'方案':label,'问题一预测Loss':mix_score(p),'h':h_score(p),'Q0':float(p@Qj),'广义Loss_情景':float(predict_loss(n,d,p=p))} for label,p in [('训练平均配比',p0),('均匀配比',np.ones(17)/17),('对数线性KKT配比',pstar)]]);display(save_table(candidates,'mixture_candidates'))
fig,ax=plt.subplots(figsize=(9,6));z=transfer[transfer.delta==.01].pivot(index='转出',columns='转入',values='问题一损失差').reindex(index=domains,columns=domains)
cm=plt.get_cmap('RdBu_r').copy();cm.set_bad('#cccccc');vmax=np.nanmax(abs(z.to_numpy()));im=ax.imshow(z,cmap=cm,vmin=-vmax,vmax=vmax)
ax.set_xticks(range(17),domains,rotation=75,ha='right',fontsize=7);ax.set_yticks(range(17),domains,fontsize=7);ax.set(title='转移1个百分点：对数线性预测损失变化（灰色为不可行/对角）',xlabel='转入领域',ylabel='转出领域');plt.colorbar(im,ax=ax);finish_fig('04_domain_transfer')
show(f'以pile_cc为共同补偿域，在3个转移步长共{len(interactions)}组组合中，交互差I均为正，表现为次加性收益，即联合损失下降少于两个单独下降之和；当前结果不支持在这些方向上宣称互补增益。这是约束与非线性模型下的条件预测。')
show('固定u时，η>0使广义损失关于问题一f严格递增，因此对数线性KKT配比继续最小化本模型的配比部分；这不代表真实训练最优，也不代表加入质量处理成本后仍是联合最优。组合效应表只给出规定补偿方式下的预测效应。')

# %% [markdown]
# 固定$u$代表随配比同步改变基准质量；若坚持固定绝对评分$Q$，则$u=Q-Q_0(p)$随配比变化，转移方向导数需增加质量基准项：
#
# $$
# \left.\frac{dL}{d\delta}\right|_Q=(L-E_s)\left[\frac{\eta}{s_L}\left(\frac{a_k}{p_k+\varepsilon}-\frac{a_i}{p_i+\varepsilon}\right)+\lambda(Q_k-Q_i)\right].
# $$
#
# 两种干预定义不能混用。上节表采用固定额外处理水平$u$，这是承接问题一原始配方实验的口径；固定$Q$的结论还依赖未标定的质量映射。
#
# ## 7. 不确定性、外推与适用范围
#
# 组自助法 = 整组有放回重采样，保留同一实验内的相关性。下列区间仅描述当前输入及拟合方案内的变动，未包含问题一评分误差、来源定义差异和半合成生成机制的不确定性。质量和配比没有联合实验，因此不能用分别较好的拟合替代对H3的检验。
#
# B9仅提供大模型规模元数据；对缺少正训练量的行不计算损失。B10损失是估计值，仅作为外推一致性检查，不作为真实训练验证。指数扰动后重新校准幅度，检查大模型预测和替代量对参数的敏感性。

# %%
# 对同一组留出预测进行配对组重采样，估计加入因素后的MSE改善。
# 固定已得OOF预测，区间未包含重新选模和重训的不确定性。
paired=[]
for label,groups,truth,pred,base in [('质量',q.group.to_numpy(),q.val_loss.to_numpy(),qcv,quality_predict(q,0)),('配比',mix.group.to_numpy(),mix.loss.to_numpy(),mcv['共同配比修正'],mcv['无配比项'])]:
    dg=pd.DataFrame({'group':groups,'gain':(truth-base)**2-(truth-pred)**2}).groupby('group').gain.agg(['sum','count'])
    values=[]
    for _ in range(1000):
        z=dg.iloc[RNG.integers(0,len(dg),len(dg))];values.append(z['sum'].sum()/z['count'].sum())
    lo,hi=np.quantile(values,[.025,.975]);paired.append({'因素':label,'MSE改善':float(np.mean((truth-base)**2-(truth-pred)**2)),'区间下限':lo,'区间上限':hi,'正改善区间':bool(lo>0)})
display(save_table(pd.DataFrame(paired),'paired_group_improvement'))
uncertainty=pd.DataFrame([{'参数':'theta_Q','估计':theta,'2.5%':qci[0],'97.5%':qci[1],'解释':'B7整组重采样；80次'}, {'参数':'eta','估计':eta,'2.5%':etaci[0],'97.5%':etaci[1],'解释':'配方整组重采样；50次'}]);display(save_table(uncertainty,'conditional_uncertainty'))
extrap=data['B9'].copy();valid=np.isfinite(extrap.N_params_B)&np.isfinite(extrap.D_tokens_B)&(extrap.N_params_B>0)&(extrap.D_tokens_B>0)
extrap['B1口径基线预测']=np.nan
extrap.loc[valid,'B1口径基线预测']=classic(extrap.loc[valid,'N_params_B'],extrap.loc[valid,'D_tokens_B'],par)
extrap['状态']=np.where(valid,'情景外推，非实测验证','N或D无效，不预测');save_table(extrap,'large_model_scenarios')
n,dd,y=xy(data['B10']);display(save_table(pd.DataFrame([{'数据':'B10估计Loss，非独立实测',**metrics(y,classic(n,dd,par))}]),'estimated_loss_consistency'))
ns,ds,ys=xy(data['B1']);sensitivity=[]
for fa in [.8,1,1.2]:
    for fv in [.8,1,1.2]:
        aa,vv=alpha*fa,nu*fv;c=lsq_linear(np.c_[np.ones(len(ys)),ns**(-aa),ds**(-vv)],ys,bounds=(0,np.inf)).x
        pp=[c[0],c[1],aa,c[2],vv];tn=c[1]*7**(-aa);td=c[2]*140**(-vv);z=np.exp(-theta*.1)+td/tn*(np.exp(-theta*.1)-1)
        sensitivity.append({'alpha倍数':fa,'nu倍数':fv,'B1_RMSE':metrics(ys,classic(ns,ds,pp))['RMSE'],'70B_1400B基线Loss':float(classic(70,1400,pp)),'7B质量提高0.1等价N倍数_sQ1':float(z**(-1/aa)) if z>0 else np.inf})
display(save_table(pd.DataFrame(sensitivity),'exponent_sensitivity'))
show('H1允许校准后可用于来源内预测，但不能据此声称所有来源共享同一绝对损失；H2在现有质量情景和已覆盖尺度的配方留出上得到有限支持，留尺度误差限制外推；H3仍为工作假设。进一步检验应在相同验证集、分词和训练设置下交叉改变N、D、质量处理强度和配比，给每个处理后的数据重新计算问题一Q，并留出整个处理组合。')

# %% [markdown]
# ## 8. 结果归纳与后续接口
#
# 结果分为三层：规模参数是附件B的拟合结果；质量响应与配比响应分别来自半合成质量实验及RegMix配方实验；将两者组合后的四因素预测和资源替代量是有条件的情景计算。接口显式保留这个区别，不把无法识别的质量刻度设成已知常数。

# %%
qrmse=float(qmetrics.loc[(qmetrics['检验']=='ND组合五折留出')&(qmetrics['模型']=='共同指数修正'),'RMSE'].iloc[0])
qbase=float(qmetrics.loc[(qmetrics['检验']=='ND组合五折留出')&(qmetrics['模型']=='无质量项'),'RMSE'].iloc[0])
mrmse=float(mm.loc[(mm['模型']=='共同配比修正')&(mm['检验']=='配方分组五折-全部'),'RMSE'].iloc[0])
mbase=float(mm.loc[(mm['模型']=='无配比项')&(mm['检验']=='配方分组五折-全部'),'RMSE'].iloc[0])
summary=f'''本版采用共同乘性修正标度律，实际执行得到：

- B1：E={E:.6f}，A={A:.6f}，α={alpha:.6f}，B={B:.6f}，ν={nu:.6f}；按规模留出的最大RMSE为{b1metrics.iloc[1:].RMSE.max():.6f}。
- 质量：θ_Q={theta:.6f}，ND组合留出RMSE由无质量项的{qbase:.6f}降至{qrmse:.6f}，改善{(1-qrmse/qbase)*100:.1f}%。该结论限于附件B质量情景；λ=θ_Q/s_Q仍需刻度标定。
- 配比：η={eta:.6f}，配方分组留出RMSE由{mbase:.6f}降至{mrmse:.6f}，改善{(1-mrmse/mbase)*100:.1f}%。整个尺度留出明显变差，模型适于已覆盖范围内的条件分析，不能据此承诺任意规模外推。
- 已完成边际效用与弹性、满足配比约束的领域替代/组合效应、质量与参数量等损失条件、条件算力最优分配；解析导数及等损失关系已用数值独立核验。

Q允许负值，质量使用半弹性。共同指数修正下，固定质量和配比的训练算力最优N/D分配不受共同乘子影响；质量改善降低损失水平，并不自动改变该分配。领域组合效应受补偿域和非线性链接影响，不是直接估计的领域因果交互。'''
show(summary);(OUT/'results_summary.md').write_text(summary,encoding='utf-8')
interface={'model':'E_s+(A_s*N**(-alpha)+B_s*D**(-nu))*exp(-theta_Q*u/s_Q+eta*h(p))','units':{'N':'billion parameters','D':'billion tokens','compute':'6e18*N*D FLOPs'},'B1':dict(zip(['E','A','alpha','B','nu'],map(float,par))),'RegMix':dict(zip(['E','A','B'],map(float,mixparams))),'theta_Q':theta,'eta':eta,'lambda':None,'s_Q':None,'s_Q_scenarios':[.5,1,2],'domain_order':domains,'Q_domain':Qj.tolist(),'p0':p0.tolist(),'p_star':pstar.tolist(),'log_linear':q1['log_linear_model'],'h_anchor':anchor,'h_scale':sL,'quality_reference_qB':1,'status':{'joint_quality_composition':'untested working hypothesis','quality_to_Q1_mapping':'unidentified','eta_transfer_to_B1':'scenario assumption','large_scale_extrapolation':'limited by failed leave-scale validation'},'metrics':{'quality_group_RMSE':qrmse,'quality_no_term_RMSE':qbase,'mixture_group_RMSE':mrmse,'mixture_no_term_RMSE':mbase},'q1_interface_sha256':meta['interface_sha256']}
(OUT/'q2_interface.json').write_text(json.dumps(interface,ensure_ascii=False,indent=2),encoding='utf-8')
verification={'completed':True,'q1_model':'对数线性混料','q1_input_hash_verified':True,'quality_overlap_verified':True,'recipe_group_leakage_checked':True,'finite_difference_and_equivalence_assertions':'passed','quality_scale_identified':False,'joint_response_validated':False,'notes':'自助区间为条件区间；全部情景结果需要相应来源与评分映射假设。'}
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
print('结果目录：',OUT)

# %% [markdown]
# ### 方法与元数据来源
#
# - Hoffmann等，Training Compute-Optimal Large Language Models：[原论文](https://arxiv.org/abs/2203.15556)，用于经典标度结构和训练算力近似。
# - RegMix：[ICLR 2025原论文](https://proceedings.iclr.cc/paper_files/paper/2025/file/5f67d864aae6115374fed7beddd119e0-Paper-Conference.pdf)，Table 2用于模型规模与Token量匹配。
# - 问题一当前输出及附件B本地说明、source_manifest提供本实验的数据口径；问题一评分与附件B质量变量之间没有已提供的实测标定关系。

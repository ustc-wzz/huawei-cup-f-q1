"""Independent Q2 diagnostics; preserve the frozen model and paper outputs."""
from pathlib import Path
import hashlib
import json
import tempfile
import numpy as np
import pandas as pd
from scipy.optimize import least_squares, lsq_linear
from sklearn.model_selection import GroupKFold
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output_q2_model_evidence'
OUT.mkdir(exist_ok=True)
inputs = {}
def read(path, json_file=False):
    p = ROOT / path
    inputs[path] = hashlib.sha256(p.read_bytes()).hexdigest()
    return json.loads(p.read_text()) if json_file else pd.read_csv(p)
cfg = read('output_q2_shared/q2_interface.json', True)
b1 = read('real_attachments/B_scaling_laws/pythia_training_log_existing.csv')
q = read('output_q2_shared/tables/quality_oof_predictions.csv')
m = read('output_q2_shared/tables/mixture_oof_predictions.csv')
b = cfg['B1']
E,A,B,alpha,nu = [b[k] for k in ['E','A','B','alpha','nu']]
theta,eta = cfg['theta_Q'],cfg['eta']
q['group'] = q.groupby(['N_params_B','D_tokens_B']).ngroup()
names = ['none','parameter','data','common']
labels = ['无修正','仅参数项','仅数据项','共同修正']

def qpred(d, t, kind):
    tn=A*d.N_params_B.to_numpy()**(-alpha)
    td=B*d.D_tokens_B.to_numpy()**(-nu)
    fac=np.exp(t*(1-d.Q_score.to_numpy()))
    return E+tn*(fac if kind in ['parameter','common'] else 1)+td*(fac if kind in ['data','common'] else 1)

def qfit(d, kind):
    if kind=='none': return 0.
    f=least_squares(lambda t:qpred(d,t[0],kind)-d.val_loss.to_numpy(),[.3],bounds=([0],[8]),max_nfev=2000)
    assert f.success
    return float(f.x[0])

def mpred(d,t,kind):
    e,a,b=np.exp(t[:3]); fac=np.exp(t[3]*d.h.to_numpy())
    return e+a*d.N.to_numpy()**(-alpha)*(fac if kind in ['parameter','common'] else 1)+b*d.D.to_numpy()**(-nu)*(fac if kind in ['data','common'] else 1)

def mfit(d,kind):
    fits=[]
    for t0 in np.linspace(.02,.8,3):
        init=np.r_[np.log([1.3,.15,1.6]),t0]
        if kind=='none':
            f=least_squares(lambda t:mpred(d,np.r_[t,0],kind)-d.loss.to_numpy(),init[:3],bounds=([-12]*3,[5]*3),max_nfev=3000)
            f.x=np.r_[f.x,0]
        else:
            f=least_squares(lambda t:mpred(d,t,kind)-d.loss.to_numpy(),init,bounds=([-12]*3+[0],[5]*3+[3]),max_nfev=3000)
        fits.append(f)
    f=min(fits,key=lambda f:f.cost)
    assert f.success
    return f.x

rows=[]; folds=[]
for branch,d,target,fit,predict in [('quality',q,'val_loss',qfit,qpred),('mixture',m,'loss',mfit,mpred)]:
    splits=list(GroupKFold(5).split(d,groups=d.group))
    predictions=d.copy()
    for kind in names:
        pred=np.zeros(len(d))
        for fold,(tr,te) in enumerate(splits):
            assert not set(d.iloc[tr].group)&set(d.iloc[te].group)
            pars=fit(d.iloc[tr],kind)
            pred[te]=predict(d.iloc[te],pars,kind)
            folds.append(dict(branch=branch,kind=kind,fold=fold,n=len(te),RMSE=float(np.sqrt(np.mean((pred[te]-d.iloc[te][target])**2)))))
        rmse=float(np.sqrt(np.mean((pred-d[target])**2)))
        full=fit(d,kind)
        rows.append(dict(branch=branch,kind=kind,n=len(d),RMSE=rmse,coefficient=float(full if branch=='quality' else full[3])))
        predictions[kind]=pred
    predictions.to_csv(OUT/f'{branch}_candidate_oof.csv',index=False)
comp=pd.DataFrame(rows); comp.to_csv(OUT/'candidate_comparison.csv',index=False)
pd.DataFrame(folds).to_csv(OUT/'candidate_folds.csv',index=False)
for branch,old,key in [('quality',q,'quality_group_RMSE'),('mixture',m,'mixture_group_RMSE')]:
    actual=comp.query('branch==@branch and kind=="common"').RMSE.iloc[0]
    assert abs(actual-cfg['metrics'][key])<1e-6,(branch,actual)
print(comp.to_string(index=False),flush=True)

# Profile objectives: nuisance amplitudes are refitted at every grid point.
n,d,y=[b1[c].to_numpy() for c in ['N_params_B','D_tokens_B','val_loss']]
av=np.unique(np.r_[np.linspace(.335,.345,41),alpha])
nv=np.unique(np.r_[np.linspace(.275,.285,41),nu])
profile=[]
for aa in av:
    for vv in nv:
        f=least_squares(lambda z:np.log(np.exp(z[0])+np.exp(z[1])*n**(-aa)+np.exp(z[2])*d**(-vv))-np.log(y),
            np.log([E,A,B]),bounds=([-12]*3,[4,8,8]),loss='huber',f_scale=.01,max_nfev=1000,gtol=1e-12,ftol=1e-12,xtol=1e-12)
        assert f.success
        profile.append(dict(alpha=aa,nu=vv,objective=f.cost))
prof=pd.DataFrame(profile); prof.to_csv(OUT/'exponent_profile.csv',index=False)
qp=pd.DataFrame({'theta':np.unique(np.r_[np.linspace(.15,.65,161),theta])})
qp['RMSE']=[np.sqrt(np.mean((qpred(q,t,'common')-q.val_loss)**2)) for t in qp.theta]
qp.to_csv(OUT/'quality_profile.csv',index=False)
ep=[]
for ee in np.unique(np.r_[np.linspace(.02,.14,161),eta]):
    fac=np.exp(ee*m.h.to_numpy())
    x=np.column_stack([np.ones(len(m)),m.N.to_numpy()**(-alpha)*fac,m.D.to_numpy()**(-nu)*fac])
    f=lsq_linear(x,m.loss.to_numpy(),bounds=(np.exp(-12),np.exp(5)),tol=1e-12)
    assert f.success
    ep.append(dict(eta=ee,RMSE=np.sqrt(np.mean((x@f.x-m.loss)**2))))
ep=pd.DataFrame(ep);ep.to_csv(OUT/'mixture_profile.csv',index=False)
assert abs(qp.loc[qp.RMSE.idxmin(),'theta']-theta)<1e-9
assert abs(ep.loc[ep.RMSE.idxmin(),'eta']-eta)<1e-9
print('Profiles finished.',flush=True)

fontpath=Path(tempfile.gettempdir())/'q2_NotoSansSC_Regular.ttf'
if not fontpath.exists():
    vf=TTFont(str(ROOT/'assets/fonts/NotoSansSC.ttf'))
    instantiateVariableFont(vf,{'wght':400},inplace=True).save(str(fontpath))
font_manager.fontManager.addfont(str(fontpath))
plt.rcParams.update({'font.family':'Noto Sans SC','font.size':9,'axes.titlesize':10,'axes.labelsize':9,
    'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,'legend.frameon':False,
    'axes.spines.top':False,'axes.spines.right':False,'axes.unicode_minus':False,
    'pdf.fonttype':42,'svg.fonttype':'none','mathtext.fontset':'stix','axes.linewidth':.7})
BLUE,ORANGE,GREEN,GRAY='#287BA5','#CC7737','#328776','#959EA5'
colors=[GRAY,ORANGE,GREEN,BLUE]
def export(fig,name):
    for ext in ['png','pdf','svg']: fig.savefig(OUT/f'{name}.{ext}',dpi=600,facecolor='white')
    svg=OUT/f'{name}.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    # Smaller Python-rendered preview for visual QA, not a substitute deliverable.
    fig.savefig(OUT/f'{name}_preview.png',dpi=150,facecolor='white')
    plt.close(fig)

fig,axes=plt.subplots(1,2,figsize=(7.2,3.2))
fig.subplots_adjust(left=.09,right=.99,bottom=.20,top=.83,wspace=.33)
for ax,branch,title in zip(axes,['quality','mixture'],['(a)  质量：按ND组合留出','(b)  配比：按完整配方留出']):
    vals=comp.query('branch==@branch').set_index('kind').loc[names,'RMSE'].to_numpy()
    ax.bar(np.arange(4),vals,color=colors,width=.65)
    for i,v in enumerate(vals):ax.text(i,v+max(vals)*.035,f'{v:.4f}',ha='center',fontsize=8)
    ax.set_xticks(np.arange(4),labels,rotation=18,ha='right')
    ax.set(ylabel='五折留出预测 RMSE',ylim=(0,max(vals)*1.24))
    ax.set_title(title,loc='left',pad=12)
    ax.set_axisbelow(True);ax.grid(axis='y',alpha=.18)
export(fig,'01_model_comparison')

fig,axes=plt.subplots(1,3,figsize=(8.5,3.05))
fig.subplots_adjust(left=.075,right=.98,bottom=.23,top=.81,wspace=.60)
ax=axes[0];zz=prof.pivot(index='nu',columns='alpha',values='objective').to_numpy()
levels=[1,5,20,50,100]
cs=ax.contour(av,nv,zz/zz.min()-1,levels=levels,colors=[BLUE],linewidths=.8)
ax.clabel(cs,fmt='%g',fontsize=7)
ax.scatter([alpha],[nu],color=ORANGE,marker='*',s=65,zorder=5)
ax.set(xlabel=r'参数指数 $\alpha$',ylabel=r'数据指数 $\nu$')
ax.set_title('(a)  两个指数的联合估计',loc='left',pad=12)
ax.text(.03,.91,rf'$\alpha={alpha:.4f},\ \nu={nu:.4f}$',transform=ax.transAxes,fontsize=8,bbox=dict(facecolor='white',edgecolor='none',pad=1))
ax.text(.02,.03,r'$J/J_{\min}-1$'+' 等值线',transform=ax.transAxes,fontsize=8,bbox=dict(facecolor='white',edgecolor='none',pad=1))
for ax,data,xcol,chosen,col,title,xlabel in [
    (axes[1],qp,'theta',theta,BLUE,'(b)  质量系数',r'$\theta_Q=\lambda s_Q$'),
    (axes[2],ep,'eta',eta,GREEN,'(c)  配比系数',r'$\eta$')]:
    ax.plot(data[xcol],data.RMSE,color=col,lw=1.8)
    yy=float(data.loc[(data[xcol]-chosen).abs().idxmin(),'RMSE'])
    ax.scatter([chosen],[yy],color=ORANGE,zorder=4,s=25)
    ax.axvline(chosen,color=ORANGE,ls='--',lw=.8)
    ax.text(.05,.89,f'估计值 {chosen:.4f}',transform=ax.transAxes,fontsize=8)
    ax.set(xlabel=xlabel,ylabel='全量拟合 RMSE')
    ax.set_title(title,loc='left',pad=12);ax.grid(alpha=.18)
export(fig,'02_parameter_profiles')

fig,axes=plt.subplots(1,2,figsize=(7.2,3.5))
fig.subplots_adjust(left=.10,right=.98,bottom=.19,top=.84,wspace=.36)
ax=axes[0]
nn=np.geomspace(n.min(),n.max(),150);dd=np.geomspace(d.min(),d.max(),150)
ax.loglog(nn,A*nn**(-alpha),color=BLUE,lw=2,label=rf'$AN^{{-\alpha}}$, $\alpha={alpha:.3f}$')
ax.loglog(dd,B*dd**(-nu),color=ORANGE,lw=2,ls='--',label=rf'$BD^{{-\nu}}$, $\nu={nu:.3f}$')
ax.axhline(E,color=GRAY,ls=':',lw=1.3,label=rf'$E={E:.3f}$')
ax.set(xlabel=r'规模（B；$N$与$D$同轴）',ylabel='损失分项贡献')
ax.set_title('(a)  两项规模收益逐渐递减',loc='left',pad=13)
ax.legend(loc='lower left',fontsize=8);ax.grid(alpha=.18)
ax=axes[1]
nx=np.geomspace(n.min()/1.25,n.max()*1.25,180)
dx=np.geomspace(d.min()/1.5,d.max()*1.5,180)
xx,yy=np.meshgrid(nx,dx);loss=E+A*xx**(-alpha)+B*yy**(-nu)
cs=ax.contour(xx,yy,loss,levels=[2,2.2,2.5,3,3.5,4,4.5],cmap='cividis',linewidths=.9)
ax.clabel(cs,fmt='%.1f',fontsize=7)
ax.scatter(n,d,s=3,color=GRAY,alpha=.25,rasterized=True,label='B1检查点')
equal=(B/A)**(1/nu)*nx**(alpha/nu)
optimal=(nu*B/(alpha*A))**(1/nu)*nx**(alpha/nu)
ax.plot(nx,equal,color=ORANGE,lw=1.5,ls='--',label='两项贡献相等')
ax.plot(nx,optimal,color=BLUE,lw=1.5,ls='-.',label='固定算力最优分配')
ax.scatter([7],[140],marker='*',color=GREEN,s=85,zorder=5)
ax.annotate('(7, 140)',(7,140),xytext=(-6,-23),textcoords='offset points',fontsize=8,color=GREEN,ha='right')
ax.set(xscale='log',yscale='log',xlim=(nx.min(),nx.max()),ylim=(dx.min(),dx.max()),xlabel=r'参数量 $N$（B）',ylabel=r'数据量 $D$（B）')
ax.set_title('(b)  等损失线与规模分配',loc='left',pad=13)
ax.legend(loc='lower left',fontsize=7.3,facecolor='white',frameon=True,framealpha=.9,edgecolor='none')
export(fig,'03_scaling_geometry')
pd.DataFrame({'N':nx,'equal_contribution_D':equal,'compute_optimal_D':optimal}).to_csv(OUT/'scaling_ridges.csv',index=False)
pd.DataFrame({'N':nn,'parameter_term':A*nn**(-alpha),'D':dd,'data_term':B*dd**(-nu)}).to_csv(OUT/'scaling_contributions.csv',index=False)
pd.DataFrame({'N':xx.ravel(),'D':yy.ravel(),'loss':loss.ravel()}).to_csv(OUT/'loss_contours.csv',index=False)
for path,expected in inputs.items(): assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected
(OUT/'verification.json').write_text(json.dumps({'input_sha256':inputs,'frozen_inputs_unchanged':True,
    'common_oof_reproduced_tolerance':1e-6,'group_overlap':False,'profile_minima_checked':['theta_Q','eta'],
    'profile_exponent_minimum':prof.loc[prof.objective.idxmin()].to_dict(),
    'comparison':rows,'note':'RMSE curves are training profiles, not uncertainty intervals. Existing model is unchanged.'},ensure_ascii=False,indent=2))
print('All figures and source data exported.',flush=True)

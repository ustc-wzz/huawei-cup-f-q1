"""Plot Q2 paper evidence from frozen outputs; no fitting or raw-data access."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output_q2_paper'
OUT.mkdir(exist_ok=True)
TAB = ROOT / 'output_q2_shared/tables'
inputs = {}

def read(name):
    path = TAB / f'{name}.csv'
    inputs[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return pd.read_csv(path)

path = ROOT / 'output_q2_shared/q2_interface.json'
inputs[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
cfg = json.loads(path.read_text())
font_path=Path(tempfile.gettempdir())/'q2_NotoSansSC_Regular.ttf'
if not font_path.exists():
    vf=TTFont(str(ROOT/'assets/fonts/NotoSansSC.ttf'))
    instantiateVariableFont(vf,{'wght':400},inplace=True).save(str(font_path))
font_manager.fontManager.addfont(str(font_path))
plt.rcParams.update({'font.family': 'Noto Sans SC', 'font.size': 9,
    'axes.titlesize': 10, 'axes.labelsize': 9, 'axes.spines.top': False,
    'axes.spines.right': False, 'axes.linewidth': .7, 'xtick.labelsize': 8,
    'ytick.labelsize': 8, 'legend.fontsize': 8, 'legend.frameon': False,
    'axes.unicode_minus': False, 'svg.fonttype': 'none', 'pdf.fonttype': 42,
    'savefig.facecolor': 'white'})
BLUE, ORANGE, GRAY = '#3579A8', '#C97840', '#929BA3'
GREEN = '#428779'

def export(fig, name):
    for ext in ['png', 'pdf', 'svg']:
        fig.savefig(OUT / f'{name}.{ext}', dpi=600)
    svg=OUT/f'{name}.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)

def panel(ax, label, title):
    ax.set_title(f'{label}  {title}', loc='left', pad=13, fontweight='normal')

def one(df, **matches):
    z = df
    for key, value in matches.items():
        z = z[z[key] == value]
    assert len(z) == 1, matches
    return z.iloc[0]

q, m = read('quality_validation'), read('mixture_validation')
rows = []
for label, df, split, baseline, corrected in [
    ('质量', q, 'ND组合五折留出', '无质量项', '共同指数修正'),
    ('配比', m, '配方分组五折-全部', '无配比项', '共同配比修正')]:
    a = one(df, 检验=split, 模型=baseline)
    b = one(df, 检验=split, 模型=corrected)
    rows.append({'comparison': label, 'n': int(b['n']), 'baseline_RMSE': a.RMSE,
                 'corrected_RMSE': b.RMSE, 'reduction_pct': 100*(1-b.RMSE/a.RMSE)})
evidence = pd.DataFrame(rows)
evidence.to_csv(OUT/'01_correction_comparison.csv', index=False)
transfer = []
for scale in ['1M', '60M', '1B']:
    a = one(m, 检验=f'配方分组五折-test_{scale}', 模型='共同配比修正')
    b = one(m, 检验=f'留尺度-test_{scale}', 模型='共同配比修正')
    transfer.append({'scale': scale, 'n': int(a['n']), 'recipe_RMSE': a.RMSE,
                     'held_scale_RMSE': b.RMSE})
scales = pd.DataFrame(transfer)
scales.to_csv(OUT/'01_scale_validation.csv', index=False)
fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.35), gridspec_kw={'width_ratios':[1, 1.02]})
fig.subplots_adjust(left=.09, right=.98, bottom=.22, top=.79, wspace=.38)
ax = axes[0]
x = np.arange(2)
ax.bar(x-.17, evidence.baseline_RMSE, .31, color=GRAY, label='无修正')
ax.bar(x+.17, evidence.corrected_RMSE, .31, color=BLUE, label='有修正')
for i, row in evidence.iterrows():
    for xx, val in [(i-.17, row.baseline_RMSE), (i+.17, row.corrected_RMSE)]:
        ax.text(xx, val+.006, f'{val:.4f}', ha='center', fontsize=8)
    ax.text(i, .298, f'误差降低 {row.reduction_pct:.1f}%', ha='center', color=BLUE, fontsize=8)
ax.set_xticks(x, ['质量修正\nB7半合成 · n=450', '配比修正\n配方记录 · n=576'])
ax.set(ylabel='留出预测 RMSE', ylim=(0, .335))
ax.legend(loc='upper left', bbox_to_anchor=(-.08, 1.28), ncol=2, columnspacing=.9)
panel(ax, 'a', '加入修正后的预测改善')
ax = axes[1]
x = np.arange(3)
ax.bar(x-.17, scales.recipe_RMSE, .31, color=BLUE, label='配方分组留出')
ax.bar(x+.17, scales.held_scale_RMSE, .31, color=ORANGE, label='完整尺度留出')
for i, row in scales.iterrows():
    for xx, val in [(i-.17, row.recipe_RMSE), (i+.17, row.held_scale_RMSE)]:
        ax.text(xx, val*1.16, f'{val:.3f}', ha='center', fontsize=7.5)
ax.set(yscale='log', ylim=(.015, 16), ylabel='RMSE（对数轴）')
ax.set_xticks(x, ['1M\nn=256', '60M\nn=256', '1B\nn=64'])
ax.legend(loc='upper left', bbox_to_anchor=(-.10, 1.28), ncol=2, columnspacing=.7, fontsize=7.5)
panel(ax, 'b', '跨尺度绝对预测仍有不足')
export(fig, '01_correction_effectiveness')

b = cfg['B1']
E, A, B, alpha, nu = [b[k] for k in ['E', 'A', 'B', 'alpha', 'nu']]
theta, eta = cfg['theta_Q'], cfg['eta']
N, D = 7., 140.
tn, td = A*N**(-alpha), B*D**(-nu)
base = E+tn+td

def ratio(du, s):
    rho = np.exp(-theta*np.asarray(du)/s)
    z = rho+(td/tn)*(rho-1)
    return np.where(z>0, np.maximum(z, 1e-300)**(-1/alpha), np.inf)

du = np.linspace(0, .20, 201)
curves = []
fig, ax = plt.subplots(figsize=(7, 3.5))
fig.subplots_adjust(left=.12, right=.81, bottom=.19, top=.88)
styles = [(0.5, ORANGE, '--'), (1., BLUE, '-'), (2., GREEN, ':')]
for s, color, ls in styles:
    values = ratio(du, s)
    assert np.all(np.isfinite(values)) and np.all(np.diff(values)>0)
    assert np.allclose(E+tn*values**(-alpha)+td,
                       E+(tn+td)*np.exp(-theta*du/s), atol=1e-12)
    critical = float(s/theta*np.log((tn+td)/td))
    for u, v in zip(du, values):
        curves.append({'delta_u':u, 's_Q':s, 'parameter_multiplier':v,
                       'critical_delta_u':critical, 'N_B':N, 'D_B':D})
    ax.plot(du, values, color=color, ls=ls, lw=1.8)
    ax.text(.204, values[-1], f'$s_Q={s:g}$', va='center', color=color)
    v = float(ratio(.1, s))
    ax.scatter([.1], [v], color=color, zorder=5, s=24)
    position = {0.5:(.105,2.8), 1.:(.13,1.62), 2.:(.14,1.07)}[s]
    ax.annotate(f'{v:.3f} 倍', (.1,v), xytext=position,
                arrowprops={'arrowstyle':'-','color':color,'lw':.65},color=color,fontsize=8)
ax.axvline(.1, color=GRAY, lw=.8, ls='--', zorder=0)
ax.axhline(1, color='#CBD1D5', lw=.8, zorder=0)
ax.set(xlim=(0,.20), ylim=(.85, max(ratio(du,.5))*1.09),
       xlabel='额外质量增量 Δu', ylabel='等损失参数倍数 N′ / N')
ax.set_xticks([0,.05,.1,.15,.2])
ax.set_title('初始 7B 参数、固定 140B Token 的条件替代关系', loc='left', pad=12)
ax.text(.02,.94, '质量刻度取三种情景\n固定数据量与配比，不固定算力',
        transform=ax.transAxes, va='top', color='#555555', fontsize=8)
export(fig, '02_quality_parameter_substitution')
pd.DataFrame(curves).to_csv(OUT/'02_substitution_curves.csv', index=False)
existing = read('quality_parameter_substitution')
for s, _, _ in styles:
    row = one(existing, **{'s_Q情景':s, 'N_B':N, 'D_B':D})
    assert np.isclose(ratio(.1,s), row['等价参数倍数'], rtol=1e-12)

domains = cfg['domain_order']
p0 = np.array(cfg['p0'])
coeff = np.array([cfg['log_linear']['a_i'][d] for d in domains])
eps = cfg['log_linear']['epsilon']
def loss(p):
    assert np.all(p>=0) and np.isclose(p.sum(),1)
    f = cfg['log_linear']['intercept']+coeff@np.log(p+eps)
    h = (f-cfg['h_anchor'])/cfg['h_scale']
    return float(E+(tn+td)*np.exp(eta*h))

donor = domains.index('pile_cc')
effects=[]
for target in domains:
    if target == 'pile_cc': continue
    pp=p0.copy(); pp[donor]-=.01; pp[domains.index(target)]+=.01
    effects.append({'target':target, 'loss_change':loss(pp)-base})
ordered = sorted(effects, key=lambda v:v['loss_change'])
chosen = [ordered[0], ordered[(len(ordered)-1)//2], ordered[-1]]
df = pd.DataFrame(ordered)
df['selected'] = df.target.isin([item['target'] for item in chosen])
df.to_csv(OUT/'03_all_fixed_donor_directions.csv', index=False)
responses=[]
fig, axes = plt.subplots(1,2,figsize=(7,3.45),gridspec_kw={'width_ratios':[1.13,1]})
fig.subplots_adjust(left=.11,right=.98,bottom=.20,top=.83,wspace=.48)
ax=axes[0]
for item, color, ls in zip(chosen,[BLUE,GRAY,ORANGE],['-','--',':']):
    vals=[]
    for delta in np.linspace(0,.01,101):
        pp=p0.copy(); pp[donor]-=delta; pp[domains.index(item['target'])]+=delta
        v=loss(pp)-base; vals.append(v)
        responses.append({'donor':'pile_cc','recipient':item['target'],
                          'delta':delta,'loss_change':v,'final_loss':v+base})
    ax.plot(np.linspace(0,1,101),np.array(vals)*1000,label=item['target'],color=color,ls=ls,lw=1.6)
ax.axhline(0,color='#BBC2C7',lw=.8)
ax.set(xlabel='从 pile_cc 转出的份额（百分点）',ylabel=r'最终损失变化（$\times 10^{-3}$）',xlim=(0,1))
ax.legend(loc='lower left',fontsize=8)
panel(ax,'a','相同转出域下比较调整方向')
ax.text(.02,.98,'负值表示损失降低',transform=ax.transAxes,va='top',fontsize=8,color='#555555')
ax=axes[1]
candidates=read('mixture_candidates')
values=[]
for name,p in [('训练平均配比',p0),('均匀配比',np.ones(17)/17),('对数线性KKT配比',np.array(cfg['p_star']))]:
    val=loss(p); saved=one(candidates,方案=name)['广义Loss_情景']
    assert np.isclose(val,saved,rtol=1e-12)
    values.append(val)
ax.axvline(base,color=GRAY,lw=.8,ls='--')
for i,(val,color) in enumerate(zip(values,[GRAY,GREEN,BLUE])):
    ax.plot([val,base],[i,i],color=color,lw=1.3)
    ax.scatter([val],[i],color=color,s=34,zorder=5)
    ax.annotate(f'{val:.6f}',(val,i),xytext=(0,10),textcoords='offset points',ha='center',fontsize=8)
    if i:
        ax.annotate(f'ΔL = {val-base:.6f}',(val,i),xytext=(0,-17),textcoords='offset points',ha='center',fontsize=7.5,color=color)
ax.set_yticks(range(3),['训练平均','均匀','候选配比'])
ax.set(ylim=(2.6,-.65),xlim=(min(values)-.004,base+.004),xlabel='统一模型的最终预测损失')
ax.set_xticks([2.17,2.18])
panel(ax,'b','完整配比方案的预测收益')
export(fig,'03_mixture_loss_response')
pd.DataFrame(responses).to_csv(OUT/'03_transfer_curves.csv',index=False)
candidates.to_csv(OUT/'03_candidate_losses.csv',index=False)
old=read('domain_transfers')
max_error=0.
for item in effects:
    saved=one(old,转出='pile_cc',转入=item['target'],delta=.01)['广义损失差_情景']
    max_error=max(max_error,abs(saved-item['loss_change']))
assert max_error<1e-12
report={'version':'v0.9.11','fit_recomputed':False,'inputs_sha256':inputs,
        'frozen_B1_parameters':b,'theta_Q':theta,'eta':eta,
        'reference':{'N_B':N,'D_B':D,'u':0,'mixture':'p0'},
        'validation_comparison':rows,'selected_directions':chosen,
        'selection_rule':'min / lower median / max of all 16 recipients at delta=0.01, donor pile_cc',
        'transfer_max_abs_difference_from_existing_csv':max_error,
        'substitution_equal_loss_check':True,'existing_substitution_match':True,
        'candidate_loss_match':True,'figure_count':3,'visual_qa':'pending'}
(OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'figures':3,'selected_directions':chosen,'base_loss':base},ensure_ascii=False))

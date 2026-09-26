"""Reproducible publication diagram of the implemented historical Q4 model.

Contract: display T→M→x→Z→S and T→Z, with equation-level noise.
Dashed U links describe sensitivity assumptions, not an estimated latent model.
Standalone figure export; no numerical results or notebooks are modified.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.path import Path as MPath
from repro_runtime import configure_fonts


def draw():
    configure_fonts()
    available = {f.name for f in font_manager.fontManager.ttflist}
    if 'Arial Unicode MS' in available:
        plt.rcParams['font.family'] = ['Arial Unicode MS']
    plt.rcParams.update({'font.size': 12, 'mathtext.fontset': 'stix',
                         'pdf.fonttype': 42, 'svg.fonttype': 'none',
                         'axes.unicode_minus': False})
    fig = plt.figure(figsize=(15, 7), facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1]); ax.set(xlim=(0,15), ylim=(0,7)); ax.axis('off')
    ink, blue, teal, orange = '#243747', '#366A8B', '#347E7A', '#AF784A'
    def text(x,y,s,size=12,color=ink,**kw):
        return ax.text(x,y,s,fontsize=size,color=color,ha='center',va='center',**kw)
    def box(x,y,w,h,fc,ec):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,
            boxstyle='round,pad=0.015,rounding_size=0.10',fc=fc,ec=ec,lw=1.25))
    def arrow(points,color=blue,dashed=False,lw=1.6):
        path=MPath(points,[MPath.MOVETO]+[MPath.LINETO]*(len(points)-1))
        ax.add_patch(FancyArrowPatch(path=path,arrowstyle='-|>',mutation_scale=14,
                    linewidth=lw,color=color,linestyle=(0,(4,3)) if dashed else '-',zorder=2))
    ax.text(.55,6.58,'时间、规模与能力：结构中介模型',ha='left',va='center',fontsize=20,color=ink,weight='bold')
    ax.text(.55,6.20,'历史归因的计算结构  ·  第四问',ha='left',va='center',fontsize=11,color='#75828C')
    y=3.90
    nodes=[(1.45,1.85,'#F1F5F8',blue,r'$T$','时间','技术时代代理'),
           (4.25,2.10,'#EAF2F7',blue,r'$M=(\ln N,\,\ln D)$','规模中介','参数量与训练数据量'),
           (7.15,2.10,'#EAF2F7',blue,r'$x(M)$','标度响应','承接第二问'),
           (10.15,2.10,'#EAF4F1',teal,r'$Z$','变换后的能力','综合分的 logit 变换'),
           (13.20,2.20,'#EAF4F1',teal,r'$S$','综合能力分','六任务等权聚合')]
    for x,w,fc,ec,sym,title,sub in nodes:
        box(x,y,w,1.38,fc,ec)
        text(x,y+.34,sym,19,ec); text(x,y-.10,title,13);text(x,y-.43,sub,10,'#667681')
    for a,b in [(2.39,3.18),(5.32,6.08),(8.22,9.08),(11.22,12.08)]:
        arrow([(a,y),(b,y)],teal if a>10 else blue)
    text(7.15,4.82,'规模传导路径',11,blue)
    arrow([(1.45,4.61),(1.45,5.62),(10.15,5.62),(10.15,4.61)],teal)
    text(6.00,5.64,'非规模技术路径  ·  剩余时间效应的解释假设',12,teal,
         bbox=dict(facecolor='white',edgecolor='none',pad=6))
    text(4.25,5.10,r'$\varepsilon_M$  规模扰动',11,blue)
    arrow([(4.25,4.94),(4.25,4.61)],blue,lw=1.2)
    text(11.70,5.10,r'$\varepsilon_Y$  能力与评测扰动',11,teal)
    arrow([(11.1,4.94),(10.62,4.61)],teal,lw=1.2)
    text(11.65,3.38,'逆 logit',9,'#667681')
    # U is deliberately segregated from the fitted solid-arrow structure.
    box(7.15,2.08,3.20,.86,'#FAF4ED',orange)
    text(7.15,2.22,r'$U$  未观测共同影响因素',12,orange)
    text(7.15,1.89,'仅用于敏感性分析',10,'#8B7764')
    arrow([(5.54,2.08),(4.25,2.08),(4.25,3.19)],orange,True,1.3)
    arrow([(8.76,2.08),(10.15,2.08),(10.15,3.19)],orange,True,1.3)
    text(4.25,2.82,'潜在混杂',9,orange,bbox=dict(facecolor='white',edgecolor='none',pad=3))
    text(10.15,2.82,'潜在混杂',9,orange,bbox=dict(facecolor='white',edgecolor='none',pad=3))
    ax.plot([.55,14.45],[1.32,1.32],color='#DCE3E8',lw=.9)
    text(4.00,.98,r'$M=a_0+a_TT+\varepsilon_M$',15)
    text(10.10,.98,r'$Z=\beta_0+\kappa x(M)+\gamma T+\varepsilon_Y$',15)
    text(4.00,.53,r'$x(M)=-\ln\!\left(AN^{-\alpha}+BD^{-\nu}\right)$',14)
    text(10.10,.53,r'$S=100\,\mathrm{expit}(Z)=100/(1+e^{-Z})$',14)
    text(7.50,.19,r'实线：主模型计算路径    虚线：敏感性分析    识别假设：$\varepsilon_M\perp\varepsilon_Y$',10,'#667681')
    dest=ROOT/'figures'/'q4_causal_publication'; dest.parent.mkdir(exist_ok=True)
    for suffix in ['png','pdf','svg']:
        fig.savefig(dest.with_suffix('.'+suffix),dpi=600,facecolor='white')
    fig.savefig('/tmp/q4_causal_preview.png',dpi=140,facecolor='white')
    plt.close(fig)
    print(dest.with_suffix('.png'))

if __name__=='__main__': draw()

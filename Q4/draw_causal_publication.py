"""Node-only diagram of the implemented Q4 model, exported at 600 dpi.

Solid paths: T→M→x→Z→S and T→Z; equation-level disturbances enter M/Z.
Dashed U links represent sensitivity analysis, not a fitted latent variable.
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
    if 'Arial Unicode MS' in {f.name for f in font_manager.fontManager.ttflist}:
        plt.rcParams['font.family'] = ['Arial Unicode MS']
    plt.rcParams.update({'font.size': 12, 'mathtext.fontset': 'stix',
                         'pdf.fonttype': 42, 'svg.fonttype': 'none',
                         'axes.unicode_minus': False})
    fig=plt.figure(figsize=(15,5),facecolor='white')
    ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,15),ylim=(0,5));ax.axis('off')
    def node(x,y,w,h,lines,tone="blue"):
        fill,edge,ink = {
            "blue": ("#E8F2FE", "#CFDFF2", "#326D9E"),
            "green": ("#EAF5EC", "#CFE4D4", "#477858"),
            "orange": ("#FFF0E1", "#EDD8C2", "#996B3C"),
        }[tone]
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,
            boxstyle='round,pad=0.02,rounding_size=0.14',
            facecolor=fill,edgecolor=edge,linewidth=1.0,zorder=3))
        ax.text(x,y,lines,ha='center',va='center',fontsize=13,
                color=ink,linespacing=1.6,zorder=4)
    def arrow(points,dashed=False):
        path=MPath(points,[MPath.MOVETO]+[MPath.LINETO]*(len(points)-1))
        ax.add_patch(FancyArrowPatch(path=path,arrowstyle='-|>',mutation_scale=11,
            linewidth=1.15,color='#8393A3',linestyle=(0,(4,3)) if dashed else '-',zorder=1))
    y=3.25
    node(1.45,y,2.05,.90,'$T$：时间\n技术时代代理')
    node(4.35,y,2.20,.90,'$M$：规模中介\n$(\\ln N,\\,\\ln D)$')
    node(7.25,y,2.20,.90,'$x(M)$：标度响应\n承接第二问')
    node(10.25,y,2.20,.90,'$Z$：能力变换\n$\\operatorname{logit}(S/100)$',tone="green")
    node(13.35,y,2.25,.90,'$S$：综合能力分\n六任务等权聚合',tone="green")
    for a,b in [(2.50,3.23),(5.47,6.13),(8.37,9.13),(11.37,12.20)]:
        arrow([(a,y),(b,y)])
    node(4.35,4.50,2.20,.58,'$\\varepsilon_M$：规模扰动',tone="orange")
    node(10.25,4.50,2.65,.58,'$\\varepsilon_Y$：能力与评测扰动',tone="orange")
    arrow([(4.35,4.19),(4.35,3.72)])
    arrow([(10.25,4.19),(10.25,3.72)])
    node(7.25,1.78,3.10,.90,'$U$：未观测共同影响因素\n仅用于敏感性分析',tone="orange")
    arrow([(5.68,1.78),(4.35,1.78),(4.35,2.78)],True)
    arrow([(8.82,1.78),(9.80,1.78),(9.80,2.78)],True)
    arrow([(1.45,2.78),(1.45,.57),(10.65,.57),(10.65,2.78)])
    dest=ROOT/'figures'/'q4_causal_publication';dest.parent.mkdir(exist_ok=True)
    for ext in ['png','pdf','svg']:
        fig.savefig(dest.with_suffix('.'+ext),dpi=600,facecolor='white')
    fig.savefig('/tmp/q4_causal_preview.png',dpi=140,facecolor='white')
    plt.close(fig)
    print(dest.with_suffix('.png'))

if __name__=='__main__': draw()

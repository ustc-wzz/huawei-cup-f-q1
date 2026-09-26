from pathlib import Path
import sys, shutil, json
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'Q4'),str(ROOT)]
import plots
import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox
OUT=ROOT/'Q4/paper_restructure_v0924/assets'
plots.setup()
from matplotlib import font_manager
font_manager.fontManager.addfont(str(ROOT/"assets/fonts/NotoSansSC-Regular.ttf"))
plt.rcParams["font.family"]=["Noto Sans SC Diagram"]
def capture(fig,name):
    if name=='04_frontier_forecasts':groups=[('frontier',[0]),('broad_forecast',[1])]
    else:groups=[('historical_validation',[0,1]),('broad_validation',[2])]
    for ax in fig.axes:
        ax.set_axisbelow(True);ax.grid(axis='y',alpha=.7)
    for label,indices in groups:
        for i,ax in enumerate(fig.axes):ax.set_visible(i in indices)
        for i in indices:
            if len(indices)==1:fig.axes[i].set_title('')
        fig.canvas.draw()
        boxes=[fig.axes[i].get_tightbbox(fig.canvas.get_renderer()) for i in indices]
        bbox=Bbox.union(boxes).transformed(fig.dpi_scale_trans.inverted()).expanded(1.025,1.025)
        for ext in ['png','svg','pdf']:fig.savefig(OUT/f'{label}.{ext}',bbox_inches=bbox,dpi=400)
    for svg in OUT.glob('*.svg'):svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)
plots.export=capture
plots.forecast_plot();plots.validation_plot()
for filename in ['q4_causal_publication.png','fig_39_q4_mediation_and_sensitivity.png']:
    shutil.copy2(ROOT/'figures'/filename,OUT/filename)
print('Saved four separated evidence panels and two source figures.')

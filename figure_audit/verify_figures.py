"""Check publication exports and unchanged numeric tables; create contact sheets."""
from pathlib import Path
import hashlib,json,re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'figure_audit'

def run():
    baseline=json.loads((OUT/'before_table_hashes.json').read_text())
    changed=[p for p,h in baseline.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    numbered=[]
    for path in (ROOT/'figures').glob('*.svg'):
        if re.search(r'图\s*\d+\s',path.read_text()): numbered.append(path.name)
    outputs=[]
    for num in range(1,21):
        svg=next((ROOT/'figures').glob(f'fig_{num:02d}_*.svg'))
        assert svg.with_suffix('.png').exists() and svg.with_suffix('.pdf').exists()
        ET.parse(svg)
        outputs.append(svg.with_suffix('.png'))
    t5=outputs[4].with_suffix('.svg').read_text()
    t6=outputs[5].with_suffix('.svg').read_text()
    assert 'Pearson 相关系数' in t5 and 'Person' not in t5
    assert '反向相关最强的指标对' not in t6 and '(c)' not in t6
    assert '(a)' in t6 and '(b)' in t6
    assert not changed,changed
    assert not numbered,numbered
    for page in range(4):
        fig,axes=plt.subplots(2,3,figsize=(18,11),facecolor='#eeeeee')
        for ax in axes.flat:ax.axis('off')
        for ax,path in zip(axes.flat,outputs[page*5:(page+1)*5]):
            ax.imshow(mpimg.imread(path));ax.set_title(path.stem,fontsize=9)
        fig.tight_layout();fig.savefig(OUT/f'contact_{page+1}.png',dpi=130);plt.close(fig)
    result={'numbered_titles_remaining_all_figures':numbered,'q1_png_svg_pdf_sets':len(outputs),
            'unchanged_result_tables':len(baseline),'changed_result_tables':changed,
            'figure5_pearson_label':True,'figure6_two_panel_labels':True}
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':run()

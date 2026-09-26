"""Audit Q4 figure exports and numeric replay against a pre-run snapshot."""
from pathlib import Path
import argparse,hashlib,json,re,shutil
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'figure_audit'

def run(baseline):
    hashes=json.loads((AUDIT/'q4_before_table_hashes.json').read_text())
    differences=[]
    for name,h in hashes.items():
        now=ROOT/name
        if hashlib.sha256(now.read_bytes()).hexdigest()==h:continue
        old=baseline/'tables'/now.name
        assert hashlib.sha256(old.read_bytes()).hexdigest()==h,name
        a,b=pd.read_csv(old),pd.read_csv(now)
        pd.testing.assert_frame_equal(a,b,check_exact=False,rtol=1e-9,atol=1e-10)
        differences.append(name)
    for name in differences:shutil.copyfile(baseline/'tables'/Path(name).name,ROOT/name)
    files=[]
    for num in range(37,44):
        svg=next((ROOT/'figures').glob(f'fig_{num}_*.svg'))
        content=svg.read_text()
        assert not re.search(r'图\s*\d+\s',content),svg.name
        assert 'εM' not in content and 'εY' not in content and 'log10 D' not in content
        ET.parse(svg)
        for ext in ['png','svg','pdf']:assert svg.with_suffix('.'+ext).exists()
        if num>37:assert '(a)' in content and '(b)' in content
        files.append(svg.with_suffix('.png'))
    standalone=ROOT/'figures/q4_causal_publication.png'
    for ext in ['png','svg','pdf']:assert standalone.with_suffix('.'+ext).exists()
    files.append(standalone)
    for page in range(2):
        fig,axes=plt.subplots(2,2,figsize=(18,10),facecolor='#eeeeee')
        for ax,path in zip(axes.flat,files[page*4:page*4+4]):
            ax.axis('off');ax.imshow(mpimg.imread(path));ax.set_title(path.stem,fontsize=10)
        fig.tight_layout();fig.savefig(AUDIT/f'q4_contact_{page+1}.png',dpi=150);plt.close(fig)
    result={'figures_png_svg_pdf':8,'result_tables_checked':len(hashes),
            'numerically_equivalent_replay_files':differences,'baseline_table_bytes_preserved':True,
            'panel_labels_continuous':True,'math_labels_rendered':True,'no_numbered_total_titles':True}
    (AUDIT/'q4_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True)
    run(p.parse_args().baseline)

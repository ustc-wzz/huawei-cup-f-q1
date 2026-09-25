"""Build and execute the Q3 notebook using this interpreter, without global kernel changes."""
from pathlib import Path
import json,sys,tempfile
import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'Q3/notebook_source.py';target=ROOT/'0925_问题三.ipynb'
cells=[];kind=None;lines=[]
def append():
    if kind is None:return
    text='\n'.join(lines).strip('\n')
    if kind=='markdown':
        text='\n'.join(x[2:] if x.startswith('# ') else '' if x=='#' else x for x in text.splitlines())
        cells.append(nbformat.v4.new_markdown_cell(text))
    else:cells.append(nbformat.v4.new_code_cell(text))
for line in source.read_text().splitlines():
    if line.startswith('# %%'):
        append();kind='markdown' if '[markdown]' in line else 'code';lines=[]
    else:lines.append(line)
append()
nb=nbformat.v4.new_notebook(cells=cells,metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}})
def start(cell,cell_index,**kw):
    if cell.cell_type=='code':print(f'Executing cell {cell_index}: {cell.source.splitlines()[0][:70]}',flush=True)
def done(cell,cell_index,**kw):
    nbformat.write(nb,target)
    if cell.cell_type=='code':print(f'Completed cell {cell_index}',flush=True)
with tempfile.TemporaryDirectory(prefix='q3-kernel-') as tmp:
    folder=Path(tmp)/'q3-local';folder.mkdir()
    (folder/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],
        'display_name':'Q3 current Python','language':'python'}))
    km=KernelManager(kernel_name='q3-local',kernel_spec_manager=KernelSpecManager(kernel_dirs=[tmp]))
    try:
        NotebookClient(nb,km=km,timeout=1200,resources={'metadata':{'path':str(ROOT)}},
                       on_cell_start=start,on_cell_executed=done).execute()
    finally:
        if km.has_kernel:km.shutdown_kernel(now=True)
        nbformat.write(nb,target)
assert all(c.execution_count is not None for c in nb.cells if c.cell_type=='code')
assert not any(o.output_type=='error' for c in nb.cells for o in c.get('outputs',[]))
print('All Q3 notebook cells executed successfully.',flush=True)

# Reproducible delivery checks (visual inspection is recorded separately).
import hashlib
written=nbformat.read(target,as_version=4)
assert [c.source for c in written.cells]==[c.source for c in cells]
manifest=json.loads((ROOT/'output_q3_resource/input_manifest.json').read_text())
assert all(hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256'] for r in manifest)
figures=sorted((ROOT/'output_q3_resource/figures').glob('*.png'))
assert all(p.with_suffix('.pdf').is_file() for p in figures)
checks={'status':'passed','notebook_cells':len(written.cells),
        'executed_code_cells':sum(c.cell_type=='code' for c in written.cells),
        'mirror_exact':True,'all_input_hashes_current':True,'no_error_outputs':True,
        'figures_png_pdf_pairs':len(figures)}
(ROOT/'output_q3_resource/delivery_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(checks,ensure_ascii=False),flush=True)

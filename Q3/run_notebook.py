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

"""从文本镜像生成并实际执行固定主notebook。"""
from pathlib import Path
import nbformat
from nbclient import NotebookClient
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'Q2/notebook_source.py'
cells=[];kind=None;lines=[]
def append():
    if kind is None:return
    text='\n'.join(lines).strip('\n')
    if kind=='markdown':
        text='\n'.join(line[2:] if line.startswith('# ') else '' if line=='#' else line for line in text.splitlines())
        cells.append(nbformat.v4.new_markdown_cell(text))
    else:cells.append(nbformat.v4.new_code_cell(text))
for line in source.read_text().splitlines():
    if line.startswith('# %%'):
        append();kind='markdown' if '[markdown]' in line else 'code';lines=[]
    else:lines.append(line)
append()
n=nbformat.v4.new_notebook(cells=cells,metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}})
p=ROOT/'0924_问题二.ipynb'
def start(cell,cell_index,**kw):
    if cell.cell_type=='code':print(f'执行 {cell_index}: {cell.source.splitlines()[0][:60]}',flush=True)
def done(cell,cell_index,**kw):
    nbformat.write(n,p)
    if cell.cell_type=='code':print(f'完成 {cell_index}',flush=True)
try:
    NotebookClient(n,timeout=600,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}},on_cell_start=start,on_cell_executed=done).execute()
finally:nbformat.write(n,p)
assert all(not any(o.output_type=='error' for o in c.get('outputs',[])) for c in n.cells)
print('全部运行通过',flush=True)

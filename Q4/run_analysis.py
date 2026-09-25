"""Run all Q4 numerical experiments using only local attachments and Q1-3 interfaces."""
import hashlib, importlib.metadata, json, time
from pathlib import Path
from data_pipeline import ROOT, OUT, CD, read_data, aggregate_c8, dump
from evolution_model import mediation_analysis, bridge_analysis, coupled_forecast, broad_analysis

def provenance(started):
    paths=[p for p in CD.glob('*.csv')]+[ROOT/'output_q2_shared/q2_interface.json',ROOT/'output_q3_resource/config.json',
      ROOT/'Q3/resource_model.py',ROOT/'0924_F题_问题一.ipynb',ROOT/'0924_问题二.ipynb',ROOT/'0925_问题三.ipynb',
      ROOT/'notebook_source.py',ROOT/'Q2/notebook_source.py',ROOT/'Q3/notebook_source.py']
    dump([dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths],'input_manifest')
    dump({k:importlib.metadata.version(k) for k in ['numpy','pandas','scipy','matplotlib','scikit-learn','nbformat','nbclient','ipykernel']},'versions')
    dump(dict(elapsed_seconds=time.time()-started,data_source='local attachments only',seed=20260925,
              bootstrap_replicates=400,status='numerical analysis completed'),'execution')

def run():
    started=time.time()
    clean,nd,epoch,paired=read_data()
    print(f'Data: {len(clean)} screened models; {len(nd)} complete ND models.',flush=True)
    c8,c8audit=aggregate_c8(clean);print('C8:',c8audit,flush=True)
    med,val=mediation_analysis(nd);print('Mediation:',med.to_string(index=False),flush=True)
    bridge,bmodels,bmetrics=bridge_analysis();print('Bridge:',bmetrics.to_string(index=False),flush=True)
    pred=coupled_forecast(nd,epoch,clean.date.max(),bmodels)
    print('Coupled forecast:',pred.query('technical_half_life_months==24').to_string(index=False),flush=True)
    broad,metrics=broad_analysis(clean,epoch);print('Broad validation:',metrics.to_string(index=False),flush=True)
    provenance(started)
    return clean,nd

if __name__=='__main__':run()

"""Verify numeric replay against hash-matched baseline; retain stable interfaces."""
from pathlib import Path
import hashlib,json,math,shutil
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'F题_四问完整复现包_v0.9.5'
OUT=ROOT/'figure_audit'

def equal_json(a,b):
    if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(equal_json(a[k],b[k]) for k in a)
    if isinstance(a,list):return isinstance(b,list) and len(a)==len(b) and all(equal_json(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and not isinstance(a,bool):return np.isclose(a,b,rtol=1e-9,atol=1e-10,equal_nan=True)
    return a==b

def run():
    baseline=json.loads((OUT/'before_table_hashes.json').read_text())
    changes=[]
    for name,h in baseline.items():
        old,new=BASE/name,ROOT/name
        assert hashlib.sha256(old.read_bytes()).hexdigest()==h, name
        if hashlib.sha256(new.read_bytes()).hexdigest()==h:continue
        record={'file':name}
        if '.csv' in name:
            a,b=pd.read_csv(old),pd.read_csv(new)
            assert a.shape==b.shape and list(a.columns)==list(b.columns),name
            maximum=0.0
            for col in a:
                x,y=a[col],b[col]
                xn,yn=pd.to_numeric(x,errors='coerce'),pd.to_numeric(y,errors='coerce')
                numeric=xn.notna() | yn.notna()
                assert np.allclose(xn[numeric],yn[numeric],rtol=1e-9,atol=1e-10,equal_nan=True), (name,col)
                textmask=~numeric
                assert x[textmask].fillna('').equals(y[textmask].fillna('')), (name,col)
                if numeric.any():maximum=max(maximum,float(np.nanmax(abs(xn[numeric].astype(float)-yn[numeric].astype(float)))))
            record['max_absolute_numeric_difference']=maximum
        elif name.endswith('.json'):
            assert equal_json(json.loads(old.read_text()),json.loads(new.read_text())),name
            record['numeric_equivalent']=True
        else:raise AssertionError(name)
        changes.append(record)
    # All checks must pass before stable baseline bytes are restored.
    for record in changes:shutil.copyfile(BASE/record['file'],ROOT/record['file'])
    report={'tables_checked':len(baseline),'relative_tolerance':1e-9,'absolute_tolerance':1e-10,
            'replay_differences':changes,'baseline_bytes_retained':True,
            'reason':'重跑的浮点尾数与gzip时间戳差异；数值等价核验通过后保留原表字节及下游接口哈希。'}
    (OUT/'numeric_replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Numeric tables verified:',len(baseline),'Equivalent replay differences:',len(changes))
if __name__=='__main__':run()

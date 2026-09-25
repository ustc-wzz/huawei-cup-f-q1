"""同步已验证的四问代码和结果到本地完整包，更新哈希清单及ZIP。原始附件仅保留本地。"""
from pathlib import Path
import hashlib,json,shutil,zipfile
from run_all import NOTEBOOKS,verify_delivery
from refresh_reports import refresh

ROOT=Path(__file__).resolve().parent
PACKAGE=ROOT/'F题_四问完整复现包'

def build():
    for i in range(1,5):verify_delivery(i)
    refresh()
    for name in NOTEBOOKS+['notebook_source.py','run_all.py','refresh_reports.py','论文正文.md','CHANGELOG.md','revision_v080.json']:
        shutil.copy2(ROOT/name,PACKAGE/name)
    for name in ['Q2','Q3','Q4']:
        target=PACKAGE/name
        if target.exists():shutil.rmtree(target)
        target.mkdir()
    for name in ['Q2/notebook_source.py','Q2/export_q1_inputs.py','Q2/run_shared.py']:
        shutil.copy2(ROOT/name,PACKAGE/name)
    for name in ['Q3','Q4']:
        for p in (ROOT/name).iterdir():
            if p.suffix in ('.py','.md','.txt'):shutil.copy2(p,PACKAGE/name/p.name)
    shutil.copytree(ROOT/'Q3/quality_audit',PACKAGE/'Q3/quality_audit',ignore=shutil.ignore_patterns('*.log','__pycache__','.DS_Store'))
    for name in ['output_q1','output_q2_shared','output_q3_resource','output_q4_evolution']:
        # Q1 includes only the active result branch, not historical experiments.
        src=ROOT/name/('length_domain_calibrated22' if name=='output_q1' else '')
        dst=PACKAGE/name
        if dst.exists():shutil.rmtree(dst)
        if name=='output_q1':dst=dst/'length_domain_calibrated22'
        shutil.copytree(src,dst,ignore=shutil.ignore_patterns('__pycache__','.DS_Store','*.log'))
    shutil.copy2(ROOT/'repro_requirements.txt',PACKAGE/'requirements.txt')
    entries=[]
    for p in sorted(PACKAGE.rglob('*')):
        if p.is_file() and p.name not in ('PACKAGE_MANIFEST.json','.DS_Store') and '__pycache__' not in p.parts:
            entries.append(dict(path=str(p.relative_to(PACKAGE)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    (PACKAGE/'PACKAGE_MANIFEST.json').write_text(json.dumps(dict(format_version=1,release='v0.8.0',files=len(entries),entries=entries),ensure_ascii=False,indent=2)+'\n')
    archive=ROOT/'F题_四问完整复现包.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for record in entries+[{ 'path':'PACKAGE_MANIFEST.json'}]:
            p=PACKAGE/record['path'];z.write(p,p.relative_to(ROOT))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    print(f'完整包已同步：{len(entries)}文件；ZIP校验通过。',flush=True)

if __name__=='__main__':build()

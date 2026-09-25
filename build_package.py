"""同步已验证的四问代码和结果到本地完整包，更新哈希清单及ZIP。原始附件仅保留本地。"""
from pathlib import Path
import argparse,hashlib,json,re,shutil,tempfile,zipfile
from run_all import NOTEBOOKS,verify_delivery
from refresh_reports import refresh

ROOT=Path(__file__).resolve().parent
DELIVERIES=ROOT/'交付版本'

def populate(PACKAGE, version):
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
    readme=PACKAGE/'README.md'
    readme.write_text(re.sub(r'v\d+\.\d+\.\d+',version,readme.read_text()))
    # README must be finalized before hashing.
    for record in entries:
        if record['path']=='README.md':
            record.update(bytes=readme.stat().st_size,sha256=hashlib.sha256(readme.read_bytes()).hexdigest())
    (PACKAGE/'PACKAGE_MANIFEST.json').write_text(json.dumps(dict(format_version=1,release=version,files=len(entries),entries=entries),ensure_ascii=False,indent=2)+'\n')
    archive=PACKAGE.parent/f'F题_四问完整复现包_{version}.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for record in entries+[{ 'path':'PACKAGE_MANIFEST.json'}]:
            p=PACKAGE/record['path'];z.write(p,Path(PACKAGE.name)/p.relative_to(PACKAGE))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    print(f'完整包已同步：{len(entries)}文件；ZIP校验通过。',flush=True)

def build(version, base=None):
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',version):
        raise ValueError('版本格式必须为v主版本.次版本.修订号')
    target=DELIVERIES/version
    if target.exists():
        raise FileExistsError(f'版本已存在，拒绝覆盖：{target}')
    if base is None:
        versions=[p for p in DELIVERIES.glob('v*') if re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',p.name)]
        if not versions:raise FileNotFoundError('没有基础完整包，请通过--base-package指定')
        base=max(versions,key=lambda p:tuple(map(int,p.name[1:].split('.'))))/'F题_四问完整复现包'
    base=Path(base)
    if not (base/'real_attachments').is_dir():
        raise FileNotFoundError(f'基础完整包缺少附件：{base}')
    DELIVERIES.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.building-',dir=DELIVERIES) as tmp:
        stage=Path(tmp)/version
        package=stage/'F题_四问完整复现包'
        shutil.copytree(base,package,ignore=shutil.ignore_patterns('__pycache__','.DS_Store'))
        populate(package,version)
        # Final publication fails rather than replacing an existing release.
        if target.exists():raise FileExistsError(target)
        stage.rename(target)
    print(f'版本快照已保存：{target}',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='创建新版本完整包；不覆盖已有版本')
    parser.add_argument('--version',required=True,help='例如v0.8.1')
    parser.add_argument('--base-package',type=Path,help='基础完整包；默认使用最新版本附件')
    args=parser.parse_args()
    build(args.version,args.base_package)

"""创建带版本号的独立完整包；保留既有ZIP和目录。"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,tempfile,zipfile
from run_all import NOTEBOOKS,MIRRORS,verify_delivery
from refresh_reports import refresh
from repro_runtime import prepare_inputs,sha256

ROOT=Path(__file__).resolve().parent

def build(version='v0.9.5',include_cache=True):
    import re
    if not re.fullmatch(r'v\d+\.\d+\.\d+',version):raise ValueError('版本号格式需为v0.9.0')
    name='F题_四问完整复现包_'+version
    target=ROOT/name;archive=ROOT/(name+'.zip')
    if target.exists() or archive.exists():raise FileExistsError('版本已存在，保留旧包；请指定新的--version')
    prepare_inputs(ROOT)
    for i in range(1,5):verify_delivery(i)
    refresh()
    with tempfile.TemporaryDirectory(prefix='.package-',dir=ROOT) as tmp:
        package=Path(tmp)/name;package.mkdir()
        names=NOTEBOOKS+MIRRORS+['run_all.py','repro_runtime.py','python_bootstrap.py','bootstrap_uv.json','signal_cache.py','repro_inputs.json',
            'refresh_reports.py','build_figures_doc.py','四问结果分析与论文插图.docx','Q1/模型建立.md','Q2/模型建立.md','公式完整性核查.md','formula_verification.json','论文正文.md','CHANGELOG.md','run_windows.bat','run_macos.command']
        for relative in names:
            dest=package/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,dest)
        for folder in ['Q2','Q3','Q4']:
            for p in (ROOT/folder).iterdir():
                if p.is_file() and p.suffix in ('.py','.md','.txt') and (folder!='Q2' or p.name in ['export_q1_inputs.py','run_shared.py','notebook_source.py']):
                    shutil.copy2(p,package/folder/p.name)
        ignore=shutil.ignore_patterns('__pycache__','.DS_Store','*.log')
        shutil.copytree(ROOT/'Q3/quality_audit',package/'Q3/quality_audit',ignore=ignore)
        for folder in ['figures','output_q1/length_domain_calibrated22','output_q2_shared','output_q3_resource','output_q4_evolution','assets/fonts']:
            shutil.copytree(ROOT/folder,package/folder,ignore=ignore)
        # Only manifest-listed original inputs; never rely on a cache as the sole source.
        manifest=json.loads((ROOT/'repro_inputs.json').read_text(encoding='utf-8'))
        for record in manifest['files']:
            dest=package/record['path'];dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/record['path'],dest)
        if include_cache:
            shutil.copytree(ROOT/'real_attachments/A_data_value/signals_cache',package/'real_attachments/A_data_value/signals_cache',ignore=ignore)
        shutil.copy2(ROOT/'repro_requirements.txt',package/'requirements.txt')
        (package/'README.md').write_text((ROOT/'PACKAGE_README.md').read_text(encoding='utf-8').replace('v0.9.2',version),encoding='utf-8')
        if (ROOT/'portability_verification.json').exists():shutil.copy2(ROOT/'portability_verification.json',package/'portability_verification.json')
        # Check the package itself, without generating caches in no-cache packages.
        for record in manifest['files']:assert sha256(package/record['path'])==record['sha256']
        entries=[dict(path=str(p.relative_to(package)),bytes=p.stat().st_size,sha256=sha256(p)) for p in sorted(package.rglob('*')) if p.is_file()]
        (package/'PACKAGE_MANIFEST.json').write_text(json.dumps(dict(format_version=1,release=version,includes_cache=include_cache,files=len(entries),entries=entries),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        zipped=Path(tmp)/(name+'.zip')
        with zipfile.ZipFile(zipped,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(package.rglob('*')):
                if p.is_file():z.write(p,Path(name)/p.relative_to(package))
        with zipfile.ZipFile(zipped) as z:assert z.testzip() is None
        package.rename(target);zipped.rename(archive)
    print(f'交付完成：{archive}；{len(entries)}个文件；保留旧版本。',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',default='v0.9.5')
    parser.add_argument('--without-cache',action='store_true')
    args=parser.parse_args();build(args.version,not args.without_cache)

"""标准库启动检查、附件定位与跨平台绘图支持。导入本模块不需要第三方库。"""
from pathlib import Path
import hashlib,importlib.metadata,json,os,struct,subprocess,sys,venv

ROOT=Path(__file__).resolve().parent

def requirements_path(root):
    return next((root/name for name in ['requirements.txt','repro_requirements.txt'] if (root/name).is_file()))

def dependency_errors(requirements):
    errors=[]
    for line in Path(requirements).read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        name,version=line.split('==')
        try:actual=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:actual='未安装'
        if actual!=version:errors.append(f'{name}: {actual} → {version}')
    if not errors:
        try:
            # Validate imports as well as distribution metadata (including compiled libraries).
            import numpy,pandas,scipy,sklearn,matplotlib,seaborn,pyarrow,joblib,nbformat,nbclient,ipykernel,jupyter_client
        except Exception as error:errors.append(f'依赖无法导入：{error}')
    return errors

def ensure_environment(entry, arguments):
    """已有合适环境则复用；否则只安装到包内独立环境，不修改系统Python。"""
    root=Path(entry).resolve().parent
    os.environ['PYTHONUTF8']='1';os.environ['PYTHONIOENCODING']='utf-8'
    for stream in [sys.stdout,sys.stderr]:
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
    if sys.version_info[:2] not in [(3,12),(3,13)] or struct.calcsize('P')!=8:
        raise RuntimeError('此复现包需要64位Python 3.12或3.13；推荐Python 3.12。当前为 '+sys.version.split()[0])
    if not sys.flags.utf8_mode:
        raise SystemExit(subprocess.call([sys.executable,'-X','utf8',str(entry),*arguments],cwd=root))
    requirements=requirements_path(root)
    errors=dependency_errors(requirements)
    if not errors:
        print('Python及依赖检查通过；使用：'+sys.executable,flush=True);return
    environment=root/'.repro-env'
    python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    probe="import sys;sys.path.insert(0,sys.argv[1]);from repro_runtime import dependency_errors;errors=dependency_errors(sys.argv[2]);print('\\n'.join(errors));sys.exit(bool(errors))"
    if python.is_file():
        existing=subprocess.run([str(python),'-X','utf8','-c',probe,str(root),str(requirements)],cwd=root,capture_output=True,text=True,encoding='utf-8')
        if existing.returncode==0:
            print('复用已准备的包内独立环境，无需安装依赖。',flush=True)
            raise SystemExit(subprocess.call([str(python),'-X','utf8',str(entry),*arguments],cwd=root))
    print('正在准备包内独立环境（首次需要联网）：\n'+'\n'.join(errors),flush=True)
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(python),'-X','utf8','-m','ensurepip','--upgrade'],cwd=root,check=True)
    command=[str(python),'-X','utf8','-m','pip','install','--only-binary=:all:','-r',str(requirements)]
    subprocess.run(command,cwd=root,check=True)
    subprocess.run([str(python),'-X','utf8','-c',probe,str(root),str(requirements)],cwd=root,check=True)
    raise SystemExit(subprocess.call([str(python),'-X','utf8',str(entry),*arguments],cwd=root))

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def prepare_inputs(root=ROOT):
    """输入从入口所在目录定位，与终端当前目录无关；缓存不是必要输入。"""
    import shutil
    root=Path(root)
    target=root/'real_attachments'
    if not target.is_dir():
        for candidate in [root/'附件/real_attachments',root/'附件',root.parent/'real_attachments']:
            if (candidate/'A_data_value').is_dir() and (candidate/'B_scaling_laws').is_dir():
                print('自动定位附件：'+str(candidate),flush=True)
                shutil.copytree(candidate,target,dirs_exist_ok=True);break
    manifest=json.loads((root/'repro_inputs.json').read_text(encoding='utf-8'))
    missing=[];changed=[]
    for record in manifest['files']:
        path=root/record['path']
        if not path.is_file():missing.append(record['path'])
        elif sha256(path)!=record['sha256']:changed.append(record['path'])
    if missing or changed:
        raise FileNotFoundError('原始附件不完整或损坏，请将ZIP完整解压后运行。\n缺少：'+', '.join(missing[:8])+'\n校验不符：'+', '.join(changed[:8]))
    (target/'A_data_value/signals_cache').mkdir(parents=True,exist_ok=True)
    print(f'原始输入完整性检查通过：{len(manifest["files"])}个文件；缺失缓存会自动生成。',flush=True)

def configure_fonts():
    """每个新内核注册随包字体，不依赖系统安装或联网。"""
    from matplotlib import font_manager,rcParams,ft2font
    font=ROOT/'assets/fonts/NotoSansSC.ttf'
    if font.is_file():
        font_manager.fontManager.addfont(str(font))
        family=font_manager.FontProperties(fname=str(font)).get_name()
        candidate=str(font)
    else:
        family=None;candidate=None
        for name in ['Microsoft YaHei','SimHei','Noto Sans CJK SC','PingFang SC','Arial Unicode MS']:
            try:candidate=font_manager.findfont(name,fallback_to_default=False)
            except ValueError:continue
            if all(ord(ch) in ft2font.FT2Font(candidate).get_charmap() for ch in '中文质量参数'):family=name;break
        if family is None:raise RuntimeError('缺少中文字体，请重新完整解压ZIP中的assets/fonts目录')
    if not all(ord(ch) in ft2font.FT2Font(candidate).get_charmap() for ch in '中文质量参数'):
        raise RuntimeError('中文字体文件损坏或不含中文字形')
    rcParams.update({'font.family':'sans-serif','font.sans-serif':[family,'DejaVu Sans'],
                     'axes.unicode_minus':False,'pdf.fonttype':42})
    return family
